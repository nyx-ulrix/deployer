"""Backups, version history and point-in-time recovery - orchestration (docs/BACKUPS.md).

Runs on the main server only. Owns every platform row (`backups`, `backup_log_segments`,
`backup_copies`, `backup_policies`, soft-deleted `data_sources`) and delegates byte-level work to
`executors.executor_for(data_source)`, so the same flow serves databases on the main server and on
host devices.

Hooks for host devices
----------------------
- `register_copy_target(fn)`: `fn(*, artifact_type, artifact_id, ref, from_device_id, to_device_id)
  -> {ref, size_bytes, sha256}` copies an encrypted artifact between backup stores (`None` = main
  server). Used for policy copies (`copy_to_primary` / `copy_to_device_id`) and to stage artifacts on
  another host for cross-host restores. Without a hook, copies stay `pending`.

Job types (all `runs_on="primary"`): backup.snapshot, backup.archive_logs, backup.restore,
backup.verify, backup.prune, backup.platform_snapshot, backup.copy, source.finalize_delete,
source.undelete.
"""

from __future__ import annotations

import importlib
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crypto import decrypt_json
from app.errors import ApiError, not_found, validation_error
from app.models import (
    Backup,
    BackupCopy,
    BackupLogSegment,
    BackupPolicy,
    DataSource,
    Device,
    Job,
    Project,
    new_id,
    utcnow,
)
from app.redis_client import get_redis
from app.serializers import iso
from app.services import executors, jobs, schema_diff

log = logging.getLogger(__name__)

TRIGGERS = ("scheduled", "manual", "pre_restore", "pre_drop", "pre_delete", "pre_move", "final")
SAFETY_TRIGGERS = ("pre_restore", "pre_drop", "pre_delete", "pre_move")
GFS_TRIGGERS = ("scheduled", "manual")
SCHEDULES = {"hourly": timedelta(hours=1), "every_6h": timedelta(hours=6), "daily": timedelta(days=1)}
SAFETY_KEEP = timedelta(days=30)
DELETED_KEEP = timedelta(days=30)
PLATFORM_KEEP = 30
FAILED_KEEP = timedelta(days=1)
VERIFY_EVERY = timedelta(days=7)
PRUNE_EVERY = timedelta(hours=1)
PLATFORM_EVERY = timedelta(days=1)
LOG_INTERVALS = {"mariadb": timedelta(minutes=5), "mongodb": timedelta(minutes=1)}
SUPPORTED_ENGINES = ("mariadb", "mongodb")
MAX_KEEP = 1000
DELETED_NAME_PREFIX = "__deleted__"


# =============================================================================================
# helpers
# =============================================================================================


def _provisioning():
    # Looked up at call time (tests substitute the module in sys.modules).
    return importlib.import_module("app.services.provisioning")


