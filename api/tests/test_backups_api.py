"""Backup API and orchestration against a fake executor (no database servers or dump tools needed).

The fake executor writes real encrypted artifacts into a temporary BACKUP_DIR so downloads, deletion
and verification paths are exercised end to end; restores only record their arguments.
"""

import gzip
import io
import secrets
from datetime import datetime, timedelta

import pytest

from app.errors import ApiError
from app.models import AuditLog, Backup, BackupCopy, BackupLogSegment, BackupPolicy, DataSource, Job, SchemaLink, utcnow
from app.services import audit, backup_engine, backups, executors, jobs, provisioning


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


class FakeExecutor(executors.LocalExecutor):
    def __init__(self, root):
        super().__init__(root)
        self.calls = []
        self.binlog_seq = 1
        self.row_counts = {"users": 2}
        self.archive_result = []
        self.fail_snapshot = False

    def snapshot(self, *, kind, engine, database_name, artifact_ref, on_progress=None):
        if self.fail_snapshot:
            raise RuntimeError("dump failed")
        self.calls.append(("snapshot", database_name))
        writer = backup_engine.ArtifactWriter(self.artifact_path(artifact_ref))
        writer.write(f"-- dump of {database_name}\nINSERT INTO `users` VALUES (1),(2);\n".encode())
        info = writer.commit()
        point = {
            "binlog_file": f"mysql-bin.{self.binlog_seq:06d}",
            "binlog_pos": 4,
            "gtid": "0-1-1",
            "consistent_at": _iso(utcnow()),
        }
        return {**info, "consistent_point": point, "row_counts": dict(self.row_counts)}

    def archive_logs(self, **kwargs):
        self.calls.append(("archive_logs", kwargs["since_point"]))
        return self.archive_result

    def restore(self, **kwargs):
        self.calls.append(("restore", kwargs))
        return {
            "row_counts": {"users": 1},
            "swap": "rename",
            "resume_point": {"binlog_file": "mysql-bin.000009", "binlog_pos": 400},
        }

    def verify(self, **kwargs):
        self.calls.append(("verify", kwargs))
        return {
            "ok": kwargs["expected_row_counts"] == self.row_counts,
            "row_counts": self.row_counts,
            "mismatches": [],
            "message": "checked",
        }

    def ensure_database(self, *, kind, database_name):
        self.calls.append(("ensure_database", database_name))
        return {
            "host": "mariadb",
            "port": 3306,
            "username": "u_" + secrets.token_hex(6),
            "password": secrets.token_hex(16),
            "database": database_name,
            "tls": False,
        }

    def platform_snapshot(self, *, artifact_ref, on_progress=None):
        return self.snapshot(kind="sql", engine="mariadb", database_name="deployer", artifact_ref=artifact_ref)


SCHEMA_V1 = {
    "source_id": "x",
    "name": "main-sql",
    "kind": "sql",
    "engine": "mariadb",
    "status": "ok",
    "error": None,
    "relationships": [],
    "entities": [
        {
            "name": "users",
            "type": "table",
            "row_count": 99,
            "validator": None,
            "indexes": [],
            "fields": [
                {
                    "name": "id",
                    "data_type": "int(11)",
                    "nullable": False,
                    "default": None,
                    "primary_key": True,
                    "unique": False,
                    "indexed": True,
                    "foreign_key": None,
                    "occurrence": None,
                }
            ],
        }
    ],
}


@pytest.fixture
def env(tmp_path, monkeypatch, db, make_user, make_project, auth_headers, make_source):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    fake = FakeExecutor(tmp_path / "backups")
    monkeypatch.setattr(executors, "executor_for", lambda _host: fake)
    monkeypatch.setattr(executors, "local_executor", lambda: fake)
    state = {"schema": SCHEMA_V1}
    monkeypatch.setattr(backups, "_schema_snapshot", lambda ds: state["schema"])
    from app.services import introspection

    monkeypatch.setattr(introspection, "introspect_source", lambda ds, sample=200: state["schema"])
    dropped, created = [], []
    monkeypatch.setattr(provisioning, "drop_managed_source", lambda db, ds: dropped.append(ds.database_name))
    monkeypatch.setattr(
        provisioning, "create_mariadb_database", lambda name, user, pw: created.append((name, user)) or {}
    )

    owner, admin, dev, viewer = (make_user() for _ in range(4))
    project = make_project(owner, "Shop", members={admin: "admin", dev: "developer", viewer: "viewer"})
    config = {
        "host": "mariadb",
        "port": 3306,
        "username": "u_0123456789ab",
        "password": secrets.token_hex(16),
        "database": "p_shop_abc123",
    }
    ds = make_source(project, mode="managed", database_name="p_shop_abc123", config=config)
    return {
        "fake": fake,
        "state": state,
        "db": db,
        "ds": ds,
        "project": project,
        "dropped": dropped,
        "created": created,
        "owner": auth_headers(owner),
        "admin": auth_headers(admin),
        "dev": auth_headers(dev),
        "viewer": auth_headers(viewer),
        "base": f"/v1/projects/{project.id}/data-sources/{ds.id}",
        "pbase": f"/v1/projects/{project.id}",
    }


def _snapshot(client, env, label=None, headers="dev"):
    resp = client.post(f"{env['base']}/backups", json={"label": label} if label else {}, headers=env[headers])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job"]["type"] == "backup.snapshot" and body["job"]["status"] == "queued"
    jobs.run_queued()
    return body["backup_id"]


def test_policy_defaults_validation_and_roles(client, env):
    policy = client.get(f"{env['base']}/backup-policy", headers=env["viewer"]).json()
    assert policy["schedule"] == "hourly" and policy["keep_hourly"] == 24 and policy["pitr_window_days"] == 7
    assert policy["copy_to_device_id"] is None and policy["safety_snapshots"] is True
    assert client.put(f"{env['base']}/backup-policy", json={"schedule": "daily"}, headers=env["dev"]).status_code == 403
    resp = client.put(
        f"{env['base']}/backup-policy",
        json={"schedule": "daily", "keep_daily": 14, "pitr_window_days": 3},
        headers=env["admin"],
    )
    assert resp.status_code == 200 and resp.json()["schedule"] == "daily" and resp.json()["keep_daily"] == 14
    for bad in ({"pitr_window_days": 36}, {"schedule": "weekly"}, {"copy_to_device_id": "nope"}, {"keep_hourly": -1}):
        assert client.put(f"{env['base']}/backup-policy", json=bad, headers=env["admin"]).status_code == 422


def test_external_sources_have_no_backups(client, env, make_source):
    ext = make_source(env["project"], "nosql", name="atlas", config={})
    resp = client.get(f"{env['pbase']}/data-sources/{ext.id}/backup-policy", headers=env["viewer"])
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "backups_not_available"


