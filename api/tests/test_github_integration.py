"""GitHub connection (connect/disconnect), repo listing, detect, create with a connection (clone token,
automatic webhook), hook removal and the "connection removed" deploy failure. GitHub is faked at
`github._api`; the OAuth token exchange at `oauth._http_*` (tests.test_oauth.providers)."""

import base64
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.config import get_settings
from app.crypto import decrypt_secret, encrypt_secret
from app.models import App, Deployment, GitHubConnection, User, UserIdentity
from app.services import app_runner, deployments, github, jobs, oauth
from app.services.tokens import REFRESH_COOKIE
from tests.apps_support import FakeDockerCli
from tests.test_oauth import BASE, providers  # noqa: F401 (fixture)

API_DIR = Path(__file__).resolve().parents[1]


class FakeGitHub:
    def __init__(self):
        self.calls: list[tuple] = []
        self.routes: dict[tuple[str, str], tuple[int, object]] = {}

    def __call__(self, method, path, *, token=None, params=None, json_body=None):
        self.calls.append((method, path, token, json_body, params))
        return self.routes.get((method, path), (404, {"message": "Not Found"}))


class TokenDocker(FakeDockerCli):
    def __init__(self):
        super().__init__()
        self.tokens: list[str | None] = []

    def git_clone(self, url, branch, dest, *, token, on_line=None):
        self.tokens.append(token)
        super().git_clone(url, branch, dest, token=token, on_line=on_line)


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github, "_api", fake)
    return fake


@pytest.fixture
def docker(tmp_path, monkeypatch):
    fake = TokenDocker()
    app_runner.set_docker(fake)
    monkeypatch.setattr(get_settings(), "caddy_apps_dir", str(tmp_path / "apps"))
    monkeypatch.setattr(get_settings(), "app_build_dir", str(tmp_path))
    yield fake
    app_runner.set_docker(None)


@pytest.fixture
def env(make_user, make_project, auth_headers):
    owner, admin, dev, viewer = (make_user() for _ in range(4))
    project = make_project(owner, members={admin: "admin", dev: "developer", viewer: "viewer"})
    return {
        "project": project,
        "base": f"/v1/projects/{project.id}/apps",
        "admin": auth_headers(admin),
        "dev": auth_headers(dev),
        "viewer": auth_headers(viewer),
        "dev_user": dev,
    }


def fake_token() -> str:
    return "gh-test-" + secrets.token_hex(16)


def connect(db, user: User) -> str:
    token = fake_token()
    github.save_connection(db, user.id, login="octo", github_user_id="42", token=token, scopes=github.CONNECT_SCOPE)
    db.commit()
    return token


def b64(text: str) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


# --- connect / disconnect ------------------------------------------------------------------------


def test_connect_stores_encrypted_token_and_never_signs_in(client, owner, owner_headers, providers, login, db):  # noqa: F811
    login(owner.email)  # the browser's refresh cookie: the signed-in user who starts the flow
    status = client.get("/v1/integrations/github", headers=owner_headers).json()
    assert status == {"connected": False, "login": None, "scopes": [], "configured": True}

    resp = client.post("/v1/integrations/github/connect", headers=owner_headers)
    assert resp.status_code == 200 and oauth.BROWSER_COOKIE in resp.cookies
    q = {k: v[0] for k, v in parse_qs(urlsplit(resp.json()["url"]).query).items()}
    assert q["scope"] == "repo admin:repo_hook read:user" and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == f"{BASE}/v1/auth/oauth/github/callback"
    users_before = db.query(User).count()

    cb = client.get(
        "/v1/auth/oauth/github/callback", params={"code": "good-code", "state": q["state"]}, follow_redirects=False
    )
    assert cb.headers["location"] == f"{BASE}/integrations/github/done?ok=1"
    assert REFRESH_COOKIE not in cb.cookies  # no sign-in on this path
    assert db.query(User).count() == users_before and db.query(UserIdentity).count() == 0
    row = db.scalar(select(GitHubConnection))
    assert row.user_id == owner.id and (row.github_login, row.github_user_id) == ("octo", "42")
    assert "provider-token" not in row.token_encrypted and decrypt_secret(row.token_encrypted) == "provider-token"

    status = client.get("/v1/integrations/github", headers=owner_headers)
    assert status.json() == {
        "connected": True,
        "login": "octo",
        "scopes": ["repo", "admin:repo_hook", "read:user"],
        "configured": True,
    }
    assert "provider-token" not in status.text
    # The state can't be replayed.
    again = client.get(
        "/v1/auth/oauth/github/callback", params={"code": "good-code", "state": q["state"]}, follow_redirects=False
    )
    assert "oauth_state_invalid" in again.headers["location"]

    gone = client.delete("/v1/integrations/github", headers=owner_headers).json()
    assert gone["ok"] is True and "github.com/settings/applications" in gone["message"]
    assert client.get("/v1/integrations/github", headers=owner_headers).json()["connected"] is False


