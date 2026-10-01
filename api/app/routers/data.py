"""Data browser (docs/API.md "Data browser"). Also reachable with project API keys (docs/DATA_API.md)."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError
from app.services import data_browser, firestore, rtdb, source_ops
from app.services.sources import get_source

router = APIRouter(tags=["data"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer", api_keys=True))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer", api_keys=True))]

TABLE_ROWS = "/projects/{project_id}/data-sources/{source_id}/tables/{table}/rows"
COLLECTION_DOCS = "/projects/{project_id}/data-sources/{source_id}/collections/{name}/documents"
# Routed with `{name:path}`: a Firestore subcollection is a path, `users/u1/orders` (docs/CLOUD.md "C2-3").
DOCS_ROUTE = COLLECTION_DOCS.replace("{name}", "{name:path}")
# A Firebase Realtime Database is one JSON tree, read and written by path (docs/CLOUD.md "C2-4").
RTDB = "/projects/{project_id}/data-sources/{source_id}/rtdb"


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


class RtdbWrite(BaseModel):
    path: str = Field(default="", max_length=4096)  # "" is the root
    value: Any = None


def _sql_source(db: DbSession, access: ProjectAccess, source_id: str):
    # Operations go through source_ops so device-hosted sources are served by their device.
    ds = get_source(db, access.project.id, source_id, kind="sql")
    db.commit()  # don't hold the platform DB transaction open during project queries
    return ds


def _mongo_source(db: DbSession, access: ProjectAccess, source_id: str):
    ds = get_source(db, access.project.id, source_id, kind="nosql")
    db.commit()
    return ds


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
    ds = _sql_source(db, access, source_id)
    return source_ops.list_rows(ds, table, limit=limit, offset=offset, order_by=order_by or None, order=order)


@router.post(TABLE_ROWS)
def insert_row(source_id: str, table: str, body: RowInsert, access: Developer, db: DbSession) -> dict:
    return source_ops.insert_row(_sql_source(db, access, source_id), table, body.values)


@router.patch(TABLE_ROWS)
def update_row(source_id: str, table: str, body: RowUpdate, access: Developer, db: DbSession) -> dict:
    return source_ops.update_row(_sql_source(db, access, source_id), table, body.pk, body.values)


@router.delete(TABLE_ROWS)
def delete_row(
    source_id: str, table: str, access: Developer, db: DbSession, body: Annotated[RowDelete, Body()]
) -> dict:
    return source_ops.delete_row(_sql_source(db, access, source_id), table, body.pk)


# --- MongoDB, DynamoDB, Firestore ---------------------------------------------------------------


@router.get(DOCS_ROUTE)
def list_documents(
    source_id: str,
    name: str,
    access: Viewer,
    db: DbSession,
    filter: str | None = None,
    limit: Annotated[int, Query(ge=1, le=data_browser.MAX_LIMIT)] = 50,
    skip: Annotated[int, Query(ge=0)] = 0,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,  # DynamoDB / Firestore: the last next_cursor
) -> dict:
    ds = _mongo_source(db, access, source_id)
    return source_ops.list_documents(ds, name, filter_json=filter, limit=limit, skip=skip, cursor=cursor)


@router.post(DOCS_ROUTE)
def insert_document(source_id: str, name: str, body: DocumentInsert, access: Developer, db: DbSession) -> dict:
    return source_ops.insert_document(_mongo_source(db, access, source_id), name, body.document)


@router.patch(DOCS_ROUTE + "/{doc_id}")
def update_document(
    source_id: str, name: str, doc_id: str, body: DocumentUpdate, access: Developer, db: DbSession
) -> dict:
    return source_ops.update_document(_mongo_source(db, access, source_id), name, doc_id, body.set, body.unset)


@router.delete(DOCS_ROUTE + "/{doc_id}")
def delete_document(source_id: str, name: str, doc_id: str, access: Developer, db: DbSession) -> dict:
    return source_ops.delete_document(_mongo_source(db, access, source_id), name, doc_id)


@router.get(DOCS_ROUTE + "/{doc_id}/collections")
def list_subcollections(source_id: str, name: str, doc_id: str, access: Viewer, db: DbSession) -> dict:
    """Firestore: the collections under one document, as paths the documents routes take."""
    ds = _mongo_source(db, access, source_id)
    if ds.engine != firestore.ENGINE:
        raise ApiError(400, "not_supported", "Only Firestore documents have collections of their own")
    return firestore.subcollections(ds, name, doc_id)


# --- Firebase Realtime Database: read / write by path (docs/CLOUD.md "C2-4") --------------------------


def _rtdb_source(db: DbSession, access: ProjectAccess, source_id: str):
    ds = get_source(db, access.project.id, source_id, kind="nosql")
    if ds.engine != rtdb.ENGINE:
        raise ApiError(400, "wrong_source_kind", "These routes are for Firebase Realtime Databases")
    db.commit()
    return ds


def _json_or_text(value: str | None) -> Any:
    """Query values the Firebase way: JSON (`18`, `true`, `"18"`), anything else is text (`Oslo`)."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return value
    return parsed if isinstance(parsed, str | int | float | bool) else value


@router.get(RTDB)
def rtdb_read(
    source_id: str,
    access: Viewer,
    db: DbSession,
    path: Annotated[str, Query(max_length=4096)] = "",
    shallow: bool = False,
    order_by: Annotated[str | None, Query(alias="orderBy", max_length=1000)] = None,
    start_at: Annotated[str | None, Query(alias="startAt", max_length=1000)] = None,
    end_at: Annotated[str | None, Query(alias="endAt", max_length=1000)] = None,
    equal_to: Annotated[str | None, Query(alias="equalTo", max_length=1000)] = None,
    limit_to_first: Annotated[int | None, Query(alias="limitToFirst", ge=1)] = None,
    limit_to_last: Annotated[int | None, Query(alias="limitToLast", ge=1)] = None,
) -> dict:
    """The value at `path`; `shallow` cuts each child to `true` (or its plain value); orderBy + startAt / endAt /
    equalTo / limitToFirst / limitToLast filter like Firebase's REST API and add `children` in order."""
    query = {
        "shallow": shallow,
        "orderBy": _json_or_text(order_by),
        "startAt": _json_or_text(start_at),
        "endAt": _json_or_text(end_at),
        "equalTo": _json_or_text(equal_to),
        "limitToFirst": limit_to_first,
        "limitToLast": limit_to_last,
    }
    return rtdb.read(_rtdb_source(db, access, source_id), path, query)


@router.put(RTDB)
def rtdb_set(source_id: str, body: RtdbWrite, access: Developer, db: DbSession) -> dict:
    """Replaces the value at `path`."""
    return rtdb.write(_rtdb_source(db, access, source_id), "set", body.path, body.value)


@router.patch(RTDB)
def rtdb_update(source_id: str, body: RtdbWrite, access: Developer, db: DbSession) -> dict:
    """Sets the given children of `path` (keys may be deeper paths, `address/city`); others stay."""
    return rtdb.write(_rtdb_source(db, access, source_id), "update", body.path, body.value)


@router.post(RTDB)
def rtdb_push(source_id: str, body: RtdbWrite, access: Developer, db: DbSession) -> dict:
    """Adds `value` as a new child of `path` under a Firebase-made, time-ordered key."""
    return rtdb.write(_rtdb_source(db, access, source_id), "push", body.path, body.value)


@router.delete(RTDB)
def rtdb_delete(
    source_id: str, access: Developer, db: DbSession, path: Annotated[str, Query(max_length=4096)] = ""
) -> dict:
    return rtdb.write(_rtdb_source(db, access, source_id), "delete", path)