def parse_time(value: Any) -> datetime | None:
    """ISO string / datetime -> naive UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ApiError(422, "validation_error", f"Invalid timestamp: {value!r}") from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def supported(ds: DataSource) -> bool:
    return ds.mode == "managed" and ds.engine in SUPPORTED_ENGINES


def require_supported(ds: DataSource) -> None:
    if not supported(ds):
        raise ApiError(
            400,
            "backups_not_available",
            "Backups are only taken for managed MariaDB and MongoDB databases. External databases are backed up "
            "by their provider.",
        )


def snapshot_ref(backup: Backup) -> str:
    if backup.scope == "platform" or not backup.data_source_id:
        return f"platform/snapshots/{backup.id}.bin"
    return f"{backup.data_source_id}/snapshots/{backup.id}.bin"


def logs_prefix(data_source_id: str) -> str:
    return f"{data_source_id}/logs"


def consistent_at(backup: Backup) -> datetime | None:
    cp = backup.consistent_point or {}
    return parse_time(cp.get("consistent_at")) or backup.started_at


def pitr_base_ok(backup: Backup) -> bool:
    cp = backup.consistent_point or {}
    if backup.engine == "mariadb":
        return bool(cp.get("binlog_file")) and cp.get("binlog_pos") is not None
    return cp.get("oplog_ts_start") is not None and cp.get("oplog_ts_end") is not None


# =============================================================================================
# policies
# =============================================================================================


def ensure_policy(db: Session, ds: DataSource) -> BackupPolicy:
    policy = db.get(BackupPolicy, ds.id)
    if policy is None:
        policy = BackupPolicy(
            data_source_id=ds.id,
            enabled=True,
            schedule="hourly",
            keep_hourly=24,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=12,
            pitr_enabled=True,
            pitr_window_days=7,
            copy_to_primary=False,
            copy_to_device_id=None,
            safety_snapshots=True,
        )
        db.add(policy)
        db.flush()
    return policy


def policy_out(policy: BackupPolicy) -> dict:
    return {
        "enabled": policy.enabled,
        "schedule": policy.schedule,
        "keep_hourly": policy.keep_hourly,
        "keep_daily": policy.keep_daily,
        "keep_weekly": policy.keep_weekly,
        "keep_monthly": policy.keep_monthly,
        "pitr_enabled": policy.pitr_enabled,
        "pitr_window_days": policy.pitr_window_days,
        "copy_to_primary": policy.copy_to_primary,
        "copy_to_device_id": policy.copy_to_device_id,
        "safety_snapshots": policy.safety_snapshots,
        "updated_at": iso(policy.updated_at),
    }


def update_policy(db: Session, ds: DataSource, policy: BackupPolicy, patch: dict[str, Any]) -> BackupPolicy:
    if "schedule" in patch and patch["schedule"] not in SCHEDULES:
        raise validation_error("schedule must be hourly, every_6h or daily")
    for key in ("keep_hourly", "keep_daily", "keep_weekly", "keep_monthly"):
        if key in patch:
            value = patch[key]
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_KEEP:
                raise validation_error(f"{key} must be between 0 and {MAX_KEEP}")
    if "pitr_window_days" in patch:
        value = patch["pitr_window_days"]
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 35:
            raise validation_error("pitr_window_days must be between 1 and 35")
    for key in ("enabled", "pitr_enabled", "copy_to_primary", "safety_snapshots"):
        if key in patch and not isinstance(patch[key], bool):
            raise validation_error(f"{key} must be a boolean")
    copy_primary = patch.get("copy_to_primary", policy.copy_to_primary)
    copy_device = patch.get("copy_to_device_id", policy.copy_to_device_id)
    if copy_device == "":
        copy_device = None
    if copy_primary and copy_device:
        raise validation_error("Choose at most one copy target (copy_to_primary or copy_to_device_id)")
    if copy_device:
        from app.services import devices

        device = db.get(Device, copy_device)
        if device is None:
            raise validation_error("copy_to_device_id: device not found")
        # Same sharing rules as hosting a database, for the backup_storage role (docs/DEVICES.md "Rules").
        problem = devices.placement_problem(db, device, db.get(Project, ds.project_id), role="backup_storage")
        if problem:
            raise validation_error(f"copy_to_device_id: {problem}")
        if copy_device == ds.device_id:
            raise validation_error("copy_to_device_id must be a different device than the one hosting the database")
    for key in (
        "enabled",
        "schedule",
        "keep_hourly",
        "keep_daily",
        "keep_weekly",
        "keep_monthly",
        "pitr_enabled",
        "pitr_window_days",
        "copy_to_primary",
        "safety_snapshots",
    ):
        if key in patch:
            setattr(policy, key, patch[key])
    if "copy_to_device_id" in patch:
        policy.copy_to_device_id = copy_device
    policy.updated_at = utcnow()
    return policy


# =============================================================================================
# serializers
# =============================================================================================


def copies_by_artifact(db: Session, artifact_type: str, ids: Iterable[str]) -> dict[str, list[BackupCopy]]:
    ids = list(ids)
    out: dict[str, list[BackupCopy]] = {i: [] for i in ids}
    if not ids:
        return out
    for copy in db.scalars(
        select(BackupCopy)
        .where(BackupCopy.artifact_type == artifact_type, BackupCopy.artifact_id.in_(ids))
        .order_by(BackupCopy.created_at)
    ):
        out.setdefault(copy.artifact_id, []).append(copy)
    return out


def backup_out(backup: Backup, copies: list[BackupCopy] | None = None) -> dict:
    return {
        "id": backup.id,
        "data_source_id": backup.data_source_id,
        "scope": backup.scope,
        "trigger": backup.trigger,
        "status": backup.status,
        "label": backup.label,
        "pinned": backup.pinned,
        "size_bytes": backup.size_bytes,
        "started_at": iso(backup.started_at),
        "finished_at": iso(backup.finished_at),
        "verified_at": iso(backup.verified_at),
        "verify_status": backup.verify_status,
        "copies": [{"location": c.location, "device_id": c.device_id, "status": c.status} for c in copies or []],
        "row_counts": backup.row_counts,
        "expires_at": iso(backup.expires_at),
        "job_id": backup.job_id,
        "error": backup.error,
    }


def backups_out(db: Session, backups: list[Backup]) -> list[dict]:
    copies = copies_by_artifact(db, "backup", [b.id for b in backups])
    return [backup_out(b, copies.get(b.id)) for b in backups]


def get_backup(db: Session, ds: DataSource, backup_id: str) -> Backup:
    backup = db.get(Backup, backup_id)
    if backup is None or backup.data_source_id != ds.id or backup.scope != "source":
        raise not_found("Backup")
    return backup


# =============================================================================================
# copies (device storage hook)
# =============================================================================================

CopyTarget = Callable[..., dict]
_copy_target: CopyTarget | None = None


def register_copy_target(fn: CopyTarget | None) -> None:
    """See module docstring."""
    global _copy_target
    _copy_target = fn


def _copy_destination(policy: BackupPolicy | None, host_device_id: str | None) -> tuple[str, str | None] | None:
    if policy is None:
        return None
    if policy.copy_to_primary and host_device_id is not None:
        return "primary", None
    if policy.copy_to_device_id and policy.copy_to_device_id != host_device_id:
        return "device", policy.copy_to_device_id
    return None


def replicate(
    db: Session,
    *,
    artifact_type: str,
    artifact_id: str,
    local: BackupCopy,
    policy: BackupPolicy | None,
) -> BackupCopy | None:
    """Creates the policy copy of an artifact (status pending/ok/missing). Caller commits."""
    dest = _copy_destination(policy, local.device_id)
    if dest is None:
        return None
    location, device_id = dest
    copy = BackupCopy(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        location=location,
        device_id=device_id,
        ref=local.ref,
        size_bytes=local.size_bytes,
        sha256=local.sha256,
        status="pending",
    )
    db.add(copy)
    db.flush()
    _try_copy(copy, local)
    return copy


def _try_copy(copy: BackupCopy, source: BackupCopy) -> None:
    if _copy_target is None:
        return
    try:
        info = _copy_target(
            artifact_type=copy.artifact_type,
            artifact_id=copy.artifact_id,
            ref=source.ref,
            from_device_id=source.device_id,
            to_device_id=copy.device_id,
        )
    except Exception as exc:  # noqa: BLE001 - copies are retried by backup.copy
        log.warning("copy of %s %s failed: %s", copy.artifact_type, copy.artifact_id, exc)
        return
    copy.ref = str(info.get("ref") or source.ref)
    copy.size_bytes = info.get("size_bytes", copy.size_bytes)
    sha = info.get("sha256")
    if sha and source.sha256 and sha != source.sha256:
        copy.status = "missing"
        log.warning("copy of %s %s has a checksum mismatch", copy.artifact_type, copy.artifact_id)
        return
    copy.sha256 = sha or copy.sha256
    copy.status = "ok"
    copy.verified_at = utcnow()


def _delete_copy_bytes(db: Session, copy: BackupCopy) -> None:
    same_store = BackupCopy.device_id.is_(None) if copy.device_id is None else BackupCopy.device_id == copy.device_id
    shared = db.scalar(
        select(func.count())
        .select_from(BackupCopy)
        .where(BackupCopy.id != copy.id, BackupCopy.ref == copy.ref, same_store)
    )
    if shared:
        return
    try:
        executors.executor_for(copy.device_id).delete_artifact(copy.ref)
    except Exception as exc:  # noqa: BLE001 - an offline device keeps an orphan file; the row still goes
        log.warning("could not delete artifact %s on %s: %s", copy.ref, copy.device_id or "main server", exc)


def delete_artifact_rows(db: Session, artifact_type: str, artifact_id: str) -> None:
    for copy in list(
        db.scalars(
            select(BackupCopy).where(BackupCopy.artifact_type == artifact_type, BackupCopy.artifact_id == artifact_id)
        )
    ):
        _delete_copy_bytes(db, copy)
        db.delete(copy)
        db.flush()


def delete_backup(db: Session, backup: Backup) -> None:
    """Deletes a backup and all its copies. Caller commits."""
    delete_artifact_rows(db, "backup", backup.id)
    db.delete(backup)


def delete_segment(db: Session, segment: BackupLogSegment) -> None:
    delete_artifact_rows(db, "segment", segment.id)
    db.delete(segment)


def local_copy(db: Session, artifact_type: str, artifact_id: str, device_id: str | None) -> BackupCopy | None:
    for copy in db.scalars(
        select(BackupCopy).where(
            BackupCopy.artifact_type == artifact_type,
            BackupCopy.artifact_id == artifact_id,
            BackupCopy.status == "ok",
        )
    ):
        if copy.device_id == device_id:
            return copy
    return None


def any_copy(db: Session, artifact_type: str, artifact_id: str, prefer_device: str | None) -> BackupCopy | None:
    copies = list(
        db.scalars(
            select(BackupCopy).where(
                BackupCopy.artifact_type == artifact_type,
                BackupCopy.artifact_id == artifact_id,
                BackupCopy.status == "ok",
            )
        )
    )
    copies.sort(key=lambda c: (c.device_id != prefer_device, c.location != "local"))
    return copies[0] if copies else None


# =============================================================================================
# snapshots
# =============================================================================================


def start_snapshot(
    db: Session,
    ds: DataSource,
    *,
    trigger: str,
    label: str | None = None,
    user_id: str | None = None,
    pinned: bool = False,
    expires_at: datetime | None = None,
) -> tuple[Job, Backup]:
    """Adds a running Backup + queued job. Caller commits, then `jobs.dispatch(job.id)`."""
    require_supported(ds)
    if trigger not in TRIGGERS:
        raise ValueError(trigger)
    now = utcnow()
    backup = Backup(
        id=new_id(),
        data_source_id=ds.id,
        project_id=ds.project_id,
        scope="source",
        engine=ds.engine,
        trigger=trigger,
        status="running",
        label=label,
        pinned=bool(pinned or label),
        started_at=now,
        created_by_id=user_id,
        expires_at=expires_at or (now + SAFETY_KEEP if trigger in SAFETY_TRIGGERS else None),
    )
    db.add(backup)
    job = jobs.enqueue(
        db,
        type="backup.snapshot",
        params={"backup_id": backup.id, "trigger": trigger},
        project_id=ds.project_id,
        data_source_id=ds.id,
        device_id=ds.device_id,
        created_by_id=user_id,
    )
    backup.job_id = job.id
    db.flush()
    return job, backup


def perform_snapshot(factory: jobs.SessionFactory, backup_id: str, progress: executors.ProgressFn) -> dict:
    session = factory()
    try:
        backup = session.get(Backup, backup_id)
        if backup is None:
            raise ApiError(404, "not_found", "Backup not found")
        ds = session.get(DataSource, backup.data_source_id)
        if ds is None:
            backup.status, backup.error, backup.finished_at = "failed", "Data source no longer exists", utcnow()
            session.commit()
            raise ApiError(404, "not_found", "Data source no longer exists")
        ref = snapshot_ref(backup)
        kind, engine, database, device_id = ds.kind, ds.engine, ds.database_name, ds.device_id
        backup.status, backup.started_at = "running", utcnow()
        session.commit()
        try:
            executor = executors.executor_for(device_id)
            result = executor.snapshot(
                kind=kind, engine=engine, database_name=database, artifact_ref=ref, on_progress=progress
            )
        except Exception as exc:
            backup.status, backup.finished_at = "failed", utcnow()
            backup.error = jobs.redact_error(jobs._error_text(exc))
            session.commit()
            raise
        progress(0.93, "Recording schema")
        schema = _schema_snapshot(ds)
        backup.status = "succeeded"
        backup.finished_at = utcnow()
        backup.size_bytes = int(result.get("size_bytes") or 0)
        backup.sha256 = result.get("sha256")
        backup.consistent_point = result.get("consistent_point") or {}
        backup.row_counts = result.get("row_counts") or {}
        backup.schema_snapshot = schema
        backup.error = None
        local = BackupCopy(
            artifact_type="backup",
            artifact_id=backup.id,
            location="local",
            device_id=device_id,
            ref=ref,
            size_bytes=backup.size_bytes,
            sha256=backup.sha256,
            status="ok",
            verified_at=utcnow(),
        )
        session.add(local)
        session.flush()
        replicate(
            session, artifact_type="backup", artifact_id=backup.id, local=local, policy=session.get(BackupPolicy, ds.id)
        )
        session.commit()
        return {"backup_id": backup.id, "size_bytes": backup.size_bytes, "row_counts": backup.row_counts}
    finally:
        session.close()


def _schema_snapshot(ds: DataSource) -> dict | None:
    try:
        from app.services import source_ops  # routes device-hosted sources to their device

        schema = source_ops.introspect_sources([ds], 100)[0]
    except Exception:  # noqa: BLE001
        log.warning("schema snapshot of %s failed", ds.id, exc_info=True)
        return None
    return schema if schema.get("status") == "ok" else None


@jobs.job_handler("backup.snapshot")
def _job_snapshot(ctx: jobs.JobContext) -> dict:
    ctx.progress(0.01, "Starting snapshot", force=True)
    return perform_snapshot(ctx.session_factory, ctx.params["backup_id"], ctx.progress)


def safety_snapshot(db: Session, ds: DataSource, *, trigger: str, user_id: str | None) -> Backup | None:
    """Synchronous safety snapshot before a destructive action (when the policy asks for one).

    Commits the session. Raises 500 `safety_snapshot_failed` if the snapshot fails.
    """
    if not supported(ds) or ds.deleted_at is not None:
        return None
    policy = ensure_policy(db, ds)
    if not policy.safety_snapshots:
        db.commit()
        return None
    job, backup = start_snapshot(db, ds, trigger=trigger, user_id=user_id)
    db.commit()
    status = jobs.run_job(job.id)
    db.expire_all()
    backup = db.get(Backup, backup.id)
    if status != "succeeded" or backup is None or backup.status != "succeeded":
        error = (backup.error if backup else None) or "unknown error"
        raise ApiError(500, "safety_snapshot_failed", f"The safety snapshot failed, nothing was changed: {error}")
    return backup


# =============================================================================================
# log archiving & recovery window
# =============================================================================================


@dataclass
class SegKey:
    lo: Any
    hi: Any
    inclusive: bool
    gap: bool


def _seq(name: str | None) -> int | None:
    m = re.search(r"\.(\d+)$", name or "")
    return int(m.group(1)) if m else None


def _ts(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    return int(value[0]), int(value[1])


def seg_key(seg: BackupLogSegment) -> SegKey | None:
    sp, ep = seg.start_point or {}, seg.end_point or {}
    if seg.kind == "binlog":
        lo, hi = _seq(sp.get("binlog_file")), _seq(ep.get("binlog_file"))
    else:
        lo, hi = _ts(sp.get("ts")), _ts(ep.get("ts"))
    if lo is None or hi is None:
        return None
    return SegKey(lo, hi, bool(sp.get("inclusive")), bool(sp.get("gap")))


def contiguous(prev: BackupLogSegment, nxt: BackupLogSegment) -> bool:
    a, b = seg_key(prev), seg_key(nxt)
    if a is None or b is None or b.gap:
        return False
    if nxt.kind == "binlog":
        return b.lo == a.hi + 1
    return b.lo == a.hi


def _snapshot_anchor(backup: Backup) -> Any:
    cp = backup.consistent_point or {}
    if backup.engine == "mariadb":
        return _seq(cp.get("binlog_file"))
    return _ts(cp.get("oplog_ts_start"))


def covers_anchor(seg: BackupLogSegment, anchor: Any) -> bool:
    key = seg_key(seg)
    if key is None or anchor is None:
        return False
    if seg.kind == "binlog":
        return key.lo <= anchor <= key.hi
    return (key.lo < anchor <= key.hi) or (key.inclusive and key.lo == anchor)


def ordered_segments(db: Session, data_source_id: str) -> list[BackupLogSegment]:
    segs = list(db.scalars(select(BackupLogSegment).where(BackupLogSegment.data_source_id == data_source_id)))

    def order(seg: BackupLogSegment) -> tuple:
        key = seg_key(seg)
        return (key is not None, key.hi if key else 0, seg.created_at)

    segs.sort(key=order)
    return segs


def chain_from(backup: Backup, segments: list[BackupLogSegment]) -> list[BackupLogSegment]:
    """Contiguous segments starting at the snapshot's consistent point (empty if logs don't reach it)."""
    anchor = _snapshot_anchor(backup)
    chain: list[BackupLogSegment] = []
    for seg in segments:
        if not chain:
            if covers_anchor(seg, anchor):
                chain.append(seg)
            continue
        if contiguous(chain[-1], seg):
            chain.append(seg)
        elif seg_key(seg) and seg_key(chain[-1]) and seg_key(seg).hi <= seg_key(chain[-1]).hi:
            continue  # duplicate/overlap (shouldn't happen)
        else:
            break
    return chain


def successful_snapshots(db: Session, data_source_id: str) -> list[Backup]:
    return list(
        db.scalars(
            select(Backup)
            .where(Backup.data_source_id == data_source_id, Backup.scope == "source", Backup.status == "succeeded")
            .order_by(Backup.started_at)
        )
    )


def _replay_floor(backup: Backup) -> datetime:
    """Earliest time a PITR restore from this snapshot can target."""
    cp = backup.consistent_point or {}
    at = consistent_at(backup) or backup.started_at
    if backup.engine == "mongodb" and cp.get("oplog_ts_end"):
        at = max(at, datetime.fromtimestamp(int(cp["oplog_ts_end"][0]), UTC).replace(tzinfo=None))
    return at


def recovery_window(
    db: Session, ds: DataSource, policy: BackupPolicy | None = None, now: datetime | None = None
) -> dict:
    policy = policy or ensure_policy(db, ds)
    now = now or utcnow()
    snaps = successful_snapshots(db, ds.id)
    out = {"pitr_enabled": bool(policy.pitr_enabled), "earliest": None, "latest": None, "snapshots": len(snaps)}
    if not policy.pitr_enabled or not snaps:
        return out
    segments = ordered_segments(db, ds.id)
    intervals: list[tuple[datetime, datetime]] = []
    for snap in snaps:
        if not pitr_base_ok(snap):
            continue
        start = _replay_floor(snap)
        chain = chain_from(snap, segments)
        end = max([start] + [s.end_at for s in chain])
        intervals.append((start, end))
    if not intervals:
        return out
    intervals.sort()
    merged: list[list[datetime]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    earliest, latest = merged[-1]
    window_start = now - timedelta(days=policy.pitr_window_days)
    if latest < window_start:
        return out
    out["earliest"] = iso(max(earliest, window_start))
    out["latest"] = iso(latest)
    return out


@dataclass
class RestorePlan:
    backup: Backup
    segments: list[BackupLogSegment]
    until: datetime | None


def plan_restore(
    db: Session, ds: DataSource, *, backup_id: str | None, point_in_time: Any, now: datetime | None = None
) -> RestorePlan:
    if bool(backup_id) == bool(point_in_time):
        raise validation_error("Pass exactly one of backup_id or point_in_time")
    if backup_id:
        backup = get_backup(db, ds, backup_id)
        if backup.status != "succeeded":
            raise ApiError(409, "backup_not_ready", "Only succeeded backups can be restored")
        return RestorePlan(backup, [], None)
    until = parse_time(point_in_time)
    policy = ensure_policy(db, ds)
    window = recovery_window(db, ds, policy, now)
    earliest, latest = parse_time(window["earliest"]), parse_time(window["latest"])
    if not window["pitr_enabled"] or earliest is None or latest is None or not earliest <= until <= latest:
        raise ApiError(
            422,
            "outside_recovery_window",
            "That point in time is outside the recovery window",
            {"earliest": window["earliest"], "latest": window["latest"]},
        )
    segments = ordered_segments(db, ds.id)
    for snap in reversed(successful_snapshots(db, ds.id)):
        if not pitr_base_ok(snap) or _replay_floor(snap) > until:
            continue
        chain = chain_from(snap, segments)
        end = max([_replay_floor(snap)] + [s.end_at for s in chain])
        if end < until:
            continue
        needed = []
        for seg in chain:
            needed.append(seg)
            if seg.end_at >= until:
                break
        return RestorePlan(snap, needed, until)
    raise ApiError(422, "outside_recovery_window", "No snapshot and logs cover that point in time", window)


def _gap_marker(db: Session, ds: DataSource, resume_point: dict | None) -> None:
    """After an in-place restore, older logs can't be replayed across the swap: record a gap."""
    if not resume_point:
        return
    now = utcnow()
    if ds.engine == "mariadb" and resume_point.get("binlog_file"):
        seq = _seq(resume_point["binlog_file"])
        if seq is None:
            return
        from app.services.backup_engine import binlog_name_with_seq

        prev = binlog_name_with_seq(resume_point["binlog_file"], max(seq - 1, 1))
        point = {"binlog_file": prev}
        kind = "binlog"
    elif ds.engine == "mongodb" and resume_point.get("ts"):
        point = {"ts": resume_point["ts"]}
        kind = "oplog"
    else:
        return
    db.add(
        BackupLogSegment(
            id=new_id(),
            data_source_id=ds.id,
            kind=kind,
            start_at=now,
            end_at=now,
            start_point={**point, "gap": True, "reason": "restore"},
            end_point=point,
            size_bytes=0,
        )
    )


