"""docs/CLOUD.md "G3": the `deployer-boundary` permissions boundary. The IAM calls run against botocore's real
service models (Stubber validates every parameter name), the Deployer user's policy may only create roles and
write their policies when the boundary is on them and can never change or delete the boundary, and the deploy /
GitHub Actions jobs pass the boundary's ARN to every role they make."""

import json
from urllib.parse import quote

import pytest
from botocore.stub import Stubber

from app.models import App
from app.services import cloud, cloud_aws, cloud_deploy
from app.services.cloud_aws import BOUNDARY_DOCUMENT, BOUNDARY_POLICY, TAG, AwsClient
from tests.apps_support import make_app
from tests.test_cloud import FakeCloud, aws_key_id, aws_secret, connection, deploy

ACCOUNT = "123456789012"


@pytest.fixture
def aws(monkeypatch):
    fake = FakeCloud(
        ensure_boundary={"arn": f"arn:aws:iam::{ACCOUNT}:policy/{BOUNDARY_POLICY}", "current": True},
        ensure_repository=lambda name: f"{ACCOUNT}.dkr.ecr.eu-west-1.amazonaws.com/{name}",
        registry_login=(f"{ACCOUNT}.dkr.ecr.eu-west-1.amazonaws.com", "AWS", "ecr-pw"),
        ensure_access_role=f"arn:aws:iam::{ACCOUNT}:role/{cloud_aws.ACCESS_ROLE}",
        create_service={"arn": "arn:svc", "url": "https://abc.eu-west-1.awsapprunner.com", "operation_id": "op1"},
        update_service="op2",
        operation="SUCCEEDED",
    )
    cloud_aws.set_factory(lambda config: fake)
    monkeypatch.setattr(cloud_deploy, "POLL_S", 0)
    yield fake
    cloud_aws.set_factory(None)


ARN = f"arn:aws:iam::{ACCOUNT}:policy/{BOUNDARY_POLICY}"
ROLE_WRITES = {"iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy", "iam:PutRolePermissionsBoundary"}
# Anything that could widen or lift the boundary once it exists.
ESCALATIONS = {
    "iam:CreatePolicyVersion",
    "iam:SetDefaultPolicyVersion",
    "iam:DeletePolicy",
    "iam:DeletePolicyVersion",
    "iam:DeleteRolePermissionsBoundary",
    "iam:*",
    "*",
}


def real_client():
    client = AwsClient({"region": "eu-west-1", "access_key_id": "test", "secret_access_key": "test"})
    iam = client._session.client("iam", region_name="eu-west-1")
    client._c = lambda service, region=None: iam
    return client, iam


def role(name: str, boundary: str | None = None) -> dict:
    out = {
        "RoleName": name,
        "Arn": f"arn:aws:iam::{ACCOUNT}:role/{name}",
        "Path": "/",
        "RoleId": "AROA" + "X" * 17,
        "CreateDate": "2026-01-01T00:00:00Z",
    }
    if boundary:
        out["PermissionsBoundary"] = {"PermissionsBoundaryType": "Policy", "PermissionsBoundaryArn": boundary}
    return out


def test_ensure_boundary_creates_once_and_notices_an_outdated_copy():
    client, iam = real_client()
    with Stubber(iam) as stub:
        stub.add_response(
            "create_policy",
            {"Policy": {"Arn": ARN}},
            {
                "PolicyName": BOUNDARY_POLICY,
                "PolicyDocument": json.dumps(BOUNDARY_DOCUMENT),
                "Description": "Deployer: the most any role Deployer creates (apps, GitHub Actions) may do",
            },
        )
        assert client.ensure_boundary(ACCOUNT) == {"arn": ARN, "current": True}
        # Exists with this version's document: nothing is changed (Deployer may not change it anyway).
        stub.add_client_error("create_policy", "EntityAlreadyExists")
        stub.add_response("get_policy", {"Policy": {"Arn": ARN, "DefaultVersionId": "v2"}}, {"PolicyArn": ARN})
        stub.add_response(
            "get_policy_version",
            {"PolicyVersion": {"Document": quote(json.dumps(BOUNDARY_DOCUMENT)), "VersionId": "v2"}},
            {"PolicyArn": ARN, "VersionId": "v2"},
        )
        assert client.ensure_boundary(ACCOUNT) == {"arn": ARN, "current": True}
        # An older copy: reported, kept.
        stub.add_client_error("create_policy", "EntityAlreadyExists")
        stub.add_response("get_policy", {"Policy": {"Arn": ARN, "DefaultVersionId": "v1"}}, {"PolicyArn": ARN})
        older = {"Version": "2012-10-17", "Statement": BOUNDARY_DOCUMENT["Statement"][:2]}
        stub.add_response(
            "get_policy_version",
            {"PolicyVersion": {"Document": quote(json.dumps(older)), "VersionId": "v1"}},
            {"PolicyArn": ARN, "VersionId": "v1"},
        )
        assert client.ensure_boundary(ACCOUNT) == {"arn": ARN, "current": False}
        stub.assert_no_pending_responses()


