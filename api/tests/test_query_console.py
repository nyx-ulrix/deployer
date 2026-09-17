"""Query console (docs/QUERY_CONSOLE.md): SQL runner on sqlite, mongosh runner with a fake shell,
read-only classification, the route, audit and device routing. Real servers: tests/integration."""

import datetime as dt
import json
import sys
import textwrap
import threading
import time

import pytest
from sqlalchemy import create_engine, select

from app.crypto import encrypt_json
from app.errors import ApiError
from app.models import AuditLog, DataSource
from app.services import connections, device_rpc, query_console, source_ops
from tests import devices_support
from tests.devices_support import device_source

make_device = devices_support.make_device
fake_device = devices_support.fake_device


# --- fixtures ------------------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'console.db').as_posix()}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE items "
            "(id INTEGER PRIMARY KEY, name VARCHAR(50), price NUMERIC(10,2), blob BLOB, seen DATETIME)"
        )
        for i in range(1, 8):
            conn.exec_driver_sql("INSERT INTO items (id, name) VALUES (?, ?)", (i, f"item {i}"))
    yield engine
    engine.dispose()


FAKE_MONGOSH = textwrap.dedent(
    r'''
    """A stand-in for mongosh: speaks the wrapper protocol of app/services/query_console.py."""
    import json, os, sys, time

    env = os.environ
    marker = env.get("DEPLOYER_QUERY_MARKER", "")
    uri = env.get("DEPLOYER_QUERY_URI", "")
    with open(env["DEPLOYER_QUERY_FILE"], encoding="utf-8") as fh:
        code = fh.read()
    out = sys.stdout.buffer


    def emit(obj):
        out.write((marker + json.dumps(obj) + "\n").encode("utf-8"))
        out.flush()


    if "unreachable" in uri:
        emit({"phase": "connect", "error": {"name": "MongoNetworkError", "message": "getaddrinfo ENOTFOUND unreachable",
                                            "code": None, "codeName": None}})
        sys.exit(0)
    if code.startswith("sleep"):
        time.sleep(30)
    if code.startswith("flood"):
        chunk = b"x" * 65536
        for _ in range(200):
            out.write(chunk)
        out.flush()
        emit({"phase": "done", "value": 1})
        sys.exit(0)
    if code.startswith("throw"):
        emit({"phase": "error", "error": {"name": "SyntaxError", "message": "Unexpected token (1:15)",
                                          "code": "BABEL_PARSE_ERROR", "codeName": None}})
        sys.exit(0)
    if code.startswith("servererror"):
        emit({"phase": "error", "error": {"name": "MongoServerError", "message": "unknown top level operator: $bad",
                                          "code": 2, "codeName": "BadValue"}})
        sys.exit(0)
    if code.startswith("print"):
        out.write(b"hello\n42\n")
        out.flush()
        sys.stderr.write("DeprecationWarning: something\n")
        sys.stderr.flush()
        emit({"phase": "done", "value": {"n": 7}})
        sys.exit(0)
    if code.startswith("secret"):
        out.write(("connected to " + uri + "\n").encode("utf-8"))
        emit({"phase": "done", "value": {"uri": uri}})
        sys.exit(0)
    if code.startswith("argv"):
        emit({"phase": "done", "value": {"argv": sys.argv, "env": dict(env), "cwd": os.getcwd()}})
        sys.exit(0)
    if code.startswith("crash"):
        sys.stderr.write("boom\n")
        sys.exit(2)
    if code.startswith("scalar"):
        emit({"phase": "done", "value": "str"})
        sys.exit(0)
    if code.startswith("nothing"):
        emit({"phase": "done", "value": None})
        sys.exit(0)
    batch = int(env.get("DEPLOYER_QUERY_BATCH", "0"))
    if code.startswith("exact"):
        batch -= 1
    emit({"phase": "done", "value": [{"_id": {"$oid": "%024x" % i}, "n": i} for i in range(batch)]})
    '''
)


@pytest.fixture
def fake_mongosh(tmp_path, monkeypatch):
    script = tmp_path / "fake_mongosh.py"
    script.write_text(FAKE_MONGOSH, encoding="utf-8")
    monkeypatch.setattr(query_console, "mongosh_command", lambda: [sys.executable, str(script)])
    return script


