# Backups, Versions & Recovery

Every **managed** database (MariaDB or MongoDB, on the main server or a host device) is backed up
automatically and can be restored to a saved **version** (snapshot) or to **any point in time**
inside the recovery window. External databases (Atlas, remote MySQL/Postgres) are the provider's
responsibility; the dashboard says so.

## What gets protected

| Protection | How | Default |
|---|---|---|
| **Snapshots (versions)** | MariaDB: `mariadb-dump --single-transaction --routines --triggers --events` of the one database, recording the binlog GTID/position. MongoDB: `mongodump --db <db> --archive --gzip`, recording the oplog timestamp before and after. | Hourly |
| **Point-in-time recovery (PITR)** | MariaDB binary log (ROW format) archived every 5 min via `mariadb-binlog --read-from-remote-server --raw`; MongoDB oplog entries for `<db>.*` tailed every minute into segments. Restore = nearest snapshot before T + replay logs up to T. | On, 7-day window |
| **Safety snapshots** | Taken automatically before: restore in place, dropping a table/collection from the dashboard, deleting a data source or project, moving a database to another device. | On |
| **Deleted databases** | Deleting a data source/project keeps its final snapshot + logs for 30 days ("Recently deleted"). | 30 days |
| **Platform metadata** | The main server's `deployer` database (users, projects, settings) is snapshotted daily with the same mechanism. | Daily, keep 30 |
| **Verification** | Weekly: restore the latest snapshot into a temporary database, compare table/collection row counts and checksums with the snapshot manifest, drop it, record `verified_at`. | Weekly |

MongoDB PITR needs an oplog, so the managed MongoDB runs as a **single-node replica set** (`rs0`,
keyfile auth). MariaDB runs with `log_bin`, `binlog_format=ROW`, `server_id=1`, binlog expiry 8 days.

## Retention (grandfather-father-son)

Default policy per data source: keep **24 hourly, 7 daily, 4 weekly, 12 monthly** snapshots.
A snapshot is kept if it is the newest one in any bucket it qualifies for. **Pinned** (labelled)
versions and safety snapshots from the last 30 days are never pruned automatically. Log segments are
kept for the PITR window plus the age of the oldest snapshot needed to replay into that window.

## Storage & encryption

- Every artifact (snapshot, log segment) is gzip-compressed and encrypted with **chunked
  AES-256-GCM** (1 MiB chunks, per-file random key prefix, STREAM-style nonces) using a backup key
  derived from `MASTER_KEY` via HKDF (`info="deployer-backups-v1"`). Each artifact has a SHA-256 of
  the ciphertext recorded in the platform DB.
- **Locations:**
  - `local` — the `backups` Docker volume on the device that hosts the database (always).
  - `device` — an encrypted copy on another host device with the `backup_storage` role or the main
    server (optional per policy: `copy_to_device_id`, "Main server" allowed). Copies travel through the
    device transfer endpoints (see DEVICES.md). The storing device cannot decrypt them.
- Layout: `/backups/<data_source_id>/snapshots/<backup_id>.bin`,
  `/backups/<data_source_id>/logs/<segment_id>.bin`, `/backups/platform/...`.
- The instance export (see ARCHITECTURE.md) includes the backup key material so a restored instance
  can read backups copied to other devices.

## Version history ("Versions" tab per database)

- Timeline of snapshots: time, trigger (scheduled / manual / before restore / before drop / before
  move / before delete), size, status, verified badge, label, pinned flag.
- Each snapshot stores a **schema snapshot** (the `SourceSchema` from `GET /schema` for that source)
  so any two versions — or a version vs the live database — can be **diffed**: entities added/removed,
  fields added/removed/type changed/nullability changed, indexes and validators changed, row count
  deltas.
- Actions: **Create version now** (optional label), **Label/pin**, **Compare**, **Restore**,
  **Download** (owner only; decrypted `.sql.gz` or mongodump archive), **Delete** (admin+, not pinned).

## Restore options

| Mode | Behaviour | Role |
|---|---|---|
| `new_source` (default in UI) | Restores into a **new data source** in the same project (`<name>-restored-<time>`), on the chosen host. Nothing existing is touched. | admin+ |
| `in_place` | Takes a safety snapshot, then replaces the live database's contents. Connections are briefly interrupted. | owner |

