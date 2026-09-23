from app.models import AuditLog, User
from tests.conftest import DEFAULT_PASSWORD

# Fake OAuth values built at runtime (the secret scan flags credential-shaped literals).
GH_ID = "Ov23" + "li" + "a1b2c3d4e5f6g7h8"
GH_SECRET = "0f" * 20
G_ID = "1234" + "-abc123.apps.googleusercontent.com"
G_SECRET = "GOCSPX" + "-" + "x" * 28


def test_status_uninitialized(client):
    resp = client.get("/v1/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["initialized"] is False
    assert body["public_url"] == "http://localhost:8080"
    assert body["providers"] == {"google": False, "github": False}
    assert body["allow_signup"] is False
    assert body["version"]


def test_create_owner_then_already_initialized(client, db):
    resp = client.post(
        "/v1/setup/owner",
        json={"email": "Boss@Example.com", "password": DEFAULT_PASSWORD, "display_name": "Boss"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["user"]["email"] == "boss@example.com"
    assert body["user"]["is_instance_owner"] is True
    assert body["user"]["has_password"] is True
    assert "deployer_rt" in resp.cookies

    set_cookie = resp.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Path=/v1/auth" in set_cookie
    assert "SameSite=lax" in set_cookie.replace("Lax", "lax")
    assert "Secure" not in set_cookie

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "boss@example.com"

    assert client.get("/v1/setup/status").json()["initialized"] is True
    again = client.post("/v1/setup/owner", json={"email": "other@example.com", "password": DEFAULT_PASSWORD})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_initialized"
    assert db.query(User).count() == 1
    assert db.query(AuditLog).filter_by(action="auth.signup").count() == 1


def test_create_owner_validates_password(client):
    resp = client.post("/v1/setup/owner", json={"email": "boss@example.com", "password": "short"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_create_owner_validates_email(client):
    resp = client.post("/v1/setup/owner", json={"email": "not-an-email", "password": DEFAULT_PASSWORD})
    assert resp.status_code == 422


def test_secure_cookie_when_public_url_https(client, set_setting):
    set_setting("public_url", "https://deployer.example.com")
    resp = client.post("/v1/setup/owner", json={"email": "boss@example.com", "password": DEFAULT_PASSWORD})
    assert resp.status_code == 200
    assert "Secure" in resp.headers["set-cookie"]


def test_health_never_fails(client, monkeypatch):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["services"] == {"mariadb": True, "mongodb": False, "redis": True}

    from app.redis_client import get_redis

    def boom():
        raise ConnectionError("down")

    monkeypatch.setattr(get_redis(), "ping", boom)
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["services"]["redis"] is False


# --- instance settings (instance owner only) ------------------------------------------------------


def test_instance_settings_requires_instance_owner(client, owner, make_user, auth_headers):
    other = make_user()
    assert client.get("/v1/instance/settings").status_code == 401
    assert client.get("/v1/instance/settings", headers=auth_headers(other)).status_code == 403
    assert client.put("/v1/instance/settings", json={}, headers=auth_headers(other)).status_code == 403
    assert client.get("/v1/instance/users", headers=auth_headers(other)).status_code == 403


def test_instance_settings_roundtrip(client, owner_headers, db):
    resp = client.get("/v1/instance/settings", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "public_url": "http://localhost:8080",
        "allow_signup": False,
        "google": {
            "client_id": None,
            "secret_set": False,
            "configured": False,
            "callback_url": "http://localhost:8080/v1/auth/oauth/google/callback",
        },
        "github": {
            "client_id": None,
            "secret_set": False,
            "configured": False,
            "callback_url": "http://localhost:8080/v1/auth/oauth/github/callback",
        },
    }

    resp = client.put(
        "/v1/instance/settings",
        json={
            "public_url": "https://deployer.example.com/",
            "allow_signup": True,
            "github_client_id": f"  {GH_ID}\n",
            "github_client_secret": GH_SECRET,
            "google_client_id": G_ID,
        },
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["public_url"] == "https://deployer.example.com"
    assert body["allow_signup"] is True
    assert body["github"] == {
        "client_id": GH_ID,
        "secret_set": True,
        "configured": True,
        "callback_url": "https://deployer.example.com/v1/auth/oauth/github/callback",
    }
    assert body["google"]["configured"] is False and body["google"]["secret_set"] is False
    assert GH_SECRET not in resp.text

    from app.models import InstanceSetting

    stored = db.get(InstanceSetting, "github_client_secret")
    assert stored.is_secret and GH_SECRET not in stored.value

    # Omitted fields are unchanged; empty strings clear.
    resp = client.put(
        "/v1/instance/settings", json={"github_client_secret": "", "allow_signup": False}, headers=owner_headers
    )
    body = resp.json()
    assert body["github"]["client_id"] == GH_ID
    assert body["github"]["secret_set"] is False and body["github"]["configured"] is False
    assert body["allow_signup"] is False
    assert body["public_url"] == "https://deployer.example.com"
    db.rollback()  # end the snapshot transaction (MariaDB REPEATABLE READ)
    assert db.query(AuditLog).filter_by(action="instance.settings_update").count() == 2


def test_instance_settings_rejects_bad_public_url(client, owner_headers):
    for bad in ["ftp://x.com", "https://x.com/path", "x.com", "https://", "https://x.com?a=1", "https://u:p@x.com"]:
        resp = client.put("/v1/instance/settings", json={"public_url": bad}, headers=owner_headers)
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["code"] == "validation_error"
    resp = client.put("/v1/instance/settings", json={"public_url": "http://192.168.1.5:8080"}, headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json()["public_url"] == "http://192.168.1.5:8080"


def test_instance_users(client, owner, owner_headers, make_user):
    make_user("second@example.com")
    resp = client.get("/v1/instance/users", headers=owner_headers)
    assert resp.status_code == 200
    assert [u["email"] for u in resp.json()] == ["owner@example.com", "second@example.com"]


# --- OAuth app validation (a whole "ID ... SECRET ..." block once got pasted into the client-ID field) ---


def test_instance_settings_rejects_pasted_oauth_blocks(client, owner_headers):
    cases = {
        "google_client_id": [f"ID {G_ID} SECRET {G_SECRET}", G_SECRET, "my-app", f"ID:{G_ID}"],
        "google_client_secret": [f"SECRET {G_SECRET}", G_ID, f"{G_SECRET}\n{G_ID}"],
        "github_client_id": [f"ID {GH_ID}", "gh id", "not-a-github-id"],
        "github_client_secret": [f"secret: {GH_SECRET}", GH_ID, "Client secret=" + GH_SECRET],
    }
    for field, values in cases.items():
        for bad in values:
            resp = client.put("/v1/instance/settings", json={field: bad}, headers=owner_headers)
            assert resp.status_code == 422, (field, bad)
            error = resp.json()["error"]
            assert error["code"] == "validation_error" and error["details"] == {"field": field}
    resp = client.put("/v1/instance/settings", json={"google_client_id": f"ID {G_ID}"}, headers=owner_headers)
    assert (
        "Paste only the Google Client ID, e.g. 1234-abc.apps.googleusercontent.com" in resp.json()["error"]["message"]
    )
    assert client.get("/v1/instance/settings", headers=owner_headers).json()["google"]["client_id"] is None

    ok = {"google_client_id": G_ID, "google_client_secret": G_SECRET, "github_client_id": "Iv1." + "a" * 16}
    resp = client.put("/v1/instance/settings", json=ok, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["google"]["configured"] is True
    legacy_id = "a1B2" * 5  # older GitHub apps: 20 alphanumerics
    assert (
        client.put("/v1/instance/settings", json={"github_client_id": legacy_id}, headers=owner_headers).status_code
        == 200
    )


def test_oauth_cli(db, owner, capsys, monkeypatch):
    import io
    import json

    from app import cli
    from app.services import instance_settings

    def run(*argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8-sig"))))
        code = cli.main(list(argv))
        return code, capsys.readouterr().out

    code, out = run("oauth", "status")
    status = json.loads(out)
    assert code == 0 and status["public_url"] == "http://localhost:8080"
    assert status["google"] == {
        "client_id": None,
        "has_secret": False,
        "configured": False,
        "callback_url": "http://localhost:8080/v1/auth/oauth/google/callback",
    }

    # Bad input: exit 2 with a single line saying what is wrong; nothing stored.
    code, out = run(
        "oauth", "set", "--provider", "google", stdin=json.dumps({"client_id": f"ID {G_ID} SECRET {G_SECRET}"})
    )
    assert code == 2 and "Paste only the Google Client ID" in out and out.count("\n") == 1
    assert run("oauth", "set", "--provider", "google", stdin="not json")[0] == 2
    code, out = run("oauth", "set", "--provider", "google", stdin=json.dumps({"client_id": G_ID}))
    assert code == 2 and "secret is required" in out

    code, out = run(
        "oauth", "set", "--provider", "google", stdin=json.dumps({"client_id": G_ID, "client_secret": G_SECRET})
    )
    assert code == 0 and G_SECRET not in out
    db.expire_all()
    app = instance_settings.oauth_app(db, "google")
    assert (app.client_id, app.client_secret) == (G_ID, G_SECRET)
    code, out = run("oauth", "status")
    assert G_SECRET not in out and json.loads(out)["google"]["has_secret"] is True

    # An empty secret keeps the stored one.
    new_id = "99-xyz.apps.googleusercontent.com"
    assert run("oauth", "set", "--provider", "google", stdin=json.dumps({"client_id": new_id}))[0] == 0
    db.expire_all()
    assert instance_settings.oauth_app(db, "google").client_secret == G_SECRET

    assert run("oauth", "clear", "--provider", "google")[0] == 0
    db.expire_all()
    assert not instance_settings.oauth_app(db, "google").client_id
    db.rollback()
    assert db.query(AuditLog).filter_by(action="instance.settings_update").count() == 3
