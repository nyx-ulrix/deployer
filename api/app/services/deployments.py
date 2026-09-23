"""Apps & deployments - push-to-deploy orchestration (docs/DEPLOYMENTS.md).

The API side (routers/apps.py) creates `apps` / `deployments` rows and enqueues jobs; the worker
runs them through `app_runner.DockerCli`:

- `app.deploy {deployment_id}`: clone -> build -> run -> health wait -> route (Caddy) -> stop the
  previous container -> prune images. One deploy at a time per app: a deployment created while
  another one is active stays `queued` without a job and is started by `enqueue_next` when the
  active one ends (the scheduler sweep covers worker crashes).
- `app.remove {app_id, slug}`: containers, images and the Caddy file of a deleted app.
- `app.route {app_id}`: rewrite the Caddy file (hostname added/removed) and reload.

Secrets: env vars are `encrypt_json`, the repo token and webhook secret `encrypt_secret`; none of
them is ever written to a deployment log (git/docker output is redacted before it is stored).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt_json, decrypt_secret, encrypt_json, encrypt_secret, random_token
from app.errors import ApiError, conflict, not_found
from app.models import ApiKey, App, DataSource, Deployment, Domain, Job, utcnow
from app.redis_client import get_redis
from app.serializers import iso
from app.services import jobs
from app.services.app_runner import DockerCli, DockerError, get_docker
from app.services.connections import load_config, parse_mongo_uri, redact, sql_app_uri
from app.services.instance_settings import public_url
from app.services.remote_access import domain_out

log = logging.getLogger(__name__)

PRESETS = ("static", "node", "python", "dockerfile")
PRESET_PORTS = {"static": 80, "node": 3000, "python": 8000}
PORT_MIN, PORT_MAX = 8100, 8199
IMAGE_PREFIX = "deployer-app"
KEEP_IMAGES = 5
LOG_CAP = 1024 * 1024
LOG_FLUSH_S = 2.0
HEALTH_TIMEOUT_S = 60
ACTIVE_STATUSES = ("queued", "building", "deploying")
FINAL_STATUSES = ("live", "failed", "cancelled", "superseded")
LOGS_KEEP = 500
LOGS_POLL_S = 10
WEBHOOK_LIMIT, WEBHOOK_WINDOW_S = 6, 60
PLACEHOLDER_FILE = "_empty.caddy"

_SLUG_MAX = 40  # container name = deployer-app-<slug>-<8 chars> stays well under Docker's limits


# =============================================================================================
# helpers
# =============================================================================================


def app_slug(db: Session, project_id: str, name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:_SLUG_MAX].rstrip("-") or "app"
    taken = set(db.scalars(select(App.slug).where(App.project_id == project_id)))
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def allocate_port(db: Session) -> int:
    used = set(db.scalars(select(App.port)))
    for port in range(PORT_MIN, PORT_MAX + 1):
        if port not in used:
            return port
    raise conflict("no_ports_left", f"All app ports ({PORT_MIN}-{PORT_MAX}) are in use")


def internal_port(app: App) -> int:
    return PRESET_PORTS.get(app.preset) or int(app.container_port or 0)


def image_tag(app_id: str, deployment_id: str) -> str:
    return f"{IMAGE_PREFIX}/{app_id}:{deployment_id}"


def container_name(app: App, deployment_id: str) -> str:
    return f"deployer-app-{app.slug}-{deployment_id[:8]}"


def logs_key(app_id: str) -> str:
    return f"apps:logs:{app_id}"


# --- secrets -------------------------------------------------------------------------------------


def env_of(app: App) -> dict[str, str]:
    value = decrypt_json(app.env_encrypted) if app.env_encrypted else {}
    return {str(k): str(v) for k, v in (value or {}).items()}


def set_env(app: App, env: dict[str, str]) -> None:
    app.env_encrypted = encrypt_json(dict(env))


def repo_token(app: App) -> str | None:
    return decrypt_secret(app.repo_token_encrypted) if app.repo_token_encrypted else None


def webhook_secret(app: App) -> str:
    return decrypt_secret(app.webhook_secret_encrypted)


def rotate_webhook_secret(app: App) -> str:
    secret = random_token(32)
    app.webhook_secret_encrypted = encrypt_secret(secret)
    return secret


def webhook_url(db: Session, app: App) -> str:
    return f"{public_url(db)}/v1/hooks/github/{app.id}"


def check_api_key(db: Session, project_id: str, api_key_id: str | None) -> None:
    if api_key_id is None:
        return
    key = db.get(ApiKey, api_key_id)
    if key is None or key.project_id != project_id or key.revoked_at is not None:
        raise ApiError(422, "validation_error", "API key not found in this project", {"field": "api_key_id"})
    if not key.secret_encrypted:
        raise ApiError(
            422, "validation_error", "This API key has no stored secret; create a new key", {"field": "api_key_id"}
        )


# --- serializers ---------------------------------------------------------------------------------


def local_url(db: Session, app: App) -> str:
    host = (urlsplit(public_url(db)).hostname or "localhost").lower()
    if host == "127.0.0.1":
        host = "localhost"
    return f"http://{host}:{app.port}"


def app_domains(db: Session, app_id: str) -> list[Domain]:
    return list(db.scalars(select(Domain).where(Domain.app_id == app_id).order_by(Domain.created_at)))


def deployment_out(dep: Deployment, *, with_log: bool = False) -> dict:
    out = {
        "id": dep.id,
        "app_id": dep.app_id,
        "status": dep.status,
        "trigger": dep.trigger,
        "commit_sha": dep.commit_sha,
        "commit_message": dep.commit_message,
        "branch": dep.branch,
        "image_tag": dep.image_tag,
        "created_at": iso(dep.created_at),
        "started_at": iso(dep.started_at),
        "finished_at": iso(dep.finished_at),
        "error": dep.error,
        "rollback_of": dep.rollback_of,
        "job_id": dep.job_id,
    }
    if with_log:
        out["log"] = dep.log or ""
    return out


def app_out(db: Session, app: App) -> dict:
    domains = app_domains(db, app.id)
    live = db.get(Deployment, app.live_deployment_id) if app.live_deployment_id else None
    return {
        "id": app.id,
        "project_id": app.project_id,
        "name": app.name,
        "slug": app.slug,
        "repo_url": app.repo_url,
        "branch": app.branch,
        "root_dir": app.root_dir,
        "preset": app.preset,
        "install_command": app.install_command,
        "build_command": app.build_command,
        "start_command": app.start_command,
        "output_dir": app.output_dir,
        "container_port": app.container_port,
        "env_keys": sorted(env_of(app)),
        "has_repo_token": app.repo_token_encrypted is not None,
        "api_key_id": app.api_key_id,
        "database_access": bool(app.database_access),
        "port": app.port,
        "local_url": local_url(db, app),
        "urls": [f"https://{d.hostname}" for d in domains if d.status == "active"],
        "live_deployment": deployment_out(live) if live else None,
        "domains": [domain_out(d) for d in domains],
        "created_at": iso(app.created_at),
        "updated_at": iso(app.updated_at),
    }


# =============================================================================================
# deployment lifecycle (API side)
# =============================================================================================


def get_app(db: Session, project_id: str, app_id: str) -> App:
    app = db.get(App, app_id)
    if app is None or app.project_id != project_id:
        raise not_found("App")
    return app


def get_deployment(db: Session, app: App, deployment_id: str) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if dep is None or dep.app_id != app.id:
        raise not_found("Deployment")
    return dep


def _enqueue_job(db: Session, app: App, dep: Deployment) -> Job:
    job = jobs.enqueue(
        db,
        type="app.deploy",
        params={"deployment_id": dep.id, "key": app.id},
        project_id=app.project_id,
        created_by_id=dep.created_by_id,
    )
    dep.job_id = job.id
    return job


def start_deployment(
    db: Session,
    app: App,
    *,
    trigger: str,
    user_id: str | None,
    branch: str | None = None,
    commit_sha: str | None = None,
    commit_message: str | None = None,
    rollback_of: Deployment | None = None,
) -> tuple[Deployment, Job | None]:
    """Adds a deployment; gives it a job unless another deploy of this app is active (then it waits
    in `queued` and `enqueue_next` starts it). Caller commits and dispatches the returned job."""
    dep = Deployment(
        app_id=app.id,
        status="queued",
        trigger=trigger,
        branch=branch or app.branch,
        commit_sha=commit_sha,
        commit_message=(commit_message or None) and commit_message[:200],
        created_by_id=user_id,
        log="",
    )
    if rollback_of is not None:
        dep.rollback_of = rollback_of.id
        dep.image_tag = rollback_of.image_tag
        dep.commit_sha, dep.commit_message, dep.branch = (
            rollback_of.commit_sha,
            rollback_of.commit_message,
            rollback_of.branch,
        )
    db.add(dep)
    db.flush()
    job = None
    if jobs.active_job(db, "app.deploy", key=app.id) is None:
        job = _enqueue_job(db, app, dep)
    return dep, job


def enqueue_next(factory: jobs.SessionFactory, app_id: str, *, finishing_job_id: str | None = None) -> str | None:
    """Starts the oldest waiting deployment of an app when no deploy job is active (other than the
    one that is just finishing and calls this from its handler). Commits."""
    with factory() as db:
        app = db.get(App, app_id)
        active = jobs.active_job(db, "app.deploy", key=app_id)
        if app is None or (active is not None and active.id != finishing_job_id):
            return None
        dep = db.scalar(
            select(Deployment)
            .where(Deployment.app_id == app_id, Deployment.status == "queued", Deployment.job_id.is_(None))
            .order_by(Deployment.created_at)
        )
        if dep is None:
            return None
        job = _enqueue_job(db, app, dep)
        db.commit()
    jobs.dispatch(job.id)
    return job.id


def cancel_deployment(db: Session, dep: Deployment) -> Deployment:
    if dep.status == "queued":
        dep.status, dep.finished_at = "cancelled", utcnow()
        if dep.job_id and (job := db.get(Job, dep.job_id)) is not None and job.status in jobs.ACTIVE_STATUSES:
            jobs.request_cancel(db, job)
    elif dep.status in ("building", "deploying"):
        if dep.job_id and (job := db.get(Job, dep.job_id)) is not None:
            jobs.request_cancel(db, job)
    else:
        raise conflict("not_cancellable", f"This deployment is {dep.status}")
    return dep


def rollback(db: Session, app: App, old: Deployment, *, user_id: str) -> tuple[Deployment, Job | None]:
    if not old.image_tag or old.status not in ("live", "superseded"):
        raise conflict(
            "not_rollbackable", "Only a previous successful deployment whose image is still kept can be re-deployed"
        )
    return start_deployment(db, app, trigger="rollback", user_id=user_id, rollback_of=old)


# --- GitHub webhook ------------------------------------------------------------------------------


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[len("sha256=") :].strip().lower(), digest)


def handle_push(db: Session, app: App, payload: dict) -> tuple[Deployment | None, Job | None]:
    """A `push` event: (deployment, job) for the app's branch, (None, None) when ignored. A push
    while a deployment is still queued replaces its commit instead of adding another."""
    if payload.get("ref") != f"refs/heads/{app.branch}" or payload.get("deleted"):
        return None, None
    sha = str(payload.get("after") or "")[:40] or None
    head = payload.get("head_commit") or {}
    message = str(head.get("message") or "").splitlines()[0][:200] if head.get("message") else None
    waiting = db.scalar(
        select(Deployment)
        .where(Deployment.app_id == app.id, Deployment.status == "queued")
        .order_by(Deployment.created_at.desc())
    )
    if waiting is not None:
        waiting.commit_sha, waiting.commit_message, waiting.branch = sha, message, app.branch
        waiting.trigger = "webhook"
        return waiting, None
    return start_deployment(db, app, trigger="webhook", user_id=None, commit_sha=sha, commit_message=message)


def runtime_logs(app: App, tail: int) -> tuple[list[str], str | None]:
    try:
        lines = get_redis().lrange(logs_key(app.id), -max(1, tail), -1)
    except Exception:  # noqa: BLE001
        lines = []
    return list(lines), None


# =============================================================================================
# Caddy
# =============================================================================================


def apps_dir() -> Path:
    return Path(get_settings().caddy_apps_dir)


def render_caddyfile(app_id: str, port: int, container: str, upstream_port: int, hostnames: list[str]) -> str:
    upstream = f"\treverse_proxy {container}:{upstream_port}"
    lines = [f"# apps/{app_id}.caddy - generated by Deployer, do not edit", f":{port} {{", upstream, "}"]
    for host in hostnames:
        lines += [f"http://{host}:8081 {{", upstream, "}"]
    return "\n".join(lines) + "\n"


def write_caddy_file(app_id: str, text: str | None) -> None:
    """Writes (atomically) or removes `<apps_dir>/<app_id>.caddy`."""
    directory = apps_dir()
    target = directory / f"{app_id}.caddy"
    if text is None:
        target.unlink(missing_ok=True)
        return
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".app-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def ensure_apps_dir() -> None:
    """Worker startup: the directory (and a harmless placeholder so `import apps/*.caddy` always has a
    match, whatever the Caddy version does with an empty glob)."""
    try:
        directory = apps_dir()
        directory.mkdir(parents=True, exist_ok=True)
        placeholder = directory / PLACEHOLDER_FILE
        if not placeholder.exists():
            placeholder.write_text("# Deployer writes one <app_id>.caddy per deployed app here.\n", encoding="utf-8")
    except OSError:
        log.warning("Could not prepare %s (app routing unavailable)", get_settings().caddy_apps_dir, exc_info=True)


def route_app(cli: DockerCli, db: Session, app: App, live: Deployment | None) -> None:
    """Points the app's Caddy file at `live` (or removes it) and reloads Caddy."""
    if live is not None and live.container_name:
        hostnames = [d.hostname for d in app_domains(db, app.id) if d.status == "active"]
        write_caddy_file(app.id, render_caddyfile(app.id, app.port, live.container_name, internal_port(app), hostnames))
    else:
        write_caddy_file(app.id, None)
    cli.caddy_reload()


