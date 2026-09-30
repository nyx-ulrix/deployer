"""Data sources (docs/API.md "Data sources")."""

from __future__ import annotations

import ipaddress
import socket
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.crypto import decrypt_json, encrypt_json
from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, forbidden, validation_error
from app.models import DataSource, utcnow
from app.services import audit, connections, devices, provisioning, source_ops
from app.services.sources import data_source_out, get_source, project_sources

router = APIRouter(tags=["data-sources"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]
Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]


class DataSourceInput(BaseModel):
    kind: Literal["sql", "nosql"]
    mode: Literal["managed", "external"]
    engine: Literal["mariadb", "mysql", "postgresql", "mongodb"]
    name: str = Field(min_length=1, max_length=63)
    config: dict[str, Any] | None = None
    # Managed sources only: host device to place the database on (docs/DEVICES.md); null = main server.
    device_id: str | None = None


# A-027: Deployer connects from inside its container, where localhost is the container itself.
SAME_PC_HOST_MESSAGE = (
    "'{host}' is the Deployer container itself, not this PC. For a database on this PC, use the PC's "
    "network IP address (from ipconfig) as the host (host.docker.internal reaches Windows only with the "
    "Docker Desktop runtime), and let the database accept network connections (MySQL/MariaDB: "
    "bind-address=0.0.0.0; PostgreSQL: listen_addresses and pg_hba.conf)."
)


def _reject_loopback(host: str | None) -> None:
    h = (host or "").strip().strip("[]").lower()
    try:
        ip = ipaddress.ip_address(h)
        loopback = ip.is_loopback or ip.is_unspecified
    except ValueError:
        loopback = h == "localhost" or h.endswith(".localhost")
    if loopback:
        raise validation_error(SAME_PC_HOST_MESSAGE.format(host=h))


# A-114: the connection test reaches whatever host it is given, from inside Deployer's network. Project
# admins who are not the instance owner may not point it at Deployer's own containers (Docker DNS names,
# Docker's default 172.16.0.0/12 address pool) or at link-local addresses (cloud metadata endpoints).
# LAN addresses (10.x, 192.168.x) stay allowed: that is where a database on this PC or the network lives.
DOCKER_POOL = ipaddress.ip_network("172.16.0.0/12")
INTERNAL_HOST_MESSAGE = (
    "'{host}' is on Deployer's own internal network. Only the instance owner can connect a data source "
    "there; use the database server's LAN IP address or public hostname."
)


def _config_hosts(kind: str, config: dict[str, Any]) -> list[str]:
    if kind == "sql":
        # psycopg/libpq try each host of a comma-separated list ("db.example.com,mariadb") in turn.
        return config["host"].split(",")
    uri = config["uri"]
    scheme, _, rest = uri.partition("://")
    netloc = rest.split("/", 1)[0].split("?", 1)[0].rsplit("@", 1)[-1]
    # Every seed host of a replica-set URI, not just the first.
    return [connections.parse_mongo_uri(f"{scheme}://{part}")["host"] or "" for part in netloc.split(",")]


def _resolve(host: str) -> list[str]:
    try:
        return [info[4][0] for info in socket.getaddrinfo(host, None)]
    except (OSError, UnicodeError):
        return []  # unresolvable: the connection test itself reports that


def _is_internal(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
        or ip in DOCKER_POOL
    )


def _reject_internal(kind: str, config: dict[str, Any]) -> None:
    # ponytail: resolve-then-connect, a DNS name that changes answers in between slips through;
    # pinning the resolved IP into the driver would close that but breaks TLS hostname checks.
    for host in _config_hosts(kind, config):
        h = host.strip().strip("[]").rstrip(".").lower()
        if not h:
            continue
        try:
            addresses = [str(ipaddress.ip_address(h))]
        except ValueError:
            if "." not in h:  # Docker DNS: compose service and container names (mariadb, redis, ...)
                raise validation_error(INTERNAL_HOST_MESSAGE.format(host=h)) from None
            # mongodb+srv names are SRV records, usually without an address of their own.
            addresses = _resolve(h)
        if any(_is_internal(a) for a in addresses):
            raise validation_error(INTERNAL_HOST_MESSAGE.format(host=h))


def external_config(body: DataSourceInput, access: ProjectAccess) -> tuple[str, dict[str, Any] | None]:
    """normalize_input plus the A-114 internal-network check for everyone but the instance owner."""
    name, config = normalize_input(body)
    if config is not None and not access.user.is_instance_owner:
        _reject_internal(body.kind, config)
    return name, config


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=63)
    # External sources only: keys given here replace the stored ones (e.g. just a rotated password).
    config: dict[str, Any] | None = None


