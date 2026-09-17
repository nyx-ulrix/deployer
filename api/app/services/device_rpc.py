"""Primary-side RPC to host devices over Redis pub/sub (docs/DEVICES.md "Runtime protocol").

Any API/worker process calls `call(device_id, method, params, timeout)`. It publishes the call on
`device:{id}:calls`; the API process holding that device's WebSocket (see routers/devices.py)
forwards it and publishes the device's answer on `device:rpc:reply:{call_id}`.

- A device is online while `device:{id}:online` exists (refreshed by hello/heartbeat, 60 s TTL).
- Calls fail fast with `503 device_offline` when the device is not connected (or nobody holds its
  socket), and with `504 device_timeout` when no answer arrives in time.
- Messages are size-limited; bulk data goes through `transfers` (HTTP), never through the socket.
- Redis failures never propagate as 500s: they become `503 device_offline`.

Transfers (`PUT/GET /v1/devices/transfers/{id}`) are temp files registered in Redis
(`device:transfer:{id}`) for one device and one direction, deleted after download or 24 h.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.errors import ApiError
from app.redis_client import get_redis

log = logging.getLogger(__name__)

ONLINE_TTL_SECONDS = 60
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 6 * 3600.0
MAX_MESSAGE_BYTES = 8 * 1024 * 1024
TRANSFER_TTL_SECONDS = 24 * 3600
_TRANSFER_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def calls_channel(device_id: str) -> str:
    return f"device:{device_id}:calls"


def reply_channel(call_id: str) -> str:
    return f"device:rpc:reply:{call_id}"


def online_key(device_id: str) -> str:
    return f"device:{device_id}:online"


def offline_error(message: str = "The host device is offline") -> ApiError:
    return ApiError(503, "device_offline", message)


# ---------------------------------------------------------------------------------------------
# online state
# ---------------------------------------------------------------------------------------------


def is_online(device_id: str | None) -> bool:
    if not device_id:
        return False
    try:
        return bool(get_redis().exists(online_key(device_id)))
    except Exception:  # noqa: BLE001
        return False


def mark_online(device_id: str, connection_id: str) -> None:
    try:
        get_redis().set(online_key(device_id), connection_id, ex=ONLINE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        log.warning("could not mark device %s online", device_id, exc_info=True)


def mark_offline(device_id: str, connection_id: str) -> None:
    try:
        r = get_redis()
        if r.get(online_key(device_id)) == connection_id:
            r.delete(online_key(device_id))
    except Exception:  # noqa: BLE001
        log.warning("could not mark device %s offline", device_id, exc_info=True)


# ---------------------------------------------------------------------------------------------
# calls
# ---------------------------------------------------------------------------------------------


def _error_from(payload: Any) -> ApiError:
    err = payload if isinstance(payload, dict) else {}
    status = err.get("status")
    status = status if isinstance(status, int) and 400 <= status <= 599 else 502
    code = str(err.get("code") or "device_error")[:64]
    message = str(err.get("message") or "The host device reported an error")[:2000]
    details = err.get("details") if isinstance(err.get("details"), dict) else {}
    return ApiError(status, code, message, details)


def progress_channel(progress_id: str) -> str:
    return f"device:rpc:progress:{progress_id}"


CONNECTION_CHECK_SECONDS = 15.0


def call(
    device_id: str | None,
    method: str,
    params: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    progress_id: str | None = None,
    on_progress: Callable[[float | None, str | None], None] | None = None,
) -> Any:
    """Runs `method` on the device and returns its result (raises ApiError on failure).

    `progress_id` + `on_progress`: `progress` messages the device sends with `job_id == progress_id`
    are delivered to `on_progress(fraction, message)` while waiting. A call fails with
    `device_offline` when the device's connection drops (or is replaced) while it runs.
    """
    if not device_id:
        raise offline_error("No host device")
    timeout = max(1.0, min(float(timeout), MAX_TIMEOUT))
    call_id = uuid.uuid4().hex
    message = json.dumps(
        {"type": "call", "id": call_id, "method": method, "params": params or {}, "timeout": timeout},
        separators=(",", ":"),
        default=str,
    )
    if len(message) > MAX_MESSAGE_BYTES:
        raise ApiError(413, "payload_too_large", "The request is too large to send to a host device")
    try:
        r = get_redis()
        connection = r.get(online_key(device_id))
        if not connection:
            raise offline_error()
        pubsub = r.pubsub(ignore_subscribe_messages=True)
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise offline_error("Device channel unavailable") from exc
    reply_ch = reply_channel(call_id)
    try:
        try:
            channels = [reply_ch] + ([progress_channel(progress_id)] if progress_id and on_progress else [])
            pubsub.subscribe(*channels)
            receivers = r.publish(calls_channel(device_id), message)
        except Exception as exc:  # noqa: BLE001
            raise offline_error("Device channel unavailable") from exc
        if not receivers:
            raise offline_error()
        deadline = time.monotonic() + timeout + 2.0
        next_check = time.monotonic() + CONNECTION_CHECK_SECONDS
        while True:
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise ApiError(504, "device_timeout", f"The host device did not answer {method} in time")
            if now >= next_check:
                next_check = now + CONNECTION_CHECK_SECONDS
                try:
                    current = r.get(online_key(device_id))
                except Exception:  # noqa: BLE001
                    current = connection
                if current != connection:
                    raise offline_error("The host device disconnected while working on the request")
            try:
                msg = pubsub.get_message(timeout=min(remaining, 1.0))
            except Exception as exc:  # noqa: BLE001
                raise offline_error("Device channel lost") from exc
            if not msg or msg.get("type") != "message":
                continue
            try:
                payload = json.loads(msg["data"])
            except (TypeError, ValueError):
                raise ApiError(502, "device_error", "Malformed reply from host device") from None
            if msg.get("channel") != reply_ch:
                if on_progress and isinstance(payload, dict):
                    try:
                        on_progress(payload.get("progress"), payload.get("message"))
                    except Exception:  # noqa: BLE001
                        log.debug("progress callback failed", exc_info=True)
                continue
            if payload.get("ok"):
                return payload.get("result")
            raise _error_from(payload.get("error"))
    finally:
        try:
            pubsub.close()
        except Exception:  # noqa: BLE001
            pass


def publish_reply(call_id: str, reply: dict) -> None:
    data = json.dumps(reply, separators=(",", ":"), default=str)
    if len(data) > MAX_MESSAGE_BYTES:
        data = json.dumps(
            {
                "ok": False,
                "error": {"status": 502, "code": "result_too_large", "message": "Device result is too large"},
            }
        )
    try:
        get_redis().publish(reply_channel(call_id), data)
    except Exception:  # noqa: BLE001
        log.warning("could not publish device reply %s", call_id, exc_info=True)


def publish_progress(progress_id: str, progress: Any, message: Any) -> None:
    try:
        value = float(progress) if progress is not None else None
    except (TypeError, ValueError):
        value = None
    try:
        get_redis().publish(
            progress_channel(progress_id),
            json.dumps({"progress": value, "message": str(message)[:1000] if message is not None else None}),
        )
    except Exception:  # noqa: BLE001
        log.debug("could not publish progress", exc_info=True)


def publish_control(device_id: str, action: str, **extra: Any) -> None:
    """Control messages to the socket holder, e.g. `close` when a device is disabled or removed."""
    try:
        get_redis().publish(
            calls_channel(device_id), json.dumps({"type": "control", "action": action, **extra}, default=str)
        )
    except Exception:  # noqa: BLE001
        log.warning("could not publish control %s for device %s", action, device_id, exc_info=True)


class CallListener(threading.Thread):
    """Subscribes to a device's call channel and hands messages to a callback (socket holder side).

    The subscription is established synchronously in `start()` so publishers see a receiver as
    soon as this returns.
    """

    def __init__(self, device_id: str, on_message):
        super().__init__(name=f"device-calls-{device_id[:8]}", daemon=True)
        self.device_id = device_id
        self.on_message = on_message
        self._stop_event = threading.Event()
        self._pubsub = get_redis().pubsub(ignore_subscribe_messages=True)
        self._pubsub.subscribe(calls_channel(device_id))

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                msg = self._pubsub.get_message(timeout=1.0)
            except Exception:  # noqa: BLE001
                if self._stop_event.is_set():
                    return
                log.warning("device call listener for %s lost Redis", self.device_id, exc_info=True)
                self.on_message(None)
                return
            if msg and msg.get("type") == "message":
                self.on_message(msg["data"])

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._pubsub.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------------------------
# transfers
# ---------------------------------------------------------------------------------------------


def transfer_dir() -> Path:
    """Where transfer files live. Must be shared by the API and worker containers on the primary:
    `DEVICE_TRANSFER_DIR`, else `<BACKUP_DIR>/.transfers` when the backups volume is mounted, else a
    temp directory (single-process setups and tests)."""
    base = os.environ.get("DEVICE_TRANSFER_DIR")
    if not base:
        backup_dir = Path(os.environ.get("BACKUP_DIR") or "/backups")
        if backup_dir.is_dir() and os.access(backup_dir, os.W_OK):
            base = str(backup_dir / ".transfers")
        else:
            base = os.path.join(tempfile.gettempdir(), "deployer-transfers")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def move_file(src: str | os.PathLike, dst: str | os.PathLike) -> None:
    """`os.replace`, falling back to copy-and-delete when `src` and `dst` are on different filesystems
    (inside the container `/tmp` and the `/backups` volume are separate mounts; a plain rename fails
    with EXDEV "Invalid cross-device link")."""
    try:
        os.replace(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.move(str(src), str(dst))


def _transfer_key(transfer_id: str) -> str:
    return f"device:transfer:{transfer_id}"


def valid_transfer_id(transfer_id: str) -> bool:
    return bool(_TRANSFER_ID_RE.fullmatch(transfer_id or ""))


def transfer_path(transfer_id: str) -> Path:
    if not valid_transfer_id(transfer_id):
        raise ApiError(404, "not_found", "Transfer not found")
    return transfer_dir() / f"{transfer_id}.bin"


def create_transfer(
    device_id: str, mode: str, *, source_path: str | os.PathLike | None = None, keep: bool = False
) -> str:
    """Registers a transfer for one device. `mode="put"`: the device uploads; `mode="get"`: the device
    downloads `source_path` (moved into the transfer directory). Returns the transfer id."""
    if mode not in ("put", "get"):
        raise ValueError(mode)
    transfer_id = uuid.uuid4().hex
    path = transfer_path(transfer_id)
    if mode == "get":
        if source_path is None:
            raise ValueError("source_path is required for downloads")
        move_file(source_path, path)
    meta = {"device_id": device_id, "mode": mode, "complete": mode == "get", "keep": keep, "created": time.time()}
    get_redis().set(_transfer_key(transfer_id), json.dumps(meta), ex=TRANSFER_TTL_SECONDS)
    return transfer_id


def get_transfer(transfer_id: str) -> dict | None:
    if not valid_transfer_id(transfer_id):
        return None
    raw = get_redis().get(_transfer_key(transfer_id))
    return json.loads(raw) if raw else None


def update_transfer(transfer_id: str, **fields: Any) -> None:
    meta = get_transfer(transfer_id)
    if meta is None:
        return
    meta.update(fields)
    get_redis().set(_transfer_key(transfer_id), json.dumps(meta), ex=TRANSFER_TTL_SECONDS)


def finish_transfer(transfer_id: str) -> None:
    """Deletes a transfer's file and registration."""
    try:
        get_redis().delete(_transfer_key(transfer_id))
    except Exception:  # noqa: BLE001
        pass
    try:
        transfer_path(transfer_id).unlink(missing_ok=True)
    except (OSError, ApiError):
        pass


def claim_upload(transfer_id: str) -> Path:
    """For the primary after a device upload: returns the completed file path (caller deletes)."""
    meta = get_transfer(transfer_id)
    path = transfer_path(transfer_id)
    if meta is None or meta.get("mode") != "put" or not meta.get("complete") or not path.exists():
        raise ApiError(502, "transfer_incomplete", "The device upload did not complete")
    return path


def cleanup_transfers(max_age_seconds: int = TRANSFER_TTL_SECONDS) -> int:
    removed = 0
    now = time.time()
    try:
        for item in transfer_dir().glob("*.bin*"):
            try:
                if now - item.stat().st_mtime > max_age_seconds:
                    item.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        pass
    return removed
