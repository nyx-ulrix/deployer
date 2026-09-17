"""Byte-level backup work against THIS installation's managed MariaDB / MongoDB (used by LocalExecutor).

Tools (installed in the API image, see api/Dockerfile): `mariadb-dump`, `mariadb-binlog`, `mariadb`
(MariaDB 11.x client) and `mongodump` / `mongorestore` (MongoDB Database Tools 100.x).

Credentials never appear in process arguments: MariaDB tools get a 0600 `--defaults-extra-file`,
Mongo tools a 0600 `--config` YAML holding the URI; both live in a private temp directory that is
removed afterwards.

MariaDB
-------
- Snapshot: `mariadb-dump --single-transaction --routines --triggers --events --gtid --master-data=2
  --hex-blob <db>` (no `--databases`, so the dump carries no CREATE DATABASE/USE and can be loaded
  into any name). The stream is read line by line: the `CHANGE MASTER TO` / `gtid_slave_pos`
  comments give the consistent binlog position, and exact row counts are taken from the extended
  INSERT statements. It is then gzip-compressed and encrypted.
- Logs: after `FLUSH BINARY LOGS`, every closed binlog file is fetched with
  `mariadb-binlog --read-from-remote-server --raw` and parsed (event headers only) to learn which
  databases it touches; files that touch the database are stored encrypted as that source's segment,
  others only extend its recorded coverage. `<BACKUP_DIR>/_mariadb/binlog-index.json` caches
  per-file metadata so a file is downloaded at most once per interested source.
- Restore: load the dump into a temporary database (DEFINER clauses rewritten to the target's
  managed user), replay `mariadb-binlog --database=<source> --rewrite-db=<source>-><tmp>
  --start-position=<pos> --stop-datetime=<until+1s> --disable-log-bin` (qualified `<source>.` names
  in statement text are rewritten too), then swap into the target: one atomic multi-table
  `RENAME TABLE` when only base tables are involved, otherwise the live objects are dropped and the
  artifacts are loaded straight into the target (after the temp restore proved they work).

MongoDB (single-node replica set `rs0`)
---------------------------------------
- Snapshot: `mongodump --db <db> --archive --gzip`, oplog timestamp recorded before and after;
  row counts from mongodump's "done dumping" log lines.
- Logs: `local.oplog.rs` entries with `ns` in `<db>.*` (plus `admin.$cmd` applyOps touching it) are
  stored as raw BSON segments.
- Restore: `mongorestore --archive --gzip --nsFrom <src>.* --nsTo <tmp>.*`, then
  `mongorestore --oplogReplay --oplogLimit` over an `oplog.bson` built from the segments (namespaces
  renamed, collection UUIDs stripped), then collections are moved into the target with
  `renameCollection ... dropTarget`.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import secrets
import shutil
import struct
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, Any
from urllib.parse import quote

from app.config import get_settings
from app.services import backup_crypto

log = logging.getLogger(__name__)

ProgressFn = Callable[[float | None, str | None], None]

DB_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
PLATFORM_DB_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
BINLOG_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+\.(\d{6,})$")
TMP_PREFIX = "rtmp_"
VERIFY_PREFIX = "verify_"
GZIP_LEVEL = 6

MARIADB_DUMP = os.environ.get("MARIADB_DUMP_BIN", "mariadb-dump")
MARIADB_BINLOG = os.environ.get("MARIADB_BINLOG_BIN", "mariadb-binlog")
MARIADB_CLIENT = os.environ.get("MARIADB_CLIENT_BIN", "mariadb")
MONGODUMP = os.environ.get("MONGODUMP_BIN", "mongodump")
MONGORESTORE = os.environ.get("MONGORESTORE_BIN", "mongorestore")

_archive_lock = threading.Lock()


class BackupEngineError(RuntimeError):
    """A tool failed; the message is already redacted."""


def _noop(fraction: float | None = None, message: str | None = None) -> None:
    return None


def check_db_name(name: str, *, platform: bool = False) -> str:
    regex = PLATFORM_DB_RE if platform else DB_NAME_RE
    if not isinstance(name, str) or not regex.fullmatch(name):
        raise ValueError(f"Refusing to use invalid database name: {name!r}")
    return name


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def _secrets() -> list[str]:
    s = get_settings()
    return [s.mariadb_root_password, s.mongo_root_password, quote(s.mongo_root_password or "", safe="")]


def _redact(text: str) -> str:
    from app.services.connections import redact

    return redact(text, _secrets())


# =============================================================================================
# credentials & processes
# =============================================================================================


@contextmanager
def private_tmpdir(prefix: str = "dpl-bk-") -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=os.environ.get("BACKUP_TMP_DIR") or None))
    with suppress(OSError):
        os.chmod(path, 0o700)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _write_private(path: Path, content: str) -> Path:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def _option_value(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


@contextmanager
def mariadb_defaults_file() -> Iterator[Path]:
    s = get_settings()
    with private_tmpdir("dpl-my-") as tmp:
        yield _write_private(
            tmp / "client.cnf",
            "[client]\n"
            f"user=root\npassword={_option_value(s.mariadb_root_password or '')}\n"
            f"host={_option_value(s.mariadb_host)}\nport={int(s.mariadb_port)}\n"
            # `[client]` is also read by mariadb-binlog, which does not know this option and would
            # exit 7 ("unknown variable"); `loose-` makes unknown options a warning instead.
            "loose-default-character-set=utf8mb4\n",
        )


def mongo_root_uri() -> str:
    s = get_settings()
    user = quote(s.mongo_root_username or "", safe="")
    pw = quote(s.mongo_root_password or "", safe="")
    creds = f"{user}:{pw}@" if user else ""
    return f"mongodb://{creds}{s.mongo_host}:{int(s.mongo_port)}/?authSource=admin&directConnection=true"


@contextmanager
def mongo_config_file() -> Iterator[Path]:
    with private_tmpdir("dpl-mg-") as tmp:
        # JSON strings are valid YAML scalars.
        yield _write_private(tmp / "tools.yaml", f"uri: {json.dumps(mongo_root_uri())}\n")


def _tool_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("MARIADB_", "MONGO_", "MYSQL_PWD"))}
    env["TZ"] = "UTC"
    return env


def _stderr_text(fh: IO[bytes]) -> str:
    fh.flush()
    fh.seek(0)
    return _redact(fh.read()[-4000:].decode("utf-8", "replace").strip())


def _check_exit(proc: subprocess.Popen, stderr: IO[bytes], tool: str) -> None:
    code = proc.wait()
    if code != 0:
        raise BackupEngineError(f"{tool} failed (exit {code}): {_stderr_text(stderr) or 'no output'}")


def _root_engine():
    from app.services import provisioning

    return provisioning.mariadb_root_engine()


def _mongo_client():
    from app.services import provisioning

    return provisioning.mongo_root_client()


# =============================================================================================
# pure helpers (unit-tested)
# =============================================================================================

_STRING_RE = re.compile(rb"'(?:[^'\\]|\\.)*'", re.DOTALL)
_INSERT_RE = re.compile(rb"^INSERT INTO `((?:[^`]|``)+)` VALUES\s*(.*)$", re.DOTALL)
_TABLE_COMMENT_RE = re.compile(rb"^-- Table structure for table `((?:[^`]|``)+)`")
_CHANGE_MASTER_RE = re.compile(rb"CHANGE MASTER TO MASTER_LOG_FILE='([^']+)', MASTER_LOG_POS=(\d+)")
_GTID_RE = re.compile(rb"SET GLOBAL gtid_slave_pos='([^']*)'")
_DEFINER_RE = re.compile(rb"DEFINER=`(?:[^`]|``)*`@`(?:[^`]|``)*`")


def _count_row_tuples(fragment: bytes) -> int:
    """Number of `(...)` row tuples in a fragment of an extended INSERT (strings blanked first)."""
    body = _STRING_RE.sub(b"''", fragment).strip()
    return body.count(b"),(") + 1 if body.startswith(b"(") else 0


def count_insert_rows(line: bytes) -> tuple[str, int] | None:
    """(table, rows) for the first line of an extended INSERT in a mariadb-dump, else None.

    Older dumps put the rows on the same line (`VALUES (1,'a'),(2,'b');`); MariaDB 11 puts each row on
    its own following line (`VALUES\\n(1,'a'),\\n(2,'b');`), in which case this returns 0 and the
    scanner counts the row lines that follow.
    """
    m = _INSERT_RE.match(line)
    if not m:
        return None
    table = m.group(1).replace(b"``", b"`").decode("utf-8", "replace")
    return table, _count_row_tuples(m.group(2))


class DumpScanner:
    """Collects the consistent point and exact row counts from mariadb-dump output lines."""

    def __init__(self) -> None:
        self.row_counts: dict[str, int] = {}
        self.binlog_file: str | None = None
        self.binlog_pos: int | None = None
        self.gtid: str | None = None
        self._open_insert: str | None = None  # table of a multi-line INSERT whose rows follow

    def feed(self, line: bytes) -> None:
        if self._open_insert is not None:
            stripped = line.rstrip(b"\r\n")
            if stripped.startswith(b"("):
                self.row_counts[self._open_insert] = self.row_counts.get(self._open_insert, 0) + _count_row_tuples(
                    stripped
                )
            if stripped.endswith(b";"):
                self._open_insert = None
            return
        if line.startswith(b"INSERT INTO `"):
            counted = count_insert_rows(line)
            if counted:
                table, rows = counted
                self.row_counts[table] = self.row_counts.get(table, 0) + rows
                if rows == 0 and not line.rstrip(b"\r\n").endswith(b";"):
                    self._open_insert = table
            return
        if not line.startswith(b"--"):
            return
        m = _TABLE_COMMENT_RE.match(line)
        if m:
            self.row_counts.setdefault(m.group(1).replace(b"``", b"`").decode("utf-8", "replace"), 0)
            return
        m = _CHANGE_MASTER_RE.search(line)
        if m and self.binlog_file is None:
            self.binlog_file, self.binlog_pos = m.group(1).decode(), int(m.group(2))
            return
        m = _GTID_RE.search(line)
        if m:
            self.gtid = m.group(1).decode()


def name_rewriter(source: str, target: str) -> Callable[[bytes], bytes]:
    pattern = re.compile(rb"(?<![A-Za-z0-9_$])" + re.escape(source.encode()) + rb"(?![A-Za-z0-9_$])")
    replacement = target.encode()
    return lambda line: pattern.sub(replacement, line)


def rewrite_dump_line(line: bytes, *, definer: bytes, rename: Callable[[bytes], bytes] | None) -> bytes:
    """DEFINER -> the target's user; database name -> target. Data (INSERT) lines are never touched."""
    if line.startswith(b"INSERT INTO `"):
        return line
    if b"DEFINER=" in line:
        line = _DEFINER_RE.sub(definer, line)
    if rename is not None:
        line = rename(line)
    return line


