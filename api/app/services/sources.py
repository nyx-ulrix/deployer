"""Shared helpers for routers working with a project's data sources."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, not_found
from app.models import DataSource
from app.serializers import iso
from app.services import connections


def get_source(db: Session, project_id: str, source_id: str, kind: str | None = None) -> DataSource:
    ds = db.get(DataSource, source_id)
    if ds is None or ds.project_id != project_id:
        raise not_found("Data source")
    if kind and ds.kind != kind:
        noun = "SQL" if kind == "sql" else "NoSQL (MongoDB)"
        raise ApiError(400, "wrong_source_kind", f"This operation needs a {noun} data source")
    return ds


def project_sources(db: Session, project_id: str) -> list[DataSource]:
    return list(
        db.scalars(
            select(DataSource)
            .where(DataSource.project_id == project_id)
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
    }
