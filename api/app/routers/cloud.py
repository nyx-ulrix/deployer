"""Cloud connections (instance owner) and the hosting targets apps can use (docs/CLOUD.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.deps import DbSession, InstanceOwner, ProjectAccess, require_role
from app.errors import ApiError
from app.models import Project
from app.services import audit, cloud, cloud_db, jobs
from app.services.sources import data_source_out

router = APIRouter(tags=["cloud"])

Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]
Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]


class AwsCredentials(BaseModel):
    access_key_id: str = Field(max_length=40)
    secret_access_key: str = Field(max_length=100)
    region: str = Field(max_length=30)
    role_arn: str | None = Field(default=None, max_length=600)


class FirebaseCredentials(BaseModel):
    service_account_json: str = Field(max_length=20_000)
    project_id: str | None = Field(default=None, max_length=40)
    region: str | None = Field(default=None, max_length=30)


class ConnectionCreate(BaseModel):
    provider: Literal["aws", "firebase"]
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None, max_length=36)  # None: every project may use it
    aws: AwsCredentials | None = None
    firebase: FirebaseCredentials | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


@router.get("/instance/cloud")
def list_connections(owner: InstanceOwner, db: DbSession) -> dict:
    return {
        "connections": [cloud.connection_out(c, db) for c in cloud.list_connections(db)],
        "targets": cloud.TARGETS,
    }


@router.get("/instance/cloud/requirements")
def requirements(owner: InstanceOwner) -> dict:
    """The least-privilege IAM policy for the AWS user, the Google roles and APIs for the service account."""
    return cloud.requirements()


@router.post("/instance/cloud", status_code=201)
def create_connection(body: ConnectionCreate, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    creds = body.aws if body.provider == "aws" else body.firebase
    if creds is None:
        raise ApiError(422, "validation_error", f"Send the {body.provider} credentials", {"field": body.provider})
    if body.project_id and db.get(Project, body.project_id) is None:
        raise ApiError(422, "validation_error", "Project not found", {"field": "project_id"})
    conn = cloud.create_connection(
        db,
        provider=body.provider,
        name=body.name,
        project_id=body.project_id,
        raw=creds.model_dump(),
        user_id=owner.id,
    )
    # Never the credentials: provider, name and scope only.
    audit.record(
        db,
        "cloud.connection_create",
        request=request,
        user_id=owner.id,
        project_id=body.project_id,
        connection_id=conn.id,
        provider=conn.provider,
    )
    db.commit()
    return cloud.connection_out(conn, db)


@router.post("/instance/cloud/{connection_id}/check")
def check_connection(connection_id: str, owner: InstanceOwner, db: DbSession) -> dict:
    conn = cloud.check_connection(db, cloud.get_connection(db, connection_id))
    db.commit()
    return cloud.connection_out(conn, db)


@router.delete("/instance/cloud/{connection_id}")
def delete_connection(connection_id: str, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    conn = cloud.get_connection(db, connection_id)
    cloud.delete_connection(db, conn)
    audit.record(db, "cloud.connection_delete", request=request, user_id=owner.id, connection_id=connection_id)
    db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/cloud/connections")
def project_connections(access: Admin, db: DbSession) -> list[dict]:
    """Read-only: the connections this project's apps may use (instance-wide + the project's own)."""
    return [cloud.connection_out(c) for c in cloud.list_connections(db, access.project.id)]


@router.get("/projects/{project_id}/cloud/targets")
def project_targets(access: Viewer, db: DbSession) -> list[dict]:
    return cloud.targets_out(db, access.project.id)


# --- cloud databases (docs/CLOUD.md "C2") ---------------------------------------------------------


class CloudDatabaseCreate(BaseModel):
    connection_id: str = Field(max_length=36)
    name: str = Field(min_length=1, max_length=63)
    engine: Literal["mysql", "mariadb", "postgresql"]
    instance_class: str = Field(default=cloud_db.DEFAULT_CLASS, max_length=40)
    # Billable: the caller must say they accept the AWS charges (the dashboard asks with the cost note).
    confirm_billing: bool = False


class CloudDatabaseConnect(BaseModel):
    connection_id: str = Field(max_length=36)
    name: str = Field(min_length=1, max_length=63)
    resource_id: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(default="", max_length=500)
    database: str | None = Field(default=None, max_length=128)


def _name(db, project_id: str, name: str) -> str:
    from app.routers.data_sources import _ensure_name_free

    name = name.strip()
    if not name:
        raise ApiError(422, "validation_error", "name is required", {"field": "name"})
    _ensure_name_free(db, project_id, name)
    return name


def _audit(db, request: Request, access: ProjectAccess, ds, action: str) -> None:
    audit.record(
        db,
        "data_source.create",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        name=ds.name,
        kind=ds.kind,
        engine=ds.engine,
        mode=ds.mode,
        cloud=action,
        cloud_connection_id=ds.cloud_connection_id,
    )


@router.get("/projects/{project_id}/cloud/databases/options")
def database_options(access: Viewer) -> dict:
    """Where a database can live, in plain language, and the sizes / cost of a new AWS database."""
    return cloud_db.options()


@router.get("/projects/{project_id}/cloud/connections/{connection_id}/databases")
def connection_databases(connection_id: str, access: Admin, db: DbSession) -> dict:
    """The RDS / Aurora databases of an AWS connection's region, to connect one (and this PC's public IP)."""
    return cloud_db.list_resources(db, access.project.id, connection_id)


@router.post("/projects/{project_id}/cloud/databases", status_code=201)
def create_database(body: CloudDatabaseCreate, request: Request, access: Admin, db: DbSession) -> dict:
    if not body.confirm_billing:
        raise ApiError(
            422,
            "billing_not_confirmed",
            "This creates a database AWS bills to your account. " + cloud_db.COST_NOTE + " Send confirm_billing: true.",
            {"field": "confirm_billing"},
        )
    name = _name(db, access.project.id, body.name)
    ds, job = cloud_db.create(
        db,
        access.project.id,
        connection_id=body.connection_id,
        name=name,
        engine=body.engine,
        instance_class=body.instance_class,
        user_id=access.user.id,
    )
    _audit(db, request, access, ds, "create")
    db.commit()
    jobs.dispatch(job.id)
    return {"data_source": data_source_out(ds), "job": jobs.job_out(job)}


@router.post("/projects/{project_id}/cloud/databases/connect", status_code=201)
def connect_database(body: CloudDatabaseConnect, request: Request, access: Admin, db: DbSession) -> dict:
    name = _name(db, access.project.id, body.name)
    ds = cloud_db.connect(
        db,
        access.project.id,
        connection_id=body.connection_id,
        name=name,
        resource_id=body.resource_id,
        username=body.username,
        password=body.password,
        database=body.database,
    )
    _audit(db, request, access, ds, "connect")
    db.commit()
    return data_source_out(ds)
