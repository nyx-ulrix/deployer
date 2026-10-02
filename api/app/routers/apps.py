"""Apps, deployments, app hostnames and the GitHub webhook (docs/DEPLOYMENTS.md "API")."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.crypto import encrypt_secret
from app.db import get_sessionmaker
from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, conflict, forbidden, not_found
from app.models import App, AppReplica, Deployment, Domain, Project, User
from app.services import (
    app_runner,
    audit,
    cloud,
    cloud_deploy,
    cloud_secrets,
    cohost_apps,
    deployments,
    device_rpc,
    github,
    github_actions,
    jobs,
    rate_limit,
)
from app.services import remote_access as ra

router = APIRouter(tags=["apps"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]
Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]

BASE = "/projects/{project_id}/apps"
_COMMAND = Field(default=None, max_length=500)
_BRANCH_RE = re.compile(r"^[^\s~^:?*\[\\]+$")
Target = Literal["local", "aws_static", "aws_app", "firebase_hosting", "firebase_app"]


def _valid_branch(value: str | None) -> str | None:
    if value is not None and (not _BRANCH_RE.match(value) or value.startswith("-")):
        raise ValueError("is not a valid branch name")
    return value


def _one_line(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise ValueError("must be a single line")
    return value or None


class AppFields(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    repo_url: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default=None, max_length=120)
    root_dir: str | None = Field(default=None, max_length=200)
    preset: Literal["static", "node", "python", "dockerfile"] | None = None
    install_command: str | None = _COMMAND
    build_command: str | None = _COMMAND
    start_command: str | None = _COMMAND
    output_dir: str | None = Field(default=None, max_length=200)
    container_port: int | None = Field(default=None, ge=1, le=65535)
    env: dict[str, str] | None = None
    repo_token: str | None = Field(default=None, max_length=500)
    api_key_id: str | None = Field(default=None, max_length=36)
    database_access: bool | None = None
    # docs/COHOSTING.md "Websites on both PCs" (admin-only)
    cohost: bool | None = None
    cohost_share_repo_access: bool | None = None
    # docs/CLOUD.md: where it runs (admin-only to change) and with which cloud connection.
    target: Target | None = None
    cloud_connection_id: str | None = Field(default=None, max_length=36)
    # docs/CLOUD.md "G1": keep the variables in AWS Secrets Manager / Google Secret Manager (App Runner / Cloud
    # Run apps, admin-only, billable: confirm_billing when switching it on).
    cloud_secrets: bool | None = None
    # docs/CLOUD.md "C2-6": an App Runner app with database access also reaches the internet (a NAT gateway).
    internet_access: bool | None = None
    # Putting the app on a cloud target (or another account) bills that account: the caller confirms it.
    confirm_billing: bool = False

    @field_validator("install_command", "build_command", "start_command", "output_dir", "repo_token", "branch")
    @classmethod
    def _single_line(cls, value: str | None) -> str | None:
        return _one_line(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be empty")
        return value.strip() if value else value

    @field_validator("repo_url")
    @classmethod
    def _repo_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or any(c.isspace() for c in value)
        ):
            raise ValueError("must be an https:// URL without credentials")
        return value

    @field_validator("branch")
    @classmethod
    def _branch(cls, value: str | None) -> str | None:
        return _valid_branch(value)

    @field_validator("root_dir")
    @classmethod
    def _root_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().strip("/") or "."
        if ".." in value.split("/") or "\\" in value or "\n" in value:
            raise ValueError("must be a relative path inside the repository")
        return value

    @field_validator("env")
    @classmethod
    def _env(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        for key in value:
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$", key):
                raise ValueError(f"invalid environment variable name {key!r}")
            if app_runner.reserved_env(key):
                raise ValueError(f"{key} is reserved (DOCKER_*, LD_* and PATH configure the worker's docker)")
        if len(json.dumps(value)) > 64 * 1024:
            raise ValueError("environment is too large (64 KB max)")
        return value


class AppCreate(AppFields):
    name: str = Field(max_length=120)
    repo_url: str = Field(max_length=500)
    preset: Literal["static", "node", "python", "dockerfile"]
    # Clone + add the push webhook with the caller's GitHub connection instead of a repo_token.
    use_github_connection: bool = False


class DetectBody(AppFields):
    """Only `repo_url` (required) and `branch` are used; AppFields gives them the same validation."""

    repo_url: str = Field(max_length=500)


def _check_preset(app: App) -> None:
    if app.preset == "dockerfile" and not app.container_port:
        raise ApiError(
            422, "validation_error", "container_port is required for the dockerfile preset", {"field": "container_port"}
        )
    if app.preset == "python" and not app.start_command:
        raise ApiError(
            422, "validation_error", "start_command is required for the python preset", {"field": "start_command"}
        )


def _check_database_access(access: ProjectAccess, enable: bool | None) -> None:
    """docs/DEPLOYMENTS.md "Database access": only admins switch it on; anyone who edits may turn it off."""
    if enable and not access.at_least("admin"):
        raise forbidden("Only project admins can give an app database access")


def _check_api_key_access(access: ProjectAccess, app: App | None, body: AppFields, repo_moved: bool) -> None:
    """A-171: the attached key's secret lands in the container, so only admins attach or swap one, and
    only admins point a keyed app at another repository (its code would read DEPLOYER_API_KEY).
    Detaching is allowed to anyone who edits, like switching database access off."""
    if access.at_least("admin"):
        return
    current = app.api_key_id if app else None
    new = body.api_key_id if "api_key_id" in body.model_fields_set else current
    if new and new != current:
        raise forbidden("Only project admins can attach an API key to an app")
    if new and repo_moved:
        raise forbidden("Only project admins can change the repository of an app with an API key attached")


def _audit_database_access(db, request: Request, access: ProjectAccess, app: App) -> None:
    audit.record(
        db,
        "app.database_access",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        enabled=app.database_access,
    )


def _check_cohost(access: ProjectAccess, app: App, body: AppFields) -> bool:
    """True when the request changes a co-hosting flag; only project admins may."""
    changed = any(
        field in body.model_fields_set and bool(getattr(body, field)) != bool(getattr(app, field))
        for field in ("cohost", "cohost_share_repo_access")
    )
    if changed and not access.at_least("admin"):
        raise forbidden("Only project admins can change co-hosting")
    return changed


def _audit_cohost(db, request: Request, access: ProjectAccess, app: App) -> None:
    audit.record(
        db,
        "app.cohost",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        enabled=app.cohost,
        share_repo_access=app.cohost_share_repo_access,
    )


def _check_target(db, app: App) -> None:
    """docs/CLOUD.md: a cloud target needs a usable connection of its provider, a static preset for the
    static targets, and none of the switches that tie an app to this PC."""
    if app.target == "local":
        app.cloud_connection_id = None
        return
    cloud.usable_connection(db, app.project_id, app.cloud_connection_id, app.target)
    if app.target in cloud.STATIC_TARGETS and app.preset != "static":
        raise ApiError(
            422,
            "validation_error",
            f"{cloud.TARGETS[app.target]['label']} serves static files: use the static preset, or a full-app target",
            {"field": "target"},
        )
    # docs/CLOUD.md "C2": on App Runner / Cloud Run, database access means the project's databases in the
    # same cloud account (AWS: RDS, DynamoDB; Firebase: Firestore) instead.
    tied = (
        ("cohost", "api_key_id")
        if app.target in cloud.DATABASE_TARGETS
        else ("database_access", "cohost", "api_key_id")
    )
    for field in tied:
        if getattr(app, field):
            raise ApiError(
                422,
                "validation_error",
                f"{field} ties an app to this PC and is not available on cloud targets",
                {"field": field},
            )


def _check_billing(app: App, body: AppFields) -> None:
    """docs/CLOUD.md: a cloud target creates billable resources on the first deploy, so moving an app onto one
    (or onto another cloud account) needs confirm_billing: true, like every other billable action."""
    if app.target != "local" and not body.confirm_billing:
        raise ApiError(
            422,
            "billing_not_confirmed",
            f"{cloud.TARGETS[app.target]['label']} is billed to the cloud account: {cloud.TARGETS[app.target]['cost']} "
            "Send confirm_billing: true.",
            {"field": "confirm_billing"},
        )


def _set_cloud_secrets(db, access: ProjectAccess, app: App, body: AppFields) -> None:
    """docs/CLOUD.md "G1": admins switch the secret store on (billable: confirm_billing) or off; App Runner /
    Cloud Run apps only. Called after a target switch, which starts the app's cloud state afresh."""
    if not access.at_least("admin"):
        raise forbidden("Only project admins can change where an app's secrets are kept (it is billed)")
    enable = bool(body.cloud_secrets)
    if not enable and app.target not in cloud.DATABASE_TARGETS:
        return  # nothing to switch off
    if app.target not in cloud.DATABASE_TARGETS:
        raise ApiError(
            422,
            "validation_error",
            "Keeping variables in the cloud secret store is for App Runner and Cloud Run apps",
            {"field": "cloud_secrets"},
        )
    if enable and not cloud_secrets.enabled(app) and not body.confirm_billing:
        provider = cloud.TARGETS[app.target]["provider"]
        raise ApiError(
            422,
            "billing_not_confirmed",
            f"{cloud_secrets.STORE[provider]} is billed to the cloud account: {cloud_secrets.COST[provider]} "
            "Send confirm_billing: true.",
            {"field": "confirm_billing"},
        )
    cloud_secrets.set_enabled(app, enable)


