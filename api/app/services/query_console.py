"""Query console (docs/QUERY_CONSOLE.md): SQL scripts against SQL data sources and MongoDB shell
code against NoSQL data sources.

- SQL: statements are split with `sqlparse` (strings and comments respected) and run one after the
  other on a single autocommit connection; execution stops at the first error. The user's SQL runs
  as given (`exec_driver_sql`), nothing is ever interpolated into it, and the connection is
  invalidated afterwards so session state (`SET`, `USE`, temp tables, statement timeouts) never
  leaks back into the shared pool.
- MongoDB: the code runs in a real `mongosh` process in the `query-shell` sidecar container, which
  holds no Deployer secrets (app/shell_runner.py; this process only sends it the source's connection
  string, database name, code and limits over HTTP). The sidecar's wrapper (`WRAPPER_JS`) connects
  with the source's own credentials, evaluates the user's code and prints one marker-prefixed
  relaxed Extended JSON line with the result; this module parses and redacts what comes back.
- Every role: MongoDB code may not name Node.js escape hatches (`MONGO_ESCAPE_NAMES`).
- Read-only role (viewers): statements / code must pass the textual classifiers below. They are
  best effort by design (`db.items["insert" + "One"]` slips through). SQL runs are also put in the
  database's own read-only mode (`READ_ONLY_SESSION`) and refused (503) when that cannot be set;
  MongoDB has no such mode, so there the database user of the source is the real boundary.
- Query text and results never go to logs or audit entries (routers/query.py records counts only).
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from collections.abc import Iterable
from typing import Any

import httpx
import sqlparse
from sqlalchemy import Engine
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlparse import sql as sqltree
from sqlparse import tokens as T

from app.config import get_settings
from app.errors import ApiError
from app.models import DataSource
from app.services import connections
from app.services.data_browser import encode_value

MAX_QUERY_CHARS = 200_000
DEFAULT_MAX_ROWS = 500
MAX_ROWS = 5000
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120
SHELL_HTTP_MARGIN = 15  # seconds the sidecar gets past the query timeout to kill, clean up and answer
CONNECT_TIMEOUT_MS = 5000


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _clamp(value: Any, maximum: int, default: int) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


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
# Functions with side effects that a read-only statement may not call (matched as names outside
# strings and comments, schema-qualified or quoted too). Sequence writes also fail in the read-only
# session below; the others (killing the app's connections, `set_config`, dblink's second
# connection) are not stopped by a read-only transaction.
WRITE_FUNCTIONS = frozenset(
    {
        "setval",
        "nextval",
        "set_config",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_notify",
        "dblink",
        "dblink_exec",
    }
)
# The database-level read-only mode for read-only runs, by SQLAlchemy dialect. PostgreSQL also runs
# the whole script in one READ ONLY transaction: its session default alone could be switched back
# mid-script (`set_config('default_transaction_read_only', ...)` from a function we do not know).
READ_ONLY_SESSION = {
    "mysql": ("SET SESSION TRANSACTION READ ONLY",),
    "postgresql": ("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY", "START TRANSACTION READ ONLY"),
    "sqlite": ("PRAGMA query_only = ON",),
}
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


SQL_READ_ONLY_STARTS_TEXT = "SELECT, WITH, SHOW, EXPLAIN, DESCRIBE, TABLE, VALUES"


def sql_read_only_refusal(statements: Iterable[str]) -> str | None:
    """Why a viewer may not run this script, naming the word that tripped the check (None = allowed).
    Every statement must start with a read-only keyword and (except `SHOW ...`) contain no writing
    keyword or side-effecting function name outside strings and comments."""
    for text in statements:
        parsed = sqlparse.parse(text)
        first = _leading_keyword(parsed[0]) if parsed else None
        if first not in READ_ONLY_STARTS:
            start = f"starts with `{first}`" if first else "does not start with one of them"
            return f"Viewers can only run read-only SQL ({SQL_READ_ONLY_STARTS_TEXT}); this statement {start}"
        if first == "SHOW":
            continue
        for tok in parsed[0].flatten():
            if tok.ttype in T.Keyword and tok.normalized.upper() in WRITE_KEYWORDS:
                return (
                    f"`{tok.value}` looks like a write command, so viewers cannot run this statement. "
                    'If it is a column or table name, quote it (`name` on MariaDB/MySQL, "name" on PostgreSQL)'
                )
            name = tok.value.strip('"`')
            if tok.ttype in (T.Name, T.String.Symbol) and name.lower() in WRITE_FUNCTIONS:
                return f"`{name}` changes data or the server, so viewers cannot call it"
    return None


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


def _canceller(engine: Engine, conn: Any) -> Any:
    """A callable that stops the statement running on `conn` from another thread (None = no way to).
    It backs up the server-side timeouts, which MySQL applies to SELECT only and which are skipped
    when the `SET` fails (privileges, MySQL-only variable on MariaDB or the other way round)."""
    raw = conn.connection.dbapi_connection
    dialect = engine.dialect.name
    if dialect == "postgresql":
        return raw.cancel
    if dialect == "sqlite":
        return raw.interrupt
    if dialect != "mysql":
        return None
    thread_id = int(raw.thread_id())

    def kill() -> None:
        # A private pool with the engine's own connect settings: the shared pool may be busy.
        pool = engine.pool.recreate()
        try:
            killer = pool.connect()
            try:
                killer.cursor().execute(f"KILL QUERY {thread_id}")
            finally:
                killer.invalidate()
        finally:
            pool.dispose()

    return kill


class _Watchdog:
    """Calls `cancel` once when a statement outlives `seconds`, unless it finished first."""

    def __init__(self, cancel: Any, seconds: int) -> None:
        self.cancel = cancel
        self.fired = False
        self.done = False
        self.lock = threading.Lock()
        self.timer = threading.Timer(seconds, self._fire)
        self.timer.daemon = True

    def _fire(self) -> None:
        with self.lock:
            if self.done:
                return
            self.fired = True
            try:
                self.cancel()
            except Exception:  # noqa: BLE001 - the driver's read timeout stays as the last bound
                pass

    def __enter__(self) -> _Watchdog:
        if self.cancel:
            self.timer.start()
        return self

    def __exit__(self, *exc: object) -> None:
        with self.lock:
            self.done = True
        self.timer.cancel()


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


def _enter_read_only(conn: Any, dialect: str, secret_values: list[str | None]) -> None:
    """Puts the console connection in the database's read-only mode; fails closed (503) when the
    dialect has none or the server refuses it, so a viewer's script never runs with write access."""
    statements = READ_ONLY_SESSION.get(dialect)
    if not statements:
        raise ApiError(503, "read_only_unavailable", f"Read-only mode is not supported for {dialect} sources")
    try:
        for statement in statements:
            conn.exec_driver_sql(statement)
    except Exception as exc:  # noqa: BLE001 - driver errors vary widely
        orig = getattr(exc, "orig", None) or exc
        message = connections.redact(_error_text(orig), secret_values)
        raise ApiError(
            503, "read_only_unavailable", f"Cannot switch the database to read-only mode: {message}"
        ) from exc


