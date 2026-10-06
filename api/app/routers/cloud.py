"""Cloud connections (instance owner) and the hosting targets apps can use (docs/CLOUD.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.deps import DbSession, InstanceOwner, ProjectAccess, require_role
from app.errors import ApiError
from app.models import CloudConnection, Project
from app.services import audit, cloud, cloud_db, dynamo, firestore, firestore_admin, jobs, rtdb
from app.services.sources import data_source_out, get_source

router = APIRouter(tags=["cloud"])

Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]
Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
# docs/CLOUD.md "Deleting a cloud database over the API and MCP": also a service key (typed confirmation).
AdminOrServiceKey = Annotated[ProjectAccess, Depends(require_role("admin", service_keys=True))]

BACKUP_COST = (
    "An on-demand backup is a full copy of the table kept by AWS until you delete it (in the AWS console, "
    "DynamoDB -> Backups), billed at about US$0.10 per GB per month. Making one does not slow the table down."
)
BACKUP_RESTORE = (
    "Restoring never changes the original table: AWS copies the backup (or the table as it was at the time you "
    "pick) into a new table, which appears here as a new database. Your app keeps using the original until you "
    "point it at the new one."
)
PITR_COST = (
    "Point-in-time recovery keeps a continuous backup, so you can restore the table as it was at any second of "
    "the last 35 days. While it is on, AWS bills about US$0.20 per GB of table size per month (US regions). "
    "Turning it off deletes that history."
)
RESTORE_COST = (
    "Restoring creates a new table in your AWS account: AWS charges about US$0.15 per GB restored, then the new "
    "table is billed like any on-demand table (storage about US$0.25 per GB per month, plus reads and writes) "
    "until you remove it here, which keeps a final backup."
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
    """The least-privilege IAM policies for the AWS user, the Google roles and APIs for the service account."""
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
    engine: Literal["mysql", "mariadb", "postgresql", "dynamodb", "firebase_rtdb", "firestore"]
    instance_class: str = Field(default=cloud_db.DEFAULT_CLASS, max_length=40)
    # A Firebase connection: where the Realtime Database (default us-central1, docs/CLOUD.md "C2-4") or the new
    # Firestore database (default nam5, "Firestore backups") goes.
    location: str | None = Field(default=None, max_length=40)
    # Firestore only: the new database's id (default deployer-<name>-<id8>).
    database: str | None = Field(default=None, max_length=63)
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
    # Realtime Database (a Firebase connection, docs/CLOUD.md "C2-4"): the instance id from the listing.
    instance: str | None = Field(default=None, max_length=100)


class CloudBackupCreate(BaseModel):
    table: str | None = Field(default=None, max_length=255)  # None: every table of the database
    confirm_billing: bool = False


class PitrUpdate(BaseModel):
    table: str = Field(min_length=1, max_length=255)
    enabled: bool
    confirm_billing: bool = False  # needed to switch it on (billed), not off


class CloudRestore(BaseModel):
    name: str = Field(min_length=1, max_length=63)  # the new data source
    # Either an on-demand backup of one of the source's tables...
    backup_arn: str | None = Field(default=None, max_length=1024)
    # ...or a table with point-in-time recovery on, at a time in its window (or its latest restorable time).
    table: str | None = Field(default=None, max_length=255)
    point_in_time: datetime | None = None
    latest: bool = False
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
        intro, cost = (
            ("This creates a Realtime Database in your Firebase project.", cloud_db.RTDB_COST_NOTE)
            if body.engine == rtdb.ENGINE
            else ("This creates a Firestore database in your Firebase project.", cloud_db.FIRESTORE_CREATE_COST)
            if body.engine == firestore.ENGINE
            else ("This creates a database AWS bills to your account.", cloud_db.DYNAMODB_COST_NOTE)
            if dynamodb
            else ("This creates a database AWS bills to your account.", cloud_db.COST_NOTE)
        )
        raise ApiError(
            422,
            "billing_not_confirmed",
            f"{intro} {cost} Send confirm_billing: true.",
            {"field": "confirm_billing"},
        )
    name = _name(db, access.project.id, body.name)
    if body.engine == rtdb.ENGINE:  # synchronous: Firebase answers with the ready database
        ds = cloud_db.create_rtdb(
            db, access.project.id, connection_id=body.connection_id, name=name, location=body.location or "us-central1"
        )
        _audit(db, request, access, ds, "create")
        db.commit()
        return {"data_source": data_source_out(ds), "job": None}
    if body.engine == firestore.ENGINE:
        ds, job = cloud_db.create_firestore(
            db,
            access.project.id,
            connection_id=body.connection_id,
            name=name,
            database=body.database,
            location=body.location or "nam5",
            user_id=access.user.id,
        )
    elif dynamodb:
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
    if conn is not None and conn.provider == "firebase" and body.instance:
        ds = cloud_db.connect_rtdb(
            db, access.project.id, connection_id=body.connection_id, name=name, instance=body.instance
        )
    elif conn is not None and conn.provider == "firebase":
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


@router.delete("/projects/{project_id}/cloud/databases/{source_id}")
def delete_database(
    source_id: str,
    request: Request,
    access: AdminOrServiceKey,
    db: DbSession,
    confirm_name: Annotated[str, Query(max_length=63)] = "",
    confirm_delete: bool = False,
) -> dict:
    """Deletes a cloud database like the dashboard does (a created one after its final snapshot / backup, a
    connected one is only forgotten), for an admin's session or a service key; both confirmations needed."""
    from app.routers.data_sources import delete_data_source

    ds = get_source(db, access.project.id, source_id)
    if not ds.cloud_connection_id and not ds.cloud_state:
        raise ApiError(
            400, "not_a_cloud_database", "This database is not in a cloud account; remove it in the dashboard"
        )
    summary = cloud_db.delete_summary(ds)
    _confirm_delete(ds, confirm_name, confirm_delete, summary)
    return {**delete_data_source(source_id, access, db, request), **summary}


