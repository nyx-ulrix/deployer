"""Connections to project data sources (managed or external).

- Builds SQLAlchemy engines (MariaDB/MySQL via PyMySQL, PostgreSQL via psycopg 3) and pymongo
  clients from a data source's decrypted config.
- Caches one engine / client per data source id (small pools, `pool_pre_ping`); the cache key also
  includes the encrypted config so credential changes produce a fresh connection. Call
  `invalidate(data_source_id)` when a source is deleted.
- Connection tests (`try_sql`, `try_mongo`) never raise; they return `(ok, message, version)`
  with passwords redacted from driver messages and, when the cause is recognisable, a plain hint first
  (`friendly_error`: wrong password, unknown database, unreachable host, Atlas Network Access, ...).
"""

from __future__ import annotations

import hashlib
import re
import ssl
import threading
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.crypto import decrypt_json
from app.errors import ApiError
from app.models import DataSource, utcnow

CONNECT_TIMEOUT_S = 5
TEST_IO_TIMEOUT_S = 10  # A-113: a connection test's MySQL handshake/query read, not the 300 s of real work
DEFAULT_PORTS = {"mariadb": 3306, "mysql": 3306, "postgresql": 5432, "mongodb": 27017}

_lock = threading.Lock()
_sql_cache: dict[str, tuple[str, Engine]] = {}
_mongo_cache: dict[str, tuple[str, MongoClient]] = {}


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------


DEVICE_REMOVED = "This database's PC was removed; its data is still on that PC."


def device_removed(ds: DataSource) -> bool:
    """A-047: a device-hosted source whose device was removed. Its device_id is cleared but its data is
    still on that PC; the main server's database of the same name (if any) is not it."""
    if ds.device_id or ds.mode != "managed":
        return False
    try:
        return bool(decrypt_json(ds.config_encrypted).get("on_device"))
    except Exception:  # noqa: BLE001
        return False


def require_host(ds: DataSource) -> None:
    if device_removed(ds):
        raise ApiError(409, "device_removed", DEVICE_REMOVED)


CLOUD_CREATING = "This database is still being created in your cloud account (usually 5-15 minutes)."


def load_config(ds: DataSource) -> dict[str, Any]:
    if ds.status == "creating":
        raise ApiError(409, "cloud_database_creating", CLOUD_CREATING)
    config = decrypt_json(ds.config_encrypted)
    if config.get("on_device") and not ds.device_id:
        raise ApiError(409, "device_removed", DEVICE_REMOVED)  # A-047: never the main server's namesake
    return config


def _fingerprint(ds: DataSource) -> str:
    return hashlib.sha256(ds.config_encrypted.encode("utf-8")).hexdigest()


def redact(message: str, secrets: list[str | None] | None = None, *, limit: int | None = 1000) -> str:
    """Removes passwords from driver error messages (and other text: `limit=None` keeps the length)."""
    out = str(message)
    for secret in secrets or []:
        if secret:
            out = out.replace(secret, "***")
            quoted = quote(secret, safe="")
            if quoted != secret:
                out = out.replace(quoted, "***")
    # user:password@ in any URI; the bound keeps a 200 000-char "://a:" repeat linear (was ~20 s)
    out = re.sub(r"(://[^:/@\s]+:)[^@\s]{1,512}@", r"\1***@", out)
    return out if limit is None else out[:limit]


def sql_url(engine_name: str, config: dict[str, Any]) -> URL:
    driver = "postgresql+psycopg" if engine_name == "postgresql" else "mysql+pymysql"
    query = {} if engine_name == "postgresql" else {"charset": "utf8mb4"}
    return URL.create(
        driver,
        username=config.get("username") or None,
        password=config.get("password") or None,
        host=config.get("host") or None,
        port=int(config.get("port") or DEFAULT_PORTS[engine_name]),
        database=config.get("database") or None,
        query=query,
    )


def _connect_args(engine_name: str, config: dict[str, Any], io_timeout: int = 300) -> dict[str, Any]:
    if engine_name == "postgresql":  # libpq's connect_timeout already covers the handshake
        return {"connect_timeout": CONNECT_TIMEOUT_S, "sslmode": "require" if config.get("tls") else "prefer"}
    # PyMySQL's connect_timeout covers only the TCP connect; the greeting/auth reads use read_timeout.
    args: dict[str, Any] = {
        "connect_timeout": CONNECT_TIMEOUT_S,
        "read_timeout": io_timeout,
        "write_timeout": io_timeout,
    }
    if config.get("tls"):
        args["ssl"] = ssl.create_default_context()
        if config.get("tls_verify") is False:
            # docs/CLOUD.md: AWS RDS signs with its own CA, which is not in the system store. Encrypted but
            # not authenticated, like PostgreSQL's sslmode=require above.
            # ponytail: pin the RDS CA bundle (truststore.pki.rds.amazonaws.com) to verify the server too.
            args["ssl"].check_hostname = False
            args["ssl"].verify_mode = ssl.CERT_NONE
    return args


