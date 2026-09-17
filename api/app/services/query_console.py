"""Query console (docs/QUERY_CONSOLE.md): SQL scripts against SQL data sources and MongoDB shell
code against NoSQL data sources.

- SQL: statements are split with `sqlparse` (strings and comments respected) and run one after the
  other on a single autocommit connection; execution stops at the first error. The user's SQL runs
  as given (`exec_driver_sql`), nothing is ever interpolated into it, and the connection is
  invalidated afterwards so session state (`SET`, `USE`, temp tables, statement timeouts) never
  leaks back into the shared pool.
- MongoDB: the code runs in a real `mongosh` process (`--nodb --quiet --norc --eval <wrapper>`).
  The wrapper (`WRAPPER_JS`, no secrets, no user code) connects with the source's own credentials,
  evaluates the user's code from a 0600 file through the shell's own evaluator (the path `load()`
  uses, so the async rewriter applies) and prints one marker-prefixed relaxed Extended JSON line
  with the result. URI, file path and marker reach the shell only through the child's environment
  (never argv), HOME is a private temporary directory, the process is killed at the timeout, its
  output is size-capped and at most `MAX_SHELLS` shells run per API process.
- Read-only role (viewers): statements / code must pass the textual classifiers below. They are
  best effort by design (`db.items["insert" + "One"]` slips through); the database user of the
  source is the real boundary.
- Query text and results never go to logs or audit entries (routers/query.py records counts only).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import sqlparse
from sqlalchemy import Engine
from sqlparse import sql as sqltree
from sqlparse import tokens as T

from app.errors import ApiError
from app.models import DataSource
from app.services import connections
from app.services.data_browser import encode_value

MAX_QUERY_CHARS = 200_000
DEFAULT_MAX_ROWS = 500
MAX_ROWS = 5000
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120
MAX_SHELLS = 4
MAX_SHELL_STDOUT = 8 * 1024 * 1024
MAX_SHELL_STDERR = 1024 * 1024
CONNECT_TIMEOUT_MS = 5000


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _clamp(value: Any, maximum: int, default: int) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _read_only_refused(kind: str) -> ApiError:
    if kind == "sql":
        message = "Viewers can only run read-only SQL (SELECT, WITH, SHOW, EXPLAIN, DESCRIBE, TABLE, VALUES)"
    else:
        message = "Viewers can only run read-only MongoDB shell code (no insert/update/delete/drop/command calls)"
    return ApiError(403, "read_only_role", message)


def _error_text(exc: BaseException) -> str:
    """Driver error text; PyMySQL's `(errno, message)` tuples become `message (error errno)`."""
    args = getattr(exc, "args", ())
    if len(args) == 2 and isinstance(args[0], int) and isinstance(args[1], str):
        return f"{args[1]} (error {args[0]})"
    return str(exc)


# =============================================================================================
# SQL
# =============================================================================================

READ_ONLY_STARTS = frozenset({"SELECT", "WITH", "SHOW", "EXPLAIN", "DESCRIBE", "DESC", "TABLE", "VALUES"})
# Keywords that write, lock or change session state when they appear anywhere in a statement that
# otherwise starts read-only (PostgreSQL data-modifying CTEs, `SELECT ... FOR UPDATE`, `INTO OUTFILE`).
WRITE_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "MERGE",
        "UPSERT",
        "INTO",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "RENAME",
        "GRANT",
        "REVOKE",
        "LOCK",
        "UNLOCK",
        "SET",
        "CALL",
        "EXEC",
        "EXECUTE",
        "DO",
        "LOAD",
        "HANDLER",
        "INSTALL",
        "UNINSTALL",
        "FLUSH",
        "RESET",
        "PURGE",
        "KILL",
        "START",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "RELEASE",
        "PREPARE",
        "DEALLOCATE",
        "IMPORT",
        "COPY",
        "VACUUM",
        "CLUSTER",
        "REINDEX",
        "REFRESH",
        "NOTIFY",
        "LISTEN",
        "UNLISTEN",
        "DECLARE",
        "OUTFILE",
        "DUMPFILE",
        "SHUTDOWN",
        "OPTIMIZE",
        "REPAIR",
    }
)
# Statements whose `rowcount` is meaningful even when it is 0 (result type "count" instead of "empty").
COUNT_STATEMENTS = frozenset({"INSERT", "UPDATE", "DELETE", "REPLACE", "MERGE", "UPSERT", "LOAD", "COPY", "IMPORT"})
_TIMEOUT_ERRNOS = frozenset({1969, 3024})  # MariaDB max_statement_time, MySQL max_execution_time
_TIMEOUT_RE = re.compile(
    r"max_statement_time|maximum statement execution time|statement timeout|canceling statement", re.IGNORECASE
)


