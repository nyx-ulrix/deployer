"""GitHub Actions builds (docs/CLOUD.md "C3"): switching a cloud app to GitHub Actions (checks, billing
confirmation, the setup job's AWS role / Google workload identity and the committed workflow), pushes left to
the workflow, "Deploy now" dispatching it, the signed run reports becoming deployments (and rollback targets),
the runs list, rewriting the workflow when build settings change, and switching back (teardown). AWS, Google
and GitHub are fakes; GitHub's OIDC tokens are signed with a key made here."""

import base64
import hashlib
import hmac
import json
import secrets
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.models import App, Deployment, Job
from app.services import cloud, cloud_aws, cloud_deploy, cloud_gcp, deployments, github, github_actions, jobs
from tests.apps_support import make_app
from tests.test_cloud import FakeCloud, connection
from tests.test_github_integration import FakeGitHub

REPO = "Acme/Shop"
SHA = "b" * 40
ECR = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/deployer-shop-x"
AWS_APP_STATE = {
    "ecr_repository": "deployer-shop-x",
    "ecr_uri": ECR,
    "service_arn": "arn:aws:apprunner:eu-west-1:1:service/deployer-shop-x/abc",
    "service_name": "deployer-shop-x",
    "service_url": "https://abc.eu-west-1.awsapprunner.com",
    "access_role_arn": "arn:aws:iam::1:role/deployer-apprunner-ecr-access",
}
RUN_STATE = {
    "registry": "us-central1-docker.pkg.dev/demo-proj-123/deployer",
    "ar_package": "shop-x",
    "run_service": "deployer-shop-x",
    "run_region": "us-central1",
    "site": "shop-x",
    "released": True,
}


@pytest.fixture
def people(make_user, make_project, auth_headers):
    admin, dev = make_user(), make_user()
    project = make_project(make_user(), members={admin: "admin", dev: "developer"})
    return {
        "project": project,
        "base": f"/v1/projects/{project.id}/apps",
        "admin_user": admin,
        "admin": auth_headers(admin),
        "dev": auth_headers(dev),
    }


@pytest.fixture
def aws(monkeypatch):
    fake = FakeCloud(
        ensure_github_oidc=lambda account: f"arn:aws:iam::{account}:oidc-provider/{cloud_aws.GITHUB_OIDC_HOST}",
        ensure_boundary={"arn": "arn:aws:iam::1:policy/deployer-boundary", "current": True},
        ensure_github_role=lambda name, trust, policy, boundary: f"arn:aws:iam::1:role/{name}",
        update_service="op9",
        operation="SUCCEEDED",
        ensure_access_role=AWS_APP_STATE["access_role_arn"],
    )
    cloud_aws.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_aws.set_factory(None)


@pytest.fixture
def gcp():
    fake = FakeCloud(project_info={"projectNumber": "555"})
    fake.project = "demo-proj-123"
    cloud_gcp.set_factory(lambda config: fake)
    yield fake
    cloud_gcp.set_factory(None)


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGitHub()
    fake.routes[("GET", "/repos/acme/shop")] = (200, {"full_name": REPO, "id": 99, "permissions": {"push": True}})
    monkeypatch.setattr(github, "_api", fake)
    return fake


