"""Moving a managed database between hosts (main server <-> host devices), docs/DEVICES.md "Rules".

`POST /projects/{id}/data-sources/{sid}/move` creates a `jobs` row (`type = "device.move"`) and runs
it in a background thread of the API process (the process that receives device uploads):

1. safety snapshot on the source when the backups executor is available (`pre_move`),
2. dump the source's data (tables + rows / collections + documents, the export `data` format) —
   locally or on the source device (`datasource.export` -> transfer upload),
3. provision a database on the target and restore the dump there (`datasource.import` on devices),
4. switch `data_sources.device_id` / `database_name` / display config to the new copy,
5. keep the old copy for 7 days: a cleanup entry is scheduled and dropped later by
   `run_due_cleanups()` (worker maintenance loop).

Writes that reach the old copy while the move runs are not carried over; moves are meant for quiet
periods (the dashboard says so).
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.crypto import decrypt_json, encrypt_json
from app.db import get_sessionmaker
from app.errors import ApiError
from app.models import DataSource, Job, Project, User, new_id, utcnow
from app.redis_client import get_redis
from app.serializers import iso
from app.services import backups, connections, device_rpc, jobs, provisioning

log = logging.getLogger(__name__)

MOVE_JOB = "device.move"
KEEP_OLD_COPY_DAYS = 7
CLEANUP_KEY = "device:cleanup:moved_copies"
LONG_TIMEOUT = 6 * 3600


def create_move_job(db: Session, ds: DataSource, target_device_id: str | None, user: User) -> Job:
    job = Job(
        id=new_id(),
        type=MOVE_JOB,
        status="running",
        progress=0.0,
        message="Starting move",
        params={"from_device_id": ds.device_id, "to_device_id": target_device_id},
        project_id=ds.project_id,
        data_source_id=ds.id,
        device_id=target_device_id or ds.device_id,
        created_by_id=user.id,
        started_at=utcnow(),
    )
    db.add(job)
    db.flush()
    return job


def start_move(job_id: str) -> threading.Thread:
    thread = threading.Thread(target=run_move, args=(job_id,), name=f"device-move-{job_id[:8]}", daemon=True)
    thread.start()
    return thread


def _update(job_id: str, **fields: Any) -> None:
    session = get_sessionmaker()()
    try:
        job = session.get(Job, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------------------------
# steps
# ---------------------------------------------------------------------------------------------


def dump_source(ds: DataSource, *, timeout: float = LONG_TIMEOUT) -> Path:
    """Writes the source's data entry (transfer.py format) to a local gzip JSON file."""
    from app.services import transfer

    if ds.device_id:
        transfer_id = device_rpc.create_transfer(ds.device_id, "put")
        try:
            device_rpc.call(
                ds.device_id,
                "datasource.export",
                {
                    "kind": ds.kind,
                    "database_name": ds.database_name,
                    "source_name": ds.name,
                    "transfer_id": transfer_id,
                },
                timeout=timeout,
            )
            src = device_rpc.claim_upload(transfer_id)
            fd, out = tempfile.mkstemp(prefix="deployer-move-", suffix=".json.gz")
            os.close(fd)
            device_rpc.move_file(src, out)  # the transfer store and /tmp are different mounts
            return Path(out)
        finally:
            device_rpc.finish_transfer(transfer_id)
    fd, out = tempfile.mkstemp(prefix="deployer-move-", suffix=".json.gz")
    os.close(fd)
    try:
        with gzip.open(out, "wt", encoding="utf-8", compresslevel=6) as fh:
            transfer.write_source_data(fh, ds)
    except BaseException:
        Path(out).unlink(missing_ok=True)
        raise
    return Path(out)


def provision_target(project: Project, ds: DataSource, target_device_id: str | None) -> tuple[str, dict]:
    """Creates an empty database for `ds` on the target host. Returns (database_name, stored config)."""
    if target_device_id:
        database, config, _ = provisioning.provision_on_device(project, ds.kind, target_device_id, ds.database_name)
        return database, config
    username, password = provisioning.generate_username(), provisioning.generate_password()
    if ds.kind == "sql":
        database = provisioning._pick_database_name(
            project.slug, ds.database_name, provisioning.mariadb_database_exists
        )
        return database, provisioning.create_mariadb_database(database, username, password)
    database = provisioning._pick_database_name(project.slug, ds.database_name, provisioning.mongo_database_exists)
    return database, provisioning.create_mongo_database(database, username, password)


