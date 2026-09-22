"""Query console (docs/QUERY_CONSOLE.md): run SQL or MongoDB shell code against a data source, and the
server-side query log of those runs (docs/QUERY_EDITOR.md)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, forbidden, not_found
from app.services import audit, query_console, query_log, source_ops
from app.services.sources import get_source

router = APIRouter(tags=["query"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
QueryRunner = Annotated[ProjectAccess, Depends(require_role("viewer", api_keys=True))]  # docs/DATA_API.md
Owner = Annotated[ProjectAccess, Depends(require_role("owner"))]


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=query_console.MAX_QUERY_CHARS)
    max_rows: int = Field(query_console.DEFAULT_MAX_ROWS, ge=1, le=query_console.MAX_ROWS)
    timeout_seconds: int = Field(query_console.DEFAULT_TIMEOUT_SECONDS, ge=1, le=query_console.MAX_TIMEOUT_SECONDS)
    layout: Literal["terminal", "editor"] | None = None  # logged as given; absent = "api"


def _naive_utc(value: datetime | None) -> datetime | None:
    # Timestamps are stored naive-UTC (see models.utcnow); accept `...Z` / offsets from clients.
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


@router.post("/projects/{project_id}/data-sources/{source_id}/query")
def run_query(source_id: str, body: QueryRequest, access: QueryRunner, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id)
    # Viewers may only run read-only queries; the service refuses anything else with 403 read_only_role.
    read_only = not access.at_least("developer")
    db.commit()  # don't hold the platform DB transaction open while the query runs
    started = time.monotonic()
    ok, statements = False, None
    result, error = None, None
    try:
        result = source_ops.run_query(
            ds, body.query, max_rows=body.max_rows, timeout_seconds=body.timeout_seconds, read_only=read_only
        )
        ok, statements = query_console.summarize(result)
    except ApiError as exc:
        error = exc
        raise
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        # Counts and timing only: query text and results never reach the audit log...
        audit.record(
            db,
            "query.run",
            request=request,
            user_id=access.user.id,
            project_id=access.project.id,
            data_source_id=ds.id,
            api_key_id=access.api_key_id,
            kind=ds.kind,
            statements=statements,
            read_only=read_only,
            duration_ms=duration_ms,
            ok=ok,
        )
        # ...the query log is where the text lives, for every outcome incl. refusals and failures.
        run = query_log.record_run(
            db,
            project_id=access.project.id,
            ds=ds,
            user=access.user,
            query_text=body.query,
            read_only=read_only,
            layout="api" if access.api_key else (body.layout or "api"),
            duration_ms=duration_ms,
            result=result,
            error=error,
        )
        db.commit()
    result["run_id"] = run.id
    return result


@router.get("/projects/{project_id}/query-log")
def list_query_log(
    access: Viewer,
    db: DbSession,
    source_id: str | None = None,
    user: Literal["me", "all"] = "me",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: datetime | None = None,
) -> dict:
    if user == "all" and not access.at_least("admin"):
        raise forbidden("Only admins can see other members' query runs")
    runs, has_more = query_log.list_runs(
        db,
        access.project.id,
        user_id=None if user == "all" else access.user.id,
        source_id=source_id,
        before=_naive_utc(before),
        limit=limit,
    )
    return {"runs": [query_log.serialize(r, truncate=query_log.LIST_TEXT_LIMIT) for r in runs], "has_more": has_more}


@router.get("/projects/{project_id}/query-log/{run_id}")
def get_query_run(run_id: str, access: Viewer, db: DbSession) -> dict:
    run = query_log.get_run(db, access.project.id, run_id)
    if run is None:
        raise not_found("Query run")
    if run.user_id != access.user.id and not access.at_least("admin"):
        raise forbidden("Only admins can see other members' query runs")
    return query_log.serialize(run)


@router.delete("/projects/{project_id}/query-log")
def delete_query_log(access: Owner, db: DbSession, before: datetime) -> dict:
    deleted = query_log.delete_before(db, access.project.id, _naive_utc(before))
    db.commit()
    return {"deleted": deleted}
