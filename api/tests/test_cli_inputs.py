"""Input requests (docs/CLI.md "Input requests")."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql

from app.errors import ApiError
from app.models import App, AuditLog, CliInput, ProjectMember, utcnow
from app.routers.apps import _check_env
from app.services import cli_inputs, cli_tokens, deployments
from app.services.tokens import create_access_token
from tests.apps_support import make_app

FIELDS = [
    {"key": "GOOGLE_CLIENT_ID", "label": "Client ID", "pattern": r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$"},
    {"key": "GOOGLE_CLIENT_SECRET", "label": "Client secret", "secret": True},
    {"key": "NOTE", "label": "Note", "optional": True, "multiline": True, "link": "https://example.com/code"},
]
CLIENT_ID = "123-abc.apps.googleusercontent.com"
SECRET = "GOCSPX-unit-test-secret-value"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _issue(db, user, name="test"):
    row, raw = cli_tokens.issue_token(db, user, name)
    db.commit()
    return row, bearer(raw)


@pytest.fixture
def token(db, owner):
    return _issue(db, owner)[1]


def _create(client, headers, **extra):
    resp = client.post(
        "/v1/auth/cli/inputs", json={"title": "Google sign-in", "fields": FIELDS, **extra}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _poll(client, headers, input_id):
    return client.post(f"/v1/auth/cli/inputs/{input_id}/poll", headers=headers)


def _submit(client, headers, input_id, values):
    return client.post(f"/v1/inputs/{input_id}/submit", json={"values": values}, headers=headers)


def test_create_with_token_or_session(client, owner_headers, token):
    data = _create(client, token, description="Paste the values from the console.")
    assert data["expires_in"] == 1800 and data["interval"] == 3
    assert data["url"].endswith(f"/input/{data['id']}")
    assert _create(client, owner_headers)["id"] != data["id"]
    assert client.post("/v1/auth/cli/inputs", json={"title": "x", "fields": FIELDS}).status_code == 401

    page = client.get(f"/v1/inputs/{data['id']}", headers=owner_headers).json()
    assert page["title"] == "Google sign-in" and page["status"] == "pending" and page["apps"] == []
    assert page["description"] == "Paste the values from the console."
    assert [f["key"] for f in page["fields"]] == ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "NOTE"]
    assert page["fields"][1]["secret"] is True and page["fields"][2]["link"] == "https://example.com/code"
    # Only a signed-in dashboard session can open the form.
    assert client.get(f"/v1/inputs/{data['id']}", headers=token).status_code == 403


def test_create_is_rate_limited_per_user(client, owner_headers, token, make_user, auth_headers):
    for _ in range(30):
        _create(client, token)
    resp = client.post("/v1/auth/cli/inputs", json={"title": "x", "fields": FIELDS}, headers=owner_headers)
    assert resp.status_code == 429 and resp.json()["error"]["code"] == "rate_limited"
    _create(client, auth_headers(make_user()))  # another user has their own budget


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x", "fields": []},
        {"title": " ", "fields": FIELDS},
        {"title": "x", "fields": [{"key": "1BAD", "label": "x"}]},
        {"title": "x", "fields": [{"key": "A", "label": "x"}, {"key": "A", "label": "y"}]},
        {"title": "x", "fields": [{"key": "A", "label": "x", "pattern": "("}]},
        {"title": "x", "fields": [{"key": "A", "label": "x", "pattern": "a{4294967296}"}]},  # OverflowError
        {"title": "x", "fields": [{"key": "TOKEN\n", "label": "x"}]},
        {"title": "x", "fields": [{"key": "K" * 129, "label": "x"}]},
        {"title": "x", "fields": [{"key": "A", "label": "x", "link": "http://example.com"}]},
        {"title": "x", "fields": [{"key": f"K{i}", "label": "x"} for i in range(11)]},
    ],
)
def test_create_validation(client, owner_headers, body):
    assert client.post("/v1/auth/cli/inputs", json=body, headers=owner_headers).status_code == 422


def test_values_are_returned_once_then_wiped(client, db, owner_headers, token):
    data = _create(client, token)
    assert _poll(client, token, data["id"]).json() == {"status": "pending", "interval": 3}

    resp = _submit(
        client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": f"  {CLIENT_ID} ", "GOOGLE_CLIENT_SECRET": SECRET}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "keys": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]}
    db.expire_all()
    row = db.get(CliInput, data["id"])
    assert row.values_encrypted and SECRET not in row.values_encrypted

    out = _poll(client, token, data["id"]).json()
    assert out == {"status": "submitted", "values": {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": SECRET}}
    assert _poll(client, token, data["id"]).json() == {"status": "consumed", "interval": 3}
    db.expire_all()
    assert db.get(CliInput, data["id"]).values_encrypted is None
    assert _submit(client, owner_headers, data["id"], {}).json()["error"]["code"] == "input_not_pending"

    # The audit log names the keys, never the values.
    details = [str(r.details) for r in db.scalars(select(AuditLog).where(AuditLog.action.like("cli.input%")))]
    assert len(details) == 2 and not any(SECRET in d or CLIENT_ID in d for d in details)


def test_submit_validation(client, owner_headers, token):
    data = _create(client, token)

    def error(values):
        resp = _submit(client, owner_headers, data["id"], values)
        assert resp.status_code == 422, resp.text
        return resp.json()["error"]["details"]["field"]

    good = {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"}
    assert error({"GOOGLE_CLIENT_ID": CLIENT_ID}) == "GOOGLE_CLIENT_SECRET"
    assert error({**good, "GOOGLE_CLIENT_SECRET": "   "}) == "GOOGLE_CLIENT_SECRET"
    assert error({**good, "OTHER": "x"}) == "OTHER"
    assert error({**good, "GOOGLE_CLIENT_SECRET": "a\nb"}) == "GOOGLE_CLIENT_SECRET"
    assert error({**good, "GOOGLE_CLIENT_SECRET": "x" * (8 * 1024 + 1)}) == "GOOGLE_CLIENT_SECRET"
    assert _poll(client, token, data["id"]).json()["status"] == "pending"
    # multiline fields take several lines; `pattern` is the browser's hint only, the server never runs it
    resp = _submit(client, owner_headers, data["id"], {**good, "GOOGLE_CLIENT_ID": "x", "NOTE": "line 1\nline 2"})
    assert resp.status_code == 200 and resp.json()["keys"] == ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "NOTE"]


def test_values_are_capped_together(client, owner_headers, token):
    fields = [{"key": f"PEM{i}", "label": f"PEM {i}", "multiline": True} for i in range(7)]
    data = _create(client, token, fields=fields)
    resp = _submit(client, owner_headers, data["id"], {f"PEM{i}": "x" * 8000 for i in range(7)})
    assert resp.status_code == 422 and "48 KB" in resp.json()["error"]["message"]
    assert "field" not in (resp.json()["error"].get("details") or {})
    # Non-ASCII text is counted (and stored) as UTF-8, not as \uXXXX escapes.
    values = {f"PEM{i}": "\u9375" * 2000 for i in range(7)}  # 7 x 6 KB
    assert _submit(client, owner_headers, data["id"], values).status_code == 200
    assert _poll(client, token, data["id"]).json()["values"] == values
    # TEXT (64 KB) on MariaDB can't hold 48 KB once encrypted and base64'd.
    assert CliInput.__table__.c.values_encrypted.type.compile(dialect=mysql.dialect()) == "MEDIUMTEXT"


def test_key_names_match_the_environment(client, owner, owner_headers, token, db, make_project):
    app = make_app(db, make_project(owner), "Kanban")
    long_key = "K" * 128
    data = _create(client, token, app_ids=[app.id], fields=[{"key": long_key, "label": "Long"}])
    assert _submit(client, owner_headers, data["id"], {long_key: "v"}).status_code == 200
    with pytest.raises(ValueError):
        _check_env({"TOKEN\n": "v"})  # PATCH env_set too: `$` would match before a final newline


def test_token_cannot_fill_and_others_cannot_see(client, owner_headers, token, make_user, auth_headers):
    data = _create(client, token)
    values = {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"}
    assert _submit(client, token, data["id"], values).status_code == 403

    stranger = auth_headers(make_user())
    assert _submit(client, stranger, data["id"], values).status_code == 404
    assert client.get(f"/v1/inputs/{data['id']}", headers=stranger).status_code == 404
    assert _poll(client, stranger, data["id"]).status_code == 404
    assert client.post(f"/v1/auth/cli/inputs/{data['id']}/cancel", headers=stranger).status_code == 404
    assert _poll(client, token, data["id"]).json()["status"] == "pending"


def test_expired_and_cancelled(client, db, owner_headers, token):
    data = _create(client, token)
    row = db.get(CliInput, data["id"])
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    resp = _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "input_not_pending"
    assert _poll(client, token, data["id"]).json() == {"status": "expired", "interval": 3}
    assert client.get(f"/v1/inputs/{data['id']}", headers=owner_headers).json()["status"] == "expired"

    data = _create(client, token)
    resp = client.post(f"/v1/auth/cli/inputs/{data['id']}/cancel", headers=token)
    assert resp.json() == {"ok": True, "status": "cancelled"}
    assert _poll(client, token, data["id"]).json()["status"] == "cancelled"
    resp = _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"})
    assert resp.status_code == 409
    resp = client.post(f"/v1/auth/cli/inputs/{data['id']}/cancel", headers=token)
    assert resp.json() == {"ok": True, "status": "cancelled"}


def test_cancel_after_submit(client, db, owner, owner_headers, token, make_project):
    # Without app_ids the values nobody collected are dropped.
    data = _create(client, token)
    _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": SECRET})
    resp = client.post(f"/v1/auth/cli/inputs/{data['id']}/cancel", headers=token)
    assert resp.json() == {"ok": True, "status": "cancelled"}
    db.expire_all()
    assert db.get(CliInput, data["id"]).values_encrypted is None
    assert _poll(client, token, data["id"]).json() == {"status": "cancelled", "interval": 3}

    # With app_ids the values are already in the Environment: the request stays submitted.
    app = make_app(db, make_project(owner), "Kanban")
    data = _create(client, token, app_ids=[app.id])
    _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": SECRET})
    resp = client.post(f"/v1/auth/cli/inputs/{data['id']}/cancel", headers=token)
    assert resp.json() == {"ok": True, "status": "submitted"}
    assert _poll(client, token, data["id"]).json()["status"] == "submitted"
    db.expire_all()
    assert deployments.env_of(db.get(App, app.id))["GOOGLE_CLIENT_SECRET"] == SECRET


def test_values_are_delivered_exactly_once(client, db, owner, owner_headers, token, monkeypatch):
    """Each change is a conditional UPDATE: a request that read the row before another changed it gets
    nothing (here `db` holds the stale copy a concurrent poll, cancel or submit would have)."""
    data = _create(client, token)
    stale = db.get(CliInput, data["id"])
    assert stale.status == "pending"
    assert client.post(f"/v1/auth/cli/inputs/{data['id']}/cancel", headers=token).status_code == 200
    with pytest.raises(ApiError) as exc:
        cli_inputs.mark_submitted(db, stale, {"GOOGLE_CLIENT_ID": CLIENT_ID})
    assert exc.value.status_code == 409 and stale.status == "cancelled"
    db.rollback()

    data = _create(client, token)
    _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": SECRET})
    stale = db.get(CliInput, data["id"])
    assert stale.status == "submitted" and stale.values_encrypted
    assert "values" in _poll(client, token, data["id"]).json()
    assert stale.status == "submitted" and stale.values_encrypted
    monkeypatch.setattr(cli_inputs, "decrypt_secret", lambda _: pytest.fail("the second poll got the values"))
    assert cli_inputs.poll(db, owner, stale) == {"status": "consumed", "interval": 3}
    assert cli_inputs.cancel(db, stale) == "consumed"
    db.commit()


def test_poll_and_cancel_answer_only_the_creating_credential(client, db, owner, owner_headers, token):
    data = _create(client, token)
    _, other_token = _issue(db, owner, "other")
    for headers in (other_token, owner_headers):
        assert _poll(client, headers, data["id"]).status_code == 404
        assert client.post(f"/v1/auth/cli/inputs/{data['id']}/cancel", headers=headers).status_code == 404
    assert _poll(client, token, data["id"]).json()["status"] == "pending"

    # Made by a session: any session of that user, but no token.
    data = _create(client, owner_headers)
    assert _poll(client, token, data["id"]).status_code == 404
    another_session = bearer(create_access_token(owner))
    assert _poll(client, another_session, data["id"]).json()["status"] == "pending"


def test_requested_by(client, db, owner, owner_headers):
    row, headers = _issue(db, owner, "jiaen-server (agent)")
    data = _create(client, headers)
    page = client.get(f"/v1/inputs/{data['id']}", headers=owner_headers).json()
    assert page["requested_by"] == {"kind": "cli", "name": "jiaen-server (agent)", "prefix": row.prefix}
    assert row.prefix.startswith("dpt_")
    data = _create(client, owner_headers)
    page = client.get(f"/v1/inputs/{data['id']}", headers=owner_headers).json()
    assert page["requested_by"] == {"kind": "session", "name": None, "prefix": None}


def test_revoking_the_token_cancels_its_requests(client, db, owner, owner_headers, make_project):
    row, headers = _issue(db, owner)
    pending = _create(client, headers)
    held = _create(client, headers)
    _submit(client, owner_headers, held["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": SECRET})
    app = make_app(db, make_project(owner), "Kanban")
    saved = _create(client, headers, app_ids=[app.id])
    _submit(client, owner_headers, saved["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": SECRET})
    other = _create(client, _issue(db, owner, "other")[1])

    assert client.delete(f"/v1/auth/cli/tokens/{row.id}", headers=owner_headers).status_code == 200
    db.expire_all()
    status = {
        key: db.get(CliInput, d["id"]).status for key, d in [("p", pending), ("h", held), ("s", saved), ("o", other)]
    }
    assert status == {"p": "cancelled", "h": "cancelled", "s": "submitted", "o": "pending"}
    assert db.get(CliInput, held["id"]).values_encrypted is None


def test_uncollected_values_are_dropped(client, db, owner_headers, token):
    data = _create(client, token)
    _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"})
    row = db.get(CliInput, data["id"])
    row.submitted_at = utcnow() - cli_inputs.VALUES_TTL - timedelta(seconds=1)
    db.commit()
    assert _poll(client, token, data["id"]).json()["status"] == "expired"
    db.expire_all()
    assert db.get(CliInput, data["id"]).values_encrypted is None


def test_scheduler_tick_drops_uncollected_values_without_a_poll(client, db, owner_headers, token):
    """The command line that would poll may be gone: the worker's tick (worker.scheduler_tick) wipes them."""
    old, fresh = _create(client, token), _create(client, token)
    for data in (old, fresh):
        _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"})
    db.get(CliInput, old["id"]).submitted_at = utcnow() - cli_inputs.VALUES_TTL - timedelta(seconds=1)
    db.commit()
    assert cli_inputs.expire_due(db) == 1
    db.commit()
    db.expire_all()
    assert db.get(CliInput, old["id"]).status == "expired" and db.get(CliInput, old["id"]).values_encrypted is None
    assert db.get(CliInput, fresh["id"]).values_encrypted is not None
    assert cli_inputs.prune(db) == 0  # rows themselves go a day after expiry


