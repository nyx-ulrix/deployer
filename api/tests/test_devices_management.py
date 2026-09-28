"""Device management, placement rules and routing of device-hosted data sources."""

import io
import zipfile

from sqlalchemy import select

from app.models import BackupPolicy, DataSource, Device, DeviceProjectGrant, Job, SourceReplica
from app.services import device_moves, device_rpc, devices
from tests import devices_support
from tests.devices_support import device_source

# Shared fixtures (assigned, not imported, so fixture parameters don't shadow an import).
fake_device = devices_support.fake_device
make_device = devices_support.make_device


def test_list_and_visibility(client, owner, owner_headers, make_user, auth_headers, make_device):
    alice = make_user()
    mine, _ = make_device(owner, "Owner PC")
    hers, _ = make_device(alice, "Alice PC")
    names = [d["name"] for d in client.get("/v1/devices", headers=auth_headers(alice)).json()]
    assert names == ["Alice PC"]
    assert [d["name"] for d in client.get("/v1/devices", headers=owner_headers).json()] == ["Owner PC"]
    all_devices = client.get("/v1/devices", params={"scope": "all"}, headers=owner_headers).json()
    assert {d["name"] for d in all_devices} == {"Owner PC", "Alice PC"}
    # scope=all is ignored for non-owners
    assert len(client.get("/v1/devices", params={"scope": "all"}, headers=auth_headers(alice)).json()) == 1
    assert client.get(f"/v1/devices/{mine.id}", headers=auth_headers(alice)).status_code == 404
    got = client.get(f"/v1/devices/{hers.id}", headers=owner_headers).json()
    assert got["owner_email"] == alice.email and got["hosted_sources_count"] == 0 and got["online"] is False