# =============================================================================================
# Dockerfile generation
# =============================================================================================

_NGINX_CONF = (
    "server { listen 80; root /usr/share/nginx/html; index index.html; "
    "location / { try_files $uri $uri/ /index.html; } }"
)


def generate_dockerfile(app: App) -> str | None:
    """The build recipe for the static/node/python presets; None for `dockerfile` (the repo's own)."""
    if app.preset == "dockerfile":
        return None
    lines: list[str] = []
    if app.preset == "static":
        install = app.install_command or "if [ -f package.json ]; then npm ci; fi"
        build = app.build_command or (
            "if [ -f package.json ] && node -e \"process.exit(require('./package.json').scripts?.build ? 0 : 1)\"; "
            "then npm run build; fi"
        )
        if app.output_dir:
            collect = f"mkdir -p /out && cp -r {json.dumps(app.output_dir.rstrip('/') or '.')}/. /out/"
        else:
            collect = (
                "mkdir -p /out && for d in dist build out public .; "
                'do if [ -d "$d" ]; then cp -r "$d/." /out/; break; fi; done'
            )
        lines += [
            "FROM node:22-alpine AS build",
            "WORKDIR /app",
            "COPY . .",
            f"RUN {install}",
            f"RUN {build}",
            f"RUN {collect}",
            "FROM nginx:1.27-alpine",
            f"RUN printf '%s\\n' {_shell_quote(_NGINX_CONF)} > /etc/nginx/conf.d/default.conf",
            "COPY --from=build /out /usr/share/nginx/html",
            "EXPOSE 80",
        ]
    elif app.preset == "node":
        lines += ["FROM node:22-alpine", "WORKDIR /app", "COPY . .", f"RUN {app.install_command or 'npm ci'}"]
        if app.build_command:
            lines.append(f"RUN {app.build_command}")
        lines += ["ENV PORT=3000", "EXPOSE 3000", f"CMD {json.dumps(['sh', '-c', app.start_command or 'npm start'])}"]
    elif app.preset == "python":
        lines += [
            "FROM python:3.12-slim",
            "WORKDIR /app",
            "COPY . .",
            f"RUN {app.install_command or 'pip install --no-cache-dir -r requirements.txt'}",
        ]
        if app.build_command:
            lines.append(f"RUN {app.build_command}")
        lines += ["ENV PORT=8000", "EXPOSE 8000", f"CMD {json.dumps(['sh', '-c', app.start_command or ''])}"]
    return "\n".join(lines) + "\n"


