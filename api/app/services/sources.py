"""Shared helpers for routers working with a project's data sources."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, not_found
from app.models import DataSource
from app.serializers import iso
from app.services import connections


def get_source(
    db: Session, project_id: str, source_id: str, kind: str | None = None, *, include_deleted: bool = False
) -> DataSource:
    ds = db.get(DataSource, source_id)
    if ds is None or ds.project_id != project_id:
        raise not_found("Data source")
    # Soft-deleted sources ("Recently deleted", docs/BACKUPS.md) are only reachable from backup routes.
    if ds.deleted_at is not None and not include_deleted:
        raise not_found("Data source")
    if kind and ds.kind != kind:
        noun = "SQL" if kind == "sql" else "NoSQL (MongoDB)"
        raise ApiError(400, "wrong_source_kind", f"This operation needs a {noun} data source")
    return ds


def project_sources(db: Session, project_id: str) -> list[DataSource]:
    return list(
        db.scalars(
            select(DataSource)
            .where(DataSource.project_id == project_id, DataSource.deleted_at.is_(None))
            .order_by(DataSource.created_at, DataSource.name)
        )
    )


def data_source_out(ds: DataSource) -> dict:
    return {
        "id": ds.id,
        "project_id": ds.project_id,
        "name": ds.name,
        "kind": ds.kind,
        "engine": ds.engine,
        "mode": ds.mode,
        "database_name": ds.database_name,
        "status": ds.status,
        "status_message": ds.status_message,
        "last_checked_at": iso(ds.last_checked_at),
        "display": connections.display_for(ds),
        "created_at": iso(ds.created_at),
        # docs/DEVICES.md: host device of a managed source (null = main server).
        "device_id": ds.device_id,
        "device_name": _device_name(ds),
        # docs/COHOSTING.md: live copies on co-host devices.
        "replicas": _replicas(ds),
    }


def _replicas(ds: DataSource) -> list[dict]:
    from sqlalchemy.orm import object_session

    from app.services import cohosting

    session = object_session(ds)
    if session is None or ds.mode != "managed":
        return []
    return cohosting.source_replicas(session, ds.id)


def _device_name(ds: DataSource) -> str | None:
    if not ds.device_id:
        return None
    from sqlalchemy.orm import object_session

    from app.models import Device

    session = object_session(ds)
    device = session.get(Device, ds.device_id) if session is not None else None
    return device.name if device else None
