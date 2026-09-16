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
     "api_keys": [...], "data_sources": [... + decrypted "config", without config_encrypted],
     "schema_links": [...],
     "data": {<data_source_id>: {"kind": "sql", "engine", "database_name",
                                 "tables": [{name, create_sql, columns: [{name, type}], rows: [[...], ...]}]}
                              | {"kind": "nosql", "database_name",
                                 "collections": [{name, type, options, indexes: [...], documents: [...]}]}}}

Rows are arrays aligned with `columns` (binary -> {"$base64"}, decimals/dates -> strings); Mongo
options, indexes and documents are canonical Extended JSON. Only *managed* sources carry data.

Streaming & limits
------------------
- The plaintext JSON is written incrementally into a gzip temp file while rows / documents are read
  with server-side cursors, so exporting never holds a whole table or collection in Python objects.
- AES-GCM (``app.crypto``) is one-shot, so the *compressed* payload, its ciphertext and the base64 text
  are each held in memory once while the final file is produced (~3x the gzip size at peak).
- Import decrypts and decompresses in memory and parses the plaintext with ``json.loads``: peak memory
  is roughly the uncompressed payload size plus Python object overhead. Very large databases
  (multiple GB) should be moved with native dump tools instead.
- Views, triggers, stored routines and events of managed MariaDB databases are not exported; MongoDB
  views are. Generated (virtual/stored) SQL columns are recreated by their DDL, not copied.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import json
import logging
import os
import re
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import IO, Any

from bson import json_util
from cryptography.exceptions import InvalidTag
from sqlalchemy import DateTime, select
from sqlalchemy.orm import Session

from app import __version__
from app.crypto import decrypt_json, decrypt_with_passphrase, encrypt_json, encrypt_secret, encrypt_with_passphrase
from app.errors import ApiError
from app.models import (
    ApiKey,
    DataSource,
    InstanceSetting,
    Project,
    ProjectInvite,
    ProjectMember,
    SchemaLink,
    User,
    UserIdentity,
    new_id,
    utcnow,
)
from app.services import connections, ddl_export, provisioning
from app.services.data_browser import encode_value
from app.services.slugs import unique_slug

log = logging.getLogger(__name__)

FORMAT = "deployer-export"
VERSION = 1
MIN_PASSPHRASE = 12
MAX_UPLOAD_BYTES = 8 * 1024**3
BATCH = 1000
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
        from app.crypto import decrypt_secret

        value: Any = decrypt_secret(row.value)
    else:
        try:
            value = json.loads(row.value)
        except ValueError:
            value = row.value
    return {"key": row.key, "value": value, "is_secret": bool(row.is_secret)}


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


def _write_sql_data(w: _Writer, ds: DataSource) -> tuple[int, int]:
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
    finally:
        engine.dispose()
    return tables, rows_total


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


def write_payload(fh: IO[str], db: Session, *, scope: str, projects: list[Project], created_at: str) -> dict[str, int]:
    """Streams the plaintext payload JSON to `fh`. Returns counts."""
    w = _Writer(fh)
    project_ids = [p.id for p in projects]
    counts = {"users": 0, "projects": len(projects), "data_sources": 0, "rows": 0, "documents": 0}
    w.open("{")
    w.field("version", VERSION)
    w.field("scope", scope)
    w.field("created_at", created_at)

    if scope == "instance":
        w.field("instance_settings", [_setting_out(s) for s in db.scalars(select(InstanceSetting))])
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

    w.field("api_keys", [model_to_dict(k) for k in by_project(ApiKey)])
    sources: list[DataSource] = by_project(DataSource)
    counts["data_sources"] = len(sources)
    w.field("data_sources", [_source_out(ds) for ds in sources])
    w.field("schema_links", [model_to_dict(link) for link in by_project(SchemaLink)])

    w.open_field("data", "{")
    for ds in sources:
        if ds.mode != "managed":
            continue
        w._sep()
        w.fh.write(json.dumps(ds.id) + ":")
        w.open("{")
        try:
            if ds.kind == "sql":
                _, rows = _write_sql_data(w, ds)
                counts["rows"] += rows
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
        with open(gz_path, "rb") as fh:
            compressed = fh.read()
        header, payload_b64 = encrypt_with_passphrase(compressed, passphrase)
        del compressed
        with open(out_path, "w", encoding="utf-8") as out:
            out.write("{")
            out.write(f'"format":{json.dumps(FORMAT)},"version":{VERSION},"scope":{json.dumps(scope)},')
            out.write(f'"created_at":{json.dumps(created_at)},"app_version":{json.dumps(__version__)},')
            out.write(f'"encryption":{json.dumps(header)},"payload":"')
            for i in range(0, len(payload_b64), 1 << 20):
                out.write(payload_b64[i : i + (1 << 20)])
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


