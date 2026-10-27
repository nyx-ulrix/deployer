"""installer/deployer_cli.py end to end against this API (docs/CLI.md): its HTTP calls go to the test client."""

import http.client
import importlib.util
import io
import json
import os
import signal
import stat
import threading
import time
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

    def call(self, method, path, body=None, **kw):
        out = real_call(self, method, path, body, **kw)
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
    assert cli.main([*args, "--prompt"]) == 0
    out = capsys.readouterr().out
    assert all(r in out for r in redirects) and "GOCSPX-secret" not in out
    db.expire_all()
    for app in (kanban, editor):
        env = deployments.env_of(db.get(type(app), app.id))
        assert env == {
            "GOOGLE_CLIENT_ID": "123-abc.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "GOCSPX-secret",
        }


def _fill(cli, client, owner_headers, monkeypatch, values):
    """The owner opens the input link and submits the form during the first poll wait."""
    created, filled = {}, {}
    real_call = cli.Api.call

    def call(self, method, path, body=None, **kw):
        out = real_call(self, method, path, body, **kw)
        if path == "/auth/cli/inputs" and method == "POST":
            created.update(out, body=body)
        return out

    def fill_once(_seconds):
        if filled:
            return
        resp = client.post(f"/v1/inputs/{created['id']}/submit", json={"values": values}, headers=owner_headers)
        filled["status"] = resp.status_code

    monkeypatch.setattr(cli.Api, "call", call)
    monkeypatch.setattr(cli.time, "sleep", fill_once)
    return created, filled


def test_env_set_on_the_web_writes_the_value_and_prints_no_secret(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban", env={"KEEP": "1"})
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    created, filled = _fill(cli, client, owner_headers, monkeypatch, {"AGENT_TOKEN": "web-secret"})
    assert cli.main(["env", "set", "kanban", "AGENT_TOKEN"]) == 0
    assert filled["status"] == 200
    assert created["body"]["app_ids"] == [app.id] and created["body"]["fields"][0]["secret"] is True
    assert created["body"]["title"] == "Set AGENT_TOKEN"  # the page names the app itself
    captured = capsys.readouterr()
    assert f"/input/{created['id']}" in captured.err and "Set AGENT_TOKEN" in captured.out
    assert "web-secret" not in captured.out + captured.err
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"KEEP": "1", "AGENT_TOKEN": "web-secret"}


