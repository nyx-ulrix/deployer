"""Co-hosting phase 2 (docs/COHOSTING.md "Websites on both PCs"): apps on co-host devices, the apps
tunnel with failover, the device-side `apps.*` RPCs and migration 0010. Uses FakeDockerCli, fake
devices and the fake Cloudflare API."""

import json
import secrets
import sqlite3
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.config import get_settings
from app.crypto import encrypt_json, encrypt_secret, sha256_hex
from app.errors import ApiError
from app.models import (
    ApiKey,
    App,
    AppReplica,
    AuditLog,
    DataSource,
    Deployment,
    DeviceProjectGrant,
    Domain,
    Job,
    ProjectMember,
    SourceReplica,
)
from app.services import cohost_apps, deployments, device_apps, device_host, jobs
from tests import devices_support
from tests.apps_support import FAKE_SHA, make_app, new_token
from tests.test_deployments import docker  # noqa: F401 - fixture
from tests.test_github_integration import API_DIR
from tests.test_remote_access import desired, fake_cf, link, state_dir  # noqa: F401 - fixtures

make_device = devices_support.make_device
fake_device = devices_support.fake_device


@pytest.fixture
def team(db, owner, make_user, make_project, make_device):
    users = {
        "owner": owner,
        "admin": make_user("admin@example.com"),
        "cohost": make_user("cohost@example.com"),
        "dev": make_user("dev@example.com"),
    }
    project = make_project(
        owner, "Shop", members={users["admin"]: "admin", users["cohost"]: "developer", users["dev"]: "developer"}
    )
    member = db.scalar(select(ProjectMember).where(ProjectMember.user_id == users["cohost"].id))
    member.can_cohost = True
    device, _ = make_device(users["cohost"], "Home PC", sharing_mode="selected")
    db.add(DeviceProjectGrant(device_id=device.id, project_id=project.id))
    db.commit()
    return {"project": project, "users": users, "device": device}


def handler_for(calls_state=None):
    """A co-host device that accepts everything; `calls_state["apps"]` is what `apps.status` reports."""
    state = calls_state if calls_state is not None else {"apps": [], "tunnel": None}

    def handler(method, params):
        if method == "apps.tunnel":
            state["tunnel"] = device_apps.fingerprint(params["token"])
            return {"tunnel": state["tunnel"]}
        if method == "apps.deploy":
            name = f"deployer-app-{params['slug']}-{params['deployment_id'][:8]}"
            return {"status": "live", "image_tag": params["image_tag"], "container": name, "port": 8100}
        if method == "apps.status":
            return {"apps": list(state["apps"]), "tunnel": state["tunnel"]}
        if method == "apps.remove":
            state["apps"] = [a for a in state["apps"] if a["app_id"] != params["app_id"]]
            return {"removed": True}
        raise AssertionError(method)

    return handler


def deploy(db, app):
    dep, _ = deployments.start_deployment(db, app, trigger="manual", user_id=None)
    db.commit()
    return dep


def replicas(db, app_id):
    db.expire_all()
    return {r.device_id: r for r in db.scalars(select(AppReplica).where(AppReplica.app_id == app_id))}


def managed_source(db, project, password):
    config = {"host": "mariadb", "port": 3306, "username": "u_main", "password": password, "database": "p_shop_abc123"}
    ds = DataSource(
        project_id=project.id,
        name="main",
        kind="sql",
        engine="mariadb",
        mode="managed",
        database_name="p_shop_abc123",
        config_encrypted=encrypt_json(config),
        status="ok",
    )
    db.add(ds)
    db.commit()
    return ds


# --- main server: orchestration ------------------------------------------------------------------