def archive_source_logs(factory: jobs.SessionFactory, data_source_id: str) -> dict:
    session = factory()
    try:
        ds = session.get(DataSource, data_source_id)
        if ds is None or not supported(ds) or ds.deleted_at is not None:
            return {"skipped": "not applicable"}
        policy = ensure_policy(session, ds)
        if not policy.pitr_enabled:
            session.commit()
            return {"skipped": "pitr disabled"}
        segments = ordered_segments(session, ds.id)
        last = segments[-1] if segments else None
        if last is not None:
            since = dict(last.end_point or {})
        else:
            window_start = utcnow() - timedelta(days=policy.pitr_window_days)
            snaps = [s for s in successful_snapshots(session, ds.id) if pitr_base_ok(s)]
            if not snaps:
                session.commit()
                return {"skipped": "no snapshot yet"}
            older = [s for s in snaps if consistent_at(s) <= window_start]
            base = older[-1] if older else snaps[0]
            since = {"after": base.consistent_point}
        kind, engine, database, device_id = ds.kind, ds.engine, ds.database_name, ds.device_id
        session.commit()

        executor = executors.executor_for(device_id)
        results = executor.archive_logs(
            kind=kind, engine=engine, database_name=database, since_point=since, artifact_ref_prefix=logs_prefix(ds.id)
        )
        seg_kind = "binlog" if engine == "mariadb" else "oplog"
        created = extended = 0
        new_locals: list[tuple[BackupLogSegment, BackupCopy]] = []
        for item in results:
            row = BackupLogSegment(
                id=item.get("id") or new_id(),
                data_source_id=ds.id,
                kind=seg_kind,
                start_at=parse_time(item["start_at"]) or utcnow(),
                end_at=parse_time(item["end_at"]) or utcnow(),
                start_point=item.get("start_point") or {},
                end_point=item.get("end_point") or {},
                size_bytes=int(item.get("size_bytes") or 0),
                sha256=item.get("sha256"),
            )
            if not item.get("ref") and last is not None and contiguous(last, row):
                last.end_point = dict(row.end_point)
                last.end_at = max(last.end_at, row.end_at)
                extended += 1
                continue
            session.add(row)
            session.flush()
            created += 1
            if item.get("ref"):
                copy = BackupCopy(
                    artifact_type="segment",
                    artifact_id=row.id,
                    location="local",
                    device_id=device_id,
                    ref=item["ref"],
                    size_bytes=row.size_bytes,
                    sha256=row.sha256,
                    status="ok",
                    verified_at=utcnow(),
                )
                session.add(copy)
                session.flush()
                new_locals.append((row, copy))
            last = row
        for row, copy in new_locals:
            replicate(session, artifact_type="segment", artifact_id=row.id, local=copy, policy=policy)
        session.commit()
        return {"segments_created": created, "segments_extended": extended}
    finally:
        session.close()