def _check_internet(access: ProjectAccess, app: App, body: AppFields) -> None:
    """docs/CLOUD.md "C2-6": `internet_access` (kept in cloud_state) is for App Runner apps with database
    access - their traffic goes through the VPC, which has no internet route; every other app already reaches
    the internet. Turning it on adds a billed NAT gateway: admins only, with confirm_billing: true."""
    state = dict(app.cloud_state or {})
    had = bool(state.get("internet_access"))
    want = had if body.internet_access is None else body.internet_access
    if want and not (app.target == "aws_app" and app.database_access):
        if body.internet_access:
            raise ApiError(
                422,
                "validation_error",
                "'Let this app reach the internet too' is for App Runner apps with database access; other apps "
                "already reach the internet",
                {"field": "internet_access"},
            )
        want = False  # the switch it depended on went off
    if want and not had:
        if not access.at_least("admin"):
            raise forbidden("Only project admins can add a NAT gateway (it is billed to the cloud account)")
        if not body.confirm_billing:
            raise ApiError(
                422,
                "billing_not_confirmed",
                f"{cloud.NAT_COST} Send confirm_billing: true.",
                {"field": "confirm_billing"},
            )
    if want:
        state["internet_access"] = True
    else:
        state.pop("internet_access", None)
    app.cloud_state = state or None