def _shell_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


# =============================================================================================
# deploy job
# =============================================================================================


class _DeployLog:
    """Deployment log kept in memory (tail of LOG_CAP bytes), flushed to the row every LOG_FLUSH_S."""

    def __init__(self, factory: jobs.SessionFactory, deployment_id: str, secrets: list[str | None]):
        self.factory, self.deployment_id, self.secrets = factory, deployment_id, secrets
        self.lines: list[str] = []
        self.size = 0
        self.last_flush = 0.0

    def write(self, line: str) -> None:
        line = redact(line, self.secrets, limit=None)
        self.lines.append(line)
        self.size += len(line) + 1
        while self.size > LOG_CAP and len(self.lines) > 1:
            self.size -= len(self.lines.pop(0)) + 1
        if time.monotonic() - self.last_flush >= LOG_FLUSH_S:
            self.flush()

    def step(self, title: str) -> None:
        self.write(f"==> {title}")
        self.flush()

    def flush(self) -> None:
        self.last_flush = time.monotonic()
        with self.factory() as db:
            dep = db.get(Deployment, self.deployment_id)
            if dep is not None:
                dep.log = "\n".join(self.lines)
                db.commit()


def _update(factory: jobs.SessionFactory, deployment_id: str, **values) -> None:
    with factory() as db:
        dep = db.get(Deployment, deployment_id)
        if dep is not None:
            for key, value in values.items():
                setattr(dep, key, value)
            db.commit()