def save_upload(src: IO[bytes], max_bytes: int = MAX_UPLOAD_BYTES) -> str:
    """Copies an uploaded file to a temp file in chunks, enforcing a size limit."""
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
                    raise ApiError(413, "file_too_large", "The export file is too large")
                out.write(chunk)
    except BaseException:
        _unlink(path)
        raise
    return path


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
        plaintext = gzip.decompress(compressed)
        del compressed
        payload = json.loads(plaintext)
    except (OSError, EOFError, ValueError) as exc:
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


def restore_sql_data(ds: DataSource, data: dict) -> int:
    config = decrypt_json(ds.config_encrypted)
    engine = connections.build_sql_engine(ds.engine, config, pooled=False)

    def q(name: str) -> str:
        return engine.dialect.identifier_preparer.quote_identifier(name).replace("%", "%%")

    rows_total = 0
    tables = _list(data, "tables")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            for t in tables:
                create_sql = t.get("create_sql") or ""
                if not isinstance(create_sql, str) or not _CREATE_TABLE_RE.match(create_sql):
                    raise ApiError(400, "invalid_export", f"Invalid table definition for {t.get('name')!r}")
                conn.exec_driver_sql(create_sql.replace("%", "%%"))
            conn.commit()
            for t in tables:
                columns = [c["name"] for c in t.get("columns") or []]
                rows = t.get("rows") or []
                if not columns or not rows:
                    continue
                sql = (
                    f"INSERT INTO {q(t['name'])} ("
                    + ", ".join(q(c) for c in columns)
                    + ") VALUES ("
                    + ", ".join(["%s"] * len(columns))
                    + ")"
                )
                for i in range(0, len(rows), BATCH):
                    batch = [tuple(_decode_cell(v) for v in row) for row in rows[i : i + BATCH]]
                    conn.exec_driver_sql(sql, batch)
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
        collections = _list(data, "collections")
        ordered = sorted(collections, key=lambda c: c.get("type") == "view")
        for coll in ordered:
            name = coll["name"]
            options = _from_canonical(coll.get("options") or {})
            database.create_collection(name, **options)
            if coll.get("type") == "view":
                continue
            docs = coll.get("documents") or []
            target = database[name]
            for i in range(0, len(docs), BATCH):
                batch = _from_canonical(docs[i : i + BATCH])
                if batch:
                    target.insert_many(batch, ordered=False, bypass_document_validation=True)
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


def restore_data(ds: DataSource, data: dict | None) -> tuple[int, int]:
    if not data:
        return 0, 0
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
) -> DataSource | None:
    kind = row.get("kind")
    if kind not in ("sql", "nosql"):
        raise ApiError(400, "invalid_export", f"Unknown data source kind: {kind!r}")
    try:
        ds = provisioning.provision_managed_source(
            db,
            project,
            kind,
            row["name"],
            database_name=row.get("database_name") if keep_name else None,
            data_source_id=data_source_id,
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
    return ds


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
        projects: dict[str, Project] = {}
        for p in _list(payload, "projects"):
            project = dict_to_model(Project, p)
            db.add(project)
            projects[project.id] = project
            totals["projects"] += 1
        db.flush()
        for m in _list(payload, "project_members"):
            db.add(dict_to_model(ProjectMember, m))
        for inv in _list(payload, "project_invites"):
            db.add(dict_to_model(ProjectInvite, inv))
        for k in _list(payload, "api_keys"):
            db.add(dict_to_model(ApiKey, k))
        db.flush()
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
                )
                if ds is None:
                    continue
            else:
                db.add(_external_source(row))
            totals["data_sources"] += 1
        db.flush()
        known_sources = {row for row in db.scalars(select(DataSource.id))}
        for link in _list(payload, "schema_links"):
            if link.get("from_source_id") in known_sources and link.get("to_source_id") in known_sources:
                db.add(dict_to_model(SchemaLink, link))
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
        for k in _list(payload, "api_keys"):
            project = project_map.get(k.get("project_id"))
            if project is None:
                continue
            if db.scalar(select(ApiKey.id).where(ApiKey.key_hash == k.get("key_hash"))):
                skipped_api_keys += 1
                continue
            db.add(dict_to_model(ApiKey, k, id=new_id(), project_id=project.id, created_by_id=user.id))
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
                )
                if ds is None:
                    continue
            else:
                db.add(_external_source(row, id=new_source_id, project_id=project.id))
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
