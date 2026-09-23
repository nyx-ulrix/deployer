# Co-hosting: live two-way database copies and failover websites

A project owner can let a member **co-host** the project: the member's own PC keeps a live copy of
the project's databases (phase 1, built) and runs the project's apps, and visitors reach the apps
through the same address whichever PC is up (phase 2, not built yet). Decisions taken with the owner
(2026-09-23):

- **Co-hosting is optional.** Members who never install Deployer keep working exactly as before:
  schema, data browser and query console on the web dashboard, against the main server. Nothing in
  phase 1 needs a device for normal editing.
- **Both copies accept writes** and sync both ways, continuously.
- **Conflicts are handled like a Git merge conflict:** when the same row / document changed on both
  PCs, nothing is overwritten. Both versions are kept, someone picks one or combines them, and the
  choice is applied to both PCs.
- **One address, automatic failover** for websites (phase 2): every hosting PC runs a connector of the
  same Cloudflare tunnel; Cloudflare sends visitors to a healthy one.
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
4. The **dashboard** (`deployer.<domain>`) stays on the master; only apps fail over (phase 2).
5. Tables **without a primary key** are not synced (a warning on the copy lists them).
6. Moving a database that has copies to another host is refused (`409 has_replicas`); remove the
   copies first. Sources placed on a host device can't be copied (`409 replica_unsupported`, v1).

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
  data is sent); an admin can delete them.

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
  copy: read changes on each side since its position (up to 1000 changes / 4 MB, whole transactions),
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
    (`sync_versions`); no marker field is added to documents (the draft's `_dsync` field was dropped).
  - **Ids (MariaDB):** MariaDB has no per-table auto-increment step, and per-table id ranges don't work
    (applying a row with a high id moves the other copy's counter into that range). So the sync sets
    the server-wide `auto_increment_increment = 10` with `auto_increment_offset = 1` on the main server
    and `2..10` on co-host devices (one offset per device, shared by all its copies, stored in
    `source_replicas.id_offset`) - only on servers that hold copies, at copy time and re-asserted at
    every round (a MariaDB restart resets runtime settings; no compose change needed). It affects every
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
the change started from - MariaDB: the binlog before-image; MongoDB (5.0 has no pre-images): the last
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
change). The chosen value is written to **both** copies (device first; `503` while it is offline,
nothing changed) without echo, recorded as a version (`origin = resolution`) and the conflict is
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
`error` with `resync_required` ("re-copy needed") and a re-copy fixes it.

## Websites on both PCs (phase 2 - not built)

- Devices gain the **app-hosting role**: an app with `cohost: true` is also deployed on each co-host
  device of its project (device RPC `apps.deploy` running the same build steps with the device's own
  worker, image built from the same commit).
- A second tunnel, `deployer-apps-<instance>`, carries **only app hostnames**; the master and every
  co-host device run a connector for it (the device receives its connector token over the control
  channel - the only tunnel secret it gets; the dashboard tunnel and API token never leave the master).
  Each connector's Caddy routes app hostnames to its local container. Cloudflare balances between
  healthy connectors, so when one PC is off the other serves.
- On a device, app env vars that reference master secrets (`DEPLOYER_API_KEY`) are **not** injected;
  apps there reach their database directly (database access, DEPLOYMENTS.md) against the local copy.

## API (`/v1/projects/{pid}`)

| Method | Path | Role | Notes |
|---|---|---|---|
| PATCH | `/members/{user_id}` | admin+ | `{role?, can_cohost?}`; `Member` gains `can_cohost`; 422 for a member below developer; audit `member.cohost_change` |
| GET | `/cohosting/eligibility` | viewer+ | `{can_cohost, devices: [{id, name, online, granted}], offer}` - the caller's own active `database_host` devices only |
| POST | `/data-sources/{sid}/replicas` | developer+ with `can_cohost` | `{device_id}` (their own, shared with the project, online) → `{replica, job}` (`replica.copy`); 409 `replica_unsupported` / `replica_exists` / `one_device_per_member` / `device_outdated` / `too_many_cohosts`; 422 `device_not_eligible`; 503 `device_offline` |
| GET | `/data-sources/{sid}/replicas` | viewer+ | `Replica[]` (also in `DataSource.replicas`) |
| POST | `/data-sources/{sid}/replicas/{rid}/pause` / `resume` / `recopy` | co-host owner or admin+ | `{replica, job?}`; resume/recopy need the device owner to still have `can_cohost`; recopy 503 while offline |
| DELETE | `/data-sources/{sid}/replicas/{rid}?drop=false` | co-host owner or admin+ | stops sync; `drop=true` also drops the device copy (503 while offline) |
| GET | `/data-sources/{sid}/sync-conflicts?status=open\|resolved` | developer+ | `SyncConflict[]` (newest first, max 500) |
| GET | `/data-sources/{sid}/sync-conflicts/{cid}` | developer+ | `SyncConflict` |
| POST | `/data-sources/{sid}/sync-conflicts/{cid}/resolve` | co-host owner or admin+ (developer+) | `{choice: "primary"\|"replica"\|"manual", value?: object\|null}` → `SyncConflict`; 409 `conflict_resolved` / `write_rejected` / `sync_busy`; 503 `device_offline` |
| GET | `/data-sources/{sid}/sync-history?table=&key=<JSON>` | developer+ | `HistoryItem[]` newest first (max 200) |
| POST | `/data-sources/{sid}/sync-history/restore` | co-host owner or admin+ (developer+) | `{table, key, version_id}` → `{ok, resolved_conflict_id}` |

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
