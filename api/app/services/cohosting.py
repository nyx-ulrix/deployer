"""Co-hosting control plane (docs/COHOSTING.md): replicas, the initial copy job, conflicts and history.

The data plane (reading and applying changes) is `source_sync.py`.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.errors import ApiError, not_found
from app.models import (
    DataSource,
    Device,
    ProjectMember,
    SourceReplica,
    SyncConflict,
    SyncVersion,
    role_rank,
    utcnow,
)
from app.serializers import iso
from app.services import device_moves, device_rpc, jobs, source_sync

log = logging.getLogger(__name__)

COPY_JOB = "replica.copy"
SYNC_METHODS = ("sync.position", "sync.sql_changes", "sync.sql_apply", "sync.mongo_changes", "sync.mongo_apply")

# =============================================================================================
# who may co-host
# =============================================================================================


def member_can_cohost(member: ProjectMember | None) -> bool:
    return bool(member and member.can_cohost and role_rank(member.role) >= role_rank("developer"))


def eligibility(db: Session, project, user) -> dict:
    """For the dashboard: offer "Copy to my device" only when `offer` is true (docs/COHOSTING.md
    "Dashboard"). Lists only the caller's own devices."""
    from app.services import devices

    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
    )
    can = member_can_cohost(member)
    out = []
    for device in db.scalars(select(Device).where(Device.owner_id == user.id).order_by(Device.name)):
        if device.status != "active" or "database_host" not in (device.roles or []):
            continue
        out.append(
            {
                "id": device.id,
                "name": device.name,
                "online": device_rpc.is_online(device.id),
                "granted": devices.placement_problem(db, device, project) is None,
            }
        )
    return {"can_cohost": can, "devices": out, "offer": can and bool(out)}


def pause_member_replicas(db: Session, project_id: str, user_id: str, reason: str) -> int:
    """Stops sending data to a member's devices (co-hosting switched off, demoted or removed)."""
    rows = db.scalars(
        select(SourceReplica)
        .join(DataSource, DataSource.id == SourceReplica.data_source_id)
        .join(Device, Device.id == SourceReplica.device_id)
        .where(DataSource.project_id == project_id, Device.owner_id == user_id, SourceReplica.status != "paused")
    ).all()
    for rep in rows:
        rep.status = "paused"
        rep.error = reason
    return len(rows)


# =============================================================================================
# serialization
# =============================================================================================


def open_conflict_counts(db: Session, replica_ids: list[str]) -> dict[str, int]:
    if not replica_ids:
        return {}
    return dict(
        db.execute(
            select(SyncConflict.replica_id, func.count())
            .where(SyncConflict.replica_id.in_(replica_ids), SyncConflict.status == "open")
            .group_by(SyncConflict.replica_id)
        ).all()
    )


def replica_out(db: Session, rep: SourceReplica, *, open_conflicts: int | None = None) -> dict:
    device = db.get(Device, rep.device_id)
    if open_conflicts is None:
        open_conflicts = open_conflict_counts(db, [rep.id]).get(rep.id, 0)
    return {
        "id": rep.id,
        "data_source_id": rep.data_source_id,
        "device_id": rep.device_id,
        "device_name": device.name if device else None,
        "owner_id": device.owner_id if device else None,
        "online": device_rpc.is_online(rep.device_id),
        "status": rep.status,
        "lag_seconds": rep.lag_seconds,
        "last_synced_at": iso(rep.last_synced_at),
        "error": rep.error,
        "warnings": rep.warnings or [],
        "open_conflicts": open_conflicts,
        "created_at": iso(rep.created_at),
    }


def source_replicas(db: Session, data_source_id: str) -> list[dict]:
    reps = list(
        db.scalars(
            select(SourceReplica)
            .where(SourceReplica.data_source_id == data_source_id)
            .order_by(SourceReplica.created_at)
        )
    )
    counts = open_conflict_counts(db, [r.id for r in reps])
    return [replica_out(db, r, open_conflicts=counts.get(r.id, 0)) for r in reps]


# =============================================================================================
# initial copy (job `replica.copy`)
# =============================================================================================


def allocate_offset(db: Session, rep: SourceReplica) -> int:
    """The device's MariaDB auto_increment offset: shared by all its copies, unique per device."""
    same = db.scalar(
        select(SourceReplica.id_offset).where(
            SourceReplica.device_id == rep.device_id, SourceReplica.id_offset.is_not(None)
        )
    )
    if same:
        return int(same)
    used = set(
        db.scalars(
            select(SourceReplica.id_offset).where(
                SourceReplica.id_offset.is_not(None), SourceReplica.device_id != rep.device_id
            )
        )
    )
    for offset in range(2, source_sync.AUTO_INCREMENT_STEP + 1):
        if offset not in used:
            return offset
    raise ApiError(
        409,
        "too_many_cohosts",
        f"At most {source_sync.AUTO_INCREMENT_STEP - 1} co-host devices can hold database copies",
    )


