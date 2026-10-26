"""Command-line logins and tokens (docs/CLI.md).

`deployer login` creates a login and polls it without credentials; the user approves its code in the
dashboard (`/cli/approve?code=...`), which needs a signed-in browser session, never a token.
"""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.deps import CurrentUser, DbSession, SessionUser, client_ip
from app.errors import ApiError
from app.services import audit, cli_tokens, rate_limit
from app.services.instance_settings import public_url

router = APIRouter(tags=["cli"])


class LoginCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    hostname: str | None = Field(default=None, max_length=500)
    os: str | None = Field(default=None, max_length=200)


class LoginPoll(BaseModel):
    poll_secret: str = Field(max_length=200)


class LoginAction(BaseModel):
    user_code: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, max_length=200)


@router.post("/auth/cli/logins")
def create_login(body: LoginCreate, request: Request, db: DbSession) -> dict:
    allowed, retry_after = rate_limit.hit(f"rl:cli-login:{client_ip(request) or '-'}", 20, 3600)
    if not allowed:
        raise ApiError(429, "rate_limited", "Too many login attempts", {"retry_after": retry_after})
    row, poll_secret = cli_tokens.create_login(db, name=body.name, hostname=body.hostname, os=body.os)
    audit.record(db, "cli.login_create", request=request, login_id=row.id, name=row.name, hostname=row.hostname)
    db.commit()
    return {
        "login_id": row.id,
        "poll_secret": poll_secret,
        "user_code": row.user_code,
        "verification_uri": f"{public_url(db)}/cli/approve?code={row.user_code}",
        "verification_uri_base": f"{public_url(db)}/cli/approve",
        "expires_in": cli_tokens.LOGIN_TTL_SECONDS,
        "interval": cli_tokens.POLL_INTERVAL_SECONDS,
    }


@router.post("/auth/cli/logins/{login_id}/poll")
def poll_login(login_id: str, body: LoginPoll, db: DbSession) -> dict:
    result = cli_tokens.poll_login(db, login_id, body.poll_secret)
    db.commit()
    return result


@router.get("/auth/cli/logins")
def login_by_code(user: SessionUser, db: DbSession, code: str = Query(max_length=20)) -> dict:
    row = cli_tokens.login_by_code(db, code)
    db.commit()  # an expired status sticks
    return cli_tokens.login_out(row)


@router.post("/auth/cli/logins/{login_id}/approve")
def approve_login(login_id: str, body: LoginAction, request: Request, user: SessionUser, db: DbSession) -> dict:
    row = cli_tokens.login_for_action(db, login_id, body.user_code)
    token = cli_tokens.approve(db, row, user, body.name)
    audit.record(db, "cli.login_approve", request=request, user_id=user.id, login_id=row.id, token_id=token.id)
    db.commit()
    return {"login": cli_tokens.login_out(row), "token": cli_tokens.token_out(token)}


@router.post("/auth/cli/logins/{login_id}/deny")
def deny_login(login_id: str, body: LoginAction, request: Request, user: SessionUser, db: DbSession) -> dict:
    row = cli_tokens.login_for_action(db, login_id, body.user_code)
    row.status = "denied"
    audit.record(db, "cli.login_deny", request=request, user_id=user.id, login_id=row.id)
    db.commit()
    return cli_tokens.login_out(row)


@router.get("/auth/cli/tokens")
def list_tokens(request: Request, user: CurrentUser, db: DbSession) -> list[dict]:
    current = getattr(request.state, "cli_token_id", None)
    return [cli_tokens.token_out(row, current) for row in cli_tokens.list_tokens(db, user)]


@router.delete("/auth/cli/tokens/current")
def revoke_current(request: Request, user: CurrentUser, db: DbSession) -> dict:
    """`deployer logout`: the token revokes itself."""
    token_id = getattr(request.state, "cli_token_id", None)
    if not token_id:
        raise ApiError(400, "not_a_cli_token", "Call this with a command-line token")
    cli_tokens.revoke(db, user, token_id)
    audit.record(db, "cli.token_revoke", request=request, user_id=user.id, token_id=token_id)
    db.commit()
    return {"ok": True}


@router.delete("/auth/cli/tokens/{token_id}")
def revoke_token(token_id: str, request: Request, user: CurrentUser, db: DbSession) -> dict:
    cli_tokens.revoke(db, user, token_id)
    audit.record(db, "cli.token_revoke", request=request, user_id=user.id, token_id=token_id)
    db.commit()
    return {"ok": True}
