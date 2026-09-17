"""Cloudflare API v4 client against an in-memory fake (httpx.MockTransport). No network access.

`FakeCloudflare` is also used by tests/test_remote_access.py.
"""

import json
import re
import uuid

import httpx
import pytest

from app.services import cloudflare as cf

API_TOKEN = "cf-test-token-SECRET-1234567890"


def _ok(result, result_info=None, status=200):
    body = {"success": True, "errors": [], "messages": [], "result": result}
    if result_info is not None:
        body["result_info"] = result_info
    return httpx.Response(status, json=body)


def _err(status, code, message):
    return httpx.Response(
        status, json={"success": False, "errors": [{"code": code, "message": message}], "messages": [], "result": None}
    )


class FakeCloudflare:
    """Minimal stateful stand-in for the parts of the Cloudflare API that Deployer uses."""

    def __init__(self, token: str = API_TOKEN):
        self.token = token
        self.token_status = "active"
        self.accounts = [{"id": "acc1", "name": "My Account"}]
        self.zones = [{"id": "zone1", "name": "example.com", "status": "active", "account": {"id": "acc1"}}]
        self.tunnels: dict[str, dict] = {}
        self.tunnel_configs: dict[str, dict] = {}
        self.records: dict[str, dict] = {}
        self.connections: dict[str, list] = {}
        # Paths (regex) that answer 403, e.g. r"/cfd_tunnel".
        self.forbidden: list[str] = []
        self.fail: dict[str, httpx.Response] = {}  # "METHOD path-regex" -> response
        self.requests: list[httpx.Request] = []
        self.per_page_override: int | None = None
        self.unreachable = False

    # --- helpers for tests ---
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def add_record(self, name, type_="A", content="192.0.2.1", zone_id="zone1"):
        rid = uuid.uuid4().hex
        self.records[rid] = {"id": rid, "zone_id": zone_id, "name": name, "type": type_, "content": content}
        return rid

    def calls(self, method=None, pattern=None):
        return [
            r
            for r in self.requests
            if (method is None or r.method == method) and (pattern is None or re.search(pattern, r.url.path))
        ]

    def _page(self, items, request):
        page = int(request.url.params.get("page", 1))
        per_page = int(request.url.params.get("per_page", 20))
        start = (page - 1) * per_page
        total_pages = max(1, -(-len(items) // per_page))
        info = {"page": page, "per_page": per_page, "count": len(items[start : start + per_page])}
        info.update({"total_count": len(items), "total_pages": total_pages})
        return _ok(items[start : start + per_page], info)

    # --- router ---
    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.unreachable:
            raise httpx.ConnectError("boom", request=request)
        path = request.url.path.removeprefix("/client/v4")
        method = request.method
        for key, response in self.fail.items():
            m, _, pattern = key.partition(" ")
            if m == method and re.search(pattern, path):
                return response
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return _err(401, 1000, "Invalid API Token")
        if any(re.search(p, path) for p in self.forbidden):
            return _err(403, 10000, "Authentication error")
        body = json.loads(request.content) if request.content else None

        if path == "/user/tokens/verify":
            return _ok({"id": "tok", "status": self.token_status})
        if path == "/accounts":
            return self._page(self.accounts, request)
        if m := re.fullmatch(r"/accounts/([^/]+)", path):
            acc = next((a for a in self.accounts if a["id"] == m[1]), None)
            return _ok(acc) if acc else _err(404, 1003, "Account not found")
        if path == "/zones":
            account_id = request.url.params.get("account.id")
            zones = [z for z in self.zones if not account_id or z["account"]["id"] == account_id]
            return self._page(zones, request)
        if m := re.fullmatch(r"/zones/([^/]+)", path):
            zone = next((z for z in self.zones if z["id"] == m[1]), None)
            return (
                _ok(zone)
                if zone
                else _err(400, 7003, "Could not route to /zones/x, perhaps your object identifier is invalid?")
            )
        if m := re.fullmatch(r"/zones/([^/]+)/dns_records", path):
            if method == "GET":
                name = request.url.params.get("name")
                items = [r for r in self.records.values() if r["zone_id"] == m[1] and (not name or r["name"] == name)]
                return self._page(items, request)
            rid = uuid.uuid4().hex
            self.records[rid] = {"id": rid, "zone_id": m[1], **body}
            return _ok(self.records[rid])
        if m := re.fullmatch(r"/zones/([^/]+)/dns_records/([^/]+)", path):
            if m[2] not in self.records:
                return _err(404, 81044, "Record does not exist.")
            if method == "DELETE":
                del self.records[m[2]]
                return _ok({"id": m[2]})
            self.records[m[2]] = {"id": m[2], "zone_id": m[1], **body}
            return _ok(self.records[m[2]])
        if m := re.fullmatch(r"/accounts/([^/]+)/cfd_tunnel", path):
            if method == "GET":
                name = request.url.params.get("name")
                items = [
                    t
                    for t in self.tunnels.values()
                    if t["account_tag"] == m[1] and not t["deleted_at"] and (not name or t["name"] == name)
                ]
                return self._page(items, request)
            tid = str(uuid.uuid4())
            self.tunnels[tid] = {
                "id": tid,
                "account_tag": m[1],
                "name": body["name"],
                "config_src": body.get("config_src"),
                "status": "inactive",
                "deleted_at": None,
            }
            return _ok(self.tunnels[tid])
        if m := re.fullmatch(r"/accounts/([^/]+)/cfd_tunnel/([^/]+)(/[a-z]+)?", path):
            tunnel = self.tunnels.get(m[2])
            if tunnel is None or tunnel["deleted_at"]:
                return _err(404, 1003, "Tunnel not found")
            sub = m[3]
            if sub is None and method == "GET":
                return _ok(tunnel)
            if sub is None and method == "DELETE":
                if self.connections.get(m[2]):
                    return _err(400, 1022, "Cannot delete tunnel because it has active connections")
                tunnel["deleted_at"] = "2026-09-16T00:00:00Z"
                return _ok(tunnel)
            if sub == "/token":
                return _ok(f"connector-token-for-{m[2]}")
            if sub == "/connections":
                if method == "DELETE":
                    self.connections[m[2]] = []
                    return _ok(None)
                return _ok(self.connections.get(m[2], []))
            if sub == "/configurations" and method == "PUT":
                self.tunnel_configs[m[2]] = body["config"]
                return _ok({"tunnel_id": m[2], "config": body["config"], "version": 1})
        return _err(404, 7000, f"No route for {method} {path}")


@pytest.fixture
def fake_cf():
    fake = FakeCloudflare()
    cf.set_transport(fake.transport())
    yield fake
    cf.set_transport(None)


def test_bearer_header_and_verify(fake_cf):
    with cf.CloudflareClient(API_TOKEN) as client:
        assert client.verify_token()["status"] == "active"
    request = fake_cf.requests[0]
    assert str(request.url) == "https://api.cloudflare.com/client/v4/user/tokens/verify"
    assert request.headers["Authorization"] == f"Bearer {API_TOKEN}"


def test_token_hidden_in_repr_and_errors(fake_cf):
    client = cf.CloudflareClient(API_TOKEN)
    assert API_TOKEN not in repr(client)
    fake_cf.token = "other"
    with pytest.raises(cf.CloudflareError) as info:
        client.verify_token()
    assert API_TOKEN not in str(info.value) and API_TOKEN not in repr(info.value)
    client.close()


def test_pagination_accounts_zones_and_records(fake_cf):
    fake_cf.accounts = [{"id": f"acc{i}", "name": f"A{i}"} for i in range(1, 121)]
    fake_cf.zones = [
        {"id": f"z{i}", "name": f"site{i}.com", "status": "active", "account": {"id": "acc1"}} for i in range(75)
    ]
    for i in range(130):
        fake_cf.add_record(f"r{i}.site1.com", zone_id="z1")
    with cf.CloudflareClient(API_TOKEN) as client:
        assert len(client.list_accounts()) == 120
        assert len(client.list_zones("acc1")) == 75
        assert client.list_zones("acc2") == []
        assert len(client.list_dns_records("z1")) == 130
    assert len(fake_cf.calls("GET", r"^/client/v4/accounts$")) == 3
    zone_calls = fake_cf.calls("GET", r"^/client/v4/zones$")
    assert zone_calls[0].url.params["account.id"] == "acc1"


def test_check_permissions_all_ok(fake_cf):
    with cf.CloudflareClient(API_TOKEN) as client:
        result = client.check_permissions()
    assert result == {
        "ok": True,
        "accounts": [{"id": "acc1", "name": "My Account"}],
        "zones": [{"id": "zone1", "name": "example.com", "account_id": "acc1", "status": "active"}],
        "missing_permissions": [],
    }
    paths = {r.url.path for r in fake_cf.requests}
    assert "/client/v4/accounts/acc1/cfd_tunnel" in paths
    assert "/client/v4/zones/zone1/dns_records" in paths
    # Only harmless reads.
    assert {r.method for r in fake_cf.requests} == {"GET"}


def test_check_permissions_missing(fake_cf):
    fake_cf.forbidden = [r"/cfd_tunnel", r"/dns_records"]
    with cf.CloudflareClient(API_TOKEN) as client:
        result = client.check_permissions()
    assert result["ok"] is False
    assert result["missing_permissions"] == [cf.PERM_TUNNEL, cf.PERM_DNS]


def test_check_permissions_no_zones_and_no_accounts(fake_cf):
    fake_cf.zones = []
    with cf.CloudflareClient(API_TOKEN) as client:
        assert client.check_permissions()["missing_permissions"] == [cf.PERM_ZONE]
    fake_cf.accounts = []
    with cf.CloudflareClient(API_TOKEN) as client:
        assert client.check_permissions()["missing_permissions"] == [cf.PERM_ACCOUNT_SETTINGS]


def test_invalid_token_maps_to_auth_failed(fake_cf):
    with cf.CloudflareClient("wrong-token") as client, pytest.raises(cf.CloudflareError) as info:
        client.check_permissions()
    assert info.value.is_auth_error
    err = cf.to_api_error(info.value)
    assert (err.status_code, err.code) == (400, "cloudflare_auth_failed")


def test_inactive_token_is_auth_failure(fake_cf):
    fake_cf.token_status = "expired"
    with cf.CloudflareClient(API_TOKEN) as client, pytest.raises(cf.CloudflareError) as info:
        client.check_permissions()
    assert cf.to_api_error(info.value).code == "cloudflare_auth_failed"


def test_error_mapping(fake_cf):
    fake_cf.fail["GET /zones/zone1$"] = _err(500, 10000, "Internal error")
    fake_cf.forbidden = [r"/cfd_tunnel"]
    with cf.CloudflareClient(API_TOKEN) as client:
        with pytest.raises(cf.CloudflareError) as info:
            client.get_zone("zone1")
        err = cf.to_api_error(info.value)
        assert (err.status_code, err.code, err.message) == (502, "cloudflare_api_error", "Cloudflare: Internal error")

        with pytest.raises(cf.CloudflareError) as info:
            client.create_tunnel("acc1", "x")
        err = cf.to_api_error(info.value, cf.PERM_TUNNEL)
        assert err.code == "cloudflare_permission_missing"
        assert err.details["missing_permissions"] == [cf.PERM_TUNNEL]

        with pytest.raises(cf.CloudflareError) as info:
            client.delete_dns_record("zone1", "nope")
        assert info.value.is_not_found


def test_success_false_with_200_is_error(fake_cf):
    fake_cf.fail["GET /accounts$"] = httpx.Response(
        200, json={"success": False, "errors": [{"code": 9999, "message": "nope"}]}
    )
    with cf.CloudflareClient(API_TOKEN) as client, pytest.raises(cf.CloudflareError) as info:
        client.list_accounts()
    assert info.value.message == "nope"


def test_unreachable(fake_cf):
    fake_cf.unreachable = True
    with cf.CloudflareClient(API_TOKEN) as client, pytest.raises(cf.CloudflareError) as info:
        client.verify_token()
    assert info.value.status_code == 0
    assert cf.to_api_error(info.value).status_code == 502


def test_tunnel_and_cname_calls(fake_cf):
    with cf.CloudflareClient(API_TOKEN) as client:
        tunnel = client.create_tunnel("acc1", "deployer-abc")
        assert fake_cf.calls("POST")[0].content and json.loads(fake_cf.calls("POST")[0].content) == {
            "name": "deployer-abc",
            "config_src": "cloudflare",
        }
        assert client.get_tunnel_token("acc1", tunnel["id"]) == f"connector-token-for-{tunnel['id']}"
        record = client.create_cname("zone1", "app.example.com", cf.tunnel_cname_target(tunnel["id"]))
        assert record["proxied"] is True and record["type"] == "CNAME"
        assert record["content"] == f"{tunnel['id']}.cfargotunnel.com"
