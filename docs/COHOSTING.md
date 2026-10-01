# Co-hosting: live two-way database copies and failover websites

A project owner can let a member **co-host** the project: the member's own PC keeps a live copy of
the project's databases (phase 1, built) and runs the project's apps, and visitors reach the apps
through the same address whichever PC is up (phase 2, built; not yet exercised with two real PCs). Decisions taken with the owner
(2026-09-23):

- **Co-hosting is optional.** Members who never install Deployer keep working exactly as before:
  schema, data browser and query console on the web dashboard, against the main server. Nothing in
  phase 1 needs a device for normal editing.
- **Both copies accept writes** and sync both ways, continuously.
- **Conflicts are handled like a Git merge conflict:** when the same row / document changed on both
  PCs, nothing is overwritten. Both versions are kept, someone picks one or combines them, and the
  choice is applied to both PCs.
- **One address, automatic failover** for websites (phase 2): every hosting PC runs a connector of the
  same Cloudflare tunnel (the *apps* tunnel); Cloudflare sends visitors to a healthy one.
- **Secrets stay on the master.** Co-hosts never see the master's API keys, OAuth settings or other
  secrets in any dashboard; only accounts signed in to the master (with the right role) can reveal them.

## Honest limits (shown in the dashboard where they matter)

1. **Conflicts:** if the same row / document is changed on both PCs before they synced (typically
   while they can't reach each other), that row is not synced until someone resolves the conflict
   (*Databases → Sync*). Every other row keeps syncing. Inserts don't conflict (see ids below) unless
   a unique column collides - then that row is a conflict too.
2. **The co-host owns their PC.** The database copy on it is readable by whoever controls that PC -
   that is what a copy is. What is protected is the master's *platform* secrets (API key secrets,
   OAuth apps, Cloudflare token, other projects, the database's own password on the master): they are
   never sent.
3. **Schema changes** made through Deployer (Schema tab: create/drop table or collection) are repeated
   on every copy right away (a copy that can't take it gets a warning). DDL typed into the query
   console runs only where it ran: the sync then stops with an error naming the table
   (`schema_mismatch`) until the copy matches again (apply the same change there, or re-copy).
4. The **dashboard** (`deployer.<domain>`) stays on the master; only co-hosted apps fail over (phase 2).
5. Tables **without a primary key** are not synced (a warning on the copy lists them).
6. Moving a database that has copies to another host is refused (`409 has_replicas`); remove the
   copies first. Sources placed on a host device can't be copied (`409 replica_unsupported`, v1).
7. Removing a device that holds copies is refused too (`409 device_has_copies`); remove them with
   "Also delete the copy on the device" first. Detaching a device stops its co-hosted apps and its apps
   tunnel connector.

## Roles

- `project_members.can_cohost` (bool, default false): set by project admins/owners on the Members tab
  (`PATCH /members/{user_id} {can_cohost}`). Needs the `developer` role or higher; demoting a member
  below developer clears it. Only the owner changes the owner's own flag (or another admin's).
- The co-host attaches their PC as a **host device** of the master (existing enrollment, DEVICES.md),
  owned by them, and shares it with the project (`sharing_mode = selected` + a `device_project_grants`
  row, or `my_projects` when they administer the project) - the same rule as database placement.
- A project can have **one co-host device per member**, any number of members (at most 9 co-host
  devices per main server, see ids).
- Switching `can_cohost` off, demoting the member or removing them **pauses** their copies (no more
  data is sent); an admin can delete them. So does unsharing the device from the project, removing its
  `database_host` role or disabling it: every sync round re-checks these rules and pauses the copy with
  the reason, and a queued copy job fails; Resume is refused (`409 device_not_eligible`) until the rule
  holds again. Paused copies get no schema changes either, and each copy keeps at most 50 warnings.

## Dashboard (for whoever builds it)

- Offer **"Copy to my device"** / any co-hosting prompt only when
  `GET /v1/projects/{pid}/cohosting/eligibility` returns `offer: true`, i.e. the member (a) has
  `can_cohost` and (b) owns at least one approved, active host device attached to this Deployer.
  Everyone else sees no co-hosting UI at all; editing works exactly as without co-hosting.
- `devices[].granted = false` means the device isn't shared with this project yet (link to the
  device's sharing settings); `online = false` means creating the copy will fail with 503.
- The data source response lists its copies (`replicas[]`) with `status`, `lag_seconds`,
  `last_synced_at`, `open_conflicts`, `error`, `warnings` - show a Sync badge and a conflicts count.
- Conflicts page: list with `?status=open`; each conflict carries a field diff
  (`fields[].changed_by`: `primary` | `replica` | `both`) and, when the two sides changed different
  fields, a `suggested` merged row - the user confirms it with `choice: "manual"`.

## Database sync (phase 1 - built)

Managed sources on the main server only. For a source with a co-host copy, `source_replicas` rows:
`id, data_source_id, device_id, status (copying|syncing|paused|error), position_primary,
position_replica (JSON: MariaDB {gtid} / Mongo {token}), id_offset, last_synced_at, lag_seconds,
error, warnings, created_by_id, created_at, updated_at`, unique `(data_source_id, device_id)`.

- **Initial copy** (job `replica.copy`, worker): check/raise the binlog settings, record the main
  server's position (MariaDB `@@gtid_binlog_pos`; Mongo a change-stream resume token), provision a
  database with the **same name** on the device (`datasource.provision`, its password stays on the
  device), dump → transfer → restore (`device_moves.dump_source` / `restore_into`), then record the
  device's position (`sync.position`, which also sets the device's id offset) and go `syncing`.
  Changes made on the main server during the copy are synced afterwards (no gap; re-applying a change
  the dump already contained is a no-op). A failed copy drops the partial database. `recopy` drops
  and copies again; open conflicts then end with the main server's version.
