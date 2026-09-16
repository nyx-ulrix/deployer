import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.models import AuditLog, ProjectMember, User, UserIdentity
from app.services import oauth
from app.services.oauth import OAuthFlowError
from app.services.tokens import REFRESH_COOKIE

BASE = "http://localhost:8080"


class FakeProviders:
    def __init__(self):
        self.github_user = {"id": 42, "login": "octo", "name": "Octo Cat", "avatar_url": "https://avatars/octo.png"}
        self.github_emails = [
            {"email": "other@example.com", "primary": False, "verified": True},
            {"email": "Octo@Example.com", "primary": True, "verified": True},
        ]
        self.google_info = {
            "sub": "g-123",
            "email": "gina@example.com",
            "email_verified": True,
            "name": "Gina",
            "picture": "https://pics/gina.png",
        }
        self.token_requests: list[tuple[str, dict]] = []

    def post_form(self, url, data):
        self.token_requests.append((url, data))
        if data["code"] == "bad-code":
            raise OAuthFlowError("oauth_failed")
        return {"access_token": "provider-token", "token_type": "bearer"}

    def get_json(self, url, access_token):
        assert access_token == "provider-token"
        return {
            oauth.GITHUB_USER_URL: self.github_user,
            oauth.GITHUB_EMAILS_URL: self.github_emails,
            oauth.GOOGLE_USERINFO_URL: self.google_info,
        }[url]


@pytest.fixture
def providers(monkeypatch, set_setting):
    fake = FakeProviders()
    monkeypatch.setattr(oauth, "_http_post_form", fake.post_form)
    monkeypatch.setattr(oauth, "_http_get_json", fake.get_json)
    for p in ("google", "github"):
        set_setting(f"{p}_client_id", f"{p}-client")
        set_setting(f"{p}_client_secret", f"{p}-secret")
    return fake


def _start(client, provider="github", **params) -> str:
    resp = client.get(f"/v1/auth/oauth/{provider}/start", params=params, follow_redirects=False)
    assert resp.status_code == 302, resp.text
    query = parse_qs(urlsplit(resp.headers["location"]).query)
    return query["state"][0]


def _callback(client, provider="github", state="x", code="good-code", **extra):
    params = {"code": code, "state": state, **extra}
    return client.get(f"/v1/auth/oauth/{provider}/callback", params=params, follow_redirects=False)


def _error_of(resp) -> str | None:
    return parse_qs(urlsplit(resp.headers["location"]).query).get("error", [None])[0]