def restore_into(target: DataSource, dump: Path, *, timeout: float = LONG_TIMEOUT) -> dict:
    from app.services import transfer

    if target.device_id:
        fd, staged = tempfile.mkstemp(prefix="deployer-move-stage-", suffix=".json.gz")
        os.close(fd)
        with open(dump, "rb") as src, open(staged, "wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
        transfer_id = device_rpc.create_transfer(target.device_id, "get", source_path=staged)
        try:
            return device_rpc.call(
                target.device_id,
                "datasource.import",
                {
                    "kind": target.kind,
                    "database_name": target.database_name,
                    "source_name": target.name,
                    "transfer_id": transfer_id,
                },
                timeout=timeout,
            )
        finally:
            device_rpc.finish_transfer(transfer_id)
    with gzip.open(dump, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    rows, documents = transfer.restore_data(target, data)
    return {"rows": rows, "documents": documents}


def drop_copy(kind: str, device_id: str | None, database: str, config_encrypted: str | None) -> None:
    if device_id:
        provisioning.drop_on_device(device_id, kind, database)
        return
    username = None
    if config_encrypted:
        try:
            username = decrypt_json(config_encrypted).get("username")
        except Exception:  # noqa: BLE001
            username = None
    if kind == "sql":
        provisioning.drop_mariadb_database(database, username)
    else:
        provisioning.drop_mongo_database(database, username)


def _safety_snapshot(data_source_id: str, user_id: str | None) -> None:
    """`pre_move` snapshot on the current host (docs/BACKUPS.md "Safety snapshots"), when the source's
    policy asks for one. A failed snapshot aborts the move before anything changed."""
    session = get_sessionmaker()()
    try:
        ds = session.get(DataSource, data_source_id)
        if ds is not None:
            backups.safety_snapshot(session, ds, trigger="pre_move", user_id=user_id)
    finally:
        session.close()


def run_move(job_id: str) -> None:
    # The job row is `running` from the start; heartbeat so the worker's `jobs.recover_stale()` doesn't
    # fail a long move (it treats a running job without a heartbeat as a crashed worker).
    with jobs.Heartbeat(job_id):
        _run_move(job_id)


def _run_move(job_id: str) -> None:
    session = get_sessionmaker()()
    dump: Path | None = None
    created: tuple[str | None, str, str] | None = None  # (device_id, kind, database) of the new copy
    new_config: dict | None = None
    try:
        job = session.get(Job, job_id)
        ds = session.get(DataSource, job.data_source_id) if job else None
        if job is None or ds is None:
            return
        project = session.get(Project, ds.project_id)
        target = (job.params or {}).get("to_device_id")
        source_device = ds.device_id
        session.commit()

        _update(job_id, progress=0.05, message="Taking a safety snapshot")
        _safety_snapshot(ds.id, job.created_by_id)

        _update(job_id, progress=0.15, message="Copying data from the current host")
        dump = dump_source(ds)

        _update(job_id, progress=0.5, message="Creating the database on the new host")
        database, new_config = provision_target(project, ds, target)
        created = (target, ds.kind, database)

        _update(job_id, progress=0.6, message="Restoring data on the new host")
        # Device configs carry no password; main-server configs are stored encrypted as usual.
        stored_config = new_config
        target_ds = DataSource(
            id=f"{ds.id}-move",
            project_id=ds.project_id,
            name=ds.name,
            kind=ds.kind,
            engine=ds.engine,
            mode="managed",
            database_name=database,
            config_encrypted=encrypt_json(stored_config),
            device_id=target,
        )
        counts = restore_into(target_ds, dump) or {}

        _update(job_id, progress=0.9, message="Switching over")
        ds = session.get(DataSource, ds.id)
        old = {
            "device_id": source_device,
            "kind": ds.kind,
            "database_name": ds.database_name,
            "config_encrypted": None if source_device else ds.config_encrypted,
        }
        ds.device_id = target
        ds.database_name = database
        ds.config_encrypted = encrypt_json(stored_config)
        ds.status = "ok"
        ds.status_message = "Moved"
        ds.last_checked_at = utcnow()
        session.commit()
        created = None
        connections.invalidate(ds.id)
        connections.invalidate(target_ds.id)
        expires = utcnow() + timedelta(days=KEEP_OLD_COPY_DAYS)
        schedule_cleanup(old, due=time.time() + KEEP_OLD_COPY_DAYS * 86400)
        _update(
            job_id,
            status="succeeded",
            progress=1.0,
            message="Moved",
            finished_at=utcnow(),
            result={
                "from_device_id": source_device,
                "to_device_id": target,
                "database_name": database,
                "rows": counts.get("rows"),
                "documents": counts.get("documents"),
                "old_copy_expires_at": iso(expires),
            },
        )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        message = (
            exc.message if isinstance(exc, ApiError) else connections.redact(str(getattr(exc, "orig", None) or exc))
        )
        if not isinstance(exc, ApiError):
            log.exception("move job %s failed", job_id)
        if created is not None:
            device_id, kind, database = created
            try:
                drop_copy(kind, device_id, database, encrypt_json(new_config) if new_config else None)
            except Exception:  # noqa: BLE001
                log.warning("could not drop partial copy %s", database, exc_info=True)
        try:
            _update(job_id, status="failed", error=message[:2000], message="Move failed", finished_at=utcnow())
        except Exception:  # noqa: BLE001
            log.exception("could not record move failure")
    finally:
        session.close()
        if dump is not None:
            dump.unlink(missing_ok=True)


# ---------------------------------------------------------------------------------------------
# delayed cleanup of old copies
# ---------------------------------------------------------------------------------------------


def schedule_cleanup(entry: dict, due: float) -> None:
    try:
        get_redis().zadd(CLEANUP_KEY, {json.dumps(entry, sort_keys=True): due})
    except Exception:  # noqa: BLE001
        log.warning("could not schedule cleanup of %s", entry.get("database_name"), exc_info=True)


def drop_copies_on_device(device_id: str) -> int:
    """Drops the kept old copies on a device right away (the device is being removed)."""
    r = get_redis()
    dropped = 0
    for member in r.zrange(CLEANUP_KEY, 0, -1):
        try:
            entry = json.loads(member)
        except ValueError:
            continue
        if entry.get("device_id") != device_id:
            continue
        try:
            drop_copy(entry["kind"], device_id, entry["database_name"], None)
            r.zrem(CLEANUP_KEY, member)
            dropped += 1
        except ApiError as exc:
            if exc.code == "not_hosted":
                r.zrem(CLEANUP_KEY, member)
            else:
                log.warning("could not drop old copy %s on removed device: %s", entry.get("database_name"), exc.message)
    return dropped


def run_due_cleanups(now: float | None = None, limit: int = 20) -> int:
    """Drops old copies whose keep period ended. Offline devices are retried an hour later."""
    now = time.time() if now is None else now
    r = get_redis()
    dropped = 0
    for member in r.zrangebyscore(CLEANUP_KEY, "-inf", now, start=0, num=limit):
        if not r.zrem(CLEANUP_KEY, member):
            continue  # another worker took it
        try:
            entry = json.loads(member)
            drop_copy(entry["kind"], entry.get("device_id"), entry["database_name"], entry.get("config_encrypted"))
            dropped += 1
        except ApiError as exc:
            if exc.code in ("device_offline", "device_timeout"):
                r.zadd(CLEANUP_KEY, {member: now + 3600})
            else:
                log.warning("dropping old copy failed: %s", exc.message)
        except Exception:  # noqa: BLE001
            log.warning("dropping old copy failed", exc_info=True)
            r.zadd(CLEANUP_KEY, {member: now + 3600})
    return dropped