def test_app_ids_write_the_environment(client, db, owner, owner_headers, token, make_user, make_project, auth_headers):
    project = make_project(owner, "Kanban project")
    app = make_app(db, project, "Kanban", env={"KEEP": "1", "GOOGLE_CLIENT_SECRET": "old"})
    data = _create(client, token, app_ids=[app.id])
    page = client.get(f"/v1/inputs/{data['id']}", headers=owner_headers).json()
    assert page["apps"] == [{"id": app.id, "name": "Kanban", "project_name": "Kanban project"}]

    resp = _submit(client, owner_headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "new"})
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert deployments.env_of(db.get(type(app), app.id)) == {
        "KEEP": "1",
        "GOOGLE_CLIENT_SECRET": "new",
        "GOOGLE_CLIENT_ID": CLIENT_ID,
    }
    row = db.get(CliInput, data["id"])
    assert row.values_encrypted is None

    out = _poll(client, token, data["id"]).json()
    assert out == {
        "status": "submitted",
        "keys": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        "apps": [{"id": app.id, "name": "Kanban"}],
    }
    page = client.get(f"/v1/inputs/{data['id']}", headers=owner_headers)
    assert page.json()["status"] == "submitted" and "values" not in page.json() and "new" not in page.text
    assert "values" not in _poll(client, token, data["id"]).json()
    rows = db.scalars(select(AuditLog).where(AuditLog.project_id == project.id)).all()
    assert [r.action for r in rows] == ["app.update"] and "new" not in str(rows[0].details)


