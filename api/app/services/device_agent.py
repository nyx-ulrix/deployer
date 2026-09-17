"""Device agent: the host device's outbound connection to the main Deployer (docs/DEVICES.md).

Runs inside `python -m app.worker` on installations that have a `device_link`:

- opens `WS {primary}/v1/devices/connect` with `Authorization: Device <token>`, sends `hello`, then a
  `heartbeat` with metrics every 20 s;
- executes `call` messages in worker threads (bounded concurrency) through
  `device_host.dispatch`, answering with `result` messages; long jobs stream `progress`;
- reconnects with exponential backoff (1 s -> 60 s) and never follows redirects to other hosts;
- publishes its connection state to Redis (`device:agent:status`) for `GET /v1/device/status`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import socket
import time
from typing import Any
from urllib.parse import urlsplit

from app import __version__
from app.db import get_sessionmaker
from app.errors import ApiError
from app.redis_client import get_redis
from app.services import device_host

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 20
MIN_BACKOFF = 1.0
MAX_BACKOFF = 60.0
MAX_CONCURRENT_CALLS = 4
MAX_MESSAGE_BYTES = 8 * 1024 * 1024
STATUS_KEY = "device:agent:status"
LINK_CHECK_SECONDS = 5


def ws_url(primary_url: str) -> str:
    parts = urlsplit(primary_url.rstrip("/"))
    scheme = "wss" if parts.scheme == "https" else "ws"
    return f"{scheme}://{parts.netloc}/v1/devices/connect"


def read_status() -> dict:
    try:
        raw = get_redis().get(STATUS_KEY)
        return json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return {}


def write_status(**fields: Any) -> None:
    try:
        current = read_status()
        current.update(fields)
        current["updated_at"] = time.time()
        get_redis().set(STATUS_KEY, json.dumps(current, default=str), ex=24 * 3600)
    except Exception:  # noqa: BLE001
        log.debug("could not write agent status", exc_info=True)


def _load_link() -> dict | None:
    session = get_sessionmaker()()
    try:
        return device_host.load_link(session)
    finally:
        session.close()


def _connector():
    """`websockets` connect() that refuses cross-origin redirects."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import SecurityError

    class SameOriginConnect(connect):
        def process_redirect(self, exc: Exception) -> Exception | str:
            result = super().process_redirect(exc)
            if isinstance(result, str) and not device_host.same_origin(
                result.replace("wss://", "https://").replace("ws://", "http://"),
                self.uri.replace("wss://", "https://").replace("ws://", "http://"),
            ):
                return SecurityError(f"refusing redirect to another host: {result}")
            return result

    return SameOriginConnect


