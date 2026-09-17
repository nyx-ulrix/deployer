import importlib
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AfterValidator, BaseModel, Field
from pydantic_core import PydanticCustomError
from sqlalchemy import delete, select

from app.deps import CurrentUser, DbSession, ProjectAccess, require_role
from app.errors import ApiError
from app.models import ApiKey, DataSource, Project, ProjectInvite, ProjectMember, SchemaLink, utcnow
from app.serializers import project_out
from app.services import audit
from app.services.slugs import unique_slug

router = APIRouter(tags=["projects"])
log = logging.getLogger(__name__)

MANAGED_SOURCE_NAMES = {"sql": "main-sql", "nosql": "main-nosql"}


def _provisioning():
    # Imported lazily (and via importlib so tests can substitute sys.modules entries).
    return importlib.import_module("app.services.provisioning")


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise PydanticCustomError("value_error", "Name must not be empty")
    return value


class Provision(BaseModel):
    sql: bool = False
    nosql: bool = False
    # Host device for the managed databases (docs/DEVICES.md); null = main server.
    device_id: str | None = None


ProjectName = Annotated[str, Field(max_length=120), AfterValidator(_clean_name)]


class ProjectCreate(BaseModel):
    name: ProjectName
    description: str | None = Field(default=None, max_length=5000)
    provision: Provision | None = None


class ProjectUpdate(BaseModel):
    name: ProjectName | None = None
    description: str | None = Field(default=None, max_length=5000)


@router.get("/projects")
def list_projects(user: CurrentUser, db: DbSession) -> list[dict]:
    rows = db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at, Project.name)
    ).all()
    return [project_out(db, project, role) for project, role in rows]


@router.post("/projects")
def create_project(body: ProjectCreate, request: Request, user: CurrentUser, db: DbSession) -> dict:
    project = Project(
        slug=unique_slug(db, body.name),
        name=body.name,
        description=(body.description or "").strip() or None,
        owner_id=user.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.flush()

    kinds = [k for k in ("sql", "nosql") if body.provision and getattr(body.provision, k)]
    provisioned: list[DataSource] = []
    if kinds:
        provisioning = _provisioning()
        placement: dict = {}
        if body.provision and body.provision.device_id:
            from app.services import devices

            for kind in kinds:
                devices.validate_placement(db, project, body.provision.device_id, kind)
            placement = {"device_id": body.provision.device_id}
        try:
            for kind in kinds:
                source = provisioning.provision_managed_source(
                    db, project, kind, MANAGED_SOURCE_NAMES[kind], **placement
                )
                db.add(source)
                db.flush()
                provisioned.append(source)
        except Exception:
            # Undo databases already created on the servers, then the metadata.
            for source in provisioned:
                try:
                    provisioning.drop_managed_source(db, source)
                except Exception:  # noqa: BLE001
                    log.warning("Failed to drop managed source %s after a failed create", source.name, exc_info=True)
            db.rollback()
            raise

    audit.record(
        db,
        "project.create",
        request=request,
        user_id=user.id,
        project_id=project.id,
        slug=project.slug,
        provisioned=kinds,
    )
    db.commit()
    return project_out(db, project, "owner")


@router.get("/projects/{project_id}")
def get_project(access: Annotated[ProjectAccess, Depends(require_role("viewer"))], db: DbSession) -> dict:
    return project_out(db, access.project, access.role)


@router.patch("/projects/{project_id}")
def update_project(
    body: ProjectUpdate, access: Annotated[ProjectAccess, Depends(require_role("admin"))], db: DbSession
) -> dict:
    project = access.project
    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        project.name = body.name
    if "description" in fields:
        project.description = (body.description or "").strip() or None
    project.updated_at = utcnow()
    db.commit()
    return project_out(db, project, access.role)


@router.delete("/projects/{project_id}")
def delete_project(
    request: Request,
    access: Annotated[ProjectAccess, Depends(require_role("owner"))],
    db: DbSession,
    confirm: Annotated[str | None, Query()] = None,
) -> dict:
    project = access.project
    if confirm != project.slug:
        raise ApiError(
            400,
            "confirmation_required",
            "Pass ?confirm=<project slug> to delete this project",
            {"slug": project.slug},
        )
    # docs/BACKUPS.md: every managed database gets a final snapshot (kept 30 days) before it is dropped;
    # the snapshot + drop run as jobs that don't depend on the project rows deleted below.
    from app.services import backups, jobs

    finalize_jobs = []
    managed = [s for s in project.data_sources if s.mode == "managed"]
    if managed:
        provisioning = _provisioning()
        for source in managed:
            if source.deleted_at is not None:
                continue  # already handled by its own delete
            job = backups.enqueue_detached_finalize(db, source, user_id=access.user.id)
            if job is None:
                provisioning.drop_managed_source(db, source)
            else:
                finalize_jobs.append(job.id)
        # drop_managed_source may or may not delete the row itself; reload before the cascade.
        db.flush()
        db.expire(project, ["data_sources"])
    backups.expire_project_backups(db, project.id)

    project_id, slug = project.id, project.slug
    db.execute(delete(SchemaLink).where(SchemaLink.project_id == project_id))
    db.execute(delete(ApiKey).where(ApiKey.project_id == project_id))
    db.execute(delete(ProjectInvite).where(ProjectInvite.project_id == project_id))
    db.delete(project)
    audit.record(db, "project.delete", request=request, user_id=access.user.id, project_id=project_id, slug=slug)
    db.commit()
    for job_id in finalize_jobs:
        jobs.dispatch(job_id)
    return {"ok": True}