def mongo_config() -> dict:
    # Built at runtime so no connection string with a password appears in the source (gitleaks).
    return {"uri": "mongodb://" + "app:s3cret-pw" + "@mongo.example:27017/app?authSource=app", "database": "app"}


def sql_config() -> dict:
    return {"host": "db.example", "port": 3306, "username": "app", "password": "pw-" + "x" * 8, "database": "app"}


def add_source(db, project, kind="sql", **overrides) -> DataSource:
    config = sql_config() if kind == "sql" else mongo_config()
    ds = DataSource(
        project_id=project.id,
        name=overrides.pop("name", f"main-{kind}"),
        kind=kind,
        engine="mariadb" if kind == "sql" else "mongodb",
        mode="external",
        database_name="app",
        config_encrypted=encrypt_json(config),
        status="ok",
        **overrides,
    )
    db.add(ds)
    db.commit()
    return ds


@pytest.fixture
def project_setup(make_user, make_project, auth_headers):
    owner = make_user()
    dev, viewer = make_user(), make_user()
    project = make_project(owner, "Shop", members={dev: "developer", viewer: "viewer"})
    return {
        "project": project,
        "owner": auth_headers(owner),
        "dev": auth_headers(dev),
        "viewer": auth_headers(viewer),
        "base": f"/v1/projects/{project.id}/data-sources",
    }


# --- statement splitting & classification --------------------------------------------------------


def test_split_sql_respects_strings_and_comments():
    script = (
        "SELECT ';' AS a; -- trailing; comment\n"
        "SELECT 2 /* ; inside */;\n"
        "INSERT INTO t VALUES ('x;y', 'it''s', 'a\\'b');\n"
        ";;\n-- only a comment\n/* block ; */\n"
        "SELECT 3"
    )
    statements = query_console.split_sql(script)
    assert statements == [
        "SELECT ';' AS a; -- trailing; comment",
        "SELECT 2 /* ; inside */;",
        "INSERT INTO t VALUES ('x;y', 'it''s', 'a\\'b');",
        # Comments ahead of a statement stay with it (the statement runs as written); the empty
        # `;;` chunk is dropped.
        "-- only a comment\n/* block ; */\nSELECT 3",
    ]
    assert query_console.split_sql("  \n-- nothing\n;") == []
    percent = query_console.split_sql("SELECT 'a%' LIKE '%'; SELECT \"q;\" -- c")
    assert percent == ["SELECT 'a%' LIKE '%';", 'SELECT "q;" -- c']


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM t",
        "  -- comment\n  select 1;",
        "/* c */ WITH t AS (SELECT 1) SELECT * FROM t",
        "SHOW CREATE TABLE t",
        "SHOW TABLES",
        "EXPLAIN SELECT * FROM t",
        "DESCRIBE t",
        "DESC t",
        "TABLE t",
        "VALUES (1, 2)",
        "(SELECT 1) UNION (SELECT 2)",
        "SELECT 'delete', \"update\" FROM t WHERE x = 'insert into'",
        "SELECT deleted_at, insert_count FROM t ORDER BY id DESC LIMIT 5",
        "select count(*) as n from t group by a having n > 1",
    ],
)
def test_sql_read_only_accepts(statement):
    assert query_console.sql_is_read_only([statement])


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "CREATE TABLE t (a int)",
        "DROP TABLE t",
        "TRUNCATE t",
        "SET NAMES utf8",
        "BEGIN",
        "CALL p()",
        "GRANT ALL ON *.* TO x",
        "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d",
        "SELECT * FROM t FOR UPDATE",
        "SELECT * INTO OUTFILE '/tmp/x' FROM t",
        "EXPLAIN ANALYZE DELETE FROM t",
        "SELECT 1; INSERT INTO t VALUES (1)",
        "PRAGMA table_info(t)",
    ],
)
def test_sql_read_only_refuses(statement):
    assert not query_console.sql_is_read_only(query_console.split_sql(statement))


@pytest.mark.parametrize(
    "code",
    [
        "db.items.find({})",
        "db.items.find({name: 'insertion'}).limit(5)",
        "db.items.countDocuments({ deleted: true })",
        "db.items.aggregate([{$match: {a: 1}}, {$group: {_id: '$a', n: {$sum: 1}}}])",
        "db.getCollectionNames()",
        "db.stats()",
        "show collections",
        "printjson(db.items.findOne())",
    ],
)
def test_mongo_read_only_accepts(code):
    assert query_console.mongo_is_read_only(code)


