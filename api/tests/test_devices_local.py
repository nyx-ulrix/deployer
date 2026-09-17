"""Device side: primary URL validation, the device-local API, RPC method guards and the CLI."""

import json

import httpx
import pytest

from app.errors import ApiError
from app.routers import device_local
from app.services import device_executor, device_host


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://deployer.example.com/", "https://deployer.example.com"),
        ("https://deployer.example.com:8443", "https://deployer.example.com:8443"),
        ("http://localhost:8080", "http://localhost:8080"),
        ("http://192.168.1.20:8080", "http://192.168.1.20:8080"),
        ("http://10.0.0.5", "http://10.0.0.5"),
        ("http://100.101.102.103:8080", "http://100.101.102.103:8080"),
        ("http://my-pc.tail1234.ts.net", "http://my-pc.tail1234.ts.net"),
    ],
)
def test_primary_url_allowed(url, expected):
    assert device_host.validate_primary_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://deployer.example.com",
        "http://8.8.8.8",
        "ftp://localhost",
        "https://user:pw@example.com",
        "https://example.com/some/path",
        "https://example.com/?x=1",
        "javascript:alert(1)",
        "http://host.docker.internal:8091",
        "",
    ],
)
def test_primary_url_rejected(url, monkeypatch):
    monkeypatch.delenv("DEPLOYER_ALLOW_INSECURE_PRIMARY", raising=False)
    with pytest.raises(ApiError) as exc:
        device_host.validate_primary_url(url)
    assert exc.value.code == "invalid_primary_url"


def test_insecure_flag_allows_docker_host(monkeypatch):
    monkeypatch.setenv("DEPLOYER_ALLOW_INSECURE_PRIMARY", "1")
    assert device_host.validate_primary_url("http://host.docker.internal:8091") == "http://host.docker.internal:8091"
    with pytest.raises(ApiError):
        device_host.validate_primary_url("http://example.com")


class FakePrimary:
    def __init__(self):
        self.poll_result = {"status": "pending", "interval": 5}
        self.requests = []

    def __call__(self, primary_url, method, path, body=None):
        self.requests.append((primary_url, method, path, body))
        req = httpx.Request(method, primary_url + path)
        if path == "/v1/devices/enrollments":
            return httpx.Response(
                200,
                request=req,
                json={
                    "enrollment_id": "e1",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": f"{primary_url}/devices/approve?code=ABCD-EFGH",
                    "poll_secret": "secret-1",
                    "expires_in": 900,
                },
            )
        return httpx.Response(200, request=req, json=self.poll_result)


@pytest.fixture
def fake_primary(monkeypatch):
    fake = FakePrimary()
    monkeypatch.setattr(device_local, "primary_request", fake)
    monkeypatch.setattr(device_local, "_ensure_poller", lambda: None)
    return fake