@jobs.job_handler("backup.archive_logs")
def _job_archive(ctx: jobs.JobContext) -> dict:
    return archive_source_logs(ctx.session_factory, ctx.params["data_source_id"])


# =============================================================================================
# restore
# =============================================================================================


def _restored_name(db: Session, ds: DataSource, requested: str | None, now: datetime) -> str:
    name = (requested or "").strip() or f"{(ds.deleted_name or ds.name)[:40]}-restored-{now:%Y%m%d-%H%M}"
    if len(name) > 63:
        raise validation_error("new_name must be at most 63 characters")
    return name


def _name_taken(db: Session, project_id: str, name: str) -> bool:
    return (
        db.scalar(select(DataSource.id).where(DataSource.project_id == project_id, DataSource.name == name)) is not None
    )


def start_restore(
    db: Session,
    ds: DataSource,
    *,
    user_id: str,
    role_is_owner: bool,
    mode: str,
    backup_id: str | None,
    point_in_time: Any,
    new_name: str | None,
    device_id: str | None,
    device_id_set: bool,
) -> Job:
    require_supported(ds)
    if ds.deleted_at is not None:
        raise ApiError(409, "source_deleted", "Restore the deleted data source first")
    if mode not in ("new_source", "in_place"):
        raise validation_error("mode must be new_source or in_place")
    if mode == "in_place" and not role_is_owner:
        raise ApiError(403, "forbidden", "Only the project owner can restore in place")
    plan = plan_restore(db, ds, backup_id=backup_id, point_in_time=point_in_time)
    params: dict[str, Any] = {
        "mode": mode,
        "backup_id": plan.backup.id,
        "point_in_time": iso(plan.until) if plan.until else None,
    }
    if mode == "new_source":
        target_device = device_id if device_id_set else ds.device_id
        if target_device:
            from app.services import devices  # same placement rules as creating a source (docs/DEVICES.md)

            devices.validate_placement(db, db.get(Project, ds.project_id), target_device, ds.kind)
        name = _restored_name(db, ds, new_name, utcnow())
        if _name_taken(db, ds.project_id, name):
            raise ApiError(409, "name_taken", f"A data source named '{name}' already exists in this project")
        params.update(new_name=name, target_device_id=target_device)
    if jobs.active_job(db, "backup.restore", data_source_id=ds.id):
        raise ApiError(409, "restore_in_progress", "A restore of this data source is already running")
    return jobs.enqueue(
        db,
        type="backup.restore",
        params=params,
        project_id=ds.project_id,
        data_source_id=ds.id,
        device_id=ds.device_id,
        created_by_id=user_id,
    )


def _stage_artifacts(
    session: Session, plan_backup: Backup, segments: list[BackupLogSegment], host_device: str | None
) -> tuple[str, list[dict], list[str]]:
    """Refs of the snapshot and segments on `host_device`, copying them there when needed.

    Returns (snapshot_ref, segment dicts, staged refs to clean up afterwards).
    """
    staged: list[str] = []

    def ref_on_host(artifact_type: str, artifact_id: str) -> str:
        copy = local_copy(session, artifact_type, artifact_id, host_device)
        if copy is not None:
            return copy.ref
        source = any_copy(session, artifact_type, artifact_id, host_device)
        if source is None:
            raise ApiError(409, "artifact_missing", f"No usable copy of {artifact_type} {artifact_id} exists")
        if _copy_target is None:
            raise ApiError(
                409,
                "cross_host_restore_unavailable",
                "The backup is stored on another host and host-device transfers are not available",
            )
        info = _copy_target(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            ref=source.ref,
            from_device_id=source.device_id,
            to_device_id=host_device,
        )
        staged.append(str(info.get("ref") or source.ref))
        return staged[-1]

    snap_ref = ref_on_host("backup", plan_backup.id)
    seg_dicts = []
    for seg in segments:
        ref = ref_on_host("segment", seg.id) if (seg.size_bytes or 0) > 0 else None
        seg_dicts.append({"id": seg.id, "ref": ref, "start_point": seg.start_point, "end_point": seg.end_point})
    return snap_ref, seg_dicts, staged


