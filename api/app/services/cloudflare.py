"""Thin Cloudflare API v4 client (docs/REMOTE_ACCESS.md).

Only the calls Deployer needs: token verification, accounts/zones, remotely-managed tunnels and
proxied CNAME records. The API token is sent as a bearer header and is never logged, included in
exception messages or returned by `repr()`.

Tests replace the network with `httpx.MockTransport` via `set_transport()`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.errors import ApiError

log = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"
TIMEOUT = httpx.Timeout(20.0, connect=8.0)
MAX_PAGES = 40

# Human-readable names, exactly as shown in the Cloudflare dashboard token editor.
PERM_TUNNEL = "Account / Cloudflare Tunnel / Edit"
PERM_ACCOUNT_SETTINGS = "Account / Account Settings / Read"
PERM_DNS = "Zone / DNS / Edit"
PERM_ZONE = "Zone / Zone / Read"
REQUIRED_PERMISSIONS = [PERM_TUNNEL, PERM_ACCOUNT_SETTINGS, PERM_DNS, PERM_ZONE]

# Cloudflare error codes that mean "this token is not valid" (rather than "not allowed").
_AUTH_ERROR_CODES = {1000, 1001, 6003, 6103, 6111, 9103, 9106, 9107}
# Cloudflare error codes that mean "this object does not exist".
_NOT_FOUND_CODES = {1003, 7003, 81044, 1033}

_transport: httpx.BaseTransport | None = None


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Test hook: route every client through this transport (None restores the network)."""
    global _transport
    _transport = transport


@dataclass(eq=False)
class CloudflareError(Exception):
    status_code: int  # HTTP status from Cloudflare; 0 when Cloudflare could not be reached
    message: str
    errors: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return f"Cloudflare API error {self.status_code}: {self.message}"

    @property
    def codes(self) -> set[int]:
        return {
            int(e["code"]) for e in self.errors if isinstance(e.get("code"), int | str) and str(e["code"]).isdigit()
        }

    @property
    def is_auth_error(self) -> bool:
        return self.status_code == 401 or (self.status_code == 400 and bool(self.codes & _AUTH_ERROR_CODES))

    @property
    def is_forbidden(self) -> bool:
        return self.status_code == 403 and not self.is_auth_error

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404 or bool(self.codes & _NOT_FOUND_CODES)


def to_api_error(exc: CloudflareError, permission: str | None = None) -> ApiError:
    """Maps a Cloudflare failure to the documented Deployer error codes."""
    if exc.is_auth_error:
        return ApiError(
            400,
            "cloudflare_auth_failed",
            "Cloudflare rejected the API token (invalid, expired or revoked)",
        )
    if exc.status_code == 403:
        missing = [permission] if permission else []
        detail = f": {permission}" if permission else ""
        return ApiError(
            400,
            "cloudflare_permission_missing",
            f"The Cloudflare API token is missing a required permission{detail}",
            {"missing_permissions": missing, "cloudflare_message": exc.message},
        )
    if exc.status_code == 0:
        return ApiError(502, "cloudflare_api_error", exc.message)
    return ApiError(502, "cloudflare_api_error", f"Cloudflare: {exc.message}", {"status": exc.status_code})