def test_connect_requires_the_same_signed_in_user(client, owner, providers, login, make_user, auth_headers, db):  # noqa: F811
    other = make_user()
    login(owner.email)  # this browser is signed in as the owner...
    url = client.post("/v1/integrations/github/connect", headers=auth_headers(other)).json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    cb = client.get(
        "/v1/auth/oauth/github/callback", params={"code": "good-code", "state": state}, follow_redirects=False
    )  # ...but the flow was started by `other`
    assert cb.headers["location"] == f"{BASE}/integrations/github/done?error=github_connect_user_mismatch"
    assert db.scalar(select(GitHubConnection)) is None

    client.cookies.clear()  # not signed in at all in this browser
    url = client.post("/v1/integrations/github/connect", headers=auth_headers(owner)).json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    cb = client.get(
        "/v1/auth/oauth/github/callback", params={"code": "good-code", "state": state}, follow_redirects=False
    )
    assert cb.headers["location"].endswith("error=github_connect_user_mismatch")
    assert db.scalar(select(GitHubConnection)) is None and REFRESH_COOKIE not in cb.cookies


def test_connect_needs_configuration_and_auth(client, owner_headers):
    assert client.post("/v1/integrations/github/connect").status_code == 401
    resp = client.post("/v1/integrations/github/connect", headers=owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (400, "provider_not_configured")
    assert client.get("/v1/integrations/github", headers=owner_headers).json()["configured"] is False


# --- repositories --------------------------------------------------------------------------------


def test_list_repos(client, owner, owner_headers, gh, db):
    resp = client.get("/v1/integrations/github/repos", headers=owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "github_not_connected")
    token = connect(db, owner)
    repo = {
        "full_name": "nyx-ulrix/HawkerHub",
        "private": True,
        "default_branch": "main",
        "html_url": "https://github.com/nyx-ulrix/HawkerHub",
        "clone_url": "https://github.com/nyx-ulrix/HawkerHub.git",
        "pushed_at": "2026-09-01T00:00:00Z",
        "description": "Hawker centre finder",
        "owner": {"login": "nyx-ulrix"},
    }
    other = {**repo, "full_name": "acme/site", "private": False, "description": None}
    gh.routes[("GET", "/user/repos")] = (200, [repo, other])
    rows = client.get("/v1/integrations/github/repos", headers=owner_headers).json()
    assert [r["full_name"] for r in rows] == ["nyx-ulrix/HawkerHub", "acme/site"]
    assert set(rows[0]) == {
        "full_name",
        "private",
        "default_branch",
        "html_url",
        "clone_url",
        "pushed_at",
        "description",
    }
    _, _, used, _, params = gh.calls[0]
    assert used == token and params["affiliation"] == "owner,collaborator,organization_member"
    assert params["sort"] == "pushed"
    rows = client.get("/v1/integrations/github/repos", params={"q": "HAWKER"}, headers=owner_headers).json()
    assert [r["full_name"] for r in rows] == ["nyx-ulrix/HawkerHub"]
    gh.routes[("GET", "/user/repos")] = (401, {"message": "Bad credentials"})
    resp = client.get("/v1/integrations/github/repos", headers=owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "github_not_connected")


# --- detect --------------------------------------------------------------------------------------

HAWKERHUB = {
    "requirements.txt": "Flask==3.0.3\nPyMySQL\npymongo\n",
    "app/__init__.py": "def create_app():\n    app = Flask(__name__)\n    return app\n",
    ".env.example": "HH_SQL_HOST=\nHH_SQL_PASSWORD=\nHH_MONGO_URI=\n",
    "app/templates/index.html": "",
}


def serve_repo(gh, full: str, files: dict[str, str], *, private: bool, branch="main"):
    gh.routes[("GET", f"/repos/{full}")] = (
        200,
        {
            "name": full.split("/")[1],
            "private": private,
            "default_branch": branch,
            "html_url": f"https://github.com/{full}",
        },
    )
    tree = [{"path": p, "type": "blob", "size": len(t)} for p, t in files.items()]
    gh.routes[("GET", f"/repos/{full}/git/trees/{branch}")] = (200, {"tree": tree})
    for path, text in files.items():
        gh.routes[("GET", f"/repos/{full}/contents/{path}")] = (200, b64(text))


def test_detect(client, env, gh, db):
    url = f"{env['base']}/detect"
    # Private repository through the caller's connection.
    token = connect(db, env["dev_user"])
    serve_repo(gh, "nyx-ulrix/HawkerHub", HAWKERHUB, private=True)
    resp = client.post(url, json={"repo_url": "https://github.com/nyx-ulrix/HawkerHub.git"}, headers=env["dev"])
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert (d["name"], d["repo_url"], d["branch"], d["private"]) == (
        "HawkerHub",
        "https://github.com/nyx-ulrix/HawkerHub",
        "main",
        True,
    )
    assert d["preset"] == "python" and d["start_command"] == "python -m flask --app app run --host 0.0.0.0 --port 8000"
    assert d["database_access_suggested"] is True and d["env_keys"] == [
        "HH_SQL_HOST",
        "HH_SQL_PASSWORD",
        "HH_MONGO_URI",
    ]
    assert {c[2] for c in gh.calls} == {token}
    assert db.scalar(select(App)) is None  # never persisted

    # Public repository, anonymous (no connection for the admin).
    gh.calls.clear()
    serve_repo(gh, "acme/site", {"index.html": "<h1>hi</h1>"}, private=False, branch="gh-pages")
    d = client.post(url, json={"repo_url": "https://github.com/acme/site"}, headers=env["admin"]).json()
    assert (d["preset"], d["branch"], d["output_dir"]) == ("static", "gh-pages", ".")
    assert {c[2] for c in gh.calls} == {None}

    missing = client.post(url, json={"repo_url": "https://github.com/acme/secret"}, headers=env["admin"])
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "repo_not_accessible"
    assert "connect GitHub for private repositories" in missing.json()["error"]["message"]
    branch = client.post(url, json={"repo_url": "https://github.com/acme/site", "branch": "nope"}, headers=env["admin"])
    assert branch.json()["error"]["code"] == "branch_not_found"

    gh.calls.clear()
    other = client.post(url, json={"repo_url": "https://gitlab.com/acme/shop.git"}, headers=env["dev"]).json()
    assert other["name"] == "shop" and other["detected"] == [] and "Only GitHub" in other["warnings"][0]
    assert gh.calls == []
    assert client.post(url, json={"repo_url": "https://github.com/a/b"}, headers=env["viewer"]).status_code == 403
    assert client.post(url, json={"repo_url": "http://github.com/a/b"}, headers=env["dev"]).status_code == 422


# --- create with a connection --------------------------------------------------------------------

BODY = {"name": "Shop", "repo_url": "https://github.com/acme/shop", "preset": "node", "use_github_connection": True}


def test_create_with_connection_hook_clone_rotate_delete(client, env, gh, docker, set_setting, db):
    set_setting("public_url", "https://deploy.example.com")
    resp = client.post(env["base"], json=BODY, headers=env["dev"])
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "github_not_connected")
    token = connect(db, env["dev_user"])
    assert client.post(env["base"], json={**BODY, "repo_token": fake_token()}, headers=env["dev"]).status_code == 422
    gitlab = {**BODY, "repo_url": "https://gitlab.com/acme/shop"}
    assert client.post(env["base"], json=gitlab, headers=env["dev"]).status_code == 422

    gh.routes[("POST", "/repos/acme/shop/hooks")] = (201, {"id": 123})
    resp = client.post(env["base"], json=BODY, headers=env["dev"])
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["warnings"] == [] and out["has_repo_token"] is False
    assert out["github"] == {"connected_by_email": env["dev_user"].email, "hook_active": True}
    row = db.get(App, out["id"])
    assert (row.github_hook_id, row.github_connection_user_id) == ("123", env["dev_user"].id)
    method, path, used, body, _ = gh.calls[-1]
    assert (method, path, used) == ("POST", "/repos/acme/shop/hooks", token)
    assert body["events"] == ["push"] and body["active"] is True
    assert body["config"] == {
        "url": f"https://deploy.example.com/v1/hooks/github/{row.id}",
        "content_type": "json",
        "secret": deployments.webhook_secret(row),
        "insecure_ssl": "0",
    }
    assert token not in resp.text

    # The deploy job clones with the creator's connection token (redacted from the log).
    docker.leak = token
    dep, _ = deployments.start_deployment(db, row, trigger="manual", user_id=None)
    db.commit()
    jobs.run_queued()
    db.expire_all()
    dep = db.get(Deployment, dep.id)
    assert dep.status == "live" and docker.tokens == [token] and token not in dep.log

    # Rotating the secret updates the hook on GitHub.
    gh.routes[("PATCH", "/repos/acme/shop/hooks/123")] = (200, {"id": 123})
    rotated = client.post(f"{env['base']}/{row.id}/webhook/rotate", headers=env["dev"]).json()
    assert rotated["hook_active"] is True and rotated["warnings"] == []
    assert gh.calls[-1][0:3] == ("PATCH", "/repos/acme/shop/hooks/123", token)
    assert gh.calls[-1][3]["config"]["secret"] == rotated["secret"]

    # Deleting the app (as an admin) removes the hook with the creator's connection.
    assert client.delete(f"{env['base']}/{row.id}", headers=env["admin"]).status_code == 200
    assert gh.calls[-1][0:3] == ("DELETE", "/repos/acme/shop/hooks/123", token)


