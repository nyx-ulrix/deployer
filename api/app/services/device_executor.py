"""Backups on host devices: the `BackupExecutor` for device-hosted databases (docs/BACKUPS.md,
docs/DEVICES.md) plus the remote job dispatcher and the device-side job runner.

Primary side (`register()`, called at API startup by `routers/devices.py` and at import of the
`device_worker` worker plugin - never at import of this module):

- `DeviceExecutor(device_id)` implements `executors.BackupExecutor` by sending `jobs.run` RPCs with
  job types `executor.<method>` that the device answers with `executors.run_local_call` against its
  own LocalExecutor (progress is streamed back). Artifact bytes move through device transfers:
  `open_artifact` pulls a file from the device (`transfer.upload`), `put_artifact` pushes one
  (`transfer.download`).
- `dispatch_remote_job(job)` runs a `runs_on="host"` job on the job's device and records the
  outcome with `jobs.finish`.

Device side (`run_device_job`, used by `device_host` for `jobs.run`): executor calls may only name
databases listed in `device_hosted_credentials`; other job types run their registered handler with a
context that forwards progress to the main Deployer.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, Any

from app.errors import ApiError
from app.services import device_rpc

log = logging.getLogger(__name__)

EXECUTOR_PREFIX = "executor."
LONG_TIMEOUT = 6 * 3600.0
SHORT_TIMEOUT = 120.0


def _noop(fraction: float | None = None, message: str | None = None) -> None:
    return None


class _TempArtifact:
    """Binary file object for a downloaded artifact; the temp file is removed on close."""

    def __init__(self, path: str):
        self._path = path
        self._fh = open(path, "rb")  # noqa: SIM115

    def __getattr__(self, name: str) -> Any:
        return getattr(self._fh, name)

    def __iter__(self):
        return iter(self._fh)

    def __enter__(self):
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._fh.close()
        finally:
            Path(self._path).unlink(missing_ok=True)


class DeviceExecutor:
    """`executors.BackupExecutor` for databases on host device `device_id`."""

    def __init__(self, device_id: str):
        self.device_id = device_id

    def _run(self, method: str, params: dict, *, timeout: float, on_progress=None) -> Any:
        job_id = uuid.uuid4().hex
        return device_rpc.call(
            self.device_id,
            "jobs.run",
            {"job_id": job_id, "type": EXECUTOR_PREFIX + method, "params": params},
            timeout=timeout,
            progress_id=f"{self.device_id}:{job_id}",
            on_progress=on_progress,
        )

    def snapshot(self, *, kind, engine, database_name, artifact_ref, on_progress=_noop) -> dict:
        return self._run(
            "snapshot",
            {"kind": kind, "engine": engine, "database_name": database_name, "artifact_ref": artifact_ref},
            timeout=LONG_TIMEOUT,
            on_progress=on_progress,
        )

    def archive_logs(self, *, kind, engine, database_name, since_point, artifact_ref_prefix) -> list[dict]:
        return self._run(
            "archive_logs",
            {
                "kind": kind,
                "engine": engine,
                "database_name": database_name,
                "since_point": since_point,
                "artifact_ref_prefix": artifact_ref_prefix,
            },
            timeout=LONG_TIMEOUT,
        )

    def restore(
        self,
        *,
        kind,
        engine,
        target_database_name,
        snapshot_ref,
        segments,
        until,
        on_progress=_noop,
        source_database_name,
        consistent_point=None,
    ) -> dict:
        return self._run(
            "restore",
            {
                "kind": kind,
                "engine": engine,
                "target_database_name": target_database_name,
                "snapshot_ref": snapshot_ref,
                "segments": segments,
                "until": until.isoformat() if isinstance(until, datetime) else until,
                "source_database_name": source_database_name,
                "consistent_point": consistent_point,
            },
            timeout=LONG_TIMEOUT,
            on_progress=on_progress,
        )

    def verify(self, *, kind, engine, snapshot_ref, expected_row_counts) -> dict:
        return self._run(
            "verify",
            {"kind": kind, "engine": engine, "snapshot_ref": snapshot_ref, "expected_row_counts": expected_row_counts},
            timeout=LONG_TIMEOUT,
        )

    def delete_artifact(self, ref: str) -> None:
        self._run("delete_artifact", {"ref": ref}, timeout=SHORT_TIMEOUT)

    def artifact_exists(self, ref: str) -> bool:
        return bool(self._run("artifact_exists", {"ref": ref}, timeout=SHORT_TIMEOUT))

    def storage_stats(self) -> dict:
        return self._run("storage_stats", {}, timeout=SHORT_TIMEOUT)

    def artifact_path(self, ref: str) -> Path:
        from app.services.executors import RemoteArtifactError

        raise RemoteArtifactError(f"Artifact {ref} is stored on a host device")

    def open_artifact(self, ref: str) -> IO[bytes]:
        from app.services.executors import check_ref

        check_ref(ref)
        transfer_id = device_rpc.create_transfer(self.device_id, "put")
        try:
            device_rpc.call(
                self.device_id, "transfer.upload", {"transfer_id": transfer_id, "local_ref": ref}, timeout=LONG_TIMEOUT
            )
            src = device_rpc.claim_upload(transfer_id)
            fd, tmp = tempfile.mkstemp(prefix="deployer-artifact-", suffix=".bin", dir=device_rpc.transfer_dir())
            os.close(fd)
            os.replace(src, tmp)
        finally:
            device_rpc.finish_transfer(transfer_id)
        return _TempArtifact(tmp)  # type: ignore[return-value]

    def put_artifact(self, ref: str, src: IO[bytes] | str | os.PathLike) -> dict:
        """Stores bytes (already encrypted) at `ref` in the device's backup store. Returns {sha256, size}."""
        from app.services.executors import check_ref

        check_ref(ref)
        fd, staged = tempfile.mkstemp(prefix="deployer-artifact-", suffix=".bin", dir=device_rpc.transfer_dir())
        try:
            with os.fdopen(fd, "wb") as out:
                if isinstance(src, str | os.PathLike):
                    with open(src, "rb") as fh:
                        while chunk := fh.read(1 << 20):
                            out.write(chunk)
                else:
                    while chunk := src.read(1 << 20):
                        out.write(chunk)
            transfer_id = device_rpc.create_transfer(self.device_id, "get", source_path=staged)
        except BaseException:
            Path(staged).unlink(missing_ok=True)
            raise
        try:
            return device_rpc.call(
                self.device_id,
                "transfer.download",
                {"transfer_id": transfer_id, "local_ref": ref},
                timeout=LONG_TIMEOUT,
            )
        finally:
            device_rpc.finish_transfer(transfer_id)

    def ensure_database(self, *, kind, database_name) -> dict:
        from app.services import provisioning

        result = device_rpc.call(
            self.device_id, "datasource.provision", {"kind": kind, "database_name": database_name}, timeout=90
        )
        return provisioning.device_source_config(kind, database_name, str(result.get("username") or ""))