def _leading_keyword(statement: sqltree.Statement) -> str | None:
    """First keyword of a statement: comments are skipped, leading parentheses and groups entered."""
    tok = statement.token_first(skip_cm=True)
    while isinstance(tok, sqltree.TokenList):
        if isinstance(tok, sqltree.Parenthesis):
            _, tok = tok.token_next(0, skip_ws=True, skip_cm=True)
        else:
            tok = tok.token_first(skip_cm=True)
    if tok is None or tok.ttype not in T.Keyword:
        return None
    return tok.normalized.upper()


def _is_blank(statement: sqltree.Statement) -> bool:
    for tok in statement.flatten():
        if tok.is_whitespace or tok.ttype in T.Comment:
            continue
        if tok.ttype is T.Punctuation and tok.value == ";":
            continue
        return False
    return True


def split_sql(query: str) -> list[str]:
    """Splits a script into statements (`;` inside strings and comments is respected). Chunks that
    hold only comments or semicolons are dropped; the statements keep their text as written."""
    statements = []
    for chunk in sqlparse.split(query):
        text = chunk.strip()
        if not text:
            continue
        parsed = sqlparse.parse(text)
        if not parsed or _is_blank(parsed[0]):
            continue
        statements.append(text)
    return statements


def sql_is_read_only(statements: Iterable[str]) -> bool:
    """True when every statement starts with a read-only keyword and (except `SHOW ...`) contains no
    writing keyword outside strings and comments."""
    for text in statements:
        parsed = sqlparse.parse(text)
        if not parsed:
            return False
        first = _leading_keyword(parsed[0])
        if first not in READ_ONLY_STARTS:
            return False
        if first == "SHOW":
            continue
        for tok in parsed[0].flatten():
            if tok.ttype in T.Keyword and tok.normalized.upper() in WRITE_KEYWORDS:
                return False
    return True


def _is_timeout(exc: BaseException) -> bool:
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], int) and args[0] in _TIMEOUT_ERRNOS:
        return True
    if getattr(exc, "sqlstate", None) == "57014":  # PostgreSQL query_canceled
        return True
    return bool(_TIMEOUT_RE.search(str(exc)))


def _statement_error(exc: BaseException, secret_values: list[str | None]) -> dict:
    orig = getattr(exc, "orig", None) or exc
    code = "query_timeout" if _is_timeout(orig) else "query_failed"
    return {"code": code, "message": connections.redact(_error_text(orig), secret_values)}


def _timeout_statement(engine_name: str, seconds: int) -> str | None:
    # `seconds` is a validated integer of our own, never user input.
    if engine_name == "mariadb":
        return f"SET SESSION max_statement_time = {int(seconds)}"
    if engine_name == "mysql":
        return f"SET SESSION max_execution_time = {int(seconds) * 1000}"
    if engine_name == "postgresql":
        return f"SET statement_timeout = {int(seconds) * 1000}"
    return None


def _first_keyword(statement: str) -> str | None:
    parsed = sqlparse.parse(statement)
    return _leading_keyword(parsed[0]) if parsed else None


