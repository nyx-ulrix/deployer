"""Shared FastAPI dependencies: current user and project role checks."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import sha256_hex
from app.db import get_db
from app.errors import ApiError, forbidden, not_found, unauthorized
from app.models import ApiKey, Project, ProjectMember, User, role_rank, utcnow

DbSession = Annotated[Session, Depends(get_db)]


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"], audience="deployer")
    except jwt.PyJWTError as exc:
        raise unauthorized("Invalid or expired access token") from exc
    if claims.get("typ") != "access":
        raise unauthorized("Invalid access token")
    return claims


def bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized()
    return token


def api_key_not_allowed() -> ApiError:
    return ApiError(401, "api_key_not_allowed", "API keys can only call the data, query and schema endpoints")


def get_current_user(request: Request, db: DbSession) -> User:
    token = bearer_token(request)
    if token.startswith(API_KEY_PREFIX):
        raise api_key_not_allowed()
    claims = decode_access_token(token)
    user = db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise unauthorized("Account not found or disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_instance_owner(user: CurrentUser) -> User:
    if not user.is_instance_owner:
        raise forbidden("Only the instance owner can do that")
    return user


InstanceOwner = Annotated[User, Depends(require_instance_owner)]


@dataclass
class ProjectAccess:
    project: Project
    user: User  # for API keys: the key's creator, or the project owner if that account is gone
    role: str
    api_key: ApiKey | None = None

    def at_least(self, role: str) -> bool:
        return role_rank(self.role) >= role_rank(role)

    @property
    def api_key_id(self) -> str | None:
        return self.api_key.id if self.api_key else None


API_KEY_PREFIX = "dpl_"
API_KEY_ROLES = {"anon": "viewer", "service": "developer"}
LAST_USED_INTERVAL = timedelta(seconds=60)  # `last_used_at` is written at most this often per key


def load_api_key_access(db: Session, token: str, project_id: str) -> ProjectAccess:
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == sha256_hex(token)))
    if key is None:
        raise unauthorized("Invalid API key")
    if key.project_id != project_id:
        raise not_found("Project")  # don't reveal that the project exists
    if key.revoked_at is not None:
        raise ApiError(401, "api_key_revoked", "This API key has been revoked")
    project = db.get(Project, project_id)
    user = db.get(User, key.created_by_id) if key.created_by_id else None
    if user is None or not user.is_active:
        user = db.get(User, project.owner_id)
    now = utcnow()
    if key.last_used_at is None or now - key.last_used_at >= LAST_USED_INTERVAL:
        key.last_used_at = now
        db.commit()
    return ProjectAccess(project=project, user=user, role=API_KEY_ROLES[key.role], api_key=key)


def load_project_access(db: Session, user: User, project_id: str) -> ProjectAccess:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project")
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
    )
    if member is None:
        # Don't reveal that the project exists.
        raise not_found("Project")
    return ProjectAccess(project=project, user=user, role=member.role)


def require_role(minimum: str, *, api_keys: bool = False):
    """Dependency factory for routes with a `project_id` path parameter.

    Usage: `access: Annotated[ProjectAccess, Depends(require_role("admin"))]`
    `api_keys=True` also accepts a project API key (`dpl_...`, docs/DATA_API.md): anon keys act as
    viewer, service keys as developer. Elsewhere a key gets 401 `api_key_not_allowed`.
    """

    def dependency(project_id: str, request: Request, db: DbSession) -> ProjectAccess:
        token = bearer_token(request)
        if api_keys and token.startswith(API_KEY_PREFIX):
            access = load_api_key_access(db, token, project_id)
        else:
            access = load_project_access(db, get_current_user(request, db), project_id)
        if not access.at_least(minimum):
            raise forbidden(f"Requires the {minimum} role or higher on this project")
        return access

    return dependency


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