def dispatch_remote_job(job: Any) -> None:
    """`executors.register_remote_job_dispatcher` hook: run `job` on its device and record the outcome."""
    from app.services import jobs

    try:
        result = device_rpc.call(
            job.device_id,
            "jobs.run",
            {
                "job_id": job.id,
                "type": job.type,
                "params": job.params or {},
                "project_id": job.project_id,
                "data_source_id": job.data_source_id,
            },
            timeout=LONG_TIMEOUT,
        )
    except ApiError as exc:
        jobs.finish(job.id, status="failed", error=exc.message)
        return
    jobs.finish(
        job.id, status="succeeded", result=result if isinstance(result, dict) or result is None else {"value": result}
    )


def register() -> None:
    """Installs the device executor factory, remote job dispatcher and copy target (idempotent)."""
    from app.services import backups, executors

    executors.register_device_executor_factory(DeviceExecutor)
    executors.register_remote_job_dispatcher(dispatch_remote_job)
    backups.register_copy_target(copy_artifact)


def unregister() -> None:
    """Removes the hooks installed by `register()` (API shutdown)."""
    from app.services import backups, executors

    executors.register_device_executor_factory(None)
    executors.register_remote_job_dispatcher(None)
    backups.register_copy_target(None)


def copy_artifact(
    *, artifact_type: str, artifact_id: str, ref: str, from_device_id: str | None, to_device_id: str | None
) -> dict:
    """`backups.register_copy_target` hook: copies an encrypted artifact between backup stores
    (`None` = main server) through device transfers. Returns `{ref, size_bytes, sha256}`."""
    import hashlib

    from app.services import executors

    _ = (artifact_type, artifact_id)
    executors.check_ref(ref)
    if (from_device_id or None) == (to_device_id or None):
        raise ValueError("source and destination are the same backup store")
    if from_device_id is None:
        src_path = executors.local_executor().artifact_path(ref)
        return {"ref": ref, **_sized(DeviceExecutor(to_device_id).put_artifact(ref, src_path))}
    with DeviceExecutor(from_device_id).open_artifact(ref) as stream:
        if to_device_id is not None:
            return {"ref": ref, **_sized(DeviceExecutor(to_device_id).put_artifact(ref, stream))}
        dest = executors.local_executor().artifact_path(ref)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        digest, size = hashlib.sha256(), 0
        try:
            with open(tmp, "wb") as out:
                while chunk := stream.read(1 << 20):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
    return {"ref": ref, "size_bytes": size, "sha256": digest.hexdigest()}


