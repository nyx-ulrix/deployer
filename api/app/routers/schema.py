"""Schema viewer, DDL export, cross-database links and table/collection management
(docs/API.md "Schema")."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, not_found
from app.models import SchemaLink, utcnow
from app.serializers import iso
from app.services import audit, ddl_export, introspection, source_ops
from app.services.conventions import check_conventions
from app.services.sources import get_source, project_sources

router = APIRouter(tags=["schema"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]
Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]


def link_out(link: SchemaLink) -> dict:
    return {
        "id": link.id,
        "from_source_id": link.from_source_id,
        "from_entity": link.from_entity,
        "from_field": link.from_field,
        "to_source_id": link.to_source_id,
        "to_entity": link.to_entity,
        "to_field": link.to_field,
        "cardinality": link.cardinality,
        "note": link.note,
        "created_at": iso(link.created_at),
    }


def project_links(db: DbSession, project_id: str) -> list[SchemaLink]:
    return list(
        db.scalars(select(SchemaLink).where(SchemaLink.project_id == project_id).order_by(SchemaLink.created_at))
    )


# ---------------------------------------------------------------------------------------------
# schema + export
# ---------------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/schema")
def get_schema(
    access: Viewer,
    db: DbSession,
    source_id: str | None = None,
    sample: Annotated[int, Query(ge=0, le=introspection.MAX_SAMPLE)] = introspection.DEFAULT_SAMPLE,
) -> dict:
    project = access.project
    if source_id:
        sources = [get_source(db, project.id, source_id)]
    else:
        sources = project_sources(db, project.id)
    links = [link_out(link) for link in project_links(db, project.id)]
    db.commit()  # release the platform DB transaction while talking to project databases
    schemas = source_ops.introspect_sources(sources, sample)
    if source_id:
        links = [lk for lk in links if source_id in (lk["from_source_id"], lk["to_source_id"])]
    return {
        "sources": schemas,
        "links": links,
        "conventions": check_conventions(
            schemas,
            links if not source_id else [lk for lk in links if lk["from_source_id"] == lk["to_source_id"] == source_id],
        ),
        "generated_at": iso(utcnow()),
    }


def _slug_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "project"


@router.get("/projects/{project_id}/schema/export")
def export_schema(
    access: Viewer,
    db: DbSession,
    request: Request,
    format: Literal["sql", "mongo", "bundle"] = "bundle",
    source_id: str | None = None,
) -> Response:
    project = access.project
    if source_id:
        ds = get_source(db, project.id, source_id)
        if format == "sql" and ds.kind != "sql":
            raise ApiError(400, "wrong_source_kind", "format=sql needs an SQL data source")
        if format == "mongo" and ds.kind != "nosql":
            raise ApiError(400, "wrong_source_kind", "format=mongo needs a MongoDB data source")
        sources = [ds]
    else:
        sources = project_sources(db, project.id)
    links = [link_out(link) for link in project_links(db, project.id)]
    audit.record(
        db,
        "schema.export",
        request=request,
        user_id=access.user.id,
        project_id=project.id,
        format=format,
        source_id=source_id,
    )
    db.commit()
    now = datetime.now(UTC)
    base = _slug_filename(project.slug)
    if format == "sql":
        content = source_ops.export_sources(sources, "sql", now).encode("utf-8")
        filename, media = f"{base}-schema.sql", "application/sql"
    elif format == "mongo":
        content = source_ops.export_sources(sources, "nosql", now).encode("utf-8")
        filename, media = f"{base}-schema.mongo.js", "text/javascript"
    else:
        content = ddl_export.build_bundle(
            project_name=project.name,
            sql_text=source_ops.export_sources(sources, "sql", now),
            mongo_text=source_ops.export_sources(sources, "nosql", now),
            links=links,
            now=now,
        )
        filename, media = f"{base}-schema.zip", "application/zip"
    return Response(
        content=content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ---------------------------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------------------------


class LinkInput(BaseModel):
    from_source_id: str
    from_entity: str = Field(min_length=1, max_length=128)
    from_field: str = Field(min_length=1, max_length=255)
    to_source_id: str
    to_entity: str = Field(min_length=1, max_length=128)
    to_field: str = Field(min_length=1, max_length=255)
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
    note: str | None = Field(default=None, max_length=2000)


@router.get("/projects/{project_id}/schema/links")
def list_links(access: Viewer, db: DbSession) -> list[dict]:
    return [link_out(link) for link in project_links(db, access.project.id)]


@router.post("/projects/{project_id}/schema/links")
def create_link(body: LinkInput, access: Developer, db: DbSession, request: Request) -> dict:
    project = access.project
    get_source(db, project.id, body.from_source_id)
    get_source(db, project.id, body.to_source_id)
    link = SchemaLink(project_id=project.id, **body.model_dump())
    db.add(link)
    db.flush()
    audit.record(
        db,
        "schema.link_create",
        request=request,
        user_id=access.user.id,
        project_id=project.id,
        link_id=link.id,
        link_from=f"{body.from_entity}.{body.from_field}",
        link_to=f"{body.to_entity}.{body.to_field}",
    )
    db.commit()
    return link_out(link)


@router.delete("/projects/{project_id}/schema/links/{link_id}")
def delete_link(link_id: str, access: Developer, db: DbSession, request: Request) -> dict:
    link = db.get(SchemaLink, link_id)
    if link is None or link.project_id != access.project.id:
        raise not_found("Link")
    audit.record(
        db,
        "schema.link_delete",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        link_id=link.id,
    )
    db.delete(link)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------------------------
# tables & collections
# ---------------------------------------------------------------------------------------------


class ColumnReference(BaseModel):
    table: str
    column: str
    on_delete: Literal["cascade", "set null", "restrict"] | None = None


class ColumnSpec(BaseModel):
    name: str
    type: str
    nullable: bool | None = None
    default: str | int | float | bool | None = None
    primary_key: bool = False
    unique: bool = False
    auto_increment: bool = False
    references: ColumnReference | None = None


class TableSpec(BaseModel):
    name: str
    columns: list[ColumnSpec] = Field(default_factory=list, max_length=500)
    timestamps: bool = False


class CollectionInput(BaseModel):
    name: str
    validator: dict[str, Any] | None = None


@router.post("/projects/{project_id}/data-sources/{source_id}/tables")
def create_table(source_id: str, body: TableSpec, access: Developer, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id, kind="sql")
    spec = body.model_dump()
    source_ops.create_table(ds, spec)
    audit.record(
        db,
        "schema.table_create",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        table=body.name,
    )
    db.commit()
    entity = source_ops.sql_entity(ds, body.name)
    if entity is None:
        raise ApiError(500, "introspection_failed", "Table was created but could not be read back")
    return entity


@router.delete("/projects/{project_id}/data-sources/{source_id}/tables/{table}")
def drop_table(source_id: str, table: str, access: Admin, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id, kind="sql")
    from app.services import backups  # docs/BACKUPS.md: safety snapshot before a drop (per policy)

    backups.safety_snapshot(db, ds, trigger="pre_drop", user_id=access.user.id)
    source_ops.drop_table(ds, table)
    audit.record(
        db,
        "schema.table_drop",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        table=table,
    )
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/data-sources/{source_id}/collections")
def create_collection(
    source_id: str, body: CollectionInput, access: Developer, db: DbSession, request: Request
) -> dict:
    ds = get_source(db, access.project.id, source_id, kind="nosql")
    source_ops.create_collection(ds, body.name, body.validator)
    audit.record(
        db,
        "schema.collection_create",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        collection=body.name,
    )
    db.commit()
    entity = source_ops.mongo_entity(ds, body.name)
    if entity is None:
        raise ApiError(500, "introspection_failed", "Collection was created but could not be read back")
    return entity


@router.delete("/projects/{project_id}/data-sources/{source_id}/collections/{name}")
def drop_collection(source_id: str, name: str, access: Admin, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id, kind="nosql")
    from app.services import backups  # docs/BACKUPS.md: safety snapshot before a drop (per policy)

    backups.safety_snapshot(db, ds, trigger="pre_drop", user_id=access.user.id)
    source_ops.drop_collection(ds, name)
    audit.record(
        db,
        "schema.collection_drop",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        collection=name,
    )
    db.commit()
    return {"ok": True}