def test_google_oauth_on_the_web_saves_both_values_on_each_app(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    kanban = make_app(db, project, "Kanban")
    editor = make_app(db, project, "Printer Editor")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    values = {"GOOGLE_CLIENT_ID": "123-abc.apps.googleusercontent.com", "GOOGLE_CLIENT_SECRET": "GOCSPX-secret"}
    created, filled = _fill(cli, client, owner_headers, monkeypatch, values)
    redirect = "https://kanban.example.com/auth/callback"
    assert cli.main(["google-oauth", "kanban", "printer-editor", "--redirect", redirect]) == 0
    assert filled["status"] == 200
    assert sorted(created["body"]["app_ids"]) == sorted([kanban.id, editor.id])
    assert redirect in created["body"]["description"]
    captured = capsys.readouterr()
    assert redirect in captured.out and "GOCSPX-secret" not in captured.out + captured.err
    db.expire_all()
    for app in (kanban, editor):
        assert deployments.env_of(db.get(type(app), app.id)) == values


def test_ask_prints_the_values_as_json(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    created, filled = _fill(cli, client, owner_headers, monkeypatch, {"CODE": "4711", "TOKEN": "t0p"})
    args = ["ask", "Verification code", "CODE", "TOKEN:secret", "--link", "https://example.com/device", "--json"]
    assert cli.main(args) == 0
    assert filled["status"] == 200
    fields = created["body"]["fields"]
    assert fields[0]["link"] == "https://example.com/device" and fields[1]["secret"] is True
    assert json.loads(capsys.readouterr().out) == {"CODE": "4711", "TOKEN": "t0p"}
    # Delivered once: the request is consumed.
    poll = client.post(f"/v1/auth/cli/inputs/{created['id']}/poll", headers=owner_headers).json()
    assert "values" not in poll


def test_ask_into_an_app_prints_only_the_keys(cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Shop")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    _fill(cli, client, owner_headers, monkeypatch, {"STRIPE_KEY": "sk_live_x"})
    assert cli.main(["ask", "Stripe", "STRIPE_KEY:secret", "--app", "shop"]) == 0
    captured = capsys.readouterr()
    assert "STRIPE_KEY" in captured.out and "sk_live_x" not in captured.out + captured.err
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"STRIPE_KEY": "sk_live_x"}


def test_ctrl_c_cancels_the_request(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)

    def interrupt(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", interrupt)
    assert cli.main(["ask", "Code", "CODE"]) == 130
    cancels = [c for c in cli.calls if c[0] == "POST" and c[1].endswith("/cancel")]
    assert len(cancels) == 1


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


def _fail_on(cli, monkeypatch, match, errors):
    """urlopen raises the next of `errors` for each request whose path contains `match`, then passes."""
    real = cli.urllib.request.urlopen
    queue, seen = list(errors), []

    def urlopen(req, timeout=None):
        seen.append(timeout)
        if match in req.full_url and queue:
            exc = queue.pop(0)
            raise exc(req) if callable(exc) and not isinstance(exc, BaseException) else exc
        return real(req, timeout=timeout)

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)
    return seen


def _http_error(status):
    return lambda req: urllib.error.HTTPError(
        req.full_url, status, "error", {}, io.BytesIO(b"<html>Bad gateway</html>")
    )


def test_poll_retries_transient_failures_until_it_gets_the_value(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    _fill(cli, client, owner_headers, monkeypatch, {"API_KEY": "web-secret"})
    # The API restarts (502), then a poll connection is dropped and one times out: it keeps waiting.
    errors = [_http_error(502), http.client.RemoteDisconnected("closed"), TimeoutError("timed out")]
    _fail_on(cli, monkeypatch, "/poll", errors)
    assert cli.main(["env", "set", "kanban", "API_KEY"]) == 0
    captured = capsys.readouterr()
    assert captured.err.count("retrying") == 1 and "Traceback" not in captured.err
    assert "App Runner or Cloud Run" in captured.out
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"API_KEY": "web-secret"}
    assert not [c for c in cli.calls if c[1].endswith("/cancel")]


def test_poll_gives_up_on_a_404_and_cancels(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    _fail_on(cli, monkeypatch, "/poll", [_http_error(404)])
    assert cli.main(["ask", "Code", "CODE"]) == 1
    assert "retrying" not in capsys.readouterr().err
    assert [c for c in cli.calls if c[1].endswith("/cancel")]


@pytest.mark.parametrize(
    "error", [http.client.RemoteDisconnected("closed"), TimeoutError("timed out"), ConnectionResetError(104, "reset")]
)
def test_ctrl_c_exits_130_even_when_the_cancel_fails(cli, client, owner_headers, monkeypatch, capsys, error):
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()

    def interrupt(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", interrupt)
    timeouts = _fail_on(cli, monkeypatch, "/cancel", [error])
    assert cli.main(["ask", "Code", "CODE"]) == 130
    assert timeouts[-1] == 5  # the cancel waits 5 s at most
    assert "Traceback" not in capsys.readouterr().err


def test_sigterm_cancels_the_request(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)
    before = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(cli.time, "sleep", lambda _s: os.kill(os.getpid(), signal.SIGTERM))
    assert cli.main(["ask", "Code", "CODE"]) == 130
    assert len([c for c in cli.calls if c[1].endswith("/cancel")]) == 1
    assert signal.getsignal(signal.SIGTERM) == before


def _no_input_request(cli):
    return not [c for c in cli.calls if c[1] == "/v1/auth/cli/inputs"]


def test_env_set_reads_a_redirected_file(cli, client, db, owner, owner_headers, make_project, monkeypatch, tmp_path):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    path = tmp_path / "secret.txt"
    path.write_text("file-secret\n")
    with open(path, encoding="utf-8") as fh:
        monkeypatch.setattr(cli.sys, "stdin", fh)
        assert cli.main(["env", "set", "kanban", "API_KEY"]) == 0
    assert _no_input_request(cli)
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"API_KEY": "file-secret"}


def _pipe(monkeypatch, cli, text=None, delay=0.0):
    """stdin is a real pipe; `text` is written after `delay` seconds and the pipe closed (None: left idle)."""
    r, w = os.pipe()
    reader = os.fdopen(r, "r", encoding="utf-8")
    monkeypatch.setattr(cli.sys, "stdin", reader)

    def produce():
        time.sleep(delay)
        os.write(w, text.encode())
        os.close(w)

    if text is not None:
        threading.Thread(target=produce, daemon=True).start()
    return reader, w


def test_env_set_waits_for_a_slow_pipe(cli, client, db, owner, owner_headers, make_project, monkeypatch):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    reader, _ = _pipe(monkeypatch, cli, "piped-value\n", delay=0.6)  # like `op read` or `aws secretsmanager`
    try:
        assert cli.main(["env", "set", "kanban", "API_KEY"]) == 0
    finally:
        reader.close()
    assert _no_input_request(cli)
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"API_KEY": "piped-value"}


def test_env_set_with_an_idle_pipe_asks_on_the_web(cli, client, db, owner, owner_headers, make_project, monkeypatch):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    monkeypatch.setattr(cli, "PIPE_WAIT", 0.05)
    reader, w = _pipe(monkeypatch, cli)  # an agent's stdin: open, never written
    _fill(cli, client, owner_headers, monkeypatch, {"API_KEY": "web-secret"})
    try:
        assert cli.main(["env", "set", "kanban", "API_KEY"]) == 0
    finally:
        reader.close()
        os.close(w)
    assert not _no_input_request(cli)
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"API_KEY": "web-secret"}


def test_env_set_stdin_waits_as_long_as_the_producer_needs(
    cli, client, db, owner, owner_headers, make_project, monkeypatch
):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    monkeypatch.setattr(cli, "PIPE_WAIT", 0.05)
    reader, _ = _pipe(monkeypatch, cli, "slow-value\n", delay=0.3)
    try:
        assert cli.main(["env", "set", "kanban", "API_KEY", "--stdin"]) == 0
    finally:
        reader.close()
    assert _no_input_request(cli)
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"API_KEY": "slow-value"}
    assert cli.main(["env", "set", "kanban", "API_KEY", "--stdin", "--generate"]) == 1