def _runtime_settings(app: App) -> tuple:
    """What a running App Runner / Cloud Run service was published with: a change republishes it (G1). Compared
    before and after a PATCH, since the dashboard sends every field whether it changed or not."""
    return (
        deployments.env_of(app),
        bool(app.database_access),
        cloud_secrets.enabled(app),
        bool((app.cloud_state or {}).get("internet_access")),
    )


def _switch_target(db, request: Request, access: ProjectAccess, app: App, before: tuple) -> str | None:
    """The target or connection changed: the old target's resources are torn down (job), the local
    container removed, deployments forget their artifacts (they belong to the old target). Returns the job id."""
    target, connection_id, state = before
    if db.scalar(
        select(Deployment.id).where(Deployment.app_id == app.id, Deployment.status.in_(deployments.ACTIVE_STATUSES))
    ):
        raise conflict("deployment_active", "Wait for the running deployment to finish (or cancel it) first")
    if deployments.app_domains(db, app.id):
        raise conflict("domains_exist", "Remove the app's custom domains first; add them again on the new target")
    old = App(
        id=app.id,
        project_id=app.project_id,
        name=app.name,
        slug=app.slug,
        target=target,
        cloud_connection_id=connection_id,
        cloud_state=state,
    )
    job_id = cloud_deploy.enqueue_teardown(db, old, access.user.id)
    if target == "local" and app.live_deployment_id:
        job_id = jobs.enqueue(
            db,
            type="app.remove",
            params={"app_id": app.id, "slug": app.slug},
            project_id=app.project_id,
            created_by_id=access.user.id,
        ).id
    for dep in db.scalars(select(Deployment).where(Deployment.app_id == app.id)):
        dep.image_tag = None
        if dep.status == "live":
            dep.status = "superseded"
    app.live_deployment_id, app.cloud_state = None, None
    if app.target != "local":  # the switches that tie an app to this PC go off
        app.cohost, app.cohost_share_repo_access, app.api_key_id = False, False, None
        if app.target not in cloud.DATABASE_TARGETS:  # App Runner / Cloud Run keep it: their cloud databases
            app.database_access = False
    audit.record(
        db,
        "app.target",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        target=app.target,
        previous=target,
        cloud_connection_id=app.cloud_connection_id,
    )
    return job_id


def _dispatch(job) -> None:
    if job is not None:
        jobs.dispatch(job.id)


# --- apps ----------------------------------------------------------------------------------------


@router.get(BASE)
def list_apps(access: Viewer, db: DbSession) -> list[dict]:
    rows = db.scalars(select(App).where(App.project_id == access.project.id).order_by(App.created_at))
    return [deployments.app_out(db, app) for app in rows]