def _drop_device_copy(device_id: str, kind: str, database: str) -> None:
    try:
        device_rpc.call(device_id, "datasource.drop", {"kind": kind, "database_name": database}, timeout=120)
    except ApiError as exc:
        if exc.code != "not_hosted":
            raise


@jobs.job_handler(COPY_JOB)
def run_copy(ctx: jobs.JobContext) -> dict:
    session = ctx.db()
    created = False
    rep_id = str(ctx.params.get("replica_id") or "")
    try:
        rep = session.get(SourceReplica, rep_id)
        ds = session.get(DataSource, rep.data_source_id) if rep else None
        if rep is None or ds is None:
            raise jobs.JobError("The copy was removed")
        if ds.mode != "managed" or ds.device_id is not None or ds.deleted_at is not None:
            raise ApiError(409, "replica_unsupported", "Only managed databases on the main server can be copied")
        device_id, kind, database = rep.device_id, ds.kind, ds.database_name
        rep.status = "copying"
        rep.error = None
        rep.id_offset = rep.id_offset or allocate_offset(session, rep)
        offset = rep.id_offset
        if ctx.params.get("recopy"):
            # A fresh copy of the main server: open conflicts end with the main server's version; the
            # kept versions describe the old copy and would mislead conflict/echo detection.
            for conflict in session.scalars(
                select(SyncConflict).where(SyncConflict.replica_id == rep.id, SyncConflict.status == "open")
            ):
                conflict.status, conflict.resolution = "resolved", "primary"
                conflict.resolved_json, conflict.resolved_at = conflict.primary_json, utcnow()
                conflict.resolved_by_id = ctx.created_by_id
            session.execute(delete(SyncVersion).where(SyncVersion.replica_id == rep.id))
        session.commit()

        ctx.progress(0.05, "Preparing the main server", force=True)
        if kind == "sql":
            source_sync.ensure_mariadb_settings(offset=source_sync.PRIMARY_ID_OFFSET)
        # Taken before the dump: changes made while copying are synced afterwards (no gap).
        position_primary = source_sync.local_position(kind, database)

        ctx.progress(0.1, "Creating the database on the device", force=True)
        if ctx.params.get("recopy"):
            _drop_device_copy(device_id, kind, database)
        device_rpc.call(device_id, "datasource.provision", {"kind": kind, "database_name": database}, timeout=90)
        created = True

        ctx.progress(0.2, "Copying data", force=True)
        dump = device_moves.dump_source(ds)
        try:
            ctx.check_cancelled()
            ctx.progress(0.5, "Restoring data on the device", force=True)
            target = DataSource(
                id=f"{ds.id}-replica",
                project_id=ds.project_id,
                name=ds.name,
                kind=kind,
                engine=ds.engine,
                mode="managed",
                database_name=database,
                config_encrypted="",
                device_id=device_id,
            )
            counts = device_moves.restore_into(target, dump) or {}
        finally:
            dump.unlink(missing_ok=True)

        ctx.progress(0.9, "Starting the sync", force=True)
        params: dict[str, Any] = {"kind": kind, "database_name": database}
        if kind == "sql":
            params["auto_increment"] = {"increment": source_sync.AUTO_INCREMENT_STEP, "offset": offset}
        position_replica = device_rpc.call(device_id, "sync.position", params, timeout=60)

        rep = session.get(SourceReplica, rep_id)
        if rep is None:
            raise jobs.JobError("The copy was removed while copying")
        rep.position_primary = position_primary
        rep.position_replica = position_replica
        rep.status = "syncing"
        rep.error = None
        rep.last_synced_at = utcnow()
        rep.lag_seconds = 0.0
        session.commit()
        created = False
        return {
            "replica_id": rep_id,
            "database_name": database,
            "rows": counts.get("rows"),
            "documents": counts.get("documents"),
        }
    except BaseException as exc:
        session.rollback()
        message = exc.message if isinstance(exc, ApiError) else jobs.redact_error(str(exc))
        if created:
            try:
                _drop_device_copy(device_id, kind, database)
            except Exception:  # noqa: BLE001
                log.warning("could not drop the partial copy on device %s", device_id, exc_info=True)
        rep = session.get(SourceReplica, rep_id)
        if rep is not None:
            rep.status = "error"
            rep.error = f"Copy failed: {message}"[:2000]
            session.commit()
        raise
    finally:
        session.close()