def _run_statement(conn: Any, statement: str, *, max_rows: int, streaming: bool, last: bool, secret_values) -> dict:
    started = time.monotonic()
    entry: dict[str, Any] = {"statement": statement}
    # `no_parameters`: the driver gets `cursor.execute(statement)` with no (empty) parameter set, so
    # PyMySQL and psycopg leave percent signs alone (`LIKE 'x%'`) - the text reaches the server as given.
    options: dict[str, Any] = {"no_parameters": True}
    if streaming:
        options["stream_results"] = True
    try:
        result = conn.exec_driver_sql(statement, execution_options=options)
        if result.returns_rows:
            columns = [str(c) for c in result.keys()]
            fetched = result.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            rows = [[encode_value(v) for v in row] for row in fetched[:max_rows]]
            entry.update(type="rows", columns=columns, rows=rows, row_count=len(rows), truncated=truncated)
            # A truncated last result is not drained: the connection is invalidated right after.
            if not (truncated and last):
                result.close()
        else:
            rowcount = result.rowcount
            result.close()
            counted = rowcount is not None and rowcount >= 0
            if counted and (rowcount > 0 or _first_keyword(statement) in COUNT_STATEMENTS):
                entry.update(type="count", affected_rows=int(rowcount))
            else:
                entry.update(type="empty")
    except Exception as exc:  # noqa: BLE001 - SQLAlchemy wraps DBAPI errors, drivers raise others
        entry.update(type="error", error=_statement_error(exc, secret_values))
    entry["duration_ms"] = _ms(started)
    return entry


def run_sql(
    engine_name: str, engine: Engine, query: str, *, max_rows: int, timeout_seconds: int, read_only: bool
) -> dict:
    """Runs a SQL script; see the module docstring and docs/QUERY_CONSOLE.md for the result shape."""
    statements = split_sql(query)
    if not statements:
        raise ApiError(422, "validation_error", "The query contains no SQL statement")
    if read_only and not sql_is_read_only(statements):
        raise _read_only_refused("sql")
    max_rows = _clamp(max_rows, MAX_ROWS, DEFAULT_MAX_ROWS)
    timeout_seconds = _clamp(timeout_seconds, MAX_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS)
    secret_values = [engine.url.password]
    # PyMySQL streams rows (unbuffered cursor) so `SELECT * FROM huge` costs `max_rows + 1` rows of
    # memory; psycopg and sqlite fetch client-side (use LIMIT).
    streaming = engine.dialect.name == "mysql"
    started = time.monotonic()
    try:
        conn = engine.connect()
    except Exception as exc:  # noqa: BLE001 - driver connect errors vary widely
        orig = getattr(exc, "orig", None) or exc
        message = connections.redact(_error_text(orig), secret_values)
        raise ApiError(503, "database_unavailable", f"Cannot connect to the database: {message}") from exc
    results: list[dict] = []
    try:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        timeout_sql = _timeout_statement(engine_name, timeout_seconds)
        if timeout_sql and engine.dialect.name in ("mysql", "postgresql"):
            try:
                conn.exec_driver_sql(timeout_sql)
            except Exception:  # noqa: BLE001 - best effort (privileges, older servers)
                pass
        for index, statement in enumerate(statements):
            entry = _run_statement(
                conn,
                statement,
                max_rows=max_rows,
                streaming=streaming,
                last=index == len(statements) - 1,
                secret_values=secret_values,
            )
            results.append(entry)
            if entry["type"] == "error":
                break
    finally:
        # Drop the DBAPI connection: session state set by the script must not reach other requests.
        try:
            conn.invalidate()
        except Exception:  # noqa: BLE001
            pass
        conn.close()
    return {"kind": "sql", "engine": engine_name, "duration_ms": _ms(started), "results": results}


# =============================================================================================
# MongoDB (mongosh)
# =============================================================================================

# Method / global names viewers may not use (docs/QUERY_CONSOLE.md), matched as whole identifiers
# anywhere in the code, strings and comments included (over-matching is the safe direction).
MONGO_WRITE_NAMES = (
    "insert",
    "insertOne",
    "insertMany",
    "update",
    "updateOne",
    "updateMany",
    "replaceOne",
    "delete",
    "deleteOne",
    "deleteMany",
    "remove",
    "save",
    "drop",
    "dropDatabase",
    "dropIndex",
    "dropIndexes",
    "createCollection",
    "createIndex",
    "createIndexes",
    "createView",
    "renameCollection",
    "convertToCapped",
    "reIndex",
    "bulkWrite",
    "findOneAndUpdate",
    "findOneAndReplace",
    "findOneAndDelete",
    "findAndModify",
    "mapReduce",
    "$out",
    "$merge",
    "runCommand",
    "adminCommand",
    "createUser",
    "updateUser",
    "dropUser",
    "createRole",
    "getSiblingDB",
    "getMongo",
    "load",
    "require",
    "process",
    "fs",
    "child_process",
    "eval",
    "Function",
    "constructor",
    "globalThis",
    "Reflect",
    "import",
)
_MONGO_WRITE_RE = re.compile(r"(?<![\w$])(?:" + "|".join(re.escape(n) for n in MONGO_WRITE_NAMES) + r")(?![\w$])")
_MONGO_URI_RE = re.compile(r"^(mongodb(?:\+srv)?://[^/?]*)(/[^?]*)?(\?.*)?$")
_shells = threading.BoundedSemaphore(MAX_SHELLS)

