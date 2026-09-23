"""Apps API: CRUD + roles, slug/port allocation, env reveal audit, webhook, hostnames, export/import."""

import hashlib
import hmac
import json
import os

import pytest
from sqlalchemy import select

from app.crypto import decrypt_secret
from app.models import ApiKey, AuditLog, Deployment, Domain, Job
from app.services import deployments, rate_limit, transfer
from app.services import remote_access as ra
from tests.apps_support import make_app, new_token
from tests.test_remote_access import fake_cf, link, state_dir  # noqa: F401 (fixtures)

BODY = {"name": "My Shop", "repo_url": "https://github.com/acme/shop", "preset": "node"}


@pytest.fixture
def env(make_user, make_project, auth_headers):
    owner, admin, dev, viewer, outsider = (make_user() for _ in range(5))
    project = make_project(owner, members={admin: "admin", dev: "developer", viewer: "viewer"})
    return {
        "project": project,
        "base": f"/v1/projects/{project.id}/apps",
        "owner": auth_headers(owner),
        "admin": auth_headers(admin),
        "dev": auth_headers(dev),
        "viewer": auth_headers(viewer),
        "outsider": auth_headers(outsider),
        "admin_user": admin,
    }


def create(client, env, **extra):
    resp = client.post(env["base"], json={**BODY, **extra}, headers=env["dev"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_create_list_get_and_roles(client, env, db):
    assert client.post(env["base"], json=BODY, headers=env["viewer"]).status_code == 403
    assert client.post(env["base"], json=BODY, headers=env["outsider"]).status_code == 404
    app = create(client, env)
    assert set(app) == {
        "id", "project_id", "name", "slug", "repo_url", "branch", "root_dir", "preset", "install_command",
        "build_command", "start_command", "output_dir", "container_port", "env_keys", "has_repo_token",
        "api_key_id", "database_access", "port", "local_url", "urls", "live_deployment", "domains", "created_at",
        "updated_at",
    }  # fmt: skip
    assert (app["slug"], app["port"], app["branch"], app["root_dir"]) == ("my-shop", 8100, "main", ".")
    assert app["local_url"] == "http://localhost:8100" and app["urls"] == [] and app["live_deployment"] is None
    assert app["env_keys"] == [] and app["has_repo_token"] is False and app["database_access"] is False
    second = create(client, env, name="My Shop!!")
    assert (second["slug"], second["port"]) == ("my-shop-2", 8101)
    row = db.get(deployments.App, app["id"])
    assert len(decrypt_secret(row.webhook_secret_encrypted)) > 20
    listed = client.get(env["base"], headers=env["viewer"]).json()
    assert [a["id"] for a in listed] == [app["id"], second["id"]]
    assert client.get(f"{env['base']}/{app['id']}", headers=env["viewer"]).json()["name"] == "My Shop"
    assert client.get(f"{env['base']}/{app['id']}", headers=env["outsider"]).status_code == 404


def test_validation_and_ports(client, env, monkeypatch):
    bad = [
        {"repo_url": "http://github.com/acme/shop"},
        {"repo_url": "https://user:token@github.com/acme/shop"},
        {"preset": "dockerfile"},
        {"preset": "python"},
        {"env": {"1BAD": "x"}},
        {"root_dir": "../etc"},
        {"build_command": "npm run build\nrm -rf /"},
        {"branch": "feat branch"},
    ]
    for extra in bad:
        resp = client.post(env["base"], json={**BODY, **extra}, headers=env["dev"])
        assert resp.status_code == 422, (extra, resp.text)
    create(client, env, preset="dockerfile", container_port=5000, root_dir="/web/")
    monkeypatch.setattr(deployments, "PORT_MAX", 8101)
    create(client, env)
    resp = client.post(env["base"], json=BODY, headers=env["dev"])
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "no_ports_left")


def test_patch_token_env_and_api_key(client, env, db):
    app = create(client, env)
    url = f"{env['base']}/{app['id']}"
    token = new_token()
    resp = client.patch(
        url, json={"env": {"A": "1", "B": "2"}, "repo_token": token, "branch": "dev"}, headers=env["dev"]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["env_keys"] == ["A", "B"] and resp.json()["has_repo_token"] and resp.json()["branch"] == "dev"
    assert token not in resp.text
    assert client.patch(url, json={"repo_token": None}, headers=env["dev"]).json()["has_repo_token"] is False
    assert client.patch(url, json={"preset": "python"}, headers=env["dev"]).status_code == 422
    assert client.patch(url, json={"name": "x"}, headers=env["viewer"]).status_code == 403

    key = client.post(
        f"/v1/projects/{env['project'].id}/api-keys", json={"name": "k", "role": "service"}, headers=env["admin"]
    )
    key_id = key.json()["api_key"]["id"]
    assert client.patch(url, json={"api_key_id": key_id}, headers=env["dev"]).json()["api_key_id"] == key_id
    db.get(ApiKey, key_id).secret_encrypted = None
    db.commit()
    assert client.patch(url, json={"api_key_id": key_id}, headers=env["dev"]).status_code == 422
    assert client.patch(url, json={"api_key_id": "nope"}, headers=env["dev"]).status_code == 422

    env_resp = client.get(f"{url}/env", headers=env["admin"])
    assert env_resp.json() == {"env": {"A": "1", "B": "2"}}
    assert client.get(f"{url}/env", headers=env["dev"]).status_code == 403
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "app.env.reveal")).all()
    assert len(audit) == 1 and audit[0].user_id == env["admin_user"].id and audit[0].details["app_id"] == app["id"]


