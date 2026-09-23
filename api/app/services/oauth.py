"""Google / GitHub sign-in and account linking (authorization-code flow with state + PKCE S256).

State records live in Redis for 10 minutes and are deleted on first use. Each state is also bound to
the browser that started the flow via a short-lived HttpOnly nonce cookie (`deployer_oauth`), so a
callback URL (or authorize URL) crafted by someone else can't log a victim in or link their identity.

Provider HTTP traffic goes through `_http_post_form` / `_http_get_json` so tests can monkeypatch them
(no network in tests).

Account linking is never automatic: an OAuth login whose email matches an existing account is
refused with `account_exists_link_required`.

Intent `github_connect` (docs/DEPLOYMENTS.md "Connect a Git repository") reuses the GitHub app and this
callback with wider scopes to store a repository-access token (`services.github`). It never signs
anyone in: the callback also requires the refresh-token cookie of the user who started it.
"""

import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from fastapi import Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crypto import random_token, sha256_hex
from app.errors import ApiError, not_found
from app.models import User, UserIdentity, utcnow
from app.redis_client import get_redis
from app.services import audit, github, invites, tokens
from app.services.instance_settings import OAuthApp, allow_signup, oauth_app, oauth_callback_url, public_url
from app.services.passwords import normalize_email
from app.services.tokens import cookie_secure

log = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600
STATE_PREFIX = "oauth:state:"
HTTP_TIMEOUT = 10.0
DEFAULT_LINK_REDIRECT = "/settings/account"
BROWSER_COOKIE = "deployer_oauth"
BROWSER_COOKIE_PATH = "/v1/auth/oauth"


@dataclass(frozen=True)
class ProviderSpec:
    authorize_url: str
    token_url: str
    scope: str


PROVIDERS: dict[str, ProviderSpec] = {
    "google": ProviderSpec(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="openid email profile",
    ),
    "github": ProviderSpec(
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scope="read:user user:email",
    ),
}
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


