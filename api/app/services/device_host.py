"""Device side of host devices (docs/DEVICES.md): link state, hosted database credentials, metrics
and the RPC method implementations the device agent dispatches to.

Stored in this installation's own `instance_settings` (both encrypted with MASTER_KEY):

- `device_link`: JSON `{primary_url, device_id, device_token, device_name}`.
- `device_hosted_credentials`: JSON `{database_name: {kind, username, password, created_at}}`.

RPC `datasource.*` and `sync.*` methods only ever touch databases listed in `device_hosted_credentials`
(`datasource.provision` additionally requires that the database does not exist yet), so the main
Deployer can never reach this device's own platform database or anything else on it.
"""

from __future__ import annotations

import gzip
import hashlib
import ipaddress
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.crypto import encrypt_json
from app.db import get_sessionmaker
from app.errors import ApiError
from app.models import DataSource, utcnow
from app.serializers import iso
from app.services import instance_settings, provisioning

log = logging.getLogger(__name__)

RESERVED_DATABASES = frozenset(
    {"deployer", "mysql", "information_schema", "performance_schema", "sys", "admin", "local", "config", "test"}
)
_creds_lock = threading.RLock()


# ---------------------------------------------------------------------------------------------
# primary URL validation
# ---------------------------------------------------------------------------------------------

_PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",  # CGNAT, used by Tailscale
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
]


def insecure_primary_allowed() -> bool:
    return os.environ.get("DEPLOYER_ALLOW_INSECURE_PRIMARY", "").strip().lower() in ("1", "true", "yes")


def validate_primary_url(url: str) -> str:
    """Returns the normalized origin (`scheme://host[:port]`) or raises 422 `invalid_primary_url`.

    https is always allowed; plain http only for localhost, private/Tailscale addresses and
    `*.ts.net` (plus `host.docker.internal` when DEPLOYER_ALLOW_INSECURE_PRIMARY=1, for tests).
    """

    def bad(message: str) -> ApiError:
        return ApiError(422, "invalid_primary_url", message)

    raw = (url or "").strip().rstrip("/")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise bad("Not a valid URL") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise bad("The main Deployer URL must start with https:// (or http:// on a private network)")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise bad("Use only the main Deployer's address, e.g. https://deployer.example.com")
    host = parts.hostname.lower()
    if parts.scheme == "http" and not http_host_allowed(host):
        raise bad("Plain http:// is only allowed for localhost, private LAN addresses and *.ts.net; use https://")
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    return f"{parts.scheme}://{netloc}"


def http_host_allowed(host: str) -> bool:
    host = host.lower().strip("[]")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".ts.net"):
        return True
    if host == "host.docker.internal" and insecure_primary_allowed():
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _PRIVATE_NETS)


def same_origin(a: str, b: str) -> bool:
    try:
        pa, pb = urlsplit(a), urlsplit(b)
        return (pa.scheme, pa.hostname, pa.port) == (pb.scheme, pb.hostname, pb.port)
    except ValueError:
        return False


# ---------------------------------------------------------------------------------------------
# link & credentials
# ---------------------------------------------------------------------------------------------


def _load_json_setting(db: Session, key: str) -> Any:
    raw = instance_settings.get_value(db, key)
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        log.warning("instance setting %s is not valid JSON", key)
        return None


def load_link(db: Session) -> dict | None:
    link = _load_json_setting(db, "device_link")
    if isinstance(link, dict) and link.get("primary_url") and link.get("device_token"):
        return link
    return None


def save_link(db: Session, link: dict) -> None:
    instance_settings.set_value(db, "device_link", json.dumps(link))


def clear_link(db: Session) -> None:
    instance_settings.set_value(db, "device_link", None)


def device_mode(db: Session) -> str:
    try:
        return "host" if load_link(db) else "standalone"
    except Exception:  # noqa: BLE001 - e.g. MASTER_KEY rotated; don't break setup status
        log.warning("could not read device_link", exc_info=True)
        return "standalone"


def load_credentials(db: Session) -> dict[str, dict]:
    creds = _load_json_setting(db, "device_hosted_credentials")
    return creds if isinstance(creds, dict) else {}


