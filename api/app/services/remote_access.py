"""Remote access orchestration (docs/REMOTE_ACCESS.md).

Owns the `remote_access_mode` / `cloudflare_*` instance settings and the dashboard `domains`, talks to
Cloudflare through `app.services.cloudflare`, and hands the desired connector state to the tunnel
sidecar through files on the shared `tunnel_state` volume:

- `<tunnel_state_dir>/desired.json` (written here, mode 0600, atomic replace)
- `<tunnel_state_dir>/status.json`  (written by deploy/tunnel/supervisor.sh)

Functions that change state commit the session themselves (they interleave external side effects).
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError, conflict, not_found
from app.models import Domain
from app.redis_client import get_redis
from app.services import audit
from app.services import cloudflare as cf
from app.services.instance_settings import get_value, oauth_callback_url, public_url, set_value

log = logging.getLogger(__name__)

# Caddy listener reserved for the tunnel (deploy/Caddyfile): not published on the host, trusts
# X-Forwarded-Proto and takes the client IP from Cf-Connecting-Ip.
ORIGIN_SERVICE = "http://caddy:8081"
MODES = ("off", "cloudflare", "quick")
QUICK_SUFFIX = ".trycloudflare.com"
# The sidecar refreshes status.json at least every 15 s.
STATUS_STALE_SECONDS = 45
# The linked account's zones are cached in Redis so the settings page doesn't hit Cloudflare on every load.
ZONES_CACHE_SECONDS = 300

_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_last_write_error: str | None = None


# --- settings helpers ----------------------------------------------------------------------------


def mode(db: Session) -> str:
    value = get_value(db, "remote_access_mode")
    return value if value in MODES else "off"


def instance_id(db: Session) -> str:
    value = get_value(db, "instance_id")
    if not value:
        value = uuid.uuid4().hex
        set_value(db, "instance_id", value)
        db.flush()
    return str(value)


def tunnel_name(db: Session) -> str:
    return f"deployer-{instance_id(db).replace('-', '')[:8]}"


def is_linked(db: Session) -> bool:
    return bool(get_value(db, "cloudflare_account_id"))


def _linked_state(db: Session) -> tuple[str, str, str]:
    """(api_token, account_id, tunnel_id) or 409 not_linked."""
    token = get_value(db, "cloudflare_api_token") or ""
    account_id = get_value(db, "cloudflare_account_id") or ""
    tunnel_id = get_value(db, "cloudflare_tunnel_id") or ""
    if not (token and account_id and tunnel_id):
        raise conflict("not_linked", "No Cloudflare account is linked")
    return token, account_id, tunnel_id


def _client(token: str, timeout: float | None = None) -> cf.CloudflareClient:
    return cf.CloudflareClient(token, timeout=timeout or cf.TIMEOUT)


def local_url(request: Request | None) -> str:
    port = get_settings().deployer_http_port
    if not port and request is not None and (request.url.hostname or "") in ("localhost", "127.0.0.1"):
        port = request.url.port or 0
    return f"http://localhost:{port or 8080}"


def _public_host(db: Session) -> str:
    return (urlsplit(public_url(db)).hostname or "").lower()


def _revert_public_url(db: Session, request: Request | None, *, hostnames=(), quick: bool = False) -> bool:
    host = _public_host(db)
    if host in set(hostnames) or (quick and host.endswith(QUICK_SUFFIX)):
        set_value(db, "public_url", local_url(request))
        return True
    return False


# --- sidecar files -------------------------------------------------------------------------------


def state_dir() -> Path:
    return Path(get_settings().tunnel_state_dir)


def desired_state(db: Session) -> dict:
    current = mode(db)
    if current == "cloudflare":
        token = get_value(db, "cloudflare_tunnel_token")
        if token:
            return {"mode": "cloudflare", "token": str(token)}
        return {"mode": "off"}
    if current == "quick":
        return {"mode": "quick"}
    return {"mode": "off"}


def write_desired(desired: dict) -> bool:
    """Atomically writes desired.json (0600). Returns False (and remembers the error) on failure."""
    global _last_write_error
    directory = state_dir()
    target = directory / "desired.json"
    data = json.dumps(desired, separators=(",", ":")).encode()
    tmp_path = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".desired-", suffix=".tmp", dir=directory)
        try:
            os.chmod(tmp_path, 0o600)
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_path, target)
        tmp_path = None
    except OSError as exc:
        _last_write_error = f"Could not write {target}: {exc.strerror or type(exc).__name__}"
        log.warning("%s", _last_write_error)
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    _last_write_error = None
    return True


def _read_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def sync_desired(db: Session) -> bool:
    """Writes desired.json only when it differs from the stored settings."""
    desired = desired_state(db)
    if _read_json(state_dir() / "desired.json") == desired and _last_write_error is None:
        return True
    return write_desired(desired)


def sync_on_startup() -> None:
    """Re-creates desired.json after a volume reset. Silently skipped outside the compose stack."""
    if not state_dir().is_dir():
        return
    from app.db import get_sessionmaker

    try:
        with get_sessionmaker()() as db:
            sync_desired(db)
            db.commit()
    except Exception:  # noqa: BLE001 - never block API startup on this
        log.warning("Could not sync the tunnel sidecar state on startup", exc_info=True)


def read_status() -> dict | None:
    return _read_json(state_dir() / "status.json")


def _parse_ts(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def connector_state(db: Session) -> tuple[dict, str | None]:
    """(connector, quick_url) from status.json."""
    current = mode(db)
    status = read_status()
    if _last_write_error:
        return {"running": False, "started_at": None, "last_error": _last_write_error}, None
    if status is None:
        error = None if current == "off" else "The tunnel sidecar has not reported its status yet"
        return {"running": False, "started_at": None, "last_error": error}, None
    updated = _parse_ts(status.get("updated_at"))
    stale = updated is None or (datetime.now(UTC) - updated).total_seconds() > STATUS_STALE_SECONDS
    matches = status.get("mode") == current
    running = bool(status.get("running")) and matches and not stale
    error = status.get("last_error") or None
    if stale and current != "off":
        error = "The tunnel sidecar is not running (no recent status update)"
    connector = {
        "running": running,
        "started_at": status.get("started_at") if running else None,
        "last_error": error,
    }
    quick_url = status.get("quick_url") if running and current == "quick" else None
    return connector, (quick_url or None)


# --- serializers ---------------------------------------------------------------------------------


def domain_out(domain: Domain) -> dict:
    return {
        "id": domain.id,
        "hostname": domain.hostname,
        "zone_id": domain.zone_id,
        "zone_name": domain.zone_name,
        "target_type": domain.target_type,
        "project_id": domain.project_id,
        "status": domain.status,
        "status_message": domain.status_message,
        "url": f"https://{domain.hostname}",
    }


def _domains(db: Session) -> list[Domain]:
    return list(
        db.scalars(
            select(Domain).where(Domain.provider == "cloudflare").order_by(Domain.created_at, Domain.hostname)
        ).all()
    )


def _zones_key(account_id: str) -> str:
    return f"remote_access:zones:{account_id}"


def _cached_zones(account_id: str) -> list[dict] | None:
    try:
        raw = get_redis().get(_zones_key(account_id))
    except Exception:  # noqa: BLE001 - without Redis, just ask Cloudflare
        return None
    return json.loads(raw) if raw else None


def _remember_zones(account_id: str, zones: list[dict] | None) -> None:
    try:
        if zones is None:
            get_redis().delete(_zones_key(account_id))
        else:
            get_redis().set(_zones_key(account_id), json.dumps(zones), ex=ZONES_CACHE_SECONDS)
    except Exception:  # noqa: BLE001
        log.debug("could not cache Cloudflare zones", exc_info=True)


def fetch_zones(client: cf.CloudflareClient, account_id: str) -> list[dict]:
    """`[{id, name, account_id, status}]` of the account, remembered for ZONES_CACHE_SECONDS. Raises."""
    zones = [
        {"id": z["id"], "name": z["name"], "account_id": account_id, "status": z.get("status")}
        for z in client.list_zones(account_id)
    ]
    _remember_zones(account_id, zones)
    return zones


def remote_access_out(db: Session, *, live: bool = True) -> dict:
    connector, quick_url = connector_state(db)
    linked = is_linked(db)
    cloudflare: dict = {
        "linked": linked,
        "token_valid": None,
        "account": None,
        "tunnel": None,
        "domains": [],
        "zones": [],
    }
    if linked:
        account_id = get_value(db, "cloudflare_account_id")
        cloudflare["account"] = {"id": account_id, "name": get_value(db, "cloudflare_account_name") or account_id}
        tunnel_id = get_value(db, "cloudflare_tunnel_id")
        token = get_value(db, "cloudflare_api_token")
        zones = _cached_zones(account_id)
        tunnel = None
        if tunnel_id:
            tunnel = {
                "id": tunnel_id,
                "name": get_value(db, "cloudflare_tunnel_name"),
                "status": None,
                "connections": 0,
            }
        if live and token:
            try:
                with _client(token, timeout=8.0) as client:
                    if tunnel is not None:
                        info = client.get_tunnel(account_id, tunnel_id)
                        tunnel["status"] = info.get("status")
                        clients = client.list_tunnel_connections(account_id, tunnel_id)
                        tunnel["connections"] = sum(len(c.get("conns") or []) for c in clients if isinstance(c, dict))
                    cloudflare["token_valid"] = True
                    if zones is None:
                        zones = fetch_zones(client, account_id)
            except cf.CloudflareError as exc:
                if exc.is_auth_error:
                    cloudflare["token_valid"] = False
                elif exc.is_not_found:
                    cloudflare["token_valid"] = True
                    if tunnel is not None:
                        tunnel["status"] = "deleted"
        cloudflare["tunnel"] = tunnel
        cloudflare["domains"] = [domain_out(d) for d in _domains(db)]
        cloudflare["zones"] = zones or []  # [] while Cloudflare can't be reached
    return {
        "mode": mode(db),
        "public_url": public_url(db),
        "connector": connector,
        "cloudflare": cloudflare,
        "quick": {"url": quick_url},
    }


# --- hostname validation -------------------------------------------------------------------------


def normalize_hostname(raw: str, field: str = "hostname") -> str:
    def invalid() -> ApiError:
        return ApiError(422, "validation_error", f"'{raw}' is not a valid hostname", {"field": field})

    value = (raw or "").strip().rstrip(".").lower()
    if not value or "://" in value or "/" in value or ":" in value or "*" in value:
        raise invalid()
    try:
        ascii_name = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise invalid() from exc
    labels = ascii_name.split(".")
    if len(ascii_name) > 253 or len(labels) < 2 or not all(_LABEL_RE.match(label) for label in labels):
        raise invalid()
    return ascii_name


def hostname_in_zone(hostname: str, zone_name: str) -> bool:
    return hostname == zone_name or hostname.endswith("." + zone_name)


# --- Cloudflare flows ----------------------------------------------------------------------------


def verify(api_token: str) -> dict:
    try:
        with _client(api_token) as client:
            return client.check_permissions()
    except cf.CloudflareError as exc:
        raise cf.to_api_error(exc) from None


def _ingress(hostnames: list[str]) -> list[dict]:
    rules = [{"hostname": h, "service": ORIGIN_SERVICE, "originRequest": {}} for h in hostnames]
    rules.append({"service": "http_status:404"})
    return rules


def _put_ingress(client: cf.CloudflareClient, account_id: str, tunnel_id: str, hostnames: list[str]) -> None:
    try:
        client.put_tunnel_configuration(account_id, tunnel_id, _ingress(hostnames))
    except cf.CloudflareError as exc:
        raise cf.to_api_error(exc, cf.PERM_TUNNEL) from None


def _active_hostnames(db: Session, *, exclude: str | None = None) -> list[str]:
    return [
        d.hostname
        for d in _domains(db)
        if d.target_type == "dashboard" and d.status == "active" and d.hostname != exclude
    ]


def link(db: Session, api_token: str, account_id: str, *, request: Request | None, user_id: str) -> dict:
    api_token = api_token.strip()
    account_id = account_id.strip()
    previous_account = get_value(db, "cloudflare_account_id")
    if previous_account and previous_account != account_id and _domains(db):
        raise conflict(
            "already_linked",
            "Another Cloudflare account is linked and has hostnames. Unlink it first.",
        )
    name = tunnel_name(db)
    client = _client(api_token)
    try:
        try:
            token_info = client.verify_token()
        except cf.CloudflareError as exc:
            raise cf.to_api_error(exc) from None
        if token_info.get("status") not in (None, "active"):
            raise ApiError(400, "cloudflare_auth_failed", f"The Cloudflare API token is {token_info['status']}")
        try:
            account = client.get_account(account_id)
        except cf.CloudflareError as exc:
            if exc.is_auth_error:
                raise cf.to_api_error(exc) from None
            if exc.status_code in (403, 404) or exc.is_not_found:
                raise ApiError(
                    404,
                    "account_not_found",
                    "That Cloudflare account was not found or the token has no access to it",
                    {"missing_permissions": [cf.PERM_ACCOUNT_SETTINGS]},
                ) from None
            raise cf.to_api_error(exc) from None

        tunnel = None
        try:
            stored_id = get_value(db, "cloudflare_tunnel_id")
            if stored_id and previous_account == account_id:
                try:
                    found = client.get_tunnel(account_id, stored_id)
                    if found and not found.get("deleted_at"):
                        tunnel = found
                except cf.CloudflareError as exc:
                    if not exc.is_not_found:
                        raise
            if tunnel is None:
                candidates = [
                    t
                    for t in client.list_tunnels(account_id, name)
                    if t.get("name") == name and not t.get("deleted_at")
                ]
                candidates.sort(key=lambda t: t.get("config_src") != "cloudflare")
                tunnel = candidates[0] if candidates else None
            created = tunnel is None
            if created:
                tunnel = client.create_tunnel(account_id, name)
            connector_token = client.get_tunnel_token(account_id, tunnel["id"])
        except cf.CloudflareError as exc:
            raise cf.to_api_error(exc, cf.PERM_TUNNEL) from None

        hostnames = _active_hostnames(db) if previous_account == account_id else []
        _put_ingress(client, account_id, tunnel["id"], hostnames)
        try:
            fetch_zones(client, account_id)  # warm the cache so the response below can list zones
        except cf.CloudflareError:
            _remember_zones(account_id, None)
    finally:
        client.close()

    previous_mode = mode(db)
    set_value(db, "cloudflare_api_token", api_token)
    set_value(db, "cloudflare_account_id", account_id)
    set_value(db, "cloudflare_account_name", account.get("name") or account_id)
    set_value(db, "cloudflare_tunnel_id", tunnel["id"])
    set_value(db, "cloudflare_tunnel_name", tunnel.get("name") or name)
    set_value(db, "cloudflare_tunnel_token", connector_token)
    set_value(db, "remote_access_mode", "cloudflare")
    if previous_mode == "quick":
        _revert_public_url(db, request, quick=True)
    audit.record(
        db,
        "remote_access.cloudflare_link",
        request=request,
        user_id=user_id,
        account_id=account_id,
        tunnel_id=tunnel["id"],
        tunnel_created=created,
    )
    db.commit()
    write_desired(desired_state(db))
    return remote_access_out(db, live=False)


def add_hostname(
    db: Session, zone_id: str, hostname: str, overwrite: bool, *, request: Request | None, user_id: str
) -> dict:
    token, account_id, tunnel_id = _linked_state(db)
    host = normalize_hostname(hostname)
    if db.scalar(select(Domain).where(Domain.hostname == host)) is not None:
        raise conflict("domain_exists", f"{host} is already configured")
    target = cf.tunnel_cname_target(tunnel_id)

    with _client(token) as client:
        try:
            zone = client.get_zone(zone_id.strip())
        except cf.CloudflareError as exc:
            if exc.is_auth_error or exc.status_code in (0, 429) or exc.status_code >= 500:
                raise cf.to_api_error(exc) from None
            raise ApiError(404, "zone_not_found", "Zone not found in the linked Cloudflare account") from None
        zone_account = (zone.get("account") or {}).get("id")
        if not zone.get("name") or (zone_account and zone_account != account_id):
            raise ApiError(404, "zone_not_found", "Zone not found in the linked Cloudflare account")
        zone_name = normalize_hostname(zone["name"], "zone_id")
        if not hostname_in_zone(host, zone_name):
            raise ApiError(
                422,
                "hostname_not_in_zone",
                f"{host} is not part of the zone {zone_name}",
                {"field": "hostname", "zone_name": zone_name},
            )

        try:
            records = [r for r in client.list_dns_records(zone["id"], host) if str(r.get("name", "")).lower() == host]
        except cf.CloudflareError as exc:
            raise cf.to_api_error(exc, cf.PERM_DNS) from None
        ours = [r for r in records if r.get("type") == "CNAME" and str(r.get("content", "")).lower() == target]
        others = [r for r in records if r not in ours]
        if others and not overwrite:
            raise ApiError(
                409,
                "dns_record_exists",
                f"A DNS record for {host} already exists. Overwrite it to use this hostname.",
                {"records": [{"id": r.get("id"), "type": r.get("type"), "content": r.get("content")} for r in others]},
            )

        domain = Domain(
            hostname=host,
            provider="cloudflare",
            zone_id=zone["id"],
            zone_name=zone_name,
            target_type="dashboard",
            status="pending",
        )
        hostnames = [*_active_hostnames(db), host]
        _put_ingress(client, account_id, tunnel_id, hostnames)

        try:
            if ours:
                record = ours[0]
                for extra in others:
                    client.delete_dns_record(zone["id"], extra["id"])
            elif len(others) == 1 and others[0].get("type") == "CNAME":
                record = client.update_cname(zone["id"], others[0]["id"], host, target)
            else:
                for extra in others:
                    client.delete_dns_record(zone["id"], extra["id"])
                record = client.create_cname(zone["id"], host, target)
        except cf.CloudflareError as exc:
            try:
                client.put_tunnel_configuration(account_id, tunnel_id, _ingress(hostnames[:-1]))
            except cf.CloudflareError:
                log.warning("Could not roll back the tunnel ingress for %s", host)
            raise cf.to_api_error(exc, cf.PERM_DNS) from None

    domain.dns_record_id = (record or {}).get("id")
    domain.status = "active"
    domain.status_message = None
    db.add(domain)
    audit.record(
        db,
        "remote_access.hostname_add",
        request=request,
        user_id=user_id,
        hostname=host,
        zone_id=zone["id"],
        overwrote=bool(others),
    )
    db.commit()
    return domain_out(domain)


def remove_hostname(db: Session, domain_id: str, *, request: Request | None, user_id: str) -> None:
    domain = db.get(Domain, domain_id)
    if domain is None or domain.provider != "cloudflare":
        raise not_found("Domain")
    token = get_value(db, "cloudflare_api_token")
    account_id = get_value(db, "cloudflare_account_id")
    tunnel_id = get_value(db, "cloudflare_tunnel_id")
    if token and account_id and tunnel_id:
        with _client(token) as client:
            if domain.dns_record_id and domain.zone_id:
                try:
                    client.delete_dns_record(domain.zone_id, domain.dns_record_id)
                except cf.CloudflareError as exc:
                    if not exc.is_not_found:
                        raise cf.to_api_error(exc, cf.PERM_DNS) from None
            _put_ingress(client, account_id, tunnel_id, _active_hostnames(db, exclude=domain.hostname))
    hostname = domain.hostname
    db.delete(domain)
    reverted = _revert_public_url(db, request, hostnames=[hostname])
    audit.record(
        db, "remote_access.hostname_remove", request=request, user_id=user_id, hostname=hostname, reverted=reverted
    )
    db.commit()


def unlink(db: Session, delete_dns: bool, delete_tunnel: bool, *, request: Request | None, user_id: str) -> dict:
    if not is_linked(db):
        raise conflict("not_linked", "No Cloudflare account is linked")
    token = get_value(db, "cloudflare_api_token")
    account_id = get_value(db, "cloudflare_account_id")
    tunnel_id = get_value(db, "cloudflare_tunnel_id")
    domains = _domains(db)
    current_mode = mode(db)

    if (delete_dns or delete_tunnel) and not token:
        raise ApiError(400, "cloudflare_auth_failed", "No Cloudflare API token is stored; unlink without deleting")
    if delete_dns or delete_tunnel:
        with _client(token) as client:
            if delete_dns:
                for domain in domains:
                    if not (domain.dns_record_id and domain.zone_id):
                        continue
                    try:
                        client.delete_dns_record(domain.zone_id, domain.dns_record_id)
                    except cf.CloudflareError as exc:
                        if not exc.is_not_found:
                            raise cf.to_api_error(exc, cf.PERM_DNS) from None
            if delete_tunnel and tunnel_id:
                if current_mode == "cloudflare":
                    write_desired({"mode": "off"})  # stop the connector before deleting the tunnel
                try:
                    try:
                        client.cleanup_tunnel_connections(account_id, tunnel_id)
                    except cf.CloudflareError as exc:
                        if not exc.is_not_found:
                            log.info("Tunnel connection cleanup failed: %s", exc.message)
                    client.delete_tunnel(account_id, tunnel_id)
                except cf.CloudflareError as exc:
                    if not exc.is_not_found:
                        write_desired(desired_state(db))  # still linked: restore the connector
                        raise cf.to_api_error(exc, cf.PERM_TUNNEL) from None

    hostnames = [d.hostname for d in domains]
    for domain in domains:
        db.delete(domain)
    _remember_zones(account_id, None)
    for key in (
        "cloudflare_api_token",
        "cloudflare_account_id",
        "cloudflare_account_name",
        "cloudflare_tunnel_id",
        "cloudflare_tunnel_name",
        "cloudflare_tunnel_token",
    ):
        set_value(db, key, None)
    if current_mode == "cloudflare":
        set_value(db, "remote_access_mode", "off")
    reverted = _revert_public_url(db, request, hostnames=hostnames)
    audit.record(
        db,
        "remote_access.cloudflare_unlink",
        request=request,
        user_id=user_id,
        account_id=account_id,
        deleted_dns=delete_dns,
        deleted_tunnel=delete_tunnel,
        public_url_reverted=reverted,
    )
    db.commit()
    write_desired(desired_state(db))
    return remote_access_out(db, live=False)


def set_quick(db: Session, enabled: bool, *, request: Request | None, user_id: str) -> dict:
    previous = mode(db)
    if enabled:
        new_mode = "quick"
    else:
        new_mode = previous if previous != "quick" else ("cloudflare" if is_linked(db) else "off")
    set_value(db, "remote_access_mode", new_mode)
    reverted = False
    if new_mode != "quick":
        reverted = _revert_public_url(db, request, quick=True)
    if new_mode != previous:
        audit.record(
            db, "remote_access.mode_change", request=request, user_id=user_id, mode=new_mode, reverted=reverted
        )
    db.commit()
    write_desired(desired_state(db))
    return remote_access_out(db, live=False)


def switch_public_url(
    db: Session,
    *,
    domain_id: str | None,
    quick: bool,
    local: bool,
    request: Request | None,
    user_id: str,
) -> tuple[str, str]:
    """Sets public_url; returns (previous, new). Caller builds the response."""
    if sum((bool(domain_id), bool(quick), bool(local))) != 1:
        raise ApiError(422, "validation_error", "Pass exactly one of domain_id, quick or local")
    previous = public_url(db)
    if domain_id:
        domain = db.get(Domain, domain_id)
        if domain is None:
            raise not_found("Domain")
        if domain.status != "active":
            raise conflict("domain_not_active", f"{domain.hostname} is not active yet")
        if mode(db) != "cloudflare":
            raise conflict("tunnel_not_active", "Remote access is not using the Cloudflare tunnel")
        new = f"https://{domain.hostname}"
    elif quick:
        _connector, quick_url = connector_state(db)
        if mode(db) != "quick" or not quick_url:
            raise conflict("quick_tunnel_not_ready", "The quick tunnel is not running yet")
        new = quick_url.rstrip("/")
    else:
        new = local_url(request)
    set_value(db, "public_url", new)
    audit.record(
        db, "remote_access.public_url_switch", request=request, user_id=user_id, previous=previous, public_url=new
    )
    db.commit()
    return previous, new


def oauth_callbacks(db: Session) -> dict:
    return {"google": oauth_callback_url(db, "google"), "github": oauth_callback_url(db, "github")}
