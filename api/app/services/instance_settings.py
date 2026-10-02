"""Runtime instance settings stored in `instance_settings`, falling back to env defaults."""

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt_secret, encrypt_secret
from app.errors import ApiError
from app.models import InstanceSetting, User

SECRET_KEYS = {
    "google_client_secret",
    "github_client_secret",
    # docs/REMOTE_ACCESS.md
    "cloudflare_api_token",
    "cloudflare_tunnel_token",
    # docs/COHOSTING.md "Websites on both PCs": connector token of the apps tunnel (main server) and, on
    # a co-host device, the one it received through RPC `apps.tunnel`.
    "cloudflare_apps_tunnel_token",
    "cohost_apps_tunnel_token",
    # docs/DEVICES.md — set on a host device: {"primary_url", "device_id", "device_token", "device_name"}
    "device_link",
    # On a host device: {database_name: {kind, username, password}} for databases it hosts.
    "device_hosted_credentials",
    # docs/MONITORING.md: alert webhook (Slack/Discord-style URLs carry a token in the path).
    "alert_webhook_url",
}
KNOWN_KEYS = {
    "public_url",
    "allow_signup",
    # A-023: when on (the default), only the instance owner can create or import projects. Migration 0014
    # (L-02) stores it off on instances that already had other users, so an update changes nothing for them.
    "owner_only_projects",
    "google_client_id",
    "github_client_id",
    "remote_access_mode",
    "cloudflare_account_id",
    "cloudflare_account_name",
    "cloudflare_tunnel_id",
    "cloudflare_tunnel_name",
    "cloudflare_apps_tunnel_id",
    "cloudflare_apps_tunnel_name",
    # On a co-host device: {app_id: {...}} of the co-hosted apps it runs (services/device_apps.py).
    "device_cohost_apps",
    # Random per-installation id (docs/REMOTE_ACCESS.md: tunnel name `deployer-<first 8>`).
    "instance_id",
    # docs/MONITORING.md: requests per minute per project API key (0 = unlimited).
    "api_key_rate_limit",
    *SECRET_KEYS,
}


def is_initialized(db: Session) -> bool:
    """True once the instance owner exists (setup done)."""
    return db.scalar(select(User.id).limit(1)) is not None


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


def reachable_elsewhere(db: Session) -> bool:
    """False while public_url is localhost: links built from it (invites, API snippets) only open on this PC."""
    host = (urlsplit(public_url(db)).hostname or "localhost").lower()
    return host not in ("localhost", "127.0.0.1", "::1") and not host.endswith(".localhost")


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


OAUTH_KEYS = ("google_client_id", "google_client_secret", "github_client_id", "github_client_secret")
_GOOGLE_ID = re.compile(r"^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$")
_GITHUB_ID = re.compile(r"^((Ov23|Iv1\.|Iv23)[A-Za-z0-9._-]+|[A-Za-z0-9]{20})$")
_LABEL = re.compile(r"^(client[ _-]?)?(id|secret)[\s:=]", re.I)
# ASCII only: these messages also reach the Windows console through `python -m app.cli oauth set`.
_EXAMPLES = {
    "google_client_id": "1234-abc.apps.googleusercontent.com",
    "google_client_secret": "GOCSPX-...",
    "github_client_id": "Ov23li...",
    "github_client_secret": "a 40-character hex string",
}


def validate_oauth_value(key: str, value: str) -> str:
    """Trims and checks one OAuth app field; raises a 422 that says what was pasted wrong. "" passes (clears)."""
    value = value.strip()
    if not value:
        return value
    provider, _, part = key.partition("_")
    name = f"{provider.title().replace('Github', 'GitHub')} {'Client ID' if part == 'client_id' else 'Client secret'}"
    example = _EXAMPLES[key]

    def bad(message: str) -> ApiError:
        return ApiError(422, "validation_error", message, {"field": key})

    if _LABEL.match(value) or any(c.isspace() for c in value):
        raise bad(
            f"Paste only the {name}, e.g. {example} - not the whole block "
            "(the value has spaces or an ID/SECRET label in it)"
        )
    if part == "client_secret":
        if _GOOGLE_ID.match(value) or value.endswith(".googleusercontent.com") or _GITHUB_ID.match(value):
            raise bad(f"That looks like the Client ID, not the {name} - paste the secret, e.g. {example}")
        return value
    if not (_GOOGLE_ID if provider == "google" else _GITHUB_ID).match(value):
        hint = " (that looks like the Client secret)" if value.startswith("GOCSPX-") else ""
        raise bad(f"That is not a {name}{hint} - paste only the Client ID, e.g. {example}")
    return value


def oauth_callback_url(db: Session, provider: str) -> str:
    return f"{public_url(db)}/v1/auth/oauth/{provider}/callback"


def allow_signup(db: Session) -> bool:
    return bool(get_value(db, "allow_signup"))


def owner_only_projects(db: Session) -> bool:
    value = get_value(db, "owner_only_projects")
    return True if value is None else bool(value)


API_KEY_RATE_LIMIT_DEFAULT = 600


def api_key_rate_limit(db: Session) -> int:
    value = get_value(db, "api_key_rate_limit")
    return API_KEY_RATE_LIMIT_DEFAULT if value is None else int(value)
