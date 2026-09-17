"""Host device end-to-end against real MariaDB 11 and MongoDB 5.0 (device side + primary routing).

Skipped unless both servers are configured (see test_managed_databases.py for docker commands)::

    DEPLOYER_IT_MARIADB_URL=mysql://root:<password>@127.0.0.1:13306 \
    DEPLOYER_IT_MONGO_URI=mongodb://admin:<password>@127.0.0.1:37017 pytest tests/integration/test_host_device.py

The "device" and the "main Deployer" share this process: RPC calls travel through fakeredis to an
in-process socket-holder stand-in that runs `device_host.dispatch`, exactly what the device agent does.
"""

import io
import json
import os
from urllib.parse import urlsplit

import pytest

from app.config import get_settings
from app.errors import ApiError
from app.services import device_host, device_rpc, provisioning, source_ops, transfer
from tests import devices_support
from tests.devices_support import FakeDevice

make_device = devices_support.make_device  # shared fixture

MARIADB_URL = os.environ.get("DEPLOYER_IT_MARIADB_URL")
MONGO_URI = os.environ.get("DEPLOYER_IT_MONGO_URI")

pytestmark = pytest.mark.skipif(
    not (MARIADB_URL and MONGO_URI), reason="set DEPLOYER_IT_MARIADB_URL and DEPLOYER_IT_MONGO_URI"
)


@pytest.fixture
def servers(monkeypatch):
    settings = get_settings()
    m, g = urlsplit(MARIADB_URL), urlsplit(MONGO_URI)
    monkeypatch.setattr(settings, "mariadb_host", m.hostname)
    monkeypatch.setattr(settings, "mariadb_port", m.port or 3306)
    monkeypatch.setattr(settings, "mariadb_root_password", m.password or "")
    monkeypatch.setattr(settings, "mongo_host", g.hostname)
    monkeypatch.setattr(settings, "mongo_port", g.port or 27017)
    monkeypatch.setattr(settings, "mongo_root_username", g.username or "")
    monkeypatch.setattr(settings, "mongo_root_password", g.password or "")
    monkeypatch.setattr(settings, "managed_mongodb_enabled", True)
    provisioning.mariadb_root_engine.cache_clear()
    provisioning.mongo_root_client.cache_clear()
    yield
    from app.db import get_sessionmaker

    session = get_sessionmaker()()
    try:
        for name, entry in device_host.load_credentials(session).items():
            try:
                device_host.m_drop({"kind": entry["kind"], "database_name": name}, device_host.CallContext())
            except Exception:  # noqa: BLE001
                pass
    finally:
        session.close()


@pytest.fixture
def device_process(servers, owner, make_device, tmp_path, monkeypatch):
    """A connected device whose RPCs run `device_host.dispatch` in this process."""
    monkeypatch.setenv("DEVICE_TRANSFER_DIR", str(tmp_path / "transfers"))
    device, _ = make_device(owner)
    ctx = device_host.CallContext()

    def upload(c, transfer_id, path):
        data = open(path, "rb").read()
        device_rpc.transfer_path(transfer_id).write_bytes(data)
        device_rpc.update_transfer(transfer_id, complete=True)
        return {"sha256": "", "size": len(data)}

    def download(c, transfer_id, path):
        path.write_bytes(device_rpc.transfer_path(transfer_id).read_bytes())
        return {"sha256": "", "size": path.stat().st_size}

    monkeypatch.setattr(device_host, "upload_file", upload)
    monkeypatch.setattr(device_host, "download_file", download)
    fd = FakeDevice(device.id, lambda method, params: device_host.dispatch(method, params, ctx)).start()
    yield device
    fd.stop()


def test_device_hosted_sql_and_mongo(db, owner, make_project, device_process):
    device = device_process
    project = make_project(owner, "Edge Shop")

    # Commit after each provision: here the "device" shares the test's SQLite file, and an open write
    # transaction would block the device from saving its hosted credentials (separate DBs in reality).
    sql = provisioning.provision_managed_source(db, project, "sql", "main-sql", device_id=device.id)
    db.commit()
    mongo = provisioning.provision_managed_source(db, project, "nosql", "main-nosql", device_id=device.id)
    db.commit()
    creds = device_host.get_credentials()
    assert set(creds) == {sql.database_name, mongo.database_name}
    assert "password" not in json.dumps(provisioning.connections.load_config(sql))

    source_ops.create_table(
        sql,
        {
            "name": "users",
            "columns": [
                {"name": "id", "type": "bigint", "primary_key": True, "auto_increment": True},
                {"name": "email", "type": "varchar(255)", "nullable": False, "unique": True},
            ],
            "timestamps": False,
        },
    )
    source_ops.insert_row(sql, "users", {"email": "a@example.com"})
    source_ops.insert_row(sql, "users", {"email": "b@example.com"})
    rows = source_ops.list_rows(sql, "users", limit=10, offset=0, order_by=None, order="asc")
    assert rows["total"] == 2
    schema = source_ops.introspect_sources([sql, mongo])
    assert schema[0]["status"] == "ok" and schema[0]["entities"][0]["name"] == "users"
    assert "CREATE TABLE `users`" in source_ops.export_sources([sql], "sql")

    source_ops.create_collection(mongo, "events", None)
    doc = source_ops.insert_document(mongo, "events", {"kind": "signup", "n": 1})["document"]
    assert source_ops.list_documents(mongo, "events", filter_json=None)["total"] == 1
    source_ops.update_document(mongo, "events", doc["_id"]["$oid"], {"n": 2}, None)

    info = source_ops.connection_info(sql)
    assert info["password"] and info["database"] == sql.database_name

    # Export streamed from the device, restored on the device into a second database.
    buf = io.StringIO()
    counts = transfer._write_device_data(buf, sql)
    data = json.loads(buf.getvalue())
    assert counts["rows"] == 2 and data["tables"][0]["name"] == "users"
    copy = provisioning.provision_managed_source(db, project, "sql", "copy", device_id=device.id)
    db.commit()
    assert transfer.restore_data(copy, data) == (2, 0)
    assert source_ops.list_rows(copy, "users", limit=10, offset=0, order_by=None, order="asc")["total"] == 2

    # Device refuses databases it does not host.
    with pytest.raises(ApiError) as exc:
        device_rpc.call(device.id, "datasource.call", {"kind": "sql", "database_name": "mysql", "op": "introspect"})
    assert exc.value.code in ("not_hosted", "validation_error")

    for ds in (sql, mongo, copy):
        provisioning.drop_managed_source(db, ds)
    assert device_host.get_credentials() == {}
    assert not provisioning.mariadb_database_exists(sql.database_name)
