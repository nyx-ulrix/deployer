"""Route tests for data sources, schema, links and the SQL data browser.

External connections are faked: `connections.try_config` is patched and SQL engines point at a local
SQLite file, so no real MariaDB/Postgres/MongoDB is needed.
"""

import io
import zipfile

import pytest
from sqlalchemy import create_engine, select

from app.crypto import decrypt_json, encrypt_json
from app.models import AuditLog, DataSource, ProjectMember, SchemaLink
from app.services import connections

# Obviously fake credentials: built at runtime so secret scanners never see a literal
# "user:password@host" URI in the repository.
FAKE_SQL_PASSWORD = "fake-sql-password"
FAKE_MONGO_PASSWORD = "fake-mongo-password"

EXTERNAL_SQL = {
    "kind": "sql",
    "mode": "external",
    "engine": "mysql",
    "name": "shop",
    "config": {"host": "db.example.com", "username": "app", "password": FAKE_SQL_PASSWORD, "database": "shop"},
}
EXTERNAL_MONGO = {
    "kind": "nosql",
    "mode": "external",
    "engine": "mongodb",
    "name": "atlas",
    "config": {
        "uri": f"mongodb+srv://app:{FAKE_MONGO_PASSWORD}@cluster0.example.invalid/?retryWrites=true",
        "database": "app",
    },
}


@pytest.fixture
def fake_connect(monkeypatch):
    state = {"ok": True, "calls": []}

    def try_config(kind, engine, config):
        state["calls"].append((kind, engine, config))
        if state["ok"]:
            return True, "Connected", "11.4.2-MariaDB"
        return False, "Access denied for user 'app'", None

    monkeypatch.setattr(connections, "try_config", try_config)
    return state


@pytest.fixture
def sqlite_engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'project.db').as_posix()}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL)")
        conn.exec_driver_sql(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), "
            "total NUMERIC(10,2))"
        )
        conn.exec_driver_sql("INSERT INTO users (id, email) VALUES (1, 'a@example.com')")
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: engine)
    yield engine
    engine.dispose()


@pytest.fixture
def project_setup(make_user, make_project, auth_headers):
    owner = make_user()
    admin, dev, viewer = make_user(), make_user(), make_user()
    project = make_project(owner, "Shop", members={admin: "admin", dev: "developer", viewer: "viewer"})
    return {
        "project": project,
        "owner": auth_headers(owner),
        "admin": auth_headers(admin),
        "dev": auth_headers(dev),
        "viewer": auth_headers(viewer),
        "base": f"/v1/projects/{project.id}",
    }


def test_create_external_sql_source(client, db, project_setup, fake_connect):
    s = project_setup
    resp = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "sql" and body["engine"] == "mysql" and body["mode"] == "external"
    assert body["database_name"] == "shop"
    assert body["status"] == "ok"
    assert body["display"] == {"host": "db.example.com", "port": 3306, "username": "app", "tls": False}
    assert FAKE_SQL_PASSWORD not in resp.text

    ds = db.get(DataSource, body["id"])
    assert decrypt_json(ds.config_encrypted)["password"] == FAKE_SQL_PASSWORD
    assert FAKE_SQL_PASSWORD not in ds.config_encrypted
    assert db.scalar(select(AuditLog).where(AuditLog.action == "data_source.create")) is not None

    listed = client.get(f"{s['base']}/data-sources", headers=s["viewer"]).json()
    assert [d["id"] for d in listed] == [body["id"]]

    dup = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"])
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "name_taken"


