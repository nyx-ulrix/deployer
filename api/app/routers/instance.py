from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.deps import DbSession, InstanceOwner
from app.errors import ApiError, not_found
from app.models import AuditLog, Project, ProjectMember, User
from app.serializers import iso, project_out, user_out
from app.services import audit, deployments, remote_access, tokens
from app.services.alerts import validate_webhook_url
from app.services.instance_settings import (
    OAUTH_KEYS,
    allow_signup,
    api_key_rate_limit,
    get_value,
    oauth_app,
    oauth_callback_url,
    owner_only_projects,
    public_url,
    set_value,
    validate_oauth_value,
)

router = APIRouter(tags=["instance"])


def settings_out(db) -> dict:
    def provider(name: str) -> dict:
        app = oauth_app(db, name)
        return {
            "client_id": app.client_id or None,
            "secret_set": bool(app.client_secret),
            "configured": app.configured,
            "callback_url": oauth_callback_url(db, name),
        }

    return {
        "public_url": public_url(db),
        # The address on the Deployer PC itself (its real port), for OAuth callbacks and "continue from" hints.
        "local_url": remote_access.local_url(None),
        "allow_signup": allow_signup(db),
        "owner_only_projects": owner_only_projects(db),
        "google": provider("google"),
        "github": provider("github"),
        # docs/MONITORING.md
        "alert_webhook_url": get_value(db, "alert_webhook_url") or None,
        "api_key_rate_limit": api_key_rate_limit(db),
    }


def validate_public_url(value: str) -> str:
    value = value.strip()
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError as exc:
        raise ApiError(422, "validation_error", "public_url is not a valid URL", {"field": "public_url"}) from exc
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or parts.username
        or parts.password
    ):
        raise ApiError(
            422,
            "validation_error",
            "public_url must be an http(s) origin without a path, e.g. https://deployer.example.com",
            {"field": "public_url"},
        )
    return f"{parts.scheme}://{parts.netloc}"


@router.get("/instance/settings")
def get_settings_(owner: InstanceOwner, db: DbSession) -> dict:
    return settings_out(db)


class SettingsUpdate(BaseModel):
    public_url: str | None = Field(default=None, max_length=500)
    allow_signup: bool | None = None
    owner_only_projects: bool | None = None
    google_client_id: str | None = Field(default=None, max_length=500)
    google_client_secret: str | None = Field(default=None, max_length=500)
    github_client_id: str | None = Field(default=None, max_length=500)
    github_client_secret: str | None = Field(default=None, max_length=500)
    alert_webhook_url: str | None = Field(default=None, max_length=500)  # "" clears
    api_key_rate_limit: int | None = Field(default=None, ge=0, le=100_000)  # per key per minute, 0 = off


@router.put("/instance/settings")
def update_settings(body: SettingsUpdate, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    changed: list[str] = []
    previous_url = public_url(db)
    for key in (
        "public_url",
        "allow_signup",
        "owner_only_projects",
        "google_client_id",
        "google_client_secret",
        "github_client_id",
        "github_client_secret",
        "alert_webhook_url",
        "api_key_rate_limit",
    ):
        value = getattr(body, key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if key == "public_url" and value:
                value = validate_public_url(value)
            elif key in OAUTH_KEYS:
                value = validate_oauth_value(key, value)
            elif key == "alert_webhook_url" and value:
                value = validate_webhook_url(value)
        set_value(db, key, value)
        changed.append(key)
    if changed:
        audit.record(db, "instance.settings_update", request=request, user_id=owner.id, keys=changed)
    db.commit()
    warnings = deployments.resync_webhooks(db) if public_url(db) != previous_url else []
    db.commit()
    return {**settings_out(db), "warnings": warnings}


@router.get("/instance/users")
def list_users(owner: InstanceOwner, db: DbSession) -> list[dict]:
    users = db.scalars(select(User).order_by(User.created_at, User.email)).all()
    return [user_out(u) for u in users]


class UserUpdate(BaseModel):
    is_active: bool


@router.patch("/instance/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    """Disable or re-enable an account (A-023). Disabling signs it out everywhere; its access tokens
    already stop at the next request (deps.get_current_user checks is_active)."""
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    if user.is_instance_owner and not body.is_active:
        raise ApiError(400, "cannot_disable_owner", "The instance owner can't be disabled")
    if user.is_active != body.is_active:
        user.is_active = body.is_active
        if not body.is_active:
            tokens.revoke_user_tokens(db, user.id)
        audit.record(
            db,
            "instance.user_update",
            request=request,
            user_id=owner.id,
            target_user_id=user.id,
            is_active=body.is_active,
        )
        db.commit()
    return user_out(user)


@router.get("/instance/projects")
def list_all_projects(owner: InstanceOwner, db: DbSession) -> list[dict]:
    """Every project on this instance, including ones the owner isn't a member of (A-023)."""
    members = dict(db.execute(select(ProjectMember.project_id, func.count()).group_by(ProjectMember.project_id)).all())
    mine = dict(
        db.execute(select(ProjectMember.project_id, ProjectMember.role).where(ProjectMember.user_id == owner.id)).all()
    )
    rows = db.execute(
        select(Project, User.email)
        .outerjoin(User, User.id == Project.owner_id)
        .order_by(Project.created_at, Project.name)
    ).all()
    return [
        {**project_out(db, p, mine.get(p.id)), "owner_email": email, "member_count": members.get(p.id, 0)}
        for p, email in rows
    ]


@router.get("/instance/audit")
def list_audit(
    owner: InstanceOwner,
    db: DbSession,
    limit: int = Query(100, ge=1, le=500),
    before: int | None = Query(None, description="id cursor: rows older than this one"),
    action: str | None = None,
) -> list[dict]:
    """A-102: the audit log, newest first (kept 90 days; the worker prunes older rows)."""
    stmt = select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.user_id)
    if before is not None:
        stmt = stmt.where(AuditLog.id < before)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit)).all()
    return [
        {
            "id": a.id,
            "action": a.action,
            "user_id": a.user_id,
            "user_email": email,
            "project_id": a.project_id,
            "ip": a.ip,
            "user_agent": a.user_agent,
            "details": a.details,
            "created_at": iso(a.created_at),
        }
        for a, email in rows
    ]
