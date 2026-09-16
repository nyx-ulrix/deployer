"""Route tests for data sources, schema, links and the SQL data browser.

External connections are faked: `connections.try_config` is patched and SQL engines point at a local
SQLite file, so no real MariaDB/Postgres/MongoDB is needed.
"""

import io
import zipfile

import pytest
from sqlalchemy import create_engine, select

from app.crypto import decrypt_json
from app.models import AuditLog, DataSource, SchemaLink
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