# The wrapper passed with `--eval` (docs/QUERY_CONSOLE.md). Everything variable comes from the
# environment; it is deleted before the user's code runs. The user's code is evaluated through the
# shell's own evaluator (`MongoshNodeRepl.loadExternalCode`, what `load()` uses, so the async
# rewriter applies) and the raw result is turned into its printable form with the shell's
# `asPrintable` hook - for cursors that is the first `displayBatchSize` documents. An async IIFE
# because `--eval` scripts may not use top-level `await`; the shell awaits a Promise result before
# it prints (nothing, for undefined) and exits. Verified against mongosh 2.11.1
# (tests/integration/test_query_console.py).
WRAPPER_JS = """(async () => {
  const env = process.env;
  const marker = String(env.DEPLOYER_QUERY_MARKER || "");
  const emit = (obj) => { process.stdout.write(marker + EJSON.stringify(obj, { relaxed: true }) + "\\n"); };
  const describe = (e) => ({
    name: e && e.name ? String(e.name) : "Error",
    message: e && e.message !== undefined ? String(e.message) : String(e),
    code: e && e.code !== undefined ? e.code : null,
    codeName: e && e.codeName ? String(e.codeName) : null,
  });
  const file = env.DEPLOYER_QUERY_FILE;
  const uri = env.DEPLOYER_QUERY_URI;
  const dbName = env.DEPLOYER_QUERY_DB;
  const batch = parseInt(env.DEPLOYER_QUERY_BATCH, 10);
  delete env.DEPLOYER_QUERY_URI;
  delete env.DEPLOYER_QUERY_FILE;
  delete env.DEPLOYER_QUERY_MARKER;
  let code = null;
  let connected = false;
  try {
    code = require("fs").readFileSync(file, "utf8");
    await config.set("displayBatchSize", batch);
    db = (await connect(uri)).getSiblingDB(dbName);
    connected = true;
  } catch (e) {
    emit({ phase: "connect", error: describe(e) });
  }
  if (connected) {
    const listener = db.getMongo()._instanceState.evaluationListener;
    try {
      let raw = await listener.loadExternalCode(code, "@(query)");
      if (raw !== null && raw !== undefined && typeof raw.then === "function") raw = await raw;
      const asPrintable = Symbol.for("@@mongosh.asPrintable");
      let value = raw;
      if (raw !== null && raw !== undefined && (typeof raw === "object" || typeof raw === "function")
          && typeof raw[asPrintable] === "function") {
        value = await raw[asPrintable]();
      }
      if (value !== null && typeof value === "object" && !Array.isArray(value)
          && Array.isArray(value.documents) && typeof value.cursorHasMore === "boolean") {
        value = value.documents;  // CursorIterationResult: the first batch of a cursor
      }
      emit({ phase: "done", value: value === undefined ? null : value });
    } catch (e) {
      emit({ phase: "error", error: describe(e) });
    }
  }
})();
"""


def mongo_is_read_only(code: str) -> bool:
    return _MONGO_WRITE_RE.search(code) is None


def mongosh_command() -> list[str] | None:
    """The mongosh executable as an argv prefix, or None when it is not installed (tests replace it)."""
    path = shutil.which("mongosh")
    return [path] if path else None


@dataclass
class ProcessOutcome:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_capped: bool
    duration_ms: int