def test_replicate_on_live_and_rollback(client, db, docker, team, fake_device, auth_headers):  # noqa: F811
    t = team
    project, device = t["project"], t["device"]
    key = ApiKey(
        project_id=project.id,
        name="k",
        role="service",
        prefix="dpl_service_x",
        key_hash=sha256_hex("s"),
        secret_encrypted=encrypt_secret("dpl_service_secret"),
    )
    db.add(key)
    main_pw = "main-db-" + secrets.token_hex(8)
    ds = managed_source(db, project, main_pw)
    db.add(SourceReplica(data_source_id=ds.id, device_id=device.id, status="syncing"))
    db.commit()
    token = new_token()
    leaky = "mysql://u_main:" + main_pw + "@mariadb:3306/p_shop_abc123"
    app = make_app(
        db,
        project,
        env={"NODE_ENV": "production", "COPIED_DB_URL": leaky, "DEPLOYER_DB_MAIN_HOST": "x"},
        token=token,
        api_key_id=key.id,
        cohost=True,
        database_access=True,
    )
    fd = fake_device(device.id, handler_for())

    first = deploy(db, app)
    assert [status for _, status in jobs.run_queued()] == ["succeeded", "succeeded"]
    assert [m for m, _ in fd.calls] == ["apps.tunnel", "apps.deploy"]
    assert fd.calls[0][1] == {"token": None}  # no co-hosted hostname yet: no apps tunnel
    params = fd.calls[1][1]
    db.expire_all()
    first = db.get(Deployment, first.id)
    assert (params["deployment_id"], params["image_tag"], params["commit_sha"]) == (
        first.id,
        first.image_tag,
        FAKE_SHA,
    )
    assert params["env"] == {
        "NODE_ENV": "production",
        "PORT": "3000",
        "DEPLOYER_URL": "http://localhost:8080/v1",
        "DEPLOYER_PROJECT_ID": project.id,
    }
    assert params["databases"] == [{"name": "main", "kind": "sql", "database_name": "p_shop_abc123"}]
    assert params["repo_token"] is None and params["repo_access_withheld"] is True
    assert "FROM node:22-alpine" in params["dockerfile"] and params["container_port"] == 3000
    sent = json.dumps([p for _, p in fd.calls])
    for secret in ("dpl_service_secret", main_pw, token, get_settings().master_key, get_settings().jwt_secret):
        assert secret not in sent
    rep = replicas(db, app.id)[device.id]
    assert (rep.status, rep.deployment_id, rep.port) == ("live", first.id, 8100)
    assert rep.container_name == f"deployer-app-shop-{first.id[:8]}"

    out = client.get(f"/v1/projects/{project.id}/apps/{app.id}", headers=auth_headers(t["users"]["dev"])).json()
    assert out["cohost"] is True and out["cohost_share_repo_access"] is False
    assert [(r["device_name"], r["status"], r["online"]) for r in out["replicas"]] == [("Home PC", "live", True)]

    # A second deploy, then a rollback to the first: the device follows both, the rollback with the old image.
    second = deploy(db, db.get(App, app.id))
    jobs.run_queued()
    db.expire_all()
    rollback, _ = deployments.rollback(db, db.get(App, app.id), db.get(Deployment, first.id), user_id=None)
    db.commit()
    jobs.run_queued()
    deploys = [p for m, p in fd.calls if m == "apps.deploy"]
    assert [p["deployment_id"] for p in deploys] == [first.id, second.id, rollback.id]
    assert deploys[-1]["image_tag"] == first.image_tag
    assert replicas(db, app.id)[device.id].deployment_id == rollback.id


def test_repo_token_only_when_the_owner_allows_it(db, docker, team, fake_device):  # noqa: F811
    token = new_token()
    app = make_app(db, team["project"], token=token, cohost=True, cohost_share_repo_access=True)
    fd = fake_device(team["device"].id, handler_for())
    deploy(db, app)
    jobs.run_queued()
    (params,) = [p for m, p in fd.calls if m == "apps.deploy"]
    assert params["repo_token"] == token and params["repo_access_withheld"] is False
    # A public repository (no token, no connection) is neither shared nor withheld.
    public = make_app(db, team["project"], "Blog", cohost=True)
    deploy(db, public)
    jobs.run_queued()
    params = [p for m, p in fd.calls if m == "apps.deploy"][-1]
    assert params["repo_token"] is None and params["repo_access_withheld"] is False


