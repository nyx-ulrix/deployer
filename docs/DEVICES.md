# Host Devices

A Deployer installation can be **attached to another Deployer** as a *host device*. Any signed-in
user can do this with their own PC: install Deployer on the PC, open its dashboard, choose
**Make this PC a host device**, and sign in to the main Deployer to approve it. Projects can then
place their managed databases on that device. Everything else (users, projects, schema viewer,
data browser, exports, backups UI) keeps working from the main Deployer's dashboard.

## Terms

| Term | Meaning |
|---|---|
| **Main Deployer** (primary) | The installation people sign in to. Owns users, projects and all metadata. |
| **Host device** | Another installation attached to the main Deployer. Runs MariaDB/MongoDB/Redis/worker locally and hosts databases for projects. Has no users of its own. |
| **The primary itself** | Always available as a host, shown as "Main server" (`device_id = null`). |

## Connectivity

Host devices connect **outbound** to the main Deployer's public URL (a WebSocket for control plus
HTTPS for bulk transfers). The main Deployer never connects to a device, so devices work behind home
routers without port forwarding. The only requirement is that the device can reach the main
Deployer's URL (same LAN, Tailscale, Cloudflare Tunnel, ...). Plain `http://` URLs are allowed only
for `localhost`, private LAN ranges and `*.ts.net`; the dashboard warns otherwise.

## Enrollment (device authorization flow, like signing in on a TV)

```text
Device dashboard (http://localhost:8080, not initialized OR local instance owner)
  1. User enters main Deployer URL + device name
  2. Device API → POST {primary}/v1/devices/enrollments  {name, hostname, os, version, capabilities}
       ← {enrollment_id, user_code "ABCD-EFGH", verification_uri, poll_secret, expires_in: 900}
  3. Device dashboard shows the code and a button opening
       {primary}/devices/approve?code=ABCD-EFGH   (new tab)
  4. User signs in to the MAIN Deployer there (password / Google / GitHub) and approves:
       name, roles [database_host], sharing (all my projects | selected projects)
  5. Device API polls POST {primary}/v1/devices/enrollments/{id}/poll {poll_secret} every 5 s
       ← {status:"approved", device_id, device_token}
  6. Device stores {primary_url, device_id, device_token} encrypted (MASTER_KEY) and starts the agent
```

The user's password never touches the device. The device token (`dpd_<random>`, SHA-256 hashed on
the primary) only authorizes the device endpoints below.

## Runtime protocol

- **Control channel:** device opens `WS {primary}/v1/devices/connect` with header
  `Authorization: Device <token>`. Messages are JSON:
  - device → primary: `{"type":"hello", version, capabilities, metrics}`,
    `{"type":"heartbeat", metrics}` every 20 s, `{"type":"result", id, ok, result|error}`,
    `{"type":"progress", job_id, progress, message}`.
  - primary → device: `{"type":"call", id, method, params, timeout}`.
  - Reconnect with exponential backoff (1 s → 60 s). Primary marks a device offline after 60 s
    without a heartbeat (`devices.last_seen_at`, live state in Redis `device:{id}:online`).
- **RPC routing on the primary:** any API process publishes calls to Redis channel
  `device:{id}:calls`; the process holding the socket forwards them; replies come back on
  `device:rpc:reply:{call_id}`. Default timeout 30 s; long work runs as jobs (below).
- **Bulk data:** `PUT/GET {primary}/v1/devices/transfers/{transfer_id}` (device token), streamed,
  used for backup copies, exports and moving databases. Transfers are temp files on the primary,
  deleted after download or after 24 h.
- **Metrics:** cpu %, memory used/total, disk free/total for the Docker data root, uptime,
  engines available (`mariadb`, `mongodb` – false without AVX), Deployer version.

### RPC methods (device side)

