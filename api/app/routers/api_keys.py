import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import AfterValidator, BaseModel, Field
from pydantic_core import PydanticCustomError
from sqlalchemy import select

from app.crypto import sha256_hex
from app.deps import DbSession, ProjectAccess, require_role
from app.errors import not_found
from app.models import ApiKey, utcnow
from app.serializers import iso
from app.services import audit

router = APIRouter(tags=["api-keys"])

Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]
PREFIX_LENGTH = 16


def api_key_out(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "role": key.role,
        "created_at": iso(key.created_at),
        "last_used_at": iso(key.last_used_at),
        "revoked_at": iso(key.revoked_at),
    }


def generate_secret(role: str) -> str:
    return f"dpl_{role}_{secrets.token_urlsafe(32)}"


def _clean(value: str) -> str:
    value = value.strip()
    if not value:
        raise PydanticCustomError("value_error", "Name must not be empty")
    return value


class ApiKeyCreate(BaseModel):
    name: Annotated[str, Field(max_length=120), AfterValidator(_clean)]
    role: Literal["anon", "service"]


@router.get("/projects/{project_id}/api-keys")
def list_api_keys(access: Admin, db: DbSession) -> list[dict]:
    keys = db.scalars(
        select(ApiKey).where(ApiKey.project_id == access.project.id).order_by(ApiKey.created_at.desc())
    ).all()
    return [api_key_out(k) for k in keys]


@router.post("/projects/{project_id}/api-keys")
def create_api_key(body: ApiKeyCreate, request: Request, access: Admin, db: DbSession) -> dict:
    secret = generate_secret(body.role)
    key = ApiKey(
        project_id=access.project.id,
        name=body.name,
        role=body.role,
        prefix=secret[:PREFIX_LENGTH],
        key_hash=sha256_hex(secret),
        created_by_id=access.user.id,
        created_at=utcnow(),
    )
    db.add(key)
    db.flush()
    audit.record(
        db,
        "api_key.create",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        api_key_id=key.id,
        role=key.role,
    )
    db.commit()
    return {"api_key": api_key_out(key), "secret": secret}


@router.delete("/projects/{project_id}/api-keys/{key_id}")
def revoke_api_key(key_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    key = db.get(ApiKey, key_id)
    if key is None or key.project_id != access.project.id:
        raise not_found("API key")
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        audit.record(
            db,
            "api_key.revoke",
            request=request,
            user_id=access.user.id,
            project_id=access.project.id,
            api_key_id=key.id,
        )
    db.commit()
    return {"ok": True}
