"""Live two-way sync between a managed database on the main server and its copy on a co-host device
(docs/COHOSTING.md "Database sync").

Every 2 s the worker's scheduler leader runs `sync_round(replica_id)` for each `syncing` replica:

1. read the changes made on each side since its position (MariaDB: row binlog through
   `python-mysql-replication`, resumed by GTID; MongoDB: change streams, resumed by token) —
   the device side through the `sync.*_changes` RPCs,
2. apply the primary's changes to the device, then the device's changes to the primary
   (`sync.*_apply` on the device), row by row, each checked against the target's current version,
3. advance each side's position after its changes were applied.

Merge model (like Git): a change is applied only when the target still holds the version the change
started from (SQL: the binlog before-image; MongoDB: the last synced version kept in `sync_versions`,
since MongoDB 5.0 has no pre-images). Otherwise the key is in **conflict**: nothing is applied to it on
either side, both versions are stored in `sync_conflicts`, later changes to that key update the open
conflict, and every other key keeps syncing. Re-applying an already applied change is a no-op (the
target already holds that change's - or a later change's - after-version), so a crash between apply
and position update is harmless.

No echo loops: on the device, applied changes are written with `sql_log_bin = 0`; on the main server
they are written with the device's origin `server_id` (`SET SESSION server_id`), and the main server's
reader for that device skips transactions from it (other copies of the same source still receive them).
MongoDB writes are recognised when they come back by their version hash in `sync_versions`.

Everything that talks to a database takes the database name explicitly and touches nothing else;
the device only runs these functions for databases it hosts (device_host `m_sync_*`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import ApiError
from app.models import DataSource, SourceReplica, SyncConflict, SyncVersion, utcnow
from app.services import connections, device_rpc, provisioning

log = logging.getLogger(__name__)

# MariaDB ids: every server holding a replicated database gets auto_increment_increment = STEP and its
# own offset (main server 1, co-host devices 2..STEP), so inserts on different copies never pick the
# same id. Server-wide (MariaDB has no per-table setting); set only on servers that hold copies.
AUTO_INCREMENT_STEP = 10
PRIMARY_ID_OFFSET = 1
ORIGIN_SERVER_ID_BASE = 1_000_000  # origin server_id of changes applied on the main server for a device
MIN_BINLOG_EXPIRE_SECONDS = 7 * 86400
BATCH_LIMIT = 1000
MAX_BATCH_BYTES = 4 * 1024 * 1024  # stays well under device_rpc.MAX_MESSAGE_BYTES
ROUND_EVERY_S = 2.0
MAX_BACKOFF_S = 300.0
VERSION_KEEP_DAYS = 7
ABSENT = "-"  # hash of "no row"

# =============================================================================================
# values: JSON-safe encoding (RPC, platform DB) and version hashes
# =============================================================================================


def enc(value: Any) -> Any:
    """SQL value -> JSON-safe value (tagged for types JSON can't carry)."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return {"$dec": str(value)}
    if isinstance(value, datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, dtime):
        return {"$time": value.isoformat()}
    if isinstance(value, timedelta):
        return {"$td": value.total_seconds()}
    if isinstance(value, bytes | bytearray | memoryview):
        return {"$b64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, set | frozenset):  # SET columns (binlog) -> MariaDB's own text form
        return ",".join(sorted(str(v) for v in value))
    if isinstance(value, dict | list):
        return {"$json": json.dumps(value, sort_keys=True, default=str)}
    return str(value)


def dec(value: Any) -> Any:
    if not isinstance(value, dict) or len(value) != 1:
        return value
    ((tag, raw),) = value.items()
    try:
        if tag == "$dec":
            return Decimal(raw)
        if tag == "$dt":
            return datetime.fromisoformat(raw)
        if tag == "$date":
            return date.fromisoformat(raw)
        if tag == "$time":
            return dtime.fromisoformat(raw)
        if tag == "$td":
            return timedelta(seconds=float(raw))
        if tag == "$b64":
            return base64.b64decode(raw)
        if tag == "$json":
            return raw
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ApiError(422, "validation_error", f"Invalid {tag} value") from exc
    return value


def enc_row(row: dict | None) -> dict | None:
    return None if row is None else {str(k): enc(v) for k, v in row.items()}


def _norm(value: Any) -> Any:
    """Canonical form for comparing versions read from a binlog and from a SELECT."""
    if isinstance(value, float):
        return float(f"{value:.6g}")  # FLOAT columns differ in the last digits between the two
    if isinstance(value, dict):
        if set(value) == {"$b64"}:
            raw = base64.b64decode(value["$b64"])
            try:
                return raw.decode("utf-8")  # TEXT may arrive as bytes from one side
            except UnicodeDecodeError:
                return value
        if set(value) == {"$dec"}:
            return {"$dec": str(Decimal(value["$dec"]).normalize())}
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def row_hash(row: dict | None) -> str:
    if row is None:
        return ABSENT
    raw = json.dumps(_norm(row), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def key_hash(key: dict) -> str:
    return row_hash(key)


def _project(row: dict | None, cols: list[str] | None) -> dict | None:
    if row is None or cols is None:
        return row
    return {c: row.get(c) for c in cols}


def same(current: dict | None, version: dict | None, *, sql: bool) -> bool:
    """SQL rows are compared on the version's columns (a copy may have extra columns)."""
    if version is None or current is None:
        return version is None and current is None
    return row_hash(_project(current, list(version) if sql else None)) == row_hash(version)


# =============================================================================================
# applying changes (shared by the main server and the device)
# =============================================================================================


class SchemaMismatch(ApiError):
    def __init__(self, message: str):
        super().__init__(409, "schema_mismatch", message)


class WriteRejected(Exception):
    """The target refused the write (unique / foreign key violation): the key becomes a conflict."""


class Store(Protocol):
    def get(self, table: str, key: dict) -> dict | None: ...
    def put(self, table: str, key: dict, row: dict | None, exists: bool) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def apply_changes(store: Store, changes: list[dict], kind: str) -> list[dict]:
    """Applies changes in order; returns one outcome per change:
    `{"result": "applied"|"skipped"|"conflict", "current": <target version>, "reason"?}`.

    Change: `{table, key, op, before, after, ts, force?, base_hash?, concurrent?}`. A change applies
    when the target holds its starting version (SQL `before`; MongoDB `base_hash`, or - without a
    known base - when the other side did not change the key in this round). `force` (conflict
    resolution, history restore) writes unconditionally. A key that conflicted stays in conflict for
    the rest of the batch.
    """
    sql = kind == "sql"
    keys = [(c["table"], key_hash(c["key"])) for c in changes]
    after_hashes = [row_hash(c.get("after")) for c in changes]
    last_index = {(k, h): i for i, (k, h) in enumerate(zip(keys, after_hashes, strict=True))}
    conflicted: set[tuple[str, str]] = set()
    outcomes: list[dict] = []
    for i, change in enumerate(changes):
        k, table, key = keys[i], change["table"], change["key"]
        after, before = change.get("after"), change.get("before")
        current = None
        try:
            current = store.get(table, key)
            if k in conflicted:
                result = "conflict"
            elif change.get("force"):
                store.put(table, key, after, current is not None)
                result = "applied"
            else:
                cols = list(after or before or {}) if sql else None
                cur_hash = ABSENT if current is None else row_hash(_project(current, cols))
                if last_index.get((k, cur_hash), -1) >= i:
                    result = "skipped"  # already holds this (or a later) version of the key
                else:
                    if sql:
                        ok = same(current, before, sql=True)
                    elif change.get("base_hash") is not None:
                        ok = row_hash(current) == change["base_hash"]
                    else:
                        ok = not change.get("concurrent")
                    if ok:
                        store.put(table, key, after, current is not None)
                        result = "applied"
                    else:
                        result = "conflict"
            store.commit()
            outcome = {"result": result, "current": current}
        except WriteRejected as exc:
            store.rollback()
            outcome = {"result": "conflict", "current": current, "reason": str(exc)[:500]}
        except Exception:
            store.rollback()
            raise
        if outcome["result"] == "conflict":
            conflicted.add(k)
        outcomes.append(outcome)
    return outcomes


def _q(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


class SqlStore:
    """Root connection to one database; one short transaction per change (row locked while checked)."""

    def __init__(self, database: str, *, log_bin: bool, origin_server_id: int | None = None):
        import pymysql

        s = get_settings()
        provisioning._check(provisioning.DB_NAME_RE, database, "database name")
        self.database = database
        self._integrity = pymysql.err.IntegrityError
        self.conn = pymysql.connect(
            host=s.mariadb_host,
            port=int(s.mariadb_port),
            user="root",
            password=s.mariadb_root_password or "",
            database=database,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=connections.CONNECT_TIMEOUT_S,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self._columns: dict[str, dict[str, bool]] = {}
        with self.conn.cursor() as cur:
            if not log_bin:
                cur.execute("SET SESSION sql_log_bin = 0")
            elif origin_server_id:
                try:
                    cur.execute(f"SET SESSION server_id = {int(origin_server_id)}")
                except pymysql.err.MySQLError:
                    # ponytail: a server that refuses a session server_id falls back to no binlog
                    # (other copies of this source then miss these changes until a re-copy).
                    log.warning("session server_id not supported; applying without binlog")
                    cur.execute("SET SESSION sql_log_bin = 0")

    def columns(self, table: str) -> dict[str, bool]:
        """{column: writable} of a table in this database; SchemaMismatch if it doesn't exist."""
        if table not in self._columns:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT COLUMN_NAME, EXTRA FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                    (self.database, table),
                )
                rows = cur.fetchall()
            if not rows:
                raise SchemaMismatch(f"Table {table!r} does not exist on this copy")
            self._columns[table] = {r["COLUMN_NAME"]: "GENERATED" not in (r["EXTRA"] or "").upper() for r in rows}
        return self._columns[table]

    def _check(self, table: str, names) -> dict[str, bool]:
        cols = self.columns(table)
        missing = [n for n in names if n not in cols]
        if missing:
            raise SchemaMismatch(f"Column(s) {', '.join(map(repr, missing))} of {table!r} are missing on this copy")
        return cols

    def _where(self, table: str, key: dict) -> tuple[str, list]:
        self._check(table, key)
        return " AND ".join(f"{_q(c)} = %s" for c in key), [dec(v) for v in key.values()]

    def get(self, table: str, key: dict) -> dict | None:
        where, args = self._where(table, key)
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {_q(table)} WHERE {where} FOR UPDATE", args)
            row = cur.fetchone()
        return enc_row(row)

    def put(self, table: str, key: dict, row: dict | None, exists: bool) -> None:
        where, args = self._where(table, key)
        try:
            with self.conn.cursor() as cur:
                if row is None:
                    cur.execute(f"DELETE FROM {_q(table)} WHERE {where}", args)
                    return
                cols = self._check(table, row)
                names = [n for n in row if cols[n]]
                values = [dec(row[n]) for n in names]
                if exists:
                    sets = [n for n in names if n not in key] or names
                    cur.execute(
                        f"UPDATE {_q(table)} SET {', '.join(f'{_q(n)} = %s' for n in sets)} WHERE {where}",
                        [dec(row[n]) for n in sets] + args,
                    )
                else:
                    marks = ", ".join(["%s"] * len(names))
                    cur.execute(f"INSERT INTO {_q(table)} ({', '.join(map(_q, names))}) VALUES ({marks})", values)
        except self._integrity as exc:
            raise WriteRejected(connections.redact(str(exc))) from exc

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass


def _valid_collection(name: Any) -> str:
    if (
        not isinstance(name, str)
        or not 0 < len(name) <= 120
        or "$" in name
        or "\0" in name
        or name.startswith("system.")
    ):
        raise ApiError(422, "validation_error", "Invalid collection name")
    return name


def ext(value: Any) -> Any:
    """BSON value/document -> canonical extended JSON (plain JSON types)."""
    from bson import json_util

    return json.loads(json_util.dumps(value, json_options=json_util.CANONICAL_JSON_OPTIONS))


def unext(value: Any) -> Any:
    from bson import json_util

    return json_util.loads(json.dumps(value), json_options=json_util.CANONICAL_JSON_OPTIONS)


class MongoStore:
    def __init__(self, database: str):
        provisioning._check(provisioning.DB_NAME_RE, database, "database name")
        self.db = provisioning.mongo_root_client()[database]

    def get(self, table: str, key: dict) -> dict | None:
        doc = self.db[_valid_collection(table)].find_one({"_id": unext(key["_id"])})
        return None if doc is None else ext(doc)

    def put(self, table: str, key: dict, row: dict | None, exists: bool) -> None:
        from pymongo.errors import DuplicateKeyError

        coll = self.db[_valid_collection(table)]
        _id = unext(key["_id"])
        try:
            if row is None:
                coll.delete_one({"_id": _id})
            else:
                doc = unext(row)
                doc["_id"] = _id
                coll.replace_one({"_id": _id}, doc, upsert=True)
        except DuplicateKeyError as exc:
            raise WriteRejected(connections.redact(str(exc))) from exc

    def commit(self) -> None:  # ponytail: no multi-document transaction; check-then-write has a tiny race
        return None

    def rollback(self) -> None:
        return None


def check_changes(changes: Any, kind: str) -> list[dict]:
    """Validates the shape of changes received over RPC (values are bound, names are checked later)."""
    if not isinstance(changes, list) or len(changes) > 5 * BATCH_LIMIT:
        raise ApiError(422, "validation_error", "changes must be a list")
    for c in changes:
        if not isinstance(c, dict) or not isinstance(c.get("table"), str) or not isinstance(c.get("key"), dict):
            raise ApiError(422, "validation_error", "Malformed change")
        if not c["key"] or (kind == "nosql" and set(c["key"]) != {"_id"}):
            raise ApiError(422, "validation_error", "Malformed change key")
        for part in ("before", "after"):
            if c.get(part) is not None and not isinstance(c[part], dict):
                raise ApiError(422, "validation_error", "Malformed change")
    return changes


def apply_local(
    kind: str, database: str, changes: list[dict], *, log_bin: bool, origin_server_id: int | None = None
) -> list[dict]:
    changes = check_changes(changes, kind)
    if not changes:
        return []
    if kind == "sql":
        store = SqlStore(database, log_bin=log_bin, origin_server_id=origin_server_id)
        try:
            return apply_changes(store, changes, "sql")
        finally:
            store.close()
    return apply_changes(MongoStore(database), changes, "nosql")


# =============================================================================================
# server settings & positions
# =============================================================================================


def ensure_mariadb_settings(*, offset: int | None = None) -> None:
    """Binlog prerequisites (ROW format with full images and column metadata, >= 7 days retention)
    and, with `offset`, this server's auto_increment step/offset. Re-asserted every sync round so a
    MariaDB restart (which resets runtime settings) is repaired within seconds."""
    with provisioning.mariadb_root_engine().connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT @@log_bin, @@binlog_format, @@binlog_row_image, @@binlog_row_metadata, "
            "@@binlog_expire_logs_seconds, @@auto_increment_increment, @@auto_increment_offset"
        ).first()
        if not row[0] or str(row[1]).upper() != "ROW":
            raise ApiError(409, "binlog_required", "MariaDB must run with a ROW binary log for co-hosting")
        if str(row[2]).upper() != "FULL":
            conn.exec_driver_sql("SET GLOBAL binlog_row_image = 'FULL'")
        if str(row[3]).upper() != "FULL":
            conn.exec_driver_sql("SET GLOBAL binlog_row_metadata = 'FULL'")
        if 0 < int(row[4] or 0) < MIN_BINLOG_EXPIRE_SECONDS:
            conn.exec_driver_sql(f"SET GLOBAL binlog_expire_logs_seconds = {MIN_BINLOG_EXPIRE_SECONDS}")
        if offset is not None and (int(row[5]), int(row[6])) != (AUTO_INCREMENT_STEP, int(offset)):
            if not 1 <= int(offset) <= AUTO_INCREMENT_STEP:
                raise ApiError(422, "validation_error", "Invalid auto_increment offset")
            conn.exec_driver_sql(f"SET GLOBAL auto_increment_increment = {AUTO_INCREMENT_STEP}")
            conn.exec_driver_sql(f"SET GLOBAL auto_increment_offset = {int(offset)}")


def local_position(kind: str, database: str) -> dict:
    """The current end of this server's change history (taken before a dump / after a restore)."""
    if kind == "sql":
        with provisioning.mariadb_root_engine().connect() as conn:
            return {"gtid": str(conn.exec_driver_sql("SELECT @@gtid_binlog_pos").scalar() or "")}
    client = provisioning.mongo_root_client()
    with client[database].watch(max_await_time_ms=50) as stream:
        if stream.resume_token is not None:
            return {"token": _dumps_token(stream.resume_token)}
    from app.services.backup_engine import _latest_oplog_ts, ts_list

    return {"ts": ts_list(_latest_oplog_ts(client))}


def _dumps_token(token: Any) -> str:
    from bson import json_util

    return json_util.dumps(token, json_options=json_util.CANONICAL_JSON_OPTIONS)


# =============================================================================================
# reading changes
# =============================================================================================


def _parse_gtids(value: str | None) -> dict[int, str]:
    out: dict[int, str] = {}
    for part in filter(None, (p.strip() for p in (value or "").split(","))):
        domain, _, _ = part.partition("-")
        out[int(domain)] = part
    return out


def _primary_key(database: str, table: str) -> tuple[list[str], list[str]]:
    """(primary key columns, all columns in ordinal order) from information_schema."""
    with provisioning.mariadb_root_engine().connect() as conn:
        pk = [
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = %s "
                "AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION",
                (database, table),
            )
        ]
        cols = [
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                "ORDER BY ORDINAL_POSITION",
                (database, table),
            )
        ]
    return pk, cols


def _named(values: dict, cols: list[str]) -> dict:
    """Column names are in the binlog with binlog_row_metadata=FULL; events logged without it carry
    UNKNOWN_COL<i> placeholders, mapped here by position."""
    out = {}
    for name, value in values.items():
        if name.startswith("UNKNOWN_COL"):
            idx = int(name[len("UNKNOWN_COL") :])
            name = cols[idx] if idx < len(cols) else name
        out[name] = value
    return out


def row_changes(table: str, pk: list[str], before: dict | None, after: dict | None, ts: int) -> list[dict]:
    """One binlog row image pair -> change dicts (a primary key update becomes delete + insert)."""
    before, after = enc_row(before), enc_row(after)
    kb = {c: before.get(c) for c in pk} if before is not None else None
    ka = {c: after.get(c) for c in pk} if after is not None else None
    if kb is not None and ka is not None and key_hash(kb) != key_hash(ka):
        return [
            {"table": table, "key": kb, "op": "delete", "before": before, "after": None, "ts": ts},
            {"table": table, "key": ka, "op": "insert", "before": None, "after": after, "ts": ts},
        ]
    op = "insert" if before is None else "delete" if after is None else "update"
    return [{"table": table, "key": kb or ka, "op": op, "before": before, "after": after, "ts": ts}]


def read_sql_changes(
    database: str, since: dict | None, limit: int = BATCH_LIMIT, *, skip_server_id: int | None = None
) -> dict:
    """Row changes of `database` after GTID position `since`, whole transactions only.

    Returns `{changes, position, skipped_tables, more}`. Transactions logged with `skip_server_id`
    (changes this sync applied for that device) are passed over. Tables without a primary key are
    not synced (`skipped_tables`).
    """
    import pymysql
    from pymysqlreplication import BinLogStreamReader
    from pymysqlreplication.event import MariadbGtidEvent
    from pymysqlreplication.row_event import DeleteRowsEvent, UpdateRowsEvent, WriteRowsEvent

    provisioning._check(provisioning.DB_NAME_RE, database, "database name")
    s = get_settings()
    gtids = _parse_gtids((since or {}).get("gtid"))
    changes: list[dict] = []
    skipped: set[str] = set()
    tables: dict[str, tuple[list[str], list[str]]] = {}
    size, more, skip_txn = 0, False, False
    stream = BinLogStreamReader(
        connection_settings={
            "host": s.mariadb_host,
            "port": int(s.mariadb_port),
            "user": "root",
            "passwd": s.mariadb_root_password or "",
        },
        server_id=100_000 + secrets.randbelow(2**30),  # unique per reader connection
        blocking=False,
        is_mariadb=True,
        auto_position=",".join(gtids[d] for d in sorted(gtids)),
        only_schemas=[database],
        only_events=[MariadbGtidEvent, WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent],
        enable_logging=False,
    )
    try:
        for event in stream:
            if isinstance(event, MariadbGtidEvent):
                if len(changes) >= limit or size >= MAX_BATCH_BYTES:
                    more = True
                    break
                gtids[event.domain_id] = event.gtid
                skip_txn = skip_server_id is not None and event.server_id == skip_server_id
                continue
            if skip_txn or event.schema != database:
                continue
            if event.table not in tables:
                tables[event.table] = _primary_key(database, event.table)
            pk, cols = tables[event.table]
            if not pk:
                skipped.add(event.table)
                continue
            for row in event.rows:
                if isinstance(event, WriteRowsEvent):
                    before, after = None, _named(row["values"], cols)
                elif isinstance(event, DeleteRowsEvent):
                    before, after = _named(row["values"], cols), None
                else:
                    before, after = _named(row["before_values"], cols), _named(row["after_values"], cols)
                for change in row_changes(event.table, pk, before, after, int(event.timestamp)):
                    size += len(json.dumps(change, default=str))
                    changes.append(change)
    except pymysql.err.OperationalError as exc:
        if exc.args and exc.args[0] == 1236:
            raise ApiError(
                409, "resync_required", "The change history needed to continue was purged; re-copy this database"
            ) from exc
        raise ApiError(503, "database_unavailable", f"Could not read the binary log: {_redact(exc)}") from exc
    finally:
        stream.close()
    return {
        "changes": changes,
        "position": {"gtid": ",".join(gtids[d] for d in sorted(gtids))},
        "skipped_tables": sorted(skipped),
        "more": more,
    }


def _mongo_change(event: dict) -> dict | None:
    op = event.get("operationType")
    if op not in ("insert", "update", "replace", "delete"):
        return None  # drop / rename / invalidate ...: not data
    coll = (event.get("ns") or {}).get("coll") or ""
    if not coll or coll.startswith("system."):
        return None
    after = None
    if op != "delete":
        doc = event.get("fullDocument")
        if doc is None:
            return None  # deleted since; its delete event follows
        after = ext(doc)
    cluster_time = event.get("clusterTime")
    return {
        "table": coll,
        "key": {"_id": ext(event["documentKey"]["_id"])},
        "op": {"insert": "insert", "delete": "delete"}.get(op, "update"),
        "before": None,
        "after": after,
        "ts": int(cluster_time.time) if cluster_time is not None else int(time.time()),
    }


def read_mongo_changes(database: str, since: dict | None, limit: int = BATCH_LIMIT) -> dict:
    """Document changes of `database` after resume token / operation time `since` (change stream)."""
    from bson import Timestamp, json_util
    from pymongo.errors import OperationFailure, PyMongoError

    provisioning._check(provisioning.DB_NAME_RE, database, "database name")
    kwargs: dict[str, Any] = {"full_document": "updateLookup", "max_await_time_ms": 50}
    since = since or {}
    if since.get("token"):
        kwargs["resume_after"] = json_util.loads(since["token"])
    elif since.get("ts"):
        kwargs["start_at_operation_time"] = Timestamp(*since["ts"])
    changes: list[dict] = []
    size, more, position = 0, False, since
    try:
        with provisioning.mongo_root_client()[database].watch(**kwargs) as stream:
            while True:
                if len(changes) >= limit or size >= MAX_BATCH_BYTES:
                    more = True
                    break
                event = stream.try_next()
                if event is None:
                    break
                change = _mongo_change(event)
                if change is not None:
                    size += len(json.dumps(change))
                    changes.append(change)
            if stream.resume_token is not None:
                position = {"token": _dumps_token(stream.resume_token)}
    except OperationFailure as exc:
        if exc.code in (280, 286):  # ChangeStreamFatalError / ChangeStreamHistoryLost
            raise ApiError(
                409, "resync_required", "The change history needed to continue was purged; re-copy this database"
            ) from exc
        raise ApiError(503, "database_unavailable", f"Could not read the change stream: {_redact(exc)}") from exc
    except PyMongoError as exc:
        raise ApiError(503, "database_unavailable", f"Could not read the change stream: {_redact(exc)}") from exc
    return {"changes": changes, "position": position, "skipped_tables": [], "more": more}


def _redact(exc: BaseException) -> str:
    s = get_settings()
    return connections.redact(str(exc), [s.mariadb_root_password, s.mongo_root_password])


# =============================================================================================
# the two sides of a replica
# =============================================================================================


class Side(Protocol):
    def changes(self, since: dict | None, limit: int) -> dict: ...
    def apply(self, changes: list[dict]) -> list[dict]: ...


def origin_server_id(id_offset: int | None) -> int:
    return ORIGIN_SERVER_ID_BASE + int(id_offset or 2)


class PrimarySide:
    """The main server's database (this process)."""

    def __init__(self, kind: str, database: str, origin: int):
        self.kind, self.database, self.origin = kind, database, origin

    def changes(self, since: dict | None, limit: int) -> dict:
        if self.kind == "sql":
            ensure_mariadb_settings(offset=PRIMARY_ID_OFFSET)
            return read_sql_changes(self.database, since, limit, skip_server_id=self.origin)
        return read_mongo_changes(self.database, since, limit)

    def apply(self, changes: list[dict]) -> list[dict]:
        return apply_local(self.kind, self.database, changes, log_bin=True, origin_server_id=self.origin)


class DeviceSide:
    """The co-host device's copy, over the control channel (device_host `m_sync_*`)."""

    def __init__(self, device_id: str, kind: str, database: str, id_offset: int | None):
        self.device_id, self.kind, self.database, self.id_offset = device_id, kind, database, id_offset
        self.prefix = "sync.sql" if kind == "sql" else "sync.mongo"

    def changes(self, since: dict | None, limit: int) -> dict:
        params: dict[str, Any] = {"database_name": self.database, "since": since, "limit": limit}
        if self.kind == "sql" and self.id_offset:
            params["auto_increment"] = {"increment": AUTO_INCREMENT_STEP, "offset": self.id_offset}
        out = device_rpc.call(self.device_id, f"{self.prefix}_changes", params, timeout=60)
        if not isinstance(out, dict) or not isinstance(out.get("changes"), list):
            raise ApiError(502, "device_error", "Malformed sync reply from the device")
        # Only the fields a reader produces: a device can't send `force` and skip conflict detection.
        fields = ("table", "key", "op", "before", "after", "ts")
        changes = [{f: c.get(f) for f in fields} for c in check_changes(out["changes"], self.kind)]
        skipped = [str(t)[:128] for t in out.get("skipped_tables") or [] if isinstance(t, str)]
        return {**out, "changes": changes, "skipped_tables": skipped[:100]}

    def apply(self, changes: list[dict]) -> list[dict]:
        out = device_rpc.call(
            self.device_id, f"{self.prefix}_apply", {"database_name": self.database, "changes": changes}, timeout=120
        )
        outcomes = out.get("outcomes") if isinstance(out, dict) else None
        if not isinstance(outcomes, list) or len(outcomes) != len(changes):
            raise ApiError(502, "device_error", "Malformed sync reply from the device")
        return outcomes


def sides_for(replica: SourceReplica, ds: DataSource) -> tuple[Side, Side]:
    """(main server side, device side) of a replica. Tests replace this."""
    return (
        PrimarySide(ds.kind, ds.database_name, origin_server_id(replica.id_offset)),
        DeviceSide(replica.device_id, ds.kind, ds.database_name, replica.id_offset),
    )


# =============================================================================================
# one sync round
# =============================================================================================


def _dt(ts: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(ts), UTC).replace(tzinfo=None) if ts is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def latest_versions(session: Session, replica_id: str, keys: set[tuple[str, str]]) -> dict:
    """Newest `SyncVersion` per (table, key_hash)."""
    out: dict[tuple[str, str], SyncVersion] = {}
    hashes = sorted({h for _, h in keys})
    for i in range(0, len(hashes), 500):
        rows = session.scalars(
            select(SyncVersion)
            .where(SyncVersion.replica_id == replica_id, SyncVersion.key_hash.in_(hashes[i : i + 500]))
            .order_by(SyncVersion.id)
        )
        for row in rows:
            if (row.table_name, row.key_hash) in keys:
                out[(row.table_name, row.key_hash)] = row
    return out


def add_version(
    session: Session,
    replica_id: str,
    table: str,
    key: dict,
    value: dict | None,
    origin: str,
    user_id: str | None = None,
) -> SyncVersion:
    row = SyncVersion(
        replica_id=replica_id,
        table_name=table,
        key_json=key,
        key_hash=key_hash(key),
        version_hash=row_hash(value),
        json=value,
        origin=origin,
        user_id=user_id,
        synced_at=utcnow(),
    )
    session.add(row)
    return row


class _Round:
    def __init__(self, session: Session, replica: SourceReplica, kind: str, batches: dict[str, list[dict]]):
        self.session, self.replica, self.kind, self.batches = session, replica, kind, batches
        self.open = {
            (c.table_name, c.key_hash): c
            for c in session.scalars(
                select(SyncConflict).where(SyncConflict.replica_id == replica.id, SyncConflict.status == "open")
            )
        }
        keys = {(c["table"], key_hash(c["key"])) for batch in batches.values() for c in batch}
        self.latest = latest_versions(session, replica.id, keys) if keys else {}
        self.stats = {"applied": 0, "conflicts": 0}

    def _last_change(self, side: str, k: tuple[str, str]) -> dict | None:
        found = None
        for c in self.batches[side]:
            if (c["table"], key_hash(c["key"])) == k:
                found = c
        return found

    def _merge(self, conflict: SyncConflict, side: str, change: dict) -> None:
        setattr(conflict, f"{side}_json", change.get("after"))
        setattr(conflict, f"op_{side}", change.get("op"))
        setattr(conflict, f"{side}_changed_at", _dt(change.get("ts")))
        conflict.updated_at = utcnow()

    def _conflict(self, k: tuple[str, str], side: str, change: dict, current: dict | None) -> None:
        other = "replica" if side == "primary" else "primary"
        latest = self.latest.get(k)
        base = latest.json if latest is not None else (change.get("before") if self.kind == "sql" else None)
        theirs = self._last_change(other, k)
        row = SyncConflict(
            replica_id=self.replica.id,
            table_name=change["table"],
            key_json=change["key"],
            key_hash=k[1],
            status="open",
            base_json=base,
        )
        self._merge(row, side, change)
        setattr(row, f"{other}_json", current)
        setattr(row, f"op_{other}", theirs["op"] if theirs else ("delete" if current is None else "update"))
        setattr(row, f"{other}_changed_at", _dt(theirs["ts"]) if theirs else None)
        self.session.add(row)
        self.open[k] = row
        self.stats["conflicts"] += 1

    def transfer(self, side: str, target: Side) -> None:
        """Applies `side`'s changes to the other copy (`target`)."""
        other_keys = {
            (c["table"], key_hash(c["key"])) for c in self.batches["replica" if side == "primary" else "primary"]
        }
        to_send: list[dict] = []
        for change in self.batches[side]:
            k = (change["table"], key_hash(change["key"]))
            if k in self.open:
                self._merge(self.open[k], side, change)
                continue
            if self.kind == "nosql":
                latest = self.latest.get(k)
                if latest is not None and latest.version_hash == row_hash(change.get("after")):
                    continue  # our own write coming back, or already synced
                change = {
                    **change,
                    "base_hash": latest.version_hash if latest is not None else None,
                    "concurrent": k in other_keys,
                }
            to_send.append(change)
        if not to_send:
            return
        outcomes = target.apply(to_send)
        for change, outcome in zip(to_send, outcomes, strict=True):
            k = (change["table"], key_hash(change["key"]))
            result = outcome.get("result") if isinstance(outcome, dict) else None
            if result == "applied" or (result == "skipped" and self.kind == "nosql"):
                self.latest[k] = add_version(
                    self.session, self.replica.id, change["table"], change["key"], change.get("after"), side
                )
                self.stats["applied"] += result == "applied"
            elif result == "conflict":
                if k in self.open:
                    self._merge(self.open[k], side, change)
                else:
                    self._conflict(k, side, change, outcome.get("current"))
            elif result != "skipped":
                raise ApiError(502, "device_error", "Malformed sync outcome")


def _merge_warnings(existing: list | None, skipped: list[str]) -> list:
    out = [w for w in (existing or []) if isinstance(w, dict)]
    known = {w.get("table") for w in out}
    for table in skipped:
        if table not in known:
            out.append({"table": table, "message": "No primary key: changes to this table are not synced"})
    return out


def sync_round(replica_id: str, *, session_factory=None) -> dict | None:
    """One round for one replica. Returns stats, or None when nothing ran (offline, paused ...).

    Positions move only after the changes they cover were applied. A device that is offline leaves
    everything as it is (the lag grows); errors propagate to the caller (status `error`, backoff).
    """
    session = (session_factory or get_sessionmaker())()
    try:
        replica = session.get(SourceReplica, replica_id)
        if replica is None or replica.status not in ("syncing", "error"):
            return None
        ds = session.get(DataSource, replica.data_source_id)
        if ds is None or ds.deleted_at is not None or ds.device_id is not None or ds.mode != "managed":
            replica.status = "error"
            replica.error = "The source is no longer a managed database on the main server; remove this copy"
            session.commit()
            return None
        if not device_rpc.is_online(replica.device_id):
            _stale(replica)
            session.commit()
            return None
        primary, device = sides_for(replica, ds)
        p = primary.changes(replica.position_primary, BATCH_LIMIT)
        r = device.changes(replica.position_replica, BATCH_LIMIT)
        rnd = _Round(session, replica, ds.kind, {"primary": p["changes"], "replica": r["changes"]})
        rnd.transfer("primary", device)
        replica.position_primary = p["position"]
        session.commit()
        rnd.transfer("replica", primary)
        replica.position_replica = r["position"]
        now = utcnow()
        replica.status = "syncing"
        replica.error = None
        replica.last_synced_at = now
        pending = [c["ts"] for side in (p, r) if side.get("more") for c in side["changes"][-1:]]
        replica.lag_seconds = max([0.0] + [time.time() - float(ts) for ts in pending])
        replica.warnings = _merge_warnings(
            replica.warnings, sorted(set(p.get("skipped_tables") or []) | set(r.get("skipped_tables") or []))
        )
        session.commit()
        return rnd.stats
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def _stale(replica: SourceReplica) -> None:
    if replica.last_synced_at is not None:
        replica.lag_seconds = max(0.0, (utcnow() - replica.last_synced_at).total_seconds())


def record_error(replica_id: str, message: str, *, session_factory=None) -> None:
    session = (session_factory or get_sessionmaker())()
    try:
        replica = session.get(SourceReplica, replica_id)
        if replica is not None and replica.status in ("syncing", "error"):
            replica.status = "error"
            replica.error = message[:2000]
            _stale(replica)
            session.commit()
    finally:
        session.close()


# =============================================================================================
# worker loop (scheduler leader only)
# =============================================================================================


class ReplicaLock:
    """Redis `SET NX PX` lock so a sync round and a conflict resolution never interleave for one copy
    (plain commands only: no Lua, works with fakeredis too)."""

    def __init__(self, replica_id: str, ttl_ms: int = 600_000):
        self.key = f"source_sync:replica:{replica_id}"
        self.token = secrets.token_hex(8)
        self.ttl_ms = ttl_ms

    def acquire(self, wait: float = 0.0) -> bool:
        from app.redis_client import get_redis

        deadline = time.monotonic() + wait
        while True:
            if get_redis().set(self.key, self.token, nx=True, px=self.ttl_ms):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)

    def release(self) -> None:
        from redis.exceptions import WatchError

        from app.redis_client import get_redis

        with get_redis().pipeline() as pipe:
            try:
                pipe.watch(self.key)
                if pipe.get(self.key) == self.token:
                    pipe.multi()
                    pipe.delete(self.key)
                    pipe.execute()
                else:
                    pipe.unwatch()
            except WatchError:
                pass