Target can be a version (`backup_id`) or a timestamp (`point_in_time`, must be inside the recovery
window returned by the API). Restores run as jobs with progress.

## Jobs

Long operations (snapshot, log archive, restore, verify, copy, move, prune) are rows in `jobs`. Backup
jobs are orchestrated by the main server's **worker** (they own every platform row) and hand the
byte-level work — dump, log archiving, restore, verify — to the host of the database: locally, or on a
host device through `jobs.run` RPCs with `executor.<method>` types (DEVICES.md). Moves run in the API
process. The worker also runs the scheduler (one leader via a Redis lock) that enqueues scheduled
snapshots, log archiving, pruning and verification.

Job states: `queued → running → succeeded | failed | cancelled`, with `progress` (0–1) and `message`.

## Data model (primary)

| Table | Key columns |
|---|---|
| `jobs` | `id, type, status, progress, message, params (JSON), result (JSON), error, project_id, data_source_id, device_id, created_by_id, created_at, started_at, finished_at` |
| `backup_policies` | `data_source_id (PK), enabled, schedule ("hourly"/"every_6h"/"daily"), keep_hourly, keep_daily, keep_weekly, keep_monthly, pitr_enabled, pitr_window_days, copy_to_device_id (nullable; "" = main server encoded as NULL + copy_to_primary bool), copy_to_primary, safety_snapshots, updated_at` |
| `backups` | `id, data_source_id (nullable for platform; no FK, backups outlive purged sources), project_id, scope ("source"/"platform"), engine, trigger, status, label, pinned, size_bytes, sha256, started_at, finished_at, consistent_point (JSON: gtid/binlog file+pos or oplog ts), schema_snapshot (JSON), row_counts (JSON), error, verified_at, verify_status, expires_at, created_by_id, job_id` |
| `backup_log_segments` | `id, data_source_id, kind ("binlog"/"oplog"), start_at, end_at, start_point (JSON), end_point (JSON), size_bytes, sha256, created_at` |
| `backup_copies` | `id, artifact_type ("backup"/"segment"), artifact_id, location ("local"/"device"/"primary"), device_id, ref, size_bytes, sha256, status ("ok"/"missing"/"pending"), verified_at, created_at` |

`data_sources` gains `deleted_at` (soft delete for "Recently deleted").

## API

