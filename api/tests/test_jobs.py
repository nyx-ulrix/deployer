"""Job queue, runner, cancellation, crash recovery, remote dispatch, worker leadership and the jobs API."""

import threading
from datetime import timedelta

import pytest

from app.models import Job, utcnow
from app.services import executors, jobs
from app.worker import LEADER_KEY, acquire_leadership, release_leadership, runner_loop

CALLS: list = []


@jobs.job_handler("test.ok")
def _ok(ctx: jobs.JobContext):
    ctx.progress(0.5, "halfway", force=True)
    CALLS.append(("ok", ctx.params))
    return {"echo": ctx.params.get("value")}


@jobs.job_handler("test.fail")
def _fail(ctx: jobs.JobContext):
    raise RuntimeError("boom")


@jobs.job_handler("test.cancel")
def _cancel(ctx: jobs.JobContext):
    jobs.get_redis().set(jobs.cancel_key(ctx.job_id), "1")
    ctx.check_cancelled()
    return {"unreachable": True}


@jobs.job_handler("test.host", runs_on="host")
def _host(ctx: jobs.JobContext):
    return {"ran": "locally"}


@pytest.fixture(autouse=True)
def _reset():
    CALLS.clear()
    yield
    executors.register_remote_job_dispatcher(None)


def _enqueue(db, type_, **kw):
    job = jobs.enqueue(db, type=type_, params=kw.pop("params", {}), **kw)
    db.commit()
    return job


def test_enqueue_dispatch_and_run(db, fake_redis, make_user, make_project):
    owner = make_user()
    project = make_project(owner)
    job = _enqueue(db, "test.ok", params={"value": 42}, project_id=project.id)
    assert job.status == "queued"
    jobs.dispatch(job.id)
    assert fake_redis.lrange(jobs.QUEUE_KEY, 0, -1) == [job.id]
    assert jobs.run_job(job.id) == "succeeded"
    assert jobs.run_job(job.id) is None  # already claimed
    db.expire_all()
    row = db.get(Job, job.id)
    assert (row.status, row.progress, row.result, row.message) == ("succeeded", 1.0, {"echo": 42}, "Done")
    assert row.started_at and row.finished_at
    out = jobs.job_out(row)
    assert set(out) >= {
        "id",
        "type",
        "status",
        "progress",
        "message",
        "result",
        "error",
        "data_source_id",
        "device_id",
        "created_at",
        "started_at",
        "finished_at",
    }
    assert not fake_redis.exists(jobs.heartbeat_key(job.id))


def test_failure_cancel_and_unknown(db):
    failed = _enqueue(db, "test.fail")
    cancelled = _enqueue(db, "test.cancel")
    unknown = _enqueue(db, "test.nope")
    assert jobs.run_queued() == [(failed.id, "failed"), (cancelled.id, "cancelled"), (unknown.id, "failed")]
    db.expire_all()
    assert db.get(Job, failed.id).error == "boom"
    assert db.get(Job, cancelled.id).status == "cancelled"
    assert "Unknown job type" in db.get(Job, unknown.id).error


def test_error_messages_are_redacted(db, monkeypatch):
    import secrets

    from app.config import get_settings

    secret = secrets.token_hex(12)
    monkeypatch.setattr(get_settings(), "mariadb_root_password", secret)

    @jobs.job_handler("test.leak")
    def _leak(ctx):
        raise RuntimeError(f"Access denied using password {secret}")

    job = _enqueue(db, "test.leak")
    jobs.run_job(job.id)
    db.expire_all()
    assert secret not in db.get(Job, job.id).error and "***" in db.get(Job, job.id).error


def test_request_cancel_queued_and_running(db, fake_redis):
    queued = _enqueue(db, "test.ok")
    jobs.request_cancel(db, queued)
    db.commit()
    assert queued.status == "cancelled" and jobs.run_job(queued.id) is None
    running = _enqueue(db, "test.ok")
    running.status = "running"
    db.commit()
    jobs.request_cancel(db, running)
    assert fake_redis.exists(jobs.cancel_key(running.id)) and running.message == "Cancelling..."


