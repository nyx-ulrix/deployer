"""Remote access endpoints (docs/REMOTE_ACCESS.md) with a fake Cloudflare API and a temp tunnel_state dir."""

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import AuditLog, Domain, InstanceSetting
from app.services import cloudflare as cf
from app.services import remote_access as ra
from tests.test_cloudflare_client import API_TOKEN, FakeCloudflare

BASE = "/v1/instance/remote-access"


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "tunnel_state_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "deployer_http_port", 0)
    monkeypatch.setattr(ra, "_last_write_error", None)
    return tmp_path


@pytest.fixture
def fake_cf(state_dir):
    fake = FakeCloudflare()
    cf.set_transport(fake.transport())
    yield fake
    cf.set_transport(None)


def desired(state_dir):
    return json.loads((state_dir / "desired.json").read_text())


def write_status(state_dir, **fields):
    status = {
        "mode": "off",
        "running": False,
        "pid": None,
        "started_at": None,
        "quick_url": None,
        "last_error": None,
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **fields,
    }
    (state_dir / "status.json").write_text(json.dumps(status))


def link(client, headers, account_id="acc1"):
    resp = client.post(
        f"{BASE}/cloudflare/link", json={"api_token": API_TOKEN, "account_id": account_id}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def add_host(client, headers, hostname="app.example.com", **extra):
    return client.post(
        f"{BASE}/cloudflare/hostnames", json={"zone_id": "zone1", "hostname": hostname, **extra}, headers=headers
    )


def assert_no_secrets(resp):
    assert API_TOKEN not in resp.text
    assert "connector-token-for-" not in resp.text


# --- access control ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "", None),
        ("post", "/cloudflare/verify", {"api_token": "x"}),
        ("post", "/cloudflare/link", {"api_token": "x", "account_id": "acc1"}),
        ("post", "/cloudflare/hostnames", {"zone_id": "zone1", "hostname": "a.example.com"}),
        ("delete", "/cloudflare/hostnames/abc", None),
        ("post", "/cloudflare/unlink", {"delete_dns": False, "delete_tunnel": False}),
        ("post", "/quick", {"enabled": True}),
        ("post", "/public-url", {"local": True}),
    ],
)
def test_non_owner_forbidden(client, make_user, auth_headers, fake_cf, method, path, body):
    user = make_user()
    kwargs = {"headers": auth_headers(user)}
    if body is not None:
        kwargs["json"] = body
    resp = getattr(client, method)(f"{BASE}{path}", **kwargs)
    assert resp.status_code == 403
    assert client.get(BASE).status_code == 401
    assert fake_cf.requests == []


# --- GET / verify --------------------------------------------------------------------------------


def test_get_default_off(client, owner_headers, state_dir):
    resp = client.get(BASE, headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "mode": "off",
        "public_url": "http://localhost:8080",
        "connector": {"running": False, "started_at": None, "last_error": None},
        "cloudflare": {
            "linked": False,
            "token_valid": None,
            "account": None,
            "tunnel": None,
            "domains": [],
            "zones": [],
        },
        "quick": {"url": None},
    }
    # GET re-syncs desired.json.
    assert desired(state_dir) == {"mode": "off"}