def test_database_access_is_admin_only(client, env, db):
    resp = client.post(env["base"], json={**BODY, "database_access": True}, headers=env["dev"])
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "forbidden"
    assert "Only project admins" in resp.json()["error"]["message"]
    app = create(client, env)
    url = f"{env['base']}/{app['id']}"
    assert client.patch(url, json={"database_access": True}, headers=env["dev"]).status_code == 403
    on = client.patch(url, json={"database_access": True}, headers=env["admin"])
    assert on.status_code == 200 and on.json()["database_access"] is True
    # A developer can still edit the app (even re-sending the current value) and switch it off.
    same = client.patch(url, json={"name": "Renamed", "database_access": True}, headers=env["dev"])
    assert same.status_code == 200 and same.json()["database_access"] is True
    off = client.patch(url, json={"database_access": False}, headers=env["dev"])
    assert off.status_code == 200 and off.json()["database_access"] is False
    created = client.post(env["base"], json={**BODY, "database_access": True}, headers=env["admin"])
    assert created.status_code == 201 and created.json()["database_access"] is True
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "app.database_access")).all()
    assert sorted(a.details["enabled"] for a in audit) == [False, True, True]


def test_webhook(client, env, db, fake_redis, set_setting):
    set_setting("public_url", "https://deployer.example.com")
    app = create(client, env)
    url = f"{env['base']}/{app['id']}"
    hook = client.get(f"{url}/webhook", headers=env["dev"]).json()
    assert hook["url"] == f"https://deployer.example.com/v1/hooks/github/{app['id']}"
    assert client.get(f"{url}/webhook", headers=env["viewer"]).status_code == 403
    rotated = client.post(f"{url}/webhook/rotate", headers=env["dev"]).json()
    assert rotated["secret"] != hook["secret"] and rotated["url"] == hook["url"]
    secret = rotated["secret"]
    assert {a.action for a in db.scalars(select(AuditLog))} >= {"app.webhook.reveal", "app.webhook.rotate"}

    hook_url = f"/v1/hooks/github/{app['id']}"
    body = json.dumps({"zen": "keep it simple"}).encode()
    headers = {"X-Hub-Signature-256": sign(secret, body), "X-GitHub-Event": "ping", "Content-Type": "application/json"}
    assert client.post(hook_url, content=body, headers=headers).json() == {"ok": True}
    bad = client.post(hook_url, content=body, headers={**headers, "X-Hub-Signature-256": sign(hook["secret"], body)})
    assert (bad.status_code, bad.json()["error"]["code"]) == (401, "bad_signature")
    assert client.post(hook_url, content=body, headers={"X-GitHub-Event": "ping"}).status_code == 401
    assert client.post("/v1/hooks/github/nope", content=body, headers=headers).status_code == 404

    def push(ref, sha, message="Fix checkout\n\nlong body"):
        payload = json.dumps({"ref": ref, "after": sha, "head_commit": {"id": sha, "message": message}}).encode()
        return client.post(
            hook_url,
            content=payload,
            headers={**headers, "X-Hub-Signature-256": sign(secret, payload), "X-GitHub-Event": "push"},
        )

    rate_limit.reset(f"rl:hook:{app['id']}")  # every delivery counts, including the rejected ones above
    other = push("refs/heads/feature", "b" * 40)
    assert other.status_code == 200 and other.json() == {"ignored": True}
    assert client.post(hook_url, content=body, headers={**headers, "X-GitHub-Event": "issues"}).json() == {
        "ignored": True
    }
    first = push("refs/heads/main", "c" * 40)
    assert first.status_code == 202, first.text
    dep_id = first.json()["deployment_id"]
    dep = db.get(Deployment, dep_id)
    assert (dep.status, dep.trigger, dep.commit_sha, dep.commit_message) == (
        "queued",
        "webhook",
        "c" * 40,
        "Fix checkout",
    )
    assert dep.job_id and db.get(Job, dep.job_id).params["deployment_id"] == dep_id
    # Coalescing: a push while the deployment is still queued replaces its commit.
    again = push("refs/heads/main", "d" * 40, "Newer")
    assert again.status_code == 202 and again.json()["deployment_id"] == dep_id
    db.expire_all()
    assert db.get(Deployment, dep_id).commit_sha == "d" * 40 and db.get(Deployment, dep_id).commit_message == "Newer"
    assert db.scalar(select(Deployment).where(Deployment.app_id == app["id"], Deployment.id != dep_id)) is None
    # Rate limit 6/min per app: other, issues, push, push (4) + two more = 6, the 7th is refused.
    db.get(Deployment, dep_id).status = "building"
    db.commit()
    assert push("refs/heads/main", "e" * 40).status_code == 202  # a new deployment: nothing queued
    assert push("refs/heads/main", "f" * 40).status_code == 202  # coalesced into that one
    limited = push("refs/heads/main", "g" * 40)
    assert (limited.status_code, limited.json()["error"]["code"]) == (429, "rate_limited")