def test_snapshot_lifecycle_label_download_delete(client, env, db, tmp_path):
    backup_id = _snapshot(client, env, label="before launch")
    listed = client.get(f"{env['base']}/backups", headers=env["viewer"]).json()
    assert len(listed) == 1
    b = listed[0]
    assert b["id"] == backup_id and b["status"] == "succeeded" and b["trigger"] == "manual"
    assert b["label"] == "before launch" and b["pinned"] is True and b["row_counts"] == {"users": 2}
    assert b["copies"] == [{"location": "local", "device_id": None, "status": "ok"}] and b["size_bytes"] > 0
    row = db.get(Backup, backup_id)
    assert row.consistent_point["binlog_file"] == "mysql-bin.000001" and row.schema_snapshot == SCHEMA_V1
    path = tmp_path / "backups" / env["ds"].id / "snapshots" / f"{backup_id}.bin"
    assert path.is_file() and b"INSERT" not in path.read_bytes()

    # Download: owner only, decrypted (still gzip-compressed) content.
    url = f"{env['base']}/backups/{backup_id}/download"
    assert client.get(url, headers=env["admin"]).status_code == 403
    resp = client.get(url, headers=env["owner"])
    assert resp.status_code == 200 and resp.headers["content-disposition"].endswith('.sql.gz"')
    assert gzip.GzipFile(fileobj=io.BytesIO(resp.content)).read().startswith(b"-- dump of p_shop_abc123")

    # Pinned versions can't be deleted; unpinning allows it (admin+), and the file goes too.
    assert client.delete(f"{env['base']}/backups/{backup_id}", headers=env["admin"]).json()["error"]["code"] == (
        "backup_pinned"
    )
    resp = client.patch(f"{env['base']}/backups/{backup_id}", json={"pinned": False}, headers=env["dev"])
    assert resp.json()["pinned"] is False and resp.json()["label"] == "before launch"
    assert client.delete(f"{env['base']}/backups/{backup_id}", headers=env["dev"]).status_code == 403
    assert client.delete(f"{env['base']}/backups/{backup_id}", headers=env["admin"]).json() == {"ok": True}
    assert not path.exists()
    db.expire_all()
    assert db.query(BackupCopy).count() == 0


def test_list_reports_the_servers_retention_reason(client, env, db):
    """kept_as is gfs_keep's reason, and exactly the versions without one are pruned (A-084)."""
    ds = env["ds"]
    client.put(
        f"{env['base']}/backup-policy",
        json={"keep_hourly": 0, "keep_daily": 1, "keep_weekly": 0, "keep_monthly": 0},
        headers=env["admin"],
    )
    now = utcnow()

    def add(key, age, trigger="scheduled", **kw):
        b = Backup(
            data_source_id=ds.id,
            scope="source",
            engine="mariadb",
            trigger=trigger,
            status="succeeded",
            started_at=now - age,
            **kw,
        )
        db.add(b)
        db.flush()
        return key, b.id

    ids = dict(
        [
            # A safety snapshot never takes a GFS bucket, so the older scheduled one keeps "daily".
            add("safety", timedelta(minutes=5), trigger="pre_drop"),
            add("today", timedelta(minutes=10)),
            add("today_older", timedelta(minutes=20)),
            add("old", timedelta(days=3)),
            add("pinned", timedelta(days=4), pinned=True),
        ]
    )
    db.commit()
    listed = {b["id"]: b["kept_as"] for b in client.get(f"{env['base']}/backups", headers=env["viewer"]).json()}
    assert {k: listed[v] for k, v in ids.items()} == {
        "safety": "safety",
        "today": "daily",
        "today_older": None,
        "old": None,
        "pinned": "pinned",
    }
    backups.prune_source(db, ds, utcnow())
    db.commit()
    assert {b.id for b in db.query(Backup).all()} == {v for v in ids.values() if listed[v]}


def test_list_without_policy_row_uses_the_default_policy(client, env, db):
    """No policy row yet: the prune job would use the default policy, so kept_as must too (A-084)."""
    ds = env["ds"]
    db.query(BackupPolicy).delete()
    now = utcnow()
    safety = Backup(data_source_id=ds.id, scope="source", engine="mariadb", trigger="pre_move", status="succeeded")
    newest = Backup(data_source_id=ds.id, scope="source", engine="mariadb", trigger="manual", status="succeeded")
    safety.started_at, newest.started_at = now - timedelta(minutes=5), now - timedelta(minutes=10)
    db.add_all([safety, newest])
    db.commit()
    listed = {b["id"]: b["kept_as"] for b in client.get(f"{env['base']}/backups", headers=env["viewer"]).json()}
    assert listed == {safety.id: "safety", newest.id: "hourly"}
    assert db.query(BackupPolicy).count() == 0


def test_failed_snapshot_is_recorded(client, env, db):
    env["fake"].fail_snapshot = True
    backup_id = _snapshot(client, env)
    db.expire_all()
    backup = db.get(Backup, backup_id)
    assert backup.status == "failed" and "dump failed" in backup.error
    assert db.get(Job, backup.job_id).status == "failed"


def test_schema_and_diff(client, env):
    first = _snapshot(client, env)
    v2 = {
        **SCHEMA_V1,
        "entities": [
            {
                **SCHEMA_V1["entities"][0],
                "fields": SCHEMA_V1["entities"][0]["fields"]
                + [
                    {
                        "name": "email",
                        "data_type": "varchar(255)",
                        "nullable": True,
                        "default": None,
                        "primary_key": False,
                        "unique": False,
                        "indexed": False,
                        "foreign_key": None,
                        "occurrence": None,
                    }
                ],
            },
            {"name": "orders", "type": "table", "row_count": 0, "fields": [], "indexes": [], "validator": None},
        ],
    }
    env["state"]["schema"] = v2
    env["fake"].row_counts = {"users": 5, "orders": 0}
    second = _snapshot(client, env)

    schema = client.get(f"{env['base']}/backups/{first}/schema", headers=env["viewer"]).json()
    assert schema["entities"][0]["row_count"] == 2  # exact count from the snapshot, not the estimate
    diff = client.get(f"{env['base']}/backups/diff", params={"from": first, "to": second}, headers=env["viewer"]).json()
    assert diff["from"]["backup_id"] == first and diff["to"]["backup_id"] == second
    by_name = {e["name"]: e for e in diff["entities"]}
    assert by_name["orders"]["change"] == "added"
    assert [f["name"] for f in by_name["users"]["fields"]] == ["email"]
    assert by_name["users"]["row_count"] == {"before": 2, "after": 5}
    current = client.get(f"{env['base']}/backups/diff", params={"from": second}, headers=env["viewer"]).json()
    assert current["to"]["backup_id"] is None
    # Same structure: the live (estimated) row count of users differs from the exact snapshot count,
    # but estimates are not compared, so nothing shows as changed.
    assert current["entities"] == []
    back = client.get(f"{env['base']}/backups/diff", params={"from": first}, headers=env["viewer"]).json()
    assert {e["name"]: e["row_count"] for e in back["entities"]} == {
        "orders": {"before": None, "after": None},
        "users": {"before": None, "after": None},
    }
    # Live database unreachable: an error, not "every table removed".
    env["state"]["schema"] = {**v2, "status": "error", "error": "connection refused", "entities": []}
    resp = client.get(f"{env['base']}/backups/diff", params={"from": second}, headers=env["viewer"])
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "source_unavailable"


