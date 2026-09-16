import re

from app.crypto import sha256_hex
from app.models import ApiKey, AuditLog


def test_api_key_lifecycle(client, owner, make_user, make_project, auth_headers, db):
    admin, dev = make_user(), make_user()
    project = make_project(owner, members={admin: "admin", dev: "developer"})
    base = f"/v1/projects/{project.id}/api-keys"
    h = auth_headers(admin)

    assert client.get(base, headers=auth_headers(dev)).status_code == 403
    assert client.post(base, json={"name": "x", "role": "anon"}, headers=auth_headers(dev)).status_code == 403
    assert client.post(base, json={"name": "x", "role": "root"}, headers=h).status_code == 422
    assert client.post(base, json={"name": " ", "role": "anon"}, headers=h).status_code == 422

    resp = client.post(base, json={"name": "Web app", "role": "service"}, headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    secret = body["secret"]
    assert re.fullmatch(r"dpl_service_[A-Za-z0-9_-]{43}", secret)
    key = body["api_key"]
    assert set(key) == {"id", "name", "prefix", "role", "created_at", "last_used_at", "revoked_at"}
    assert key["prefix"] == secret[:16]
    assert key["role"] == "service" and key["revoked_at"] is None

    row = db.get(ApiKey, key["id"])
    assert row.key_hash == sha256_hex(secret)
    assert row.created_by_id == admin.id

    listed = client.get(base, headers=h).json()
    assert [k["id"] for k in listed] == [key["id"]]
    assert "secret" not in listed[0]

    resp = client.delete(f"{base}/{key['id']}", headers=h)
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    listed = client.get(base, headers=h).json()
    assert listed[0]["revoked_at"] is not None
    assert client.delete(f"{base}/nope", headers=h).status_code == 404

    other = make_project(owner, "Other")
    assert (
        client.delete(f"/v1/projects/{other.id}/api-keys/{key['id']}", headers=auth_headers(owner)).status_code == 404
    )
    assert db.query(AuditLog).filter_by(action="api_key.create").count() == 1
    assert db.query(AuditLog).filter_by(action="api_key.revoke").count() == 1
