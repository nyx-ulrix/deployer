"""Backup API and orchestration against a fake executor (no database servers or dump tools needed).

The fake executor writes real encrypted artifacts into a temporary BACKUP_DIR so downloads, deletion
and verification paths are exercised end to end; restores only record their arguments.
"""

import gzip
import io
import secrets
from datetime import datetime, timedelta

import pytest

from app.crypto import encrypt_json
from app.models import Backup, BackupCopy, BackupLogSegment, BackupPolicy, DataSource, Job, utcnow
from app.services import backup_engine, backups, executors, jobs, provisioning


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
def env(tmp_path, monkeypatch, db, make_user, make_project, auth_headers):
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
    ds = DataSource(
        project_id=project.id,
        name="main-sql",
        kind="sql",
        engine="mariadb",
        mode="managed",
        database_name="p_shop_abc123",
        config_encrypted=encrypt_json(
            {
                "host": "mariadb",
                "port": 3306,
                "username": "u_0123456789ab",
                "password": secrets.token_hex(16),
                "database": "p_shop_abc123",
            }
        ),
        status="ok",
    )
    db.add(ds)
    db.commit()
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


def test_external_sources_have_no_backups(client, env, db):
    ext = DataSource(
        project_id=env["project"].id,
        name="atlas",
        kind="nosql",
        engine="mongodb",
        mode="external",
        database_name="app",
        config_encrypted=encrypt_json({}),
    )
    db.add(ext)
    db.commit()
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
    # Same structure; only the live (estimated) row count of users differs from the exact snapshot count.
    assert [(e["name"], e["fields"], e["row_count"]) for e in current["entities"]] == [
        ("users", [], {"before": 5, "after": 99})
    ]


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


def test_soft_delete_and_restore_deleted_source(client, env, db):
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
    db.add(
        DataSource(
            project_id=ds.project_id,
            name="main-sql",
            kind="sql",
            engine="mysql",
            mode="external",
            database_name="x",
            config_encrypted=encrypt_json({}),
        )
    )
    db.commit()
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


def test_pre_drop_safety_snapshot(client, env, db, monkeypatch):
    from app.services import source_ops

    dropped = []
    monkeypatch.setattr(source_ops, "drop_table", lambda ds, table: dropped.append(table))
    resp = client.delete(f"{env['base']}/tables/users", headers=env["admin"])
    assert resp.status_code == 200 and dropped == ["users"]
    db.expire_all()
    safety = db.query(Backup).one()
    assert safety.trigger == "pre_drop" and safety.status == "succeeded"
    env["fake"].fail_snapshot = True
    resp = client.delete(f"{env['base']}/tables/orders", headers=env["admin"])
    assert resp.status_code == 500 and resp.json()["error"]["code"] == "safety_snapshot_failed"
    assert dropped == ["users"]
    client.put(f"{env['base']}/backup-policy", json={"safety_snapshots": False}, headers=env["admin"])
    assert client.delete(f"{env['base']}/tables/orders", headers=env["admin"]).status_code == 200


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
    assert health["platform"] == {"last_success_at": None, "last_error": None}
    assert health["storage"][0]["location"] == "primary" and health["storage"][0]["used_bytes"] > 0
    resp = client.post("/v1/instance/backups/platform", headers=owner_headers)
    assert resp.status_code == 200 and resp.json()["job"]["type"] == "backup.platform_snapshot"
    jobs.run_queued()
    health = client.get("/v1/instance/backups", headers=owner_headers).json()
    assert health["platform"]["last_success_at"]


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