| Method | Params | Result |
|---|---|---|
| `datasource.provision` | `{kind, database_name}` | `{database_name, username}` (password stays on the device) |
| `datasource.drop` | `{kind, database_name}` | `{}` |
| `datasource.check` | `{kind, database_name}` | `{ok, message, server_version}` |
| `datasource.call` | `{kind, database_name, source_name?, op, args}` | op result — `op` is one of the local service operations: `introspect`, `entity` (`{name}`), `ddl_export`, `connection_info`, `query` (`{query, max_rows, timeout_seconds, read_only}` — the query console runner, [QUERY_CONSOLE.md](QUERY_CONSOLE.md); the primary calls it with timeout `timeout_seconds + 15`), `rows.list`, `rows.insert`, `rows.update`, `rows.delete`, `documents.list`, `documents.insert`, `documents.update`, `documents.delete`, `table.create`, `table.drop`, `collection.create`, `collection.drop` |
| `datasource.export` | `{kind, database_name, source_name?, transfer_id}` | `{sha256, size, tables, rows, documents}` — device writes the export `data` entry (gzip JSON) and PUTs it to the transfer |
| `datasource.import` | `{kind, database_name, source_name?, transfer_id}` | `{rows, documents}` — device GETs a gzip JSON `data` entry and restores it into a hosted database |
| `jobs.run` | `{job_id, type, params, project_id?, data_source_id?}` | job result. `type` is `executor.<method>` (backup executor calls: `snapshot`, `archive_logs`, `restore`, `verify`, `delete_artifact`, `artifact_exists`, `storage_stats`) or a `runs_on="host"` job type. Device streams `progress` messages with the same `job_id` |
| `transfer.upload` | `{transfer_id, local_ref}` | `{sha256, size}` — device PUTs a local file (e.g. a backup blob) to the primary |
| `transfer.download` | `{transfer_id, local_ref}` | `{sha256, size}` — device GETs a transfer into its local store |
| `storage.delete` | `{local_ref}` | `{}` |
| `device.detach` | `{}` | `{}` — device forgets its credentials after confirming no hosted databases remain (409 `databases_remain` otherwise) |
| `device.ping` / `device.status` | `{}` | `{pong, time, version}` / `{hosted_sources, metrics}` |

Devices only execute these methods against **their own managed databases** — never arbitrary hosts:
`datasource.*` and `executor.snapshot|archive_logs|restore` only accept databases listed in the
device's `device_hosted_credentials` (`datasource.provision` only creates databases that don't exist
yet), and `local_ref`s must stay inside the device's backup store. Errors come back as
`{status, code, message, details}` and are re-raised on the primary with the same status and code.

Implementation: `app/services/device_rpc.py` (primary), `device_agent.py` + `device_host.py`
(device), `source_ops.py` (routing of data source operations), `device_executor.py` (backups),
`device_moves.py` (moves), `device_worker.py` (worker plugin, `WORKER_PLUGINS=app.services.device_worker`).

## Main Deployer API (primary side)