@pytest.mark.parametrize(
    "code",
    [
        "db.items.insertOne({a: 1})",
        "db.items.insert({a: 1})",
        "db.items.updateMany({}, {$set: {a: 1}})",
        "db.items.deleteOne({})",
        "db.items.drop()",
        "db.dropDatabase()",
        "db.items.createIndex({a: 1})",
        "db.items.bulkWrite([])",
        "db.items.findOneAndUpdate({}, {$set: {a: 1}})",
        "db.getSiblingDB('admin').getCollectionNames()",
        "db.runCommand({ping: 1})",
        "db.adminCommand({listDatabases: 1})",
        "db.getMongo()",
        "load('/etc/passwd')",
        "require('fs').readFileSync('/etc/passwd')",
        "process.env",
        "child_process.execSync('id')",
        "db.items.aggregate([{$out: 'copy'}])",
        "db.items.find({ $where: 'this.insertOne' })",  # over-matching inside strings is the safe direction
        "eval('1')",
        "globalThis.process",
    ],
)
def test_mongo_read_only_refuses(code):
    assert not query_console.mongo_is_read_only(code)


# --- SQL runner (sqlite) -------------------------------------------------------------------------


def test_run_sql_rows_count_empty_error_and_truncation(sqlite_engine):
    result = query_console.run_sql(
        "mariadb",
        sqlite_engine,
        "CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT);\n"
        "INSERT INTO notes (body) VALUES ('a'), ('b');\n"
        "UPDATE items SET price = 1.5, blob = X'0001', seen = '2024-01-02 03:04:05' WHERE id = 1;\n"
        "SELECT id, name, price, blob, seen FROM items ORDER BY id;\n"
        "DELETE FROM notes WHERE id > 100;\n"
        "SELEC oops;\n"
        "SELECT 'never runs'",
        max_rows=3,
        timeout_seconds=5,
        read_only=False,
    )
    assert result["kind"] == "sql" and result["engine"] == "mariadb" and isinstance(result["duration_ms"], int)
    types = [r["type"] for r in result["results"]]
    assert types == ["empty", "count", "count", "rows", "count", "error"]
    created, inserted, updated, rows, deleted, failed = result["results"]
    assert created["statement"].startswith("CREATE TABLE notes")
    assert inserted["affected_rows"] == 2 and updated["affected_rows"] == 1 and deleted["affected_rows"] == 0
    assert rows["columns"] == ["id", "name", "price", "blob", "seen"]
    assert rows["row_count"] == 3 and rows["truncated"] is True
    # sqlite hands raw SQL results back untyped (the string stays a string); bytes are base64-wrapped.
    assert rows["rows"][0] == [1, "item 1", 1.5, {"$base64": "AAE="}, "2024-01-02 03:04:05"]
    assert rows["rows"][2] == [3, "item 3", None, None, None]
    assert failed["error"]["code"] == "query_failed" and "syntax" in failed["error"]["message"].lower()
    assert failed["statement"] == "SELEC oops;"
    assert all(isinstance(r["duration_ms"], int) for r in result["results"])

    exact = query_console.run_sql(
        "mariadb", sqlite_engine, "SELECT id FROM items", max_rows=7, timeout_seconds=5, read_only=False
    )
    assert exact["results"][0]["row_count"] == 7 and exact["results"][0]["truncated"] is False
    like_sql = "SELECT name FROM items WHERE name LIKE 'item 1%'"
    like = query_console.run_sql("mariadb", sqlite_engine, like_sql, max_rows=7, timeout_seconds=5, read_only=True)
    assert like["results"][0]["rows"] == [["item 1"]]


def test_run_sql_encodes_python_values(sqlite_engine, monkeypatch):
    # Decimal / date values as drivers return them for other engines (sqlite hands back plain types).
    with sqlite_engine.begin() as conn:
        conn.exec_driver_sql("UPDATE items SET seen = ? WHERE id = 2", (dt.datetime(2024, 5, 6, 7, 8, 9),))
    out = query_console.run_sql(
        "mariadb", sqlite_engine, "SELECT seen FROM items WHERE id = 2", max_rows=5, timeout_seconds=5, read_only=True
    )
    assert out["results"][0]["rows"] == [["2024-05-06 07:08:09"]]


