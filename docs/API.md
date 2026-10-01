# Deployer HTTP API (v1)

This file covers the foundation endpoints. Feature areas added later document their endpoints next to
their design:

| Area | Endpoints documented in |
|---|---|
| Host devices (enrollment, device management, placement, moving databases, device-local status) | [DEVICES.md](DEVICES.md) |
| Backups, versions, point-in-time restore, jobs, recently deleted | [BACKUPS.md](BACKUPS.md) |
| Cloudflare remote access & custom domains | [REMOTE_ACCESS.md](REMOTE_ACCESS.md) |
| Query console (`POST /projects/{id}/data-sources/{sid}/query`: SQL scripts and MongoDB shell code per data source; `api_keys: true`, service keys only) | [QUERY_CONSOLE.md](QUERY_CONSOLE.md) |
| Data API for apps: API keys on the data, query and schema routes, reveal / config download | [DATA_API.md](DATA_API.md) |
| Query editor: query log (`/projects/{id}/query-log`) and saved queries (`/projects/{id}/saved-queries`) | [QUERY_EDITOR.md](QUERY_EDITOR.md) |
| Saved-query versions: strict version control (`/projects/{id}/saved-queries/{sid}/versions`, `/restore`, `409 version_conflict`) | [QUERY_EDITOR.md](QUERY_EDITOR.md) "Phase 2 — versions" |
| Push-to-deploy: apps (`/projects/{id}/apps`), deployments, rollback, runtime logs, app hostnames, and the unauthenticated GitHub webhook `POST /hooks/github/{app_id}` (HMAC `X-Hub-Signature-256`). `database_access` (opt-in, admin+ to enable) joins an app to the databases network and injects `DEPLOYER_DB_<NAME>_*` | [DEPLOYMENTS.md](DEPLOYMENTS.md) |
| MCP server for AI agents: `POST /projects/{id}/mcp` (Streamable HTTP, JSON-RPC 2.0; project API key or session; `GET` 405). Tools for data, queries, schema and apps; anon keys get the read-only tools | [MCP.md](MCP.md) |
| Cloud hosting (phase C1): the owner's AWS / Firebase connections (`GET/POST /instance/cloud`, `GET /instance/cloud/requirements`, `POST /instance/cloud/{id}/check`, `DELETE /instance/cloud/{id}`), `GET /projects/{id}/cloud/connections` (admin+, read-only), `GET /projects/{id}/cloud/targets`; apps gain `target` + `cloud_connection_id` (admin+ to change), `cloud`, deployments `target_url`, cloud custom domains with `dns_records` and `POST .../domains/{did}/check`. Credentials are never returned | [CLOUD.md](CLOUD.md) |
| Connect a Git repository: the user's GitHub connection (`GET/DELETE /integrations/github`, `POST /integrations/github/connect`, `GET /integrations/github/repos?q=&page=`), `POST /projects/{id}/apps/detect` (suggested app settings), `use_github_connection` on `POST /apps` (automatic clone token + webhook) | [DEPLOYMENTS.md](DEPLOYMENTS.md) "Connect a Git repository" |

Base path `/v1`. JSON in/out unless noted. Authenticated endpoints need
`Authorization: Bearer <access_token>`. Timestamps are ISO-8601 UTC strings. IDs are UUID strings.

Errors always look like:

```json
{ "error": { "code": "snake_case_code", "message": "Human readable", "details": {} } }
```

Common codes: `unauthorized` (401), `forbidden` (403), `not_found` (404), `method_not_allowed` (405),
`validation_error` (422), `conflict` (409), `rate_limited` (429), `not_initialized` / `already_initialized` (409),
and `internal_error` (500, an unexpected failure; the details are in `deployer logs api` on the PC).
A malformed body or query is `422 validation_error` whose message names the first bad field
(e.g. `branch: is not a valid branch name`); `details.errors` lists every error (`loc`, `msg`, `type`),
without the submitted values.

Roles are ordered `viewer < developer < admin < owner`. "admin+" means admin or owner.

## Shared shapes

