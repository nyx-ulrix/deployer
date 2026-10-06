"""docs/CLOUD.md "G1": app secrets in AWS Secrets Manager / Google Secret Manager (opt-in, billable), and an
environment change reaching an App Runner / Cloud Run app at once (an `env` deployment republishes the live
artifact from this PC - also for apps that build on GitHub Actions). AWS and Google are fakes; the real
clients' request shapes run against botocore's models (Stubber) and `httpx.MockTransport`."""

import base64
import json
import secrets as pysecrets

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.crypto import encrypt_json
from app.models import App, DataSource, Deployment, Job
from app.services import cloud, cloud_aws, cloud_deploy, cloud_gcp, cloud_secrets, jobs
from tests.apps_support import make_app
from tests.test_cloud import FakeCloud, connection, deploy

ARN = "arn:aws:secretsmanager:eu-west-1:123456789012:secret:{}-AbCdEf"
SA = "serviceAccount:555-compute@developer.gserviceaccount.com"


@pytest.fixture
def aws(monkeypatch):
    fake = FakeCloud(
        ensure_repository=lambda name: f"123456789012.dkr.ecr.eu-west-1.amazonaws.com/{name}",
        registry_login=("123456789012.dkr.ecr.eu-west-1.amazonaws.com", "AWS", "ecr-" + pysecrets.token_hex(8)),
        ensure_boundary={"arn": "arn:aws:iam::123456789012:policy/deployer-boundary", "current": True},
        ensure_access_role="arn:aws:iam::123456789012:role/deployer-apprunner-ecr-access",
        ensure_instance_role=lambda name, policy, boundary: f"arn:aws:iam::123456789012:role/{name}",
        create_service={"arn": "arn:svc", "url": "https://abc.eu-west-1.awsapprunner.com", "operation_id": "op1"},
        update_service="op2",
        operation="SUCCEEDED",
        put_secret=lambda name, value: ARN.format(name),
    )
    cloud_aws.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_aws.set_factory(None)


@pytest.fixture
def gcp(monkeypatch):
    fake = FakeCloud(
        project_info={"projectNumber": "555"},
        create_version=lambda site, config: f"sites/{site}/versions/v1",
        ensure_repository="us-central1-docker.pkg.dev/demo-proj-123/deployer",
        docker_login=("us-central1-docker.pkg.dev", "oauth2accesstoken", "ya29." + pysecrets.token_hex(8)),
        create_service="projects/demo-proj-123/locations/us-central1/operations/op1",
        update_service="projects/demo-proj-123/locations/us-central1/operations/op2",
        operation={"done": True, "error": None},
        put_secret=lambda name, value: name,
    )
    cloud_gcp.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_gcp.set_factory(None)


def rds_source(db, project, conn, password: str) -> DataSource:
    """A connected (not created) RDS database on the connection: its password must reach the store."""
    config = {"host": "shop.abc.eu-west-1.rds.amazonaws.com", "port": 3306, "username": "deployer"}
    config |= {"password": password, "database": "shopdb", "tls": True, "tls_verify": False}
    ds = DataSource(
        project_id=project.id,
        name="Shop DB",
        kind="sql",
        engine="mysql",
        mode="external",
        database_name="shopdb",
        config_encrypted=encrypt_json(config),
        status="ok",
        cloud_connection_id=conn.id,
        cloud_state={"provider": "aws", "service": "rds", "created": False, "instance_id": "shop", "port": 3306},
    )
    db.add(ds)
    db.commit()
    return ds


def kwargs_of(fake: FakeCloud, name: str) -> list[dict]:
    return [kw for n, kw in fake.kwargs if n == name]


def run_env_deployment(db, resp) -> Deployment:
    dep_id = resp.json()["env_deployment_id"]
    assert dep_id, resp.text
    jobs.run_queued()
    db.expire_all()
    dep = db.get(Deployment, dep_id)
    assert dep.trigger == "env" and dep.status == "live", dep.error
    return dep


