"""Cloud connections (instance owner) and the hosting targets apps can use (docs/CLOUD.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.deps import DbSession, InstanceOwner, ProjectAccess, require_role
from app.errors import ApiError
from app.models import CloudConnection, Project
from app.services import audit, cloud, cloud_db, dynamo, firestore, jobs
from app.services.sources import data_source_out, get_source

router = APIRouter(tags=["cloud"])

Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]
Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]

BACKUP_COST = (
    "An on-demand backup is a full copy of the table kept by AWS until you delete it (in the AWS console, "
    "DynamoDB -> Backups), billed at about US$0.10 per GB per month. Making one does not slow the table down."
)
BACKUP_RESTORE = (
    "To restore, open the backup in the AWS console (DynamoDB -> Backups -> Restore): AWS creates a new table "
    "from it, which you can then connect here with Add database -> In your AWS account."
)


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


class TableKey(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: Literal["S", "N", "B"] = "S"  # text, number, binary


class CloudDatabaseCreate(BaseModel):
    connection_id: str = Field(max_length=36)
    name: str = Field(min_length=1, max_length=63)
    engine: Literal["mysql", "mariadb", "postgresql", "dynamodb"]
    instance_class: str = Field(default=cloud_db.DEFAULT_CLASS, max_length=40)
    # DynamoDB only (docs/CLOUD.md "C2-2"): the table's key; default a text `id`.
    partition_key: TableKey | None = None
    sort_key: TableKey | None = None
    # Billable: the caller must say they accept the AWS charges (the dashboard asks with the cost note).
    confirm_billing: bool = False


class CloudDatabaseConnect(BaseModel):
    connection_id: str = Field(max_length=36)
    name: str = Field(min_length=1, max_length=63)
    # RDS / Aurora: the instance or cluster and the database login.
    resource_id: str | None = Field(default=None, max_length=63)
    username: str = Field(default="", max_length=128)
    password: str = Field(default="", max_length=500)
    # RDS: the database name; Firestore (a Firebase connection, docs/CLOUD.md "C2-3"): the database id,
    # default "(default)".
    database: str | None = Field(default=None, max_length=128)
    # DynamoDB: the tables (from the connection's listing); set instead of resource_id.
    tables: list[str] | None = Field(default=None, max_length=100)


class CloudBackupCreate(BaseModel):
    table: str | None = Field(default=None, max_length=255)  # None: every table of the database
    confirm_billing: bool = False


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
    """The RDS / Aurora databases and DynamoDB tables of an AWS connection's region, to connect one (and this
    PC's public IP), or the Firestore databases of a Firebase connection (`firestore`)."""
    return cloud_db.list_resources(db, access.project.id, connection_id)


@router.post("/projects/{project_id}/cloud/databases", status_code=201)
def create_database(body: CloudDatabaseCreate, request: Request, access: Admin, db: DbSession) -> dict:
    dynamodb = body.engine == "dynamodb"
    if not body.confirm_billing:
        cost = cloud_db.DYNAMODB_COST_NOTE if dynamodb else cloud_db.COST_NOTE
        raise ApiError(
            422,
            "billing_not_confirmed",
            "This creates a database AWS bills to your account. " + cost + " Send confirm_billing: true.",
            {"field": "confirm_billing"},
        )
    name = _name(db, access.project.id, body.name)
    if dynamodb:
        ds, job = cloud_db.create_table(
            db,
            access.project.id,
            connection_id=body.connection_id,
            name=name,
            partition_key=(body.partition_key or TableKey(name="id")).model_dump(),
            sort_key=body.sort_key.model_dump() if body.sort_key else None,
            user_id=access.user.id,
        )
    else:
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
    conn = db.get(CloudConnection, body.connection_id)
    if conn is not None and conn.provider == "firebase":
        ds = cloud_db.connect_firestore(
            db,
            access.project.id,
            connection_id=body.connection_id,
            name=name,
            database=body.database or firestore.DEFAULT_DATABASE,
        )
    elif body.tables is not None:
        ds = cloud_db.connect_tables(
            db, access.project.id, connection_id=body.connection_id, name=name, tables=body.tables
        )
    elif not body.resource_id or not body.username.strip():
        raise ApiError(422, "validation_error", "Pick the database and enter its user", {"field": "resource_id"})
    else:
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


# --- DynamoDB on-demand backups (docs/CLOUD.md "C2-2") --------------------------------------------


def _dynamo_source(db, access: ProjectAccess, source_id: str):
    ds = get_source(db, access.project.id, source_id)
    if ds.engine != dynamo.ENGINE:
        raise ApiError(400, "wrong_source_kind", "Cloud backups here are for DynamoDB databases")
    db.commit()
    return ds


@router.get("/projects/{project_id}/data-sources/{source_id}/cloud-backups")
def list_cloud_backups(source_id: str, access: Viewer, db: DbSession) -> dict:
    """The tables' on-demand backups in AWS, newest first (also ones made in the AWS console)."""
    ds = _dynamo_source(db, access, source_id)
    return {"backups": dynamo.list_backups(ds), "cost": BACKUP_COST, "restore": BACKUP_RESTORE}


@router.post("/projects/{project_id}/data-sources/{source_id}/cloud-backups", status_code=201)
def create_cloud_backup(
    source_id: str, body: CloudBackupCreate, request: Request, access: Admin, db: DbSession
) -> dict:
    if not body.confirm_billing:
        raise ApiError(
            422, "billing_not_confirmed", BACKUP_COST + " Send confirm_billing: true.", {"field": "confirm_billing"}
        )
    ds = _dynamo_source(db, access, source_id)
    backups = dynamo.create_backups(ds, body.table)
    audit.record(
        db,
        "data_source.cloud_backup",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        tables=[b["table"] for b in backups],
    )
    db.commit()
    return {"backups": backups}


# --- Firestore export (docs/CLOUD.md "C2-3") -------------------------------------------------------


@router.get("/projects/{project_id}/data-sources/{source_id}/firestore/export")
def export_firestore(
    source_id: str,
    request: Request,
    access: Viewer,
    db: DbSession,
    collection: Annotated[list[str] | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=firestore.EXPORT_LIMIT)] = firestore.EXPORT_LIMIT,
) -> dict:
    """The documents of the top-level collections (or the given collection paths) as one JSON object."""
    ds = get_source(db, access.project.id, source_id)
    if ds.engine != firestore.ENGINE:
        raise ApiError(400, "wrong_source_kind", "This export is for Firestore databases")
    audit.record(
        db,
        "data_source.export",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        collections=collection,
    )
    db.commit()
    return firestore.export_documents(ds, collection, limit)