def save_credentials(db: Session, creds: dict[str, dict]) -> None:
    instance_settings.set_value(db, "device_hosted_credentials", json.dumps(creds) if creds else None)


def _with_session(fn: Callable[[Session], Any]) -> Any:
    session = get_sessionmaker()()
    try:
        return fn(session)
    finally:
        session.close()


def get_credentials() -> dict[str, dict]:
    return _with_session(load_credentials)


# ---------------------------------------------------------------------------------------------
# local DataSource objects for hosted databases
# ---------------------------------------------------------------------------------------------

_source_cache: dict[str, tuple[str, str]] = {}  # database -> (creds fingerprint, config_encrypted)


def local_config(kind: str, database: str, username: str, password: str) -> dict[str, Any]:
    s = get_settings()
    if kind == "sql":
        return {
            "host": s.mariadb_host,
            "port": s.mariadb_port,
            "username": username,
            "password": password,
            "database": database,
            "tls": False,
        }
    return {
        "uri": provisioning.mongo_uri(database, username, password),
        "database": database,
        "username": username,
        "password": password,
    }


def hosted_entry(database_name: Any, kind: Any, creds: dict[str, dict] | None = None) -> dict:
    """Returns the credentials entry for a hosted database or raises 404 (never touches others)."""
    if not isinstance(database_name, str) or not provisioning.DB_NAME_RE.fullmatch(database_name):
        raise ApiError(422, "validation_error", "Invalid database name")
    creds = get_credentials() if creds is None else creds
    entry = creds.get(database_name)
    if not isinstance(entry, dict) or (kind is not None and entry.get("kind") != kind):
        raise ApiError(404, "not_hosted", "That database is not hosted on this device")
    return entry


def local_source(database_name: str, kind: str | None, source_name: str | None = None) -> DataSource:
    entry = hosted_entry(database_name, kind)
    kind = entry["kind"]
    fingerprint = hashlib.sha256(f"{kind}|{entry.get('username')}|{entry.get('password')}".encode()).hexdigest()
    cached = _source_cache.get(database_name)
    if cached is None or cached[0] != fingerprint:
        config = local_config(kind, database_name, entry["username"], entry["password"])
        cached = (fingerprint, encrypt_json(config))
        _source_cache[database_name] = cached
    return DataSource(
        id=f"hosted-{database_name}",
        project_id="",
        name=(source_name or database_name)[:63],
        kind=kind,
        engine="mariadb" if kind == "sql" else "mongodb",
        mode="managed",
        database_name=database_name,
        config_encrypted=cached[1],
        status="ok",
    )


# ---------------------------------------------------------------------------------------------
# metrics & status
# ---------------------------------------------------------------------------------------------

_cpu_prev: tuple[float, float] | None = None


def _cpu_percent() -> float | None:
    global _cpu_prev
    try:
        with open("/proc/stat", encoding="ascii") as fh:
            fields = [float(x) for x in fh.readline().split()[1:]]
    except (OSError, ValueError):
        return None
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0)
    total = sum(fields)
    prev, _cpu_prev = _cpu_prev, (idle, total)
    if prev is None or total <= prev[1]:
        return None
    return round(100.0 * (1.0 - (idle - prev[0]) / (total - prev[1])), 1)


def _memory() -> tuple[int | None, int | None]:
    try:
        info = {}
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0]) * 1024
        total = info.get("MemTotal")
        available = info.get("MemAvailable", info.get("MemFree"))
        return (total - available if total and available is not None else None), total
    except (OSError, ValueError, IndexError):
        return None, None


def _uptime() -> float | None:
    try:
        with open("/proc/uptime", encoding="ascii") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def collect_metrics() -> dict[str, Any]:
    used, total = _memory()
    disk_path = os.environ.get("DEVICE_DISK_PATH") or "/"
    try:
        disk = shutil.disk_usage(disk_path)
        disk_free, disk_total = disk.free, disk.total
    except OSError:
        disk_free = disk_total = None
    return {
        "cpu_percent": _cpu_percent(),
        "memory_used_bytes": used,
        "memory_total_bytes": total,
        "disk_free_bytes": disk_free,
        "disk_total_bytes": disk_total,
        "uptime_seconds": _uptime(),
        "engines": {"mariadb": True, "mongodb": bool(get_settings().managed_mongodb_enabled)},
        "version": __version__,
        "collected_at": iso(utcnow()),
    }


