"""Device side of co-hosted apps (docs/COHOSTING.md "Websites on both PCs"): RPC `apps.*`.

The main Deployer sends `apps.deploy` for an app of a project this PC co-hosts; this device's worker
clones, builds and runs it through its own `DockerCli` (the same code paths as the main server's deploy
job) and routes it in its own Caddy: a local `:81xx` listener and, per hostname, an `http://<host>:8081`
block that the apps tunnel connector (RPC `apps.tunnel`) reaches.

- Only databases this device hosts (`device_hosted_credentials`) are injected as `DEPLOYER_DB_*`, with
  this device's own credentials: the main server's never leave it.
- The environment may not carry `DEPLOYER_API_KEY` or `DEPLOYER_DB_*` (refused).
- Containers are labelled `deployer.cohost_app` (not `deployer.app`) and Caddy files are named
  `cohost-<app_id>.caddy`, so this installation's own app cleanup never touches them.
- State (`instance_settings.device_cohost_apps`): `{app_id: {slug, deployment_id, image_tag, container,
  port, upstream_port, hostnames, databases}}`. One deploy at a time on a device.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile
import threading
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import ApiError
from app.models import App
from app.services import deployments, device_host, instance_settings, jobs
from app.services import remote_access as ra
from app.services.app_runner import DockerError, get_docker
from app.services.connections import redact

log = logging.getLogger(__name__)

STATE_KEY = "device_cohost_apps"
TUNNEL_KEY = "cohost_apps_tunnel_token"
LABEL_APP = "deployer.cohost_app"
LABEL_DEPLOYMENT = "deployer.cohost_deployment"
WITHHELD_MESSAGE = "The app's owner hasn't allowed co-hosts to clone this private repository"

_lock = threading.Lock()  # ponytail: one co-host deploy at a time per PC; old PCs build slowly anyway
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_BRANCH = re.compile(r"^[^\s~^:?*\[\\]{1,120}$")
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_TOKEN = re.compile(r"^[A-Za-z0-9+/=_.-]{1,4096}$")


def _bad(message: str) -> ApiError:
    return ApiError(422, "validation_error", message)


def _app_id(params: dict) -> str:
    app_id = params.get("app_id")
    if not isinstance(app_id, str) or not _UUID.fullmatch(app_id):
        raise _bad("Invalid app_id")
    return app_id


def _check_deploy(params: dict) -> dict:
    """Everything `apps.deploy` accepts, validated; anything else is refused."""
    app_id = _app_id(params)
    deployment_id = params.get("deployment_id")
    if not isinstance(deployment_id, str) or not _UUID.fullmatch(deployment_id):
        raise _bad("Invalid deployment_id")
    tag = params.get("image_tag")
    prefix = f"{deployments.IMAGE_PREFIX}/{app_id}:"
    if not isinstance(tag, str) or not tag.startswith(prefix) or not _UUID.fullmatch(tag[len(prefix) :]):
        raise _bad("Invalid image_tag")
    slug = params.get("slug")
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
        raise _bad("Invalid slug")
    sha = params.get("commit_sha")
    if sha is not None and (not isinstance(sha, str) or not _SHA.fullmatch(sha)):
        raise _bad("Invalid commit_sha")
    url = params.get("repo_url")
    if (
        not isinstance(url, str)
        or len(url) > 500
        or not re.fullmatch(r"https://[^\s/@:]+(:\d+)?/\S*", url)
        or "@" in url.split("/", 3)[2]
    ):
        raise _bad("repo_url must be an https:// URL without credentials")
    branch = params.get("branch")
    if not isinstance(branch, str) or not _BRANCH.fullmatch(branch) or branch.startswith("-"):
        raise _bad("Invalid branch")
    root_dir = params.get("root_dir") or "."
    if not isinstance(root_dir, str) or ".." in root_dir.split("/") or "\\" in root_dir or root_dir.startswith("/"):
        raise _bad("Invalid root_dir")
    dockerfile = params.get("dockerfile")
    if dockerfile is not None and (not isinstance(dockerfile, str) or len(dockerfile) > 64 * 1024):
        raise _bad("Invalid dockerfile")
    port = params.get("container_port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise _bad("Invalid container_port")
    env = params.get("env") or {}
    if not isinstance(env, dict) or len(env) > 500:
        raise _bad("Invalid env")
    for key, value in env.items():
        if not isinstance(key, str) or not _ENV_KEY.fullmatch(key) or not isinstance(value, str):
            raise _bad("Invalid env")
        if key == "DEPLOYER_API_KEY" or key.startswith("DEPLOYER_DB_"):
            raise _bad(f"{key} is not accepted on a co-host device")
    databases = params.get("databases") or []
    if not isinstance(databases, list) or len(databases) > 50:
        raise _bad("Invalid databases")
    checked_dbs = []
    for item in databases:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            raise _bad("Invalid databases")
        entry = device_host.hosted_entry(item.get("database_name"), item.get("kind"))  # 404 not_hosted otherwise
        checked_dbs.append((item["name"][:63], entry["kind"], item["database_name"], entry))
    hostnames = params.get("hostnames") or []
    if not isinstance(hostnames, list) or len(hostnames) > 50 or not all(isinstance(h, str) for h in hostnames):
        raise _bad("Invalid hostnames")
    token = params.get("repo_token")
    if token is not None and (not isinstance(token, str) or len(token) > 500 or any(c.isspace() for c in token)):
        raise _bad("Invalid repo_token")
    job_id = params.get("job_id")
    return {
        "app_id": app_id,
        "deployment_id": deployment_id,
        "image_tag": tag,
        "slug": slug,
        "commit_sha": sha,
        "repo_url": url,
        "branch": branch,
        "root_dir": root_dir,
        "dockerfile": dockerfile,
        "container_port": port,
        "env": dict(env),
        "databases": checked_dbs,
        "hostnames": [ra.normalize_hostname(h) for h in hostnames],
        "repo_token": token,
        "repo_access_withheld": params.get("repo_access_withheld") is True,
        "job_id": str(job_id)[:64] if job_id else None,
    }


# --- state ---------------------------------------------------------------------------------------


def _load(db) -> dict[str, dict]:
    value = instance_settings.get_value(db, STATE_KEY)
    return value if isinstance(value, dict) else {}


def _save(state: dict[str, dict]) -> None:
    with get_sessionmaker()() as db:
        instance_settings.set_value(db, STATE_KEY, state or None)
        db.commit()


def _state() -> dict[str, dict]:
    with get_sessionmaker()() as db:
        return _load(db)


def _allocate_port(db, state: dict[str, dict]) -> int:
    used = {int(e["port"]) for e in state.values() if isinstance(e.get("port"), int)}
    used |= set(db.scalars(select(App.port)))  # this installation's own apps
    for port in range(deployments.PORT_MIN, deployments.PORT_MAX + 1):
        if port not in used:
            return port
    raise ApiError(409, "no_ports_left", "All app ports on this PC are in use")


def _database_env(databases: list[tuple]) -> dict[str, str]:
    env: dict[str, str] = {}
    for name, kind, database, entry in databases:
        config = device_host.local_config(kind, database, entry["username"], entry["password"])
        env.update(deployments.source_env(name, kind, "mariadb" if kind == "sql" else "mongodb", config, database))
    return env


def fingerprint(token: str | None) -> str | None:
    """Identifies a tunnel token without revealing it (`apps.status` reports it; the sweep compares)."""
    return hashlib.sha256(token.encode()).hexdigest()[:16] if token else None


def _caddy_name(app_id: str) -> str:
    return f"{deployments.COHOST_FILE_PREFIX}{app_id}"


# --- RPC methods ---------------------------------------------------------------------------------


def m_deploy(params: dict, ctx: device_host.CallContext) -> dict:
    p = _check_deploy(params)
    app_id, dep_id, tag = p["app_id"], p["deployment_id"], p["image_tag"]

    def progress(fraction: float, message: str) -> None:
        if p["job_id"]:
            ctx.progress(p["job_id"], fraction, message)

    cli = get_docker()
    db_env = _database_env(p["databases"])
    secrets = [p["repo_token"], *(v for v in [*p["env"].values(), *db_env.values()] if len(v) >= 8)]
    with _lock:
        with get_sessionmaker()() as db:
            state = _load(db)
            entry = dict(state.get(app_id) or {})
            port = entry.get("port") or _allocate_port(db, state)
        name = f"deployer-app-{p['slug']}-{dep_id[:8]}"
        started = None
        try:
            if entry.get("deployment_id") != dep_id or not entry.get("container"):
                if tag.split(":", 1)[1] not in cli.list_images(f"{deployments.IMAGE_PREFIX}/{app_id}"):
                    _clone_and_build(cli, p, progress)
                progress(0.7, "Starting")
                cli.remove_container(name)
                cli.run_container(
                    name, tag, labels={LABEL_APP: app_id, LABEL_DEPLOYMENT: dep_id}, env={**db_env, **p["env"]}
                )
                started = name
                if db_env:
                    cli.network_connect(get_settings().app_db_network, name)
                if not cli.wait_tcp(name, p["container_port"], deployments.HEALTH_TIMEOUT_S):
                    tail = "\n".join(cli.logs(name, since=None, tail=20))
                    raise ApiError(
                        500,
                        "app_deploy_failed",
                        f"The container did not accept connections on port {p['container_port']} within "
                        f"{deployments.HEALTH_TIMEOUT_S} s" + (f"\n{tail}" if tail else ""),
                    )
            progress(0.9, "Routing")
            text = deployments.render_caddyfile(_caddy_name(app_id), port, name, p["container_port"], p["hostnames"])
            deployments.write_caddy_file(_caddy_name(app_id), text)
            cli.caddy_reload()
            started = None  # routed: ours now
            old = entry.get("container")
            if old and old != name:
                cli.remove_container(old)
            for other in cli.list_images(f"{deployments.IMAGE_PREFIX}/{app_id}"):
                if other != tag.split(":", 1)[1]:
                    cli.remove_image(
                        f"{deployments.IMAGE_PREFIX}/{app_id}:{other}"
                    )  # ponytail: no local rollback cache
        except DockerError as exc:
            raise ApiError(500, "app_deploy_failed", deployments._docker_failure(exc, secrets)) from None
        except jobs.JobError as exc:
            raise ApiError(422, "app_deploy_failed", redact(str(exc), secrets, limit=2000)) from None
        except ApiError as exc:
            exc.message = redact(exc.message, secrets, limit=2000)
            raise
        finally:
            if started:
                cli.remove_container(started)
        state = _state()
        state[app_id] = {
            "slug": p["slug"],
            "deployment_id": dep_id,
            "image_tag": tag,
            "container": name,
            "port": port,
            "upstream_port": p["container_port"],
            "hostnames": p["hostnames"],
            "databases": [d[2] for d in p["databases"]],
        }
        _save(state)
    return {"status": "live", "image_tag": tag, "container": name, "port": port}


def _clone_and_build(cli, p: dict, progress) -> None:
    workdir = tempfile.mkdtemp(prefix="deployer-cohost-", dir=get_settings().app_build_dir or None)
    try:
        progress(0.05, "Cloning")
        checkout = os.path.join(workdir, "src")
        try:
            cli.git_clone(p["repo_url"], p["branch"], checkout, token=p["repo_token"])
            if p["commit_sha"] and cli.git_head(checkout)[0] != p["commit_sha"]:
                cli.git_checkout(checkout, p["commit_sha"], token=p["repo_token"])
        except DockerError:
            if p["repo_access_withheld"]:
                raise ApiError(422, "repo_access_withheld", WITHHELD_MESSAGE) from None
            raise
        progress(0.2, "Building")
        deployments.build_image(cli, workdir, checkout, p["root_dir"], p["dockerfile"], p["image_tag"], lambda _: None)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def m_remove(params: dict, ctx: device_host.CallContext) -> dict:
    app_id = _app_id(params)
    cli = get_docker()
    with _lock:
        state = _state()
        entry = state.pop(app_id, None) or {}
        if entry.get("container"):
            cli.remove_container(entry["container"])
        for tag in cli.list_images(f"{deployments.IMAGE_PREFIX}/{app_id}"):
            cli.remove_image(f"{deployments.IMAGE_PREFIX}/{app_id}:{tag}")
        deployments.write_caddy_file(_caddy_name(app_id), None)
        cli.caddy_reload()
        _save(state)
    return {"removed": bool(entry)}


def m_status(params: dict, ctx: device_host.CallContext) -> dict:
    with get_sessionmaker()() as db:
        state = _load(db)
        token = instance_settings.get_value(db, TUNNEL_KEY)
    apps = [
        {k: e.get(k) for k in ("deployment_id", "image_tag", "container", "port")} | {"app_id": app_id}
        for app_id, e in sorted(state.items())
    ]
    return {"apps": apps, "tunnel": fingerprint(token)}


def m_logs(params: dict, ctx: device_host.CallContext) -> dict:
    app_id = _app_id(params)
    tail = params.get("tail", 200)
    if not isinstance(tail, int) or isinstance(tail, bool) or not 1 <= tail <= 500:
        raise _bad("Invalid tail")
    entry = _state().get(app_id)
    if not entry or not entry.get("container"):
        raise ApiError(404, "not_found", "This PC does not run that app")
    return {"lines": get_docker().logs(entry["container"], since=None, tail=tail), "container": entry["container"]}


def m_tunnel(params: dict, ctx: device_host.CallContext) -> dict:
    """The apps tunnel's connector token (the only tunnel secret a device receives), or null to stop."""
    token = params.get("token")
    if token is not None and (not isinstance(token, str) or not _TOKEN.fullmatch(token)):
        raise _bad("Invalid token")
    with get_sessionmaker()() as db:
        instance_settings.set_value(db, TUNNEL_KEY, token)
        db.commit()
        ok = ra.write_desired(ra.desired_state(db))
    if not ok:
        raise ApiError(503, "tunnel_unavailable", "Could not hand the token to this PC's tunnel sidecar")
    return {"tunnel": fingerprint(token)}


def remove_all() -> None:
    """Detaching: stop the apps tunnel connector and every co-hosted app, or they keep serving visitors."""
    with get_sessionmaker()() as db:
        token = instance_settings.get_value(db, TUNNEL_KEY)
    if token:
        m_tunnel({"token": None}, device_host.CallContext())
    for app_id in sorted(_state()):
        m_remove({"app_id": app_id}, device_host.CallContext())


METHODS: dict[str, Any] = {
    "apps.deploy": m_deploy,
    "apps.remove": m_remove,
    "apps.status": m_status,
    "apps.logs": m_logs,
    "apps.tunnel": m_tunnel,
}