Base `/v1`. "user" = `Authorization: Bearer`; "device" = `Authorization: Device <token>` only (user
tokens are rejected there, device tokens are rejected on every user endpoint).

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| POST | `/devices/enrollments` | none (20/h per IP) | `{name, hostname?, os?, version?, capabilities?}` | `{enrollment_id, user_code, verification_uri, poll_secret, expires_in:900, interval:5}` |
| POST | `/devices/enrollments/{id}/poll` | poll secret | `{poll_secret}` | `{status:"pending"\|"denied"\|"expired"\|"consumed", interval}` or once `{status:"approved", device_id, device_token, device_name}`. Faster than every 4 s → 429 `slow_down`; wrong secret → 404 |
| GET | `/devices/enrollments?code=ABCD-EFGH` (also `/devices/enrollments/by-code/{code}`) | user (30 lookups/10 min) | – | `DeviceEnrollment`; 404 if unknown |
| POST | `/devices/enrollments/{id}/approve` | user | `{user_code?, name?, roles?:("database_host"\|"backup_storage")[], sharing_mode?:"my_projects"\|"selected", project_ids?:string[]}` | `Device` (owned by the caller); 409 `enrollment_not_pending`; 404 if `user_code` doesn't match |
| POST | `/devices/enrollments/{id}/deny` | user | `{user_code?}` | `{ok:true}` |
| GET | `/devices?scope=mine\|all` | user | `all` only for the instance owner (ignored otherwise) | `Device[]` |
| GET | `/devices/{id}` | device owner or instance owner | – | `Device` |
| PATCH | `/devices/{id}` | device owner or instance owner (`status`: instance owner only) | `{name?, roles?, sharing_mode?, project_ids?, status?:"active"\|"disabled"}` | `Device`; disabling closes its socket |
| DELETE | `/devices/{id}?force=false` | device owner or instance owner (`force`: instance owner) | – | `{ok:true}`; 409 `device_in_use` `{details.data_sources}` while it hosts databases; `force=true` marks them `status=error, "device removed"` |
| GET | `/projects/{id}/placement-options` | admin+ | – | `PlacementOption[]` (main server first) |
| POST | `/projects/{id}/data-sources/{sid}/move` | admin+ | `{device_id: string\|null}` | `{job: Job}` (`type:"device.move"`, BACKUPS.md `Job`); 400 `not_managed`; 409 `already_there` / `move_in_progress`; 503 `device_offline`; 422 `device_not_eligible` |
| POST | `/projects/{id}/data-sources` | admin+ | `DataSourceInput` + `device_id?` (managed only) | `DataSource` |
| POST | `/projects` | user | `provision:{sql, nosql, device_id?}` | `Project` |
| WS | `/devices/connect` | device | protocol above | close codes: 4403 disabled/removed, 4000 replaced by a newer connection, 4408 no heartbeat, 1009 message too large |
| PUT | `/devices/transfers/{transfer_id}` | device (the transfer's device) | raw bytes | `{ok, size, sha256}`; 409 if already uploaded |
| GET | `/devices/transfers/{transfer_id}` | device (the transfer's device) | – | raw bytes (deleted after a complete download) |

```ts
type Device = {
  id: string; name: string; owner_id: string; owner_email: string | null; owner_name: string | null;
  status: "active" | "disabled"; roles: ("database_host" | "backup_storage")[];
  sharing_mode: "my_projects" | "selected"; project_ids: string[];      // [] unless selected
  hostname: string | null; os: string | null; version: string | null;
  capabilities: { engines?: { mariadb: boolean; mongodb: boolean }; methods?: string[]; protocol?: number };
  metrics: { cpu_percent: number | null; memory_used_bytes: number | null; memory_total_bytes: number | null;
             disk_free_bytes: number | null; disk_total_bytes: number | null; uptime_seconds: number | null;
             engines: { mariadb: boolean; mongodb: boolean }; version: string; collected_at: string } | null;
  engines: { mariadb: boolean; mongodb: boolean };
  online: boolean; last_seen_at: string | null;
  hosted_sources_count: number;          // live sources only (not "Recently deleted" ones)
  can_manage: boolean;                   // caller is the device owner or the instance owner
  created_at: string;
};
type DeviceEnrollment = {
  id: string; user_code: string; name: string; hostname: string | null; os: string | null;
  version: string | null; capabilities: object; status: "pending" | "approved" | "denied" | "expired" | "consumed";
  expires_at: string; created_at: string;
};
type PlacementOption = {
  device_id: string | null; name: string; online: boolean; eligible: boolean; reason: string | null;
  disk_free_bytes: number | null; engines: { mariadb: boolean; mongodb: boolean }; roles: string[];
};
// DataSource gains: device_id: string | null; device_name: string | null
```

Device-hosted sources: every schema / data browser / query console / check / connection / DDL export
route routes to the device (`503 device_offline` while it is disconnected; the schema view and DDL
export show an error entry instead). `GET .../connection` returns the device-local connection details (fetched from the
device, never stored on the primary) with an `external_hint` and `device_id`.

### Errors (besides the common codes in API.md)

| Code | HTTP | When |
|---|---|---|
| `rate_limited` | 429 | Enrollment creation (20/h per IP) or code lookups (30/10 min per user) |
| `slow_down` | 429 | Device polled an enrollment faster than every 4 s (`details.interval`) |
| `enrollment_not_pending` | 409 | Approving/denying an enrollment that is not `pending` |
| `device_disabled` | 403 | A disabled device used its token |
| `device_in_use` | 409 | Removing a device that still hosts live databases (`details.data_sources`) |
| `device_not_eligible` | 422 | Placement on a device that may not host databases for this project |
| `managed_mongodb_unavailable` | 409 | Placement of a MongoDB database on a device (or main server) without managed MongoDB |
| `not_managed`, `already_there`, `move_in_progress` | 400 / 409 / 409 | Move preconditions |
| `device_offline` | 503 | The device is not connected (also for every schema/data/backup route of its sources) |
| `device_timeout` | 504 | The device did not answer an RPC in time |
| `device_busy` | 503 | The device's call queue is full |
| `device_error`, `result_too_large` | 502 | Malformed or oversized answer from the device |
| `payload_too_large` | 413 | An RPC request exceeds the 8 MiB message limit |
| `file_too_large` | 413 | A transfer upload exceeds `DEVICE_MAX_TRANSFER_BYTES` (default 64 GiB) |
| `transfer_complete` | 409 | `PUT /devices/transfers/{id}` after the upload already completed |
| `transfer_incomplete`, `transfer_failed` | 502 | The device upload did not complete / the device could not reach the transfer endpoint |

Errors raised **on the device** and re-raised on the primary with the same status: `unknown_method` (400),
`unsupported_job` (400), `not_hosted` (404), `database_exists` (409), `databases_remain` (409),
`invalid_local_ref` (422), `validation_error` (422), `database_unavailable` (503),
`device_internal_error` (500).

## Data model (primary)

| Table | Purpose |
|---|---|
| `devices` | `id, name, owner_id, status (active/disabled), roles (JSON list), sharing_mode (my_projects/selected), token_hash, hostname, os, version, capabilities (JSON), metrics (JSON), last_seen_at, created_at` |
| `device_enrollments` | `id, user_code, poll_secret_hash, name, hostname, os, version, capabilities, status (pending/approved/denied/expired/consumed), approved_by_id, device_id, expires_at, created_at` |
| `device_project_grants` | `device_id, project_id` — used when `sharing_mode = selected` |
| `data_sources.device_id` | nullable FK; `null` = main server |

## Rules

- Any signed-in user can approve an enrollment; the device is owned by them.
- A device can host databases for a project if its owner is a member (developer+) of that project and
  either `sharing_mode = my_projects` (projects where the device owner is owner/admin) or the project
  is in `device_project_grants`. The project's admins choose placement when creating a managed data
  source ("Host on"), restoring a backup into a new source, or moving a database. The same sharing
  rule applies to devices with the `backup_storage` role chosen as a backup copy target
  (`copy_to_device_id`, BACKUPS.md).
- Instance owner can see, disable and remove every device. Device owner can rename, change roles and
  sharing, and remove their device.
- Removing a device requires it to host no databases — move them first
  (`POST .../data-sources/{sid}/move`, which snapshots, restores on the target, switches over and
  keeps the old copy for 7 days). `?force=true` (instance owner only) detaches anyway and marks those
  sources `status=error, status_message="device removed"`.
- A device that is offline makes its sources return `503 device_offline`; everything else keeps working.
- On the device itself, while attached: the local dashboard shows a **Host device status** page
  (main Deployer URL, connection state, hosted databases, disk, last backup) instead of the setup
  wizard. Local detach is possible from the Deployer Control app / `deployer.ps1 device detach`
  (requires Windows admin on that PC).
- Device-hosted databases are included in backups (run on the device, copies per policy) and in
  exports (data streamed from the device).

## Device-local API (on the host device's own API, served at its localhost)

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/v1/device/status` | – | – | `{mode:"standalone"\|"host", primary_url, device_id, device_name, connected, last_error, last_connected_at, hosted_sources:[{database_name, kind, size_bytes}], metrics}` |
| POST | `/v1/device/enroll/start` | none if instance not initialized, else instance-owner bearer | `{primary_url, device_name}` | `{user_code, verification_url, expires_in}` |
| GET | `/v1/device/enroll/status` | same | – | `{status:"idle"\|"pending"\|"approved"\|"denied"\|"expired"\|"error", message}` |
| POST | `/v1/device/enroll/cancel` | same | – | `{ok:true}` |

`/v1/setup/status` gains `device_mode: "standalone" | "host"` so the dashboard can route to the
status page.

`enroll/start` errors: 422 `invalid_primary_url`, 409 `already_attached`, 502 `primary_unreachable` /
`enrollment_failed` / `primary_redirect` (redirects are only followed within the same origin; TLS is
verified). `http://host.docker.internal` is accepted only with `DEPLOYER_ALLOW_INSECURE_PRIMARY=1`
(tests).

Local emergency detach (inside the api container):
`python -m app.cli device status` and `python -m app.cli device detach [--force]` (without `--force`
it refuses while databases are hosted; with it, the databases and their credentials are kept).
