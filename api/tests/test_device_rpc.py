"""Primary-side device RPC: Redis pub/sub routing, the control WebSocket and transfers."""

import hashlib
import json
import threading
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.errors import ApiError
from app.models import Device, Job
from app.services import device_rpc
from tests import devices_support

# Shared fixtures (assigned, not imported, so fixture parameters don't shadow an import).
fake_device = devices_support.fake_device
make_device = devices_support.make_device


def test_call_offline_device():
    with pytest.raises(ApiError) as exc:
        device_rpc.call("missing-device", "device.ping", {}, timeout=1)
    assert exc.value.status_code == 503 and exc.value.code == "device_offline"


def test_online_key_without_socket_holder_is_offline():
    device_rpc.mark_online("dev-1", "conn")
    with pytest.raises(ApiError) as exc:
        device_rpc.call("dev-1", "device.ping", {}, timeout=1)
    assert exc.value.code == "device_offline"


def test_call_roundtrip_and_errors(fake_device):
    def handler(method, params):
        if method == "boom":
            raise ApiError(404, "not_hosted", "nope")
        return {"echo": params}

    fake_device("dev-2", handler)
    assert device_rpc.call("dev-2", "echo", {"a": 1}, timeout=5) == {"echo": {"a": 1}}
    with pytest.raises(ApiError) as exc:
        device_rpc.call("dev-2", "boom", {}, timeout=5)
    assert (exc.value.status_code, exc.value.code, exc.value.message) == (404, "not_hosted", "nope")


def test_call_timeout(fake_device):
    fake_device("dev-3", lambda m, p: time.sleep(10))
    started = time.monotonic()
    with pytest.raises(ApiError) as exc:
        device_rpc.call("dev-3", "slow", {}, timeout=1)
    assert exc.value.status_code == 504 and exc.value.code == "device_timeout"
    assert time.monotonic() - started < 8


def test_call_fails_when_connection_replaced(fake_device, monkeypatch):
    monkeypatch.setattr(device_rpc, "CONNECTION_CHECK_SECONDS", 0.2)

    def handler(method, params):
        time.sleep(0.1)
        device_rpc.mark_online("dev-4", "other-connection")
        time.sleep(3)
        return {}

    fake_device("dev-4", handler)
    with pytest.raises(ApiError) as exc:
        device_rpc.call("dev-4", "slow", {}, timeout=10)
    assert exc.value.code == "device_offline"


def test_error_status_is_clamped():
    err = device_rpc._error_from({"status": 200, "code": "x", "message": "m"})
    assert err.status_code == 502


# --- WebSocket control channel ------------------------------------------------------------------


def _hello(ws, **extra):
    ws.send_text(
        json.dumps(
            {
                "type": "hello",
                "version": "0.1.0",
                "capabilities": {"engines": {"mariadb": True}},
                "metrics": {"cpu_percent": 5},
                **extra,
            }
        )
    )


