"""Query console against real servers (docs/QUERY_CONSOLE.md).

- SQL: a throwaway MariaDB 11, e.g. `docker run -d --rm -p 127.0.0.1:33071:3306 -e MARIADB_ROOT_PASSWORD=... mariadb:11`
  and `DEPLOYER_IT_MARIADB_URL=mysql://root:<password>@127.0.0.1:33071` (runs from the venv).
- MongoDB: needs a `mongo:8.0` container and a query-shell sidecar on one network, the sidecar started
  from the API image like the `query-shell` service of deploy/docker-compose.yml (root, capabilities
  dropped, `python -m app.shell_runner`; .github/workflows/ci.yml):
  `QUERY_SHELL_URL=http://query-shell:8090` and
  `DEPLOYER_IT_MONGO_URI=mongodb://admin:<password>@mongo-host:27017/?authSource=admin`.

Each part is skipped unless its URL is set. The tests create and drop their own database.
"""

import json
import os
import re
import time
from urllib.parse import unquote, urlsplit

import pytest

from app import shell_runner
from app.config import get_settings
from app.errors import ApiError
from app.services import connections, query_console

MARIADB_URL = os.environ.get("DEPLOYER_IT_MARIADB_URL")
MONGO_URI = os.environ.get("DEPLOYER_IT_MONGO_URI")
DATABASE = "deployer_query_it"


def run(engine, query, **kwargs):
    params = {"max_rows": 5, "timeout_seconds": 10, "read_only": False, **kwargs}
    return query_console.run_sql("mariadb", engine, query, **params)


# --- MariaDB -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mariadb():
    if not MARIADB_URL:
        pytest.skip("set DEPLOYER_IT_MARIADB_URL")
    parts = urlsplit(MARIADB_URL)
    base = {
        "host": parts.hostname,
        "port": parts.port or 3306,
        "username": unquote(parts.username or "root"),
        "password": unquote(parts.password or ""),
        "tls": False,
    }
    admin = connections.build_sql_engine("mariadb", {**base, "database": None}, pooled=False)
    with admin.connect() as conn:
        conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {DATABASE}")
        conn.exec_driver_sql(f"CREATE DATABASE {DATABASE}")
    engine = connections.build_sql_engine("mariadb", {**base, "database": DATABASE})
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {DATABASE}")
    admin.dispose()


def test_mariadb_multi_statement_script(mariadb):
    out = run(
        mariadb,
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(20), bin VARBINARY(4), price DECIMAL(6,2), d DATETIME);\n"
        "INSERT INTO t VALUES (1, 'x1', X'0001', 1.50, '2024-01-02 03:04:05'), (2, 'y2', NULL, NULL, NULL),\n"
        "  (3, 'x3', NULL, NULL, NULL);\n"
        "SELECT * FROM t ORDER BY id;\n"
        "UPDATE t SET name = CONCAT(name, '!') WHERE id > 1;\n"
        "SELECT name FROM t WHERE name LIKE 'x%' ORDER BY id;  -- percent signs are not format specifiers\n"
        "SHOW CREATE TABLE t;",
    )
    assert [r["type"] for r in out["results"]] == ["empty", "count", "rows", "count", "rows", "rows"]
    created, inserted, rows, updated, like, show = out["results"]
    assert inserted["affected_rows"] == 3 and updated["affected_rows"] == 2
    assert rows["columns"] == ["id", "name", "bin", "price", "d"] and rows["truncated"] is False
    assert rows["rows"][0] == [1, "x1", {"$base64": "AAE="}, "1.50", "2024-01-02T03:04:05"]
    assert like["rows"] == [["x1"], ["x3!"]]
    assert show["columns"] == ["Table", "Create Table"] and "CREATE TABLE" in show["rows"][0][1]


