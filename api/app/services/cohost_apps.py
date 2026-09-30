"""Co-hosting phase 2 on the main server (docs/COHOSTING.md "Websites on both PCs").

An app with `cohost` also runs on every co-host device of its project: a device owned by a member with
`can_cohost`, shared with the project, and (for apps with database access) holding a live copy of every
managed database the app uses. Visitors reach all copies through the app's hostnames on the apps tunnel
(services/remote_access.py), where Cloudflare balances between healthy connectors.

- `replicate()` runs when a deployment goes live (deploy and rollback) and from the scheduler sweep: it
  keeps one `app_replicas` row per eligible device and enqueues `app.replicate` for online devices whose
  copy is not at the live deployment yet.
- Job `app.replicate {app_id, device_id}`: sends the apps tunnel connector token (`apps.tunnel`) and
  `apps.deploy` to the device, which clones, builds and runs the app with its own worker.
- `sweep()` (scheduler leader, every tick): catches up devices that were offline (`replicate()` for every
  co-hosted app), then asks each online device what it runs (`apps.status`), removes copies the main
  server no longer wants (app deleted, co-hosting off, device no longer eligible) and fixes the device's
  tunnel token.

What a device receives: the app's own environment variables (minus `DEPLOYER_API_KEY`, `DEPLOYER_DB_*`
and any value containing a secret of the main server's databases), the names of the databases whose
local copies it should inject, the generated Dockerfile, the repository token only when an admin allowed
it (`cohost_share_repo_access`), and the apps tunnel's connector token. Never the dashboard tunnel token,
the Cloudflare API token, the data API key or the main server's database credentials.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, conflict
from app.models import App, AppReplica, DataSource, Deployment, Device, Project, ProjectMember, SourceReplica, utcnow
from app.serializers import iso
from app.services import app_runner, deployments, device_rpc, devices, jobs
from app.services.cohosting import member_can_cohost
from app.services.connections import device_removed, load_config
from app.services.device_apps import fingerprint
from app.services.instance_settings import get_value

log = logging.getLogger(__name__)

REPLICATE_JOB = "app.replicate"
DEPLOY_TIMEOUT = app_runner.GIT_TIMEOUT + app_runner.BUILD_TIMEOUT + 600
_CONNECTION_ERRORS = ("device_offline", "device_timeout", "device_busy")
WITHHELD_ENV_PREFIXES = ("DEPLOYER_DB_",)
WITHHELD_ENV_KEYS = ("DEPLOYER_API_KEY",)


# =============================================================================================
# who runs a copy
# =============================================================================================


def cohost_devices(db: Session, project: Project) -> list[Device]:
    """Active devices of members with `can_cohost` (developer+) that are shared with the project."""
    out = []
    for member in db.scalars(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.can_cohost.is_(True))
    ):
        if not member_can_cohost(member):
            continue
        for device in db.scalars(select(Device).where(Device.owner_id == member.user_id).order_by(Device.name)):
            if devices.placement_problem(db, device, project) is None:
                out.append(device)
    return out


def required_sources(db: Session, app: App) -> list[DataSource]:
    """The managed databases on the main server an app with database access uses."""
    if not app.database_access:
        return []
    rows = db.scalars(
        select(DataSource).where(
            DataSource.project_id == app.project_id,
            DataSource.mode == "managed",
            DataSource.deleted_at.is_(None),
            DataSource.device_id.is_(None),
        )
    )
    return [ds for ds in rows if not device_removed(ds)]  # A-047: a removed PC's database is not here


def copy_problem(db: Session, app: App, device_id: str) -> str | None:
    """None when the device holds a live (`syncing`) copy of every database the app uses."""
    for ds in required_sources(db, app):
        live = db.scalar(
            select(SourceReplica.id).where(
                SourceReplica.data_source_id == ds.id,
                SourceReplica.device_id == device_id,
                SourceReplica.status == "syncing",
            )
        )
        if live is None:
            return f"This PC has no live copy of the database '{ds.name}'"
    return None


def eligible_devices(db: Session, app: App) -> list[Device]:
    project = db.get(Project, app.project_id)
    return [d for d in cohost_devices(db, project) if copy_problem(db, app, d.id) is None]


def device_problem(db: Session, app: App, device: Device) -> str | None:
    """Why `device` may not run a copy of `app` right now (None: it may)."""
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == app.project_id, ProjectMember.user_id == device.owner_id
        )
    )
    if not member_can_cohost(member):
        return "The owner of this PC no longer co-hosts this project"
    project = db.get(Project, app.project_id)
    return devices.placement_problem(db, device, project) or copy_problem(db, app, device.id)


# =============================================================================================
# serialization
# =============================================================================================


def replicas_out(db: Session, app_id: str) -> list[dict]:
    rows = db.scalars(select(AppReplica).where(AppReplica.app_id == app_id).order_by(AppReplica.created_at))
    out = []
    for rep in rows:
        device = db.get(Device, rep.device_id)
        out.append(
            {
                "device_id": rep.device_id,
                "device_name": device.name if device else None,
                "online": device_rpc.is_online(rep.device_id),
                "status": rep.status,
                "deployment_id": rep.deployment_id,
                "error": rep.error,
                "last_seen_at": iso(rep.last_seen_at),
            }
        )
    return out


# =============================================================================================
# orchestration
# =============================================================================================


def _key(app_id: str, device_id: str) -> str:
    return f"{app_id}:{device_id}"


def replicate(factory: jobs.SessionFactory, app_id: str, *, user_id: str | None = None, retry: bool = False) -> list:
    """Brings the app's copies in line with its live deployment: a row per eligible device and
    `app.replicate` for online devices that lag behind. `retry` also re-sends to copies that are live or
    failed at the current deployment (settings or hostnames changed; a device re-running the same
    deployment only updates its routes). Rows of devices that are no longer eligible become `stopped`
    (the sweep removes their containers); turning co-hosting off deletes them. Commits; returns job ids."""
    job_ids: list[str] = []
    with factory() as db:
        app = db.get(App, app_id)
        if app is None:
            return []
        wanted = {d.id for d in eligible_devices(db, app)} if app.cohost else set()
        existing = {r.device_id: r for r in db.scalars(select(AppReplica).where(AppReplica.app_id == app_id))}
        for device_id, rep in existing.items():
            if not app.cohost:
                db.delete(rep)
            elif device_id not in wanted and rep.status != "stopped":
                device = db.get(Device, device_id)
                rep.status = "stopped"  # the sweep removes the copy from the device
                rep.error = (device_problem(db, app, device) if device else None) or "No longer eligible"
        live = app.live_deployment_id
        for device_id in sorted(wanted):
            rep = existing.get(device_id)
            if rep is None:
                rep = AppReplica(app_id=app_id, device_id=device_id, status="pending")
                db.add(rep)
            if not live:
                continue
            current = rep.deployment_id == live
            if current and (rep.status == "building" or (rep.status in ("live", "failed") and not retry)):
                continue  # a build error does not heal by itself: the next deploy or a settings change retries
            rep.deployment_id, rep.status, rep.error = live, "pending", None
            if not device_rpc.is_online(device_id) or jobs.active_job(db, REPLICATE_JOB, key=_key(app_id, device_id)):
                continue
            job = jobs.enqueue(
                db,
                type=REPLICATE_JOB,
                params={"app_id": app_id, "device_id": device_id, "key": _key(app_id, device_id)},
                project_id=app.project_id,
                device_id=device_id,
                created_by_id=user_id,
            )
            job_ids.append(job.id)
        db.commit()
    for job_id in job_ids:
        jobs.dispatch(job_id)
    return job_ids


def _main_secrets(db: Session, app: App) -> list[str]:
    """Credentials of the project's databases on this server: never sent to a device, even when a user
    copied them into the app's own variables."""
    out = []
    for ds in db.scalars(select(DataSource).where(DataSource.project_id == app.project_id)):
        try:
            config = load_config(ds)
        except Exception:  # noqa: BLE001 - an undecryptable config has nothing to leak
            continue
        out += [str(config[k]) for k in ("password", "uri") if config.get(k)]
    return [s for s in out if len(s) >= 6]