def binlog_seq(name: str) -> int:
    m = BINLOG_NAME_RE.fullmatch(name or "")
    if not m:
        raise ValueError(f"Unexpected binlog file name: {name!r}")
    return int(m.group(1))


def binlog_name_with_seq(template: str, seq: int) -> str:
    m = BINLOG_NAME_RE.fullmatch(template)
    if not m:
        raise ValueError(f"Unexpected binlog file name: {template!r}")
    width = len(m.group(1))
    return template[: m.start(1)] + str(seq).zfill(width)


# MariaDB binlog event types we look at.
_QUERY_EVENT = 2
_TABLE_MAP_EVENT = 19
_QUERY_COMPRESSED_EVENT = 165


def parse_binlog(data: bytes) -> dict[str, Any]:
    """Event-header scan of a raw binlog file: databases touched and first/last event time.

    Returns `{dbs: [...], first_at, last_at, events}`; `dbs` contains "*" if the file could not be
    fully understood (callers then treat it as touching every database).
    """
    dbs: set[str] = set()
    first = last = None
    events = 0
    if not data.startswith(b"\xfebin"):
        return {"dbs": ["*"], "first_at": None, "last_at": None, "events": 0}
    pos = 4
    try:
        while pos + 19 <= len(data):
            ts, etype, _server, size, _next, _flags = struct.unpack_from("<IBIIIH", data, pos)
            if size < 19 or pos + size > len(data):
                if pos + size > len(data):
                    dbs.add("*")  # truncated tail
                break
            body = data[pos + 19 : pos + size]
            events += 1
            if ts:
                first = ts if first is None else min(first, ts)
                last = ts if last is None else max(last, ts)
            if etype in (_QUERY_EVENT, _QUERY_COMPRESSED_EVENT) and len(body) >= 13:
                db_len = body[8]
                status_len = struct.unpack_from("<H", body, 11)[0]
                start = 13 + status_len
                name = body[start : start + db_len].decode("utf-8", "replace")
                if name:
                    dbs.add(name)
            elif etype == _TABLE_MAP_EVENT and len(body) >= 9:
                db_len = body[8]
                dbs.add(body[9 : 9 + db_len].decode("utf-8", "replace"))
            pos += size
    except struct.error:
        dbs.add("*")
    return {
        "dbs": sorted(dbs),
        "first_at": iso(datetime.fromtimestamp(first, UTC).replace(tzinfo=None)) if first else None,
        "last_at": iso(datetime.fromtimestamp(last, UTC).replace(tzinfo=None)) if last else None,
        "events": events,
    }


