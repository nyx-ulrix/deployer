# Monitoring and alerts

*Settings → Monitoring* (instance owner only) shows how the PC running Deployer is doing: host CPU,
memory and disk, every Deployer container and deployed app, API traffic, and alerts. Everything is
kept in Redis for 24 hours; nothing leaves the PC unless you set an alert webhook.

## What is collected

| What | Who collects it | How often | Kept |
|---|---|---|---|
| Host: CPU %, memory used/total, disk free/total, uptime | worker (`metrics` thread, `device_host.collect_metrics`) | every 15 s | 24 h at 1-minute resolution (the last sample of each minute) |
| Containers: status, health, restart count, CPU %, memory | worker (`DockerCli.stats()`: `docker ps`, `docker inspect`, `docker stats --no-stream`) | every 15 s | latest snapshot only |
| API requests: count, 5xx count, latency histogram | API middleware, per route template (`GET /v1/projects/{project_id}`, never the raw path) | every request (not `/v1/health`) | 24 h, per minute |

- **Disk** is whichever of two disks has less free space: the worker's root filesystem (the Docker
  data root, inside the WSL2 VM's sparse `ext4.vhdx`, which reports about 1 TB whatever the drive
  under it holds) and the Windows drive the install folder is on (`./mongodb` bind-mounted read-only
  at `DEVICE_DISK_PATH=/host-disk`, named by `DEPLOYER_HOST_DRIVE` in `.env`). `disk_label` says which
  (`drive C:`, `the Docker disk`). **Memory** and **CPU** are the engine VM's, which is what Deployer
  can actually use.
- **Containers**: the compose project's services (`COMPOSE_PROJECT`, default `deployer`) plus every
  container labelled `deployer.app` (deployed apps).
- **p95 latency** is estimated from a fixed histogram (5 ms … 10 s buckets, interpolated), so it is
  approximate; anything over 10 s shows as 10 s. Long downloads (exports, backups) count their full
  transfer time.

Redis keys: `metrics:host` (sorted set, ≤ 1440 points), `metrics:containers` (5-minute TTL),
`metrics:req:<minute>` (hash per minute, 25-hour TTL). If Redis is down, metrics are skipped and
requests are unaffected.

## Alerts

The worker that leads the scheduler evaluates these rules once a minute. A condition becomes an
**open alert** once it has held for its duration and **resolves** as soon as it no longer holds.

| Alert | Condition | Severity |
|---|---|---|
| `disk_low` | disk free < 10 % or < 5 GB on the fuller of the Docker disk and the Windows drive | critical |
| `memory_high` | memory used > 90 % for 5 minutes | warning |
| `container_unhealthy` | a container `restarting`, `dead` or `unhealthy` for over 2 minutes | critical (Deployer service) / warning (app) |
| `api_errors` | API 5xx rate > 5 % over the last 5 minutes (at least 20 requests) | warning |
| `backup_failed` | a backup (snapshot, platform snapshot or point-in-time log save) failed in the last 24 h and has not succeeded since, per database / platform data; failed restores, restore tests, pruning and off-PC copies do not raise it | critical |
| `backup_stale` | a managed database with backups on has had no successful snapshot for twice its schedule (e.g. over 2 hours when hourly), counted from its creation when it has none, and still true an hour later (so a PC waking from sleep gets its catch-up snapshot first) - catches a snapshot job that hangs instead of failing | critical |
| `backup_verify_failed` | the latest restore test (`backup.verify`) of a database's backups failed; resolves when a later one passes (retried daily) | critical |
| `tunnel_down` | remote access is on but the Cloudflare connector has not been running for 5 minutes | critical |
| `replica_error` / `replica_lag` | a co-host database copy in `error` (critical), or a syncing copy more than 10 minutes behind (warning); a co-hosted app copy that `failed` (warning) | as noted |

Alert state lives in Redis (`alerts:state`, with `first_seen`, `last_seen`, `opened_at`). The owner
sees a bell with the number of open alerts in the header; *Settings → Monitoring* lists them.
**Snooze** hides an alert from the bell for a while, **Dismiss** until it resolves (`alerts:mute`);
neither stops it from resolving or re-opening later.

### Webhook

Set **Alert webhook URL** on the Monitoring page (instance setting `alert_webhook_url`, stored
encrypted because chat webhooks carry a token in the path). It must be `https://`, at most 500
characters, with no `user:password@` or `#fragment`. When an alert opens or resolves, the worker POSTs:

```json
{"alert": "disk_low", "severity": "critical", "message": "Disk space low: 3.2 GB free on drive C: (4 %)",
 "status": "open", "started_at": "2026-09-28T10:00:00Z", "resolved_at": null,
 "instance": "https://deployer.example.com",
 "text": "[open] critical: Disk space low: 3.2 GB free on drive C: (4 %) (https://deployer.example.com)"}
```

`status` is `open` or `resolved`; `text` is a one-line summary so Slack-style incoming webhooks show
it as-is. Any 2xx counts as delivered; otherwise it retries after 10 s, 60 s
and 5 minutes (redirects are not followed, the URL is never logged). Messages contain names and
numbers only, never job error text, tokens or connection strings. **Send test** posts one
`"status": "test"` message and shows the HTTP status. There is no email/SMTP delivery: point the
webhook at Slack, Discord (append `/slack` to a Discord webhook URL), ntfy or your own endpoint.

## API key rate limit

Project API keys (`dpl_…`, data/query/schema/MCP endpoints) are limited to **600 requests per minute
per key** by default: instance setting `api_key_rate_limit` (0 = unlimited), editable on the
Monitoring page. Over the limit: `429 rate_limited` with `details.retry_after` and a `Retry-After`
header. This is separate from the MCP limit of 60 tool calls per minute ([MCP.md](MCP.md)). Signed-in
users (dashboard sessions) are not limited this way.

## API

See [API.md](API.md#monitoring-instance-owner-only): `GET /v1/instance/metrics?window=1h|6h|24h`,
`GET /v1/instance/metrics/summary`, `GET /v1/instance/alerts`, `POST /v1/instance/alerts/{id}/dismiss`,
`POST /v1/instance/alerts/{id}/snooze`, `POST /v1/instance/alerts/webhook-test`.

## Not covered (yet)

- Metrics of host devices and co-host PCs (each installation monitors itself; see *Devices* for
  their heartbeat status) and per-container history (only the latest snapshot is kept).
- Email/SMTP alerts, custom thresholds, and a Prometheus/OpenMetrics endpoint.
- Webhook retries do not survive a worker restart.