def replica_lock(replica_id: str) -> ReplicaLock:
    return ReplicaLock(replica_id)


_backoff: dict[str, tuple[float, float]] = {}  # replica id -> (next attempt, delay)


def run_due(*, session_factory=None, now: float | None = None) -> int:
    """One pass over the replicas due for a round. Returns how many rounds ran."""
    factory = session_factory or get_sessionmaker()
    now = time.monotonic() if now is None else now
    session = factory()
    try:
        ids = list(session.scalars(select(SourceReplica.id).where(SourceReplica.status.in_(("syncing", "error")))))
    finally:
        session.close()
    ran = 0
    # ponytail: one replica after another in this thread; a pool when many co-hosts make rounds slow.
    for replica_id in ids:
        next_at, delay = _backoff.get(replica_id, (0.0, 0.0))
        if now < next_at:
            continue
        lock = replica_lock(replica_id)
        if not lock.acquire():
            continue
        try:
            sync_round(replica_id, session_factory=factory)
            _backoff.pop(replica_id, None)
        except ApiError as exc:
            if exc.code in ("device_offline", "device_timeout", "device_busy"):
                _backoff[replica_id] = (now + 10.0, 10.0)  # connection trouble: keep status, retry soon
            else:
                _failed(replica_id, exc.message, now, delay, factory)
        except Exception as exc:  # noqa: BLE001
            log.warning("sync of replica %s failed", replica_id, exc_info=True)
            _failed(replica_id, _redact(getattr(exc, "orig", None) or exc), now, delay, factory)
        finally:
            try:
                lock.release()
            except Exception:  # noqa: BLE001
                pass
        ran += 1
    return ran