def _confirm_delete(ds, confirm_name: str, confirm_delete: bool, summary: dict) -> None:
    """Without the database's exact name and confirm_delete the answer is the dry run (`details`)."""
    if confirm_name != ds.name or not confirm_delete:
        raise ApiError(
            422,
            "delete_not_confirmed",
            f"Deleting '{ds.name}' removes what details.removes lists; {summary['keeps']} Ask the user, then send "
            "confirm_name (the database's exact name) and confirm_delete: true.",
            summary,
        )


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
    return {
        "backups": dynamo.list_backups(ds),
        "pitr": dynamo.pitr_status(ds),
        "cost": BACKUP_COST,
        "pitr_cost": PITR_COST,
        "restore": BACKUP_RESTORE,
        "restore_cost": RESTORE_COST,
    }


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


@router.put("/projects/{project_id}/data-sources/{source_id}/cloud-backups/pitr")
def set_point_in_time_recovery(
    source_id: str, body: PitrUpdate, request: Request, access: Admin, db: DbSession
) -> dict:
    """Point-in-time recovery of one table on (billed: confirm_billing) or off (its restore window is lost)."""
    if body.enabled and not body.confirm_billing:
        raise ApiError(
            422, "billing_not_confirmed", PITR_COST + " Send confirm_billing: true.", {"field": "confirm_billing"}
        )
    ds = _dynamo_source(db, access, source_id)
    pitr = dynamo.set_pitr(ds, body.table, body.enabled)
    audit.record(
        db,
        "data_source.cloud_pitr",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        table=body.table,
        enabled=body.enabled,
    )
    db.commit()
    return pitr


