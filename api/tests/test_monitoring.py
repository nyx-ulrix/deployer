"""Monitoring: metrics sampling, request counters, alerts and the alert webhook (docs/MONITORING.md)."""

import json
import time
from datetime import timedelta

import pytest

from app.models import Job, utcnow
from app.services import alerts, app_runner, metrics

GB = 1024**3


def host_point(t, *, cpu=10.0, mem_used=2 * GB, mem_total=8 * GB, free=50 * GB, total=100 * GB):
    return {
        "t": t,
        "collected_at": metrics._iso(t),
        "cpu_percent": cpu,
        "memory_used_bytes": mem_used,
        "memory_total_bytes": mem_total,
        "disk_free_bytes": free,
        "disk_total_bytes": total,
        "uptime_seconds": 100.0,
    }


def put_host(fake_redis, point):
    fake_redis.zadd(metrics.HOST_KEY, {json.dumps(point): point["t"]})


class FakeDocker(app_runner.DockerCli):
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def _run(self, args, **kwargs):
        self.calls.append(args)
        return self.outputs[args[1]]


def test_docker_stats_parses_ps_inspect_and_stats():
    docker = FakeDocker(
        {
            "ps": "deployer-api-1\tdeployer\tapi\t\n"
            "deployer-app-web-1\t\t\tapp123\n"
            "other-thing\tsomething-else\tx\t\n"
            "deployer-redis-1\tdeployer\tredis\t\n",
            "inspect": "/deployer-api-1\trunning\thealthy\t0\t2026-09-28T10:00:00Z\n"
            "/deployer-app-web-1\trestarting\t\t7\t2026-09-28T10:01:00Z\n"
            "/deployer-redis-1\texited\t\t0\t2026-09-28T09:00:00Z\n",
            "stats": json.dumps({"Name": "deployer-api-1", "CPUPerc": "1.5%", "MemUsage": "100MiB / 1GiB"}) + "\n",
        }
    )
    rows = {r["name"]: r for r in docker.stats("deployer")}
    assert set(rows) == {"deployer-api-1", "deployer-app-web-1", "deployer-redis-1"}
    api = rows["deployer-api-1"]
    assert api["cpu_percent"] == 1.5 and api["memory_bytes"] == 100 * 1024**2 and api["memory_limit_bytes"] == GB
    assert api["health"] == "healthy" and api["service"] == "api"
    web = rows["deployer-app-web-1"]
    assert web["status"] == "restarting" and web["restarts"] == 7 and web["app_id"] == "app123"
    assert web["cpu_percent"] is None
    assert docker.calls[-1][-1] == "deployer-api-1"  # docker stats only for running containers


def test_sample_writes_bounded_host_series_and_containers(fake_redis, monkeypatch):
    monkeypatch.setattr("app.services.device_host.collect_metrics", lambda: host_point(0))
    docker = FakeDocker({"ps": "", "inspect": "", "stats": ""})
    app_runner.set_docker(docker)
    try:
        now = 1_800_000_000
        fake_redis.zadd(metrics.HOST_KEY, {json.dumps({"t": now - 90_000}): now - 90_000})  # older than 24 h
        metrics.sample(now)
        metrics.sample(now + 15)  # same minute: replaces the point
    finally:
        app_runner.set_docker(None)
    members = fake_redis.zrange(metrics.HOST_KEY, 0, -1)
    assert len(members) == 1 and json.loads(members[0])["collected_at"] == metrics._iso(now + 15)
    assert json.loads(fake_redis.get(metrics.CONTAINERS_KEY))["containers"] == []


def test_p95_interpolates_within_bucket():
    hist = [0] * (len(metrics.LATENCY_BUCKETS_MS) + 1)
    assert metrics.p95(hist) is None
    hist[2] = 100  # all in (10, 25] ms
    assert 10 < metrics.p95(hist) <= 25
    hist[-1] = 100  # half over 10 s
    assert metrics.p95(hist) == 10000


def test_middleware_counts_per_route_template(client, fake_redis, owner_headers):
    client.get("/v1/projects/abc", headers=owner_headers)  # 404 for a missing project
    client.get("/v1/projects/def", headers=owner_headers)
    client.get("/v1/health")
    client.get("/v1/no-such-route")
    client.request("FROB", "/v1/projects/abc", headers=owner_headers)
    fields = {}
    for key in fake_redis.keys(metrics.REQ_PREFIX + "*"):
        fields.update(fake_redis.hgetall(key))
    assert fields["GET /v1/projects/{project_id}|n"] == "2"
    assert fields["unmatched|n"] == "1"
    assert not any("/abc" in f or "/v1/health" in f or "FROB" in f or "no-such" in f for f in fields)


