from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession, client_ip
from app.errors import ApiError, conflict, not_found
from app.models import User, UserIdentity
from app.serializers import user_out
from app.services import audit, invites, oauth, rate_limit, tokens
from app.services.instance_settings import allow_signup, oauth_app
from app.services.passwords import (
    Email,
    hash_password,
    needs_rehash,
    normalize_email,
    validate_password,
    verify_password,
)

router = APIRouter(tags=["auth"])


@router.get("/auth/providers")
def providers(db: DbSession) -> dict:
    return {
        "google": oauth_app(db, "google").configured,
        "github": oauth_app(db, "github").configured,
        "allow_signup": allow_signup(db),
    }


# --- password accounts ---------------------------------------------------------------------------


class SignupIn(BaseModel):
    email: Email
    password: str
    display_name: str | None = Field(default=None, max_length=120)
    invite_token: str | None = Field(default=None, max_length=200)


@router.post("/auth/signup")
def signup(body: SignupIn, request: Request, response: Response, db: DbSession) -> dict:
    if db.scalar(select(User.id).limit(1)) is None:
        raise conflict("not_initialized", "Create the instance owner first")
    invite = None
    if body.invite_token:
        invite = invites.find_pending_invite(db, body.invite_token)
        if invite is None and not allow_signup(db):
            raise ApiError(400, "invite_invalid", "This invite is invalid, expired or already used")
        if invite is not None and not invites.email_matches(invite, body.email):
            raise ApiError(403, "invite_email_mismatch", "This invite was sent to a different email address")
    if invite is None and not allow_signup(db):
        raise ApiError(403, "signup_disabled", "Sign-up is disabled on this instance")
    validate_password(body.password)
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email)) is not None:
        raise conflict("email_taken", "An account with this email already exists")

    user = User(
        email=body.email,
        display_name=(body.display_name or "").strip() or None,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    audit.record(db, "auth.signup", request=request, user_id=user.id, method="password")
    if invite is not None:
        project_id = invites.accept_invite(db, invite, user)
        audit.record(db, "invite.accept", request=request, user_id=user.id, project_id=project_id, invite_id=invite.id)
    payload = tokens.start_session(db, response, user, request)
    db.commit()
    return payload


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: DbSession) -> dict:
    email = normalize_email(body.email)
    ip = client_ip(request)
    rate_limit.check_login(ip, email)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    ok = verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None or not user.is_active:
        audit.record(db, "auth.login_failed", request=request, user_id=user.id if user else None, email=email)
        db.commit()
        raise ApiError(401, "invalid_credentials", "Incorrect email or password")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    rate_limit.reset(rate_limit.login_key(ip, email))
    audit.record(db, "auth.login", request=request, user_id=user.id, method="password")
    payload = tokens.start_session(db, response, user, request)
    db.commit()
    return payload


def _unauthorized_clearing_cookie(db, message: str) -> JSONResponse:
    resp = JSONResponse(status_code=401, content={"error": {"code": "unauthorized", "message": message, "details": {}}})
    tokens.clear_refresh_cookie(resp, db)
    return resp


@router.post("/auth/refresh")
def refresh(request: Request, response: Response, db: DbSession):
    raw = request.cookies.get(tokens.REFRESH_COOKIE)
    try:
        user, new_raw = tokens.rotate_refresh_token(db, raw, request)
    except ApiError as exc:
        db.rollback()
        return _unauthorized_clearing_cookie(db, exc.message)
    tokens.set_refresh_cookie(response, db, new_raw)
    payload = tokens.auth_payload(user)
    db.commit()
    return payload


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: DbSession) -> dict:
    row = tokens.find_refresh_token(db, request.cookies.get(tokens.REFRESH_COOKIE))
    if row is not None:
        tokens.revoke_family(db, row.family_id)
        audit.record(db, "auth.logout", request=request, user_id=row.user_id)
    tokens.clear_refresh_cookie(response, db)
    db.commit()
    return {"ok": True}


# --- current user --------------------------------------------------------------------------------