def capabilities() -> dict[str, Any]:
    return {
        "engines": {"mariadb": True, "mongodb": bool(get_settings().managed_mongodb_enabled)},
        "methods": sorted(METHODS),
        "protocol": 1,
    }


def database_size(kind: str, database: str) -> int | None:
    try:
        if kind == "sql":
            with provisioning.mariadb_root_engine().connect() as conn:
                value = conn.exec_driver_sql(
                    "SELECT COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s",
                    (database,),
                ).scalar()
            return int(value or 0)
        stats = provisioning.mongo_root_client()[database].command("dbStats")
        return int(stats.get("storageSize", 0) + stats.get("indexSize", 0))
    except Exception:  # noqa: BLE001
        return None


def hosted_summary(db: Session, *, sizes: bool = True) -> list[dict]:
    out = []
    for name, entry in sorted(load_credentials(db).items()):
        kind = entry.get("kind")
        out.append(
            {
                "database_name": name,
                "kind": kind,
                "size_bytes": database_size(kind, name) if sizes else None,
            }
        )
    return out


# ---------------------------------------------------------------------------------------------
# RPC context & local store
# ---------------------------------------------------------------------------------------------


@dataclass
class CallContext:
    """What a device RPC method may use besides its params."""

    primary_url: str = ""
    device_token: str = ""
    progress: Callable[[str, float, str | None], None] = lambda job_id, progress, message: None
    detach: Callable[[], None] = lambda: None
    extra: dict[str, Any] = field(default_factory=dict)


def store_root() -> Path:
    """Local store for files exchanged with the primary (backup blobs etc.)."""
    base = os.environ.get("DEVICE_STORE_DIR") or os.environ.get("BACKUP_DIR") or "/backups"
    path = Path(base)
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "deployer-device-store"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def resolve_local_ref(local_ref: Any) -> Path:
    """Maps a relative `local_ref` inside the local store to a path; rejects traversal.

    Refs follow the backup artifact grammar (`executors.check_ref`): the store is the backups volume.
    """
    from app.services.executors import check_ref

    try:
        check_ref(local_ref)
    except ValueError as exc:
        raise ApiError(422, "invalid_local_ref", "Invalid local_ref") from exc
    root = store_root().resolve()
    path = (root / local_ref).resolve()
    if path == root or root not in path.parents:
        raise ApiError(422, "invalid_local_ref", "Invalid local_ref")
    return path


def _transfer_url(ctx: CallContext, transfer_id: Any) -> str:
    if not isinstance(transfer_id, str) or not re.fullmatch(r"[0-9a-f]{32}", transfer_id):
        raise ApiError(422, "validation_error", "Invalid transfer_id")
    return f"{ctx.primary_url.rstrip('/')}/v1/devices/transfers/{transfer_id}"


def _http_client(ctx: CallContext):
    import httpx

    return httpx.Client(
        headers={"Authorization": f"Device {ctx.device_token}"},
        timeout=httpx.Timeout(60.0, read=600.0, write=600.0),
        follow_redirects=False,
        verify=True,
    )


def upload_file(ctx: CallContext, transfer_id: str, path: Path) -> dict:
    url = _transfer_url(ctx, transfer_id)
    digest = hashlib.sha256()
    size = 0

    def chunks():
        nonlocal size
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                digest.update(chunk)
                size += len(chunk)
                yield chunk

    with _http_client(ctx) as client:
        resp = client.put(url, content=chunks(), headers={"Content-Type": "application/octet-stream"})
    if resp.status_code != 200:
        raise ApiError(502, "transfer_failed", f"Upload to the main Deployer failed ({resp.status_code})")
    return {"sha256": digest.hexdigest(), "size": size}


