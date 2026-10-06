"""Firestore managed exports, scheduled backups and restores (docs/CLOUD.md "Firestore backups").

Firestore Admin REST v1 through `GcpClient.firestore` (the seam tests fake) and, for the export bucket, the Cloud
Storage JSON API (`GcpClient.bucket` / `create_bucket`), with the Firebase connection's service account:

- managed export: `POST databases/<id>:exportDocuments {outputUriPrefix}` to
  `gs://<bucket>/deployer-exports/<database>/<UTC time>` - a bucket the user names, or `deployer-<project>-firestore`
  made on request (private, in the database's location). Imports only ever go into a NEW database
  (`cloud_db.create_firestore` with `import_from`, then `:importDocuments`), never over existing data;
- backup schedules: `databases/<id>/backupSchedules` (daily, or weekly on one day, with a retention);
- backups: `locations/-/backups` filtered to this database; a restore makes a new database
  (`cloud_db.create_firestore` with `restore_from`, `databases:restore`).

Exports, imports, schedules and restores cost money, so their routes need `confirm_billing: true`.

Point-in-time recovery ("Firestore point-in-time recovery and deletes"): `PATCH databases/<id>`
(`pointInTimeRecoveryEnablement`, billed) and copies of the database as it was at a minute in its version window
into a NEW database (`databases:clone`, through `cloud_db.create_firestore` with `clone_from`). Deleting - the
database (`DELETE databases/<id>`, refused while Google's delete protection is on), one backup
(`DELETE locations/<l>/backups/<id>`) or one Deployer-made export's files in a `deployer-*` bucket - only ever
happens on an admin's explicit, name-confirmed request (the routes check `confirm_name` + `confirm_delete`).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from app.errors import ApiError, CloudError
from app.models import DataSource
from app.services import cloud_gcp, firestore

EXPORT_ROLE = "Cloud Datastore Import Export Admin"
OWNER_ROLE = "Cloud Datastore Owner"
DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
MAX_RETENTION_DAYS = {"daily": 7, "weekly": 14 * 7}  # Google's limits
EXPORT_COST = (
    "A managed export reads every document it copies: Google bills one read per document (about US$0.06 per "
    "100,000) plus Cloud Storage for the files (about US$0.02 per GB a month) until you delete them (Stored exports "
    "below, or the Google Cloud console for a bucket you made)."
)
IMPORT_COST = (
    "Importing makes a new Firestore database and writes every exported document into it: Google bills one write "
    "per document (about US$0.18 per 100,000) and the new database's storage and use until you delete it (its Backups "
    "tab, or the Firebase console)."
)
SCHEDULE_COST = (
    "Google takes the backups on its own (also while this PC is off) and keeps each one until its retention ends, "
    "billing its storage (about US$0.03 per GB a month; prices vary by location). Backups do not slow the "
    "database down. Removing the schedule keeps the backups already taken until they expire."
)
RESTORE_COST = (
    "Restoring makes a new Firestore database from the backup (the original is not touched): Google bills the "
    "restore (about US$0.20 per GB) and the new database's storage and use until you delete it (its Backups tab, "
    "or the Firebase console)."
)
EXPORT_NOTE = (
    "An export copies the documents (all collections, or the ones you name) into files in a Cloud Storage bucket, in "
    "Google's own format. Use it to keep a copy outside the database, to move data to another project, or to load it "
    "into a new database here (Import into a new database). Big databases take a while; the list shows progress."
)
RESTORE_NOTE = (
    "A restore always makes a new database next to this one (Google cannot restore over an existing database). It "
    "is added here as a new database; point your app at it when you are happy with it."
)
PITR_COST = (
    "Point-in-time recovery keeps every version of your documents for 7 days (without it Google keeps only the "
    "last hour), so you can copy the database as it was at any minute of that week into a new database. While it is "
    "on, Google bills the storage those versions take, at the database's storage price (about US$0.18 per GB a "
    "month in nam5; prices vary by location). Turning it off drops the older versions."
)
CLONE_COST = (
    "Restoring to a point in time makes a new Firestore database from the versions Google kept (the original is not "
    "touched): Google bills it like a restore (about US$0.20 per GB) and the new database's storage and use until "
    "you delete it."
)
PITR_NOTE = (
    "Google always keeps the last hour of changes; with point-in-time recovery on, the last 7 days. Restore to a "
    "time copies the database as it was at that minute into a new database next to this one."
)
_SCHEDULE_ID = re.compile(r"^[\w-]{1,100}$")
_GS_URI = re.compile(r"^gs://[a-z0-9][a-z0-9_.-]{1,61}[a-z0-9](/[^\s]{0,1000})?$")


def _db_path(ds: DataSource, tail: str = "") -> str:
    return f"databases/{quote(firestore.database_of(ds), safe='()')}{tail}"


def _call(gcp, role: str, method: str, path: str, body: Any = None, params: Any = None, destroy: bool = False) -> Any:
    """`destroy`: a database or backup delete, through the seam's own `delete_firestore` (`firestore()` refuses it)."""
    try:
        return gcp.delete_firestore(path, params) if destroy else gcp.firestore(method, path, body, params)
    except CloudError as exc:
        if exc.code == "PERMISSION_DENIED" or exc.status == 403:
            raise ApiError(
                502,
                "cloud_error",
                f"{exc.message} - the Firebase service account needs the {role} role and the Cloud Firestore API "
                "turned on (Settings -> Cloud accounts shows how).",
            ) from None
        if exc.code == "NOT_FOUND" or exc.status == 404:
            raise ApiError(404, "not_found", exc.message) from None
        if exc.code == "ALREADY_EXISTS" or exc.status == 409:
            raise ApiError(409, "conflict", exc.message) from None
        if exc.status == 400:
            raise ApiError(400, "invalid_request", exc.message) from None
        raise ApiError(502, "cloud_error", exc.message) from None


