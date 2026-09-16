"""Export/import file format and platform-metadata roundtrips (no managed databases involved)."""

import base64
import gzip
import json
import os
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.crypto import decrypt_json, decrypt_with_passphrase, encrypt_json, encrypt_with_passphrase
from app.errors import ApiError
from app.models import (
    ApiKey,
    DataSource,
    InstanceSetting,
    Project,
    ProjectInvite,
    ProjectMember,
    SchemaLink,
    User,
    UserIdentity,
    utcnow,
)
from app.services import instance_settings, transfer

PASS = "correct horse battery staple"

# Fake credential, assembled at runtime so secret scanners never see a literal URI with a password.
FAKE_ATLAS_URI = "mongodb+srv://" + "u:fake-password" + "@cluster.example.invalid"


@pytest.fixture
def populated(db, make_user, make_project):
    owner = make_user("owner@example.com", owner=True, display_name="Owner")
    member = make_user("member@example.com")
    project = make_project(owner, "Shop", members={member: "developer"})
    db.add(UserIdentity(user_id=owner.id, provider="github", provider_user_id="42", provider_username="octo"))
    instance_settings.set_value(db, "google_client_secret", "g-secret")
    instance_settings.set_value(db, "allow_signup", True)
    ext = DataSource(
        project_id=project.id,
        name="warehouse",
        kind="sql",
        engine="postgresql",
        mode="external",
        database_name="wh",
        config_encrypted=encrypt_json(
            {"host": "pg.example.com", "port": 5432, "username": "u", "password": "pw", "database": "wh", "tls": True}
        ),
    )
    mongo = DataSource(
        project_id=project.id,
        name="atlas",
        kind="nosql",
        engine="mongodb",
        mode="external",
        database_name="app",
        config_encrypted=encrypt_json({"uri": FAKE_ATLAS_URI, "database": "app"}),
    )
    db.add_all([ext, mongo])
    db.flush()
    db.add(
        SchemaLink(
            project_id=project.id,
            from_source_id=mongo.id,
            from_entity="events",
            from_field="user_id",
            to_source_id=ext.id,
            to_entity="users",
            to_field="id",
            cardinality="many_to_one",
        )
    )
    db.add(
        ApiKey(
            project_id=project.id,
            name="web",
            role="anon",
            prefix="dpl_anon_abc",
            key_hash="h" * 64,
            created_by_id=owner.id,
        )
    )
    db.add(
        ProjectInvite(
            project_id=project.id,
            email="new@example.com",
            role="viewer",
            token_hash="t" * 64,
            invited_by_id=owner.id,
            expires_at=utcnow() + timedelta(days=3),
        )
    )
    db.add(
        ProjectInvite(
            project_id=project.id,
            email="old@example.com",
            role="viewer",
            token_hash="o" * 64,
            invited_by_id=owner.id,
            expires_at=utcnow() - timedelta(days=3),
        )
    )
    db.commit()
    return {"owner": owner, "member": member, "project": project, "ext": ext, "mongo": mongo}


def _read_plain(path):
    with open(path, encoding="utf-8") as fh:
        outer = json.load(fh)
    plain = gzip.decompress(decrypt_with_passphrase(outer["encryption"], outer["payload"], PASS))
    return outer, json.loads(plain)


def test_export_file_format_instance(db, populated):
    path, counts = transfer.build_export_file(db, scope="instance", projects=[populated["project"]], passphrase=PASS)
    try:
        outer, payload = _read_plain(path)
    finally:
        os.unlink(path)
    assert outer["format"] == "deployer-export" and outer["version"] == 1 and outer["scope"] == "instance"
    assert outer["encryption"]["kdf"] == "scrypt" and outer["encryption"]["cipher"] == "AES-256-GCM"
    assert outer["created_at"].endswith("Z") and outer["app_version"]
    assert counts == {"users": 2, "projects": 1, "data_sources": 2, "rows": 0, "documents": 0}

    assert payload["version"] == 1 and payload["scope"] == "instance"
    settings = {s["key"]: s for s in payload["instance_settings"]}
    assert settings["google_client_secret"] == {"key": "google_client_secret", "value": "g-secret", "is_secret": True}
    assert settings["allow_signup"]["value"] is True
    assert {u["email"] for u in payload["users"]} == {"owner@example.com", "member@example.com"}
    assert all("password_hash" in u for u in payload["users"])
    assert len(payload["user_identities"]) == 1
    assert [i["email"] for i in payload["project_invites"]] == ["new@example.com"]
    assert {m["email"] for m in payload["project_members"]} == {"owner@example.com", "member@example.com"}
    ds = {d["name"]: d for d in payload["data_sources"]}
    assert ds["warehouse"]["config"]["password"] == "pw" and "config_encrypted" not in ds["warehouse"]
    assert len(payload["schema_links"]) == 1 and len(payload["api_keys"]) == 1
    assert payload["data"] == {}
    assert "audit_logs" not in payload


