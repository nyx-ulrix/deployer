"""The seam between backup orchestration and the machine that hosts a database.

`app.services.backups` (always on the main server) owns every platform row - backups, segments,
copies, policies, schema snapshots - and calls a `BackupExecutor` only for byte-level work on the
host that runs the database:

- `LocalExecutor` - this installation's own managed MariaDB/MongoDB and `BACKUP_DIR` (/backups).
  It is used by the main server for `device_id = None`, and by a host device to serve RPCs.
- a device executor - registered by the host-devices code with `register_device_executor_factory`;
  it forwards the same calls to the device (e.g. `jobs.run` with `executor.<method>` job types that
  the device answers with `run_local_call`).

Artifact refs are relative paths inside the host's backup store, e.g.
`<data_source_id>/snapshots/<backup_id>.bin`. Bytes are always gzip-compressed and encrypted
(`backup_crypto`) before they touch disk, so a store never holds plaintext.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable

ProgressFn = Callable[[float | None, str | None], None]

_REF_RE = re.compile(r"^[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_.\-]+)*$")


def _noop_progress(fraction: float | None = None, message: str | None = None) -> None:
    return None


@runtime_checkable
class BackupExecutor(Protocol):
    """Byte-level backup work on the host of a database. All methods may block for a long time."""

    def snapshot(
        self, *, kind: str, engine: str, database_name: str, artifact_ref: str, on_progress: ProgressFn
    ) -> dict:
        """Dump `database_name` into the encrypted artifact `artifact_ref`.

        Returns `{size_bytes, sha256, consistent_point, row_counts}`; `consistent_point` is
        `{binlog_file, binlog_pos, gtid, consistent_at}` (MariaDB) or
        `{oplog_ts_start: [t, i], oplog_ts_end: [t, i], consistent_at}` (MongoDB); `consistent_at`
        is an ISO UTC time from which point-in-time replay can start.
        """
        ...

    def archive_logs(
        self, *, kind: str, engine: str, database_name: str, since_point: dict | None, artifact_ref_prefix: str
    ) -> list[dict]:
        """Archive closed binlog files / oplog entries of `database_name` newer than `since_point`.

        Returns ordered segments `{id, ref | None, start_at, end_at, start_point, end_point,
        size_bytes, sha256}` (ISO UTC times). `ref = None` means "nothing for this database in that
        range" - the orchestrator only extends its recorded coverage. `since_point` is the
        `end_point` of the newest recorded segment, or `{"after": <snapshot consistent_point>}`.
        """
        ...

    def restore(
        self,
        *,
        kind: str,
        engine: str,
        target_database_name: str,
        snapshot_ref: str,
        segments: list[dict],
        until: datetime | None,
        on_progress: ProgressFn,
        source_database_name: str,
        consistent_point: dict | None,
    ) -> dict:
        """Restore a snapshot (+ replay `segments` `{ref, start_point, end_point}` up to `until`)
        into a temporary database, then swap it into `target_database_name` (which may exist and be
        live - the managed user's grants are kept). Returns `{row_counts, swap}`."""
        ...

    def verify(self, *, kind: str, engine: str, snapshot_ref: str, expected_row_counts: dict | None) -> dict:
        """Restore into a temporary `verify_*` database, compare row counts, always drop it.
        Returns `{ok, row_counts, mismatches, message}`."""
        ...

    def delete_artifact(self, ref: str) -> None: ...

    def artifact_path(self, ref: str) -> Path:
        """Local filesystem path of an artifact. Raises for remote executors."""
        ...

    def open_artifact(self, ref: str) -> IO[bytes]:
        """Readable binary stream of the (encrypted) artifact."""
        ...

    def artifact_exists(self, ref: str) -> bool: ...

    def ensure_database(self, *, kind: str, database_name: str) -> dict:
        """Create an empty database + dedicated user (restore as a new source). Returns the
        connection config to store for the new DataSource (`provisioning` shape)."""
        ...

    def storage_stats(self) -> dict:
        """`{used_bytes, free_bytes}` of the backup store."""
        ...


class RemoteArtifactError(RuntimeError):
    pass


def check_ref(ref: str) -> str:
    if not isinstance(ref, str) or len(ref) > 500 or not _REF_RE.fullmatch(ref) or ".." in ref.split("/"):
        raise ValueError(f"Invalid artifact ref: {ref!r}")
    return ref


def backup_root() -> Path:
    return Path(os.environ.get("BACKUP_DIR") or "/backups")


class LocalExecutor:
    """Runs dump/restore tools against this installation's managed databases (see backup_engine)."""

    def __init__(self, root: Path | None = None):
        self._root = root

    @property
    def root(self) -> Path:
        return self._root or backup_root()

    def artifact_path(self, ref: str) -> Path:
        return self.root / check_ref(ref)

    def open_artifact(self, ref: str) -> IO[bytes]:
        return open(self.artifact_path(ref), "rb")

    def artifact_exists(self, ref: str) -> bool:
        return self.artifact_path(ref).is_file()

    def delete_artifact(self, ref: str) -> None:
        path = self.artifact_path(ref)
        path.unlink(missing_ok=True)

    def storage_stats(self) -> dict:
        import shutil

        root = self.root
        used = 0
        if root.is_dir():
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    try:
                        used += os.path.getsize(os.path.join(dirpath, name))
                    except OSError:
                        pass
        try:
            free = shutil.disk_usage(root if root.exists() else root.parent).free
        except OSError:
            free = None
        return {"used_bytes": used, "free_bytes": free}

    def snapshot(self, *, kind, engine, database_name, artifact_ref, on_progress=_noop_progress) -> dict:
        from app.services import backup_engine

        path = self.artifact_path(artifact_ref)
        if kind == "sql":
            return backup_engine.mariadb_snapshot(database_name, path, on_progress)
        return backup_engine.mongo_snapshot(database_name, path, on_progress)

    def archive_logs(self, *, kind, engine, database_name, since_point, artifact_ref_prefix) -> list[dict]:
        from app.services import backup_engine

        check_ref(artifact_ref_prefix.rstrip("/"))
        if kind == "sql":
            return backup_engine.mariadb_archive_logs(database_name, since_point, artifact_ref_prefix, self.root)
        return backup_engine.mongo_archive_logs(database_name, since_point, artifact_ref_prefix, self.root)

    def restore(
        self,
        *,
        kind,
        engine,
        target_database_name,
        snapshot_ref,
        segments,
        until,
        on_progress=_noop_progress,
        source_database_name,
        consistent_point=None,
    ) -> dict:
        from app.services import backup_engine

        seg_paths = [{**seg, "path": self.artifact_path(seg["ref"])} for seg in segments if seg.get("ref")]
        fn = backup_engine.mariadb_restore if kind == "sql" else backup_engine.mongo_restore
        return fn(
            snapshot_path=self.artifact_path(snapshot_ref),
            segments=seg_paths,
            target=target_database_name,
            source=source_database_name,
            consistent_point=consistent_point or {},
            until=until,
            on_progress=on_progress,
        )

    def verify(self, *, kind, engine, snapshot_ref, expected_row_counts) -> dict:
        from app.services import backup_engine

        fn = backup_engine.mariadb_verify if kind == "sql" else backup_engine.mongo_verify
        return fn(self.artifact_path(snapshot_ref), expected_row_counts)

    def ensure_database(self, *, kind, database_name) -> dict:
        from app.services import backup_engine

        return backup_engine.ensure_database(kind, database_name)

    def platform_snapshot(self, *, artifact_ref, on_progress=_noop_progress) -> dict:
        """Main server only: snapshot of the platform metadata database."""
        from app.config import get_settings
        from app.services import backup_engine

        return backup_engine.mariadb_snapshot(
            get_settings().mariadb_database, self.artifact_path(artifact_ref), on_progress
        )


# ---------------------------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------------------------

_local = LocalExecutor()
_device_factory: Callable[[str], BackupExecutor] | None = None
_remote_job_dispatcher: Callable[[Any], None] | None = None


def local_executor() -> LocalExecutor:
    return _local


def register_device_executor_factory(factory: Callable[[str], BackupExecutor] | None) -> None:
    """`factory(device_id) -> BackupExecutor` for databases hosted on a device."""
    global _device_factory
    _device_factory = factory


def register_remote_job_dispatcher(fn: Callable[[Any], None] | None) -> None:
    """`fn(job: models.Job)`: run a job on its device. It should block until the device finished and
    record the outcome with `jobs.finish(job.id, status=..., result=..., error=...)` (progress via
    `jobs.update_progress`). Raising marks the job failed."""
    global _remote_job_dispatcher
    _remote_job_dispatcher = fn


class DeviceExecutorUnavailable(RuntimeError):
    pass


def executor_for(data_source_or_device_id: Any) -> BackupExecutor:
    """LocalExecutor for the main server (`None` / a DataSource with `device_id = None`), otherwise the
    registered device executor."""
    device_id = data_source_or_device_id
    if device_id is not None and not isinstance(device_id, str):
        device_id = getattr(data_source_or_device_id, "device_id", None)
    if not device_id:
        return _local
    if _device_factory is None:
        raise DeviceExecutorUnavailable("host devices not available")
    return _device_factory(device_id)


def dispatch_remote_job(job: Any) -> None:
    if _remote_job_dispatcher is None:
        raise NotImplementedError("host devices not available")
    _remote_job_dispatcher(job)


# ---------------------------------------------------------------------------------------------
# device side helper
# ---------------------------------------------------------------------------------------------

LOCAL_CALLS = (
    "snapshot",
    "archive_logs",
    "restore",
    "verify",
    "delete_artifact",
    "ensure_database",
    "storage_stats",
    "artifact_exists",
)


def run_local_call(method: str, params: dict, on_progress: ProgressFn = _noop_progress) -> Any:
    """Runs one executor method on this installation's LocalExecutor from JSON params (for device RPC).

    `until` may be an ISO string. Only the methods in LOCAL_CALLS are allowed.
    """
    if method not in LOCAL_CALLS:
        raise ValueError(f"Unsupported executor call: {method}")
    params = dict(params or {})
    fn = getattr(_local, method)
    if method in ("snapshot", "restore"):
        params["on_progress"] = on_progress
    if method == "restore" and isinstance(params.get("until"), str):
        from app.services.backups import parse_time

        params["until"] = parse_time(params["until"])
    if method in ("delete_artifact", "artifact_exists"):
        return fn(params["ref"])
    if method == "storage_stats":
        return fn()
    return fn(**params)
