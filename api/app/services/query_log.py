"""Server-side query log (docs/QUERY_EDITOR.md): every console/editor run as a `query_runs` row.

This is the only table that stores query text; audit logs keep counts only. Rows are insert-only
and pruned by the worker (`prune`: older than RETENTION_DAYS, or beyond MAX_RUNS_PER_PROJECT).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import DataSource, QueryRun, User, utcnow
from app.serializers import iso

RETENTION_DAYS = 90
MAX_RUNS_PER_PROJECT = 10_000
LIST_TEXT_LIMIT = 2_000


def _outcome(result: dict | None, error: ApiError | None) -> tuple[str, int, int, int | None, str | None]:
    """`(status, statements, rows, affected_rows, error_message)` of a run."""
    if error is not None:
        if error.code == "read_only_role":
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
    run = QueryRun(
        project_id=project_id,
        data_source_id=ds.id,
        source_name=ds.name,
        kind=ds.kind,
        engine=ds.engine,
        user_id=user.id,
        user_email=user.email,
        query_text=query_text,
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
) -> tuple[list[QueryRun], bool]:
    """Newest first; `user_id=None` means everyone. Returns `(runs, has_more)`."""
    stmt = select(QueryRun).where(QueryRun.project_id == project_id)
    if user_id is not None:
        stmt = stmt.where(QueryRun.user_id == user_id)
    if source_id:
        stmt = stmt.where(QueryRun.data_source_id == source_id)
    if before is not None:
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
        # Ids are fetched first: MariaDB does not allow LIMIT/OFFSET inside an IN subquery.
        stale = list(
            db.scalars(
                select(QueryRun.id)
                .where(QueryRun.project_id == project_id)
                .order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
                .offset(MAX_RUNS_PER_PROJECT)
            )
        )
        for i in range(0, len(stale), 1000):
            deleted += db.execute(delete(QueryRun).where(QueryRun.id.in_(stale[i : i + 1000]))).rowcount
    return deleted