class DeviceAgent:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._detached = False
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)

    def stop(self) -> None:
        self._stop.set()

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def run_forever(self) -> None:
        backoff = MIN_BACKOFF
        while not self._stop.is_set():
            try:
                link = await asyncio.to_thread(_load_link)
            except Exception:  # noqa: BLE001 - platform DB not ready yet
                log.debug("device link unavailable", exc_info=True)
                link = None
            if not link:
                write_status(mode="standalone", connected=False)
                await self._sleep(LINK_CHECK_SECONDS)
                continue
            started = time.monotonic()
            self._detached = False
            try:
                await self._session(link)
                error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                error = _describe(exc)
                log.warning("device agent connection failed: %s", error)
            write_status(mode="host", connected=False, **({"last_error": error} if error else {}))
            if self._stop.is_set():
                break
            if time.monotonic() - started > 60:
                backoff = MIN_BACKOFF
            await self._sleep(0.2 if self._detached else backoff * (0.8 + 0.4 * random.random()))
            backoff = MIN_BACKOFF if self._detached else min(backoff * 2, MAX_BACKOFF)

    async def _session(self, link: dict) -> None:
        connect = _connector()
        url = ws_url(link["primary_url"])
        async with connect(
            url,
            additional_headers={"Authorization": f"Device {link['device_token']}"},
            max_size=MAX_MESSAGE_BYTES,
            open_timeout=20,
            ping_interval=30,
            ping_timeout=30,
            close_timeout=5,
            user_agent_header=f"deployer-device/{__version__}",
        ) as ws:
            write_status(
                mode="host",
                connected=True,
                last_error=None,
                last_connected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                primary_url=link["primary_url"],
            )
            loop = asyncio.get_running_loop()
            metrics = await asyncio.to_thread(device_host.collect_metrics)
            await ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "version": __version__,
                        "capabilities": device_host.capabilities(),
                        "metrics": metrics,
                        "hostname": socket.gethostname(),
                    }
                )
            )
            ctx = device_host.CallContext(
                primary_url=link["primary_url"],
                device_token=link["device_token"],
                progress=lambda job_id, progress, message: asyncio.run_coroutine_threadsafe(
                    _send(ws, {"type": "progress", "job_id": job_id, "progress": progress, "message": message}), loop
                ),
                detach=lambda: loop.call_soon_threadsafe(self._on_detach),
            )
            heartbeat = asyncio.create_task(self._heartbeat(ws, link))
            tasks: set[asyncio.Task] = set()
            try:
                async for raw in ws:
                    if self._stop.is_set():
                        break
                    try:
                        msg = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(msg, dict) or msg.get("type") != "call":
                        continue
                    task = asyncio.create_task(self._handle_call(ws, msg, ctx))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    if self._detached:
                        break
            finally:
                heartbeat.cancel()
                for task in list(tasks):
                    if self._detached:
                        try:
                            await asyncio.wait_for(task, timeout=5)
                        except Exception:  # noqa: BLE001
                            pass
                    task.cancel()

    def _on_detach(self) -> None:
        self._detached = True
        write_status(mode="standalone", connected=False, last_error=None)

    async def _heartbeat(self, ws, link: dict) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            current = await asyncio.to_thread(_load_link)
            if not current or current.get("device_token") != link.get("device_token"):
                await ws.close(code=1000, reason="detached")
                return
            metrics = await asyncio.to_thread(device_host.collect_metrics)
            await _send(ws, {"type": "heartbeat", "metrics": metrics})
            write_status(mode="host", connected=True, metrics=metrics)

    async def _handle_call(self, ws, msg: dict, ctx: device_host.CallContext) -> None:
        call_id = str(msg.get("id") or "")[:64]
        method = msg.get("method")
        params = msg.get("params")
        try:
            timeout = float(msg.get("timeout") or 30)
        except (TypeError, ValueError):
            timeout = 30.0
        async with self._semaphore:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(device_host.dispatch, method, params, ctx), timeout=timeout + 1
                )
                reply = {"type": "result", "id": call_id, "ok": True, "result": result}
            except TimeoutError:
                reply = {
                    "type": "result",
                    "id": call_id,
                    "ok": False,
                    "error": {"status": 504, "code": "device_timeout", "message": f"{method} timed out on the device"},
                }
            except Exception as exc:  # noqa: BLE001
                if not isinstance(exc, ApiError):
                    log.exception("device call %s failed", method)
                reply = {"type": "result", "id": call_id, "ok": False, "error": device_host.error_payload(exc)}
        data = json.dumps(reply, default=str)
        if len(data) > MAX_MESSAGE_BYTES:
            data = json.dumps(
                {
                    "type": "result",
                    "id": call_id,
                    "ok": False,
                    "error": {"status": 502, "code": "result_too_large", "message": "Result too large; narrow it down"},
                }
            )
        try:
            await ws.send(data)
        except Exception:  # noqa: BLE001
            log.warning("could not send result for %s", method)
        if self._detached:
            await ws.close(code=1000, reason="detached")


async def _send(ws, payload: dict) -> None:
    try:
        await ws.send(json.dumps(payload, default=str))
    except Exception:  # noqa: BLE001
        log.debug("send failed", exc_info=True)


def _describe(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return f"The main Deployer rejected this device (HTTP {status}); it may have been removed or disabled"
    return f"{type(exc).__name__}: {exc}"[:500]


async def run_agent(stop: asyncio.Event | None = None) -> None:
    """Entry point for the worker: runs until `stop` is set (or forever)."""
    agent = DeviceAgent()
    if stop is None:
        await agent.run_forever()
        return
    runner = asyncio.create_task(agent.run_forever())
    await stop.wait()
    agent.stop()
    try:
        await asyncio.wait_for(runner, timeout=10)
    except (TimeoutError, asyncio.CancelledError):
        runner.cancel()
