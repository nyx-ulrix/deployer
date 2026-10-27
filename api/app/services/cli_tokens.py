"""Command-line tokens (docs/CLI.md).

`deployer login` asks for a login (`create_login`), prints a code and a link, and polls. The user
opens the link on any device through the public URL, signs in to the dashboard and approves the
code; the next poll hands the command line a `dpt_` token once. The token then works like a signed-in
session of that user until it is revoked, so a server without a browser never needs one.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import decrypt_secret, encrypt_secret, random_token, sha256_hex
from app.errors import ApiError, not_found, unauthorized
from app.models import CliLogin, CliToken, User, utcnow
from app.redis_client import get_redis
from app.serializers import iso
from app.services import cli_inputs
from app.services.devices import generate_user_code, normalize_user_code

TOKEN_PREFIX = "dpt_"
PREFIX_LENGTH = 12  # shown in lists: `dpt_` + 8 characters
LOGIN_TTL_SECONDS = 10 * 60
POLL_INTERVAL_SECONDS = 3
POLL_MIN_INTERVAL_SECONDS = 2
LAST_USED_INTERVAL = timedelta(seconds=60)  # `last_used_at` is written at most this often per token


def _clean(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


def issue_token(db: Session, user: User, name: str) -> tuple[CliToken, str]:
    """Adds a token for `user` (caller commits). Returns (row, raw token); the raw token is never stored."""
    raw = TOKEN_PREFIX + random_token(32)
    row = CliToken(
        user_id=user.id,
        name=_clean(name, 80) or "deployer CLI",
        prefix=raw[:PREFIX_LENGTH],
        token_hash=sha256_hex(raw),
    )
    db.add(row)
    db.flush()
    return row, raw


def authenticate(db: Session, raw: str) -> tuple[User, CliToken]:
    """The user a `dpt_` bearer token acts as; 401 when it is unknown, revoked or its user is disabled."""
    row = db.scalar(select(CliToken).where(CliToken.token_hash == sha256_hex(raw)))
    if row is None:
        raise unauthorized("Invalid command-line token")
    if row.revoked_at is not None:
        raise ApiError(401, "cli_token_revoked", "This command-line token has been revoked; run `deployer login`")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise unauthorized("Account not found or disabled")
    now = utcnow()
    if row.last_used_at is None or now - row.last_used_at >= LAST_USED_INTERVAL:
        row.last_used_at = now
        db.commit()
    return user, row


def token_out(row: CliToken, current_id: str | None = None) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.prefix,
        "created_at": iso(row.created_at),
        "last_used_at": iso(row.last_used_at),
        "current": row.id == current_id,
    }


def list_tokens(db: Session, user: User) -> list[CliToken]:
    return list(
        db.scalars(
            select(CliToken)
            .where(CliToken.user_id == user.id, CliToken.revoked_at.is_(None))
            .order_by(CliToken.created_at.desc())
        )
    )


def revoke(db: Session, user: User, token_id: str) -> CliToken:
    """Revokes one of the user's own tokens and cancels the input requests it still waits on
    (docs/CLI.md "Input requests"). Caller commits."""
    row = db.get(CliToken, token_id)
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        raise not_found("Token")
    row.revoked_at = utcnow()
    cli_inputs.cancel_for_token(db, row.id)
    return row


# ---------------------------------------------------------------------------------------------
# login requests (device flow)
# ---------------------------------------------------------------------------------------------


def expire_if_needed(row: CliLogin) -> CliLogin:
    if row.status in ("pending", "approved") and row.expires_at <= utcnow():
        row.status = "expired"
        row.token_encrypted = None
    return row


def create_login(db: Session, *, name: str | None, hostname: str | None, os: str | None) -> tuple[CliLogin, str]:
    """Adds a pending login (caller commits). Returns (row, raw poll secret)."""
    poll_secret = random_token(32)
    for _ in range(10):
        code = generate_user_code()
        if db.scalar(select(CliLogin.id).where(CliLogin.user_code == code)) is None:
            break
    else:  # pragma: no cover - 32^8 codes
        raise ApiError(500, "login_failed", "Could not allocate a login code")
    row = CliLogin(
        user_code=code,
        poll_secret_hash=sha256_hex(poll_secret),
        name=_clean(name, 80) or "deployer CLI",
        hostname=_clean(hostname, 255),
        os=_clean(os, 120),
        status="pending",
        expires_at=utcnow() + timedelta(seconds=LOGIN_TTL_SECONDS),
    )
    db.add(row)
    db.flush()
    return row, poll_secret


def _poll_allowed(login_id: str) -> bool:
    try:
        return bool(get_redis().set(f"cli:login:poll:{login_id}", "1", nx=True, px=POLL_MIN_INTERVAL_SECONDS * 1000))
    except Exception:  # noqa: BLE001 - fail open when Redis is unavailable
        return True


def poll_login(db: Session, login_id: str, poll_secret: str) -> dict:
    """Command-line poll. Delivers the raw token once. Caller commits."""
    row = db.get(CliLogin, login_id)
    if row is None or not poll_secret or not secrets.compare_digest(row.poll_secret_hash, sha256_hex(poll_secret)):
        raise not_found("Login")
    if not _poll_allowed(row.id):
        raise ApiError(429, "slow_down", "Polling too fast", {"interval": POLL_INTERVAL_SECONDS})
    expire_if_needed(row)
    if row.status == "approved" and row.token_encrypted:
        token = decrypt_secret(row.token_encrypted)
        row.token_encrypted = None
        row.status = "consumed"
        user = db.get(User, row.approved_by_id) if row.approved_by_id else None
        return {"status": "approved", "token": token, "email": user.email if user else None}
    return {"status": row.status, "interval": POLL_INTERVAL_SECONDS}


def login_by_code(db: Session, code: str) -> CliLogin:
    normalized = normalize_user_code(code)
    if normalized is None:
        raise not_found("Login")
    row = db.scalar(select(CliLogin).where(CliLogin.user_code == normalized))
    if row is None:
        raise not_found("Login")
    return expire_if_needed(row)


def login_for_action(db: Session, login_id: str, user_code: str | None) -> CliLogin:
    """The pending login an approve/deny names; the code must match, so an id alone is not enough."""
    row = db.get(CliLogin, login_id)
    if row is None or normalize_user_code(user_code) != row.user_code:
        raise not_found("Login")
    expire_if_needed(row)
    if row.status != "pending":
        raise ApiError(409, "login_not_pending", f"This login is already {row.status}")
    return row


def approve(db: Session, row: CliLogin, user: User, name: str | None) -> CliToken:
    """Issues the token and parks it (encrypted) for the next poll. Caller commits."""
    token, raw = issue_token(db, user, name or row.name)
    row.status = "approved"
    row.approved_by_id = user.id
    row.token_encrypted = encrypt_secret(raw)
    return token


def login_out(row: CliLogin) -> dict:
    return {
        "id": row.id,
        "user_code": row.user_code,
        "name": row.name,
        "hostname": row.hostname,
        "os": row.os,
        "status": row.status,
        "expires_at": iso(row.expires_at),
        "created_at": iso(row.created_at),
    }


def prune(db: Session) -> int:
    """Deletes login requests a day past expiry (caller commits)."""
    cutoff = utcnow() - timedelta(days=1)
    rows = list(db.scalars(select(CliLogin).where(CliLogin.expires_at < cutoff)))
    for row in rows:
        db.delete(row)
    return len(rows)
