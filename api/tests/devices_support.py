"""Shared helpers for host-device tests (import the fixtures into a test module to use them)."""

import json
import threading

import pytest

from app.crypto import encrypt_json
from app.errors import ApiError
from app.models import DataSource, Device
from app.services import device_rpc, devices, provisioning


@pytest.fixture
def make_device(db):
    def factory(owner, name="Laptop", *, status="active", roles=None, sharing_mode="my_projects", mongodb=True):
        token = devices.generate_device_token()
        device = Device(
            name=name,
            owner_id=owner.id,
            status=status,
            roles=roles or ["database_host"],
            sharing_mode=sharing_mode,
            token_hash=devices.hash_token(token),
            capabilities={"engines": {"mariadb": True, "mongodb": mongodb}},
        )
        db.add(device)
        db.commit()
        return device, token

    return factory


class FakeDevice:
    """Subscribes to a device's call channel like a socket holder and answers with `handler`."""

    def __init__(self, device_id, handler):
        self.device_id = device_id
        self.handler = handler
        self.calls = []
        self.listener = device_rpc.CallListener(device_id, self._on_message)
        device_rpc.mark_online(device_id, "fake-conn")

    def _on_message(self, data):
        if data is None:
            return
        msg = json.loads(data)
        if msg.get("type") != "call":
            return
        self.calls.append((msg["method"], msg["params"]))
        threading.Thread(target=self._answer, args=(msg,), daemon=True).start()

    def _answer(self, msg):
        try:
            reply = {"ok": True, "result": self.handler(msg["method"], msg["params"])}
        except ApiError as exc:
            reply = {"ok": False, "error": {"status": exc.status_code, "code": exc.code, "message": exc.message}}
        device_rpc.publish_reply(msg["id"], reply)

    def start(self):
        self.listener.start()
        return self

    def stop(self):
        self.listener.stop()
        device_rpc.mark_offline(self.device_id, "fake-conn")


@pytest.fixture
def fake_device():
    started = []

    def factory(device_id, handler):
        fd = FakeDevice(device_id, handler).start()
        started.append(fd)
        return fd

    yield factory
    for fd in started:
        fd.stop()


def device_source(db, project, device, kind="sql", name=None, database_name="p_test_abc123"):
    ds = DataSource(
        project_id=project.id,
        name=name or f"main-{kind}",
        kind=kind,
        engine="mariadb" if kind == "sql" else "mongodb",
        mode="managed",
        database_name=database_name,
        config_encrypted=encrypt_json(provisioning.device_source_config(kind, database_name, "u_0123456789ab")),
        status="ok",
        device_id=device.id,
    )
    db.add(ds)
    db.commit()
    return ds