```ts
type User = {
  id: string; email: string; display_name: string | null; avatar_url: string | null;
  is_instance_owner: boolean; is_active: boolean; has_password: boolean; created_at: string;
  identities: Identity[];
};
type Identity = {
  id: string; provider: "google" | "github"; provider_email: string | null;
  provider_username: string | null; created_at: string;
};
type AuthResponse = { access_token: string; token_type: "bearer"; expires_in: number; user: User };

type Role = "owner" | "admin" | "developer" | "viewer";
type Project = {
  id: string; slug: string; name: string; description: string | null;
  owner_id: string; my_role: Role; created_at: string; updated_at: string;
  data_source_counts: { sql: number; nosql: number };
};
type Member = { user_id: string; email: string; display_name: string | null;
                avatar_url: string | null; role: Role; can_cohost: boolean; created_at: string };
type Invite = { id: string; email: string | null; role: Exclude<Role, "owner">;
                invited_by: string; expires_at: string; created_at: string };

type DataSource = {
  id: string; project_id: string; name: string;
  kind: "sql" | "nosql";
  engine: "mariadb" | "mysql" | "postgresql" | "mongodb";
  mode: "managed" | "external";
  database_name: string;
  status: "ok" | "error" | "unknown"; status_message: string | null; last_checked_at: string | null;
  display: { host: string | null; port: number | null; username: string | null; tls: boolean };
  created_at: string;
  replicas: Replica[];   // live copies on co-host devices, COHOSTING.md ([] for external sources)
};
type ApiKey = { id: string; name: string; prefix: string; role: "anon" | "service";
                created_at: string; last_used_at: string | null; revoked_at: string | null };
```

---