def test_aws_app_keeps_its_secrets_in_secrets_manager(client, db, docker, team, aws):
    conn = connection(db)
    password = "pw-" + pysecrets.token_hex(12)
    rds_source(db, team["project"], conn, password)
    api_key = "sk-" + pysecrets.token_hex(12)
    env = {"API_KEY": api_key, "NODE_ENV": "production"}
    app = make_app(
        db, team["project"], "Api", env=env, target="aws_app", cloud_connection_id=conn.id, database_access=True
    )
    url = f"{team['base']}/{app.id}"
    name = cloud_deploy.resource_name(app)

    # Off by default; admins switch it on after confirming the cost; never on a static target.
    shown = client.get(url, headers=team["dev"]).json()["cloud"]["secrets"]
    assert shown["enabled"] is False and shown["store"] == "AWS Secrets Manager" and "US$0.40" in shown["cost"]
    assert (
        client.patch(url, json={"cloud_secrets": True, "confirm_billing": True}, headers=team["dev"]).status_code == 403
    )
    refused = client.patch(url, json={"cloud_secrets": True}, headers=team["admin"])
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "billing_not_confirmed"
    assert "Secrets Manager" in refused.json()["error"]["message"]
    static = make_app(db, team["project"], "Site", preset="static", target="aws_static", cloud_connection_id=conn.id)
    wrong = client.patch(
        f"{team['base']}/{static.id}", json={"cloud_secrets": True, "confirm_billing": True}, headers=team["admin"]
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["details"]["field"] == "cloud_secrets"
    resp = client.patch(url, json={"cloud_secrets": True, "confirm_billing": True}, headers=team["admin"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["cloud"]["secrets"]["enabled"] is True and resp.json()["env_deployment_id"] is None

    # The deploy stores the app's variables and the database password / URL; the service gets references.
    dep = deploy(db, db.get(App, app.id))
    assert dep.status == "live", dep.error
    assert aws.args("put_secret") == [
        (f"{name}-API_KEY", api_key),
        (f"{name}-DEPLOYER_DB_SHOP_DB_PASSWORD", password),
        (
            f"{name}-DEPLOYER_DB_SHOP_DB_URL",
            f"mysql://deployer:{password}@shop.abc.eu-west-1.rds.amazonaws.com:3306/shopdb?ssl=true",
        ),
        (f"{name}-NODE_ENV", "production"),
    ]
    (_, _, _, plain, _, _) = aws.args("create_service")[0]
    refs = kwargs_of(aws, "create_service")[0]["secret_arns"]
    assert set(refs) == {"API_KEY", "NODE_ENV", "DEPLOYER_DB_SHOP_DB_PASSWORD", "DEPLOYER_DB_SHOP_DB_URL"}
    assert refs["API_KEY"] == ARN.format(f"{name}-API_KEY")
    assert not set(refs) & set(plain) and plain["DEPLOYER_DB_SHOP_DB_HOST"] == "shop.abc.eu-west-1.rds.amazonaws.com"
    ((role, policy, _),) = aws.args("ensure_instance_role")
    assert role == cloud_deploy.instance_role_name(app)
    assert policy["Statement"] == [
        {"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": sorted(refs.values())}
    ]
    assert kwargs_of(aws, "create_service")[0]["instance_role_arn"] == f"arn:aws:iam::123456789012:role/{role}"
    assert (
        api_key not in dep.log and password not in dep.log and "Storing 4 secret(s) in AWS Secrets Manager" in dep.log
    )
    db.expire_all()
    out = client.get(url, headers=team["dev"]).json()
    assert out["cloud"]["secrets"]["stored"] == sorted(refs) and api_key not in json.dumps(out)
    assert any("AWS Secrets Manager secrets" in r for r in out["cloud"]["resources"])

    # Changing the variables republishes the live image at once (no build): new values stored, the removed
    # variable's secret deleted after the rollout.
    aws.calls.clear()
    aws.kwargs.clear()
    docker.calls.clear()
    new_key = "sk-" + pysecrets.token_hex(12)
    resp = client.patch(url, json={"env": {"API_KEY": new_key}}, headers=team["dev"])
    assert resp.status_code == 200, resp.text
    env_dep = run_env_deployment(db, resp)
    assert env_dep.image_tag == dep.image_tag and env_dep.rollback_of == dep.id and docker.steps() == []
    assert (f"{name}-API_KEY", new_key) in aws.args("put_secret") and not any(
        "NODE_ENV" in a[0] for a in aws.args("put_secret")
    )
    assert aws.names().index("delete_secret") > aws.names().index("operation")
    assert aws.args("delete_secret") == [(ARN.format(f"{name}-NODE_ENV"),)]
    assert "NODE_ENV" not in kwargs_of(aws, "update_service")[0]["secret_arns"]
    assert sorted(cloud_secrets.state_of(db.get(App, app.id))["stored"]) == [
        "API_KEY",
        "DEPLOYER_DB_SHOP_DB_PASSWORD",
        "DEPLOYER_DB_SHOP_DB_URL",
    ]
    assert new_key not in env_dep.log and db.get(Deployment, dep.id).status == "superseded"

    # Switching it off: plain environment again, every stored secret deleted once the new version is live.
    aws.calls.clear()
    aws.kwargs.clear()
    resp = client.patch(url, json={"cloud_secrets": False}, headers=team["admin"])
    assert resp.status_code == 200, resp.text
    run_env_deployment(db, resp)
    assert aws.args("put_secret") == [] and "secret_arns" not in kwargs_of(aws, "update_service")[0]
    assert aws.args("update_service")[0][3]["API_KEY"] == new_key
    assert sorted(a[0] for a in aws.args("delete_secret")) == sorted(
        ARN.format(f"{name}-{k}") for k in ("API_KEY", "DEPLOYER_DB_SHOP_DB_PASSWORD", "DEPLOYER_DB_SHOP_DB_URL")
    )
    assert [a[:2] for a in aws.args("ensure_instance_role")] == [(role, None)]  # the role stays, allowed nothing
    assert cloud_secrets.state_of(db.get(App, app.id)) == {"enabled": False, "stored": {}}

    # Deleting the app deletes what is still in the store.
    client.patch(url, json={"cloud_secrets": True, "confirm_billing": True}, headers=team["admin"])
    jobs.run_queued()
    aws.calls.clear()
    deleted = client.delete(url, headers=team["admin"])
    assert deleted.status_code == 200, deleted.text
    jobs.run_queued()
    assert db.get(Job, deleted.json()["teardown_job_id"]).status == "succeeded"
    assert sorted(a[0] for a in aws.args("delete_secret")) == sorted(
        ARN.format(f"{name}-{k}") for k in ("API_KEY", "DEPLOYER_DB_SHOP_DB_PASSWORD", "DEPLOYER_DB_SHOP_DB_URL")
    )


def test_env_change_reaches_a_github_built_app_without_a_rollback(client, db, docker, team, aws):
    conn = connection(db)
    ecr = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/deployer-api-x"
    state = {
        "ecr_repository": "deployer-api-x",
        "ecr_uri": ecr,
        "service_arn": "arn:svc",
        "service_name": "deployer-api-x",
        "service_url": "https://abc.eu-west-1.awsapprunner.com",
        "access_role_arn": "arn:aws:iam::1:role/deployer-apprunner-ecr-access",
        "github": {"status": "ready", "repo": "acme/api", "workflow_path": ".github/workflows/x.yml", "branch": "main"},
    }
    app = make_app(
        db, team["project"], "Api", env={"A": "1"}, target="aws_app", cloud_connection_id=conn.id, cloud_state=state
    )
    built = Deployment(app_id=app.id, status="live", trigger="github", branch="main", image_tag=f"{ecr}:gh-7-1", log="")
    db.add(built)
    db.flush()
    app.live_deployment_id = built.id
    db.commit()
    url = f"{team['base']}/{app.id}"
    # A setting that is not environment does not republish.
    same = client.patch(url, json={"name": "Api 2"}, headers=team["dev"])
    assert same.status_code == 200 and same.json()["env_deployment_id"] is None
    resp = client.patch(url, json={"env": {"A": "2", "B": "3"}}, headers=team["dev"])
    assert resp.status_code == 200, resp.text
    dep = run_env_deployment(db, resp)
    assert docker.steps() == [] and aws.names()[-2:] == ["update_service", "operation"]
    assert aws.args("update_service")[0][1] == f"{ecr}:gh-7-1" and aws.args("update_service")[0][3] == {
        "A": "2",
        "B": "3",
    }
    assert db.get(App, app.id).live_deployment_id == dep.id and db.get(Deployment, built.id).status == "superseded"
    listed = client.get(f"{url}/deployments", headers=team["dev"]).json()
    rows = listed["deployments"] if isinstance(listed, dict) else listed
    assert [d["trigger"] for d in rows][:2] == ["env", "github"]


def test_cloud_run_app_keeps_its_secrets_in_secret_manager(client, db, docker, team, gcp):
    conn = connection(db, "firebase")
    token = "tok-" + pysecrets.token_hex(12)
    app = make_app(db, team["project"], "Api", env={"TOKEN": token}, target="firebase_app", cloud_connection_id=conn.id)
    url = f"{team['base']}/{app.id}"
    shown = client.get(url, headers=team["dev"]).json()["cloud"]["secrets"]
    assert shown["store"] == "Google Secret Manager" and "free" in shown["cost"]
    resp = client.patch(url, json={"cloud_secrets": True, "confirm_billing": True}, headers=team["admin"])
    assert resp.status_code == 200, resp.text
    name = f"{cloud_deploy.resource_name(app)}-TOKEN"
    dep = deploy(db, db.get(App, app.id))
    assert dep.status == "live", dep.error
    assert gcp.args("put_secret") == [(name, token)] and gcp.args("allow_secret") == [(name, SA)]
    assert gcp.args("create_service")[0][3] == {} and kwargs_of(gcp, "create_service")[0] == {
        "secrets": {"TOKEN": name}
    }
    assert token not in dep.log and "555-compute@developer.gserviceaccount.com" in dep.log
    # Moving the app off Cloud Run deletes the secret with the service.
    gcp.calls.clear()
    moved = client.patch(url, json={"target": "local"}, headers=team["admin"])
    assert moved.status_code == 200, moved.text
    jobs.run_queued()
    assert db.get(Job, moved.json()["teardown_job_id"]).status == "succeeded"
    assert gcp.args("delete_secret") == [(name,)]


def test_mcp_set_app_secrets_store(client, db, team, aws):
    conn = connection(db)
    app = make_app(db, team["project"], "Api", target="aws_app", cloud_connection_id=conn.id)
    mcp = f"/v1/projects/{team['project'].id}/mcp"

    def call(headers, **arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
        body["params"] = {"name": "set_app_secrets_store", "arguments": {"app_id": app.id, **arguments}}
        out = client.post(mcp, json=body, headers=headers).json()
        if "error" in out:
            return None, out["error"]
        return out["result"]["isError"], json.loads(out["result"]["content"][0]["text"])

    assert call(team["dev"], enabled=True, confirm_billing=True)[1]["code"] == -32602  # admins only
    is_error, out = call(team["admin"], enabled=True)
    assert is_error and out["error"]["code"] == "billing_not_confirmed"
    is_error, out = call(team["admin"], enabled=True, confirm_billing=True)
    assert not is_error and out["cloud"]["secrets"]["enabled"] is True, out
    assert not call(team["admin"], enabled=False)[0]


def test_policy_and_roles_cover_the_secret_stores():
    statement = next(s for s in cloud.aws_statements() if s["Sid"] == "AppSecrets")
    assert statement["Resource"] == "arn:aws:secretsmanager:*:*:secret:deployer-*"
    assert set(statement["Action"]) == {
        "secretsmanager:CreateSecret",
        "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue",
        "secretsmanager:DeleteSecret",
        "secretsmanager:TagResource",
    }
    assert {r["role"]: r.get("only_for") for r in cloud.GOOGLE_ROLES}["roles/secretmanager.admin"] == "cloud_secrets"
    assert {a["api"]: a.get("only_for") for a in cloud.GOOGLE_APIS}["secretmanager.googleapis.com"] == "cloud_secrets"


def test_secrets_manager_calls_match_botocore_models():
    """The real AwsClient methods against botocore's service models (a wrong parameter name fails here)."""
    from botocore.stub import Stubber

    from app.services.cloud_aws import TAG, AwsClient

    aws = AwsClient({"region": "eu-west-1", "access_key_id": "test", "secret_access_key": "test"})
    sm = aws._session.client("secretsmanager", region_name="eu-west-1")
    aws._c = lambda service, region=None: sm
    name, arn = "deployer-api-1a2b3c4d-API_KEY", ARN.format("deployer-api-1a2b3c4d-API_KEY")
    with Stubber(sm) as stub:
        stub.add_response(
            "create_secret", {"ARN": arn, "Name": name}, {"Name": name, "SecretString": "v1", "Tags": [TAG]}
        )
        # Exists with the same value: nothing written. Exists with another value: a new version.
        stub.add_client_error("create_secret", "ResourceExistsException")
        stub.add_response("get_secret_value", {"ARN": arn, "Name": name, "SecretString": "v1"}, {"SecretId": name})
        stub.add_client_error("create_secret", "ResourceExistsException")
        stub.add_response("get_secret_value", {"ARN": arn, "Name": name, "SecretString": "v1"}, {"SecretId": name})
        stub.add_response(
            "put_secret_value",
            {"ARN": arn, "Name": name, "VersionId": "2" * 32},
            {"SecretId": name, "SecretString": "v2"},
        )
        stub.add_response(
            "delete_secret", {"ARN": arn, "Name": name}, {"SecretId": arn, "ForceDeleteWithoutRecovery": True}
        )
        stub.add_client_error("delete_secret", "ResourceNotFoundException")
        assert aws.put_secret(name, "v1") == arn
        assert aws.put_secret(name, "v1") == arn
        assert aws.put_secret(name, "v2") == arn
        aws.delete_secret(arn)
        aws.delete_secret(arn)  # already gone
        stub.assert_no_pending_responses()


def test_secret_manager_rest_shapes():
    """The real GcpClient against a mock transport: paths, bodies, the unchanged-value check and 404s."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    config = {
        "service_account": {
            "client_email": "deployer@demo-proj-123.iam.gserviceaccount.com",
            "private_key": pem.decode(),
        },
        "project_id": "demo-proj-123",
    }
    base = "/v1/projects/demo-proj-123/secrets"
    name = "deployer-api-1a2b3c4d-TOKEN"
    seen: list[tuple[str, str, dict | None]] = []
    versions: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == cloud_gcp.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3600})
        body = json.loads(request.content) if request.content else None
        seen.append(
            (request.method, request.url.path + ("?" + request.url.query.decode() if request.url.query else ""), body)
        )
        assert request.headers["Authorization"] == "Bearer ya29.x"
        path = request.url.path
        if path == base and request.method == "POST":
            return httpx.Response(409 if versions else 200, json={"name": f"projects/555/secrets/{name}"})
        if path.endswith("/versions/latest:access"):
            if not versions:
                return httpx.Response(404, json={"error": {"message": "no version", "status": "NOT_FOUND"}})
            return httpx.Response(200, json={"payload": {"data": versions[-1]}})
        if path.endswith(":addVersion"):
            versions.append(body["payload"]["data"])
            return httpx.Response(200, json={"name": f"projects/555/secrets/{name}/versions/{len(versions)}"})
        if path.endswith(":setIamPolicy"):
            return httpx.Response(200, json=body["policy"])
        if request.method == "DELETE":
            return httpx.Response(404 if versions and versions.pop() == "gone" else 200, json={})
        return httpx.Response(404, json={"error": {"message": "nope"}})

    cloud_gcp.set_transport(httpx.MockTransport(handle))
    try:
        gcp = cloud_gcp.client(config)
        assert gcp.put_secret(name, "v1") == name
        assert gcp.put_secret(name, "v1") == name  # unchanged: no new version
        assert gcp.put_secret(name, "v2") == name
        gcp.allow_secret(name, SA)
        gcp.delete_secret(name)
        versions.append("gone")
        gcp.delete_secret(name)  # already gone: fine
    finally:
        cloud_gcp.set_transport(None)
        cloud_gcp._tokens.clear()
    enc = lambda v: base64.b64encode(v.encode()).decode()  # noqa: E731
    create = {"replication": {"automatic": {}}, "labels": {"managed-by": "deployer"}}
    assert seen == [
        ("POST", f"{base}?secretId={name}", create),
        ("GET", f"{base}/{name}/versions/latest:access", None),
        ("POST", f"{base}/{name}:addVersion", {"payload": {"data": enc("v1")}}),
        ("POST", f"{base}?secretId={name}", create),
        ("GET", f"{base}/{name}/versions/latest:access", None),
        ("POST", f"{base}?secretId={name}", create),
        ("GET", f"{base}/{name}/versions/latest:access", None),
        ("POST", f"{base}/{name}:addVersion", {"payload": {"data": enc("v2")}}),
        (
            "POST",
            f"{base}/{name}:setIamPolicy",
            {"policy": {"bindings": [{"role": cloud_gcp.SECRET_ACCESSOR, "members": [SA]}]}},
        ),
        ("DELETE", f"{base}/{name}", None),
        ("DELETE", f"{base}/{name}", None),
    ]
    # A Cloud Run service body references the secret, never the value.
    body = cloud_gcp.GcpClient._service_body("img", 3000, {"A": "1"}, {"TOKEN": name})
    assert body["template"]["containers"][0]["env"] == [
        {"name": "A", "value": "1"},
        {"name": "TOKEN", "valueSource": {"secretKeyRef": {"secret": name, "version": "latest"}}},
    ]


def test_deploy_never_writes_back_an_option_switched_meanwhile(client, db, docker, team, aws):
    """The job records the stored secrets; `enabled` is the row's current value, not the job's copy."""
    conn = connection(db)
    app = make_app(db, team["project"], "Api", env={"A": "1"}, target="aws_app", cloud_connection_id=conn.id)
    cloud_secrets.set_enabled(app, True)
    db.commit()

    def switched_off_meanwhile(name, value):
        with jobs.get_sessionmaker()() as session:
            row = session.get(App, app.id)
            cloud_secrets.set_enabled(row, False)
            session.commit()
        return ARN.format(name)

    aws.returns["put_secret"] = switched_off_meanwhile
    dep = deploy(db, db.get(App, app.id))
    assert dep.status == "live", dep.error
    assert cloud_secrets.state_of(db.get(App, app.id)) == {
        "enabled": False,
        "stored": {"A": ARN.format(f"{cloud_deploy.resource_name(app)}-A")},
    }


def test_split_keeps_empty_values_out_of_the_store():
    """Secrets Manager refuses an empty SecretString (botocore: min 1), so an empty variable stays plain."""
    app = App(env_encrypted=encrypt_json({"API_KEY": "sk-1", "FEATURE": ""}))
    env = {"API_KEY": "sk-1", "FEATURE": "", "DEPLOYER_DB_X_HOST": "h", "DEPLOYER_DB_X_PASSWORD": "pw-9"}
    plain, secret = cloud_secrets.split(app, env, [{"config": {"password": "pw-9"}}])
    assert secret == {"API_KEY": "sk-1", "DEPLOYER_DB_X_PASSWORD": "pw-9"}
    assert plain == {"FEATURE": "", "DEPLOYER_DB_X_HOST": "h"}
