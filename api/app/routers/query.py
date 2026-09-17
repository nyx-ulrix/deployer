"""Query console (docs/QUERY_CONSOLE.md): run SQL or MongoDB shell code against a data source."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.deps import DbSession, ProjectAccess, require_role
from app.services import audit, query_console, source_ops
from app.services.sources import get_source

router = APIRouter(tags=["query"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=query_console.MAX_QUERY_CHARS)
    max_rows: int = Field(query_console.DEFAULT_MAX_ROWS, ge=1, le=query_console.MAX_ROWS)
    timeout_seconds: int = Field(query_console.DEFAULT_TIMEOUT_SECONDS, ge=1, le=query_console.MAX_TIMEOUT_SECONDS)


@router.post("/projects/{project_id}/data-sources/{source_id}/query")
def run_query(source_id: str, body: QueryRequest, access: Viewer, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id)
    # Viewers may only run read-only queries; the service refuses anything else with 403 read_only_role.
    read_only = not access.at_least("developer")
    db.commit()  # don't hold the platform DB transaction open while the query runs
    started = time.monotonic()
    ok, statements = False, None
    try:
        result = source_ops.run_query(
            ds, body.query, max_rows=body.max_rows, timeout_seconds=body.timeout_seconds, read_only=read_only
        )
        ok, statements = query_console.summarize(result)
    finally:
        # Counts and timing only: query text and results are never logged.
        audit.record(
            db,
            "query.run",
            request=request,
            user_id=access.user.id,
            project_id=access.project.id,
            data_source_id=ds.id,
            kind=ds.kind,
            statements=statements,
            read_only=read_only,
            duration_ms=int((time.monotonic() - started) * 1000),
            ok=ok,
        )
        db.commit()
    return result