def perform_restore(ctx: jobs.JobContext) -> dict:
    factory = ctx.session_factory
    params = ctx.params
    session = factory()
    new_ds: DataSource | None = None
    staged: list[str] = []
    host: str | None = None
    try:
        ds = session.get(DataSource, ctx.data_source_id or params.get("data_source_id"))
        if ds is None:
            raise ApiError(404, "not_found", "Data source not found")
        project = session.get(Project, ds.project_id)
        plan = plan_restore(
            session,
            ds,
            backup_id=None if params.get("point_in_time") else params["backup_id"],
            point_in_time=params.get("point_in_time"),
        )
        if params.get("point_in_time") and plan.backup.id != params.get("backup_id"):
            log.info("restore %s: base snapshot changed to %s", ctx.job_id, plan.backup.id)
        result: dict[str, Any] = {
            "mode": params["mode"],
            "backup_id": plan.backup.id,
            "point_in_time": params.get("point_in_time"),
        }
        ctx.check_cancelled()

        if params["mode"] == "in_place":
            host = ds.device_id
            ctx.progress(0.02, "Taking a safety snapshot", force=True)
            job_like, safety = start_snapshot(session, ds, trigger="pre_restore", user_id=ctx.created_by_id)
            # Run it inline as part of this job (its own job row documents it).
            session.commit()
            status = jobs.run_job(job_like.id, session_factory=factory)
            session.expire_all()
            safety = session.get(Backup, safety.id)
            if status != "succeeded" or safety is None or safety.status != "succeeded":
                raise ApiError(500, "safety_snapshot_failed", "The safety snapshot failed; nothing was changed")
            result["safety_backup_id"] = safety.id
            target_name = ds.database_name
            target_ds = ds
        else:
            host = params.get("target_device_id")
            name = params["new_name"]
            if _name_taken(session, ds.project_id, name):
                raise ApiError(409, "name_taken", f"A data source named '{name}' already exists in this project")
            from app.crypto import encrypt_json

            provisioning = _provisioning()

            executor = executors.executor_for(host)
            config = None
            for _ in range(5):
                candidate = provisioning.generate_database_name(project.slug if project else "restored")
                try:
                    config = executor.ensure_database(kind=ds.kind, database_name=candidate)
                    break
                except ApiError as exc:
                    if exc.code != "database_exists":
                        raise
            if config is None:
                raise ApiError(500, "provisioning_failed", "Could not allocate a database name")
            new_ds = DataSource(
                id=new_id(),
                project_id=ds.project_id,
                name=name,
                kind=ds.kind,
                engine=ds.engine,
                mode="managed",
                database_name=config.get("database") or candidate,
                config_encrypted=encrypt_json(config),
                status="unknown",
                status_message="Restoring from backup...",
                device_id=host,
            )
            session.add(new_ds)
            session.flush()
            ensure_policy(session, new_ds)
            session.commit()
            target_name = new_ds.database_name
            target_ds = new_ds
            result["data_source_id"] = new_ds.id

        snap_ref, seg_dicts, staged = _stage_artifacts(session, plan.backup, plan.segments, host)
        consistent_point = dict(plan.backup.consistent_point or {})
        source_db = ds.database_name
        engine, kind = ds.engine, ds.kind
        session.commit()
        ctx.check_cancelled()

        def progress(fraction, message=None):
            ctx.progress(0.1 + 0.85 * fraction if fraction is not None else None, message)

        restored = executors.executor_for(host).restore(
            kind=kind,
            engine=engine,
            target_database_name=target_name,
            snapshot_ref=snap_ref,
            segments=seg_dicts,
            until=plan.until,
            on_progress=progress,
            source_database_name=source_db,
            consistent_point=consistent_point,
        )
        result["row_counts"] = restored.get("row_counts")
        target_ds = session.get(DataSource, target_ds.id)
        from app.services import connections

        connections.invalidate(target_ds.id)
        target_ds.status = "ok"
        target_ds.status_message = f"Restored from backup {plan.backup.id[:8]}" + (
            f" to {params['point_in_time']}" if params.get("point_in_time") else ""
        )
        target_ds.last_checked_at = utcnow()
        if params["mode"] == "in_place":
            _gap_marker(session, target_ds, restored.get("resume_point"))
        follow_job, _ = start_snapshot(session, target_ds, trigger="scheduled", user_id=ctx.created_by_id)
        session.commit()
        jobs.dispatch(follow_job.id)
        new_ds = None  # success: keep it
        return result
    except BaseException:
        session.rollback()
        if new_ds is not None:
            _discard_new_source(factory, new_ds.id)
        raise
    finally:
        for ref in staged:
            try:
                executors.executor_for(host).delete_artifact(ref)
            except Exception:  # noqa: BLE001
                log.warning("could not remove staged artifact %s", ref)
        session.close()


def _discard_new_source(factory: jobs.SessionFactory, data_source_id: str) -> None:
    provisioning = _provisioning()

    session = factory()
    try:
        ds = session.get(DataSource, data_source_id)
        if ds is None:
            return
        try:
            provisioning.drop_managed_source(session, ds)
        except Exception:  # noqa: BLE001
            log.warning("could not drop the database of failed restore target %s", data_source_id, exc_info=True)
        policy = session.get(BackupPolicy, ds.id)
        if policy is not None:
            session.delete(policy)
        session.delete(ds)
        session.commit()
    finally:
        session.close()


@jobs.job_handler("backup.restore")
def _job_restore(ctx: jobs.JobContext) -> dict:
    return perform_restore(ctx)


# =============================================================================================
# verification
# =============================================================================================


def perform_verify(factory: jobs.SessionFactory, backup_id: str) -> dict:
    session = factory()
    try:
        backup = session.get(Backup, backup_id)
        if backup is None or backup.status != "succeeded":
            return {"skipped": "backup not available"}
        ds = session.get(DataSource, backup.data_source_id) if backup.data_source_id else None
        host = ds.device_id if ds else None
        copy = local_copy(session, "backup", backup.id, host)
        if copy is None:
            raise ApiError(409, "artifact_missing", "No local copy of this backup exists")
        kind = "sql" if backup.engine == "mariadb" else "nosql"
        expected = dict(backup.row_counts or {})
        engine, ref, sha = backup.engine, copy.ref, backup.sha256
        session.commit()
        executor = executors.executor_for(host)
        try:
            checksum_ok = True
            if isinstance(executor, executors.LocalExecutor) and sha:
                from app.services.backup_crypto import sha256_file

                checksum_ok = sha256_file(executor.artifact_path(ref)) == sha
            outcome = (
                executor.verify(kind=kind, engine=engine, snapshot_ref=ref, expected_row_counts=expected)
                if checksum_ok
                else {"ok": False, "message": "Checksum mismatch", "mismatches": []}
            )
        except Exception as exc:  # noqa: BLE001 - a failed verification is a result, not a job failure
            outcome = {"ok": False, "message": jobs.redact_error(jobs._error_text(exc)), "mismatches": []}
        backup = session.get(Backup, backup_id)
        backup.verified_at = utcnow()
        backup.verify_status = "ok" if outcome.get("ok") else "failed"
        copy = session.get(BackupCopy, copy.id)
        if copy is not None and outcome.get("ok"):
            copy.verified_at = utcnow()
        session.commit()
        return {
            "backup_id": backup_id,
            "ok": bool(outcome.get("ok")),
            "message": outcome.get("message"),
            "mismatches": outcome.get("mismatches", []),
        }
    finally:
        session.close()


@jobs.job_handler("backup.verify")
def _job_verify(ctx: jobs.JobContext) -> dict:
    return perform_verify(ctx.session_factory, ctx.params["backup_id"])


# =============================================================================================
# retention (GFS)
# =============================================================================================


def _bucket_keys(dt: datetime) -> dict[str, tuple]:
    iso_year, iso_week, _ = dt.isocalendar()
    return {
        "hourly": (dt.year, dt.month, dt.day, dt.hour),
        "daily": (dt.year, dt.month, dt.day),
        "weekly": (iso_year, iso_week),
        "monthly": (dt.year, dt.month),
    }


def gfs_keep(snapshots: list[Backup], policy: BackupPolicy, now: datetime) -> dict[str, str]:
    """Pure: which snapshots to keep and why. Returns {backup_id: reason}. Others may be pruned."""
    keep: dict[str, str] = {}
    ok = [s for s in snapshots if s.status == "succeeded"]
    ok.sort(key=lambda s: s.started_at, reverse=True)
    limits = {
        "hourly": policy.keep_hourly,
        "daily": policy.keep_daily,
        "weekly": policy.keep_weekly,
        "monthly": policy.keep_monthly,
    }
    seen: dict[str, set] = {k: set() for k in limits}
    for snap in ok:
        if snap.pinned:
            keep.setdefault(snap.id, "pinned")
        if snap.trigger in SAFETY_TRIGGERS or snap.trigger == "final":
            if now - snap.started_at < SAFETY_KEEP or (snap.expires_at and snap.expires_at > now):
                keep.setdefault(snap.id, "safety")
            continue
        if snap.trigger not in GFS_TRIGGERS:
            continue
        for bucket, key in _bucket_keys(snap.started_at).items():
            if key in seen[bucket]:
                continue
            if len(seen[bucket]) < limits[bucket]:
                seen[bucket].add(key)
                keep.setdefault(snap.id, bucket)
    gfs = [s for s in ok if s.trigger in GFS_TRIGGERS]
    if gfs:
        keep.setdefault(gfs[0].id, "latest")
    for snap in snapshots:
        if snap.status == "running":
            keep.setdefault(snap.id, "running")
        elif snap.status == "failed" and now - snap.started_at < FAILED_KEEP:
            keep.setdefault(snap.id, "recent_failure")
    return keep


def segments_to_prune(
    snapshots_kept: list[Backup], segments: list[BackupLogSegment], policy: BackupPolicy, now: datetime
) -> list[BackupLogSegment]:
    """Pure: log segments no kept snapshot needs for the PITR window."""
    if not segments:
        return []
    if not policy.pitr_enabled:
        return list(segments)
    window_start = now - timedelta(days=policy.pitr_window_days)
    bases = [s for s in snapshots_kept if s.status == "succeeded" and pitr_base_ok(s)]
    if not bases:
        return []  # nothing to anchor on yet; keep everything
    bases.sort(key=lambda s: _replay_floor(s))
    older = [s for s in bases if _replay_floor(s) <= window_start]
    base = older[-1] if older else bases[0]
    anchor = _snapshot_anchor(base)
    prune = []
    for seg in segments:
        key = seg_key(seg)
        if key is None:
            continue
        if covers_anchor(seg, anchor):
            continue
        if seg.kind == "binlog":
            if key.hi < anchor:
                prune.append(seg)
        elif key.hi < anchor:
            prune.append(seg)
    return prune


