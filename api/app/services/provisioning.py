"""Managed database provisioning on this host (MariaDB + MongoDB containers).

Public contract (used by the projects router):

- `provision_managed_source(db, project, kind, name)` creates a database plus a dedicated user that
  can only access it, and adds a `DataSource` row to the session (caller commits).
- `drop_managed_source(db, data_source)` drops the database and its user (does not delete the row).

Every generated identifier is validated against a strict regex before being interpolated into
DDL (MariaDB/Mongo user management statements can't use bound parameters for identifiers).
"""

from __future__ import annotations

import logging
import re
import secrets
import string
from functools import lru_cache
from typing import Any, Literal

from pymongo import MongoClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import encrypt_json
from app.errors import ApiError
from app.models import DataSource, Project, new_id, utcnow
from app.services import connections

log = logging.getLogger(__name__)

DB_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
GENERATED_DB_NAME_RE = re.compile(r"^p_[a-z0-9_]{1,55}_[0-9a-f]{6}$")
USER_RE = re.compile(r"^u_[0-9a-f]{12}$")
PASSWORD_RE = re.compile(r"^[A-Za-z0-9]{32}$")
_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def _check(regex: re.Pattern[str], value: str, what: str) -> str:
    if not regex.fullmatch(value):
        raise ValueError(f"Refusing to use invalid {what}: {value!r}")
    return value


def generate_database_name(slug: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (slug or "project").lower().replace("-", "_"))
    base = re.sub(r"_+", "_", base).strip("_") or "project"
    name = f"p_{base[:55]}_{secrets.token_hex(3)}"
    return _check(GENERATED_DB_NAME_RE, name, "database name")


def generate_username() -> str:
    return _check(USER_RE, f"u_{secrets.token_hex(6)}", "user name")


