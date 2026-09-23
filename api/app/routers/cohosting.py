"""Co-hosting (docs/COHOSTING.md): live database copies on members' host devices, sync conflicts and
per-key history."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, forbidden, not_found, validation_error
from app.models import DataSource, Device, ProjectMember, SourceReplica, SyncConflict, SyncVersion
from app.services import audit, cohosting, device_rpc, devices, jobs, source_sync
from app.services.sources import get_source

router = APIRouter(tags=["cohosting"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]


@router.get("/projects/{project_id}/cohosting/eligibility")
def cohosting_eligibility(access: Viewer, db: DbSession) -> dict:
    return cohosting.eligibility(db, access.project, access.user)


def _replica(db, ds: DataSource, replica_id: str) -> SourceReplica:
    rep = db.get(SourceReplica, replica_id)
    if rep is None or rep.data_source_id != ds.id:
        raise not_found("Copy")
    return rep


def _require_owner_or_admin(db, access: ProjectAccess, rep: SourceReplica) -> None:
    """The co-host who owns the copy's device, or a project admin."""
    if access.at_least("admin"):
        return
    device = db.get(Device, rep.device_id)
    if device is None or device.owner_id != access.user.id or not access.at_least("developer"):
        raise forbidden("Only the co-host who owns this copy or a project admin can do that")


# --- replicas ---------------------------------------------------------------------------------------


class ReplicaCreate(BaseModel):
    device_id: str


@router.post("/projects/{project_id}/data-sources/{source_id}/replicas")
def create_replica(source_id: str, body: ReplicaCreate, request: Request, access: Developer, db: DbSession) -> dict:
    ds = get_source(db, access.project.id, source_id)
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == access.project.id, ProjectMember.user_id == access.user.id
        )
    )
    if not cohosting.member_can_cohost(member):
        raise forbidden("A project admin must allow you to co-host this project first")
    if ds.mode != "managed" or ds.device_id is not None:
        raise ApiError(
            409, "replica_unsupported", "Only managed databases on the main server can be copied to a device"
        )
    device = db.get(Device, body.device_id)
    if device is None or device.owner_id != access.user.id:
        raise not_found("Device")
    problem = devices.placement_problem(db, device, access.project)
    if problem:
        raise ApiError(422, "device_not_eligible", problem)
    if ds.kind == "nosql" and not devices.engines_of(device)["mongodb"]:
        raise ApiError(409, "managed_mongodb_unavailable", f"Managed MongoDB is not available on '{device.name}'")
    methods = (device.capabilities or {}).get("methods")
    if isinstance(methods, list) and not set(cohosting.SYNC_METHODS) <= set(methods):
        raise ApiError(409, "device_outdated", f"Update Deployer on '{device.name}' to use co-hosting")
    if not device_rpc.is_online(device.id):
        raise device_rpc.offline_error()
    if db.scalar(
        select(SourceReplica.id).where(SourceReplica.data_source_id == ds.id, SourceReplica.device_id == device.id)
    ):
        raise ApiError(409, "replica_exists", "This database already has a copy on that device")
    other_device = db.scalar(
        select(SourceReplica.id)
        .join(DataSource, DataSource.id == SourceReplica.data_source_id)
        .join(Device, Device.id == SourceReplica.device_id)
        .where(
            DataSource.project_id == access.project.id,
            Device.owner_id == access.user.id,
            SourceReplica.device_id != device.id,
        )
    )
    if other_device:
        raise ApiError(409, "one_device_per_member", "You already co-host this project on another device")
    rep = SourceReplica(data_source_id=ds.id, device_id=device.id, status="copying", created_by_id=access.user.id)
    db.add(rep)
    db.flush()
    job = jobs.enqueue(
        db,
        type=cohosting.COPY_JOB,
        params={"replica_id": rep.id},
        project_id=access.project.id,
        data_source_id=ds.id,
        device_id=device.id,
        created_by_id=access.user.id,
    )
    audit.record(
        db,
        "replica.create",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        device_id=device.id,
        replica_id=rep.id,
    )
    db.commit()
    jobs.dispatch(job.id)
    return {"replica": cohosting.replica_out(db, rep, open_conflicts=0), "job": jobs.job_out(job)}


@router.get("/projects/{project_id}/data-sources/{source_id}/replicas")
def list_replicas(source_id: str, access: Viewer, db: DbSession) -> list[dict]:
    ds = get_source(db, access.project.id, source_id)
    return cohosting.source_replicas(db, ds.id)


@router.post("/projects/{project_id}/data-sources/{source_id}/replicas/{replica_id}/{action}")
def replica_action(
    source_id: str,
    replica_id: str,
    action: Literal["pause", "resume", "recopy"],
    request: Request,
    access: Viewer,
    db: DbSession,
) -> dict:
    ds = get_source(db, access.project.id, source_id)
    rep = _replica(db, ds, replica_id)
    _require_owner_or_admin(db, access, rep)
    job = None
    if action != "pause":
        device = db.get(Device, rep.device_id)
        member = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == access.project.id, ProjectMember.user_id == device.owner_id
            )
        )
        if not cohosting.member_can_cohost(member):
            raise forbidden("The device owner is not allowed to co-host this project")
    if action == "pause":
        if rep.status == "copying":
            raise ApiError(409, "replica_copying", "Wait until the copy has finished")
        rep.status = "paused"
    elif action == "resume":
        if rep.status != "paused":
            raise ApiError(409, "replica_not_paused", "This copy is not paused")
        rep.status = "syncing" if rep.position_primary is not None else "error"
        rep.error = None if rep.position_primary is not None else "Re-copy needed"
    else:
        if rep.status == "copying":
            raise ApiError(409, "replica_copying", "A copy is already running")
        if not device_rpc.is_online(rep.device_id):
            raise device_rpc.offline_error()
        rep.status = "copying"
        job = jobs.enqueue(
            db,
            type=cohosting.COPY_JOB,
            params={"replica_id": rep.id, "recopy": True},
            project_id=access.project.id,
            data_source_id=ds.id,
            device_id=rep.device_id,
            created_by_id=access.user.id,
        )
    audit.record(
        db,
        f"replica.{action}",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        replica_id=rep.id,
    )
    db.commit()
    if job is not None:
        jobs.dispatch(job.id)
    out = {"replica": cohosting.replica_out(db, rep)}
    if job is not None:
        out["job"] = jobs.job_out(job)
    return out