def test_enrollment_on_uninitialized_device(client, db, fake_primary, fake_redis):
    status = client.get("/v1/device/status").json()
    assert status["mode"] == "standalone" and status["connected"] is False and status["hosted_sources"] == []
    assert client.get("/v1/setup/status").json()["device_mode"] == "standalone"
    assert client.get("/v1/device/enroll/status").json() == {"status": "idle", "message": None}

    resp = client.post("/v1/device/enroll/start", json={"primary_url": "http://example.com", "device_name": "PC"})
    assert resp.status_code == 422
    resp = client.post("/v1/device/enroll/start", json={"primary_url": "http://192.168.1.2:8080/", "device_name": "PC"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "user_code": "ABCD-EFGH",
        "verification_url": "http://192.168.1.2:8080/devices/approve?code=ABCD-EFGH",
        "expires_in": 900,
    }
    assert fake_primary.requests[0][3]["name"] == "PC"
    assert "secret-1" not in fake_redis.get(device_local.STATE_KEY)

    assert client.get("/v1/device/enroll/status").json()["status"] == "pending"
    assert fake_primary.requests[-1][2] == "/v1/devices/enrollments/e1/poll"
    assert fake_primary.requests[-1][3] == {"poll_secret": "secret-1"}

    fake_primary.poll_result = {"status": "approved", "device_id": "d1", "device_token": "dpd_tok", "device_name": "PC"}
    fake_redis.delete(device_local.POLL_LOCK_KEY)
    assert client.get("/v1/device/enroll/status").json()["status"] == "approved"
    db.expire_all()
    link = device_host.load_link(db)
    assert link == {
        "primary_url": "http://192.168.1.2:8080",
        "device_id": "d1",
        "device_token": "dpd_tok",
        "device_name": "PC",
    }
    assert client.get("/v1/setup/status").json()["device_mode"] == "host"
    status = client.get("/v1/device/status").json()
    assert status["mode"] == "host" and status["device_id"] == "d1" and status["primary_url"] == link["primary_url"]
    resp = client.post("/v1/device/enroll/start", json={"primary_url": "http://192.168.1.2:8080", "device_name": "PC"})
    assert resp.status_code == 409


def test_enrollment_denied_and_cancel(client, fake_primary, fake_redis):
    client.post("/v1/device/enroll/start", json={"primary_url": "https://main.example.com", "device_name": "PC"})
    fake_primary.poll_result = {"status": "denied"}
    assert client.get("/v1/device/enroll/status").json()["status"] == "denied"
    assert client.post("/v1/device/enroll/cancel").json() == {"ok": True}
    assert client.get("/v1/device/enroll/status").json()["status"] == "idle"


def test_enrollment_requires_instance_owner_once_initialized(
    client, owner, owner_headers, make_user, auth_headers, fake_primary
):
    body = {"primary_url": "https://main.example.com", "device_name": "PC"}
    assert client.post("/v1/device/enroll/start", json=body).status_code == 401
    assert client.post("/v1/device/enroll/start", json=body, headers=auth_headers(make_user())).status_code == 403
    assert client.get("/v1/device/enroll/status").status_code == 401
    assert client.post("/v1/device/enroll/start", json=body, headers=owner_headers).status_code == 200


def test_redirects_to_other_hosts_refused(monkeypatch):
    def handler(request):
        if request.url.host == "main.example.com":
            return httpx.Response(302, headers={"location": "https://evil.example.net/v1/devices/enrollments"})
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(device_local.httpx, "Client", lambda **kw: real_client(transport=transport, **kw))
    with pytest.raises(ApiError) as exc:
        device_local.primary_request("https://main.example.com", "POST", "/v1/devices/enrollments", {})
    assert exc.value.code == "primary_redirect"


# --- RPC guards on the device ---------------------------------------------------------------------


def _set_creds(set_setting, creds):
    set_setting("device_hosted_credentials", json.dumps(creds))


def test_datasource_methods_only_touch_hosted_databases(set_setting):
    ctx = device_host.CallContext()
    _set_creds(set_setting, {"p_shop_abc123": {"kind": "sql", "username": "u_0123456789ab", "password": "x" * 32}})
    for params in (
        {"kind": "sql", "database_name": "deployer", "op": "rows.list", "args": {"table": "users"}},
        {"kind": "sql", "database_name": "p_other_000000", "op": "introspect", "args": {}},
        {"kind": "nosql", "database_name": "p_shop_abc123", "op": "introspect", "args": {}},
        {"kind": "sql", "database_name": "../etc", "op": "introspect", "args": {}},
    ):
        with pytest.raises(ApiError) as exc:
            device_host.dispatch("datasource.call", params, ctx)
        assert exc.value.code in ("not_hosted", "validation_error")
    with pytest.raises(ApiError):
        device_host.dispatch("datasource.drop", {"kind": "sql", "database_name": "deployer"}, ctx)
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("datasource.provision", {"kind": "sql", "database_name": "mysql"}, ctx)
    assert exc.value.code == "validation_error"
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("no.such.method", {}, ctx)
    assert exc.value.code == "unknown_method"
    source = device_host.local_source("p_shop_abc123", "sql", "main-sql")
    assert source.name == "main-sql" and source.device_id is None
    assert device_host.local_source("p_shop_abc123", "sql").config_encrypted == source.config_encrypted


def test_executor_calls_guarded(set_setting):
    ctx = device_host.CallContext()
    _set_creds(set_setting, {"p_shop_abc123": {"kind": "sql", "username": "u", "password": "p"}})
    with pytest.raises(ApiError) as exc:
        device_host.dispatch(
            "jobs.run",
            {
                "job_id": "j",
                "type": "executor.snapshot",
                "params": {"kind": "sql", "engine": "mariadb", "database_name": "deployer", "artifact_ref": "x/y.bin"},
            },
            ctx,
        )
    assert exc.value.code in ("not_hosted", "validation_error")
    with pytest.raises(ApiError) as exc:
        device_executor.run_executor_call(
            "snapshot",
            {"kind": "sql", "engine": "mariadb", "database_name": "p_shop_abc123", "artifact_ref": "../../etc/passwd"},
            "j",
            ctx,
        )
    assert exc.value.code == "invalid_local_ref"
    with pytest.raises(ApiError) as exc:
        device_executor.run_executor_call("ensure_database", {"kind": "sql", "database_name": "p_x"}, "j", ctx)
    assert exc.value.code == "unsupported_job"
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("jobs.run", {"job_id": "j", "type": "backup.anything", "params": {}}, ctx)
    assert exc.value.code == "unsupported_job"


def test_local_ref_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVICE_STORE_DIR", str(tmp_path))
    assert device_host.resolve_local_ref("src/snapshots/a.bin") == (tmp_path / "src/snapshots/a.bin").resolve()
    for bad in ("../x", "/etc/passwd", "a/../../x", "a//b", "", None, "a\\b"):
        with pytest.raises(ApiError):
            device_host.resolve_local_ref(bad)


def test_detach_rpc_and_cli(db, set_setting, capsys):
    from app import cli

    link = {"primary_url": "https://main.example.com", "device_id": "d1", "device_token": "dpd_x", "device_name": "PC"}
    set_setting("device_link", json.dumps(link))
    _set_creds(set_setting, {"p_shop_abc123": {"kind": "sql", "username": "u", "password": "p"}})
    detached = []
    ctx = device_host.CallContext(detach=lambda: detached.append(True))
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("device.detach", {}, ctx)
    assert exc.value.code == "databases_remain" and not detached

    assert cli.main(["device", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "host"
    assert cli.main(["device", "detach"]) == 2
    db.expire_all()
    assert device_host.load_link(db) is not None
    assert cli.main(["device", "detach", "--force"]) == 0
    db.expire_all()
    assert device_host.load_link(db) is None
    assert device_host.load_credentials(db)  # hosted databases are kept

    set_setting("device_link", json.dumps(link))
    _set_creds(set_setting, {})
    assert device_host.dispatch("device.detach", {}, ctx) == {}
    db.expire_all()
    assert device_host.load_link(db) is None and detached == [True]
