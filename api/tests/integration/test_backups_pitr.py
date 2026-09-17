"""Point-in-time recovery against real MariaDB 11 (ROW binlog) and MongoDB 5.0 (replica set) servers.

Needs the dump tools (`mariadb-dump`, `mariadb-binlog`, `mariadb`, `mongodump`, `mongorestore`), so it
normally runs inside the API image on the compose `backend` network, e.g.::

    DEPLOYER_IT_MARIADB_URL=mysql://root:<password>@mariadb:3306
    DEPLOYER_IT_MONGO_URI=mongodb://admin:<password>@mongodb:27017
    python -m pytest -p no:cacheprovider tests/integration/test_backups_pitr.py

MariaDB must run with `--log-bin --binlog-format=ROW --server-id=1`; MongoDB as replica set `rs0`
(see deploy/docker-compose.yml). Skipped unless both URLs are set and the tools are on PATH.

Each scenario writes rows before a snapshot, after it, then notes a timestamp T and changes/deletes
rows afterwards, and asserts the exact data of: a version restored as a new source, a point-in-time
restore to T as a new source, and a point-in-time restore to T in place.
"""

import os
import shutil
import time
from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.models import Backup, BackupLogSegment, DataSource, Job, utcnow
from app.services import backup_engine, backups, connections, jobs, provisioning

MARIADB_URL = os.environ.get("DEPLOYER_IT_MARIADB_URL")
MONGO_URI = os.environ.get("DEPLOYER_IT_MONGO_URI")
TOOLS = ("mariadb-dump", "mariadb-binlog", "mariadb", "mongodump", "mongorestore")

pytestmark = pytest.mark.skipif(
    not (MARIADB_URL and MONGO_URI and all(shutil.which(t) for t in TOOLS)),
    reason="set DEPLOYER_IT_MARIADB_URL / DEPLOYER_IT_MONGO_URI and install the backup tools",
)


@pytest.fixture
def servers(monkeypatch, tmp_path):
    settings = get_settings()
    m, g = urlsplit(MARIADB_URL), urlsplit(MONGO_URI)
    monkeypatch.setattr(settings, "mariadb_host", m.hostname)
    monkeypatch.setattr(settings, "mariadb_port", m.port or 3306)
    monkeypatch.setattr(settings, "mariadb_root_password", unquote(m.password or ""))
    monkeypatch.setattr(settings, "mongo_host", g.hostname)
    monkeypatch.setattr(settings, "mongo_port", g.port or 27017)
    monkeypatch.setattr(settings, "mongo_root_username", unquote(g.username or ""))
    monkeypatch.setattr(settings, "mongo_root_password", unquote(g.password or ""))
    monkeypatch.setattr(settings, "managed_mongodb_enabled", True)
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    provisioning.mariadb_root_engine.cache_clear()
    provisioning.mongo_root_client.cache_clear()
    assert backup_engine.ensure_mongo_replica_set() in ("ok", "initiated")
    for _ in range(30):  # a freshly initiated set needs a moment to elect itself primary
        if provisioning.mongo_root_client().admin.command("hello").get("isWritablePrimary"):
            break
        time.sleep(1)
    yield
    session = jobs.get_sessionmaker()()
    try:
        for ds in session.scalars(select(DataSource).where(DataSource.mode == "managed")):
            try:
                provisioning.drop_managed_source(session, ds)
            except Exception:  # noqa: BLE001
                pass
    finally:
        session.close()
    connections.dispose_all()
    provisioning.mariadb_root_engine.cache_clear()
    provisioning.mongo_root_client.cache_clear()


def _run_all() -> None:
    for job_id, status in jobs.run_queued():
        if status != "succeeded":
            session = jobs.get_sessionmaker()()
            try:
                job = session.get(Job, job_id)
                pytest.fail(f"job {job.type} {status}: {job.error}")
            finally:
                session.close()


def _source(db, source_id) -> DataSource:
    db.expire_all()
    return db.get(DataSource, source_id)


def _snapshot(db, ds) -> Backup:
    job, backup = backups.start_snapshot(db, ds, trigger="manual")
    db.commit()
    _run_all()
    db.expire_all()
    backup = db.get(Backup, backup.id)
    assert backup.status == "succeeded", backup.error
    return backup


