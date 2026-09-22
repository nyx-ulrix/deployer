import os
import re

from app.crypto import sha256_hex
from app.models import ApiKey, AuditLog
from app.services import transfer


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
    assert set(key) == {"id", "name", "prefix", "role", "created_at", "last_used_at", "revoked_at", "revealable"}
    assert key["revealable"] is True
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


def _create(client, project, headers, role="anon") -> tuple[dict, str]:
    resp = client.post(f"/v1/projects/{project.id}/api-keys", json={"name": "k", "role": role}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["api_key"], resp.json()["secret"]


def test_reveal(client, owner, make_user, make_project, auth_headers, db):
    admin, dev = make_user(), make_user()
    project = make_project(owner, members={admin: "admin", dev: "developer"})
    h = auth_headers(admin)
    key, secret = _create(client, project, h)
    url = f"/v1/projects/{project.id}/api-keys/{key['id']}/reveal"

    assert client.get(url, headers=h).json() == {"secret": secret}
    assert client.get(url, headers=auth_headers(dev)).status_code == 403
    other = make_project(owner, "Other")
    assert (
        client.get(f"/v1/projects/{other.id}/api-keys/{key['id']}/reveal", headers=auth_headers(owner)).status_code
        == 404
    )
    assert db.query(AuditLog).filter_by(action="api_key.reveal").count() == 1

    old = db.get(ApiKey, key["id"])
    old.secret_encrypted = None
    db.commit()
    resp = client.get(url, headers=h)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_revealable"
    assert client.get(f"/v1/projects/{project.id}/api-keys", headers=h).json()[0]["revealable"] is False

    key2, _ = _create(client, project, h)
    client.delete(f"/v1/projects/{project.id}/api-keys/{key2['id']}", headers=h)
    resp = client.get(f"/v1/projects/{project.id}/api-keys/{key2['id']}/reveal", headers=h)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "api_key_revoked"


def test_config_download(client, owner, make_project, auth_headers, set_setting, db):
    from app.crypto import encrypt_json
    from app.models import DataSource

    project = make_project(owner)
    for name, kind in [("main", "sql"), ("docs", "nosql")]:
        db.add(
            DataSource(
                project_id=project.id,
                name=name,
                kind=kind,
                engine="mariadb" if kind == "sql" else "mongodb",
                mode="external",
                database_name="app",
                config_encrypted=encrypt_json({}),
            )
        )
    db.commit()
    set_setting("public_url", "https://deployer.example.com/")
    h = auth_headers(owner)
    key, secret = _create(client, project, h, role="service")

    resp = client.get(f"/v1/projects/{project.id}/api-keys/{key['id']}/config", headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-disposition"] == f'attachment; filename="deployer-{project.slug}-service.json"'
    assert resp.headers["content-type"].startswith("application/json")
    cfg = resp.json()["deployer"]
    assert cfg["url"] == "https://deployer.example.com/v1"
    assert cfg["project_id"] == project.id and cfg["project"] == project.slug
    assert cfg["role"] == "service" and cfg["api_key"] == secret
    assert sorted((s["name"], s["kind"], s["engine"]) for s in cfg["data_sources"]) == [
        ("docs", "nosql", "mongodb"),
        ("main", "sql", "mariadb"),
    ]
    assert all(set(s) == {"id", "name", "kind", "engine"} for s in cfg["data_sources"])
    assert cfg["endpoints"] == {
        "rows": "/projects/{project_id}/data-sources/{source_id}/tables/{table}/rows",
        "documents": "/projects/{project_id}/data-sources/{source_id}/collections/{name}/documents",
        "query": "/projects/{project_id}/data-sources/{source_id}/query",
        "schema": "/projects/{project_id}/schema",
    }
    assert cfg["generated_at"]
    other = make_project(owner, "Other")
    assert client.get(f"/v1/projects/{other.id}/api-keys/{key['id']}/config", headers=h).status_code == 404


def test_secret_survives_export_import(client, owner, make_user, make_project, auth_headers, db):
    project = make_project(owner)
    key, secret = _create(client, project, auth_headers(owner))
    passphrase = "correct horse battery staple"
    path, _ = transfer.build_export_file(db, scope="projects", projects=[project], passphrase=passphrase)
    try:
        payload = transfer.read_export_file(path, passphrase, "projects")
    finally:
        os.unlink(path)
    [exported] = payload["api_keys"]
    assert exported["secret"] == secret and "secret_encrypted" not in exported

    db.query(ApiKey).delete()  # otherwise the same hash is skipped as a duplicate
    db.commit()
    importer = make_user()
    [imported], _ = transfer.import_projects(db, payload, importer)
    db.commit()
    [new_key] = client.get(f"/v1/projects/{imported.id}/api-keys", headers=auth_headers(importer)).json()
    assert new_key["id"] != key["id"] and new_key["revealable"] is True
    resp = client.get(f"/v1/projects/{imported.id}/api-keys/{new_key['id']}/reveal", headers=auth_headers(importer))
    assert resp.json() == {"secret": secret}
