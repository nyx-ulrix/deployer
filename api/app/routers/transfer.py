"""Export / import endpoints: `/setup/import`, `/instance/export`, `/projects/export`, `/projects/import`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession, InstanceOwner
from app.errors import ApiError, conflict, forbidden, not_found
from app.models import Project, ProjectMember, User
from app.serializers import project_out
from app.services import audit, transfer

router = APIRouter(tags=["transfer"])


class InstanceExportInput(BaseModel):
    passphrase: str = Field(min_length=transfer.MIN_PASSPHRASE)


class ProjectsExportInput(BaseModel):
    project_ids: list[str] = Field(min_length=1, max_length=500)
    passphrase: str = Field(min_length=transfer.MIN_PASSPHRASE)


def _download(path: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        transfer.iter_file(path),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _save_upload(file: UploadFile) -> str:
    return transfer.save_upload(file.file)


@router.post("/setup/import")
def setup_import(
    db: DbSession,
    request: Request,
    file: Annotated[UploadFile, File()],
    passphrase: Annotated[str, Form()],
) -> dict:
    if db.scalar(select(func.count()).select_from(User)):
        raise conflict("already_initialized", "This instance is already set up")
    transfer.check_passphrase(passphrase)
    path = _save_upload(file)
    try:
        payload = transfer.read_export_file(path, passphrase, "instance")
    finally:
        transfer._unlink(path)
    if db.scalar(select(func.count()).select_from(User)):
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
    return _download(path, transfer.export_filename("instance"))


@router.post("/projects/export")
def projects_export(body: ProjectsExportInput, user: CurrentUser, db: DbSession, request: Request) -> StreamingResponse:
    projects = []
    for project_id in dict.fromkeys(body.project_ids):
        project = db.get(Project, project_id)
        member = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        if project is None or member is None:
            raise not_found("Project")
        if member.role != "owner" and project.owner_id != user.id:
            raise forbidden(f"Only the owner can export project '{project.name}'")
        projects.append(project)
    path, counts = transfer.build_export_file(db, scope="projects", projects=projects, passphrase=body.passphrase)
    for project in projects:
        audit.record(db, "projects.export", request=request, user_id=user.id, project_id=project.id, **counts)
    db.commit()
    return _download(path, transfer.export_filename("projects"))


@router.post("/projects/import")
def projects_import(
    user: CurrentUser,
    db: DbSession,
    request: Request,
    file: Annotated[UploadFile, File()],
    passphrase: Annotated[str, Form()],
) -> dict:
    transfer.check_passphrase(passphrase)
    path = _save_upload(file)
    try:
        payload = transfer.read_export_file(path, passphrase, "projects")
    finally:
        transfer._unlink(path)
    if not payload.get("projects"):
        raise ApiError(400, "invalid_export", "The export contains no projects")
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
