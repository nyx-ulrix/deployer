"""End-to-end checks against real MariaDB 11 and MongoDB 5.0 servers.

Skipped unless both are configured, e.g.::

    docker run -d --name dpl-it-mariadb -e MARIADB_ROOT_PASSWORD=test -p 13306:3306 mariadb:11
    docker run -d --name dpl-it-mongo -e MONGO_INITDB_ROOT_USERNAME=admin \
        -e MONGO_INITDB_ROOT_PASSWORD=test -p 37017:27017 mongo:5.0
    DEPLOYER_IT_MARIADB_URL=mysql://root:test@127.0.0.1:13306 \
    DEPLOYER_IT_MONGO_URI=mongodb://admin:test@127.0.0.1:37017 pytest tests/integration
"""

import io
import os
import zipfile
from urllib.parse import urlsplit

import pymysql
import pytest
from pymongo import MongoClient
from sqlalchemy import select

from app.config import get_settings
from app.models import DataSource, Project, User
from app.services import connections, provisioning

MARIADB_URL = os.environ.get("DEPLOYER_IT_MARIADB_URL")
MONGO_URI = os.environ.get("DEPLOYER_IT_MONGO_URI")

pytestmark = pytest.mark.skipif(
    not (MARIADB_URL and MONGO_URI), reason="set DEPLOYER_IT_MARIADB_URL and DEPLOYER_IT_MONGO_URI"
)

PASS = "integration passphrase 123"


@pytest.fixture
def managed_servers(monkeypatch):
    settings = get_settings()
    m = urlsplit(MARIADB_URL)
    g = urlsplit(MONGO_URI)
    monkeypatch.setattr(settings, "mariadb_host", m.hostname)
    monkeypatch.setattr(settings, "mariadb_port", m.port or 3306)
    monkeypatch.setattr(settings, "mariadb_root_password", m.password or "")
    monkeypatch.setattr(settings, "mongo_host", g.hostname)
    monkeypatch.setattr(settings, "mongo_port", g.port or 27017)
    monkeypatch.setattr(settings, "mongo_root_username", g.username or "")
    monkeypatch.setattr(settings, "mongo_root_password", g.password or "")
    monkeypatch.setattr(settings, "managed_mongodb_enabled", True)
    provisioning.mariadb_root_engine.cache_clear()
    provisioning.mongo_root_client.cache_clear()
    created: list[DataSource] = []
    yield created
    from app.db import get_sessionmaker

    session = get_sessionmaker()()
    try:
        for ds in session.scalars(select(DataSource).where(DataSource.mode == "managed")):
            try:
                provisioning.drop_managed_source(session, ds)
            except Exception:  # noqa: BLE001
                pass
    finally:
        session.close()
    connections.dispose_all()
    provisioning.mariadb_root_engine.cache_clear()
    provisioning.mongo_root_client.cache_clear()


def _root_mysql():
    m = urlsplit(MARIADB_URL)
    return pymysql.connect(host=m.hostname, port=m.port or 3306, user=m.username, password=m.password)