def rename_oplog_entry(entry: dict, source: str, target: str) -> dict | None:
    """Namespace-renamed copy of an oplog entry without collection UUIDs; None if nothing is left."""
    src_prefix, dst_prefix = f"{source}.", f"{target}."

    def ns_map(ns: Any) -> Any:
        if isinstance(ns, str) and ns.startswith(src_prefix):
            return dst_prefix + ns[len(src_prefix) :]
        return ns

    out = dict(entry)
    out.pop("ui", None)
    op = out.get("op")
    if op == "n":
        return None
    ns = out.get("ns", "")
    if ns == "admin.$cmd" and isinstance(out.get("o"), dict) and "applyOps" in out["o"]:
        o = dict(out["o"])
        inner = [rename_oplog_entry(x, source, target) for x in o.get("applyOps") or [] if isinstance(x, dict)]
        inner = [x for x in inner if x is not None and str(x.get("ns", "")).startswith(dst_prefix)]
        if not inner:
            return None
        o["applyOps"] = inner
        out["o"] = o
        return out
    if not isinstance(ns, str) or not ns.startswith(src_prefix):
        return None
    out["ns"] = ns_map(ns)
    if op == "c" and isinstance(out.get("o"), dict):
        o = dict(out["o"])
        for key in ("renameCollection", "to"):
            if key in o:
                o[key] = ns_map(o[key])
        if "applyOps" in o:
            o["applyOps"] = [
                x for x in (rename_oplog_entry(y, source, target) for y in o["applyOps"] or []) if x is not None
            ]
        out["o"] = o
    return out


MONGO_DONE_RE = re.compile(r"done dumping `([^`]+)` \((\d+) documents?\)")


def parse_mongodump_counts(stderr_text: str, database: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    prefix = f"{database}."
    for ns, n in MONGO_DONE_RE.findall(stderr_text):
        if ns.startswith(prefix):
            counts[ns[len(prefix) :]] = int(n)
    return counts


def ts_list(ts: Any) -> list[int] | None:
    if ts is None:
        return None
    return [int(ts.time), int(ts.inc)]


def ts_from(value: Any):
    from bson import Timestamp

    if value is None:
        return None
    if isinstance(value, Timestamp):
        return value
    return Timestamp(int(value[0]), int(value[1]))


# =============================================================================================
# artifact writing
# =============================================================================================


class ArtifactWriter:
    """gzip -> encrypt -> `<path>.partial`, renamed into place by `commit()`."""

    def __init__(self, path: Path, *, compress: bool = True):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._partial = path.with_name(path.name + ".partial")
        self._fh = open(self._partial, "wb")  # noqa: SIM115
        with suppress(OSError):
            os.chmod(self._partial, 0o600)
        self._enc = backup_crypto.EncryptingWriter(self._fh)
        self._gz = gzip.GzipFile(fileobj=self._enc, mode="wb", compresslevel=GZIP_LEVEL, mtime=0) if compress else None
        self.plain_bytes = 0

    def write(self, data: bytes) -> None:
        self.plain_bytes += len(data)
        (self._gz or self._enc).write(data)

    def commit(self) -> dict[str, Any]:
        if self._gz is not None:
            self._gz.close()
        self._enc.close()
        self._fh.close()
        os.replace(self._partial, self.path)
        return {"size_bytes": self._enc.size, "sha256": self._enc.sha256}

    def abort(self) -> None:
        with suppress(Exception):
            self._fh.close()
        with suppress(OSError):
            self._partial.unlink()


def open_artifact_plain(path: Path, *, compressed: bool = True) -> IO[bytes]:
    """Readable decrypted (and gunzipped) stream of an artifact."""
    raw = open(path, "rb")  # noqa: SIM115
    reader = backup_crypto.DecryptingReader(raw)
    stream: IO[bytes] = gzip.GzipFile(fileobj=reader, mode="rb") if compressed else reader  # type: ignore[assignment]
    original_close = stream.close

    def close() -> None:
        with suppress(Exception):
            original_close()
        raw.close()

    stream.close = close  # type: ignore[method-assign]
    return stream


# =============================================================================================
# MariaDB
# =============================================================================================


def _mariadb_log_bin_enabled() -> bool:
    with _root_engine().connect() as conn:
        return bool(conn.exec_driver_sql("SELECT @@log_bin").scalar())


def _mariadb_size_estimate(database: str) -> int:
    with _root_engine().connect() as conn:
        value = conn.exec_driver_sql(
            "SELECT COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s",
            (database,),
        ).scalar()
    return int(value or 0)


def mariadb_snapshot(database: str, path: Path, on_progress: ProgressFn = _noop) -> dict[str, Any]:
    check_db_name(database, platform=True)
    log_bin = _mariadb_log_bin_enabled()
    estimate = max(_mariadb_size_estimate(database), 1)
    started = _now()
    writer = ArtifactWriter(path)
    scanner = DumpScanner()
    try:
        with mariadb_defaults_file() as cnf, tempfile.TemporaryFile() as err:
            args = [
                MARIADB_DUMP,
                f"--defaults-extra-file={cnf}",
                "--single-transaction",
                "--quick",
                "--routines",
                "--triggers",
                "--events",
                "--hex-blob",
                "--default-character-set=utf8mb4",
            ]
            if log_bin:
                args += ["--gtid", "--master-data=2"]
            args.append(database)
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=err, env=_tool_env())  # noqa: S603
            assert proc.stdout is not None
            last = time.monotonic()
            for line in proc.stdout:
                scanner.feed(line)
                writer.write(line)
                if time.monotonic() - last > 2:
                    last = time.monotonic()
                    on_progress(
                        min(0.9, writer.plain_bytes / (estimate * 1.5)), f"Dumped {writer.plain_bytes >> 20} MiB"
                    )
            _check_exit(proc, err, "mariadb-dump")
        info = writer.commit()
    except BaseException:
        writer.abort()
        raise
    point = {
        "binlog_file": scanner.binlog_file,
        "binlog_pos": scanner.binlog_pos,
        "gtid": scanner.gtid,
        "consistent_at": iso(started),
    }
    return {**info, "consistent_point": point, "row_counts": scanner.row_counts}