def test_create_external_mongo_display(client, project_setup, fake_connect):
    s = project_setup
    resp = client.post(f"{s['base']}/data-sources", json=EXTERNAL_MONGO, headers=s["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["display"] == {"host": "cluster0.example.invalid", "port": None, "username": "app", "tls": True}
    assert FAKE_MONGO_PASSWORD not in resp.text


def test_create_input_friction(client, project_setup, fake_connect):
    # A-117: kind follows from engine, a pasted username is trimmed, the Mongo database defaults from the URI.
    s = project_setup
    sql = {k: v for k, v in EXTERNAL_SQL.items() if k != "kind"}
    sql["config"] = {**sql["config"], "username": " app\n"}
    assert client.post(f"{s['base']}/data-sources", json=sql, headers=s["admin"]).json()["kind"] == "sql"
    assert fake_connect["calls"][-1][2]["username"] == "app"
    uri = f"mongodb+srv://app:{FAKE_MONGO_PASSWORD}@cluster0.example.invalid/shop?retryWrites=true"
    mongo = {"mode": "external", "engine": "mongodb", "name": "atlas", "config": {"uri": uri}}
    resp = client.post(f"{s['base']}/data-sources", json=mongo, headers=s["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "nosql" and resp.json()["database_name"] == "shop"
    bare = {**mongo, "name": "b", "config": {"uri": "mongodb://db.example.com/?tls=true"}}
    assert client.post(f"{s['base']}/data-sources", json=bare, headers=s["admin"]).status_code == 422
    # An explicit kind that contradicts the engine is still refused.
    assert (
        client.post(f"{s['base']}/data-sources", json={**mongo, "kind": "sql"}, headers=s["admin"]).status_code == 422
    )


def test_connection_failure_and_test_endpoint(client, project_setup, fake_connect):
    s = project_setup
    fake_connect["ok"] = False
    resp = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"])
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "connection_failed"
    tested = client.post(f"{s['base']}/data-sources/test", json=EXTERNAL_SQL, headers=s["admin"])
    assert tested.status_code == 200
    assert tested.json() == {"ok": False, "message": "Access denied for user 'app'", "server_version": None}


def test_input_validation_and_roles(client, project_setup, fake_connect):
    s = project_setup
    bad = [
        {**EXTERNAL_SQL, "engine": "mongodb"},
        {**EXTERNAL_MONGO, "engine": "mysql"},
        {**EXTERNAL_SQL, "config": {"host": "x"}},
        {**EXTERNAL_MONGO, "config": {"uri": "http://x", "database": "a"}},
        {"kind": "sql", "mode": "managed", "engine": "postgresql", "name": "x"},
    ]
    for body in bad:
        resp = client.post(f"{s['base']}/data-sources", json=body, headers=s["admin"])
        assert resp.status_code == 422, (body, resp.text)
    assert client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["dev"]).status_code == 403
    assert client.post(f"{s['base']}/data-sources/test", json=EXTERNAL_SQL, headers=s["dev"]).status_code == 403


def test_same_pc_host_is_explained(client, project_setup, fake_connect):
    # A-027: localhost inside the API container is the container, not the PC running XAMPP/Postgres.
    s = project_setup
    for host in ("localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0", "LocalHost"):
        body = {**EXTERNAL_SQL, "config": {**EXTERNAL_SQL["config"], "host": host}}
        for path in ("data-sources", "data-sources/test"):
            resp = client.post(f"{s['base']}/{path}", json=body, headers=s["admin"])
            assert resp.status_code == 422, (host, resp.text)
            assert "host.docker.internal" in resp.json()["error"]["message"]
    mongo = {**EXTERNAL_MONGO, "config": {"uri": "mongodb://127.0.0.1:27017/?tls=false", "database": "app"}}
    assert client.post(f"{s['base']}/data-sources", json=mongo, headers=s["admin"]).status_code == 422
    assert fake_connect["calls"] == []
    ok = {**EXTERNAL_SQL, "config": {**EXTERNAL_SQL["config"], "host": "host.docker.internal"}}
    assert client.post(f"{s['base']}/data-sources", json=ok, headers=s["admin"]).status_code == 200


def test_internal_network_is_refused_for_non_owners(
    client, db, make_user, auth_headers, project_setup, fake_connect, monkeypatch
):
    # A-114: project admins may not aim the connection test at Deployer's own containers or metadata IPs.
    from app.routers import data_sources

    monkeypatch.setattr(data_sources, "_resolve", lambda host: {"db.internal.example": ["172.18.0.3"]}.get(host, []))
    s = project_setup
    for host in (
        "mariadb",
        "redis.",
        "172.18.0.3",
        "169.254.169.254",
        "::ffff:172.17.0.1",
        "db.internal.example",
        "db1.example.com,mariadb",
    ):
        body = {**EXTERNAL_SQL, "config": {**EXTERNAL_SQL["config"], "host": host}}
        for path in ("data-sources", "data-sources/test"):
            resp = client.post(f"{s['base']}/{path}", json=body, headers=s["admin"])
            assert resp.status_code == 422, (host, resp.text)
            assert "internal network" in resp.json()["error"]["message"]
    # Every seed host of a replica-set URI is checked, not just the first.
    mongo = {**EXTERNAL_MONGO, "config": {"uri": "mongodb://db1.example.com,mongodb:27017/?tls=false", "database": "a"}}
    assert client.post(f"{s['base']}/data-sources/test", json=mongo, headers=s["admin"]).status_code == 422
    assert fake_connect["calls"] == []
    # The LAN (a database on this PC or the network) stays allowed, and the instance owner is not limited.
    lan = {**EXTERNAL_SQL, "config": {**EXTERNAL_SQL["config"], "host": "192.168.1.20"}}
    assert client.post(f"{s['base']}/data-sources/test", json=lan, headers=s["admin"]).json()["ok"] is True
    internal = {**EXTERNAL_SQL, "config": {**EXTERNAL_SQL["config"], "host": "mariadb"}}
    # The project owner is not the instance owner either.
    assert client.post(f"{s['base']}/data-sources/test", json=internal, headers=s["owner"]).status_code == 422
    instance_owner = make_user(owner=True)
    db.add(ProjectMember(project_id=s["project"].id, user_id=instance_owner.id, role="admin"))
    db.commit()
    resp = client.post(f"{s['base']}/data-sources/test", json=internal, headers=auth_headers(instance_owner))
    assert resp.json()["ok"] is True


def test_managed_mongo_unavailable(client, project_setup):
    s = project_setup
    body = {"kind": "nosql", "mode": "managed", "engine": "mongodb", "name": "docs"}
    resp = client.post(f"{s['base']}/data-sources", json=body, headers=s["admin"])
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "managed_mongodb_unavailable"


def test_check_connection_and_delete(client, db, project_setup, fake_connect, monkeypatch):
    s = project_setup
    sid = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"]).json()["id"]

    monkeypatch.setattr(connections, "try_source", lambda ds: (False, "timed out", None))
    checked = client.post(f"{s['base']}/data-sources/{sid}/check", headers=s["viewer"]).json()
    assert checked["status"] == "error" and checked["status_message"] == "timed out"
    assert checked["last_checked_at"]

    assert client.get(f"{s['base']}/data-sources/{sid}/connection", headers=s["viewer"]).status_code == 403
    conn = client.get(f"{s['base']}/data-sources/{sid}/connection", headers=s["dev"]).json()
    assert conn["password"] == FAKE_SQL_PASSWORD
    assert conn["uri"] == f"mysql://app:{FAKE_SQL_PASSWORD}@db.example.com:3306/shop"
    assert conn["external_hint"]

    assert client.delete(f"{s['base']}/data-sources/{sid}?drop=true", headers=s["admin"]).status_code == 403
    resp = client.delete(f"{s['base']}/data-sources/{sid}?drop=true", headers=s["owner"])
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "cannot_drop_external"
    assert client.delete(f"{s['base']}/data-sources/{sid}", headers=s["admin"]).json() == {"ok": True}
    db.expire_all()
    assert db.get(DataSource, sid) is None
    assert client.delete(f"{s['base']}/data-sources/{sid}", headers=s["admin"]).status_code == 404


def test_update_external_source_in_place(client, db, project_setup, fake_connect, monkeypatch):
    # A-030: a rotated password is edited in place, keeping the id (links, key configs, saved queries).
    s = project_setup
    sid = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"]).json()["id"]
    invalidated = []
    monkeypatch.setattr(connections, "invalidate", invalidated.append)
    url = f"{s['base']}/data-sources/{sid}"
    rotated = "fake-rotated-password"

    assert client.patch(url, json={"name": "x"}, headers=s["dev"]).status_code == 403
    fake_connect["ok"] = False
    resp = client.patch(url, json={"config": {"password": rotated}}, headers=s["admin"])
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "connection_failed"
    db.expire_all()
    assert decrypt_json(db.get(DataSource, sid).config_encrypted)["password"] == FAKE_SQL_PASSWORD

    fake_connect["ok"] = True
    resp = client.patch(url, json={"name": "shop-main", "config": {"password": rotated}}, headers=s["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == sid and resp.json()["name"] == "shop-main" and rotated not in resp.text
    db.expire_all()
    config = decrypt_json(db.get(DataSource, sid).config_encrypted)
    assert config["password"] == rotated and config["host"] == "db.example.com"
    assert fake_connect["calls"][-1][2] == config
    assert invalidated == [sid]
    log = db.scalar(select(AuditLog).where(AuditLog.action == "data_source.update"))
    assert log is not None and rotated not in str(log.details)

    bad = client.patch(url, json={"config": {"host": "localhost"}}, headers=s["admin"])
    assert bad.status_code == 422
    client.post(f"{s['base']}/data-sources", json={**EXTERNAL_SQL, "name": "other"}, headers=s["admin"])
    assert client.patch(url, json={"name": "other"}, headers=s["admin"]).status_code == 409
    calls = len(fake_connect["calls"])
    assert client.patch(url, json={"name": "shop-main", "config": {}}, headers=s["admin"]).status_code == 200
    assert len(fake_connect["calls"]) == calls  # nothing changed: no reconnect


def test_other_projects_sources_are_hidden(client, make_user, make_project, auth_headers, project_setup, fake_connect):
    s = project_setup
    sid = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"]).json()["id"]
    stranger = make_user()
    other = make_project(stranger, "Other")
    resp = client.post(f"/v1/projects/{other.id}/data-sources/{sid}/check", headers=auth_headers(stranger))
    assert resp.status_code == 404


def test_schema_links_and_export(client, db, project_setup, fake_connect, sqlite_engine, monkeypatch):
    s = project_setup
    sql_id = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"]).json()["id"]
    mongo_id = client.post(f"{s['base']}/data-sources", json=EXTERNAL_MONGO, headers=s["admin"]).json()["id"]

    def fake_mongo(ds, sample=200):
        return {
            "source_id": ds.id,
            "name": ds.name,
            "kind": ds.kind,
            "engine": ds.engine,
            "status": "error",
            "error": "unreachable",
            "entities": [],
            "relationships": [],
        }

    from app.services import introspection

    real = introspection.introspect_source
    monkeypatch.setattr(
        introspection, "introspect_source", lambda ds, sample=200: fake_mongo(ds) if ds.kind == "nosql" else real(ds)
    )

    link_body = {
        "from_source_id": mongo_id,
        "from_entity": "events",
        "from_field": "user_id",
        "to_source_id": sql_id,
        "to_entity": "users",
        "to_field": "id",
        "cardinality": "many_to_one",
        "note": "events belong to users",
    }
    assert client.post(f"{s['base']}/schema/links", json=link_body, headers=s["viewer"]).status_code == 403
    link = client.post(f"{s['base']}/schema/links", json=link_body, headers=s["dev"])
    assert link.status_code == 200, link.text
    link = link.json()
    assert link["note"] == "events belong to users" and link["created_at"]
    assert client.get(f"{s['base']}/schema/links", headers=s["viewer"]).json() == [link]
    bad = {**link_body, "to_source_id": "00000000-0000-0000-0000-000000000000"}
    assert client.post(f"{s['base']}/schema/links", json=bad, headers=s["dev"]).status_code == 404

    schema = client.get(f"{s['base']}/schema", headers=s["viewer"])
    assert schema.status_code == 200, schema.text
    schema = schema.json()
    assert set(schema) == {"sources", "links", "conventions", "generated_at"}
    by_kind = {src["kind"]: src for src in schema["sources"]}
    assert by_kind["nosql"]["status"] == "error" and by_kind["nosql"]["error"] == "unreachable"
    sql = by_kind["sql"]
    assert sql["status"] == "ok"
    assert sorted(e["name"] for e in sql["entities"]) == ["orders", "users"]
    assert sql["relationships"][0]["origin"] == "foreign_key"
    rules = {i["rule"] for i in schema["conventions"]}
    assert {"S3", "S5"} <= rules

    only = client.get(f"{s['base']}/schema?source_id={sql_id}", headers=s["viewer"]).json()
    assert [src["source_id"] for src in only["sources"]] == [sql_id]

    resp = client.get(f"{s['base']}/schema/export?format=sql", headers=s["viewer"])
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment; filename=")
    assert "CREATE TABLE users" in resp.text and "CREATE TABLE orders" in resp.text
    assert resp.text.index("CREATE TABLE users") < resp.text.index("CREATE TABLE orders")

    wrong = client.get(f"{s['base']}/schema/export?format=mongo&source_id={sql_id}", headers=s["viewer"])
    assert wrong.status_code == 400

    bundle = client.get(f"{s['base']}/schema/export?format=bundle", headers=s["viewer"])
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
        assert sorted(zf.namelist()) == ["README.md", "links.json", "schema.mongo.js", "schema.sql"]

    assert client.delete(f"{s['base']}/schema/links/{link['id']}", headers=s["dev"]).json() == {"ok": True}
    db.expire_all()
    assert db.scalar(select(SchemaLink)) is None


def test_deleting_source_removes_links(client, db, project_setup, fake_connect):
    s = project_setup
    a = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"]).json()["id"]
    b = client.post(f"{s['base']}/data-sources", json=EXTERNAL_MONGO, headers=s["admin"]).json()["id"]
    body = {
        "from_source_id": b,
        "from_entity": "e",
        "from_field": "f",
        "to_source_id": a,
        "to_entity": "t",
        "to_field": "id",
        "cardinality": "many_to_one",
    }
    assert client.post(f"{s['base']}/schema/links", json=body, headers=s["dev"]).status_code == 200
    assert client.delete(f"{s['base']}/data-sources/{a}", headers=s["admin"]).status_code == 200
    db.expire_all()
    assert db.scalar(select(SchemaLink)) is None


def test_sql_data_browser_routes(client, project_setup, fake_connect, sqlite_engine):
    s = project_setup
    sid = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"]).json()["id"]
    rows_url = f"{s['base']}/data-sources/{sid}/tables/orders/rows"

    assert (
        client.post(rows_url, json={"values": {"user_id": 1, "total": "5.50"}}, headers=s["viewer"]).status_code == 403
    )
    created = client.post(rows_url, json={"values": {"user_id": 1, "total": "5.50"}}, headers=s["dev"])
    assert created.status_code == 200, created.text
    row = created.json()["row"]
    assert row["user_id"] == 1

    page = client.get(f"{rows_url}?limit=10&order_by=id&order=desc", headers=s["viewer"]).json()
    assert page["columns"] == ["id", "user_id", "total"] and page["primary_key"] == ["id"] and page["total"] == 1
    assert client.get(f"{rows_url}?limit=501", headers=s["viewer"]).status_code == 422
    assert client.get(f"{rows_url}?order_by=nope", headers=s["viewer"]).status_code == 400

    patched = client.patch(rows_url, json={"pk": {"id": row["id"]}, "values": {"total": "7.25"}}, headers=s["dev"])
    assert patched.status_code == 200, patched.text
    resp = client.request("DELETE", rows_url, json={"pk": {"id": row["id"]}}, headers=s["dev"])
    assert resp.json() == {"ok": True}

    mongo_url = f"{s['base']}/data-sources/{sid}/collections/x/documents"
    assert client.get(mongo_url, headers=s["viewer"]).json()["error"]["code"] == "wrong_source_kind"


def test_drop_table_route(client, project_setup, fake_connect, sqlite_engine):
    s = project_setup
    sid = client.post(f"{s['base']}/data-sources", json=EXTERNAL_SQL, headers=s["admin"]).json()["id"]
    url = f"{s['base']}/data-sources/{sid}/tables/orders"
    assert client.delete(url, headers=s["dev"]).status_code == 403
    assert client.delete(url, headers=s["admin"]).json() == {"ok": True}
    assert client.delete(url, headers=s["admin"]).status_code == 404
    bad = client.post(
        f"{s['base']}/data-sources/{sid}/tables",
        json={"name": "bad name", "columns": [{"name": "id", "type": "INT"}]},
        headers=s["dev"],
    )
    assert bad.status_code == 422


def test_managed_connection_hint_says_database_access_is_needed():
    # A-026: only apps with Database access can reach a managed database; it is not reachable from other computers.
    config = {"host": "mariadb", "port": 3306, "username": "u", "password": "pw", "database": "shop"}
    ds = DataSource(kind="sql", mode="managed", engine="mariadb", config_encrypted=encrypt_json(config))
    hint = connections.connection_info(ds)["external_hint"]
    assert "Database access" in hint and "other computers" in hint
    assert "Docker" not in hint and "directly" not in hint


def test_connection_errors_get_a_plain_hint_and_keep_the_driver_text():
    # A-106: a wrong password, a missing database, an unreachable host and the Atlas allowlist read differently.
    import socket

    import psycopg
    import pymysql
    from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

    sql = {"host": "db.example.invalid", "port": 3306, "username": "app", "password": "pw-x", "database": "shop"}
    denied = pymysql.err.OperationalError(1045, "Access denied for user 'app'@'172.18.0.5' (using password: YES)")
    msg = connections.friendly_error("sql", denied, sql, ["pw-x"])
    assert msg.startswith("Wrong username or password") and "Details: " in msg and "172.18.0.5" in msg
    missing = pymysql.err.OperationalError(1049, "Unknown database 'shop'")
    assert connections.friendly_error("sql", missing, sql, []).startswith("Database 'shop' does not exist")
    pg = psycopg.OperationalError('connection failed: FATAL:  password authentication failed for user "app"')
    assert connections.friendly_error("sql", pg, sql, []).startswith("Wrong username or password.")
    pg_db = psycopg.OperationalError('connection failed: FATAL:  database "shop" does not exist')
    assert connections.friendly_error("sql", pg_db, sql, []).startswith("Database 'shop' does not exist")
    odd = pymysql.err.OperationalError(9999, "something new")
    assert connections.friendly_error("sql", odd, sql, []) == "(9999, 'something new')"

    mongo = {"uri": "mongodb+srv://cluster0.example.invalid/", "database": "app"}
    auth = OperationFailure("Authentication failed.", code=18)
    assert connections.friendly_error("nosql", auth, mongo, []).startswith("Wrong username or password")
    denied_db = OperationFailure("not authorized on app to execute command", code=13)
    assert connections.friendly_error("nosql", denied_db, mongo, []).startswith("This user has no access")
    timeout = ServerSelectionTimeoutError("cluster0.example.invalid:27017: timed out, Topology Description: ...")
    assert "Network Access" in connections.friendly_error("nosql", timeout, mongo, [])

    # End to end through try_sql: a closed local port is "could not reach", with the port named.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    ok, message, _ = connections.try_sql("mysql", {**sql, "host": "127.0.0.1", "port": port})
    assert not ok and message.startswith(f"Could not reach the server at 127.0.0.1:{port}.") and "pw-x" not in message


def test_try_sql_gives_up_quickly_on_a_silent_server(monkeypatch):
    # A-113: a port that accepts TCP but never sends a MySQL greeting must not hang for the 300 s
    # read_timeout meant for real queries.
    import socket
    import time

    monkeypatch.setattr(connections, "TEST_IO_TIMEOUT_S", 1)
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()  # the kernel completes the handshake; nothing ever answers
        port = server.getsockname()[1]
        started = time.monotonic()
        ok, message, _ = connections.try_sql("mysql", {"host": "127.0.0.1", "port": port, "username": "u"})
    assert time.monotonic() - started < 4
    assert not ok and message.startswith(f"The server at 127.0.0.1:{port} accepted the connection")


def test_managed_create_drops_database_when_commit_fails(client, db, project_setup, fake_provisioning, monkeypatch):
    # A-110: a failure after provisioning (audit or commit) must not leave an orphaned database and user.
    from app.routers import data_sources as router

    monkeypatch.setattr(router, "provisioning", fake_provisioning)

    def boom(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(router.audit, "record", boom)
    s = project_setup
    body = {"kind": "sql", "mode": "managed", "engine": "mariadb", "name": "main"}
    with pytest.raises(RuntimeError):
        client.post(f"{s['base']}/data-sources", json=body, headers=s["admin"])
    assert fake_provisioning.dropped == [(s["project"].id, "sql", "main")]
    assert db.scalar(select(DataSource).where(DataSource.name == "main")) is None