def test_eligibility(db, docker, team, fake_device, make_device):  # noqa: F811
    t = team
    project, device = t["project"], t["device"]
    make_device(t["users"]["dev"], "Dev laptop")  # member without can_cohost
    make_device(t["users"]["cohost"], "Work PC", sharing_mode="selected")  # not shared with the project
    app = make_app(db, project, cohost=True)

    # Offline: the copy waits (pending, no job) and catches up when the device is back.
    dep = deploy(db, app)
    assert [status for _, status in jobs.run_queued()] == ["succeeded"]
    rows = replicas(db, app.id)
    assert list(rows) == [device.id] and rows[device.id].status == "pending"
    assert rows[device.id].deployment_id == dep.id

    # Database access: only devices holding a live copy of every managed source qualify.
    db.get(App, app.id).database_access = True
    ds = managed_source(db, project, "pw-" + secrets.token_hex(8))
    cohost_apps.replicate(jobs.get_sessionmaker(), app.id)
    rep = replicas(db, app.id)[device.id]
    assert rep.status == "stopped" and "no live copy of the database 'main'" in rep.error
    copy = SourceReplica(data_source_id=ds.id, device_id=device.id, status="paused")
    db.add(copy)
    db.commit()
    cohost_apps.replicate(jobs.get_sessionmaker(), app.id)
    assert replicas(db, app.id)[device.id].status == "stopped"
    copy.status = "syncing"
    db.commit()

    fd = fake_device(device.id, handler_for())
    cohost_apps.sweep(jobs.get_sessionmaker())
    assert replicas(db, app.id)[device.id].status == "pending"
    assert [status for _, status in jobs.run_queued()] == ["succeeded"]
    assert replicas(db, app.id)[device.id].status == "live"
    assert [m for m, _ in fd.calls if m == "apps.deploy"] == ["apps.deploy"]

    # The owner loses co-hosting: the copy is stopped (and removed from the PC by the sweep).
    member = db.scalar(select(ProjectMember).where(ProjectMember.user_id == t["users"]["cohost"].id))
    member.can_cohost = False
    db.commit()
    cohost_apps.replicate(jobs.get_sessionmaker(), app.id)
    assert replicas(db, app.id)[device.id].status == "stopped"


def test_failed_device_build_is_reported_and_not_retried_every_tick(db, docker, team, fake_device):  # noqa: F811
    app = make_app(db, team["project"], token=new_token(), cohost=True)

    def handler(method, params):
        if method == "apps.deploy":
            raise ApiError(422, "repo_access_withheld", device_apps.WITHHELD_MESSAGE)
        return handler_for()(method, params)

    fd = fake_device(team["device"].id, handler)
    deploy(db, app)
    assert [status for _, status in jobs.run_queued()] == ["succeeded", "failed"]
    rep = replicas(db, app.id)[team["device"].id]
    assert rep.status == "failed" and rep.error == device_apps.WITHHELD_MESSAGE
    cohost_apps.replicate(jobs.get_sessionmaker(), app.id)
    assert jobs.run_queued() == []
    # Allowing co-hosts to clone retries.
    assert cohost_apps.replicate(jobs.get_sessionmaker(), app.id, retry=True)
    assert len([m for m, _ in fd.calls if m == "apps.deploy"]) == 1


def test_sweep_token_only_to_cohost_devices_and_cleanup(db, team, fake_device, make_device, set_setting):
    t = team
    apps_token = secrets.token_urlsafe(24)
    set_setting("cloudflare_apps_tunnel_token", apps_token)
    app = make_app(db, t["project"], cohost=True)
    dep = Deployment(app_id=app.id, status="live", trigger="manual", branch="main", log="")
    db.add(dep)
    db.flush()
    dep.image_tag = deployments.image_tag(app.id, dep.id)
    app.live_deployment_id = dep.id
    db.commit()
    spare, _ = make_device(t["users"]["owner"], "Spare PC")  # not a co-host device of anything
    stale_app = str(uuid.uuid4())
    home_state = {"apps": [], "tunnel": None}
    spare_state = {"apps": [{"app_id": stale_app}], "tunnel": None}
    home = fake_device(t["device"].id, handler_for(home_state))
    spare_fd = fake_device(spare.id, handler_for(spare_state))

    cohost_apps.sweep(jobs.get_sessionmaker())
    assert ("apps.tunnel", {"token": apps_token}) in home.calls
    assert [m for m, _ in spare_fd.calls] == ["apps.status", "apps.remove"]  # never the tunnel token
    assert spare_fd.calls[1][1] == {"app_id": stale_app}
    assert [status for _, status in jobs.run_queued()] == ["succeeded"]
    assert replicas(db, app.id)[t["device"].id].status == "live"

    # Co-hosting switched off: the rows go, the sweep removes the copy and takes the token back.
    home_state["apps"] = [{"app_id": app.id}]
    db.get(App, app.id).cohost = False
    db.commit()
    home.calls.clear()
    cohost_apps.sweep(jobs.get_sessionmaker())
    assert replicas(db, app.id) == {}
    assert home.calls == [
        ("apps.status", {}),
        ("apps.remove", {"app_id": app.id}),
        ("apps.tunnel", {"token": None}),
    ]