def test_metrics_endpoints(client, fake_redis, owner_headers, make_user, auth_headers):
    now = time.time()
    put_host(fake_redis, host_point(metrics._minute(now), cpu=42.0))
    for status in (200, 200, 500):
        metrics.record_request("GET /v1/x", status, 30.0, now)
    resp = client.get("/v1/instance/metrics", params={"window": "1h"}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current"]["cpu_percent"] == 42.0 and len(body["points"]) == 60
    assert body["requests"]["requests"] == 3 and body["requests"]["errors_5xx"] == 1
    assert body["routes"][0]["route"] == "GET /v1/x"
    assert len(client.get("/v1/instance/metrics?window=24h", headers=owner_headers).json()["points"]) == 120
    assert client.get("/v1/instance/metrics?window=2d", headers=owner_headers).status_code == 422

    summary = client.get("/v1/instance/metrics/summary", headers=owner_headers).json()
    assert summary["requests_5m"]["requests"] >= 3 and summary["alerts"]["active"] == 0

    member = auth_headers(make_user())
    for path in ("/v1/instance/metrics", "/v1/instance/metrics/summary", "/v1/instance/alerts"):
        assert client.get(path, headers=member).status_code == 403


@pytest.fixture
def factory():
    from app.db import get_sessionmaker

    return get_sessionmaker()


def test_alerts_open_hold_and_resolve(fake_redis, factory, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "deliver_async", lambda url, payload: sent.append(payload))
    now = time.time()
    put_host(fake_redis, host_point(metrics._minute(now), free=3 * GB, mem_used=7.6 * GB))

    events = alerts.evaluate(factory, now)
    assert [(e, a["alert"]) for e, a in events] == [("open", "disk_low")]  # memory needs 5 minutes
    assert {a["alert"] for a in alerts.active()} == {"disk_low"}
    assert sent == []  # no webhook configured

    assert [a["alert"] for _, a in alerts.evaluate(factory, now + 301)] == ["memory_high"]
    fake_redis.delete(metrics.HOST_KEY)
    put_host(fake_redis, host_point(metrics._minute(now + 360)))
    resolved = alerts.evaluate(factory, now + 360)
    assert sorted((e, a["alert"]) for e, a in resolved) == [("resolved", "disk_low"), ("resolved", "memory_high")]
    assert alerts.active() == []


def test_disk_low_watches_the_host_drive_not_the_sparse_wsl_disk(fake_redis, factory, monkeypatch):
    """A-013: `/` is a sparse ~1 TB WSL vhdx; the Windows drive under it (DEVICE_DISK_PATH) is what fills."""
    from types import SimpleNamespace

    from app.services import device_host

    disks = {"/": SimpleNamespace(free=990 * GB, total=1000 * GB)}

    def disk_usage(path):
        if path not in disks:
            raise FileNotFoundError(path)
        return disks[path]

    monkeypatch.setattr(device_host.shutil, "disk_usage", disk_usage)
    monkeypatch.setenv("DEVICE_DISK_PATH", "/host-disk")
    monkeypatch.setenv("DEVICE_DISK_DRIVE", "C:")
    assert device_host.disk_space() == (990 * GB, 1000 * GB, "the Docker disk")  # mount missing: `/` only

    disks["/host-disk"] = SimpleNamespace(free=3 * GB, total=200 * GB)
    assert device_host.disk_space() == (3 * GB, 200 * GB, "drive C:")

    monkeypatch.setattr(alerts, "deliver_async", lambda url, payload: None)
    now = time.time()
    host = device_host.collect_metrics()
    put_host(fake_redis, {"t": metrics._minute(now), **{k: host[k] for k in metrics.HOST_FIELDS}})
    assert metrics.current_host()["disk_label"] == "drive C:"
    (event,) = alerts.evaluate(factory, now)
    assert event[1]["alert"] == "disk_low" and "free on drive C:" in event[1]["message"]


def test_backup_failure_and_api_error_rules(fake_redis, factory, db):
    now = time.time()
    db.add(Job(type="backup.platform_snapshot", status="failed", finished_at=utcnow() - timedelta(hours=1)))
    db.commit()
    for status in [500] * 5 + [200] * 20:
        metrics.record_request("GET /v1/x", status, 5.0, now)
    ids = {a["id"] for _, a in alerts.evaluate(factory, now)}
    assert ids == {"backup:backup.platform_snapshot:platform", "api_errors"}

    db.add(Job(type="backup.platform_snapshot", status="succeeded", finished_at=utcnow()))
    db.commit()
    alerts.evaluate(factory, now + 60)
    assert "backup:backup.platform_snapshot:platform" not in {a["id"] for a in alerts.active()}


def test_container_rule_waits_two_minutes(fake_redis, factory):
    doc = {
        "collected_at": "x",
        "containers": [{"name": "deployer-mariadb-1", "service": "mariadb", "status": "restarting"}],
    }
    fake_redis.set(metrics.CONTAINERS_KEY, json.dumps(doc))
    now = time.time()
    assert alerts.evaluate(factory, now) == []
    (event, alert) = alerts.evaluate(factory, now + 121)[0]
    assert event == "open" and alert["severity"] == "critical" and "mariadb" in alert["message"]


def test_dismiss_snooze_and_summary(client, fake_redis, factory, owner_headers):
    now = time.time()
    put_host(fake_redis, host_point(metrics._minute(now), free=1 * GB))
    alerts.evaluate(factory, now)
    listed = client.get("/v1/instance/alerts", headers=owner_headers).json()
    assert [a["id"] for a in listed] == ["disk_low"] and listed[0]["opened_at"]
    summary = client.get("/v1/instance/metrics/summary", headers=owner_headers).json()["alerts"]
    assert summary["visible"] == 1 and summary["critical"] == 1 and summary["top"]["id"] == "disk_low"

    snoozed = client.post("/v1/instance/alerts/disk_low/snooze", json={"minutes": 60}, headers=owner_headers)
    assert snoozed.status_code == 200 and snoozed.json()["snoozed_until"]
    assert client.get("/v1/instance/metrics/summary", headers=owner_headers).json()["alerts"]["visible"] == 0
    assert client.post("/v1/instance/alerts/disk_low/dismiss", headers=owner_headers).json()["dismissed"] is True
    assert client.post("/v1/instance/alerts/nope/dismiss", headers=owner_headers).status_code == 404
    # Mutes survive re-evaluation but are dropped when the alert resolves.
    alerts.evaluate(factory, now + 60)
    assert alerts.active()[0]["dismissed"] is True
    fake_redis.delete(metrics.HOST_KEY)
    alerts.evaluate(factory, now + 120)
    assert fake_redis.hlen(alerts.MUTE_KEY) == 0


def test_webhook_setting_validation_and_payload(client, fake_redis, factory, owner_headers, monkeypatch):
    for bad in ("http://hooks.example.com/x", "https://user:pw@hooks.example.com/x", "https://a b.example.com"):
        resp = client.put("/v1/instance/settings", json={"alert_webhook_url": bad}, headers=owner_headers)
        assert resp.status_code == 422, bad
    url = "https://hooks.example.com/services/test-path"
    resp = client.put(
        "/v1/instance/settings", json={"alert_webhook_url": url, "api_key_rate_limit": 100}, headers=owner_headers
    )
    assert resp.status_code == 200 and resp.json()["alert_webhook_url"] == url
    assert resp.json()["api_key_rate_limit"] == 100

    posted = []
    monkeypatch.setattr(alerts, "post_webhook", lambda u, p: posted.append((u, p)) or (True, "HTTP 200"))
    test = client.post("/v1/instance/alerts/webhook-test", json={}, headers=owner_headers)
    assert test.json() == {"ok": True, "detail": "HTTP 200"} and posted[-1][0] == url

    sent = []
    monkeypatch.setattr(alerts, "deliver_async", lambda u, p: sent.append((u, p)))
    now = time.time()
    put_host(fake_redis, host_point(metrics._minute(now), free=1 * GB))
    alerts.evaluate(factory, now)
    assert sent[0][0] == url
    payload = sent[0][1]
    assert set(payload) == {"alert", "severity", "message", "status", "started_at", "resolved_at", "instance", "text"}
    assert payload["alert"] == "disk_low" and payload["status"] == "open" and payload["instance"].startswith("http")


def test_deliver_retries_with_backoff(monkeypatch):
    results = iter([(False, "HTTP 502"), (False, "ConnectError"), (True, "HTTP 204")])
    monkeypatch.setattr(alerts, "post_webhook", lambda u, p: next(results))
    slept = []
    assert alerts.deliver("https://hooks.example.com/x", {}, sleep=slept.append) is True
    assert slept == list(alerts.WEBHOOK_BACKOFF_S[1:3])
