"""Project API keys on the data, query and schema routes (docs/DATA_API.md)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import ApiKey, AuditLog, QueryRun, User, utcnow
from app.services import connections
from tests.test_query_console import add_source, project_setup, sqlite_engine  # noqa: F401 (fixtures)


@pytest.fixture
def setup(client, db, project_setup, sqlite_engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: sqlite_engine)
    project = project_setup["project"]
    ds = add_source(db, project)

    def make_key(role: str, headers=None) -> tuple[dict, dict]:
        resp = client.post(
            f"/v1/projects/{project.id}/api-keys",
            json={"name": f"{role} key", "role": role},
            headers=headers or project_setup["owner"],
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["api_key"], {"Authorization": f"Bearer {resp.json()['secret']}"}

    return {
        **project_setup,
        "ds": ds,
        "rows": f"{project_setup['base']}/{ds.id}/tables/items/rows",
        "query": f"{project_setup['base']}/{ds.id}/query",
        "make_key": make_key,
    }


def test_anon_key_reads_but_cannot_write(client, db, setup):
    key, h = setup["make_key"]("anon")
    resp = client.get(setup["rows"], params={"limit": 2, "order_by": "id", "order": "desc"}, headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 7 and [r["id"] for r in body["rows"]] == [7, 6]
    assert body["primary_key"] == ["id"] and "name" in body["columns"]

    denied = client.post(setup["rows"], json={"values": {"name": "new"}}, headers=h)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "forbidden"

    db.expire_all()
    assert db.get(ApiKey, key["id"]).last_used_at is not None
    # JWT users are unaffected.
    assert client.get(setup["rows"], headers=setup["viewer"]).status_code == 200


def test_service_key_writes(client, setup):
    _, h = setup["make_key"]("service")
    resp = client.post(setup["rows"], json={"values": {"name": "inserted"}}, headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["row"]["name"] == "inserted"
    updated = client.patch(setup["rows"], json={"pk": {"id": 8}, "values": {"name": "changed"}}, headers=h)
    assert updated.status_code == 200 and updated.json()["row"]["name"] == "changed"
    assert client.request("DELETE", setup["rows"], json={"pk": {"id": 8}}, headers=h).status_code == 200


def test_revoked_unknown_and_foreign_keys(client, db, setup, make_user, make_project):
    key, h = setup["make_key"]("anon")
    client.delete(f"/v1/projects/{setup['project'].id}/api-keys/{key['id']}", headers=setup["owner"])
    resp = client.get(setup["rows"], headers=h)
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "api_key_revoked"

    unknown = client.get(setup["rows"], headers={"Authorization": "Bearer dpl_anon_" + "x" * 43})
    assert unknown.status_code == 401 and unknown.json()["error"]["code"] == "unauthorized"

    other_owner = make_user()
    other = make_project(other_owner, "Other")
    _, other_h = setup["make_key"]("anon")
    resp = client.get(f"/v1/projects/{other.id}/data-sources/{setup['ds'].id}/tables/items/rows", headers=other_h)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"


def test_keys_only_reach_data_routes(client, setup):
    _, h = setup["make_key"]("service")
    pid = setup["project"].id
    for method, path, json in [
        ("GET", f"/v1/projects/{pid}/members", None),
        ("GET", f"/v1/projects/{pid}/api-keys", None),
        ("POST", f"/v1/projects/{pid}/schema/links", {}),
        ("GET", "/v1/auth/me", None),
    ]:
        resp = client.request(method, path, json=json, headers=h)
        assert resp.status_code == 401, (path, resp.text)
        assert resp.json()["error"]["code"] == "api_key_not_allowed"
    # GET schema routes are allowed.
    assert client.get(f"/v1/projects/{pid}/schema/links", headers=h).status_code == 200
    schema = client.get(f"/v1/projects/{pid}/schema", headers=h)
    assert schema.status_code == 200 and schema.json()["sources"][0]["source_id"] == setup["ds"].id


def test_query_route_logs_api_layout_and_viewer_rule(client, db, setup):
    key, anon = setup["make_key"]("anon")
    ok = client.post(setup["query"], json={"query": "SELECT id FROM items", "layout": "editor"}, headers=anon)
    assert ok.status_code == 200, ok.text
    refused = client.post(setup["query"], json={"query": "DELETE FROM items"}, headers=anon)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "read_only_role"
    _, service = setup["make_key"]("service")
    assert (
        client.post(setup["query"], json={"query": "DELETE FROM items WHERE id = 1"}, headers=service).status_code
        == 200
    )

    db.expire_all()
    runs = list(db.scalars(select(QueryRun).order_by(QueryRun.created_at, QueryRun.id)))
    assert [r.layout for r in runs] == ["api", "api", "api"]
    assert [r.status for r in runs] == ["ok", "refused", "ok"]
    assert runs[0].user_id == db.get(ApiKey, key["id"]).created_by_id
    audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "query.run")))
    assert audits[0].details["api_key_id"] == key["id"]


def test_acting_user_falls_back_to_owner(client, db, setup, make_user, auth_headers):
    admin = make_user()
    from app.models import ProjectMember

    db.add(ProjectMember(project_id=setup["project"].id, user_id=admin.id, role="admin"))
    db.commit()
    key, h = setup["make_key"]("anon", auth_headers(admin))
    admin.is_active = False
    db.commit()
    assert client.post(setup["query"], json={"query": "SELECT 1"}, headers=h).status_code == 200
    db.expire_all()
    run = db.scalar(select(QueryRun))
    assert run.user_id == setup["project"].owner_id != admin.id
    assert db.get(User, run.user_id).is_active


def test_last_used_is_throttled(client, db, setup):
    key, h = setup["make_key"]("anon")
    row = db.get(ApiKey, key["id"])
    recent = utcnow() - timedelta(seconds=10)
    row.last_used_at = recent
    db.commit()
    assert client.get(setup["rows"], headers=h).status_code == 200
    db.expire_all()
    assert db.get(ApiKey, key["id"]).last_used_at == recent
    row.last_used_at = utcnow() - timedelta(minutes=2)
    db.commit()
    assert client.get(setup["rows"], headers=h).status_code == 200
    db.expire_all()
    assert db.get(ApiKey, key["id"]).last_used_at > recent