def test_verify_ok_and_missing_permissions(client, owner_headers, fake_cf):
    resp = client.post(f"{BASE}/cloudflare/verify", json={"api_token": API_TOKEN}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert resp.json()["zones"] == [{"id": "zone1", "name": "example.com", "account_id": "acc1", "status": "active"}]
    assert_no_secrets(resp)

    fake_cf.forbidden = [r"/cfd_tunnel"]
    body = client.post(f"{BASE}/cloudflare/verify", json={"api_token": API_TOKEN}, headers=owner_headers).json()
    assert body["ok"] is False
    assert body["missing_permissions"] == [cf.PERM_TUNNEL]


def test_verify_invalid_token(client, owner_headers, fake_cf):
    resp = client.post(f"{BASE}/cloudflare/verify", json={"api_token": "nope"}, headers=owner_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "cloudflare_auth_failed"
    assert "nope" not in resp.text


# --- link ----------------------------------------------------------------------------------------


def test_link_creates_tunnel_and_writes_desired(client, owner_headers, fake_cf, state_dir, db):
    body = link(client, owner_headers)
    assert body["mode"] == "cloudflare"
    assert body["cloudflare"]["linked"] is True
    assert body["cloudflare"]["account"] == {"id": "acc1", "name": "My Account"}
    tunnel = body["cloudflare"]["tunnel"]
    assert tunnel["name"].startswith("deployer-") and len(tunnel["name"]) == len("deployer-") + 8
    assert len(fake_cf.tunnels) == 1
    assert fake_cf.tunnels[tunnel["id"]]["config_src"] == "cloudflare"
    # Empty ingress with only the catch-all rule.
    assert fake_cf.tunnel_configs[tunnel["id"]] == {"ingress": [{"service": "http_status:404"}]}

    assert desired(state_dir) == {"mode": "cloudflare", "token": f"connector-token-for-{tunnel['id']}"}
    if os.name != "nt":
        assert (state_dir / "desired.json").stat().st_mode & 0o777 == 0o600
    assert not [p for p in state_dir.iterdir() if p.name.startswith(".desired-")]

    # Secrets are encrypted at rest; instance_id was generated and persisted.
    row = db.get(InstanceSetting, "cloudflare_api_token")
    assert row.is_secret and API_TOKEN not in row.value
    assert db.get(InstanceSetting, "cloudflare_tunnel_token").is_secret
    instance_id = json.loads(db.get(InstanceSetting, "instance_id").value)
    assert tunnel["name"] == f"deployer-{instance_id[:8]}"
    audit = db.query(AuditLog).filter_by(action="remote_access.cloudflare_link").one()
    assert API_TOKEN not in json.dumps(audit.details)


def test_link_reuses_existing_tunnel(client, owner_headers, fake_cf, state_dir):
    first = link(client, owner_headers)["cloudflare"]["tunnel"]
    second = link(client, owner_headers)["cloudflare"]["tunnel"]
    assert first["id"] == second["id"]
    assert len(fake_cf.calls("POST", r"/cfd_tunnel$")) == 1

    # Settings lost (e.g. unlink without deleting the tunnel): found again by name.
    client.post(f"{BASE}/cloudflare/unlink", json={"delete_dns": False, "delete_tunnel": False}, headers=owner_headers)
    third = link(client, owner_headers)["cloudflare"]["tunnel"]
    assert third["id"] == first["id"]
    assert len(fake_cf.tunnels) == 1


def test_link_errors(client, owner_headers, fake_cf):
    resp = client.post(
        f"{BASE}/cloudflare/link", json={"api_token": "bad", "account_id": "acc1"}, headers=owner_headers
    )
    assert resp.json()["error"]["code"] == "cloudflare_auth_failed"

    resp = client.post(
        f"{BASE}/cloudflare/link", json={"api_token": API_TOKEN, "account_id": "missing"}, headers=owner_headers
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "account_not_found")

    fake_cf.forbidden = [r"/cfd_tunnel"]
    resp = client.post(
        f"{BASE}/cloudflare/link", json={"api_token": API_TOKEN, "account_id": "acc1"}, headers=owner_headers
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "cloudflare_permission_missing"
    assert resp.json()["error"]["details"]["missing_permissions"] == [cf.PERM_TUNNEL]
    assert client.get(BASE, headers=owner_headers).json()["cloudflare"]["linked"] is False

    fake_cf.forbidden = []
    fake_cf.fail["PUT /configurations$"] = cf.httpx.Response(
        502, json={"success": False, "errors": [{"code": 1, "message": "upstream"}]}
    )
    resp = client.post(
        f"{BASE}/cloudflare/link", json={"api_token": API_TOKEN, "account_id": "acc1"}, headers=owner_headers
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (502, "cloudflare_api_error")


# --- hostnames -----------------------------------------------------------------------------------


def test_add_hostname_requires_link(client, owner_headers, fake_cf):
    resp = add_host(client, owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "not_linked")


def test_add_hostname_new(client, owner_headers, fake_cf, db):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    resp = add_host(client, owner_headers, "App.Example.com.")
    assert resp.status_code == 200, resp.text
    domain = resp.json()
    assert domain["hostname"] == "app.example.com"
    assert domain["url"] == "https://app.example.com"
    assert domain["status"] == "active" and domain["zone_name"] == "example.com"
    assert domain["target_type"] == "dashboard" and domain["project_id"] is None

    record = fake_cf.records[db.get(Domain, domain["id"]).dns_record_id]
    assert record["type"] == "CNAME" and record["proxied"] is True
    assert record["content"] == f"{tunnel_id}.cfargotunnel.com"

    add_host(client, owner_headers, "example.com")  # apex
    assert fake_cf.tunnel_configs[tunnel_id] == {
        "ingress": [
            {"hostname": "app.example.com", "service": "http://caddy:8081", "originRequest": {}},
            {"hostname": "example.com", "service": "http://caddy:8081", "originRequest": {}},
            {"service": "http_status:404"},
        ]
    }

    listed = client.get(BASE, headers=owner_headers).json()["cloudflare"]["domains"]
    assert [d["hostname"] for d in listed] == ["app.example.com", "example.com"]

    dup = add_host(client, owner_headers, "app.example.com")
    assert (dup.status_code, dup.json()["error"]["code"]) == (409, "domain_exists")


def test_add_hostname_validation(client, owner_headers, fake_cf):
    link(client, owner_headers)
    resp = add_host(client, owner_headers, "app.other.org")
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "hostname_not_in_zone")
    resp = add_host(client, owner_headers, "notexample.com")
    assert resp.json()["error"]["code"] == "hostname_not_in_zone"
    for bad in ("https://app.example.com", "-bad.example.com", "a..example.com", "*.example.com", "localhost"):
        resp = add_host(client, owner_headers, bad)
        assert resp.status_code == 422, bad
    resp = client.post(
        f"{BASE}/cloudflare/hostnames", json={"zone_id": "nozone", "hostname": "a.example.com"}, headers=owner_headers
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "zone_not_found")
    fake_cf.zones.append({"id": "zone2", "name": "foreign.com", "status": "active", "account": {"id": "acc9"}})
    resp = client.post(
        f"{BASE}/cloudflare/hostnames", json={"zone_id": "zone2", "hostname": "a.foreign.com"}, headers=owner_headers
    )
    assert resp.json()["error"]["code"] == "zone_not_found"
    assert fake_cf.calls("POST", r"/dns_records$") == []


def test_idn_hostname(client, owner_headers, fake_cf):
    fake_cf.zones.append(
        {"id": "zone3", "name": "xn--bcher-kva.example", "status": "active", "account": {"id": "acc1"}}
    )
    link(client, owner_headers)
    resp = client.post(
        f"{BASE}/cloudflare/hostnames",
        json={"zone_id": "zone3", "hostname": "App.Bücher.example"},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["hostname"] == "app.xn--bcher-kva.example"


def test_add_hostname_existing_record(client, owner_headers, fake_cf, db):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    old_id = fake_cf.add_record("app.example.com", "A", "192.0.2.10")
    resp = add_host(client, owner_headers)
    assert resp.status_code == 409
    error = resp.json()["error"]
    assert error["code"] == "dns_record_exists"
    assert error["details"]["records"] == [{"id": old_id, "type": "A", "content": "192.0.2.10"}]
    assert db.query(Domain).count() == 0
    assert fake_cf.tunnel_configs[tunnel_id]["ingress"] == [{"service": "http_status:404"}]

    resp = add_host(client, owner_headers, overwrite=True)
    assert resp.status_code == 200, resp.text
    assert old_id not in fake_cf.records
    records = [r for r in fake_cf.records.values() if r["name"] == "app.example.com"]
    assert len(records) == 1 and records[0]["content"] == f"{tunnel_id}.cfargotunnel.com"


def test_add_hostname_overwrite_cname_updates_in_place(client, owner_headers, fake_cf, db):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    rid = fake_cf.add_record("app.example.com", "CNAME", "somewhere.else.net")
    resp = add_host(client, owner_headers, overwrite=True)
    assert resp.status_code == 200
    assert db.get(Domain, resp.json()["id"]).dns_record_id == rid
    assert fake_cf.records[rid]["content"] == f"{tunnel_id}.cfargotunnel.com"
    assert len(fake_cf.calls("PUT", r"/dns_records/")) == 1


def test_add_hostname_reuses_our_own_record(client, owner_headers, fake_cf):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    rid = fake_cf.add_record("app.example.com", "CNAME", f"{tunnel_id}.cfargotunnel.com")
    resp = add_host(client, owner_headers)
    assert resp.status_code == 200
    assert fake_cf.calls("POST", r"/dns_records$") == []
    assert rid in fake_cf.records


def test_add_hostname_dns_failure_rolls_back_ingress(client, owner_headers, fake_cf, db):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    fake_cf.fail["POST /dns_records$"] = cf.httpx.Response(
        403, json={"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]}
    )
    resp = add_host(client, owner_headers)
    assert resp.json()["error"]["code"] == "cloudflare_permission_missing"
    assert resp.json()["error"]["details"]["missing_permissions"] == [cf.PERM_DNS]
    assert db.query(Domain).count() == 0
    assert fake_cf.tunnel_configs[tunnel_id]["ingress"] == [{"service": "http_status:404"}]


def test_remove_hostname(client, owner_headers, fake_cf, db):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    a = add_host(client, owner_headers, "a.example.com").json()
    add_host(client, owner_headers, "b.example.com")
    resp = client.delete(f"{BASE}/cloudflare/hostnames/{a['id']}", headers=owner_headers)
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert [r["name"] for r in fake_cf.records.values()] == ["b.example.com"]
    assert [r.get("hostname") for r in fake_cf.tunnel_configs[tunnel_id]["ingress"]] == ["b.example.com", None]
    assert client.delete(f"{BASE}/cloudflare/hostnames/{a['id']}", headers=owner_headers).status_code == 404


# --- unlink --------------------------------------------------------------------------------------


def test_unlink_keep_everything(client, owner_headers, fake_cf, state_dir, db):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    add_host(client, owner_headers)
    resp = client.post(
        f"{BASE}/cloudflare/unlink", json={"delete_dns": False, "delete_tunnel": False}, headers=owner_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "off"
    assert body["cloudflare"] == {
        "linked": False,
        "token_valid": None,
        "account": None,
        "tunnel": None,
        "domains": [],
        "zones": [],
    }
    assert len(fake_cf.records) == 1
    assert fake_cf.tunnels[tunnel_id]["deleted_at"] is None
    assert desired(state_dir) == {"mode": "off"}
    db.expire_all()
    assert db.query(Domain).count() == 0
    for key in ("cloudflare_api_token", "cloudflare_tunnel_token", "cloudflare_account_id", "cloudflare_tunnel_id"):
        assert db.get(InstanceSetting, key) is None
    again = client.post(f"{BASE}/cloudflare/unlink", json={}, headers=owner_headers)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "not_linked")


def test_unlink_delete_dns_and_tunnel(client, owner_headers, fake_cf, state_dir):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    add_host(client, owner_headers)
    fake_cf.add_record("other.example.com", "A")  # not ours; must survive
    fake_cf.connections[tunnel_id] = [{"id": "c1", "conns": [{"id": "x"}]}]
    resp = client.post(
        f"{BASE}/cloudflare/unlink", json={"delete_dns": True, "delete_tunnel": True}, headers=owner_headers
    )
    assert resp.status_code == 200, resp.text
    assert [r["name"] for r in fake_cf.records.values()] == ["other.example.com"]
    assert fake_cf.tunnels[tunnel_id]["deleted_at"] is not None
    assert desired(state_dir) == {"mode": "off"}


def test_unlink_failure_keeps_link(client, owner_headers, fake_cf, state_dir):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    fake_cf.fail[f"DELETE /cfd_tunnel/{tunnel_id}$"] = cf.httpx.Response(
        500, json={"success": False, "errors": [{"code": 1, "message": "oops"}]}
    )
    resp = client.post(
        f"{BASE}/cloudflare/unlink", json={"delete_dns": False, "delete_tunnel": True}, headers=owner_headers
    )
    assert resp.status_code == 502
    assert client.get(BASE, headers=owner_headers).json()["cloudflare"]["linked"] is True
    assert desired(state_dir)["mode"] == "cloudflare"


# --- quick tunnel ----------------------------------------------------------------------------------


def test_quick_mode(client, owner_headers, state_dir):
    resp = client.post(f"{BASE}/quick", json={"enabled": True}, headers=owner_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "quick" and body["quick"] == {"url": None}
    assert body["connector"]["running"] is False
    assert desired(state_dir) == {"mode": "quick"}

    write_status(
        state_dir,
        mode="quick",
        running=True,
        pid=42,
        started_at="2026-09-16T10:00:00Z",
        quick_url="https://funny-words-here.trycloudflare.com",
    )
    body = client.get(BASE, headers=owner_headers).json()
    assert body["connector"] == {"running": True, "started_at": "2026-09-16T10:00:00Z", "last_error": None}
    assert body["quick"] == {"url": "https://funny-words-here.trycloudflare.com"}

    resp = client.post(f"{BASE}/public-url", json={"quick": True}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["public_url"] == "https://funny-words-here.trycloudflare.com"

    # Stale status (sidecar gone) is not "running".
    old = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_status(state_dir, mode="quick", running=True, quick_url="https://x.trycloudflare.com", updated_at=old)
    body = client.get(BASE, headers=owner_headers).json()
    assert body["connector"]["running"] is False and "not running" in body["connector"]["last_error"]
    assert body["quick"]["url"] is None

    # Disabling reverts a quick public URL to localhost.
    body = client.post(f"{BASE}/quick", json={"enabled": False}, headers=owner_headers).json()
    assert body["mode"] == "off"
    assert body["public_url"] == "http://localhost:8080"
    assert desired(state_dir) == {"mode": "off"}


def test_quick_then_back_to_cloudflare(client, owner_headers, fake_cf, state_dir):
    link(client, owner_headers)
    client.post(f"{BASE}/quick", json={"enabled": True}, headers=owner_headers)
    assert desired(state_dir) == {"mode": "quick"}
    body = client.post(f"{BASE}/quick", json={"enabled": False}, headers=owner_headers).json()
    assert body["mode"] == "cloudflare"
    assert desired(state_dir)["mode"] == "cloudflare"


def test_public_url_quick_not_ready(client, owner_headers, state_dir):
    resp = client.post(f"{BASE}/public-url", json={"quick": True}, headers=owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "quick_tunnel_not_ready")


# --- public URL ----------------------------------------------------------------------------------


def test_public_url_switch_and_revert_on_remove(client, owner_headers, fake_cf, set_setting):
    set_setting("google_client_id", "gid")
    link(client, owner_headers)
    domain = add_host(client, owner_headers).json()

    resp = client.post(f"{BASE}/public-url", json={"domain_id": domain["id"]}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous_public_url"] == "http://localhost:8080"
    assert body["settings"]["public_url"] == "https://app.example.com"
    assert body["oauth_callbacks"] == {
        "google": "https://app.example.com/v1/auth/oauth/google/callback",
        "github": "https://app.example.com/v1/auth/oauth/github/callback",
    }
    assert body["settings"]["google"]["callback_url"] == body["oauth_callbacks"]["google"]
    assert_no_secrets(resp)

    # Removing the domain in use reverts to localhost (port from the request host here).
    resp = client.delete(
        f"{BASE}/cloudflare/hostnames/{domain['id']}", headers={**owner_headers, "Host": "localhost:8094"}
    )
    assert resp.status_code == 200
    assert client.get("/v1/instance/settings", headers=owner_headers).json()["public_url"] == "http://localhost:8094"


def test_public_url_revert_on_unlink_uses_env_port(client, owner_headers, fake_cf, monkeypatch):
    monkeypatch.setattr(get_settings(), "deployer_http_port", 9000)
    link(client, owner_headers)
    domain = add_host(client, owner_headers).json()
    client.post(f"{BASE}/public-url", json={"domain_id": domain["id"]}, headers=owner_headers)
    body = client.post(f"{BASE}/cloudflare/unlink", json={}, headers=owner_headers).json()
    assert body["public_url"] == "http://localhost:9000"


def test_public_url_local_and_validation(client, owner_headers, fake_cf, set_setting):
    set_setting("public_url", "https://old.example.net")
    resp = client.post(f"{BASE}/public-url", json={"local": True}, headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json()["previous_public_url"] == "https://old.example.net"
    assert resp.json()["settings"]["public_url"] == "http://localhost:8080"

    for body in ({}, {"local": True, "quick": True}):
        resp = client.post(f"{BASE}/public-url", json=body, headers=owner_headers)
        assert resp.status_code == 422
    resp = client.post(f"{BASE}/public-url", json={"domain_id": "nope"}, headers=owner_headers)
    assert resp.status_code == 404


def test_public_url_domain_requires_cloudflare_mode(client, owner_headers, fake_cf):
    link(client, owner_headers)
    domain = add_host(client, owner_headers).json()
    client.post(f"{BASE}/quick", json={"enabled": True}, headers=owner_headers)
    resp = client.post(f"{BASE}/public-url", json={"domain_id": domain["id"]}, headers=owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "tunnel_not_active")


# --- live status / secrets -------------------------------------------------------------------------


def test_get_live_tunnel_status_and_no_secrets(client, owner_headers, fake_cf, state_dir):
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    add_host(client, owner_headers)
    fake_cf.tunnels[tunnel_id]["status"] = "healthy"
    fake_cf.connections[tunnel_id] = [{"id": "c1", "conns": [{"id": "a"}, {"id": "b"}]}, {"id": "c2", "conns": [{}]}]
    write_status(state_dir, mode="cloudflare", running=True, pid=7, started_at="2026-09-16T10:00:00Z")

    resp = client.get(BASE, headers=owner_headers)
    body = resp.json()
    assert body["cloudflare"]["token_valid"] is True
    assert body["cloudflare"]["tunnel"]["status"] == "healthy"
    assert body["cloudflare"]["tunnel"]["connections"] == 3
    assert body["connector"]["running"] is True
    assert_no_secrets(resp)

    # Revoked token.
    fake_cf.token = "rotated"
    body = client.get(BASE, headers=owner_headers).json()
    assert body["cloudflare"]["token_valid"] is False

    # Status for a different mode than desired is not "running".
    write_status(state_dir, mode="quick", running=True)
    assert client.get(BASE, headers=owner_headers).json()["connector"]["running"] is False

    for resp in (
        client.get("/v1/instance/settings", headers=owner_headers),
        client.post(f"{BASE}/quick", json={"enabled": False}, headers=owner_headers),
    ):
        assert_no_secrets(resp)


def test_zones_of_linked_account_are_listed_and_cached(client, owner_headers, fake_cf, state_dir):
    zone = {"id": "zone1", "name": "example.com", "account_id": "acc1", "status": "active"}
    assert client.get(BASE, headers=owner_headers).json()["cloudflare"]["zones"] == []
    body = link(client, owner_headers)
    assert body["cloudflare"]["zones"] == [zone]  # available right after linking, without live calls
    zone_calls = len(fake_cf.calls("GET", r"^/client/v4/zones$"))
    body = client.get(BASE, headers=owner_headers).json()
    assert body["cloudflare"]["zones"] == [zone]
    assert len(fake_cf.calls("GET", r"^/client/v4/zones$")) == zone_calls  # served from the cache

    # Cloudflare unreachable: no cache -> [], status reads tolerate it.
    ra._remember_zones("acc1", None)
    fake_cf.unreachable = True
    body = client.get(BASE, headers=owner_headers).json()
    assert body["cloudflare"]["zones"] == [] and body["cloudflare"]["token_valid"] is None
    fake_cf.unreachable = False
    fake_cf.zones.append({"id": "zone2", "name": "other.com", "status": "pending", "account": {"id": "acc1"}})
    zones = client.get(BASE, headers=owner_headers).json()["cloudflare"]["zones"]
    assert [z["id"] for z in zones] == ["zone1", "zone2"]
    unlinked = client.post(f"{BASE}/cloudflare/unlink", json={}, headers=owner_headers).json()
    assert unlinked["cloudflare"]["zones"] == []


def test_desired_write_failure_is_reported(client, owner_headers, tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(get_settings(), "tunnel_state_dir", str(blocker / "sub"))
    monkeypatch.setattr(ra, "_last_write_error", None)
    body = client.post(f"{BASE}/quick", json={"enabled": True}, headers=owner_headers).json()
    assert body["mode"] == "quick"
    assert body["connector"]["last_error"].startswith("Could not write")