def download_file(ctx: CallContext, transfer_id: str, path: Path) -> dict:
    url = _transfer_url(ctx, transfer_id)
    digest = hashlib.sha256()
    size = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    try:
        with _http_client(ctx) as client, client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise ApiError(502, "transfer_failed", f"Download from the main Deployer failed ({resp.status_code})")
            with open(tmp, "wb") as out:
                for chunk in resp.iter_bytes(1 << 20):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"sha256": digest.hexdigest(), "size": size}


# ---------------------------------------------------------------------------------------------
# RPC methods
# ---------------------------------------------------------------------------------------------


def _kind(params: dict) -> str:
    kind = params.get("kind")
    if kind not in ("sql", "nosql"):
        raise ApiError(422, "validation_error", "kind must be sql or nosql")
    return kind


def m_provision(params: dict, ctx: CallContext) -> dict:
    kind = _kind(params)
    database = params.get("database_name")
    if (
        not isinstance(database, str)
        or not provisioning.DB_NAME_RE.fullmatch(database)
        or database in RESERVED_DATABASES
        or database.startswith("verify_")
    ):
        raise ApiError(422, "validation_error", "Invalid database name")
    if kind == "nosql" and not get_settings().managed_mongodb_enabled:
        raise ApiError(409, "managed_mongodb_unavailable", "Managed MongoDB is not available on this device")
    with _creds_lock:
        session = get_sessionmaker()()
        try:
            creds = load_credentials(session)
            exists = provisioning.mariadb_database_exists if kind == "sql" else provisioning.mongo_database_exists
            try:
                taken = database in creds or exists(database)
            except Exception as exc:  # noqa: BLE001
                raise provisioning._unavailable("MariaDB" if kind == "sql" else "MongoDB", exc) from exc
            if taken:
                raise ApiError(409, "database_exists", "A database with that name already exists on this device")
            username, password = provisioning.generate_username(), provisioning.generate_password()
            if kind == "sql":
                provisioning.create_mariadb_database(database, username, password)
            else:
                provisioning.create_mongo_database(database, username, password)
            creds[database] = {
                "kind": kind,
                "username": username,
                "password": password,
                "created_at": iso(utcnow()),
            }
            try:
                save_credentials(session, creds)
                session.commit()
            except Exception:
                session.rollback()
                (provisioning.drop_mariadb_database if kind == "sql" else provisioning.drop_mongo_database)(
                    database, username
                )
                raise
        finally:
            session.close()
    return {"database_name": database, "username": username}


def m_drop(params: dict, ctx: CallContext) -> dict:
    kind = _kind(params)
    database = params.get("database_name")
    with _creds_lock:
        session = get_sessionmaker()()
        try:
            creds = load_credentials(session)
            entry = hosted_entry(database, kind, creds)
            from app.services import connections

            connections.invalidate(f"hosted-{database}")
            _source_cache.pop(database, None)
            try:
                if kind == "sql":
                    provisioning.drop_mariadb_database(database, entry.get("username"))
                else:
                    provisioning.drop_mongo_database(database, entry.get("username"))
            except ApiError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise provisioning._unavailable("MariaDB" if kind == "sql" else "MongoDB", exc) from exc
            creds.pop(database, None)
            save_credentials(session, creds)
            session.commit()
        finally:
            session.close()
    return {}


def m_check(params: dict, ctx: CallContext) -> dict:
    from app.services import connections

    ds = local_source(params.get("database_name"), _kind(params))
    ok, message, version = connections.try_source(ds)
    return {"ok": ok, "message": message, "server_version": version}


def m_call(params: dict, ctx: CallContext) -> Any:
    from app.services import source_ops

    ds = local_source(params.get("database_name"), _kind(params), params.get("source_name"))
    op = params.get("op")
    args = params.get("args") if isinstance(params.get("args"), dict) else {}
    if not isinstance(op, str):
        raise ApiError(422, "validation_error", "op is required")
    return source_ops.run_local(ds, op, args)