# ---- binlog archiving ------------------------------------------------------------------------


def _index_path(root: Path) -> Path:
    return root / "_mariadb" / "binlog-index.json"


def _load_index(root: Path) -> dict[str, Any]:
    try:
        data = json.loads(_index_path(root).read_text("utf-8"))
        if isinstance(data, dict):
            data.setdefault("files", {})
            data.setdefault("flush_pos", {})
            return data
    except (OSError, ValueError):
        pass
    return {"files": {}, "flush_pos": {}}


def _save_index(root: Path, index: dict[str, Any]) -> None:
    path = _index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the index small: forget files the server no longer has.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, separators=(",", ":")), "utf-8")
    os.replace(tmp, path)


def _fetch_binlog(name: str, dest_dir: Path) -> Path:
    if not BINLOG_NAME_RE.fullmatch(name):
        raise ValueError(f"Unexpected binlog file name: {name!r}")
    with mariadb_defaults_file() as cnf, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(  # noqa: S603
            [
                MARIADB_BINLOG,
                f"--defaults-extra-file={cnf}",
                "--read-from-remote-server",
                "--raw",
                f"--result-file={dest_dir.as_posix()}/",
                name,
            ],
            stdout=subprocess.DEVNULL,
            stderr=err,
            env=_tool_env(),
        )
        _check_exit(proc, err, "mariadb-binlog")
    path = dest_dir / name
    if not path.is_file():
        raise BackupEngineError(f"mariadb-binlog did not produce {name}")
    return path


def mariadb_archive_logs(database: str, since_point: dict | None, prefix: str, root: Path) -> list[dict]:
    check_db_name(database)
    if not since_point:
        return []
    if "after" in since_point:
        base = since_point["after"] or {}
        if not base.get("binlog_file"):
            return []
        start_seq = binlog_seq(base["binlog_file"])
    else:
        if not since_point.get("binlog_file"):
            return []
        start_seq = binlog_seq(since_point["binlog_file"]) + 1
    if not _mariadb_log_bin_enabled():
        return []

    from app.models import new_id

    with _archive_lock, _root_engine().connect() as conn:
        index = _load_index(root)
        status = conn.exec_driver_sql("SHOW MASTER STATUS").first()
        if status is None:
            return []
        current, pos = str(status[0]), int(status[1])
        if binlog_seq(current) >= start_seq and pos > int(index["flush_pos"].get(current, 0)):
            flushed_at = conn.exec_driver_sql("SELECT UTC_TIMESTAMP(6)").scalar()
            conn.exec_driver_sql("FLUSH BINARY LOGS")
            index["files"].setdefault(current, {})["closed_at"] = iso(flushed_at)
            status = conn.exec_driver_sql("SHOW MASTER STATUS").first()
            index["flush_pos"] = {str(status[0]): int(status[1])}
        logs = [(str(r[0]), int(r[1])) for r in conn.exec_driver_sql("SHOW BINARY LOGS")]
        closed = logs[:-1]
        available = {name for name, _ in logs}
        index["files"] = {k: v for k, v in index["files"].items() if k in available}

        segments: list[dict] = []
        expected_seq = start_seq
        with private_tmpdir("dpl-binlog-") as tmp:
            for name, size in closed:
                seq = binlog_seq(name)
                if seq < start_seq:
                    continue
                meta = index["files"].setdefault(name, {})
                raw_path: Path | None = None
                if "dbs" not in meta or meta.get("size") != size:
                    raw_path = _fetch_binlog(name, tmp)
                    parsed = parse_binlog(raw_path.read_bytes())
                    meta.update(dbs=parsed["dbs"], first_at=parsed["first_at"], last_at=parsed["last_at"], size=size)
                closed_at = meta.get("closed_at") or meta.get("last_at") or iso(_now())
                start_at = meta.get("first_at") or closed_at
                point = {"binlog_file": name}
                start_point = dict(point)
                if seq != expected_seq:
                    start_point["gap"] = True
                expected_seq = seq + 1
                touches = database in meta["dbs"] or "*" in meta["dbs"]
                seg: dict[str, Any] = {
                    "id": new_id(),
                    "ref": None,
                    "start_at": start_at,
                    "end_at": closed_at,
                    "start_point": start_point,
                    "end_point": point,
                    "size_bytes": 0,
                    "sha256": None,
                }
                if touches:
                    if raw_path is None:
                        raw_path = _fetch_binlog(name, tmp)
                    ref = f"{prefix.rstrip('/')}/{seg['id']}.bin"
                    writer = ArtifactWriter(root / ref)
                    try:
                        with open(raw_path, "rb") as fh:
                            while chunk := fh.read(1 << 20):
                                writer.write(chunk)
                        info = writer.commit()
                    except BaseException:
                        writer.abort()
                        raise
                    seg.update(ref=ref, **info)
                if raw_path is not None:
                    raw_path.unlink(missing_ok=True)
                segments.append(seg)
        _save_index(root, index)
    return segments


# ---- restore ---------------------------------------------------------------------------------


def _mysql_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _managed_user_for(database: str) -> str | None:
    with _root_engine().connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT User FROM mysql.db WHERE Db = %s AND User LIKE 'u\\_%%' ORDER BY User LIMIT 1", (database,)
        ).first()
    return str(rows[0]) if rows else None


def _run_mariadb_client(database: str, feed: Callable[[Callable[[bytes], None]], None]) -> None:
    """Runs `mariadb <database>` as root and streams SQL into it via `feed(write)`."""
    with mariadb_defaults_file() as cnf, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(  # noqa: S603
            [MARIADB_CLIENT, f"--defaults-extra-file={cnf}", "--binary-mode", "--max-allowed-packet=1G", database],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=err,
            env=_tool_env(),
        )
        assert proc.stdin is not None
        try:
            feed(proc.stdin.write)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        _check_exit(proc, err, "mariadb")