def _segment(db, ds, seq, start_at, end_at, *, data=True, env=None):
    seg = BackupLogSegment(
        data_source_id=ds.id,
        kind="binlog",
        start_at=start_at,
        end_at=end_at,
        start_point={"binlog_file": f"mysql-bin.{seq:06d}"},
        end_point={"binlog_file": f"mysql-bin.{seq:06d}"},
        size_bytes=10 if data else 0,
    )
    db.add(seg)
    db.flush()
    if data:
        db.add(
            BackupCopy(
                artifact_type="segment",
                artifact_id=seg.id,
                location="local",
                device_id=None,
                ref=f"{ds.id}/logs/{seg.id}.bin",
                size_bytes=10,
                status="ok",
            )
        )
    db.commit()
    return seg


def test_recovery_window_pitr_restore_new_source(client, env, db):
    ds = env["ds"]
    backup_id = _snapshot(client, env)
    t0 = backups.consistent_at(db.get(Backup, backup_id))
    s1 = _segment(db, ds, 1, t0, t0 + timedelta(minutes=5))
    _segment(db, ds, 2, t0 + timedelta(minutes=5), t0 + timedelta(minutes=10), data=False)
    s3 = _segment(db, ds, 3, t0 + timedelta(minutes=10), t0 + timedelta(minutes=15))
    _segment(db, ds, 5, t0 + timedelta(minutes=20), t0 + timedelta(minutes=25))  # gap: file 4 missing

    window = client.get(f"{env['base']}/recovery-window", headers=env["viewer"]).json()
    assert window == {
        "pitr_enabled": True,
        "earliest": _iso(t0),
        "latest": _iso(t0 + timedelta(minutes=15)),
        "snapshots": 1,
    }
    target = t0 + timedelta(minutes=12)
    resp = client.post(
        f"{env['base']}/restore", json={"point_in_time": _iso(t0 + timedelta(minutes=20))}, headers=env["admin"]
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "outside_recovery_window"
    assert (
        client.post(f"{env['base']}/restore", json={"point_in_time": _iso(target)}, headers=env["dev"]).status_code
        == 403
    )
    resp = client.post(
        f"{env['base']}/restore", json={"point_in_time": _iso(target), "new_name": "recovered"}, headers=env["admin"]
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job"]["id"]
    results = dict(jobs.run_queued())
    assert results[job_id] == "succeeded", db.get(Job, job_id).error

    kind, restore = [c for c in env["fake"].calls if c[0] == "restore"][0]
    assert restore["source_database_name"] == "p_shop_abc123" and restore["until"] == target.replace(microsecond=0)
    assert [s["id"] for s in restore["segments"]] == [s1.id, pytest.approx(restore["segments"][1]["id"]), s3.id]
    assert [bool(s["ref"]) for s in restore["segments"]] == [True, False, True]
    assert restore["consistent_point"]["binlog_pos"] == 4
    db.expire_all()
    new = db.query(DataSource).filter_by(name="recovered").one()
    assert new.status == "ok" and new.device_id is None and restore["target_database_name"] == new.database_name
    assert db.get(BackupPolicy, new.id) is not None
    assert db.get(Job, job_id).result["data_source_id"] == new.id
    # A first snapshot of the restored source ran right after.
    assert db.query(Backup).filter_by(data_source_id=new.id, status="succeeded").count() == 1


def test_restore_version_in_place_takes_safety_snapshot(client, env, db):
    backup_id = _snapshot(client, env)
    body = {"backup_id": backup_id, "mode": "in_place"}
    assert client.post(f"{env['base']}/restore", json=body, headers=env["admin"]).status_code == 403
    resp = client.post(f"{env['base']}/restore", json=body, headers=env["owner"])
    assert resp.status_code == 200, resp.text
    jobs.run_queued()
    db.expire_all()
    job = db.get(Job, resp.json()["job"]["id"])
    assert job.status == "succeeded", job.error
    safety = db.get(Backup, job.result["safety_backup_id"])
    assert safety.trigger == "pre_restore" and safety.status == "succeeded" and safety.expires_at
    restore = [c[1] for c in env["fake"].calls if c[0] == "restore"][0]
    assert restore["target_database_name"] == "p_shop_abc123" and restore["segments"] == []
    assert restore["until"] is None
    gap = db.query(BackupLogSegment).filter_by(data_source_id=env["ds"].id).one()
    assert gap.start_point["gap"] is True and gap.end_point == {"binlog_file": "mysql-bin.000008"}


class _WorkerKilled(BaseException):
    """Stands in for the worker process dying mid-job: nothing after it runs."""


def test_jobs_ended_by_a_dead_worker_or_cancel_leave_nothing_stuck(client, env, db, monkeypatch, fake_redis):
    # A queued snapshot cancelled before it ran: its Backup row must not stay "running".
    resp = client.post(f"{env['base']}/backups", json={}, headers=env["dev"])
    backup_id, job_id = resp.json()["backup_id"], resp.json()["job"]["id"]
    client.post(f"{env['pbase']}/jobs/{job_id}/cancel", headers=env["admin"])
    # A new-source restore killed mid-restore: recover_stale fails the job; the half-made source stays.
    source_backup = _snapshot(client, env)
    resp = client.post(
        f"{env['base']}/restore", json={"backup_id": source_backup, "new_name": "half"}, headers=env["admin"]
    )
    restore_job = resp.json()["job"]["id"]

    def killed(**kwargs):
        raise _WorkerKilled

    monkeypatch.setattr(env["fake"], "restore", killed)
    monkeypatch.setattr(backups, "_discard_new_source", lambda factory, ds_id: None)  # dead: no cleanup
    with pytest.raises(_WorkerKilled):
        jobs.run_job(restore_job)
    monkeypatch.undo()
    monkeypatch.setattr(executors, "executor_for", lambda _host: env["fake"])
    monkeypatch.setattr(provisioning, "drop_managed_source", lambda db, ds: env["dropped"].append(ds.database_name))
    half = db.query(DataSource).filter_by(name="half").one()
    half_id, half_db = half.id, half.database_name
    job = db.get(Job, restore_job)
    job.started_at = utcnow() - timedelta(minutes=10)
    db.commit()
    fake_redis.delete(jobs.heartbeat_key(restore_job))
    assert jobs.recover_stale() == 1

    assert backups.reconcile_interrupted(jobs.get_sessionmaker()) == 2
    db.expire_all()
    cancelled = db.get(Backup, backup_id)
    assert cancelled.status == "failed" and cancelled.finished_at is not None
    assert db.get(DataSource, half_id) is None and half_db in env["dropped"]
    assert db.get(BackupPolicy, half_id) is None and db.get(Job, restore_job).result is None
    assert backups.reconcile_interrupted(jobs.get_sessionmaker()) == 0
    # No longer "running": deletable like any other failed version.
    assert client.delete(f"{env['base']}/backups/{backup_id}", headers=env["admin"]).json() == {"ok": True}


def test_snapshot_killed_mid_run_is_failed_by_recover_stale(client, env, db, monkeypatch, fake_redis):
    # A-126: the PC slept or rebooted while a snapshot ran; its version must not stay "running" forever.
    resp = client.post(f"{env['base']}/backups", json={}, headers=env["dev"])
    backup_id, job_id = resp.json()["backup_id"], resp.json()["job"]["id"]

    def killed(**kwargs):
        raise _WorkerKilled

    monkeypatch.setattr(env["fake"], "snapshot", killed)
    with pytest.raises(_WorkerKilled):
        jobs.run_job(job_id)
    db.expire_all()
    assert db.get(Backup, backup_id).status == "running"
    db.get(Job, job_id).started_at = utcnow() - timedelta(minutes=10)
    db.commit()
    fake_redis.delete(jobs.heartbeat_key(job_id))
    assert jobs.recover_stale() == 1
    assert backups.reconcile_interrupted(jobs.get_sessionmaker()) == 1
    db.expire_all()
    backup = db.get(Backup, backup_id)
    assert backup.status == "failed" and backup.finished_at is not None
    assert backup.error == db.get(Job, job_id).error
    assert client.delete(f"{env['base']}/backups/{backup_id}", headers=env["admin"]).json() == {"ok": True}


def test_sweep_leftovers_removes_stale_partials_and_temp_databases(tmp_path, monkeypatch):
    import os
    import time
    from contextlib import contextmanager

    stale, fresh, done = tmp_path / "a" / "x.bin.partial", tmp_path / "y.bin.partial", tmp_path / "z.bin"
    for path in (stale, fresh, done):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    old = time.time() - 2 * backup_engine.PARTIAL_MAX_AGE_S
    os.utime(stale, (old, old))
    os.utime(done, (old, old))
    sql = []

    class Conn:
        def exec_driver_sql(self, statement, params=None):
            sql.append(statement)
            return [("rtmp_0a1b2c",), ("verify_0a1b2c",), ("rtrash_0a1b2c",), ("p_shop_abc123",), ("mysql",)]

    class Engine:
        @contextmanager
        def connect(self):
            yield Conn()

    class Mongo:
        def __init__(self):
            self.dropped = []

        def list_database_names(self):
            return ["verify_0a1b2c", "p_shop_abc123", "admin"]

        def drop_database(self, name):
            self.dropped.append(name)

    mongo = Mongo()
    monkeypatch.setattr(backup_engine, "_root_engine", Engine)
    monkeypatch.setattr(backup_engine, "_mongo_client", lambda: mongo)
    assert backup_engine.sweep_leftovers(tmp_path) == {"partial_files": 1, "databases": 4}
    assert not stale.exists() and fresh.exists() and done.exists()
    assert [s for s in sql if s.startswith("DROP")] == [
        f"DROP DATABASE IF EXISTS `{n}`" for n in ("rtmp_0a1b2c", "verify_0a1b2c", "rtrash_0a1b2c")
    ]
    assert mongo.dropped == ["verify_0a1b2c"]


def test_archive_logs_creates_and_extends_segments(client, env, db):
    ds = env["ds"]
    _snapshot(client, env)
    now = utcnow().replace(microsecond=0)
    env["fake"].archive_result = [
        {
            "id": None,
            "ref": f"{ds.id}/logs/a.bin",
            "start_at": _iso(now),
            "end_at": _iso(now + timedelta(minutes=1)),
            "start_point": {"binlog_file": "mysql-bin.000001"},
            "end_point": {"binlog_file": "mysql-bin.000001"},
            "size_bytes": 5,
            "sha256": "ab",
        },
        {
            "id": None,
            "ref": None,
            "start_at": _iso(now),
            "end_at": _iso(now + timedelta(minutes=5)),
            "start_point": {"binlog_file": "mysql-bin.000002"},
            "end_point": {"binlog_file": "mysql-bin.000002"},
            "size_bytes": 0,
            "sha256": None,
        },
    ]
    result = backups.archive_source_logs(jobs.get_sessionmaker(), ds.id)
    assert result == {"segments_created": 1, "segments_extended": 1}
    assert env["fake"].calls[-1] == ("archive_logs", {"after": db.query(Backup).one().consistent_point})
    db.expire_all()
    seg = db.query(BackupLogSegment).one()
    assert seg.end_point == {"binlog_file": "mysql-bin.000002"} and seg.end_at == now + timedelta(minutes=5)
    env["fake"].archive_result = []
    backups.archive_source_logs(jobs.get_sessionmaker(), ds.id)
    assert env["fake"].calls[-1] == ("archive_logs", {"binlog_file": "mysql-bin.000002"})


def test_verify_job(client, env, db):
    backup_id = _snapshot(client, env)
    result = backups.perform_verify(jobs.get_sessionmaker(), backup_id)
    assert result["ok"] is True
    env["fake"].row_counts = {"users": 3}
    db.get(Backup, backup_id)
    assert backups.perform_verify(jobs.get_sessionmaker(), backup_id)["ok"] is False
    db.expire_all()
    backup = db.get(Backup, backup_id)
    assert backup.verified_at and backup.verify_status == "failed"
    listed = client.get(f"{env['base']}/backups", headers=env["viewer"]).json()[0]
    assert listed["verify_status"] == "failed"


def test_verify_reports_a_missing_backup_file(client, env, db):
    """A-125: verify checks the file is there before the restore test, and says so in plain words."""
    backup_id = _snapshot(client, env)
    env["fake"].delete_artifact(backups.snapshot_ref(db.get(Backup, backup_id)))
    result = backups.perform_verify(jobs.get_sessionmaker(), backup_id)
    assert result["ok"] is False and "missing" in result["message"]
    assert not [c for c in env["fake"].calls if c[0] == "verify"]


def test_platform_snapshot_records_like_a_source_snapshot(client, env, db, owner_headers, monkeypatch):
    """A-125: every snapshot kind shares _record_snapshot, so a result without a point still stores {} not None."""
    monkeypatch.setattr(
        env["fake"], "platform_snapshot", lambda *, artifact_ref, on_progress=None: {"size_bytes": 5, "sha256": "ab"}
    )
    client.post("/v1/instance/backups/platform", headers=owner_headers)
    jobs.run_queued()
    db.expire_all()
    snap = db.query(Backup).filter_by(scope="platform").one()
    assert snap.status == "succeeded" and snap.error is None and snap.size_bytes == 5
    assert snap.consistent_point == {} and snap.row_counts == {}
    copy = db.query(BackupCopy).filter_by(artifact_id=snap.id).one()
    assert copy.status == "ok" and copy.sha256 == "ab" and copy.device_id is None


def test_failed_verify_alerts_shows_in_health_and_retries_next_day(client, env, db, owner_headers, fake_redis):
    """A-038: a failed verification is not a failed job, so it needs its own alert, health field and retry."""
    from app.services import alerts

    backup_id = _snapshot(client, env)
    env["fake"].row_counts = {"users": 3}
    assert backups.perform_verify(jobs.get_sessionmaker(), backup_id)["ok"] is False
    db.expire_all()
    out: dict = {}
    alerts._backup_rules(db, out)
    assert [c.alert for c in out.values()] == ["backup_verify_failed"]
    [src] = client.get("/v1/instance/backups", headers=owner_headers).json()["sources"]
    assert src["last_verify_status"] == "failed" and src["last_verified_at"]

    factory = jobs.get_sessionmaker()

    def verify_jobs(at):
        return [j for j in backups.scheduler_tick(factory, at) if db.get(Job, j).type == "backup.verify"]

    assert verify_jobs(utcnow() + timedelta(hours=12)) == []
    assert len(verify_jobs(utcnow() + timedelta(days=1, minutes=1))) == 1

    env["fake"].row_counts = {"users": 2}
    assert backups.perform_verify(factory, backup_id)["ok"] is True
    db.expire_all()
    out = {}
    alerts._backup_rules(db, out)
    assert out == {}
    [src] = client.get("/v1/instance/backups", headers=owner_headers).json()["sources"]
    assert src["last_verify_status"] == "ok"


def test_no_successful_backup_for_twice_the_schedule_alerts(client, env, db):
    """A-046: a hung snapshot job fails nothing, so a database whose backups silently stopped needs its own alert."""
    from app.services import alerts

    ds = env["ds"]
    backups.ensure_policy(db, ds)
    db.commit()
    out: dict = {}
    alerts._backup_rules(db, out)
    assert out == {}  # new database, not overdue yet
    ds.created_at = utcnow() - timedelta(hours=3)
    db.commit()
    alerts._backup_rules(db, out)
    cond = out[f"backup_stale:{ds.id}"]
    assert [c.alert for c in out.values()] == ["backup_stale"] and "over 2 hours" in cond.message
    assert cond.for_s == 3600  # a PC waking from a long sleep gets its catch-up snapshot before the alert opens

    backup_id = _snapshot(client, env)
    db.expire_all()
    out = {}
    alerts._backup_rules(db, out)
    assert out == {}
    db.get(Backup, backup_id).started_at = utcnow() - timedelta(hours=3)
    db.commit()
    alerts._backup_rules(db, out)
    assert list(out) == [f"backup_stale:{ds.id}"]


def test_soft_delete_and_restore_deleted_source(client, env, db, make_source):
    ds = env["ds"]
    base = env["pbase"]
    _snapshot(client, env)
    resp = client.delete(f"{base}/data-sources/{ds.id}?drop=true", headers=env["owner"])
    assert resp.status_code == 200 and resp.json()["job"]["type"] == "source.finalize_delete"
    assert client.get(f"{base}/data-sources", headers=env["viewer"]).json() == []
    assert client.get(f"{base}", headers=env["viewer"]).json()["data_source_counts"] == {"sql": 0, "nosql": 0}
    assert client.get(f"{env['base']}/backup-policy", headers=env["viewer"]).status_code == 200
    jobs.run_queued()
    db.expire_all()
    final = db.query(Backup).filter_by(data_source_id=ds.id, trigger="final").one()
    assert final.status == "succeeded" and final.expires_at and env["dropped"] == ["p_shop_abc123"]

    deleted = client.get(f"{base}/deleted-sources", headers=env["admin"]).json()
    assert [d["name"] for d in deleted] == ["main-sql"] and deleted[0]["purge_at"]
    assert client.get(f"{base}/deleted-sources", headers=env["dev"]).status_code == 403
    # The name can be reused while the old source is in "Recently deleted".
    make_source(env["project"], engine="mysql", database_name="x", config={})
    resp = client.post(f"{base}/deleted-sources/{ds.id}/restore", json={}, headers=env["admin"])
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "name_taken"
    resp = client.post(f"{base}/deleted-sources/{ds.id}/restore", json={"name": "main-sql-2"}, headers=env["admin"])
    assert resp.status_code == 200
    results = dict(jobs.run_queued())
    assert results[resp.json()["job"]["id"]] == "succeeded"
    db.expire_all()
    restored = db.get(DataSource, ds.id)
    assert restored.deleted_at is None and restored.name == "main-sql-2" and restored.status == "ok"
    assert env["created"] == [("p_shop_abc123", "u_0123456789ab")]  # same database name and user
    restore = [c[1] for c in env["fake"].calls if c[0] == "restore"][-1]
    assert restore["target_database_name"] == "p_shop_abc123"


def test_schema_links_survive_soft_delete_and_go_on_purge(client, env, db):
    # A-028: a soft delete hides the source's links; restoring brings them back; the purge removes them.
    ds, base = env["ds"], env["pbase"]
    ds_id = ds.id
    body = {
        "from_source_id": ds.id,
        "from_entity": "orders",
        "from_field": "user_id",
        "to_source_id": ds.id,
        "to_entity": "users",
        "to_field": "id",
        "cardinality": "many_to_one",
    }
    link = client.post(f"{base}/schema/links", json=body, headers=env["admin"]).json()
    client.delete(f"{base}/data-sources/{ds.id}", headers=env["admin"])
    jobs.run_queued()
    assert client.get(f"{base}/schema/links", headers=env["viewer"]).json() == []
    assert client.post(f"{base}/deleted-sources/{ds.id}/restore", json={}, headers=env["admin"]).status_code == 200
    jobs.run_queued()
    assert client.get(f"{base}/schema/links", headers=env["viewer"]).json() == [link]

    client.delete(f"{base}/data-sources/{ds.id}", headers=env["admin"])
    jobs.run_queued()
    backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=31))
    db.expire_all()
    assert db.get(DataSource, ds_id) is None and db.query(SchemaLink).count() == 0


