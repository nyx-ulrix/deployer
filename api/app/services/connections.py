"""Connections to project data sources (managed or external).

- Builds SQLAlchemy engines (MariaDB/MySQL via PyMySQL, PostgreSQL via psycopg 3) and pymongo
  clients from a data source's decrypted config.
- Caches one engine / client per data source id (small pools, `pool_pre_ping`); the cache key also
  includes the encrypted config so credential changes produce a fresh connection. Call
  `invalidate(data_source_id)` when a source is deleted.
- Connection tests (`try_sql`, `try_mongo`) never raise; they return `(ok, message, version)`
  with passwords redacted from driver messages.
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
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.crypto import decrypt_json
from app.models import DataSource, utcnow

CONNECT_TIMEOUT_S = 5
SQL_ENGINES = ("mariadb", "mysql", "postgresql")
DEFAULT_PORTS = {"mariadb": 3306, "mysql": 3306, "postgresql": 5432, "mongodb": 27017}

_lock = threading.Lock()
_sql_cache: dict[str, tuple[str, Engine]] = {}
_mongo_cache: dict[str, tuple[str, MongoClient]] = {}


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------


def load_config(ds: DataSource) -> dict[str, Any]:
    return decrypt_json(ds.config_encrypted)


def _fingerprint(ds: DataSource) -> str:
    return hashlib.sha256(ds.config_encrypted.encode("utf-8")).hexdigest()


def redact(message: str, secrets: list[str | None] | None = None) -> str:
    """Removes passwords from driver error messages."""
    out = str(message)
    for secret in secrets or []:
        if secret:
            out = out.replace(secret, "***")
            quoted = quote(secret, safe="")
            if quoted != secret:
                out = out.replace(quoted, "***")
    # user:password@ in any URI
    out = re.sub(r"(://[^:/@\s]+:)[^@\s]+@", r"\1***@", out)
    return out[:1000]


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


def _connect_args(engine_name: str, config: dict[str, Any]) -> dict[str, Any]:
    if engine_name == "postgresql":
        return {"connect_timeout": CONNECT_TIMEOUT_S, "sslmode": "require" if config.get("tls") else "prefer"}
    args: dict[str, Any] = {"connect_timeout": CONNECT_TIMEOUT_S, "read_timeout": 300, "write_timeout": 300}
    if config.get("tls"):
        args["ssl"] = ssl.create_default_context()
    return args


def build_sql_engine(engine_name: str, config: dict[str, Any], *, pooled: bool = True) -> Engine:
    kwargs: dict[str, Any] = {"connect_args": _connect_args(engine_name, config)}
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
    for sid in list(_sql_cache) + list(_mongo_cache):
        invalidate(sid)


# ---------------------------------------------------------------------------------------------
# tests & status
# ---------------------------------------------------------------------------------------------


def try_sql(engine_name: str, config: dict[str, Any]) -> tuple[bool, str, str | None]:
    engine = build_sql_engine(engine_name, config, pooled=False)
    try:
        with engine.connect() as conn:
            if engine_name == "postgresql":
                version = conn.exec_driver_sql("SHOW server_version").scalar()
            else:
                version = conn.exec_driver_sql("SELECT VERSION()").scalar()
        return True, "Connected", str(version) if version is not None else None
    except Exception as exc:  # noqa: BLE001 - driver errors vary widely
        orig = getattr(exc, "orig", None) or exc
        return False, redact(str(orig), [config.get("password")]), None
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
        return False, redact(str(exc), [config.get("password"), mongo_uri_password(config.get("uri", ""))]), None
    finally:
        if client is not None:
            client.close()


def try_config(kind: str, engine_name: str, config: dict[str, Any]) -> tuple[bool, str, str | None]:
    if kind == "sql":
        return try_sql(engine_name, config)
    return try_mongo(config)


def try_source(ds: DataSource) -> tuple[bool, str, str | None]:
    try:
        config = load_config(ds)
    except Exception as exc:  # noqa: BLE001
        return False, f"Cannot decrypt connection config: {exc}", None
    return try_config(ds.kind, ds.engine, config)


def check_status(db: Session, ds: DataSource) -> DataSource:
    """Tests the source and stores status / status_message / last_checked_at. Caller commits."""
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
    result: dict[str, Any] = {"host": None, "port": None, "username": None, "tls": False}
    m = re.match(r"^(mongodb(?:\+srv)?)://([^/?]*)(/[^?]*)?(\?.*)?$", uri or "")
    if not m:
        return result
    scheme, netloc, _path, query = m.groups()
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
        info["external_hint"] = (
            f"Managed databases are reachable only from containers on the Deployer Docker network "
            f"(host '{info['host']}'). They are not published on the host machine; apps deployed by "
            f"Deployer can use this URI directly."
        )
    else:
        info["external_hint"] = "External database: use these credentials from anywhere that can reach the server."
    return info


def ping_sql(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
