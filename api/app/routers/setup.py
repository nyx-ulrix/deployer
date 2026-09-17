from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import __version__
from app.deps import DbSession
from app.errors import conflict
from app.models import User
from app.services import audit, tokens
from app.services.instance_settings import allow_signup, oauth_app, public_url
from app.services.passwords import Email, hash_password, validate_password

router = APIRouter(tags=["setup"])


def is_initialized(db) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


@router.get("/setup/status")
def setup_status(db: DbSession) -> dict:
    return {
        "initialized": is_initialized(db),
        "version": __version__,
        "public_url": public_url(db),
        "providers": {p: oauth_app(db, p).configured for p in ("google", "github")},
        "allow_signup": allow_signup(db),
        "device_mode": _device_mode(db),
    }


def _device_mode(db) -> str:
    """docs/DEVICES.md: "host" when this installation is attached to a main Deployer."""
    from app.services.device_host import device_mode

    return device_mode(db)


class OwnerIn(BaseModel):
    email: Email
    password: str
    display_name: str | None = Field(default=None, max_length=120)


@router.post("/setup/owner")
def create_owner(body: OwnerIn, request: Request, response: Response, db: DbSession) -> dict:
    if is_initialized(db):
        raise conflict("already_initialized", "This instance already has an owner")
    validate_password(body.password)
    user = User(
        email=body.email,
        display_name=(body.display_name or "").strip() or None,
        password_hash=hash_password(body.password),
        is_instance_owner=True,
    )
    db.add(user)
    db.flush()
    audit.record(db, "auth.signup", request=request, user_id=user.id, method="password", instance_owner=True)
    payload = tokens.start_session(db, response, user, request)
    db.commit()
    return payload