def collection_ids(values: list[str] | None) -> list[str]:
    """Collection ids (`users`: every collection with that name, at any depth); none = all of them."""
    out = []
    for v in values or []:
        if not isinstance(v, str) or not v.strip() or "/" in v or len(v) > 1500:
            raise ApiError(
                422,
                "validation_error",
                "Collections are collection ids such as users (every collection with that name, at any depth)",
                {"field": "collections"},
            )
        out.append(v.strip())
    return list(dict.fromkeys(out))


def _days(duration: Any) -> int | None:
    m = re.fullmatch(r"(\d+)s", str(duration or ""))
    return int(m[1]) // 86400 if m else None


# --- managed export / import -------------------------------------------------------------------------


def default_bucket(ds: DataSource) -> str:
    """Bucket names are global; the Google project id is unique, so this one is the project's."""
    return f"deployer-{(ds.cloud_state or {}).get('project_id')}-firestore"


def bucket_location(location: str | None) -> str:
    """The Cloud Storage location matching a Firestore location (multi-regions nam5 / eur3 -> US / EU)."""
    return {"nam5": "US", "eur3": "EU"}.get(location or "", location or "US")


def operation_out(op: dict) -> dict:
    meta = op.get("metadata") or {}
    kind = str(meta.get("@type") or "")
    err = op.get("error") or None
    progress = meta.get("progressDocuments") or {}
    return {
        "id": str(op.get("name") or "").rsplit("/", 1)[-1],
        "kind": "export" if "Export" in kind else "import" if "Import" in kind else "other",
        "done": bool(op.get("done")),
        "state": meta.get("operationState") or ("FAILED" if err else "SUCCESSFUL" if op.get("done") else "PROCESSING"),
        "uri": meta.get("outputUriPrefix")
        or meta.get("inputUriPrefix")
        or (op.get("response") or {}).get("outputUriPrefix"),
        "collections": meta.get("collectionIds") or [],
        "documents": int(progress.get("completedWork") or 0) or None,
        "started_at": meta.get("startTime"),
        "ended_at": meta.get("endTime"),
        "error": (err.get("message") or "failed") if isinstance(err, dict) else None,
    }


