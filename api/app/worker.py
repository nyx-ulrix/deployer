"""Deployer worker: `python -m app.worker` (docs/BACKUPS.md "Jobs").

Threads started by `start_background_tasks()`:

- `runner-N` (WORKER_CONCURRENCY, default 2): BLPOP `jobs:queue` and run jobs (`jobs.run_job`). Jobs
  with `device_id` whose handler must run on the host (or that have no local handler) are handed to
  `executors.dispatch_remote_job`; backup jobs orchestrate from here and use device executors.
- `scheduler`: leader election via Redis `SET scheduler:leader <id> NX PX 30000`, renewed every 10 s.
  The leader fails stale `running` jobs, re-dispatches lost `queued` jobs and enqueues due work
  (`backups.scheduler_tick`: snapshots per policy, log archiving - MariaDB 5 min / MongoDB 1 min -,
  hourly pruning incl. purging sources deleted > 30 days ago, weekly verification, daily platform
  snapshot).
- `mongo-replset`: initiates the managed MongoDB single-node replica set on first start/upgrade.
- `source-sync`: while this worker leads the scheduler, a co-hosting sync round every 2 s for each
  syncing database copy (docs/COHOSTING.md, `source_sync.sync_loop`).
- `app-logs`: every 10 s copies new `docker logs` lines of live app containers into Redis
  (docs/DEPLOYMENTS.md); the scheduler tick also removes orphan app containers.
- any task added with `register_background_task(name, fn)`.

Extension point (host devices): call `register_background_task("device-agent", fn)` before
`start_background_tasks()` runs - e.g. from a module listed in `WORKER_PLUGINS` (comma-separated
module names imported at startup) - where `fn(stop: threading.Event)` blocks until `stop` is set.
"""

from __future__ import annotations

import importlib
import logging
import os
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable

import redis
from redis.exceptions import WatchError

from app.config import get_settings
from app.services import jobs

log = logging.getLogger("app.worker")

LEADER_KEY = "scheduler:leader"
LEADER_TTL_MS = 30_000
RENEW_EVERY_S = 10
TICK_EVERY_S = 15
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"

BackgroundTask = Callable[[threading.Event], None]
_tasks: list[tuple[str, BackgroundTask]] = []


def register_background_task(name: str, fn: BackgroundTask) -> None:
    """Adds a long-running task `fn(stop_event)` to the worker (started by start_background_tasks)."""
    _tasks.append((name, fn))


def _worker_redis() -> redis.Redis:
    # Own connection with a socket timeout longer than the BLPOP timeout.
    return redis.Redis.from_url(
        get_settings().redis_url, decode_responses=True, socket_timeout=30, socket_connect_timeout=5
    )


# ---------------------------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------------------------


def runner_loop(stop: threading.Event, client_factory: Callable[[], redis.Redis] = _worker_redis) -> None:
    client = None
    while not stop.is_set():
        try:
            if client is None:
                client = client_factory()
            item = client.blpop([jobs.QUEUE_KEY], timeout=5)
        except redis.RedisError as exc:
            log.warning("queue unavailable: %s", exc)
            client = None
            stop.wait(3)
            continue
        if not item:
            continue
        job_id = item[1]
        try:
            status = jobs.run_job(job_id)
            if status:
                log.info("job %s finished: %s", job_id, status)
        except Exception:  # noqa: BLE001 - keep the runner alive
            log.exception("running job %s crashed", job_id)


# ---------------------------------------------------------------------------------------------
# scheduler
# ---------------------------------------------------------------------------------------------


def acquire_leadership(client: redis.Redis, me: str = WORKER_ID) -> bool:
    if client.set(LEADER_KEY, me, nx=True, px=LEADER_TTL_MS):
        return True
    with client.pipeline() as pipe:
        try:
            pipe.watch(LEADER_KEY)
            if pipe.get(LEADER_KEY) != me:
                pipe.unwatch()
                return False
            pipe.multi()
            pipe.pexpire(LEADER_KEY, LEADER_TTL_MS)
            pipe.execute()
            return True
        except WatchError:
            return False


def release_leadership(client: redis.Redis, me: str = WORKER_ID) -> None:
    with client.pipeline() as pipe:
        try:
            pipe.watch(LEADER_KEY)
            if pipe.get(LEADER_KEY) == me:
                pipe.multi()
                pipe.delete(LEADER_KEY)
                pipe.execute()
            else:
                pipe.unwatch()
        except (WatchError, redis.RedisError):
            pass


PRUNE_QUERY_LOG_EVERY_S = 24 * 3600
_last_query_log_prune = float("-inf")  # module-level: the leader is one process, ticks every TICK_EVERY_S