## Health & setup (no auth)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | – | `{status:"ok"\|"degraded", version (release tag without the `v`; `0.1.0` in builds from source), services:{mariadb:bool, mongodb:bool\|null, redis:bool}}`; 503 + `"degraded"` while MariaDB or Redis is down; `mongodb` is null when MongoDB is switched off (no AVX) |
| GET | `/setup/status` | – | `{initialized:boolean, version, public_url, reachable_elsewhere:boolean, providers:{google:boolean, github:boolean}, allow_signup:boolean, device_mode:"standalone"\|"host", managed_mongodb:boolean}` (`device_mode`: [DEVICES.md](DEVICES.md); `managed_mongodb` is false on CPUs without AVX, and the dashboard then unticks MongoDB in "New project") |
| POST | `/setup/owner` | `{email, password, display_name?}` | `AuthResponse` (+ refresh cookie). 409 `already_initialized` if any user exists |
| POST | `/setup/import` | multipart: `file`, `passphrase` | `{ok:true, summary:{users, projects, data_sources, rows, documents}}`. Only while not initialized; `scope` must be `instance`. 400 `bad_passphrase` / `invalid_export`; 413 `file_too_large` when the file or its unpacked contents pass the memory-based import limit ([ARCHITECTURE.md](ARCHITECTURE.md#export--import-format)) |

## Auth

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/auth/providers` | – | – | `{google:boolean, github:boolean, allow_signup:boolean}` |
| POST | `/auth/signup` | – | `{email, password, display_name?, invite_token?}` | `AuthResponse`. Allowed if `allow_signup` or a valid invite token (email-locked invites must match); 429 `rate_limited` (shares the per-IP login limit) |
| POST | `/auth/login` | – | `{email, password}` | `AuthResponse`; 401 `invalid_credentials`; 429 `rate_limited` |
| POST | `/auth/refresh` | cookie | – | `AuthResponse` (rotates cookie); 401 `unauthorized` |
| POST | `/auth/logout` | cookie | – | `{ok:true}` (revokes refresh token, clears cookie) |
| GET | `/auth/me` | bearer | – | `User` |
| PATCH | `/auth/me` | bearer | `{display_name?}` | `User` |
| POST | `/auth/password` | bearer | `{current_password?, new_password}` | `{ok:true}` (`current_password` required if one exists; a forgotten one is reset on the Deployer PC with `python -m app.cli user reset-password [--email]`, password as `{"password"}` JSON on stdin) |
| GET | `/auth/oauth/{provider}/start?redirect=/path&invite_token=` | – | – | **302** to provider (login/signup intent) |
| POST | `/auth/oauth/{provider}/link` | bearer | `{redirect?:"/settings/account"}` | `{authorize_url}` — dashboard navigates to it |
| GET | `/auth/oauth/{provider}/callback?code&state` | – | – | **302** to dashboard (see below) |
| DELETE | `/auth/identities/{identity_id}` | bearer | – | `User`; 409 `last_login_method` |

OAuth callback redirects:
- Success (login): sets refresh cookie, 302 → `{public_url}/auth/complete?redirect=<path>`; the
  dashboard then calls `POST /auth/refresh` to obtain an access token.
- Success (link): 302 → `{public_url}<redirect>?linked=<provider>`.
- Failure: 302 → `{public_url}/login?error=<code>` (login) or `{public_url}<redirect>?error=<code>` (link).
  Codes: `oauth_failed`, `oauth_state_invalid` (the state or the browser nonce cookie is missing, used
  or expired; usually the flow was started on a different address than `public_url`, so start again from
  `public_url`), `not_initialized`, `account_exists_link_required`, `identity_in_use`, `signup_disabled`,
  `invite_invalid`, `invite_email_mismatch`, `provider_not_configured`, `email_not_verified`.
- GitHub connect (deploys): 302 → `{public_url}/integrations/github/done?ok=1` or `?error=<code>`
  (`oauth_failed`, `github_connect_user_mismatch`, `provider_not_configured`).

Provider callback URLs (shown in the setup wizard):
`{public_url}/v1/auth/oauth/google/callback`, `{public_url}/v1/auth/oauth/github/callback`.

## Instance (instance owner only)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/instance/settings` | – | `InstanceSettings` |
| PUT | `/instance/settings` | `{public_url?, allow_signup?, owner_only_projects?, google_client_id?, google_client_secret?, github_client_id?, github_client_secret?, alert_webhook_url?, api_key_rate_limit?}` (empty string clears) | `InstanceSettings & {warnings}` (a changed `public_url` re-points the apps' GitHub webhooks; `warnings` lists the ones that could not follow) |
| GET | `/instance/users` | – | `User[]` |
| PATCH | `/instance/users/{id}` | `{is_active:boolean}` | `User`. Disabling signs the account out everywhere (refresh tokens revoked; access tokens are refused at the next request) and stops the API keys (401 `account_disabled`) and GitHub push deploys (403 `account_disabled`) of projects it owns; apps already running keep running. 400 `cannot_disable_owner` for the instance owner |
| GET | `/instance/projects` | – | `(Project & {owner_email, member_count})[]`: every project, `my_role` null where the owner isn't a member |
| GET | `/instance/audit?limit=100&before={id}&action=` | – | `{id, action, user_id, user_email, project_id, ip, user_agent, details, created_at}[]`, newest first (`limit` 1-500; `before` pages by id). Rows are kept 90 days (API key reveals/downloads and instance exports are kept); the worker also deletes refresh tokens a day after they expire |
| POST | `/instance/export` | `{passphrase}` | file download `deployer-instance-YYYYMMDD-HHMM.json`, built inside the request (through remote access prefer the job below) |
| POST | `/instance/export/jobs` | `{passphrase}` | `{job}` (`transfer.export`); see "Export / import jobs" |

OAuth values are trimmed and checked before they are stored (the same check backs
`python -m app.cli oauth set`). Any whitespace inside a value or a leading `ID`/`SECRET`/`Client ID:`
label is rejected; `google_client_id` must match `^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$`;
`github_client_id` must start with `Ov23`, `Iv1.` or `Iv23`, or be 20 letters/digits; a secret that
looks like a Client ID is rejected. Failures are `422 validation_error` with `details.field` set to the
key and a message saying what to paste, e.g. "Paste only the Google Client ID, e.g.
1234-abc.apps.googleusercontent.com - not the whole block".

```ts
type InstanceSettings = {
  public_url: string; allow_signup: boolean;
  local_url: string;                 // the dashboard on the Deployer PC itself, with its real port (http://localhost:8080)
  owner_only_projects: boolean;      // default true: only the instance owner can create/import projects
  google: { client_id: string | null; secret_set: boolean; configured: boolean; callback_url: string };
  github: { client_id: string | null; secret_set: boolean; configured: boolean; callback_url: string };
  alert_webhook_url: string | null;  // https only, no user:password@ (MONITORING.md)
  api_key_rate_limit: number;        // requests/min per project API key, default 600, 0 = unlimited
};
```

`alert_webhook_url` failures are `422 validation_error` with `details.field: "alert_webhook_url"`;
`api_key_rate_limit` must be 0-100000.

### Monitoring (instance owner only)

[MONITORING.md](MONITORING.md). Metrics and alerts live in Redis; everything here is owner-only (403
for other users, 401 `api_key_not_allowed` for API keys).

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/instance/metrics?window=1h\|6h\|24h` | – | `InstanceMetrics` (default `1h`; other windows 422) |
| GET | `/instance/metrics/summary` | – | `MetricsSummary` (for the header bell; cheap) |
| GET | `/instance/alerts` | – | `Alert[]` (open alerts, critical first; muted ones included with their flags) |
| POST | `/instance/alerts/{id}/dismiss` | – | `Alert` (hidden from the bell until it resolves); 404 if not active |
| POST | `/instance/alerts/{id}/snooze` | `{minutes}` (5-10080) | `Alert` |
| POST | `/instance/alerts/webhook-test` | `{url?}` (default: the saved URL) | `{ok, detail}` (`detail`: `HTTP 204`, `ConnectTimeout`, ...); 422 if no URL is set |

```ts
type Host = { cpu_percent: number | null; memory_used_bytes: number | null; memory_total_bytes: number | null;
  disk_free_bytes: number | null; disk_total_bytes: number | null; disk_label: string | null;  // the fuller of the Docker disk and the host drive
  uptime_seconds: number | null; collected_at: string };
type RequestTotals = { requests: number; errors_5xx: number; error_rate: number | null; p95_ms: number | null };
type InstanceMetrics = {
  window: "1h" | "6h" | "24h"; step_seconds: number;   // 60 / 180 / 720: at most 120 points
  current: Host | null;                                // null if the worker hasn't sampled for 3 minutes
  points: { t: string; cpu_percent: number | null; memory_percent: number | null; disk_free_bytes: number | null;
            requests_per_min: number; error_rate: number | null; p95_ms: number | null }[];
  requests: RequestTotals;                             // whole window
  routes: (RequestTotals & { route: string })[];       // top 15 by count, e.g. "GET /v1/projects/{project_id}"
  containers: { collected_at: string; containers: { name: string; service: string | null; app_id: string | null;
    status: string | null; health: string | null; restarts: number | null; started_at: string | null;
    cpu_percent: number | null; memory_bytes: number | null; memory_limit_bytes: number | null }[] } | null;
};
type MetricsSummary = { current: Host | null; requests_5m: RequestTotals;
  containers: { total: number; running: number; problems: number } | null;
  alerts: { active: number; visible: number; critical: number; top: Alert | null } };
type Alert = { id: string; alert: string; severity: "warning" | "critical"; message: string;
  first_seen: string; last_seen: string; opened_at: string; dismissed: boolean; snoozed_until: string | null };
```

## Projects

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects` | member | – | `Project[]` |
| POST | `/projects` | any user (only the instance owner while `owner_only_projects` is on, the default; 403 otherwise) | `{name, description?, provision?:{sql:boolean, nosql:boolean}}` | `Project` (creates managed MariaDB and/or MongoDB sources when requested) |
| GET | `/projects/{project_id}` | viewer+ | – | `Project` |
| PATCH | `/projects/{project_id}` | admin+ | `{name?, description?}` | `Project` |
| DELETE | `/projects/{project_id}?confirm=<slug>` | owner | – | `{ok:true}` (managed databases get a final snapshot, kept 30 days, then are dropped by a job; for those 30 days the instance owner can restore the project or download the snapshots — [BACKUPS.md](BACKUPS.md)) |
| POST | `/projects/export` | owner of each | `{project_ids:string[], passphrase}` | file download `deployer-projects-YYYYMMDD-HHMM.json`, built inside the request (through remote access prefer the job below) |
| POST | `/projects/export/jobs` | owner of each | `{project_ids:string[], passphrase}` | `{job}` (`transfer.export`; with one project it also shows in that project's jobs) |
| POST | `/projects/import` | as `POST /projects` | multipart: `file`, `passphrase` | `{ok:true, projects:Project[], summary}` (`scope` must be `projects`; 413 `file_too_large` as for `/setup/import`) |
| POST | `/projects/import/jobs` | as `POST /projects` | multipart: `file`, `passphrase` | `{job}` (`transfer.import`). The file is checked and decrypted first (400 `bad_passphrase` / `invalid_export`, 413 `file_too_large` as above); the job recreates the projects |

### Export / import jobs

Exports and imports started with the `/jobs` forms above run in the background (A-044), so a request
through remote access (~100 s limit) only has to start them. They are the caller's own: other users get 404.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/transfers` | – | `Job[]`: the caller's last 20 `transfer.export` / `transfer.import` jobs, newest first. A finished export's `result` is `{filename, counts}`; an import's is `{projects:[{id, name}], summary}` |
| GET | `/transfers/{job_id}/download` | – | the export file (`Content-Disposition` with `params.filename`). 409 `export_not_ready` until the job succeeded; 410 `export_expired` after 24 hours |
| POST | `/transfers/{job_id}/cancel` | – | `Job` (a running export stops before its next database) |

## Members & invites

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/members` | viewer+ | – | `Member[]` |
| PATCH | `/projects/{id}/members/{user_id}` | admin+ | `{role?, can_cohost?}` (role not `owner`; can't change the owner's role; only the owner changes the owner's `can_cohost`; `can_cohost` needs developer+, 422 otherwise, and is cleared on demotion — [COHOSTING.md](COHOSTING.md)) | `Member` + `api_keys_to_rotate: ApiKey[]` (live keys they created or revealed, when someone else demotes them below admin; else `[]`) |
| DELETE | `/projects/{id}/members/{user_id}` | admin+ or self | – | `{ok:true, api_keys_to_rotate: ApiKey[]}` (owner can't be removed; the live keys they created or revealed keep working until revoked; `[]` when you leave) |
| GET | `/projects/{id}/invites` | admin+ | – | `Invite[]` (pending only) |
| POST | `/projects/{id}/invites` | admin+ | `{email?, role, expires_in_days?:1..30 (default 7)}` | `{invite:Invite, invite_url, reachable_elsewhere:boolean}` — token only returned here |
| DELETE | `/projects/{id}/invites/{invite_id}` | admin+ | – | `{ok:true}` |
| GET | `/invites/{token}` | – | – | `{project_name, role, invited_by_name, email, expires_at}`; 404 if invalid/expired/used |
| POST | `/invites/{token}/accept` | bearer | – | `{project_id}`; 403 `invite_email_mismatch` |

`invite_url` = `{public_url}/invite/{token}`. `reachable_elsewhere` is false while `public_url` is
localhost (`localhost`, `127.0.0.1`, `::1`, `*.localhost`): the link then only opens on the Deployer PC, and the
dashboard says to turn on remote access first (the API-key snippets warn the same way).

## API keys

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/api-keys` | admin+ | – | `ApiKey[]` |
| POST | `/projects/{id}/api-keys` | admin+ | `{name, role}` | `{api_key:ApiKey, secret}` — secret `dpl_<role>_<random>` shown once |
| DELETE | `/projects/{id}/api-keys/{key_id}` | admin+ | – | `{ok:true}` (revokes) |
| GET | `/projects/{id}/api-keys/{key_id}/reveal` | admin+ | – | `{secret}`; 409 `not_revealable` (key predates stored secrets), 409 `api_key_revoked` |
| GET | `/projects/{id}/api-keys/{key_id}/config` | admin+ | – | app config JSON download `deployer-<slug>-<role>.json` (same 409s) — [DATA_API.md](DATA_API.md) |

`ApiKey` has `revealable: boolean`. Keys (`Authorization: Bearer dpl_...`) are accepted **only** by the
data browser, `POST .../query` (service keys only), the GET schema routes (marked `api_keys: true` below) and the MCP
endpoint `POST /projects/{id}/mcp` ([MCP.md](MCP.md)): `anon` acts as viewer, `service` as developer;
elsewhere they get 401 `api_key_not_allowed`. See [DATA_API.md](DATA_API.md).

## Data sources

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/data-sources` | viewer+ | – | `DataSource[]` |
| POST | `/projects/{id}/data-sources/test` | admin+ | `DataSourceInput` | `{ok:boolean, message, server_version:string\|null}` — a failed `message` (also in `connection_failed` below and the stored status) starts with a plain hint when the cause is recognisable (wrong password, unknown database, unreachable host, Atlas Network Access), then `Details:` and the redacted driver text |
| POST | `/projects/{id}/data-sources` | admin+ | `DataSourceInput` | `DataSource` (external sources are tested first; 400 `connection_failed`) |
| PATCH | `/projects/{id}/data-sources/{sid}` | admin+ | `{name?, config?}` | `DataSource` — edits in place, keeping the id (links, API key configs, saved queries). `config` (external only) is merged over the stored one, so `{config:{password}}` rotates just the password; a changed connection is tested first (400 `connection_failed`); 422 for `config` on a managed source; 409 `name_taken`. Renaming a managed source renames its `DEPLOYER_DB_<NAME>_*` variables from the apps' next deploy ([DEPLOYMENTS.md](DEPLOYMENTS.md)) |
| POST | `/projects/{id}/data-sources/{sid}/check` | viewer+ | – | `DataSource` (refreshes status) |
| GET | `/projects/{id}/data-sources/{sid}/connection` | developer+ | – | `{uri, host, port, username, password, database}` for use in apps; `external_hint` says where they work (managed: only apps with Database access on this server; device-hosted: only on that PC, use the Data API elsewhere) |
| DELETE | `/projects/{id}/data-sources/{sid}?drop=false` | admin+ (`drop=true`: owner) | – | `{ok:true, job?: Job}` — managed sources are soft-deleted ("Recently deleted", [BACKUPS.md](BACKUPS.md)) with a final snapshot job; 400 `cannot_drop_external` |

```ts
type DataSourceInput =
  | { kind: "sql"; mode: "managed"; engine: "mariadb"; name: string }
  | { kind: "nosql"; mode: "managed"; engine: "mongodb"; name: string }
  | { kind: "sql"; mode: "external"; engine: "mariadb" | "mysql" | "postgresql"; name: string;
      config: { host: string; port?: number; username: string; password: string; database: string; tls?: boolean } }
  | { kind: "nosql"; mode: "external"; engine: "mongodb"; name: string;
      config: { uri: string; database?: string } };
```

`kind` may be left out: it follows from `engine` (`mongodb` is `nosql`, the rest `sql`). Host, username
and database are trimmed. A MongoDB `database` left out defaults to the one named in the URI path
(`mongodb+srv://cluster.example.net/shop`); 422 when neither names one.

External hosts are reached from inside the Deployer container, so `localhost`, `127.x`, `::1` and
`0.0.0.0` (also in a MongoDB URI) are rejected with 422 `validation_error`. For a database on the same
PC use the PC's network IP address (`host.docker.internal` reaches Windows only with the Docker Desktop
runtime; on the default WSL engine it is the WSL VM), and let the database accept network connections (MySQL/MariaDB `bind-address`, PostgreSQL `listen_addresses` + `pg_hba.conf`).

For everyone except the instance owner (A-114), test/create/update also refuse, with 422
`validation_error`, hosts on Deployer's own network: names without a dot (Docker service and container
names such as `mariadb` or `redis`), and hosts that are or resolve to `172.16.0.0/12` (Docker's address
pool), link-local (`169.254.x`, cloud metadata), multicast or reserved addresses. Every host of a
comma-separated PostgreSQL host list and of a MongoDB seed list is checked. LAN addresses (`10.x`, `192.168.x`) and public hosts are allowed.

A project may have any number of SQL and NoSQL sources at once (typically one of each).

### Co-hosting (live copies on members' devices)

Full table, shapes and rules in [COHOSTING.md](COHOSTING.md) "API":

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/cohosting/eligibility` | viewer+ | – | `{can_cohost, devices:[{id, name, online, granted}], offer}` (caller's own devices) |
| POST | `/projects/{id}/data-sources/{sid}/replicas` | developer+ with `can_cohost` | `{device_id}` | `{replica:Replica, job:Job}` |
| GET | `/projects/{id}/data-sources/{sid}/replicas` | viewer+ | – | `Replica[]` |
| POST | `/projects/{id}/data-sources/{sid}/replicas/{rid}/pause\|resume\|recopy` | co-host owner or admin+ | – | `{replica, job?}` |
| DELETE | `/projects/{id}/data-sources/{sid}/replicas/{rid}?drop=false` | co-host owner or admin+ | – | `{ok:true}` |
| GET | `/projects/{id}/data-sources/{sid}/sync-conflicts?status=open\|resolved` | developer+ | – | `SyncConflict[]` |
| GET | `/projects/{id}/data-sources/{sid}/sync-conflicts/{cid}` | developer+ | – | `SyncConflict` |
| POST | `/projects/{id}/data-sources/{sid}/sync-conflicts/{cid}/resolve` | co-host owner or admin+ | `{choice:"primary"\|"replica"\|"manual", value?}` | `SyncConflict` |
| GET | `/projects/{id}/data-sources/{sid}/sync-history?table=&key=<JSON>` | developer+ | – | `HistoryItem[]` |
| POST | `/projects/{id}/data-sources/{sid}/sync-history/restore` | co-host owner or admin+ | `{table, key, version_id}` | `{ok:true, resolved_conflict_id}` |

`POST .../move` ([DEVICES.md](DEVICES.md)) returns 409 `has_replicas` while a source has co-host copies.

## Schema

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/schema?source_id=&sample=200` | viewer+ (`api_keys: true`) | – | `ProjectSchema` |
| GET | `/projects/{id}/schema/export?format=sql\|mongo\|bundle&source_id=` | viewer+ (`api_keys: true`) | – | file: `.sql` / `.js` / `.zip` |
| GET | `/projects/{id}/schema/links` | viewer+ (`api_keys: true`) | – | `SchemaLink[]` |
| POST | `/projects/{id}/schema/links` | developer+ | `Omit<SchemaLink,"id"\|"created_at">` | `SchemaLink` |
| DELETE | `/projects/{id}/schema/links/{link_id}` | developer+ | – | `{ok:true}` |
| POST | `/projects/{id}/data-sources/{sid}/tables` | developer+ | `TableSpec` | `Entity` |
| DELETE | `/projects/{id}/data-sources/{sid}/tables/{table}` | admin+ | – | 202 `{ok:true, job:Job}` when the source's backup policy takes a safety snapshot first (the snapshot and the drop run as job `schema.drop`; asking again while it is queued or running returns the same job), else `{ok:true}` |
| POST | `/projects/{id}/data-sources/{sid}/collections` | developer+ | `{name, validator?:object}` | `Entity` |
| DELETE | `/projects/{id}/data-sources/{sid}/collections/{name}` | admin+ | – | 202 `{ok:true, job:Job}` when the source's backup policy takes a safety snapshot first (the snapshot and the drop run as job `schema.drop`; asking again while it is queued or running returns the same job), else `{ok:true}` |

```ts
type ProjectSchema = {
  sources: SourceSchema[];
  links: SchemaLink[];
  conventions: ConventionIssue[];
  generated_at: string;
};
type SourceSchema = {
  source_id: string; name: string; kind: "sql" | "nosql"; engine: string;
  status: "ok" | "error"; error: string | null;
  entities: Entity[];
  relationships: Relationship[];
};
type Entity = {
  name: string; type: "table" | "collection";
  row_count: number | null;
  fields: Field[];
  indexes: { name: string; fields: string[]; unique: boolean }[];
  validator: object | null;            // Mongo $jsonSchema, if any
};
type Field = {
  name: string;                         // nested Mongo fields use dot paths: "address.city"
  data_type: string;                    // SQL: full column type ("bigint(20) unsigned"); Mongo: "string" | "objectId" | "int|string" ...
  nullable: boolean;
  default: string | null;
  primary_key: boolean;
  unique: boolean;
  indexed: boolean;
  foreign_key: { entity: string; field: string } | null;
  occurrence: number | null;            // Mongo only: 0..1 share of sampled docs containing the field
};
type Relationship = {
  from_entity: string; from_fields: string[];   // the "many" / referencing side
  to_entity: string; to_fields: string[];
  cardinality: "one_to_one" | "many_to_one";
  origin: "foreign_key" | "inferred";
};
type SchemaLink = {
  id: string;
  from_source_id: string; from_entity: string; from_field: string;
  to_source_id: string; to_entity: string; to_field: string;
  cardinality: "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many";
  note: string | null; created_at: string;
};
type ConventionIssue = {
  rule: string;                         // e.g. "N1" — see docs/CONVENTIONS.md
  severity: "warning" | "info";
  source_id: string | null; entity: string | null; field: string | null;
  message: string;
};
type TableSpec = {
  name: string;
  columns: { name: string; type: string; nullable?: boolean; default?: string | null;
             primary_key?: boolean; unique?: boolean; auto_increment?: boolean;
             references?: { table: string; column: string; on_delete?: "cascade" | "set null" | "restrict" } }[];
  timestamps?: boolean;                 // adds created_at / updated_at; updated_at refreshes on every UPDATE
                                        // (MySQL: ON UPDATE; Postgres: a BEFORE UPDATE trigger calling
                                        // the shared function deployer_set_updated_at(); creation fails
                                        // if another role already owns a function of that name)
};
```

## Data browser

All routes accept API keys (`api_keys: true`, [DATA_API.md](DATA_API.md)). SQL (`kind = sql`):

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/data-sources/{sid}/tables/{table}/rows?limit=50&offset=0&order_by=&order=asc` | viewer+ | – | `{columns:string[], primary_key:string[], rows:object[], total:number}` |
| POST | `.../tables/{table}/rows` | developer+ | `{values:object}` | `{row:object}` |
| PATCH | `.../tables/{table}/rows` | developer+ | `{pk:object, values:object}` | `{row:object}` |
| DELETE | `.../tables/{table}/rows` | developer+ | `{pk:object}` | `{ok:true}` |

MongoDB (`kind = nosql`):

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/data-sources/{sid}/collections/{name}/documents?filter={json}&limit=50&skip=0` | viewer+ | – | `{documents:object[], total:number}` (relaxed Extended JSON) |
| POST | `.../collections/{name}/documents` | developer+ | `{document:object}` | `{document:object}` |
| PATCH | `.../collections/{name}/documents/{doc_id}` | developer+ | `{set:object, unset?:string[]}` | `{document:object}` |
| DELETE | `.../collections/{name}/documents/{doc_id}` | developer+ | – | `{ok:true}` |

`doc_id` is the string form of `_id` (tried as ObjectId hex, then as a 64-bit integer, then as the raw string).
Binary SQL values are returned as `{"$base64": "..."}`, decimals as strings, datetimes as ISO strings.
For yes/no columns (BOOLEAN, or TINYINT(1), which is how MariaDB stores BOOLEAN) the strings
`true/false`, `yes/no`, `on/off` and `1/0` are accepted and stored as yes/no. Common database errors
(wrong type 1366, duplicate 1062, missing linked row 1452, row still referenced 1451, required column
empty 1048, and their PostgreSQL equivalents) come back as `400 query_failed` with a plain message;
the driver's own text is in `details.detail` and the MariaDB error number in `details.errno`.