@router.post("/projects/{project_id}/data-sources/{source_id}/cloud-backups/restore", status_code=201)
def restore_cloud_backup(source_id: str, body: CloudRestore, request: Request, access: Admin, db: DbSession) -> dict:
    """Restores an on-demand backup, or a table at a point in time, into a NEW table that becomes a new data
    source (job `data_source.cloud_restore`); the original table is never touched."""
    if not body.confirm_billing:
        raise ApiError(
            422, "billing_not_confirmed", RESTORE_COST + " Send confirm_billing: true.", {"field": "confirm_billing"}
        )
    if bool(body.backup_arn) == bool(body.table) or (body.table and (body.point_in_time is None) == (not body.latest)):
        raise ApiError(
            422,
            "validation_error",
            "Send backup_arn, or table with point_in_time or latest: true",
            {"field": "backup_arn"},
        )
    ds = _dynamo_source(db, access, source_id)
    name = _name(db, access.project.id, body.name)
    spec = dynamo.restore_spec(
        ds, backup_arn=body.backup_arn, table=body.table, point_in_time=body.point_in_time, latest=body.latest
    )
    new, job = cloud_db.restore_table(db, access.project.id, ds, name=name, spec=spec, user_id=access.user.id)
    _audit(db, request, access, new, "restore")
    db.commit()
    jobs.dispatch(job.id)
    return {"data_source": data_source_out(new), "job": jobs.job_out(job)}


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


# --- Firestore managed exports, scheduled backups, restores (docs/CLOUD.md "Firestore backups") --------------


class FirestoreExport(BaseModel):
    bucket: str | None = Field(default=None, max_length=222)  # a bucket the user made, or:
    create_bucket: bool = False  # deployer-<project>-firestore, made on request
    collections: list[str] | None = Field(default=None, max_length=100)  # collection ids; none = all
    confirm_billing: bool = False


class FirestoreImport(BaseModel):
    input_uri: str = Field(max_length=1100)  # gs://<bucket>/<export folder>
    name: str = Field(min_length=1, max_length=63)  # the new data source
    database: str | None = Field(default=None, max_length=63)  # the new database's id
    location: str | None = Field(default=None, max_length=40)  # default: this database's location
    collections: list[str] | None = Field(default=None, max_length=100)
    confirm_billing: bool = False


class FirestoreSchedule(BaseModel):
    recurrence: Literal["daily", "weekly"]
    day: str | None = Field(default=None, max_length=10)  # weekly: MONDAY .. SUNDAY
    retention_days: int = Field(ge=1, le=firestore_admin.MAX_RETENTION_DAYS["weekly"])
    confirm_billing: bool = False


class FirestorePitr(BaseModel):
    enabled: bool
    confirm_billing: bool = False  # needed to switch it on (billed), not off


class FirestoreClone(BaseModel):
    point_in_time: datetime  # rounded down to the minute; UTC when no zone is given
    name: str = Field(min_length=1, max_length=63)  # the new data source
    database: str | None = Field(default=None, max_length=63)  # the new database's id
    confirm_billing: bool = False


class FirestoreRestore(BaseModel):
    backup: str = Field(max_length=300)  # a backup's `name` from the list
    name: str = Field(min_length=1, max_length=63)  # the new data source
    database: str | None = Field(default=None, max_length=63)  # the new database's id
    confirm_billing: bool = False


def _firestore_source(db, access: ProjectAccess, source_id: str):
    ds = get_source(db, access.project.id, source_id)
    if ds.engine != firestore.ENGINE:
        raise ApiError(400, "wrong_source_kind", "This is for Firestore databases")
    return ds


def _billing(confirmed: bool, cost: str) -> None:
    if not confirmed:
        raise ApiError(
            422, "billing_not_confirmed", cost + " Send confirm_billing: true.", {"field": "confirm_billing"}
        )


def _record(db, request: Request, access: ProjectAccess, ds, action: str, **details) -> None:
    audit.record(
        db,
        action,
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        **details,
    )


@router.get("/projects/{project_id}/data-sources/{source_id}/firestore/backups")
def firestore_backups(source_id: str, access: Viewer, db: DbSession) -> dict:
    """Backup schedules, backups and recent managed exports / imports of a Firestore database."""
    ds = _firestore_source(db, access, source_id)
    db.commit()
    return firestore_admin.overview(ds)


@router.post("/projects/{project_id}/data-sources/{source_id}/firestore/exports", status_code=201)
def firestore_managed_export(
    source_id: str, body: FirestoreExport, request: Request, access: Admin, db: DbSession
) -> dict:
    _billing(body.confirm_billing, firestore_admin.EXPORT_COST)
    ds = _firestore_source(db, access, source_id)
    out = firestore_admin.export(ds, bucket=body.bucket, create_bucket=body.create_bucket, collections=body.collections)
    ds.cloud_state = {**(ds.cloud_state or {}), "export_bucket": out["bucket"]}
    _record(db, request, access, ds, "data_source.cloud_export", output_uri=out["output_uri"])
    db.commit()
    return out