def build_sql_engine(engine_name: str, config: dict[str, Any], *, pooled: bool = True, io_timeout: int = 300) -> Engine:
    kwargs: dict[str, Any] = {"connect_args": _connect_args(engine_name, config, io_timeout)}
    if pooled:
        kwargs.update(pool_size=2, max_overflow=3, pool_pre_ping=True, pool_recycle=1800, pool_timeout=10)
    else:
        kwargs["poolclass"] = NullPool
    return create_engine(sql_url(engine_name, config), **kwargs)


def build_mongo_client(config: dict[str, Any], *, pooled: bool = True) -> MongoClient:
    return MongoClient(
        config["uri"],
        serverSelectionTimeoutMS=CONNECT_TIMEOUT_S * 1000,
        connectTimeoutMS=CONNECT_TIMEOUT_S * 1000,
        maxPoolSize=5 if pooled else 1,
        appname="deployer",
        uuidRepresentation="standard",
    )


# ---------------------------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------------------------


def get_sql_engine(ds: DataSource) -> Engine:
    fp = _fingerprint(ds)
    with _lock:
        cached = _sql_cache.get(ds.id)
        if cached and cached[0] == fp:
            return cached[1]
        if cached:
            cached[1].dispose()
        engine = build_sql_engine(ds.engine, load_config(ds))
        _sql_cache[ds.id] = (fp, engine)
        return engine


def get_mongo_client(ds: DataSource) -> MongoClient:
    fp = _fingerprint(ds)
    with _lock:
        cached = _mongo_cache.get(ds.id)
        if cached and cached[0] == fp:
            return cached[1]
        if cached:
            cached[1].close()
        client = build_mongo_client(load_config(ds))
        _mongo_cache[ds.id] = (fp, client)
        return client


def get_mongo_db(ds: DataSource) -> Database:
    config = load_config(ds)
    return get_mongo_client(ds)[config["database"]]


def invalidate(data_source_id: str) -> None:
    with _lock:
        sql = _sql_cache.pop(data_source_id, None)
        mongo = _mongo_cache.pop(data_source_id, None)
    if sql:
        sql[1].dispose()
    if mongo:
        mongo[1].close()


def dispose_all() -> None:
    """Test teardown seam: drop every cached engine/client (like the provisioning `cache_clear`s)."""
    for sid in list(_sql_cache) + list(_mongo_cache):
        invalidate(sid)


# ---------------------------------------------------------------------------------------------
# tests & status
# ---------------------------------------------------------------------------------------------


_UNREACHABLE = (
    "Could not reach the server at {where}. Check the host and port, that the server is running and accepts "
    "remote connections, and that a firewall allows that port."
)
_BAD_HOST = "The host name {host} could not be found. Check its spelling."
_ATLAS = " For MongoDB Atlas, add this PC's public IP address under Network Access."
# PyMySQL error codes -> hint
_MYSQL_HINTS = {
    1044: "This user has no access to database '{database}'. Grant it privileges on that database.",
    1045: (
        "Wrong username or password, or this user may not connect from Deployer's address "
        "(MySQL users are per host; allow the user from '%')."
    ),
    1049: "Database '{database}' does not exist on that server. Check the database name.",
    1130: "The server does not allow connections from Deployer's address. Allow the user from host '%'.",
    2003: _UNREACHABLE,
    2005: _BAD_HOST,
    2013: (  # A-113: something listens on that port but did not answer like MySQL/MariaDB in time
        "The server at {where} accepted the connection but did not answer like a MySQL/MariaDB server. "
        "Check the port (usually 3306) and the TLS setting."
    ),
}
# lowercase PostgreSQL / libpq message fragment -> hint (first match wins)
_PG_HINTS = (
    ("password authentication failed", "Wrong username or password."),
    ('role "', "User '{username}' does not exist on that server."),
    ('database "', "Database '{database}' does not exist on that server. Check the database name."),
    ("no pg_hba.conf entry", "The server does not allow connections from Deployer's address (pg_hba.conf)."),
    ("server does not support ssl", "The server does not support TLS. Turn TLS off for this connection."),
    ("could not translate host name", _BAD_HOST),
    ("name or service not known", _BAD_HOST),
    ("timeout expired", _UNREACHABLE),
    ("connection refused", _UNREACHABLE),
    ("could not connect", _UNREACHABLE),
)