def test_restore_deleted_source_can_be_retried_after_a_failure(client, env, db, monkeypatch):
    ds = env["ds"]
    base = env["pbase"]
    live = {"p_shop_abc123"}

    def create(name, user, pw):
        if name in live:
            raise ApiError(503, "database_unavailable", f"database {name} exists")
        live.add(name)
        return {}

    monkeypatch.setattr(provisioning, "create_mariadb_database", create)
    monkeypatch.setattr(provisioning, "drop_managed_source", lambda db, ds: live.discard(ds.database_name))
    _snapshot(client, env)
    client.delete(f"{base}/data-sources/{ds.id}?drop=true", headers=env["owner"])
    jobs.run_queued()
    assert live == set()

    fail = {"restore": True}
    real_restore = env["fake"].restore

    def restore(**kwargs):
        if fail.pop("restore", False):
            raise RuntimeError("restore failed")
        return real_restore(**kwargs)

    monkeypatch.setattr(env["fake"], "restore", restore)
    url = f"{base}/deleted-sources/{ds.id}/restore"
    job_id = client.post(url, json={}, headers=env["admin"]).json()["job"]["id"]
    assert dict(jobs.run_queued())[job_id] == "failed"
    assert live == set()  # the half-restored database was dropped again
    job_id = client.post(url, json={}, headers=env["admin"]).json()["job"]["id"]
    assert dict(jobs.run_queued())[job_id] == "succeeded"
    db.expire_all()
    assert db.get(DataSource, ds.id).deleted_at is None and live == {"p_shop_abc123"}