def list_operations(gcp, ds: DataSource) -> list[dict]:
    """This database's recent exports and imports (Google keeps them a few days), newest first."""
    out = _call(gcp, EXPORT_ROLE, "GET", _db_path(ds, "/operations")) or {}
    ops = [operation_out(o) for o in out.get("operations") or []]
    return sorted((o for o in ops if o["kind"] != "other"), key=lambda o: o["started_at"] or "", reverse=True)


def export(ds: DataSource, *, bucket: str | None, create_bucket: bool, collections: list[str] | None) -> dict:
    """Starts a managed export; returns `{operation, bucket, output_uri}` (it runs on in Google)."""
    ids = collection_ids(collections)
    gcp = firestore.gcp_for(ds)
    if create_bucket:
        bucket = default_bucket(ds)
        try:
            gcp.create_bucket(bucket, bucket_location((ds.cloud_state or {}).get("location")))
        except CloudError as exc:
            raise ApiError(
                502,
                "cloud_error",
                f"{exc.message} - creating the bucket needs the Storage Admin role on the project and the Cloud "
                "Storage API turned on (Settings -> Cloud accounts); or name a bucket you made.",
            ) from None
    else:
        bucket = (bucket or "").strip().removeprefix("gs://").strip("/")
        if not cloud_gcp.BUCKET_RE.match(bucket):
            raise ApiError(
                422, "validation_error", "Name a Cloud Storage bucket, or let Deployer make one", {"field": "bucket"}
            )
        try:
            gcp.bucket(bucket)
        except CloudError as exc:
            raise ApiError(
                400,
                "bucket_unavailable",
                f"Bucket {bucket}: {exc.message} - create it in the Google Cloud console (Cloud Storage, in the "
                "database's location) and give the Firebase service account the Storage Admin role on it, or let "
                "Deployer make one.",
            ) from None
    stamp = f"{datetime.now(UTC):%Y%m%d-%H%M%S}"
    prefix = f"gs://{bucket}/deployer-exports/{firestore.database_of(ds).strip('()')}/{stamp}"
    body: dict[str, Any] = {"outputUriPrefix": prefix}
    if ids:
        body["collectionIds"] = ids
    op = _call(gcp, EXPORT_ROLE, "POST", _db_path(ds, ":exportDocuments"), body) or {}
    return {"operation": operation_out(op), "bucket": bucket, "output_uri": prefix}


def check_input_uri(uri: str) -> str:
    uri = (uri or "").strip().rstrip("/")
    if not _GS_URI.match(uri):
        raise ApiError(
            422,
            "validation_error",
            "Give the export's folder, gs://<bucket>/<path> (the export list shows it)",
            {"field": "input_uri"},
        )
    return uri


# --- scheduled backups -------------------------------------------------------------------------------


def schedule_out(s: dict) -> dict:
    weekly = s.get("weeklyRecurrence")
    return {
        "id": str(s.get("name") or "").rsplit("/", 1)[-1],
        "recurrence": "weekly" if weekly is not None else "daily",
        "day": (weekly or {}).get("day"),
        "retention_days": _days(s.get("retention")),
        "created_at": s.get("createTime"),
    }


def list_schedules(gcp, ds: DataSource) -> list[dict]:
    out = _call(gcp, OWNER_ROLE, "GET", _db_path(ds, "/backupSchedules")) or {}
    return [schedule_out(s) for s in out.get("backupSchedules") or []]


def create_schedule(ds: DataSource, recurrence: str, day: str | None, retention_days: int) -> dict:
    """Google allows one daily and one weekly schedule per database."""
    if recurrence not in MAX_RETENTION_DAYS:
        raise ApiError(422, "validation_error", "recurrence is daily or weekly", {"field": "recurrence"})
    if recurrence == "weekly" and day not in DAYS:
        raise ApiError(422, "validation_error", f"Pick the day: {', '.join(DAYS)}", {"field": "day"})
    longest = MAX_RETENTION_DAYS[recurrence]
    if not 1 <= int(retention_days) <= longest:
        raise ApiError(
            422,
            "validation_error",
            f"{recurrence.capitalize()} backups can be kept 1 to {longest} days",
            {"field": "retention_days"},
        )
    gcp = firestore.gcp_for(ds)
    if any(s["recurrence"] == recurrence for s in list_schedules(gcp, ds)):
        raise ApiError(
            409,
            "schedule_exists",
            f"This database already has a {recurrence} backup schedule: remove it first to change it",
        )
    body: dict[str, Any] = {"retention": f"{int(retention_days) * 86400}s"}
    body.update({"weeklyRecurrence": {"day": day}} if recurrence == "weekly" else {"dailyRecurrence": {}})
    return schedule_out(_call(gcp, OWNER_ROLE, "POST", _db_path(ds, "/backupSchedules"), body) or {})