def test_managed_lifecycle_and_roundtrip(client, db, managed_servers, make_user, make_project, auth_headers):
    owner = make_user("owner@example.com", owner=True)
    project = make_project(owner, "IT Shop")
    h = auth_headers(owner)
    base = f"/v1/projects/{project.id}"

    # --- provisioning -------------------------------------------------------------------------
    sql = client.post(
        f"{base}/data-sources", json={"kind": "sql", "mode": "managed", "engine": "mariadb", "name": "main"}, headers=h
    )
    assert sql.status_code == 200, sql.text
    sql = sql.json()
    assert sql["database_name"].startswith("p_it_shop_") and sql["status"] == "ok"
    mongo = client.post(
        f"{base}/data-sources",
        json={"kind": "nosql", "mode": "managed", "engine": "mongodb", "name": "docs"},
        headers=h,
    )
    assert mongo.status_code == 200, mongo.text
    mongo = mongo.json()

    conn_info = client.get(f"{base}/data-sources/{sql['id']}/connection", headers=h).json()
    assert conn_info["database"] == sql["database_name"] and len(conn_info["password"]) == 32
    # the dedicated user can only see its own database
    user_conn = pymysql.connect(
        host=conn_info["host"], port=conn_info["port"], user=conn_info["username"], password=conn_info["password"]
    )
    with user_conn.cursor() as cur:
        cur.execute("SHOW DATABASES")
        visible = {r[0] for r in cur.fetchall()}
    user_conn.close()
    assert sql["database_name"] in visible and "mysql" not in visible

    checked = client.post(f"{base}/data-sources/{sql['id']}/check", headers=h).json()
    assert checked["status"] == "ok"

    # --- tables & collections -----------------------------------------------------------------
    users_spec = {
        "name": "users",
        "columns": [
            {"name": "id", "type": "BIGINT UNSIGNED", "primary_key": True, "auto_increment": True},
            {"name": "email", "type": "VARCHAR(255)", "nullable": False, "unique": True},
            {"name": "is_admin", "type": "BOOLEAN", "default": "FALSE", "nullable": False},
            {"name": "avatar", "type": "BLOB"},
            {"name": "balance", "type": "DECIMAL(10,2)", "default": "0.00"},
        ],
        "timestamps": True,
    }
    resp = client.post(f"{base}/data-sources/{sql['id']}/tables", json=users_spec, headers=h)
    assert resp.status_code == 200, resp.text
    entity = resp.json()
    fields = {f["name"]: f for f in entity["fields"]}
    assert fields["id"]["data_type"] == "bigint(20) unsigned" and fields["id"]["primary_key"]
    assert fields["email"]["unique"] and fields["created_at"]["data_type"] == "datetime"

    orders_spec = {
        "name": "orders",
        "columns": [
            {"name": "id", "type": "INT", "primary_key": True, "auto_increment": True},
            {
                "name": "user_id",
                "type": "BIGINT UNSIGNED",
                "nullable": False,
                "references": {"table": "users", "column": "id", "on_delete": "cascade"},
            },
            {"name": "note", "type": "TEXT"},
        ],
    }
    assert client.post(f"{base}/data-sources/{sql['id']}/tables", json=orders_spec, headers=h).status_code == 200
    dup = client.post(f"{base}/data-sources/{sql['id']}/tables", json=orders_spec, headers=h)
    assert dup.status_code == 409

    coll = client.post(
        f"{base}/data-sources/{mongo['id']}/collections",
        json={"name": "events", "validator": {"bsonType": "object", "required": ["kind"]}},
        headers=h,
    )
    assert coll.status_code == 200, coll.text
    assert coll.json()["validator"] == {"$jsonSchema": {"bsonType": "object", "required": ["kind"]}}
    assert (
        client.post(f"{base}/data-sources/{mongo['id']}/collections", json={"name": "users"}, headers=h).status_code
        == 200
    )

    # --- data browser -------------------------------------------------------------------------
    rows = f"{base}/data-sources/{sql['id']}/tables/users/rows"
    r1 = client.post(
        rows, json={"values": {"email": "a@example.com", "avatar": {"$base64": "AAEC"}, "balance": "12.50"}}, headers=h
    )
    assert r1.status_code == 200, r1.text
    r1 = r1.json()["row"]
    assert r1["id"] == 1 and r1["avatar"] == {"$base64": "AAEC"} and r1["balance"] == "12.50"
    assert r1["created_at"] and "T" in r1["created_at"]
    client.post(rows, json={"values": {"email": "b@example.com"}}, headers=h)
    orders = f"{base}/data-sources/{sql['id']}/tables/orders/rows"
    assert client.post(orders, json={"values": {"user_id": 1, "note": "100% done"}}, headers=h).status_code == 200
    bad_fk = client.post(orders, json={"values": {"user_id": 99}}, headers=h)
    assert bad_fk.status_code == 400 and bad_fk.json()["error"]["code"] == "query_failed"
    page = client.get(f"{rows}?order_by=email&order=desc&limit=1", headers=h).json()
    assert page["total"] == 2 and page["rows"][0]["email"] == "b@example.com"
    upd = client.patch(rows, json={"pk": {"id": 2}, "values": {"is_admin": True}}, headers=h)
    assert upd.status_code == 200 and upd.json()["row"]["is_admin"] == 1

    docs = f"{base}/data-sources/{mongo['id']}/collections/events/documents"
    d1 = client.post(
        docs,
        json={
            "document": {
                "kind": "signup",
                "user_id": 1,
                "at": {"$date": "2024-01-01T00:00:00Z"},
                "meta": {"ip": "1.2.3.4"},
            }
        },
        headers=h,
    )
    assert d1.status_code == 200, d1.text
    d1 = d1.json()["document"]
    doc_id = d1["_id"]["$oid"]
    invalid = client.post(docs, json={"document": {"no_kind": True}}, headers=h)
    assert invalid.status_code == 400
    client.post(docs, json={"document": {"_id": "custom", "kind": "login", "user_id": "1"}}, headers=h)
    listed = client.get(docs, params={"filter": '{"kind": "signup"}'}, headers=h).json()
    assert listed["total"] == 1 and listed["documents"][0]["meta"] == {"ip": "1.2.3.4"}
    forbidden = client.get(docs, params={"filter": '{"$where": "true"}'}, headers=h)
    assert forbidden.status_code == 400 and forbidden.json()["error"]["code"] == "forbidden_operator"
    patched = client.patch(f"{docs}/{doc_id}", json={"set": {"meta.ip": "5.6.7.8"}, "unset": ["at"]}, headers=h).json()
    assert patched["document"]["meta"]["ip"] == "5.6.7.8" and "at" not in patched["document"]
    assert client.patch(f"{docs}/custom", json={"set": {"n": 1}}, headers=h).status_code == 200
    MongoClient(MONGO_URI)[mongo["database_name"]]["events"].create_index("user_id")

    # --- schema, conventions & export ---------------------------------------------------------
    link = {
        "from_source_id": mongo["id"],
        "from_entity": "events",
        "from_field": "user_id",
        "to_source_id": sql["id"],
        "to_entity": "users",
        "to_field": "id",
        "cardinality": "many_to_one",
    }
    assert client.post(f"{base}/schema/links", json=link, headers=h).status_code == 200

    schema = client.get(f"{base}/schema?sample=50", headers=h).json()
    by_kind = {s["kind"]: s for s in schema["sources"]}
    assert by_kind["sql"]["status"] == "ok", by_kind["sql"]["error"]
    assert by_kind["nosql"]["status"] == "ok", by_kind["nosql"]["error"]
    sql_rels = by_kind["sql"]["relationships"]
    assert {
        "from_entity": "orders",
        "from_fields": ["user_id"],
        "to_entity": "users",
        "to_fields": ["id"],
        "cardinality": "many_to_one",
        "origin": "foreign_key",
    } in sql_rels
    events = next(e for e in by_kind["nosql"]["entities"] if e["name"] == "events")
    ev_fields = {f["name"]: f for f in events["fields"]}
    assert ev_fields["user_id"]["data_type"] == "int|string" and ev_fields["user_id"]["indexed"]
    assert ev_fields["meta.ip"]["occurrence"] == 0.5
    assert events["validator"]["$jsonSchema"]["required"] == ["kind"]
    inferred = by_kind["nosql"]["relationships"]
    assert any(r["from_entity"] == "events" and r["to_entity"] == "users" for r in inferred)
    rules = {(i["rule"], i["entity"], i["field"]) for i in schema["conventions"]}
    assert ("S7", "events", "user_id") in rules
    assert ("X2", "events", "user_id") not in rules

    sql_export = client.get(f"{base}/schema/export?format=sql", headers=h).text
    assert sql_export.index("CREATE TABLE `users`") < sql_export.index("CREATE TABLE `orders`")
    assert "SET FOREIGN_KEY_CHECKS=0;" in sql_export
    mongo_export = client.get(f"{base}/schema/export?format=mongo", headers=h).text
    assert 'database.createCollection("events", EJSON.deserialize(' in mongo_export
    assert '"user_id": 1' in mongo_export
    assert '// database.runCommand({ collMod: "users"' not in mongo_export  # empty collection: nothing inferred
    bundle = client.get(f"{base}/schema/export?format=bundle", headers=h)
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
        assert "CREATE TABLE `orders`" in zf.read("schema.sql").decode()

    # --- projects export -> import ------------------------------------------------------------
    exported = client.post("/v1/projects/export", json={"project_ids": [project.id], "passphrase": PASS}, headers=h)
    assert exported.status_code == 200, exported.text
    importer = make_user("importer@example.com")
    ih = auth_headers(importer)
    imported = client.post(
        "/v1/projects/import", files={"file": ("p.json", exported.content)}, data={"passphrase": PASS}, headers=ih
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["summary"]["rows"] == 3 and body["summary"]["documents"] == 2
    new_pid = body["projects"][0]["id"]
    new_sources = client.get(f"/v1/projects/{new_pid}/data-sources", headers=ih).json()
    new_sql = next(s for s in new_sources if s["kind"] == "sql")
    new_mongo = next(s for s in new_sources if s["kind"] == "nosql")
    assert new_sql["database_name"] != sql["database_name"]
    new_rows = client.get(f"/v1/projects/{new_pid}/data-sources/{new_sql['id']}/tables/users/rows", headers=ih).json()
    assert [r["email"] for r in new_rows["rows"]] == ["a@example.com", "b@example.com"]
    assert new_rows["rows"][0]["avatar"] == {"$base64": "AAEC"} and new_rows["rows"][0]["balance"] == "12.50"
    new_orders = client.get(
        f"/v1/projects/{new_pid}/data-sources/{new_sql['id']}/tables/orders/rows", headers=ih
    ).json()
    assert new_orders["rows"][0]["note"] == "100% done"
    new_docs = client.get(
        f"/v1/projects/{new_pid}/data-sources/{new_mongo['id']}/collections/events/documents", headers=ih
    ).json()
    assert new_docs["total"] == 2
    assert any(d["_id"] == {"$oid": doc_id} for d in new_docs["documents"])
    new_schema = client.get(f"/v1/projects/{new_pid}/schema", headers=ih).json()
    new_events = next(
        e for s in new_schema["sources"] if s["kind"] == "nosql" for e in s["entities"] if e["name"] == "events"
    )
    assert {tuple(i["fields"]) for i in new_events["indexes"]} >= {("_id",), ("user_id",)}
    assert new_events["validator"]["$jsonSchema"]["required"] == ["kind"]
    assert len(new_schema["links"]) == 1

    # --- instance export -> wipe -> setup import ----------------------------------------------
    inst = client.post("/v1/instance/export", json={"passphrase": PASS}, headers=h)
    assert inst.status_code == 200, inst.text
    old_names = {s.id: s.database_name for s in db.scalars(select(DataSource))}
    for ds in db.scalars(select(DataSource)):
        provisioning.drop_managed_source(db, ds)
    from app.models import ApiKey, ProjectInvite, ProjectMember, SchemaLink, UserIdentity

    for model in (SchemaLink, ApiKey, ProjectInvite, ProjectMember, DataSource, Project, UserIdentity):
        db.query(model).delete()
    db.query(User).delete()
    db.commit()
    connections.dispose_all()

    restored = client.post("/v1/setup/import", files={"file": ("i.json", inst.content)}, data={"passphrase": PASS})
    assert restored.status_code == 200, restored.text
    summary = restored.json()["summary"]
    assert summary["users"] == 2 and summary["projects"] == 2 and summary["data_sources"] == 4
    assert summary["rows"] == 6 and summary["documents"] == 4
    db.expire_all()
    for ds in db.scalars(select(DataSource)):
        assert ds.database_name == old_names[ds.id]  # names were free again, so they are kept
    h2 = auth_headers(db.get(User, owner.id))
    again = client.get(f"{base}/data-sources/{sql['id']}/tables/users/rows", headers=h2).json()
    assert again["total"] == 2
    conn2 = client.get(f"{base}/data-sources/{sql['id']}/connection", headers=h2).json()
    assert conn2["password"] != conn_info["password"]  # fresh credentials on the new host


def test_provisioning_identifiers_are_validated(managed_servers):
    with pytest.raises(ValueError):
        provisioning.create_mariadb_database("p_x`; DROP DATABASE mysql; --", "u_000000000000", "a" * 32)
    with pytest.raises(ValueError):
        provisioning.create_mongo_database("p_ok", "u_bad'user", "a" * 32)
    name = provisioning.generate_database_name("A very-long Slug!" * 10)
    assert len(name) <= 64 and provisioning.GENERATED_DB_NAME_RE.fullmatch(name)


def test_project_create_and_delete_with_provisioning(client, managed_servers, make_user, auth_headers):
    owner = make_user("owner@example.com", owner=True)
    h = auth_headers(owner)
    resp = client.post("/v1/projects", json={"name": "Prov Test", "provision": {"sql": True, "nosql": True}}, headers=h)
    assert resp.status_code == 200, resp.text
    project = resp.json()
    assert project["data_source_counts"] == {"sql": 1, "nosql": 1}
    sources = client.get(f"/v1/projects/{project['id']}/data-sources", headers=h).json()
    names = {s["kind"]: s["database_name"] for s in sources}
    with _root_mysql() as conn, conn.cursor() as cur:
        cur.execute("SHOW DATABASES LIKE %s", (names["sql"],))
        assert cur.fetchone()
    resp = client.delete(f"/v1/projects/{project['id']}?confirm={project['slug']}", headers=h)
    assert resp.status_code == 200, resp.text
    with _root_mysql() as conn, conn.cursor() as cur:
        cur.execute("SHOW DATABASES LIKE %s", (names["sql"],))
        assert cur.fetchone() is None
    root = MongoClient(MONGO_URI)
    assert names["nosql"] not in root.list_database_names()
    assert root["admin"]["system.users"].count_documents({"db": names["nosql"]}) == 0
