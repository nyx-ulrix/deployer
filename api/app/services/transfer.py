"""Encrypted export / import of instances and projects (docs/ARCHITECTURE.md "Export / import format").

File layout::

    {"format": "deployer-export", "version": 1, "scope": "instance" | "projects", "created_at": ...,
     "app_version": ..., "encryption": {...scrypt/AES-GCM header...},
     "payload": base64(AES-256-GCM(gzip(plaintext JSON)))}

Plaintext payload (version 1)::

    {"version": 1, "scope": ..., "created_at": ...,
     "instance_settings": [{key, value, is_secret}],          # instance scope only, decrypted values
     "users": [...], "user_identities": [...],                 # instance scope only (with password_hash)
     "projects": [...], "project_members": [... + email],
     "project_invites": [...],                                 # instance scope only, pending invites
     "api_keys": [... + decrypted "secret" (null for keys made before secrets were kept), without secret_encrypted],
     "apps": [... + decrypted "env", "repo_token", "webhook_secret"; no port / live deployment],   # docs/DEPLOYMENTS.md
     "data_sources": [... + decrypted "config", without config_encrypted],
     "schema_links": [...], "saved_queries": [...], "saved_query_versions": [...],   # query_runs never travel
     "data": {<data_source_id>: {"kind": "sql", "engine", "database_name",
                                 "tables": [{name, create_sql, columns: [{name, type}], rows: [[...], ...]}]}
                              | {"kind": "nosql", "database_name",
                                 "collections": [{name, type, options, indexes: [...], documents: [...]}]}}}

Rows are arrays aligned with `columns` (binary -> {"$base64"}, decimals/dates -> strings); Mongo
options, indexes and documents are canonical Extended JSON. Only *managed* sources carry data.

Instance exports additionally carry ``devices``, ``device_project_grants``, ``backup_policies``,
``domains`` and ``backup_keys`` (backup key material, docs/BACKUPS.md). A host device's own
``device_link`` / ``device_hosted_credentials`` settings are never exported or imported.

Host devices (docs/DEVICES.md): data of device-hosted sources is produced *on the device*
(``datasource.export`` RPC -> transfer upload) and copied verbatim into the payload; on import it is
restored on the same device when that device is known here, eligible and connected, otherwise on the
main server with a warning. Soft-deleted sources are not exported.

Streaming & limits
------------------
- The plaintext JSON is written incrementally into a gzip temp file while rows / documents are read
  with server-side cursors, so exporting never holds a whole table or collection in Python objects.
- The gzip file is then encrypted and base64-encoded in chunks (``encrypt_stream_with_passphrase``).
- Import decrypts and decompresses in memory and parses the plaintext with ``json.loads``: peak memory
  is several times the uncompressed payload. ``import_limit()`` (a sixth of the memory available now to
  the API container or the machine, whichever is less, at most 1 GiB) caps both the upload and the
  unpacked payload with a 413 ``file_too_large`` instead of the API being OOM-killed.
  Larger databases should be moved with native dump tools.
- Views, triggers, stored routines and events of managed MariaDB databases are not exported; MongoDB
  views are. They are counted into the source's ``data`` entry as ``"skipped": {"views": n, ...}`` and
  reported as ``warnings`` in the export counts (audit log) and the import summary. Generated
  (virtual/stored) SQL columns are recreated by their DDL, not copied.
- Backup files, backup/PITR history, versions, query runs, deployments and audit logs never travel.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import itertools
import json
import logging
import os
import re
import tempfile
import zlib
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime
from typing import IO, Any

from bson import json_util
from cryptography.exceptions import InvalidTag
from sqlalchemy import DateTime, select
from sqlalchemy.orm import Session

from app import __version__
from app.crypto import (
    decrypt_json,
    decrypt_secret,
    decrypt_with_passphrase,
    encrypt_json,
    encrypt_secret,
    encrypt_stream_with_passphrase,
)
from app.errors import ApiError
from app.models import (
    ApiKey,
    App,
    BackupPolicy,
    CloudConnection,
    DataSource,
    Device,
    DeviceProjectGrant,
    Domain,
    InstanceSetting,
    Project,
    ProjectInvite,
    ProjectMember,
    SavedQuery,
    SavedQueryVersion,
    SchemaLink,
    User,
    UserIdentity,
    new_id,
    utcnow,
)
from app.services import backup_crypto, connections, ddl_export, device_host, device_rpc, provisioning
from app.services.data_browser import encode_value
from app.services.slugs import unique_slug

log = logging.getLogger(__name__)

FORMAT = "deployer-export"
VERSION = 1
MIN_PASSPHRASE = 12
MAX_IMPORT_BYTES = 1024**3
BATCH = 1000
DEVICE_TIMEOUT = 6 * 3600
# A host device's own link/credentials never travel in exports: a restored copy must not
# impersonate the device (it would kick the real one off the main Deployer).
DEVICE_LOCAL_SETTINGS = frozenset(
    {"device_link", "device_hosted_credentials", "device_cohost_apps", "cohost_apps_tunnel_token"}
)
_CANONICAL = json_util.CANONICAL_JSON_OPTIONS


def check_passphrase(passphrase: str | None) -> str:
    if not passphrase or len(passphrase) < MIN_PASSPHRASE:
        raise ApiError(422, "validation_error", f"The passphrase must be at least {MIN_PASSPHRASE} characters")
    return passphrase


def export_filename(scope: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"deployer-{scope}-{now.strftime('%Y%m%d-%H%M')}.json"


# =============================================================================================
# row <-> dict
# =============================================================================================


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return encode_value(value)


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def model_to_dict(obj: Any) -> dict[str, Any]:
    out = {}
    for col in obj.__table__.columns:
        value = getattr(obj, col.key)
        out[col.key] = value.isoformat() if isinstance(value, datetime) else value
    return out


def _parse_dt(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApiError(400, "invalid_export", f"Invalid timestamp in export: {value!r}") from exc
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    return value


def dict_to_model(cls: type, row: dict[str, Any], **overrides: Any) -> Any:
    if not isinstance(row, dict):
        raise ApiError(400, "invalid_export", f"Malformed {cls.__name__} record")
    kwargs = {}
    for col in cls.__table__.columns:
        if col.key in overrides:
            kwargs[col.key] = overrides[col.key]
        elif col.key in row:
            value = row[col.key]
            kwargs[col.key] = _parse_dt(value) if isinstance(col.type, DateTime) else value
    return cls(**kwargs)


# =============================================================================================
# export
# =============================================================================================


class _Writer:
    """Minimal streaming JSON writer on top of a text file."""

    def __init__(self, fh: IO[str]):
        self.fh = fh
        self._first: list[bool] = []

    def open(self, char: str) -> None:
        self.fh.write(char)
        self._first.append(True)

    def close(self, char: str) -> None:
        self.fh.write(char)
        self._first.pop()

    def _sep(self) -> None:
        if self._first and self._first[-1]:
            self._first[-1] = False
        else:
            self.fh.write(",")

    def item(self, raw: str) -> None:
        self._sep()
        self.fh.write(raw)

    def field(self, name: str, value: Any) -> None:
        self._sep()
        self.fh.write(json.dumps(name) + ":" + _dumps(value))

    def raw_field(self, name: str, raw: str) -> None:
        self._sep()
        self.fh.write(json.dumps(name) + ":" + raw)

    def open_field(self, name: str, char: str) -> None:
        self._sep()
        self.fh.write(json.dumps(name) + ":")
        self.open(char)


def _pending_invites(db: Session) -> list[ProjectInvite]:
    now = utcnow()
    return list(
        db.scalars(
            select(ProjectInvite).where(
                ProjectInvite.accepted_at.is_(None), ProjectInvite.revoked_at.is_(None), ProjectInvite.expires_at > now
            )
        )
    )


def _setting_out(row: InstanceSetting) -> dict:
    if row.is_secret:
        value: Any = decrypt_secret(row.value)
    else:
        try:
            value = json.loads(row.value)
        except ValueError:
            value = row.value
    return {"key": row.key, "value": value, "is_secret": bool(row.is_secret)}


def _api_key_out(key: ApiKey) -> dict:
    row = model_to_dict(key)
    row.pop("secret_encrypted", None)
    row["secret"] = decrypt_secret(key.secret_encrypted) if key.secret_encrypted else None
    return row


def _api_key_secret(row: dict) -> str | None:
    # Re-encrypted with this instance's MASTER_KEY; an old export's `secret_encrypted` is unusable here.
    secret = row.get("secret") if isinstance(row, dict) else None
    return encrypt_secret(secret) if isinstance(secret, str) and secret else None


_APP_SECRETS = ("env_encrypted", "repo_token_encrypted", "webhook_secret_encrypted")


def _app_out(app: App) -> dict:
    row = model_to_dict(app)
    # The GitHub connection token itself is never exported; the hook belongs to the source instance's URL.
    for key in (*_APP_SECRETS, "port", "live_deployment_id", "github_hook_id"):
        row.pop(key, None)
    row["env"] = decrypt_json(app.env_encrypted) if app.env_encrypted else {}
    row["repo_token"] = decrypt_secret(app.repo_token_encrypted) if app.repo_token_encrypted else None
    row["webhook_secret"] = decrypt_secret(app.webhook_secret_encrypted)
    return row


def _app_model(db: Session, row: dict, **overrides: Any) -> App:
    """Re-encrypts the secrets with this instance's key; a fresh port; nothing live yet."""
    from app.crypto import random_token
    from app.services import deployments

    env = row.get("env") if isinstance(row.get("env"), dict) else {}
    token = row.get("repo_token")
    secret = row.get("webhook_secret")
    app = dict_to_model(
        App,
        row,
        env_encrypted=encrypt_json({str(k): str(v) for k, v in env.items()}),
        repo_token_encrypted=encrypt_secret(token) if isinstance(token, str) and token else None,
        webhook_secret_encrypted=encrypt_secret(secret if isinstance(secret, str) and secret else random_token(32)),
        port=deployments.allocate_port(db),
        live_deployment_id=None,
        **overrides,
    )
    if app.api_key_id and db.get(ApiKey, app.api_key_id) is None:
        app.api_key_id = None
    # docs/CLOUD.md: cloud connections are not exported (credentials). An app keeps its cloud target only
    # when it keeps its id and the connection exists here; otherwise it comes back on this PC (`local`) so
    # two apps never share (and tear down) the same cloud resources.
    keep_cloud = "id" not in overrides and app.cloud_connection_id and db.get(CloudConnection, app.cloud_connection_id)
    if not keep_cloud:
        app.target, app.cloud_connection_id, app.cloud_state = "local", None, None
    return app