def device_env(db: Session, app: App) -> dict[str, str]:
    """The environment a device runs the app with (it adds its own DEPLOYER_DB_* for local copies)."""
    secrets = _main_secrets(db, app)
    env = deployments.runtime_env(db, app, api_key=False)
    return {
        k: v
        for k, v in env.items()
        if k not in WITHHELD_ENV_KEYS
        and not k.startswith(WITHHELD_ENV_PREFIXES)
        and not any(secret in v for secret in secrets)
    }


def deploy_params(db: Session, app: App, dep: Deployment, job_id: str) -> tuple[dict, str | None]:
    """(`apps.deploy` params, repo token or None). The token is sent only with `cohost_share_repo_access`."""
    needs_token = bool(app.repo_token_encrypted or app.github_connection_user_id)
    token = deployments.clone_token(db, app) if needs_token and app.cohost_share_repo_access else None
    hostnames = [d.hostname for d in deployments.app_domains(db, app.id) if d.status == "active"]
    params = {
        "job_id": job_id,
        "app_id": app.id,
        "slug": app.slug,
        "deployment_id": dep.id,
        "image_tag": dep.image_tag,
        "commit_sha": dep.commit_sha,
        "repo_url": app.repo_url,
        "branch": dep.branch,
        "root_dir": app.root_dir,
        "dockerfile": deployments.generate_dockerfile(app),
        "container_port": deployments.internal_port(app),
        "env": device_env(db, app),
        "databases": [
            {"name": ds.name, "kind": ds.kind, "database_name": ds.database_name} for ds in required_sources(db, app)
        ],
        "hostnames": hostnames,
        "repo_token": token,
        "repo_access_withheld": needs_token and not app.cohost_share_repo_access,
    }
    return params, token