def normalize_input(body: DataSourceInput) -> tuple[str, dict[str, Any] | None]:
    """Validates the kind/mode/engine combination and returns (name, external config)."""
    name = body.name.strip()
    if not name:
        raise validation_error("name is required")
    if body.kind == "sql" and body.engine == "mongodb":
        raise validation_error("SQL data sources use mariadb, mysql or postgresql")
    if body.kind == "nosql" and body.engine != "mongodb":
        raise validation_error("NoSQL data sources use mongodb")
    if body.mode == "managed":
        if body.kind == "sql" and body.engine != "mariadb":
            raise validation_error("Managed SQL data sources use mariadb")
        return name, None
    cfg = body.config or {}
    if body.kind == "sql":
        missing = [k for k in ("host", "username", "database") if not str(cfg.get(k) or "").strip()]
        if missing:
            raise validation_error(f"config is missing: {', '.join(missing)}")
        port = cfg.get("port") or connections.DEFAULT_PORTS[body.engine]
        try:
            port = int(port)
        except (TypeError, ValueError) as exc:
            raise validation_error("config.port must be a number") from exc
        if not 1 <= port <= 65535:
            raise validation_error("config.port must be between 1 and 65535")
        _reject_loopback(str(cfg["host"]))
        return name, {
            "host": str(cfg["host"]).strip(),
            "port": port,
            "username": str(cfg["username"]),
            "password": str(cfg.get("password") or ""),
            "database": str(cfg["database"]).strip(),
            "tls": bool(cfg.get("tls", False)),
        }
    uri = str(cfg.get("uri") or "").strip()
    database = str(cfg.get("database") or "").strip()
    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        raise validation_error("config.uri must start with mongodb:// or mongodb+srv://")
    if not database:
        raise validation_error("config.database is required")
    _reject_loopback(connections.parse_mongo_uri(uri)["host"])
    return name, {"uri": uri, "database": database}


def _ensure_name_free(db: DbSession, project_id: str, name: str, *, except_id: str | None = None) -> None:
    query = select(DataSource.id).where(DataSource.project_id == project_id, DataSource.name == name)
    if except_id:
        query = query.where(DataSource.id != except_id)
    exists = db.scalar(query)
    if exists:
        raise ApiError(409, "name_taken", f"A data source named '{name}' already exists in this project")


@router.get("/projects/{project_id}/data-sources")
def list_data_sources(access: Viewer, db: DbSession) -> list[dict]:
    return [data_source_out(ds) for ds in project_sources(db, access.project.id)]


@router.post("/projects/{project_id}/data-sources/test")
def test_data_source(body: DataSourceInput, access: Admin, db: DbSession) -> dict:
    _, config = external_config(body, access)
    if body.mode == "managed":
        from app.config import get_settings

        if body.device_id:
            from app.services import device_rpc

            device = devices.validate_placement(db, access.project, body.device_id, body.kind)
            if not device_rpc.is_online(device.id):
                return {"ok": False, "message": f"Host device '{device.name}' is offline", "server_version": None}
            message = f"Will be provisioned on host device '{device.name}'"
            return {"ok": True, "message": message, "server_version": None}
        if body.kind == "nosql" and not get_settings().managed_mongodb_enabled:
            return {"ok": False, "message": "Managed MongoDB is not available on this host", "server_version": None}
        return {"ok": True, "message": "Managed databases are provisioned on this host", "server_version": None}
    ok, message, version = connections.try_config(body.kind, body.engine, config or {})
    return {"ok": ok, "message": message, "server_version": version}


@router.post("/projects/{project_id}/data-sources")
def create_data_source(body: DataSourceInput, access: Admin, db: DbSession, request: Request) -> dict:
    name, config = external_config(body, access)
    project = access.project
    _ensure_name_free(db, project.id, name)
    if body.mode == "managed":
        device = devices.validate_placement(db, project, body.device_id, body.kind)
        placement = {"device_id": device.id} if device else {}
        ds = provisioning.provision_managed_source(db, project, body.kind, name, **placement)
    else:
        assert config is not None
        ok, message, version = connections.try_config(body.kind, body.engine, config)
        if not ok:
            raise ApiError(400, "connection_failed", message)
        ds = DataSource(
            project_id=project.id,
            name=name,
            kind=body.kind,
            engine=body.engine,
            mode="external",
            database_name=config["database"],
            config_encrypted=encrypt_json(config),
            status="ok",
            status_message=f"Connected (server {version})" if version else "Connected",
            last_checked_at=utcnow(),
        )
        db.add(ds)
    # A-110: until the commit lands, a new managed database and user have no row pointing at them,
    # so any failure up to and including the commit drops them again.
    try:
        db.flush()
        audit.record(
            db,
            "data_source.create",
            request=request,
            user_id=access.user.id,
            project_id=project.id,
            data_source_id=ds.id,
            name=ds.name,
            kind=ds.kind,
            engine=ds.engine,
            mode=ds.mode,
        )
        db.commit()
    except Exception:
        if body.mode == "managed":
            try:
                provisioning.drop_managed_source(db, ds)
            except Exception:  # noqa: BLE001
                pass
        db.rollback()
        raise
    return data_source_out(ds)