def test_pre_drop_safety_snapshot(client, env, db, monkeypatch):
    from app.services import source_ops

    dropped = []
    monkeypatch.setattr(source_ops, "drop_table", lambda ds, table: dropped.append(table))
    monkeypatch.setattr(source_ops, "sql_entity", lambda ds, table: None if table == "typo" else {"name": table})
    # A-107: a missing table is a 404 before any snapshot or job, not after a whole-database dump.
    resp = client.delete(f"{env['base']}/tables/typo", headers=env["admin"])
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"
    assert db.query(Backup).count() == 0 and db.query(Job).count() == 0
    # A-044: with a safety snapshot the drop is a job, so the request returns before the snapshot runs.
    resp = client.delete(f"{env['base']}/tables/users", headers=env["admin"])
    assert resp.status_code == 202 and dropped == []
    job_id = resp.json()["job"]["id"]
    # A retry while it is queued gets the same job, not a second drop.
    assert client.delete(f"{env['base']}/tables/users", headers=env["admin"]).json()["job"]["id"] == job_id
    assert dict(jobs.run_queued())[job_id] == "succeeded" and dropped == ["users"]
    db.expire_all()
    safety = db.query(Backup).one()
    assert safety.trigger == "pre_drop" and safety.status == "succeeded"
    assert db.get(Job, job_id).result == {"safety_backup_id": safety.id}
    env["fake"].fail_snapshot = True
    job_id = client.delete(f"{env['base']}/tables/orders", headers=env["admin"]).json()["job"]["id"]
    assert dict(jobs.run_queued())[job_id] == "failed"
    db.expire_all()
    assert "safety snapshot failed" in db.get(Job, job_id).error and dropped == ["users"]
    client.put(f"{env['base']}/backup-policy", json={"safety_snapshots": False}, headers=env["admin"])
    resp = client.delete(f"{env['base']}/tables/orders", headers=env["admin"])
    assert resp.status_code == 200 and resp.json() == {"ok": True} and dropped == ["users", "orders"]