def test_roles_are_created_within_the_boundary_and_old_ones_get_it():
    client, iam = real_client()
    access, app_role, gha = cloud_aws.ACCESS_ROLE, "deployer-app-shop-x", "deployer-gha-shop-x"
    policy = {"Version": "2012-10-17", "Statement": []}
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole"}]}
    with Stubber(iam) as stub:
        # Access role: new -> created with the boundary, then the AWS managed policy attached.
        stub.add_client_error("get_role", "NoSuchEntity")
        stub.add_response("create_role", {"Role": role(access, ARN)})
        stub.add_response("attach_role_policy", {}, {"RoleName": access, "PolicyArn": cloud_aws.ECR_ACCESS_POLICY})
        assert client.ensure_access_role(ARN).endswith(f":role/{access}")
        # Access role made before G3: gets the boundary on the next deploy; one that has it is left alone.
        stub.add_response("get_role", {"Role": role(access)}, {"RoleName": access})
        stub.add_response("put_role_permissions_boundary", {}, {"RoleName": access, "PermissionsBoundary": ARN})
        client.ensure_access_role(ARN)
        stub.add_response("get_role", {"Role": role(access, ARN)}, {"RoleName": access})
        client.ensure_access_role(ARN)
        # Instance role: created within the boundary, policy written; later (no tables) the policy goes.
        stub.add_client_error("get_role", "NoSuchEntity")
        tasks = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        stub.add_response(
            "create_role",
            {"Role": role(app_role, ARN)},
            {
                "RoleName": app_role,
                "AssumeRolePolicyDocument": json.dumps(tasks),
                "Description": "Deployer: what this App Runner app's code may use",
                "PermissionsBoundary": ARN,
                "Tags": [TAG],
            },
        )
        stub.add_response(
            "put_role_policy",
            {},
            {"RoleName": app_role, "PolicyName": cloud_aws.INSTANCE_ROLE_POLICY, "PolicyDocument": json.dumps(policy)},
        )
        assert client.ensure_instance_role(app_role, policy, ARN).endswith(f":role/{app_role}")
        stub.add_response("get_role", {"Role": role(app_role)}, {"RoleName": app_role})
        stub.add_response("put_role_permissions_boundary", {}, {"RoleName": app_role, "PermissionsBoundary": ARN})
        stub.add_response(
            "delete_role_policy", {}, {"RoleName": app_role, "PolicyName": cloud_aws.INSTANCE_ROLE_POLICY}
        )
        client.ensure_instance_role(app_role, None, ARN)
        # GitHub Actions role: the same, plus the trust rewritten on an existing one.
        stub.add_client_error("get_role", "NoSuchEntity")
        stub.add_response(
            "create_role",
            {"Role": role(gha, ARN)},
            {
                "RoleName": gha,
                "AssumeRolePolicyDocument": json.dumps(trust),
                "Description": "Deployer: GitHub Actions deploys of one app",
                "MaxSessionDuration": 3600,
                "PermissionsBoundary": ARN,
                "Tags": [TAG],
            },
        )
        stub.add_response(
            "put_role_policy",
            {},
            {"RoleName": gha, "PolicyName": cloud_aws.GITHUB_ROLE_POLICY, "PolicyDocument": json.dumps(policy)},
        )
        client.ensure_github_role(gha, trust, policy, ARN)
        stub.add_response("get_role", {"Role": role(gha)}, {"RoleName": gha})
        stub.add_response("put_role_permissions_boundary", {}, {"RoleName": gha, "PermissionsBoundary": ARN})
        stub.add_response("update_assume_role_policy", {}, {"RoleName": gha, "PolicyDocument": json.dumps(trust)})
        stub.add_response(
            "put_role_policy",
            {},
            {"RoleName": gha, "PolicyName": cloud_aws.GITHUB_ROLE_POLICY, "PolicyDocument": json.dumps(policy)},
        )
        client.ensure_github_role(gha, trust, policy, ARN)
        stub.assert_no_pending_responses()


def _actions(statement: dict) -> set[str]:
    a = statement["Action"]
    return {a} if isinstance(a, str) else set(a)


def _resources(statement: dict) -> set[str]:
    r = statement["Resource"]
    return {r} if isinstance(r, str) else set(r)