def test_app_ids_need_developer(client, db, owner, make_user, make_project, auth_headers):
    dev, viewer, outsider = make_user(), make_user(), make_user()
    project = make_project(owner, members={dev: "developer", viewer: "viewer"})
    app = make_app(db, project, "Kanban")
    body = {"title": "x", "fields": [{"key": "TOKEN", "label": "Token"}], "app_ids": [app.id]}
    for user in (viewer, outsider):
        assert client.post("/v1/auth/cli/inputs", json=body, headers=auth_headers(user)).status_code == 404
    unknown = {**body, "app_ids": ["no-such-app"]}
    assert client.post("/v1/auth/cli/inputs", json=unknown, headers=auth_headers(dev)).status_code == 404
    # The same answer for an app that exists in someone else's project and one that doesn't exist.
    messages = {
        client.post("/v1/auth/cli/inputs", json=b, headers=auth_headers(outsider)).json()["error"]["message"]
        for b in (body, unknown)
    }
    assert messages == {"App not found"}
    reserved = {**body, "fields": [{"key": "PATH", "label": "Path"}]}
    assert client.post("/v1/auth/cli/inputs", json=reserved, headers=auth_headers(dev)).status_code == 422
    assert client.post("/v1/auth/cli/inputs", json=body, headers=auth_headers(dev)).status_code == 201