def test_projects_scope_omits_instance_data(db, populated):
    path, _ = transfer.build_export_file(db, scope="projects", projects=[populated["project"]], passphrase=PASS)
    try:
        _, payload = _read_plain(path)
    finally:
        os.unlink(path)
    for key in ("instance_settings", "users", "user_identities", "project_invites"):
        assert key not in payload


def test_read_export_errors(db, populated, tmp_path):
    path, _ = transfer.build_export_file(db, scope="projects", projects=[populated["project"]], passphrase=PASS)
    try:
        with pytest.raises(ApiError) as err:
            transfer.read_export_file(path, "wrong passphrase!!", "projects")
        assert err.value.code == "bad_passphrase"
        with pytest.raises(ApiError) as err:
            transfer.read_export_file(path, PASS, "instance")
        assert err.value.code == "invalid_export"
        with pytest.raises(ApiError) as err:
            transfer.read_export_file(path, "short", "projects")
        assert err.value.status_code == 422
        assert transfer.read_export_file(path, PASS, "projects")["scope"] == "projects"
    finally:
        os.unlink(path)

    garbage = tmp_path / "garbage.json"
    garbage.write_text("not json at all")
    with pytest.raises(ApiError) as err:
        transfer.read_export_file(str(garbage), PASS, "projects")
    assert err.value.code == "invalid_export"

    header, ct = encrypt_with_passphrase(b"not gzip", PASS)
    bogus = tmp_path / "bogus.json"
    bogus.write_text(
        json.dumps(
            {"format": "deployer-export", "version": 1, "scope": "projects", "encryption": header, "payload": ct}
        )
    )
    with pytest.raises(ApiError) as err:
        transfer.read_export_file(str(bogus), PASS, "projects")
    assert err.value.code == "invalid_export"

    tampered = tmp_path / "tampered.json"
    header, ct = encrypt_with_passphrase(gzip.compress(b"{}"), PASS)
    raw = bytearray(base64.b64decode(ct))
    raw[0] ^= 1
    tampered.write_text(
        json.dumps(
            {
                "format": "deployer-export",
                "version": 1,
                "scope": "projects",
                "encryption": header,
                "payload": base64.b64encode(bytes(raw)).decode(),
            }
        )
    )
    with pytest.raises(ApiError) as err:
        transfer.read_export_file(str(tampered), PASS, "projects")
    assert err.value.code == "bad_passphrase"


def test_instance_roundtrip(db, populated):
    path, _ = transfer.build_export_file(db, scope="instance", projects=[populated["project"]], passphrase=PASS)
    try:
        payload = transfer.read_export_file(path, PASS, "instance")
    finally:
        os.unlink(path)
    ids = {
        "owner": populated["owner"].id,
        "project": populated["project"].id,
        "ext": populated["ext"].id,
    }
    hashes = {u["email"]: u["password_hash"] for u in payload["users"]}
    # wipe everything, as on a fresh install
    for model in (SchemaLink, ApiKey, ProjectInvite, ProjectMember, DataSource, Project, UserIdentity, InstanceSetting):
        db.query(model).delete()
    db.query(User).delete()
    db.commit()

    summary = transfer.import_instance(db, payload)
    assert summary == {"users": 2, "projects": 1, "data_sources": 2, "rows": 0, "documents": 0}
    db.expire_all()
    owner = db.get(User, ids["owner"])
    assert owner.is_instance_owner and owner.password_hash == hashes["owner@example.com"]
    assert db.get(Project, ids["project"]).slug == populated["project"].slug
    ext = db.get(DataSource, ids["ext"])
    assert decrypt_json(ext.config_encrypted)["password"] == "pw"
    assert ext.status == "unknown"
    assert instance_settings.get_value(db, "google_client_secret") == "g-secret"
    assert instance_settings.get_value(db, "allow_signup") is True
    assert db.scalar(select(func.count()).select_from(ProjectMember)) == 2
    assert db.scalar(select(func.count()).select_from(ProjectInvite)) == 1
    assert db.scalar(select(func.count()).select_from(SchemaLink)) == 1
    assert db.scalar(select(func.count()).select_from(UserIdentity)) == 1


