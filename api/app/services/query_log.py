"""Server-side query log (docs/QUERY_EDITOR.md): every console/editor run as a `query_runs` row.

This is the only table that stores query text; audit logs keep counts only. Rows are insert-only,
keep at most STORED_TEXT_LIMIT chars of text, and are pruned by the worker (`prune`: older than
RETENTION_DAYS, or beyond MAX_RUNS_PER_PROJECT) and per project on insert (A-031). Password literals
are masked before the text is stored (A-119), as are URI, connection-string and `auth()` passwords (V-05).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import DataSource, QueryRun, User, utcnow
from app.serializers import iso
from app.services import connections

RETENTION_DAYS = 90
MAX_RUNS_PER_PROJECT = 10_000
LIST_TEXT_LIMIT = 2_000
STORED_TEXT_LIMIT = 20_000  # A-031: requests may carry 200 000 chars; the log keeps the head
PRUNE_SLACK = 500  # record_run trims a project once it is this far over MAX_RUNS_PER_PROJECT

REDACTED = "'***'"
_LIT = r"""(?:'(?:[^'\\]|\\.|'')*'|"(?:[^"\\]|\\.|"")*")"""
# A-119: the literal after each prefix is a password: MySQL/MariaDB `IDENTIFIED [WITH plugin] BY|AS`,
# `SET PASSWORD ... =`, `PASSWORD('x')`; PostgreSQL `[ENCRYPTED] PASSWORD 'x'`; Mongo `pwd: "x"` and
# `changeUserPassword("user", "x")` / `[db.]auth("user", "x")`. ponytail: literal patterns only, a
# password built by an expression or dollar-quoted ($$x$$) is kept; add a SQL tokenizer if that shows up.
_SECRET = re.compile(
    r"(\bIDENTIFIED\s+(?:WITH\s+\S+\s+)?(?:BY|AS)\s+(?:PASSWORD\s+)?"
    r"|\bSET\s+PASSWORD\b[^=;]{0,300}=\s*(?:PASSWORD\s*\(\s*)?"  # bounded: `*` is O(n^2) on repeats
    r"|(?<![\"'])\bPASSWORD\s*(?:\(\s*)?"
    r"|\bpwd[\"']?\s*:\s*"
    rf"|\b(?:changeUserPassword|auth)\s*\(\s*{_LIT}\s*,\s*)"
    rf"{_LIT}",
    re.IGNORECASE,
)
# V-05: libpq/ODBC `password=x` / `Pwd=x;` inside a connection string (dblink, CREATE SERVER, ...). A quoted
# value is SQL's `WHERE password = 'x'` (kept); `PASSWORD(` is MySQL's function, handled above.
_CONNSTR = re.compile(r"""(\b(?:password|pwd)\s*=\s*)[^\s'";()]+(?=[\s'";)]|$)""", re.IGNORECASE)


def redact(text: str) -> str:
    """`text` with every password literal, URI `user:password@` and connection-string password masked."""
    text = _SECRET.sub(lambda m: m.group(1) + REDACTED, text)
    return _CONNSTR.sub(r"\1***", connections.redact(text, limit=None))


def _outcome(result: dict | None, error: ApiError | None) -> tuple[str, int, int, int | None, str | None]:
    """`(status, statements, rows, affected_rows, error_message)` of a run."""
    if error is not None:
        if error.code in ("read_only_role", "shell_code_refused"):
            status = "refused"
        elif error.code == "query_timeout":
            status = "timeout"
        else:
            status = "error"
        return status, 0, 0, None, error.message
    if result is None:  # the service crashed with something that is not an ApiError
        return "error", 0, 0, None, None
    if result.get("kind") == "sql":
        results = result.get("results") or []
        errors = [r["error"] for r in results if r.get("type") == "error"]
        counts = [r["affected_rows"] for r in results if r.get("type") == "count"]
        rows = sum(r.get("row_count") or 0 for r in results)
        affected = sum(counts) if counts else None
        if not errors:
            return "ok", len(results), rows, affected, None
        first = errors[0]
        status = "timeout" if first.get("code") == "query_timeout" else "error"
        return status, len(results), rows, affected, first.get("message")
    docs = result.get("result_docs")
    rows = len(docs) if isinstance(docs, list) else 0
    err = result.get("error")
    return ("error", 1, rows, None, err.get("message")) if err else ("ok", 1, rows, None, None)