def prune_source(db: Session, ds: DataSource, now: datetime) -> dict:
    policy = ensure_policy(db, ds)
    snaps = list(db.scalars(select(Backup).where(Backup.data_source_id == ds.id, Backup.scope == "source")))
    keep = gfs_keep(snaps, policy, now)
    deleted = 0
    for snap in snaps:
        if snap.id in keep:
            continue
        if snap.expires_at and snap.expires_at > now and snap.trigger not in GFS_TRIGGERS:
            continue
        delete_backup(db, snap)
        deleted += 1
    db.flush()
    kept = [s for s in snaps if s.id in keep]
    segs = ordered_segments(db, ds.id)
    pruned_segments = 0
    for seg in segments_to_prune(kept, segs, policy, now):
        delete_segment(db, seg)
        pruned_segments += 1
    return {"backups_deleted": deleted, "segments_deleted": pruned_segments}


def purge_source(db: Session, data_source_id: str) -> None:
    for backup in list(db.scalars(select(Backup).where(Backup.data_source_id == data_source_id))):
        delete_backup(db, backup)
    for seg in list(db.scalars(select(BackupLogSegment).where(BackupLogSegment.data_source_id == data_source_id))):
        delete_segment(db, seg)
    policy = db.get(BackupPolicy, data_source_id)
    if policy is not None:
        db.delete(policy)


def prune_all(factory: jobs.SessionFactory, now: datetime | None = None) -> dict:
    now = now or utcnow()
    session = factory()
    summary = {"sources": 0, "backups_deleted": 0, "segments_deleted": 0, "purged_sources": 0, "platform_deleted": 0}
    try:
        sources = list(session.scalars(select(DataSource).where(DataSource.mode == "managed")))
        known_ids = {ds.id for ds in session.scalars(select(DataSource))}
        for ds in sources:
            if not supported(ds):
                continue
            try:
                if ds.deleted_at is not None and now - ds.deleted_at >= DELETED_KEEP:
                    purge_source(session, ds.id)
                    session.delete(ds)
                    summary["purged_sources"] += 1
                else:
                    res = prune_source(session, ds, now)
                    summary["backups_deleted"] += res["backups_deleted"]
                    summary["segments_deleted"] += res["segments_deleted"]
                    summary["sources"] += 1
                session.commit()
            except Exception:  # noqa: BLE001 - one source must not block the others
                session.rollback()
                log.exception("pruning %s failed", ds.id)
        # Backups whose source row is gone (deleted projects): keep until expires_at.
        orphan_ids = {
            sid
            for sid in session.scalars(
                select(Backup.data_source_id).where(Backup.data_source_id.is_not(None)).distinct()
            )
            if sid not in known_ids
        }
        for sid in orphan_ids:
            backups = list(session.scalars(select(Backup).where(Backup.data_source_id == sid)))
            if all(b.expires_at is not None and b.expires_at <= now for b in backups):
                purge_source(session, sid)
                summary["purged_sources"] += 1
        platform = list(
            session.scalars(select(Backup).where(Backup.scope == "platform").order_by(Backup.started_at.desc()))
        )
        ok = [b for b in platform if b.status == "succeeded"]
        for b in ok[PLATFORM_KEEP:]:
            if not b.pinned:
                delete_backup(session, b)
                summary["platform_deleted"] += 1
        for b in platform:
            if b.status == "failed" and now - b.started_at > FAILED_KEEP:
                delete_backup(session, b)
        session.commit()
        return summary
    finally:
        session.close()


@jobs.job_handler("backup.prune")
def _job_prune(ctx: jobs.JobContext) -> dict:
    return prune_all(ctx.session_factory)


# =============================================================================================
# copies retry
# =============================================================================================


@jobs.job_handler("backup.copy")
def _job_copy(ctx: jobs.JobContext) -> dict:
    if _copy_target is None:
        return {"skipped": "no copy target registered"}
    session = ctx.db()
    done = 0
    try:
        for copy in list(session.scalars(select(BackupCopy).where(BackupCopy.status == "pending").limit(200))):
            source = local_copy(session, copy.artifact_type, copy.artifact_id, _artifact_host(session, copy))
            if source is None:
                continue
            _try_copy(copy, source)
            done += copy.status == "ok"
            session.commit()
        return {"copied": done}
    finally:
        session.close()


def _artifact_host(session: Session, copy: BackupCopy) -> str | None:
    local = session.scalar(
        select(BackupCopy).where(
            BackupCopy.artifact_type == copy.artifact_type,
            BackupCopy.artifact_id == copy.artifact_id,
            BackupCopy.location == "local",
        )
    )
    return local.device_id if local else None


# =============================================================================================
# platform snapshots
# =============================================================================================


def start_platform_snapshot(db: Session, user_id: str | None) -> Job:
    backup = Backup(
        id=new_id(),
        data_source_id=None,
        project_id=None,
        scope="platform",
        engine="mariadb",
        trigger="manual" if user_id else "scheduled",
        status="running",
        started_at=utcnow(),
        created_by_id=user_id,
    )
    db.add(backup)
    job = jobs.enqueue(db, type="backup.platform_snapshot", params={"backup_id": backup.id}, created_by_id=user_id)
    backup.job_id = job.id
    db.flush()
    return job


@jobs.job_handler("backup.platform_snapshot")
def _job_platform_snapshot(ctx: jobs.JobContext) -> dict:
    session = ctx.db()
    try:
        backup = session.get(Backup, ctx.params["backup_id"])
        if backup is None:
            raise ApiError(404, "not_found", "Backup not found")
        ref = snapshot_ref(backup)
        session.commit()
        try:
            result = executors.local_executor().platform_snapshot(artifact_ref=ref, on_progress=ctx.progress)
        except Exception as exc:
            backup.status, backup.finished_at = "failed", utcnow()
            backup.error = jobs.redact_error(jobs._error_text(exc))
            session.commit()
            raise
        backup.status, backup.finished_at = "succeeded", utcnow()
        backup.size_bytes, backup.sha256 = int(result.get("size_bytes") or 0), result.get("sha256")
        backup.consistent_point, backup.row_counts = result.get("consistent_point"), result.get("row_counts")
        session.add(
            BackupCopy(
                artifact_type="backup",
                artifact_id=backup.id,
                location="local",
                device_id=None,
                ref=ref,
                size_bytes=backup.size_bytes,
                sha256=backup.sha256,
                status="ok",
                verified_at=utcnow(),
            )
        )
        session.commit()
        return {"backup_id": backup.id, "size_bytes": backup.size_bytes}
    finally:
        session.close()


# =============================================================================================
# soft delete / recently deleted
# =============================================================================================


def soft_delete_source(db: Session, ds: DataSource, *, user_id: str | None, drop: bool) -> Job | None:
    """Hides the source ("Recently deleted") and enqueues its final snapshot (+ drop). Caller commits
    and dispatches the returned job."""
    from app.services import connections

    now = utcnow()
    connections.invalidate(ds.id)
    ds.deleted_name = ds.name
    ds.name = f"{DELETED_NAME_PREFIX}{ds.id}"[:63]
    ds.deleted_at = now
    db.flush()
    if not supported(ds):
        return None
    return jobs.enqueue(
        db,
        type="source.finalize_delete",
        params={"data_source_id": ds.id, "drop": bool(drop)},
        project_id=ds.project_id,
        data_source_id=ds.id,
        device_id=ds.device_id,
        created_by_id=user_id,
    )


def detached_source_params(ds: DataSource, *, drop: bool) -> dict:
    """Job params for a source whose row is about to disappear (project deletion)."""
    return {
        "data_source_id": ds.id,
        "drop": bool(drop),
        "detached": {
            "project_id": ds.project_id,
            "name": ds.name,
            "kind": ds.kind,
            "engine": ds.engine,
            "mode": ds.mode,
            "database_name": ds.database_name,
            "device_id": ds.device_id,
            "config_encrypted": ds.config_encrypted,
        },
    }


def enqueue_detached_finalize(db: Session, ds: DataSource, *, user_id: str | None) -> Job | None:
    if not supported(ds):
        return None
    return jobs.enqueue(
        db,
        type="source.finalize_delete",
        params=detached_source_params(ds, drop=True),
        project_id=None,
        data_source_id=None,
        device_id=ds.device_id,
        created_by_id=user_id,
    )