def test_localhost_public_url_warns_and_skips_hook(client, env, gh, db):
    connect(db, env["dev_user"])
    resp = client.post(env["base"], json=BODY, headers=env["dev"])
    assert resp.status_code == 201
    out = resp.json()
    assert out["warnings"] == [
        "GitHub can't reach http://localhost:8080 — set up a public URL (Settings → Domains) to deploy on push"
    ]
    assert out["github"]["hook_active"] is False and gh.calls == []
    # A manual (non-connection) app has no github block and no warnings.
    plain = client.post(env["base"], json={**BODY, "name": "Plain", "use_github_connection": False}, headers=env["dev"])
    assert plain.json()["github"] is None and plain.json()["warnings"] == []


def test_other_user_changing_the_repo_detaches_the_connection(client, env, gh, set_setting, db):
    set_setting("public_url", "https://deploy.example.com")
    connect(db, env["dev_user"])
    gh.routes[("POST", "/repos/acme/shop/hooks")] = (201, {"id": 7})
    app_id = client.post(env["base"], json=BODY, headers=env["dev"]).json()["id"]
    resp = client.patch(
        f"{env['base']}/{app_id}", json={"repo_url": "https://github.com/evil/fork"}, headers=env["admin"]
    )
    assert resp.status_code == 200 and resp.json()["github"] is None
    assert gh.calls[-1][0:2] == ("DELETE", "/repos/acme/shop/hooks/7")
    db.expire_all()
    assert db.get(App, app_id).github_connection_user_id is None


