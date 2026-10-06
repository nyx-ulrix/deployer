"""The Deployer AWS permissions as separate managed policies, each comfortably under IAM's size limit."""

import hashlib
import json

from app.services import cloud

# IAM's limit for one managed policy is 6,144 characters, whitespace not counted.
IAM_LIMIT = 6144
HEADROOM = 600

# The single policy before the split into AWS_POLICIES: its statement ids and a fingerprint of their exact
# contents (sorted by Sid, keys sorted, no whitespace).
BEFORE_SPLIT_SIDS = [
    "AppRunner",
    "AppRunnerImageAccessRole",
    "AppRunnerInstanceRoles",
    "AppSecrets",
    "BoundaryPolicy",
    "Certificates",
    "CloudFront",
    "ContainerRepositories",
    "DatabaseFirewallCreate",
    "DatabaseFirewallRules",
    "DatabaseFirewallTag",
    "Databases",
    "DatabasesRead",
    "DynamoDBData",
    "DynamoDBEndpointCreate",
    "DynamoDBEndpointRead",
    "DynamoDBEndpointTag",
    "DynamoDBList",
    "DynamoDBTables",
    "GitHubActionsRoles",
    "GitHubActionsSignIn",
    "RegistryLogin",
    "RolesWithinBoundary",
    "ServiceLinkedRoles",
    "StaticSiteBuckets",
    "WhoAmI",
]
BEFORE_SPLIT_SHA256 = "49a3cd3956814527fde2040f61229f0a746724dfaff6e76b755681b8a8e5fdcf"  # G2 added iam:ListRoleTags
# A statement added after the split: put its Sid here (a changed one updates the fingerprint instead).
ADDED_SINCE_SPLIT: set[str] = {"GitHubActionsRoleList"}  # G2: the orphan sweep lists roles


def _size(document: dict) -> int:
    return len(json.dumps(document, separators=(",", ":")))


def test_every_policy_leaves_room_under_the_iam_limit():
    assert len(cloud.AWS_POLICIES) <= 10  # what one IAM user can have attached
    for p in cloud.AWS_POLICIES:
        assert p["document"]["Version"] == "2012-10-17" and p["name"].startswith("Deployer") and p["for"]
        assert _size(p["document"]) <= IAM_LIMIT - HEADROOM, (
            f"{p['name']} is {_size(p['document'])} characters; put new statements in another policy "
            "(or a new entry in cloud.AWS_POLICIES) and update the Cloud accounts guide"
        )
    assert len({p["name"] for p in cloud.AWS_POLICIES}) == len(cloud.AWS_POLICIES)
    assert cloud.requirements()["aws"]["policies"] == cloud.AWS_POLICIES


def test_split_kept_exactly_the_previous_permissions():
    sids = [s["Sid"] for s in cloud.aws_statements()]
    assert len(sids) == len(set(sids)), "a statement is in two policies"
    before = sorted((s for s in cloud.aws_statements() if s["Sid"] not in ADDED_SINCE_SPLIT), key=lambda s: s["Sid"])
    assert [s["Sid"] for s in before] == BEFORE_SPLIT_SIDS, "new statement? add its Sid to ADDED_SINCE_SPLIT"
    digest = hashlib.sha256(json.dumps(before, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == BEFORE_SPLIT_SHA256, f"a statement changed; if intended, set BEFORE_SPLIT_SHA256 = {digest!r}"


def test_iam_statements_and_the_boundary_condition_stay_together():
    # docs/CLOUD.md "G3": one policy holds every iam:* permission, so the boundary condition is reviewed in one place.
    holders = {
        p["name"]
        for p in cloud.AWS_POLICIES
        for s in p["document"]["Statement"]
        for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
        if a.startswith("iam:")
    }
    assert holders == {"DeployerRoles"}