@router.patch("/projects/{project_id}/data-sources/{source_id}")
def update_data_source(source_id: str, body: DataSourceUpdate, access: Admin, db: DbSession, request: Request) -> dict:
    """A-030: rename a source or change an external source's connection (password rotation) in place,
    keeping its id, schema links, key configs and saved queries."""
    ds = get_source(db, access.project.id, source_id)
    if body.config is not None and ds.mode != "external":
        raise validation_error("Managed databases have no connection settings to edit")
    name = (body.name or ds.name).strip()
    if not name:
        raise validation_error("name is required")
    config = None
    if body.config is not None:
        merged = {**decrypt_json(ds.config_encrypted), **body.config}
        _, config = external_config(
            DataSourceInput(kind=ds.kind, mode=ds.mode, engine=ds.engine, name=name, config=merged), access
        )
    changed = []
    if name != ds.name:
        _ensure_name_free(db, access.project.id, name, except_id=ds.id)
        ds.name = name
        changed.append("name")
    if config is not None and config != decrypt_json(ds.config_encrypted):
        ok, message, version = connections.try_config(ds.kind, ds.engine, config)
        if not ok:
            raise ApiError(400, "connection_failed", message)
        ds.config_encrypted = encrypt_json(config)
        ds.database_name = config["database"]
        ds.status = "ok"
        ds.status_message = f"Connected (server {version})" if version else "Connected"
        ds.last_checked_at = utcnow()
        changed.append("config")
    if changed:
        connections.invalidate(ds.id)
        audit.record(
            db,
            "data_source.update",
            request=request,
            user_id=access.user.id,
            project_id=access.project.id,
            data_source_id=ds.id,
            name=ds.name,
            changed=changed,
        )
        db.commit()
    return data_source_out(ds)


@router.post("/projects/{project_id}/data-sources/{source_id}/check")
def check_data_source(source_id: str, access: Viewer, db: DbSession) -> dict:
    ds = get_source(db, access.project.id, source_id)
    source_ops.check_status(db, ds)
    db.commit()
    return data_source_out(ds)


@router.get("/projects/{project_id}/data-sources/{source_id}/connection")
def data_source_connection(source_id: str, access: Developer, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id)
    info = source_ops.connection_info(ds)
    audit.record(
        db,
        "data_source.credentials_view",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
    )
    db.commit()
    return info


@router.delete("/projects/{project_id}/data-sources/{source_id}")
def delete_data_source(source_id: str, access: Admin, db: DbSession, request: Request, drop: bool = False) -> dict:
    ds = get_source(db, access.project.id, source_id)
    if drop:
        if not access.at_least("owner"):
            raise forbidden("Only the project owner can drop a database")
        if ds.mode != "managed":
            raise ApiError(
                400, "cannot_drop_external", "External databases are never dropped; delete without drop=true"
            )
        connections.require_host(ds)  # A-047: nothing on this server to drop
    # docs/BACKUPS.md: soft delete ("Recently deleted" for 30 days). Managed sources get a final
    # snapshot first; with drop=true the database is dropped by that job once the snapshot succeeded.
    from app.services import backups, jobs

    connections.invalidate(ds.id)
    # Schema links survive a soft delete (hidden by project_links, back on undelete); a hard delete or
    # the 30-day purge removes them through the schema_links FKs (ON DELETE CASCADE).
    audit.record(
        db,
        "data_source.delete",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        name=ds.name,
        kind=ds.kind,
        engine=ds.engine,
        mode=ds.mode,
        database_name=ds.database_name,
        dropped=bool(drop),
    )
    if not backups.supported(ds):
        # External databases are the provider's responsibility: nothing to snapshot, delete right away.
        db.delete(ds)
        db.commit()
        return {"ok": True}
    finalize = backups.soft_delete_source(db, ds, user_id=access.user.id, drop=bool(drop))
    db.commit()
    if finalize is not None:
        jobs.dispatch(finalize.id)
    return {"ok": True, "job": jobs.job_out(finalize)} if finalize is not None else {"ok": True}