@router.delete("/projects/{project_id}/data-sources/{source_id}/replicas/{replica_id}")
def delete_replica(
    source_id: str, replica_id: str, request: Request, access: Viewer, db: DbSession, drop: bool = False
) -> dict:
    ds = get_source(db, access.project.id, source_id)
    rep = _replica(db, ds, replica_id)
    _require_owner_or_admin(db, access, rep)
    if drop:
        cohosting._drop_device_copy(rep.device_id, ds.kind, ds.database_name)  # 503 while offline
    audit.record(
        db,
        "replica.delete",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        replica_id=rep.id,
        device_id=rep.device_id,
        dropped=drop,
    )
    db.delete(rep)
    db.commit()
    return {"ok": True}


# --- conflicts ---------------------------------------------------------------------------------------


def _replica_ids(db, ds: DataSource) -> list[str]:
    return list(db.scalars(select(SourceReplica.id).where(SourceReplica.data_source_id == ds.id)))


@router.get("/projects/{project_id}/data-sources/{source_id}/sync-conflicts")
def list_conflicts(
    source_id: str, access: Developer, db: DbSession, status: Literal["open", "resolved"] | None = None
) -> list[dict]:
    ds = get_source(db, access.project.id, source_id)
    ids = _replica_ids(db, ds)
    if not ids:
        return []
    stmt = select(SyncConflict).where(SyncConflict.replica_id.in_(ids))
    if status:
        stmt = stmt.where(SyncConflict.status == status)
    rows = db.scalars(stmt.order_by(SyncConflict.created_at.desc()).limit(500))
    return [cohosting.conflict_out(c) for c in rows]


@router.get("/projects/{project_id}/data-sources/{source_id}/sync-conflicts/{conflict_id}")
def get_conflict(source_id: str, conflict_id: str, access: Developer, db: DbSession) -> dict:
    ds = get_source(db, access.project.id, source_id)
    return cohosting.conflict_out(cohosting.get_conflict(db, ds.id, conflict_id))


class ResolveInput(BaseModel):
    choice: Literal["primary", "replica", "manual"]
    value: dict[str, Any] | None = None


@router.post("/projects/{project_id}/data-sources/{source_id}/sync-conflicts/{conflict_id}/resolve")
def resolve_conflict(
    source_id: str, conflict_id: str, body: ResolveInput, request: Request, access: Developer, db: DbSession
) -> dict:
    ds = get_source(db, access.project.id, source_id)
    conflict = cohosting.get_conflict(db, ds.id, conflict_id)
    _require_owner_or_admin(db, access, db.get(SourceReplica, conflict.replica_id))
    cohosting.resolve(db, conflict, body.choice, body.value, access.user.id)
    audit.record(
        db,
        "sync.conflict_resolve",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        conflict_id=conflict.id,
        table=conflict.table_name,
        choice=body.choice,
    )
    db.commit()
    return cohosting.conflict_out(conflict)


# --- per-key history ----------------------------------------------------------------------------------


def _key_param(raw: str) -> dict:
    try:
        key = json.loads(raw)
    except ValueError as exc:
        raise validation_error('key must be a JSON object, e.g. {"id": 5}') from exc
    if not isinstance(key, dict) or not key:
        raise validation_error('key must be a JSON object, e.g. {"id": 5}')
    return key


@router.get("/projects/{project_id}/data-sources/{source_id}/sync-history")
def sync_history(source_id: str, table: str, key: str, access: Developer, db: DbSession) -> list[dict]:
    ds = get_source(db, access.project.id, source_id)
    return cohosting.history(db, _replica_ids(db, ds), table, _key_param(key))


class RestoreInput(BaseModel):
    table: str
    key: dict[str, Any]
    version_id: int | str


@router.post("/projects/{project_id}/data-sources/{source_id}/sync-history/restore")
def restore_history(source_id: str, body: RestoreInput, request: Request, access: Developer, db: DbSession) -> dict:
    ds = get_source(db, access.project.id, source_id)
    try:
        version = db.get(SyncVersion, int(body.version_id))
    except (TypeError, ValueError):
        version = None
    ids = _replica_ids(db, ds)
    if (
        version is None
        or version.replica_id not in ids
        or version.table_name != body.table
        or version.key_hash != source_sync.key_hash(body.key)
    ):
        raise not_found("Version")
    rep = db.get(SourceReplica, version.replica_id)
    _require_owner_or_admin(db, access, rep)
    conflict = cohosting.restore_version(db, version, access.user.id)
    audit.record(
        db,
        "sync.history_restore",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        table=version.table_name,
        version_id=version.id,
    )
    db.commit()
    return {"ok": True, "resolved_conflict_id": conflict.id if conflict else None}
