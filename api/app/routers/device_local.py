"""Device-local API (docs/DEVICES.md "Device-local API"), served by an installation about to become,
or already acting as, a host device.

Enrollment state lives in Redis (`device:enroll:state`, poll secret encrypted with MASTER_KEY). While
an enrollment is pending a background thread polls the main Deployer every 5 s; `GET .../status`
also polls when the thread is gone (e.g. after an API restart). On approval the device link is saved
to `instance_settings.device_link` and the worker's device agent connects on its own.
"""

from __future__ import annotations

import json
import logging
import platform
import socket
import threading
import time
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.crypto import decrypt_secret, encrypt_secret
from app.db import get_sessionmaker
from app.deps import DbSession, get_current_user
from app.errors import ApiError, forbidden
from app.models import User
from app.redis_client import get_redis
from app.services import device_agent, device_host

router = APIRouter(tags=["device-local"])
log = logging.getLogger(__name__)

STATE_KEY = "device:enroll:state"
POLL_LOCK_KEY = "device:enroll:polling"
POLL_INTERVAL = 5.0
STATUS_STALE_SECONDS = 90
_poller_lock = threading.Lock()
_poller: threading.Thread | None = None


def require_local_admin(request: Request, db: DbSession) -> None:
    """No auth while this installation has no users; afterwards only the instance owner."""
    if db.scalar(select(User.id).limit(1)) is None:
        return
    user = get_current_user(request, db)
    if not user.is_instance_owner:
        raise forbidden("Only the instance owner can attach this installation to another Deployer")


LocalAdmin = Annotated[None, Depends(require_local_admin)]


# ---------------------------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------------------------


def _load_state() -> dict:
    try:
        raw = get_redis().get(STATE_KEY)
        return json.loads(raw) if raw else {}
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ApiError(503, "redis_unavailable", "Enrollment state is unavailable (Redis)") from exc


def _save_state(state: dict) -> None:
    get_redis().set(STATE_KEY, json.dumps(state), ex=3600)


def _public_state(state: dict) -> dict:
    status = state.get("status") or "idle"
    if status == "pending" and time.time() > float(state.get("expires_at") or 0):
        status = "expired"
    return {"status": status, "message": state.get("message")}


# ---------------------------------------------------------------------------------------------
# HTTP to the main Deployer
# ---------------------------------------------------------------------------------------------


def primary_request(primary_url: str, method: str, path: str, body: dict | None = None) -> httpx.Response:
    """Calls the main Deployer with TLS verification, following redirects only within its origin."""
    url = primary_url.rstrip("/") + path
    with httpx.Client(timeout=15.0, follow_redirects=False, verify=True) as client:
        for _ in range(4):
            resp = client.request(method, url, json=body)
            if resp.status_code not in (301, 302, 303, 307, 308):
                return resp
            location = resp.headers.get("location") or ""
            target = str(resp.url.join(location))
            if not device_host.same_origin(target, url) and not (
                target.startswith("https://") and device_host.same_origin(target.replace("https://", "http://", 1), url)
            ):
                raise ApiError(502, "primary_redirect", "The main Deployer redirected to another host; refusing")
            url = target
    raise ApiError(502, "primary_redirect", "Too many redirects from the main Deployer")


def _primary_error(resp: httpx.Response) -> str:
    try:
        return str(resp.json()["error"]["message"])[:300]
    except Exception:  # noqa: BLE001
        return f"HTTP {resp.status_code}"


def poll_once(force: bool = False) -> dict:
    state = _load_state()
    if state.get("status") != "pending":
        return state
    if time.time() > float(state.get("expires_at") or 0):
        state.update(status="expired", message="The code expired; start again")
        _save_state(state)
        return state
    try:
        if not get_redis().set(POLL_LOCK_KEY, "1", nx=True, px=int(POLL_INTERVAL * 1000) - 300) and not force:
            return state
    except Exception:  # noqa: BLE001
        return state
    try:
        resp = primary_request(
            state["primary_url"],
            "POST",
            f"/v1/devices/enrollments/{state['enrollment_id']}/poll",
            {"poll_secret": decrypt_secret(state["poll_secret"])},
        )
    except (httpx.HTTPError, ApiError) as exc:
        state["message"] = f"Could not reach the main Deployer: {getattr(exc, 'message', None) or exc}"[:300]
        _save_state(state)
        return state
    if resp.status_code == 429:
        return state
    if resp.status_code != 200:
        state.update(status="error", message=f"Enrollment failed: {_primary_error(resp)}")
        _save_state(state)
        return state
    data = resp.json()
    status = data.get("status")
    if status == "approved" and data.get("device_token"):
        session = get_sessionmaker()()
        try:
            device_host.save_link(
                session,
                {
                    "primary_url": state["primary_url"],
                    "device_id": data.get("device_id"),
                    "device_token": data["device_token"],
                    "device_name": data.get("device_name") or state.get("device_name"),
                },
            )
            session.commit()
        finally:
            session.close()
        state.update(status="approved", message="Attached to the main Deployer", poll_secret=None)
    elif status in ("denied", "expired"):
        state.update(status=status, message=f"The enrollment was {status}")
    elif status == "consumed":
        state.update(status="error", message="This enrollment was already used")
    else:
        state["message"] = "Waiting for approval on the main Deployer"
    _save_state(state)
    return state


