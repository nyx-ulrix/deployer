"""Command-line logins (device flow) and `dpt_` tokens (docs/CLI.md)."""

import json
from datetime import timedelta

from sqlalchemy import select

from app import cli
from app.models import CliLogin, CliToken, utcnow
from app.services import cli_tokens
from tests.conftest import DEFAULT_PASSWORD

LOGIN = {"name": "deployer CLI on jiaen-server", "hostname": "jiaen-server", "os": "Linux 7.0"}


def _login(client):
    resp = client.post("/v1/auth/cli/logins", json=LOGIN)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _poll(client, fake_redis, data):
    fake_redis.delete(f"cli:login:poll:{data['login_id']}")
    return client.post(f"/v1/auth/cli/logins/{data['login_id']}/poll", json={"poll_secret": data["poll_secret"]})


def _approve(client, headers, data, **extra):
    return client.post(
        f"/v1/auth/cli/logins/{data['login_id']}/approve",
        json={"user_code": data["user_code"], **extra},
        headers=headers,
    )


def _token(client, fake_redis, headers):
    data = _login(client)
    assert _approve(client, headers, data).status_code == 200
    return _poll(client, fake_redis, data).json()["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_full_login_flow(client, db, owner, owner_headers, fake_redis):
    data = _login(client)
    assert data["expires_in"] == 600
    assert data["verification_uri"].endswith(f"/cli/approve?code={data['user_code']}")

    assert _poll(client, fake_redis, data).json()["status"] == "pending"
    resp = client.post(f"/v1/auth/cli/logins/{data['login_id']}/poll", json={"poll_secret": data["poll_secret"]})
    assert resp.status_code == 429 and resp.json()["error"]["code"] == "slow_down"
    fake_redis.delete(f"cli:login:poll:{data['login_id']}")
    assert client.post(f"/v1/auth/cli/logins/{data['login_id']}/poll", json={"poll_secret": "x"}).status_code == 404

    # Looking a code up needs a signed-in user; it accepts the code in any spelling.
    assert client.get("/v1/auth/cli/logins", params={"code": data["user_code"]}).status_code == 401
    code = data["user_code"].lower().replace("-", " ")
    resp = client.get("/v1/auth/cli/logins", params={"code": code}, headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json()["hostname"] == "jiaen-server" and resp.json()["status"] == "pending"

    # The id alone is not enough: the code must match.
    wrong = client.post(
        f"/v1/auth/cli/logins/{data['login_id']}/approve", json={"user_code": "AAAA-AAAA"}, headers=owner_headers
    )
    assert wrong.status_code == 404
    resp = _approve(client, owner_headers, data, name="my server")
    assert resp.status_code == 200, resp.text
    assert resp.json()["token"]["name"] == "my server"
    assert _approve(client, owner_headers, data).json()["error"]["code"] == "login_not_pending"

    out = _poll(client, fake_redis, data).json()
    assert out["status"] == "approved" and out["email"] == owner.email
    token = out["token"]
    assert token.startswith("dpt_")
    # Delivered once; the database keeps only the hash.
    assert _poll(client, fake_redis, data).json() == {"status": "consumed", "interval": 3}
    db.expire_all()
    assert db.scalar(select(CliLogin.token_encrypted).where(CliLogin.id == data["login_id"])) is None
    row = db.scalar(select(CliToken))
    assert row.token_hash != token and token not in (row.prefix, row.name)

    me = client.get("/v1/auth/me", headers=bearer(token))
    assert me.status_code == 200 and me.json()["email"] == owner.email


def test_token_acts_as_the_user_on_project_routes(client, owner, owner_headers, fake_redis):
    token = _token(client, fake_redis, owner_headers)
    resp = client.post("/v1/projects", json={"name": "Kanban"}, headers=bearer(token))
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    assert client.get(f"/v1/projects/{pid}/apps", headers=bearer(token)).status_code == 200


def test_token_cannot_approve_logins_or_change_the_password(client, owner, owner_headers, fake_redis):
    token = _token(client, fake_redis, owner_headers)
    data = _login(client)
    assert _approve(client, bearer(token), data).status_code == 403
    assert (
        client.get("/v1/auth/cli/logins", params={"code": data["user_code"]}, headers=bearer(token)).status_code == 403
    )
    deny = client.post(
        f"/v1/auth/cli/logins/{data['login_id']}/deny", json={"user_code": data["user_code"]}, headers=bearer(token)
    )
    assert deny.status_code == 403
    resp = client.post(
        "/v1/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "another long password"},
        headers=bearer(token),
    )
    assert resp.status_code == 403


def test_deny_and_expiry(client, db, owner, owner_headers, fake_redis):
    data = _login(client)
    resp = client.post(
        f"/v1/auth/cli/logins/{data['login_id']}/deny", json={"user_code": data["user_code"]}, headers=owner_headers
    )
    assert resp.status_code == 200 and resp.json()["status"] == "denied"
    assert _poll(client, fake_redis, data).json()["status"] == "denied"

    data = _login(client)
    row = db.get(CliLogin, data["login_id"])
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _poll(client, fake_redis, data).json()["status"] == "expired"
    assert _approve(client, owner_headers, data).json()["error"]["code"] == "login_not_pending"


def test_list_and_revoke(client, owner, owner_headers, make_user, auth_headers, fake_redis):
    token = _token(client, fake_redis, owner_headers)
    other = _token(client, fake_redis, owner_headers)
    listed = client.get("/v1/auth/cli/tokens", headers=bearer(token)).json()
    assert len(listed) == 2 and [t["current"] for t in listed].count(True) == 1
    assert all(t["prefix"].startswith("dpt_") and len(t["prefix"]) == 12 for t in listed)
    assert "token_hash" not in listed[0]

    # Someone else can't see or revoke them.
    stranger = auth_headers(make_user())
    assert client.get("/v1/auth/cli/tokens", headers=stranger).json() == []
    other_id = next(t["id"] for t in listed if not t["current"])
    assert client.delete(f"/v1/auth/cli/tokens/{other_id}", headers=stranger).status_code == 404

    assert client.delete(f"/v1/auth/cli/tokens/{other_id}", headers=owner_headers).status_code == 200
    resp = client.get("/v1/auth/me", headers=bearer(other))
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "cli_token_revoked"

    # `deployer logout`: a token revokes itself; a session can't use that route.
    assert client.delete("/v1/auth/cli/tokens/current", headers=owner_headers).status_code == 400
    assert client.delete("/v1/auth/cli/tokens/current", headers=bearer(token)).status_code == 200
    assert client.get("/v1/auth/me", headers=bearer(token)).status_code == 401


def test_disabled_user_and_unknown_tokens_are_refused(client, db, owner, owner_headers, fake_redis):
    token = _token(client, fake_redis, owner_headers)
    assert client.get("/v1/auth/me", headers=bearer("dpt_" + "x" * 43)).status_code == 401
    owner.is_active = False
    db.commit()
    assert client.get("/v1/auth/me", headers=bearer(token)).status_code == 401


def test_login_create_is_rate_limited(client, fake_redis):
    for _ in range(20):
        assert client.post("/v1/auth/cli/logins", json={}).status_code == 200
    resp = client.post("/v1/auth/cli/logins", json={})
    assert resp.status_code == 429 and resp.json()["error"]["code"] == "rate_limited"


def test_prune_drops_old_logins(db):
    row, _ = cli_tokens.create_login(db, name=None, hostname=None, os=None)
    row.expires_at = utcnow() - timedelta(days=2)
    fresh, _ = cli_tokens.create_login(db, name=None, hostname=None, os=None)
    db.commit()
    assert cli_tokens.prune(db) == 1
    db.commit()
    assert db.get(CliLogin, fresh.id) is not None and db.get(CliLogin, row.id) is None


def test_local_token_create(client, owner, capsys):
    assert cli.main(["cli-token", "create", "--name", "local test"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["email"] == owner.email and out["token"].startswith("dpt_")
    assert client.get("/v1/auth/me", headers=bearer(out["token"])).json()["email"] == owner.email
    assert cli.main(["cli-token", "create", "--email", "nobody@example.com"]) == 2