def _sized(result: Any) -> dict:
    result = result if isinstance(result, dict) else {}
    return {"size_bytes": result.get("size"), "sha256": result.get("sha256")}


# ---------------------------------------------------------------------------------------------
# device side
# ---------------------------------------------------------------------------------------------

_EXECUTOR_DB_PARAMS = {
    "snapshot": "database_name",
    "archive_logs": "database_name",
    "restore": "target_database_name",
}
_DEVICE_EXECUTOR_CALLS = {
    "snapshot",
    "archive_logs",
    "restore",
    "verify",
    "delete_artifact",
    "artifact_exists",
    "storage_stats",
}


def run_executor_call(method: str, params: dict, job_id: str, ctx: Any) -> Any:
    from app.services import device_host, executors

    if method not in _DEVICE_EXECUTOR_CALLS:
        raise ApiError(400, "unsupported_job", f"Executor call {method!r} is not allowed on a host device")
    field = _EXECUTOR_DB_PARAMS.get(method)
    if field:
        entry = device_host.hosted_entry(params.get(field), params.get("kind"))
        if entry.get("kind") != params.get("kind"):
            raise ApiError(404, "not_hosted", "That database is not hosted on this device")
    source = params.get("source_database_name")
    if source is not None and (
        not isinstance(source, str) or source in device_host.RESERVED_DATABASES or source.startswith("verify_")
    ):
        raise ApiError(422, "validation_error", "Invalid source database")
    for ref_field in ("artifact_ref", "snapshot_ref", "ref"):
        if ref_field in params:
            try:
                executors.check_ref(params[ref_field])
            except ValueError as exc:
                raise ApiError(422, "invalid_local_ref", str(exc)) from exc
    if "artifact_ref_prefix" in params:
        try:
            executors.check_ref(str(params["artifact_ref_prefix"]).rstrip("/"))
        except ValueError as exc:
            raise ApiError(422, "invalid_local_ref", str(exc)) from exc
    for seg in params.get("segments") or []:
        if isinstance(seg, dict) and seg.get("ref"):
            try:
                executors.check_ref(seg["ref"])
            except ValueError as exc:
                raise ApiError(422, "invalid_local_ref", str(exc)) from exc

    def on_progress(fraction: float | None = None, message: str | None = None) -> None:
        ctx.progress(job_id, fraction, message)

    try:
        return executors.run_local_call(method, params, on_progress)
    except ValueError as exc:
        raise ApiError(400, "backup_failed", str(exc)[:1000]) from exc


def _device_job_context_class():
    from app.services import jobs

    @dataclass
    class DeviceJobContext(jobs.JobContext):
        forward: Any = None

        def progress(self, fraction: float | None, message: str | None = None, *, force: bool = False) -> None:
            if self.forward is not None:
                self.forward(self.job_id, fraction, message)

        def cancelled(self) -> bool:
            return False

    return DeviceJobContext


def run_device_job(job_id: str, job_type: str, params: dict, ctx: Any, extra: dict | None = None) -> Any:
    """Device side of `jobs.run`."""
    if job_type.startswith(EXECUTOR_PREFIX):
        return run_executor_call(job_type[len(EXECUTOR_PREFIX) :], params, job_id, ctx)
    try:
        from app.services import jobs
    except Exception as exc:  # noqa: BLE001
        raise ApiError(400, "unsupported_job", f"This device can't run jobs of type {job_type!r}") from exc
    spec = jobs.handler_for(job_type)
    if spec is None or getattr(spec, "runs_on", "primary") != "host":
        raise ApiError(400, "unsupported_job", f"This device can't run jobs of type {job_type!r}")
    extra = extra or {}
    context = _device_job_context_class()(
        job_id=job_id,
        type=job_type,
        params=params,
        project_id=extra.get("project_id"),
        data_source_id=extra.get("data_source_id"),
        forward=ctx.progress,
    )
    result = spec.fn(context)
    return result if isinstance(result, dict) or result is None else {"value": result}