# --- apps tunnel ---------------------------------------------------------------------------------


def test_apps_tunnel_created_once_cname_moves_and_ingress(
    client,
    db,
    team,
    auth_headers,
    owner_headers,
    fake_cf,  # noqa: F811
    state_dir,  # noqa: F811
):
    t = team
    dashboard_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    admin = auth_headers(t["users"]["admin"])
    app = make_app(db, t["project"])
    base = f"/v1/projects/{t['project'].id}/apps/{app.id}"
    domain = client.post(f"{base}/domains", json={"hostname": "shop.example.com"}, headers=admin).json()

    def cname(domain_id):
        db.expire_all()
        return fake_cf.records[db.get(Domain, domain_id).dns_record_id]["content"]

    def ingress(tunnel_id):
        return [r.get("hostname") for r in fake_cf.tunnel_configs[tunnel_id]["ingress"]]

    assert cname(domain["id"]) == f"{dashboard_id}.cfargotunnel.com"
    assert client.patch(base, json={"cohost": True}, headers=auth_headers(t["users"]["dev"])).status_code == 403
    assert client.patch(base, json={"cohost": False}, headers=auth_headers(t["users"]["dev"])).status_code == 200
    resp = client.patch(base, json={"cohost": True}, headers=admin)
    assert resp.status_code == 200 and resp.json()["cohost"] is True
    (apps_tunnel,) = [x for x in fake_cf.tunnels.values() if x["name"].startswith("deployer-apps-")]
    apps_id = apps_tunnel["id"]
    assert cname(domain["id"]) == f"{apps_id}.cfargotunnel.com"
    assert ingress(apps_id) == ["shop.example.com", None] and ingress(dashboard_id) == [None]
    assert desired(state_dir)["apps_token"] == f"connector-token-for-{apps_id}"
    assert resp.json()["replicas"][0]["status"] == "pending"  # the co-host device is registered

    # A second co-hosted app reuses the apps tunnel.
    blog = make_app(db, t["project"], "Blog", cohost=True)
    blog_domain = client.post(
        f"/v1/projects/{t['project'].id}/apps/{blog.id}/domains", json={"hostname": "blog.example.com"}, headers=admin
    ).json()
    assert cname(blog_domain["id"]) == f"{apps_id}.cfargotunnel.com"
    assert ingress(apps_id) == ["shop.example.com", "blog.example.com", None]
    assert len(fake_cf.calls("POST", r"/cfd_tunnel$")) == 2  # the dashboard tunnel and the apps tunnel

    # Co-hosting off: back to the dashboard tunnel.
    assert client.patch(base, json={"cohost": False}, headers=admin).status_code == 200
    assert cname(domain["id"]) == f"{dashboard_id}.cfargotunnel.com"
    assert ingress(dashboard_id) == ["shop.example.com", None] and ingress(apps_id) == ["blog.example.com", None]
    assert replicas(db, app.id) == {}
    blog_url = f"/v1/projects/{t['project'].id}/apps/{blog.id}/domains/{blog_domain['id']}"
    assert client.delete(blog_url, headers=admin).json() == {"ok": True}
    assert ingress(apps_id) == [None]
    audit = [a.details for a in db.scalars(select(AuditLog).where(AuditLog.action == "app.cohost"))]
    assert [a["enabled"] for a in audit] == [True, False]


# --- device side ---------------------------------------------------------------------------------