@router.post("/projects/{project_id}/data-sources/{source_id}/firestore/import", status_code=201)
def firestore_import(source_id: str, body: FirestoreImport, request: Request, access: Admin, db: DbSession) -> dict:
    """Loads a managed export into a NEW Firestore database, added as a new data source (never over existing data)."""
    _billing(body.confirm_billing, firestore_admin.IMPORT_COST)
    src = _firestore_source(db, access, source_id)
    uri = firestore_admin.check_input_uri(body.input_uri)
    ds, job = cloud_db.create_firestore(
        db,
        access.project.id,
        connection_id=src.cloud_connection_id or "",
        name=_name(db, access.project.id, body.name),
        database=body.database,
        location=body.location or (src.cloud_state or {}).get("location") or "",
        user_id=access.user.id,
        import_from=uri,
        collections=firestore_admin.collection_ids(body.collections),
    )
    _audit(db, request, access, ds, "import")
    db.commit()
    jobs.dispatch(job.id)
    return {"data_source": data_source_out(ds), "job": jobs.job_out(job)}


@router.post("/projects/{project_id}/data-sources/{source_id}/firestore/backup-schedules", status_code=201)
def firestore_create_schedule(
    source_id: str, body: FirestoreSchedule, request: Request, access: Admin, db: DbSession
) -> dict:
    _billing(body.confirm_billing, firestore_admin.SCHEDULE_COST)
    ds = _firestore_source(db, access, source_id)
    schedule = firestore_admin.create_schedule(ds, body.recurrence, body.day, body.retention_days)
    _record(db, request, access, ds, "data_source.cloud_backup_schedule", schedule=schedule)
    db.commit()
    return schedule


