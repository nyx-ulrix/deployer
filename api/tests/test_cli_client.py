"""installer/deployer_cli.py end to end against this API (docs/CLI.md): its HTTP calls go to the test client."""

import importlib.util
import io
import json
import stat
import urllib.error
from pathlib import Path

import pytest

from app.services import deployments
from tests.apps_support import make_app

CLI_PATH = Path(__file__).resolve().parents[2] / "installer" / "deployer_cli.py"


@pytest.fixture
def cli(client, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("deployer_cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("DEPLOYER_CONFIG", str(tmp_path / "cli.json"))
    for var in ("DEPLOYER_URL", "DEPLOYER_TOKEN", "SUDO_USER"):
        monkeypatch.delenv(var, raising=False)
    calls = []

    class Response:
        def __init__(self, body: bytes):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(req, timeout=None):
        path = req.full_url.split("://", 1)[1]
        path = path[path.index("/") :]
        calls.append((req.get_method(), path))
        resp = client.request(req.get_method(), path, content=req.data, headers=dict(req.header_items()))
        if resp.status_code >= 400:
            raise urllib.error.HTTPError(req.full_url, resp.status_code, "error", {}, io.BytesIO(resp.content))
        return Response(resp.content)

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    module.calls = calls
    return module


def _login(cli, client, owner_headers, monkeypatch):
    """Runs `deployer login`; the first poll wait is when the user approves the code in the dashboard."""
    approved = {}

    def approve_once(_seconds):
        if approved:
            return
        login = client.get("/v1/auth/cli/logins", params={"code": cli_code["code"]}, headers=owner_headers).json()
        resp = client.post(
            f"/v1/auth/cli/logins/{login['id']}/approve", json={"user_code": login["user_code"]}, headers=owner_headers
        )
        approved["ok"] = resp.status_code == 200

    cli_code = {}
    real_call = cli.Api.call

    def call(self, method, path, body=None, *, auth=True):
        out = real_call(self, method, path, body, auth=auth)
        if path == "/auth/cli/logins" and method == "POST":
            cli_code["code"] = out["user_code"]
        return out

    monkeypatch.setattr(cli.Api, "call", call)
    monkeypatch.setattr(cli.time, "sleep", approve_once)
    assert cli.main(["login", "--url", "http://deployer.test"]) == 0
    assert approved["ok"]
    monkeypatch.setattr(cli.Api, "call", real_call)


def test_login_saves_a_private_token_and_whoami_uses_it(
    cli, client, owner, owner_headers, monkeypatch, capsys, tmp_path
):
    _login(cli, client, owner_headers, monkeypatch)
    out = capsys.readouterr().out
    assert "/cli/approve?code=" in out and f"Signed in as {owner.email}" in out
    path = tmp_path / "cli.json"
    saved = json.loads(path.read_text())
    assert saved["url"] == "http://deployer.test" and saved["token"].startswith("dpt_")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert cli.main(["whoami"]) == 0
    assert owner.email in capsys.readouterr().out

    assert cli.main(["logout"]) == 0
    assert not path.exists()
    assert client.get("/v1/auth/me", headers={"Authorization": f"Bearer {saved['token']}"}).status_code == 401


def test_env_commands_never_print_secrets(cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban", env={"KEEP": "1"})
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()

    assert cli.main(["env", "set", "kanban", "SESSION_SECRET", "--generate"]) == 0
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("typed-secret\n"))
    assert cli.main(["env", "set", "tools/kanban", "AGENT_TOKEN"]) == 0
    out = capsys.readouterr().out
    db.expire_all()
    env = deployments.env_of(db.get(type(app), app.id))
    assert env["KEEP"] == "1" and env["AGENT_TOKEN"] == "typed-secret"
    assert len(env["SESSION_SECRET"]) == 64 and int(env["SESSION_SECRET"], 16) >= 0
    assert env["SESSION_SECRET"] not in out and "typed-secret" not in out
    # Setting one variable never fetched the others (GET /env is the audited "reveal").
    assert not [c for c in cli.calls if c[1].endswith("/env")]

    assert cli.main(["env", "list", "kanban"]) == 0
    assert capsys.readouterr().out.split() == ["AGENT_TOKEN", "KEEP", "SESSION_SECRET"]
    assert cli.main(["env", "unset", "kanban", "KEEP"]) == 0
    db.expire_all()
    assert "KEEP" not in deployments.env_of(db.get(type(app), app.id))


def test_google_oauth_saves_both_values_on_each_app(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    kanban = make_app(db, project, "Kanban")
    editor = make_app(db, project, "Printer Editor")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()

    # No hostname yet and no --redirect: it says what to do first.
    assert cli.main(["google-oauth", "kanban"]) == 1
    assert "domain add" in capsys.readouterr().err

    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("123-abc.apps.googleusercontent.com\nGOCSPX-secret\n"))
    redirects = ["https://kanban.example.com/auth/callback", "https://printer-editor.example.com/auth/callback"]
    args = ["google-oauth", "kanban", "printer-editor", "--redirect", redirects[0], "--redirect", redirects[1]]
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert all(r in out for r in redirects) and "GOCSPX-secret" not in out
    db.expire_all()
    for app in (kanban, editor):
        env = deployments.env_of(db.get(type(app), app.id))
        assert env == {
            "GOOGLE_CLIENT_ID": "123-abc.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "GOCSPX-secret",
        }


def test_app_lookup(cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys):
    one, two = make_project(owner, "One"), make_project(owner, "Two")
    make_app(db, one, "Site")
    make_app(db, two, "Site")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    assert cli.main(["app", "show", "site"]) == 1
    assert "matches several apps" in capsys.readouterr().err
    assert cli.main(["app", "show", "two/site"]) == 0
    assert "two/site" in capsys.readouterr().out
    assert cli.main(["apps", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2


def test_not_signed_in(cli, capsys):
    assert cli.main(["apps"]) == 1
    assert "deployer login" in capsys.readouterr().err