def test_deploy_cancel_rollback_and_delete(client, env, db):
    app = create(client, env)
    url = f"{env['base']}/{app['id']}"
    assert client.post(f"{url}/deploy", headers=env["viewer"]).status_code == 403
    resp = client.post(f"{url}/deploy", json={"branch": "release"}, headers=env["dev"])
    assert resp.status_code == 202, resp.text
    dep = resp.json()
    assert dep["status"] == "queued" and dep["branch"] == "release" and dep["trigger"] == "manual" and "log" not in dep
    listed = client.get(f"{url}/deployments", headers=env["viewer"]).json()
    assert [d["id"] for d in listed["deployments"]] == [dep["id"]] and listed["has_more"] is False
    with_log = client.get(f"{url}/deployments/{dep['id']}?log=1", headers=env["viewer"]).json()
    assert (
        with_log["log"] == ""
        and "log" not in client.get(f"{url}/deployments/{dep['id']}", headers=env["viewer"]).json()
    )
    cancelled = client.post(f"{url}/deployments/{dep['id']}/cancel", headers=env["dev"]).json()
    assert cancelled["status"] == "cancelled" and db.get(Job, dep["job_id"]).status == "cancelled"
    assert client.post(f"{url}/deployments/{dep['id']}/cancel", headers=env["dev"]).status_code == 409
    rb = client.post(f"{url}/deployments/{dep['id']}/rollback", headers=env["dev"])
    assert (rb.status_code, rb.json()["error"]["code"]) == (409, "not_rollbackable")
    old = Deployment(
        app_id=app["id"], status="superseded", trigger="manual", branch="main", log="", image_tag="deployer-app/x:y"
    )
    db.add(old)
    db.commit()
    rb = client.post(f"{url}/deployments/{old.id}/rollback", headers=env["dev"])
    assert rb.status_code == 202 and rb.json()["rollback_of"] == old.id and rb.json()["image_tag"] == "deployer-app/x:y"
    page = client.get(f"{url}/deployments?limit=1", headers=env["viewer"]).json()
    assert len(page["deployments"]) == 1 and page["has_more"] is True
    older = client.get(f"{url}/deployments?limit=5&before={page['deployments'][0]['id']}", headers=env["viewer"]).json()
    assert (
        page["deployments"][0]["id"] not in [d["id"] for d in older["deployments"]] and len(older["deployments"]) == 2
    )
    assert client.get(f"{url}/logs", headers=env["viewer"]).json() == {"lines": [], "container": None}

    assert client.delete(url, headers=env["dev"]).status_code == 403
    resp = client.delete(url, headers=env["admin"])
    assert resp.status_code == 200, resp.text
    job = db.get(Job, resp.json()["job_id"])
    assert job.type == "app.remove" and job.params == {"app_id": app["id"], "slug": "my-shop"}
    assert db.get(deployments.App, app["id"]) is None and client.get(url, headers=env["dev"]).status_code == 404
    assert db.get(Deployment, dep["id"]) is None