@router.get("/auth/me")
def me(user: CurrentUser) -> dict:
    return user_out(user)


class MeUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)


@router.patch("/auth/me")
def update_me(body: MeUpdate, user: CurrentUser, db: DbSession) -> dict:
    if "display_name" in body.model_fields_set:
        user.display_name = (body.display_name or "").strip() or None
    db.commit()
    return user_out(user)


class PasswordChange(BaseModel):
    current_password: str | None = Field(default=None, max_length=1024)
    new_password: str


@router.post("/auth/password")
def change_password(body: PasswordChange, request: Request, user: CurrentUser, db: DbSession) -> dict:
    if user.password_hash is not None:
        if not body.current_password or not verify_password(user.password_hash, body.current_password):
            raise ApiError(400, "invalid_current_password", "Current password is incorrect")
    validate_password(body.new_password)
    had_password = user.password_hash is not None
    user.password_hash = hash_password(body.new_password)
    # Sign out other sessions; keep the one making this request (if its cookie is present).
    current = tokens.find_refresh_token(db, request.cookies.get(tokens.REFRESH_COOKIE))
    keep_family = current.family_id if current is not None and current.user_id == user.id else None
    tokens.revoke_user_tokens(db, user.id, except_family_id=keep_family)
    audit.record(db, "auth.password_change", request=request, user_id=user.id, kind="change" if had_password else "set")
    db.commit()
    return {"ok": True}


# --- OAuth ---------------------------------------------------------------------------------------


@router.get("/auth/oauth/{provider}/start")
def oauth_start(
    provider: str, db: DbSession, redirect: str | None = None, invite_token: str | None = None
) -> RedirectResponse:
    oauth.get_provider(provider)
    if db.scalar(select(User.id).limit(1)) is None:
        return RedirectResponse(oauth.login_error_url(db, "not_initialized"), status_code=302)
    try:
        url, nonce = oauth.begin(db, provider, intent="login", redirect=redirect, invite_token=invite_token)
    except ApiError as exc:
        if exc.code == "provider_not_configured":
            return RedirectResponse(oauth.login_error_url(db, exc.code), status_code=302)
        raise
    resp = RedirectResponse(url, status_code=302)
    oauth.set_browser_cookie(resp, db, nonce)
    return resp


class LinkIn(BaseModel):
    redirect: str | None = None


@router.post("/auth/oauth/{provider}/link")
def oauth_link(provider: str, response: Response, user: CurrentUser, db: DbSession, body: LinkIn | None = None) -> dict:
    redirect = body.redirect if body else None
    url, nonce = oauth.begin(db, provider, intent="link", redirect=redirect, user_id=user.id)
    # Sent with this same-origin fetch; the browser presents it on the provider's redirect back.
    oauth.set_browser_cookie(response, db, nonce)
    return {"authorize_url": url}


@router.get("/auth/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    result = oauth.handle_callback(
        db,
        request,
        provider,
        code=code,
        state=state,
        error=error,
        browser_nonce=request.cookies.get(oauth.BROWSER_COOKIE),
    )
    resp = RedirectResponse(result.redirect_url, status_code=302)
    oauth.clear_browser_cookie(resp, db)
    if result.login_user is not None:
        raw, _ = tokens.issue_refresh_token(db, result.login_user, request)
        tokens.set_refresh_cookie(resp, db, raw)
    db.commit()
    return resp


@router.delete("/auth/identities/{identity_id}")
def unlink_identity(identity_id: str, request: Request, user: CurrentUser, db: DbSession) -> dict:
    identity = db.get(UserIdentity, identity_id)
    if identity is None or identity.user_id != user.id:
        raise not_found("Identity")
    if user.password_hash is None and len(user.identities) <= 1:
        raise conflict("last_login_method", "Set a password or link another account before removing this one")
    provider = identity.provider
    user.identities.remove(identity)
    audit.record(db, "auth.identity_unlink", request=request, user_id=user.id, provider=provider)
    db.commit()
    return user_out(user)