def test_update_permissions(client, db, owner, owner_headers, make_user, make_project, auth_headers, make_device):
    alice = make_user()
    project = make_project(alice, "Shop")
    device, _ = make_device(alice)
    headers = auth_headers(alice)
    resp = client.patch(
        f"/v1/devices/{device.id}",
        json={"name": "Renamed", "roles": ["backup_storage"], "sharing_mode": "selected", "project_ids": [project.id]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Renamed" and body["roles"] == ["backup_storage"] and body["project_ids"] == [project.id]
    assert client.patch(f"/v1/devices/{device.id}", json={"status": "disabled"}, headers=headers).status_code == 403
    resp = client.patch(f"/v1/devices/{device.id}", json={"status": "disabled"}, headers=owner_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "disabled"
    resp = client.patch(f"/v1/devices/{device.id}", json={"project_ids": []}, headers=headers)
    assert resp.json()["project_ids"] == []
    assert db.scalars(select(DeviceProjectGrant)).first() is None


def test_placement_rules(db, make_user, make_project, make_device):
    alice, bob = make_user(), make_user()
    project = make_project(alice, "P", members={bob: "developer"})
    alice_pc, _ = make_device(alice, "A")
    bob_pc, _ = make_device(bob, "B")
    bob_selected, _ = make_device(bob, "B2", sharing_mode="selected")
    storage_only, _ = make_device(alice, "S", roles=["backup_storage"])
    assert devices.device_can_host(db, alice_pc, project)
    # my_projects: bob is only a developer there
    assert not devices.device_can_host(db, bob_pc, project)
    assert not devices.device_can_host(db, bob_selected, project)
    db.add(DeviceProjectGrant(device_id=bob_selected.id, project_id=project.id))
    db.commit()
    assert devices.device_can_host(db, bob_selected, project)
    assert not devices.device_can_host(db, storage_only, project)
    options = devices.placement_options(db, project)
    assert options[0]["device_id"] is None and options[0]["eligible"]
    by_name = {o["name"]: o for o in options[1:]}
    assert by_name["A"]["eligible"] and not by_name["B"]["eligible"] and by_name["B"]["reason"]


def test_create_source_on_device(
    client, db, owner, owner_headers, make_project, make_user, auth_headers, make_device, fake_device
):
    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    stranger = make_user()
    other, _ = make_device(stranger, "Not mine")
    body = {"kind": "sql", "mode": "managed", "engine": "mariadb", "name": "db", "device_id": other.id}
    resp = client.post(f"/v1/projects/{project.id}/data-sources", json=body, headers=owner_headers)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "device_not_eligible"

    body["device_id"] = device.id
    resp = client.post(f"/v1/projects/{project.id}/data-sources", json=body, headers=owner_headers)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "device_offline"

    fd = fake_device(device.id, lambda m, p: {"database_name": p["database_name"], "username": "u_0123456789ab"})
    resp = client.post(f"/v1/projects/{project.id}/data-sources", json=body, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["device_id"] == device.id and out["device_name"] == "Laptop"
    assert out["display"]["username"] == "u_0123456789ab"
    method, params = fd.calls[-1]
    assert method == "datasource.provision" and params["kind"] == "sql"
    assert out["database_name"] == params["database_name"]
    stored = db.get(DataSource, out["id"])
    from app.crypto import decrypt_json

    assert "password" not in decrypt_json(stored.config_encrypted)

    resp = client.get(f"/v1/projects/{project.id}/placement-options", headers=owner_headers)
    assert [o["device_id"] for o in resp.json()] == [None, device.id]
    assert resp.json()[1]["online"] is True


def test_project_create_with_device(client, owner, owner_headers, make_device, fake_device):
    device, _ = make_device(owner, mongodb=False)
    fake_device(device.id, lambda m, p: {"database_name": p["database_name"], "username": "u_0123456789ab"})
    resp = client.post(
        "/v1/projects",
        json={"name": "Edge", "provision": {"sql": True, "nosql": True, "device_id": device.id}},
        headers=owner_headers,
    )
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "managed_mongodb_unavailable"
    resp = client.post(
        "/v1/projects", json={"name": "Edge", "provision": {"sql": True, "device_id": device.id}}, headers=owner_headers
    )
    assert resp.status_code == 200, resp.text
    sources = client.get(f"/v1/projects/{resp.json()['id']}/data-sources", headers=owner_headers).json()
    assert [s["device_id"] for s in sources] == [device.id]


def test_routing_for_device_hosted_sources(client, db, owner, owner_headers, make_project, make_device, fake_device):
    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    sql = device_source(db, project, device, "sql")
    mongo = device_source(db, project, device, "nosql", database_name="p_test_def456")
    db.add(BackupPolicy(data_source_id=sql.id, safety_snapshots=False))  # no pre_drop snapshot in this test
    db.commit()
    base = f"/v1/projects/{project.id}/data-sources"

    # Offline: operations 503, schema degrades to an error entry.
    resp = client.get(f"{base}/{sql.id}/tables/users/rows", headers=owner_headers)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "device_offline"
    schema = client.get(f"/v1/projects/{project.id}/schema", headers=owner_headers).json()
    assert {s["status"] for s in schema["sources"]} == {"error"}
    resp = client.post(f"{base}/{sql.id}/check", headers=owner_headers)
    assert resp.json()["status"] == "error"

    entity = {"name": "users", "type": "table", "row_count": 1, "fields": [], "indexes": [], "validator": None}

    def handler(method, params):
        if method == "datasource.check":
            return {"ok": True, "message": "Connected", "server_version": "11.4"}
        assert method == "datasource.call", method
        op, args = params["op"], params["args"]
        if op == "introspect":
            return {
                "source_id": "hosted",
                "name": "x",
                "kind": params["kind"],
                "engine": "mariadb",
                "status": "ok",
                "error": None,
                "entities": [entity] if params["kind"] == "sql" else [],
                "relationships": [],
            }
        if op == "rows.list":
            return {"columns": ["id"], "primary_key": ["id"], "rows": [{"id": 1}], "total": 1}
        if op == "rows.insert":
            return {"row": args["values"]}
        if op == "table.create":
            return {"ok": True}
        if op == "entity":
            return entity
        if op == "ddl_export":
            return "-- remote ddl\nCREATE TABLE users (id int);\n" if params["kind"] == "sql" else "// remote mongo\n"
        if op == "documents.insert":
            return {"document": args["document"]}
        if op == "connection_info":
            return {
                "uri": "mysql://" + "u:fake-password" + "@mariadb:3306/db",
                "host": "mariadb",
                "port": 3306,
                "username": "u",
                "password": "pw",
                "database": "db",
            }
        if op == "table.drop":
            from app.errors import ApiError

            raise ApiError(404, "not_found", "Table 'nope' not found")
        raise AssertionError(op)

    fd = fake_device(device.id, handler)
    schema = client.get(f"/v1/projects/{project.id}/schema", headers=owner_headers).json()
    by_id = {s["source_id"]: s for s in schema["sources"]}
    assert by_id[sql.id]["status"] == "ok" and by_id[sql.id]["entities"][0]["name"] == "users"
    assert by_id[sql.id]["name"] == "main-sql"

    rows = client.get(f"{base}/{sql.id}/tables/users/rows", params={"limit": 5}, headers=owner_headers).json()
    assert rows["rows"] == [{"id": 1}]
    assert fd.calls[-1][1]["args"]["limit"] == 5
    resp = client.post(f"{base}/{sql.id}/tables/users/rows", json={"values": {"id": 2}}, headers=owner_headers)
    assert resp.json() == {"row": {"id": 2}}
    resp = client.post(f"{base}/{sql.id}/tables", json={"name": "users", "columns": []}, headers=owner_headers)
    assert resp.status_code == 200 and resp.json()["name"] == "users"
    resp = client.delete(f"{base}/{sql.id}/tables/nope", headers=owner_headers)
    assert resp.status_code == 404
    resp = client.post(
        f"{base}/{mongo.id}/collections/items/documents", json={"document": {"a": 1}}, headers=owner_headers
    )
    assert resp.json() == {"document": {"a": 1}}

    resp = client.get(f"/v1/projects/{project.id}/schema/export", params={"format": "bundle"}, headers=owner_headers)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        texts = "".join(zf.read(n).decode() for n in zf.namelist())
    assert "remote ddl" in texts and "remote mongo" in texts

    resp = client.post(f"{base}/{sql.id}/check", headers=owner_headers)
    assert resp.json()["status"] == "ok"
    info = client.get(f"{base}/{sql.id}/connection", headers=owner_headers).json()
    assert info["password"] == "pw" and "host device" in info["external_hint"] and info["device_id"] == device.id


def test_remove_device(client, db, owner, owner_headers, make_user, make_project, auth_headers, make_device):
    alice = make_user()
    project = make_project(alice, "Shop")
    device, _ = make_device(alice)
    device_id = device.id
    ds_id = device_source(db, project, device).id
    resp = client.delete(f"/v1/devices/{device_id}", headers=auth_headers(alice))
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "device_in_use"
    assert client.delete(f"/v1/devices/{device_id}?force=true", headers=auth_headers(alice)).status_code == 403
    resp = client.delete(f"/v1/devices/{device_id}?force=true", headers=owner_headers)
    assert resp.status_code == 200
    db.expunge_all()
    assert db.get(Device, device_id) is None
    source = db.get(DataSource, ds_id)
    assert source.status == "error" and source.status_message == "device removed"

    empty, _ = make_device(alice, "Empty")
    assert client.delete(f"/v1/devices/{empty.id}", headers=auth_headers(make_user())).status_code == 404
    assert client.delete(f"/v1/devices/{empty.id}", headers=auth_headers(alice)).status_code == 200


def test_remove_device_with_cohost_copies(
    client, db, owner, owner_headers, make_user, make_project, auth_headers, make_device, fake_device
):
    # A-009: co-host copies used to cascade away while the full database stayed on the PC.
    alice = make_user()
    project = make_project(alice, "Shop")
    device, _ = make_device(alice)
    ds = device_source(db, project, device, database_name="p_shop_abc123")
    ds.device_id = None  # the database itself lives on the main server
    db.add(SourceReplica(data_source_id=ds.id, device_id=device.id, status="syncing"))
    db.commit()
    url = f"/v1/devices/{device.id}"
    for force in ("false", "true"):  # only the instance owner may force it
        resp = client.delete(f"{url}?force={force}", headers=auth_headers(alice))
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "device_has_copies"
        assert [r["name"] for r in resp.json()["error"]["details"]["replicas"]] == [ds.name]
    fd = fake_device(device.id, lambda method, params: {})
    assert client.delete(f"{url}?force=true", headers=owner_headers).status_code == 200
    assert fd.calls == [("datasource.drop", {"kind": "sql", "database_name": "p_shop_abc123"}), ("device.detach", {})]
    db.expunge_all()
    assert db.scalars(select(SourceReplica)).first() is None and db.get(DataSource, ds.id).status == "ok"


def test_move_validation(client, db, owner, owner_headers, make_project, make_device, monkeypatch):
    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    ds = device_source(db, project, device)
    url = f"/v1/projects/{project.id}/data-sources/{ds.id}/move"
    resp = client.post(url, json={"device_id": device.id}, headers=owner_headers)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "already_there"
    resp = client.post(url, json={"device_id": None}, headers=owner_headers)
    assert resp.status_code == 503  # source device offline

    started = []
    monkeypatch.setattr(device_moves, "start_move", lambda job_id: started.append(job_id))
    device_rpc.mark_online(device.id, "c")
    resp = client.post(url, json={"device_id": None}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    job = resp.json()["job"]
    assert job["type"] == "device.move" and started == [job["id"]]
    resp = client.post(url, json={"device_id": None}, headers=owner_headers)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "move_in_progress"
    assert db.get(Job, job["id"]).params == {"from_device_id": device.id, "to_device_id": None}


def test_move_job_runs(db, owner, make_project, make_device, fake_device, monkeypatch):
    """Device -> main server: dump on the device, restore locally, switch, schedule cleanup."""
    import gzip
    import json

    from app.models import User

    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    ds = device_source(db, project, device)
    data = {"kind": "sql", "engine": "mariadb", "database_name": ds.database_name, "tables": []}

    def handler(method, params):
        assert method == "datasource.export"
        path = device_rpc.transfer_path(params["transfer_id"])
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(json.dumps(data))
        device_rpc.update_transfer(params["transfer_id"], complete=True)
        return {"rows": 0}

    fake_device(device.id, handler)
    snapshots = []
    monkeypatch.setattr(device_moves, "_safety_snapshot", lambda sid, uid: snapshots.append(sid))
    restored = []
    monkeypatch.setattr(
        device_moves,
        "provision_target",
        lambda project, ds, target: (
            "p_shop_new123",
            {"host": "mariadb", "username": "u", "password": "p", "database": "p_shop_new123"},
        ),
    )
    monkeypatch.setattr(
        "app.services.transfer.restore_data", lambda target, payload: restored.append((target, payload)) or (0, 0)
    )
    job = device_moves.create_move_job(db, ds, None, db.get(User, owner.id))
    db.commit()
    device_moves.run_move(job.id)
    db.expire_all()
    job = db.get(Job, job.id)
    assert job.status == "succeeded", job.error
    assert snapshots == [ds.id]
    moved = db.get(DataSource, ds.id)
    assert moved.device_id is None and moved.database_name == "p_shop_new123"
    assert restored and restored[0][1] == data and restored[0][0].device_id is None
    from app.redis_client import get_redis

    entries = get_redis().zrange(device_moves.CLEANUP_KEY, 0, -1)
    assert len(entries) == 1 and json.loads(entries[0])["device_id"] == device.id

    dropped = []
    monkeypatch.setattr(device_moves, "drop_copy", lambda *a: dropped.append(a))
    import time

    assert device_moves.run_due_cleanups(now=time.time()) == 0
    assert device_moves.run_due_cleanups(now=time.time() + 8 * 86400) == 1
    assert dropped == [("sql", device.id, "p_test_abc123", None)]


def test_hosted_count_ignores_soft_deleted_sources(client, db, owner, owner_headers, make_project, make_device):
    from app.models import utcnow

    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    live = device_source(db, project, device, name="live")
    gone = device_source(db, project, device, name="gone", database_name="p_test_gone")
    gone.deleted_at = utcnow()
    db.commit()
    assert client.get(f"/v1/devices/{device.id}", headers=owner_headers).json()["hosted_sources_count"] == 1
    assert client.get("/v1/devices", headers=owner_headers).json()[0]["hosted_sources_count"] == 1
    # Removing the device still detaches both rows (the deleted one may still have a database on it).
    resp = client.delete(f"/v1/devices/{device.id}", headers=owner_headers)
    assert resp.status_code == 409 and [s["id"] for s in resp.json()["error"]["details"]["data_sources"]] == [live.id]


def test_backup_schema_of_device_source_is_read_through_the_device(db, owner, make_project, make_device, monkeypatch):
    from app.services import backups, source_ops

    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    ds = device_source(db, project, device)
    seen = []
    schema = {"source_id": ds.id, "status": "ok", "entities": [], "relationships": []}
    monkeypatch.setattr(source_ops, "introspect_sources", lambda sources, sample=200: seen.append(sources) or [schema])
    assert backups._schema_snapshot(ds) == schema
    assert backups.schema_at(db, ds, "current")[0] == schema
    assert [s[0].id for s in seen] == [ds.id, ds.id]


def test_move_job_heartbeats_while_running(db, owner, make_project, make_device, monkeypatch):
    """A long move must not be failed by the worker's stale-job sweeper (it runs outside the worker)."""
    from app.models import User
    from app.redis_client import get_redis
    from app.services import jobs

    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    ds = device_source(db, project, device)
    job = device_moves.create_move_job(db, ds, None, db.get(User, owner.id))
    db.commit()
    alive = []
    monkeypatch.setattr(
        device_moves, "_run_move", lambda job_id: alive.append(get_redis().exists(jobs.heartbeat_key(job_id)))
    )
    device_moves.run_move(job.id)
    assert alive == [1]


def _main_source(db, project):
    from app.crypto import encrypt_json

    ds = DataSource(
        project_id=project.id,
        name="main",
        kind="sql",
        engine="mariadb",
        mode="managed",
        database_name="p_shop_main",
        config_encrypted=encrypt_json({"host": "mariadb", "username": "u_main0123456", "database": "p_shop_main"}),
        status="ok",
    )
    db.add(ds)
    db.commit()
    return ds


def test_move_refused_while_db_access_apps_are_live(client, db, owner, owner_headers, make_project, make_device):
    """A-008: live apps hold the current copy's DEPLOYER_DB_* and would keep writing to it after the move."""
    from tests.apps_support import make_app

    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    device_rpc.mark_online(device.id, "c")
    ds = _main_source(db, project)
    make_app(db, project, "Store", database_access=True, live_deployment_id="dep-1")
    url = f"/v1/projects/{project.id}/data-sources/{ds.id}/move"
    resp = client.post(url, json={"device_id": device.id}, headers=owner_headers)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "apps_use_database", resp.text
    assert resp.json()["error"]["details"]["apps"] == ["Store"]


def test_move_makes_the_old_main_copy_read_only(db, owner, make_project, make_device, monkeypatch, tmp_path):
    """A-008: the old copy is read-only from the dump on; a failed move gives write access back."""
    from app.errors import ApiError
    from app.models import User
    from app.services import provisioning

    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    ds = _main_source(db, project)
    calls = []
    monkeypatch.setattr(provisioning, "set_mariadb_read_only", lambda *a: calls.append(a))
    monkeypatch.setattr(device_moves, "_safety_snapshot", lambda sid, uid: None)
    monkeypatch.setattr(device_moves, "dump_source", lambda ds: calls.append("dump") or tmp_path / "dump.json.gz")
    monkeypatch.setattr(device_moves, "provision_target", lambda p, ds, t: ("p_shop_dev", {"username": "u"}))
    monkeypatch.setattr(device_moves, "drop_copy", lambda *a: None)

    def broken_restore(target, dump):
        raise ApiError(502, "import_failed", "restore broke")

    monkeypatch.setattr(device_moves, "restore_into", broken_restore)
    job = device_moves.create_move_job(db, ds, device.id, db.get(User, owner.id))
    db.commit()
    device_moves.run_move(job.id)
    locked, unlocked = ("p_shop_main", "u_main0123456", True), ("p_shop_main", "u_main0123456", False)
    assert calls == [locked, "dump", unlocked]
    db.expire_all()
    assert db.get(Job, job.id).status == "failed" and db.get(DataSource, ds.id).device_id is None

    calls.clear()
    monkeypatch.setattr(device_moves, "restore_into", lambda target, dump: {"rows": 0})
    job = device_moves.create_move_job(db, ds, device.id, db.get(User, owner.id))
    db.commit()
    device_moves.run_move(job.id)
    db.expire_all()
    assert db.get(Job, job.id).status == "succeeded"
    assert calls == [locked, "dump"]  # kept read-only until the cleanup drops it


def test_stale_read_only_lock_is_released(db, owner, make_project, make_device, monkeypatch, fake_redis):
    """A-008: a move cut short without unlocking (API restart, failed unlock) gives write access back later."""
    from app.models import User
    from app.services import provisioning

    project = make_project(owner, "Shop")
    device, _ = make_device(owner)
    ds = _main_source(db, project)
    calls = []

    def unlock_fails(*a):
        calls.append(a)
        if not a[2]:
            raise RuntimeError("mariadb restarting")

    monkeypatch.setattr(provisioning, "set_mariadb_read_only", unlock_fails)
    monkeypatch.setattr(device_moves, "_safety_snapshot", lambda sid, uid: None)
    monkeypatch.setattr(device_moves, "dump_source", lambda ds: (_ for _ in ()).throw(RuntimeError("dump broke")))
    job = device_moves.create_move_job(db, ds, device.id, db.get(User, owner.id))
    db.commit()
    device_moves.run_move(job.id)
    assert fake_redis.hlen(device_moves.LOCKS_KEY) == 1  # still read-only: the unlock failed

    running = device_moves.create_move_job(db, ds, device.id, db.get(User, owner.id))
    db.commit()
    calls.clear()
    monkeypatch.setattr(provisioning, "set_mariadb_read_only", lambda *a: calls.append(a))
    assert device_moves.release_stale_locks() == 0 and calls == []  # another move of it is running
    running.status = "failed"
    db.commit()
    assert device_moves.release_stale_locks() == 1
    assert calls == [("p_shop_main", "u_main0123456", False)]
    assert fake_redis.hlen(device_moves.LOCKS_KEY) == 0