def _hint(kind: str, exc: BaseException, config: dict[str, Any]) -> str | None:
    """A-106: one plain sentence on the likely cause of a connection error, or None when unknown."""
    if kind == "nosql":
        if isinstance(exc, OperationFailure):
            if exc.code == 13:
                return f"This user has no access to database '{config.get('database')}'."
            if exc.code == 18 or "authentication failed" in str(exc).lower():
                return "Wrong username or password in the connection URI (check the authSource too)."
            return None
        if isinstance(exc, ConnectionFailure):  # includes ServerSelectionTimeoutError
            return (
                "Could not reach the MongoDB server. Check the host in the URI and that the server is running." + _ATLAS
            )
        if isinstance(exc, ConfigurationError):
            return "The connection URI is invalid or its host name could not be found. Check the URI."
        return None
    host = config.get("host") or "?"
    fields = {
        "host": host,
        "where": f"{host}:{config.get('port') or ''}".rstrip(":"),
        "database": config.get("database"),
        "username": config.get("username"),
    }
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], int):  # PyMySQL: (code, message)
        hint = _MYSQL_HINTS.get(args[0])
        return hint.format(**fields) if hint else None
    text_ = str(exc).lower()
    for fragment, hint in _PG_HINTS:
        if fragment in text_ and (not fragment.endswith('"') or "does not exist" in text_):
            return hint.format(**fields)
    return None


def friendly_error(kind: str, exc: BaseException, config: dict[str, Any], secrets: list[str | None]) -> str:
    """A-106: a connection error as a plain hint followed by the (redacted) driver text."""
    raw = redact(str(exc), secrets, limit=400)
    hint = _hint(kind, exc, config)
    return f"{hint} Details: {raw}" if hint else raw


def try_sql(engine_name: str, config: dict[str, Any]) -> tuple[bool, str, str | None]:
    engine = build_sql_engine(engine_name, config, pooled=False, io_timeout=TEST_IO_TIMEOUT_S)
    try:
        with engine.connect() as conn:
            if engine_name == "postgresql":
                version = conn.exec_driver_sql("SHOW server_version").scalar()
            else:
                version = conn.exec_driver_sql("SELECT VERSION()").scalar()
        return True, "Connected", str(version) if version is not None else None
    except Exception as exc:  # noqa: BLE001 - driver errors vary widely
        orig = getattr(exc, "orig", None) or exc
        return False, friendly_error("sql", orig, config, [config.get("password")]), None
    finally:
        engine.dispose()


def try_mongo(config: dict[str, Any]) -> tuple[bool, str, str | None]:
    client = None
    try:
        client = build_mongo_client(config, pooled=False)
        client[config["database"]].command("ping")
        try:
            version = client.server_info().get("version")
        except Exception:  # noqa: BLE001 - buildInfo may be restricted on some hosted tiers
            version = None
        return True, "Connected", version
    except Exception as exc:  # noqa: BLE001
        secrets = [config.get("password"), mongo_uri_password(config.get("uri", ""))]
        return False, friendly_error("nosql", exc, config, secrets), None
    finally:
        if client is not None:
            client.close()


def try_config(kind: str, engine_name: str, config: dict[str, Any]) -> tuple[bool, str, str | None]:
    if kind == "sql":
        return try_sql(engine_name, config)
    return try_mongo(config)


def cloud_engine(engine: str):
    """The adapter module of an engine reached only through its cloud connection, with no driver or
    credentials of its own (docs/CLOUD.md "C2-2".."C2-4"): services/dynamo.py, firestore.py or rtdb.py, which
    share the same functions (check, display, connection_info, run_op, introspect, entity, export_script,
    run_console). None for every other engine."""
    if engine == "dynamodb":
        from app.services import dynamo

        return dynamo
    if engine == "firestore":
        from app.services import firestore

        return firestore
    if engine == "firebase_rtdb":
        from app.services import rtdb

        return rtdb
    return None


def try_source(ds: DataSource) -> tuple[bool, str, str | None]:
    if (adapter := cloud_engine(ds.engine)) is not None:
        return adapter.check(ds)
    try:
        config = load_config(ds)
    except ApiError as exc:
        return False, exc.message, None
    except Exception as exc:  # noqa: BLE001
        return False, f"Cannot decrypt connection config: {exc}", None
    return try_config(ds.kind, ds.engine, config)


def check_status(db: Session, ds: DataSource) -> DataSource:
    """Tests the source and stores status / status_message / last_checked_at. Caller commits."""
    if ds.status == "creating":  # the cloud_db create job sets the status when it is done
        return ds
    ok, message, version = try_source(ds)
    ds.status = "ok" if ok else "error"
    ds.status_message = (f"Connected (server {version})" if version else "Connected") if ok else message
    ds.last_checked_at = utcnow()
    if not ok:
        invalidate(ds.id)
    return ds


