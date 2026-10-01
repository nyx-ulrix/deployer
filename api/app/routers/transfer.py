"""Export / import endpoints: `/setup/import`, `/instance/export`, `/projects/export`, `/projects/import`,
and their background-job forms (A-044) `.../jobs` + `/transfers` (docs/API.md "Export / import")."""

from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import CurrentUser, DbSession, InstanceOwner, ProjectCreator
from app.errors import ApiError, conflict, forbidden, not_found
from app.models import Job, Project, ProjectMember, User
from app.serializers import project_out
from app.services import audit, jobs, transfer
from app.services.instance_settings import is_initialized

router = APIRouter(tags=["transfer"])


class InstanceExportInput(BaseModel):
    passphrase: str = Field(min_length=transfer.MIN_PASSPHRASE)


class ProjectsExportInput(BaseModel):
    project_ids: list[str] = Field(min_length=1, max_length=500)
    passphrase: str = Field(min_length=transfer.MIN_PASSPHRASE)


class TempFileResponse(StreamingResponse):
    """Streams a temp file and always deletes it, also when the client is gone before the first byte
    (A-044: a tunnel that timed out the request; iter_file's own cleanup only runs once it is read)."""

    def __init__(self, path: str, filename: str):
        super().__init__(
            transfer.iter_file(path),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
        self.path = path

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            transfer._unlink(self.path)


def _save_upload(file: UploadFile) -> str:
    return transfer.save_upload(file.file)


@router.post("/setup/import")
def setup_import(
    db: DbSession,
    request: Request,
    file: Annotated[UploadFile, File()],
    passphrase: Annotated[str, Form()],
) -> dict:
    if is_initialized(db):
        raise conflict("already_initialized", "This instance is already set up")
    transfer.check_passphrase(passphrase)
    path = _save_upload(file)
    try:
        payload = transfer.read_export_file(path, passphrase, "instance")
    finally:
        transfer._unlink(path)
    if is_initialized(db):
        raise conflict("already_initialized", "This instance is already set up")
    summary = transfer.import_instance(db, payload)
    del payload
    owner = db.scalar(select(User).where(User.is_instance_owner.is_(True)))
    audit.record(db, "instance.import", request=request, user_id=owner.id if owner else None, **summary)
    db.commit()
    return {"ok": True, "summary": summary}


@router.post("/instance/export")
def instance_export(
    body: InstanceExportInput, user: InstanceOwner, db: DbSession, request: Request
) -> StreamingResponse:
    projects = list(db.scalars(select(Project).order_by(Project.created_at)))
    path, counts = transfer.build_export_file(db, scope="instance", projects=projects, passphrase=body.passphrase)
    audit.record(db, "instance.export", request=request, user_id=user.id, **counts)
    db.commit()
    return TempFileResponse(path, transfer.export_filename("instance"))


def _owned_projects(db: DbSession, user: User, project_ids: list[str]) -> list[Project]:
    projects = []
    for project_id in dict.fromkeys(project_ids):
        project = db.get(Project, project_id)
        member = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        if project is None or member is None:
            raise not_found("Project")
        if member.role != "owner" and project.owner_id != user.id:
            raise forbidden(f"Only the owner can export project '{project.name}'")
        projects.append(project)
    return projects


@router.post("/projects/export")
def projects_export(body: ProjectsExportInput, user: CurrentUser, db: DbSession, request: Request) -> StreamingResponse:
    projects = _owned_projects(db, user, body.project_ids)
    path, counts = transfer.build_export_file(db, scope="projects", projects=projects, passphrase=body.passphrase)
    for project in projects:
        audit.record(db, "projects.export", request=request, user_id=user.id, project_id=project.id, **counts)
    db.commit()
    return TempFileResponse(path, transfer.export_filename("projects"))


def _read_projects_upload(file: UploadFile, passphrase: str) -> dict:
    transfer.check_passphrase(passphrase)
    path = _save_upload(file)
    try:
        payload = transfer.read_export_file(path, passphrase, "projects")
    finally:
        transfer._unlink(path)
    if not payload.get("projects"):
        raise ApiError(400, "invalid_export", "The export contains no projects")
    return payload


@router.post("/projects/import")
def projects_import(
    user: ProjectCreator,
    db: DbSession,
    request: Request,
    file: Annotated[UploadFile, File()],
    passphrase: Annotated[str, Form()],
) -> dict:
    payload = _read_projects_upload(file, passphrase)
    projects, summary = transfer.import_projects(db, payload, user)
    del payload
    for project in projects:
        audit.record(
            db,
            "projects.import",
            request=request,
            user_id=user.id,
            project_id=project.id,
            data_sources=summary["data_sources"],
            rows=summary["rows"],
            documents=summary["documents"],
        )
    db.commit()
    return {"ok": True, "projects": [project_out(db, p, "owner") for p in projects], "summary": summary}


# ---------------------------------------------------------------------------------------------
# background jobs (A-044): the request answers at once; a tunnel's ~100 s limit no longer applies
# ---------------------------------------------------------------------------------------------


def _run(job_id: str) -> None:
    try:
        jobs.run_job(job_id)
    finally:
        transfer._pending.pop(job_id, None)  # also when it was cancelled before it started


def _spawn(job_id: str) -> None:
    """Runs the job in a thread of this process (tests replace this with `_run`)."""
    threading.Thread(target=_run, args=(job_id,), name=f"transfer-{job_id[:8]}", daemon=True).start()


def _start(
    db: DbSession, job_type: str, user: User, params: dict, pending: dict, project_id: str | None = None
) -> dict:
    job = jobs.enqueue(db, type=job_type, params=params, project_id=project_id, created_by_id=user.id)
    db.commit()
    transfer._pending[job.id] = pending
    _spawn(job.id)
    db.refresh(job)
    return {"job": jobs.job_out(job)}


@router.post("/instance/export/jobs")
def instance_export_job(body: InstanceExportInput, user: InstanceOwner, db: DbSession, request: Request) -> dict:
    params = {"scope": "instance", "filename": transfer.export_filename("instance")}
    return _start(db, transfer.EXPORT_JOB, user, params, {"passphrase": body.passphrase, "request": request})


@router.post("/projects/export/jobs")
def projects_export_job(body: ProjectsExportInput, user: CurrentUser, db: DbSession, request: Request) -> dict:
    projects = _owned_projects(db, user, body.project_ids)
    params = {
        "scope": "projects",
        "project_ids": [p.id for p in projects],
        "filename": transfer.export_filename("projects"),
    }
    pending = {"passphrase": body.passphrase, "request": request}
    # One project: the job also shows in that project's Activity drawer.
    return _start(db, transfer.EXPORT_JOB, user, params, pending, projects[0].id if len(projects) == 1 else None)


@router.post("/projects/import/jobs")
def projects_import_job(
    user: ProjectCreator,
    db: DbSession,
    request: Request,
    file: Annotated[UploadFile, File()],
    passphrase: Annotated[str, Form()],
) -> dict:
    """Upload, then a job: the file is checked and decrypted here (a wrong passphrase answers at once);
    the job recreates the projects and their data."""
    payload = _read_projects_upload(file, passphrase)
    params = {"filename": (file.filename or "")[:255], "projects": len(payload["projects"])}
    return _start(db, transfer.IMPORT_JOB, user, params, {"payload": payload, "request": request})


TRANSFER_JOBS = (transfer.EXPORT_JOB, transfer.IMPORT_JOB)


def _my_transfer_job(db: DbSession, user: User, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.type not in TRANSFER_JOBS or job.created_by_id != user.id:
        raise not_found("Job")
    return job


@router.get("/transfers")
def list_transfers(user: CurrentUser, db: DbSession) -> list[dict]:
    """The caller's own export / import jobs, newest first."""
    transfer.prune_exports()
    rows = db.scalars(
        select(Job)
        .where(Job.type.in_(TRANSFER_JOBS), Job.created_by_id == user.id)
        .order_by(Job.created_at.desc())
        .limit(20)
    )
    return [jobs.job_out(job) for job in rows]


@router.get("/transfers/{job_id}/download")
def download_transfer(job_id: str, user: CurrentUser, db: DbSession) -> FileResponse:
    job = _my_transfer_job(db, user, job_id)
    if job.type != transfer.EXPORT_JOB or job.status != "succeeded":
        raise conflict("export_not_ready", "This export hasn't finished")
    transfer.prune_exports()  # past 24 hours it is gone, also when nothing listed transfers since
    path = transfer.export_path(job.id)
    if not path.exists():
        raise ApiError(410, "export_expired", "This export file is gone (they are kept for 24 hours). Export again.")
    return FileResponse(path, media_type="application/json", filename=(job.params or {}).get("filename"))


@router.post("/transfers/{job_id}/cancel")
def cancel_transfer(job_id: str, user: CurrentUser, db: DbSession) -> dict:
    job = jobs.request_cancel(db, _my_transfer_job(db, user, job_id))
    db.commit()
    return jobs.job_out(job)