def test_projects_roundtrip_via_api(client, db, populated, make_user, auth_headers):
    owner_h = auth_headers(populated["owner"])
    pid = populated["project"].id

    member_h = auth_headers(populated["member"])
    denied = client.post("/v1/projects/export", json={"project_ids": [pid], "passphrase": PASS}, headers=member_h)
    assert denied.status_code == 403
    short = client.post("/v1/projects/export", json={"project_ids": [pid], "passphrase": "short"}, headers=owner_h)
    assert short.status_code == 422

    resp = client.post("/v1/projects/export", json={"project_ids": [pid], "passphrase": PASS}, headers=owner_h)
    assert resp.status_code == 200, resp.text
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="deployer-projects-') and disposition.endswith('.json"')
    exported = resp.content

    importer = make_user("importer@example.com")
    imp_h = auth_headers(importer)
    bad = client.post(
        "/v1/projects/import",
        files={"file": ("x.json", exported)},
        data={"passphrase": "nope nope nope"},
        headers=imp_h,
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "bad_passphrase"

    ok = client.post(
        "/v1/projects/import", files={"file": ("x.json", exported)}, data={"passphrase": PASS}, headers=imp_h
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["ok"] is True
    [project] = body["projects"]
    assert project["id"] != pid and project["slug"] != populated["project"].slug
    assert project["my_role"] == "owner" and project["owner_id"] == importer.id
    assert project["data_source_counts"] == {"sql": 1, "nosql": 1}
    summary = body["summary"]
    assert sorted(summary["skipped_members"]) == ["member@example.com", "owner@example.com"]
    assert summary["skipped_api_keys"] == 1  # same key hash still exists on this instance

    db.expire_all()
    new_sources = db.scalars(select(DataSource).where(DataSource.project_id == project["id"])).all()
    assert len(new_sources) == 2 and not {s.id for s in new_sources} & {populated["ext"].id, populated["mongo"].id}
    link = db.scalar(select(SchemaLink).where(SchemaLink.project_id == project["id"]))
    assert link.from_source_id in {s.id for s in new_sources}
    members = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project["id"])).all()
    assert [(m.user_id, m.role) for m in members] == [(importer.id, "owner")]

    wrong_scope = client.post("/setup/import", files={"file": ("x.json", exported)}, data={"passphrase": PASS})
    assert wrong_scope.status_code == 404  # sanity: no route without /v1
    already = client.post("/v1/setup/import", files={"file": ("x.json", exported)}, data={"passphrase": PASS})
    assert already.status_code == 409 and already.json()["error"]["code"] == "already_initialized"


def test_instance_export_route(client, populated, auth_headers):
    resp = client.post("/v1/instance/export", json={"passphrase": PASS}, headers=auth_headers(populated["owner"]))
    assert resp.status_code == 200, resp.text
    assert "deployer-instance-" in resp.headers["content-disposition"]
    assert json.loads(resp.content)["scope"] == "instance"
    denied = client.post("/v1/instance/export", json={"passphrase": PASS}, headers=auth_headers(populated["member"]))
    assert denied.status_code == 403


def test_setup_import_route(client, db, populated, tmp_path):
    path, _ = transfer.build_export_file(db, scope="instance", projects=[populated["project"]], passphrase=PASS)
    with open(path, "rb") as fh:
        content = fh.read()
    os.unlink(path)
    for model in (SchemaLink, ApiKey, ProjectInvite, ProjectMember, DataSource, Project, UserIdentity, InstanceSetting):
        db.query(model).delete()
    db.query(User).delete()
    db.commit()

    short = client.post("/v1/setup/import", files={"file": ("x.json", content)}, data={"passphrase": "short"})
    assert short.status_code == 422
    resp = client.post("/v1/setup/import", files={"file": ("x.json", content)}, data={"passphrase": PASS})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": True,
        "summary": {"users": 2, "projects": 1, "data_sources": 2, "rows": 0, "documents": 0},
    }
    again = client.post("/v1/setup/import", files={"file": ("x.json", content)}, data={"passphrase": PASS})
    assert again.status_code == 409