def test_project_delete_keeps_backups_then_purges(client, env, db):
    backup_id = _snapshot(client, env)
    project, ds_id = env["project"], env["ds"].id
    resp = client.delete(f"/v1/projects/{project.id}?confirm={project.slug}", headers=env["owner"])
    assert resp.status_code == 200
    jobs.run_queued()
    db.expire_all()
    assert db.get(DataSource, ds_id) is None
    assert env["dropped"] == ["p_shop_abc123"]
    all_backups = db.query(Backup).filter_by(data_source_id=ds_id).all()
    assert {b.trigger for b in all_backups} == {"manual", "final"} and all(b.expires_at for b in all_backups)
    backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=1))
    assert db.query(Backup).filter_by(data_source_id=ds_id).count() == 2
    backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=31))
    db.expire_all()
    assert db.query(Backup).count() == 0 and db.get(Backup, backup_id) is None


def test_project_delete_retries_a_failed_final_snapshot_then_drops(client, env, db, owner_headers):
    """L-03: the source row goes with the project, so a failed final snapshot left the database (and its
    user) on the host for good, unlisted. It is now listed, retried, and dropped once it succeeds."""
    project, ds_id = env["project"], env["ds"].id
    env["fake"].fail_snapshot = True
    client.delete(f"/v1/projects/{project.id}?confirm={project.slug}", headers=env["owner"])
    jobs.run_queued()
    assert env["dropped"] == []
    [item] = client.get("/v1/instance/backups", headers=owner_headers).json()["unfinished_deletes"]
    assert item["data_source_id"] == ds_id and item["project_slug"] == project.slug and "dump failed" in item["error"]

    assert backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(hours=1))["deletes_retried"] == 0
    env["fake"].fail_snapshot = False
    assert backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(hours=7))["deletes_retried"] == 1
    jobs.run_queued()
    assert env["dropped"] == ["p_shop_abc123"]
    assert db.query(Backup).filter_by(data_source_id=ds_id, trigger="final", status="succeeded").count() == 1
    assert client.get("/v1/instance/backups", headers=owner_headers).json()["unfinished_deletes"] == []
    assert backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=2))["deletes_retried"] == 0


def test_project_delete_drops_without_snapshot_after_the_keep_period(client, env, db):
    project = env["project"]
    env["fake"].fail_snapshot = True
    client.delete(f"/v1/projects/{project.id}?confirm={project.slug}", headers=env["owner"])
    jobs.run_queued()
    backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=1))
    jobs.run_queued()  # fails again: still not dropped
    assert env["dropped"] == []
    assert backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=31))["deletes_retried"] == 1
    jobs.run_queued()
    db.expire_all()
    assert env["dropped"] == ["p_shop_abc123"]
    assert db.query(Job).filter_by(type="source.finalize_delete", status="succeeded").one().params["skip_snapshot"]


def test_deleted_project_final_snapshot_is_listed_and_downloadable(client, env, db, owner_headers):
    """A-195: a deleted project's "Recently deleted" goes with it; the instance owner can still get the data."""
    manual = _snapshot(client, env)
    project = env["project"]
    assert client.get("/v1/instance/backups", headers=owner_headers).json()["deleted_projects"] == []
    client.delete(f"/v1/projects/{project.id}?confirm={project.slug}", headers=env["owner"])
    jobs.run_queued()
    [item] = client.get("/v1/instance/backups", headers=owner_headers).json()["deleted_projects"]
    assert item["project_id"] == project.id and item["project_slug"] == project.slug
    assert item["name"] == env["ds"].name and item["engine"] == "mariadb" and item["expires_at"]

    url = f"/v1/instance/backups/deleted/{item['backup_id']}/download"
    assert client.get(url, headers=env["owner"]).status_code == 403  # the former project owner
    resp = client.get(url, headers=owner_headers)
    assert resp.status_code == 200 and f'filename="{env["ds"].name}-' in resp.headers["content-disposition"]
    assert resp.content and db.query(AuditLog).filter_by(action="backup.download").count() == 1
    # Only the final snapshots: the older versions of the deleted project are not offered.
    assert client.get(f"/v1/instance/backups/deleted/{manual}/download", headers=owner_headers).status_code == 404