def _kill(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except OSError:
        pass


def _run_process(args: list[str], env: dict[str, str], timeout_seconds: int, cwd: str) -> ProcessOutcome:
    """Runs the shell with a hard timeout (kill) and output caps (kill when exceeded)."""
    started = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
        )
    except OSError as exc:
        raise ApiError(501, "mongosh_unavailable", f"The MongoDB shell could not be started: {exc}") from exc
    capped = threading.Event()

    def pump(stream: Any, limit: int, sink: list[bytes]) -> None:
        total = 0
        try:
            while True:
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    return
                if total < limit:
                    sink.append(chunk[: limit - total])
                total += len(chunk)
                if total > limit and not capped.is_set():
                    capped.set()
                    _kill(proc)
        except OSError:
            return

    out: list[bytes] = []
    err: list[bytes] = []
    threads = [
        threading.Thread(target=pump, args=(proc.stdout, MAX_SHELL_STDOUT, out), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, MAX_SHELL_STDERR, err), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(proc)
            proc.wait()
        for thread in threads:
            thread.join(timeout=5)
    finally:
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
    return ProcessOutcome(proc.returncode, b"".join(out), b"".join(err), timed_out, capped.is_set(), _ms(started))


def _connect_uri(uri: str) -> str:
    """Adds short connect / server-selection timeouts (unless the URI sets its own) so an unreachable
    server is reported as `database_unavailable` well before the query timeout."""
    m = _MONGO_URI_RE.match(uri.strip())
    if not m:
        return uri
    base, path, query = m.groups()
    query = (query or "?")[1:]
    extra = []
    if not re.search(r"(^|&)serverselectiontimeoutms=", query, re.IGNORECASE):
        extra.append(f"serverSelectionTimeoutMS={CONNECT_TIMEOUT_MS}")
    if not re.search(r"(^|&)connecttimeoutms=", query, re.IGNORECASE):
        extra.append(f"connectTimeoutMS={CONNECT_TIMEOUT_MS}")
    if not extra:
        return uri
    return f"{base}{path or '/'}?{query + '&' if query else ''}{'&'.join(extra)}"


def _child_env(home: str, values: dict[str, str]) -> dict[str, str]:
    """A minimal environment: the API's own variables (MASTER_KEY, root passwords...) never reach the
    shell, where user code could read them through `process.env`."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": home,
        "TMPDIR": home,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        **values,
    }
    if os.name == "nt":  # development on Windows: python (fake shell) and Node resolve their home from these
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env.update(USERPROFILE=home, APPDATA=home, LOCALAPPDATA=home, TEMP=home, TMP=home)
    return env


def parse_shell_output(stdout: str, marker: str) -> tuple[str, dict | None]:
    """Separates the text the script printed from the wrapper's report (the last marker line)."""
    text: list[str] = []
    report: dict | None = None
    for line in stdout.splitlines(keepends=True):
        if line.startswith(marker):
            try:
                parsed = json.loads(line[len(marker) :])
            except ValueError:
                parsed = None
            report = parsed if isinstance(parsed, dict) else None
            continue
        text.append(line)
    return "".join(text), report


def _first_line(*texts: str) -> str:
    for text in texts:
        for line in text.splitlines():
            if line.strip():
                return line.strip()
    return ""


def _shell_error_message(error: Any) -> str:
    if not isinstance(error, dict):
        return "Unknown error"
    name = str(error.get("name") or "Error")
    message = str(error.get("message") or "")
    text = f"{name}: {message}" if message else name
    if error.get("codeName"):
        text += f" [{error['codeName']}]"
    return text


def run_mongosh(
    config: dict[str, Any], database: str, query: str, *, max_rows: int, timeout_seconds: int, read_only: bool
) -> dict:
    """Runs MongoDB shell code in `mongosh`; see the module docstring and docs/QUERY_CONSOLE.md."""
    if read_only and not mongo_is_read_only(query):
        raise _read_only_refused("nosql")
    command = mongosh_command()
    if not command:
        message = "The MongoDB shell (mongosh) is not installed in this Deployer image"
        raise ApiError(501, "mongosh_unavailable", message)
    uri = str(config.get("uri") or "")
    if not uri:
        raise ApiError(503, "database_unavailable", "This data source has no connection URI")
    max_rows = _clamp(max_rows, MAX_ROWS, DEFAULT_MAX_ROWS)
    timeout_seconds = _clamp(timeout_seconds, MAX_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS)
    secret_values = [config.get("password"), connections.mongo_uri_password(uri)]
    marker = f"@@deployer:{secrets.token_hex(12)}@@"
    if not _shells.acquire(blocking=False):
        raise ApiError(429, "too_many_queries", "Too many MongoDB shell queries are running; try again in a moment")
    try:
        with tempfile.TemporaryDirectory(prefix="deployer-query-", ignore_cleanup_errors=True) as home:
            code_path = os.path.join(home, "query.js")
            fd = os.open(code_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(query)
            env = _child_env(
                home,
                {
                    "DEPLOYER_QUERY_URI": _connect_uri(uri),
                    "DEPLOYER_QUERY_DB": database,
                    "DEPLOYER_QUERY_FILE": code_path,
                    "DEPLOYER_QUERY_MARKER": marker,
                    "DEPLOYER_QUERY_BATCH": str(max_rows + 1),
                },
            )
            args = [*command, "--nodb", "--quiet", "--norc", "--eval", WRAPPER_JS]
            outcome = _run_process(args, env, timeout_seconds, home)
    finally:
        _shells.release()
    if outcome.timed_out:
        raise ApiError(504, "query_timeout", f"The MongoDB shell was stopped after {timeout_seconds} s")
    # Everything the shell wrote is redacted before parsing: printed text, errors and the result
    # itself (`db._mongo` would show the connection string).
    stdout = outcome.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
    stderr = outcome.stderr.decode("utf-8", "replace").replace("\r\n", "\n")
    stdout = connections.redact(stdout, secret_values, limit=None)
    stderr = connections.redact(stderr, secret_values, limit=None)
    text, report = parse_shell_output(stdout, marker)
    error: dict | None = None
    value: Any = None
    if report is None:
        if outcome.output_capped:
            detail = "The shell printed more than 8 MiB and was stopped"
        else:
            detail = _first_line(stderr) or f"The shell exited with status {outcome.returncode} without a result"
        error = {"code": "query_failed", "message": connections.redact(detail, secret_values)}
    elif report.get("phase") == "connect":
        detail = connections.redact(_shell_error_message(report.get("error")), secret_values)
        raise ApiError(503, "database_unavailable", f"Cannot connect to MongoDB: {detail}")
    elif report.get("phase") == "error":
        detail = connections.redact(_shell_error_message(report.get("error")), secret_values)
        error = {"code": "query_failed", "message": detail}
    else:
        value = report.get("value")
    output = text.rstrip("\n")
    if stderr.strip():
        output = (output + "\n" if output else "") + stderr.rstrip("\n")
    truncated = False
    docs: list | None = None
    if isinstance(value, list):
        if len(value) > max_rows:
            value = value[:max_rows]
            truncated = True
        if all(isinstance(doc, dict) for doc in value):
            docs = value
    return {
        "kind": "nosql",
        "engine": "mongodb",
        "duration_ms": outcome.duration_ms,
        "output": output,
        "result": value,
        "result_docs": docs,
        "truncated": truncated,
        "error": error,
    }


# =============================================================================================
# entry points
# =============================================================================================


def run_query(ds: DataSource, query: str, *, max_rows: int, timeout_seconds: int, read_only: bool) -> dict:
    """Runs `query` against a data source reachable from this process (source_ops op `query`)."""
    if ds.kind == "sql":
        return run_sql(
            ds.engine,
            connections.get_sql_engine(ds),
            query,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
            read_only=read_only,
        )
    config = connections.load_config(ds)
    return run_mongosh(
        config,
        str(config.get("database") or ds.database_name),
        query,
        max_rows=max_rows,
        timeout_seconds=timeout_seconds,
        read_only=read_only,
    )


def summarize(result: dict) -> tuple[bool, int]:
    """`(ok, statement count)` of a console result for the audit log (never the text or the rows)."""
    if result.get("kind") == "sql":
        results = result.get("results") or []
        return all(r.get("type") != "error" for r in results), len(results)
    return result.get("error") is None, 1