def test_deployer_user_may_only_write_roles_that_carry_the_boundary():
    statements = {s["Sid"]: s for s in cloud.aws_statements()}
    bounded = statements["RolesWithinBoundary"]
    assert _actions(bounded) == ROLE_WRITES
    assert bounded["Condition"] == {"ArnLike": {"iam:PermissionsBoundary": f"arn:aws:iam::*:policy/{BOUNDARY_POLICY}"}}
    assert _resources(bounded) == {
        f"arn:aws:iam::*:role/{cloud_aws.ACCESS_ROLE}",
        f"arn:aws:iam::*:role/{cloud_aws.INSTANCE_ROLE_PREFIX}*",
        f"arn:aws:iam::*:role/{cloud_aws.GITHUB_ROLE_PREFIX}*",
    }
    # The role-writing actions appear nowhere without the condition, and nothing can touch the boundary
    # policy's versions or lift it from a role.
    for sid, s in statements.items():
        if sid != "RolesWithinBoundary":
            assert not _actions(s) & ROLE_WRITES, sid
        assert not _actions(s) & ESCALATIONS, sid
    assert _actions(statements["BoundaryPolicy"]) == {"iam:CreatePolicy", "iam:GetPolicy", "iam:GetPolicyVersion"}
    assert statements["BoundaryPolicy"]["Resource"] == f"arn:aws:iam::*:policy/{BOUNDARY_POLICY}"
    # Still the tightest statement per role family: GitHub roles are never passed, deleting needs no boundary.
    assert "iam:PassRole" not in _actions(statements["GitHubActionsRoles"])
    assert {"iam:DeleteRole", "iam:DeleteRolePolicy"} <= _actions(statements["AppRunnerInstanceRoles"])


def test_boundary_document_caps_roles_to_deployer_resources():
    statements = {s["Sid"]: s for s in BOUNDARY_DOCUMENT["Statement"]}
    for sid, s in statements.items():
        assert s["Effect"] == "Allow" and not _actions(s) & {"*", "iam:*", "s3:*", "ecr:*"}, sid
        for r in _resources(s):
            # The exceptions: a login token, CloudFront's id-named distributions, DynamoDB tables that keep
            # their own names (items only, never CreateTable / DeleteTable).
            assert r == "*" or "deployer" in r or sid == "DynamoDBItems", (sid, r)
    assert _resources(statements["RegistryLogin"]) == {"*"} and _resources(statements["CloudFront"]) == {"*"}
    assert not _actions(statements["DynamoDBItems"]) & {"dynamodb:CreateTable", "dynamodb:DeleteTable"}
    assert _actions(statements["PassAccessRole"]) == {"iam:PassRole"}
    assert "iam:CreateRole" not in {a for s in statements.values() for a in _actions(s)}
    assert statements["Secrets"]["Resource"] == "arn:aws:secretsmanager:*:*:secret:deployer-*"
    assert len(json.dumps(BOUNDARY_DOCUMENT, separators=(",", ":"))) <= 6144
    req = cloud.requirements()["aws"]
    assert req["boundary"] == BOUNDARY_DOCUMENT and req["boundary_name"] == BOUNDARY_POLICY


def test_deploy_passes_the_boundary_to_every_role_and_reports_an_old_copy(client, db, docker, team, aws):  # noqa: F811
    conn = connection(db)
    app = make_app(db, team["project"], "Api", target="aws_app", cloud_connection_id=conn.id)
    first = deploy(db, app)
    assert first.status == "live", first.error
    assert aws.args("ensure_boundary") == [("1",)]  # the connection's account id
    assert aws.args("ensure_access_role") == [("arn:aws:iam::123456789012:policy/deployer-boundary",)]
    assert BOUNDARY_POLICY not in first.log
    aws.returns["ensure_boundary"] = {"arn": "arn:aws:iam::1:policy/deployer-boundary", "current": False}
    second = deploy(db, db.get(App, app.id))
    assert second.status == "live" and f"The IAM policy {BOUNDARY_POLICY} in your AWS account is older" in second.log
    assert "Settings -> Cloud accounts" in second.log


def test_boundary_cannot_be_created_fails_the_deploy_plainly(client, db, docker, team, aws):  # noqa: F811
    conn = connection(db)
    app = make_app(db, team["project"], "Api", target="aws_app", cloud_connection_id=conn.id)
    aws.fail["ensure_boundary"] = "AWS AccessDenied: iam:CreatePolicy"
    dep = deploy(db, app)
    assert dep.status == "failed" and "iam:CreatePolicy" in dep.error
    assert aws.args("ensure_access_role") == [] and aws.args("create_service") == []


def test_saving_the_aws_connection_creates_the_boundary_at_once(client, db, team, aws):  # noqa: F811
    """A copy of the key could otherwise create a wider `deployer-boundary` first and build unbounded roles
    with it, for as long as no app was deployed (a databases-only account never deploys one)."""
    aws.returns["identity"] = {"account": ACCOUNT, "arn": f"arn:aws:iam::{ACCOUNT}:user/deployer"}
    key = {"access_key_id": aws_key_id(), "secret_access_key": aws_secret(), "region": "eu-west-1"}
    body = {"provider": "aws", "name": "AWS", "aws": key}
    resp = client.post("/v1/instance/cloud", json=body, headers=team["owner"])
    assert resp.status_code == 201, resp.text
    assert aws.args("ensure_boundary") == [(ACCOUNT,)]
    # A key whose policy predates G3 still saves and checks: the first deploy reports the missing permission.
    aws.fail["ensure_boundary"] = "AWS AccessDenied: iam:CreatePolicy"
    check = client.post(f"/v1/instance/cloud/{resp.json()['id']}/check", headers=team["owner"])
    assert check.status_code == 200 and check.json()["status"] == "ok"
    assert aws.names().count("ensure_boundary") == 2