def test_run_sql_validation_and_read_only(sqlite_engine):
    with pytest.raises(ApiError) as err:
        query_console.run_sql("mariadb", sqlite_engine, "-- nothing\n;", max_rows=5, timeout_seconds=5, read_only=False)
    assert err.value.status_code == 422
    with pytest.raises(ApiError) as err:
        query_console.run_sql(
            "mariadb", sqlite_engine, "SELECT 1; DELETE FROM items", max_rows=5, timeout_seconds=5, read_only=True
        )
    assert err.value.status_code == 403 and err.value.code == "read_only_role"
    # Nothing ran: the refusal happens before any statement.
    with sqlite_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM items").scalar() == 7
    ok = query_console.run_sql(
        "mariadb", sqlite_engine, "SELECT COUNT(*) AS n FROM items", max_rows=5, timeout_seconds=5, read_only=True
    )
    assert ok["results"][0]["rows"] == [[7]]


def test_run_sql_session_state_does_not_leak(sqlite_engine):
    # The console invalidates its connection: a temp table from one run is gone in the next.
    first = query_console.run_sql(
        "mariadb",
        sqlite_engine,
        "CREATE TEMP TABLE scratch (a int); INSERT INTO scratch VALUES (1); SELECT * FROM scratch",
        max_rows=5,
        timeout_seconds=5,
        read_only=False,
    )
    assert first["results"][-1]["rows"] == [[1]]
    second = query_console.run_sql(
        "mariadb", sqlite_engine, "SELECT * FROM scratch", max_rows=5, timeout_seconds=5, read_only=False
    )
    assert second["results"][0]["type"] == "error"


def test_run_sql_database_unavailable():
    engine = create_engine("mysql+pymysql://app:nope@127.0.0.1:1/app", connect_args={"connect_timeout": 2})
    try:
        with pytest.raises(ApiError) as err:
            query_console.run_sql("mariadb", engine, "SELECT 1", max_rows=5, timeout_seconds=5, read_only=True)
        assert err.value.status_code == 503 and err.value.code == "database_unavailable"
        assert "nope" not in err.value.message
    finally:
        engine.dispose()


def test_statement_error_classification():
    class Timeout(Exception):
        pass

    interrupted = Timeout(1969, "Query execution was interrupted (max_statement_time exceeded)")
    err = query_console._statement_error(interrupted, [])
    assert err == {
        "code": "query_timeout",
        "message": "Query execution was interrupted (max_statement_time exceeded) (error 1969)",
    }
    syntax = Timeout(1064, "You have an error near 'x' for user 'u' with hunter2")
    err = query_console._statement_error(syntax, ["hunter2"])
    assert err["code"] == "query_failed" and "hunter2" not in err["message"] and "***" in err["message"]


# --- mongosh runner (fake shell) -----------------------------------------------------------------


def run_fake(query, **kwargs):
    params = {"max_rows": 5, "timeout_seconds": 5, "read_only": False, **kwargs}
    return query_console.run_mongosh(mongo_config(), "app", query, **params)


def test_mongosh_unavailable(monkeypatch):
    monkeypatch.setattr(query_console, "mongosh_command", lambda: None)
    with pytest.raises(ApiError) as err:
        run_fake("db.items.find()")
    assert err.value.status_code == 501 and err.value.code == "mongosh_unavailable"


def test_mongosh_cursor_batch_and_truncation(fake_mongosh):
    out = run_fake("db.items.find()", max_rows=5)
    assert out["kind"] == "nosql" and out["engine"] == "mongodb" and isinstance(out["duration_ms"], int)
    assert out["error"] is None and out["output"] == ""
    assert len(out["result"]) == 5 and out["truncated"] is True
    assert out["result_docs"] == out["result"] and out["result"][0] == {"_id": {"$oid": "0" * 24}, "n": 0}
    exact = run_fake("exact: db.items.find()", max_rows=5)
    assert len(exact["result"]) == 5 and exact["truncated"] is False


