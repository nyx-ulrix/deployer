"""Cloud hosting phase C1 (docs/CLOUD.md): connections, the four cloud targets' deploy / rollback /
teardown sequences, custom domains through a fake Cloudflare, MCP tools and the migration. AWS and
Google are faked (`cloud_aws.set_factory`, `cloud_gcp.set_factory` / `set_transport`); nothing here
reaches a real cloud. Credentials are generated at runtime (no key-shaped literals in the source)."""

import json
import random
import secrets
import sqlite3
import string
import sys
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from alembic import command
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.crypto import decrypt_json, encrypt_json
from app.errors import CloudError
from app.models import App, AuditLog, CloudConnection, Deployment, Domain, Job
from app.services import cloud_aws, cloud_deploy, cloud_gcp, deployments, jobs
from app.services.app_runner import DockerCli
from tests.apps_support import make_app
from tests.test_deployments import docker  # noqa: F401 - fixture
from tests.test_remote_access import fake_cf, link, state_dir  # noqa: F401 - fixtures

CLOUD = "/v1/instance/cloud"


def aws_key_id() -> str:
    return "AKIA" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))


def aws_secret() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=40))


class FakeCloud:
    """Records every call; `returns[name]` is the value (or a function of the arguments); `fail[name]`
    makes that call raise CloudError."""

    def __init__(self, **returns):
        self.calls: list[tuple] = []
        self.returns = returns
        self.fail: dict[str, str] = {}
        self.region = "us-central1"

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, *args))
            if name in self.fail:
                raise CloudError(self.fail[name])
            value = self.returns.get(name)
            return value(*args) if callable(value) else value

        return call

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def args(self, name: str) -> list[tuple]:
        return [c[1:] for c in self.calls if c[0] == name]


@pytest.fixture
def aws(monkeypatch):
    fake = FakeCloud(
        identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/deployer"},
        create_oac="oac1",
        create_index_function="arn:aws:cloudfront::123456789012:function/x",
        create_distribution={"id": "E123", "domain": "d111.cloudfront.net", "arn": "arn:aws:cloudfront::1:dist/E123"},
        ensure_repository=lambda name: f"123456789012.dkr.ecr.eu-west-1.amazonaws.com/{name}",
        registry_login=("123456789012.dkr.ecr.eu-west-1.amazonaws.com", "AWS", "ecr-" + secrets.token_hex(16)),
        ensure_access_role="arn:aws:iam::123456789012:role/deployer-apprunner-ecr-access",
        create_service={"arn": "arn:svc", "url": "https://abc.eu-west-1.awsapprunner.com", "operation_id": "op1"},
        update_service="op2",
        operation="SUCCEEDED",
        request_certificate="arn:cert",
        certificate={"status": "PENDING_VALIDATION", "records": []},
        associate_domain="abc.eu-west-1.awsapprunner.com",
    )
    cloud_aws.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_aws.set_factory(None)


@pytest.fixture
def gcp(monkeypatch):
    fake = FakeCloud(
        create_version=lambda site, config: f"sites/{site}/versions/v{len(fake.args('create_version'))}",
        populate_files=lambda version, files: (
            "https://upload-firebasehosting.googleapis.com/upload/x",
            [h for h in files.values()][:1],
        ),
        create_channel="https://site--d-1.web.app",
        ensure_repository="us-central1-docker.pkg.dev/demo-proj-123/deployer",
        docker_login=("us-central1-docker.pkg.dev", "oauth2accesstoken", "ya29." + secrets.token_hex(16)),
        create_service="projects/demo-proj-123/locations/us-central1/operations/op1",
        update_service="projects/demo-proj-123/locations/us-central1/operations/op2",
        operation={"done": True, "error": None},
        domain={"status": "pending", "records": [{"type": "A", "name": "www.example.com", "value": "199.36.158.100"}]},
    )
    cloud_gcp.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_gcp.set_factory(None)


@pytest.fixture
def team(make_user, make_project, auth_headers):
    admin, dev = make_user(), make_user()
    owner = make_user(owner=True)
    project = make_project(owner, members={admin: "admin", dev: "developer"})
    return {
        "project": project,
        "base": f"/v1/projects/{project.id}/apps",
        "owner": auth_headers(owner),
        "admin": auth_headers(admin),
        "dev": auth_headers(dev),
    }


