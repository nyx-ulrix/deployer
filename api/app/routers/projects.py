import importlib
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AfterValidator, BaseModel, Field
from pydantic_core import PydanticCustomError
from sqlalchemy import delete, select

from app.deps import CurrentUser, DbSession, ProjectAccess, ProjectCreator, require_role
from app.errors import ApiError
from app.models import ApiKey, App, DataSource, Project, ProjectInvite, ProjectMember, SchemaLink, utcnow
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
def create_project(body: ProjectCreate, request: Request, user: ProjectCreator, db: DbSession) -> dict:
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
    cloud: Annotated[Literal["keep", "delete"] | None, Query()] = None,
) -> dict:
    project = access.project
    if confirm != project.slug:
        raise ApiError(
            400,
            "confirmation_required",
            "Pass ?confirm=<project slug> to delete this project",
            {"slug": project.slug},
        )
    # docs/CLOUD.md "C2-5": what Deployer created in the user's cloud account is billed there. Deleting the
    # project never decides for the owner: without `cloud` it is refused with the list; `delete` queues each
    # one's cleanup (final snapshot / backup first), `keep` leaves them running in the account, untracked.
    cloud_jobs, in_cloud = _cloud_cleanup(db, project, cloud, access.user.id)
    # docs/BACKUPS.md: every managed database gets a final snapshot (kept 30 days) before it is dropped;
    # the snapshot + drop run as jobs that don't depend on the project rows deleted below.
    from app.services import backups, jobs

    finalize_jobs = []
    managed = [s for s in project.data_sources if s.mode == "managed"]
    # A-195: what Settings -> Backups needs to restore the project from its final snapshots.
    kept = {
        "name": project.name,
        "description": project.description,
        "members": [{"user_id": m.user_id, "role": m.role} for m in project.members],
        "sources": {
            s.id: {
                "name": s.name,
                "kind": s.kind,
                "engine": s.engine,
                "database_name": s.database_name,
                "device_id": s.device_id,
            }
            for s in managed
            if s.deleted_at is None
        },
    }
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
    audit.record(
        db,
        "project.delete",
        request=request,
        user_id=access.user.id,
        project_id=project_id,
        slug=slug,
        cloud=cloud if in_cloud else None,
        cloud_resources=in_cloud or None,
        **kept,
    )
    db.commit()
    for job_id in finalize_jobs + cloud_jobs:
        jobs.dispatch(job_id)
    out: dict = {"ok": True}
    if in_cloud:
        out["cloud"] = {"choice": cloud, "resources": in_cloud, "job_ids": cloud_jobs}
    return out


CLOUD_CHOICE = (
    "Choose what happens to them: cloud=delete removes them from your AWS / Firebase account (databases keep a "
    "final snapshot or backup there, billed for storage until you delete it in the provider's console); "
    "cloud=keep leaves them running in your account, still billed by AWS / Google, and Deployer stops tracking "
    "them (manage or delete them in the provider's console)."
)


def _cloud_cleanup(db, project: Project, choice: str | None, user_id: str) -> tuple[list[str], list[dict]]:
    """The project's databases and apps with resources Deployer created in a cloud account, and - for
    `delete` - the queued cleanup jobs, detached from the project so they outlive it. Refuses (409) without a
    choice. Connected databases (Deployer never created them) are only forgotten either way."""
    from app.models import CloudConnection, Job
    from app.services import cloud_db, cloud_deploy

    sources = [
        s
        for s in db.scalars(select(DataSource).where(DataSource.project_id == project.id))
        if s.deleted_at is None and cloud_db.is_created(s)
    ]
    apps = [
        a for a in db.scalars(select(App).where(App.project_id == project.id, App.target != "local")) if a.cloud_state
    ]
    found = [
        {"type": "database", "id": s.id, "name": s.name, "resources": cloud_db.resources(s.cloud_state)}
        for s in sources
    ] + [
        {"type": "app", "id": a.id, "name": a.name, "resources": cloud_deploy.resources(a.target, a.cloud_state)}
        for a in apps
    ]
    if not found:
        return [], []
    if choice is None:
        names = ", ".join(f"{f['type']} {f['name']}" for f in found)
        raise ApiError(
            409,
            "cloud_resources_left",
            f"This project has things Deployer created in your cloud account ({names}). {CLOUD_CHOICE}",
            {"resources": found},
        )
    if choice == "keep":
        return [], found
    # A connection scoped to this project goes with it (FK cascade), so its cleanup jobs could not sign in.
    own = {c.id for c in db.scalars(select(CloudConnection).where(CloudConnection.project_id == project.id))}
    needs_own = [
        f"{f['type']} {f['name']}" for f, x in zip(found, sources + apps, strict=True) if x.cloud_connection_id in own
    ]
    if needs_own:
        raise ApiError(
            409,
            "cloud_connection_in_project",
            "Remove these from the project first (Databases / Deploys tab), then delete the project: removing them "
            "needs a cloud connection that belongs only to this project and goes with it: " + ", ".join(needs_own),
            {"resources": needs_own},
        )
    job_ids = [cloud_db.enqueue_delete(db, s, user_id).id for s in sources]  # 409 while one is being created
    job_ids += [j for a in apps if (j := cloud_deploy.enqueue_teardown(db, a, user_id))]
    db.flush()
    for job_id in job_ids:
        db.get(Job, job_id).project_id = None  # jobs.project_id cascades: keep them past the project
    return job_ids, found
