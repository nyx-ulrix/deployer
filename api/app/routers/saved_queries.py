"""Saved queries / snippets of the query editor (docs/QUERY_EDITOR.md).

`query_text` is opaque here: the dashboard stores its notebook document in it. Folders are a plain
string per snippet; the dashboard splits `folder/name` itself, so "/" is refused in `folder`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import AfterValidator, BaseModel, Field
from pydantic_core import PydanticCustomError
from sqlalchemy import select

from app.deps import DbSession, ProjectAccess, require_role
from app.errors import forbidden, not_found, validation_error
from app.models import DataSource, SavedQuery, User, utcnow
from app.serializers import iso
from app.services import query_console

router = APIRouter(tags=["saved-queries"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]

Kind = Literal["sql", "nosql", "any"]


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise PydanticCustomError("value_error", "Name must not be empty")
    return value


def _clean_folder(value: str | None) -> str | None:
    value = (value or "").strip()
    if "/" in value:
        raise PydanticCustomError("value_error", "Folder names must not contain '/'")
    return value or None


Name = Annotated[str, Field(max_length=120), AfterValidator(_clean_name)]
Folder = Annotated[str | None, Field(max_length=120), AfterValidator(_clean_folder)]
QueryText = Annotated[str, Field(max_length=query_console.MAX_QUERY_CHARS)]


class SavedQueryCreate(BaseModel):
    name: Name
    folder: Folder = None
    query_text: QueryText
    data_source_id: str | None = None
    kind: Kind


class SavedQueryUpdate(BaseModel):
    name: Name | None = None
    folder: Folder = None
    query_text: QueryText | None = None
    data_source_id: str | None = None
    kind: Kind | None = None


def saved_query_out(sq: SavedQuery, owner_email: str | None) -> dict:
    return {
        "id": sq.id,
        "project_id": sq.project_id,
        "data_source_id": sq.data_source_id,
        "owner_id": sq.owner_id,
        "owner_email": owner_email or "",
        "name": sq.name,
        "folder": sq.folder,
        "query_text": sq.query_text,
        "kind": sq.kind,
        "created_at": iso(sq.created_at),
        "updated_at": iso(sq.updated_at),
    }


def _out(db: DbSession, sq: SavedQuery) -> dict:
    return saved_query_out(sq, db.scalar(select(User.email).where(User.id == sq.owner_id)))


def _check_source(db: DbSession, project_id: str, source_id: str | None) -> None:
    if source_id is None:
        return
    ds = db.get(DataSource, source_id)
    if ds is None or ds.project_id != project_id or ds.deleted_at is not None:
        raise validation_error("Unknown data source", {"data_source_id": source_id})


def _load_editable(db: DbSession, access: ProjectAccess, saved_query_id: str) -> SavedQuery:
    sq = db.get(SavedQuery, saved_query_id)
    if sq is None or sq.project_id != access.project.id:
        raise not_found("Saved query")
    if sq.owner_id != access.user.id and not access.at_least("admin"):
        raise forbidden("Only the owner of a saved query or an admin can change it")
    return sq


@router.get("/projects/{project_id}/saved-queries")
def list_saved_queries(access: Viewer, db: DbSession) -> list[dict]:
    rows = db.execute(
        select(SavedQuery, User.email)
        .outerjoin(User, User.id == SavedQuery.owner_id)
        .where(SavedQuery.project_id == access.project.id)
        .order_by(SavedQuery.folder.is_not(None), SavedQuery.folder, SavedQuery.name)
    ).all()
    return [saved_query_out(sq, email) for sq, email in rows]


@router.post("/projects/{project_id}/saved-queries", status_code=201)
def create_saved_query(body: SavedQueryCreate, access: Developer, db: DbSession) -> dict:
    _check_source(db, access.project.id, body.data_source_id)
    sq = SavedQuery(project_id=access.project.id, owner_id=access.user.id, **body.model_dump())
    db.add(sq)
    db.commit()
    return saved_query_out(sq, access.user.email)


@router.patch("/projects/{project_id}/saved-queries/{saved_query_id}")
def update_saved_query(saved_query_id: str, body: SavedQueryUpdate, access: Developer, db: DbSession) -> dict:
    sq = _load_editable(db, access, saved_query_id)
    changes = body.model_dump(exclude_unset=True)
    if "data_source_id" in changes:
        _check_source(db, access.project.id, changes["data_source_id"])
    for key, value in changes.items():
        setattr(sq, key, value)
    sq.updated_at = utcnow()  # also when nothing changed: a save is a save
    db.commit()
    return _out(db, sq)


@router.delete("/projects/{project_id}/saved-queries/{saved_query_id}")
def delete_saved_query(saved_query_id: str, access: Developer, db: DbSession) -> dict:
    db.delete(_load_editable(db, access, saved_query_id))
    db.commit()
    return {"ok": True}
