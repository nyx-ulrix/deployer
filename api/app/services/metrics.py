"""Host, container and API request metrics kept in Redis (docs/MONITORING.md).

- `metrics:host` (sorted set, score = minute epoch): one JSON point per minute - the last 15 s sample
  of that minute (`collect_metrics`: CPU %, memory, disk free under the worker's `/`, which lives on the
  Docker data root, uptime). Trimmed to 24 h, so at most 1440 members.
- `metrics:containers` (string, TTL 5 min): the latest `DockerCli.stats()` of the compose project and
  the deployed app containers.
- `metrics:req:<minute>` (hash, TTL 25 h): per route template `"<METHOD> <path>|n"` (requests), `|e`
  (5xx) and `|b<i>` (latency histogram, LATENCY_BUCKETS_MS), written by the API middleware.
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import threading
import time
from collections.abc import Iterable
from datetime import UTC, datetime

from app.config import get_settings
from app.redis_client import get_redis

log = logging.getLogger(__name__)

HOST_KEY = "metrics:host"
CONTAINERS_KEY = "metrics:containers"
REQ_PREFIX = "metrics:req:"
RETENTION_S = 24 * 3600
SAMPLE_EVERY_S = 15
LATENCY_BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)  # + one overflow bucket
WINDOWS = {"1h": 60, "6h": 360, "24h": 1440}  # minutes
MAX_POINTS = 120
HOST_FIELDS = (
    "cpu_percent",
    "memory_used_bytes",
    "memory_total_bytes",
    "disk_free_bytes",
    "disk_total_bytes",
    "uptime_seconds",
)
UNHEALTHY_STATES = ("restarting", "dead")


def _minute(ts: float | None = None) -> int:
    ts = time.time() if ts is None else ts
    return int(ts) - int(ts) % 60


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace("+00:00", "Z")


# --- worker: sampling ---------------------------------------------------------------------------


def sample(now: float | None = None) -> None:
    """One sample of the host and the containers (worker only: it has the Docker socket)."""
    from app.services.app_runner import DockerError, get_docker
    from app.services.device_host import collect_metrics

    now = time.time() if now is None else now
    host = collect_metrics()
    minute = _minute(now)
    point = {"t": minute, "collected_at": _iso(now), **{k: host.get(k) for k in HOST_FIELDS}}
    try:
        containers = get_docker().stats(get_settings().compose_project)
    except (DockerError, OSError) as exc:
        log.debug("container stats unavailable: %s", exc)
        containers = None
    pipe = get_redis().pipeline()
    pipe.zremrangebyscore(HOST_KEY, minute, minute)
    pipe.zadd(HOST_KEY, {json.dumps(point, separators=(",", ":")): minute})
    pipe.zremrangebyscore(HOST_KEY, "-inf", minute - RETENTION_S)
    if containers is not None:
        doc = {"collected_at": _iso(now), "containers": containers}
        pipe.set(CONTAINERS_KEY, json.dumps(doc, separators=(",", ":")), ex=300)
    pipe.execute()


def sample_loop(stop: threading.Event) -> None:
    """Worker background task: `sample()` every SAMPLE_EVERY_S."""
    while not stop.is_set():
        try:
            sample()
        except Exception:  # noqa: BLE001 - Redis down etc.; try again next round
            log.warning("metrics sample failed", exc_info=True)
        stop.wait(SAMPLE_EVERY_S)


# --- API: request counters ----------------------------------------------------------------------


def record_request(route: str, status: int, duration_ms: float, now: float | None = None) -> None:
    key = f"{REQ_PREFIX}{_minute(now)}"
    try:
        pipe = get_redis().pipeline(transaction=False)
        pipe.hincrby(key, f"{route}|n", 1)
        if status >= 500:
            pipe.hincrby(key, f"{route}|e", 1)
        pipe.hincrby(key, f"{route}|b{bisect.bisect_left(LATENCY_BUCKETS_MS, duration_ms)}", 1)
        pipe.expire(key, RETENTION_S + 3600)
        pipe.execute()
    except Exception:  # noqa: BLE001 - metrics must never break a request
        log.debug("request metrics skipped", exc_info=True)


class RequestMetricsMiddleware:
    """Pure ASGI middleware: count, 5xx and latency per route template (not raw path)."""

    SKIP = frozenset({"/v1/health"})  # the compose healthcheck polls it
    METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        import anyio

        started = time.perf_counter()
        status = 500

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = getattr(scope.get("route"), "path", None)
            if path not in self.SKIP:
                # Bounded field names: route templates and known methods only (not client-chosen strings).
                method = scope["method"] if scope["method"] in self.METHODS else "OTHER"
                route = f"{method} {path}" if path else "unmatched"
                ms = (time.perf_counter() - started) * 1000
                await anyio.to_thread.run_sync(record_request, route, status, ms)


# --- reading ------------------------------------------------------------------------------------


def _hist() -> list[int]:
    return [0] * (len(LATENCY_BUCKETS_MS) + 1)


def p95(hist: list[int]) -> float | None:
    """95th percentile from the histogram, interpolated within its bucket (overflow: 10 s)."""
    total = sum(hist)
    if not total:
        return None
    target, seen = math.ceil(0.95 * total), 0
    for i, count in enumerate(hist):
        if seen + count >= target and count:
            if i >= len(LATENCY_BUCKETS_MS):
                return float(LATENCY_BUCKETS_MS[-1])
            lower = LATENCY_BUCKETS_MS[i - 1] if i else 0
            return round(lower + (LATENCY_BUCKETS_MS[i] - lower) * (target - seen) / count, 1)
        seen += count
    return None


def _routes(raw: dict[str, str], into: dict[str, dict]) -> None:
    for field, value in raw.items():
        route, _, kind = field.rpartition("|")
        entry = into.setdefault(route, {"n": 0, "e": 0, "hist": _hist()})
        if kind == "n":
            entry["n"] += int(value)
        elif kind == "e":
            entry["e"] += int(value)
        elif kind.startswith("b") and kind[1:].isdigit() and int(kind[1:]) < len(entry["hist"]):
            entry["hist"][int(kind[1:])] += int(value)


def request_minutes(minutes: Iterable[int]) -> dict[int, dict[str, dict]]:
    """{minute: {route: {n, e, hist}}} for the given minute epochs."""
    minutes = list(minutes)
    pipe = get_redis().pipeline(transaction=False)
    for m in minutes:
        pipe.hgetall(f"{REQ_PREFIX}{m}")
    out: dict[int, dict[str, dict]] = {}
    for m, raw in zip(minutes, pipe.execute(), strict=True):
        routes: dict[str, dict] = {}
        _routes(raw or {}, routes)
        out[m] = routes
    return out


def _totals(routes: Iterable[dict]) -> dict:
    n = e = 0
    hist = _hist()
    for r in routes:
        n, e = n + r["n"], e + r["e"]
        hist = [a + b for a, b in zip(hist, r["hist"], strict=True)]
    return {"requests": n, "errors_5xx": e, "error_rate": round(e / n, 4) if n else None, "p95_ms": p95(hist)}


def request_totals(minutes: Iterable[int]) -> dict:
    return _totals(r for routes in request_minutes(minutes).values() for r in routes.values())


def host_points(start_minute: int, end_minute: int) -> dict[int, dict]:
    out = {}
    for member in get_redis().zrangebyscore(HOST_KEY, start_minute, end_minute):
        try:
            point = json.loads(member)
            out[int(point["t"])] = point
        except (ValueError, KeyError, TypeError):
            continue
    return out


def current_host(max_age_s: int = 180) -> dict | None:
    """The newest host sample, or None if the worker hasn't sampled for `max_age_s`."""
    newest = get_redis().zrevrange(HOST_KEY, 0, 0)
    if not newest:
        return None
    point = json.loads(newest[0])
    if time.time() - int(point.get("t", 0)) > max_age_s:
        return None
    return {k: point.get(k) for k in (*HOST_FIELDS, "collected_at")}