def _source_out(ds: DataSource) -> dict:
    row = model_to_dict(ds)
    row.pop("config_encrypted", None)
    row["config"] = decrypt_json(ds.config_encrypted)
    return row


def _mysql_columns(conn: Any, table: str) -> list[dict]:
    cols = []
    for name, ctype, extra in conn.exec_driver_sql(
        "SELECT COLUMN_NAME, COLUMN_TYPE, EXTRA FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
        (table,),
    ):
        extra_text = ddl_export._s(extra) or ""
        if (
            re.search(r"VIRTUAL|STORED|PERSISTENT|GENERATED", extra_text, re.IGNORECASE)
            and "DEFAULT_GENERATED" not in extra_text.upper()
        ):
            continue
        cols.append({"name": ddl_export._s(name), "type": ddl_export._s(ctype)})
    return cols


_SKIPPED_SQL = {
    "views": "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'VIEW'",
    "triggers": "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()",
    "routines": "SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = DATABASE()",
    "events": "SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA = DATABASE()",
}


def _skipped_objects(conn: Any) -> dict[str, int]:
    """Counts the database objects the export does not carry (views, triggers, routines, events)."""
    counts = {kind: int(conn.exec_driver_sql(sql).scalar() or 0) for kind, sql in _SKIPPED_SQL.items()}
    return {kind: n for kind, n in counts.items() if n}


def skipped_warning(source_name: str, skipped: Any) -> str | None:
    """ "Data source 'x' has 2 views, 1 trigger that ..." or None when nothing was skipped."""
    if not isinstance(skipped, dict):
        return None
    parts = [
        f"{n} {kind[:-1] if n == 1 else kind}" for kind in _SKIPPED_SQL if isinstance(n := skipped.get(kind), int) and n
    ]
    if not parts:
        return None
    return (
        f"Data source '{source_name}' has {', '.join(parts)} that exports do not carry; recreate them by hand "
        "(e.g. from a SQL dump of the original database)"
    )