def _restore(db, ds, user_id, **kwargs) -> dict:
    job = backups.start_restore(
        db,
        ds,
        user_id=user_id,
        role_is_owner=True,
        mode=kwargs.get("mode", "new_source"),
        backup_id=kwargs.get("backup_id"),
        point_in_time=kwargs.get("point_in_time"),
        new_name=kwargs.get("new_name"),
        device_id=None,
        device_id_set=False,
    )
    db.commit()
    _run_all()
    db.expire_all()
    return db.get(Job, job.id).result


def _pause() -> None:
    time.sleep(2.2)  # binlog / oplog times have one-second resolution


def _t_between():
    _pause()
    t = utcnow().replace(microsecond=0)
    _pause()
    return t


def _iso(dt) -> str:
    return dt.isoformat() + "Z"


def test_mariadb_pitr(servers, db, make_user, make_project):
    owner = make_user()
    project = make_project(owner, "PITR SQL")
    ds = provisioning.provision_managed_source(db, project, "sql", "main-sql")
    db.commit()

    def rows(source) -> list:
        with connections.get_sql_engine(source).connect() as conn:
            return [tuple(r) for r in conn.execute(text("SELECT id, name FROM items ORDER BY id"))]

    engine = connections.get_sql_engine(ds)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE parent (id INT PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE items (id INT PRIMARY KEY, name VARCHAR(40), parent_id INT, "
                "FOREIGN KEY (parent_id) REFERENCES parent(id))"
            )
        )
        conn.execute(text("INSERT INTO parent VALUES (1)"))
        conn.execute(text("INSERT INTO items VALUES (1, 'one', 1), (2, 'it''s (two)', NULL)"))

    snap = _snapshot(db, ds)
    assert snap.row_counts == {"parent": 1, "items": 2}
    assert snap.consistent_point["binlog_file"] and snap.consistent_point["binlog_pos"]

    _pause()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO items VALUES (3, 'three', 1)"))
        conn.execute(text("UPDATE items SET name = 'TWO' WHERE id = 2"))
        conn.execute(text(f"CREATE TABLE `{ds.database_name}`.later (x INT)"))  # qualified DDL
        conn.execute(text("INSERT INTO later VALUES (42)"))
    t = _t_between()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO items VALUES (4, 'four', NULL)"))
        conn.execute(text("DELETE FROM items WHERE id = 1"))
        conn.execute(text("DROP TABLE later"))
    _pause()
    expected_at_t = [(1, "one"), (2, "TWO"), (3, "three")]
    assert rows(ds) == [(2, "TWO"), (3, "three"), (4, "four")]

    result = backups.archive_source_logs(jobs.get_sessionmaker(), ds.id)
    assert result.get("segments_created", 0) >= 1, result
    ds = _source(db, ds.id)
    segs = db.scalars(select(BackupLogSegment).where(BackupLogSegment.data_source_id == ds.id)).all()
    assert any(s.size_bytes for s in segs)
    window = backups.recovery_window(db, ds)
    assert backups.parse_time(window["earliest"]) <= t <= backups.parse_time(window["latest"]), window

    # (a) version as a new source
    res = _restore(db, ds, owner.id, backup_id=snap.id, new_name="sql-version")
    version_ds = _source(db, res["data_source_id"])
    assert rows(version_ds) == [(1, "one"), (2, "it's (two)")]

    # (b) point in time as a new source
    ds = _source(db, ds.id)
    res = _restore(db, ds, owner.id, point_in_time=_iso(t), new_name="sql-pitr")
    pitr_ds = _source(db, res["data_source_id"])
    assert rows(pitr_ds) == expected_at_t
    with connections.get_sql_engine(pitr_ds).connect() as conn:
        assert conn.execute(text("SELECT x FROM later")).scalar() == 42
    assert rows(_source(db, ds.id)) == [(2, "TWO"), (3, "three"), (4, "four")]  # source untouched

    # (c) point in time in place (safety snapshot first; the managed user keeps working)
    ds = _source(db, ds.id)
    res = _restore(db, ds, owner.id, point_in_time=_iso(t), mode="in_place")
    assert res["safety_backup_id"]
    connections.invalidate(ds.id)
    ds = _source(db, ds.id)
    assert rows(ds) == expected_at_t
    with connections.get_sql_engine(ds).begin() as conn:  # FK still enforced after the swap
        conn.execute(text("INSERT INTO items VALUES (5, 'five', 1)"))
    safety = db.get(Backup, res["safety_backup_id"])
    assert safety.trigger == "pre_restore" and safety.row_counts["items"] == 3

    # verification restores into a temporary database and compares exact counts
    assert backups.perform_verify(jobs.get_sessionmaker(), snap.id)["ok"] is True
    with provisioning.mariadb_root_engine().connect() as conn:
        leftovers = conn.execute(
            text(
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME LIKE 'rtmp\\_%' "
                "OR SCHEMA_NAME LIKE 'verify\\_%' OR SCHEMA_NAME LIKE 'rtrash\\_%'"
            )
        ).all()
    assert leftovers == []