def _load_dump(
    snapshot_path: Path,
    database: str,
    *,
    source: str | None,
    definer_user: str | None,
    on_progress: ProgressFn = _noop,
    progress_range: tuple[float, float] = (0.0, 0.5),
) -> None:
    definer = (f"DEFINER=`{definer_user}`@`%`" if definer_user else "DEFINER=CURRENT_USER").encode()
    rename = name_rewriter(source, database) if source and source != database else None
    total = max(snapshot_path.stat().st_size, 1)

    def feed(write: Callable[[bytes], None]) -> None:
        write(b"SET SESSION sql_log_bin=0;\n")
        raw = open(snapshot_path, "rb")  # noqa: SIM115
        try:
            stream = gzip.GzipFile(fileobj=backup_crypto.DecryptingReader(raw), mode="rb")
            last = time.monotonic()
            for line in stream:
                write(rewrite_dump_line(line, definer=definer, rename=rename))
                if time.monotonic() - last > 2:
                    last = time.monotonic()
                    lo, hi = progress_range
                    on_progress(lo + (hi - lo) * min(1.0, raw.tell() / total), "Loading snapshot")
        finally:
            raw.close()

    _run_mariadb_client(database, feed)


def _replay_binlogs(
    segments: list[dict],
    database: str,
    *,
    source: str,
    consistent_point: dict,
    until: datetime | None,
    definer_user: str | None,
    on_progress: ProgressFn = _noop,
) -> int:
    """Decrypts segment files and replays them into `database`. Returns the number of files replayed."""
    files = [s for s in segments if s.get("ref") and s.get("path")]
    if not files:
        return 0
    rename = name_rewriter(source, database) if source != database else None
    definer = (f"DEFINER=`{definer_user}`@`%`" if definer_user else "DEFINER=CURRENT_USER").encode()
    with private_tmpdir("dpl-replay-") as tmp:
        paths = []
        for seg in files:
            name = (seg.get("start_point") or {}).get("binlog_file") or f"segment.{len(paths):06d}"
            if not BINLOG_NAME_RE.fullmatch(name):
                raise ValueError(f"Unexpected binlog file name: {name!r}")
            dest = tmp / name
            with open_artifact_plain(Path(seg["path"])) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            paths.append(dest)
        args = [MARIADB_BINLOG, f"--database={source}", "--disable-log-bin"]
        if source != database:
            args.append(f"--rewrite-db={source}->{database}")
        first_file = (files[0].get("start_point") or {}).get("binlog_file")
        if consistent_point.get("binlog_file") and first_file == consistent_point["binlog_file"]:
            args.append(f"--start-position={int(consistent_point['binlog_pos'])}")
        if until is not None:
            stop = until.replace(microsecond=0) + timedelta(seconds=1)
            args.append(f"--stop-datetime={stop.strftime('%Y-%m-%d %H:%M:%S')}")
        args += [p.as_posix() for p in paths]
        with tempfile.TemporaryFile() as err:
            binlog = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=err, env=_tool_env())  # noqa: S603
            assert binlog.stdout is not None
            on_progress(None, f"Replaying {len(paths)} binlog file(s)")

            def feed(write: Callable[[bytes], None]) -> None:
                for line in binlog.stdout:  # type: ignore[union-attr]
                    if b"DEFINER=" in line:
                        line = _DEFINER_RE.sub(definer, line)
                    write(rename(line) if rename else line)

            try:
                _run_mariadb_client(database, feed)
            finally:
                with suppress(Exception):
                    binlog.stdout.close()
            _check_exit(binlog, err, "mariadb-binlog")
    return len(paths)


def _mariadb_exec(sql: str, params: tuple | None = None) -> Any:
    with _root_engine().connect() as conn:
        return conn.exec_driver_sql(sql, params) if params else conn.exec_driver_sql(sql)


def _mariadb_objects(conn, database: str) -> dict[str, list[str]]:
    q = conn.exec_driver_sql
    return {
        "tables": [
            r[0]
            for r in q(
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s "
                "AND TABLE_TYPE IN ('BASE TABLE','SYSTEM VERSIONED','SEQUENCE')",
                (database,),
            )
        ],  # noqa: E501
        "views": [
            r[0] for r in q("SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA=%s", (database,))
        ],
        "triggers": [
            r[0] for r in q("SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s", (database,))
        ],  # noqa: E501
        "routines": [
            f"{r[1]} {r[0]}"
            for r in q(
                "SELECT ROUTINE_NAME, ROUTINE_TYPE FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s",
                (database,),
            )
        ],  # noqa: E501
        "events": [
            r[0] for r in q("SELECT EVENT_NAME FROM information_schema.EVENTS WHERE EVENT_SCHEMA=%s", (database,))
        ],
    }


def mariadb_row_counts(database: str) -> dict[str, int]:
    with _root_engine().connect() as conn:
        tables = _mariadb_objects(conn, database)["tables"]
        return {
            t: int(conn.exec_driver_sql(f"SELECT COUNT(*) FROM {_mysql_ident(database)}.{_mysql_ident(t)}").scalar())
            for t in tables
        }


def _mariadb_create_db(name: str) -> None:
    check_db_name(name)
    _mariadb_exec(f"CREATE DATABASE {_mysql_ident(name)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")


def _mariadb_drop_db(name: str) -> None:
    check_db_name(name)
    if not name.startswith((TMP_PREFIX, VERIFY_PREFIX, "rtrash_")):
        raise ValueError(f"Refusing to drop non-temporary database {name!r}")
    _mariadb_exec(f"DROP DATABASE IF EXISTS {_mysql_ident(name)}")