def test_mariadb_truncation_and_draining(mariadb):
    values = ",".join(f"({i})" for i in range(200))
    run(mariadb, "CREATE TABLE big (n INT PRIMARY KEY); INSERT INTO big VALUES " + values)
    out = run(mariadb, "SELECT n FROM big ORDER BY n; SELECT COUNT(*) FROM big; SELECT n FROM big", max_rows=4)
    first, count, last = out["results"]
    assert first["row_count"] == 4 and first["truncated"] is True and first["rows"] == [[0], [1], [2], [3]]
    assert count["rows"] == [[200]]  # the truncated first result was drained, the connection kept working
    assert last["truncated"] is True and last["row_count"] == 4
    # The invalidated connection does not break the pool: the next run works.
    assert run(mariadb, "SELECT 1")["results"][0]["rows"] == [[1]]


def test_mariadb_error_mid_way_keeps_earlier_results(mariadb):
    out = run(mariadb, "SELECT 1 AS a; SELEC 2; SELECT 3")
    assert [r["type"] for r in out["results"]] == ["rows", "error"]
    err = out["results"][1]["error"]
    assert err["code"] == "query_failed" and "SQL syntax" in err["message"] and "(error 1064)" in err["message"]


def test_mariadb_viewer_read_only(mariadb):
    with pytest.raises(ApiError) as err:
        run(mariadb, "INSERT INTO big VALUES (999)", read_only=True)
    assert err.value.code == "read_only_role"
    assert run(mariadb, "SELECT COUNT(*) FROM big WHERE n = 999", read_only=True)["results"][0]["rows"] == [[0]]


def test_mariadb_read_only_session(mariadb, monkeypatch):
    # Past the text classifier the server's READ ONLY session still refuses the write (error 1792).
    monkeypatch.setattr(query_console, "sql_read_only_refusal", lambda statements: None)
    out = run(mariadb, "INSERT INTO big VALUES (999)", read_only=True)
    assert out["results"][0]["type"] == "error" and "(error 1792)" in out["results"][0]["error"]["message"]


def test_mariadb_timeout(mariadb):
    started = time.monotonic()
    out = run(mariadb, "SELECT 1; SELECT SLEEP(5); SELECT 2", timeout_seconds=1)
    assert time.monotonic() - started < 4
    assert [r["type"] for r in out["results"]] == ["rows", "error"]
    assert out["results"][1]["error"]["code"] == "query_timeout"
    assert run(mariadb, "SELECT SLEEP(0.1)")["results"][0]["type"] == "rows"


def test_watchdog_kills_writes_when_the_server_timeout_is_missing(mariadb):
    # As "mysql" the SET (max_execution_time) fails on MariaDB and a write is not a SELECT anyway:
    # only the watchdog's KILL QUERY can stop it (A-034). Not `DO SLEEP(8)`: DO always reports OK and
    # a killed SLEEP returns 1, so the statement would count as finished.
    started = time.monotonic()
    out = query_console.run_sql(
        "mysql",
        mariadb,
        "CREATE TABLE killed AS SELECT a.seq FROM seq_1_to_100000 a, seq_1_to_100000 b WHERE a.seq + b.seq = 0;"
        " SELECT 2",
        max_rows=5,
        timeout_seconds=1,
        read_only=False,
    )
    assert time.monotonic() - started < 5
    assert [r["type"] for r in out["results"]] == ["error"]
    assert out["results"][0]["error"]["code"] == "query_timeout"
    assert run(mariadb, "SELECT 1")["results"][0]["type"] == "rows"


def test_mariadb_session_state_does_not_leak(mariadb):
    assert run(mariadb, "SET @x := 5; SELECT @x")["results"][-1]["rows"] == [[5]]
    assert run(mariadb, "SELECT @x")["results"][0]["rows"] == [[None]]


def test_mariadb_unavailable():
    if not MARIADB_URL:
        pytest.skip("set DEPLOYER_IT_MARIADB_URL")
    engine = connections.build_sql_engine(
        "mariadb", {"host": "127.0.0.1", "port": 1, "username": "u", "password": "p", "database": "x"}, pooled=False
    )
    with pytest.raises(ApiError) as err:
        run(engine, "SELECT 1")
    assert err.value.status_code == 503 and err.value.code == "database_unavailable"