def containers() -> dict | None:
    raw = get_redis().get(CONTAINERS_KEY)
    return json.loads(raw) if raw else None


def container_problem(c: dict) -> str | None:
    if c.get("status") in UNHEALTHY_STATES:
        return c["status"]
    if c.get("health") == "unhealthy":
        return "unhealthy"
    return None


def _pct(used, total) -> float | None:
    return round(100.0 * used / total, 1) if used is not None and total else None


def _avg(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def metrics(window: str, now: float | None = None) -> dict:
    minutes = WINDOWS[window]
    step = max(1, math.ceil(minutes / MAX_POINTS))
    end = _minute(now)
    start = end - (minutes - 1) * 60
    host = host_points(start, end)
    reqs = request_minutes(range(start, end + 60, 60))
    points = []
    for bucket in range(start, end + 60, step * 60):
        mins = range(bucket, min(bucket + step * 60, end + 60), 60)
        hp = [host[m] for m in mins if m in host]
        routes = [r for m in mins for r in reqs[m].values()]
        totals = _totals(routes)
        free = [p["disk_free_bytes"] for p in hp if p.get("disk_free_bytes") is not None]
        points.append(
            {
                "t": _iso(bucket),
                "cpu_percent": _avg([p.get("cpu_percent") for p in hp]),
                "memory_percent": _avg([_pct(p.get("memory_used_bytes"), p.get("memory_total_bytes")) for p in hp]),
                "disk_free_bytes": min(free) if free else None,
                "requests_per_min": round(totals["requests"] / len(mins), 2),
                "error_rate": totals["error_rate"],
                "p95_ms": totals["p95_ms"],
            }
        )
    by_route: dict[str, list[dict]] = {}
    for routes in reqs.values():
        for route, r in routes.items():
            by_route.setdefault(route, []).append(r)
    top = sorted(((route, _totals(rs)) for route, rs in by_route.items()), key=lambda x: -x[1]["requests"])[:15]
    return {
        "window": window,
        "step_seconds": step * 60,
        "current": current_host(),
        "points": points,
        "requests": _totals(r for routes in reqs.values() for r in routes.values()),
        "routes": [{"route": route, **t} for route, t in top],
        "containers": containers(),
    }


def summary(now: float | None = None) -> dict:
    end = _minute(now)
    snap = containers()
    listed = (snap or {}).get("containers") or []
    return {
        "current": current_host(),
        "requests_5m": request_totals(range(end - 4 * 60, end + 60, 60)),
        "containers": {
            "total": len(listed),
            "running": sum(1 for c in listed if c.get("status") == "running"),
            "problems": sum(1 for c in listed if container_problem(c)),
        }
        if snap
        else None,
    }