def generate_password() -> str:
    return _check(PASSWORD_RE, "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(32)), "password")


# ---------------------------------------------------------------------------------------------
# root connections
# ---------------------------------------------------------------------------------------------


@lru_cache
def mariadb_root_engine() -> Engine:
    s = get_settings()
    url = URL.create(
        "mysql+pymysql",
        username="root",
        password=s.mariadb_root_password or None,
        host=s.mariadb_host,
        port=s.mariadb_port,
        query={"charset": "utf8mb4"},
    )
    return create_engine(
        url,
        isolation_level="AUTOCOMMIT",
        pool_size=1,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": connections.CONNECT_TIMEOUT_S},
    )


@lru_cache
def mongo_root_client() -> MongoClient:
    s = get_settings()
    return MongoClient(
        host=s.mongo_host,
        port=s.mongo_port,
        username=s.mongo_root_username or None,
        password=s.mongo_root_password or None,
        authSource="admin",
        serverSelectionTimeoutMS=connections.CONNECT_TIMEOUT_S * 1000,
        connectTimeoutMS=connections.CONNECT_TIMEOUT_S * 1000,
        maxPoolSize=3,
        appname="deployer-provisioner",
        uuidRepresentation="standard",
    )


def _unavailable(engine: str, exc: Exception) -> ApiError:
    msg = connections.redact(
        str(getattr(exc, "orig", None) or exc),
        [
            get_settings().mariadb_root_password,
            get_settings().mongo_root_password,
        ],
    )
    return ApiError(503, "database_unavailable", f"Managed {engine} is not reachable: {msg}")


def mariadb_database_exists(name: str) -> bool:
    with mariadb_root_engine().connect() as conn:
        return (
            conn.execute(text("SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :n"), {"n": name}).first()
            is not None
        )


def mongo_database_exists(name: str) -> bool:
    client = mongo_root_client()
    if name in client.list_database_names():
        return True
    # A database with only a user (no data yet) doesn't show up in listDatabases.
    return client["admin"]["system.users"].count_documents({"db": name}, limit=1) > 0


# ---------------------------------------------------------------------------------------------
# MariaDB
# ---------------------------------------------------------------------------------------------


def create_mariadb_database(database: str, username: str, password: str) -> dict[str, Any]:
    _check(DB_NAME_RE, database, "database name")
    _check(USER_RE, username, "user name")
    _check(PASSWORD_RE, password, "password")
    s = get_settings()
    created_db = False
    try:
        with mariadb_root_engine().connect() as conn:
            conn.exec_driver_sql(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            created_db = True
            conn.exec_driver_sql(f"CREATE USER '{username}'@'%%' IDENTIFIED BY '{password}'")
            conn.exec_driver_sql(f"GRANT ALL PRIVILEGES ON `{database}`.* TO '{username}'@'%%'")
    except Exception as exc:
        if created_db:
            try:
                drop_mariadb_database(database, username)
            except Exception:  # noqa: BLE001
                log.exception("cleanup of %s failed", database)
        if isinstance(exc, ApiError):
            raise
        raise _unavailable("MariaDB", exc) from exc
    return {
        "host": s.mariadb_host,
        "port": s.mariadb_port,
        "username": username,
        "password": password,
        "database": database,
        "tls": False,
    }


def drop_mariadb_database(database: str, username: str | None) -> None:
    _check(DB_NAME_RE, database, "database name")
    with mariadb_root_engine().connect() as conn:
        conn.exec_driver_sql(f"DROP DATABASE IF EXISTS `{database}`")
        if username and USER_RE.fullmatch(username):
            conn.exec_driver_sql(f"DROP USER IF EXISTS '{username}'@'%%'")


# ---------------------------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------------------------


def mongo_uri(database: str, username: str, password: str) -> str:
    s = get_settings()
    return f"mongodb://{username}:{password}@{s.mongo_host}:{s.mongo_port}/{database}?authSource={database}"


def create_mongo_database(database: str, username: str, password: str) -> dict[str, Any]:
    _check(DB_NAME_RE, database, "database name")
    _check(USER_RE, username, "user name")
    _check(PASSWORD_RE, password, "password")
    try:
        mongo_root_client()[database].command(
            "createUser", username, pwd=password, roles=[{"role": "dbOwner", "db": database}]
        )
    except Exception as exc:
        raise _unavailable("MongoDB", exc) from exc
    return {
        "uri": mongo_uri(database, username, password),
        "database": database,
        "username": username,
        "password": password,
    }


def drop_mongo_database(database: str, username: str | None) -> None:
    _check(DB_NAME_RE, database, "database name")
    client = mongo_root_client()
    if username and USER_RE.fullmatch(username):
        try:
            client[database].command("dropUser", username)
        except Exception as exc:  # noqa: BLE001 - user may already be gone
            if "not found" not in str(exc).lower():
                raise
    client.drop_database(database)


# ---------------------------------------------------------------------------------------------
# host devices (docs/DEVICES.md)
# ---------------------------------------------------------------------------------------------


def device_source_config(kind: str, database: str, username: str) -> dict[str, Any]:
    """Primary-side config of a device-hosted database: display info only, no password."""
    if kind == "sql":
        return {
            "host": "mariadb",
            "port": 3306,
            "username": username,
            "database": database,
            "tls": False,
            "on_device": True,
        }
    return {
        "uri": f"mongodb://{username}@mongodb:27017/{database}?authSource={database}",
        "database": database,
        "username": username,
        "on_device": True,
    }


def provision_on_device(
    project: Project, kind: str, device_id: str, preferred: str | None = None
) -> tuple[str, dict[str, Any], str]:
    from app.services import device_rpc

    if kind not in ("sql", "nosql"):
        raise ApiError(422, "validation_error", f"Unknown data source kind: {kind}")
    candidates = [preferred] if preferred and DB_NAME_RE.fullmatch(preferred) else []
    candidates += [generate_database_name(project.slug) for _ in range(5)]
    for candidate in candidates:
        try:
            result = device_rpc.call(
                device_id, "datasource.provision", {"kind": kind, "database_name": candidate}, timeout=90
            )
        except ApiError as exc:
            if exc.code == "database_exists":
                continue
            raise
        database = str(result.get("database_name") or candidate)
        _check(DB_NAME_RE, database, "database name")
        config = device_source_config(kind, database, str(result.get("username") or ""))
        return database, config, "mariadb" if kind == "sql" else "mongodb"
    raise ApiError(500, "provisioning_failed", "Could not allocate a unique database name on the device")


def drop_on_device(device_id: str, kind: str, database: str) -> None:
    from app.services import device_rpc

    device_rpc.call(device_id, "datasource.drop", {"kind": kind, "database_name": database}, timeout=120)


# ---------------------------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------------------------


def _pick_database_name(slug: str, preferred: str | None, exists) -> str:
    if preferred and DB_NAME_RE.fullmatch(preferred):
        try:
            if not exists(preferred):
                return preferred
        except Exception as exc:  # noqa: BLE001
            raise ApiError(503, "database_unavailable", f"Managed database server is not reachable: {exc}") from exc
    for _ in range(5):
        name = generate_database_name(slug)
        if not exists(name):
            return name
    raise ApiError(500, "provisioning_failed", "Could not allocate a unique database name")


def provision_managed_source(
    db: Session,
    project: Project,
    kind: Literal["sql", "nosql"],
    name: str,
    *,
    database_name: str | None = None,
    data_source_id: str | None = None,
    device_id: str | None = None,
) -> DataSource:
    """Creates a managed database + dedicated user and adds the DataSource to the session.

    `database_name` (optional) is kept when valid and free on this host (used by imports);
    otherwise a fresh `p_<slug>_<hex>` name is generated.

    `device_id` (optional) places the database on that host device (docs/DEVICES.md) via the
    `datasource.provision` RPC; the password then stays on the device. Callers validate eligibility
    (`services.devices.validate_placement`) first.
    """
    settings = get_settings()
    username, password = generate_username(), generate_password()
    if device_id:
        database, config, engine = provision_on_device(project, kind, device_id, database_name)
    elif kind == "sql":
        try:
            database = _pick_database_name(project.slug, database_name, mariadb_database_exists)
        except ApiError:
            raise
        except Exception as exc:
            raise _unavailable("MariaDB", exc) from exc
        config = create_mariadb_database(database, username, password)
        engine = "mariadb"
    elif kind == "nosql":
        if not settings.managed_mongodb_enabled:
            raise ApiError(
                409,
                "managed_mongodb_unavailable",
                "Managed MongoDB is not available on this host (the CPU lacks AVX). "
                "Attach an external MongoDB such as Atlas instead.",
            )
        try:
            database = _pick_database_name(project.slug, database_name, mongo_database_exists)
        except ApiError:
            raise
        except Exception as exc:
            raise _unavailable("MongoDB", exc) from exc
        config = create_mongo_database(database, username, password)
        engine = "mongodb"
    else:
        raise ApiError(422, "validation_error", f"Unknown data source kind: {kind}")

    ds = DataSource(
        id=data_source_id or new_id(),
        project_id=project.id,
        name=name,
        kind=kind,
        engine=engine,
        mode="managed",
        database_name=database,
        config_encrypted=encrypt_json(config),
        status="ok",
        status_message="Provisioned",
        last_checked_at=utcnow(),
        device_id=device_id or None,
    )
    db.add(ds)
    # docs/BACKUPS.md: every managed source starts with the default backup policy. The source row is
    # flushed first (no ORM relationship orders the two inserts); on failure the new database is dropped.
    from app.models import BackupPolicy

    try:
        db.flush([ds])
        db.add(BackupPolicy(data_source_id=ds.id))
    except Exception:
        try:
            drop_managed_source(db, ds)
        except Exception:  # noqa: BLE001
            log.warning("cleanup of %s failed", ds.database_name, exc_info=True)
        raise
    return ds


def drop_managed_source(db: Session, data_source: DataSource) -> None:
    """Drops the managed database and its user. No-op for external sources. Row is not deleted."""
    _ = db
    if data_source.mode != "managed":
        return
    if data_source.device_id:
        drop_on_device(data_source.device_id, data_source.kind, data_source.database_name)
        return
    connections.invalidate(data_source.id)
    try:
        config = connections.load_config(data_source)
    except Exception:  # noqa: BLE001
        config = {}
    username = config.get("username")
    database = data_source.database_name
    if not DB_NAME_RE.fullmatch(database or ""):
        log.warning("not dropping managed source %s: unexpected database name %r", data_source.id, database)
        return
    try:
        if data_source.kind == "sql":
            drop_mariadb_database(database, username)
        else:
            drop_mongo_database(database, username)
    except ApiError:
        raise
    except Exception as exc:
        raise _unavailable("MariaDB" if data_source.kind == "sql" else "MongoDB", exc) from exc
