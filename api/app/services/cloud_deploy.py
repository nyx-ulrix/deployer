"""Deploying to, tearing down and adding domains on the cloud hosting targets (docs/CLOUD.md).

The `app.deploy` job (services/deployments.py) clones and builds on this PC exactly as for the `local`
target, then hands the image to `go_live`, which publishes it on the app's target:

- `aws_static`: the static preset's output (copied out of the built nginx image) -> S3 under
  `d/<deployment_id>/` -> CloudFront origin path switched to it -> invalidation `/*`;
- `aws_app`: image -> ECR -> App Runner (create once, then UpdateService), waits for the operation;
- `firebase_hosting`: version -> populateFiles/upload -> finalize -> preview channel -> live release;
- `firebase_app`: image -> Artifact Registry -> Cloud Run (create once, then update) -> public ->
  Firebase Hosting release with a `** -> run` rewrite (once).

Every resource id is written to `apps.cloud_state` the moment it exists, so a failed deploy never
creates a second one and teardown knows everything to remove. The deployment's `image_tag` is the
cloud artifact (S3 prefix, image URI or Hosting version), which is what a rollback republishes.

Cloud apps never get DEPLOYER_URL / DEPLOYER_API_KEY or anything pointing at this PC: they must keep
working while it is off. An `aws_app` with database access gets `DEPLOYER_DB_<NAME>_*` for the
project's cloud databases on the same AWS connection (services/cloud_db.py), reached through a VPC
connector - those point at AWS, never at this PC. A `firebase_app` with database access gets the project's
Firestore databases on the same Firebase connection (`DEPLOYER_DB_<NAME>_PROJECT` / `_DATABASE`) and its
Realtime Databases (`_URL` too), reached as the Cloud Run service's own service account.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import mimetypes
import os
import re
import time
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, CloudError, conflict
from app.models import App, CloudConnection, Deployment, Domain, utcnow
from app.services import cloud, cloud_aws, cloud_gcp, cloud_secrets, github_actions, jobs
from app.services import cloudflare as cf
from app.services.instance_settings import get_value

log = logging.getLogger(__name__)

POLL_S = 10.0  # tests set 0
ROLLOUT_TIMEOUT_S = 25 * 60
DOMAIN_TIMEOUT_S = 30 * 60
KEEP_ARTIFACTS = 5
SITE_ROOT = "/usr/share/nginx/html"  # where the static preset's image keeps the build output
MAX_FILES = 20000
POPULATE_BATCH = 1000
AR_REPOSITORY = "deployer"  # one Artifact Registry repository per Google project, one package per app
# Names the platforms set themselves and refuse in a service's environment.
RESERVED_ENV = {"PORT", "K_SERVICE", "K_REVISION", "K_CONFIGURATION"}
_HASHED = re.compile(r"[.-][A-Za-z0-9_-]{8,}\.(js|mjs|css|woff2?|ttf|otf|png|jpe?g|gif|svg|webp|avif|ico|map|wasm)$")
HOSTING_CONFIG = {
    "rewrites": [{"glob": "**", "path": "/index.html"}],
    "headers": [{"glob": "**/*.html", "headers": {"Cache-Control": "no-cache"}}],
}


# --- names & state -------------------------------------------------------------------------------


def resource_name(app: App) -> str:
    """`deployer-<slug>-<8 chars of id>`: S3/ECR/App Runner/CloudFront/Cloud Run-safe, <= 40 chars."""
    return f"deployer-{app.slug[:22].rstrip('-')}-{app.id[:8]}"


def instance_role_name(app: App) -> str:
    """`deployer-app-<slug>-<id8>`: the App Runner instance role (IAM role names are <= 64 chars)."""
    return cloud_aws.INSTANCE_ROLE_PREFIX + resource_name(app).removeprefix("deployer-")


def site_id(app: App) -> str:
    """Firebase Hosting site id (globally unique, <= 30 chars)."""
    return f"{app.slug[:21].rstrip('-')}-{app.id[:8]}"


def save_state(factory: jobs.SessionFactory, app_id: str, values: dict) -> None:
    """Merges `values` into the app's cloud_state (other keys, e.g. GitHub Actions' "github", are kept)."""
    with factory() as db:
        row = db.get(App, app_id, with_for_update=True)
        if row is not None:
            row.cloud_state = {**(row.cloud_state or {}), **values}
            db.commit()


def cloud_env(app: App, databases: list[dict] | None = None) -> tuple[dict[str, str], list[str]]:
    """(the app's own variables minus names the platform reserves, the dropped names). `databases`
    (cloud_db.app_databases) add their `DEPLOYER_DB_<NAME>_*` first, so the app's own variables win."""
    from app.services.deployments import env_of, source_env

    env, dropped = {}, []
    for d in databases or []:
        env.update(source_env(d["name"], d["kind"], d["engine"], d["config"], d["database_name"]))
    for key, value in env_of(app).items():
        if key in RESERVED_ENV or key.upper().startswith("AWSAPPRUNNER"):
            dropped.append(key)
        else:
            env[key] = value
    return env, dropped


def resources(target: str, state: dict | None) -> list[str]:
    """Plain-language list of what Deployer created (the delete / switch confirm dialogs show it)."""
    s = state or {}
    out = []
    if target == "aws_static":
        if s.get("distribution_id"):
            out.append(f"CloudFront distribution {s['distribution_id']} ({s.get('distribution_domain')})")
        if s.get("function_name"):
            out.append(f"CloudFront function {s['function_name']}")
        if s.get("oac_id"):
            out.append(f"CloudFront origin access control {s['oac_id']}")
        if s.get("bucket"):
            out.append(f"S3 bucket {s['bucket']} and every file in it")
        out += [f"ACM certificate for {host}" for host in (s.get("certificates") or {})]
    elif target == "aws_app":
        if s.get("service_arn"):
            out.append(f"App Runner service {s.get('service_name')} ({s['service_arn']})")
        if s.get("ecr_repository"):
            out.append(f"ECR repository {s['ecr_repository']} and its images")
        if s.get("instance_role"):
            out.append(f"IAM role {s['instance_role']} (what the app may use)")
        if s.get("nat_vpc"):
            out.append(
                f"NAT gateway with its public IP address, private subnets and route table in {s['nat_vpc']} (shared "
                "with the other apps of this account that reach the internet from that VPC: removed when the last "
                "one stops using it)"
            )
    elif target in ("firebase_hosting", "firebase_app"):
        if s.get("run_service"):
            out.append(f"Cloud Run service {s['run_service']}")
        if s.get("ar_package"):
            out.append(f"Artifact Registry images {AR_REPOSITORY}/{s['ar_package']}")
        if s.get("site"):
            out.append(f"Firebase Hosting site {s['site']} (all versions, preview channels and domains)")
    provider = cloud.TARGETS[target]["provider"] if target in cloud.TARGETS else None
    return out + (cloud_secrets.resources(provider, s) if provider else []) + github_actions.resources(s.get("github"))


def cloud_url(app: App) -> str | None:
    state = app.cloud_state or {}
    if app.target == "aws_static" and state.get("distribution_domain"):
        return f"https://{state['distribution_domain']}"
    if app.target == "aws_app":
        return state.get("service_url")
    if app.target in ("firebase_hosting", "firebase_app") and state.get("site") and state.get("released"):
        return f"https://{state['site']}.web.app"
    return None


def _connection(factory: jobs.SessionFactory, app: App) -> tuple[str, dict]:
    with factory() as db:
        conn = db.get(CloudConnection, app.cloud_connection_id) if app.cloud_connection_id else None
        if conn is None:
            raise jobs.JobError("The app's cloud connection was removed; pick another one in the app's settings")
        return conn.provider, cloud.config_of(conn)


# --- static files --------------------------------------------------------------------------------


def site_files(root: str) -> list[tuple[str, str]]:
    """(relative path with /, absolute path) of the regular files under `root`. Symlinks are skipped:
    a build could otherwise point one at the worker's own files and have them uploaded."""
    root = os.path.realpath(root)
    out: list[tuple[str, str]] = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(directory, d))]
        for name in files:
            path = os.path.join(directory, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            real = os.path.realpath(path)
            if not real.startswith(root + os.sep):
                continue
            out.append((os.path.relpath(path, root).replace(os.sep, "/"), path))
            if len(out) > MAX_FILES:
                raise jobs.JobError(f"The build output has more than {MAX_FILES} files")
    if not any(rel == "index.html" for rel, _ in out):
        raise jobs.JobError("The build output has no index.html (check output_dir)")
    return sorted(out)


# The web's own types first: `mimetypes` also reads the OS registry / mime.types, which differ between
# PCs (Windows can map .css or .js to something a browser refuses for a module script or stylesheet).
_WEB_TYPES = {
    ".html": "text/html",
    ".htm": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".webmanifest": "application/manifest+json",
}


def content_type(rel: str) -> str:
    ext = os.path.splitext(rel)[1].lower()
    return _WEB_TYPES.get(ext) or mimetypes.guess_type(rel)[0] or "application/octet-stream"


def cache_control(rel: str) -> str:
    """HTML revalidates every time; fingerprinted assets are immutable; everything else an hour."""
    if rel.endswith((".html", ".htm")) or rel == "index.html":
        return "no-cache"
    if _HASHED.search(rel):
        return "public, max-age=31536000, immutable"
    return "public, max-age=3600"


def _export(cli, tag: str, workdir: str, log_) -> list[tuple[str, str]]:
    dest = os.path.join(workdir, "site")
    os.makedirs(dest, exist_ok=True)
    log_.write(f"Copying the build output out of {tag}")
    cli.export_dir(tag, SITE_ROOT, dest)
    files = site_files(dest)
    log_.write(f"{len(files)} files")
    return files


# --- deploy --------------------------------------------------------------------------------------


class Publish:
    """One deployment's publish step; `artifact` / `url` are the results."""

    def __init__(self, ctx: jobs.JobContext, cli, app: App, dep: Deployment, tag: str, workdir: str, log_, secrets):
        self.ctx, self.cli, self.app, self.dep, self.tag, self.workdir = ctx, cli, app, dep, tag, workdir
        self.log, self.secrets = log_, secrets
        # A rollback, or an environment change (trigger `env`, docs/CLOUD.md "G1"): the cloud artifact is republished.
        self.reuse = dep.trigger in ("rollback", "env") and tag == dep.image_tag and not tag.startswith("deployer-app/")
        self.state = dict(app.cloud_state or {})
        self.provider, self.config = _connection(ctx.session_factory, app)
        secrets.extend(cloud.secrets_of(self.config))

    def save(self, **values) -> None:
        self.state.update(values)
        save_state(self.ctx.session_factory, self.app.id, values)

    def push(self, remote: str, registry: tuple[str, str, str]) -> None:
        host, user, password = registry
        self.secrets.append(password)
        self.log.step(f"Pushing {remote}")
        config_dir = os.path.join(self.workdir, "docker-config")
        os.makedirs(config_dir, exist_ok=True)
        self.cli.push(
            self.tag,
            remote,
            registry=host,
            username=user,
            password=password,
            config_dir=config_dir,
            on_line=self.log.write,
        )

    def wait(self, what: str, poll) -> None:
        """Polls `poll() -> (done, status)` until done, logging status changes (App Runner / Cloud Run)."""
        started, last = time.monotonic(), None
        while True:
            done, status = poll()
            if status != last:
                self.log.write(f"{what}: {status} ({int(time.monotonic() - started)} s)")
                last = status
            if done:
                return
            if time.monotonic() - started > ROLLOUT_TIMEOUT_S:
                raise jobs.JobError(f"{what} did not finish within {ROLLOUT_TIMEOUT_S // 60} minutes")
            time.sleep(POLL_S)

    # --- targets ---------------------------------------------------------------------------------

    def aws_static(self) -> tuple[str, str]:
        aws = cloud_aws.client(self.config)
        name = resource_name(self.app)
        prefix = self.tag if self.reuse else f"d/{self.dep.id}"
        if not self.state.get("bucket"):
            self.log.step(f"Creating the private S3 bucket {name}")
            aws.create_bucket(name)
            self.save(bucket=name)
        bucket = self.state["bucket"]
        if not self.reuse:
            files = _export(self.cli, self.tag, self.workdir, self.log)
            self.ctx.progress(0.75, "Uploading", force=True)
            self.log.step(f"Uploading {len(files)} files to s3://{bucket}/{prefix}/")
            for rel, path in files:
                aws.upload_file(bucket, f"{prefix}/{rel}", path, content_type(rel), cache_control(rel))
        if not self.state.get("oac_id"):
            self.save(oac_id=aws.create_oac(name))
        if not self.state.get("function_arn"):
            self.save(function_name=name, function_arn=aws.create_index_function(name))
        self.ctx.progress(0.85, "Rolling out", force=True)
        if not self.state.get("distribution_id"):
            self.log.step("Creating the CloudFront distribution")
            dist = aws.create_distribution(
                bucket, f"/{prefix}", self.state["oac_id"], self.state["function_arn"], f"Deployer app {self.app.name}"
            )
            self.save(distribution_id=dist["id"], distribution_domain=dist["domain"], distribution_arn=dist["arn"])
            self.log.write("CloudFront is rolling the distribution out worldwide: the URL answers within ~15 minutes")
        else:
            self.log.step(f"Pointing CloudFront at {prefix}/ and invalidating /*")
            aws.set_origin_path(self.state["distribution_id"], f"/{prefix}")
            aws.invalidate(self.state["distribution_id"])
        if not self.state.get("bucket_policy"):
            aws.allow_distribution(bucket, self.state["distribution_arn"])
            self.save(bucket_policy=True)
        return prefix, f"https://{self.state['distribution_domain']}"

    def aws_app(self) -> tuple[str, str]:
        from app.services.deployments import internal_port

        aws = cloud_aws.client(self.config)
        name = resource_name(self.app)
        if self.reuse:
            image = self.tag
        else:
            if not self.state.get("ecr_uri"):
                self.log.step(f"Creating the ECR repository {name}")
                self.save(ecr_repository=name, ecr_uri=aws.ensure_repository(name))
            image = f"{self.state['ecr_uri']}:{self.dep.id}"
            self.ctx.progress(0.75, "Pushing", force=True)
            self.push(image, aws.registry_login())
        databases = self.databases()
        env, dropped = cloud_env(self.app, databases)
        if dropped:
            self.log.write("Not sent (set by App Runner itself): " + ", ".join(sorted(dropped)))
        self.log.write("Environment: " + (", ".join(sorted(env)) or "(none)") + " - nothing that points at this PC")
        env, secret_arns, stale = cloud_secrets.sync(self, aws, env, databases)
        connector = self.connect_databases(aws, databases)
        boundary = self.boundary(aws)
        instance_role = self.instance_role(aws, databases, list(secret_arns.values()), boundary)
        extra = {"instance_role_arn": instance_role} if instance_role else {}
        if secret_arns:
            extra["secret_arns"] = secret_arns
        # Every deploy, not once: a role made before the boundary existed gets it here.
        self.save(access_role_arn=aws.ensure_access_role(boundary))
        port = internal_port(self.app)
        self.ctx.progress(0.85, "Rolling out", force=True)
        role = self.state["access_role_arn"]
        if not self.state.get("service_arn"):
            self.log.step(f"Creating the App Runner service {name}")
            svc = aws.create_service(name, image, port, env, role, connector, **extra)
            self.save(service_name=name, service_arn=svc["arn"], service_url=svc["url"])
            operation = svc["operation_id"]
        else:
            self.log.step("Updating the App Runner service to the new image")
            operation = aws.update_service(self.state["service_arn"], image, port, env, role, connector, **extra)

        def poll() -> tuple[bool, str]:
            status = aws.operation(self.state["service_arn"], operation)
            if status in ("FAILED", "ROLLBACK_SUCCEEDED", "ROLLBACK_FAILED"):
                raise jobs.JobError(
                    f"App Runner could not start this version ({status}); the previous version keeps serving. "
                    "See the service's application logs in the AWS console (App Runner -> Logs)."
                )
            return status == "SUCCEEDED", status

        self.wait("App Runner", poll)
        cloud_secrets.cleanup(self, aws, stale)
        if self.state.get("nat_vpc") and self.state["nat_vpc"] != self.nat_vpc:
            self.release_nat(self.state["nat_vpc"])  # the service no longer goes through it
        return image, self.state["service_url"]

    def databases(self) -> list[dict]:
        """The project's cloud databases this app gets (docs/CLOUD.md "C2"), logged by name."""
        from app.services import cloud_db

        with self.ctx.session_factory() as db:
            databases, notes = cloud_db.app_databases(db, db.get(App, self.app.id))
        for note in notes:
            self.log.write(note)
        for d in databases:
            self.secrets.append(d["config"].get("password") or "")
        if databases:
            self.log.write("Databases (in your cloud account): " + ", ".join(d["name"] for d in databases))
        return databases

    def boundary(self, aws) -> str:
        """docs/CLOUD.md "G3": the ARN of the account's `deployer-boundary` policy, which caps every role
        below; an account whose copy is older than this Deployer version is told so in the build log."""
        account = self.config.get("account_id") or aws.identity()["account"]
        boundary = aws.ensure_boundary(account)
        if not boundary["current"]:
            self.log.write(
                f"The IAM policy {cloud_aws.BOUNDARY_POLICY} in your AWS account is older than this version of "
                "Deployer expects: paste the current one over it (Settings -> Cloud accounts), or apps and GitHub "
                "Actions may be refused something they need"
            )
        return boundary["arn"]

    def instance_role(self, aws, databases: list[dict], secret_arns: list[str], boundary_arn: str) -> str | None:
        """docs/CLOUD.md "C2-2", "G1", "G3": the IAM role the app's code runs as (within the boundary), allowed
        to use exactly the project's DynamoDB tables and to read exactly its own secrets (created on first use,
        emptied when the app has neither). None: no role needed."""
        account, region = self.config.get("account_id") or "*", self.config.get("region")
        arns = [
            f"arn:aws:dynamodb:{region}:{account}:table/{t}"
            for d in databases
            if d["engine"] == "dynamodb"
            for t in d["config"].get("tables") or []
        ]
        if not arns and not secret_arns and not self.state.get("instance_role"):
            return None
        name = instance_role_name(self.app)
        statements = []
        if secret_arns:
            self.log.write(f"Letting the app read its secrets (IAM role {name})")
            statements.append({"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": secret_arns})
        if arns:
            self.log.step(f"Letting the app use its DynamoDB tables (IAM role {name})")
            actions = [
                "dynamodb:GetItem",
                "dynamodb:BatchGetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:BatchWriteItem",
                "dynamodb:ConditionCheckItem",
                "dynamodb:DescribeTable",
            ]
            resources = arns + [f"{a}/index/*" for a in arns]
            statements.append({"Effect": "Allow", "Action": actions, "Resource": resources})
        policy = {"Version": "2012-10-17", "Statement": statements} if statements else None
        arn = aws.ensure_instance_role(name, policy, boundary_arn)
        self.save(instance_role=name, instance_role_arn=arn)
        return arn

    nat_vpc: str | None = None  # the VPC whose NAT gateway this deploy points the service at

    def connect_databases(self, aws, databases: list[dict]) -> str | None:
        """The VPC connector the service reaches its databases through (None: App Runner's default
        egress); databases Deployer created let the connector's security group in. With internet access
        (docs/CLOUD.md "C2-6") the connector is the one on the private subnets behind the NAT gateway."""
        vpcs = [d["state"].get("vpc_id") for d in databases if d["state"].get("vpc_id")]
        if not vpcs:
            if self.state.get("internet_access"):
                self.log.write("No database in a VPC: the app keeps App Runner's own internet access (no NAT gateway)")
            return None
        vpc = vpcs[0]
        self.log.step(f"Connecting the app to the databases' network ({vpc})")
        connector = aws.ensure_vpc_connector(vpc)
        if self.state.get("internet_access"):
            connector = {**connector, "arn": self.nat_connector(aws, vpc)}
        for d in databases:
            s = d["state"]
            if d["engine"] == "dynamodb":
                continue  # no VPC: reached through the gateway endpoint below
            if s.get("vpc_id") != vpc:
                self.log.write(
                    f"Database '{d['name']}' is in another VPC ({s.get('vpc_id')}): not reachable from this app"
                )
            elif s.get("created") and s.get("group_id"):
                aws.allow_ingress(s["group_id"], int(d["config"]["port"]), source_group=connector["group_id"])
            else:
                self.log.write(
                    f"Database '{d['name']}' was not created by Deployer, so its firewall is yours: allow port "
                    f"{d['config']['port']} from security group {connector['group_id']} in it"
                )
        if any(d["engine"] == "dynamodb" for d in databases):
            self.log.write(f"Reaching DynamoDB from the VPC through a gateway endpoint (free) in {vpc}")
            aws.ensure_dynamodb_endpoint(vpc)
        if not self.nat_vpc:
            self.log.write(
                "Outgoing traffic of this app now goes through the VPC, which has no internet route: turn on 'Let "
                "this app reach the internet too' in its settings if it also calls other internet services"
            )
        self.save(vpc_connector_arn=connector["arn"])
        return connector["arn"]

    def nat_connector(self, aws, vpc: str) -> str:
        """docs/CLOUD.md "C2-6": the NAT gateway of `vpc` (created once, shared, found by tag) and the VPC
        connector on its private subnets. `nat_vpc` is recorded first, so a deploy that fails halfway still
        counts as a user of the NAT gateway and the app's teardown removes it when it is the last one."""
        self.log.step(f"Letting the app reach the internet through a NAT gateway in {vpc}")
        self.save(nat_vpc=vpc)
        self.nat_vpc = vpc
        nat = aws.ensure_nat_network(vpc)
        self.log.write(f"Private subnets {', '.join(nat['subnet_ids'])}; NAT gateway {nat['nat_id']}")

        def poll() -> tuple[bool, str]:
            state, message = aws.nat_gateway_state(nat["nat_id"])
            if state in ("failed", "deleting", "deleted"):
                raise jobs.JobError(f"AWS could not create the NAT gateway ({state}): {message or 'no reason given'}")
            return state == "available", state

        self.wait("NAT gateway", poll)
        self.log.write(f"The app's outgoing internet traffic leaves through {nat['public_ip'] or 'the NAT gateway'}")
        return aws.ensure_vpc_connector(vpc, nat["subnet_ids"])["arn"]

    def release_nat(self, vpc: str) -> None:
        """The service left the NAT gateway's subnets: forget it, and when no other app of this account uses
        it, queue its removal (the NAT gateway is billed by the hour)."""
        self.save(nat_vpc=None)
        with self.ctx.session_factory() as db:
            if nat_users(db, vpc):
                self.log.write(f"The NAT gateway in {vpc} stays: other apps of this account still use it")
                return
            job = jobs.enqueue(
                db,
                type="app.cloud_teardown",
                params={
                    "app_id": self.app.id,
                    "name": self.app.name,
                    "target": "aws_app",
                    "connection_id": self.app.cloud_connection_id,
                    "state": {"nat_vpc": vpc},
                    "domains": [],
                },
                project_id=self.app.project_id,
            )
            db.commit()
        jobs.dispatch(job.id)
        self.log.write(f"No app uses the NAT gateway in {vpc} any more: removing it (job {job.id})")

    def firebase_identity(self, gcp, databases: list[dict]) -> None:
        """docs/CLOUD.md "C2-3", "C2-4": the service runs as the project's default compute service account, which
        reaches Firestore only with Cloud Datastore User and a Realtime Database only with Firebase Realtime
        Database Admin (Deployer may not grant roles itself): say which roles to give which account."""
        try:
            number = gcp.project_info().get("projectNumber")
        except CloudError:
            number = None
        account = f"{number}-compute@developer.gserviceaccount.com" if number else "the default compute service account"
        roles = {
            "firestore": "Firestore: Cloud Datastore User",
            "firebase_rtdb": "Realtime Database: Firebase Realtime Database Admin",
        }
        needed = sorted({roles[d["engine"]] for d in databases if d["engine"] in roles})
        self.log.write(
            f"The app reaches its databases as {account}: it needs the role(s) {'; '.join(needed)} (Google Cloud "
            "console -> IAM -> Grant access), unless it already has Editor"
        )

    def allow_secrets(self, gcp, secrets: dict[str, str]) -> None:
        """docs/CLOUD.md "G1": the service runs as the project's default compute service account, which may read
        exactly these secrets (a binding on each secret, not on the project)."""
        number = str(gcp.project_info().get("projectNumber") or "")
        if not number.isdigit():
            raise jobs.JobError("Firebase did not say the project's number, needed to let the app read its secrets")
        member = f"serviceAccount:{number}-compute@developer.gserviceaccount.com"
        self.log.write(f"Letting {member.removeprefix('serviceAccount:')} read the app's secrets (and nothing else)")
        for name in sorted(secrets.values()):
            gcp.allow_secret(name, member)

    def _hosting_site(self, gcp) -> str:
        if not self.state.get("site"):
            site = site_id(self.app)
            self.log.step(f"Creating the Firebase Hosting site {site}")
            gcp.create_site(site)
            self.save(site=site)
        return self.state["site"]

    def firebase_hosting(self) -> tuple[str, str]:
        gcp = cloud_gcp.client(self.config)
        site = self._hosting_site(gcp)
        if self.reuse:
            version = self.tag
        else:
            files = _export(self.cli, self.tag, self.workdir, self.log)
            self.ctx.progress(0.75, "Uploading", force=True)
            version = gcp.create_version(site, HOSTING_CONFIG)
            self.log.step(f"Uploading {len(files)} files to {version}")
            hashes: dict[str, str] = {}
            by_hash: dict[str, str] = {}
            for rel, path in files:
                with open(path, "rb") as fh:
                    digest = hashlib.sha256(gzip.compress(fh.read(), mtime=0)).hexdigest()
                hashes["/" + rel] = digest
                by_hash[digest] = path
            items = list(hashes.items())
            uploaded = 0
            for start in range(0, len(items), POPULATE_BATCH):
                upload_url, required = gcp.populate_files(version, dict(items[start : start + POPULATE_BATCH]))
                for digest in required:
                    with open(by_hash[digest], "rb") as fh:
                        gcp.upload_file(upload_url, digest, gzip.compress(fh.read(), mtime=0))
                    uploaded += 1
            self.log.write(f"{uploaded} new files uploaded ({len(files) - uploaded} unchanged)")
            gcp.finalize_version(version)
            self.ctx.progress(0.85, "Releasing", force=True)
            channel = f"d-{self.dep.id[:8]}"
            preview = gcp.create_channel(site, channel)
            gcp.release(site, version, channel)
            self.log.write(f"Preview (7 days): {preview}")
        self.log.step("Releasing to live")
        gcp.release(site, version)
        self.save(released=True)
        return version, f"https://{site}.web.app"

    def firebase_app(self) -> tuple[str, str]:
        from app.services.deployments import internal_port

        gcp = cloud_gcp.client(self.config)
        package = f"{self.app.slug[:30].rstrip('-')}-{self.app.id[:8]}"
        if self.reuse:
            image = self.tag
        else:
            if not self.state.get("registry"):
                self.log.step(f"Preparing the Artifact Registry repository {AR_REPOSITORY}")
                self.save(registry=gcp.ensure_repository(AR_REPOSITORY), ar_package=package)
            image = f"{self.state['registry']}/{package}:{self.dep.id}"
            self.ctx.progress(0.75, "Pushing", force=True)
            self.push(image, gcp.docker_login())
        databases = self.databases()
        env, dropped = cloud_env(self.app, databases)
        if databases:
            self.firebase_identity(gcp, databases)
        if dropped:
            self.log.write("Not sent (set by Cloud Run itself): " + ", ".join(sorted(dropped)))
        self.log.write("Environment: " + (", ".join(sorted(env)) or "(none)") + " - nothing from Deployer itself")
        env, secrets, stale = cloud_secrets.sync(self, gcp, env, databases)
        if secrets:
            self.allow_secrets(gcp, secrets)
        port = internal_port(self.app)
        name = resource_name(self.app)
        self.ctx.progress(0.85, "Rolling out", force=True)
        extra = {"secrets": secrets} if secrets else {}
        if not self.state.get("run_service"):
            self.log.step(f"Creating the Cloud Run service {name} in {gcp.region}")
            operation = gcp.create_service(name, image, port, env, **extra)
            self.save(run_service=name, run_region=gcp.region)
        else:
            self.log.step("Deploying the new image to Cloud Run")
            operation = gcp.update_service(self.state["run_service"], image, port, env, **extra)

        def poll() -> tuple[bool, str]:
            op = gcp.operation(cloud_gcp.RUN, operation)
            if op["error"]:
                raise jobs.JobError(f"Cloud Run could not start this version: {op['error']}")
            return op["done"], "done" if op["done"] else "rolling out"

        self.wait("Cloud Run", poll)
        cloud_secrets.cleanup(self, gcp, stale)
        if not self.state.get("run_public"):
            self.log.write("Allowing public (unauthenticated) access to the service")
            gcp.make_public(self.state["run_service"])
            self.save(run_public=True)
        site = self._hosting_site(gcp)
        if not self.state.get("released"):
            self.log.step(f"Routing {site}.web.app to the Cloud Run service")
            rewrite = {"glob": "**", "run": {"serviceId": self.state["run_service"], "region": gcp.region}}
            version = gcp.create_version(site, {"rewrites": [rewrite]})
            gcp.finalize_version(version)
            gcp.release(site, version)
            self.save(released=True)
        return image, f"https://{site}.web.app"


def go_live(ctx: jobs.JobContext, cli, app: App, dep: Deployment, tag: str, workdir: str, log_, secrets) -> None:
    """Publishes `tag` (a local image, or the cloud artifact on a rollback) on the app's target and
    makes the deployment live. Raises (JobError / CloudError) on failure: the previous one stays live."""
    factory = ctx.session_factory
    publish = Publish(ctx, cli, app, dep, tag, workdir, log_, secrets)
    with factory() as db:
        row = db.get(Deployment, dep.id)
        row.status = "deploying"
        db.commit()
    log_.step(f"Publishing to {cloud.TARGETS[app.target]['label']}")
    log_.write(cloud.CLOUD_ENV_NOTE)
    try:
        artifact, url = getattr(publish, app.target)()
    except CloudError as exc:
        raise jobs.JobError(exc.message) from None
    ctx.progress(0.95, "Cleaning up", force=True)
    with factory() as db:
        app_row = db.get(App, app.id)
        dep_row = db.get(Deployment, dep.id)
        previous = db.get(Deployment, app_row.live_deployment_id) if app_row.live_deployment_id else None
        dep_row.status, dep_row.finished_at = "live", utcnow()
        dep_row.image_tag, dep_row.target_url = artifact, url
        app_row.live_deployment_id = dep_row.id
        if previous is not None and previous.id != dep_row.id:
            previous.status = "superseded"
        db.commit()
    log_.write(f"Live at {url}")
    try:
        with factory() as db:
            prune(db, db.get(App, app.id), publish, log_)
            db.commit()
    except CloudError as exc:  # the deployment is live; old artifacts are retried next time
        log_.write(f"Could not remove old versions: {exc.message}")


def prune(db: Session, app: App, publish: Publish, log_) -> None:
    """Keeps the artifacts of the newest KEEP_ARTIFACTS deployments (rollback targets); older S3
    prefixes / ECR images are deleted. Hosting versions and Artifact Registry images are left to the
    providers' own retention (ponytail: delete them too if storage costs show up)."""
    deps = list(
        db.scalars(
            select(Deployment)
            .where(Deployment.app_id == app.id, Deployment.image_tag.is_not(None))
            .order_by(Deployment.created_at.desc())
        )
    )
    keep = {d.image_tag for d in deps[:KEEP_ARTIFACTS]}
    # A failed publish leaves the local build tag (already removed from this PC): nothing in the cloud.
    old = [d for d in deps[KEEP_ARTIFACTS:] if d.image_tag not in keep and not d.image_tag.startswith("deployer-app/")]
    state = app.cloud_state or {}
    if app.target == "aws_static" and old:
        aws = cloud_aws.client(publish.config)
        for d in old:
            log_.write(f"Removing old version {d.image_tag}/")
            aws.delete_prefix(state["bucket"], d.image_tag + "/")
    elif app.target == "aws_app" and old:
        tags = [d.image_tag.rsplit(":", 1)[-1] for d in old]
        log_.write(f"Removing {len(tags)} old image(s) from ECR")
        cloud_aws.client(publish.config).delete_images(state["ecr_repository"], tags)
    for d in deps[KEEP_ARTIFACTS:]:
        d.image_tag = None


@jobs.job_handler("app.cloud_prune")
def _job_prune(ctx: jobs.JobContext) -> dict:
    """After a GitHub Actions deployment (docs/CLOUD.md "C3"): old artifacts go, like after a PC deploy."""
    lines: list[str] = []
    with ctx.session_factory() as db:
        app = db.get(App, str(ctx.params["app_id"]))
        if app is None or app.target == "local":
            return {"skipped": "app missing"}
        _, config = _connection(ctx.session_factory, app)
        try:
            prune(db, app, SimpleNamespace(config=config), SimpleNamespace(write=lines.append))
        except CloudError as exc:
            raise jobs.JobError(f"Could not remove old versions: {exc.message}") from None
        db.commit()
    return {"log": lines}


# --- teardown ------------------------------------------------------------------------------------


def nat_users(db: Session, vpc: str) -> int:
    """How many App Runner apps go through the NAT gateway of `vpc` (their `cloud_state.nat_vpc`; VPC ids are
    unique, so any connection to that account counts): the NAT gateway is shared and removed with its last
    user. Counted when the teardown runs, after the leaving app cleared its `nat_vpc` or its row is gone - so
    apps deleted together (a project delete) still remove it, and an app that started using it since keeps it."""
    rows = db.scalars(select(App).where(App.target == "aws_app"))
    return sum(1 for a in rows if (a.cloud_state or {}).get("nat_vpc") == vpc)


def enqueue_teardown(db: Session, app: App, user_id: str | None) -> str | None:
    """Queues `app.cloud_teardown` for everything the app's target created (and its cloud domains'
    Cloudflare records). Returns the job id, None when there is nothing to remove. Caller commits."""
    state = dict(app.cloud_state or {})
    domains = [
        {"hostname": d.hostname, "zone_id": d.zone_id, "dns_records": d.dns_records or []}
        for d in db.scalars(select(Domain).where(Domain.app_id == app.id, Domain.target_type == "cloud_app"))
    ]
    state.pop("internet_access", None)  # a switch, not a resource
    if app.target == "local" or (not state and not domains):
        return None
    job = jobs.enqueue(
        db,
        type="app.cloud_teardown",
        params={
            "app_id": app.id,
            "name": app.name,
            "slug": app.slug,
            "target": app.target,
            "connection_id": app.cloud_connection_id,
            "state": state,
            "domains": domains,
            # docs/CLOUD.md "C3": a GitHub Actions setup still running is stopped and waited for, so it can't
            # create a role / provider after the teardown looked.
            "setup_job_id": github_actions.cancel_setup(db, app.id),
        },
        project_id=app.project_id,
        created_by_id=user_id,
    )
    return job.id


def _delete_cf_records(db: Session, records: list[dict]) -> list[str]:
    """Deletes the Cloudflare records Deployer created; returns failures."""
    token = get_value(db, "cloudflare_api_token")
    created = [r for r in records if r.get("cf_id") and r.get("zone_id")]
    if not created:
        return []
    if not token:
        return [f"Cloudflare record {r['name']}: Cloudflare is no longer linked" for r in created]
    failures = []
    with cf.CloudflareClient(token) as client:
        for r in created:
            try:
                client.delete_dns_record(r["zone_id"], r["cf_id"])
            except cf.CloudflareError as exc:
                if not exc.is_not_found:
                    failures.append(f"Cloudflare record {r['type']} {r['name']}: {exc.message}")
    return failures


def teardown_steps(
    target: str,
    config: dict,
    state: dict,
    github_token: str | None = None,
    keep_member: bool = False,
    slug: str | None = None,
    app_id: str | None = None,
) -> list[tuple[str, object]]:
    """(label, zero-argument call) in dependency order; GitHub Actions' workflow / role / provider last (the
    role / provider by their name from `slug` / `app_id` even when the state never recorded them)."""
    s = state
    steps: list[tuple[str, object]] = []
    if target in ("aws_static", "aws_app"):
        aws = client = cloud_aws.client(config)
        if target == "aws_static":
            if s.get("distribution_id"):
                steps.append(
                    (
                        f"CloudFront distribution {s['distribution_id']}",
                        lambda: aws.delete_distribution(s["distribution_id"]),
                    )
                )
            if s.get("function_name"):
                steps.append(
                    (f"CloudFront function {s['function_name']}", lambda: aws.delete_function(s["function_name"]))
                )
            if s.get("oac_id"):
                steps.append((f"Origin access control {s['oac_id']}", lambda: aws.delete_oac(s["oac_id"])))
            if s.get("bucket"):
                steps.append((f"S3 bucket {s['bucket']}", lambda: aws.delete_bucket(s["bucket"])))
            for host, arn in (s.get("certificates") or {}).items():
                steps.append((f"ACM certificate for {host}", lambda arn=arn: aws.delete_certificate(arn)))
        else:
            if s.get("service_arn"):
                steps.append(
                    (f"App Runner service {s.get('service_name')}", lambda: aws.delete_service(s["service_arn"]))
                )
            if s.get("ecr_repository"):
                steps.append(
                    (f"ECR repository {s['ecr_repository']}", lambda: aws.delete_repository(s["ecr_repository"]))
                )
            if s.get("instance_role"):
                steps.append((f"IAM role {s['instance_role']}", lambda: aws.delete_instance_role(s["instance_role"])))
    else:
        gcp = client = cloud_gcp.client(config)
        if s.get("run_service"):
            steps.append((f"Cloud Run service {s['run_service']}", lambda: gcp.delete_service(s["run_service"])))
        if s.get("ar_package"):
            steps.append(
                (
                    f"Artifact Registry images {s['ar_package']}",
                    lambda: gcp.delete_package(AR_REPOSITORY, s["ar_package"]),
                )
            )
        if s.get("site"):
            steps.append((f"Firebase Hosting site {s['site']}", lambda: gcp.delete_site(s["site"])))
    steps += cloud_secrets.teardown_steps(client, cloud.TARGETS[target]["provider"], s)
    if s.get("github"):  # present from the moment the switch was asked for, so an interrupted setup has it too
        steps += github_actions.teardown_steps(client, target, s["github"], github_token, keep_member, slug, app_id)
    return steps


def nat_teardown_steps(aws, vpc: str) -> list[tuple[str, object]]:
    name = cloud_aws.nat_name(vpc)
    return [
        (f"VPC connector {name}", lambda: aws.delete_vpc_connector(name)),
        (f"NAT gateway and its IP address in {vpc}", lambda: aws.delete_nat_gateway(vpc)),
        (f"Private route table in {vpc}", lambda: aws.delete_nat_routes(vpc)),
        (f"Private subnets in {vpc}", lambda: aws.delete_nat_subnets(vpc)),
    ]


@jobs.job_handler("app.cloud_teardown")
def _job_teardown(ctx: jobs.JobContext) -> dict:
    p = ctx.params
    state = p.get("state") or {}
    records = [r for d in p.get("domains") or [] for r in d.get("dns_records") or []]
    if p.get("setup_job_id"):
        ctx.progress(0.0, "Waiting for the GitHub Actions setup to stop", force=True)
        github_actions.wait_for_setup(ctx.session_factory, p["setup_job_id"])
    with ctx.session_factory() as db:
        conn = db.get(CloudConnection, p.get("connection_id")) if p.get("connection_id") else None
        config = cloud.config_of(conn) if conn else None
        failures = _delete_cf_records(db, records)
        token, keep_member = github_actions.teardown_context(
            db, p["app_id"], p.get("connection_id"), state.get("github") or {}
        )
    if config is None:
        left = resources(p["target"], state)
        raise jobs.JobError("The cloud connection was removed; delete these by hand: " + "; ".join(left))
    removed = []
    try:
        steps = teardown_steps(p["target"], config, state, token, keep_member, p.get("slug"), p["app_id"])
    except CloudError as exc:
        raise jobs.JobError(f"Could not connect to the cloud account: {exc.message}") from None
    # docs/CLOUD.md "C2-6": the shared NAT gateway last (the deleted service holds its connector for a while),
    # and only when no app uses it any more - counted when the teardown runs, not when it was queued.
    if p["target"] == "aws_app" and state.get("nat_vpc"):
        with ctx.session_factory() as db:
            if not nat_users(db, state["nat_vpc"]):
                steps += nat_teardown_steps(cloud_aws.client(config), state["nat_vpc"])
    for i, (label, call) in enumerate(steps):
        ctx.progress(i / max(len(steps), 1), f"Removing {label}", force=True)
        try:
            call()
            removed.append(label)
        except CloudError as exc:
            failures.append(f"{label}: {exc.message}")
    if failures:
        raise jobs.JobError("Some cloud resources were not removed - " + "; ".join(failures))
    # Leftovers of apps deleted during their setup (or of a failed teardown) go too; a sweep that can't
    # run (e.g. the account's policy predates iam:ListRoles) does not fail the teardown, it is noted.
    ctx.progress(1.0, "Looking for leftovers of GitHub Actions setups", force=True)
    provider = "aws" if p["target"].startswith("aws") else "firebase"
    client = cloud_aws.client(config) if provider == "aws" else cloud_gcp.client(config)
    try:
        with ctx.session_factory() as db:
            removed += github_actions.sweep_orphans(db, client, provider)
    except CloudError as exc:
        return {"removed": removed, "sweep_error": exc.message}
    return {"removed": removed}


# --- custom domains ------------------------------------------------------------------------------


def _client_for(db: Session, app: App):
    conn = db.get(CloudConnection, app.cloud_connection_id) if app.cloud_connection_id else None
    if conn is None:
        raise conflict("no_cloud_connection", "The app has no cloud connection")
    config = cloud.config_of(conn)
    return cloud_aws.client(config) if conn.provider == "aws" else cloud_gcp.client(config)


def add_domain(db: Session, app: App, hostname: str, zone: dict | None) -> Domain:
    """Asks the target for `hostname` and stores a pending Domain; `app.cloud_domain` then creates the
    DNS records (Cloudflare) or lists them, and activates it once the provider validated it. Caller commits."""
    state = dict(app.cloud_state or {})
    ready = {
        "aws_static": "distribution_id",
        "aws_app": "service_arn",
        "firebase_hosting": "released",
        "firebase_app": "released",
    }[app.target]
    if not state.get(ready):
        raise conflict("not_deployed", "Deploy the app once before adding a domain")
    existing = list(db.scalars(select(Domain).where(Domain.app_id == app.id, Domain.target_type == "cloud_app")))
    if app.target == "aws_static" and existing:
        # ponytail: one certificate per distribution; request a multi-name certificate to allow more.
        raise conflict("one_domain_only", "A CloudFront site takes one custom domain for now; remove the other first")
    try:
        client = _client_for(db, app)
        records: list[dict] = []
        if app.target == "aws_static":
            arn = client.request_certificate(hostname)
            state["certificates"] = {**(state.get("certificates") or {}), hostname: arn}
            records.append({"type": "CNAME", "name": hostname, "value": state["distribution_domain"]})
        elif app.target == "aws_app":
            target = client.associate_domain(state["service_arn"], hostname)
            records.append({"type": "CNAME", "name": hostname, "value": target})
        else:
            client.add_domain(state["site"], hostname)
    except CloudError as exc:
        raise ApiError(502, "cloud_error", exc.message) from None
    app.cloud_state = state
    domain = Domain(
        hostname=hostname,
        provider=cloud.TARGETS[app.target]["provider"],
        zone_id=zone["id"] if zone else None,
        zone_name=zone["name"] if zone else None,
        target_type="cloud_app",
        project_id=app.project_id,
        app_id=app.id,
        status="pending",
        status_message="Waiting for the DNS records and the provider's validation",
        dns_records=records,
    )
    db.add(domain)
    db.flush()
    return domain


def _merge_records(domain: Domain, found: list[dict]) -> list[dict]:
    records = [dict(r) for r in domain.dns_records or []]
    known = {(r["type"], r["name"].lower()) for r in records}
    for r in found:
        if r.get("type") and r.get("name") and (r["type"], r["name"].lower()) not in known:
            records.append({"type": r["type"], "name": r["name"], "value": r["value"]})
            known.add((r["type"], r["name"].lower()))
    return records


def _create_cf_records(db: Session, domain: Domain, records: list[dict]) -> None:
    """Creates the not-yet-created records in the domain's Cloudflare zone (DNS only). A failure is noted
    on the record (`error`) so the dashboard shows it with the record to add by hand."""
    token = get_value(db, "cloudflare_api_token")
    todo = [r for r in records if not r.get("cf_id") and not r.get("error")]
    if not (domain.zone_id and token and todo):
        return
    with cf.CloudflareClient(token) as client:
        for r in todo:
            try:
                created = client.create_record(domain.zone_id, r["type"], r["name"], r["value"])
                r["cf_id"], r["zone_id"] = created.get("id"), domain.zone_id
            except cf.CloudflareError as exc:
                r["error"] = f"Cloudflare: {exc.message}"


def check_domain(db: Session, app: App, domain: Domain) -> str:
    """One validation pass: new records merged (and created in Cloudflare), status updated. Returns it."""
    state = app.cloud_state or {}
    client = _client_for(db, app)
    host = domain.hostname
    try:
        if app.target == "aws_static":
            arn = (state.get("certificates") or {}).get(host)
            cert = client.certificate(arn)
            found, status = cert["records"], cert["status"]
            if status == "ISSUED":
                client.set_aliases(state["distribution_id"], [host], arn)
                status = "active"
            elif status in ("FAILED", "VALIDATION_TIMED_OUT", "REVOKED"):
                domain.status, domain.status_message = "error", f"The certificate could not be issued ({status})"
        elif app.target == "aws_app":
            out = client.domain_status(state["service_arn"], host)
            found, status = out["records"], out["status"]
            if status in ("create_failed", "delete_failed", "missing"):
                domain.status, domain.status_message = "error", f"App Runner reports the domain as {status}"
        else:
            out = client.domain(state["site"], host)
            found, status = out["records"], out["status"]
    except CloudError as exc:
        domain.status_message = f"Could not check: {exc.message}"
        return domain.status
    records = _merge_records(domain, found)
    _create_cf_records(db, domain, records)
    domain.dns_records = records
    if status == "active":
        domain.status, domain.status_message = "active", None
    elif domain.status != "error":
        who = "Cloudflare records created; " if domain.zone_id else "Add the DNS records below; "
        domain.status_message = who + "waiting for the provider to validate them (can take up to an hour)"
    return domain.status


def enqueue_domain_check(db: Session, domain: Domain, user_id: str | None) -> str:
    job = jobs.enqueue(
        db,
        type="app.cloud_domain",
        params={"domain_id": domain.id},
        project_id=domain.project_id,
        created_by_id=user_id,
    )
    return job.id


@jobs.job_handler("app.cloud_domain")
def _job_domain(ctx: jobs.JobContext) -> dict:
    domain_id = str(ctx.params["domain_id"])
    started = time.monotonic()
    while True:
        with ctx.session_factory() as db:
            domain = db.get(Domain, domain_id)
            app = db.get(App, domain.app_id) if domain is not None and domain.app_id else None
            if domain is None or app is None or app.target == "local":
                return {"skipped": "domain or app missing"}
            status = check_domain(db, app, domain)
            timed_out = time.monotonic() - started >= DOMAIN_TIMEOUT_S
            if status == "pending" and timed_out:
                domain.status_message = "Not validated yet - check the DNS records below, then press Check again"
            db.commit()
        if status != "pending" or timed_out:
            return {"status": status}
        ctx.check_cancelled()
        ctx.progress(None, "Waiting for DNS validation")
        time.sleep(POLL_S * 3)


def remove_domain(db: Session, app: App, domain: Domain) -> list[str]:
    """Detaches the hostname from the target and deletes the Cloudflare records Deployer created.
    Returns warnings (things to finish by hand). Caller deletes the row and commits."""
    warnings = _delete_cf_records(db, domain.dns_records or [])
    state = dict(app.cloud_state or {})
    host = domain.hostname
    try:
        client = _client_for(db, app)
        if app.target == "aws_static":
            arn = (state.get("certificates") or {}).pop(host, None)
            if state.get("distribution_id") and domain.status == "active":
                client.set_aliases(state["distribution_id"], [], None)
            if arn:
                try:
                    client.delete_certificate(arn)
                except CloudError:
                    warnings.append(
                        f"The ACM certificate for {host} is still attached while CloudFront updates; delete it "
                        "later in ACM (us-east-1). Certificates are free."
                    )
            app.cloud_state = state
        elif app.target == "aws_app" and state.get("service_arn"):
            client.disassociate_domain(state["service_arn"], host)
        elif state.get("site"):
            client.delete_domain(state["site"], host)
    except (CloudError, ApiError) as exc:
        warnings.append(f"Could not detach {host} from the cloud target: {getattr(exc, 'message', exc)}")
    return warnings
