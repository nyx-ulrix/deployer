"""Project API keys on the data, query and schema routes (docs/DATA_API.md)."""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import ApiKey, AuditLog, QueryRun, User, utcnow
from app.services import connections


@pytest.fixture
def setup(client, db, project_setup, sqlite_engine, monkeypatch, make_source):
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: sqlite_engine)
    project = project_setup["project"]
    ds = make_source(project)

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
    assert "anon key is read-only; use a service key" in denied.json()["error"]["message"]  # A-196

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


def test_query_route_refuses_anon_keys(client, db, setup):
    """A-031: an anon key may be public, and each run can hold a query slot for up to 120 s and log
    200 000 chars, so the query console is service-key only (humans keep the viewer rule)."""
    _, anon = setup["make_key"]("anon")
    refused = client.post(setup["query"], json={"query": "SELECT id FROM items"}, headers=anon)
    assert refused.status_code == 403 and "service key" in refused.json()["error"]["message"]
    db.expire_all()
    assert db.scalar(select(QueryRun)) is None  # refused before anything runs or is logged


def test_query_route_logs_api_layout(client, db, setup):
    key, service = setup["make_key"]("service")
    ok = client.post(setup["query"], json={"query": "SELECT id FROM items", "layout": "editor"}, headers=service)
    assert ok.status_code == 200, ok.text
    assert (
        client.post(setup["query"], json={"query": "DELETE FROM items WHERE id = 1"}, headers=service).status_code
        == 200
    )

    db.expire_all()
    runs = list(db.scalars(select(QueryRun).order_by(QueryRun.created_at, QueryRun.id)))
    assert [r.layout for r in runs] == ["api", "api"]
    assert [r.status for r in runs] == ["ok", "ok"]
    assert runs[0].user_id == db.get(ApiKey, key["id"]).created_by_id
    audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "query.run")))
    assert audits[0].details["api_key_id"] == key["id"]


def test_acting_user_falls_back_to_owner(client, db, setup, make_user, auth_headers):
    admin = make_user()
    from app.models import ProjectMember

    db.add(ProjectMember(project_id=setup["project"].id, user_id=admin.id, role="admin"))
    db.commit()
    key, h = setup["make_key"]("service", auth_headers(admin))
    admin.is_active = False
    db.commit()
    assert client.post(setup["query"], json={"query": "SELECT 1"}, headers=h).status_code == 200
    db.expire_all()
    run = db.scalar(select(QueryRun))
    assert run.user_id == setup["project"].owner_id != admin.id
    assert db.get(User, run.user_id).is_active


def test_keys_stop_when_project_owner_is_disabled(client, db, setup):
    # A-023: disabling an account must also cut off the API keys of the projects it owns.
    key, h = setup["make_key"]("anon")
    db.get(User, setup["project"].owner_id).is_active = False
    db.commit()
    resp = client.post(setup["query"], json={"query": "SELECT 1"}, headers=h)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "account_disabled"


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


def test_per_key_rate_limit(client, setup, set_setting):
    """docs/MONITORING.md: `api_key_rate_limit` requests per minute per key; 429 with Retry-After."""
    set_setting("api_key_rate_limit", 2)
    _, h = setup["make_key"]("anon")
    _, other = setup["make_key"]("anon")
    url = f"/v1/projects/{setup['project'].id}/schema/links"
    assert [client.get(url, headers=h).status_code for _ in range(2)] == [200, 200]
    limited = client.get(url, headers=h)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    retry_after = limited.json()["error"]["details"]["retry_after"]
    assert 1 <= int(limited.headers["Retry-After"]) <= 60 and retry_after <= 60
    assert client.get(url, headers=other).status_code == 200  # counted per key
    assert client.get(url, headers=setup["owner"]).status_code == 200  # users are unaffected

    set_setting("api_key_rate_limit", 0)  # 0 = unlimited
    assert client.get(url, headers=h).status_code == 200


REPO = Path(__file__).resolve().parents[2]


def test_anon_key_is_not_advertised_as_public():
    """A-004: an anon key reads every table and collection (no per-table allowlist yet), so the
    docs, the agent skill and the dashboard must say so instead of calling it the public-client key."""
    places = {
        "docs/DATA_API.md": "read ALL data",
        "skills/deploy-website/SKILL.md": "reads **all** data",
        "dashboard/src/features/projects/ApiKeysTab.tsx": "can read ALL data",
    }
    misleading = re.compile(r"safe for browsers|public clients \||anon . public|Public key for client apps", re.I)
    for rel, warning in places.items():
        text = (REPO / rel).read_text(encoding="utf-8")
        assert warning in text, rel
        assert not misleading.search(text), (rel, misleading.search(text))


def test_cors_only_on_key_routes_and_without_credentials(client, setup):
    """A-018: browsers can call the data API with a key, but cookie/session routes stay same-origin."""
    _, h = setup["make_key"]("anon")
    origin = {"Origin": "https://site.example"}
    preflight = {**origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}

    resp = client.options(setup["rows"], headers=preflight)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in resp.headers

    resp = client.get(setup["rows"], headers={**h, **origin})
    assert resp.status_code == 200 and resp.headers["access-control-allow-origin"] == "*"

    # V-04: Firestore subcollection paths (encoded, as docs/DATA_API.md fetches them) and the listing.
    docs = f"{setup['base']}/{setup['ds'].id}/collections"
    for path in (
        f"{docs}/users%2Fu1%2Forders/documents",
        f"{docs}/users/u1/orders/documents/o1",
        f"{docs}/users/documents/x/collections",
        f"{setup['base']}/{setup['ds'].id}/rtdb",  # the Realtime Database route takes keys too
    ):
        resp = client.options(path, headers=preflight)
        assert resp.status_code == 200 and resp.headers["access-control-allow-origin"] == "*", path

    for path in ("/v1/auth/refresh", f"/v1/projects/{setup['project'].id}/api-keys", f"{docs}/users"):
        resp = client.options(path, headers=preflight)
        assert "access-control-allow-origin" not in resp.headers, path