@pytest.fixture
def hosted(set_setting):
    password = "local-" + secrets.token_hex(8)
    set_setting(
        "device_hosted_credentials",
        json.dumps({"p_shop_abc123": {"kind": "sql", "username": "u_local", "password": password}}),
    )
    return password


def deploy_params(app_id=None, dep_id=None, **extra):
    app_id, dep_id = app_id or str(uuid.uuid4()), dep_id or str(uuid.uuid4())
    return {
        "job_id": "job-1",
        "app_id": app_id,
        "slug": "shop",
        "deployment_id": dep_id,
        "image_tag": f"deployer-app/{app_id}:{dep_id}",
        "commit_sha": FAKE_SHA,
        "repo_url": "https://github.com/acme/shop",
        "branch": "main",
        "root_dir": ".",
        "dockerfile": 'FROM node:22-alpine\nCMD ["npm", "start"]\n',
        "container_port": 3000,
        "env": {"NODE_ENV": "production", "PORT": "3000"},
        "databases": [{"name": "main", "kind": "sql", "database_name": "p_shop_abc123"}],
        "hostnames": ["Shop.Example.com"],
        "repo_token": None,
        "repo_access_withheld": False,
        **extra,
    }


def test_device_deploy_route_status_logs_remove(db, docker, hosted):  # noqa: F811
    progress = []
    ctx = device_host.CallContext(progress=lambda job_id, fraction, message: progress.append((job_id, message)))
    params = deploy_params()
    app_id, dep_id = params["app_id"], params["deployment_id"]
    out = device_host.dispatch("apps.deploy", params, ctx)
    name = f"deployer-app-shop-{dep_id[:8]}"
    assert out == {"status": "live", "image_tag": params["image_tag"], "container": name, "port": 8100}
    assert docker.steps() == ["clone", "build", "rm", "run", "connect", "health", "reload"]
    assert docker.calls[4] == ("connect", get_settings().app_db_network, name)
    container = docker.containers[name]
    assert container["labels"] == {"deployer.cohost_app": app_id, "deployer.cohost_deployment": dep_id}
    env = container["env"]
    assert env["NODE_ENV"] == "production" and env["DEPLOYER_DB_MAIN_PASSWORD"] == hosted
    assert env["DEPLOYER_DB_MAIN_HOST"] == get_settings().mariadb_host and env["DEPLOYER_DB_MAIN_USER"] == "u_local"
    assert ("job-1", "Building") in progress
    caddy = deployments.apps_dir() / f"cohost-{app_id}.caddy"
    assert ":8100 {" in caddy.read_text() and "http://shop.example.com:8081 {" in caddy.read_text()
    # This installation's own app cleanup leaves co-hosted copies alone.
    docker.calls.clear()
    deployments.scheduler_tick(jobs.get_sessionmaker())
    assert name in docker.containers and caddy.exists()

    # The same deployment again (hostnames changed): routes only.
    docker.calls.clear()
    device_host.dispatch("apps.deploy", {**params, "hostnames": ["www.example.com"]}, ctx)
    assert docker.steps() == ["reload"] and "www.example.com" in caddy.read_text()
    status = device_host.dispatch("apps.status", {}, ctx)
    assert status["tunnel"] is None
    assert status["apps"] == [
        {"app_id": app_id, "deployment_id": dep_id, "image_tag": params["image_tag"], "container": name, "port": 8100}
    ]
    assert device_host.dispatch("apps.logs", {"app_id": app_id, "tail": 5}, ctx)["lines"] == ["hello from the app"]

    # A new deployment swaps containers and keeps only the current image.
    new = deploy_params(app_id=app_id)
    docker.calls.clear()
    device_host.dispatch("apps.deploy", new, ctx)
    new_name = f"deployer-app-shop-{new['deployment_id'][:8]}"
    assert set(docker.containers) == {new_name} and docker.images == {new["image_tag"]}
    assert device_host.dispatch("apps.remove", {"app_id": app_id}, ctx) == {"removed": True}
    assert docker.containers == {} and docker.images == set() and not caddy.exists()
    assert device_host.dispatch("apps.status", {}, ctx)["apps"] == []


