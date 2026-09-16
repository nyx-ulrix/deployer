import jwt

from app.config import get_settings
from app.crypto import sha256_hex
from app.models import AuditLog, RefreshToken, User, UserIdentity
from app.services.tokens import REFRESH_COOKIE
from tests.conftest import DEFAULT_PASSWORD


def _refresh(client, token: str | None = None):
    # Send an explicit cookie header so tests can replay old tokens.
    cookies = {REFRESH_COOKIE: token} if token is not None else None
    if cookies is not None:
        client.cookies.clear()
    return client.post("/v1/auth/refresh", cookies=cookies)


def test_providers(client, owner, set_setting):
    assert client.get("/v1/auth/providers").json() == {"google": False, "github": False, "allow_signup": False}
    set_setting("github_client_id", "abc")
    set_setting("github_client_secret", "shh")
    set_setting("allow_signup", True)
    assert client.get("/v1/auth/providers").json() == {"google": False, "github": True, "allow_signup": True}


def test_login_success_and_access_token_claims(client, owner, db):
    resp = client.post("/v1/auth/login", json={"email": "OWNER@example.com ", "password": DEFAULT_PASSWORD})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    claims = jwt.decode(body["access_token"], get_settings().jwt_secret, algorithms=["HS256"], audience="deployer")
    assert claims["sub"] == owner.id and claims["typ"] == "access"
    assert body["user"]["id"] == owner.id
    raw = resp.cookies[REFRESH_COOKIE]
    row = db.query(RefreshToken).one()
    assert row.token_hash == sha256_hex(raw)
    assert row.user_id == owner.id
    assert db.query(AuditLog).filter_by(action="auth.login").count() == 1


