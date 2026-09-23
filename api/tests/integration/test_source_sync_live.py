"""Co-hosting sync against real MariaDB 11 (row binlog, GTID) and MongoDB 5.0 (replica set rs0).

Skipped unless both servers are configured (see test_managed_databases.py for docker commands; the
MariaDB container needs `--log-bin --binlog-format=ROW --server-id=1`, MongoDB `--replSet rs0`)::

    DEPLOYER_IT_MARIADB_URL=mysql://root:<password>@127.0.0.1:13306 \
    DEPLOYER_IT_MONGO_URI=mongodb://admin:<password>@127.0.0.1:37017 pytest tests/integration/test_source_sync_live.py

One server plays both copies: database `it_sync_main` is the main server's (applied with the origin
server_id, read skipping it) and `it_sync_copy` the device's (applied with sql_log_bin = 0), exactly
the settings each side uses in production. Warning: sets the server's GLOBAL auto_increment_* and
binlog_row_metadata; use a throwaway server.
"""

import os
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.crypto import encrypt_json
from app.models import DataSource, SourceReplica, SyncConflict
from app.services import device_rpc, provisioning, source_sync
from tests import devices_support

make_device = devices_support.make_device  # shared fixture

MARIADB_URL = os.environ.get("DEPLOYER_IT_MARIADB_URL")
MONGO_URI = os.environ.get("DEPLOYER_IT_MONGO_URI")

pytestmark = pytest.mark.skipif(
    not (MARIADB_URL and MONGO_URI), reason="set DEPLOYER_IT_MARIADB_URL and DEPLOYER_IT_MONGO_URI"
)

MAIN, COPY = "it_sync_main", "it_sync_copy"


class CopySide:
    """The device's side, run in-process with the device's settings."""

    def __init__(self, kind):
        self.kind = kind

    def changes(self, since, limit):
        if self.kind == "sql":
            return source_sync.read_sql_changes(COPY, since, limit)
        return source_sync.read_mongo_changes(COPY, since, limit)

    def apply(self, changes):
        return source_sync.apply_local(self.kind, COPY, changes, log_bin=False)


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
    with provisioning.mariadb_root_engine().connect() as conn:
        for name in (MAIN, COPY):
            conn.exec_driver_sql(f"DROP DATABASE IF EXISTS `{name}`")
    for name in (MAIN, COPY):
        provisioning.mongo_root_client().drop_database(name)


@pytest.fixture
def replica(db, owner, make_project, make_device, monkeypatch, servers):
    def build(kind):
        project = make_project(owner, f"Live {kind}")
        device, _ = make_device(owner)
        ds = DataSource(
            project_id=project.id,
            name="main",
            kind=kind,
            engine="mariadb" if kind == "sql" else "mongodb",
            mode="managed",
            database_name=MAIN,
            config_encrypted=encrypt_json({}),
            status="ok",
        )
        db.add(ds)
        db.flush()
        rep = SourceReplica(
            data_source_id=ds.id,
            device_id=device.id,
            status="syncing",
            position_primary=source_sync.local_position(kind, MAIN),
            position_replica=source_sync.local_position(kind, COPY),
            id_offset=2,
        )
        db.add(rep)
        db.commit()
        primary = source_sync.PrimarySide(kind, MAIN, source_sync.origin_server_id(2))
        monkeypatch.setattr(source_sync, "sides_for", lambda r, d: (primary, CopySide(kind)))
        device_rpc.mark_online(device.id, "conn")
        return rep

    return build


def _sql(database, statement, args=None):
    with provisioning.mariadb_root_engine().connect() as conn:
        result = conn.exec_driver_sql(statement.replace("{db}", f"`{database}`"), args or ())
        return result.fetchall() if result.returns_rows else None


def test_mariadb_two_way_sync(db, replica):
    source_sync.ensure_mariadb_settings(offset=source_sync.PRIMARY_ID_OFFSET)
    for name in (MAIN, COPY):
        _sql(name, "CREATE DATABASE IF NOT EXISTS {db}")
        _sql(name, "CREATE TABLE {db}.users (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(50), n DECIMAL(6,2))")
        _sql(name, "CREATE TABLE {db}.logs (line TEXT)")
    rep = replica("sql")

    _sql(MAIN, "INSERT INTO {db}.users (name, n) VALUES ('ana', 1.50)")
    _sql(COPY, "INSERT INTO {db}.users (id, name, n) VALUES (2, 'bo', 2.00)")
    _sql(MAIN, "INSERT INTO {db}.logs VALUES ('not synced')")
    assert source_sync.sync_round(rep.id) == {"applied": 2, "conflicts": 0}
    for name in (MAIN, COPY):
        assert [tuple(r[:2]) for r in _sql(name, "SELECT id, name FROM {db}.users ORDER BY id")] == [
            (1, "ana"),
            (2, "bo"),
        ]
    assert _sql(COPY, "SELECT COUNT(*) FROM {db}.logs")[0][0] == 0
    # No echo.
    assert source_sync.sync_round(rep.id) == {"applied": 0, "conflicts": 0}
    db.expire_all()
    assert [w["table"] for w in db.get(SourceReplica, rep.id).warnings] == ["logs"]

    # Same row on both sides -> an open conflict, the rest keeps syncing.
    _sql(MAIN, "UPDATE {db}.users SET name = 'ANA' WHERE id = 1")
    _sql(COPY, "UPDATE {db}.users SET name = 'Ana B' WHERE id = 1")
    _sql(COPY, "UPDATE {db}.users SET name = 'BO' WHERE id = 2")
    assert source_sync.sync_round(rep.id) == {"applied": 1, "conflicts": 1}
    assert _sql(MAIN, "SELECT name FROM {db}.users WHERE id = 1")[0][0] == "ANA"
    assert _sql(COPY, "SELECT name FROM {db}.users WHERE id = 1")[0][0] == "Ana B"
    assert _sql(MAIN, "SELECT name FROM {db}.users WHERE id = 2")[0][0] == "BO"
    db.expire_all()
    (conflict,) = db.scalars(select(SyncConflict))
    assert conflict.base_json["name"] == "ana" and conflict.primary_json["name"] == "ANA"


def test_mongodb_two_way_sync(db, replica):
    client = provisioning.mongo_root_client()
    for name in (MAIN, COPY):
        client[name].create_collection("orders")
    rep = replica("nosql")
    client[MAIN].orders.insert_one({"_id": 1, "total": 5})
    client[COPY].orders.insert_one({"_id": 2, "total": 7})
    assert source_sync.sync_round(rep.id) == {"applied": 2, "conflicts": 0}
    for name in (MAIN, COPY):
        assert sorted(d["_id"] for d in client[name].orders.find()) == [1, 2]
    # The applied writes come back through the change streams and are recognised as echoes.
    assert source_sync.sync_round(rep.id) == {"applied": 0, "conflicts": 0}
    client[COPY].orders.update_one({"_id": 1}, {"$set": {"total": 6}})
    source_sync.sync_round(rep.id)
    assert client[MAIN].orders.find_one({"_id": 1})["total"] == 6