def connection(db, provider="aws", project_id=None) -> CloudConnection:
    config = (
        {"access_key_id": aws_key_id(), "secret_access_key": aws_secret(), "region": "eu-west-1", "account_id": "1"}
        if provider == "aws"
        else {"service_account": {"client_email": "x@y", "private_key": "k"}, "project_id": "demo-proj-123"}
    )
    conn = CloudConnection(
        provider=provider, name=provider, project_id=project_id, config_encrypted=encrypt_json(config)
    )
    db.add(conn)
    db.commit()
    return conn


def deploy(db, app, **kw) -> Deployment:
    dep, _ = deployments.start_deployment(db, app, trigger="manual", user_id=None, **kw)
    db.commit()
    jobs.run_queued()
    db.expire_all()
    return db.get(Deployment, dep.id)


def rollback(db, app, old) -> Deployment:
    dep, _ = deployments.rollback(db, db.get(App, app.id), old, user_id=None)
    db.commit()
    jobs.run_queued()
    db.expire_all()
    return db.get(Deployment, dep.id)


# --- connections ---------------------------------------------------------------------------------


def test_aws_connection_is_validated_and_secrets_never_returned(client, db, team, aws):
    secret = aws_secret()
    body = {
        "provider": "aws",
        "name": "My AWS",
        "aws": {"access_key_id": aws_key_id(), "secret_access_key": secret, "region": "eu-west-1"},
    }
    assert client.post(CLOUD, json=body, headers=team["admin"]).status_code == 403  # instance owner only
    resp = client.post(CLOUD, json=body, headers=team["owner"])
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["account"]["account_id"] == "123456789012" and out["status"] == "ok" and secret not in resp.text
    assert aws.names() == ["identity"]
    listed = client.get(CLOUD, headers=team["owner"])
    assert secret not in listed.text and body["aws"]["access_key_id"] not in listed.text
    assert "aws_static" in listed.json()["targets"]
    stored = db.get(CloudConnection, out["id"])
    assert (
        secret not in stored.config_encrypted and decrypt_json(stored.config_encrypted)["secret_access_key"] == secret
    )
    audit = db.query(AuditLog).filter(AuditLog.action == "cloud.connection_create").one()
    assert secret not in json.dumps(audit.details)
    # Project admins see a read-only list.
    project_list = client.get(f"/v1/projects/{team['project'].id}/cloud/connections", headers=team["admin"])
    assert project_list.status_code == 200 and [c["id"] for c in project_list.json()] == [out["id"]]
    assert client.get(f"/v1/projects/{team['project'].id}/cloud/connections", headers=team["dev"]).status_code == 403

    aws.fail["identity"] = "AWS InvalidClientTokenId: The security token included in the request is invalid."
    bad = client.post(CLOUD, json=body, headers=team["owner"])
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "cloud_credentials_invalid"
    wrong = {**body, "aws": {**body["aws"], "access_key_id": "not-a-key"}}
    assert client.post(CLOUD, json=wrong, headers=team["owner"]).json()["error"]["details"]["field"] == "access_key_id"

    policy = client.get(f"{CLOUD}/requirements", headers=team["owner"]).json()
    actions = {
        a
        for s in policy["aws"]["policy"]["Statement"]
        for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
    }
    assert {
        "sts:GetCallerIdentity",
        "cloudfront:CreateDistribution",
        "apprunner:UpdateService",
        "iam:PassRole",
    } <= actions
    assert {r["role"] for r in policy["firebase"]["roles"]} >= {"roles/firebasehosting.admin", "roles/run.admin"}


def test_firebase_connection_token_exchange_ignores_key_token_uri(client, db, team):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    sa = {
        "type": "service_account",
        "project_id": "demo-proj-123",
        "private_key_id": "k1",
        "private_key": pem,
        "client_email": "deployer@demo-proj-123.iam.gserviceaccount.com",
        "token_uri": "https://attacker.example/token",
    }
    access_token = "ya29." + secrets.token_hex(12)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == cloud_gcp.TOKEN_URL:
            form = parse_qs(request.content.decode())
            claims = jwt.decode(
                form["assertion"][0], key.public_key(), algorithms=["RS256"], audience=cloud_gcp.TOKEN_URL
            )
            assert claims["iss"] == sa["client_email"] and "cloud-platform" in claims["scope"]
            return httpx.Response(200, json={"access_token": access_token, "expires_in": 3600})
        if request.url.path == "/v1beta1/projects/demo-proj-123":
            assert request.headers["Authorization"] == f"Bearer {access_token}"
            return httpx.Response(200, json={"projectId": "demo-proj-123", "displayName": "Demo"})
        return httpx.Response(404, json={"error": {"message": "nope"}})

    cloud_gcp.set_transport(httpx.MockTransport(handle))
    try:
        resp = client.post(
            CLOUD,
            json={"provider": "firebase", "name": "Firebase", "firebase": {"service_account_json": json.dumps(sa)}},
            headers=team["owner"],
        )
    finally:
        cloud_gcp.set_transport(None)
    assert resp.status_code == 201, resp.text
    assert resp.json()["account"] == {
        "project_id": "demo-proj-123",
        "region": "us-central1",
        "client_email": sa["client_email"],
    }
    assert "PRIVATE KEY" not in resp.text and access_token not in resp.text
    assert all(r.url.host != "attacker.example" for r in seen)
    stored = decrypt_json(db.get(CloudConnection, resp.json()["id"]).config_encrypted)
    assert "token_uri" not in stored["service_account"]