def delete_schedule(ds: DataSource, schedule_id: str) -> None:
    """Stops future backups; the ones already taken stay until they expire."""
    if not _SCHEDULE_ID.match(schedule_id or ""):
        raise ApiError(404, "schedule_not_found", "No such backup schedule")
    try:
        _call(firestore.gcp_for(ds), OWNER_ROLE, "DELETE", _db_path(ds, f"/backupSchedules/{schedule_id}"))
    except ApiError as exc:
        if exc.code == "not_found":
            raise ApiError(404, "schedule_not_found", "No such backup schedule") from None
        raise


# --- backups, restore -----------------------------------------------------------------------------------


def backup_out(b: dict) -> dict:
    name = str(b.get("name") or "")
    m = re.fullmatch(r"projects/[^/]+/locations/([^/]+)/backups/([^/]+)", name)
    stats = b.get("stats") or {}
    return {
        "name": name,
        "id": m[2] if m else name.rsplit("/", 1)[-1],
        "location": m[1] if m else None,
        "state": b.get("state"),
        "snapshot_time": b.get("snapshotTime"),
        "expire_time": b.get("expireTime"),
        "size_bytes": int(stats["sizeBytes"]) if stats.get("sizeBytes") else None,
        "documents": int(stats["documentCount"]) if stats.get("documentCount") else None,
    }


def list_backups(gcp, ds: DataSource) -> list[dict]:
    """This database's backups (every location), newest first."""
    out = _call(gcp, OWNER_ROLE, "GET", "locations/-/backups") or {}
    full = f"projects/{(ds.cloud_state or {}).get('project_id')}/databases/{firestore.database_of(ds)}"
    found = [backup_out(b) for b in out.get("backups") or [] if b.get("database") == full]
    return sorted(found, key=lambda b: b["snapshot_time"] or "", reverse=True)


def restore_location(ds: DataSource, backup: str) -> str:
    """The location of one of this project's backups (the restored database goes there), else 422."""
    project = re.escape(str((ds.cloud_state or {}).get("project_id")))
    m = re.fullmatch(rf"projects/{project}/locations/([a-z0-9-]{{2,30}})/backups/[\w-]{{1,100}}", backup or "")
    if not m:
        raise ApiError(422, "validation_error", "Pick a backup of this database (from the list)", {"field": "backup"})
    return m[1]


# --- point-in-time recovery ------------------------------------------------------------------------------


def _full_name(ds: DataSource) -> str:
    return f"projects/{(ds.cloud_state or {}).get('project_id')}/databases/{firestore.database_of(ds)}"


def database_out(info: dict) -> dict:
    """Point-in-time recovery and delete protection of the database (`GET databases/<id>`)."""
    return {
        "pitr": info.get("pointInTimeRecoveryEnablement") == "POINT_IN_TIME_RECOVERY_ENABLED",
        "earliest_version_time": info.get("earliestVersionTime"),
        "delete_protection": info.get("deleteProtectionState") == "DELETE_PROTECTION_ENABLED",
    }


def describe(gcp, ds: DataSource) -> dict:
    return _call(gcp, OWNER_ROLE, "GET", _db_path(ds)) or {}


def set_pitr(ds: DataSource, enabled: bool) -> dict:
    """Google applies it in the background (a long-running operation); the Backups tab shows the new state."""
    state = "POINT_IN_TIME_RECOVERY_ENABLED" if enabled else "POINT_IN_TIME_RECOVERY_DISABLED"
    params = {"updateMask": "pointInTimeRecoveryEnablement"}
    _call(firestore.gcp_for(ds), OWNER_ROLE, "PATCH", _db_path(ds), {"pointInTimeRecoveryEnablement": state}, params)
    return {"pitr": enabled}