@router.post(BASE, status_code=201)
def create_app(body: AppCreate, request: Request, access: Developer, db: DbSession) -> dict:
    project = access.project
    _check_database_access(access, body.database_access)
    if (body.cohost or body.cohost_share_repo_access) and not access.at_least("admin"):
        raise forbidden("Only project admins can change co-hosting")
    if body.cohost:
        cohost_apps.check_single_cohost(db, None)
    _check_api_key_access(access, None, body, repo_moved=False)
    deployments.check_api_key(db, project.id, body.api_key_id)
    if body.use_github_connection:
        if body.repo_token:
            raise ApiError(422, "validation_error", "Send either repo_token or use_github_connection, not both")
        if github.parse_repo(body.repo_url) is None:
            raise ApiError(
                422, "validation_error", "use_github_connection needs a https://github.com/<owner>/<repo> URL"
            )
        github.require_token(db, access.user.id)
    app = App(
        project_id=project.id,
        name=body.name,
        slug=deployments.app_slug(db, project.id, body.name),
        repo_url=body.repo_url,
        branch=body.branch or "main",
        root_dir=body.root_dir or ".",
        preset=body.preset,
        install_command=body.install_command,
        build_command=body.build_command,
        start_command=body.start_command,
        output_dir=body.output_dir,
        container_port=body.container_port,
        api_key_id=body.api_key_id,
        database_access=bool(body.database_access),
        cohost=bool(body.cohost),
        cohost_share_repo_access=bool(body.cohost_share_repo_access),
        port=deployments.allocate_port(db),
        created_by_id=access.user.id,
        github_connection_user_id=access.user.id if body.use_github_connection else None,
        target=body.target or "local",
        cloud_connection_id=body.cloud_connection_id,
    )
    _check_preset(app)
    if app.target != "local" and not access.at_least("admin"):
        raise forbidden("Only project admins can put an app on a cloud target (it is billed to the cloud account)")
    _check_target(db, app)
    _check_billing(app, body)
    if body.cloud_secrets is not None:
        _set_cloud_secrets(db, access, app, body)
    _check_internet(access, app, body)
    deployments.set_env(app, body.env or {})
    if body.repo_token:
        app.repo_token_encrypted = encrypt_secret(body.repo_token)
    secret = deployments.rotate_webhook_secret(app)
    db.add(app)
    db.flush()
    warnings = github.sync_hook(db, app, deployments.webhook_url(db, app), secret)
    audit.record(
        db,
        "app.create",
        request=request,
        user_id=access.user.id,
        project_id=project.id,
        app_id=app.id,
        preset=app.preset,
        target=app.target,
    )
    if app.database_access:
        _audit_database_access(db, request, access, app)
    if app.cohost or app.cohost_share_repo_access:
        _audit_cohost(db, request, access, app)
    db.commit()
    return {**deployments.app_out(db, app), "warnings": warnings}


@router.post(BASE + "/detect")
def detect_app(body: DetectBody, access: Developer, db: DbSession) -> dict:
    """A suggested app draft read from the repository (never persisted)."""
    return github.detect_draft(db, access.user.id, body.repo_url, body.branch)


@router.get(BASE + "/{app_id}")
def get_app(app_id: str, access: Viewer, db: DbSession) -> dict:
    return deployments.app_out(db, deployments.get_app(db, access.project.id, app_id))


