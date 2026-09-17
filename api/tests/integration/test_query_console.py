"""Query console against real servers (docs/QUERY_CONSOLE.md).

- SQL: a throwaway MariaDB 11, e.g. `docker run -d --rm -p 127.0.0.1:33071:3306 -e MARIADB_ROOT_PASSWORD=... mariadb:11`
  and `DEPLOYER_IT_MARIADB_URL=mysql://root:<password>@127.0.0.1:33071` (runs from the venv).
- MongoDB: needs `mongosh` on PATH, so it normally runs inside the API image on a network shared with
  a `mongo:5.0` container: `DEPLOYER_IT_MONGO_URI=mongodb://admin:<password>@mongo-host:27017/?authSource=admin`.

Each part is skipped unless its URL is set. The tests create and drop their own database.
"""

import os
import shutil
import time
from urllib.parse import unquote, urlsplit

import pytest

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


def test_mariadb_timeout(mariadb):
    started = time.monotonic()
    out = run(mariadb, "SELECT 1; SELECT SLEEP(5); SELECT 2", timeout_seconds=1)
    assert time.monotonic() - started < 4
    assert [r["type"] for r in out["results"]] == ["rows", "error"]
    assert out["results"][1]["error"]["code"] == "query_timeout"
    assert run(mariadb, "SELECT SLEEP(0.1)")["results"][0]["type"] == "rows"


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
    if not shutil.which("mongosh"):
        pytest.skip("mongosh is not on PATH (run inside the API image)")
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


def test_mongosh_secrets_stay_out_of_argv(mongo):
    password = connections.mongo_uri_password(MONGO_URI)
    assert password
    out = sh(
        mongo,
        "const fs = require('fs');\n"
        "const cmdline = fs.readFileSync('/proc/self/cmdline', 'utf8').split('\\0');\n"
        "({cmdline, env: Object.keys(process.env).filter((k) => k.startsWith('DEPLOYER')),\n"
        "  uri: String(process.env.DEPLOYER_QUERY_URI), file: String(process.env.DEPLOYER_QUERY_FILE),\n"
        "  home: process.env.HOME, cwd: process.cwd()})",
    )
    assert out["error"] is None, out
    result = out["result"]
    assert password not in " ".join(result["cmdline"]) and "mongodb://" not in " ".join(result["cmdline"])
    assert sorted(result["env"]) == ["DEPLOYER_QUERY_BATCH", "DEPLOYER_QUERY_DB"]
    assert result["uri"] == "undefined" and result["file"] == "undefined"
    assert result["home"].startswith("/tmp/deployer-query-") and result["cwd"] == result["home"]
    # The shell's own log files and config stay in the private HOME (deleted with it).
    assert not os.path.exists(result["home"])


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