def scheduler_tick() -> None:
    global _last_query_log_prune
    from app.services import backups, deployments, query_log

    jobs.recover_stale()
    jobs.redispatch_queued()
    backups.scheduler_tick(jobs.get_sessionmaker())
    deployments.scheduler_tick(jobs.get_sessionmaker())
    if time.monotonic() - _last_query_log_prune >= PRUNE_QUERY_LOG_EVERY_S:
        _last_query_log_prune = time.monotonic()
        with jobs.get_sessionmaker()() as session:
            pruned = query_log.prune(session)
            session.commit()
        if pruned:
            log.info("pruned %d query log row(s)", pruned)


def scheduler_loop(stop: threading.Event, client_factory: Callable[[], redis.Redis] = _worker_redis) -> None:
    client = None
    leader = False
    last_tick = 0.0
    while not stop.is_set():
        try:
            if client is None:
                client = client_factory()
            now_leader = acquire_leadership(client)
            if now_leader != leader:
                log.info("scheduler leadership %s", "acquired" if now_leader else "lost")
            leader = now_leader
            if leader and time.monotonic() - last_tick >= TICK_EVERY_S:
                last_tick = time.monotonic()
                try:
                    scheduler_tick()
                except Exception:  # noqa: BLE001
                    log.exception("scheduler tick failed")
        except redis.RedisError as exc:
            log.warning("scheduler: redis unavailable: %s", exc)
            client, leader = None, False
        stop.wait(min(RENEW_EVERY_S, TICK_EVERY_S))
    if client is not None and leader:
        release_leadership(client)


def mongo_replset_loop(stop: threading.Event) -> None:
    from app.services.backup_engine import ensure_mongo_replica_set

    while not stop.is_set():
        status = ensure_mongo_replica_set()
        if status in ("ok", "initiated", "disabled", "no_replset"):
            if status == "initiated":
                log.info("initiated the MongoDB replica set rs0")
            elif status == "no_replset":
                log.warning("managed MongoDB runs without --replSet: MongoDB point-in-time recovery is unavailable")
            return
        log.info("MongoDB replica set not ready yet (%s); retrying", status)
        stop.wait(10)


# ---------------------------------------------------------------------------------------------
# process
# ---------------------------------------------------------------------------------------------


def _load_plugins() -> None:
    for name in filter(None, (m.strip() for m in os.environ.get("WORKER_PLUGINS", "").split(","))):
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001
            log.exception("could not load worker plugin %s", name)


def start_background_tasks(stop: threading.Event, *, concurrency: int | None = None) -> list[threading.Thread]:
    concurrency = concurrency or max(1, int(os.environ.get("WORKER_CONCURRENCY", "2")))
    specs: list[tuple[str, BackgroundTask]] = [(f"runner-{i + 1}", runner_loop) for i in range(concurrency)]
    from app.services import deployments, source_sync

    specs += [
        ("scheduler", scheduler_loop),
        ("mongo-replset", mongo_replset_loop),
        ("app-logs", deployments.logs_loop),
        ("source-sync", source_sync.sync_loop),
        *_tasks,
    ]
    threads = []
    for name, fn in specs:
        thread = threading.Thread(target=_guard(name, fn, stop), name=name, daemon=True)
        thread.start()
        threads.append(thread)
    return threads


def _guard(name: str, fn: BackgroundTask, stop: threading.Event) -> Callable[[], None]:
    def run() -> None:
        while not stop.is_set():
            try:
                fn(stop)
                return
            except Exception:  # noqa: BLE001 - restart crashed loops
                log.exception("background task %s crashed; restarting in 5 s", name)
                stop.wait(5)

    return run


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("worker %s starting", WORKER_ID)
    _load_plugins()
    try:
        failed = jobs.recover_stale()
        if failed:
            log.warning("marked %d interrupted job(s) as failed", failed)
    except Exception:  # noqa: BLE001 - the database may still be starting; the scheduler retries
        log.warning("could not check for interrupted jobs yet", exc_info=True)
    stop = threading.Event()

    def _signal(signum, _frame) -> None:
        log.info("received signal %s, stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)
    threads = start_background_tasks(stop)
    while not stop.is_set():
        stop.wait(1)
    for thread in threads:
        thread.join(timeout=5)
    log.info("worker stopped")


if __name__ == "__main__":
    # `python -m app.worker` runs this file as `__main__`. Plugins do `from app import worker`, which
    # would import a *second* copy of this module with its own task registry, so their background
    # tasks would never start. Hand off to the canonical module so both sides share one registry.
    from app.worker import main as _canonical_main

    _canonical_main()