def test_recover_stale_and_redispatch(db, fake_redis):
    stale = _enqueue(db, "test.ok")
    alive = _enqueue(db, "test.ok")
    fresh = _enqueue(db, "test.ok")
    long_ago = utcnow() - timedelta(minutes=10)
    for job in (stale, alive):
        job.status, job.started_at = "running", long_ago
    fresh.status, fresh.started_at = "running", utcnow()
    lost = _enqueue(db, "test.ok")
    lost.created_at = long_ago
    db.commit()
    jobs.heartbeat(alive.id)
    assert jobs.recover_stale() == 1
    db.expire_all()
    assert db.get(Job, stale.id).status == "failed" and "worker stopped" in db.get(Job, stale.id).error
    assert db.get(Job, alive.id).status == "running" and db.get(Job, fresh.id).status == "running"
    assert jobs.redispatch_queued() == 1
    assert fake_redis.lrange(jobs.QUEUE_KEY, 0, -1) == [lost.id]
    assert jobs.redispatch_queued() == 0  # already in the queue


def test_device_jobs_go_to_the_remote_dispatcher(db, make_user):
    from app.models import Device

    owner = make_user()
    device = Device(name="PC", owner_id=owner.id, roles=["database_host"], token_hash="0" * 64)
    db.add(device)
    db.commit()
    host_job = _enqueue(db, "test.host", device_id=device.id)
    unknown_job = _enqueue(db, "device.custom", device_id=device.id)
    primary_job = _enqueue(db, "test.ok", device_id=device.id, params={"value": 1})

    # Without the host-devices code: fail cleanly.
    assert jobs.run_job(host_job.id) == "failed"
    db.expire_all()
    assert db.get(Job, host_job.id).error == "host devices not available"

    seen = []

    def dispatcher(job):
        seen.append(job.id)
        jobs.finish(job.id, status="succeeded", result={"remote": True})

    executors.register_remote_job_dispatcher(dispatcher)
    assert jobs.run_job(unknown_job.id) == "succeeded"
    assert jobs.run_job(primary_job.id) == "succeeded"  # runs_on="primary" handlers stay local
    assert seen == [unknown_job.id] and CALLS == [("ok", {"value": 1})]
    db.expire_all()
    assert db.get(Job, unknown_job.id).result == {"remote": True}


def test_executor_for_routes_devices():
    assert isinstance(executors.executor_for(None), executors.LocalExecutor)
    with pytest.raises(executors.DeviceExecutorUnavailable):
        executors.executor_for("device-1")
    sentinel = object()
    executors.register_device_executor_factory(lambda device_id: (sentinel, device_id))
    try:
        assert executors.executor_for("device-1") == (sentinel, "device-1")

        class Source:
            device_id = None

        assert isinstance(executors.executor_for(Source()), executors.LocalExecutor)
    finally:
        executors.register_device_executor_factory(None)
    for bad in ("../x", "/etc/passwd", "a/../../b", "a b"):
        with pytest.raises(ValueError):
            executors.check_ref(bad)


def test_worker_leadership_and_runner(db, fake_redis):
    assert acquire_leadership(fake_redis, "w1")
    assert not acquire_leadership(fake_redis, "w2")
    assert acquire_leadership(fake_redis, "w1")  # renew
    assert fake_redis.pttl(LEADER_KEY) > 0
    release_leadership(fake_redis, "w2")
    assert fake_redis.get(LEADER_KEY) == "w1"
    release_leadership(fake_redis, "w1")
    assert acquire_leadership(fake_redis, "w2")

    job = _enqueue(db, "test.ok", params={"value": "via-runner"})
    jobs.dispatch(job.id)
    stop = threading.Event()

    class OneShot:
        def blpop(self, keys, timeout):
            item = fake_redis.lpop(keys[0])
            if item is None:
                stop.set()
                return None
            return (keys[0], item)

    runner_loop(stop, client_factory=OneShot)
    db.expire_all()
    assert db.get(Job, job.id).status == "succeeded"


def test_jobs_api(client, db, make_user, make_project, auth_headers):
    owner, viewer, dev, admin, outsider = (make_user() for _ in range(5))
    project = make_project(owner, members={viewer: "viewer", dev: "developer", admin: "admin"})
    other = make_project(outsider, "Other")
    job = _enqueue(db, "test.ok", project_id=project.id)
    foreign = _enqueue(db, "test.ok", project_id=other.id)
    base = f"/v1/projects/{project.id}/jobs"

    listed = client.get(base, headers=auth_headers(viewer)).json()
    assert [j["id"] for j in listed] == [job.id]
    assert client.get(f"{base}/{job.id}", headers=auth_headers(viewer)).json()["status"] == "queued"
    assert client.get(f"{base}/{foreign.id}", headers=auth_headers(owner)).status_code == 404
    assert client.post(f"{base}/{job.id}/cancel", headers=auth_headers(dev)).status_code == 403
    resp = client.post(f"{base}/{job.id}/cancel", headers=auth_headers(admin))
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    assert client.get(base, headers=auth_headers(outsider)).status_code == 404
