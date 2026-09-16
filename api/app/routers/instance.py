from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DbSession, InstanceOwner
from app.errors import ApiError
from app.models import User
from app.serializers import user_out
from app.services import audit
from app.services.instance_settings import (
    allow_signup,
    oauth_app,
    oauth_callback_url,
    public_url,
    set_value,
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
        "allow_signup": allow_signup(db),
        "google": provider("google"),
        "github": provider("github"),
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
    google_client_id: str | None = Field(default=None, max_length=500)
    google_client_secret: str | None = Field(default=None, max_length=500)
    github_client_id: str | None = Field(default=None, max_length=500)
    github_client_secret: str | None = Field(default=None, max_length=500)


@router.put("/instance/settings")
def update_settings(body: SettingsUpdate, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    changed: list[str] = []
    for key in (
        "public_url",
        "allow_signup",
        "google_client_id",
        "google_client_secret",
        "github_client_id",
        "github_client_secret",
    ):
        value = getattr(body, key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if key == "public_url" and value:
                value = validate_public_url(value)
        set_value(db, key, value)
        changed.append(key)
    if changed:
        audit.record(db, "instance.settings_update", request=request, user_id=owner.id, keys=changed)
    db.commit()
    return settings_out(db)


@router.get("/instance/users")
def list_users(owner: InstanceOwner, db: DbSession) -> list[dict]:
    users = db.scalars(select(User).order_by(User.created_at, User.email)).all()
    return [user_out(u) for u in users]