def _wait_for(predicate, timeout=15):
    """Polls `predicate` (the server handles socket messages on its own threads, so under full-suite
    load a few hundred ms of lag is normal)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _wait_online(device_id, timeout=15):
    return _wait_for(lambda: device_rpc.is_online(device_id), timeout)


def _fresh(db, model, key):
    db.rollback()  # end any read transaction so the server's writes are visible (and not blocked)
    db.expire_all()
    return db.get(model, key)


def test_websocket_requires_device_token(client, owner, owner_headers):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/devices/connect", headers=owner_headers) as ws:
            ws.receive_text()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/devices/connect", headers={"Authorization": "Device dpd_wrong"}) as ws:
            ws.receive_text()


def test_websocket_disabled_device_rejected(client, owner, make_device):
    device, token = make_device(owner, status="disabled")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/devices/connect", headers={"Authorization": f"Device {token}"}) as ws:
            ws.receive_text()


def test_websocket_call_flow(client, db, owner, make_device):
    device, token = make_device(owner)
    with client.websocket_connect("/v1/devices/connect", headers={"Authorization": f"Device {token}"}) as ws:
        _hello(ws, hostname="pc-1")
        assert _wait_online(device.id)
        results = {}

        def caller():
            try:
                results["value"] = device_rpc.call(device.id, "device.ping", {"x": 1}, timeout=10)
            except ApiError as exc:  # pragma: no cover - reported below
                results["error"] = exc

        t = threading.Thread(target=caller)
        t.start()
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "call" and msg["method"] == "device.ping" and msg["params"] == {"x": 1}
        ws.send_text(json.dumps({"type": "result", "id": msg["id"], "ok": True, "result": {"pong": True}}))
        t.join(10)
        assert results == {"value": {"pong": True}}

        ws.send_text(json.dumps({"type": "heartbeat", "metrics": {"cpu_percent": 42}}))
        device_id = device.id
        assert _wait_for(lambda: (_fresh(db, Device, device_id).metrics or {}).get("cpu_percent") == 42)
        refreshed = _fresh(db, Device, device_id)
        assert refreshed.hostname == "pc-1" and refreshed.last_seen_at is not None
    assert _wait_for(lambda: not device_rpc.is_online(device_id))
    db.rollback()


def test_websocket_progress_updates_job(client, db, owner, make_device):
    device, token = make_device(owner)
    job = Job(type="backup.snapshot", status="running", device_id=device.id)
    db.add(job)
    db.commit()
    with client.websocket_connect("/v1/devices/connect", headers={"Authorization": f"Device {token}"}) as ws:
        _hello(ws)
        assert _wait_online(device.id)
        ws.send_text(json.dumps({"type": "progress", "job_id": job.id, "progress": 0.5, "message": "half"}))
        job_id = job.id
        assert _wait_for(lambda: _fresh(db, Job, job_id).progress == 0.5)
        assert _fresh(db, Job, job_id).message == "half"
    db.rollback()


def test_disabling_device_closes_socket(client, owner, owner_headers, make_device):
    device, token = make_device(owner)
    with client.websocket_connect("/v1/devices/connect", headers={"Authorization": f"Device {token}"}) as ws:
        _hello(ws)
        assert _wait_online(device.id)
        resp = client.patch(f"/v1/devices/{device.id}", json={"status": "disabled"}, headers=owner_headers)
        assert resp.status_code == 200
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 4403


# --- transfers ------------------------------------------------------------------------------------


def test_transfers_put_and_get(client, owner, make_device, owner_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("DEVICE_TRANSFER_DIR", str(tmp_path))
    device, token = make_device(owner)
    other, other_token = make_device(owner, "Other")
    headers = {"Authorization": f"Device {token}"}

    upload_id = device_rpc.create_transfer(device.id, "put")
    body = b"x" * 3_000_000
    assert client.put(f"/v1/devices/transfers/{upload_id}", content=body, headers=owner_headers).status_code == 401
    assert (
        client.put(
            f"/v1/devices/transfers/{upload_id}", content=body, headers={"Authorization": f"Device {other_token}"}
        ).status_code
        == 404
    )
    resp = client.put(f"/v1/devices/transfers/{upload_id}", content=body, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["sha256"] == hashlib.sha256(body).hexdigest()
    assert client.put(f"/v1/devices/transfers/{upload_id}", content=b"again", headers=headers).status_code == 409
    assert device_rpc.claim_upload(upload_id).read_bytes() == body

    src = tmp_path / "payload.bin"
    src.write_bytes(b"hello device")
    download_id = device_rpc.create_transfer(device.id, "get", source_path=src)
    assert client.get(f"/v1/devices/transfers/{download_id}", headers=owner_headers).status_code == 401
    resp = client.get(f"/v1/devices/transfers/{download_id}", headers=headers)
    assert resp.status_code == 200 and resp.content == b"hello device"
    assert not device_rpc.transfer_path(download_id).exists()
    assert client.get(f"/v1/devices/transfers/{download_id}", headers=headers).status_code == 404
    assert client.get("/v1/devices/transfers/..%2F..%2Fetc", headers=headers).status_code == 404