class OAuthFlowError(Exception):
    """A failure that is reported to the browser as `?error=<code>`."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class OAuthProfile:
    provider_user_id: str
    email: str
    display_name: str | None
    avatar_url: str | None
    username: str | None


@dataclass
class CallbackResult:
    redirect_url: str
    login_user: User | None = None  # set when a refresh cookie must be issued


# --- helpers -------------------------------------------------------------------------------------


def get_provider(provider: str) -> ProviderSpec:
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise not_found("OAuth provider")
    return spec


def require_app(db: Session, provider: str) -> OAuthApp:
    get_provider(provider)
    app = oauth_app(db, provider)
    if not app.configured:
        raise ApiError(400, "provider_not_configured", f"{provider.title()} sign-in is not configured")
    return app


def sanitize_redirect(value: str | None, default: str = "/") -> str:
    """Only same-site absolute paths: must start with '/', not '//' or '/\\', no scheme/control chars."""
    if not value or not isinstance(value, str) or len(value) > 1000:
        return default
    value = value.split("#", 1)[0]
    if not value.startswith("/") or value.startswith("//") or value.startswith("/\\"):
        return default
    # A leading single '/' already rules out a scheme; browsers treat '\' like '/' so reject it.
    if "\\" in value or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return default
    return value


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _with_query(path: str, **params: str) -> str:
    return path + ("&" if "?" in path else "?") + urlencode(params)


def login_error_url(db: Session, code: str) -> str:
    return f"{public_url(db)}/login?error={quote(code)}"


# --- flow start ----------------------------------------------------------------------------------


def begin(
    db: Session,
    provider: str,
    *,
    intent: str,
    redirect: str | None,
    user_id: str | None = None,
    invite_token: str | None = None,
    scope: str | None = None,
) -> tuple[str, str]:
    """Stores a state record. Returns (provider authorize URL, browser nonce for `set_browser_cookie`).

    Raises ApiError `not_found` (unknown provider) / `provider_not_configured`.
    """
    spec = get_provider(provider)
    app = require_app(db, provider)
    state = random_token(32)
    verifier = random_token(48)
    browser_nonce = random_token(32)
    record = {
        "provider": provider,
        "intent": intent,
        "user_id": user_id,
        "redirect": sanitize_redirect(redirect, DEFAULT_LINK_REDIRECT if intent == "link" else "/"),
        "invite_token": invite_token or None,
        "code_verifier": verifier,
        "browser_hash": sha256_hex(browser_nonce),
    }
    get_redis().set(STATE_PREFIX + state, json.dumps(record), ex=STATE_TTL_SECONDS)
    params = {
        "client_id": app.client_id,
        "redirect_uri": oauth_callback_url(db, provider),
        "response_type": "code",
        "scope": scope or spec.scope,
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if provider == "google":
        params["prompt"] = "select_account"
    return f"{spec.authorize_url}?{urlencode(params)}", browser_nonce


def set_browser_cookie(response: Response, db: Session, nonce: str) -> None:
    response.set_cookie(
        BROWSER_COOKIE,
        nonce,
        max_age=STATE_TTL_SECONDS,
        path=BROWSER_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(db),
    )


def clear_browser_cookie(response: Response, db: Session) -> None:
    response.delete_cookie(
        BROWSER_COOKIE, path=BROWSER_COOKIE_PATH, httponly=True, samesite="lax", secure=cookie_secure(db)
    )


def _browser_matches(record: dict, nonce: str | None) -> bool:
    expected = record.get("browser_hash")
    if not isinstance(expected, str) or not nonce or len(nonce) > 200:
        return False
    return hmac.compare_digest(sha256_hex(nonce), expected)


def pop_state(state: str | None) -> dict | None:
    if not state or len(state) > 200:
        return None
    key = STATE_PREFIX + state
    pipe = get_redis().pipeline()
    pipe.get(key)
    pipe.delete(key)
    raw, _ = pipe.execute()
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


# --- provider HTTP -------------------------------------------------------------------------------


def _http_post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.post(url, data=data, headers={"Accept": "application/json", "User-Agent": "Deployer"})
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("OAuth token request to %s failed: %s", url, exc)
        raise OAuthFlowError("oauth_failed") from exc
    if resp.status_code >= 400 or not isinstance(body, dict) or "error" in body:
        log.warning("OAuth token request to %s rejected: %s", url, resp.status_code)
        raise OAuthFlowError("oauth_failed")
    return body


def _http_get_json(url: str, access_token: str) -> Any:
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json", "User-Agent": "Deployer"}
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("OAuth profile request to %s failed: %s", url, exc)
        raise OAuthFlowError("oauth_failed") from exc


def exchange_code(provider: str, app: OAuthApp, code: str, redirect_uri: str, code_verifier: str) -> str:
    """Returns the provider access token."""
    return _exchange(provider, app, code, redirect_uri, code_verifier)["access_token"]


def _exchange(provider: str, app: OAuthApp, code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    """The token response (with a non-empty `access_token`)."""
    body = _http_post_form(
        PROVIDERS[provider].token_url,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": app.client_id,
            "client_secret": app.client_secret,
            "code_verifier": code_verifier,
        },
    )
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise OAuthFlowError("oauth_failed")
    return body


def fetch_profile(provider: str, access_token: str) -> OAuthProfile:
    """Raises OAuthFlowError(`email_not_verified`) without a verified email."""
    if provider == "google":
        info = _http_get_json(GOOGLE_USERINFO_URL, access_token)
        if not isinstance(info, dict) or not info.get("sub"):
            raise OAuthFlowError("oauth_failed")
        verified = info.get("email_verified")
        if isinstance(verified, str):
            verified = verified.lower() == "true"
        if not info.get("email") or verified is not True:
            raise OAuthFlowError("email_not_verified")
        return OAuthProfile(
            provider_user_id=str(info["sub"]),
            email=normalize_email(info["email"]),
            display_name=info.get("name") or None,
            avatar_url=info.get("picture") or None,
            username=None,
        )
    if provider == "github":
        user = _http_get_json(GITHUB_USER_URL, access_token)
        if not isinstance(user, dict) or user.get("id") is None:
            raise OAuthFlowError("oauth_failed")
        emails = _http_get_json(GITHUB_EMAILS_URL, access_token)
        primary = next(
            (
                e
                for e in (emails if isinstance(emails, list) else [])
                if isinstance(e, dict) and e.get("primary") and e.get("verified") is True and e.get("email")
            ),
            None,
        )
        if primary is None:
            raise OAuthFlowError("email_not_verified")
        return OAuthProfile(
            provider_user_id=str(user["id"]),
            email=normalize_email(primary["email"]),
            display_name=user.get("name") or user.get("login") or None,
            avatar_url=user.get("avatar_url") or None,
            username=user.get("login") or None,
        )
    raise OAuthFlowError("oauth_failed")


# --- callback ------------------------------------------------------------------------------------


def _find_identity(db: Session, provider: str, provider_user_id: str) -> UserIdentity | None:
    return db.scalar(
        select(UserIdentity).where(UserIdentity.provider == provider, UserIdentity.provider_user_id == provider_user_id)
    )


def _login(db: Session, request: Request, provider: str, profile: OAuthProfile, record: dict) -> User:
    if db.scalar(select(User.id).limit(1)) is None:
        raise OAuthFlowError("not_initialized")

    identity = _find_identity(db, provider, profile.provider_user_id)
    if identity is not None:
        user = identity.user
        if not user.is_active:
            raise OAuthFlowError("oauth_failed")
        identity.provider_email = profile.email
        identity.provider_username = profile.username
        audit.record(db, "auth.oauth_login", request=request, user_id=user.id, provider=provider)
        return user

    if db.scalar(select(User.id).where(func.lower(User.email) == profile.email)) is not None:
        raise OAuthFlowError("account_exists_link_required")

    invite = invites.find_pending_invite(db, record.get("invite_token"))
    if invite is not None and not invites.email_matches(invite, profile.email):
        raise OAuthFlowError("invite_email_mismatch")
    if invite is None and not allow_signup(db):
        raise OAuthFlowError("signup_disabled")

    user = User(
        email=profile.email,
        display_name=(profile.display_name or "")[:120] or None,
        avatar_url=(profile.avatar_url or "")[:500] or None,
        password_hash=None,
    )
    user.identities.append(
        UserIdentity(
            provider=provider,
            provider_user_id=profile.provider_user_id,
            provider_email=profile.email,
            provider_username=profile.username,
        )
    )
    db.add(user)
    db.flush()
    if invite is not None:
        project_id = invites.accept_invite(db, invite, user)
        audit.record(db, "invite.accept", request=request, user_id=user.id, project_id=project_id, invite_id=invite.id)
    audit.record(db, "auth.signup", request=request, user_id=user.id, method=provider)
    audit.record(db, "auth.oauth_login", request=request, user_id=user.id, provider=provider)
    return user


def _link(db: Session, request: Request, provider: str, profile: OAuthProfile, record: dict) -> None:
    user = db.get(User, record.get("user_id") or "")
    if user is None or not user.is_active:
        raise OAuthFlowError("oauth_failed")
    identity = _find_identity(db, provider, profile.provider_user_id)
    if identity is not None:
        if identity.user_id != user.id:
            raise OAuthFlowError("identity_in_use")
        return
    user.identities.append(
        UserIdentity(
            provider=provider,
            provider_user_id=profile.provider_user_id,
            provider_email=profile.email,
            provider_username=profile.username,
        )
    )
    db.flush()
    audit.record(db, "auth.identity_link", request=request, user_id=user.id, provider=provider)


def handle_callback(
    db: Session,
    request: Request,
    provider: str,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
    browser_nonce: str | None,
) -> CallbackResult:
    """Completes the flow. Never raises for flow failures: returns the error redirect instead.

    Caller must issue a refresh cookie for `login_user` (if any) and commit.
    """
    get_provider(provider)
    base = public_url(db)
    record = pop_state(state)
    if record is None or record.get("provider") != provider or not _browser_matches(record, browser_nonce):
        return CallbackResult(login_error_url(db, "oauth_state_invalid"))

    if record.get("intent") == "github_connect":
        return CallbackResult(_connect(db, request, provider, code=code, error=error, record=record))
    intent = "link" if record.get("intent") == "link" else "login"
    redirect = sanitize_redirect(record.get("redirect"), DEFAULT_LINK_REDIRECT if intent == "link" else "/")
    try:
        if error or not code:
            raise OAuthFlowError("oauth_failed")
        app = oauth_app(db, provider)
        if not app.configured:
            raise OAuthFlowError("provider_not_configured")
        access_token = exchange_code(
            provider, app, code, oauth_callback_url(db, provider), str(record.get("code_verifier") or "")
        )
        profile = fetch_profile(provider, access_token)
        if intent == "link":
            _link(db, request, provider, profile, record)
            return CallbackResult(base + _with_query(redirect, linked=provider))
        user = _login(db, request, provider, profile, record)
        return CallbackResult(f"{base}/auth/complete?{urlencode({'redirect': redirect})}", login_user=user)
    except OAuthFlowError as exc:
        db.rollback()
        audit.record(
            db,
            "auth.oauth_failed",
            request=request,
            user_id=record.get("user_id"),
            provider=provider,
            intent=intent,
            code=exc.code,
        )
        if intent == "link":
            return CallbackResult(base + _with_query(redirect, error=exc.code))
        return CallbackResult(login_error_url(db, exc.code))


def _connect(db: Session, request: Request, provider: str, *, code: str | None, error: str | None, record: dict) -> str:
    """`github_connect` callback: stores the user's GitHub token. Returns the dashboard redirect URL."""
    done = f"{public_url(db)}/integrations/github/done"
    user_id = str(record.get("user_id") or "")
    try:
        if provider != "github" or error or not code:
            raise OAuthFlowError("oauth_failed")
        user = db.get(User, user_id)
        session = tokens.find_refresh_token(db, request.cookies.get(tokens.REFRESH_COOKIE))
        if (
            user is None
            or not user.is_active
            or session is None
            or session.user_id != user.id
            or session.revoked_at is not None
            or session.expires_at <= utcnow()
        ):
            raise OAuthFlowError("github_connect_user_mismatch")
        app = oauth_app(db, provider)
        if not app.configured:
            raise OAuthFlowError("provider_not_configured")
        body = _exchange(provider, app, code, oauth_callback_url(db, provider), str(record.get("code_verifier") or ""))
        token = body["access_token"]
        profile = _http_get_json(GITHUB_USER_URL, token)
        if not isinstance(profile, dict) or profile.get("id") is None or not profile.get("login"):
            raise OAuthFlowError("oauth_failed")
        scopes = " ".join(str(body.get("scope") or github.CONNECT_SCOPE).replace(",", " ").split())
        github.save_connection(
            db, user.id, login=str(profile["login"]), github_user_id=str(profile["id"]), token=token, scopes=scopes
        )
        audit.record(db, "github.connect", request=request, user_id=user.id, login=str(profile["login"]))
        return done + "?ok=1"
    except OAuthFlowError as exc:
        db.rollback()
        audit.record(db, "github.connect_failed", request=request, user_id=user_id or None, code=exc.code)
        return done + "?" + urlencode({"error": exc.code})
