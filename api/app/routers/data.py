"""Data browser (docs/API.md "Data browser")."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from app.deps import DbSession, ProjectAccess, require_role
from app.services import connections, data_browser
from app.services.sources import get_source

router = APIRouter(tags=["data"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]

TABLE_ROWS = "/projects/{project_id}/data-sources/{source_id}/tables/{table}/rows"
COLLECTION_DOCS = "/projects/{project_id}/data-sources/{source_id}/collections/{name}/documents"


class RowInsert(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class RowUpdate(BaseModel):
    pk: dict[str, Any]
    values: dict[str, Any]


class RowDelete(BaseModel):
    pk: dict[str, Any]


class DocumentInsert(BaseModel):
    document: dict[str, Any]


class DocumentUpdate(BaseModel):
    set: dict[str, Any] = Field(default_factory=dict)
    unset: list[str] | None = None


def _sql_engine(db: DbSession, access: ProjectAccess, source_id: str):
    ds = get_source(db, access.project.id, source_id, kind="sql")
    engine = connections.get_sql_engine(ds)
    db.commit()  # don't hold the platform DB transaction open during project queries
    return engine


def _mongo_db(db: DbSession, access: ProjectAccess, source_id: str):
    ds = get_source(db, access.project.id, source_id, kind="nosql")
    database = connections.get_mongo_db(ds)
    db.commit()
    return database


# --- SQL ---------------------------------------------------------------------------------------


@router.get(TABLE_ROWS)
def list_rows(
    source_id: str,
    table: str,
    access: Viewer,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=data_browser.MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order_by: str | None = None,
    order: Literal["asc", "desc"] = "asc",
) -> dict:
    engine = _sql_engine(db, access, source_id)
    return data_browser.list_rows(engine, table, limit=limit, offset=offset, order_by=order_by or None, order=order)


@router.post(TABLE_ROWS)
def insert_row(source_id: str, table: str, body: RowInsert, access: Developer, db: DbSession) -> dict:
    return data_browser.insert_row(_sql_engine(db, access, source_id), table, body.values)


@router.patch(TABLE_ROWS)
def update_row(source_id: str, table: str, body: RowUpdate, access: Developer, db: DbSession) -> dict:
    return data_browser.update_row(_sql_engine(db, access, source_id), table, body.pk, body.values)


@router.delete(TABLE_ROWS)
def delete_row(
    source_id: str, table: str, access: Developer, db: DbSession, body: Annotated[RowDelete, Body()]
) -> dict:
    return data_browser.delete_row(_sql_engine(db, access, source_id), table, body.pk)


# --- MongoDB -----------------------------------------------------------------------------------


@router.get(COLLECTION_DOCS)
def list_documents(
    source_id: str,
    name: str,
    access: Viewer,
    db: DbSession,
    filter: str | None = None,
    limit: Annotated[int, Query(ge=1, le=data_browser.MAX_LIMIT)] = 50,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    database = _mongo_db(db, access, source_id)
    return data_browser.list_documents(database, name, filter_json=filter, limit=limit, skip=skip)


@router.post(COLLECTION_DOCS)
def insert_document(source_id: str, name: str, body: DocumentInsert, access: Developer, db: DbSession) -> dict:
    return data_browser.insert_document(_mongo_db(db, access, source_id), name, body.document)


@router.patch(COLLECTION_DOCS + "/{doc_id}")
def update_document(
    source_id: str, name: str, doc_id: str, body: DocumentUpdate, access: Developer, db: DbSession
) -> dict:
    return data_browser.update_document(_mongo_db(db, access, source_id), name, doc_id, body.set, body.unset)


@router.delete(COLLECTION_DOCS + "/{doc_id}")
def delete_document(source_id: str, name: str, doc_id: str, access: Developer, db: DbSession) -> dict:
    return data_browser.delete_document(_mongo_db(db, access, source_id), name, doc_id)