# ---------------------------------------------------------------------------------------------
# display / connection info
# ---------------------------------------------------------------------------------------------


def mongo_uri_password(uri: str) -> str | None:
    try:
        parts = urlsplit(uri)
        netloc = parts.netloc
        if "@" in netloc:
            userinfo = netloc.rsplit("@", 1)[0]
            if ":" in userinfo:
                return unquote(userinfo.split(":", 1)[1])
    except ValueError:
        return None
    return None


def parse_mongo_uri(uri: str) -> dict[str, Any]:
    """Parses host/port/username/tls from a MongoDB URI without DNS lookups (works for +srv)."""
    result: dict[str, Any] = {"host": None, "port": None, "username": None, "tls": False, "database": None}
    m = re.match(r"^(mongodb(?:\+srv)?)://([^/?]*)(/[^?]*)?(\?.*)?$", uri or "")
    if not m:
        return result
    scheme, netloc, path, query = m.groups()
    result["database"] = unquote((path or "").lstrip("/")).strip() or None
    if "@" in netloc:
        userinfo, hosts = netloc.rsplit("@", 1)
        result["username"] = unquote(userinfo.split(":", 1)[0]) or None
    else:
        hosts = netloc
    first = hosts.split(",")[0]
    if first.startswith("["):  # IPv6
        host, _, rest = first[1:].partition("]")
        port = rest.lstrip(":") or None
    else:
        host, _, port = first.partition(":")
    result["host"] = host or None
    if scheme == "mongodb+srv":
        result["tls"] = True
    else:
        result["port"] = int(port) if port and port.isdigit() else 27017
    q = (query or "").lower()
    if re.search(r"[?&](tls|ssl)=true", q):
        result["tls"] = True
    if re.search(r"[?&](tls|ssl)=false", q):
        result["tls"] = False
    return result


def display_for(ds: DataSource, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if (adapter := cloud_engine(ds.engine)) is not None:
        return adapter.display(ds)
    try:
        config = config if config is not None else load_config(ds)
    except Exception:  # noqa: BLE001
        return {"host": None, "port": None, "username": None, "tls": False}
    if ds.kind == "sql":
        return {
            "host": config.get("host"),
            "port": int(config.get("port") or DEFAULT_PORTS.get(ds.engine, 0)) or None,
            "username": config.get("username"),
            "tls": bool(config.get("tls")),
        }
    parsed = parse_mongo_uri(config.get("uri", ""))
    parsed.pop("database")  # display is host/port/username/tls, like SQL's
    if config.get("username"):
        parsed["username"] = config["username"]
    return parsed


def sql_app_uri(engine_name: str, config: dict[str, Any]) -> str:
    scheme = "postgresql" if engine_name == "postgresql" else "mysql"
    user = quote(config.get("username") or "", safe="")
    pw = quote(config.get("password") or "", safe="")
    creds = f"{user}:{pw}@" if user else ""
    port = int(config.get("port") or DEFAULT_PORTS[engine_name])
    uri = f"{scheme}://{creds}{config.get('host')}:{port}/{quote(config.get('database') or '', safe='')}"
    if config.get("tls"):
        uri += "?sslmode=require" if engine_name == "postgresql" else "?ssl=true"
    return uri


def connection_info(ds: DataSource) -> dict[str, Any]:
    if (adapter := cloud_engine(ds.engine)) is not None:  # no password: apps use their cloud identity
        return adapter.connection_info(ds)
    config = load_config(ds)
    if ds.kind == "sql":
        info = {
            "uri": sql_app_uri(ds.engine, config),
            "host": config.get("host"),
            "port": int(config.get("port") or DEFAULT_PORTS[ds.engine]),
            "username": config.get("username"),
            "password": config.get("password"),
            "database": config.get("database"),
        }
    else:
        parsed = parse_mongo_uri(config.get("uri", ""))
        info = {
            "uri": config.get("uri"),
            "host": parsed["host"],
            "port": parsed["port"],
            "username": config.get("username") or parsed["username"],
            "password": config.get("password") or mongo_uri_password(config.get("uri", "")),
            "database": config.get("database"),
        }
    if ds.mode == "managed":
        # Only apps with database_access join the databases network (deployments.database_env).
        info["external_hint"] = (
            "Use this from apps you deploy here; turn on Database access (\"Connect to this project's "
            "databases\") in the app's settings first. It does not work from other computers."
        )
    else:
        info["external_hint"] = "Use these from any app or computer that can reach this database's server."
    return info