def test_app_hostnames(client, env, db, owner_headers, fake_cf):  # noqa: F811
    app = create(client, env)
    url = f"{env['base']}/{app['id']}"
    missing = client.post(f"{url}/domains", json={"hostname": "shop.example.com"}, headers=env["admin"])
    assert (missing.status_code, missing.json()["error"]["code"]) == (409, "not_linked")
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    assert client.post(f"{url}/domains", json={"hostname": "shop.example.com"}, headers=env["dev"]).status_code == 403
    nozone = client.post(f"{url}/domains", json={"hostname": "shop.other.org"}, headers=env["admin"])
    assert (nozone.status_code, nozone.json()["error"]["code"]) == (404, "zone_not_found")
    resp = client.post(f"{url}/domains", json={"hostname": "Shop.Example.com"}, headers=env["admin"])
    assert resp.status_code == 200, resp.text
    domain = resp.json()
    assert domain["target_type"] == "app" and domain["app_id"] == app["id"] and domain["status"] == "active"
    assert fake_cf.records[db.get(Domain, domain["id"]).dns_record_id]["content"] == f"{tunnel_id}.cfargotunnel.com"
    assert [r.get("hostname") for r in fake_cf.tunnel_configs[tunnel_id]["ingress"]] == ["shop.example.com", None]
    out = client.get(url, headers=env["viewer"]).json()
    assert out["urls"] == ["https://shop.example.com"] and out["domains"][0]["id"] == domain["id"]
    assert db.scalar(select(Job).where(Job.type == "app.route")) is None  # nothing live yet: no reroute job

    db.get(deployments.App, app["id"]).live_deployment_id = "fake"
    db.commit()
    assert client.delete(f"{url}/domains/{domain['id']}", headers=env["admin"]).json() == {"ok": True}
    assert db.scalar(select(Job).where(Job.type == "app.route")).params == {"app_id": app["id"]}
    assert (
        fake_cf.records == {}
        and client.delete(f"{url}/domains/{domain['id']}", headers=env["admin"]).status_code == 404
    )

    client.post(f"{url}/domains", json={"hostname": "shop.example.com"}, headers=env["admin"])
    assert client.delete(url, headers=env["admin"]).status_code == 200
    assert fake_cf.records == {} and db.scalar(select(Domain)) is None
    assert [r.get("hostname") for r in fake_cf.tunnel_configs[tunnel_id]["ingress"]] == [None]


def test_export_import_roundtrip(client, env, db, make_user, auth_headers):
    token = new_token()
    project = env["project"]
    app = make_app(db, project, "Shop", env={"A": "1"}, token=token, start_command="node server.js")
    db.add(
        Domain(
            hostname="shop.example.com",
            zone_id="z",
            target_type="app",
            app_id=app.id,
            project_id=project.id,
            status="active",
        )
    )
    db.commit()
    secret = deployments.webhook_secret(app)
    path, _ = transfer.build_export_file(db, scope="projects", projects=[project], passphrase="correct horse battery")
    try:
        payload = transfer.read_export_file(path, "correct horse battery", "projects")
    finally:
        os.unlink(path)
    [row] = payload["apps"]
    assert row["env"] == {"A": "1"} and row["repo_token"] == token and row["webhook_secret"] == secret
    assert "port" not in row and "env_encrypted" not in row and payload["domains"][0]["app_id"] == app.id

    importer = make_user()
    created, summary = transfer.import_projects(db, payload, importer)
    new = db.scalar(select(deployments.App).where(deployments.App.project_id == created[0].id))
    assert new.id != app.id and new.port == 8101 and new.live_deployment_id is None
    assert deployments.env_of(new) == {"A": "1"} and deployments.repo_token(new) == token
    assert deployments.webhook_secret(new) == secret and new.start_command == "node server.js"
    assert db.scalar(select(Domain).where(Domain.app_id == new.id)) is None  # hostnames stay with the source instance

    # Instance scope keeps ids and app hostnames.
    path, _ = transfer.build_export_file(db, scope="instance", projects=[project], passphrase="correct horse battery")
    try:
        payload = transfer.read_export_file(path, "correct horse battery", "instance")
    finally:
        os.unlink(path)
    for model in (Domain, Deployment, deployments.App):
        db.query(model).delete()
    db.query(Job).delete()
    for model in (ApiKey, ra.Domain):
        db.query(model).delete()
    from app.models import InstanceSetting, Project, ProjectMember, User

    for model in (ProjectMember, Project, InstanceSetting):
        db.query(model).delete()
    db.query(User).delete()
    db.commit()
    transfer.import_instance(db, payload)
    restored = db.get(deployments.App, app.id)
    assert restored is not None and deployments.repo_token(restored) == token and restored.port == 8100
    assert db.scalar(select(Domain).where(Domain.app_id == app.id)).hostname == "shop.example.com"