def _write_sql_data(w: _Writer, ds: DataSource) -> tuple[int, int, dict[str, int]]:
    config = decrypt_json(ds.config_encrypted)
    engine = connections.build_sql_engine(ds.engine, config, pooled=False)
    rows_total = 0
    tables = 0
    try:
        order = ddl_export.mysql_table_order(engine)
        with engine.connect() as conn:
            q = engine.dialect.identifier_preparer.quote_identifier
            w.field("kind", "sql")
            w.field("engine", ds.engine)
            w.field("database_name", ds.database_name)
            w.open_field("tables", "[")
            for table in order:
                create_sql = ddl_export.show_create_table(conn, engine.dialect, table)
                columns = _mysql_columns(conn, table)
                w._sep()
                w.open("{")
                w.field("name", table)
                w.field("create_sql", create_sql)
                w.field("columns", columns)
                w.open_field("rows", "[")
                if columns:
                    select_sql = "SELECT " + ", ".join(q(c["name"]) for c in columns) + " FROM " + q(table)
                    result = conn.execution_options(stream_results=True, max_row_buffer=BATCH).exec_driver_sql(
                        select_sql.replace("%", "%%")
                    )
                    for row in result:
                        w.item(_dumps([encode_value(v) for v in row]))
                        rows_total += 1
                    result.close()
                w.close("]")
                w.close("}")
                tables += 1
            w.close("]")
            skipped = _skipped_objects(conn)
            if skipped:
                w.field("skipped", skipped)
    finally:
        engine.dispose()
    return tables, rows_total, skipped


def _write_mongo_data(w: _Writer, ds: DataSource) -> int:
    config = decrypt_json(ds.config_encrypted)
    client = connections.build_mongo_client(config, pooled=False)
    documents = 0
    try:
        database = client[config["database"]]
        infos = [i for i in database.list_collections() if not i["name"].startswith("system.")]
        infos.sort(key=lambda i: (i.get("type") == "view", i["name"]))
        w.field("kind", "nosql")
        w.field("engine", ds.engine)
        w.field("database_name", ds.database_name)
        w.open_field("collections", "[")
        for info in infos:
            ctype = info.get("type", "collection")
            w._sep()
            w.open("{")
            w.field("name", info["name"])
            w.field("type", ctype)
            w.raw_field("options", json_util.dumps(info.get("options") or {}, json_options=_CANONICAL))
            coll = database[info["name"]]
            if ctype == "view":
                w.raw_field("indexes", "[]")
                w.raw_field("documents", "[]")
            else:
                indexes = [{"name": name, **ix} for name, ix in coll.index_information().items()]
                w.raw_field("indexes", json_util.dumps(indexes, json_options=_CANONICAL))
                w.open_field("documents", "[")
                for doc in coll.find(batch_size=BATCH):
                    w.item(json_util.dumps(doc, json_options=_CANONICAL))
                    documents += 1
                w.close("]")
            w.close("}")
        w.close("]")
    finally:
        client.close()
    return documents


def write_source_data(fh: IO[str], ds: DataSource) -> dict[str, Any]:
    """Writes one source's `data` entry (a JSON object) to `fh`. Used locally and on host devices."""
    w = _Writer(fh)
    w.open("{")
    if ds.kind == "sql":
        tables, rows, skipped = _write_sql_data(w, ds)
        counts = {"tables": tables, "rows": rows, "documents": 0, "skipped": skipped}
    else:
        counts = {"tables": 0, "rows": 0, "documents": _write_mongo_data(w, ds)}
    w.close("}")
    return counts


def _write_device_data(fh: IO[str], ds: DataSource) -> dict[str, Any]:
    """Has the host device export the source's data and copies it verbatim into `fh`."""
    transfer_id = device_rpc.create_transfer(ds.device_id, "put")
    try:
        try:
            result = device_rpc.call(
                ds.device_id,
                "datasource.export",
                {
                    "kind": ds.kind,
                    "database_name": ds.database_name,
                    "source_name": ds.name,
                    "transfer_id": transfer_id,
                },
                timeout=DEVICE_TIMEOUT,
            )
        except ApiError as exc:
            if exc.code == "device_offline":
                raise ApiError(
                    503, "device_offline", f"The host device of data source '{ds.name}' is offline; try again later"
                ) from exc
            raise
        path = device_rpc.claim_upload(transfer_id)
        with gzip.open(path, "rt", encoding="utf-8") as src:
            head = src.read(1)
            if head != "{":
                raise ApiError(502, "export_failed", f"Host device returned invalid data for '{ds.name}'")
            fh.write(head)
            while chunk := src.read(1 << 20):
                fh.write(chunk)
    finally:
        device_rpc.finish_transfer(transfer_id)
    result = result if isinstance(result, dict) else {}
    return {
        "rows": int(result.get("rows") or 0),
        "documents": int(result.get("documents") or 0),
        "skipped": result.get("skipped"),
    }


