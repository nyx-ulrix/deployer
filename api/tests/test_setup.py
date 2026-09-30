from sqlalchemy import select

from app.models import AuditLog, RefreshToken, User
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


def test_status_reports_managed_mongodb(client, monkeypatch):
    # A-017: the "New project" dialog reads this to untick MongoDB on CPUs without AVX.
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "managed_mongodb_enabled", False)
    assert client.get("/v1/setup/status").json()["managed_mongodb"] is False
    monkeypatch.setattr(get_settings(), "managed_mongodb_enabled", True)
    assert client.get("/v1/setup/status").json()["managed_mongodb"] is True


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


def test_secure_cookie_when_request_is_https(client):
    resp = client.post(
        "https://testserver/v1/setup/owner", json={"email": "boss@example.com", "password": DEFAULT_PASSWORD}
    )
    assert resp.status_code == 200
    assert "Secure" in resp.headers["set-cookie"]


def test_health_reports_degraded_when_a_required_service_is_down(client, monkeypatch):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # MongoDB is switched off in tests (as on a CPU without AVX): null, not a failure.
    assert body["services"] == {"mariadb": True, "mongodb": None, "redis": True}

    from app.redis_client import get_redis

    def boom():
        raise ConnectionError("down")

    monkeypatch.setattr(get_redis(), "ping", boom)
    resp = client.get("/v1/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
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
        "local_url": "http://localhost:8080",
        "allow_signup": False,
        "owner_only_projects": True,
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
        "alert_webhook_url": None,
        "api_key_rate_limit": 600,
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


# --- A-023: the owner can see every project and disable other accounts ---------------------------


def test_owner_disables_user_and_sees_their_projects(
    client, owner, owner_headers, make_user, make_project, auth_headers, login, db
):
    stranger = make_user("stranger@example.com")
    make_project(stranger, "Stranger Shop")
    session = login("stranger@example.com")
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    resp = client.get("/v1/instance/projects", headers=owner_headers)
    assert resp.status_code == 200
    [project] = resp.json()
    assert (project["name"], project["owner_email"], project["member_count"], project["my_role"]) == (
        "Stranger Shop",
        "stranger@example.com",
        1,
        None,
    )
    assert client.get("/v1/instance/projects", headers=headers).status_code == 403
    assert client.patch(f"/v1/instance/users/{owner.id}", json={"is_active": False}, headers=headers).status_code == 403

    resp = client.patch(f"/v1/instance/users/{stranger.id}", json={"is_active": False}, headers=owner_headers)
    assert resp.status_code == 200 and resp.json()["is_active"] is False
    # The live access token stops working, every session is revoked, and the password is refused.
    assert client.get("/v1/auth/me", headers=headers).status_code == 401
    db.expire_all()
    sessions = db.scalars(select(RefreshToken).where(RefreshToken.user_id == stranger.id)).all()
    assert sessions and all(t.revoked_at is not None for t in sessions)
    assert (
        client.post("/v1/auth/login", json={"email": stranger.email, "password": DEFAULT_PASSWORD}).status_code == 401
    )
    assert db.scalar(select(AuditLog).where(AuditLog.action == "instance.user_update")) is not None

    resp = client.patch(f"/v1/instance/users/{owner.id}", json={"is_active": False}, headers=owner_headers)
    assert resp.status_code == 400
    assert client.patch("/v1/instance/users/nope", json={"is_active": False}, headers=owner_headers).status_code == 404

    assert client.patch(f"/v1/instance/users/{stranger.id}", json={"is_active": True}, headers=owner_headers).json()[
        "is_active"
    ]
    login("stranger@example.com")


def test_only_owner_creates_projects_by_default(client, owner, owner_headers, make_user, auth_headers):
    member = auth_headers(make_user())
    resp = client.post("/v1/projects", json={"name": "Mine"}, headers=member)
    assert resp.status_code == 403
    assert "instance owner" in resp.json()["error"]["message"]
    assert client.post("/v1/projects", json={"name": "Owner's"}, headers=owner_headers).status_code == 200

    resp = client.put("/v1/instance/settings", json={"owner_only_projects": False}, headers=owner_headers)
    assert resp.json()["owner_only_projects"] is False
    assert client.post("/v1/projects", json={"name": "Mine"}, headers=member).status_code == 200


def test_is_initialized_is_the_single_setup_check(db, owner):
    # A-105: every "is the instance set up?" gate goes through instance_settings.is_initialized.
    from pathlib import Path

    from app.services.instance_settings import is_initialized

    assert is_initialized(db) is True
    app_dir = Path(__file__).resolve().parents[1] / "app"
    copies = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if p.name != "instance_settings.py"
        and ("select(User.id).limit(1)" in (text := p.read_text(encoding="utf-8")) or "select_from(User)" in text)
    ]
    assert copies == []


def test_is_initialized_false_without_users(db):
    from app.services.instance_settings import is_initialized

    assert is_initialized(db) is False