- **Engine** (`services/source_sync.py`): the worker's scheduler leader runs a round every 2 s per
  copy (up to 4 copies at a time in a small thread pool, so one slow device doesn't delay the others): read changes on each side since its position (up to 1000 changes / 4 MB, a bigger row or document alone in its own batch; ending at a transaction boundary when it can; a bigger transaction such as a bulk UPDATE or CSV import is split across rounds, its position `{gtid, txn, skip}` resuming inside it),
  apply the main server's changes to the device, then the device's to the main server, row by row,
  and advance each position only after its changes were applied. Errors → `status=error` with the
  message, retried with backoff (4 s doubling to 5 min); a device that is offline (or drops mid-round)
  leaves positions and status alone while `lag_seconds` grows; the round catches up on reconnect.
  - **MariaDB:** row-based binlog read with `python-mysql-replication` (`BinLogStreamReader`,
    `only_schemas=[db]`, resumed by GTID, non-blocking). The device reads its own binlog through RPC
    `sync.sql_changes` and applies through `sync.sql_apply`. Echo loops are impossible: the device
    applies with `SET SESSION sql_log_bin = 0`; the main server applies with `SET SESSION server_id =
    1000000 + <device offset>` and its reader for that device skips transactions with that server_id
    (so a second copy of the same source still receives them - `sql_log_bin = 0` on the main server
    would have hidden them from other copies; if a server refused the session server_id the sync falls
    back to `sql_log_bin = 0`). Values travel as JSON with tags for decimals, dates, times, binary.
  - **MongoDB:** change streams (`fullDocument: updateLookup`) with resume tokens on both sides
    (device: `sync.mongo_changes` / `sync.mongo_apply`, writes with `replace_one(upsert)` / `delete_one`).
    MongoDB has no way to write without an oplog entry, so a write the sync made is recognised when it
    comes back because its content hash equals the last version the sync recorded for that document
    (`sync_versions`), or an older version whose echo that side still owes (`sync_versions.echo`,
    consumed once) - an echo that arrives after the document already moved on must not undo the newer
    version, while a real edit back to an old value still syncs. No marker field is added to documents
    (the draft's `_dsync` field was dropped).
  - **Ids (MariaDB):** MariaDB has no per-table auto-increment step, and per-table id ranges don't work
    (applying a row with a high id moves the other copy's counter into that range). So the sync sets
    the server-wide `auto_increment_increment = 10` with `auto_increment_offset = 1` on the main server
    and `2..10` on co-host devices (one offset per device, shared by all its copies, stored in
    `source_replicas.id_offset`) - only on servers that hold copies. At copy time the worker writes
    them to `zz-deployer-cohosting.cnf` in MariaDB's conf.d (`mariadb_conf` volume, `MARIADB_CONF_DIR`)
    so MariaDB starts with them after a restart, and sets them at runtime; every round re-checks them
    and logs a warning when it had to set them again. The file stays after the last copy is removed
    (harmless). It affects every
    database on those servers: new ids skip numbers (unique, just sparser). Connections opened before
    co-hosting was enabled keep the old step until they reconnect - redeploy apps after the first copy;
    any id collision that still happens surfaces as a conflict, never an overwrite. MongoDB `ObjectId`s
    are unique by construction.
  - **Binlog prerequisites**, checked at copy time and every round on both servers: `log_bin` ON with
    `binlog_format = ROW` (else `409 binlog_required`), `binlog_row_image = FULL`,
    `binlog_row_metadata = FULL` (column names/types in the binlog; also in `deploy/docker-compose.yml`
    so it survives restarts) and `binlog_expire_logs_seconds` raised to 7 days when lower (compose
    already keeps 8 days).

### Merge model (conflicts)

Like a Git merge: a change is applied to the other copy only when that copy still holds the version
the change started from - MariaDB: the binlog before-image; MongoDB (pre-images are not enabled): the last
synced version in `sync_versions` (without one, a document changed on both sides in the same round is
a conflict). Otherwise:

- the key goes into `sync_conflicts` with `status = open`, `base_json` (last synced version when
  known: the kept version, else the change's before-image), `primary_json` ("ours", the main
  Deployer's version) and `replica_json` ("theirs", the device's version) - `null` = deleted -,
  `op_primary` / `op_replica` (insert/update/delete), `primary_changed_at` / `replica_changed_at`;
- **neither side's change is applied to that key**; each copy keeps its own value (like a working tree
  with a conflict); further changes to that key update the open conflict's side instead of syncing;
- every other key keeps syncing and the copy stays `syncing` (`open_conflicts` counts them);
- a write the target refuses (unique / foreign key violation) also becomes a conflict for that key.

**Resolving** (`POST .../sync-conflicts/{cid}/resolve {choice, value?}`): `primary`, `replica`
(either may be "deleted") or `manual` with the whole row / document (`null` deletes; key fields can't
change). First one sync round runs (under the copy's lock) so changes neither side had read yet come
in: if they touched this row, the conflict now shows them and the resolution is refused with `409
conflict_changed` (review and resolve again) - nothing made before a resolution can arrive later and
reopen it with a stale version. The chosen value is then written to **both** copies (`503` while the
device is offline, nothing changed; main server first - if it refuses, `409 write_rejected` and the
device is untouched; if the device then refuses or fails, the main server's previous value is put
back (only while main still holds the written value - an app write made meanwhile is kept), and when the copies may still differ - the device's outcome is unknown, or the undo failed - the
row is recorded as an open conflict) without echo, recorded as a version (`origin = resolution`) and the conflict is
marked resolved (`resolution, resolved_json, resolved_by_id, resolved_at`; audit
`sync.conflict_resolve`). The field diff's `suggested` value merges fields that changed on only one
side (none when a field changed differently on both, a side deleted the row, or the base is unknown).

**History ("version control")**: `sync_versions (replica_id, table_name, key_json, key_hash,
version_hash, json, origin primary|replica|resolution|restore, user_id, synced_at)` keeps every version
the sync applied or a user chose, only for keys that changed since the copy. `GET .../sync-history`
returns them plus the key's resolved conflicts, newest first; `POST .../sync-history/restore` writes a
kept version to both copies (audit `sync.history_restore`) and closes an open conflict on that key.
Versions of a key are pruned once both copies agreed on it for 7 days (hourly, none while a conflict
is open). **Storage cost:** one platform-database row per applied change holding the full row /
document JSON, kept 7 days - roughly (changes per week) × (row size + ~250 bytes); a copy doing 10,000
row changes a day with 1 KB rows keeps about 90 MB.

**Offline:** while the device is offline both sides keep their binlog/oplog (7+ days; Mongo oplog
size permitting); on reconnect the loop catches up. If a position fell out of retention the copy goes
`error` with `resync_required` ("re-copy needed") and a re-copy fixes it. A single row change over the
8 MB device message limit can't be sent either way; the copy's error then says so and a Re-copy fixes it.

## Websites on both PCs (phase 2 - built)

A project admin ticks **Co-host this app** (App → Settings; `PATCH /apps/{id} {cohost: true}`, admin
only, audit `app.cohost`). From then on every deployment that goes live (deploy, push, rollback) also
runs on each **co-host device** of the project, and the app's hostnames are served by whichever PCs
are up.

**Which devices.** A device qualifies when its owner is a member with `can_cohost` (developer+), it is
active and shared with the project (the placement rule of DEVICES.md), and - only for apps with
**database access** - it holds a live (`syncing`) copy of every managed database of the project on the
main server. Apps without database access run on any co-host device. `app_replicas` (migration
`0010_cohost_apps`: `id, app_id, device_id, status, deployment_id, image_tag, container_name, port,
error, last_seen_at, created_at, updated_at`, unique `(app_id, device_id)`) keeps one row per device:
`pending` (waiting, e.g. offline) → `building` → `live`, or `failed` (error shown), or `stopped` (the
device no longer qualifies; its copy is removed). Turning co-hosting off deletes the rows.

**How a copy is built** (`services/cohost_apps.py` on the main server, `services/device_apps.py` on the
device):

1. When a deployment goes live, `replicate()` creates/refreshes the rows and enqueues job
   `app.replicate {app_id, device_id}` for each online device whose copy is not at that deployment.
2. The job sends `apps.tunnel {token}` (the apps tunnel's connector token, see below) and then
   `apps.deploy` with the commit, repository URL/branch/root directory, the Dockerfile the main server
   generates for the preset, the container port, the hostnames, the names of the databases to inject
   and the environment (below). Progress streams into the job.
3. The device's worker clones that commit, builds (the same `build_image` code as the main server's
   deploy job, BuildKit), starts `deployer-app-<slug>-<8>` (labelled `deployer.cohost_app`), joins it to
   its databases network when databases are injected, waits for the port, writes
   `cohost-<app_id>.caddy` (a local `:81xx` listener plus `http://<host>:8081` per hostname) and
   reloads its Caddy, then removes the previous container and older images of that app. A second
   `apps.deploy` for the same deployment only rewrites the routes (used when hostnames change).
   Rollbacks rebuild the old commit when the device no longer has that image.
4. **Catch-up** (scheduler sweep, every tick on the main server): pending copies of devices that came
   back online get their job; each online device reports what it runs (`apps.status`) and copies the
   main server no longer wants (app deleted, co-hosting off, device no longer eligible) are removed
   (`apps.remove`); its tunnel token is corrected. A copy that failed to build is retried on the next
   deployment or when an admin changes a co-hosting setting or a hostname (not every tick).

**Environment on a device.** The app's own variables plus `PORT`, `DEPLOYER_URL`, `DEPLOYER_PROJECT_ID`
- minus `DEPLOYER_API_KEY`, minus any `DEPLOYER_DB_*` the app set itself, minus any variable whose
value contains a password or URI of the project's databases on the main server. The device then adds
`DEPLOYER_DB_<NAME>_*` pointing at **its own local copies** with its own credentials (only databases in
its hosted-credentials list; others are refused with `not_hosted`). An app that uses the data API
through `DEPLOYER_API_KEY` therefore has no key on a co-host PC: co-hosted apps that need their data
should use database access.

**Private repositories.** A repository token (or the creator's GitHub connection) is sent to devices
only when an admin also ticks **Let co-hosts clone this private repository**
(`cohost_share_repo_access`). Without it the device clones anonymously; for a private repository that
fails with "The app's owner hasn't allowed co-hosts to clone this private repository" (`failed`).
Trade-off: a token sent to a device is readable by whoever controls that PC (it lives only in the
worker's memory during the clone, but that PC's owner is root there). Prefer a read-only fine-grained
per-repository token for co-hosted apps.

**One address with failover: the apps tunnel.** Co-hosted app hostnames move to a second Cloudflare
tunnel, `deployer-apps-<first 8 of instance_id>`, created on first need (a hostname added to a
co-hosted app, or co-hosting switched on for an app with hostnames). Its ingress routes each co-hosted
hostname to `http://caddy:8081`; their CNAMEs point at `<apps tunnel id>.cfargotunnel.com`. The
dashboard tunnel keeps the dashboard and every app that is not co-hosted; switching co-hosting off moves
the hostnames back. The main server runs a connector for it (the tunnel sidecar's second process,
REMOTE_ACCESS.md), and so does each co-host device that runs (or is about to run) a copy: the device
receives the apps tunnel's connector token through `apps.tunnel` - the only tunnel secret a device
ever gets; the dashboard tunnel token and the Cloudflare API token never leave the main server. Every
connector's Caddy has the host blocks of the apps it runs, and Cloudflare balances visitors between
healthy connectors: when one PC is off, the others serve.

**Status.** `GET /apps/{id}` returns `cohost`, `cohost_share_repo_access` and
`replicas: [{device_id, device_name, online, status, deployment_id, error, last_seen_at}]`; the app
header says "Also running on N co-host PCs". `GET /apps/{id}/logs?device_id=` reads a copy's runtime
logs through `apps.logs` (503 while that PC is offline).

### Honest limits (phase 2)

- **One co-hosted app per installation.** Every co-hosted hostname shares the one apps tunnel, and
  Cloudflare sends each visitor to any of its connectors, so a PC running only app A would receive (and
  could read) app B's visitors. Until each app gets its own tunnel, switching co-hosting on for a second
  app (in any project) is refused with 409 `cohost_limit`; if two are co-hosted anyway (older data), no
  device gets the apps tunnel token and only the main server serves them.
- **Each copy talks to its own PC's database copy.** Writes made by the app on a co-host PC land in that
  PC's copy and reach the main server through the phase-1 sync (seconds, or once the PCs can reach each
  other again) - with the same conflict rules. Two visitors served by different PCs can briefly see
  different data.
- **Cloudflare picks the PC**, not Deployer: a visitor may be sent to any healthy connector, and a PC
  whose app is broken but whose connector is up still receives traffic (there is no HTTP health check).
  Sessions kept in an app's memory don't follow a visitor to another PC.
- **Secrets on co-host PCs:** see "Environment on a device" and "Private repositories". The co-host PC's
  owner can read the app's variables (minus the withheld ones), its code, the apps tunnel token and the
  traffic their PC serves.
- On rollback a device that no longer has the image rebuilds the old commit with the *current* preset
  settings; one build at a time per device; devices keep no older images.
- The dashboard (`deployer.<domain>`) and apps that are not co-hosted stay on the main server only.
- Not exercised with two real PCs yet (tests use fake devices, a fake Docker CLI and a fake Cloudflare).

## API (`/v1/projects/{pid}`)

| Method | Path | Role | Notes |
|---|---|---|---|
| PATCH | `/members/{user_id}` | admin+ | `{role?, can_cohost?}`; `Member` gains `can_cohost`; 422 for a member below developer; audit `member.cohost_change` |
| GET | `/cohosting/eligibility` | viewer+ | `{can_cohost, devices: [{id, name, online, granted}], offer}` - the caller's own active `database_host` devices only |
| POST | `/data-sources/{sid}/replicas` | developer+ with `can_cohost` | `{device_id}` (their own, shared with the project, online) → `{replica, job}` (`replica.copy`); 409 `replica_unsupported` / `replica_exists` / `one_device_per_member` / `device_outdated` / `too_many_cohosts`; 422 `device_not_eligible`; 503 `device_offline` |
| GET | `/data-sources/{sid}/replicas` | viewer+ | `Replica[]` (also in `DataSource.replicas`) |
| POST | `/data-sources/{sid}/replicas/{rid}/pause` / `resume` / `recopy` | co-host owner or admin+ | `{replica, job?}`; resume/recopy need the device to still pass the placement rules and its owner `can_cohost` (else 409 `device_not_eligible`); recopy 503 while offline |
| DELETE | `/data-sources/{sid}/replicas/{rid}?drop=false` | co-host owner or admin+ | stops sync; `drop=true` also drops the device copy (503 while offline) |
| GET | `/data-sources/{sid}/sync-conflicts?status=open\|resolved` | developer+ | `SyncConflict[]` (newest first, max 500) |
| GET | `/data-sources/{sid}/sync-conflicts/{cid}` | developer+ | `SyncConflict` |
| POST | `/data-sources/{sid}/sync-conflicts/{cid}/resolve` | co-host owner or admin+ (developer+) | `{choice: "primary"\|"replica"\|"manual", value?: object\|null}` → `SyncConflict`; 409 `conflict_resolved` / `conflict_changed` / `write_rejected` / `sync_busy`; 503 `device_offline` |
| GET | `/data-sources/{sid}/sync-history?table=&key=<JSON>` | developer+ | `HistoryItem[]` newest first (max 200) |
| POST | `/data-sources/{sid}/sync-history/restore` | co-host owner or admin+ (developer+) | `{table, key, version_id}` → `{ok, resolved_conflict_id}` |
| PATCH | `/apps/{id}` | admin+ for these fields | `{cohost?, cohost_share_repo_access?}` → `App` (+ `cohost`, `cohost_share_repo_access`, `replicas[]`); moves the app's hostnames between the dashboard and apps tunnels (Cloudflare errors: nothing saved); developers get 403 `forbidden`; 409 `cohost_limit` while another app of the installation is co-hosted; audit `app.cohost` |
| GET | `/apps/{id}/logs?device_id=&tail=` | viewer+ | a co-host copy's runtime logs `{lines, container, device_id}`; 404 when that PC runs no copy; 503 `device_offline` |

```ts
type Replica = {
  id: string; data_source_id: string; device_id: string; device_name: string | null; owner_id: string | null;
  online: boolean; status: "copying" | "syncing" | "paused" | "error"; lag_seconds: number | null;
  last_synced_at: string | null; error: string | null; warnings: { table: string; message: string }[];
  open_conflicts: number; created_at: string;
};
type SyncConflict = {
  id: string; replica_id: string; table: string; key: object; status: "open" | "resolved";
  base: object | null; primary: object | null; replica: object | null;          // null = deleted / unknown base
  op_primary: "insert" | "update" | "delete" | null; op_replica: "insert" | "update" | "delete" | null;
  primary_changed_at: string | null; replica_changed_at: string | null;
  resolution: "primary" | "replica" | "manual" | null; resolved: object | null;
  resolved_by_id: string | null; resolved_at: string | null; created_at: string; updated_at: string;
  fields: { name: string; base: any; primary: any; replica: any; changed_by: "both" | "primary" | "replica" }[];
  suggested: object | null;
};
type HistoryItem = {
  type: "version" | "conflict"; id: string; replica_id: string;
  origin: "primary" | "replica" | "resolution" | "restore" | "manual";   // conflicts: their resolution
  value: object | null; user_id: string | null; at: string;
};
```

SQL values in rows use JSON tags where JSON has no type: `{"$dec": "1.50"}`, `{"$dt": "2026-09-23T10:00:00"}`,
`{"$date": ...}`, `{"$time": ...}`, `{"$td": seconds}`, `{"$b64": ...}`; a `manual` value may use them
or plain strings. MongoDB documents are canonical extended JSON.

Secret-bearing responses (API key reveal/config, instance settings, Cloudflare) keep their existing
role checks on the master and are never proxied to or cached on devices.