def write_payload(fh: IO[str], db: Session, *, scope: str, projects: list[Project], created_at: str) -> dict[str, Any]:
    """Streams the plaintext payload JSON to `fh`. Returns counts (+ `warnings` when objects were skipped)."""
    w = _Writer(fh)
    project_ids = [p.id for p in projects]
    counts: dict[str, Any] = {"users": 0, "projects": len(projects), "data_sources": 0, "rows": 0, "documents": 0}
    warnings: list[str] = []
    w.open("{")
    w.field("version", VERSION)
    w.field("scope", scope)
    w.field("created_at", created_at)

    if scope == "instance":
        w.field(
            "instance_settings",
            [_setting_out(s) for s in db.scalars(select(InstanceSetting)) if s.key not in DEVICE_LOCAL_SETTINGS],
        )
        users = list(db.scalars(select(User).order_by(User.created_at)))
        counts["users"] = len(users)
        w.field("users", [model_to_dict(u) for u in users])
        w.field("user_identities", [model_to_dict(i) for i in db.scalars(select(UserIdentity))])
    w.field("projects", [model_to_dict(p) for p in projects])

    members = []
    if project_ids:
        for m, email in db.execute(
            select(ProjectMember, User.email)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id.in_(project_ids))
        ):
            row = model_to_dict(m)
            row["email"] = email
            members.append(row)
    w.field("project_members", members)
    if scope == "instance":
        w.field("project_invites", [model_to_dict(i) for i in _pending_invites(db)])

    def by_project(model: type) -> list[Any]:
        if not project_ids:
            return []
        return list(db.scalars(select(model).where(model.project_id.in_(project_ids)).order_by(model.created_at)))

    w.field("api_keys", [_api_key_out(k) for k in by_project(ApiKey)])
    apps = by_project(App)
    w.field("apps", [_app_out(a) for a in apps])
    sources: list[DataSource] = [ds for ds in by_project(DataSource) if ds.deleted_at is None]
    counts["data_sources"] = len(sources)
    w.field("data_sources", [_source_out(ds) for ds in sources])
    w.field("schema_links", [model_to_dict(link) for link in by_project(SchemaLink)])
    saved = by_project(SavedQuery)
    w.field("saved_queries", [model_to_dict(q) for q in saved])
    versions = []
    if saved:
        versions = db.scalars(
            select(SavedQueryVersion)
            .where(SavedQueryVersion.saved_query_id.in_([q.id for q in saved]))
            .order_by(SavedQueryVersion.saved_query_id, SavedQueryVersion.version)
        )
    w.field("saved_query_versions", [model_to_dict(v) for v in versions])
    if scope == "instance":
        w.field("devices", [model_to_dict(d) for d in db.scalars(select(Device).order_by(Device.created_at))])
        w.field("device_project_grants", [model_to_dict(g) for g in db.scalars(select(DeviceProjectGrant))])
        source_ids = {ds.id for ds in sources}
        w.field(
            "backup_policies",
            [model_to_dict(p) for p in db.scalars(select(BackupPolicy)) if p.data_source_id in source_ids],
        )
        w.field("domains", [model_to_dict(d) for d in db.scalars(select(Domain).order_by(Domain.created_at))])
        w.field("backup_keys", backup_crypto.export_key_material())
    elif apps:
        app_ids = [a.id for a in apps]
        w.field("domains", [model_to_dict(d) for d in db.scalars(select(Domain).where(Domain.app_id.in_(app_ids)))])

    w.open_field("data", "{")
    for ds in sources:
        if ds.mode != "managed":
            continue
        if connections.device_removed(ds):
            warnings.append(f"{ds.name}: {connections.DEVICE_REMOVED} Its data is not in this export.")
            continue
        w._sep()
        w.fh.write(json.dumps(ds.id) + ":")
        if ds.device_id:
            device_counts = _write_device_data(w.fh, ds)
            counts["rows"] += device_counts["rows"]
            counts["documents"] += device_counts["documents"]
            if warning := skipped_warning(ds.name, device_counts["skipped"]):
                warnings.append(warning)
            continue
        w.open("{")
        try:
            if ds.kind == "sql":
                _, rows, skipped = _write_sql_data(w, ds)
                counts["rows"] += rows
                if warning := skipped_warning(ds.name, skipped):
                    warnings.append(warning)
            else:
                counts["documents"] += _write_mongo_data(w, ds)
        except ApiError:
            raise
        except Exception as exc:
            msg = connections.redact(str(getattr(exc, "orig", None) or exc))
            raise ApiError(502, "export_failed", f"Could not read managed data source '{ds.name}': {msg}") from exc
        w.close("}")
    w.close("}")
    w.close("}")
    if warnings:
        counts["warnings"] = warnings
    return counts


def build_export_file(db: Session, *, scope: str, projects: list[Project], passphrase: str) -> tuple[str, dict]:
    """Writes the encrypted export to a temp file. Returns (path, counts); caller deletes the file."""
    check_passphrase(passphrase)
    now = datetime.now(UTC).replace(microsecond=0)
    created_at = now.replace(tzinfo=None).isoformat() + "Z"
    fd, gz_path = tempfile.mkstemp(prefix="deployer-payload-", suffix=".json.gz")
    os.close(fd)
    out_fd, out_path = tempfile.mkstemp(prefix="deployer-export-", suffix=".json")
    os.close(out_fd)
    try:
        with gzip.open(gz_path, "wt", encoding="utf-8", compresslevel=6) as fh:
            counts = write_payload(fh, db, scope=scope, projects=projects, created_at=created_at)
        with open(gz_path, "rb") as src, open(out_path, "w", encoding="utf-8") as out:
            header, payload_chunks = encrypt_stream_with_passphrase(src, passphrase)
            out.write("{")
            out.write(f'"format":{json.dumps(FORMAT)},"version":{VERSION},"scope":{json.dumps(scope)},')
            out.write(f'"created_at":{json.dumps(created_at)},"app_version":{json.dumps(__version__)},')
            out.write(f'"encryption":{json.dumps(header)},"payload":"')
            for chunk in payload_chunks:
                out.write(chunk)
            out.write('"}')
        return out_path, counts
    except BaseException:
        _unlink(out_path)
        raise
    finally:
        _unlink(gz_path)


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# =============================================================================================
# reading
# =============================================================================================


def _cgroup_free(root: str = "/sys/fs/cgroup") -> int | None:
    """Memory left under this container's limit (compose sets API_MEM_LIMIT, while /proc/meminfo shows
    the whole VM), not counting reclaimable file cache; None when unlimited or not readable."""
    for limit_f, usage_f, stat_f in (
        ("memory.max", "memory.current", "memory.stat"),  # cgroup v2
        ("memory/memory.limit_in_bytes", "memory/memory.usage_in_bytes", "memory/memory.stat"),  # v1
    ):
        try:
            with open(os.path.join(root, limit_f), encoding="ascii") as fh:
                raw = fh.read().strip()
            if raw == "max":
                return None
            with open(os.path.join(root, usage_f), encoding="ascii") as fh:
                usage = int(fh.read())
            with open(os.path.join(root, stat_f), encoding="ascii") as fh:
                stat = {k: int(v) for k, _, v in (line.partition(" ") for line in fh) if v.strip().isdigit()}
        except (OSError, ValueError):
            continue
        cache = stat.get("total_inactive_file", stat.get("inactive_file", 0))
        return max(0, int(raw) - (usage - cache))
    return None


