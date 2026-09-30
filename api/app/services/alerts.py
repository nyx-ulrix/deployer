"""Alert rules, state and webhook delivery (docs/MONITORING.md).

`evaluate()` runs on the worker's scheduler leader once a minute. Each rule yields the conditions that
are true right now; a condition becomes an open alert once it has held for its `for_s`, and is resolved
(removed) as soon as it no longer holds. Redis keys:

- `alerts:state` (hash id -> JSON): pending and open alerts with first_seen / last_seen / opened_at.
- `alerts:mute` (hash id -> JSON): owner's dismiss / snooze, dropped when the alert resolves.

With the `alert_webhook_url` instance setting, an alert opening or resolving POSTs
`{alert, severity, message, status, started_at, resolved_at, instance, text}` (retried with backoff).
Messages never contain secrets: names and numbers only, no job error text.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import AppReplica, Backup, BackupPolicy, DataSource, Device, Job, SourceReplica, utcnow
from app.redis_client import get_redis
from app.services import connections, metrics
from app.services.instance_settings import get_value, public_url

log = logging.getLogger(__name__)

STATE_KEY = "alerts:state"
MUTE_KEY = "alerts:mute"
EVALUATE_EVERY_S = 60
GB = 1024**3
WEBHOOK_TIMEOUT_S = 10
WEBHOOK_BACKOFF_S = (0, 10, 60, 300)  # delay before each attempt


@dataclass
class Condition:
    alert: str  # rule name, e.g. "disk_low"
    severity: str  # warning | critical
    message: str
    for_s: int = 0


# Plain words for the backup job types, so an alert never shows "backup.archive_logs". "{}" is the database;
# prune and copy run for every database at once (no data_source_id), so they name none.
BACKUP_JOB_LABELS = {
    "backup.snapshot": "A backup of {}",
    "backup.platform_snapshot": "The backup of the platform data (users, projects, settings)",
    "backup.archive_logs": "Saving changes for point-in-time restore of {}",
    "backup.restore": "A restore of {}",
    "backup.verify": "A restore test of {}",
    "backup.prune": "Removing old backups",
    "backup.copy": "Copying backups off this PC",
}


def _fmt_gb(value: float) -> str:
    return f"{value / GB:.1f} GB"


def _fmt_age(age: timedelta) -> str:
    hours = int(age.total_seconds() // 3600)
    return f"{hours // 24} days" if hours >= 48 else f"{hours} hours"


# --- rules --------------------------------------------------------------------------------------


def _host_rules(out: dict[str, Condition]) -> None:
    host = metrics.current_host()
    if not host:
        return
    free, total = host.get("disk_free_bytes"), host.get("disk_total_bytes")
    if free is not None and total and (free < 0.10 * total or free < 5 * GB):
        out["disk_low"] = Condition(
            "disk_low",
            "critical",
            f"Disk space low: {_fmt_gb(free)} free on {host.get('disk_label') or 'the host'} "
            f"({100 * free / total:.0f} %)",
        )
    used, mem_total = host.get("memory_used_bytes"), host.get("memory_total_bytes")
    if used is not None and mem_total and used > 0.90 * mem_total:
        out["memory_high"] = Condition(
            "memory_high", "warning", f"Memory use above 90 % ({100 * used / mem_total:.0f} %) for 5 minutes", 300
        )


def _container_rules(out: dict[str, Condition]) -> None:
    snap = metrics.containers()
    for c in (snap or {}).get("containers") or []:
        problem = metrics.container_problem(c)
        if problem:
            what = f"app container {c['name']}" if c.get("app_id") else f"service {c.get('service') or c['name']}"
            out[f"container:{c['name']}"] = Condition(
                "container_unhealthy",
                "warning" if c.get("app_id") else "critical",
                f"The {what} is {problem} (for over 2 minutes)",
                120,
            )


def _api_rule(out: dict[str, Condition], now: float) -> None:
    end = metrics._minute(now)
    totals = metrics.request_totals(range(end - 4 * 60, end + 60, 60))
    if totals["requests"] >= 20 and totals["errors_5xx"] / totals["requests"] > 0.05:
        out["api_errors"] = Condition(
            "api_errors",
            "warning",
            f"API 5xx error rate {100 * totals['error_rate']:.1f} % over the last 5 minutes "
            f"({totals['errors_5xx']} of {totals['requests']} requests)",
        )


def _backup_rules(db: Session, out: dict[str, Condition]) -> None:
    since = utcnow() - timedelta(hours=24)
    failed = db.scalars(
        select(Job)
        .where(Job.type.like("backup.%"), Job.status == "failed", Job.finished_at >= since)
        .order_by(Job.finished_at.desc())
    ).all()
    seen: set[tuple[str, str | None]] = set()
    for job in failed:
        key = (job.type, job.data_source_id)
        if key in seen:
            continue
        seen.add(key)
        recovered = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.type == job.type,
                Job.data_source_id.is_(None)
                if job.data_source_id is None
                else Job.data_source_id == job.data_source_id,
                Job.status == "succeeded",
                Job.finished_at > job.finished_at,
            )
        )
        if recovered:
            continue
        ds = db.get(DataSource, job.data_source_id) if job.data_source_id else None
        # A hard delete nulls the job's data_source_id (ON DELETE SET NULL).
        target = f"database {ds.name}" if ds is not None and ds.deleted_at is None else "a deleted database"
        what = BACKUP_JOB_LABELS.get(job.type, "A backup task for {}").format(target)
        out[f"backup:{job.type}:{job.data_source_id or 'platform'}"] = Condition(
            "backup_failed",
            "critical",
            f"{what} failed. Open Settings > Backups for the reason; this alert clears once it next succeeds",
        )
    # A job that never ends (a hung tool) fails nothing: alert when a scheduled database has had no
    # successful snapshot for twice its schedule. Held for an hour first, so a PC that just woke from
    # sleep (or backups just re-enabled) gets its catch-up snapshot before anyone is paged.
    from app.services.backups import SCHEDULES, last_verification, supported

    now = utcnow()
    last_ok = (
        select(func.max(Backup.started_at))
        .where(Backup.data_source_id == DataSource.id, Backup.status == "succeeded")
        .scalar_subquery()
    )
    for ds, schedule, last in db.execute(
        select(DataSource, BackupPolicy.schedule, last_ok)
        .join(BackupPolicy, BackupPolicy.data_source_id == DataSource.id)
        .where(BackupPolicy.enabled.is_(True), DataSource.mode == "managed", DataSource.deleted_at.is_(None))
    ).all():
        every = SCHEDULES.get(schedule, SCHEDULES["hourly"])
        if supported(ds) and not connections.device_removed(ds) and now - (last or ds.created_at) > 2 * every:
            out[f"backup_stale:{ds.id}"] = Condition(
                "backup_stale",
                "critical",
                f"Database {ds.name} has had no successful backup for over {_fmt_age(2 * every)}; "
                "see Settings > Backups",
                3600,
            )
    # A failed verification is a job result, not a failed job: alert until a later verification passes.
    for ds_id in db.scalars(select(Backup.data_source_id).where(Backup.verify_status == "failed").distinct()):
        ds = db.get(DataSource, ds_id) if ds_id else None
        checked = last_verification(db, ds_id) if ds is not None and ds.deleted_at is None else None
        if checked is not None and checked.verify_status == "failed":
            out[f"backup_verify:{ds_id}"] = Condition(
                "backup_verify_failed",
                "critical",
                f"The latest restore test of a backup of database {ds.name} failed; see Settings > Backups",
            )


def _tunnel_rule(db: Session, out: dict[str, Condition]) -> None:
    from app.services import remote_access

    if remote_access.mode(db) == "off":
        return
    connector, _ = remote_access.connector_state(db)
    if not connector.get("running"):
        out["tunnel_down"] = Condition(
            "tunnel_down", "critical", "The Cloudflare tunnel connector is down (for over 5 minutes)", 300
        )


def _replica_rules(db: Session, out: dict[str, Condition]) -> None:
    now = utcnow()
    rows = db.execute(
        select(SourceReplica, DataSource.name, Device.name)
        .join(DataSource, DataSource.id == SourceReplica.data_source_id)
        .join(Device, Device.id == SourceReplica.device_id)
        .where(SourceReplica.status.in_(("error", "syncing")))
    ).all()
    for rep, source, device in rows:
        if rep.status == "error":
            out[f"replica:{rep.id}"] = Condition(
                "replica_error", "critical", f"The copy of {source} on {device} stopped syncing (error)"
            )
            continue
        lag = rep.lag_seconds or 0.0
        if rep.last_synced_at is not None:
            lag = max(lag, (now - rep.last_synced_at).total_seconds())
        if lag > 600:
            out[f"replica:{rep.id}"] = Condition(
                "replica_lag", "warning", f"The copy of {source} on {device} is {int(lag // 60)} minutes behind"
            )
    for rep, device in db.execute(
        select(AppReplica, Device.name)
        .join(Device, Device.id == AppReplica.device_id)
        .where(AppReplica.status == "failed")
    ).all():
        out[f"app_replica:{rep.id}"] = Condition(
            "replica_error", "warning", f"The co-hosted copy of an app on {device} failed"
        )


def conditions(db: Session, now: float) -> dict[str, Condition]:
    out: dict[str, Condition] = {}
    for rule in (
        lambda: _host_rules(out),
        lambda: _container_rules(out),
        lambda: _api_rule(out, now),
        lambda: _backup_rules(db, out),
        lambda: _tunnel_rule(db, out),
        lambda: _replica_rules(db, out),
    ):
        try:
            rule()
        except Exception:  # noqa: BLE001 - one broken rule must not hide the others
            log.exception("alert rule failed")
    return out


# --- state --------------------------------------------------------------------------------------


def evaluate(session_factory, now: float | None = None) -> list[tuple[str, dict]]:
    """One evaluation round. Returns the (event, alert) pairs it sent ("open" / "resolved")."""
    now = time.time() if now is None else now
    with session_factory() as db:
        current = conditions(db, now)
        webhook = get_value(db, "alert_webhook_url")
        instance = public_url(db)
    r = get_redis()
    state = {k: json.loads(v) for k, v in r.hgetall(STATE_KEY).items()}
    events: list[tuple[str, dict]] = []
    pipe = r.pipeline()
    for alert_id, cond in current.items():
        a = state.get(alert_id) or {"id": alert_id, "first_seen": now, "status": "pending"}
        a.update(alert=cond.alert, severity=cond.severity, message=cond.message, last_seen=now)
        if a["status"] == "pending" and now - a["first_seen"] >= cond.for_s:
            a.update(status="open", opened_at=now)
            events.append(("open", a))
        pipe.hset(STATE_KEY, alert_id, json.dumps(a))
    for alert_id, a in state.items():
        if alert_id not in current:
            pipe.hdel(STATE_KEY, alert_id)
            pipe.hdel(MUTE_KEY, alert_id)
            if a.get("status") == "open":
                events.append(("resolved", {**a, "resolved_at": now}))
    pipe.execute()
    if webhook:
        for event, a in events:
            deliver_async(str(webhook), webhook_payload(a, event, instance))
    return events


def _iso(value) -> str | None:
    return metrics._iso(value) if value else None


def alert_out(a: dict, mute: dict | None = None) -> dict:
    mute = mute or {}
    snoozed = mute.get("snoozed_until") or 0
    return {
        "id": a["id"],
        "alert": a.get("alert"),
        "severity": a.get("severity"),
        "message": a.get("message"),
        "first_seen": _iso(a.get("first_seen")),
        "last_seen": _iso(a.get("last_seen")),
        "opened_at": _iso(a.get("opened_at")),
        "dismissed": bool(mute.get("dismissed")),
        "snoozed_until": _iso(snoozed) if snoozed > time.time() else None,
    }


def active() -> list[dict]:
    """Open alerts (pending ones haven't lasted long enough yet), critical first."""
    r = get_redis()
    mutes = {k: json.loads(v) for k, v in r.hgetall(MUTE_KEY).items()}
    out = [alert_out(a, mutes.get(a["id"])) for a in map(json.loads, r.hgetall(STATE_KEY).values())]
    out = [a for a in out if a["opened_at"]]
    return sorted(out, key=lambda a: (a["severity"] != "critical", a["first_seen"] or ""))


def visible(alerts: list[dict]) -> list[dict]:
    return [a for a in alerts if not a["dismissed"] and not a["snoozed_until"]]


def mute(alert_id: str, *, dismissed: bool = False, snooze_minutes: int | None = None) -> dict:
    r = get_redis()
    raw = r.hget(STATE_KEY, alert_id)
    if raw is None:
        raise ApiError(404, "not_found", "Alert not found (it may have resolved)")
    doc = json.loads(r.hget(MUTE_KEY, alert_id) or "{}")
    if dismissed:
        doc["dismissed"] = True
    if snooze_minutes:
        doc["snoozed_until"] = time.time() + snooze_minutes * 60
    r.hset(MUTE_KEY, alert_id, json.dumps(doc))
    return alert_out(json.loads(raw), doc)


# --- webhook ------------------------------------------------------------------------------------


def validate_webhook_url(value: str) -> str:
    value = value.strip()

    def bad(message: str) -> ApiError:
        return ApiError(422, "validation_error", message, {"field": "alert_webhook_url"})

    if len(value) > 500 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise bad("alert_webhook_url must be a URL of at most 500 characters without spaces")
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError as exc:
        raise bad("alert_webhook_url is not a valid URL") from exc
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise bad("alert_webhook_url must be an https:// URL without user:password@ or #fragment")
    return value


def webhook_payload(a: dict, event: str, instance: str) -> dict:
    return {
        # `text` makes Slack (and Discord's /slack) incoming webhooks render it as-is.
        "text": f"[{event}] {a.get('severity')}: {a.get('message')} ({instance})",
        "alert": a.get("alert"),
        "severity": a.get("severity"),
        "message": a.get("message"),
        "status": event,
        "started_at": _iso(a.get("first_seen")),
        "resolved_at": _iso(a.get("resolved_at")),
        "instance": instance,
    }


def post_webhook(url: str, payload: dict) -> tuple[bool, str]:
    """One delivery attempt. Returns (ok, short description). No redirects; the body is not read back."""
    try:
        resp = httpx.post(
            url, json=payload, timeout=WEBHOOK_TIMEOUT_S, follow_redirects=False, headers={"User-Agent": "Deployer"}
        )
    except httpx.HTTPError as exc:
        return False, type(exc).__name__
    return resp.is_success, f"HTTP {resp.status_code}"


def deliver(url: str, payload: dict, sleep=time.sleep) -> bool:
    for attempt, delay in enumerate(WEBHOOK_BACKOFF_S):
        if delay:
            sleep(delay)
        ok, detail = post_webhook(url, payload)
        if ok:
            return True
        log.warning("alert webhook attempt %d failed: %s", attempt + 1, detail)  # never log the URL
    return False


def deliver_async(url: str, payload: dict) -> None:
    # ponytail: retries live in a daemon thread and are lost on a worker restart; a Redis outbox if that matters.
    threading.Thread(target=deliver, args=(url, payload), name="alert-webhook", daemon=True).start()