# --- MongoDB (mongosh) ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mongo():
    if not MONGO_URI:
        pytest.skip("set DEPLOYER_IT_MONGO_URI")
    if not get_settings().query_shell_url:
        pytest.skip("set QUERY_SHELL_URL (a query-shell sidecar, see the module docstring)")
    config = {"uri": MONGO_URI, "database": DATABASE}
    yield config
    query_console.run_mongosh(config, DATABASE, "db.dropDatabase()", max_rows=5, timeout_seconds=30, read_only=False)


def sh(config, query, **kwargs):
    params = {"max_rows": 5, "timeout_seconds": 20, "read_only": False, **kwargs}
    return query_console.run_mongosh(config, DATABASE, query, **params)


def test_mongosh_writes_and_cursor_batches(mongo):
    out = sh(mongo, "db.items.drop(); db.items.insertMany([" + ",".join(f"{{n: {i}}}" for i in range(12)) + "])")
    assert out["error"] is None and out["result"]["acknowledged"] is True
    assert set(out["result"]["insertedIds"]) == {str(i) for i in range(12)}
    assert all("$oid" in v for v in out["result"]["insertedIds"].values())

    out = sh(mongo, "db.items.find({}, {_id: 0}).sort({n: 1})", max_rows=5)
    assert out["error"] is None and out["output"] == ""
    assert out["result"] == [{"n": i} for i in range(5)] and out["result_docs"] == out["result"]
    assert out["truncated"] is True

    out = sh(mongo, "db.items.find({n: {$lt: 3}}, {_id: 0}).sort({n: 1})", max_rows=5)
    assert out["result_docs"] == [{"n": 0}, {"n": 1}, {"n": 2}] and out["truncated"] is False

    doc = "{n: 99, when: new Date('2024-01-02T03:04:05Z'), big: Long('42'), dec: Decimal128('1.50')}"
    out = sh(mongo, f"db.items.insertOne({doc})")
    assert out["result"]["acknowledged"] is True and "$oid" in out["result"]["insertedId"]
    out = sh(mongo, "db.items.findOne({n: 99})")
    assert "$oid" in out["result"]["_id"] and out["result"]["when"] == {"$date": "2024-01-02T03:04:05Z"}
    assert out["result"]["big"] == 42 and out["result"]["dec"] == {"$numberDecimal": "1.50"}  # relaxed EJSON
    assert out["result_docs"] is None
    out = sh(mongo, "db.items.aggregate([{$match: {n: {$gte: 10}}}, {$project: {_id: 0, n: 1}}, {$sort: {n: 1}}])")
    assert out["result_docs"] == [{"n": 10}, {"n": 11}, {"n": 99}]
    assert sh(mongo, "db.items.countDocuments()")["result"] == 13
    assert sh(mongo, "show collections")["result"] == [{"name": "items", "badge": ""}]
    assert sh(mongo, "db")["result"] == DATABASE  # the script runs against the source's own database


def test_mongosh_print_output_and_undefined_result(mongo):
    out = sh(mongo, "print('hello'); print(42); printjson({a: 1}); console.log('cl'); var x = db.items.count()")
    assert out["error"] is None and out["result"] is None
    assert out["output"].splitlines() == [
        "hello",
        "42",
        "{",
        "  a: 1",
        "}",
        "cl",
        "DeprecationWarning: Collection.count() is deprecated. Use countDocuments or estimatedDocumentCount.",
    ]


def test_mongosh_errors(mongo):
    out = sh(mongo, "db.items.find({")
    assert out["result"] is None and out["error"]["code"] == "query_failed"
    assert out["error"]["message"].startswith("SyntaxError: Unexpected token (1:15)")
    out = sh(mongo, "print('before'); db.items.find({$bad: 1}).toArray()")
    assert out["output"] == "before"
    assert out["error"]["message"].startswith("MongoServerError: unknown top level operator: $bad")
    assert out["error"]["message"].endswith("[BadValue]")
    out = sh(mongo, "db.items.nope()")
    assert out["error"]["message"] == "TypeError: db.items.nope is not a function"


def test_mongosh_timeout(mongo):
    started = time.monotonic()
    with pytest.raises(ApiError) as err:
        sh(mongo, "sleep(60000)", timeout_seconds=2)
    assert err.value.status_code == 504 and err.value.code == "query_timeout"
    assert time.monotonic() - started < 6