@router.patch(BASE + "/{app_id}")
def update_app(app_id: str, body: AppFields, request: Request, access: Developer, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    changed = sorted(body.model_fields_set - {"confirm_billing"})
    if "database_access" in changed:
        _check_database_access(access, body.database_access and not app.database_access)
    access_before = app.database_access
    cohost_before = app.cohost
    target_before = (app.target, app.cloud_connection_id, app.cloud_state)
    runtime_before = _runtime_settings(app)
    cohost_changed = _check_cohost(access, app, body)
    if "cohost" in changed and body.cohost and not app.cohost:
        cohost_apps.check_single_cohost(db, app.id)
    old_repo_url = app.repo_url
    repo_moved = bool("repo_url" in changed and body.repo_url and body.repo_url != app.repo_url)
    if repo_moved and github_actions.state_of(app) is not None:
        # The workflow file, the role / provider trust and the reports all belong to the old repository.
        raise conflict(
            "builds_on_github",
            "This app builds on GitHub Actions in its current repository: switch 'Where it builds' back to This PC "
            "first, change the repository, then choose GitHub Actions again",
        )
    _check_api_key_access(access, app, body, repo_moved)
    if (
        "repo_url" in changed
        and body.repo_url
        and "repo_token" not in changed
        and urlsplit(body.repo_url).netloc.lower() != urlsplit(app.repo_url).netloc.lower()
    ):
        # The stored token was given for the old host: git would hand it to the new one.
        app.repo_token_encrypted = None
    for field in changed:
        value = getattr(body, field)
        if field == "env":
            deployments.set_env(app, value or {})
        elif field == "repo_token":
            app.repo_token_encrypted = encrypt_secret(value) if value else None
        elif field == "api_key_id":
            deployments.check_api_key(db, app.project_id, value)
            app.api_key_id = value
        elif field == "name":
            app.name = value
        elif field == "branch":
            app.branch = value or "main"
        elif field == "root_dir":
            app.root_dir = value or "."
        elif field in ("database_access", "cohost", "cohost_share_repo_access"):
            setattr(app, field, bool(value))
        elif field == "target":
            app.target = value or "local"
        elif field in ("cloud_secrets", "internet_access"):
            pass  # after the target switch below (which resets the cloud state)
        elif value is not None or field in (
            "install_command",
            "build_command",
            "start_command",
            "output_dir",
            "container_port",
            "cloud_connection_id",
        ):
            setattr(app, field, value)
    _check_preset(app)
    teardown_job = None
    if app.target == "local":
        app.cloud_connection_id = None
    moved = (app.target, app.cloud_connection_id) != target_before[:2]
    if moved:
        if not access.at_least("admin"):
            raise forbidden("Only project admins can change where an app runs")
        teardown_job = _switch_target(db, request, access, app, target_before)
    _check_target(db, app)
    if moved:
        _check_billing(app, body)
    if "cloud_secrets" in changed:
        _set_cloud_secrets(db, access, app, body)
    _check_internet(access, app, body)
    build_job = github_actions.refresh_if_needed(db, app, changed, access.user.id)
    # docs/CLOUD.md "G1": a changed environment reaches an App Runner / Cloud Run app right away (republished
    # from this PC with the live artifact) instead of waiting for the next build or rollback.
    env_dep = None
    if not moved and _runtime_settings(app) != runtime_before:
        env_dep = deployments.republish(db, app, user_id=access.user.id)
    audit.record(
        db,
        "app.update",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        changes=changed,
    )
    if app.database_access != access_before:
        _audit_database_access(db, request, access, app)
    if app.cohost != cohost_before:
        ra.move_app_hostnames(db, app)  # to the apps tunnel or back; nothing is saved if Cloudflare fails
    if cohost_changed:
        _audit_cohost(db, request, access, app)
    warnings: list[str] = []
    if repo_moved and app.github_connection_user_id:
        # Last before the commit, after validation and Cloudflare (either may raise): the webhook
        # belongs to the old repository, and only the connection's owner may point the app (and a
        # new webhook) at another one.
        github.delete_hook(db, app, repo_url=old_repo_url)
        if app.github_connection_user_id == access.user.id:
            warnings = github.sync_hook(db, app, deployments.webhook_url(db, app), deployments.webhook_secret(app))
        else:
            app.github_connection_user_id = None
            warnings = [
                "The GitHub webhook was removed with the old repository; add one by hand (app Settings → Webhook)."
            ]
    db.commit()
    for job_id in (teardown_job, build_job):
        if job_id:
            jobs.dispatch(job_id)
    if env_dep is not None:
        _dispatch(env_dep[1])
    if cohost_changed:
        cohost_apps.replicate(get_sessionmaker(), app.id, user_id=access.user.id, retry=True)
        ra.sync_desired(db)  # the apps tunnel may be new: start its connector on this PC
    db.refresh(app)
    return {
        **deployments.app_out(db, app),
        "teardown_job_id": teardown_job,
        "build_job_id": build_job,
        "env_deployment_id": env_dep[0].id if env_dep else None,
        "warnings": warnings,
    }


class BuildBody(BaseModel):
    location: Literal["pc", "github"]
    confirm_billing: bool = False


@router.put(BASE + "/{app_id}/build")
def set_build_location(app_id: str, body: BuildBody, request: Request, access: Admin, db: DbSession) -> dict:
    """docs/CLOUD.md "C3": where a cloud app builds - this PC, or GitHub Actions (which then deploys every push
    while this PC is off). Choosing GitHub Actions again re-runs its setup (repairs it)."""
    app = deployments.get_app(db, access.project.id, app_id)
    if db.scalar(
        select(Deployment.id).where(Deployment.app_id == app.id, Deployment.status.in_(deployments.ACTIVE_STATUSES))
    ):
        raise conflict("deployment_active", "Wait for the running deployment to finish (or cancel it) first")
    if jobs.active_job(db, "app.github_actions", key=app.id) is not None:
        raise conflict("build_setup_running", "Wait for the GitHub Actions setup to finish first")
    if body.location == "github":
        github_actions.check_can_build(db, app, access.user.id)
        if not body.confirm_billing:
            raise ApiError(
                422,
                "billing_not_confirmed",
                f"{github_actions.COST} Send confirm_billing: true.",
                {"field": "confirm_billing"},
            )
        job_id = github_actions.enqueue_setup(db, app, access.user.id)
    else:
        job_id = github_actions.enqueue_removal(db, app, access.user.id)
    audit.record(
        db,
        "app.build_location",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        location=body.location,
    )
    db.commit()
    if job_id:
        jobs.dispatch(job_id)
    db.refresh(app)
    return {**deployments.app_out(db, app), "job_id": job_id}


@router.get(BASE + "/{app_id}/github-runs")
def github_runs(app_id: str, access: Viewer, db: DbSession) -> dict:
    """The GitHub Actions runs of the app's workflow (also the ones while this PC was off)."""
    return github_actions.runs(db, deployments.get_app(db, access.project.id, app_id))


@router.delete(BASE + "/{app_id}")
def delete_app(app_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    teardown_job = cloud_deploy.enqueue_teardown(db, app, access.user.id)  # also the cloud domains' records
    warnings: list[str] = []
    for domain in deployments.app_domains(db, app.id):
        if domain.target_type != "cloud_app":
            # DNS + ingress, best effort: a revoked token or no internet must not block the delete
            warnings += ra.remove_hostname(db, domain.id, request=request, user_id=access.user.id, best_effort=True)
    for dep in db.scalars(
        select(Deployment).where(Deployment.app_id == app.id, Deployment.status.in_(deployments.ACTIVE_STATUSES))
    ):
        deployments.cancel_deployment(db, dep)
    github.delete_hook(db, app)
    job = jobs.enqueue(
        db,
        type="app.remove",
        params={"app_id": app.id, "slug": app.slug},
        project_id=app.project_id,
        created_by_id=access.user.id,
    )
    audit.record(
        db,
        "app.delete",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        name=app.name,
    )
    db.delete(app)
    db.commit()
    jobs.dispatch(job.id)
    if teardown_job:
        jobs.dispatch(teardown_job)
    return {"job_id": job.id, "teardown_job_id": teardown_job, "warnings": warnings}


@router.get(BASE + "/{app_id}/env")
def reveal_env(app_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    audit.record(
        db, "app.env.reveal", request=request, user_id=access.user.id, project_id=app.project_id, app_id=app.id
    )
    db.commit()
    return {"env": deployments.env_of(app)}


@router.get(BASE + "/{app_id}/webhook")
def reveal_webhook(app_id: str, request: Request, access: Developer, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    audit.record(
        db, "app.webhook.reveal", request=request, user_id=access.user.id, project_id=app.project_id, app_id=app.id
    )
    db.commit()
    return {"url": deployments.webhook_url(db, app), "secret": deployments.webhook_secret(app)}


@router.post(BASE + "/{app_id}/webhook/rotate")
def rotate_webhook(app_id: str, request: Request, access: Developer, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    secret = deployments.rotate_webhook_secret(app)
    url = deployments.webhook_url(db, app)
    warnings = github.sync_hook(db, app, url, secret)
    audit.record(
        db, "app.webhook.rotate", request=request, user_id=access.user.id, project_id=app.project_id, app_id=app.id
    )
    db.commit()
    return {"url": url, "secret": secret, "hook_active": app.github_hook_id is not None, "warnings": warnings}


# --- deployments ---------------------------------------------------------------------------------


class DeployBody(BaseModel):
    branch: str | None = Field(default=None, max_length=120)

    @field_validator("branch")
    @classmethod
    def _branch(cls, value: str | None) -> str | None:
        value = _one_line(value)
        return _valid_branch(value)


@router.post(BASE + "/{app_id}/deploy", status_code=202)
def deploy(app_id: str, request: Request, access: Developer, db: DbSession, body: DeployBody | None = None) -> dict:
    """Builds and deploys the app (on this PC), or runs its GitHub Actions workflow when it builds there
    (then the answer is `{github_actions: true, status: "dispatched", runs_url}`, no deployment yet)."""
    app = deployments.get_app(db, access.project.id, app_id)
    if github_actions.ready(app):  # docs/CLOUD.md "C3": built and deployed by its workflow on GitHub
        out = github_actions.dispatch(db, app, body.branch if body else None)
        audit.record(
            db,
            "app.deploy",
            request=request,
            user_id=access.user.id,
            project_id=app.project_id,
            app_id=app.id,
            github=True,
        )
        db.commit()
        return out
    dep, job = deployments.start_deployment(
        db, app, trigger="manual", user_id=access.user.id, branch=(body.branch if body else None)
    )
    audit.record(
        db,
        "app.deploy",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        deployment_id=dep.id,
    )
    db.commit()
    _dispatch(job)
    return deployments.deployment_out(dep)


@router.get(BASE + "/{app_id}/deployments")
def list_deployments(
    app_id: str,
    access: Viewer,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[str | None, Query(max_length=40)] = None,
) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    stmt = (
        select(Deployment)
        .where(Deployment.app_id == app.id)
        .order_by(Deployment.created_at.desc(), Deployment.id.desc())
    )
    if before:
        anchor = db.get(Deployment, before)
        if anchor is not None and anchor.app_id == app.id:
            # Keyset on (created_at, id), the sort order: same-second rows are neither repeated nor dropped (A-032).
            stmt = stmt.where(
                or_(
                    Deployment.created_at < anchor.created_at,
                    and_(Deployment.created_at == anchor.created_at, Deployment.id < anchor.id),
                )
            )
    rows = list(db.scalars(stmt.limit(limit + 1)))
    return {"deployments": [deployments.deployment_out(d) for d in rows[:limit]], "has_more": len(rows) > limit}


@router.get(BASE + "/{app_id}/deployments/{deployment_id}")
def get_deployment(app_id: str, deployment_id: str, access: Viewer, db: DbSession, log: int = 0) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    return deployments.deployment_out(deployments.get_deployment(db, app, deployment_id), with_log=bool(log))


@router.post(BASE + "/{app_id}/deployments/{deployment_id}/cancel")
def cancel_deployment(app_id: str, deployment_id: str, request: Request, access: Developer, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    dep = deployments.cancel_deployment(db, deployments.get_deployment(db, app, deployment_id))
    audit.record(
        db,
        "app.deploy.cancel",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        deployment_id=dep.id,
    )
    db.commit()
    return deployments.deployment_out(dep)


@router.post(BASE + "/{app_id}/deployments/{deployment_id}/rollback", status_code=202)
def rollback_deployment(app_id: str, deployment_id: str, request: Request, access: Developer, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    old = deployments.get_deployment(db, app, deployment_id)
    dep, job = deployments.rollback(db, app, old, user_id=access.user.id)
    audit.record(
        db,
        "app.rollback",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        deployment_id=dep.id,
        rollback_of=old.id,
    )
    db.commit()
    _dispatch(job)
    return deployments.deployment_out(dep)


@router.get(BASE + "/{app_id}/logs")
def runtime_logs(
    app_id: str,
    access: Viewer,
    db: DbSession,
    tail: Annotated[int, Query(ge=1, le=500)] = 200,
    device_id: Annotated[str | None, Query(max_length=36)] = None,
) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    if device_id:
        # docs/COHOSTING.md: the copy on a co-host device (503 device_offline while it is off).
        replica = db.scalar(select(AppReplica).where(AppReplica.app_id == app.id, AppReplica.device_id == device_id))
        if replica is None:
            raise not_found("Co-host copy")
        out = device_rpc.call(device_id, "apps.logs", {"app_id": app.id, "tail": tail}, timeout=20)
        out = out if isinstance(out, dict) else {}
        lines = [str(line) for line in out.get("lines") or []][-tail:]
        return {"lines": lines, "container": out.get("container"), "device_id": device_id}
    live = db.get(Deployment, app.live_deployment_id) if app.live_deployment_id else None
    lines = deployments.runtime_logs(app, tail)
    return {"lines": lines, "container": live.container_name if live else None}


# --- hostnames -----------------------------------------------------------------------------------


class HostnameBody(BaseModel):
    hostname: str = Field(min_length=1, max_length=300)
    overwrite: bool = False


def _reroute(db: DbSession, app: App, user_id: str) -> None:
    if app.cohost:
        cohost_apps.replicate(get_sessionmaker(), app.id, user_id=user_id, retry=True)  # device host blocks
    if app.live_deployment_id:
        job = jobs.enqueue(
            db, type="app.route", params={"app_id": app.id}, project_id=app.project_id, created_by_id=user_id
        )
        db.commit()
        jobs.dispatch(job.id)


@router.post(BASE + "/{app_id}/domains")
def add_domain(app_id: str, body: HostnameBody, request: Request, access: Admin, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    host = ra.normalize_hostname(body.hostname)
    if app.target != "local":
        return _add_cloud_domain(db, request, access, app, host)
    zone = ra.zone_for_hostname(db, host)
    out = ra.add_hostname(
        db,
        zone["id"],
        host,
        body.overwrite,
        request=request,
        user_id=access.user.id,
        target_type="app",
        project_id=app.project_id,
        app_id=app.id,
    )
    _reroute(db, app, access.user.id)
    return out


def _add_cloud_domain(db, request: Request, access: ProjectAccess, app: App, host: str) -> dict:
    """docs/CLOUD.md "Custom domains": the target is asked for the hostname; with Cloudflare linked (and a
    zone containing it) the records it needs are created there, otherwise listed to add by hand."""
    if db.scalar(select(Domain.id).where(Domain.hostname == host)) is not None:
        raise conflict("domain_exists", f"{host} is already configured")
    zone = None
    if ra.is_linked(db):
        try:
            zone = ra.zone_for_hostname(db, host)
        except ApiError as exc:
            if exc.code != "zone_not_found":
                raise
    domain = cloud_deploy.add_domain(db, app, host, zone)
    job_id = cloud_deploy.enqueue_domain_check(db, domain, access.user.id)
    audit.record(
        db,
        "app.domain_add",
        request=request,
        user_id=access.user.id,
        project_id=app.project_id,
        app_id=app.id,
        hostname=host,
        target=app.target,
        cloudflare=zone is not None,
    )
    db.commit()
    jobs.dispatch(job_id)
    return ra.domain_out(domain)


@router.post(BASE + "/{app_id}/domains/{domain_id}/check", status_code=202)
def check_domain(app_id: str, domain_id: str, access: Admin, db: DbSession) -> dict:
    """Cloud targets: look for the DNS records / validation again (after adding them by hand)."""
    app = deployments.get_app(db, access.project.id, app_id)
    domain = db.get(Domain, domain_id)
    if domain is None or domain.app_id != app.id or domain.target_type != "cloud_app":
        raise not_found("Domain")
    job_id = cloud_deploy.enqueue_domain_check(db, domain, access.user.id)
    db.commit()
    jobs.dispatch(job_id)
    return {"job_id": job_id}


@router.delete(BASE + "/{app_id}/domains/{domain_id}")
def remove_domain(app_id: str, domain_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    domain = db.get(Domain, domain_id)
    if domain is None or domain.app_id != app.id:
        raise not_found("Domain")
    if domain.target_type == "cloud_app":
        warnings = cloud_deploy.remove_domain(db, app, domain)
        hostname = domain.hostname
        db.delete(domain)
        audit.record(
            db,
            "app.domain_remove",
            request=request,
            user_id=access.user.id,
            project_id=app.project_id,
            app_id=app.id,
            hostname=hostname,
        )
        db.commit()
        return {"ok": True, "warnings": warnings}
    ra.remove_hostname(db, domain.id, request=request, user_id=access.user.id)
    _reroute(db, app, access.user.id)
    return {"ok": True}


# --- GitHub webhook (no bearer auth: HMAC of the raw body with the app's secret) ------------------

WEBHOOK_MAX_BODY = 5 * 2**20  # push payloads are a few KB; GitHub caps any payload at 25 MB


async def read_body_capped(request: Request, limit: int) -> bytes:
    """The request body, but at most `limit + 1` bytes are read (longer means too large)."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            break
    return bytes(data[: limit + 1])


@router.post("/hooks/github/{app_id}")
async def github_webhook(app_id: str, request: Request, db: DbSession) -> Any:
    # Async only to stream the capped body; the DB and Redis work runs in the threadpool (A-138).
    app = await run_in_threadpool(db.get, App, app_id)
    if app is None:
        raise not_found("App")
    body = await read_body_capped(request, WEBHOOK_MAX_BODY)
    if len(body) > WEBHOOK_MAX_BODY:
        raise ApiError(413, "payload_too_large", f"Webhook payloads are limited to {WEBHOOK_MAX_BODY // 2**20} MB")
    if request.headers.get("X-GitHub-Event") == github_actions.REPORT_EVENT:
        return await run_in_threadpool(_actions_report, db, app, request.headers, body)
    return await run_in_threadpool(_github_delivery, db, app, request.headers, body)


def _actions_report(db: Session, app: App, headers: Any, body: bytes) -> Any:
    """docs/CLOUD.md "C3": a GitHub Actions run of the app's workflow reports its result, signed with GitHub's
    OIDC token for this app (no shared secret)."""
    authorization = headers.get("Authorization") or ""
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "bad_signature", "A GitHub Actions report needs its OIDC token")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise ApiError(400, "invalid_payload", "The body is not JSON") from None
    dep = github_actions.record_report(db, app, authorization, payload)
    allowed, retry_after = rate_limit.hit(f"rl:hook:{app.id}", deployments.WEBHOOK_LIMIT, deployments.WEBHOOK_WINDOW_S)
    if not allowed:
        raise ApiError(429, "rate_limited", "Too many reports; try again later", {"retry_after": retry_after})
    if dep is None:
        return {"ignored": True}
    audit.record(db, "app.deploy", project_id=app.project_id, app_id=app.id, deployment_id=dep.id, trigger="github")
    job = None
    if dep.status == "live":  # old artifacts go, like after a deploy from this PC
        job = jobs.enqueue(db, type="app.cloud_prune", params={"app_id": app.id}, project_id=app.project_id)
    db.commit()
    _dispatch(job)
    return {"deployment_id": dep.id, "status": dep.status}


def _github_delivery(db: Session, app: App, headers: Any, body: bytes) -> Any:
    if not deployments.verify_signature(deployments.webhook_secret(app), body, headers.get("X-Hub-Signature-256")):
        raise ApiError(401, "bad_signature", "X-Hub-Signature-256 does not match")
    # Only signed deliveries count (A-138): unsigned junk must not use up the app's real pushes.
    allowed, retry_after = rate_limit.hit(f"rl:hook:{app.id}", deployments.WEBHOOK_LIMIT, deployments.WEBHOOK_WINDOW_S)
    if not allowed:
        raise ApiError(
            429, "rate_limited", "Too many webhook deliveries; try again later", {"retry_after": retry_after}
        )
    project = db.get(Project, app.project_id)
    owner = db.get(User, project.owner_id) if project else None
    if owner is None or not owner.is_active:
        # A-023: a disabled account's pushes must not keep deploying new code on this PC.
        raise ApiError(403, "account_disabled", "The account that owns this project has been disabled")
    event = headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"ok": True}
    if event != "push":
        return {"ignored": True}
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise ApiError(400, "invalid_payload", "The body is not JSON") from None
    dep, job = deployments.handle_push(db, app, payload if isinstance(payload, dict) else {})
    if dep is None:
        return {"ignored": True}
    audit.record(db, "app.deploy", project_id=app.project_id, app_id=app.id, deployment_id=dep.id, trigger="webhook")
    db.commit()
    _dispatch(job)
    return JSONResponse({"deployment_id": dep.id}, status_code=202)