def clone_spec(ds: DataSource, point_in_time: datetime) -> tuple[dict, str]:
    """`({database, snapshotTime}, location)` to copy the database as it was at `point_in_time` (rounded down to
    the minute, as Google requires) into a new one; `400 invalid_restore_time` outside the version window."""
    at = (point_in_time if point_in_time.tzinfo else point_in_time.replace(tzinfo=UTC)).astimezone(UTC)
    at = at.replace(second=0, microsecond=0)
    info = describe(firestore.gcp_for(ds), ds)
    try:
        start = datetime.fromisoformat(str(info["earliestVersionTime"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        start = None
    if at > datetime.now(UTC) - timedelta(minutes=1) or (start and at < start):
        since = f" from {start:%Y-%m-%d %H:%M} UTC" if start else ""
        raise ApiError(
            400,
            "invalid_restore_time",
            f"Pick a minute in the past{since} (Google keeps the last hour, or 7 days with point-in-time recovery on)",
            {"field": "point_in_time"},
        )
    spec = {"database": _full_name(ds), "snapshotTime": f"{at:%Y-%m-%dT%H:%M:%SZ}"}
    return spec, info.get("locationId") or (ds.cloud_state or {}).get("location") or ""


# --- deletes (the routes check the typed name and confirm_delete first) ---------------------------------


def database_delete_summary(ds: DataSource) -> dict:
    project = (ds.cloud_state or {}).get("project_id")
    return {
        "name": ds.name,
        "removes": [
            f"Firestore database {firestore.database_of(ds)} in the Google project {project}: every document in it "
            "and its backup schedules (Google has no undo)",
            f"{ds.name} in Deployer",
        ],
        "keeps": "Backups already taken stay in Google until they expire (restore them in the Google Cloud console), "
        "and exports stay in Cloud Storage.",
    }


def delete_database(ds: DataSource) -> None:
    """Deletes the database in Google, unless its delete protection is on (`409 delete_protected`)."""
    gcp = firestore.gcp_for(ds)
    info = describe(gcp, ds)
    if info.get("deleteProtectionState") == "DELETE_PROTECTION_ENABLED":
        raise ApiError(
            409,
            "delete_protected",
            "Google's delete protection is on for this database: turn it off in the Google Cloud console "
            "(Firestore -> the database -> Delete protection), then delete it here.",
        )
    etag = {"etag": info["etag"]} if info.get("etag") else None
    _call(gcp, OWNER_ROLE, "DELETE", _db_path(ds), None, etag, destroy=True)


def backup_delete_summary(ds: DataSource, backup: str) -> dict:
    restore_location(ds, backup)  # one of this project's backups, else 422
    return {
        "name": ds.name,
        "removes": [f"The backup {backup.rsplit('/', 1)[-1]} of {firestore.database_of(ds)} (Google has no undo)"],
        "keeps": "The database and its other backups are not touched.",
    }


def delete_backup(ds: DataSource, backup: str) -> None:
    restore_location(ds, backup)
    gcp = firestore.gcp_for(ds)
    path = backup.split("/", 2)[2]  # locations/<l>/backups/<id>
    try:
        found = _call(gcp, OWNER_ROLE, "GET", path) or {}
    except ApiError as exc:
        if exc.code != "not_found":
            raise
        found = {}
    if found.get("database") != _full_name(ds):
        raise ApiError(404, "backup_not_found", "No such backup of this database")
    _call(gcp, OWNER_ROLE, "DELETE", path, destroy=True)


def _export_dir(ds: DataSource) -> str:
    return f"deployer-exports/{firestore.database_of(ds).strip('()')}/"


def export_folder(ds: DataSource, uri: str) -> tuple[str, str]:
    """(bucket, folder) of an export Deployer made of this database in a `deployer-*` bucket, else 422."""
    pattern = rf"gs://(deployer-[a-z0-9_.-]{{0,52}}[a-z0-9])/({re.escape(_export_dir(ds))}\d{{8}}-\d{{6}})/?"
    m = re.fullmatch(pattern, (uri or "").strip())
    if not m:
        raise ApiError(
            422,
            "validation_error",
            "Deployer only deletes its own exports of this database in a deployer-* bucket "
            "(gs://deployer-.../deployer-exports/<database>/<time>, from the list); delete others in the Google Cloud "
            "console",
            {"field": "uri"},
        )
    return m[1], m[2]


def export_delete_summary(ds: DataSource, uri: str) -> dict:
    bucket, folder = export_folder(ds, uri)
    return {
        "name": ds.name,
        "removes": [f"Every file of the export gs://{bucket}/{folder} (Google has no undo)"],
        "keeps": "The database is not touched, nor databases already imported from this export.",
    }


def _storage(fn, *args):
    try:
        return fn(*args)
    except CloudError as exc:
        if exc.status == 404:
            raise ApiError(404, "export_not_found", "That export's bucket is gone") from None
        raise ApiError(
            502,
            "cloud_error",
            f"{exc.message} - the Firebase service account needs the Storage Admin role on the bucket "
            "(Settings -> Cloud accounts shows how).",
        ) from None


def delete_export(ds: DataSource, uri: str) -> int:
    """Deletes the export's files; returns how many."""
    bucket, folder = export_folder(ds, uri)
    gcp = firestore.gcp_for(ds)
    names, _ = _storage(gcp.list_objects, bucket, f"{folder}/")
    if not names:
        raise ApiError(404, "export_not_found", "No files left in that export")
    # ponytail: one request per file while the admin waits; a job if exports grow to thousands of files.
    for name in names:
        _storage(gcp.delete_object, bucket, name)
    return len(names)


def list_exports(gcp, ds: DataSource) -> list[dict]:
    """The exports Deployer made of this database in its remembered `deployer-*` bucket, newest first (exports in
    the user's own buckets are listed and deleted in the Google Cloud console)."""
    bucket = (ds.cloud_state or {}).get("export_bucket") or ""
    if not bucket.startswith("deployer-"):
        return []
    try:
        _, folders = gcp.list_objects(bucket, _export_dir(ds), "/")
    except CloudError as exc:
        if exc.status == 404:
            return []
        raise ApiError(
            502,
            "cloud_error",
            f"{exc.message} - the Firebase service account needs the Storage Admin role on the bucket",
        ) from None
    out = []
    for folder in sorted(folders, reverse=True):
        m = re.search(r"/(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)(\d\d)/?$", folder)
        if m:
            uri = f"gs://{bucket}/{folder.rstrip('/')}"
            out.append({"uri": uri, "created_at": f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}Z"})
    return out


# --- the Backups tab ------------------------------------------------------------------------------------


def overview(ds: DataSource) -> dict:
    """The database's point-in-time recovery and delete protection (`status`), its schedules, backups, recent
    exports / imports and stored exports; each read on its own, so a missing role only empties that one
    (`problems` says why)."""
    gcp = firestore.gcp_for(ds)
    state = ds.cloud_state or {}
    out: dict[str, Any] = {
        "database": firestore.database_of(ds),
        "location": state.get("location"),
        "bucket": state.get("export_bucket"),
        "default_bucket": default_bucket(ds),
        "days": list(DAYS),
        "max_retention_days": MAX_RETENTION_DAYS,
        "costs": {
            "export": EXPORT_COST,
            "import": IMPORT_COST,
            "schedule": SCHEDULE_COST,
            "restore": RESTORE_COST,
            "pitr": PITR_COST,
            "clone": CLONE_COST,
        },
        "notes": {"export": EXPORT_NOTE, "restore": RESTORE_NOTE, "pitr": PITR_NOTE},
        "problems": {},
        "status": None,
    }
    try:
        out["status"] = database_out(describe(gcp, ds))
    except ApiError as exc:
        out["problems"]["status"] = exc.message
    lists = (
        ("schedules", list_schedules),
        ("backups", list_backups),
        ("operations", list_operations),
        ("exports", list_exports),
    )
    for key, fn in lists:
        try:
            out[key] = fn(gcp, ds)
        except ApiError as exc:
            out[key], out["problems"][key] = [], exc.message
    return out
