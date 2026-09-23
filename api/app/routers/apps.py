"""Apps, deployments, app hostnames and the GitHub webhook (docs/DEPLOYMENTS.md "API")."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.crypto import encrypt_secret
from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError, forbidden, not_found
from app.models import App, Deployment, Domain
from app.services import audit, deployments, github, jobs, rate_limit
from app.services import remote_access as ra

router = APIRouter(tags=["apps"])

Viewer = Annotated[ProjectAccess, Depends(require_role("viewer"))]
Developer = Annotated[ProjectAccess, Depends(require_role("developer"))]
Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]

BASE = "/projects/{project_id}/apps"
_COMMAND = Field(default=None, max_length=500)
_BRANCH_RE = re.compile(r"^[^\s~^:?*\[\\]+$")


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
        if value is not None and (not _BRANCH_RE.match(value) or value.startswith("-")):
            raise ValueError("is not a valid branch name")
        return value

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
        port=deployments.allocate_port(db),
        created_by_id=access.user.id,
        github_connection_user_id=access.user.id if body.use_github_connection else None,
    )
    _check_preset(app)
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
    )
    if app.database_access:
        _audit_database_access(db, request, access, app)
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
    changed = sorted(body.model_fields_set)
    if "database_access" in changed:
        _check_database_access(access, body.database_access and not app.database_access)
    access_before = app.database_access
    if "repo_url" in changed and body.repo_url and body.repo_url != app.repo_url and app.github_connection_user_id:
        # The webhook belongs to the old repository; only the connection's owner may point it elsewhere.
        github.delete_hook(db, app)
        if app.github_connection_user_id != access.user.id:
            app.github_connection_user_id = None
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
        elif field == "database_access":
            app.database_access = bool(value)
        elif value is not None or field in (
            "install_command",
            "build_command",
            "start_command",
            "output_dir",
            "container_port",
        ):
            setattr(app, field, value)
    _check_preset(app)
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
    db.commit()
    return deployments.app_out(db, app)


@router.delete(BASE + "/{app_id}")
def delete_app(app_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    for domain in deployments.app_domains(db, app.id):
        ra.remove_hostname(db, domain.id, request=request, user_id=access.user.id)  # DNS + ingress; commits
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
    return {"job_id": job.id}


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
        if value is not None and (not _BRANCH_RE.match(value) or value.startswith("-")):
            raise ValueError("is not a valid branch name")
        return value


@router.post(BASE + "/{app_id}/deploy", status_code=202)
def deploy(app_id: str, request: Request, access: Developer, db: DbSession, body: DeployBody | None = None) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
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
            stmt = stmt.where(Deployment.created_at <= anchor.created_at, Deployment.id != anchor.id)
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
def runtime_logs(app_id: str, access: Viewer, db: DbSession, tail: Annotated[int, Query(ge=1, le=500)] = 200) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    live = db.get(Deployment, app.live_deployment_id) if app.live_deployment_id else None
    lines, _ = deployments.runtime_logs(app, tail)
    return {"lines": lines, "container": live.container_name if live else None}


# --- hostnames -----------------------------------------------------------------------------------


class HostnameBody(BaseModel):
    hostname: str = Field(min_length=1, max_length=300)
    overwrite: bool = False


def _reroute(db: DbSession, app: App, user_id: str) -> None:
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


@router.delete(BASE + "/{app_id}/domains/{domain_id}")
def remove_domain(app_id: str, domain_id: str, request: Request, access: Admin, db: DbSession) -> dict:
    app = deployments.get_app(db, access.project.id, app_id)
    domain = db.get(Domain, domain_id)
    if domain is None or domain.app_id != app.id:
        raise not_found("Domain")
    ra.remove_hostname(db, domain.id, request=request, user_id=access.user.id)
    _reroute(db, app, access.user.id)
    return {"ok": True}


# --- GitHub webhook (no bearer auth: HMAC of the raw body with the app's secret) ------------------


@router.post("/hooks/github/{app_id}")
async def github_webhook(app_id: str, request: Request, db: DbSession) -> Any:
    app = db.get(App, app_id)
    if app is None:
        raise not_found("App")
    allowed, retry_after = rate_limit.hit(f"rl:hook:{app_id}", deployments.WEBHOOK_LIMIT, deployments.WEBHOOK_WINDOW_S)
    if not allowed:
        raise ApiError(
            429, "rate_limited", "Too many webhook deliveries; try again later", {"retry_after": retry_after}
        )
    body = await request.body()
    if not deployments.verify_signature(
        deployments.webhook_secret(app), body, request.headers.get("X-Hub-Signature-256")
    ):
        raise ApiError(401, "bad_signature", "X-Hub-Signature-256 does not match")
    event = request.headers.get("X-GitHub-Event", "")
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