def test_device_refuses_what_it_must_not_run(db, docker, hosted):  # noqa: F811
    ctx = device_host.CallContext()
    for bad, code in (
        ({"env": {"DEPLOYER_API_KEY": "x"}}, "validation_error"),
        ({"env": {"DEPLOYER_DB_MAIN_PASSWORD": "x"}}, "validation_error"),
        ({"databases": [{"name": "x", "kind": "sql", "database_name": "p_other_abc123"}]}, "not_hosted"),
        ({"databases": [{"name": "x", "kind": "sql", "database_name": "mysql"}]}, "not_hosted"),
        ({"image_tag": f"deployer-app/{uuid.uuid4()}:{uuid.uuid4()}"}, "validation_error"),
        ({"repo_url": "https://user@github.com/acme/shop"}, "validation_error"),
        ({"root_dir": "../etc"}, "validation_error"),
        ({"hostnames": ["not a host"]}, "validation_error"),
    ):
        with pytest.raises(ApiError) as exc:
            device_host.dispatch("apps.deploy", deploy_params(**bad), ctx)
        assert exc.value.code == code, bad
    assert docker.calls == []


def test_device_private_repo_withheld_or_shared(db, docker, hosted, monkeypatch):  # noqa: F811
    ctx = device_host.CallContext()
    docker.fail_at = "clone"
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("apps.deploy", deploy_params(repo_access_withheld=True), ctx)
    assert (exc.value.code, exc.value.message) == ("repo_access_withheld", device_apps.WITHHELD_MESSAGE)
    assert docker.containers == {}

    token = new_token()
    docker.leak = token  # the clone error echoes the token: it must not come back
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("apps.deploy", deploy_params(repo_token=token), ctx)
    assert exc.value.code == "app_deploy_failed" and token not in exc.value.message

    docker.fail_at = None
    seen = []
    original = docker.git_clone
    monkeypatch.setattr(
        docker,
        "git_clone",
        lambda url, branch, dest, *, token, on_line=None: (
            seen.append(token),
            original(url, branch, dest, token=token),
        ),
    )
    assert device_host.dispatch("apps.deploy", deploy_params(repo_token=token), ctx)["status"] == "live"
    assert seen == [token]


def test_device_apps_tunnel_token(db, state_dir):  # noqa: F811
    ctx = device_host.CallContext()
    token = secrets.token_urlsafe(24)
    assert device_host.dispatch("apps.tunnel", {"token": token}, ctx) == {"tunnel": device_apps.fingerprint(token)}
    assert desired(state_dir) == {"mode": "off", "apps_token": token}
    assert device_host.dispatch("apps.status", {}, ctx)["tunnel"] == device_apps.fingerprint(token)
    with pytest.raises(ApiError):
        device_host.dispatch("apps.tunnel", {"token": "not a token"}, ctx)
    device_host.dispatch("apps.tunnel", {"token": None}, ctx)
    assert desired(state_dir) == {"mode": "off"}


# --- migration ------------------------------------------------------------------------------------


def test_migration_0010(tmp_path):
    db_file = tmp_path / "scratch.db"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db_file)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    apps = {row[1] for row in conn.execute("PRAGMA table_info(apps)")}
    versions = {row[1] for row in conn.execute("PRAGMA table_info(sync_versions)")}
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(app_replicas)")}
    assert "app_replicas" in tables and {"cohost", "cohost_share_repo_access"} <= apps and "echo" in versions
    assert {"ix_app_replicas_app_id", "ix_app_replicas_device_id"} <= indexes
    conn.close()
    command.downgrade(cfg, "0009")
    conn = sqlite3.connect(db_file)
    assert "cohost" not in {row[1] for row in conn.execute("PRAGMA table_info(apps)")}
    assert "app_replicas" not in {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    command.upgrade(cfg, "head")


def test_jobs_of_deleted_apps_are_skipped(db, team):
    app = make_app(db, team["project"], cohost=True)
    job = jobs.enqueue(db, type="app.replicate", params={"app_id": app.id, "device_id": team["device"].id})
    db.delete(db.get(App, app.id))
    db.commit()
    assert jobs.run_job(job.id) == "succeeded"
    db.expire_all()
    assert db.get(Job, job.id).result == {"skipped": "not co-hosted"}
