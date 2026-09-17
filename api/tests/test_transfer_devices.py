"""Exports/imports with host devices: device tables, device-hosted data streamed from the device."""

import gzip
import io
import json

import pytest
from sqlalchemy import func, select, text

from app.crypto import encrypt_json
from app.db import Base, get_engine
from app.models import BackupPolicy, DataSource, Device, DeviceProjectGrant, Domain, User
from app.services import device_rpc, provisioning, transfer
from tests import devices_support
from tests.devices_support import device_source

# Shared fixtures (assigned, not imported, so fixture parameters don't shadow an import).
fake_device = devices_support.fake_device
make_device = devices_support.make_device

SQL_DATA = {
    "kind": "sql",
    "engine": "mariadb",
    "database_name": "p_test_abc123",
    "tables": [
        {
            "name": "users",
            "create_sql": "CREATE TABLE users (id int)",
            "columns": [{"name": "id", "type": "int"}],
            "rows": [[1], [2]],
        }
    ],
}


def _payload(db, scope, projects):
    buf = io.StringIO()
    transfer.write_payload(buf, db, scope=scope, projects=projects, created_at="2026-09-16T00:00:00Z")
    return json.loads(buf.getvalue())


def _export_handler(data):
    def handler(method, params):
        if method == "datasource.export":
            with gzip.open(device_rpc.transfer_path(params["transfer_id"]), "wt", encoding="utf-8") as fh:
                fh.write(json.dumps(data))
            device_rpc.update_transfer(params["transfer_id"], complete=True)
            return {"rows": 2, "documents": 0, "tables": 1}
        raise AssertionError(method)

    return handler


def _wipe(db):
    db.close()
    engine = get_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    _ = text


@pytest.fixture
def world(db, owner, make_project, make_device, set_setting):
    project = make_project(owner, "Shop")
    device, _ = make_device(owner, sharing_mode="selected")
    db.add(DeviceProjectGrant(device_id=device.id, project_id=project.id))
    ds = device_source(db, project, device)
    db.add(BackupPolicy(data_source_id=ds.id, schedule="daily", keep_daily=3, copy_to_device_id=device.id))
    db.add(Domain(hostname="shop.example.com", target_type="project", project_id=project.id, status="active"))
    set_setting("device_link", json.dumps({"primary_url": "https://x", "device_token": "dpd_secret"}))
    set_setting("google_client_id", "gid")
    db.commit()
    return {"project": project, "device": device, "ds": ds, "owner": owner}


def test_instance_export_includes_device_tables_and_device_data(db, world, fake_device):
    fd = fake_device(world["device"].id, _export_handler(SQL_DATA))
    payload = _payload(db, "instance", [world["project"]])
    assert [d["id"] for d in payload["devices"]] == [world["device"].id]
    assert payload["devices"][0]["token_hash"] == world["device"].token_hash
    assert [g["project_id"] for g in payload["device_project_grants"]] == [world["project"].id]
    assert payload["backup_policies"][0]["keep_daily"] == 3
    assert payload["domains"][0]["hostname"] == "shop.example.com"
    keys = {s["key"] for s in payload["instance_settings"]}
    assert "google_client_id" in keys and "device_link" not in keys
    assert payload["data"][world["ds"].id] == SQL_DATA
    assert payload["data_sources"][0]["device_id"] == world["device"].id
    assert fd.calls[0][0] == "datasource.export" and fd.calls[0][1]["database_name"] == "p_test_abc123"
    assert not list(device_rpc.transfer_dir().glob(f"{fd.calls[0][1]['transfer_id']}*"))

    projects_payload = _payload(db, "projects", [world["project"]])
    assert "devices" not in projects_payload and projects_payload["data"][world["ds"].id] == SQL_DATA


def test_export_fails_when_device_offline(db, world):
    from app.errors import ApiError

    with pytest.raises(ApiError) as exc:
        _payload(db, "instance", [world["project"]])
    assert exc.value.status_code == 503 and exc.value.code == "device_offline"
    assert "main-sql" in exc.value.message


@pytest.fixture
def fake_provision(monkeypatch):
    calls = []

    def provision_managed_source(db, project, kind, name, *, database_name=None, data_source_id=None, device_id=None):
        calls.append({"kind": kind, "name": name, "database_name": database_name, "device_id": device_id})
        ds = DataSource(
            id=data_source_id,
            project_id=project.id,
            name=name,
            kind=kind,
            engine="mariadb",
            mode="managed",
            database_name=database_name or "p_generated_000000",
            config_encrypted=encrypt_json({}),
            device_id=device_id,
        )
        db.add(ds)
        return ds

    monkeypatch.setattr(provisioning, "provision_managed_source", provision_managed_source)
    monkeypatch.setattr(provisioning, "drop_managed_source", lambda db, ds: None)
    return calls


def test_instance_import_offline_device_restores_on_main(db, world, fake_device, fake_provision, monkeypatch):
    fd = fake_device(world["device"].id, _export_handler(SQL_DATA))
    payload = _payload(db, "instance", [world["project"]])
    fd.stop()
    ids = {"device": world["device"].id, "ds": world["ds"].id}
    _wipe(db)
    restored = []
    monkeypatch.setattr(transfer, "restore_sql_data", lambda ds, data: restored.append((ds.device_id, data)) or 2)

    summary = transfer.import_instance(db, payload)
    assert summary["rows"] == 2 and any("not connected" in w for w in summary["warnings"])
    assert fake_provision == [{"kind": "sql", "name": "main-sql", "database_name": "p_test_abc123", "device_id": None}]
    assert restored == [(None, SQL_DATA)]
    db.expire_all()
    assert db.get(Device, ids["device"]) is not None
    assert db.scalar(select(func.count()).select_from(DeviceProjectGrant)) == 1
    assert db.scalar(select(func.count()).select_from(Domain)) == 1
    policy = db.get(BackupPolicy, ids["ds"])
    assert policy.keep_daily == 3 and policy.copy_to_device_id == ids["device"]
    assert db.scalar(select(User.email)) == "owner@example.com"


def test_instance_import_onto_connected_device(db, world, fake_device, fake_provision):
    fd = fake_device(world["device"].id, _export_handler(SQL_DATA))
    payload = _payload(db, "instance", [world["project"]])
    fd.stop()
    device_id = world["device"].id
    _wipe(db)
    received = []

    def device_handler(method, params):
        assert method == "datasource.import"
        # the device downloads the transfer (simulated by reading the file)
        path = device_rpc.transfer_path(params["transfer_id"])
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            received.append(json.load(fh))
        return {"rows": 2, "documents": 0}

    fake_device(device_id, device_handler)
    summary = transfer.import_instance(db, payload)
    assert "warnings" not in summary and summary["rows"] == 2
    assert fake_provision[0]["device_id"] == device_id
    assert received == [SQL_DATA]


def test_projects_import_checks_device_eligibility(db, world, fake_device, fake_provision, make_user, monkeypatch):
    fd = fake_device(world["device"].id, _export_handler(SQL_DATA))
    payload = _payload(db, "projects", [world["project"]])
    fd.stop()
    monkeypatch.setattr(transfer, "restore_sql_data", lambda ds, data: 2)
    fake_device(world["device"].id, lambda m, p: {"rows": 2})
    # The device shares only the selected (old) project, so the re-imported copy goes to the main server.
    _, summary = transfer.import_projects(db, payload, db.get(User, world["owner"].id))
    assert fake_provision[-1]["device_id"] is None
    assert any("can't host" in w for w in summary["warnings"])

    other = make_user()
    _, summary = transfer.import_projects(db, payload, other)
    assert fake_provision[-1]["device_id"] is None