def run_sql(
    engine_name: str, engine: Engine, query: str, *, max_rows: int, timeout_seconds: int, read_only: bool
) -> dict:
    """Runs a SQL script; see the module docstring and docs/QUERY_CONSOLE.md for the result shape."""
    statements = split_sql(query)
    if not statements:
        raise ApiError(422, "validation_error", "The query contains no SQL statement")
    refusal = sql_read_only_refusal(statements) if read_only else None
    if refusal:
        raise ApiError(403, "read_only_role", refusal)
    max_rows = _clamp(max_rows, MAX_ROWS, DEFAULT_MAX_ROWS)
    timeout_seconds = _clamp(timeout_seconds, MAX_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS)
    secret_values = [engine.url.password]
    # PyMySQL streams rows (unbuffered cursor) so `SELECT * FROM huge` costs `max_rows + 1` rows of
    # memory; psycopg and sqlite fetch client-side (use LIMIT).
    streaming = engine.dialect.name == "mysql"
    started = time.monotonic()
    try:
        conn = engine.connect()
    except PoolTimeoutError as exc:
        # The source's pool (shared with the data browser) is full of running queries: busy, not down.
        raise ApiError(
            429, "too_many_queries", "Too many queries are running on this database; try again in a moment"
        ) from exc
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
            except Exception:  # noqa: BLE001 - the watchdog below enforces the timeout anyway
                pass
        if read_only:
            _enter_read_only(conn, engine.dialect.name, secret_values)
        cancel = _canceller(engine, conn)
        for index, statement in enumerate(statements):
            with _Watchdog(cancel, timeout_seconds) as watchdog:
                entry = _run_statement(
                    conn,
                    statement,
                    max_rows=max_rows,
                    streaming=streaming,
                    last=index == len(statements) - 1,
                    secret_values=secret_values,
                )
            # A statement that finished as the timer fired keeps its result: it did run (and commit).
            if watchdog.fired and entry["type"] == "error":
                message = f"The statement was stopped after {timeout_seconds} s"
                error = {"code": "query_timeout", "message": message}
                entry = {"statement": statement, "type": "error", "error": error, "duration_ms": entry["duration_ms"]}
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
    "ensureIndex",
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
    "removeOne",
    "initializeOrderedBulkOp",
    "initializeUnorderedBulkOp",
    "hideIndex",
    "unhideIndex",
    "createSearchIndex",
    "createSearchIndexes",
    "updateSearchIndex",
    "dropSearchIndex",
    "createEncryptedCollection",
    "compactStructuredEncryptionData",
    "configureQueryAnalyzer",
    # users and roles (the managed user is dbOwner, so these work on the project's database)
    "createUser",
    "updateUser",
    "dropUser",
    "dropAllUsers",
    "changeUserPassword",
    "grantRolesToUser",
    "revokeRolesFromUser",
    "createRole",
    "updateRole",
    "dropRole",
    "dropAllRoles",
    "grantRolesToRole",
    "revokeRolesFromRole",
    "grantPrivilegesToRole",
    "revokePrivilegesFromRole",
    # server administration helpers and the replica set / sharding / stream processing globals
    "shutdownServer",
    "fsyncLock",
    "fsyncUnlock",
    "killOp",
    "setProfilingLevel",
    "setLogLevel",
    "rotateCertificates",
    "enableFreeMonitoring",
    "disableFreeMonitoring",
    "rs",
    "sh",
    "sp",
    # other databases, connections and the shell internals behind them (raw driver access)
    "getSiblingDB",
    "getMongo",
    "Mongo",
    "connect",
    "_mongo",
    "_serviceProvider",
    "_instanceState",
    "_runCommand",
    "_runAdminCommand",
    "_runReadCommand",
    "_runAdminReadCommand",
    "_runCursorCommand",
    "_runAdminCursorCommand",
)
# Node.js escape hatches refused for EVERY role (SECURITY.md "Query console"). Same matching as above.
# Best effort (string building, `this["req" + "uire"]`, gets through): the boundary is the query-shell
# sidecar, which has no secrets, volumes or Docker socket and runs each shell under its own uid.
MONGO_ESCAPE_NAMES = (
    "require",
    "process",
    "child_process",
    "fs",
    "module",
    "global",
    "globalThis",
    "eval",
    "Function",
    "constructor",
    "Reflect",
    "import",
    "load",
    "snippet",
)