def check_single_cohost(db: Session, app_id: str | None) -> None:
    """409 `cohost_limit` when another app of this installation is co-hosted already. Every co-hosted
    hostname rides the one apps tunnel, whose connectors Cloudflare balances between, so a device running
    only app A would get (and read) the visitors of app B (audit A-010)."""
    query = select(App.id).where(App.cohost.is_(True))
    if app_id:
        query = query.where(App.id != app_id)
    if db.scalar(query.limit(1)) is not None:
        raise conflict(
            "cohost_limit",
            "Only one app on this Deployer can be co-hosted for now, and another app already is. "
            "Turn co-hosting off there first.",
        )


def apps_tunnel_token(db: Session) -> str | None:
    """The token devices get, or None while more than one app is co-hosted (older data, or two admins at
    once): the devices then drop their connector and only the main server, which runs every app, serves
    the apps tunnel."""
    if len(db.scalars(select(App.id).where(App.cohost.is_(True)).limit(2)).all()) > 1:
        log.warning("more than one app is co-hosted: the apps tunnel stays on the main server only")
        return None
    return get_value(db, "cloudflare_apps_tunnel_token") or None


def push_tunnel(device_id: str, token: str | None) -> None:
    device_rpc.call(device_id, "apps.tunnel", {"token": token}, timeout=30)


