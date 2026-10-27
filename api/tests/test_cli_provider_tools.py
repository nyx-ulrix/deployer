"""`deployer google-apis` and `deployer webhook` (docs/CLI.md): they drive gcloud / gh, faked here."""

import json
import subprocess

from tests import test_cli_client
from tests.apps_support import make_app

cli = test_cli_client.cli  # the fixture
_login = test_cli_client._login


def _fake_run(cli, monkeypatch, answers):
    """Replaces the CLI's subprocess runner; `answers(cmd, stdin)` returns (returncode, stdout)."""
    ran = []

    def run(cmd, *, stdin=None):
        ran.append((cmd, stdin))
        code, out = answers(cmd, stdin)
        return subprocess.CompletedProcess(cmd, code, out, "" if code == 0 else "boom")

    monkeypatch.setattr(cli, "_run", run)
    return ran


def test_google_apis_takes_the_project_from_the_apps_client_id(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    make_app(db, project, "Kanban", env={"GOOGLE_CLIENT_ID": "288417034809-abc.apps.googleusercontent.com"})
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()

    def answers(cmd, _stdin):
        if cmd[-2:] == ["get-value", "account"]:
            return 0, "me@example.com\n"
        if "list" in cmd:
            return 0, "calendar-json.googleapis.com\ndrive.googleapis.com\n"
        return 0, ""

    ran = _fake_run(cli, monkeypatch, answers)
    assert cli.main(["google-apis", "calendar", "drive", "--app", "kanban"]) == 0
    enable = next(cmd for cmd, _ in ran if "enable" in cmd)
    assert enable[-3:] == ["calendar-json.googleapis.com", "drive.googleapis.com", "--project=288417034809"]
    assert "288417034809" in capsys.readouterr().out


def test_google_apis_needs_gcloud_signed_in(cli, client, owner_headers, monkeypatch, capsys):
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    ran = _fake_run(cli, monkeypatch, lambda cmd, _stdin: (0, ""))
    assert cli.main(["google-apis", "calendar", "--project", "123"]) == 1
    assert "gcloud auth login" in capsys.readouterr().err
    assert not [cmd for cmd, _ in ran if "enable" in cmd]


def test_webhook_through_gh_sends_the_secret_on_stdin_only(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    make_app(db, project, "Shop")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()

    def answers(cmd, _stdin):
        if cmd[:3] == ["gh", "api", "user"]:
            return 0, "octocat\n"
        if cmd[:3] == ["gh", "api", "repos/acme/shop/hooks"]:
            return 0, ""  # no hook for this URL yet
        return 0, "{}"

    ran = _fake_run(cli, monkeypatch, answers)
    assert cli.main(["webhook", "shop"]) == 0
    cmd, stdin = ran[-1]
    assert cmd[:5] == ["gh", "api", "-X", "POST", "repos/acme/shop/hooks"]
    body = json.loads(stdin)
    secret = body["config"]["secret"]
    assert body["events"] == ["push"] and secret
    assert all(secret not in part for c, _ in ran for part in c)
    out = capsys.readouterr()
    assert "added on acme/shop" in out.out and secret not in out.out + out.err


def test_webhook_without_a_connection_or_gh_says_what_to_do(
    cli, client, db, owner, owner_headers, make_project, monkeypatch, capsys
):
    project = make_project(owner, "Tools")
    make_app(db, project, "Shop")
    _login(cli, client, owner_headers, monkeypatch)
    capsys.readouterr()
    _fake_run(cli, monkeypatch, lambda cmd, _stdin: (1, ""))
    assert cli.main(["webhook", "shop"]) == 1
    assert "gh auth login" in capsys.readouterr().err
