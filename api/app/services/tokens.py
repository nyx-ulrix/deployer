"""Access tokens (JWT), rotating refresh tokens and the refresh cookie.

- Access token: HS256 JWT, `aud="deployer"`, `typ="access"`, `sub=<user id>` (see deps.decode_access_token).
- Refresh token: 256-bit random, only its SHA-256 is stored. Every use rotates it within the same
  `family_id`; presenting an already rotated/revoked token revokes the whole family, except within
  a short grace window after a rotation (concurrent refreshes from several tabs).
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import random_token, sha256_hex
from app.deps import client_ip
from app.errors import unauthorized
from app.models import RefreshToken, User, new_id, utcnow
from app.serializers import user_out
from app.services.instance_settings import public_url

REFRESH_COOKIE = "deployer_rt"
REFRESH_COOKIE_PATH = "/v1/auth"


# --- access tokens -------------------------------------------------------------------------------


def create_access_token(user: User) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set")
    now = datetime.now(UTC)
    claims = {
        "sub": user.id,
        "aud": "deployer",
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def auth_payload(user: User) -> dict:
    """The `AuthResponse` body (without touching refresh tokens)."""
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "expires_in": get_settings().access_token_ttl_seconds,
        "user": user_out(user),
    }


# --- refresh tokens ------------------------------------------------------------------------------


def issue_refresh_token(
    db: Session, user: User, request: Request | None = None, family_id: str | None = None
) -> tuple[str, RefreshToken]:
    """Adds a new refresh token row (caller commits). Returns (raw token, row)."""
    raw = random_token(32)
    row = RefreshToken(
        id=new_id(),
        user_id=user.id,
        token_hash=sha256_hex(raw),
        family_id=family_id or new_id(),
        expires_at=utcnow() + timedelta(days=get_settings().refresh_token_ttl_days),
        ip=client_ip(request) if request else None,
        user_agent=((request.headers.get("User-Agent") or "")[:255] or None) if request else None,
    )
    db.add(row)
    db.flush()
    return raw, row


def revoke_family(db: Session, family_id: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def revoke_user_tokens(db: Session, user_id: str, except_family_id: str | None = None) -> None:
    stmt = update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    if except_family_id:
        stmt = stmt.where(RefreshToken.family_id != except_family_id)
    db.execute(stmt.values(revoked_at=utcnow()))


def find_refresh_token(db: Session, raw: str | None) -> RefreshToken | None:
    if not raw or len(raw) > 200:
        return None
    return db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw)))


ROTATION_GRACE_SECONDS = 30


def _within_rotation_grace(db: Session, row: RefreshToken) -> bool:
    """True if `row` was rotated (not logged out) moments ago and its family is still live."""
    if row.replaced_by_id is None or row.revoked_at is None:
        return False
    if utcnow() - row.revoked_at > timedelta(seconds=ROTATION_GRACE_SECONDS):
        return False
    live = db.scalar(
        select(RefreshToken.id).where(
            RefreshToken.family_id == row.family_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
    )
    return live is not None


def rotate_refresh_token(db: Session, raw: str | None, request: Request | None = None) -> tuple[User, str]:
    """Validates and rotates a refresh token. Returns (user, new raw token); caller commits.

    Raises 401 on unknown/expired tokens. On reuse of a rotated/revoked token the whole family is
    revoked and committed before raising.
    """
    if not raw or len(raw) > 200:
        raise unauthorized("Missing or invalid refresh token")
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw)).with_for_update())
    if row is None:
        raise unauthorized("Missing or invalid refresh token")
    if row.revoked_at is not None:
        if _within_rotation_grace(db, row):
            # Two tabs refreshing at the same moment present the same cookie; the loser gets a
            # sibling token in the same family instead of logging the user out everywhere.
            user = db.get(User, row.user_id)
            if user is not None and user.is_active:
                new_raw, _ = issue_refresh_token(db, user, request, family_id=row.family_id)
                return user, new_raw
        revoke_family(db, row.family_id)
        db.commit()
        raise unauthorized("Refresh token reuse detected; please sign in again")
    if row.expires_at <= utcnow():
        raise unauthorized("Refresh token expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise unauthorized("Account not found or disabled")
    new_raw, new_row = issue_refresh_token(db, user, request, family_id=row.family_id)
    row.revoked_at = utcnow()
    row.replaced_by_id = new_row.id
    return user, new_raw


# --- cookie --------------------------------------------------------------------------------------


def cookie_secure(db: Session) -> bool:
    return public_url(db).lower().startswith("https://")


def set_refresh_cookie(response: Response, db: Session, raw: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        max_age=get_settings().refresh_token_ttl_days * 86400,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(db),
    )


def clear_refresh_cookie(response: Response, db: Session) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(db),
    )


def start_session(db: Session, response: Response, user: User, request: Request | None = None) -> dict:
    """Issues a new refresh token family, sets the cookie and returns the AuthResponse body.

    Caller commits.
    """
    raw, _ = issue_refresh_token(db, user, request)
    set_refresh_cookie(response, db, raw)
    return auth_payload(user)