def test_mongosh_scalar_prints_and_stderr(fake_mongosh):
    out = run_fake("scalar")
    assert out["result"] == "str" and out["result_docs"] is None and out["truncated"] is False
    out = run_fake("print('x'); db.items.countDocuments()")
    assert out["output"] == "hello\n42\nDeprecationWarning: something"
    assert out["result"] == {"n": 7} and out["result_docs"] is None and out["error"] is None
    assert run_fake("nothing")["result"] is None


def test_mongosh_errors_are_in_band(fake_mongosh):
    out = run_fake("throw")
    assert out["result"] is None and out["result_docs"] is None
    assert out["error"] == {"code": "query_failed", "message": "SyntaxError: Unexpected token (1:15)"}
    out = run_fake("servererror")
    assert out["error"]["message"] == "MongoServerError: unknown top level operator: $bad [BadValue]"
    out = run_fake("crash")
    assert out["error"]["code"] == "query_failed" and "boom" in out["error"]["message"]
    assert out["output"] == "boom"


def test_mongosh_connect_failure(fake_mongosh):
    config = {"uri": "mongodb://" + "app:pw" + "@unreachable:27017/app", "database": "app"}
    with pytest.raises(ApiError) as err:
        query_console.run_mongosh(config, "app", "db.items.find()", max_rows=5, timeout_seconds=5, read_only=False)
    assert err.value.status_code == 503 and err.value.code == "database_unavailable"
    assert "ENOTFOUND unreachable" in err.value.message


def test_mongosh_timeout_kills_the_shell(fake_mongosh):
    started = time.monotonic()
    with pytest.raises(ApiError) as err:
        run_fake("sleep(60000)", timeout_seconds=1)
    assert err.value.status_code == 504 and err.value.code == "query_timeout"
    assert time.monotonic() - started < 10


def test_mongosh_output_cap(fake_mongosh):
    out = run_fake("flood")
    assert out["error"]["code"] == "query_failed" and "8 MiB" in out["error"]["message"]
    assert out["result"] is None and len(out["output"]) <= query_console.MAX_SHELL_STDOUT


def test_mongosh_secrets_only_in_environment(fake_mongosh):
    config = mongo_config()
    password = connections.mongo_uri_password(config["uri"])
    out = run_fake("argv")
    argv, env, cwd = out["result"]["argv"], out["result"]["env"], out["result"]["cwd"]
    assert password not in " ".join(argv) and "mongodb://" not in " ".join(argv)
    assert env["DEPLOYER_QUERY_URI"].startswith("mongodb://app:")
    assert "serverSelectionTimeoutMS=5000" in env["DEPLOYER_QUERY_URI"] and env["DEPLOYER_QUERY_DB"] == "app"
    assert env["HOME"] == cwd and env["DEPLOYER_QUERY_FILE"].startswith(cwd)
    assert env["DEPLOYER_QUERY_BATCH"] == "6"
    assert "MASTER_KEY" not in env and "JWT_SECRET" not in env
    assert "--eval" in argv and query_console.WRAPPER_JS in argv and "argv" not in argv[-1]
    assert "mongodb://" not in query_console.WRAPPER_JS
    # The shell's output is redacted as well.
    out = run_fake("secret")
    assert password not in out["output"] and "***" in out["output"]
    assert password not in json.dumps(out["result"])


def test_mongosh_read_only_and_concurrency(fake_mongosh, monkeypatch):
    with pytest.raises(ApiError) as err:
        run_fake("db.items.insertOne({a: 1})", read_only=True)
    assert err.value.status_code == 403 and err.value.code == "read_only_role"
    assert run_fake("db.items.find()", read_only=True)["error"] is None
    busy = threading.BoundedSemaphore(1)
    busy.acquire()
    monkeypatch.setattr(query_console, "_shells", busy)
    with pytest.raises(ApiError) as err:
        run_fake("db.items.find()")
    assert err.value.status_code == 429 and err.value.code == "too_many_queries"


def test_connect_uri_adds_timeouts_once():
    assert query_console._connect_uri("mongodb://h:27017").endswith("/?serverSelectionTimeoutMS=5000&connectTimeoutMS=5000")
    assert query_console._connect_uri("mongodb+srv://c.example/app?retryWrites=true") == (
        "mongodb+srv://c.example/app?retryWrites=true&serverSelectionTimeoutMS=5000&connectTimeoutMS=5000"
    )
    custom = "mongodb://h/db?serverSelectionTimeoutMS=100&connectTimeoutMS=100"
    assert query_console._connect_uri(custom) == custom
    assert query_console._connect_uri("not a uri") == "not a uri"