def _final_snapshot_detached(factory: jobs.SessionFactory, info: dict, ds_id: str, user_id: str | None, progress):
    """Final snapshot of a source whose DataSource row no longer exists."""
    session = factory()
    try:
        now = utcnow()
        backup = Backup(
            id=new_id(),
            data_source_id=ds_id,
            project_id=info.get("project_id"),
            scope="source",
            engine=info["engine"],
            trigger="final",
            status="running",
            started_at=now,
            created_by_id=user_id,
            expires_at=now + DELETED_KEEP,
            label=f"Final snapshot of {info.get('name')}",
        )
        session.add(backup)
        session.commit()
        ref = snapshot_ref(backup)
        try:
            result = executors.executor_for(info.get("device_id")).snapshot(
                kind=info["kind"],
                engine=info["engine"],
                database_name=info["database_name"],
                artifact_ref=ref,
                on_progress=progress,
            )
        except Exception as exc:
            backup.status, backup.finished_at = "failed", utcnow()
            backup.error = jobs.redact_error(jobs._error_text(exc))
            session.commit()
            raise
        backup.status, backup.finished_at = "succeeded", utcnow()
        backup.size_bytes, backup.sha256 = int(result.get("size_bytes") or 0), result.get("sha256")
        backup.consistent_point, backup.row_counts = result.get("consistent_point"), result.get("row_counts")
        session.add(
            BackupCopy(
                artifact_type="backup",
                artifact_id=backup.id,
                location="local",
                device_id=info.get("device_id"),
                ref=ref,
                size_bytes=backup.size_bytes,
                sha256=backup.sha256,
                status="ok",
                verified_at=utcnow(),
            )
        )
        session.commit()
        return backup.id
    finally:
        session.close()


@jobs.job_handler("source.finalize_delete")
def _job_finalize_delete(ctx: jobs.JobContext) -> dict:
    provisioning = _provisioning()

    params = ctx.params
    ds_id = params["data_source_id"]
    detached = params.get("detached")
    ctx.progress(0.05, "Taking the final snapshot", force=True)
    if detached:
        backup_id = _final_snapshot_detached(ctx.session_factory, detached, ds_id, ctx.created_by_id, ctx.progress)
        transient = DataSource(
            id=ds_id,
            project_id=detached["project_id"],
            name=detached["name"],
            kind=detached["kind"],
            engine=detached["engine"],
            mode=detached["mode"],
            database_name=detached["database_name"],
            config_encrypted=detached["config_encrypted"],
            device_id=detached.get("device_id"),
        )
        session = ctx.db()
        try:
            provisioning.drop_managed_source(session, transient)
            session.commit()
        finally:
            session.close()
        return {"backup_id": backup_id, "dropped": True}

    session = ctx.db()
    try:
        ds = session.get(DataSource, ds_id)
        if ds is None:
            return {"skipped": "data source not found"}
        job, backup = start_snapshot(
            session,
            ds,
            trigger="final",
            user_id=ctx.created_by_id,
            expires_at=(ds.deleted_at or utcnow()) + DELETED_KEEP,
        )
        backup.label = f"Final snapshot of {ds.deleted_name or ds.name}"
        # The snapshot runs inside this job; mark its own job row as done alongside.
        session.commit()
        job_id, backup_id = job.id, backup.id
    finally:
        session.close()
    status = jobs.run_job(job_id, session_factory=ctx.session_factory)
    if status != "succeeded":
        raise ApiError(500, "final_snapshot_failed", "The final snapshot failed; the database was not dropped")
    dropped = False
    if params.get("drop"):
        session = ctx.db()
        try:
            ds = session.get(DataSource, ds_id)
            if ds is not None and ds.deleted_at is not None:
                provisioning.drop_managed_source(session, ds)
                dropped = True
            session.commit()
        finally:
            session.close()
    return {"backup_id": backup_id, "dropped": dropped}


def deleted_sources(db: Session, project_id: str) -> list[DataSource]:
    return list(
        db.scalars(
            select(DataSource)
            .where(DataSource.project_id == project_id, DataSource.deleted_at.is_not(None))
            .order_by(DataSource.deleted_at.desc())
        )
    )


def _was_dropped(db: Session, ds: DataSource) -> bool | None:
    job = db.scalar(
        select(Job)
        .where(Job.type == "source.finalize_delete", Job.data_source_id == ds.id)
        .order_by(Job.created_at.desc())
    )
    if job is None:
        return None
    if job.status in jobs.ACTIVE_STATUSES:
        raise ApiError(409, "delete_in_progress", "The deletion of this data source is still running")
    # A failed finalize job never dropped the database (the drop only follows a good final snapshot).
    return job.status == "succeeded" and bool((job.result or {}).get("dropped"))


def start_undelete(db: Session, ds: DataSource, *, name: str | None, user_id: str) -> Job:
    if ds.deleted_at is None:
        raise ApiError(409, "not_deleted", "This data source is not deleted")
    target = (name or ds.deleted_name or "").strip()
    if not target or len(target) > 63:
        raise validation_error("name must be 1-63 characters")
    if _name_taken(db, ds.project_id, target):
        raise ApiError(409, "name_taken", f"A data source named '{target}' already exists; pass another name")
    _was_dropped(db, ds)  # raises while the delete job still runs
    return jobs.enqueue(
        db,
        type="source.undelete",
        params={"data_source_id": ds.id, "name": target},
        project_id=ds.project_id,
        data_source_id=ds.id,
        device_id=ds.device_id,
        created_by_id=user_id,
    )


@jobs.job_handler("source.undelete")
def _job_undelete(ctx: jobs.JobContext) -> dict:
    provisioning = _provisioning()

    session = ctx.db()
    try:
        ds = session.get(DataSource, ctx.params["data_source_id"])
        if ds is None or ds.deleted_at is None:
            return {"skipped": "not deleted"}
        name = ctx.params["name"]
        if _name_taken(session, ds.project_id, name):
            raise ApiError(409, "name_taken", f"A data source named '{name}' already exists")
        dropped = _was_dropped(session, ds) if supported(ds) else False
        result: dict[str, Any] = {"data_source_id": ds.id, "restored_data": False}
        if dropped:
            snaps = [s for s in successful_snapshots(session, ds.id)]
            if not snaps:
                raise ApiError(409, "no_backup", "No snapshot of this data source is left to restore")
            snap = snaps[-1]
            host = ds.device_id
            config = decrypt_json(ds.config_encrypted)
            ctx.progress(0.1, "Recreating the database", force=True)
            if host is None:
                creator = (
                    provisioning.create_mariadb_database if ds.kind == "sql" else provisioning.create_mongo_database
                )
                creator(ds.database_name, config["username"], config["password"])
            else:
                from app.crypto import encrypt_json

                new_config = executors.executor_for(host).ensure_database(kind=ds.kind, database_name=ds.database_name)
                ds.config_encrypted = encrypt_json(new_config)
            snap_ref, _, staged = _stage_artifacts(session, snap, [], host)
            session.commit()
            executors.executor_for(host).restore(
                kind=ds.kind,
                engine=ds.engine,
                target_database_name=ds.database_name,
                snapshot_ref=snap_ref,
                segments=[],
                until=None,
                on_progress=lambda f, m=None: ctx.progress(f, m),
                source_database_name=ds.database_name,
                consistent_point=dict(snap.consistent_point or {}),
            )
            for ref in staged:
                executors.executor_for(host).delete_artifact(ref)
            result.update(restored_data=True, backup_id=snap.id)
        ds.name = name
        ds.deleted_at = None
        ds.deleted_name = None
        ds.status = "ok"
        ds.status_message = "Restored from Recently deleted"
        ds.last_checked_at = utcnow()
        # Final snapshots become ordinary versions again (kept by the normal retention rules).
        for backup in session.scalars(select(Backup).where(Backup.data_source_id == ds.id, Backup.trigger == "final")):
            backup.expires_at = utcnow() + SAFETY_KEEP
        session.commit()
        return result
    finally:
        session.close()


# =============================================================================================
# schema history
# =============================================================================================


def schema_at(db: Session, ds: DataSource, ref: str) -> tuple[dict | None, str | None, str]:
    """(schema, backup_id or None, ISO time) for a backup id or "current"."""
    if ref == "current":
        from app.services import source_ops

        schema = source_ops.introspect_sources([ds])[0]
        return schema, None, iso(utcnow())
    backup = get_backup(db, ds, ref)
    if backup.status != "succeeded":
        raise ApiError(409, "backup_not_ready", "That backup did not succeed")
    schema = schema_diff.apply_row_counts(backup.schema_snapshot, backup.row_counts)
    return schema, backup.id, iso(backup.started_at)


def diff(db: Session, ds: DataSource, from_ref: str, to_ref: str) -> dict:
    before, from_id, from_at = schema_at(db, ds, from_ref)
    after, to_id, to_at = schema_at(db, ds, to_ref)
    if before is None or after is None:
        raise ApiError(409, "schema_unavailable", "No schema was recorded for that version")
    return {
        "from": {"backup_id": from_id, "at": from_at},
        "to": {"backup_id": to_id, "at": to_at},
        "entities": schema_diff.diff_schemas(before, after),
    }


