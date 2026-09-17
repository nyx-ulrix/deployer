"""Backups, versions, point-in-time recovery, recently deleted sources and instance backup health
(docs/BACKUPS.md "API")."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DbSession, InstanceOwner, ProjectAccess, require_role
from app.errors import ApiError, forbidden
from app.models import Backup
from app.serializers import iso
from app.services import audit, backups, executors, jobs
from app.services.backup_crypto import BackupCryptoError, iter_decrypt
from app.services.sources import data_source_out, get_source

router = APIRouter(tags=["backups"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]
Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]
Owner = Annotated[ProjectAccess, Depends(require_role("owner"))]

BASE = "/projects/{project_id}/data-sources/{source_id}"


def _supported_source(db: DbSession, access: ProjectAccess, source_id: str):
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    backups.require_supported(ds)
    return ds


# ---------------------------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------------------------


class PolicyPatch(BaseModel):
    enabled: bool | None = None
    schedule: Literal["hourly", "every_6h", "daily"] | None = None
    keep_hourly: int | None = Field(default=None, ge=0, le=backups.MAX_KEEP)
    keep_daily: int | None = Field(default=None, ge=0, le=backups.MAX_KEEP)
    keep_weekly: int | None = Field(default=None, ge=0, le=backups.MAX_KEEP)
    keep_monthly: int | None = Field(default=None, ge=0, le=backups.MAX_KEEP)
    pitr_enabled: bool | None = None
    pitr_window_days: int | None = Field(default=None, ge=1, le=35)
    copy_to_primary: bool | None = None
    copy_to_device_id: str | None = None
    safety_snapshots: bool | None = None


@router.get(BASE + "/backup-policy")
def get_policy(source_id: str, access: Viewer, db: DbSession) -> dict:
    ds = _supported_source(db, access, source_id)
    policy = backups.ensure_policy(db, ds)
    db.commit()
    return backups.policy_out(policy)


@router.put(BASE + "/backup-policy")
def put_policy(source_id: str, body: PolicyPatch, access: Admin, db: DbSession, request: Request) -> dict:
    ds = _supported_source(db, access, source_id)
    policy = backups.ensure_policy(db, ds)
    patch: dict[str, Any] = {}
    for key in body.model_fields_set:
        value = getattr(body, key)
        if value is None and key != "copy_to_device_id":
            continue
        patch[key] = value
    backups.update_policy(db, ds, policy, patch)
    audit.record(
        db,
        "backup.policy_update",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        changes=sorted(patch),
    )
    db.commit()
    return backups.policy_out(policy)


# ---------------------------------------------------------------------------------------------
# versions
# ---------------------------------------------------------------------------------------------


@router.get(BASE + "/backups")
def list_backups(
    source_id: str, access: Viewer, db: DbSession, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[dict]:
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    rows = list(
        db.scalars(
            select(Backup)
            .where(Backup.data_source_id == ds.id, Backup.scope == "source")
            .order_by(Backup.started_at.desc())
            .limit(limit)
        )
    )
    return backups.backups_out(db, rows)


class SnapshotInput(BaseModel):
    label: str | None = Field(default=None, max_length=120)


@router.post(BASE + "/backups")
def create_backup(
    source_id: str, access: Developer, db: DbSession, request: Request, body: SnapshotInput | None = None
) -> dict:
    ds = _supported_source(db, access, source_id)
    if ds.deleted_at is not None:
        raise ApiError(409, "source_deleted", "This data source is deleted")
    label = ((body.label if body else None) or "").strip() or None
    backups.ensure_policy(db, ds)
    job, backup = backups.start_snapshot(db, ds, trigger="manual", label=label, user_id=access.user.id)
    audit.record(
        db,
        "backup.create",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        backup_id=backup.id,
    )
    db.commit()
    jobs.dispatch(job.id)
    return {"job": jobs.job_out(job), "backup_id": backup.id}


class BackupPatch(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None


@router.patch(BASE + "/backups/{backup_id}")
def update_backup(
    source_id: str, backup_id: str, body: BackupPatch, access: Developer, db: DbSession, request: Request
) -> dict:
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    backup = backups.get_backup(db, ds, backup_id)
    fields = body.model_fields_set
    if "label" in fields:
        backup.label = (body.label or "").strip() or None
        if backup.label and "pinned" not in fields:
            backup.pinned = True
    if "pinned" in fields and body.pinned is not None:
        backup.pinned = body.pinned
    audit.record(
        db,
        "backup.update",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        backup_id=backup.id,
        pinned=backup.pinned,
    )
    db.commit()
    return backups.backups_out(db, [backup])[0]


@router.delete(BASE + "/backups/{backup_id}")
def delete_backup(source_id: str, backup_id: str, access: Admin, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    backup = backups.get_backup(db, ds, backup_id)
    if backup.pinned:
        raise ApiError(409, "backup_pinned", "Unpin this version before deleting it")
    if backup.status == "running":
        raise ApiError(409, "backup_running", "This backup is still running")
    backups.delete_backup(db, backup)
    audit.record(
        db,
        "backup.delete",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        backup_id=backup_id,
    )
    db.commit()
    return {"ok": True}


@router.get(BASE + "/backups/diff")
def diff_backups(
    source_id: str,
    access: Viewer,
    db: DbSession,
    from_: Annotated[str, Query(alias="from")],
    to: str = "current",
) -> dict:
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    backups.require_supported(ds)
    db.commit()
    return backups.diff(db, ds, from_, to)


@router.get(BASE + "/backups/{backup_id}/schema")
def backup_schema(source_id: str, backup_id: str, access: Viewer, db: DbSession) -> dict:
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    schema, _, _ = backups.schema_at(db, ds, backup_id)
    if schema is None:
        raise ApiError(409, "schema_unavailable", "No schema was recorded for this version")
    return schema


def _download_name(name: str, backup: Backup) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "backup"
    stamp = backup.started_at.strftime("%Y%m%d-%H%M%S")
    ext = "sql.gz" if backup.engine == "mariadb" else "mongodump.archive.gz"
    return f"{base}-{stamp}.{ext}"


@router.get(BASE + "/backups/{backup_id}/download")
def download_backup(source_id: str, backup_id: str, access: Viewer, db: DbSession, request: Request):
    if not access.at_least("owner"):
        raise forbidden("Only the project owner can download backups")
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    backup = backups.get_backup(db, ds, backup_id)
    if backup.status != "succeeded":
        raise ApiError(409, "backup_not_ready", "This backup did not succeed")
    copy = backups.local_copy(db, "backup", backup.id, None) or backups.any_copy(db, "backup", backup.id, None)
    if copy is None:
        raise ApiError(409, "artifact_missing", "No stored copy of this backup is available")
    try:
        stream = executors.executor_for(copy.device_id).open_artifact(copy.ref)
    except (OSError, NotImplementedError, executors.DeviceExecutorUnavailable) as exc:
        raise ApiError(409, "artifact_unavailable", f"The backup file can't be read right now: {exc}") from exc
    filename = _download_name(ds.deleted_name or ds.name, backup)
    audit.record(
        db,
        "backup.download",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        backup_id=backup.id,
    )
    db.commit()

    def body() -> Iterator[bytes]:
        try:
            yield from iter_decrypt(stream)
        except BackupCryptoError:
            # Headers are already sent; a truncated download fails the client's gzip check.
            return
        finally:
            stream.close()

    return StreamingResponse(
        body(),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------------------------
# recovery
# ---------------------------------------------------------------------------------------------


@router.get(BASE + "/recovery-window")
def recovery_window(source_id: str, access: Viewer, db: DbSession) -> dict:
    ds = _supported_source(db, access, source_id)
    window = backups.recovery_window(db, ds)
    db.commit()
    return window


class RestoreInput(BaseModel):
    backup_id: str | None = None
    point_in_time: str | None = None
    mode: Literal["new_source", "in_place"] = "new_source"
    new_name: str | None = Field(default=None, max_length=63)
    device_id: str | None = None


@router.post(BASE + "/restore")
def restore(source_id: str, body: RestoreInput, access: Admin, db: DbSession, request: Request) -> dict:
    ds = _supported_source(db, access, source_id)
    job = backups.start_restore(
        db,
        ds,
        user_id=access.user.id,
        role_is_owner=access.at_least("owner"),
        mode=body.mode,
        backup_id=body.backup_id,
        point_in_time=body.point_in_time,
        new_name=body.new_name,
        device_id=body.device_id,
        device_id_set="device_id" in body.model_fields_set,
    )
    audit.record(
        db,
        "backup.restore",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        mode=body.mode,
        backup_id=body.backup_id,
        point_in_time=body.point_in_time,
        job_id=job.id,
    )
    db.commit()
    jobs.dispatch(job.id)
    return {"job": jobs.job_out(job)}


# ---------------------------------------------------------------------------------------------
# recently deleted
# ---------------------------------------------------------------------------------------------


@router.get("/projects/{project_id}/deleted-sources")
def list_deleted_sources(access: Admin, db: DbSession) -> list[dict]:
    out = []
    for ds in backups.deleted_sources(db, access.project.id):
        item = data_source_out(ds)
        item["name"] = ds.deleted_name or ds.name
        item["deleted_at"] = iso(ds.deleted_at)
        item["purge_at"] = iso(ds.deleted_at + backups.DELETED_KEEP) if ds.deleted_at else None
        out.append(item)
    return out


class UndeleteInput(BaseModel):
    name: str | None = Field(default=None, max_length=63)


@router.post("/projects/{project_id}/deleted-sources/{source_id}/restore")
def restore_deleted_source(
    source_id: str, access: Admin, db: DbSession, request: Request, body: UndeleteInput | None = None
) -> dict:
    ds = get_source(db, access.project.id, source_id, include_deleted=True)
    job = backups.start_undelete(db, ds, name=body.name if body else None, user_id=access.user.id)
    audit.record(
        db,
        "data_source.undelete",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        job_id=job.id,
    )
    db.commit()
    jobs.dispatch(job.id)
    return {"job": jobs.job_out(job)}


# ---------------------------------------------------------------------------------------------
# instance
# ---------------------------------------------------------------------------------------------


@router.get("/instance/backups")
def instance_backups(_: InstanceOwner, db: DbSession) -> dict:
    return backups.instance_health(db)


@router.post("/instance/backups/platform")
def platform_snapshot(user: InstanceOwner, db: DbSession, request: Request) -> dict:
    if jobs.active_job(db, "backup.platform_snapshot"):
        raise ApiError(409, "snapshot_in_progress", "A platform snapshot is already running")
    job = backups.start_platform_snapshot(db, user.id)
    audit.record(db, "instance.platform_snapshot", request=request, user_id=user.id, job_id=job.id)
    db.commit()
    jobs.dispatch(job.id)
    return {"job": jobs.job_out(job)}