@router.delete("/projects/{project_id}/data-sources/{source_id}/firestore/backup-schedules/{schedule_id}")
def firestore_delete_schedule(source_id: str, schedule_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    """Stops future backups; the ones already taken stay until they expire."""
    ds = _firestore_source(db, access, source_id)
    firestore_admin.delete_schedule(ds, schedule_id)
    _record(db, request, access, ds, "data_source.cloud_backup_schedule_delete", schedule_id=schedule_id)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/data-sources/{source_id}/firestore/restore", status_code=201)
def firestore_restore(source_id: str, body: FirestoreRestore, request: Request, access: Admin, db: DbSession) -> dict:
    """Restores one of the database's backups into a NEW Firestore database, added as a new data source."""
    _billing(body.confirm_billing, firestore_admin.RESTORE_COST)
    src = _firestore_source(db, access, source_id)
    ds, job = cloud_db.create_firestore(
        db,
        access.project.id,
        connection_id=src.cloud_connection_id or "",
        name=_name(db, access.project.id, body.name),
        database=body.database,
        location=firestore_admin.restore_location(src, body.backup),
        user_id=access.user.id,
        restore_from=body.backup,
    )
    _audit(db, request, access, ds, "restore")
    db.commit()
    jobs.dispatch(job.id)
    return {"data_source": data_source_out(ds), "job": jobs.job_out(job)}


# --- Firestore point-in-time recovery and deletes (docs/CLOUD.md "Firestore point-in-time recovery and deletes") --

ConfirmName = Annotated[str, Query(max_length=63)]


@router.put("/projects/{project_id}/data-sources/{source_id}/firestore/pitr")
def firestore_set_pitr(source_id: str, body: FirestorePitr, request: Request, access: Admin, db: DbSession) -> dict:
    """Point-in-time recovery on (billed: confirm_billing) or off (the versions older than an hour go)."""
    if body.enabled:
        _billing(body.confirm_billing, firestore_admin.PITR_COST)
    ds = _firestore_source(db, access, source_id)
    out = firestore_admin.set_pitr(ds, body.enabled)
    _record(db, request, access, ds, "data_source.cloud_pitr", enabled=body.enabled)
    db.commit()
    return out


@router.post("/projects/{project_id}/data-sources/{source_id}/firestore/clone", status_code=201)
def firestore_clone(source_id: str, body: FirestoreClone, request: Request, access: Admin, db: DbSession) -> dict:
    """Copies the database as it was at a minute of its version window into a NEW database and data source."""
    _billing(body.confirm_billing, firestore_admin.CLONE_COST)
    src = _firestore_source(db, access, source_id)
    name = _name(db, access.project.id, body.name)
    spec, location = firestore_admin.clone_spec(src, body.point_in_time)
    ds, job = cloud_db.create_firestore(
        db,
        access.project.id,
        connection_id=src.cloud_connection_id or "",
        name=name,
        database=body.database,
        location=location,
        user_id=access.user.id,
        clone_from=spec,
    )
    _audit(db, request, access, ds, "clone")
    db.commit()
    jobs.dispatch(job.id)
    return {"data_source": data_source_out(ds), "job": jobs.job_out(job)}


@router.delete("/projects/{project_id}/data-sources/{source_id}/firestore/database")
def firestore_delete_database(
    source_id: str,
    request: Request,
    access: Admin,
    db: DbSession,
    confirm_name: ConfirmName = "",
    confirm_delete: bool = False,
) -> dict:
    """Deletes the Firestore database in Google (not while its delete protection is on) and then the data source.
    Admins only: unlike delete_cloud_database nothing is kept, so service keys don't get it."""
    from app.routers.data_sources import delete_data_source

    ds = _firestore_source(db, access, source_id)
    summary = firestore_admin.database_delete_summary(ds)
    _confirm_delete(ds, confirm_name, confirm_delete, summary)
    firestore_admin.delete_database(ds)
    _record(db, request, access, ds, "data_source.cloud_database_delete", database=firestore.database_of(ds))
    return {**delete_data_source(source_id, access, db, request), **summary}


@router.delete("/projects/{project_id}/data-sources/{source_id}/firestore/backups")
def firestore_delete_backup(
    source_id: str,
    request: Request,
    access: Admin,
    db: DbSession,
    backup: Annotated[str, Query(max_length=300)],
    confirm_name: ConfirmName = "",
    confirm_delete: bool = False,
) -> dict:
    ds = _firestore_source(db, access, source_id)
    summary = firestore_admin.backup_delete_summary(ds, backup)
    _confirm_delete(ds, confirm_name, confirm_delete, summary)
    firestore_admin.delete_backup(ds, backup)
    _record(db, request, access, ds, "data_source.cloud_backup_delete", backup=backup)
    db.commit()
    return {"ok": True, **summary}


@router.delete("/projects/{project_id}/data-sources/{source_id}/firestore/exports")
def firestore_delete_export(
    source_id: str,
    request: Request,
    access: Admin,
    db: DbSession,
    uri: Annotated[str, Query(max_length=1100)],
    confirm_name: ConfirmName = "",
    confirm_delete: bool = False,
) -> dict:
    """Deletes the files of one export Deployer made of this database in a deployer-* bucket."""
    ds = _firestore_source(db, access, source_id)
    summary = firestore_admin.export_delete_summary(ds, uri)
    _confirm_delete(ds, confirm_name, confirm_delete, summary)
    files = firestore_admin.delete_export(ds, uri)
    _record(db, request, access, ds, "data_source.cloud_export_delete", uri=uri, files=files)
    db.commit()
    return {"ok": True, "files": files, **summary}


# --- Realtime Database export (docs/CLOUD.md "C2-4") -----------------------------------------------


@router.get("/projects/{project_id}/data-sources/{source_id}/rtdb-export")
def export_rtdb(
    source_id: str,
    request: Request,
    access: Viewer,
    db: DbSession,
    path: Annotated[str, Query(max_length=4096)] = "",
) -> dict:
    """The JSON at `path` (default the whole database) as one object."""
    ds = get_source(db, access.project.id, source_id)
    if ds.engine != rtdb.ENGINE:
        raise ApiError(400, "wrong_source_kind", "This export is for Realtime Databases")
    audit.record(
        db,
        "data_source.export",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        path=path,
    )
    db.commit()
    return rtdb.export(ds, path)