def test_google_oauth_reads_two_piped_lines_without_prompt(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    kanban = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("123-abc.apps.googleusercontent.com\nGOCSPX-secret\n"))
    assert cli.main(["google-oauth", "kanban", "--redirect", "https://kanban.example.com/auth/callback"]) == 0
    assert _no_input_request(cli)
    assert "GOCSPX-secret" not in capsys.readouterr().out
    db.expire_all()
    assert deployments.env_of(db.get(type(kanban), kanban.id)) == {
        "GOOGLE_CLIENT_ID": "123-abc.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "GOCSPX-secret",
    }


def test_ctrl_c_after_a_submit_into_an_app_says_the_values_were_saved(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Shop")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    created, filled = _fill(cli, client, owner_headers, monkeypatch, {"STRIPE_KEY": "sk_live_x"})
    fill = cli.time.sleep

    def fill_then_interrupt(seconds):
        fill(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", fill_then_interrupt)
    assert cli.main(["ask", "Stripe", "STRIPE_KEY:secret", "--app", "shop"]) == 130
    assert filled["status"] == 200
    assert "already been saved" in capsys.readouterr().err
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {"STRIPE_KEY": "sk_live_x"}


def test_an_empty_submit_into_an_app_changes_nothing(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    make_app(db, project, "Shop")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    _fill(cli, client, owner_headers, monkeypatch, {"NOTE": ""})
    assert cli.main(["ask", "Note", "NOTE:optional", "--app", "shop"]) == 0
    assert "Nothing was entered; nothing was changed." in capsys.readouterr().out


def test_a_deleted_app_stops_the_wait_and_cancels(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()

    def delete_app(_seconds):
        if db.get(type(app), app.id) is not None:
            db.delete(db.get(type(app), app.id))
            db.commit()

    monkeypatch.setattr(cli.time, "sleep", delete_app)
    assert cli.main(["env", "set", "kanban", "API_KEY"]) == 1
    assert "no longer exists" in capsys.readouterr().err
    assert len([c for c in cli.calls if c[1].endswith("/cancel")]) == 1


def test_env_set_on_the_web_takes_a_long_name(cli, client, db, owner, owner_headers, make_project, monkeypatch):
    project = make_project(owner, "Tools")
    app = make_app(db, project, "Kanban")
    _login(cli, client, owner_headers, monkeypatch)
    name = "A" * 100
    _fill(cli, client, owner_headers, monkeypatch, {name: "v"})
    assert cli.main(["env", "set", "kanban", name]) == 0
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {name: "v"}


def test_oauth_set_on_the_web_saves_deployers_own_sign_in_app(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    secret = "0123456789abcdef0123456789abcdef01234567"
    created, filled = _fill(
        cli, client, owner_headers, monkeypatch, {"client_id": "Ov23liAbc123", "client_secret": secret}
    )
    assert cli.main(["oauth", "set", "github"]) == 0
    assert filled["status"] == 200
    body = created["body"]
    assert "/v1/auth/oauth/github/callback" in body["description"]
    assert body["fields"][0]["link"].startswith("https://github.com/settings/applications/new?")
    assert body["fields"][1]["secret"] is True and "app_ids" not in body
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    github = client.get("/v1/instance/settings", headers=owner_headers).json()["github"]
    assert github["client_id"] == "Ov23liAbc123" and github["configured"] is True

    assert cli.main(["oauth", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["github"]["configured"] is True and status["google"]["configured"] is False
    assert cli.main(["oauth", "clear", "github"]) == 0
    assert client.get("/v1/instance/settings", headers=owner_headers).json()["github"]["configured"] is False


def test_oauth_set_rejects_a_pasted_secret_in_the_id_field_and_saves_nothing(
    cli, client, owner_headers, monkeypatch, capsys
):
    _login(cli, client, owner_headers, monkeypatch)
    _fill(cli, client, owner_headers, monkeypatch, {"client_id": "GOCSPX-oops", "client_secret": "GOCSPX-secret"})
    assert cli.main(["oauth", "set", "google"]) == 1
    assert "Client secret" in capsys.readouterr().err
    assert client.get("/v1/instance/settings", headers=owner_headers).json()["google"]["client_id"] is None


def test_alerts_set_on_the_web_then_clear(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    hook = "https://hooks.slack.com/services/T000/B000/xyz"
    _fill(cli, client, owner_headers, monkeypatch, {"url": hook})
    assert cli.main(["alerts", "set"]) == 0
    captured = capsys.readouterr()
    assert hook not in captured.out + captured.err
    assert client.get("/v1/instance/settings", headers=owner_headers).json()["alert_webhook_url"] == hook
    assert cli.main(["alerts", "status"]) == 0
    assert "set" in capsys.readouterr().out
    assert cli.main(["alerts", "clear"]) == 0
    assert client.get("/v1/instance/settings", headers=owner_headers).json()["alert_webhook_url"] is None


def test_instance_commands_need_the_owner(cli, client, make_user, monkeypatch, capsys):
    from app.services.tokens import create_access_token

    member = make_user("member@example.com")
    headers = {"Authorization": f"Bearer {create_access_token(member)}"}
    _login(cli, client, headers, monkeypatch)
    capsys.readouterr()
    assert cli.main(["alerts", "status"]) == 1
    assert "instance owner" in capsys.readouterr().err


def test_cloud_add_needs_a_provider_and_name(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    assert cli.main(["cloud", "add", "aws"]) == 1
    assert "Usage: deployer cloud add" in capsys.readouterr().err
    assert not [c for c in cli.calls if c[1] == "/v1/auth/cli/inputs"]
