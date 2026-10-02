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

Exports, imports, schedules and restores cost money, so their routes need `confirm_billing: true`. Nothing here
deletes data: exports stay in the bucket, backups expire on their own, removed schedules keep their backups.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
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
    "100,000) plus Cloud Storage for the files (about US$0.02 per GB a month) until you delete them in the Google "
    "Cloud console (Cloud Storage). Deployer never deletes exports."
)
IMPORT_COST = (
    "Importing makes a new Firestore database and writes every exported document into it: Google bills one write "
    "per document (about US$0.18 per 100,000) and the new database's storage and use until you delete it in the "
    "Firebase console."
)
SCHEDULE_COST = (
    "Google takes the backups on its own (also while this PC is off) and keeps each one until its retention ends, "
    "billing its storage (about US$0.03 per GB a month; prices vary by location). Backups do not slow the "
    "database down. Removing the schedule keeps the backups already taken until they expire."
)
RESTORE_COST = (
    "Restoring makes a new Firestore database from the backup (the original is not touched): Google bills the "
    "restore (about US$0.20 per GB) and the new database's storage and use until you delete it in the Firebase "
    "console."
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
_SCHEDULE_ID = re.compile(r"^[\w-]{1,100}$")
_GS_URI = re.compile(r"^gs://[a-z0-9][a-z0-9_.-]{1,61}[a-z0-9](/[^\s]{0,1000})?$")


def _db_path(ds: DataSource, tail: str = "") -> str:
    return f"databases/{quote(firestore.database_of(ds), safe='()')}{tail}"


def _call(gcp, role: str, method: str, path: str, body: Any = None) -> Any:
    try:
        return gcp.firestore(method, path, body, None)
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


# --- the Backups tab ------------------------------------------------------------------------------------


def overview(ds: DataSource) -> dict:
    """Schedules, backups and recent exports / imports; each list on its own, so a missing role only empties
    that one (`problems` says why)."""
    gcp = firestore.gcp_for(ds)
    state = ds.cloud_state or {}
    out: dict[str, Any] = {
        "database": firestore.database_of(ds),
        "location": state.get("location"),
        "bucket": state.get("export_bucket"),
        "default_bucket": default_bucket(ds),
        "days": list(DAYS),
        "max_retention_days": MAX_RETENTION_DAYS,
        "costs": {"export": EXPORT_COST, "import": IMPORT_COST, "schedule": SCHEDULE_COST, "restore": RESTORE_COST},
        "notes": {"export": EXPORT_NOTE, "restore": RESTORE_NOTE},
        "problems": {},
    }
    for key, fn in (("schedules", list_schedules), ("backups", list_backups), ("operations", list_operations)):
        try:
            out[key] = fn(gcp, ds)
        except ApiError as exc:
            out[key], out["problems"][key] = [], exc.message
    return out
