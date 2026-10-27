"""Input requests (docs/CLI.md "Input requests").

The command line (a `dpt_` token or a session) creates and polls a request; only the person signed in to
the dashboard fills it (`SessionUser`), so a token can never answer its own question.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession, SessionUser
from app.errors import ApiError, not_found
from app.models import App, CliInput, CliToken, User
from app.routers.apps import _check_env, dispatch_env_deployment, set_env_vars
from app.services import audit, cli_inputs, rate_limit
from app.services.instance_settings import public_url

router = APIRouter(tags=["cli"])

_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")  # an app's Environment takes the same names


class InputField(BaseModel):
    key: str = Field(max_length=128)
    label: str = Field(min_length=1, max_length=120)
    secret: bool = False
    help: str | None = Field(default=None, max_length=500)
    placeholder: str | None = Field(default=None, max_length=120)
    pattern: str | None = Field(default=None, max_length=200)
    optional: bool = False
    multiline: bool = False
    link: str | None = Field(default=None, max_length=2000)
    link_label: str | None = Field(default=None, max_length=60)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not _KEY_RE.fullmatch(value):
            raise ValueError("must be letters, digits and _ (not starting with a digit), at most 128")
        return value

    @field_validator("pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        # Only the browser checks values against it (services/cli_inputs.clean_values); it must compile.
        if value:
            try:
                re.compile(value)
            except (re.error, OverflowError, RecursionError) as exc:
                raise ValueError(f"is not a valid regular expression ({exc})") from None
        return value or None

    @field_validator("link")
    @classmethod
    def _link(cls, value: str | None) -> str | None:
        if not value:
            return None
        parts = urlsplit(value.strip())
        if parts.scheme != "https" or not parts.hostname or any(c.isspace() for c in value.strip()):
            raise ValueError("must be an https:// URL")
        return value.strip()


class InputCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    fields: list[InputField] = Field(min_length=1, max_length=10)
    app_ids: list[str] | None = Field(default=None, max_length=20)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _unique_keys(self) -> InputCreate:
        keys = [f.key for f in self.fields]
        if len(set(keys)) != len(keys):
            raise ValueError("field keys must be unique")
        if self.app_ids:
            _check_env(dict.fromkeys(keys, ""))  # names an app's Environment accepts
        return self


class InputSubmit(BaseModel):
    values: dict[str, str | None] = Field(max_length=10)


def _apps_for(db: Session, user: User, app_ids: list[str]) -> list[App]:
    """The apps, each needing developer on its project; always the same 404 otherwise, so an app id
    never tells whether that app exists in another project."""
    apps, unavailable = cli_inputs.usable_apps(db, user, app_ids)
    if unavailable:
        raise not_found("App")
    return apps


@router.post("/auth/cli/inputs", status_code=201)
def create_input(body: InputCreate, request: Request, user: CurrentUser, db: DbSession) -> dict:
    allowed, retry_after = rate_limit.hit(f"rl:cli-input:{user.id}", cli_inputs.CREATE_LIMIT_PER_HOUR, 3600)
    if not allowed:
        raise ApiError(429, "rate_limited", "Too many input requests", {"retry_after": retry_after})
    app_ids = [a.id for a in _apps_for(db, user, body.app_ids)] if body.app_ids else None
    token_id = getattr(request.state, "cli_token_id", None)
    row = cli_inputs.create(
        db,
        user,
        title=body.title,
        description=(body.description or "").strip() or None,
        fields=[f.model_dump(exclude_none=True) for f in body.fields],
        app_ids=app_ids,
        token=db.get(CliToken, token_id) if token_id else None,
    )
    audit.record(
        db,
        "cli.input_create",
        request=request,
        user_id=user.id,
        input_id=row.id,
        title=row.title,
        keys=[f.key for f in body.fields],
        app_ids=app_ids,
    )
    db.commit()
    return {
        "id": row.id,
        "url": f"{public_url(db)}/input/{row.id}",
        "expires_in": cli_inputs.INPUT_TTL_SECONDS,
        "interval": cli_inputs.POLL_INTERVAL_SECONDS,
    }


def _cli_row(db: Session, user: User, request: Request, input_id: str) -> CliInput:
    return cli_inputs.get_for_cli(db, user, input_id, getattr(request.state, "cli_token_id", None))


@router.post("/auth/cli/inputs/{input_id}/poll")
def poll_input(input_id: str, request: Request, user: CurrentUser, db: DbSession) -> dict:
    row = _cli_row(db, user, request, input_id)
    result = cli_inputs.poll(db, user, row)
    db.commit()
    return result


@router.post("/auth/cli/inputs/{input_id}/cancel")
def cancel_input(input_id: str, request: Request, user: CurrentUser, db: DbSession) -> dict:
    row = _cli_row(db, user, request, input_id)
    status = cli_inputs.cancel(db, row)
    db.commit()
    return {"ok": True, "status": status}


@router.get("/inputs/{input_id}")
def get_input(input_id: str, user: SessionUser, db: DbSession) -> dict:
    row = cli_inputs.get_own(db, user, input_id)
    db.commit()  # an expired status sticks
    return cli_inputs.input_out(db, user, row)


@router.post("/inputs/{input_id}/submit")
def submit_input(input_id: str, body: InputSubmit, request: Request, user: SessionUser, db: DbSession) -> dict:
    row = cli_inputs.get_own(db, user, input_id)
    db.commit()  # an expired status sticks
    cli_inputs.check_pending(row)
    values = cli_inputs.clean_values(row, body.values)
    # Pending -> submitted first (409 if a cancel or another submit won), then the Environment in the same
    # transaction: an error below rolls both back and the request stays pending.
    cli_inputs.mark_submitted(db, row, values)
    apps = []
    if row.app_ids:
        apps, unavailable = cli_inputs.usable_apps(db, user, row.app_ids)
        if unavailable:
            raise ApiError(
                409,
                "input_apps_unavailable",
                "An app this request saves to was deleted or you can no longer change it; run the command again",
                {"unavailable_apps": unavailable},
            )
    keys = sorted(values)
    if row.app_ids and not keys:
        db.commit()  # nothing typed: no app's Environment changes, and there is nothing to audit
        return {"ok": True, "keys": []}
    env_deps = []
    for app in apps:
        env_deps.append(set_env_vars(db, app, values, user_id=user.id))
        audit.record(
            db,
            "app.update",
            request=request,
            user_id=user.id,
            project_id=app.project_id,
            app_id=app.id,
            changes=["env"],
            via="cli.input",
        )
    audit.record(
        db, "cli.input_submit", request=request, user_id=user.id, input_id=row.id, keys=keys, app_ids=row.app_ids
    )
    db.commit()
    for env_dep in env_deps:
        dispatch_env_deployment(env_dep)
    return {"ok": True, "keys": keys}
