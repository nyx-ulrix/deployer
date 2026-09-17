"""Background jobs (docs/BACKUPS.md "Jobs").

Rows in `jobs` are the source of truth; Redis only carries wake-ups and liveness:

- `jobs:queue` (list): job ids to run. `dispatch(job_id)` RPUSHes after the caller committed the row.
  Losing a push is harmless: the worker's scheduler re-dispatches `queued` jobs older than a minute,
  and claiming a job is an atomic `UPDATE ... WHERE status='queued'`, so duplicates are no-ops.
- `jobs:heartbeat:<id>` (TTL 60 s): refreshed every 15 s while a worker runs the job. `running` jobs
  without a heartbeat are failed by `recover_stale()` (worker crash / container restart).
- `jobs:cancel:<id>`: set by `request_cancel()`; handlers poll `ctx.cancelled()` between steps.

Handlers::

    @job_handler("backup.snapshot")
    def run(ctx: JobContext) -> dict | None: ...      # return value -> jobs.result

`runs_on="primary"` (default) handlers run in the main server's worker even for sources on a host
device (they orchestrate and call `executors.executor_for(...)` for byte-level work).
`runs_on="host"` handlers - and job types without a local handler - that have `device_id` set are
handed to `executors.dispatch_remote_job(job)` instead of running locally.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import Job, utcnow
from app.redis_client import get_redis
from app.serializers import iso

log = logging.getLogger(__name__)

QUEUE_KEY = "jobs:queue"
HEARTBEAT_TTL_S = 60
HEARTBEAT_EVERY_S = 15
ACTIVE_STATUSES = ("queued", "running")
FINAL_STATUSES = ("succeeded", "failed", "cancelled")

SessionFactory = Callable[[], Session]


def heartbeat_key(job_id: str) -> str:
    return f"jobs:heartbeat:{job_id}"


def cancel_key(job_id: str) -> str:
    return f"jobs:cancel:{job_id}"


class JobCancelled(Exception):
    """Raise from a handler (or let `ctx.check_cancelled()` raise) to end the job as `cancelled`."""


class JobError(Exception):
    """A handler failure whose message is safe to show to users as-is."""


@dataclass
class HandlerSpec:
    type: str
    fn: Callable[[JobContext], Any]
    runs_on: Literal["primary", "host"] = "primary"


_registry: dict[str, HandlerSpec] = {}


def job_handler(job_type: str, *, runs_on: Literal["primary", "host"] = "primary"):
    def decorator(fn: Callable[[JobContext], Any]):
        _registry[job_type] = HandlerSpec(job_type, fn, runs_on)
        return fn

    return decorator


def handler_for(job_type: str) -> HandlerSpec | None:
    _load_builtin_handlers()
    return _registry.get(job_type)


_builtin_loaded = False


def _load_builtin_handlers() -> None:
    global _builtin_loaded
    if _builtin_loaded:
        return
    _builtin_loaded = True
    # Import side effect: modules register their handlers.
    from app.services import backups  # noqa: F401


# ---------------------------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------------------------


@dataclass
class JobContext:
    job_id: str
    type: str
    params: dict[str, Any]
    project_id: str | None = None
    data_source_id: str | None = None
    device_id: str | None = None
    created_by_id: str | None = None
    session_factory: SessionFactory = field(default_factory=lambda: get_sessionmaker())
    _last_progress_at: float = 0.0

    def db(self) -> Session:
        """A new session (caller closes it). Keep transactions short: jobs run for minutes."""
        return self.session_factory()

    def progress(self, fraction: float | None, message: str | None = None, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_progress_at < 1.0 and (fraction is None or fraction < 1.0):
            return
        self._last_progress_at = now
        update_progress(self.job_id, fraction, message, session_factory=self.session_factory)

    def cancelled(self) -> bool:
        try:
            if get_redis().exists(cancel_key(self.job_id)):
                return True
        except Exception:  # noqa: BLE001 - fall back to the row
            pass
        session = self.session_factory()
        try:
            status = session.scalar(select(Job.status).where(Job.id == self.job_id))
            return status == "cancelled"
        finally:
            session.close()

    def check_cancelled(self) -> None:
        if self.cancelled():
            raise JobCancelled()


# ---------------------------------------------------------------------------------------------
# enqueue / dispatch
# ---------------------------------------------------------------------------------------------


def enqueue(
    db: Session,
    *,
    type: str,  # noqa: A002 - matches the column / API field
    params: dict[str, Any] | None,
    project_id: str | None = None,
    data_source_id: str | None = None,
    device_id: str | None = None,
    created_by_id: str | None = None,
) -> Job:
    """Adds a queued job and flushes. The caller commits, then calls `dispatch(job.id)`."""
    job = Job(
        type=type,
        status="queued",
        progress=0.0,
        params=params or {},
        project_id=project_id,
        data_source_id=data_source_id,
        device_id=device_id,
        created_by_id=created_by_id,
    )
    db.add(job)
    db.flush()
    return job


def dispatch(job_id: str) -> None:
    try:
        get_redis().rpush(QUEUE_KEY, job_id)
    except Exception:  # noqa: BLE001 - the scheduler re-dispatches stuck queued jobs
        log.warning("could not push job %s to the queue; it will be picked up by the sweeper", job_id)


def active_job(db: Session, job_type: str, *, data_source_id: str | None = None, key: str | None = None) -> Job | None:
    """Newest queued/running job of a type for a source (or with params["key"] == key)."""
    stmt = select(Job).where(Job.type == job_type, Job.status.in_(ACTIVE_STATUSES))
    if data_source_id is not None:
        stmt = stmt.where(Job.data_source_id == data_source_id)
    for job in db.scalars(stmt.order_by(Job.created_at.desc())):
        if key is None or (job.params or {}).get("key") == key:
            return job
    return None


# ---------------------------------------------------------------------------------------------
# state changes
# ---------------------------------------------------------------------------------------------


def _clamp(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def update_progress(
    job_id: str, progress: float | None, message: str | None = None, *, session_factory: SessionFactory | None = None
) -> None:
    session = (session_factory or get_sessionmaker())()
    try:
        values: dict[str, Any] = {}
        if progress is not None:
            values["progress"] = _clamp(progress)
        if message is not None:
            values["message"] = message[:2000]
        if values:
            session.execute(update(Job).where(Job.id == job_id, Job.status == "running").values(**values))
            session.commit()
    finally:
        session.close()


def finish(
    job_id: str,
    *,
    status: Literal["succeeded", "failed", "cancelled"],
    result: dict | None = None,
    error: str | None = None,
    message: str | None = None,
    session_factory: SessionFactory | None = None,
) -> None:
    """Final state for a running job (also used by remote job dispatchers)."""
    session = (session_factory or get_sessionmaker())()
    try:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = utcnow()
        if status == "succeeded":
            job.progress = 1.0
        if result is not None:
            job.result = result
        if error is not None:
            job.error = redact_error(error)
        if message is not None:
            job.message = message[:2000]
        session.commit()
    finally:
        session.close()
    try:
        r = get_redis()
        r.delete(heartbeat_key(job_id))
        r.delete(cancel_key(job_id))
    except Exception:  # noqa: BLE001
        pass


def heartbeat(job_id: str) -> None:
    try:
        get_redis().set(heartbeat_key(job_id), "1", ex=HEARTBEAT_TTL_S)
    except Exception:  # noqa: BLE001
        pass


def redact_error(message: str) -> str:
    from app.services.connections import redact

    s = get_settings()
    return redact(str(message), [s.mariadb_root_password, s.mariadb_password, s.mongo_root_password, s.master_key])[
        :2000
    ]


def request_cancel(db: Session, job: Job) -> Job:
    """Queued jobs are cancelled at once; running jobs get a cancel flag the handler polls."""
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = utcnow()
        job.message = "Cancelled before it started"
    elif job.status == "running":
        try:
            get_redis().set(cancel_key(job.id), "1", ex=86400)
        except Exception:  # noqa: BLE001
            pass
        job.message = "Cancelling..."
    return job


# ---------------------------------------------------------------------------------------------
# running
# ---------------------------------------------------------------------------------------------


class Heartbeat:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"job-heartbeat-{job_id[:8]}", daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(HEARTBEAT_EVERY_S):
            heartbeat(self.job_id)

    def __enter__(self) -> Heartbeat:
        heartbeat(self.job_id)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()


def claim(job_id: str, session_factory: SessionFactory) -> Job | None:
    session = session_factory()
    try:
        res = session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(status="running", started_at=utcnow(), progress=0.0)
        )
        session.commit()
        if res.rowcount != 1:
            return None
        return session.get(Job, job_id)
    finally:
        session.close()


def run_job(job_id: str, *, session_factory: SessionFactory | None = None) -> str | None:
    """Claims and runs one job. Returns the final status, or None if it was not claimable."""
    factory = session_factory or get_sessionmaker()
    job = claim(job_id, factory)
    if job is None:
        return None
    spec = handler_for(job.type)
    with Heartbeat(job.id):
        if job.device_id and (spec is None or spec.runs_on == "host"):
            from app.services import executors

            try:
                executors.dispatch_remote_job(job)
            except Exception as exc:  # noqa: BLE001
                log.warning("remote dispatch of job %s (%s) failed: %s", job.id, job.type, exc)
                finish(job.id, status="failed", error=_error_text(exc), session_factory=factory)
                return "failed"
            # The dispatcher records the final state (jobs.finish); make sure the row isn't left running.
            session = factory()
            try:
                status = session.scalar(select(Job.status).where(Job.id == job.id))
            finally:
                session.close()
            return status
        if spec is None:
            finish(job.id, status="failed", error=f"Unknown job type: {job.type}", session_factory=factory)
            return "failed"
        ctx = JobContext(
            job_id=job.id,
            type=job.type,
            params=dict(job.params or {}),
            project_id=job.project_id,
            data_source_id=job.data_source_id,
            device_id=job.device_id,
            created_by_id=job.created_by_id,
            session_factory=factory,
        )
        try:
            result = spec.fn(ctx)
        except JobCancelled:
            finish(job.id, status="cancelled", message="Cancelled", session_factory=factory)
            return "cancelled"
        except Exception as exc:  # noqa: BLE001 - any failure ends the job
            log.exception("job %s (%s) failed", job.id, job.type)
            finish(job.id, status="failed", error=_error_text(exc), session_factory=factory)
            return "failed"
        finish(
            job.id,
            status="succeeded",
            result=result if isinstance(result, dict) else None,
            message="Done",
            session_factory=factory,
        )
        return "succeeded"


def _error_text(exc: BaseException) -> str:
    from app.errors import ApiError

    if isinstance(exc, ApiError):
        return exc.message
    orig = getattr(exc, "orig", None) or exc
    text = str(orig) or type(orig).__name__
    return text


def run_queued(*, session_factory: SessionFactory | None = None, max_jobs: int = 100) -> list[tuple[str, str | None]]:
    """Runs queued jobs in creation order in this thread (tests, CLI). Includes jobs they enqueue."""
    factory = session_factory or get_sessionmaker()
    done: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    while len(done) < max_jobs:
        session = factory()
        try:
            ids = [
                jid
                for jid in session.scalars(select(Job.id).where(Job.status == "queued").order_by(Job.created_at))
                if jid not in seen
            ]
        finally:
            session.close()
        if not ids:
            break
        seen.add(ids[0])
        done.append((ids[0], run_job(ids[0], session_factory=factory)))
    return done


def recover_stale(*, session_factory: SessionFactory | None = None, grace_seconds: int = HEARTBEAT_TTL_S) -> int:
    """Fails `running` jobs whose worker stopped heartbeating. Returns how many were failed."""
    factory = session_factory or get_sessionmaker()
    session = factory()
    failed = 0
    try:
        cutoff = utcnow() - timedelta(seconds=grace_seconds)
        running = list(session.scalars(select(Job).where(Job.status == "running")))
        r = get_redis()
        for job in running:
            if job.started_at and job.started_at > cutoff:
                continue
            try:
                alive = bool(r.exists(heartbeat_key(job.id)))
            except Exception:  # noqa: BLE001 - without Redis we can't tell; leave it
                continue
            if alive:
                continue
            job.status = "failed"
            job.finished_at = utcnow()
            job.error = "The worker stopped while this job was running (restart or crash)"
            failed += 1
        session.commit()
    finally:
        session.close()
    return failed


def redispatch_queued(*, session_factory: SessionFactory | None = None, older_than_seconds: int = 60) -> int:
    factory = session_factory or get_sessionmaker()
    session = factory()
    try:
        cutoff = utcnow() - timedelta(seconds=older_than_seconds)
        ids = list(session.scalars(select(Job.id).where(Job.status == "queued", Job.created_at < cutoff).limit(500)))
    finally:
        session.close()
    if not ids:
        return 0
    try:
        queued = set(get_redis().lrange(QUEUE_KEY, 0, -1))
    except Exception:  # noqa: BLE001
        return 0
    missing = [jid for jid in ids if jid not in queued]
    for jid in missing:
        dispatch(jid)
    return len(missing)


# ---------------------------------------------------------------------------------------------
# serializer
# ---------------------------------------------------------------------------------------------


def job_out(job: Job) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": float(job.progress or 0.0),
        "message": job.message,
        "result": job.result,
        "error": job.error,
        "project_id": job.project_id,
        "data_source_id": job.data_source_id,
        "device_id": job.device_id,
        "created_at": iso(job.created_at),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
    }