def _docker_failure(exc: DockerError, secrets: list[str | None]) -> str:
    tail = "\n".join(exc.output.strip().splitlines()[-5:])
    text = f"{exc}" + (f"\n{tail}" if tail else "")
    return redact(text, secrets, limit=2000)


def _checkout(ctx: jobs.JobContext, cli: DockerCli, app: App, dep: Deployment, workdir: str, log_: _DeployLog) -> str:
    token = repo_token(app)
    checkout = os.path.join(workdir, "src")
    log_.step("Cloning")
    log_.write(f"git clone --depth 1 --branch {dep.branch} {app.repo_url}")
    cli.git_clone(app.repo_url, dep.branch, checkout, token=token, on_line=log_.write)
    sha, message = cli.git_head(checkout)
    if dep.commit_sha and sha != dep.commit_sha:
        log_.write(f"Checking out {dep.commit_sha}")
        cli.git_checkout(checkout, dep.commit_sha, token=token, on_line=log_.write)
        sha, message = cli.git_head(checkout)
    log_.write(f"HEAD is {sha} {message}")
    _update(ctx.session_factory, dep.id, commit_sha=sha[:40], commit_message=message[:200] or None)
    return checkout


def _build(
    ctx: jobs.JobContext, cli: DockerCli, app: App, dep: Deployment, workdir: str, checkout: str, log_: _DeployLog
) -> str:
    context = os.path.normpath(os.path.join(checkout, app.root_dir or "."))
    if not (context == checkout or context.startswith(checkout + os.sep)):
        raise jobs.JobError("root_dir must stay inside the repository")
    if not os.path.isdir(context):
        raise jobs.JobError(f"root_dir '{app.root_dir}' does not exist in the repository")
    generated = generate_dockerfile(app)
    if generated is None:
        dockerfile = os.path.join(context, "Dockerfile")
        if not os.path.isfile(dockerfile):
            raise jobs.JobError(f"No Dockerfile in '{app.root_dir}'")
    else:
        dockerfile = os.path.join(workdir, "Dockerfile.deployer")
        with open(dockerfile, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(generated)
        log_.write("Generated Dockerfile:")
        for line in generated.rstrip().splitlines():
            log_.write(f"    {line}")
    tag = image_tag(app.id, dep.id)
    log_.step("Building")
    cli.build(context, dockerfile, tag, on_line=log_.write)
    _update(ctx.session_factory, dep.id, image_tag=tag)
    return tag


def _runtime_env(db: Session, app: App) -> dict[str, str]:
    env = env_of(app)
    env["PORT"] = str(internal_port(app))
    env["DEPLOYER_URL"] = f"{public_url(db)}/v1"
    env["DEPLOYER_PROJECT_ID"] = app.project_id
    if app.api_key_id:
        key = db.get(ApiKey, app.api_key_id)
        if key is not None and key.secret_encrypted and key.revoked_at is None:
            env["DEPLOYER_API_KEY"] = decrypt_secret(key.secret_encrypted)
    return env


def env_prefix(source_name: str) -> str:
    return "DEPLOYER_DB_" + re.sub(r"[^A-Z0-9]", "_", source_name.upper()) + "_"


def database_env(db: Session, app: App) -> tuple[dict[str, str], list[str]]:
    """`DEPLOYER_DB_<NAME>_*` for the project's managed sources on this server (docs/DEPLOYMENTS.md
    "Database access"), plus log notes. Host/port are the in-network names the API itself uses."""
    env: dict[str, str] = {}
    notes: list[str] = []
    sources = db.scalars(
        select(DataSource)
        .where(
            DataSource.project_id == app.project_id,
            DataSource.mode == "managed",
            DataSource.deleted_at.is_(None),
        )
        .order_by(DataSource.name)
    )
    for ds in sources:
        if ds.device_id:
            notes.append(f"Data source '{ds.name}' is on a host device and is not reachable from apps")
            continue
        config = load_config(ds)
        prefix = env_prefix(ds.name)
        database = str(config.get("database") or ds.database_name)
        if ds.kind == "sql":
            env[prefix + "HOST"] = str(config.get("host") or "")
            env[prefix + "PORT"] = str(config.get("port") or 3306)
            env[prefix + "USER"] = str(config.get("username") or "")
            env[prefix + "PASSWORD"] = str(config.get("password") or "")
            env[prefix + "URL"] = sql_app_uri(ds.engine, config)
        else:
            parsed = parse_mongo_uri(config.get("uri", ""))
            user = quote(str(config.get("username") or parsed["username"] or ""), safe="")
            pw = quote(str(config.get("password") or ""), safe="")
            name = quote(database, safe="")
            env[prefix + "URL"] = (
                f"mongodb://{user}:{pw}@{parsed['host']}:{parsed['port']}/{name}"
                f"?authSource={name}&directConnection=true"
            )
        env[prefix + "DATABASE"] = database
    return env, notes


def _prune_images(db: Session, cli: DockerCli, app: App, log_: _DeployLog) -> None:
    deps = list(
        db.scalars(
            select(Deployment)
            .where(Deployment.app_id == app.id, Deployment.image_tag.is_not(None))
            .order_by(Deployment.created_at.desc())
        )
    )
    keep = {d.image_tag for d in deps[:KEEP_IMAGES]}
    for dep in deps[KEEP_IMAGES:]:
        if dep.image_tag not in keep:
            log_.write(f"Removing old image {dep.image_tag}")
            cli.remove_image(dep.image_tag)
        dep.image_tag = None


@jobs.job_handler("app.deploy")
def _job_deploy(ctx: jobs.JobContext) -> dict:
    factory = ctx.session_factory
    deployment_id = str(ctx.params["deployment_id"])
    cli = get_docker()
    with factory() as db:
        dep = db.get(Deployment, deployment_id)
        app = db.get(App, dep.app_id) if dep is not None else None
        if dep is None or app is None:
            return {"skipped": "deployment missing"}
        if dep.status != "queued":
            return {"skipped": dep.status}
        dep.status, dep.started_at, dep.job_id = "building", utcnow(), ctx.job_id
        db.commit()
        secrets: list[str | None] = [repo_token(app), *env_of(app).values()]
    log_ = _DeployLog(factory, dep.id, secrets)
    workdir = tempfile.mkdtemp(prefix="deployer-build-", dir=get_settings().app_build_dir or None)
    new_container: str | None = None
    try:
        try:
            if dep.trigger == "rollback" and dep.image_tag:
                tag = dep.image_tag
                log_.step(f"Reusing image {tag} (rollback of {dep.rollback_of})")
            else:
                ctx.progress(0.05, "Cloning", force=True)
                checkout = _checkout(ctx, cli, app, dep, workdir, log_)
                ctx.check_cancelled()
                ctx.progress(0.2, "Building", force=True)
                tag = _build(ctx, cli, app, dep, workdir, checkout, log_)
            ctx.check_cancelled()
            ctx.progress(0.7, "Starting", force=True)
            log_.step("Starting")
            name = container_name(app, dep.id)
            with factory() as db:
                db_env, notes = database_env(db, app) if app.database_access else ({}, [])
                env = {**db_env, **_runtime_env(db, app)}  # the app's own variables win
                dep_row = db.get(Deployment, dep.id)
                dep_row.status, dep_row.container_name = "deploying", name
                db.commit()
            secrets.extend(v for k, v in db_env.items() if k.endswith(("_PASSWORD", "_URL")))
            for note in notes:
                log_.write(note)
            if db_env:
                log_.write("Database variables: " + ", ".join(sorted(db_env)))
            cli.remove_container(name)  # a stale container of the same name from an interrupted run
            cli.run_container(name, tag, labels={"deployer.app": app.id, "deployer.deployment": dep.id}, env=env)
            new_container = name
            if app.database_access:
                cli.network_connect(get_settings().app_db_network, name)
                log_.write("Connected to the project's databases network")
            port = internal_port(app)
            log_.write(f"Waiting for {name}:{port} to accept connections")
            if not cli.wait_tcp(name, port, HEALTH_TIMEOUT_S):
                for line in cli.logs(name, since=None, tail=50):
                    log_.write(f"    {line}")
                raise jobs.JobError(
                    f"The container did not accept connections on port {port} within {HEALTH_TIMEOUT_S} s"
                )
            ctx.check_cancelled()
            ctx.progress(0.85, "Routing", force=True)
            log_.step("Routing")
            with factory() as db:
                app_row = db.get(App, app.id)
                dep_row = db.get(Deployment, dep.id)
                previous = db.get(Deployment, app_row.live_deployment_id) if app_row.live_deployment_id else None
                route_app(cli, db, app_row, dep_row)
                dep_row.status, dep_row.finished_at = "live", utcnow()
                app_row.live_deployment_id = dep_row.id
                if previous is not None and previous.id != dep_row.id:
                    previous.status = "superseded"
                old_container = previous.container_name if previous is not None else None
                db.commit()
            new_container = None  # live now: no longer ours to clean up on failure
            ctx.progress(0.95, "Cleaning up", force=True)
            log_.step("Cleaning up")
            if old_container and old_container != name:
                log_.write(f"Stopping {old_container}")
                cli.remove_container(old_container)
            with factory() as db:
                _prune_images(db, cli, db.get(App, app.id), log_)
                db.commit()
            log_.write("Done")
        except DockerError as exc:
            raise jobs.JobError(_docker_failure(exc, secrets)) from exc
    except jobs.JobCancelled:
        log_.write("Cancelled")
        if new_container:
            cli.remove_container(new_container)
        _update(factory, dep.id, status="cancelled", finished_at=utcnow())
        raise
    except Exception as exc:
        message = redact(jobs._error_text(exc), secrets, limit=2000)
        log_.write(f"ERROR: {message}")
        if new_container:
            cli.remove_container(new_container)
        _update(factory, dep.id, status="failed", error=message, finished_at=utcnow())
        raise jobs.JobError(message) from exc
    finally:
        log_.flush()
        shutil.rmtree(workdir, ignore_errors=True)
        try:
            enqueue_next(factory, app.id, finishing_job_id=ctx.job_id)
        except Exception:  # noqa: BLE001 - the scheduler sweep retries
            log.exception("could not start the next deployment of app %s", app.id)
    return {"deployment_id": dep.id, "status": "live"}


@jobs.job_handler("app.route")
def _job_route(ctx: jobs.JobContext) -> dict:
    app_id = str(ctx.params["app_id"])
    with ctx.session_factory() as db:
        app = db.get(App, app_id)
        if app is None:
            return {"skipped": "app missing"}
        live = db.get(Deployment, app.live_deployment_id) if app.live_deployment_id else None
        route_app(get_docker(), db, app, live if live and live.status == "live" else None)
    return {"app_id": app_id}


@jobs.job_handler("app.remove")
def _job_remove(ctx: jobs.JobContext) -> dict:
    """Containers, images and the Caddy file of an app whose row is already gone."""
    app_id = str(ctx.params["app_id"])
    cli = get_docker()
    removed = 0
    for row in cli.list_containers():
        if row["app"] == app_id:
            cli.remove_container(row["name"])
            removed += 1
    for tag in cli.list_images(f"{IMAGE_PREFIX}/{app_id}"):
        cli.remove_image(f"{IMAGE_PREFIX}/{app_id}:{tag}")
    write_caddy_file(app_id, None)
    cli.caddy_reload()
    return {"containers": removed}


# =============================================================================================
# scheduler (worker leader)
# =============================================================================================


def scheduler_tick(factory: jobs.SessionFactory) -> None:
    _sweep_queued(factory)
    try:
        _remove_orphans(factory, get_docker())
    except DockerError as exc:
        log.warning("orphan cleanup skipped: %s", exc)


def _sweep_queued(factory: jobs.SessionFactory) -> None:
    """Queued deployments without a job get one; those whose job died are closed."""
    with factory() as db:
        waiting = list(db.scalars(select(Deployment).where(Deployment.status == "queued")))
        app_ids: set[str] = set()
        for dep in waiting:
            if dep.job_id is None:
                app_ids.add(dep.app_id)
                continue
            job = db.get(Job, dep.job_id)
            if job is None or job.status in jobs.FINAL_STATUSES:
                dep.status = "cancelled" if job is not None and job.status == "cancelled" else "failed"
                dep.error = dep.error or (job.error if job is not None else "The deploy job disappeared")
                dep.finished_at = utcnow()
                app_ids.add(dep.app_id)
        db.commit()
    for app_id in app_ids:
        enqueue_next(factory, app_id)


def _remove_orphans(factory: jobs.SessionFactory, cli: DockerCli) -> int:
    """Removes containers whose app or deployment is gone (or no longer live/deploying) and Caddy
    files of deleted apps."""
    containers = cli.list_containers()
    directory = apps_dir()
    files = [p for p in directory.glob("*.caddy") if p.name != PLACEHOLDER_FILE] if directory.is_dir() else []
    removed = 0
    with factory() as db:
        for row in containers:
            app = db.get(App, row["app"]) if row["app"] else None
            dep = db.get(Deployment, row["deployment"]) if row["deployment"] else None
            if app is None or dep is None or dep.app_id != app.id or dep.status not in ("deploying", "live"):
                log.info("removing orphan app container %s", row["name"])
                cli.remove_container(row["name"])
                removed += 1
        stale_files = [p for p in files if db.get(App, p.stem) is None]
    for path in stale_files:
        path.unlink(missing_ok=True)
    if stale_files:
        cli.caddy_reload()
    return removed + len(stale_files)


_last_poll: dict[str, str] = {}


def poll_logs(factory: jobs.SessionFactory, cli: DockerCli | None = None) -> int:
    """Copies new `docker logs` lines of every live container into Redis (`apps:logs:<app_id>`,
    last LOGS_KEEP lines). Returns the number of lines added."""
    cli = cli or get_docker()
    with factory() as db:
        live = [
            (app.id, dep.container_name)
            for app in db.scalars(select(App).where(App.live_deployment_id.is_not(None)))
            if (dep := db.get(Deployment, app.live_deployment_id)) is not None and dep.container_name
        ]
    r = get_redis()
    added = 0
    for app_id, name in live:
        since = _last_poll.get(name)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            # ponytail: --since/--tail race can drop or repeat a line at the boundary; fine for a tail view
            lines = cli.logs(name, since=since, tail=LOGS_KEEP if since is None else 5000)
        except DockerError as exc:
            log.warning("docker logs %s failed: %s", name, exc)
            continue
        _last_poll[name] = now
        if lines:
            pipe = r.pipeline()
            pipe.rpush(logs_key(app_id), *lines)
            pipe.ltrim(logs_key(app_id), -LOGS_KEEP, -1)
            pipe.expire(logs_key(app_id), 7 * 86400)
            pipe.execute()
            added += len(lines)
    return added


def logs_loop(stop) -> None:
    """Worker background task: `poll_logs` every LOGS_POLL_S."""
    ensure_apps_dir()
    while not stop.wait(LOGS_POLL_S):
        try:
            poll_logs(jobs.get_sessionmaker())
        except Exception:  # noqa: BLE001
            log.exception("app log poll failed")