def test_mongosh_runs_isolated_in_the_sidecar(mongo, monkeypatch):
    """A-001: what code that gets past the name filter can see. It runs in the query-shell sidecar
    under a slot uid: no Deployer secrets, no access to the runner (PID 1), nothing left behind."""
    password = connections.mongo_uri_password(MONGO_URI)
    assert password
    with pytest.raises(ApiError) as err:
        sh(mongo, "require('fs')")
    assert err.value.code == "shell_code_refused"
    # The name filter is best effort (string building gets past it): check what a bypass would see.
    monkeypatch.setattr(query_console, "_MONGO_ESCAPE_RE", re.compile(r"(?!)"))
    out = sh(
        mongo,
        "const fs = require('fs');\n"
        "const cmdline = fs.readFileSync('/proc/self/cmdline', 'utf8').split('\\0');\n"
        "let runner;\n"
        "try { runner = fs.readFileSync('/proc/1/environ', 'utf8'); } catch (e) { runner = e.code; }\n"
        "const child = require('child_process').spawn('sleep', ['300'], {detached: true, stdio: 'ignore'});\n"
        "child.unref();\n"
        "({cmdline, env: Object.keys(process.env).sort(),\n"
        "  uri: String(process.env.DEPLOYER_QUERY_URI), file: String(process.env.DEPLOYER_QUERY_FILE),\n"
        "  home: process.env.HOME, cwd: process.cwd(), uid: process.getuid(), runner, child: child.pid,\n"
        "  docker: fs.existsSync('/var/run/docker.sock')})",
    )
    assert out["error"] is None, out
    result = out["result"]
    assert password not in " ".join(result["cmdline"]) and "mongodb://" not in " ".join(result["cmdline"])
    deployer_env = [k for k in result["env"] if k.startswith("DEPLOYER")]
    assert deployer_env == ["DEPLOYER_QUERY_BATCH", "DEPLOYER_QUERY_DB"]
    assert not {"MASTER_KEY", "JWT_SECRET", "MONGO_ROOT_PASSWORD", "REDIS_URL"} & set(result["env"])
    assert result["uri"] == "undefined" and result["file"] == "undefined"
    assert result["home"].startswith("/tmp/deployer-query-") and result["cwd"] == result["home"]
    assert result["uid"] in shell_runner.SLOT_UIDS and result["runner"] == "EACCES"
    assert result["docker"] is False
    # After the run the left-behind process is killed and the private HOME (the shell's own config
    # and logs) deleted, as seen from the next run (possibly another slot uid: EPERM if still alive).
    probe = sh(
        mongo,
        f"const fs = require('fs'); let alive;\n"
        f"try {{ process.kill({int(result['child'])}, 0); alive = 'alive'; }} catch (e) {{ alive = e.code; }}\n"
        f"({{alive, home: fs.existsSync({json.dumps(result['home'])})}})",
    )
    assert probe["result"] == {"alive": "ESRCH", "home": False}, probe


def test_mongosh_read_only_and_connection_failures(mongo):
    with pytest.raises(ApiError) as err:
        sh(mongo, "db.items.deleteMany({})", read_only=True)
    assert err.value.code == "read_only_role"
    assert sh(mongo, "db.items.countDocuments()", read_only=True)["result"] == 13

    parts = urlsplit(MONGO_URI)
    userinfo = parts.username + ":" + "wrong" if parts.username else ""
    bad_auth = MONGO_URI.replace(parts.netloc, f"{userinfo}@{parts.hostname}:{parts.port or 27017}")
    started = time.monotonic()
    with pytest.raises(ApiError) as err:
        sh({"uri": bad_auth, "database": DATABASE}, "db.items.find()")
    assert err.value.status_code == 503 and err.value.code == "database_unavailable"
    assert "Authentication failed" in err.value.message and "wrong" not in err.value.message
    with pytest.raises(ApiError) as err:
        sh({"uri": "mongodb://nowhere.invalid:27017/x", "database": DATABASE}, "db.items.find()", timeout_seconds=20)
    assert err.value.code == "database_unavailable" and time.monotonic() - started < 15
