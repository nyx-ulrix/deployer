"""Cloud connections and hosting targets (docs/CLOUD.md phase C1).

A connection is the user's own AWS access key (optionally assuming a role) or Firebase / Google Cloud
service-account key, stored with `encrypt_json` in `cloud_connections`, validated on save, never
returned (only `connection_out`'s non-secret summary), removable any time. The owner creates them;
project admins pick one for an app's `target`.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.crypto import decrypt_json, encrypt_json
from app.errors import ApiError, CloudError, conflict, not_found
from app.models import App, CloudConnection, DataSource
from app.serializers import iso
from app.services import cloud_aws, cloud_gcp

PROVIDERS = ("aws", "firebase")

# Where an app runs (apps.target). `local` is the PC itself (docs/DEPLOYMENTS.md). The texts are shown
# as-is by the dashboard's "Where should this run?" chooser and returned by the MCP tool.
TARGETS: dict[str, dict] = {
    "local": {
        "label": "This PC",
        "provider": None,
        "kind": "any",
        "for": "Any app. Containers on this PC behind Caddy, next to the project's databases.",
        "when_pc_off": "Stops serving while the PC is off or asleep.",
        "cost": "Free (your electricity and internet).",
        "uses_deployer_data": True,
    },
    "aws_static": {
        "label": "AWS - static site (S3 + CloudFront)",
        "provider": "aws",
        "kind": "static",
        "for": "Static sites and single-page apps (React, Vue, Vite, Astro...). Files in a private S3 bucket, "
        "served worldwide over HTTPS by CloudFront.",
        "when_pc_off": "Keeps serving when this PC is off.",
        "cost": "Billed to your AWS account: mostly data transferred out and requests; a small site is often "
        "within the free tier.",
        "uses_deployer_data": False,
    },
    "aws_app": {
        "label": "AWS - full app (App Runner)",
        "provider": "aws",
        "kind": "app",
        "for": "Node, Python and Dockerfile apps (APIs, server-rendered sites). Your container runs on "
        "App Runner with HTTPS and automatic scaling.",
        "when_pc_off": "Keeps serving when this PC is off.",
        "cost": "Billed to your AWS account: per hour the service is provisioned (0.25 vCPU / 0.5 GB), plus "
        "CPU time while it handles requests, plus image storage in ECR. Roughly US$5+/month when idle.",
        "uses_deployer_data": False,
    },
    "firebase_hosting": {
        "label": "Firebase Hosting (static)",
        "provider": "firebase",
        "kind": "static",
        "for": "Static sites and single-page apps. Firebase's global CDN with HTTPS on <site>.web.app; "
        "every deployment also gets a 7-day preview link.",
        "when_pc_off": "Keeps serving when this PC is off.",
        "cost": "Free Spark plan covers 10 GB storage and 360 MB/day transfer; beyond that billed to your "
        "Google account (Blaze plan).",
        "uses_deployer_data": False,
    },
    "firebase_app": {
        "label": "Firebase - full app (Cloud Run)",
        "provider": "firebase",
        "kind": "app",
        "for": "Node, Python and Dockerfile apps. Your container runs on Google Cloud Run (scales to zero "
        "when idle) behind Firebase Hosting, so it gets the <site>.web.app address and custom domains.",
        "when_pc_off": "Keeps serving when this PC is off.",
        "cost": "Needs the Blaze (pay-as-you-go) plan: Cloud Run bills per request and CPU time while "
        "serving (a generous free tier, near zero when idle) plus image storage in Artifact Registry.",
        "uses_deployer_data": False,
    },
}
STATIC_TARGETS = tuple(t for t, v in TARGETS.items() if v["kind"] == "static")
# Targets where "database access" means the project's databases in the same cloud account (docs/CLOUD.md "C2"):
# App Runner -> RDS / DynamoDB on the AWS connection, Cloud Run -> Firestore on the Firebase connection.
DATABASE_TARGETS = ("aws_app", "firebase_app")
CLOUD_ENV_NOTE = (
    "Cloud targets get only the app's own environment variables: no DEPLOYER_URL or DEPLOYER_API_KEY, and "
    "nothing that points at this PC (which may be off). An App Runner app with database access gets "
    "DEPLOYER_DB_<NAME>_* for the project's databases in the same AWS account - pointing at AWS, never at this PC "
    "(DynamoDB tables: their names and region, used through an IAM role that may access only those tables). A "
    "Firebase full app (Cloud Run) with database access gets DEPLOYER_DB_<NAME>_PROJECT / _DATABASE for the "
    "project's Firestore databases (and _URL for its Realtime Databases) in the same Firebase project, reached as "
    "the app's own service account."
)

_AWS_KEY_ID = re.compile(r"^(AKIA|ASIA)[A-Z0-9]{16}$")
_AWS_REGION = re.compile(r"^[a-z]{2}(-gov)?-[a-z]+-\d$")
_ROLE_ARN = re.compile(r"^arn:aws(-[a-z]+)?:iam::\d{12}:role/[\w+=,.@/-]{1,512}$")

# Least privilege for everything cloud_aws.AwsClient does; resources are named deployer-*.
AWS_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "WhoAmI", "Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*"},
        {
            "Sid": "StaticSiteBuckets",
            "Effect": "Allow",
            "Action": [
                "s3:CreateBucket",
                "s3:DeleteBucket",
                "s3:PutBucketPolicy",
                "s3:PutBucketPublicAccessBlock",
                "s3:ListBucket",
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:AbortMultipartUpload",
            ],
            "Resource": ["arn:aws:s3:::deployer-*", "arn:aws:s3:::deployer-*/*"],
        },
        {
            "Sid": "CloudFront",
            "Effect": "Allow",
            "Action": [
                "cloudfront:CreateDistribution",
                "cloudfront:GetDistribution",
                "cloudfront:GetDistributionConfig",
                "cloudfront:UpdateDistribution",
                "cloudfront:DeleteDistribution",
                "cloudfront:CreateInvalidation",
                "cloudfront:CreateOriginAccessControl",
                "cloudfront:GetOriginAccessControl",
                "cloudfront:DeleteOriginAccessControl",
                "cloudfront:CreateFunction",
                "cloudfront:PublishFunction",
                "cloudfront:DescribeFunction",
                "cloudfront:DeleteFunction",
            ],
            "Resource": "*",
        },
        {
            "Sid": "Certificates",
            "Effect": "Allow",
            "Action": ["acm:RequestCertificate", "acm:DescribeCertificate", "acm:DeleteCertificate"],
            "Resource": "*",
        },
        {"Sid": "RegistryLogin", "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
        {
            "Sid": "ContainerRepositories",
            "Effect": "Allow",
            "Action": [
                "ecr:CreateRepository",
                "ecr:DescribeRepositories",
                "ecr:DeleteRepository",
                "ecr:BatchDeleteImage",
                "ecr:BatchCheckLayerAvailability",
                "ecr:InitiateLayerUpload",
                "ecr:UploadLayerPart",
                "ecr:CompleteLayerUpload",
                "ecr:PutImage",
                "ecr:BatchGetImage",
                "ecr:GetDownloadUrlForLayer",
            ],
            "Resource": "arn:aws:ecr:*:*:repository/deployer-*",
        },
        {
            "Sid": "AppRunner",
            "Effect": "Allow",
            "Action": [
                "apprunner:CreateService",
                "apprunner:UpdateService",
                "apprunner:DeleteService",
                "apprunner:DescribeService",
                "apprunner:ListOperations",
                "apprunner:AssociateCustomDomain",
                "apprunner:DisassociateCustomDomain",
                "apprunner:DescribeCustomDomains",
                "apprunner:CreateVpcConnector",
                "apprunner:ListVpcConnectors",
            ],
            "Resource": "*",
        },
        {
            "Sid": "AppRunnerImageAccessRole",
            "Effect": "Allow",
            "Action": ["iam:GetRole", "iam:CreateRole", "iam:AttachRolePolicy", "iam:PassRole"],
            "Resource": f"arn:aws:iam::*:role/{cloud_aws.ACCESS_ROLE}",
        },
        {
            "Sid": "ServiceLinkedRoles",
            "Effect": "Allow",
            "Action": "iam:CreateServiceLinkedRole",
            "Resource": "*",
            "Condition": {
                "StringLike": {
                    "iam:AWSServiceName": [
                        "apprunner.amazonaws.com",
                        "networking.apprunner.amazonaws.com",
                        "rds.amazonaws.com",
                    ]
                }
            },
        },
        # Cloud databases (docs/CLOUD.md "C2"): list RDS / Aurora to connect one, create and delete
        # deployer-* instances (the final snapshot needs CreateDBSnapshot), and the firewall around them.
        {
            "Sid": "DatabasesRead",
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDBInstances",
                "rds:DescribeDBClusters",
                "ec2:DescribeVpcs",
                "ec2:DescribeSubnets",
                "ec2:DescribeSecurityGroups",
            ],
            "Resource": "*",
        },
        {
            "Sid": "Databases",
            "Effect": "Allow",
            "Action": [
                "rds:CreateDBInstance",
                "rds:ModifyDBInstance",
                "rds:DeleteDBInstance",
                "rds:CreateDBSnapshot",
                "rds:AddTagsToResource",
            ],
            "Resource": [
                "arn:aws:rds:*:*:db:deployer-*",
                "arn:aws:rds:*:*:snapshot:deployer-*",
                "arn:aws:rds:*:*:subgrp:default",
                "arn:aws:rds:*:*:pg:default.*",
                "arn:aws:rds:*:*:og:default:*",
            ],
        },
        {
            "Sid": "DatabaseFirewallCreate",
            "Effect": "Allow",
            "Action": "ec2:CreateSecurityGroup",
            "Resource": ["arn:aws:ec2:*:*:vpc/*", "arn:aws:ec2:*:*:security-group/*"],
        },
        {
            # Only while creating a group: tagging an existing one would hand it to the next statement.
            "Sid": "DatabaseFirewallTag",
            "Effect": "Allow",
            "Action": "ec2:CreateTags",
            "Resource": "arn:aws:ec2:*:*:security-group/*",
            "Condition": {"StringEquals": {"ec2:CreateAction": "CreateSecurityGroup"}},
        },
        {
            "Sid": "DatabaseFirewallRules",
            "Effect": "Allow",
            "Action": [
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupIngress",
                "ec2:DeleteSecurityGroup",
            ],
            "Resource": "arn:aws:ec2:*:*:security-group/*",
            "Condition": {"StringEquals": {"aws:ResourceTag/managed-by": "deployer"}},
        },
        # DynamoDB (docs/CLOUD.md "C2-2"): list tables to connect them; read / write items, schema and
        # on-demand backups of any table a source names (connected tables keep their own names); create,
        # change and delete only deployer-* tables.
        # ListTables and ListBackups have no resource-level permissions: AWS only accepts "*" for them.
        {
            "Sid": "DynamoDBList",
            "Effect": "Allow",
            "Action": ["dynamodb:ListTables", "dynamodb:ListBackups"],
            "Resource": "*",
        },
        {
            "Sid": "DynamoDBData",
            "Effect": "Allow",
            "Action": [
                "dynamodb:DescribeTable",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:CreateBackup",
                "dynamodb:DescribeBackup",
                # Point-in-time recovery and restores; the restored copy is always a new deployer-* table.
                "dynamodb:DescribeContinuousBackups",
                "dynamodb:UpdateContinuousBackups",
                "dynamodb:RestoreTableFromBackup",
                "dynamodb:RestoreTableToPointInTime",
            ],
            "Resource": ["arn:aws:dynamodb:*:*:table/*", "arn:aws:dynamodb:*:*:table/*/backup/*"],
        },
        {
            "Sid": "DynamoDBTables",
            "Effect": "Allow",
            "Action": [
                "dynamodb:CreateTable",
                "dynamodb:UpdateTable",
                "dynamodb:DeleteTable",
                "dynamodb:TagResource",
                "dynamodb:BatchWriteItem",  # a restore writes the copied items into the new table
            ],
            "Resource": "arn:aws:dynamodb:*:*:table/deployer-*",
        },
        {
            # The IAM role an App Runner app's code runs as, allowed only its project's tables.
            "Sid": "AppRunnerInstanceRoles",
            "Effect": "Allow",
            "Action": [
                "iam:GetRole",
                "iam:CreateRole",
                "iam:TagRole",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:DeleteRole",
                "iam:PassRole",
            ],
            "Resource": f"arn:aws:iam::*:role/{cloud_aws.INSTANCE_ROLE_PREFIX}*",
        },
        {
            # Apps whose traffic goes through the VPC (they also use an RDS database) reach DynamoDB through
            # a free gateway endpoint; describing is read-only.
            "Sid": "DynamoDBEndpointRead",
            "Effect": "Allow",
            "Action": ["ec2:DescribeVpcEndpoints", "ec2:DescribeRouteTables"],
            "Resource": "*",
        },
        {
            "Sid": "DynamoDBEndpointCreate",
            "Effect": "Allow",
            "Action": "ec2:CreateVpcEndpoint",
            "Resource": ["arn:aws:ec2:*:*:vpc/*", "arn:aws:ec2:*:*:route-table/*", "arn:aws:ec2:*:*:vpc-endpoint/*"],
        },
        {
            "Sid": "DynamoDBEndpointTag",
            "Effect": "Allow",
            "Action": "ec2:CreateTags",
            "Resource": "arn:aws:ec2:*:*:vpc-endpoint/*",
            "Condition": {"StringEquals": {"ec2:CreateAction": "CreateVpcEndpoint"}},
        },
        # App secrets (docs/CLOUD.md "G1"): one deployer-* secret per variable of an App Runner app that keeps
        # them in Secrets Manager; GetSecretValue only to skip rewriting an unchanged value.
        {
            "Sid": "AppSecrets",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:CreateSecret",
                "secretsmanager:GetSecretValue",
                "secretsmanager:PutSecretValue",
                "secretsmanager:DeleteSecret",
                "secretsmanager:TagResource",
            ],
            "Resource": "arn:aws:secretsmanager:*:*:secret:deployer-*",
        },
        # GitHub Actions builds (docs/CLOUD.md "C3"): the account's identity provider for GitHub's OIDC tokens
        # (one, shared) and one deployer-gha-* role per app that only its repository's branch may assume.
        {
            "Sid": "GitHubActionsSignIn",
            "Effect": "Allow",
            "Action": ["iam:CreateOpenIDConnectProvider", "iam:TagOpenIDConnectProvider"],
            "Resource": f"arn:aws:iam::*:oidc-provider/{cloud_aws.GITHUB_OIDC_HOST}",
        },
        {
            "Sid": "GitHubActionsRoles",
            "Effect": "Allow",
            "Action": [
                "iam:GetRole",
                "iam:CreateRole",
                "iam:TagRole",
                "iam:UpdateAssumeRolePolicy",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:DeleteRole",
            ],
            "Resource": f"arn:aws:iam::*:role/{cloud_aws.GITHUB_ROLE_PREFIX}*",
        },
    ],
}
GOOGLE_ROLES = [
    {"role": "roles/firebasehosting.admin", "title": "Firebase Hosting Admin", "why": "sites, versions, releases"},
    {"role": "roles/firebase.viewer", "title": "Firebase Viewer", "why": "check the project on save"},
    {"role": "roles/run.admin", "title": "Cloud Run Admin", "why": "deploy and make the app public"},
    {"role": "roles/artifactregistry.admin", "title": "Artifact Registry Administrator", "why": "image repository"},
    {"role": "roles/iam.serviceAccountUser", "title": "Service Account User", "why": "run the app as its identity"},
    {
        "role": "roles/datastore.user",
        "title": "Cloud Datastore User",
        "why": "browse, edit and query Firestore databases (read and write documents only)",
        "only_for": "firestore",
    },
    {
        "role": "roles/firebasedatabase.admin",
        "title": "Firebase Realtime Database Admin",
        "why": "list and create the project's Realtime Database and read and write its data",
        "only_for": "firebase_rtdb",
    },
    {
        "role": "roles/secretmanager.admin",
        "title": "Secret Manager Admin",
        "why": "create an app's secrets, store new values and let only the app's own account read them",
        "only_for": "cloud_secrets",
    },
    {
        "role": "roles/iam.workloadIdentityPoolAdmin",
        "title": "IAM Workload Identity Pool Admin",
        "why": "let GitHub Actions sign in without a key (one pool, one provider per app)",
        "only_for": "github_actions",
    },
    {
        "role": "roles/iam.serviceAccountAdmin",
        "title": "Service Account Admin",
        "why": "let an app's GitHub Actions workflow act as this deployer account",
        "only_for": "github_actions",
        # Granted on the deployer service account itself (its Permissions tab), not on the whole project.
        "on": "service_account",
    },
]
GOOGLE_APIS = [
    {"api": "firebasehosting.googleapis.com", "title": "Firebase Hosting API"},
    {"api": "firebase.googleapis.com", "title": "Firebase Management API"},
    {"api": "run.googleapis.com", "title": "Cloud Run Admin API", "only_for": "firebase_app"},
    {"api": "artifactregistry.googleapis.com", "title": "Artifact Registry API", "only_for": "firebase_app"},
    {"api": "firestore.googleapis.com", "title": "Cloud Firestore API", "only_for": "firestore"},
    {
        "api": "firebasedatabase.googleapis.com",
        "title": "Firebase Realtime Database Management API",
        "only_for": "firebase_rtdb",
    },
    {"api": "secretmanager.googleapis.com", "title": "Secret Manager API", "only_for": "cloud_secrets"},
    {"api": "iam.googleapis.com", "title": "Identity and Access Management (IAM) API", "only_for": "github_actions"},
    {"api": "sts.googleapis.com", "title": "Security Token Service API", "only_for": "github_actions"},
    {
        "api": "iamcredentials.googleapis.com",
        "title": "IAM Service Account Credentials API",
        "only_for": "github_actions",
    },
]


def requirements() -> dict:
    return {"aws": {"policy": AWS_POLICY}, "firebase": {"roles": GOOGLE_ROLES, "apis": GOOGLE_APIS}}


# --- connections ---------------------------------------------------------------------------------


def config_of(conn: CloudConnection) -> dict:
    return decrypt_json(conn.config_encrypted)


def secrets_of(config: dict) -> list[str]:
    """Values to redact from logs and errors."""
    sa = config.get("service_account") or {}
    return [v for v in (config.get("secret_access_key"), sa.get("private_key")) if v]


def connection_out(conn: CloudConnection, db: Session | None = None) -> dict:
    """Non-secret summary: never the keys."""
    config = config_of(conn)
    out = {
        "id": conn.id,
        "provider": conn.provider,
        "name": conn.name,
        "project_id": conn.project_id,
        "status": conn.status,
        "status_message": conn.status_message,
        "created_at": iso(conn.created_at),
        "updated_at": iso(conn.updated_at),
    }
    if conn.provider == "aws":
        out["account"] = {
            "account_id": config.get("account_id"),
            "region": config.get("region"),
            "role_arn": config.get("role_arn"),
            "access_key_id_last4": str(config.get("access_key_id") or "")[-4:],
        }
    else:
        out["account"] = {
            "project_id": config.get("project_id"),
            "region": config.get("region"),
            "client_email": (config.get("service_account") or {}).get("client_email"),
        }
    if db is not None:
        out["apps_using"] = db.scalar(select(func.count()).select_from(App).where(App.cloud_connection_id == conn.id))
        out["databases_using"] = db.scalar(
            select(func.count()).select_from(DataSource).where(DataSource.cloud_connection_id == conn.id)
        )
    return out


def list_connections(db: Session, project_id: str | None = None) -> list[CloudConnection]:
    """All (project_id None), or the ones a project may use: instance-wide + its own."""
    stmt = select(CloudConnection).order_by(CloudConnection.created_at)
    if project_id is not None:
        stmt = stmt.where(or_(CloudConnection.project_id.is_(None), CloudConnection.project_id == project_id))
    return list(db.scalars(stmt))


def get_connection(db: Session, connection_id: str) -> CloudConnection:
    conn = db.get(CloudConnection, connection_id)
    if conn is None:
        raise not_found("Cloud connection")
    return conn


def usable_connection(db: Session, project_id: str, connection_id: str | None, target: str) -> CloudConnection:
    """The connection an app of `project_id` may deploy `target` with, else 422."""
    provider = TARGETS[target]["provider"]
    conn = db.get(CloudConnection, connection_id) if connection_id else None
    if conn is None or conn.project_id not in (None, project_id):
        raise ApiError(
            422, "validation_error", "Pick a cloud connection for this target", {"field": "cloud_connection_id"}
        )
    if conn.provider != provider:
        raise ApiError(
            422,
            "validation_error",
            f"The {TARGETS[target]['label']} target needs a {provider} connection",
            {"field": "cloud_connection_id"},
        )
    return conn


def _bad(message: str, field: str) -> ApiError:
    return ApiError(422, "validation_error", message, {"field": field})


def normalize_aws(raw: dict) -> dict:
    key_id = str(raw.get("access_key_id") or "").strip()
    secret = str(raw.get("secret_access_key") or "").strip()
    region = str(raw.get("region") or "").strip()
    role_arn = str(raw.get("role_arn") or "").strip() or None
    if not _AWS_KEY_ID.match(key_id):
        raise _bad("That is not an AWS access key ID (20 characters starting with AKIA)", "access_key_id")
    if not re.fullmatch(r"[A-Za-z0-9/+=]{40}", secret):
        raise _bad("That is not an AWS secret access key (40 characters)", "secret_access_key")
    if not _AWS_REGION.match(region):
        raise _bad("That is not an AWS region, e.g. us-east-1", "region")
    if role_arn and not _ROLE_ARN.match(role_arn):
        raise _bad("That is not an IAM role ARN (arn:aws:iam::<account>:role/<name>)", "role_arn")
    return {"access_key_id": key_id, "secret_access_key": secret, "region": region, "role_arn": role_arn}


def normalize_firebase(raw: dict) -> dict:
    text = raw.get("service_account_json")
    try:
        sa = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        sa = None
    if not isinstance(sa, dict) or sa.get("type") != "service_account":
        raise _bad(
            'Paste the whole service-account key file (JSON with "type": "service_account")', "service_account_json"
        )
    if not all(isinstance(sa.get(k), str) and sa.get(k) for k in ("client_email", "private_key")):
        raise _bad("The key file has no client_email / private_key", "service_account_json")
    project_id = str(raw.get("project_id") or sa.get("project_id") or "").strip()
    region = str(raw.get("region") or "us-central1").strip()
    if not cloud_gcp.PROJECT_RE.match(project_id):
        raise _bad("That is not a Firebase / Google Cloud project id", "project_id")
    if not cloud_gcp.REGION_RE.match(region):
        raise _bad("That is not a Google Cloud region, e.g. us-central1", "region")
    # Only what is needed to sign the token request; token_uri and friends are not kept (TOKEN_URL is fixed).
    keep = {k: sa[k] for k in ("type", "project_id", "private_key_id", "private_key", "client_email") if k in sa}
    return {"service_account": keep, "project_id": project_id, "region": region}


def validate(provider: str, config: dict) -> dict:
    """Checks the credentials against the provider; returns the config with what it learned. 422 on failure."""
    try:
        if provider == "aws":
            identity = cloud_aws.client(config).identity()
            return {**config, "account_id": identity["account"], "arn": identity["arn"]}
        gcp = cloud_gcp.client(config)
        gcp.access_token()
        info = gcp.project_info()
        return {**config, "display_name": info.get("displayName")}
    except CloudError as exc:
        raise ApiError(422, "cloud_credentials_invalid", f"The credentials were not accepted: {exc.message}") from None


def create_connection(
    db: Session, *, provider: str, name: str, project_id: str | None, raw: dict, user_id: str
) -> CloudConnection:
    config = normalize_aws(raw) if provider == "aws" else normalize_firebase(raw)
    config = validate(provider, config)
    conn = CloudConnection(
        provider=provider,
        name=name,
        project_id=project_id,
        config_encrypted=encrypt_json(config),
        status="ok",
        created_by_id=user_id,
    )
    db.add(conn)
    db.flush()
    return conn


def check_connection(db: Session, conn: CloudConnection) -> CloudConnection:
    try:
        validate(conn.provider, config_of(conn))
        conn.status, conn.status_message = "ok", None
    except ApiError as exc:
        conn.status, conn.status_message = "error", exc.message
    return conn


def delete_connection(db: Session, conn: CloudConnection) -> None:
    names = list(db.scalars(select(App.name).where(App.cloud_connection_id == conn.id)))
    if names:
        raise conflict(
            "connection_in_use",
            "Move these apps to another target first (their cloud resources are removed then): " + ", ".join(names),
        )
    sources = list(
        db.scalars(
            select(DataSource.name).where(DataSource.cloud_connection_id == conn.id, DataSource.deleted_at.is_(None))
        )
    )
    if sources:
        raise conflict("connection_in_use", "Remove these databases from their projects first: " + ", ".join(sources))
    db.delete(conn)


def targets_out(db: Session, project_id: str) -> list[dict]:
    """Every target with whether this project has a connection for it (MCP `list_cloud_targets`)."""
    providers = {c.provider for c in list_connections(db, project_id) if c.status == "ok"}
    return [
        {"id": t, **meta, "available": meta["provider"] is None or meta["provider"] in providers}
        for t, meta in TARGETS.items()
    ]