class CloudflareClient:
    def __init__(self, api_token: str, *, timeout: httpx.Timeout | float = TIMEOUT):
        if not api_token:
            raise ValueError("api_token is required")
        self._http = httpx.Client(
            base_url=API_BASE,
            timeout=timeout,
            transport=_transport,
            headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json"},
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return "CloudflareClient(<token hidden>)"

    def __enter__(self) -> CloudflareClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- plumbing --------------------------------------------------------------------------------

    def _request(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> dict:
        try:
            response = self._http.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            # The exception text never contains request headers.
            log.warning("Cloudflare %s %s failed: %s", method, path, type(exc).__name__)
            raise CloudflareError(0, "Could not reach the Cloudflare API") from None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            if response.is_success:
                raise CloudflareError(response.status_code, "Unexpected response from Cloudflare")
            raise CloudflareError(response.status_code, f"HTTP {response.status_code}")
        if response.is_success and payload.get("success", True):
            return payload
        errors = [e for e in payload.get("errors") or [] if isinstance(e, dict)]
        message = "; ".join(str(e.get("message") or "") for e in errors if e.get("message")) or (
            f"HTTP {response.status_code}"
        )
        status = response.status_code if not response.is_success else 400
        log.info("Cloudflare %s %s -> %s (%s)", method, path, status, [e.get("code") for e in errors])
        raise CloudflareError(status, message, errors)

    def _result(self, method: str, path: str, **kwargs) -> Any:
        return self._request(method, path, **kwargs).get("result")

    def _paginate(self, path: str, params: dict | None = None, per_page: int = 50) -> list[dict]:
        items: list[dict] = []
        page = 1
        while page <= MAX_PAGES:
            payload = self._request("GET", path, params={**(params or {}), "page": page, "per_page": per_page})
            result = payload.get("result") or []
            items.extend(result)
            info = payload.get("result_info") or {}
            total_pages = info.get("total_pages")
            if total_pages is None:
                # Some endpoints omit total_pages; stop when a page comes back short.
                if len(result) < per_page:
                    break
            elif page >= int(total_pages):
                break
            page += 1
        return items

    # --- token / accounts / zones ---------------------------------------------------------------

    def verify_token(self) -> dict:
        return self._result("GET", "/user/tokens/verify") or {}

    def list_accounts(self) -> list[dict]:
        return self._paginate("/accounts")

    def get_account(self, account_id: str) -> dict:
        return self._result("GET", f"/accounts/{account_id}") or {}

    def list_zones(self, account_id: str | None = None) -> list[dict]:
        return self._paginate("/zones", {"account.id": account_id} if account_id else None)

    def get_zone(self, zone_id: str) -> dict:
        return self._result("GET", f"/zones/{zone_id}") or {}

    # --- tunnels ---------------------------------------------------------------------------------

    def list_tunnels(self, account_id: str, name: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"is_deleted": "false"}
        if name:
            params["name"] = name
        return self._paginate(f"/accounts/{account_id}/cfd_tunnel", params)

    def create_tunnel(self, account_id: str, name: str) -> dict:
        return self._result(
            "POST", f"/accounts/{account_id}/cfd_tunnel", json={"name": name, "config_src": "cloudflare"}
        )

    def get_tunnel(self, account_id: str, tunnel_id: str) -> dict:
        return self._result("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}") or {}

    def get_tunnel_token(self, account_id: str, tunnel_id: str) -> str:
        token = self._result("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/token")
        if not isinstance(token, str) or not token:
            raise CloudflareError(502, "Cloudflare returned no tunnel token")
        return token

    def list_tunnel_connections(self, account_id: str, tunnel_id: str) -> list[dict]:
        return self._result("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections") or []

    def cleanup_tunnel_connections(self, account_id: str, tunnel_id: str) -> None:
        self._request("DELETE", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections")

    def delete_tunnel(self, account_id: str, tunnel_id: str) -> None:
        self._request("DELETE", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}")

    def put_tunnel_configuration(self, account_id: str, tunnel_id: str, ingress: list[dict]) -> dict:
        return self._result(
            "PUT",
            f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
            json={"config": {"ingress": ingress}},
        )

    # --- DNS -------------------------------------------------------------------------------------

    def list_dns_records(self, zone_id: str, name: str | None = None) -> list[dict]:
        params = {"name": name} if name else None
        return self._paginate(f"/zones/{zone_id}/dns_records", params, per_page=100)

    def create_cname(self, zone_id: str, name: str, target: str) -> dict:
        return self._result("POST", f"/zones/{zone_id}/dns_records", json=_cname_body(name, target))

    def update_cname(self, zone_id: str, record_id: str, name: str, target: str) -> dict:
        return self._result("PUT", f"/zones/{zone_id}/dns_records/{record_id}", json=_cname_body(name, target))

    def delete_dns_record(self, zone_id: str, record_id: str) -> None:
        self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")

    # --- permission check ------------------------------------------------------------------------

    def check_permissions(self) -> dict:
        """Verifies the token and probes each required permission with harmless read calls.

        Returns `{ok, accounts, zones, missing_permissions}`. Raises CloudflareError when the token
        itself is invalid (or Cloudflare is unreachable).

        Only reads are possible without side effects, so "Edit" permissions are checked through
        their read access; a token with Read-only tunnel/DNS access fails later with
        `cloudflare_permission_missing`.
        """
        token = self.verify_token()
        if token.get("status") and token["status"] != "active":
            raise CloudflareError(401, f"The API token is {token['status']}", [{"code": 1000}])

        missing: list[str] = []

        def add(permission: str) -> None:
            if permission not in missing:
                missing.append(permission)

        try:
            accounts = [{"id": a["id"], "name": a.get("name") or a["id"]} for a in self.list_accounts()]
        except CloudflareError as exc:
            if not exc.is_forbidden:
                raise
            accounts = []
        if not accounts:
            add(PERM_ACCOUNT_SETTINGS)

        zones: list[dict] = []
        for account in accounts:
            try:
                for z in self.list_zones(account["id"]):
                    zones.append(
                        {"id": z["id"], "name": z["name"], "account_id": account["id"], "status": z.get("status")}
                    )
            except CloudflareError as exc:
                if not exc.is_forbidden:
                    raise
                add(PERM_ZONE)
            try:
                self._request(
                    "GET", f"/accounts/{account['id']}/cfd_tunnel", params={"is_deleted": "false", "per_page": 1}
                )
            except CloudflareError as exc:
                if not (exc.is_forbidden or exc.status_code == 401):
                    raise
                add(PERM_TUNNEL)
        if accounts and not zones:
            # Without Zone Read the zone list is simply empty.
            add(PERM_ZONE)

        # DNS: probe one zone per account.
        probed: set[str] = set()
        for zone in zones:
            if zone["account_id"] in probed:
                continue
            probed.add(zone["account_id"])
            try:
                self._request("GET", f"/zones/{zone['id']}/dns_records", params={"per_page": 1})
            except CloudflareError as exc:
                if not (exc.is_forbidden or exc.status_code == 401):
                    raise
                add(PERM_DNS)

        return {"ok": not missing, "accounts": accounts, "zones": zones, "missing_permissions": missing}


def _cname_body(name: str, target: str) -> dict:
    return {
        "type": "CNAME",
        "name": name,
        "content": target,
        "proxied": True,
        "ttl": 1,
        "comment": "Managed by Deployer (Cloudflare Tunnel)",
    }


def tunnel_cname_target(tunnel_id: str) -> str:
    return f"{tunnel_id}.cfargotunnel.com"