def _poll_loop() -> None:
    while True:
        time.sleep(POLL_INTERVAL)
        try:
            state = poll_once()
        except Exception:  # noqa: BLE001
            log.warning("enrollment poll failed", exc_info=True)
            continue
        if state.get("status") != "pending":
            return


def _ensure_poller() -> None:
    global _poller
    with _poller_lock:
        if _poller is None or not _poller.is_alive():
            _poller = threading.Thread(target=_poll_loop, name="device-enroll-poll", daemon=True)
            _poller.start()


# ---------------------------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------------------------


class EnrollStart(BaseModel):
    primary_url: str = Field(min_length=1, max_length=500)
    device_name: str = Field(min_length=1, max_length=80)


def _link_or_none(db: Session) -> dict | None:
    try:
        return device_host.load_link(db)
    except Exception:  # noqa: BLE001
        return None


@router.get("/device/status")
def device_status(db: DbSession) -> dict:
    link = _link_or_none(db)
    agent = device_agent.read_status() if link else {}
    fresh = time.time() - float(agent.get("updated_at") or 0) < STATUS_STALE_SECONDS
    try:
        hosted = device_host.hosted_summary(db)
    except Exception:  # noqa: BLE001
        hosted = []
    metrics = agent.get("metrics") if fresh and agent.get("metrics") else device_host.collect_metrics()
    return {
        "mode": "host" if link else "standalone",
        "primary_url": link.get("primary_url") if link else None,
        "device_id": link.get("device_id") if link else None,
        "device_name": link.get("device_name") if link else None,
        "connected": bool(link and fresh and agent.get("connected")),
        "last_error": agent.get("last_error") if link else None,
        "last_connected_at": agent.get("last_connected_at") if link else None,
        "hosted_sources": hosted,
        "metrics": metrics,
    }


@router.post("/device/enroll/start")
def enroll_start(body: EnrollStart, _: LocalAdmin, db: DbSession) -> dict:
    if _link_or_none(db):
        raise ApiError(409, "already_attached", "This installation is already a host device")
    primary_url = device_host.validate_primary_url(body.primary_url)
    name = body.device_name.strip()
    if not name:
        raise ApiError(422, "validation_error", "device_name is required")
    payload: dict[str, Any] = {
        "name": name,
        "hostname": socket.gethostname()[:255],
        "os": f"{platform.system()} {platform.release()}"[:120],
        "version": __version__,
        "capabilities": device_host.capabilities(),
    }
    try:
        resp = primary_request(primary_url, "POST", "/v1/devices/enrollments", payload)
    except httpx.HTTPError as exc:
        raise ApiError(502, "primary_unreachable", f"Could not reach the main Deployer: {exc}"[:300]) from exc
    if resp.status_code != 200:
        raise ApiError(502, "enrollment_failed", f"The main Deployer refused the enrollment: {_primary_error(resp)}")
    try:
        data = resp.json()
        enrollment_id, user_code, poll_secret = data["enrollment_id"], data["user_code"], data["poll_secret"]
        expires_in = int(data.get("expires_in") or 900)
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiError(502, "enrollment_failed", "Unexpected answer from the main Deployer") from exc
    verification = str(data.get("verification_uri") or "")
    if not verification.startswith(("https://", "http://")):
        verification = f"{primary_url}/devices/approve?code={user_code}"
    _save_state(
        {
            "status": "pending",
            "message": "Waiting for approval on the main Deployer",
            "primary_url": primary_url,
            "device_name": name,
            "enrollment_id": str(enrollment_id),
            "user_code": str(user_code),
            "poll_secret": encrypt_secret(str(poll_secret)),
            "verification_url": verification,
            "expires_at": time.time() + expires_in,
            "started_at": time.time(),
        }
    )
    _ensure_poller()
    return {"user_code": user_code, "verification_url": verification, "expires_in": expires_in}


@router.get("/device/enroll/status")
def enroll_status(_: LocalAdmin) -> dict:
    state = _load_state()
    if state.get("status") == "pending":
        _ensure_poller()
        state = poll_once()
    return _public_state(state)


@router.post("/device/enroll/cancel")
def enroll_cancel(_: LocalAdmin) -> dict:
    try:
        get_redis().delete(STATE_KEY)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(503, "redis_unavailable", "Enrollment state is unavailable (Redis)") from exc
    return {"ok": True}