def record_run(
    db: Session,
    *,
    project_id: str,
    ds: DataSource,
    user: User,
    query_text: str,
    read_only: bool,
    layout: str,
    duration_ms: int,
    result: dict | None = None,
    error: ApiError | None = None,
) -> QueryRun:
    """Adds the log row for one run to the session. Caller commits."""
    status, statements, rows, affected, message = _outcome(result, error)
    # The daily prune alone lets a busy project grow for a day; trim it here too (A-031).
    count = db.scalar(select(func.count()).select_from(QueryRun).where(QueryRun.project_id == project_id))
    if count > MAX_RUNS_PER_PROJECT + PRUNE_SLACK:
        _trim_project(db, project_id)
    run = QueryRun(
        project_id=project_id,
        data_source_id=ds.id,
        source_name=ds.name,
        kind=ds.kind,
        engine=ds.engine,
        user_id=user.id,
        user_email=user.email,
        query_text=redact(query_text)[:STORED_TEXT_LIMIT],
        status=status,
        statements=statements,
        rows=rows,
        affected_rows=affected,
        duration_ms=duration_ms,
        error_message=message,
        read_only=read_only,
        layout=layout,
    )
    db.add(run)
    return run


def serialize(run: QueryRun, *, truncate: int | None = None) -> dict:
    out = {
        "id": run.id,
        "project_id": run.project_id,
        "data_source_id": run.data_source_id,
        "source_name": run.source_name,
        "kind": run.kind,
        "engine": run.engine,
        "user_id": run.user_id,
        "user_email": run.user_email,
        "query_text": run.query_text,
        "status": run.status,
        "statements": run.statements,
        "rows": run.rows,
        "affected_rows": run.affected_rows,
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
        "read_only": run.read_only,
        "layout": run.layout,
        "created_at": iso(run.created_at),
    }
    if truncate is not None and len(run.query_text) > truncate:
        out["query_text"] = run.query_text[:truncate]
        out["query_truncated"] = True
    return out


def list_runs(
    db: Session,
    project_id: str,
    *,
    user_id: str | None,
    source_id: str | None,
    before: datetime | None,
    limit: int,
    before_id: str | None = None,
) -> tuple[list[QueryRun], bool]:
    """Newest first; `user_id=None` means everyone. Returns `(runs, has_more)`.

    `before_id` (the last row of the previous page) is the exact keyset cursor: runs sharing its
    timestamp are kept (A-032). `before` alone is a plain `created_at <` cutoff and the fallback
    when that row is gone.
    """
    stmt = select(QueryRun).where(QueryRun.project_id == project_id)
    if user_id is not None:
        stmt = stmt.where(QueryRun.user_id == user_id)
    if source_id:
        stmt = stmt.where(QueryRun.data_source_id == source_id)
    anchor = get_run(db, project_id, before_id) if before_id else None
    if anchor is not None:
        stmt = stmt.where(
            or_(
                QueryRun.created_at < anchor.created_at,
                and_(QueryRun.created_at == anchor.created_at, QueryRun.id < anchor.id),
            )
        )
    elif before is not None:
        stmt = stmt.where(QueryRun.created_at < before)
    runs = list(db.scalars(stmt.order_by(QueryRun.created_at.desc(), QueryRun.id.desc()).limit(limit + 1)))
    return runs[:limit], len(runs) > limit


def get_run(db: Session, project_id: str, run_id: str) -> QueryRun | None:
    run = db.get(QueryRun, run_id)
    return run if run is not None and run.project_id == project_id else None


def delete_before(db: Session, project_id: str, before: datetime) -> int:
    result = db.execute(delete(QueryRun).where(QueryRun.project_id == project_id, QueryRun.created_at < before))
    return result.rowcount or 0


def prune(db: Session, now: datetime | None = None) -> int:
    """Deletes runs older than RETENTION_DAYS and, per project, beyond the newest MAX_RUNS_PER_PROJECT."""
    now = now or utcnow()
    deleted = db.execute(delete(QueryRun).where(QueryRun.created_at < now - timedelta(days=RETENTION_DAYS))).rowcount
    crowded = db.execute(
        select(QueryRun.project_id).group_by(QueryRun.project_id).having(func.count() > MAX_RUNS_PER_PROJECT)
    ).scalars()
    for project_id in list(crowded):
        deleted += _trim_project(db, project_id)
    return deleted


def _trim_project(db: Session, project_id: str) -> int:
    """Deletes the project's runs beyond the newest MAX_RUNS_PER_PROJECT."""
    # Ids are fetched first: MariaDB does not allow LIMIT/OFFSET inside an IN subquery.
    stale = list(
        db.scalars(
            select(QueryRun.id)
            .where(QueryRun.project_id == project_id)
            .order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
            .offset(MAX_RUNS_PER_PROJECT)
        )
    )
    deleted = 0
    for i in range(0, len(stale), 1000):
        deleted += db.execute(delete(QueryRun).where(QueryRun.id.in_(stale[i : i + 1000]))).rowcount
    return deleted