# --- targets on apps -----------------------------------------------------------------------------


def test_target_rules(client, db, team, aws):
    conn = connection(db)
    body = {"name": "Site", "repo_url": "https://github.com/acme/site", "preset": "static", "target": "aws_static"}
    body["cloud_connection_id"] = conn.id
    assert client.post(team["base"], json=body, headers=team["dev"]).status_code == 403
    assert client.post(team["base"], json={**body, "preset": "node"}, headers=team["admin"]).status_code == 422
    assert client.post(team["base"], json={**body, "database_access": True}, headers=team["admin"]).status_code == 422
    gcp_conn = connection(db, "firebase")
    wrong = client.post(team["base"], json={**body, "cloud_connection_id": gcp_conn.id}, headers=team["admin"])
    assert wrong.status_code == 422 and "aws connection" in wrong.json()["error"]["message"]
    other = connection(db, project_id=None)
    other.project_id = team["project"].id
    db.commit()
    resp = client.post(team["base"], json=body, headers=team["admin"])
    assert resp.status_code == 201, resp.text
    app = resp.json()
    assert app["target"] == "aws_static" and app["local_url"] is None and app["cloud"]["url"] is None
    # Developers may still edit a cloud app, not move it.
    patch = client.patch(f"{team['base']}/{app['id']}", json={"build_command": "npm run build"}, headers=team["dev"])
    assert patch.status_code == 200, patch.text
    moved = client.patch(f"{team['base']}/{app['id']}", json={"target": "local"}, headers=team["dev"])
    assert moved.status_code == 403
    targets = client.get(f"/v1/projects/{team['project'].id}/cloud/targets", headers=team["dev"]).json()
    assert {t["id"]: t["available"] for t in targets} == {
        "local": True,
        "aws_static": True,
        "aws_app": True,
        "firebase_hosting": True,
        "firebase_app": True,
    }
    assert client.delete(f"{CLOUD}/{conn.id}", headers=team["owner"]).json()["error"]["code"] == "connection_in_use"


def test_aws_static_deploy_creates_once_updates_after_and_rolls_back(db, docker, aws, team):  # noqa: F811
    conn = connection(db)
    app = make_app(db, team["project"], "Site", preset="static", target="aws_static", cloud_connection_id=conn.id)
    first = deploy(db, app)
    assert first.status == "live", first.error
    assert first.target_url == "https://d111.cloudfront.net" and first.image_tag == f"d/{first.id}"
    assert docker.steps()[:3] == ["clone", "build", "export"] and "run" not in docker.steps()
    assert [n for n in aws.names() if n != "upload_file"] == [
        "create_bucket",
        "create_oac",
        "create_index_function",
        "create_distribution",
        "allow_distribution",
    ]
    uploads = {a[1]: (a[3], a[4]) for a in aws.args("upload_file")}
    prefix = f"d/{first.id}"
    assert uploads == {
        f"{prefix}/assets/app-1a2b3c4d.js": ("text/javascript", "public, max-age=31536000, immutable"),
        f"{prefix}/index.html": ("text/html", "no-cache"),
        f"{prefix}/logo.png": ("image/png", "public, max-age=3600"),
    }  # the symlink to a worker file was skipped
    assert aws.args("create_distribution")[0][1] == f"/{prefix}"
    app = db.get(App, app.id)
    assert app.cloud_state["distribution_id"] == "E123" and app.cloud_state["bucket"] == cloud_deploy.resource_name(app)
    assert deployments.app_out(db, app)["urls"] == ["https://d111.cloudfront.net"]

    aws.calls.clear()
    second = deploy(db, app)
    assert second.status == "live"
    assert [n for n in aws.names() if n != "upload_file"] == ["set_origin_path", "invalidate"]
    assert aws.args("set_origin_path")[0] == ("E123", f"/d/{second.id}")

    aws.calls.clear()
    docker.calls.clear()
    back = rollback(db, app, db.get(Deployment, first.id))
    assert back.status == "live" and back.image_tag == prefix
    assert docker.steps() == [] and aws.names() == ["set_origin_path", "invalidate"]
    assert aws.args("set_origin_path")[0] == ("E123", f"/{prefix}")
    assert db.get(Deployment, second.id).status == "superseded"