def test_mongodb_pitr(servers, db, make_user, make_project):
    owner = make_user()
    project = make_project(owner, "PITR Mongo")
    ds = provisioning.provision_managed_source(db, project, "nosql", "main-nosql")
    db.commit()

    def docs(source, coll="items") -> list:
        return [(d["_id"], d.get("name")) for d in connections.get_mongo_db(source)[coll].find().sort("_id", 1)]

    mdb = connections.get_mongo_db(ds)
    mdb.create_collection("items", validator={"$jsonSchema": {"bsonType": "object", "required": ["name"]}})
    mdb.items.create_index("name", unique=True)
    mdb.items.insert_many([{"_id": 1, "name": "one"}, {"_id": 2, "name": "two"}])

    snap = _snapshot(db, ds)
    assert snap.row_counts == {"items": 2}
    assert snap.consistent_point["oplog_ts_start"] and snap.consistent_point["oplog_ts_end"]

    _pause()
    mdb.items.insert_one({"_id": 3, "name": "three"})
    mdb.items.update_one({"_id": 2}, {"$set": {"name": "TWO"}})
    mdb.later.insert_one({"_id": "L", "name": "later"})
    t = _t_between()
    mdb.items.insert_one({"_id": 4, "name": "four"})
    mdb.items.delete_one({"_id": 1})
    mdb.later.drop()
    _pause()
    expected_at_t = [(1, "one"), (2, "TWO"), (3, "three")]

    result = backups.archive_source_logs(jobs.get_sessionmaker(), ds.id)
    assert result.get("segments_created", 0) >= 1, result
    ds = _source(db, ds.id)
    window = backups.recovery_window(db, ds)
    assert backups.parse_time(window["earliest"]) <= t <= backups.parse_time(window["latest"]), window

    res = _restore(db, ds, owner.id, backup_id=snap.id, new_name="mongo-version")
    version_ds = _source(db, res["data_source_id"])
    assert docs(version_ds) == [(1, "one"), (2, "two")]

    ds = _source(db, ds.id)
    res = _restore(db, ds, owner.id, point_in_time=_iso(t), new_name="mongo-pitr")
    pitr_ds = _source(db, res["data_source_id"])
    assert docs(pitr_ds) == expected_at_t
    assert docs(pitr_ds, "later") == [("L", "later")]
    indexes = connections.get_mongo_db(pitr_ds).items.index_information()
    assert indexes["name_1"]["unique"] is True
    assert docs(_source(db, ds.id)) == [(2, "TWO"), (3, "three"), (4, "four")]

    ds = _source(db, ds.id)
    res = _restore(db, ds, owner.id, point_in_time=_iso(t), mode="in_place")
    assert res["safety_backup_id"]
    connections.invalidate(ds.id)
    ds = _source(db, ds.id)
    assert docs(ds) == expected_at_t
    live = connections.get_mongo_db(ds)
    live.items.insert_one({"_id": 5, "name": "five"})  # the managed user can still write
    options = live.command("listCollections", filter={"name": "items"})["cursor"]["firstBatch"][0]["options"]
    assert options["validator"]["$jsonSchema"]["required"] == ["name"]

    assert backups.perform_verify(jobs.get_sessionmaker(), snap.id)["ok"] is True
    names = provisioning.mongo_root_client().list_database_names()
    assert not [n for n in names if n.startswith(("rtmp_", "verify_"))]