def test_login_invalid_credentials(client, owner, make_user, db):
    resp = client.post("/v1/auth/login", json={"email": "owner@example.com", "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"
    resp = client.post("/v1/auth/login", json={"email": "nobody@example.com", "password": DEFAULT_PASSWORD})
    assert resp.json()["error"]["code"] == "invalid_credentials"
    oauth_only = make_user("oauth@example.com", password=None)
    resp = client.post("/v1/auth/login", json={"email": oauth_only.email, "password": DEFAULT_PASSWORD})
    assert resp.status_code == 401
    disabled = make_user("disabled@example.com", active=False)
    resp = client.post("/v1/auth/login", json={"email": disabled.email, "password": DEFAULT_PASSWORD})
    assert resp.status_code == 401
    assert db.query(AuditLog).filter_by(action="auth.login_failed").count() == 4


def test_login_rate_limited(client, owner):
    for _ in range(10):
        resp = client.post("/v1/auth/login", json={"email": "owner@example.com", "password": "wrong-password"})
        assert resp.status_code == 401
    resp = client.post("/v1/auth/login", json={"email": "owner@example.com", "password": DEFAULT_PASSWORD})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    # Other emails from the same IP are unaffected.
    resp = client.post("/v1/auth/login", json={"email": "someone@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_refresh_rotates_and_detects_reuse(client, owner, login, db):
    login("owner@example.com")
    first = client.cookies.get(REFRESH_COOKIE)

    resp = _refresh(client, first)
    assert resp.status_code == 200, resp.text
    second = resp.cookies[REFRESH_COOKIE]
    assert second != first
    assert resp.json()["user"]["id"] == owner.id

    resp = _refresh(client, second)
    assert resp.status_code == 200
    third = resp.cookies[REFRESH_COOKIE]

    # Right after a rotation (e.g. two tabs refreshing at once) the old token still gets a sibling.
    resp = _refresh(client, second)
    assert resp.status_code == 200
    assert resp.cookies[REFRESH_COOKIE] not in (first, second, third)

    # Past the grace window, replaying a rotated token revokes the whole family.
    from datetime import timedelta

    from app.crypto import sha256_hex

    db.expire_all()
    stale = db.query(RefreshToken).filter_by(token_hash=sha256_hex(first)).one()
    stale.revoked_at = stale.revoked_at - timedelta(seconds=120)
    db.commit()
    resp = _refresh(client, first)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert REFRESH_COOKIE in resp.headers.get("set-cookie", "")
    resp = _refresh(client, third)
    assert resp.status_code == 401
    db.expire_all()
    assert all(t.revoked_at is not None for t in db.query(RefreshToken).all())


def test_refresh_without_cookie_or_unknown(client, owner):
    assert client.post("/v1/auth/refresh").status_code == 401
    assert _refresh(client, "garbage").status_code == 401


def test_refresh_expired(client, owner, login, db):
    from datetime import timedelta

    from app.models import utcnow

    login("owner@example.com")
    raw = client.cookies.get(REFRESH_COOKIE)
    row = db.query(RefreshToken).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _refresh(client, raw).status_code == 401


def test_logout_revokes(client, owner, login, db):
    login("owner@example.com")
    raw = client.cookies.get(REFRESH_COOKIE)
    resp = client.post("/v1/auth/logout", cookies={REFRESH_COOKIE: raw})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert 'deployer_rt=""' in resp.headers["set-cookie"] or "Max-Age=0" in resp.headers["set-cookie"]
    assert _refresh(client, raw).status_code == 401
    assert db.query(AuditLog).filter_by(action="auth.logout").count() == 1
    # Logout without a cookie is still fine.
    client.cookies.clear()
    assert client.post("/v1/auth/logout").status_code == 200


def test_me_requires_bearer(client, owner, auth_headers):
    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    resp = client.get("/v1/auth/me", headers=auth_headers(owner))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "id",
        "email",
        "display_name",
        "avatar_url",
        "is_instance_owner",
        "has_password",
        "created_at",
        "identities",
    }


def test_patch_me(client, owner, auth_headers):
    resp = client.patch("/v1/auth/me", json={"display_name": "  New Name "}, headers=auth_headers(owner))
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "New Name"
    resp = client.patch("/v1/auth/me", json={}, headers=auth_headers(owner))
    assert resp.json()["display_name"] == "New Name"
    resp = client.patch("/v1/auth/me", json={"display_name": ""}, headers=auth_headers(owner))
    assert resp.json()["display_name"] is None


def test_signup_disabled_by_default(client, owner):
    resp = client.post("/v1/auth/signup", json={"email": "new@example.com", "password": DEFAULT_PASSWORD})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "signup_disabled"


def test_signup_not_initialized(client):
    resp = client.post("/v1/auth/signup", json={"email": "new@example.com", "password": DEFAULT_PASSWORD})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_initialized"


def test_signup_when_allowed(client, owner, set_setting, db):
    set_setting("allow_signup", True)
    resp = client.post(
        "/v1/auth/signup", json={"email": "New@Example.com", "password": DEFAULT_PASSWORD, "display_name": "Newbie"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["email"] == "new@example.com"
    assert resp.json()["user"]["is_instance_owner"] is False
    assert REFRESH_COOKIE in resp.cookies
    dup = client.post("/v1/auth/signup", json={"email": "new@example.com", "password": DEFAULT_PASSWORD})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "email_taken"
    short = client.post("/v1/auth/signup", json={"email": "x@example.com", "password": "123456789"})
    assert short.status_code == 422


def test_signup_with_invite(client, owner, make_project, db):
    from app.services import invites

    project = make_project(owner)
    invite, token = invites.create_invite(db, project=project, inviter=owner, role="developer", email="inv@example.com")
    db.commit()

    wrong = client.post(
        "/v1/auth/signup", json={"email": "other@example.com", "password": DEFAULT_PASSWORD, "invite_token": token}
    )
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "invite_email_mismatch"

    bad = client.post(
        "/v1/auth/signup", json={"email": "inv@example.com", "password": DEFAULT_PASSWORD, "invite_token": "nope"}
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invite_invalid"

    resp = client.post(
        "/v1/auth/signup", json={"email": "inv@example.com", "password": DEFAULT_PASSWORD, "invite_token": token}
    )
    assert resp.status_code == 200, resp.text
    user_id = resp.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    projects = client.get("/v1/projects", headers=headers).json()
    assert [(p["id"], p["my_role"]) for p in projects] == [(project.id, "developer")]
    # Accepting again afterwards is idempotent for the same user.
    again = client.post(f"/v1/invites/{token}/accept", headers=headers)
    assert again.status_code == 200
    assert again.json() == {"project_id": project.id}
    db.expire_all()
    assert db.get(User, user_id) is not None


def test_change_password(client, owner, login, db):
    login("owner@example.com")
    access = login("owner@example.com")["access_token"]  # second session (family)
    current_cookie = client.cookies.get(REFRESH_COOKIE)
    headers = {"Authorization": f"Bearer {access}"}

    resp = client.post("/v1/auth/password", json={"new_password": "another-password-1"}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_current_password"
    resp = client.post(
        "/v1/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
        headers=headers,
    )
    assert resp.status_code == 422
    resp = client.post(
        "/v1/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "another-password-1"},
        headers=headers,
        cookies={REFRESH_COOKIE: current_cookie},
    )
    assert resp.status_code == 200
    db.expire_all()
    tokens = db.query(RefreshToken).all()
    assert sum(1 for t in tokens if t.revoked_at is None) == 1  # only the current session survives
    assert (
        client.post("/v1/auth/login", json={"email": "owner@example.com", "password": DEFAULT_PASSWORD}).status_code
        == 401
    )
    login("owner@example.com", "another-password-1")
    assert db.query(AuditLog).filter_by(action="auth.password_change").count() == 1


def test_set_password_for_oauth_only_user(client, make_user, owner, auth_headers):
    user = make_user("oauth@example.com", password=None)
    resp = client.post("/v1/auth/password", json={"new_password": "brand-new-password"}, headers=auth_headers(user))
    assert resp.status_code == 200
    me = client.get("/v1/auth/me", headers=auth_headers(user)).json()
    assert me["has_password"] is True


def test_unlink_identity(client, make_user, owner, auth_headers, db):
    user = make_user("linked@example.com", password=None)
    gh = UserIdentity(user_id=user.id, provider="github", provider_user_id="1", provider_username="octo")
    db.add(gh)
    db.commit()
    headers = auth_headers(user)

    resp = client.delete(f"/v1/auth/identities/{gh.id}", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "last_login_method"

    google = UserIdentity(user_id=user.id, provider="google", provider_user_id="g-1")
    db.add(google)
    db.commit()
    resp = client.delete(f"/v1/auth/identities/{gh.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert [i["provider"] for i in resp.json()["identities"]] == ["google"]

    # Someone else's identity is not found.
    resp = client.delete(f"/v1/auth/identities/{google.id}", headers=auth_headers(owner))
    assert resp.status_code == 404
    assert db.query(AuditLog).filter_by(action="auth.identity_unlink").count() == 1