def test_parse_shell_output():
    marker = "@@deployer:abc@@"
    text, report = query_console.parse_shell_output(f"a\n{marker}{{\"phase\": \"done\", \"value\": 1}}\nb\n", marker)
    assert text == "a\nb\n" and report == {"phase": "done", "value": 1}
    assert query_console.parse_shell_output("no report\n", marker) == ("no report\n", None)
    assert query_console.parse_shell_output(f"{marker}not json\n", marker) == ("", None)


# --- route, audit, devices -----------------------------------------------------------------------


def test_query_route_roles_and_audit(client, db, project_setup, sqlite_engine, monkeypatch):
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: sqlite_engine)
    ds = add_source(db, project_setup["project"])
    url = f"{project_setup['base']}/{ds.id}/query"

    resp = client.post(url, json={"query": "INSERT INTO items (name) VALUES ('x')"}, headers=project_setup["viewer"])
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "read_only_role"
    resp = client.post(url, json={"query": "SELECT COUNT(*) AS n FROM items"}, headers=project_setup["viewer"])
    assert resp.status_code == 200 and resp.json()["results"][0]["rows"] == [[7]]
    resp = client.post(
        url,
        json={"query": "INSERT INTO items (name) VALUES ('x'); SELECT COUNT(*) AS n FROM items", "max_rows": 10},
        headers=project_setup["dev"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "sql" and [r["type"] for r in body["results"]] == ["count", "rows"]
    assert body["results"][1]["rows"] == [[8]]

    db.expire_all()
    rows = list(db.scalars(select(AuditLog).where(AuditLog.action == "query.run").order_by(AuditLog.id)))
    assert [r.details["ok"] for r in rows] == [False, True, True]
    assert [r.details["read_only"] for r in rows] == [True, True, False]
    assert rows[0].details["statements"] is None and rows[2].details["statements"] == 2
    assert rows[2].details["kind"] == "sql" and rows[2].details["data_source_id"] == ds.id
    assert isinstance(rows[2].details["duration_ms"], int) and rows[2].project_id == project_setup["project"].id
    assert "INSERT" not in json.dumps(rows[2].details) and "items" not in json.dumps(rows[2].details)


def test_query_route_validation_and_not_found(client, db, project_setup, make_user, make_project, auth_headers):
    ds = add_source(db, project_setup["project"])
    url = f"{project_setup['base']}/{ds.id}/query"
    for bad in ({"query": ""}, {"query": "SELECT 1", "max_rows": 0}, {"query": "SELECT 1", "timeout_seconds": 121}, {}):
        resp = client.post(url, json=bad, headers=project_setup["owner"])
        assert resp.status_code == 422, bad
    owner_headers = project_setup["owner"]
    resp = client.post(f"{project_setup['base']}/nope/query", json={"query": "SELECT 1"}, headers=owner_headers)
    assert resp.status_code == 404
    stranger = make_user()
    other = make_project(stranger, "Other")
    stranger_url = f"/v1/projects/{other.id}/data-sources/{ds.id}/query"
    resp = client.post(stranger_url, json={"query": "SELECT 1"}, headers=auth_headers(stranger))
    assert resp.status_code == 404
    resp = client.post(url, json={"query": "SELECT 1"})
    assert resp.status_code == 401


def test_query_route_mongo_without_mongosh(client, db, project_setup, monkeypatch):
    monkeypatch.setattr(query_console, "mongosh_command", lambda: None)
    ds = add_source(db, project_setup["project"], kind="nosql")
    url = f"{project_setup['base']}/{ds.id}/query"
    resp = client.post(url, json={"query": "db.x.find()"}, headers=project_setup["dev"])
    assert resp.status_code == 501 and resp.json()["error"]["code"] == "mongosh_unavailable"


def test_query_route_mongo_with_fake_shell(client, db, project_setup, fake_mongosh):
    ds = add_source(db, project_setup["project"], kind="nosql")
    url = f"{project_setup['base']}/{ds.id}/query"
    resp = client.post(url, json={"query": "db.items.find()", "max_rows": 2}, headers=project_setup["viewer"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "nosql" and len(body["result_docs"]) == 2 and body["truncated"] is True
    resp = client.post(url, json={"query": "db.items.insertOne({})"}, headers=project_setup["viewer"])
    assert resp.status_code == 403
    resp = client.post(url, json={"query": "sleep(1)", "timeout_seconds": 1}, headers=project_setup["dev"])
    assert resp.status_code == 504 and resp.json()["error"]["code"] == "query_timeout"
    db.expire_all()
    rows = list(db.scalars(select(AuditLog).where(AuditLog.action == "query.run").order_by(AuditLog.id)))
    assert [(r.details["kind"], r.details["ok"], r.details["statements"]) for r in rows] == [
        ("nosql", True, 1),
        ("nosql", False, None),
        ("nosql", False, None),
    ]


def test_query_route_device_hosted_source(client, db, owner, owner_headers, make_project, make_device, fake_device):
    project = make_project(owner, "Edge")
    device, _ = make_device(owner)
    ds = device_source(db, project, device, "sql")
    url = f"/v1/projects/{project.id}/data-sources/{ds.id}/query"
    resp = client.post(url, json={"query": "SELECT 1"}, headers=owner_headers)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "device_offline"

    canned = {
        "kind": "sql",
        "engine": "mariadb",
        "duration_ms": 3,
        "results": [{"statement": "SELECT 1", "type": "rows", "columns": ["1"], "rows": [[1]], "row_count": 1,
                     "truncated": False, "duration_ms": 1}],
    }

    def handler(method, params):
        assert method == "datasource.call" and params["op"] == "query"
        if params["args"]["read_only"]:
            raise ApiError(403, "read_only_role", "refused on the device")
        return canned

    fd = fake_device(device.id, handler)
    resp = client.post(url, json={"query": "SELECT 1", "max_rows": 100, "timeout_seconds": 10}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == canned
    _, params = fd.calls[-1]
    assert params["kind"] == "sql" and params["database_name"] == ds.database_name
    assert params["args"] == {"query": "SELECT 1", "max_rows": 100, "timeout_seconds": 10, "read_only": False}


def test_source_ops_query_routing(db, owner, make_project, make_device, sqlite_engine, monkeypatch):
    project = make_project(owner, "Ops")
    ds = add_source(db, project)
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: sqlite_engine)
    assert "query" in source_ops.OPS
    out = source_ops.run_local(ds, "query", {"query": "SELECT 1 AS one", "max_rows": 10, "timeout_seconds": 5})
    assert out["results"][0]["rows"] == [[1]]
    with pytest.raises(ApiError) as err:  # read_only defaults to the safe side on the device
        source_ops.run_local(ds, "query", {"query": "DELETE FROM items"})
    assert err.value.code == "read_only_role"
    with pytest.raises(ApiError) as err:
        source_ops.run_local(ds, "query", {})
    assert err.value.status_code == 422

    device, _ = make_device(owner)
    remote = device_source(db, project, device, "sql", name="edge-sql")
    seen = {}

    def fake_call(device_id, method, params, timeout=30.0, **kwargs):
        seen.update(device_id=device_id, method=method, params=params, timeout=timeout)
        return {"kind": "sql", "engine": "mariadb", "duration_ms": 1, "results": []}

    monkeypatch.setattr(device_rpc, "call", fake_call)
    out = source_ops.run_query(remote, "SELECT 2", max_rows=50, timeout_seconds=20, read_only=True)
    assert out["results"] == [] and seen["timeout"] == 35 and seen["method"] == "datasource.call"
    assert seen["params"]["op"] == "query" and seen["params"]["args"]["read_only"] is True
    monkeypatch.setattr(device_rpc, "call", lambda *a, **k: "not a dict")
    with pytest.raises(ApiError) as err:
        source_ops.run_query(remote, "SELECT 2", max_rows=50, timeout_seconds=20, read_only=True)
    assert err.value.code == "device_error"


def test_summarize():
    assert query_console.summarize({"kind": "sql", "results": [{"type": "rows"}, {"type": "error"}]}) == (False, 2)
    assert query_console.summarize({"kind": "sql", "results": [{"type": "count"}]}) == (True, 1)
    assert query_console.summarize({"kind": "nosql", "error": None}) == (True, 1)
    assert query_console.summarize({"kind": "nosql", "error": {"code": "query_failed"}}) == (False, 1)