def test_removed_connection_fails_the_deploy(db, docker, env):
    app = App(
        project_id=env["project"].id,
        name="Shop",
        slug="shop",
        repo_url="https://github.com/acme/shop",
        preset="node",
        port=deployments.allocate_port(db),
        github_connection_user_id=env["dev_user"].id,
        webhook_secret_encrypted=encrypt_secret("s"),
    )
    deployments.set_env(app, {})
    db.add(app)
    db.commit()
    dep, _ = deployments.start_deployment(db, app, trigger="manual", user_id=None)
    db.commit()
    jobs.run_queued()
    db.expire_all()
    dep = db.get(Deployment, dep.id)
    assert dep.status == "failed" and docker.tokens == []
    assert dep.error == (
        f"The GitHub connection of {env['dev_user'].email} was removed; "
        "reconnect GitHub or add a token in the app's settings"
    )


def test_migration_0009(tmp_path):
    db_file = tmp_path / "scratch.db"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db_file)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    columns = [row[1] for row in conn.execute("PRAGMA table_info(apps)")]
    assert "github_connections" in tables and {"github_connection_user_id", "github_hook_id"} <= set(columns)
    conn.close()
    command.downgrade(cfg, "0008")
    conn = sqlite3.connect(db_file)
    assert "github_hook_id" not in [row[1] for row in conn.execute("PRAGMA table_info(apps)")]
    conn.close()