def test_env_size_limit_on_submit(client, db, owner, owner_headers, token, make_project):
    app = make_app(db, make_project(owner), "Kanban", env={f"V{i}": "x" * 7000 for i in range(9)})
    data = _create(client, token, app_ids=[app.id], fields=[{"key": "BIG", "label": "Big"}])
    resp = _submit(client, owner_headers, data["id"], {"BIG": "y" * 8000})
    assert resp.status_code == 422
    assert _poll(client, token, data["id"]).json()["status"] == "pending"


def test_prune_drops_old_requests(db, owner):
    old = cli_inputs.create(db, owner, title="old", description=None, fields=[], app_ids=None)
    old.expires_at = utcnow() - timedelta(days=2)
    fresh = cli_inputs.create(db, owner, title="fresh", description=None, fields=[], app_ids=None)
    db.commit()
    assert cli_inputs.prune(db) == 1
    db.commit()
    assert db.get(CliInput, fresh.id) is not None and db.get(CliInput, old.id) is None


def test_unavailable_apps(client, db, owner, make_user, make_project, auth_headers):
    """An app deleted, or a role lost, after create: the page and the poll say so, and submit refuses."""
    dev = make_user()
    project = make_project(owner, "Tools", members={dev: "developer"})
    kanban = make_app(db, project, "Kanban", env={"KEEP": "1"})
    printer = make_app(db, make_project(owner, "Printer", members={dev: "developer"}), "Printer")
    headers = auth_headers(dev)
    data = _create(client, headers, app_ids=[kanban.id, printer.id])
    page = client.get(f"/v1/inputs/{data['id']}", headers=headers).json()
    assert page["unavailable_apps"] == 0 and len(page["apps"]) == 2

    db.delete(db.get(App, printer.id))
    db.commit()
    page = client.get(f"/v1/inputs/{data['id']}", headers=headers).json()
    assert page["unavailable_apps"] == 1 and [a["id"] for a in page["apps"]] == [kanban.id]
    assert _poll(client, headers, data["id"]).json() == {"status": "pending", "interval": 3, "unavailable_apps": 1}
    resp = _submit(client, headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "input_apps_unavailable"
    db.expire_all()
    assert deployments.env_of(db.get(App, kanban.id)) == {"KEEP": "1"}
    assert db.get(CliInput, data["id"]).status == "pending"

    # Demoted to viewer: the same, and still nothing is written.
    data = _create(client, headers, app_ids=[kanban.id])
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == dev.id)
    )
    member.role = "viewer"
    db.commit()
    assert client.get(f"/v1/inputs/{data['id']}", headers=headers).json()["unavailable_apps"] == 1
    resp = _submit(client, headers, data["id"], {"GOOGLE_CLIENT_ID": CLIENT_ID, "GOOGLE_CLIENT_SECRET": "s"})
    assert resp.status_code == 409
    db.expire_all()
    assert deployments.env_of(db.get(App, kanban.id)) == {"KEEP": "1"}


def test_app_ids_submit_with_nothing_typed_changes_nothing(client, db, owner, owner_headers, token, make_project):
    project = make_project(owner)
    app = make_app(db, project, "Kanban", env={"KEEP": "1"})
    data = _create(client, token, app_ids=[app.id], fields=[{"key": "NOTE", "label": "Note", "optional": True}])
    resp = _submit(client, owner_headers, data["id"], {"NOTE": "  "})
    assert resp.json() == {"ok": True, "keys": []}
    db.expire_all()
    assert deployments.env_of(db.get(App, app.id)) == {"KEEP": "1"}
    actions = db.scalars(select(AuditLog.action).where(AuditLog.action.in_(["app.update", "cli.input_submit"]))).all()
    assert actions == []
    assert _poll(client, token, data["id"]).json() == {
        "status": "submitted",
        "keys": [],
        "apps": [{"id": app.id, "name": "Kanban"}],
    }