def test_aws_app_deploy_env_rollout_and_rollback(db, docker, aws, team):  # noqa: F811
    conn = connection(db)
    app = make_app(
        db,
        team["project"],
        "Api",
        env={"NODE_ENV": "production", "PORT": "1"},
        target="aws_app",
        cloud_connection_id=conn.id,
        database_access=True,  # even if set behind the API's back: nothing from this PC is injected
    )
    first = deploy(db, app)
    assert first.status == "live", first.error
    image = f"123456789012.dkr.ecr.eu-west-1.amazonaws.com/{cloud_deploy.resource_name(app)}:{first.id}"
    assert first.image_tag == image and first.target_url == "https://abc.eu-west-1.awsapprunner.com"
    assert aws.names() == [
        "ensure_repository",
        "registry_login",
        "ensure_access_role",
        "create_service",
        "operation",
    ]
    (name, img, port, env, role) = aws.args("create_service")[0]
    assert (img, port, env) == (image, 3000, {"NODE_ENV": "production"})
    assert not any(k.startswith("DEPLOYER_") for k in env)
    push = next(c for c in docker.calls if c[0] == "push")
    assert push[2] == image and push[4] == "AWS"
    password = docker.passwords[0]
    assert password not in first.log and "Not sent (set by App Runner itself): PORT" in first.log

    aws.calls.clear()
    second = deploy(db, app)
    assert second.status == "live"
    assert aws.names() == ["registry_login", "update_service", "operation"]

    # A failed rollout keeps the previous version live.
    aws.returns["operation"] = "ROLLBACK_SUCCEEDED"
    third = deploy(db, app)
    assert third.status == "failed" and "previous version keeps serving" in third.error
    assert db.get(App, app.id).live_deployment_id == second.id

    aws.returns["operation"] = "SUCCEEDED"
    aws.calls.clear()
    docker.calls.clear()
    back = rollback(db, app, db.get(Deployment, first.id))
    assert back.status == "live" and docker.steps() == []
    assert aws.names() == ["update_service", "operation"] and aws.args("update_service")[0][1] == image


def test_firebase_hosting_deploy(db, docker, gcp, team):  # noqa: F811
    conn = connection(db, "firebase")
    app = make_app(db, team["project"], "Docs", preset="static", target="firebase_hosting", cloud_connection_id=conn.id)
    first = deploy(db, app)
    assert first.status == "live", first.error
    site = cloud_deploy.site_id(app)
    assert first.target_url == f"https://{site}.web.app" and first.image_tag == f"sites/{site}/versions/v1"
    assert gcp.names() == [
        "create_site",
        "create_version",
        "populate_files",
        "upload_file",  # only the hashes Hosting asked for
        "finalize_version",
        "create_channel",
        "release",
        "release",
    ]
    files = gcp.args("populate_files")[0][1]
    assert set(files) == {"/index.html", "/assets/app-1a2b3c4d.js", "/logo.png"}
    assert gcp.args("release") == [(site, first.image_tag, f"d-{first.id[:8]}"), (site, first.image_tag)]
    gcp.calls.clear()
    assert deploy(db, app).status == "live" and "create_site" not in gcp.names()
    gcp.calls.clear()
    back = rollback(db, app, db.get(Deployment, first.id))
    assert back.status == "live" and gcp.names() == ["release"] and gcp.args("release")[0] == (site, first.image_tag)


