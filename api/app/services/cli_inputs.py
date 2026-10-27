"""Input requests (docs/CLI.md "Input requests").

A command-line user or agent on a server without a screen sometimes needs its user to type something:
a secret for an app's Environment, an OAuth client id, a code from a sign-in page. It creates an input
request (`create`) and polls it; the user opens `<public_url>/input/<id>` on any device, signs in to the
dashboard and fills the form (`submit`). Without `app_ids` the next poll hands the values to the command
line once and the row forgets them; with `app_ids` the values go straight into those apps' Environment
and are never stored here or returned.

Every state change is a conditional UPDATE with a rowcount check (like jobs.claim), so two polls, or a
poll and a cancel, can never both win: exactly one poll gets the values.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.crypto import decrypt_secret, encrypt_secret
from app.errors import ApiError, not_found
from app.models import App, CliInput, CliToken, Project, ProjectMember, User, role_rank, utcnow
from app.serializers import iso

INPUT_TTL_SECONDS = 30 * 60
POLL_INTERVAL_SECONDS = 3
# Values submitted but never collected are dropped this long after the submit (the command line polls
# every few seconds, so this only matters when it was stopped). The worker does it on every tick.
VALUES_TTL = timedelta(minutes=10)
MAX_VALUE_BYTES = 8 * 1024
# All values together, as JSON: encrypted and base64'd they still fit values_encrypted.
MAX_VALUES_BYTES = 48 * 1024
CREATE_LIMIT_PER_HOUR = 30

# Still cancellable: not filled yet, or filled with values nobody has collected. A request with app_ids
# that was submitted is done (its values are already in the apps' Environment) and stays submitted.
_CANCELLABLE = or_(
    CliInput.status == "pending",
    and_(CliInput.status == "submitted", CliInput.values_encrypted.is_not(None)),
)


def _fresh_transaction(db: Session) -> None:
    """Ends the transaction earlier reads opened, so the conditional UPDATE that follows waits for a
    concurrent one and then sees its result (MariaDB's innodb_snapshot_isolation would otherwise refuse
    to update a row changed since this transaction's first read)."""
    db.commit()


def _transition(db: Session, row: CliInput, condition, **values: Any) -> bool:
    """One state change: True when this call made it, False when the row was no longer in that state
    (another request changed it first). `row` is reloaded either way. Caller commits."""
    _fresh_transaction(db)
    result = db.execute(
        update(CliInput)
        .where(CliInput.id == row.id, condition)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    db.refresh(row)
    return result.rowcount == 1


def expire_due(db: Session, input_id: str | None = None) -> int:
    """Expires pending requests past `expires_at`, and wipes values submitted more than VALUES_TTL ago
    that no poll collected. One request (before it is read) or all of them (every scheduler tick, so the
    values go even when the command line is gone). Caller commits."""
    now = utcnow()
    scope = [CliInput.id == input_id] if input_id else []
    due = [
        and_(CliInput.status == "pending", CliInput.expires_at <= now),
        and_(
            CliInput.status == "submitted",
            CliInput.values_encrypted.is_not(None),
            CliInput.submitted_at < now - VALUES_TTL,
        ),
    ]
    expired = 0
    for condition in due:
        result = db.execute(
            update(CliInput)
            .where(*scope, condition)
            .values(status="expired", values_encrypted=None)
            .execution_options(synchronize_session=False)
        )
        expired += result.rowcount
    return expired


def create(
    db: Session,
    user: User,
    *,
    title: str,
    description: str | None,
    fields: list[dict[str, Any]],
    app_ids: list[str] | None,
    token: CliToken | None = None,
) -> CliInput:
    """Adds a pending request (caller commits). `fields` and `app_ids` are already validated. `token` is
    the `dpt_` token that asks (None for a dashboard session)."""
    row = CliInput(
        user_id=user.id,
        cli_token_id=token.id if token else None,
        token_name=token.name if token else None,
        token_prefix=token.prefix if token else None,
        title=title,
        description=description or None,
        fields=fields,
        app_ids=app_ids or None,
        status="pending",
        expires_at=utcnow() + timedelta(seconds=INPUT_TTL_SECONDS),
    )
    db.add(row)
    db.flush()
    return row


def get_own(db: Session, user: User, input_id: str) -> CliInput:
    """The request if `user` created it; 404 otherwise (don't reveal that it exists)."""
    _fresh_transaction(db)
    expire_due(db, input_id)
    row = db.get(CliInput, input_id, populate_existing=True)
    if row is None or row.user_id != user.id:
        raise not_found("Input request")
    return row


def get_for_cli(db: Session, user: User, input_id: str, cli_token_id: str | None) -> CliInput:
    """Poll and cancel: the request only for the credential that created it. One made by a `dpt_` token
    answers to that token alone; one made by a dashboard session to any session of its user. 404 for
    anything else, so another token of the same user can't collect the values."""
    row = get_own(db, user, input_id)
    if row.token_prefix is not None:  # made by a token (cli_token_id is None once that token is deleted)
        allowed = cli_token_id is not None and cli_token_id == row.cli_token_id
    else:
        allowed = cli_token_id is None
    if not allowed:
        raise not_found("Input request")
    return row


def requested_by(row: CliInput) -> dict:
    if row.token_prefix is None:
        return {"kind": "session", "name": None, "prefix": None}
    return {"kind": "cli", "name": row.token_name, "prefix": row.token_prefix}


def submitted_keys(row: CliInput) -> list[str]:
    return [f["key"] for f in row.fields if f.get("set")]


def usable_apps(db: Session, user: User, app_ids: list[str]) -> tuple[list[App], int]:
    """The apps `user` may still write (developer on the app's project), and how many of `app_ids` are
    not: deleted, or in a project the user left or now only views. The reason is never told apart, so
    an id can't be used to learn whether an app exists in someone else's project."""
    apps, unavailable = [], 0
    for app_id in dict.fromkeys(app_ids):
        app = db.get(App, app_id)
        member = None
        if app is not None:
            member = db.scalar(
                select(ProjectMember).where(
                    ProjectMember.project_id == app.project_id, ProjectMember.user_id == user.id
                )
            )
        if member is None or role_rank(member.role) < role_rank("developer"):
            unavailable += 1
            continue
        apps.append(app)
    return apps, unavailable


def apps_out(db: Session, apps: list[App]) -> list[dict]:
    out = []
    for app in apps:
        project = db.get(Project, app.project_id)
        out.append({"id": app.id, "name": app.name, "project_name": project.name if project else None})
    return out


def poll(db: Session, user: User, row: CliInput) -> dict:
    """Command-line poll. Without app_ids, delivers the values once and wipes them. Caller commits."""
    if row.status == "submitted" and row.app_ids:
        apps, _ = usable_apps(db, user, row.app_ids)
        return {
            "status": "submitted",
            "keys": submitted_keys(row),
            "apps": [{"id": a.id, "name": a.name} for a in apps],
        }
    if row.status == "submitted" and row.values_encrypted:
        blob = row.values_encrypted
        consumed = _transition(
            db,
            row,
            and_(CliInput.status == "submitted", CliInput.values_encrypted == blob),
            status="consumed",
            values_encrypted=None,
        )
        if consumed:
            return {"status": "submitted", "values": json.loads(decrypt_secret(blob))}
    out: dict[str, Any] = {"status": row.status, "interval": POLL_INTERVAL_SECONDS}
    if row.status == "pending" and row.app_ids:
        _, unavailable = usable_apps(db, user, row.app_ids)
        if unavailable:  # the form can't be filled: the command line stops waiting and cancels
            out["unavailable_apps"] = unavailable
    return out


def cancel(db: Session, row: CliInput) -> str:
    """Cancels a pending request, or a submitted one whose values nobody collected (and wipes them).
    A submitted request with app_ids stays submitted: its values are already saved. Returns the status
    after the call. Caller commits."""
    _transition(db, row, _CANCELLABLE, status="cancelled", values_encrypted=None)
    return row.status


def cancel_for_token(db: Session, token_id: str) -> int:
    """A revoked token's requests: the open ones are cancelled and their values wiped. Caller commits."""
    result = db.execute(
        update(CliInput)
        .where(CliInput.cli_token_id == token_id, _CANCELLABLE)
        .values(status="cancelled", values_encrypted=None)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def check_pending(row: CliInput) -> None:
    if row.status != "pending":
        raise ApiError(409, "input_not_pending", f"This request is already {row.status}")


def _invalid(key: str, message: str) -> ApiError:
    return ApiError(422, "validation_error", message, {"field": key})


def clean_values(row: CliInput, values: dict[str, Any]) -> dict[str, str]:
    """The submitted values checked against the request's fields: trimmed, unknown keys, required fields,
    single line and size. Empty optional fields are left out. A field's `pattern` is a hint for the
    browser only: the server never runs a creator's regular expression (it could backtrack for minutes)."""
    fields = {f["key"]: f for f in row.fields}
    for key in values:
        if key not in fields:
            raise _invalid(key, f"Unknown field {key}")
    out: dict[str, str] = {}
    for key, field in fields.items():
        raw = values.get(key)
        value = "" if raw is None else str(raw).strip()
        label = field.get("label") or key
        if not value:
            if not field.get("optional"):
                raise _invalid(key, f"{label} is required")
            continue
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
            raise _invalid(key, f"{label} is too long (8 KB max)")
        if not field.get("multiline") and ("\n" in value or "\r" in value):
            raise _invalid(key, f"{label} must be a single line")
        out[key] = value
    if len(_dumps(out).encode("utf-8")) > MAX_VALUES_BYTES:
        raise ApiError(422, "validation_error", "The values are too large together (48 KB max)")
    return out


def _dumps(values: dict[str, str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def mark_submitted(db: Session, row: CliInput, values: dict[str, str]) -> None:
    """Records the submit, only while the request is still pending: 409 when a cancel, an expiry or
    another submit got there first. Values are kept (encrypted) only when no app takes them. Call it
    before writing any app's Environment, in the same transaction. Caller commits."""
    submitted = _transition(
        db,
        row,
        CliInput.status == "pending",
        status="submitted",
        submitted_at=utcnow(),
        fields=[{**f, "set": f["key"] in values} for f in row.fields],
        values_encrypted=None if row.app_ids else encrypt_secret(_dumps(values)),
    )
    if not submitted:
        check_pending(row)


def input_out(db: Session, user: User, row: CliInput) -> dict:
    apps, unavailable = usable_apps(db, user, row.app_ids) if row.app_ids else ([], 0)
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "fields": [{k: v for k, v in f.items() if k != "set"} for f in row.fields],
        "apps": apps_out(db, apps),
        "unavailable_apps": unavailable,
        "requested_by": requested_by(row),
        "status": row.status,
        "expires_at": iso(row.expires_at),
        "created_at": iso(row.created_at),
    }


def prune(db: Session) -> int:
    """Deletes input requests a day past expiry (caller commits)."""
    cutoff = utcnow() - timedelta(days=1)
    rows = list(db.scalars(select(CliInput).where(CliInput.expires_at < cutoff)))
    for row in rows:
        db.delete(row)
    return len(rows)
