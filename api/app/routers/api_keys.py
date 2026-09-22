"""Project API keys (docs/DATA_API.md): create / list / revoke, reveal the secret again, and an app
config JSON download."""

import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, Field
from pydantic_core import PydanticCustomError
from sqlalchemy import select

from app.crypto import decrypt_secret, encrypt_secret, sha256_hex
from app.deps import DbSession, ProjectAccess, require_role
from app.errors import conflict, not_found
from app.models import ApiKey, utcnow
from app.routers.data import COLLECTION_DOCS, TABLE_ROWS
from app.serializers import iso
from app.services import audit
from app.services.instance_settings import public_url
from app.services.sources import project_sources

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
        "revealable": key.secret_encrypted is not None,
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
        secret_encrypted=encrypt_secret(secret),
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


def _project_key(db: DbSession, access: ProjectAccess, key_id: str) -> ApiKey:
    key = db.get(ApiKey, key_id)
    if key is None or key.project_id != access.project.id:
        raise not_found("API key")
    return key


def _secret(key: ApiKey) -> str:
    if key.revoked_at is not None:
        raise conflict("api_key_revoked", "This key has been revoked")
    if not key.secret_encrypted:
        raise conflict("not_revealable", "This key was created before Deployer kept secrets; create a new key")
    return decrypt_secret(key.secret_encrypted)


@router.get("/projects/{project_id}/api-keys/{key_id}/reveal")
def reveal_api_key(key_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    key = _project_key(db, access, key_id)
    secret = _secret(key)
    audit.record(
        db, "api_key.reveal", request=request, user_id=access.user.id, project_id=access.project.id, api_key_id=key.id
    )
    db.commit()
    return {"secret": secret}


@router.get("/projects/{project_id}/api-keys/{key_id}/config")
def api_key_config(key_id: str, request: Request, access: Admin, db: DbSession) -> JSONResponse:
    """App config JSON (docs/DATA_API.md "Config file"), served as a download."""
    key = _project_key(db, access, key_id)
    secret = _secret(key)
    project = access.project
    audit.record(
        db, "api_key.config", request=request, user_id=access.user.id, project_id=project.id, api_key_id=key.id
    )
    config = {
        "deployer": {
            "url": f"{public_url(db)}/v1",
            "project_id": project.id,
            "project": project.slug,
            "role": key.role,
            "api_key": secret,
            "data_sources": [
                {"id": ds.id, "name": ds.name, "kind": ds.kind, "engine": ds.engine}
                for ds in project_sources(db, project.id)
            ],
            "endpoints": {
                "rows": TABLE_ROWS,
                "documents": COLLECTION_DOCS,
                "query": "/projects/{project_id}/data-sources/{source_id}/query",
                "schema": "/projects/{project_id}/schema",
            },
            "generated_at": iso(utcnow()),
        }
    }
    db.commit()
    return JSONResponse(
        config, headers={"Content-Disposition": f'attachment; filename="deployer-{project.slug}-{key.role}.json"'}
    )


@router.delete("/projects/{project_id}/api-keys/{key_id}")
def revoke_api_key(key_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    key = _project_key(db, access, key_id)
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