def test_firebase_app_deploy(db, docker, gcp, team):  # noqa: F811
    conn = connection(db, "firebase")
    app = make_app(db, team["project"], "Api", env={"A": "1"}, target="firebase_app", cloud_connection_id=conn.id)
    first = deploy(db, app)
    assert first.status == "live", first.error
    assert gcp.names() == [
        "ensure_repository",
        "docker_login",
        "create_service",
        "operation",
        "make_public",
        "create_site",
        "create_version",
        "finalize_version",
        "release",
    ]
    service = cloud_deploy.resource_name(app)
    assert gcp.args("create_service")[0][2:] == (3000, {"A": "1"})
    rewrite = gcp.args("create_version")[0][1]["rewrites"][0]
    assert rewrite == {"glob": "**", "run": {"serviceId": service, "region": "us-central1"}}
    assert first.target_url == f"https://{cloud_deploy.site_id(app)}.web.app"
    gcp.calls.clear()
    assert deploy(db, app).status == "live"
    assert gcp.names() == ["docker_login", "update_service", "operation"]


def test_delete_app_tears_down_and_reports_failures(client, db, docker, aws, team):  # noqa: F811
    conn = connection(db)
    app = make_app(db, team["project"], "Api", target="aws_app", cloud_connection_id=conn.id)
    deploy(db, app)
    shown = client.get(f"{team['base']}/{app.id}", headers=team["dev"]).json()["cloud"]["resources"]
    assert any("App Runner service" in r for r in shown) and any("ECR repository" in r for r in shown)
    aws.calls.clear()
    aws.fail["delete_service"] = "AWS AccessDenied: not allowed"
    resp = client.delete(f"{team['base']}/{app.id}", headers=team["admin"])
    assert resp.status_code == 200 and resp.json()["teardown_job_id"]
    jobs.run_queued()
    job = db.get(Job, resp.json()["teardown_job_id"])
    assert job.status == "failed" and "App Runner service" in job.error and "AccessDenied" in job.error
    assert aws.names() == ["delete_service", "delete_repository"]  # the other steps still ran


