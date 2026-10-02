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
| **Safety snapshots** | Taken automatically before: restore in place, dropping a table/collection from the dashboard (the snapshot and the drop then run as a background job the dashboard follows; a table/collection that does not exist is a 404 before any snapshot), deleting a data source or project, moving a database to another device. | On |
| **Deleted databases** | Deleting a data source/project keeps its final snapshot + logs for 30 days (a data source: the project's "Recently deleted", restorable in one click; a whole project: the instance owner restores it under *Settings → Backups → Deleted projects* - **Restore project** recreates it with the same name and the members who still have an account (the instance owner joins as admin if not one of them), and restores each database's final snapshot into a new managed database, one restore job each in the project's Activity; a failed one stays listed to retry - or downloads each final snapshot. Databases deleted on their own before the project are download-only). Then the purge drops the database and its user too if the delete did not (retried at each prune while the host is offline). If a deleted project's final snapshot or drop fails, *Settings → Backups* lists the database under "Deleted databases not removed yet"; the prune retries it every 6 hours (reusing a snapshot that succeeded) and, 30 days after the delete, drops it without a snapshot. | 30 days |
| **Platform metadata** | The main server's `deployer` database (users, projects, settings) is snapshotted daily with the same mechanism. The instance owner can download the latest one (*Settings → Backups → Download latest*); restore it with the CLI (see [Restoring platform data](#restoring-platform-data)). | Daily, keep 30 |
| **Verification** | Weekly: restore the latest snapshot into a temporary database, compare table/collection row counts and checksums with the snapshot manifest, drop it, record `verified_at`. A failed check raises the `backup_verify_failed` alert, shows as "Restore test failed" in instance backup health, and is retried the next day. | Weekly (daily after a failure) |

MongoDB PITR needs an oplog, so the managed MongoDB runs as a **single-node replica set** (`rs0`,
keyfile auth). MariaDB runs with `log_bin`, `binlog_format=ROW`, `server_id=1`, binlog expiry 8 days.

### MongoDB versions

The managed MongoDB is `mongo:8.0` (supported upstream until 2029). Installs made before audit A-143
ran 5.0, which is end-of-life, and MongoDB only opens data whose feature-compatibility version (FCV)
is its own major or the one before. So `deployer update` (and setup over a folder kept by
`uninstall -KeepData`) upgrades the data before starting the new version: after the usual backup
offer, it stops `mongodb` cleanly, then runs `deploy/mongodb/upgrade.sh` in one-off containers of MongoDB 6.0,
7.0 and 8.0 (compose services `mongodb-upgrade-6/7/8`, no network). Each step starts `mongod`
standalone on the volume, runs `setFeatureCompatibilityVersion`, shuts down cleanly and records the
new FCV in `/data/db/deployer-fcv`; a step that is already done does nothing, so a failed or
interrupted update resumes where it stopped when run again. New or already-upgraded data only runs
the 8.0 step, which returns at once. The upgrade downloads the 6.0 and 7.0 images once (several
hundred MB each); after a successful update they can be removed with `docker image rm mongo:6.0
mongo:7.0` (in the WSL runtime: `wsl -d deployer -u root docker image rm mongo:6.0 mongo:7.0`).

Only then does it set `MONGODB_IMAGE=mongo:8.0` in `.env` (a new install gets it straight away);
without that key compose keeps `mongo:5.0`. This matters for the **first** update from a version
before A-143: that update is run by the previous `deployer` script, which has no upgrade step, so it
updates everything else and leaves MongoDB on 5.0 with its data untouched. **Run `deployer update`
once more** afterwards; that run uses the new script and moves MongoDB to 8.0 (`docker compose ps`
shows which image `mongodb` runs; its log also says when the data still needs the upgrade).

If an upgrade step fails, the update stops before starting the new containers and names the step
(its output is in the update window); the backup it offered first is in `backups\<timestamp>`.
Any update that fails after the new files are in place ends with the way back: `deployer logs api`,
`deployer update -Ref <the version that was running>`, and, if the new version already migrated the
databases, `deployer restore <that backup>` after going back.

Once the data is on 8.0 (`MONGODB_IMAGE` is in `.env`; a new install of A-143 or later has it), a version
from before A-143 cannot open it: it runs MongoDB 5.0. `deployer update -Ref <such a version>` (and
`install.ps1 -Ref`) refuses it before replacing any file, and an update that failed after moving the
data says to retry with `deployer update` instead of going back. If you must go back anyway, its
MongoDB has to start on empty data and be filled from the backup taken before the upgrade
(anything written since is lost):

1. `deployer backup` (a copy of the current data, in case you change your mind).
2. `deployer compose -- rm -s -f mongodb`, then delete the 8.0 data:
   `wsl -d deployer -u root docker volume rm deployer_mongodb_data` (Docker Desktop:
   `docker volume rm deployer_mongodb_data`).
3. Delete the `MONGODB_IMAGE=` line from `.env`.
4. `deployer update -Ref <the old version>`, then `deployer restore <the backup from before the upgrade>`
   (it replaces the MariaDB data too).
Starting 8.0 on data that was never upgraded (for example setting `MONGODB_IMAGE` by hand) fails,
and the `mongodb` log says to run `deployer update`.

## Retention (grandfather-father-son)

Default policy per data source: keep **24 hourly, 7 daily, 4 weekly, 12 monthly** snapshots.
A scheduled or manual snapshot is kept if it is the newest one in any of the most recent N buckets
(UTC hours/days/ISO weeks/months); the newest one is always kept. **Pinned** (labelled) versions and
safety snapshots from the last 30 days are never pruned automatically; safety and final snapshots do
not take a bucket. The versions list shows each one's reason (`kept_as`) from these same rules, or
"May be pruned soon" when the next hourly prune will delete it. In the policy dialog each Keep box must
be a whole number from 0 to 1000 (0 turns that tier off; a blank box blocks Save rather than saving 0),
and setting all four to 0 shows a warning that only the newest version will be kept. Log segments are
kept for the PITR window plus the age of the oldest snapshot needed to replay into that window. Turning
PITR off, or shortening the window, lets the next hourly prune delete the logs that fall outside it
for good, so the policy dialog asks for confirmation before saving such a change.

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
  deltas. Row counts are compared only between two versions (both exact); against the live database
  they are left out (`null`), since the live figure is only the engine's estimate.
- Actions: **Create version now** (optional label), **Label/pin**, **Compare**, **Restore**,
  **Download** (owner only; decrypted `.sql.gz` or mongodump archive), **Delete** (admin+, not pinned).

## Restore options

| Mode | Behaviour | Role |
|---|---|---|
| `new_source` (default in UI) | Restores into a **new data source** in the same project (`<name>-restored-<time>`), on the chosen host. Nothing existing is touched. | admin+ |
| `in_place` | Takes a safety snapshot, then replaces the live database's contents. Connections are briefly interrupted. | owner |

Target can be a version (`backup_id`) or a timestamp (`point_in_time`, must be inside the recovery
window returned by the API). Restores run as jobs with progress.

## Restoring platform data

Platform snapshots are for a damaged or wrongly changed platform database on **this** PC: they sit
in the same `backups` volume and are encrypted with a key derived from `.env`'s `MASTER_KEY`. To move
to another PC or survive a broken disk, use the whole-instance export instead (*Settings → Export &
import → Whole instance*, ARCHITECTURE.md), and
keep a downloaded platform snapshot (a plain `.sql.gz` of the `deployer` database) somewhere else.
*Settings → Backups* says this too: it shows when the last whole-instance export was made, links to
it (*Export everything*), and turns into a warning until there is one from the last 30 days.

Restore one from a terminal on the Deployer PC:

```powershell
deployer compose -- exec -T api python -m app.cli platform list        # snapshots, newest first
deployer compose -- stop worker
deployer compose -- exec -T api python -m app.cli platform restore --yes   # add --backup-id <id> for an older one
deployer restart
```

The restore snapshots the current platform data first and keeps it as a version (trigger
`pre_restore`), so it can be undone with `platform restore --yes --backup-id <that id>`. Everything the
platform recorded after the chosen snapshot is forgotten: users, projects, settings and database
versions made since. The managed databases themselves are not changed. The list of platform snapshots
is kept as it is now (so newer ones stay restorable), and jobs that were queued or running when the
snapshot was taken are marked failed instead of running again.

The whole-PC dumps `deployer backup` writes to `backups\<timestamp>` (every MariaDB database, managed
MongoDB and a copy of `.env`) go back with `deployer restore <timestamp>` (or the folder's path). It
replaces all databases, offers a backup of the current ones first, and refuses a backup taken with a
different `MASTER_KEY` unless `-Force`; run `deployer restart` afterwards. The dumps include the database
accounts, so it only goes back onto the install that made it: a backup whose database passwords differ
from `.env` is refused even with `-Force` (use the encrypted export to move to another PC).

## Jobs

Long operations (snapshot, log archive, restore, verify, copy, move, prune) are rows in `jobs`. Backup
jobs are orchestrated by the main server's **worker** (they own every platform row) and hand the
byte-level work — dump, log archiving, restore, verify — to the host of the database: locally, or on a
host device through `jobs.run` RPCs with `executor.<method>` types (DEVICES.md). Moves run in the API
process, and so do the dashboard's exports and imports (`transfer.export` / `transfer.import`, kept
in the API process so the passphrase never leaves it; ARCHITECTURE.md "Export / import format"). The
worker also runs the scheduler (one leader via a Redis lock) that enqueues scheduled snapshots, log
archiving, pruning and verification.

Job states: `queued → running → succeeded | failed | cancelled`, with `progress` (0–1) and `message`.

The hourly prune deletes finished job rows after 14 days (failed ones after 30), so log archiving
(one job per database every 1–5 minutes) does not grow the table without bound. A deleted source's
`source.finalize_delete` job is kept until the source is purged, because undelete reads it.

When a job ends without its handler finishing (the PC slept, rebooted or the worker crashed, so the
job is failed as "worker stopped"; or it was cancelled while queued), the scheduler marks its `running`
version as failed (so it can be deleted and pruned) and drops a half-made `new_source` restore target.
A dump, log or restore tool (`mariadb-dump`, `mariadb-binlog`, `mariadb`, `mongodump`, `mongorestore`)
still running after 12 hours (`BACKUP_TOOL_TIMEOUT_HOURS` on the API/worker containers) is killed and
its job fails, so a hung tool cannot keep a snapshot `running` and block every later one; independently,
the `backup_stale` alert fires when a database has had no successful snapshot for twice its schedule.
At start the worker also removes `.partial` artifacts untouched for an hour and any leftover
`rtmp_*` / `verify_*` / `rtrash_*` temporary databases.

## Data model (primary)

| Table | Key columns |
|---|---|
| `jobs` | `id, type, status, progress, message, params (JSON), result (JSON), error, project_id, data_source_id, device_id, created_by_id, created_at, started_at, finished_at` |
| `backup_policies` | `data_source_id (PK), enabled, schedule ("hourly"/"every_6h"/"daily"), keep_hourly, keep_daily, keep_weekly, keep_monthly, pitr_enabled, pitr_window_days, copy_to_device_id (nullable; "" = main server encoded as NULL + copy_to_primary bool), copy_to_primary, safety_snapshots, updated_at` |
| `backups` | `id, data_source_id (nullable for platform; no FK, backups outlive purged sources), project_id, scope ("source"/"platform"), engine, trigger, status, label, pinned, size_bytes, sha256, started_at, finished_at, consistent_point (JSON: gtid/binlog file+pos or oplog ts), schema_snapshot (JSON), row_counts (JSON), error, verified_at, verify_status, expires_at, created_by_id, job_id` |
| `backup_log_segments` | `id, data_source_id, kind ("binlog"/"oplog"), start_at, end_at, start_point (JSON), end_point (JSON), size_bytes, sha256, created_at` |
| `backup_copies` | `id, artifact_type ("backup"/"segment"), artifact_id, location ("local"/"device"/"primary"), device_id, ref, size_bytes, sha256, status ("ok"/"missing"/"pending"), verified_at, created_at` |

`data_sources` gains `deleted_at` (soft delete for "Recently deleted"). Cross-database schema links of a
soft-deleted source are kept but hidden, come back when it is restored, and are removed with the purge.

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
| GET | `/v1/instance/backups` | instance owner | – | `{sources:[{data_source_id, project_id, project_name, name, engine, device_id, last_success_at, last_failure_at, last_error, pitr_latest, last_verified_at, last_verify_status, local_bytes, copy_bytes}], platform:{last_success_at, last_error, latest_backup_id}, storage:[{location, device_id, used_bytes, free_bytes}], last_export_at, deleted_projects:[{backup_id, project_id, project_slug, restorable, name, engine, size_bytes, started_at, expires_at}], unfinished_deletes:[{data_source_id, project_id, project_slug, name, engine, error, deleted_at, last_attempt_at, drop_without_snapshot_at}]}` (`deleted_projects`: the final snapshots of deleted projects' databases not yet restored, until purged; `unfinished_deletes`: deleted projects' databases whose final snapshot or drop failed, still on their host and retried) |
| POST | `/v1/instance/backups/platform` | instance owner | – | `{job: Job}` (platform snapshot now) |
| GET | `/v1/instance/backups/platform/{backup_id}/download` | instance owner | – | file (decrypted `.sql.gz` of the platform database) |
| GET | `/v1/instance/backups/deleted/{backup_id}/download` | instance owner | – | file (decrypted `.sql.gz` or mongodump archive of a deleted project's final snapshot; 404 for any other backup) |
| POST | `/v1/instance/backups/deleted/projects/{project_id}/restore` | instance owner | – | `{project: Project, jobs: Job[]}` (recreates the project if needed, then one `backup.restore` job per `restorable` database not already being restored; 404 when nothing of it is listed, 409 `nothing_to_restore`) |

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
  // Why the next prune keeps it (the prune's own rules); null = it will be pruned.
  kept_as: "pinned" | "safety" | "hourly" | "daily" | "weekly" | "monthly" | "latest" | "running" | "recent_failure" | null;
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
| `source_unavailable` | 503 | Schema or diff against `current` while the live database can't be read |
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