All under `/v1/projects/{project_id}/data-sources/{sid}` unless noted.

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/backup-policy` | viewer+ | – | `BackupPolicy` |
| PUT | `/backup-policy` | admin+ | partial `BackupPolicy` | `BackupPolicy` |
| GET | `/backups?limit=100` | viewer+ | – | `Backup[]` (newest first) |
| POST | `/backups` | developer+ | `{label?}` | `{job: Job, backup_id}` |
| PATCH | `/backups/{backup_id}` | developer+ | `{label?, pinned?}` | `Backup` |
| DELETE | `/backups/{backup_id}` | admin+ | – | `{ok:true}` (409 `backup_pinned`) |
| GET | `/backups/{backup_id}/schema` | viewer+ | – | `SourceSchema` |
| GET | `/backups/diff?from=<backup_id>&to=<backup_id\|current>` | viewer+ | – | `SchemaDiff` |
| GET | `/backups/{backup_id}/download` | owner | – | file |
| GET | `/recovery-window` | viewer+ | – | `{pitr_enabled, earliest:string\|null, latest:string\|null, snapshots:number}` |
| POST | `/restore` | admin+ (`in_place`: owner) | `{backup_id?, point_in_time?, mode:"new_source"\|"in_place", new_name?, device_id?}` | `{job: Job}` (`device_id`: host of the new source, default = the source's host; same placement rules as creating a source, 422 `device_not_eligible`) |
| GET | `/v1/projects/{project_id}/jobs?limit=50` | viewer+ | – | `Job[]` |
| GET | `/v1/projects/{project_id}/jobs/{job_id}` | viewer+ | – | `Job` |
| POST | `/v1/projects/{project_id}/jobs/{job_id}/cancel` | admin+ | – | `Job` |
| GET | `/v1/projects/{project_id}/deleted-sources` | admin+ | – | `(DataSource & {deleted_at, purge_at})[]` |
| POST | `/v1/projects/{project_id}/deleted-sources/{sid}/restore` | admin+ | `{name?}` | `{job: Job}` |
| GET | `/v1/instance/backups` | instance owner | – | `{sources:[{data_source_id, project_id, project_name, name, engine, device_id, last_success_at, last_failure_at, last_error, pitr_latest, local_bytes, copy_bytes}], platform:{last_success_at, last_error}, storage:[{location, device_id, used_bytes, free_bytes}]}` |
| POST | `/v1/instance/backups/platform` | instance owner | – | `{job: Job}` (platform snapshot now) |

```ts
type BackupPolicy = {
  enabled: boolean; schedule: "hourly" | "every_6h" | "daily";
  keep_hourly: number; keep_daily: number; keep_weekly: number; keep_monthly: number;
  pitr_enabled: boolean; pitr_window_days: number;           // 1..35
  copy_to_primary: boolean; copy_to_device_id: string | null; // at most one copy target; the device needs the
                                                             // backup_storage role and the DEVICES.md sharing rules
  safety_snapshots: boolean; updated_at: string;
};
type Backup = {
  id: string; data_source_id: string | null; scope: "source" | "platform";
  trigger: "scheduled" | "manual" | "pre_restore" | "pre_drop" | "pre_delete" | "pre_move" | "final";
  status: "running" | "succeeded" | "failed"; label: string | null; pinned: boolean;
  size_bytes: number | null; started_at: string; finished_at: string | null;
  verified_at: string | null; verify_status: "ok" | "failed" | null;
  copies: { location: "local" | "device" | "primary"; device_id: string | null; status: string }[];
  row_counts: Record<string, number> | null; expires_at: string | null; job_id: string | null;
  error: string | null;
};
type Job = {
  id: string; type: string; status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number; message: string | null; result: object | null; error: string | null;
  project_id: string | null; data_source_id: string | null; device_id: string | null;
  created_at: string; started_at: string | null; finished_at: string | null;
};
type SchemaDiff = {
  from: { backup_id: string | null; at: string }; to: { backup_id: string | null; at: string };
  entities: {
    name: string; change: "added" | "removed" | "changed";
    fields: { name: string; change: "added" | "removed" | "changed"; before: Field | null; after: Field | null }[];
    indexes: { name: string; change: "added" | "removed" | "changed" }[];
    validator_changed: boolean; row_count: { before: number | null; after: number | null };
  }[];
};
```

Errors (besides the common codes in API.md):

| Code | HTTP | When |
|---|---|---|
| `backups_not_available` | 400 | Backup routes on an external source (only managed MariaDB/MongoDB are backed up) |
| `source_deleted` | 409 | Snapshot or restore of a source in "Recently deleted" (restore it first) |
| `backup_pinned`, `backup_running` | 409 | Deleting a pinned / still running version |
| `backup_not_ready` | 409 | Restore, schema or diff of a backup that did not succeed |
| `schema_unavailable` | 409 | No schema was recorded for that version |
| `outside_recovery_window` | 422 | `point_in_time` is not covered by a snapshot + logs (`details.earliest/latest`) |
| `restore_in_progress`, `delete_in_progress`, `snapshot_in_progress` | 409 | The same operation is already running |
| `name_taken` | 409 | `new_name` / undelete name already used in the project |
| `not_deleted`, `no_backup` | 409 | Undelete of a live source / of a dropped source without any snapshot left |
| `artifact_missing`, `artifact_unavailable` | 409 | No stored copy of the backup / the copy can't be read right now (device offline) |
| `cross_host_restore_unavailable` | 409 | The backup lives on another host and host-device transfers are not available |
| `device_not_eligible` | 422 | `restore.device_id` may not host databases for this project (DEVICES.md rules) |
| `safety_snapshot_failed` | 500 | The safety snapshot before a drop/restore failed; nothing was changed |

Deleting a data source (`DELETE .../data-sources/{sid}`, API.md) soft-deletes managed sources and returns
`{ok:true, job: Job}` for the `source.finalize_delete` job (final snapshot, then the drop when
`drop=true`); external sources are removed immediately with `{ok:true}`.