def test_deleted_project_restore_recreates_it_and_its_databases(client, env, db, owner, owner_headers, monkeypatch):
    """A-195 follow-up: one click recreates the project (same id, name, members) and restores each final
    snapshot into a new managed database; a failed restore can be retried."""
    project, old = env["project"], env["ds"]
    project_id, old_id, old_name = project.id, old.id, old.name
    client.delete(f"/v1/projects/{project_id}?confirm={project.slug}", headers=env["owner"])
    jobs.run_queued()
    [item] = client.get("/v1/instance/backups", headers=owner_headers).json()["deleted_projects"]
    assert item["restorable"] is True
    # A project deleted before its sources were recorded: the final snapshot's job still says what it was.
    assert backups._deleted_source(db, db.get(Backup, item["backup_id"]), {})["database_name"] == "p_shop_abc123"

    url = f"/v1/instance/backups/deleted/projects/{project_id}/restore"
    assert client.post(url, headers=env["owner"]).status_code == 403  # instance owner only
    calls = {"n": 0}
    real_restore = env["fake"].restore

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("restore failed")
        return real_restore(**kwargs)

    monkeypatch.setattr(env["fake"], "restore", flaky)
    resp = client.post(url, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project"]["id"] == project_id and body["project"]["name"] == "Shop"
    assert body["project"]["my_role"] == "admin" and body["project"]["owner_id"] != owner.id
    assert client.post(url, headers=owner_headers).json()["error"]["code"] == "nothing_to_restore"  # running
    roles = {m["role"] for m in client.get(f"/v1/projects/{project_id}/members", headers=env["owner"]).json()}
    assert roles == {"owner", "admin", "developer", "viewer"}

    jobs.run_queued()  # the first attempt fails: the project is back, its database is still listed
    assert db.get(Job, body["jobs"][0]["id"]).status == "failed"
    [left] = client.get("/v1/instance/backups", headers=owner_headers).json()["deleted_projects"]
    assert left["backup_id"] == item["backup_id"]
    # An older final snapshot of the same database (deleted on its own, then undeleted): the newest is
    # restored, and both leave the list.
    newest = db.get(Backup, item["backup_id"])
    older = Backup(
        data_source_id=old_id,
        project_id=project_id,
        scope="source",
        engine=newest.engine,
        trigger="final",
        status="succeeded",
        started_at=newest.started_at - timedelta(days=1),
        label=newest.label,
    )
    db.add(older)
    db.commit()
    retry = client.post(url, headers=owner_headers)
    assert retry.status_code == 200, retry.text
    results = dict(jobs.run_queued())
    assert results[retry.json()["jobs"][0]["id"]] == "succeeded"

    db.expire_all()
    new = db.query(DataSource).filter_by(project_id=project_id).one()
    assert new.name == old_name and new.id != old_id and new.status == "ok"
    restore = [c[1] for c in env["fake"].calls if c[0] == "restore"][-1]
    assert restore["source_database_name"] == "p_shop_abc123" and restore["target_database_name"] == new.database_name
    assert client.get("/v1/instance/backups", headers=owner_headers).json()["deleted_projects"] == []
    assert client.post(url, headers=owner_headers).status_code == 404


def test_prune_and_purge_deleted_sources(client, env, db):
    ds = env["ds"]
    ds_id = ds.id
    old = []
    for hours in (50, 49, 48):
        b = db.get(Backup, _snapshot(client, env))
        b.started_at = utcnow() - timedelta(hours=hours)
        old.append(b.id)
        db.commit()
    client.put(
        f"{env['base']}/backup-policy",
        json={"keep_hourly": 1, "keep_daily": 0, "keep_weekly": 0, "keep_monthly": 0},
        headers=env["admin"],
    )
    summary = backups.prune_all(jobs.get_sessionmaker())
    assert summary["backups_deleted"] == 2
    db.expire_all()
    assert [b.id for b in db.query(Backup).all()] == [old[-1]]
    client.delete(f"{env['pbase']}/data-sources/{ds_id}", headers=env["admin"])
    jobs.run_queued()
    backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=31))
    db.expire_all()
    assert db.get(DataSource, ds_id) is None and db.query(Backup).count() == 0
    assert db.query(BackupPolicy).count() == 0


def test_purge_drops_a_database_deleted_without_drop(client, env, db, monkeypatch):
    # A-040: without drop=true the database and its user stayed on the host forever after the purge.
    ds_id, later = env["ds"].id, utcnow() + timedelta(days=31)
    client.delete(f"{env['pbase']}/data-sources/{ds_id}", headers=env["admin"])
    jobs.run_queued()
    assert env["dropped"] == []

    def offline(db, ds):
        raise ApiError(503, "device_offline", "The host device is offline")

    monkeypatch.setattr(provisioning, "drop_managed_source", offline)
    backups.prune_all(jobs.get_sessionmaker(), later)
    db.expire_all()
    assert db.get(DataSource, ds_id) is not None  # kept, retried at the next prune
    monkeypatch.setattr(provisioning, "drop_managed_source", lambda db, ds: env["dropped"].append(ds.database_name))
    assert backups.prune_all(jobs.get_sessionmaker(), later)["purged_sources"] == 1
    db.expire_all()
    assert db.get(DataSource, ds_id) is None and env["dropped"] == ["p_shop_abc123"]


def test_purge_treats_a_database_gone_from_its_device_as_dropped(client, env, db, monkeypatch):
    # A drop that timed out on the device but finished there answers 404 not_hosted on every retry.
    ds_id = env["ds"].id
    client.delete(f"{env['pbase']}/data-sources/{ds_id}", headers=env["admin"])
    jobs.run_queued()

    def gone(db, ds):
        raise ApiError(404, "not_hosted", "That database is not hosted on this device")

    monkeypatch.setattr(provisioning, "drop_managed_source", gone)
    assert backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=31))["purged_sources"] == 1


def test_purge_does_not_drop_twice(client, env, db):
    ds_id = env["ds"].id
    client.delete(f"{env['pbase']}/data-sources/{ds_id}?drop=true", headers=env["owner"])
    jobs.run_queued()
    backups.prune_all(jobs.get_sessionmaker(), utcnow() + timedelta(days=31))
    db.expire_all()
    assert db.get(DataSource, ds_id) is None and env["dropped"] == ["p_shop_abc123"]


def test_prune_deletes_old_finished_jobs(env, db):
    ds_id, now = env["ds"].id, utcnow()

    def job(type_, status, days, ds=None):
        row = Job(type=type_, status=status, data_source_id=ds, created_at=now - timedelta(days=days))
        db.add(row)
        db.flush()
        return row.id

    keep = {
        job("backup.archive_logs", "succeeded", 13),
        job("backup.archive_logs", "failed", 20),
        job("backup.snapshot", "running", 40),
        job("source.finalize_delete", "succeeded", 40, ds_id),  # undelete reads it
    }
    gone = {
        job("backup.archive_logs", "succeeded", 15),
        job("backup.verify", "cancelled", 15),
        job("backup.snapshot", "failed", 31),
    }
    db.commit()
    summary = backups.prune_all(jobs.get_sessionmaker(), now)
    db.expire_all()
    left = {j.id for j in db.query(Job).all()}
    assert summary["jobs_deleted"] == 3 and keep <= left and not (gone & left)


def test_scheduler_tick(env, db, fake_redis):
    factory = jobs.get_sessionmaker()
    first = backups.scheduler_tick(factory)
    types = sorted(db.get(Job, j).type for j in first)
    assert types == ["backup.archive_logs", "backup.platform_snapshot", "backup.prune", "backup.snapshot"]
    # Nothing new while those are queued / not due.
    assert backups.scheduler_tick(factory) == []
    jobs.run_queued()
    later = utcnow() + timedelta(hours=1, minutes=1)
    types = sorted(db.get(Job, j).type for j in backups.scheduler_tick(factory, later))
    assert "backup.snapshot" in types and "backup.verify" in types