def _names_re(names: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"(?<![\w$])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w$])")


_MONGO_WRITE_RE = _names_re(MONGO_WRITE_NAMES + MONGO_ESCAPE_NAMES)
_MONGO_ESCAPE_RE = _names_re(MONGO_ESCAPE_NAMES)
_MONGO_URI_RE = re.compile(r"^(mongodb(?:\+srv)?://[^/?]*)(/[^?]*)?(\?.*)?$")


def mongo_read_only_refusal(code: str) -> str | None:
    """Why a viewer may not run this code, naming the matched write name (None = allowed)."""
    match = _MONGO_WRITE_RE.search(code)
    if match is None:
        return None
    return (
        f"`{match.group()}` is a write or admin command, so viewers cannot run this code "
        "(the check also matches inside strings and comments, e.g. a field value)"
    )


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


def _call_shell(shell_url: str, payload: dict, timeout_seconds: int) -> dict:
    """Runs the code in the query-shell sidecar (app/shell_runner.py); its refusals keep their status
    and code (429 too_many_queries, 501 mongosh_unavailable)."""
    try:
        resp = httpx.post(
            shell_url.rstrip("/") + "/run", json=payload, timeout=timeout_seconds + SHELL_HTTP_MARGIN, trust_env=False
        )
    except httpx.HTTPError as exc:
        message = f"The MongoDB shell service (query-shell) is not reachable: {type(exc).__name__}"
        raise ApiError(503, "mongosh_unavailable", message) from exc
    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise ApiError(502, "mongosh_unavailable", f"The MongoDB shell service answered {resp.status_code}")
    if resp.status_code != 200:
        raise ApiError(resp.status_code, str(body.get("code")), str(body.get("message")))
    if body.get("timed_out") is None:
        raise ApiError(502, "mongosh_unavailable", "The MongoDB shell service sent a malformed answer")
    return body


