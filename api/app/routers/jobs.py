"""Project jobs (docs/BACKUPS.md "API")."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.deps import DbSession, ProjectAccess, require_role
from app.errors import not_found
from app.models import Job
from app.services import audit, jobs

router = APIRouter(tags=["jobs"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]


def _get_job(db: DbSession, project_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.project_id != project_id:
        raise not_found("Job")
    return job


@router.get("/projects/{project_id}/jobs")
def list_jobs(access: Viewer, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict]:
    rows = db.scalars(
        select(Job).where(Job.project_id == access.project.id).order_by(Job.created_at.desc()).limit(limit)
    )
    return [jobs.job_out(job) for job in rows]


@router.get("/projects/{project_id}/jobs/{job_id}")
def get_job(job_id: str, access: Viewer, db: DbSession) -> dict:
    return jobs.job_out(_get_job(db, access.project.id, job_id))


@router.post("/projects/{project_id}/jobs/{job_id}/cancel")
def cancel_job(job_id: str, access: Admin, db: DbSession, request: Request) -> dict:
    job = _get_job(db, access.project.id, job_id)
    jobs.request_cancel(db, job)
    audit.record(db, "job.cancel", request=request, user_id=access.user.id, project_id=access.project.id, job_id=job.id)
    db.commit()
    return jobs.job_out(job)
