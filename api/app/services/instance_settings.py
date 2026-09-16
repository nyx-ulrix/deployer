"""Runtime instance settings stored in `instance_settings`, falling back to env defaults."""

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt_secret, encrypt_secret
from app.models import InstanceSetting

SECRET_KEYS = {"google_client_secret", "github_client_secret"}
KNOWN_KEYS = {"public_url", "allow_signup", "google_client_id", "github_client_id", *SECRET_KEYS}


def get_value(db: Session, key: str):
    """Returns the stored value (decrypted if secret), else the env default, else None/''."""
    row = db.get(InstanceSetting, key)
    if row is not None:
        return decrypt_secret(row.value) if row.is_secret else json.loads(row.value)
    return getattr(get_settings(), key, None)


def set_value(db: Session, key: str, value) -> None:
    """Stores a value. `None` or "" deletes the override. Caller commits."""
    if key not in KNOWN_KEYS:
        raise KeyError(key)
    row = db.get(InstanceSetting, key)
    if value is None or value == "":
        if row is not None:
            db.delete(row)
        return
    is_secret = key in SECRET_KEYS
    stored = encrypt_secret(str(value)) if is_secret else json.dumps(value)
    if row is None:
        db.add(InstanceSetting(key=key, value=stored, is_secret=is_secret))
    else:
        row.value, row.is_secret = stored, is_secret


def public_url(db: Session) -> str:
    return str(get_value(db, "public_url") or get_settings().public_url).rstrip("/")


@dataclass
class OAuthApp:
    client_id: str
    client_secret: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


def oauth_app(db: Session, provider: str) -> OAuthApp:
    return OAuthApp(
        client_id=get_value(db, f"{provider}_client_id") or "",
        client_secret=get_value(db, f"{provider}_client_secret") or "",
    )


def oauth_callback_url(db: Session, provider: str) -> str:
    return f"{public_url(db)}/v1/auth/oauth/{provider}/callback"


def allow_signup(db: Session) -> bool:
    return bool(get_value(db, "allow_signup"))