def run_mongosh(
    config: dict[str, Any], database: str, query: str, *, max_rows: int, timeout_seconds: int, read_only: bool
) -> dict:
    """Runs MongoDB shell code in `mongosh`; see the module docstring and docs/QUERY_CONSOLE.md."""
    escape = _MONGO_ESCAPE_RE.search(query)
    if escape:
        message = (
            f"MongoDB shell code may not use `{escape.group()}` (Node.js access is blocked for every role, "
            "also inside strings and comments)"
        )
        raise ApiError(403, "shell_code_refused", message)
    refusal = mongo_read_only_refusal(query) if read_only else None
    if refusal:
        raise ApiError(403, "read_only_role", refusal)
    shell_url = get_settings().query_shell_url
    if not shell_url:
        message = "The MongoDB shell service (query-shell) is not configured on this Deployer"
        raise ApiError(501, "mongosh_unavailable", message)
    uri = str(config.get("uri") or "")
    if not uri:
        raise ApiError(503, "database_unavailable", "This data source has no connection URI")
    max_rows = _clamp(max_rows, MAX_ROWS, DEFAULT_MAX_ROWS)
    timeout_seconds = _clamp(timeout_seconds, MAX_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS)
    secret_values = [config.get("password"), connections.mongo_uri_password(uri)]
    marker = f"@@deployer:{secrets.token_hex(12)}@@"
    payload = {
        "uri": _connect_uri(uri),
        "database": database,
        "code": query,
        "marker": marker,
        "batch": max_rows + 1,
        "timeout_seconds": timeout_seconds,
    }
    outcome = _call_shell(shell_url, payload, timeout_seconds)
    if outcome["timed_out"]:
        raise ApiError(504, "query_timeout", f"The MongoDB shell was stopped after {timeout_seconds} s")
    # Everything the shell wrote is redacted before parsing: printed text, errors and the result
    # itself (`db._mongo` would show the connection string).
    stdout = str(outcome["stdout"]).replace("\r\n", "\n")
    stderr = str(outcome["stderr"]).replace("\r\n", "\n")
    stdout = connections.redact(stdout, secret_values, limit=None)
    stderr = connections.redact(stderr, secret_values, limit=None)
    text, report = parse_shell_output(stdout, marker)
    error: dict | None = None
    value: Any = None
    if report is None:
        if outcome.get("output_capped"):
            detail = (
                "The shell printed more than 8 MiB and was stopped. Add .limit(20) or a projection "
                "to the query, or pick fewer rows"
            )
        else:
            detail = _first_line(stderr) or f"The shell exited with status {outcome.get('returncode')} without a result"
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
        "duration_ms": int(outcome.get("duration_ms") or 0),
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
    if (adapter := connections.cloud_engine(ds.engine)) is not None:  # one JSON request (QUERY_CONSOLE.md)
        return adapter.run_console(
            ds, query, max_rows=_clamp(max_rows, MAX_ROWS, DEFAULT_MAX_ROWS), read_only=read_only
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