def _mariadb_clear(conn, database: str) -> None:
    objs = _mariadb_objects(conn, database)
    db = _mysql_ident(database)
    conn.exec_driver_sql("SET SESSION sql_log_bin=0")
    for name in objs["views"]:
        conn.exec_driver_sql(f"DROP VIEW IF EXISTS {db}.{_mysql_ident(name)}")
    conn.exec_driver_sql("SET SESSION foreign_key_checks=0")
    for name in objs["tables"]:
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {db}.{_mysql_ident(name)}")
    conn.exec_driver_sql("SET SESSION foreign_key_checks=1")
    for entry in objs["routines"]:
        rtype, name = entry.split(" ", 1)
        conn.exec_driver_sql(
            f"DROP {'FUNCTION' if rtype == 'FUNCTION' else 'PROCEDURE'} IF EXISTS {db}.{_mysql_ident(name)}"
        )
    for name in objs["events"]:
        conn.exec_driver_sql(f"DROP EVENT IF EXISTS {db}.{_mysql_ident(name)}")
    conn.exec_driver_sql("SET SESSION sql_log_bin=1")


def _mariadb_swap_rename(tmp: str, target: str) -> bool:
    """Atomic multi-table RENAME when only base tables are involved. False if not applicable."""
    with _root_engine().connect() as conn:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (target,)
        ).first()
        if not exists:
            conn.exec_driver_sql(
                f"CREATE DATABASE {_mysql_ident(target)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        src, dst = _mariadb_objects(conn, tmp), _mariadb_objects(conn, target)
        for key in ("views", "triggers", "routines", "events"):
            if src[key] or dst[key]:
                return False
        if not src["tables"] and not dst["tables"]:
            return True
        trash = f"rtrash_{secrets.token_hex(6)}"
        conn.exec_driver_sql(f"CREATE DATABASE {_mysql_ident(trash)}")
        try:
            parts = [
                f"{_mysql_ident(target)}.{_mysql_ident(t)} TO {_mysql_ident(trash)}.{_mysql_ident(t)}"
                for t in dst["tables"]
            ]
            parts += [
                f"{_mysql_ident(tmp)}.{_mysql_ident(t)} TO {_mysql_ident(target)}.{_mysql_ident(t)}"
                for t in src["tables"]
            ]
            conn.exec_driver_sql("RENAME TABLE " + ", ".join(parts))
        finally:
            conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {_mysql_ident(trash)}")
    return True


def mariadb_restore(
    *,
    snapshot_path: Path,
    segments: list[dict],
    target: str,
    source: str,
    consistent_point: dict,
    until: datetime | None,
    on_progress: ProgressFn = _noop,
) -> dict[str, Any]:
    check_db_name(target)
    check_db_name(source, platform=True)
    tmp = f"{TMP_PREFIX}{secrets.token_hex(6)}"
    definer_user = _managed_user_for(target)
    _mariadb_create_db(tmp)
    try:
        on_progress(0.02, "Loading snapshot into a temporary database")
        _load_dump(
            snapshot_path,
            tmp,
            source=source,
            definer_user=definer_user,
            on_progress=on_progress,
            progress_range=(0.02, 0.45),
        )
        replayed = _replay_binlogs(
            segments,
            tmp,
            source=source,
            consistent_point=consistent_point,
            until=until,
            definer_user=definer_user,
            on_progress=on_progress,
        )
        on_progress(0.6, "Counting rows")
        counts = mariadb_row_counts(tmp)
        on_progress(0.7, "Swapping restored data into place")
        if _mariadb_swap_rename(tmp, target):
            swap = "rename"
        else:
            with _root_engine().connect() as conn:
                _mariadb_clear(conn, target)
            _load_dump(
                snapshot_path,
                target,
                source=source,
                definer_user=definer_user,
                on_progress=on_progress,
                progress_range=(0.7, 0.9),
            )
            _replay_binlogs(
                segments,
                target,
                source=source,
                consistent_point=consistent_point,
                until=until,
                definer_user=definer_user,
            )
            swap = "reload"
        return {"row_counts": counts, "swap": swap, "replayed_files": replayed, "resume_point": mariadb_current_point()}
    finally:
        with suppress(Exception):
            _mariadb_drop_db(tmp)


def mariadb_current_point() -> dict[str, Any] | None:
    with _root_engine().connect() as conn:
        status = conn.exec_driver_sql("SHOW MASTER STATUS").first()
    if status is None:
        return None
    return {"binlog_file": str(status[0]), "binlog_pos": int(status[1]), "at": iso(_now())}


def mariadb_verify(snapshot_path: Path, expected: dict | None) -> dict[str, Any]:
    name = f"{VERIFY_PREFIX}{secrets.token_hex(6)}"
    _mariadb_create_db(name)
    try:
        _load_dump(snapshot_path, name, source=None, definer_user=None)
        counts = mariadb_row_counts(name)
    finally:
        with suppress(Exception):
            _mariadb_drop_db(name)
    return compare_counts(expected, counts)


def compare_counts(expected: dict | None, actual: dict[str, int]) -> dict[str, Any]:
    mismatches = []
    for name in sorted(set(expected or {}) | set(actual)):
        want, got = (expected or {}).get(name), actual.get(name)
        if want != got:
            mismatches.append({"entity": name, "expected": want, "actual": got})
    ok = not mismatches
    return {
        "ok": ok,
        "row_counts": actual,
        "mismatches": mismatches,
        "message": "Row counts match" if ok else f"{len(mismatches)} table(s)/collection(s) differ",
    }


# =============================================================================================
# MongoDB
# =============================================================================================


def ensure_mongo_replica_set(*, member_host: str | None = None) -> str:
    """Initiates the single-node replica set `rs0` if needed. Returns a short status string.

    Safe to call on every start: an initiated set, a mongod without `--replSet`, or an unreachable
    server are reported, not raised.
    """
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure, PyMongoError

    s = get_settings()
    if not s.managed_mongodb_enabled:
        return "disabled"
    host = member_host or os.environ.get("MONGO_REPLSET_HOST") or f"{s.mongo_host}:{s.mongo_port}"
    # A direct connection: an uninitiated member is not selectable through replica-set discovery.
    client = MongoClient(
        host=s.mongo_host,
        port=int(s.mongo_port),
        username=s.mongo_root_username or None,
        password=s.mongo_root_password or None,
        authSource="admin",
        directConnection=True,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        appname="deployer-replset-init",
    )
    try:
        try:
            client.admin.command("replSetGetStatus")
            return "ok"
        except OperationFailure as exc:
            if exc.code == 76:  # NoReplicationEnabled: started without --replSet
                return "no_replset"
            if exc.code != 94:  # NotYetInitialized
                raise
        client.admin.command("replSetInitiate", {"_id": "rs0", "members": [{"_id": 0, "host": host}]})
        return "initiated"
    except PyMongoError as exc:
        return f"error: {_redact(str(exc))}"
    finally:
        client.close()


def _oplog_available(client) -> bool:
    try:
        return "oplog.rs" in client.local.list_collection_names()
    except Exception:  # noqa: BLE001
        return False


def _latest_oplog_ts(client):
    doc = client.local["oplog.rs"].find({}, {"ts": 1}).sort("$natural", -1).limit(1)
    for d in doc:
        return d["ts"]
    return None


def _oldest_oplog_ts(client):
    for d in client.local["oplog.rs"].find({}, {"ts": 1}).sort("$natural", 1).limit(1):
        return d["ts"]
    return None


def _ts_time(ts) -> str | None:
    if ts is None:
        return None
    return iso(datetime.fromtimestamp(int(ts.time), UTC).replace(tzinfo=None))


def mongo_snapshot(database: str, path: Path, on_progress: ProgressFn = _noop) -> dict[str, Any]:
    check_db_name(database)
    client = _mongo_client()
    has_oplog = _oplog_available(client)
    ts_start = _latest_oplog_ts(client) if has_oplog else None
    started = _now()
    writer = ArtifactWriter(path, compress=False)  # the archive is already gzip-compressed by mongodump
    try:
        with mongo_config_file() as cfg, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(  # noqa: S603
                [MONGODUMP, f"--config={cfg}", f"--db={database}", "--archive", "--gzip"],
                stdout=subprocess.PIPE,
                stderr=err,
                env=_tool_env(),
            )
            assert proc.stdout is not None
            last = time.monotonic()
            while chunk := proc.stdout.read(1 << 20):
                writer.write(chunk)
                if time.monotonic() - last > 2:
                    last = time.monotonic()
                    on_progress(None, f"Dumped {writer.plain_bytes >> 20} MiB")
            _check_exit(proc, err, "mongodump")
            err.seek(0)
            counts = parse_mongodump_counts(err.read().decode("utf-8", "replace"), database)
        info = writer.commit()
    except BaseException:
        writer.abort()
        raise
    ts_end = _latest_oplog_ts(client) if has_oplog else None
    point = {
        "oplog_ts_start": ts_list(ts_start),
        "oplog_ts_end": ts_list(ts_end),
        "consistent_at": _ts_time(ts_end) or iso(started),
    }
    for name in _mongo_collections(client, database):
        counts.setdefault(name, 0)
    return {**info, "consistent_point": point, "row_counts": counts}


def _mongo_collections(client, database: str) -> list[str]:
    return sorted(
        c["name"]
        for c in client[database].list_collections(filter={"type": "collection"})
        if not c["name"].startswith("system.")
    )


def mongo_archive_logs(database: str, since_point: dict | None, prefix: str, root: Path) -> list[dict]:
    from bson.codec_options import CodecOptions
    from bson.raw_bson import RawBSONDocument

    from app.models import new_id

    check_db_name(database)
    if not since_point:
        return []
    client = _mongo_client()
    if not _oplog_available(client):
        return []
    inclusive = "after" in since_point
    since = ts_from((since_point.get("after") or {}).get("oplog_ts_start") if inclusive else since_point.get("ts"))
    if since is None:
        return []
    upper = _latest_oplog_ts(client)
    if upper is None or upper <= since:
        return []
    oldest = _oldest_oplog_ts(client)
    gap = oldest is not None and oldest > since and not (inclusive and oldest == since)
    pattern = "^" + re.escape(database) + r"\."
    query = {
        "ts": {("$gte" if inclusive else "$gt"): since, "$lte": upper},
        "$or": [{"ns": {"$regex": pattern}}, {"ns": "admin.$cmd", "o.applyOps.ns": {"$regex": pattern}}],
    }
    oplog = client.local.get_collection("oplog.rs", codec_options=CodecOptions(document_class=RawBSONDocument))
    seg_id = new_id()
    ref = f"{prefix.rstrip('/')}/{seg_id}.bin"
    writer = ArtifactWriter(root / ref)
    count = 0
    first_ts = None
    try:
        for doc in oplog.find(query).sort("$natural", 1):
            writer.write(doc.raw)
            count += 1
            if first_ts is None:
                first_ts = doc["ts"]
        info = writer.commit() if count else None
        if not count:
            writer.abort()
    except BaseException:
        writer.abort()
        raise
    # Segment ranges are (start, end]; the first one after a snapshot also includes `start` itself.
    start_point: dict[str, Any] = {"ts": ts_list(since)}
    if inclusive:
        start_point["inclusive"] = True
    if gap:
        start_point["gap"] = True
    seg: dict[str, Any] = {
        "id": seg_id,
        "ref": ref if count else None,
        "start_at": _ts_time(first_ts or since),
        "end_at": _ts_time(upper),
        "start_point": start_point,
        "end_point": {"ts": ts_list(upper)},
        "size_bytes": info["size_bytes"] if info else 0,
        "sha256": info["sha256"] if info else None,
        "entries": count,
    }
    return [seg]


def _mongorestore(args: list[str], *, stdin: IO[bytes] | None = None) -> str:
    with mongo_config_file() as cfg, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(  # noqa: S603
            [MONGORESTORE, f"--config={cfg}", *args],
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err,
            env=_tool_env(),
        )
        if stdin is not None:
            assert proc.stdin is not None
            try:
                shutil.copyfileobj(stdin, proc.stdin, 1 << 20)
                proc.stdin.close()
            except BrokenPipeError:
                pass
        _check_exit(proc, err, "mongorestore")
        err.seek(0)
        return err.read().decode("utf-8", "replace")


def _mongo_load_archive(snapshot_path: Path, source: str, target: str) -> None:
    with open_artifact_plain(snapshot_path, compressed=False) as stream:
        _mongorestore(
            [
                "--archive",
                "--gzip",
                f"--nsInclude={source}.*",
                f"--nsFrom={source}.*",
                f"--nsTo={target}.*",
                "--numInsertionWorkersPerCollection=1",
                "--stopOnError",
            ],
            stdin=stream,
        )


def _mongo_build_oplog(
    segments: list[dict], out_path: Path, *, source: str, target: str, start_ts, end_ts, limit_ts, existing: set[str]
) -> int:
    import bson

    written = 0
    with open(out_path, "wb") as out:
        for seg in segments:
            if not seg.get("ref") or not seg.get("path"):
                continue
            with open_artifact_plain(Path(seg["path"])) as stream:
                for entry in bson.decode_file_iter(stream):
                    ts = entry.get("ts")
                    if ts is None or (start_ts is not None and ts < start_ts):
                        continue
                    if limit_ts is not None and ts >= limit_ts:
                        continue
                    renamed = rename_oplog_entry(entry, source, target)
                    if renamed is None:
                        continue
                    # Inside the fuzzy dump window, collection/index creation may already be in the archive.
                    if end_ts is not None and ts <= end_ts and renamed.get("op") == "c":
                        o = renamed.get("o") or {}
                        coll = o.get("create") or o.get("createIndexes")
                        if coll and coll in existing:
                            continue
                    out.write(bson.encode(renamed))
                    written += 1
    return written


def _mongo_replay(
    segments: list[dict], target: str, *, source: str, consistent_point: dict, until: datetime | None
) -> int:
    from bson import Timestamp

    if not any(s.get("ref") for s in segments):
        return 0
    start_ts = ts_from(consistent_point.get("oplog_ts_start"))
    end_ts = ts_from(consistent_point.get("oplog_ts_end"))
    limit_ts = Timestamp(int(until.replace(tzinfo=UTC).timestamp()) + 1, 0) if until is not None else None
    existing = set(_mongo_client()[target].list_collection_names())
    with private_tmpdir("dpl-oplog-") as tmp:
        count = _mongo_build_oplog(
            segments,
            tmp / "oplog.bson",
            source=source,
            target=target,
            start_ts=start_ts,
            end_ts=end_ts,
            limit_ts=limit_ts,
            existing=existing,
        )
        if count:
            args = ["--oplogReplay", f"--dir={tmp.as_posix()}"]
            if limit_ts is not None:
                args.append(f"--oplogLimit={limit_ts.time}:{limit_ts.inc}")
            _mongorestore(args)
    return count


def mongo_row_counts(database: str) -> dict[str, int]:
    client = _mongo_client()
    return {name: int(client[database][name].count_documents({})) for name in _mongo_collections(client, database)}


def _mongo_drop_tmp(name: str) -> None:
    check_db_name(name)
    if not name.startswith((TMP_PREFIX, VERIFY_PREFIX)):
        raise ValueError(f"Refusing to drop non-temporary database {name!r}")
    _mongo_client().drop_database(name)


def _mongo_swap(tmp: str, target: str) -> None:
    client = _mongo_client()
    src_db, dst_db = client[tmp], client[target]
    src_infos = list(src_db.list_collections())
    dst_infos = list(dst_db.list_collections())
    src_colls = {c["name"] for c in src_infos if c.get("type") == "collection" and not c["name"].startswith("system.")}
    src_views = [c for c in src_infos if c.get("type") == "view"]
    for info in dst_infos:
        if info.get("type") == "view":
            dst_db.drop_collection(info["name"])
    for name in sorted(src_colls):
        client.admin.command("renameCollection", f"{tmp}.{name}", to=f"{target}.{name}", dropTarget=True)
    for info in dst_infos:
        name = info["name"]
        if info.get("type") == "collection" and not name.startswith("system.") and name not in src_colls:
            dst_db.drop_collection(name)
    for view in src_views:
        opts = view.get("options") or {}
        dst_db.command(
            "create",
            view["name"],
            viewOn=opts.get("viewOn"),
            pipeline=opts.get("pipeline") or [],
            **({"collation": opts["collation"]} if opts.get("collation") else {}),
        )


def mongo_restore(
    *,
    snapshot_path: Path,
    segments: list[dict],
    target: str,
    source: str,
    consistent_point: dict,
    until: datetime | None,
    on_progress: ProgressFn = _noop,
) -> dict[str, Any]:
    check_db_name(target)
    check_db_name(source)
    tmp = f"{TMP_PREFIX}{secrets.token_hex(6)}"
    try:
        on_progress(0.05, "Restoring snapshot into a temporary database")
        _mongo_load_archive(snapshot_path, source, tmp)
        on_progress(0.5, "Replaying oplog")
        replayed = _mongo_replay(segments, tmp, source=source, consistent_point=consistent_point, until=until)
        counts = mongo_row_counts(tmp)
        on_progress(0.8, "Swapping restored data into place")
        _mongo_swap(tmp, target)
        client = _mongo_client()
        resume = _latest_oplog_ts(client) if _oplog_available(client) else None
        return {
            "row_counts": counts,
            "swap": "rename",
            "replayed_entries": replayed,
            "resume_point": {"ts": ts_list(resume), "at": iso(_now())} if resume else None,
        }
    finally:
        with suppress(Exception):
            _mongo_drop_tmp(tmp)


def mongo_verify(snapshot_path: Path, expected: dict | None) -> dict[str, Any]:
    name = f"{VERIFY_PREFIX}{secrets.token_hex(6)}"
    try:
        # The archive holds exactly one database; map whatever it is onto the verify database.
        with open_artifact_plain(snapshot_path, compressed=False) as stream:
            _mongorestore(
                [
                    "--archive",
                    "--gzip",
                    "--nsFrom=$db$.$coll$",
                    f"--nsTo={name}.$coll$",
                    "--numInsertionWorkersPerCollection=1",
                    "--stopOnError",
                ],
                stdin=stream,
            )
        counts = mongo_row_counts(name)
    finally:
        with suppress(Exception):
            _mongo_drop_tmp(name)
    return compare_counts(expected, counts)


# =============================================================================================
# restore-as-new target
# =============================================================================================


def ensure_database(kind: str, database_name: str) -> dict[str, Any]:
    """Creates an empty managed database + dedicated user on this host; returns the connection config."""
    from app.errors import ApiError
    from app.services import provisioning

    check_db_name(database_name)
    username, password = provisioning.generate_username(), provisioning.generate_password()
    if kind == "sql":
        if provisioning.mariadb_database_exists(database_name):
            raise ApiError(409, "database_exists", f"Database {database_name} already exists")
        return provisioning.create_mariadb_database(database_name, username, password)
    if provisioning.mongo_database_exists(database_name):
        raise ApiError(409, "database_exists", f"Database {database_name} already exists")
    return provisioning.create_mongo_database(database_name, username, password)
