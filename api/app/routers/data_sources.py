"""Data sources (docs/API.md "Data sources")."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.crypto import encrypt_json
from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, forbidden
from app.models import DataSource, SchemaLink, utcnow
from app.services import audit, connections, provisioning
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


def _invalid(message: str) -> ApiError:
    return ApiError(422, "validation_error", message)


def normalize_input(body: DataSourceInput) -> tuple[str, dict[str, Any] | None]:
    """Validates the kind/mode/engine combination and returns (name, external config)."""
    name = body.name.strip()
    if not name:
        raise _invalid("name is required")
    if body.kind == "sql" and body.engine == "mongodb":
        raise _invalid("SQL data sources use mariadb, mysql or postgresql")
    if body.kind == "nosql" and body.engine != "mongodb":
        raise _invalid("NoSQL data sources use mongodb")
    if body.mode == "managed":
        if body.kind == "sql" and body.engine != "mariadb":
            raise _invalid("Managed SQL data sources use mariadb")
        return name, None
    cfg = body.config or {}
    if body.kind == "sql":
        missing = [k for k in ("host", "username", "database") if not str(cfg.get(k) or "").strip()]
        if missing:
            raise _invalid(f"config is missing: {', '.join(missing)}")
        port = cfg.get("port") or connections.DEFAULT_PORTS[body.engine]
        try:
            port = int(port)
        except (TypeError, ValueError) as exc:
            raise _invalid("config.port must be a number") from exc
        if not 1 <= port <= 65535:
            raise _invalid("config.port must be between 1 and 65535")
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
        raise _invalid("config.uri must start with mongodb:// or mongodb+srv://")
    if not database:
        raise _invalid("config.database is required")
    return name, {"uri": uri, "database": database}


def _ensure_name_free(db: DbSession, project_id: str, name: str) -> None:
    exists = db.scalar(select(DataSource.id).where(DataSource.project_id == project_id, DataSource.name == name))
    if exists:
        raise ApiError(409, "name_taken", f"A data source named '{name}' already exists in this project")


@router.get("/projects/{project_id}/data-sources")
def list_data_sources(access: Viewer, db: DbSession) -> list[dict]:
    return [data_source_out(ds) for ds in project_sources(db, access.project.id)]


@router.post("/projects/{project_id}/data-sources/test")
def test_data_source(body: DataSourceInput, access: Admin, db: DbSession) -> dict:
    _, config = normalize_input(body)
    if body.mode == "managed":
        from app.config import get_settings

        if body.kind == "nosql" and not get_settings().managed_mongodb_enabled:
            return {"ok": False, "message": "Managed MongoDB is not available on this host", "server_version": None}
        return {"ok": True, "message": "Managed databases are provisioned on this host", "server_version": None}
    ok, message, version = connections.try_config(body.kind, body.engine, config or {})
    return {"ok": ok, "message": message, "server_version": version}


@router.post("/projects/{project_id}/data-sources")
def create_data_source(body: DataSourceInput, access: Admin, db: DbSession, request: Request) -> dict:
    name, config = normalize_input(body)
    project = access.project
    _ensure_name_free(db, project.id, name)
    if body.mode == "managed":
        ds = provisioning.provision_managed_source(db, project, body.kind, name)
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
    try:
        db.flush()
    except Exception:
        if body.mode == "managed":
            try:
                provisioning.drop_managed_source(db, ds)
            except Exception:  # noqa: BLE001
                pass
        db.rollback()
        raise
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
    return data_source_out(ds)


@router.post("/projects/{project_id}/data-sources/{source_id}/check")
def check_data_source(source_id: str, access: Viewer, db: DbSession) -> dict:
    ds = get_source(db, access.project.id, source_id)
    connections.check_status(db, ds)
    db.commit()
    return data_source_out(ds)


@router.get("/projects/{project_id}/data-sources/{source_id}/connection")
def data_source_connection(source_id: str, access: Developer, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id)
    info = connections.connection_info(ds)
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
        provisioning.drop_managed_source(db, ds)
    connections.invalidate(ds.id)
    for link in db.scalars(
        select(SchemaLink).where(or_(SchemaLink.from_source_id == ds.id, SchemaLink.to_source_id == ds.id))
    ):
        db.delete(link)
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
    db.delete(ds)
    db.commit()
    return {"ok": True}
