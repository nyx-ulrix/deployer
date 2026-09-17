"""The device agent against a real uvicorn server (WebSocket client, hello/heartbeat, calls, detach)."""

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn

from app.services import device_agent, device_host, device_rpc
from tests import devices_support

make_device = devices_support.make_device  # shared fixture


@pytest.fixture
def server():
    from app.main import app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not srv.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert srv.started
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(10)


def _wait(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def test_agent_connects_serves_calls_and_detaches(server, db, owner, make_device, set_setting, monkeypatch):
    device, token = make_device(owner)
    # On this single test installation the "device" and the "primary" share a database and Redis.
    set_setting(
        "device_link",
        json.dumps({"primary_url": server, "device_id": device.id, "device_token": token, "device_name": "PC"}),
    )
    monkeypatch.setattr(device_agent, "HEARTBEAT_SECONDS", 0.5)
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()
    runner = threading.Thread(target=lambda: loop.run_until_complete(device_agent.run_agent(stop)), daemon=True)
    runner.start()
    try:
        assert _wait(lambda: device_rpc.is_online(device.id)), device_agent.read_status()
        assert device_rpc.call(device.id, "device.ping", {}, timeout=10)["pong"] is True
        status = device_agent.read_status()
        assert status["connected"] is True and status["mode"] == "host"

        def metrics_recorded():
            db.expire_all()
            from app.models import Device

            return bool((db.get(Device, device.id).metrics or {}).get("engines"))

        assert _wait(metrics_recorded)

        from app.errors import ApiError

        with pytest.raises(ApiError) as exc:
            device_rpc.call(device.id, "datasource.call", {"kind": "sql", "database_name": "deployer", "op": "x"})
        assert exc.value.code in ("not_hosted", "validation_error")

        # Progress messages reach callers that asked for them.
        seen = []
        device_host.register_job_handler(
            "test.progress",
            lambda job_id, params, ctx: (ctx.progress(job_id, 0.5, "half"), time.sleep(0.5), {"ok": 1})[2],
        )
        result = device_rpc.call(
            device.id,
            "jobs.run",
            {"job_id": "j1", "type": "test.progress", "params": {}},
            timeout=10,
            progress_id=f"{device.id}:j1",
            on_progress=lambda f, m: seen.append((f, m)),
        )
        assert result == {"ok": 1} and seen == [(0.5, "half")]

        assert device_rpc.call(device.id, "device.detach", {}, timeout=10) == {}
        assert _wait(lambda: not device_rpc.is_online(device.id))
        db.expire_all()
        assert device_host.load_link(db) is None
    finally:
        device_host.JOB_HANDLERS.pop("test.progress", None)
        loop.call_soon_threadsafe(stop.set)
        runner.join(15)


def test_agent_reports_rejection(server, db, owner, set_setting, monkeypatch):
    set_setting(
        "device_link",
        json.dumps({"primary_url": server, "device_id": "x", "device_token": "dpd_unknown", "device_name": "PC"}),
    )
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()
    runner = threading.Thread(target=lambda: loop.run_until_complete(device_agent.run_agent(stop)), daemon=True)
    runner.start()
    try:
        assert _wait(lambda: "rejected" in (device_agent.read_status().get("last_error") or ""))
    finally:
        loop.call_soon_threadsafe(stop.set)
        runner.join(15)