def test_instance_health_and_platform_snapshot(client, env, db, owner_headers):
    _snapshot(client, env)
    assert client.get("/v1/instance/backups", headers=env["admin"]).status_code == 403
    health = client.get("/v1/instance/backups", headers=owner_headers).json()
    [src] = health["sources"]
    assert src["data_source_id"] == env["ds"].id and src["project_name"] == "Shop" and src["last_success_at"]
    assert src["local_bytes"] > 0 and src["copy_bytes"] == 0 and src["last_error"] is None
    assert health["platform"] == {"last_success_at": None, "last_error": None, "latest_backup_id": None}
    assert health["storage"][0]["location"] == "primary" and health["storage"][0]["used_bytes"] > 0
    resp = client.post("/v1/instance/backups/platform", headers=owner_headers)
    assert resp.status_code == 200 and resp.json()["job"]["type"] == "backup.platform_snapshot"
    jobs.run_queued()
    health = client.get("/v1/instance/backups", headers=owner_headers).json()
    assert health["platform"]["last_success_at"]
    # A-096: the page warns until a full export (the only off-PC copy) has been downloaded.
    assert health["last_export_at"] is None
    audit.record(db, "instance.export")  # what POST /instance/export writes (its DB dumps need a live server)
    db.commit()
    assert client.get("/v1/instance/backups", headers=owner_headers).json()["last_export_at"]


def test_platform_snapshot_download_and_restore(client, env, db, owner_headers, monkeypatch, capsys):
    """A-037: platform snapshots can be downloaded by the instance owner and restored from the CLI."""
    from app import cli

    assert cli.main(["platform", "restore", "--yes"]) == 2 and "no platform snapshot" in capsys.readouterr().out
    client.post("/v1/instance/backups/platform", headers=owner_headers)
    jobs.run_queued()
    snap_id = client.get("/v1/instance/backups", headers=owner_headers).json()["platform"]["latest_backup_id"]
    assert snap_id

    url = f"/v1/instance/backups/platform/{snap_id}/download"
    assert client.get(url, headers=env["owner"]).status_code == 403  # project owner, not instance owner
    resp = client.get(url, headers=owner_headers)
    assert resp.status_code == 200 and 'filename="deployer-platform-' in resp.headers["content-disposition"]
    assert gzip.GzipFile(fileobj=io.BytesIO(resp.content)).read().startswith(b"-- dump of deployer")
    source_backup = _snapshot(client, env)
    assert client.get(f"/v1/instance/backups/platform/{source_backup}/download", headers=owner_headers).status_code == (
        404
    )

    client.post("/v1/instance/backups/platform", headers=owner_headers)
    jobs.run_queued()
    newer = client.get("/v1/instance/backups", headers=owner_headers).json()["platform"]["latest_backup_id"]
    fed = []

    def fake_client(database, feed):
        fed.append(database)
        feed(lambda chunk: fed.append(chunk))
        # What loading the older dump does: the newer version is unknown, the loaded one is still
        # `running` with its job, its copy row does not exist yet, and a job queued back then waits.
        old = db.get(Backup, snap_id)
        old.status, old.finished_at = "running", None
        db.get(Job, old.job_id).status = "running"
        db.query(BackupCopy).filter(BackupCopy.artifact_id.in_([snap_id, newer])).delete()
        db.delete(db.get(Backup, newer))
        db.add(Job(type="backup.prune", status="queued"))
        db.commit()

    monkeypatch.setattr(backup_engine, "_run_mariadb_client", fake_client)
    assert cli.main(["platform", "restore"]) == 2 and not fed  # needs --yes
    capsys.readouterr()
    assert cli.main(["platform", "restore", "--yes", "--backup-id", snap_id]) == 0
    out = capsys.readouterr().out
    assert fed[0] == "deployer" and b"".join(fed[2:]).startswith(b"-- dump of deployer")
    db.expire_all()
    for bid in (snap_id, newer):  # still listed and restorable; nothing left to be failed and pruned
        assert db.get(Backup, bid).status == "succeeded" and backups.local_copy(db, "backup", bid, None)
    assert db.get(Job, db.get(Backup, snap_id).job_id).status == "succeeded"
    assert not db.query(Job).filter(Job.status.not_in(jobs.FINAL_STATUSES)).count()
    safety = db.query(Backup).filter_by(scope="platform", trigger="pre_restore").one()
    assert safety.id in out and safety.status == "succeeded" and safety.label.startswith("Before restoring")
    assert backups.local_copy(db, "backup", safety.id, None) is not None
    assert env["fake"].artifact_exists(backups.snapshot_ref(safety))
    assert cli.main(["platform", "restore", "--yes", "--backup-id", source_backup]) == 2
    assert "not found" in capsys.readouterr().out
    assert cli.main(["platform", "list"]) == 0 and safety.id in capsys.readouterr().out


def test_copy_hook(client, env, db, monkeypatch):
    from app.models import Device

    monkeypatch.setattr(backups, "_copy_target", None)  # host-devices code may have registered one

    user = db.get(type(env["project"]), env["project"].id).owner_id
    device = Device(name="NAS", owner_id=user, roles=["backup_storage"], token_hash="1" * 64)
    db.add(device)
    db.commit()
    client.put(f"{env['base']}/backup-policy", json={"copy_to_device_id": device.id}, headers=env["admin"])
    backup_id = _snapshot(client, env)
    listed = client.get(f"{env['base']}/backups", headers=env["viewer"]).json()[0]
    assert {"location": "device", "device_id": device.id, "status": "pending"} in listed["copies"]

    copied = []

    def target(**kw):
        copied.append(kw)
        return {"ref": kw["ref"], "size_bytes": 1, "sha256": None}

    backups.register_copy_target(target)
    job = jobs.enqueue(db, type="backup.copy", params={})
    db.commit()
    assert jobs.run_job(job.id) == "succeeded"
    assert copied and copied[0]["artifact_id"] == backup_id and copied[0]["to_device_id"] == device.id
    listed = client.get(f"{env['base']}/backups", headers=env["viewer"]).json()[0]
    assert {"location": "device", "device_id": device.id, "status": "ok"} in listed["copies"]


def test_copy_target_and_restore_device_follow_sharing_rules(client, env, db, make_user):
    """Backup copies and restores only go to devices that may serve the project (docs/DEVICES.md)."""
    from app.models import Device

    stranger = make_user()
    foreign = Device(name="Foreign NAS", owner_id=stranger.id, roles=["backup_storage"], token_hash="2" * 64)
    db.add(foreign)
    db.commit()
    resp = client.put(f"{env['base']}/backup-policy", json={"copy_to_device_id": foreign.id}, headers=env["admin"])
    assert resp.status_code == 422 and "developer" in resp.json()["error"]["message"]
    backup_id = _snapshot(client, env)
    resp = client.post(
        f"{env['base']}/restore", json={"backup_id": backup_id, "device_id": foreign.id}, headers=env["admin"]
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "device_not_eligible")