# =============================================================================================
# instance health
# =============================================================================================


def instance_health(db: Session) -> dict:
    sources = list(
        db.execute(
            select(DataSource, Project.name)
            .join(Project, Project.id == DataSource.project_id)
            .where(DataSource.mode == "managed", DataSource.deleted_at.is_(None))
            .order_by(Project.name, DataSource.name)
        ).all()
    )
    out_sources = []
    for ds, project_name in sources:
        if not supported(ds):
            continue
        last_ok = db.scalar(
            select(func.max(Backup.finished_at)).where(Backup.data_source_id == ds.id, Backup.status == "succeeded")
        )
        last_fail = db.scalar(
            select(Backup)
            .where(Backup.data_source_id == ds.id, Backup.status == "failed")
            .order_by(Backup.started_at.desc())
        )
        failed_job = db.scalar(
            select(Job)
            .where(Job.data_source_id == ds.id, Job.status == "failed", Job.type.like("backup.%"))
            .order_by(Job.created_at.desc())
        )
        last_error, last_failure_at = None, None
        if last_fail is not None:
            last_error, last_failure_at = last_fail.error, last_fail.started_at
        if failed_job is not None and (last_failure_at is None or failed_job.created_at > last_failure_at):
            last_error, last_failure_at = failed_job.error, failed_job.finished_at or failed_job.created_at
        if last_ok and last_failure_at and last_ok > last_failure_at:
            last_error = None
        artifact_ids = [b for b in db.scalars(select(Backup.id).where(Backup.data_source_id == ds.id))]
        seg_ids = [s for s in db.scalars(select(BackupLogSegment.id).where(BackupLogSegment.data_source_id == ds.id))]
        local_bytes = copy_bytes = 0
        if artifact_ids or seg_ids:
            for copy in db.scalars(select(BackupCopy).where(BackupCopy.artifact_id.in_(artifact_ids + seg_ids))):
                if copy.status != "ok":
                    continue
                if copy.location == "local":
                    local_bytes += copy.size_bytes or 0
                else:
                    copy_bytes += copy.size_bytes or 0
        window = recovery_window(db, ds)
        out_sources.append(
            {
                "data_source_id": ds.id,
                "project_id": ds.project_id,
                "project_name": project_name,
                "name": ds.name,
                "engine": ds.engine,
                "device_id": ds.device_id,
                "last_success_at": iso(last_ok),
                "last_failure_at": iso(last_failure_at),
                "last_error": last_error,
                "pitr_latest": window["latest"],
                "local_bytes": local_bytes,
                "copy_bytes": copy_bytes,
            }
        )
    platform_ok = db.scalar(
        select(func.max(Backup.finished_at)).where(Backup.scope == "platform", Backup.status == "succeeded")
    )
    platform_fail = db.scalar(
        select(Backup).where(Backup.scope == "platform", Backup.status == "failed").order_by(Backup.started_at.desc())
    )
    platform_error = None
    if platform_fail is not None and (platform_ok is None or platform_fail.started_at > platform_ok):
        platform_error = platform_fail.error
    storage = []
    try:
        stats = executors.local_executor().storage_stats()
    except Exception:  # noqa: BLE001
        stats = {"used_bytes": None, "free_bytes": None}
    storage.append({"location": "primary", "device_id": None, **stats})
    per_device = dict(
        db.execute(
            select(BackupCopy.device_id, func.sum(BackupCopy.size_bytes))
            .where(BackupCopy.device_id.is_not(None), BackupCopy.status == "ok")
            .group_by(BackupCopy.device_id)
        ).all()
    )
    for device_id, used in sorted(per_device.items()):
        device = db.get(Device, device_id)
        metrics = (device.metrics or {}) if device else {}
        free = metrics.get("disk_free_bytes") or metrics.get("disk_free")
        storage.append(
            {
                "location": "device",
                "device_id": device_id,
                "used_bytes": int(used or 0),
                "free_bytes": free if isinstance(free, int) else None,
            }
        )
    return {
        "sources": out_sources,
        "platform": {"last_success_at": iso(platform_ok), "last_error": platform_error},
        "storage": storage,
    }


# =============================================================================================
# scheduler
# =============================================================================================


def _redis_due(key: str, every: timedelta, now: datetime) -> bool:
    try:
        r = get_redis()
        last = r.get(key)
        if last is not None and now.timestamp() - float(last) < every.total_seconds():
            return False
        r.set(key, str(now.timestamp()), ex=int(every.total_seconds() * 3) + 60)
        return True
    except Exception:  # noqa: BLE001
        return False


def scheduler_tick(factory: jobs.SessionFactory, now: datetime | None = None) -> list[str]:
    """Enqueues whatever is due. Call from exactly one process (the scheduler leader)."""
    now = now or utcnow()
    session = factory()
    enqueued: list[str] = []
    try:
        sources = [
            ds
            for ds in session.scalars(
                select(DataSource).where(DataSource.mode == "managed", DataSource.deleted_at.is_(None))
            )
            if supported(ds)
        ]
        for ds in sources:
            policy = ensure_policy(session, ds)
            if policy.enabled and not jobs.active_job(session, "backup.snapshot", data_source_id=ds.id):
                last = session.scalar(
                    select(Backup)
                    .where(Backup.data_source_id == ds.id, Backup.trigger.in_(GFS_TRIGGERS))
                    .order_by(Backup.started_at.desc())
                )
                due = last is None or now - last.started_at >= SCHEDULES.get(policy.schedule, SCHEDULES["hourly"])
                if last is not None and last.status == "failed" and now - last.started_at < timedelta(minutes=10):
                    due = False
                if due:
                    job, _ = start_snapshot(session, ds, trigger="scheduled")
                    enqueued.append(job.id)
            if policy.pitr_enabled and not jobs.active_job(session, "backup.archive_logs", data_source_id=ds.id):
                interval = LOG_INTERVALS.get(ds.engine, timedelta(minutes=5))
                if _redis_due(f"backups:sched:logs:{ds.id}", interval, now):
                    job = jobs.enqueue(
                        session,
                        type="backup.archive_logs",
                        params={"data_source_id": ds.id},
                        project_id=ds.project_id,
                        data_source_id=ds.id,
                        device_id=ds.device_id,
                    )
                    enqueued.append(job.id)
            latest = session.scalar(
                select(Backup)
                .where(Backup.data_source_id == ds.id, Backup.status == "succeeded")
                .order_by(Backup.started_at.desc())
            )
            if latest is not None and not jobs.active_job(session, "backup.verify", data_source_id=ds.id):
                last_verified = session.scalar(
                    select(func.max(Backup.verified_at)).where(Backup.data_source_id == ds.id)
                )
                if (
                    last_verified is None or now - last_verified >= VERIFY_EVERY
                ) and now - latest.started_at > timedelta(minutes=5):
                    job = jobs.enqueue(
                        session,
                        type="backup.verify",
                        params={"backup_id": latest.id},
                        project_id=ds.project_id,
                        data_source_id=ds.id,
                        device_id=ds.device_id,
                    )
                    enqueued.append(job.id)
            session.commit()

        if not jobs.active_job(session, "backup.prune") and _redis_due("backups:sched:prune", PRUNE_EVERY, now):
            enqueued.append(jobs.enqueue(session, type="backup.prune", params={}).id)
        if _copy_target is not None and not jobs.active_job(session, "backup.copy"):
            pending = session.scalar(select(func.count()).select_from(BackupCopy).where(BackupCopy.status == "pending"))
            if pending and _redis_due("backups:sched:copy", timedelta(minutes=10), now):
                enqueued.append(jobs.enqueue(session, type="backup.copy", params={}).id)
        if not jobs.active_job(session, "backup.platform_snapshot"):
            last_platform = session.scalar(
                select(Backup).where(Backup.scope == "platform").order_by(Backup.started_at.desc())
            )
            due = last_platform is None or now - last_platform.started_at >= PLATFORM_EVERY
            if last_platform is not None and last_platform.status == "failed":
                due = now - last_platform.started_at >= timedelta(hours=1)
            if due:
                enqueued.append(start_platform_snapshot(session, None).id)
        session.commit()
    finally:
        session.close()
    for job_id in enqueued:
        jobs.dispatch(job_id)
    return enqueued


def expire_project_backups(db: Session, project_id: str) -> None:
    """A deleted project's backups (incl. pinned) are kept for DELETED_KEEP, then purged."""
    until = utcnow() + DELETED_KEEP
    for backup in db.scalars(select(Backup).where(Backup.project_id == project_id)):
        if backup.expires_at is None or backup.expires_at > until:
            backup.expires_at = until