def test_switch_target_tears_down_old_resources(client, db, docker, aws, team):  # noqa: F811
    conn = connection(db)
    app = make_app(db, team["project"], "Site", preset="static", target="aws_static", cloud_connection_id=conn.id)
    first = deploy(db, app)
    aws.calls.clear()
    resp = client.patch(f"{team['base']}/{app.id}", json={"target": "local"}, headers=team["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["target"] == "local" and resp.json()["cloud_connection_id"] is None
    jobs.run_queued()
    assert aws.names() == ["delete_distribution", "delete_function", "delete_oac", "delete_bucket"]
    db.expire_all()
    app = db.get(App, app.id)
    assert app.cloud_state is None and app.live_deployment_id is None
    assert db.get(Deployment, first.id).image_tag is None  # no rollback across targets


# --- custom domains ------------------------------------------------------------------------------


def test_cloud_domain_with_cloudflare(client, db, docker, aws, team, fake_cf, owner_headers):  # noqa: F811
    link(client, owner_headers)
    conn = connection(db)
    app = make_app(db, team["project"], "Site", preset="static", target="aws_static", cloud_connection_id=conn.id)
    base = f"{team['base']}/{app.id}/domains"
    assert client.post(base, json={"hostname": "www.example.com"}, headers=team["admin"]).status_code == 409
    deploy(db, app)
    validation = {"type": "CNAME", "name": "_abc.www.example.com", "value": "_def.acm-validations.aws"}
    aws.returns["certificate"] = {"status": "ISSUED", "records": [validation]}
    resp = client.post(base, json={"hostname": "www.example.com"}, headers=team["admin"])
    assert resp.status_code == 200, resp.text
    jobs.run_queued()
    db.expire_all()
    domain = db.get(Domain, resp.json()["id"])
    assert domain.status == "active" and domain.provider == "aws" and domain.target_type == "cloud_app"
    created = {(r["type"], r["name"], r["content"], r["proxied"]) for r in fake_cf.records.values()}
    assert ("CNAME", "www.example.com", "d111.cloudfront.net", False) in created
    assert ("CNAME", "_abc.www.example.com", "_def.acm-validations.aws", False) in created
    assert aws.args("set_aliases")[-1] == ("E123", ["www.example.com"], "arn:cert")
    out = client.get(f"{team['base']}/{app.id}", headers=team["dev"]).json()
    assert "https://www.example.com" in out["urls"] and out["domains"][0]["dns_records"]
    assert not [d for d in fake_cf.calls("PUT", r"/configurations")[1:]]  # the tunnel ingress is untouched

    removed = client.delete(f"{base}/{domain.id}", headers=team["admin"])
    assert removed.status_code == 200 and fake_cf.records == {}
    assert aws.args("set_aliases")[-1] == ("E123", [], None) and "delete_certificate" in aws.names()


def test_cloud_domain_without_cloudflare_lists_records(client, db, docker, gcp, team, monkeypatch):  # noqa: F811
    monkeypatch.setattr(cloud_deploy, "DOMAIN_TIMEOUT_S", 0)
    conn = connection(db, "firebase")
    app = make_app(db, team["project"], "Docs", preset="static", target="firebase_hosting", cloud_connection_id=conn.id)
    deploy(db, app)
    resp = client.post(f"{team['base']}/{app.id}/domains", json={"hostname": "www.example.com"}, headers=team["admin"])
    assert resp.status_code == 200, resp.text
    jobs.run_queued()
    db.expire_all()
    domain = db.get(Domain, resp.json()["id"])
    assert domain.status == "pending" and "check the DNS records" in domain.status_message
    assert domain.dns_records == [{"type": "A", "name": "www.example.com", "value": "199.36.158.100"}]
    check = client.post(f"{team['base']}/{app.id}/domains/{domain.id}/check", headers=team["admin"])
    assert check.status_code == 202


# --- docker login, MCP, migration ----------------------------------------------------------------


def test_registry_password_goes_through_stdin_not_argv(tmp_path, monkeypatch):
    cli = DockerCli()
    calls = []
    monkeypatch.setattr(cli, "_run", lambda args, **kw: calls.append((args, kw)) or "")
    password = "pw-" + secrets.token_hex(16)
    cli.push(
        "deployer-app/a:1",
        "reg.example/x:1",
        registry="reg.example",
        username="AWS",
        password=password,
        config_dir=str(tmp_path),
    )
    assert calls[0][0][:3] == ["docker", "login", "--username"] and "--password-stdin" in calls[0][0]
    assert calls[0][1]["stdin_text"] == password
    assert all(password not in " ".join(args) for args, _ in calls)
    assert all(kw["env"]["DOCKER_CONFIG"] == str(tmp_path) for _, kw in calls)
    # The real plumbing: stdin reaches the process.
    out = DockerCli()._run([sys.executable, "-c", "import sys; print(sys.stdin.read()[::-1])"], stdin_text="abc")
    assert out.strip() == "cba"


def test_mcp_cloud_tools(client, db, docker, aws, team):  # noqa: F811
    resp = client.post(
        f"/v1/projects/{team['project'].id}/api-keys", json={"name": "k", "role": "service"}, headers=team["admin"]
    )
    headers = {"Authorization": f"Bearer {resp.json()['secret']}"}
    conn = connection(db)
    app = make_app(db, team["project"], "Api", target="aws_app", cloud_connection_id=conn.id)

    def call(tool, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        out = client.post(f"/v1/projects/{team['project'].id}/mcp", json=body, headers=headers).json()["result"]
        assert not out["isError"], out
        return json.loads(out["content"][0]["text"])

    conns = call("list_cloud_connections")
    assert [c["id"] for c in conns] == [conn.id]
    assert "secret_access_key" not in json.dumps(conns) and "config" not in conns[0]
    targets = call("list_cloud_targets")
    assert {t["id"] for t in targets["targets"]} >= {"aws_static", "aws_app", "firebase_hosting", "firebase_app"}
    started = call("deploy_app", app_id=app.id)
    assert started["target"] == "aws_app"
    jobs.run_queued()
    status = call("deployment_status", app_id=app.id, deployment_id=started["id"])
    assert status["status"] == "live" and status["target_url"] == "https://abc.eu-west-1.awsapprunner.com"
    assert call("get_app", app_id=app.id)["cloud"]["url"] == "https://abc.eu-west-1.awsapprunner.com"


def test_migration_0011(migration_db):
    cfg, db_file = migration_db
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db_file)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    apps = {row[1] for row in conn.execute("PRAGMA table_info(apps)")}
    assert "cloud_connections" in tables and {"target", "cloud_connection_id", "cloud_state"} <= apps
    assert "target_url" in {row[1] for row in conn.execute("PRAGMA table_info(deployments)")}
    assert "dns_records" in {row[1] for row in conn.execute("PRAGMA table_info(domains)")}
    conn.close()
    command.downgrade(cfg, "0010")
    conn = sqlite3.connect(db_file)
    assert "target" not in {row[1] for row in conn.execute("PRAGMA table_info(apps)")}
    conn.close()
    command.upgrade(cfg, "head")