# =============================================================================================
# conflicts: diff, suggestion, resolution, history
# =============================================================================================

_MISSING = object()


def _field(row: dict | None, name: str) -> Any:
    return _MISSING if row is None or name not in row else row[name]


def _eq(a: Any, b: Any) -> bool:
    if a is _MISSING or b is _MISSING:
        return a is b
    return source_sync.row_hash({"v": a}) == source_sync.row_hash({"v": b})


def diff(conflict: SyncConflict) -> tuple[list[dict], dict | None]:
    """Field-level diff against the base, and a merge of fields changed on only one side (None when
    a field changed differently on both sides, a side deleted the row, or the base is unknown)."""
    base, primary, replica = conflict.base_json, conflict.primary_json, conflict.replica_json
    fields = []
    mergeable = base is not None and primary is not None and replica is not None
    merged = dict(base or {})
    for name in sorted(set(base or {}) | set(primary or {}) | set(replica or {})):
        b, p, r = _field(base, name), _field(primary, name), _field(replica, name)
        if base is None:
            changed_by = "both" if not _eq(p, r) else None
        else:
            pc, rc = not _eq(p, b), not _eq(r, b)
            changed_by = "both" if pc and rc else "primary" if pc else "replica" if rc else None
        if changed_by is None:
            continue

        def show(v: Any) -> Any:
            return None if v is _MISSING else v

        fields.append({"name": name, "base": show(b), "primary": show(p), "replica": show(r), "changed_by": changed_by})
        pick = p if changed_by == "primary" else r if changed_by == "replica" else (p if _eq(p, r) else _MISSING)
        if changed_by == "both" and not _eq(p, r):
            mergeable = False
        if pick is _MISSING:
            merged.pop(name, None)
        else:
            merged[name] = pick
    return fields, (merged if mergeable else None)


def conflict_out(conflict: SyncConflict, *, detail: bool = True) -> dict:
    out = {
        "id": conflict.id,
        "replica_id": conflict.replica_id,
        "table": conflict.table_name,
        "key": conflict.key_json,
        "status": conflict.status,
        "op_primary": conflict.op_primary,
        "op_replica": conflict.op_replica,
        "primary_changed_at": iso(conflict.primary_changed_at),
        "replica_changed_at": iso(conflict.replica_changed_at),
        "base": conflict.base_json,
        "primary": conflict.primary_json,
        "replica": conflict.replica_json,
        "resolution": conflict.resolution,
        "resolved": conflict.resolved_json,
        "resolved_by_id": conflict.resolved_by_id,
        "resolved_at": iso(conflict.resolved_at),
        "created_at": iso(conflict.created_at),
        "updated_at": iso(conflict.updated_at),
    }
    if detail:
        out["fields"], out["suggested"] = diff(conflict)
    return out


def _check_value(kind: str, key: dict, value: Any) -> dict | None:
    """A full row / document for `key`, or None (= delete). Key fields must match the conflict's key."""
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise ApiError(422, "validation_error", "value must be an object (the whole row or document) or null")
    value = dict(value)
    for name, key_value in key.items():
        if name in value and not _eq(value[name], key_value):
            raise ApiError(422, "validation_error", f"value must keep the key field {name!r}")
        value[name] = key_value
    return value


def write_both(
    db: Session,
    rep: SourceReplica,
    ds: DataSource,
    table: str,
    key: dict,
    value: dict | None,
    *,
    origin: str,
    user_id: str | None,
) -> None:
    """Writes one row/document to the device copy and the main server (unconditionally), without
    echo, and records the version. Device first: when it is offline nothing changes (503)."""
    if not device_rpc.is_online(rep.device_id):
        raise device_rpc.offline_error("The co-host device is offline; try again when it is connected")
    change = {
        "table": table,
        "key": key,
        "op": "delete" if value is None else "update",
        "before": None,
        "after": value,
        "ts": int(utcnow().timestamp()),
        "force": True,
    }
    lock = source_sync.replica_lock(rep.id)
    if not lock.acquire(wait=30):
        raise ApiError(409, "sync_busy", "The sync is busy; try again in a moment")
    try:
        primary, device = source_sync.sides_for(rep, ds)
        for side in (device, primary):
            outcome = side.apply([change])[0]
            if outcome.get("result") != "applied":
                raise ApiError(409, "write_rejected", outcome.get("reason") or "The value could not be written")
        source_sync.add_version(db, rep.id, table, key, value, origin, user_id)
        db.commit()  # before the lock is released: the next round must see this version
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass


def resolve(db: Session, conflict: SyncConflict, choice: str, value: Any, user_id: str) -> SyncConflict:
    rep = db.get(SourceReplica, conflict.replica_id)
    ds = db.get(DataSource, rep.data_source_id)
    if conflict.status != "open":
        raise ApiError(409, "conflict_resolved", "This conflict is already resolved")
    if choice == "primary":
        chosen = conflict.primary_json
    elif choice == "replica":
        chosen = conflict.replica_json
    else:
        chosen = _check_value(ds.kind, conflict.key_json, value)
    write_both(db, rep, ds, conflict.table_name, conflict.key_json, chosen, origin="resolution", user_id=user_id)
    conflict.status = "resolved"
    conflict.resolution = choice
    conflict.resolved_json = chosen
    conflict.resolved_by_id = user_id
    conflict.resolved_at = utcnow()
    return conflict


def history(db: Session, replica_ids: list[str], table: str, key: dict, limit: int = 200) -> list[dict]:
    """Kept versions and resolved conflicts of one key, newest first."""
    if not replica_ids:
        return []
    kh = source_sync.key_hash(key)
    items = [
        {
            "type": "version",
            "id": str(v.id),
            "replica_id": v.replica_id,
            "origin": v.origin,
            "value": v.json,
            "user_id": v.user_id,
            "at": iso(v.synced_at),
        }
        for v in db.scalars(
            select(SyncVersion)
            .where(SyncVersion.replica_id.in_(replica_ids), SyncVersion.table_name == table, SyncVersion.key_hash == kh)
            .order_by(SyncVersion.id.desc())
            .limit(limit)
        )
    ]
    items += [
        {
            "type": "conflict",
            "id": c.id,
            "replica_id": c.replica_id,
            "origin": c.resolution,
            "value": c.resolved_json,
            "primary": c.primary_json,
            "replica": c.replica_json,
            "user_id": c.resolved_by_id,
            "at": iso(c.resolved_at),
        }
        for c in db.scalars(
            select(SyncConflict).where(
                SyncConflict.replica_id.in_(replica_ids),
                SyncConflict.table_name == table,
                SyncConflict.key_hash == kh,
                SyncConflict.status == "resolved",
            )
        )
    ]
    return sorted(items, key=lambda i: (i["at"] or "", i["type"] == "version"), reverse=True)[:limit]


def restore_version(db: Session, version: SyncVersion, user_id: str) -> SyncConflict | None:
    """Applies a kept version to both copies; an open conflict on that key is resolved by it."""
    rep = db.get(SourceReplica, version.replica_id)
    ds = db.get(DataSource, rep.data_source_id)
    conflict = db.scalar(
        select(SyncConflict).where(
            SyncConflict.replica_id == rep.id,
            SyncConflict.table_name == version.table_name,
            SyncConflict.key_hash == version.key_hash,
            SyncConflict.status == "open",
        )
    )
    write_both(db, rep, ds, version.table_name, version.key_json, version.json, origin="restore", user_id=user_id)
    if conflict is not None:
        conflict.status = "resolved"
        conflict.resolution = "manual"
        conflict.resolved_json = version.json
        conflict.resolved_by_id = user_id
        conflict.resolved_at = utcnow()
    return conflict


def get_conflict(db: Session, data_source_id: str, conflict_id: str) -> SyncConflict:
    conflict = db.get(SyncConflict, conflict_id)
    rep = db.get(SourceReplica, conflict.replica_id) if conflict else None
    if conflict is None or rep is None or rep.data_source_id != data_source_id:
        raise not_found("Conflict")
    return conflict


# =============================================================================================
# schema changes made through Deployer reach the copies too
# =============================================================================================


def fan_out_schema_change(ds: DataSource, op: str, args: dict) -> None:
    """`table.create|drop` / `collection.create|drop` done on the main server: repeat on every copy.
    A copy that can't take it gets a warning (its next sync reports the table difference)."""
    from app.db import get_sessionmaker

    session = get_sessionmaker()()
    try:
        reps = list(
            session.scalars(
                select(SourceReplica).where(
                    SourceReplica.data_source_id == ds.id, SourceReplica.status.in_(("syncing", "error", "paused"))
                )
            )
        )
        for rep in reps:
            try:
                device_rpc.call(
                    rep.device_id,
                    "datasource.call",
                    {
                        "kind": ds.kind,
                        "database_name": ds.database_name,
                        "source_name": ds.name,
                        "op": op,
                        "args": args,
                    },
                    timeout=60,
                )
            except ApiError as exc:
                target = args.get("name") or (args.get("spec") or {}).get("name")
                rep.warnings = [
                    *(rep.warnings or []),
                    {"table": target, "message": f"Schema change {op} was not applied on this copy: {exc.message}"},
                ]
        session.commit()
    finally:
        session.close()