@jobs.job_handler(REPLICATE_JOB)
def run_replicate(ctx: jobs.JobContext) -> dict:
    app_id, device_id = str(ctx.params["app_id"]), str(ctx.params["device_id"])
    factory = ctx.session_factory
    with factory() as db:
        app = db.get(App, app_id)
        rep = db.scalar(select(AppReplica).where(AppReplica.app_id == app_id, AppReplica.device_id == device_id))
        device = db.get(Device, device_id)
        if app is None or rep is None or device is None or not app.cohost:
            return {"skipped": "not co-hosted"}
        dep = db.get(Deployment, rep.deployment_id) if rep.deployment_id else None
        if dep is None or not dep.image_tag:
            return {"skipped": "nothing live"}
        problem = device_problem(db, app, device)
        if problem:
            rep.status, rep.error = "failed", problem
            db.commit()
            return {"skipped": problem}
        try:
            params, token = deploy_params(db, app, dep, ctx.job_id)
        except jobs.JobError as exc:
            rep.status, rep.error = "failed", str(exc)
            db.commit()
            raise
        tunnel = apps_tunnel_token(db)
        rep.status, rep.error = "building", None
        db.commit()
        deployment_id = dep.id
    try:
        ctx.progress(0.02, "Sending the app to the device", force=True)
        push_tunnel(device_id, tunnel)
        result = device_rpc.call(
            device_id,
            "apps.deploy",
            params,
            timeout=DEPLOY_TIMEOUT,
            progress_id=f"{device_id}:{ctx.job_id}",  # the socket publishes device progress per device
            on_progress=lambda fraction, message: ctx.progress(fraction, message),
        )
    except ApiError as exc:
        with factory() as db:
            rep = db.scalar(select(AppReplica).where(AppReplica.app_id == app_id, AppReplica.device_id == device_id))
            if rep is not None and rep.deployment_id == deployment_id:
                # Connection trouble: pending again, the sweep retries when the device is back.
                rep.status = "pending" if exc.code in _CONNECTION_ERRORS else "failed"
                rep.error = exc.message[:2000]
                db.commit()
        raise jobs.JobError(exc.message) from exc
    result = result if isinstance(result, dict) else {}
    with factory() as db:
        rep = db.scalar(select(AppReplica).where(AppReplica.app_id == app_id, AppReplica.device_id == device_id))
        if rep is not None and rep.deployment_id == deployment_id:
            rep.status, rep.error, rep.last_seen_at = "live", None, utcnow()
            rep.image_tag = str(result.get("image_tag") or "")[:200] or None
            rep.container_name = str(result.get("container") or "")[:100] or None
            port = result.get("port")
            rep.port = port if isinstance(port, int) else None
            db.commit()
    return {"app_id": app_id, "device_id": device_id, "deployment_id": deployment_id, "token_sent": token is not None}


# =============================================================================================
# scheduler sweep
# =============================================================================================


def sweep(factory: jobs.SessionFactory) -> None:
    """Every scheduler tick: catch up every co-hosted app, then reconcile each online device."""
    with factory() as db:
        app_ids = set(db.scalars(select(App.id).where(App.cohost.is_(True))))
        app_ids |= set(db.scalars(select(AppReplica.app_id).distinct()))
        device_ids = [d.id for d in db.scalars(select(Device).where(Device.status == "active"))]
    for app_id in sorted(app_ids):
        try:
            replicate(factory, app_id)
        except Exception:  # noqa: BLE001
            log.exception("co-host catch-up of app %s failed", app_id)
    for device_id in device_ids:
        if not device_rpc.is_online(device_id):
            continue
        try:
            sweep_device(factory, device_id)
        except ApiError as exc:
            if exc.code != "unknown_method":  # an older device without app hosting
                log.info("co-host sweep of device %s failed: %s", device_id, exc.message)


def sweep_device(factory: jobs.SessionFactory, device_id: str) -> None:
    status = device_rpc.call(device_id, "apps.status", {}, timeout=15)
    running = status.get("apps") if isinstance(status, dict) else None
    running = [a for a in running or [] if isinstance(a, dict) and isinstance(a.get("app_id"), str)]
    with factory() as db:
        reps = {r.app_id: r for r in db.scalars(select(AppReplica).where(AppReplica.device_id == device_id))}
        wanted = {app_id: r for app_id, r in reps.items() if r.status != "stopped"}
        remove = [a["app_id"] for a in running if a["app_id"] not in wanted]
        for item in running:
            rep = wanted.get(item["app_id"])
            if rep is not None:
                rep.last_seen_at = utcnow()
        # Only devices that run (or are about to run) a co-hosted app get the apps tunnel's token.
        token = apps_tunnel_token(db) if wanted else None
        db.commit()
    for app_id in remove:
        device_rpc.call(device_id, "apps.remove", {"app_id": app_id}, timeout=120)
    if status.get("tunnel") != fingerprint(token):
        push_tunnel(device_id, token)