def import_limit() -> int:
    """Most bytes an import may hold: a sixth of the memory available now, to the API container or the
    machine, whichever is less (the parsed payload takes several times its text), at most
    MAX_IMPORT_BYTES; MAX_IMPORT_BYTES where memory can't be read."""
    # ponytail: a heuristic cap; the real fix is a chunked import format (audit A-043, "later").
    used, total = device_host._memory()
    free = [
        f for f in ((total - used) if used is not None and total is not None else None, _cgroup_free()) if f is not None
    ]
    return min(MAX_IMPORT_BYTES, min(free) // 6) if free else MAX_IMPORT_BYTES


def _too_large(what: str, limit: int) -> ApiError:
    return ApiError(
        413,
        "file_too_large",
        f"{what} too large to import on this machine: imports are unpacked in memory, and with the memory free "
        f"now the limit is {limit // 2**20} MB. Free memory (or raise API_MEM_LIMIT in deploy/.env) and retry, "
        "or move large databases with a SQL dump (mariadb-dump / mongodump) instead",
        {"limit_bytes": limit},
    )


def save_upload(src: IO[bytes], max_bytes: int | None = None) -> str:
    """Copies an uploaded file to a temp file in chunks, enforcing `import_limit()` (413)."""
    max_bytes = import_limit() if max_bytes is None else max_bytes
    fd, path = tempfile.mkstemp(prefix="deployer-import-", suffix=".json")
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise _too_large("The export file is", max_bytes)
                out.write(chunk)
    except BaseException:
        _unlink(path)
        raise
    return path


def _gunzip(data: bytes, limit: int) -> bytes:
    """gzip.decompress that stops (413) once the output passes `limit`, before it is all in memory."""
    d = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    out = d.decompress(data, limit + 1)
    if len(out) > limit:
        raise _too_large("The export's contents are", limit)
    if not d.eof:
        raise EOFError("truncated gzip stream")
    return out


def read_export_file(path: str, passphrase: str, expected_scope: str) -> dict[str, Any]:
    check_passphrase(passphrase)
    invalid = ApiError(400, "invalid_export", "This is not a valid Deployer export file")
    try:
        with open(path, encoding="utf-8") as fh:
            outer = json.load(fh)
    except (ValueError, UnicodeDecodeError) as exc:
        raise invalid from exc
    if (
        not isinstance(outer, dict)
        or outer.get("format") != FORMAT
        or not isinstance(outer.get("encryption"), dict)
        or not isinstance(outer.get("payload"), str)
    ):
        raise invalid
    if outer.get("version") != VERSION:
        raise ApiError(400, "invalid_export", f"Unsupported export version: {outer.get('version')!r}")
    if outer.get("scope") != expected_scope:
        raise ApiError(
            400,
            "invalid_export",
            f"This file is a '{outer.get('scope')}' export; a '{expected_scope}' export is required here",
            {"scope": outer.get("scope")},
        )
    header = outer["encryption"]
    payload_b64 = outer.pop("payload")
    del outer
    try:
        compressed = decrypt_with_passphrase(header, payload_b64, passphrase)
    except InvalidTag as exc:
        raise ApiError(400, "bad_passphrase", "Wrong passphrase (or the file was modified)") from exc
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise invalid from exc
    del payload_b64
    try:
        plaintext = _gunzip(compressed, import_limit())
        del compressed
        payload = json.loads(plaintext)
    except (OSError, EOFError, ValueError, zlib.error) as exc:
        raise invalid from exc
    if not isinstance(payload, dict) or payload.get("version") != VERSION or payload.get("scope") != expected_scope:
        raise invalid
    return payload


def _list(payload: dict, key: str) -> list[dict]:
    value = payload.get(key) or []
    if not isinstance(value, list):
        raise ApiError(400, "invalid_export", f"Malformed export section: {key}")
    return value


# =============================================================================================
# restoring managed data
# =============================================================================================

_CREATE_TABLE_RE = re.compile(r"^\s*CREATE\s+TABLE\s", re.IGNORECASE)


def _decode_cell(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$base64"}:
            return base64.b64decode(value["$base64"])
        return json.dumps(value)
    if isinstance(value, list):
        return json.dumps(value)
    return value


def _parts(data: dict, key: str) -> Iterable[dict]:
    """`tables` / `collections` of a data entry: a list, or a generator from `read_data_entry`."""
    value = data.get(key) or []
    if not isinstance(value, list | Iterator):
        raise ApiError(400, "invalid_export", f"Malformed export section: {key}")
    return value


def _batches(items: Iterable[Any]) -> Iterator[list[Any]]:
    it = iter(items)
    while batch := list(itertools.islice(it, BATCH)):
        yield batch


def restore_sql_data(ds: DataSource, data: dict) -> int:
    config = decrypt_json(ds.config_encrypted)
    engine = connections.build_sql_engine(ds.engine, config, pooled=False)

    def q(name: str) -> str:
        return engine.dialect.identifier_preparer.quote_identifier(name).replace("%", "%%")

    rows_total = 0
    try:
        with engine.connect() as conn:
            # One pass (create, then fill, table by table) so a streamed entry works; with foreign key
            # checks off a table may reference one created later.
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            for t in _parts(data, "tables"):
                create_sql = t.get("create_sql") or ""
                if not isinstance(create_sql, str) or not _CREATE_TABLE_RE.match(create_sql):
                    raise ApiError(400, "invalid_export", f"Invalid table definition for {t.get('name')!r}")
                conn.exec_driver_sql(create_sql.replace("%", "%%"))
                conn.commit()
                columns = [c["name"] for c in t.get("columns") or []]
                if not columns:
                    continue
                sql = (
                    f"INSERT INTO {q(t['name'])} ("
                    + ", ".join(q(c) for c in columns)
                    + ") VALUES ("
                    + ", ".join(["%s"] * len(columns))
                    + ")"
                )
                for batch in _batches(t.get("rows") or ()):
                    conn.exec_driver_sql(sql, [tuple(_decode_cell(v) for v in row) for row in batch])
                    conn.commit()
                    rows_total += len(batch)
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()
    finally:
        engine.dispose()
    return rows_total


def _from_canonical(value: Any) -> Any:
    return json_util.loads(json.dumps(value), json_options=_CANONICAL)


def restore_mongo_data(ds: DataSource, data: dict) -> int:
    config = decrypt_json(ds.config_encrypted)
    client = connections.build_mongo_client(config, pooled=False)
    documents = 0
    try:
        database = client[config["database"]]
        # Writers list views last (and MongoDB does not need a view's source to exist).
        for coll in _parts(data, "collections"):
            name = coll["name"]
            options = _from_canonical(coll.get("options") or {})
            database.create_collection(name, **options)
            if coll.get("type") == "view":
                continue
            target = database[name]
            for batch in _batches(coll.get("documents") or ()):
                target.insert_many(_from_canonical(batch), ordered=False, bypass_document_validation=True)
                documents += len(batch)
            for ix in _from_canonical(coll.get("indexes") or []):
                ix_name = ix.pop("name", None)
                if not ix_name or ix_name == "_id_":
                    continue
                key, ix_options = ddl_export.index_key_and_options(ix_name, ix)
                target.create_index(list(key.items()), **ix_options)
    finally:
        client.close()
    return documents


def restore_device_data(ds: DataSource, data: dict) -> tuple[int, int]:
    """Sends a `data` entry to the source's host device and restores it there."""
    fd, path = tempfile.mkstemp(prefix="deployer-device-restore-", suffix=".json.gz")
    os.close(fd)
    try:
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as fh:
            fh.write(_dumps(data))
        transfer_id = device_rpc.create_transfer(ds.device_id, "get", source_path=path)
    except BaseException:
        _unlink(path)
        raise
    try:
        result = device_rpc.call(
            ds.device_id,
            "datasource.import",
            {"kind": ds.kind, "database_name": ds.database_name, "source_name": ds.name, "transfer_id": transfer_id},
            timeout=DEVICE_TIMEOUT,
        )
    finally:
        device_rpc.finish_transfer(transfer_id)
    result = result if isinstance(result, dict) else {}
    return int(result.get("rows") or 0), int(result.get("documents") or 0)


class _JsonReader:
    """Pull parser over a text stream: containers are walked token by token and each leaf value (a
    row, a document, a column list) is decoded whole with json's raw_decode."""

    _decoder = json.JSONDecoder()

    def __init__(self, fh: IO[str]):
        self.fh = fh
        self.buf, self.pos, self.eof = "", 0, False

    def _more(self, n: int = 1 << 16) -> None:
        data = "" if self.eof else self.fh.read(n)
        self.eof = not data
        self.buf = self.buf[self.pos :] + data
        self.pos = 0

    def peek(self) -> str:
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos] in " \t\r\n":
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if self.eof:
                raise ValueError("unexpected end of JSON data")
            self._more()

    def take(self, char: str) -> None:
        if self.peek() != char:
            raise ValueError(f"expected {char!r} in JSON data")
        self.pos += 1

    def value(self) -> Any:
        self.peek()
        while True:
            try:
                value, end = self._decoder.raw_decode(self.buf, self.pos)
                # A number cut by the buffer ("1." / "1e") decodes short; valid JSON never has . e E after a value.
                if self.eof or (end < len(self.buf) and self.buf[end] not in ".eE"):
                    self.pos = end
                    return value
            except ValueError:
                if self.eof:
                    raise
            self._more(max(1 << 16, len(self.buf) - self.pos))  # doubling: a big value still parses in O(n)

    def _members(self, close: str) -> Iterator[None]:
        """Yields before each member of the container just opened; the caller reads it."""
        if self.peek() == close:
            self.pos += 1
            return
        while True:
            yield
            if self.peek() != ",":
                self.take(close)
                return
            self.pos += 1

    def keys(self) -> Iterator[str]:
        """Each key of an object; the caller reads its value before asking for the next."""
        self.take("{")
        for _ in self._members("}"):
            key = self.value()
            if not isinstance(key, str):
                raise ValueError("expected an object key in JSON data")
            self.take(":")
            yield key

    def values(self) -> Iterator[Any]:
        self.take("[")
        for _ in self._members("]"):
            yield self.value()


def _stream_parts(r: _JsonReader, bulk: str) -> Iterator[dict]:
    r.take("[")
    for _ in r._members("]"):
        part: dict[str, Any] = {}
        rows: Iterator[Any] | None = None
        for key in r.keys():
            if key == bulk and rows is None:
                rows = part[key] = r.values()
                yield part  # rows / documents are written last, so the rest of `part` is already here
                for _ in rows:  # whatever the consumer did not read
                    pass
            else:
                part[key] = r.value()
        if rows is None:
            yield part


def read_data_entry(fh: IO[str]) -> dict[str, Any]:
    """A source's `data` entry parsed lazily from `fh`: `tables` / `collections` and their `rows` /
    `documents` are generators that parse as they are consumed, so a restore holds about one batch
    instead of the whole dump (the device worker has 384 MB; audit A-049). Keys after the tables
    (`skipped`) are not read. Consume it in order while `fh` is open."""
    r = _JsonReader(fh)
    entry: dict[str, Any] = {}
    for key in r.keys():
        if key in ("tables", "collections"):
            entry[key] = _stream_parts(r, "rows" if key == "tables" else "documents")
            break
        entry[key] = r.value()
    return entry


def restore_file(ds: DataSource, path: str | os.PathLike) -> tuple[int, int]:
    """Restores a gzip JSON `data` entry (write_source_data) into a source on this machine, streaming it."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return restore_data(ds, read_data_entry(fh))


def restore_data(ds: DataSource, data: dict | None) -> tuple[int, int]:
    if not data:
        return 0, 0
    if ds.device_id:
        return restore_device_data(ds, data)
    if ds.kind == "sql":
        return restore_sql_data(ds, data), 0
    return 0, restore_mongo_data(ds, data)


# =============================================================================================
# import
# =============================================================================================


def _external_source(row: dict, **overrides: Any) -> DataSource:
    config = row.get("config")
    if not isinstance(config, dict):
        raise ApiError(400, "invalid_export", f"Data source {row.get('name')!r} has no connection config")
    ds = dict_to_model(DataSource, row, config_encrypted=encrypt_json(config), **overrides)
    ds.status = "unknown"
    ds.status_message = "Imported; not checked yet"
    ds.last_checked_at = None
    return ds


def _provision_with_data(
    db: Session,
    project: Project,
    row: dict,
    data: dict | None,
    provisioned: list[DataSource],
    *,
    data_source_id: str,
    keep_name: bool,
    warnings: list[str],
    totals: dict[str, int],
    device_id: str | None = None,
) -> DataSource | None:
    kind = row.get("kind")
    if kind not in ("sql", "nosql"):
        raise ApiError(400, "invalid_export", f"Unknown data source kind: {kind!r}")
    extra: dict[str, Any] = {"device_id": device_id} if device_id else {}
    try:
        ds = provisioning.provision_managed_source(
            db,
            project,
            kind,
            row["name"],
            database_name=row.get("database_name") if keep_name else None,
            data_source_id=data_source_id,
            **extra,
        )
    except ApiError as exc:
        if exc.code == "managed_mongodb_unavailable":
            warnings.append(
                f"Skipped managed MongoDB source '{row['name']}' of project '{project.name}': "
                "managed MongoDB is not available on this host"
            )
            return None
        raise
    provisioned.append(ds)
    if row.get("created_at"):
        ds.created_at = _parse_dt(row["created_at"])
    rows, docs = restore_data(ds, data)
    totals["rows"] += rows
    totals["documents"] += docs
    if warning := skipped_warning(row["name"], (data or {}).get("skipped")):
        warnings.append(warning)
    return ds


def _import_placement(
    db: Session, row: dict, project: Project, warnings: list[str], *, check_eligibility: bool
) -> str | None:
    """Device to restore a managed source on: its original device when known, (eligible) and online."""
    device_id = row.get("device_id")
    if not device_id or row.get("mode") != "managed":
        return None
    from app.services import devices

    device = db.get(Device, device_id)
    problem = None
    if device is None:
        problem = "is not attached to this installation"
    elif check_eligibility and not devices.device_can_host(db, device, project):
        problem = "can't host this project"
    elif device.status != "active" or not device_rpc.is_online(device_id):
        problem = "is not connected"
    if problem:
        warnings.append(
            f"The host device of data source '{row.get('name')}' (project '{project.name}') {problem}; "
            "its data was restored on the main server instead"
        )
        return None
    return device_id


def _merge_backup_policy(db: Session, row: dict, known_sources: set[str], known_devices: set[str]) -> None:
    if row.get("data_source_id") not in known_sources:
        return
    values = dict_to_model(BackupPolicy, row)
    if values.copy_to_device_id and values.copy_to_device_id not in known_devices:
        values.copy_to_device_id = None
    existing = db.get(BackupPolicy, row["data_source_id"])
    if existing is None:
        db.add(values)
        return
    for col in BackupPolicy.__table__.columns:
        if col.key != "data_source_id" and col.key in row:
            setattr(existing, col.key, getattr(values, col.key))


def _import_backup_keys(material: Any, warnings: list[str]) -> None:
    if material is None:
        return
    try:
        backup_crypto.import_key_material(material)
    except Exception:  # noqa: BLE001
        log.warning("backup key material could not be imported", exc_info=True)
        warnings.append("Backup key material could not be imported; backups copied elsewhere may be unreadable")


def _cleanup(db: Session, provisioned: list[DataSource]) -> None:
    for ds in provisioned:
        try:
            provisioning.drop_managed_source(db, ds)
        except Exception:  # noqa: BLE001
            log.exception("cleanup of provisioned source %s failed", ds.database_name)


def _fail(exc: Exception) -> ApiError:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, KeyError | TypeError | ValueError):
        return ApiError(400, "invalid_export", f"Malformed export: {exc}")
    msg = connections.redact(str(getattr(exc, "orig", None) or exc))
    return ApiError(500, "import_failed", f"Import failed: {msg}")


def import_instance(db: Session, payload: dict) -> dict:
    """Restores a whole instance into an empty installation. Commits on success."""
    provisioned: list[DataSource] = []
    warnings: list[str] = []
    totals = {"users": 0, "projects": 0, "data_sources": 0, "rows": 0, "documents": 0}
    data = payload.get("data") or {}
    try:
        for s in _list(payload, "instance_settings"):
            key, value, is_secret = s["key"], s.get("value"), bool(s.get("is_secret"))
            if key in DEVICE_LOCAL_SETTINGS:
                continue
            stored = encrypt_secret(str(value)) if is_secret else json.dumps(value)
            existing = db.get(InstanceSetting, key)
            if existing is None:
                db.add(InstanceSetting(key=key, value=stored, is_secret=is_secret))
            else:
                existing.value, existing.is_secret = stored, is_secret
        for u in _list(payload, "users"):
            db.add(dict_to_model(User, u))
            totals["users"] += 1
        db.flush()
        for i in _list(payload, "user_identities"):
            db.add(dict_to_model(UserIdentity, i))
        for d in _list(payload, "devices"):
            db.add(dict_to_model(Device, d))
        db.flush()
        projects: dict[str, Project] = {}
        for p in _list(payload, "projects"):
            project = dict_to_model(Project, p)
            db.add(project)
            projects[project.id] = project
            totals["projects"] += 1
        db.flush()
        known_devices = set(db.scalars(select(Device.id)))
        for g in _list(payload, "device_project_grants"):
            if g.get("device_id") in known_devices and g.get("project_id") in projects:
                db.add(dict_to_model(DeviceProjectGrant, g))
        for m in _list(payload, "project_members"):
            db.add(dict_to_model(ProjectMember, m))
        for inv in _list(payload, "project_invites"):
            db.add(dict_to_model(ProjectInvite, inv))
        for k in _list(payload, "api_keys"):
            db.add(dict_to_model(ApiKey, k, secret_encrypted=_api_key_secret(k)))
        db.flush()
        known_apps: set[str] = set()
        for a in _list(payload, "apps"):
            if a.get("project_id") in projects:
                app = _app_model(db, a)
                db.add(app)
                db.flush()
                known_apps.add(app.id)
        for row in _list(payload, "data_sources"):
            project = projects.get(row.get("project_id"))
            if project is None:
                continue
            if row.get("mode") == "managed":
                ds = _provision_with_data(
                    db,
                    project,
                    row,
                    data.get(row["id"]),
                    provisioned,
                    data_source_id=row["id"],
                    keep_name=True,
                    warnings=warnings,
                    totals=totals,
                    device_id=_import_placement(db, row, project, warnings, check_eligibility=False),
                )
                if ds is None:
                    continue
            else:
                db.add(_external_source(row, device_id=None))
            totals["data_sources"] += 1
        db.flush()
        known_sources = {row for row in db.scalars(select(DataSource.id))}
        for link in _list(payload, "schema_links"):
            if link.get("from_source_id") in known_sources and link.get("to_source_id") in known_sources:
                db.add(dict_to_model(SchemaLink, link))
        known_users = set(db.scalars(select(User.id)))
        known_queries = set()
        for q in _list(payload, "saved_queries"):
            if q.get("project_id") not in projects or q.get("owner_id") not in known_users:
                continue
            source_id = q.get("data_source_id")
            db.add(dict_to_model(SavedQuery, q, data_source_id=source_id if source_id in known_sources else None))
            known_queries.add(q.get("id"))
        for v in _list(payload, "saved_query_versions"):
            if v.get("saved_query_id") in known_queries:
                db.add(dict_to_model(SavedQueryVersion, v))
        for policy in _list(payload, "backup_policies"):
            _merge_backup_policy(db, policy, known_sources, known_devices)
        for domain in _list(payload, "domains"):
            if (domain.get("project_id") is None or domain.get("project_id") in projects) and (
                domain.get("app_id") is None or domain.get("app_id") in known_apps
            ):
                db.add(dict_to_model(Domain, domain))
        _import_backup_keys(payload.get("backup_keys"), warnings)
        db.commit()
    except Exception as exc:
        _cleanup(db, provisioned)
        db.rollback()
        raise _fail(exc) from exc
    summary = dict(totals)
    if warnings:
        summary["warnings"] = warnings
    return summary


def import_projects(db: Session, payload: dict, user: User) -> tuple[list[Project], dict]:
    """Recreates exported projects owned by `user` with fresh IDs. Commits on success."""
    provisioned: list[DataSource] = []
    warnings: list[str] = []
    totals = {"projects": 0, "data_sources": 0, "rows": 0, "documents": 0}
    skipped_members: list[str] = []
    skipped_api_keys = 0
    data = payload.get("data") or {}
    created: list[Project] = []
    try:
        project_map: dict[str, Project] = {}
        now = utcnow()
        for p in _list(payload, "projects"):
            project = Project(
                id=new_id(),
                slug=unique_slug(db, str(p.get("slug") or p.get("name") or "project")),
                name=str(p["name"])[:120],
                description=p.get("description"),
                owner_id=user.id,
                created_at=now,
                updated_at=now,
            )
            db.add(project)
            db.flush()
            db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
            project_map[p["id"]] = project
            created.append(project)
            totals["projects"] += 1
        db.flush()
        for m in _list(payload, "project_members"):
            if m.get("project_id") in project_map:
                email = m.get("email")
                if email and email.lower() != (user.email or "").lower() and email not in skipped_members:
                    skipped_members.append(email)
        key_map: dict[str, str] = {}
        for k in _list(payload, "api_keys"):
            project = project_map.get(k.get("project_id"))
            if project is None:
                continue
            if db.scalar(select(ApiKey.id).where(ApiKey.key_hash == k.get("key_hash"))):
                skipped_api_keys += 1
                continue
            key_map[k.get("id")] = new_id()
            db.add(
                dict_to_model(
                    ApiKey,
                    k,
                    id=key_map[k.get("id")],
                    project_id=project.id,
                    created_by_id=user.id,
                    secret_encrypted=_api_key_secret(k),
                )
            )
        db.flush()
        # App hostnames are not carried over: DNS and tunnel ingress belong to the source instance.
        for a in _list(payload, "apps"):
            project = project_map.get(a.get("project_id"))
            if project is None:
                continue
            db.add(
                _app_model(
                    db,
                    a,
                    id=new_id(),
                    project_id=project.id,
                    created_by_id=user.id,
                    api_key_id=key_map.get(a.get("api_key_id")),
                    github_connection_user_id=None,  # never someone else's GitHub connection
                )
            )
            db.flush()
        source_map: dict[str, str] = {}
        for row in _list(payload, "data_sources"):
            project = project_map.get(row.get("project_id"))
            if project is None:
                continue
            new_source_id = new_id()
            if row.get("mode") == "managed":
                ds = _provision_with_data(
                    db,
                    project,
                    row,
                    data.get(row["id"]),
                    provisioned,
                    data_source_id=new_source_id,
                    keep_name=False,
                    warnings=warnings,
                    totals=totals,
                    device_id=_import_placement(db, row, project, warnings, check_eligibility=True),
                )
                if ds is None:
                    continue
            else:
                db.add(_external_source(row, id=new_source_id, project_id=project.id, device_id=None))
            source_map[row["id"]] = new_source_id
            totals["data_sources"] += 1
        db.flush()
        for link in _list(payload, "schema_links"):
            project = project_map.get(link.get("project_id"))
            f, t = source_map.get(link.get("from_source_id")), source_map.get(link.get("to_source_id"))
            if project is None or not f or not t:
                continue
            db.add(
                dict_to_model(SchemaLink, link, id=new_id(), project_id=project.id, from_source_id=f, to_source_id=t)
            )
        query_map: dict[str, str] = {}
        for q in _list(payload, "saved_queries"):
            project = project_map.get(q.get("project_id"))
            if project is None:
                continue
            # The importer owns everything here (members are not carried over, see skipped_members).
            query_map[q.get("id")] = new_id()
            db.add(
                dict_to_model(
                    SavedQuery,
                    q,
                    id=query_map[q.get("id")],
                    project_id=project.id,
                    owner_id=user.id,
                    data_source_id=source_map.get(q.get("data_source_id")),
                )
            )
        for v in _list(payload, "saved_query_versions"):
            new_query_id = query_map.get(v.get("saved_query_id"))
            if new_query_id is not None:
                db.add(dict_to_model(SavedQueryVersion, v, id=new_id(), saved_query_id=new_query_id))
        db.commit()
    except Exception as exc:
        _cleanup(db, provisioned)
        db.rollback()
        raise _fail(exc) from exc
    summary: dict[str, Any] = dict(totals)
    summary["skipped_members"] = skipped_members
    summary["skipped_api_keys"] = skipped_api_keys
    if warnings:
        summary["warnings"] = warnings
    return created, summary


def iter_file(path: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
    try:
        with open(path, "rb") as fh:
            while chunk := fh.read(chunk_size):
                yield chunk
    finally:
        _unlink(path)


__all__ = [
    "build_export_file",
    "check_passphrase",
    "export_filename",
    "import_instance",
    "import_projects",
    "iter_file",
    "read_export_file",
    "save_upload",
]
