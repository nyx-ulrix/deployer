"""Saved queries / snippets of the query editor (docs/QUERY_EDITOR.md).

`query_text` is opaque here: the dashboard stores its notebook document in it. Folders are a plain
string per snippet; the dashboard splits `folder/name` itself, so "/" is refused in `folder`.

Phase 2 (versions): every text change appends a `saved_query_versions` row and bumps
`saved_queries.version`. Writes must carry the client's `version`; a stale one is answered with
409 `version_conflict` and the current row, so the client can diff and merge. No silent overwrites.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import AfterValidator, BaseModel, Field
from pydantic_core import PydanticCustomError
from sqlalchemy import and_, select

from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, forbidden, not_found, validation_error
from app.models import DataSource, SavedQuery, SavedQueryVersion, User, utcnow
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
Message = Annotated[str | None, Field(max_length=200)]


class SavedQueryCreate(BaseModel):
    name: Name
    folder: Folder = None
    query_text: QueryText
    data_source_id: str | None = None
    kind: Kind
    message: Message = None


class SavedQueryUpdate(BaseModel):
    name: Name | None = None
    folder: Folder = None
    query_text: QueryText | None = None
    data_source_id: str | None = None
    kind: Kind | None = None
    message: Message = None
    version: int


class RestoreBody(BaseModel):
    version: int
    current_version: int
    message: Message = None


def saved_query_out(sq: SavedQuery, owner_email: str | None, updated_by_email: str | None) -> dict:
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
        "version": sq.version,
        "updated_by_email": updated_by_email or "",
        "created_at": iso(sq.created_at),
        "updated_at": iso(sq.updated_at),
    }


def version_out(v: SavedQueryVersion, *, with_text: bool = False) -> dict:
    out = {
        "id": v.id,
        "version": v.version,
        "author_id": v.author_id,
        "author_email": v.author_email,
        "message": v.message,
        "created_at": iso(v.created_at),
        "chars": len(v.query_text),
    }
    if with_text:
        out["query_text"] = v.query_text
    return out


# The version row whose number is the saved query's current one; its author is `updated_by_email`.
_CURRENT_VERSION = and_(
    SavedQueryVersion.saved_query_id == SavedQuery.id, SavedQueryVersion.version == SavedQuery.version
)


def _out(db: DbSession, sq: SavedQuery) -> dict:
    db.flush()
    row = db.execute(
        select(User.email, SavedQueryVersion.author_email)
        .select_from(SavedQuery)
        .outerjoin(User, User.id == SavedQuery.owner_id)
        .outerjoin(SavedQueryVersion, _CURRENT_VERSION)
        .where(SavedQuery.id == sq.id)
    ).one()
    return saved_query_out(sq, *row)


def _check_source(db: DbSession, project_id: str, source_id: str | None) -> None:
    if source_id is None:
        return
    ds = db.get(DataSource, source_id)
    if ds is None or ds.project_id != project_id or ds.deleted_at is not None:
        raise validation_error("Unknown data source", {"data_source_id": source_id})


def _load(db: DbSession, access: ProjectAccess, saved_query_id: str, *, for_update: bool = False) -> SavedQuery:
    # Writers lock the row: two saves racing on the same version must serialise so the second one
    # sees the bumped version and gets a 409 instead of tripping the unique (id, version) index.
    sq = db.get(SavedQuery, saved_query_id, with_for_update=for_update)
    if sq is None or sq.project_id != access.project.id:
        raise not_found("Saved query")
    return sq


def _check_version(db: DbSession, sq: SavedQuery, client_version: int) -> None:
    if client_version != sq.version:
        raise ApiError(409, "version_conflict", "Someone saved a newer version", {"current": _out(db, sq)})


def _add_version(db: DbSession, sq: SavedQuery, user: User, text: str, message: str | None) -> None:
    """Append a version row with `text` and make it current (history is never rewritten)."""
    sq.version = (sq.version or 0) + 1
    sq.query_text = text
    sq.updated_at = utcnow()
    db.add(
        SavedQueryVersion(
            saved_query_id=sq.id,
            version=sq.version,
            query_text=text,
            author_id=user.id,
            author_email=user.email,
            message=message,
        )
    )


@router.get("/projects/{project_id}/saved-queries")
def list_saved_queries(access: Viewer, db: DbSession) -> list[dict]:
    rows = db.execute(
        select(SavedQuery, User.email, SavedQueryVersion.author_email)
        .outerjoin(User, User.id == SavedQuery.owner_id)
        .outerjoin(SavedQueryVersion, _CURRENT_VERSION)
        .where(SavedQuery.project_id == access.project.id)
        .order_by(SavedQuery.folder.is_not(None), SavedQuery.folder, SavedQuery.name)
    ).all()
    return [saved_query_out(sq, email, by) for sq, email, by in rows]


@router.post("/projects/{project_id}/saved-queries", status_code=201)
def create_saved_query(body: SavedQueryCreate, access: Developer, db: DbSession) -> dict:
    _check_source(db, access.project.id, body.data_source_id)
    fields = body.model_dump(exclude={"message"})
    sq = SavedQuery(project_id=access.project.id, owner_id=access.user.id, version=0, **fields)
    db.add(sq)
    db.flush()
    _add_version(db, sq, access.user, body.query_text, body.message)
    db.commit()
    return saved_query_out(sq, access.user.email, access.user.email)


@router.patch("/projects/{project_id}/saved-queries/{saved_query_id}")
def update_saved_query(saved_query_id: str, body: SavedQueryUpdate, access: Developer, db: DbSession) -> dict:
    sq = _load(db, access, saved_query_id, for_update=True)
    _check_version(db, sq, body.version)
    changes = body.model_dump(exclude_unset=True, exclude={"version", "message"})
    if "data_source_id" in changes:
        _check_source(db, access.project.id, changes["data_source_id"])
    text = changes.pop("query_text", None)
    for key, value in changes.items():
        setattr(sq, key, value)
    if text is not None and text != sq.query_text:
        _add_version(db, sq, access.user, text, body.message)
    sq.updated_at = utcnow()  # also when nothing changed: a save is a save
    db.commit()
    return _out(db, sq)


@router.delete("/projects/{project_id}/saved-queries/{saved_query_id}")
def delete_saved_query(saved_query_id: str, access: Developer, db: DbSession) -> dict:
    sq = _load(db, access, saved_query_id)
    if sq.owner_id != access.user.id and not access.at_least("admin"):
        raise forbidden("Only the owner of a saved query or an admin can delete it")
    db.delete(sq)
    db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/saved-queries/{saved_query_id}/versions")
def list_versions(saved_query_id: str, access: Viewer, db: DbSession) -> dict:
    sq = _load(db, access, saved_query_id)
    rows = db.scalars(
        select(SavedQueryVersion)
        .where(SavedQueryVersion.saved_query_id == sq.id)
        .order_by(SavedQueryVersion.version.desc())
    )
    return {"versions": [version_out(v) for v in rows]}


def _load_version(db: DbSession, sq: SavedQuery, number: int) -> SavedQueryVersion:
    v = db.scalar(
        select(SavedQueryVersion).where(SavedQueryVersion.saved_query_id == sq.id, SavedQueryVersion.version == number)
    )
    if v is None:
        raise not_found("Version")
    return v


@router.get("/projects/{project_id}/saved-queries/{saved_query_id}/versions/{number}")
def get_version(saved_query_id: str, number: int, access: Viewer, db: DbSession) -> dict:
    return version_out(_load_version(db, _load(db, access, saved_query_id), number), with_text=True)


@router.post("/projects/{project_id}/saved-queries/{saved_query_id}/restore")
def restore_version(saved_query_id: str, body: RestoreBody, access: Developer, db: DbSession) -> dict:
    sq = _load(db, access, saved_query_id, for_update=True)
    old = _load_version(db, sq, body.version)
    _check_version(db, sq, body.current_version)
    _add_version(db, sq, access.user, old.query_text, body.message or f"Restored version {old.version}")
    db.commit()
    return _out(db, sq)