def m_export(params: dict, ctx: CallContext) -> dict:
    """Writes the source's data (transfer.py `data` entry) to a gzip JSON file and uploads it."""
    from app.services import transfer

    ds = local_source(params.get("database_name"), _kind(params), params.get("source_name"))
    fd, tmp = tempfile.mkstemp(prefix="deployer-device-export-", suffix=".json.gz")
    os.close(fd)
    try:
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fh:
            counts = transfer.write_source_data(fh, ds)
        result = upload_file(ctx, params.get("transfer_id"), Path(tmp))
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {**result, **counts}


def m_import(params: dict, ctx: CallContext) -> dict:
    """Downloads a gzip JSON `data` entry from the primary and restores it into a hosted database."""
    from app.services import transfer

    ds = local_source(params.get("database_name"), _kind(params), params.get("source_name"))
    fd, tmp = tempfile.mkstemp(prefix="deployer-device-import-", suffix=".json.gz")
    os.close(fd)
    try:
        download_file(ctx, params.get("transfer_id"), Path(tmp))
        with gzip.open(tmp, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        rows, documents = transfer.restore_data(ds, data)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {"rows": rows, "documents": documents}


def m_transfer_upload(params: dict, ctx: CallContext) -> dict:
    path = resolve_local_ref(params.get("local_ref"))
    if not path.is_file():
        raise ApiError(404, "not_found", "Local file not found")
    return upload_file(ctx, params.get("transfer_id"), path)


def m_transfer_download(params: dict, ctx: CallContext) -> dict:
    path = resolve_local_ref(params.get("local_ref"))
    return download_file(ctx, params.get("transfer_id"), path)


def m_storage_delete(params: dict, ctx: CallContext) -> dict:
    path = resolve_local_ref(params.get("local_ref"))
    path.unlink(missing_ok=True)
    return {}


def m_detach(params: dict, ctx: CallContext) -> dict:
    session = get_sessionmaker()()
    try:
        if load_credentials(session):
            raise ApiError(409, "databases_remain", "This device still hosts databases; move them first")
        clear_link(session)
        session.commit()
    finally:
        session.close()
    ctx.detach()
    return {}


def m_ping(params: dict, ctx: CallContext) -> dict:
    return {"pong": True, "time": time.time(), "version": __version__}


def m_status(params: dict, ctx: CallContext) -> dict:
    return {"hosted_sources": _with_session(lambda s: hosted_summary(s)), "metrics": collect_metrics()}


# --- co-hosting sync (docs/COHOSTING.md): only databases this device hosts ------------------------


def _sync_database(params: dict, kind: str) -> str:
    database = params.get("database_name")
    hosted_entry(database, kind)  # 422 / 404 not_hosted for anything else
    return database


def _sync_limit(params: dict) -> int:
    from app.services import source_sync

    limit = params.get("limit", source_sync.BATCH_LIMIT)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= source_sync.BATCH_LIMIT:
        raise ApiError(422, "validation_error", "Invalid limit")
    return limit


def _sync_since(params: dict) -> dict | None:
    since = params.get("since")
    if since is not None and not isinstance(since, dict):
        raise ApiError(422, "validation_error", "Invalid since")
    return since


def _sync_offset(params: dict) -> int | None:
    from app.services import source_sync

    auto = params.get("auto_increment")
    if auto is None:
        return None
    offset = auto.get("offset") if isinstance(auto, dict) else None
    if (
        not isinstance(auto, dict)
        or auto.get("increment") != source_sync.AUTO_INCREMENT_STEP
        or not isinstance(offset, int)
        or not 2 <= offset <= source_sync.AUTO_INCREMENT_STEP
    ):
        raise ApiError(422, "validation_error", "Invalid auto_increment")
    return offset


def m_sync_position(params: dict, ctx: CallContext) -> dict:
    """Current end of this device's change history for a hosted database (after the initial copy);
    SQL: also applies the binlog prerequisites and this device's auto_increment offset."""
    from app.services import source_sync

    kind = _kind(params)
    database = _sync_database(params, kind)
    if kind == "sql":
        source_sync.ensure_mariadb_settings(offset=_sync_offset(params))
    return source_sync.local_position(kind, database)


def m_sync_sql_changes(params: dict, ctx: CallContext) -> dict:
    from app.services import source_sync

    database = _sync_database(params, "sql")
    offset, since, limit = _sync_offset(params), _sync_since(params), _sync_limit(params)
    source_sync.ensure_mariadb_settings(offset=offset)
    return source_sync.read_sql_changes(database, since, limit)


def m_sync_sql_apply(params: dict, ctx: CallContext) -> dict:
    from app.services import source_sync

    database = _sync_database(params, "sql")
    changes = source_sync.check_changes(params.get("changes"), "sql")
    # sql_log_bin = 0: changes applied here are never read back as this device's own changes.
    return {"outcomes": source_sync.apply_local("sql", database, changes, log_bin=False)}


def m_sync_mongo_changes(params: dict, ctx: CallContext) -> dict:
    from app.services import source_sync

    database = _sync_database(params, "nosql")
    since, limit = _sync_since(params), _sync_limit(params)
    return source_sync.read_mongo_changes(database, since, limit)


def m_sync_mongo_apply(params: dict, ctx: CallContext) -> dict:
    from app.services import source_sync

    database = _sync_database(params, "nosql")
    changes = source_sync.check_changes(params.get("changes"), "nosql")
    return {"outcomes": source_sync.apply_local("nosql", database, changes, log_bin=False)}


# Extra job types a device can run locally (`jobs.run`): type -> fn(job_id, params, ctx) -> result.
JOB_HANDLERS: dict[str, Callable[[str, dict, CallContext], Any]] = {}


def register_job_handler(job_type: str, handler: Callable[[str, dict, CallContext], Any]) -> None:
    JOB_HANDLERS[job_type] = handler


def m_jobs_run(params: dict, ctx: CallContext) -> Any:
    """`executor.<method>` backup calls and `runs_on="host"` jobs (see device_executor)."""
    job_type = params.get("type")
    if not isinstance(job_type, str) or not job_type:
        raise ApiError(422, "validation_error", "type is required")
    job_id = str(params.get("job_id") or "")[:64]
    job_params = params.get("params") if isinstance(params.get("params"), dict) else {}
    handler = JOB_HANDLERS.get(job_type)
    if handler is not None:
        return handler(job_id, job_params, ctx)
    from app.services import device_executor

    return device_executor.run_device_job(
        job_id,
        job_type,
        job_params,
        ctx,
        {"project_id": params.get("project_id"), "data_source_id": params.get("data_source_id")},
    )


METHODS: dict[str, Callable[[dict, CallContext], Any]] = {
    "datasource.provision": m_provision,
    "datasource.drop": m_drop,
    "datasource.check": m_check,
    "datasource.call": m_call,
    "datasource.export": m_export,
    "datasource.import": m_import,
    "jobs.run": m_jobs_run,
    "transfer.upload": m_transfer_upload,
    "transfer.download": m_transfer_download,
    "storage.delete": m_storage_delete,
    "device.detach": m_detach,
    "device.ping": m_ping,
    "device.status": m_status,
    "sync.position": m_sync_position,
    "sync.sql_changes": m_sync_sql_changes,
    "sync.sql_apply": m_sync_sql_apply,
    "sync.mongo_changes": m_sync_mongo_changes,
    "sync.mongo_apply": m_sync_mongo_apply,
}


def dispatch(method: str, params: Any, ctx: CallContext) -> Any:
    fn = METHODS.get(method) if isinstance(method, str) else None
    if fn is None:
        raise ApiError(400, "unknown_method", f"Unknown method: {method!r}")
    return fn(params if isinstance(params, dict) else {}, ctx)


def error_payload(exc: BaseException) -> dict:
    if isinstance(exc, ApiError):
        return {"status": exc.status_code, "code": exc.code, "message": exc.message, "details": exc.details}
    from app.services import connections

    msg = connections.redact(str(getattr(exc, "orig", None) or exc))
    return {"status": 500, "code": "device_internal_error", "message": msg[:1000], "details": {}}