def _failed(replica_id: str, message: str, now: float, delay: float, factory) -> None:
    delay = min(MAX_BACKOFF_S, max(4.0, delay * 2))
    _backoff[replica_id] = (now + delay, delay)
    record_error(replica_id, message, session_factory=factory)


def prune_versions(*, session_factory=None, days: int = VERSION_KEEP_DAYS) -> int:
    """Forgets keys whose copies have agreed for `days` (no newer version, no open conflict)."""
    session = (session_factory or get_sessionmaker())()
    try:
        cutoff = utcnow() - timedelta(days=days)
        stale = session.execute(
            select(SyncVersion.replica_id, SyncVersion.table_name, SyncVersion.key_hash)
            .group_by(SyncVersion.replica_id, SyncVersion.table_name, SyncVersion.key_hash)
            .having(func.max(SyncVersion.synced_at) < cutoff)
            .limit(1000)
        ).all()
        removed = 0
        for replica_id, table, kh in stale:
            open_conflict = session.scalar(
                select(SyncConflict.id).where(
                    SyncConflict.replica_id == replica_id,
                    SyncConflict.table_name == table,
                    SyncConflict.key_hash == kh,
                    SyncConflict.status == "open",
                )
            )
            if open_conflict:
                continue
            removed += session.execute(
                delete(SyncVersion).where(
                    SyncVersion.replica_id == replica_id, SyncVersion.table_name == table, SyncVersion.key_hash == kh
                )
            ).rowcount
        session.commit()
        return removed
    finally:
        session.close()


def sync_loop(stop: threading.Event) -> None:
    """Background task of the worker: rounds every 2 s while this worker leads the scheduler."""
    from app import worker
    from app.redis_client import get_redis

    last_prune = float("-inf")
    while not stop.wait(ROUND_EVERY_S):
        try:
            if get_redis().get(worker.LEADER_KEY) != worker.WORKER_ID:
                continue
        except Exception:  # noqa: BLE001
            continue
        run_due()
        if time.monotonic() - last_prune >= 3600:
            last_prune = time.monotonic()
            prune_versions()