def test_start_redirects_with_state_and_pkce(client, owner, providers, fake_redis):
    resp = client.get("/v1/auth/oauth/github/start", params={"redirect": "/projects/1?tab=a"}, follow_redirects=False)
    assert resp.status_code == 302
    url = urlsplit(resp.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://github.com/login/oauth/authorize"
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q["client_id"] == "github-client"
    assert q["redirect_uri"] == f"{BASE}/v1/auth/oauth/github/callback"
    assert q["scope"] == "read:user user:email"
    assert q["code_challenge_method"] == "S256"
    key = oauth.STATE_PREFIX + q["state"]
    record = json.loads(fake_redis.get(key))
    assert 0 < fake_redis.ttl(key) <= 600
    assert record["intent"] == "login" and record["redirect"] == "/projects/1?tab=a"
    expected = base64.urlsafe_b64encode(hashlib.sha256(record["code_verifier"].encode()).digest()).rstrip(b"=")
    assert q["code_challenge"] == expected.decode()

    google = client.get("/v1/auth/oauth/google/start", follow_redirects=False)
    gurl = urlsplit(google.headers["location"])
    assert gurl.netloc == "accounts.google.com"
    assert parse_qs(gurl.query)["scope"] == ["openid email profile"]


def test_start_errors(client, owner):
    resp = client.get("/v1/auth/oauth/github/start", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{BASE}/login?error=provider_not_configured"
    assert client.get("/v1/auth/oauth/gitlab/start", follow_redirects=False).status_code == 404


def test_start_not_initialized(client, providers):
    resp = client.get("/v1/auth/oauth/github/start", follow_redirects=False)
    assert resp.headers["location"] == f"{BASE}/login?error=not_initialized"


def test_callback_invalid_or_reused_state(client, owner, providers):
    resp = _callback(client, state="unknown")
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{BASE}/login?error=oauth_state_invalid"

    state = _start(client, "github")
    # State bound to github can't be used on the google callback (and is consumed).
    assert _error_of(_callback(client, "google", state)) == "oauth_state_invalid"
    assert _error_of(_callback(client, "github", state)) == "oauth_state_invalid"


def test_callback_provider_error(client, owner, providers, db):
    state = _start(client)
    resp = _callback(client, state=state, code="", error="access_denied")
    assert resp.headers["location"] == f"{BASE}/login?error=oauth_failed"
    state = _start(client)
    assert _error_of(_callback(client, state=state, code="bad-code")) == "oauth_failed"
    assert db.query(AuditLog).filter_by(action="auth.oauth_failed").count() == 2


def test_login_existing_identity(client, make_user, owner, providers, db):
    user = make_user("octo-login@example.com", password=None)
    db.add(UserIdentity(user_id=user.id, provider="github", provider_user_id="42"))
    db.commit()

    state = _start(client, redirect="/projects?x=1")
    resp = _callback(client, state=state)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{BASE}/auth/complete?redirect=%2Fprojects%3Fx%3D1"
    assert REFRESH_COOKIE in resp.cookies

    token_url, data = providers.token_requests[-1]
    assert token_url == "https://github.com/login/oauth/access_token"
    assert data["client_secret"] == "github-secret"
    assert data["redirect_uri"] == f"{BASE}/v1/auth/oauth/github/callback"
    assert data["code_verifier"]

    refreshed = client.post("/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["user"]["id"] == user.id
    db.expire_all()
    identity = db.query(UserIdentity).one()
    assert identity.provider_email == "octo@example.com"
    assert identity.provider_username == "octo"
    assert db.query(AuditLog).filter_by(action="auth.oauth_login", user_id=user.id).count() == 1


def test_login_email_matches_existing_account(client, make_user, owner, providers, db):
    make_user("octo@example.com")
    state = _start(client)
    resp = _callback(client, state=state)
    assert resp.headers["location"] == f"{BASE}/login?error=account_exists_link_required"
    assert db.query(UserIdentity).count() == 0


def test_signup_disabled(client, owner, providers, db):
    state = _start(client)
    assert _error_of(_callback(client, state=state)) == "signup_disabled"
    assert db.query(User).count() == 1


def test_signup_allowed_creates_passwordless_user(client, owner, providers, set_setting, db):
    set_setting("allow_signup", True)
    state = _start(client)
    resp = _callback(client, state=state)
    assert resp.headers["location"] == f"{BASE}/auth/complete?redirect=%2F"
    user = db.query(User).filter_by(email="octo@example.com").one()
    assert user.password_hash is None
    assert user.display_name == "Octo Cat"
    assert user.avatar_url == "https://avatars/octo.png"
    assert user.is_instance_owner is False
    assert [(i.provider, i.provider_user_id, i.provider_username) for i in user.identities] == [
        ("github", "42", "octo")
    ]
    me = client.post("/v1/auth/refresh").json()["user"]
    assert me["has_password"] is False and len(me["identities"]) == 1


def test_signup_with_invite(client, owner, providers, make_project, db):
    from app.services import invites

    project = make_project(owner)
    _, locked = invites.create_invite(db, project=project, inviter=owner, role="viewer", email="someone@example.com")
    _, open_token = invites.create_invite(db, project=project, inviter=owner, role="developer")
    db.commit()

    state = _start(client, invite_token=locked)
    assert _error_of(_callback(client, state=state)) == "invite_email_mismatch"

    state = _start(client, invite_token="not-a-token")
    assert _error_of(_callback(client, state=state)) == "signup_disabled"

    state = _start(client, invite_token=open_token, redirect=f"/projects/{project.id}")
    resp = _callback(client, state=state)
    assert "/auth/complete" in resp.headers["location"]
    user = db.query(User).filter_by(email="octo@example.com").one()
    member = db.query(ProjectMember).filter_by(project_id=project.id, user_id=user.id).one()
    assert member.role == "developer"


def test_github_requires_primary_verified_email(client, owner, providers, set_setting):
    set_setting("allow_signup", True)
    providers.github_emails = [
        {"email": "octo@example.com", "primary": True, "verified": False},
        {"email": "alt@example.com", "primary": False, "verified": True},
    ]
    state = _start(client)
    assert _error_of(_callback(client, state=state)) == "email_not_verified"


def test_google_login_and_verification(client, owner, providers, set_setting, db):
    set_setting("allow_signup", True)
    providers.google_info["email_verified"] = False
    state = _start(client, "google")
    assert _error_of(_callback(client, "google", state)) == "email_not_verified"

    providers.google_info["email_verified"] = True
    state = _start(client, "google")
    resp = _callback(client, "google", state)
    assert "/auth/complete" in resp.headers["location"]
    user = db.query(User).filter_by(email="gina@example.com").one()
    assert user.identities[0].provider_user_id == "g-123"
    assert providers.token_requests[-1][0] == "https://oauth2.googleapis.com/token"


def test_not_initialized_at_callback(client, providers, fake_redis):
    from app.crypto import sha256_hex

    fake_redis.set(
        oauth.STATE_PREFIX + "s1",
        json.dumps(
            {
                "provider": "github",
                "intent": "login",
                "redirect": "/",
                "code_verifier": "v",
                "browser_hash": sha256_hex("nonce"),
            }
        ),
    )
    client.cookies.set(oauth.BROWSER_COOKIE, "nonce", path=oauth.BROWSER_COOKIE_PATH)
    assert _error_of(_callback(client, state="s1")) == "not_initialized"


def test_callback_requires_same_browser(client, make_user, owner, providers, db):
    """A callback URL started in another browser (login CSRF / forced linking) is rejected."""
    user = make_user("octo-login@example.com", password=None)
    db.add(UserIdentity(user_id=user.id, provider="github", provider_user_id="42"))
    db.commit()

    start = client.get("/v1/auth/oauth/github/start", follow_redirects=False)
    assert oauth.BROWSER_COOKIE in start.cookies
    set_cookie = [h for h in start.headers.get_list("set-cookie") if h.startswith(oauth.BROWSER_COOKIE)][0]
    assert "HttpOnly" in set_cookie and "Path=/v1/auth/oauth" in set_cookie
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]

    client.cookies.clear()  # the victim's browser has no (or a different) nonce
    resp = _callback(client, state=state)
    assert _error_of(resp) == "oauth_state_invalid"
    assert REFRESH_COOKIE not in resp.cookies

    state = _start(client)
    client.cookies.set(oauth.BROWSER_COOKIE, "someone-elses-nonce", path=oauth.BROWSER_COOKIE_PATH)
    assert _error_of(_callback(client, state=state)) == "oauth_state_invalid"


def _link_state(client, headers, provider="github", **body) -> str:
    resp = client.post(f"/v1/auth/oauth/{provider}/link", json=body or None, headers=headers)
    assert resp.status_code == 200, resp.text
    return parse_qs(urlsplit(resp.json()["authorize_url"]).query)["state"][0]


def test_link_flow(client, owner, owner_headers, providers, make_user, db):
    state = _link_state(client, owner_headers)
    resp = _callback(client, state=state)
    assert resp.headers["location"] == f"{BASE}/settings/account?linked=github"
    assert REFRESH_COOKIE not in resp.cookies
    identity = db.query(UserIdentity).one()
    assert identity.user_id == owner.id

    # Linking the same identity again is a no-op success.
    state = _link_state(client, owner_headers, redirect="/settings/account?tab=1")
    resp = _callback(client, state=state)
    assert resp.headers["location"] == f"{BASE}/settings/account?tab=1&linked=github"
    assert db.query(UserIdentity).count() == 1

    # Another user can't take it.
    other = make_user("other-linker@example.com")
    from app.services.tokens import create_access_token

    state = _link_state(client, {"Authorization": f"Bearer {create_access_token(other)}"}, redirect="/me")
    resp = _callback(client, state=state)
    assert resp.headers["location"] == f"{BASE}/me?error=identity_in_use"
    assert db.query(AuditLog).filter_by(action="auth.identity_link").count() == 1


def test_link_requires_auth_and_configuration(client, owner, owner_headers):
    assert client.post("/v1/auth/oauth/github/link").status_code == 401
    resp = client.post("/v1/auth/oauth/github/link", headers=owner_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "provider_not_configured"


def test_link_sanitizes_redirect(client, owner_headers, providers, fake_redis):
    state = _link_state(client, owner_headers, redirect="https://evil.example.com")
    assert json.loads(fake_redis.get(oauth.STATE_PREFIX + state))["redirect"] == "/settings/account"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "/"),
        ("", "/"),
        ("/projects", "/projects"),
        ("/a?b=c#frag", "/a?b=c"),
        ("//evil.com", "/"),
        ("/\\evil.com", "/"),
        ("https://evil.com", "/"),
        ("javascript:alert(1)", "/"),
        ("projects", "/"),
        ("/ok\nbad", "/"),
    ],
)
def test_sanitize_redirect(value, expected):
    assert oauth.sanitize_redirect(value) == expected