@pytest.fixture
def oidc():
    """GitHub's OIDC signing key, played by a key made here."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    github_actions.set_key_resolver(lambda token: key.public_key())
    yield key
    github_actions.set_key_resolver(None)


def connect_github(db, user, scopes=github.CONNECT_SCOPE) -> None:
    github.save_connection(db, user.id, login="octo", github_user_id="42", token="gh-test-token", scopes=scopes)
    db.commit()


def cloud_app(db, project, target="aws_app", state=None, provider="aws", **fields) -> App:
    conn = connection(db, provider)
    return make_app(
        db,
        project,
        target=target,
        cloud_connection_id=conn.id,
        cloud_state=dict(AWS_APP_STATE if state is None else state),
        **fields,
    )


def contents_path(app: App) -> str:
    return f"/repos/{REPO}/contents/{github_actions.workflow_path(app)}"


def committed(gh: FakeGitHub, app: App) -> str:
    puts = [c for c in gh.calls if c[0] == "PUT" and c[1] == contents_path(app)]
    return base64.b64decode(puts[-1][3]["content"]).decode()


def switch(client, people, app, location="github", headers=None, **extra):
    body = {"location": location, "confirm_billing": True, **extra}
    return client.put(f"{people['base']}/{app.id}/build", json=body, headers=headers or people["admin"])


def set_up(client, db, people, gh, app) -> dict:
    connect_github(db, people["admin_user"])
    gh.routes[("PUT", contents_path(app))] = (201, {"commit": {"sha": "c" * 40}})
    resp = switch(client, people, app)
    assert resp.status_code == 200, resp.text
    jobs.run_queued()
    db.expire_all()
    return deployments.app_out(db, db.get(App, app.id))["build"]


def report_token(key, app: App, **claims) -> str:
    now = int(time.time())
    body = {
        "iss": github_actions.ISSUER,
        "aud": github_actions.audience(app),
        "sub": f"repo:{REPO}:ref:refs/heads/main",
        "repository": REPO,
        "repository_id": "99",
        "ref": "refs/heads/main",
        "workflow_ref": f"{REPO}/{github_actions.workflow_path(app)}@refs/heads/main",
        "run_id": "123",
        "run_attempt": "1",
        "sha": SHA,
        "iat": now,
        "exp": now + 300,
        **claims,
    }
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return jwt.encode(body, pem, algorithm="RS256")


def report(client, app: App, token: str, **body):
    headers = {"X-GitHub-Event": github_actions.REPORT_EVENT, "Authorization": f"Bearer {token}"}
    return client.post(f"/v1/hooks/github/{app.id}", json=body, headers=headers)


# --- switching -----------------------------------------------------------------------------------


def test_switching_needs_admin_a_deployed_app_github_with_workflow_scope_and_billing(client, db, people, gh, aws):
    app = cloud_app(db, people["project"])
    assert switch(client, people, app, headers=people["dev"]).status_code == 403
    assert switch(client, people, app).json()["error"]["code"] == "github_not_connected"
    connect_github(db, people["admin_user"], scopes="repo admin:repo_hook read:user")  # connected before C3
    assert switch(client, people, app).json()["error"]["code"] == "github_scope_missing"
    connect_github(db, people["admin_user"])
    unconfirmed = switch(client, people, app, confirm_billing=False)
    assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "billing_not_confirmed"
    assert "2,000" in unconfirmed.json()["error"]["message"]
    fresh = cloud_app(db, people["project"], name="Fresh", state={})
    assert switch(client, people, fresh).json()["error"]["code"] == "not_deployed"
    local = make_app(db, people["project"], "Local")
    assert switch(client, people, local).status_code == 422
    assert db.query(Job).filter(Job.type == "app.github_actions").count() == 0


def test_aws_setup_role_trust_policy_and_workflow(client, db, people, gh, aws):
    app = cloud_app(db, people["project"])
    build = set_up(client, db, people, gh, app)
    assert build["location"] == "github" and build["status"] == "ready", build
    assert build["repo"] == REPO and build["runs_url"].endswith(github_actions.workflow_path(app).rsplit("/", 1)[1])
    # Deployer's address is localhost in tests: runs can't report back, and the build says so.
    assert "no public address" in build["message"] and build["reports"] is False

    assert aws.args("ensure_github_oidc") == [("1",)]
    (name, trust, policy, boundary) = aws.args("ensure_github_role")[0]
    assert boundary == "arn:aws:iam::1:policy/deployer-boundary"  # G3: the role is capped by it
    assert name == github_actions.role_name(app) and name.startswith("deployer-gha-") and len(name) <= 64
    condition = trust["Statement"][0]["Condition"]["StringEquals"]
    assert condition == {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": f"repo:{REPO}:ref:refs/heads/main",
    }
    resources = {
        r for s in policy["Statement"] for r in ([s["Resource"]] if isinstance(s["Resource"], str) else s["Resource"])
    }
    assert resources == {
        "*",  # ecr:GetAuthorizationToken only
        "arn:aws:ecr:eu-west-1:1:repository/deployer-shop-x",
        AWS_APP_STATE["service_arn"],
        AWS_APP_STATE["access_role_arn"],
    }
    star = [s for s in policy["Statement"] if s["Resource"] == "*"]
    assert [s["Action"] for s in star] == ["ecr:GetAuthorizationToken"]

    text = committed(gh, app)
    assert "id-token: write" in text and "contents: read" in text and 'branches: ["main"]' in text
    assert f'role-to-assume: "arn:aws:iam::1:role/{github_actions.role_name(app)}"' in text
    assert 'DEPLOYER_CALLBACK: ""' in text and "secrets." not in text
    recipe = text.split("echo '", 1)[1].split("'", 1)[0]
    assert base64.b64decode(recipe).decode() == deployments.generate_dockerfile(app)
    state = db.get(App, app.id).cloud_state
    assert state["service_arn"] == AWS_APP_STATE["service_arn"]  # the target's own state is untouched
    resources_listed = deployments.app_out(db, db.get(App, app.id))["cloud"]["resources"]
    assert any("deployer-gha-" in r for r in resources_listed) and any("Workflow file" in r for r in resources_listed)


def test_pushes_go_to_the_workflow_and_deploy_now_dispatches_it(client, db, people, gh, aws):
    app = cloud_app(db, people["project"])
    set_up(client, db, people, gh, app)
    payload = json.dumps({"ref": "refs/heads/main", "after": SHA}).encode()
    signature = "sha256=" + hmac.new(deployments.webhook_secret(app).encode(), payload, hashlib.sha256).hexdigest()
    pushed = client.post(
        f"/v1/hooks/github/{app.id}",
        content=payload,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )
    assert pushed.json() == {"ignored": True} and db.query(Deployment).count() == 0

    dispatches = f"/repos/{REPO}/actions/workflows/{github_actions.workflow_path(app).rsplit('/', 1)[1]}/dispatches"
    gh.routes[("POST", dispatches)] = (204, None)
    resp = client.post(f"{people['base']}/{app.id}/deploy", headers=people["dev"])
    assert resp.status_code == 202 and resp.json()["github_actions"] is True, resp.text
    assert [c[3] for c in gh.calls if c[1] == dispatches] == [{"ref": "main"}]
    other = client.post(f"{people['base']}/{app.id}/deploy", json={"branch": "dev"}, headers=people["dev"])
    assert other.status_code == 422

    runs = f"/repos/{REPO}/actions/workflows/{github_actions.workflow_path(app).rsplit('/', 1)[1]}/runs"
    run = {
        "id": 7,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "head_branch": "main",
        "head_sha": SHA,
        "head_commit": {"message": "Fix the header\n\nlong text"},
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:03:00Z",
        "html_url": f"https://github.com/{REPO}/actions/runs/7",
    }
    gh.routes[("GET", runs)] = (200, {"workflow_runs": [run]})
    listed = client.get(f"{people['base']}/{app.id}/github-runs", headers=people["dev"]).json()
    assert listed["runs"][0]["message"] == "Fix the header" and listed["runs"][0]["conclusion"] == "success"


def test_reports_become_deployments_and_rollback_targets(client, db, people, gh, aws, oidc, docker):
    app = cloud_app(db, people["project"])
    set_up(client, db, people, gh, app)
    token = report_token(oidc, app)

    assert report(client, app, "not-a-token", status="success").status_code == 401
    assert report(client, app, report_token(oidc, app, aud="deployer:other")).status_code == 401
    assert report(client, app, report_token(oidc, app, repository="Evil/Shop"), status="success").status_code == 401
    other_workflow = report_token(oidc, app, workflow_ref=f"{REPO}/.github/workflows/other.yml@refs/heads/main")
    assert report(client, app, other_workflow, status="success").status_code == 401
    assert report(client, app, report_token(oidc, app, ref="refs/heads/dev"), status="success").status_code == 401
    assert db.query(Deployment).count() == 0

    resp = report(client, app, token, status="success", artifact="docker.io/evil:latest", message="Fix\nmore")
    assert resp.status_code == 200 and resp.json()["status"] == "live", resp.text
    db.expire_all()
    dep = db.get(Deployment, resp.json()["deployment_id"])
    # The artifact comes from the run, never from the report.
    assert dep.trigger == "github" and dep.image_tag == f"{ECR}:gh-123-1" and dep.commit_sha == SHA
    assert dep.commit_message == "Fix" and f"https://github.com/{REPO}/actions/runs/123/attempts/1" in dep.log
    assert db.get(App, app.id).live_deployment_id == dep.id
    assert report(client, app, token, status="success").json() == {"ignored": True}  # delivered twice
    jobs.run_queued()
    prune = db.query(Job).filter(Job.type == "app.cloud_prune").one()
    assert prune.status == "succeeded"

    failed = report(client, app, report_token(oidc, app, run_id="124"), status="failure").json()
    db.expire_all()
    assert failed["status"] == "failed" and "runs/124" in db.get(Deployment, failed["deployment_id"]).error
    assert db.get(App, app.id).live_deployment_id == dep.id

    # Rolling back to a GitHub-built deployment republishes its image from this PC (with today's environment).
    back, _ = deployments.rollback(db, db.get(App, app.id), dep, user_id=None)
    db.commit()
    jobs.run_queued()
    db.expire_all()
    assert db.get(Deployment, back.id).status == "live"
    assert aws.args("update_service")[-1][1] == f"{ECR}:gh-123-1"


def test_firebase_hosting_report_only_accepts_its_own_sites_version(client, db, people, gh, gcp, oidc):
    state = {"site": "shop-x", "released": True}
    app = cloud_app(db, people["project"], target="firebase_hosting", state=state, provider="firebase", preset="static")
    set_up(client, db, people, gh, app)
    ok = report(client, app, report_token(oidc, app), status="success", artifact="sites/shop-x/versions/v1").json()
    evil = report(
        client, app, report_token(oidc, app, run_id="200"), status="success", artifact="sites/other/versions/v1"
    )
    db.expire_all()
    assert db.get(Deployment, ok["deployment_id"]).image_tag == "sites/shop-x/versions/v1"
    assert db.get(Deployment, evil.json()["deployment_id"]).image_tag is None
    text = committed(gh, app)
    assert "firebase-tools" in text and "google-github-actions/auth@v2" in text and "docker cp" in text


def test_google_setup_and_switching_back_removes_everything(client, db, people, gh, gcp):
    app = cloud_app(db, people["project"], target="firebase_app", state=RUN_STATE, provider="firebase")
    build = set_up(client, db, people, gh, app)
    assert build["status"] == "ready", build
    assert gcp.args("ensure_wif_pool") == [(github_actions.POOL,)]
    (pool, provider, condition) = gcp.args("ensure_wif_provider")[0]
    assert (
        provider == f"gh-{app.id[:8]}"
        and condition == "assertion.repository_id == '99' && assertion.ref == 'refs/heads/main'"
    )
    member = f"principalSet://iam.googleapis.com/projects/555/locations/global/workloadIdentityPools/{pool}/attribute.repository/{REPO}"
    assert gcp.args("set_sa_member") == [("x@y", github_actions.SA_ROLE, member, True)]
    text = committed(gh, app)
    assert (
        f'workload_identity_provider: "projects/555/locations/global/workloadIdentityPools/{pool}/providers/{provider}"'
        in text
    )
    assert "gcloud run services update" in text and 'service_account: "x@y"' in text

    gh.routes[("GET", contents_path(app))] = (200, {"sha": "f" * 40})
    gh.routes[("DELETE", contents_path(app))] = (200, {})
    resp = switch(client, people, app, location="pc")
    assert resp.status_code == 200 and resp.json()["build"] == {"location": "pc"} and resp.json()["job_id"]
    jobs.run_queued()
    assert db.get(Job, resp.json()["job_id"]).status == "succeeded"
    assert [c[0] for c in gh.calls if c[1] == contents_path(app)][-1] == "DELETE"
    assert gcp.args("delete_wif_provider") == [(pool, provider)]
    assert gcp.args("set_sa_member")[-1] == ("x@y", github_actions.SA_ROLE, member, False)
    assert "run_service" in db.get(App, app.id).cloud_state  # the app itself keeps serving


def test_changing_build_settings_rewrites_the_workflow_and_bad_values_fail_plainly(client, db, people, gh, aws):
    app = cloud_app(db, people["project"])
    set_up(client, db, people, gh, app)
    gh.routes[("GET", contents_path(app))] = (404, {})
    resp = client.patch(
        f"{people['base']}/{app.id}", json={"build_command": "npm run build:prod"}, headers=people["dev"]
    )
    assert resp.status_code == 200 and resp.json()["build_job_id"], resp.text
    jobs.run_queued()
    recipe = committed(gh, app).split("echo '", 1)[1].split("'", 1)[0]
    assert "npm run build:prod" in base64.b64decode(recipe).decode()

    # The workflow, the role's trust and the reports belong to the repository: moving it needs a switch back first.
    moved = client.patch(
        f"{people['base']}/{app.id}", json={"repo_url": "https://github.com/acme/other"}, headers=people["dev"]
    )
    assert moved.status_code == 409 and moved.json()["error"]["code"] == "builds_on_github"

    client.patch(f"{people['base']}/{app.id}", json={"root_dir": "web/${{ secrets.TOKEN }}"}, headers=people["dev"])
    jobs.run_queued()
    db.expire_all()
    build = deployments.app_out(db, db.get(App, app.id))["build"]
    assert build["status"] == "error" and "GitHub would evaluate" in build["message"]


def test_moving_the_app_tears_github_actions_down_with_the_target(client, db, people, gh, aws):
    app = cloud_app(db, people["project"])
    set_up(client, db, people, gh, app)
    gh.routes[("GET", contents_path(app))] = (200, {"sha": "f" * 40})
    gh.routes[("DELETE", contents_path(app))] = (200, {})
    resp = client.patch(f"{people['base']}/{app.id}", json={"target": "local"}, headers=people["admin"])
    assert resp.status_code == 200 and resp.json()["build"] == {"location": "pc"}
    jobs.run_queued()
    assert db.get(Job, resp.json()["teardown_job_id"]).status == "succeeded"
    assert (github_actions.role_name(app), cloud_aws.GITHUB_ROLE_POLICY) in aws.args("delete_instance_role")


def test_requirements_list_what_the_setup_uses():
    statements = {s["Sid"]: s for s in cloud.aws_statements()}
    assert statements["GitHubActionsSignIn"]["Resource"].endswith(":oidc-provider/token.actions.githubusercontent.com")
    assert statements["GitHubActionsRoles"]["Resource"] == "arn:aws:iam::*:role/deployer-gha-*"
    assert "iam:PassRole" not in statements["GitHubActionsRoles"]["Action"]
    roles = {r["role"]: r for r in cloud.GOOGLE_ROLES}
    assert roles["roles/iam.serviceAccountAdmin"]["on"] == "service_account"
    assert {"iam.googleapis.com", "sts.googleapis.com", "iamcredentials.googleapis.com"} <= {
        a["api"] for a in cloud.GOOGLE_APIS
    }


def test_real_google_client_binding_and_provider_requests():
    """The REST shapes of the workload identity calls (no Google: httpx.MockTransport)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    seen: list[tuple[str, str, dict]] = []
    policy = {"etag": "e1", "bindings": [{"role": "roles/other", "members": ["user:a@b.c"]}]}

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == cloud_gcp.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "ya29." + secrets.token_hex(8), "expires_in": 3600})
        body = json.loads(request.content) if request.content else {}
        seen.append(
            (request.method, request.url.path + (f"?{request.url.query.decode()}" if request.url.query else ""), body)
        )
        path = request.url.path
        if path.endswith(":getIamPolicy"):
            return httpx.Response(200, json=policy)
        if request.method == "POST" and path.endswith("/providers"):
            return httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS", "message": "exists"}})
        if request.method == "GET" and "/providers/" in path:
            return httpx.Response(200, json={"state": "DELETED"})
        return httpx.Response(200, json={})

    cloud_gcp.set_transport(httpx.MockTransport(handle))
    try:
        sa = {"client_email": "deployer@demo-proj-123.iam.gserviceaccount.com", "private_key": pem.decode()}
        client = cloud_gcp.GcpClient({"service_account": sa, "project_id": "demo-proj-123"})
        member = "principalSet://iam.googleapis.com/projects/555/locations/global/workloadIdentityPools/p/attribute.repository/a/b"
        client.set_sa_member(sa["client_email"], github_actions.SA_ROLE, member, True)
        client.ensure_wif_provider("deployer-github", "gh-abc12345", "assertion.ref == 'refs/heads/main'")
    finally:
        cloud_gcp.set_transport(None)
    set_policy = next(b for m, p, b in seen if p.endswith(":setIamPolicy"))["policy"]
    assert (
        set_policy["etag"] == "e1" and {"role": github_actions.SA_ROLE, "members": [member]} in set_policy["bindings"]
    )
    assert {"role": "roles/other", "members": ["user:a@b.c"]} in set_policy["bindings"]
    calls = [(m, p) for m, p, _ in seen]
    base = "/v1/projects/demo-proj-123/locations/global/workloadIdentityPools/deployer-github/providers"
    assert ("POST", f"{base}/gh-abc12345:undelete") in calls  # soft-deleted (30 days): brought back
    patch = next(b for m, p, b in seen if m == "PATCH")
    assert patch["attributeCondition"] == "assertion.ref == 'refs/heads/main'"
    assert patch["oidc"] == {"issuerUri": "https://token.actions.githubusercontent.com"}
