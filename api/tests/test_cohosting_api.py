"""Co-hosting API (docs/COHOSTING.md): member flag, eligibility, replicas, the copy job, conflicts and
history. The sync engine itself is covered by test_source_sync.py."""

import gzip
import json
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.crypto import encrypt_json
from app.errors import ApiError
from app.models import (
    AuditLog,
    DataSource,
    DeviceProjectGrant,
    ProjectMember,
    SourceReplica,
    SyncConflict,
    SyncVersion,
)
from app.services import device_moves, device_rpc, jobs, source_sync
from app.services.source_sync import key_hash
from tests import devices_support
from tests.devices_support import device_source
from tests.test_source_sync import FakeSide

fake_device = devices_support.fake_device  # shared fixtures
make_device = devices_support.make_device


@pytest.fixture
def team(db, owner, make_user, make_project, make_device):
    users = {
        "owner": owner,
        "admin": make_user("admin@example.com"),
        "cohost": make_user("cohost@example.com"),
        "dev": make_user("dev@example.com"),
        "viewer": make_user("viewer@example.com"),
    }
    project = make_project(
        owner,
        "Shop",
        members={
            users["admin"]: "admin",
            users["cohost"]: "developer",
            users["dev"]: "developer",
            users["viewer"]: "viewer",
        },
    )
    member = db.scalar(select(ProjectMember).where(ProjectMember.user_id == users["cohost"].id))
    member.can_cohost = True
    device, _ = make_device(users["cohost"], "Home PC", sharing_mode="selected")
    db.add(DeviceProjectGrant(device_id=device.id, project_id=project.id))
    ds = DataSource(
        project_id=project.id,
        name="main",
        kind="sql",
        engine="mariadb",
        mode="managed",
        database_name="p_shop_abc123",
        config_encrypted=encrypt_json({"username": "u_0123456789ab", "password": "p" * 32}),
        status="ok",
    )
    db.add(ds)
    db.commit()
    return {"project": project, "users": users, "device": device, "ds": ds}


def _url(t, suffix=""):
    return f"/v1/projects/{t['project'].id}/data-sources/{t['ds'].id}{suffix}"


def _replica(db, t, status="syncing"):
    rep = SourceReplica(
        data_source_id=t["ds"].id,
        device_id=t["device"].id,
        status=status,
        position_primary={"i": 0},
        position_replica={"i": 0},
        id_offset=2,
    )
    db.add(rep)
    db.commit()
    return rep


# --- members & eligibility ----------------------------------------------------------------------------


def test_member_cohost_flag_roles(client, db, team, auth_headers):
    t, u = team, team["users"]
    url = f"/v1/projects/{t['project'].id}/members/{u['dev'].id}"
    assert client.patch(url, json={"can_cohost": True}, headers=auth_headers(u["cohost"])).status_code == 403
    resp = client.patch(url, json={"can_cohost": True}, headers=auth_headers(u["admin"]))
    assert resp.status_code == 200 and resp.json()["can_cohost"] is True and resp.json()["role"] == "developer"
    viewer_url = f"/v1/projects/{t['project'].id}/members/{u['viewer'].id}"
    resp = client.patch(viewer_url, json={"can_cohost": True}, headers=auth_headers(u["admin"]))
    assert resp.status_code == 422
    assert client.patch(url, json={}, headers=auth_headers(u["admin"])).status_code == 422
    # The owner's settings: only the owner; the owner may flag themself.
    owner_url = f"/v1/projects/{t['project'].id}/members/{u['owner'].id}"
    assert client.patch(owner_url, json={"can_cohost": True}, headers=auth_headers(u["admin"])).status_code == 403
    assert client.patch(owner_url, json={"can_cohost": True}, headers=auth_headers(u["owner"])).status_code == 200

    # Demoting a co-host to viewer clears the flag and pauses their copies.
    rep = _replica(db, t)
    cohost_url = f"/v1/projects/{t['project'].id}/members/{u['cohost'].id}"
    resp = client.patch(cohost_url, json={"role": "viewer"}, headers=auth_headers(u["admin"]))
    assert resp.status_code == 200 and resp.json()["can_cohost"] is False
    db.expire_all()
    assert db.get(SourceReplica, rep.id).status == "paused"
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions.count("member.cohost_change") == 3 and "member.role_change" in actions
    members = client.get(f"/v1/projects/{t['project'].id}/members", headers=auth_headers(u["viewer"])).json()
    assert {m["email"]: m["can_cohost"] for m in members}["dev@example.com"] is True


def test_eligibility_lists_only_own_devices(client, db, team, auth_headers, make_device):
    t, u = team, team["users"]
    url = f"/v1/projects/{t['project'].id}/cohosting/eligibility"
    make_device(u["dev"], "Dev laptop")
    device_rpc.mark_online(t["device"].id, "c")
    body = client.get(url, headers=auth_headers(u["cohost"])).json()
    assert body == {
        "can_cohost": True,
        "devices": [{"id": t["device"].id, "name": "Home PC", "online": True, "granted": True}],
        "offer": True,
    }
    # A developer without the flag sees their device but no offer; a viewer without devices neither.
    body = client.get(url, headers=auth_headers(u["dev"])).json()
    assert body["can_cohost"] is False and body["offer"] is False
    assert [d["name"] for d in body["devices"]] == ["Dev laptop"] and body["devices"][0]["granted"] is False
    assert client.get(url, headers=auth_headers(u["viewer"])).json() == {
        "can_cohost": False,
        "devices": [],
        "offer": False,
    }


# --- replicas ------------------------------------------------------------------------------------------


def test_create_replica_validation(client, db, team, auth_headers, make_device):
    t, u = team, team["users"]
    body = {"device_id": t["device"].id}
    h = auth_headers(u["cohost"])
    assert client.post(_url(t, "/replicas"), json=body, headers=auth_headers(u["viewer"])).status_code == 403
    # Not flagged (developer without can_cohost), even an admin.
    assert client.post(_url(t, "/replicas"), json=body, headers=auth_headers(u["admin"])).status_code == 403
    # Someone else's device.
    other, _ = make_device(u["dev"], "Other")
    assert client.post(_url(t, "/replicas"), json={"device_id": other.id}, headers=h).status_code == 404
    # Offline.
    resp = client.post(_url(t, "/replicas"), json=body, headers=h)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "device_offline"
    device_rpc.mark_online(t["device"].id, "c")
    # A device-hosted source can't be replicated in v1; neither can an external one.
    hosted = device_source(db, t["project"], t["device"], name="on-device")
    resp = client.post(f"/v1/projects/{t['project'].id}/data-sources/{hosted.id}/replicas", json=body, headers=h)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "replica_unsupported"
    # Not shared with the project.
    db.query(DeviceProjectGrant).delete()
    db.commit()
    resp = client.post(_url(t, "/replicas"), json=body, headers=h)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "device_not_eligible"
    db.add(DeviceProjectGrant(device_id=t["device"].id, project_id=t["project"].id))
    db.commit()

    resp = client.post(_url(t, "/replicas"), json=body, headers=h)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["replica"]["status"] == "copying" and out["job"]["type"] == "replica.copy"
    assert client.post(_url(t, "/replicas"), json=body, headers=h).json()["error"]["code"] == "replica_exists"
    # The source response lists its copies.
    sources = client.get(f"/v1/projects/{t['project'].id}/data-sources", headers=auth_headers(u["viewer"])).json()
    (main,) = [s for s in sources if s["id"] == t["ds"].id]
    assert [(r["device_name"], r["status"], r["open_conflicts"]) for r in main["replicas"]] == [
        ("Home PC", "copying", 0)
    ]
    assert set(main["replicas"][0]) >= {"id", "device_id", "device_name", "status", "lag_seconds", "last_synced_at"}


def test_copy_job_with_fake_device(client, db, team, auth_headers, fake_device, monkeypatch):
    t, u = team, team["users"]
    settings_calls = []
    monkeypatch.setattr(source_sync, "ensure_mariadb_settings", lambda **kw: settings_calls.append(kw))
    monkeypatch.setattr(source_sync, "local_position", lambda kind, database: {"gtid": "0-1-5"})

    def dump(ds):
        fd, path = tempfile.mkstemp(suffix=".json.gz")
        os.close(fd)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump({"kind": "sql", "tables": []}, fh)
        return Path(path)

    monkeypatch.setattr(device_moves, "dump_source", dump)

    def handler(method, params):
        if method == "datasource.provision":
            return {"database_name": params["database_name"], "username": "u_0123456789ab"}
        if method == "datasource.import":
            assert device_rpc.transfer_path(params["transfer_id"]).exists()
            return {"rows": 3, "documents": 0}
        if method == "sync.position":
            return {"gtid": "0-1-9"}
        raise AssertionError(method)

    fd = fake_device(t["device"].id, handler)
    resp = client.post(_url(t, "/replicas"), json={"device_id": t["device"].id}, headers=auth_headers(u["cohost"]))
    assert resp.status_code == 200, resp.text
    assert dict(jobs.run_queued())[resp.json()["job"]["id"]] == "succeeded"
    db.expire_all()
    rep = db.get(SourceReplica, resp.json()["replica"]["id"])
    assert rep.status == "syncing" and rep.id_offset == 2
    assert rep.position_primary == {"gtid": "0-1-5"} and rep.position_replica == {"gtid": "0-1-9"}
    assert settings_calls == [{"offset": source_sync.PRIMARY_ID_OFFSET}]
    methods = [m for m, _ in fd.calls]
    assert methods == ["datasource.provision", "datasource.import", "sync.position"]
    assert fd.calls[0][1] == {"kind": "sql", "database_name": "p_shop_abc123"}  # the same name
    assert fd.calls[2][1]["auto_increment"] == {"increment": source_sync.AUTO_INCREMENT_STEP, "offset": 2}
    # The device never receives the master's secrets or the source's credentials.
    sent = json.dumps([p for _, p in fd.calls])
    for secret in (get_settings().master_key, "p" * 32, get_settings().jwt_secret):
        assert secret not in sent


def test_copy_failure_marks_replica_and_drops_partial_copy(client, db, team, auth_headers, fake_device, monkeypatch):
    t, u = team, team["users"]
    monkeypatch.setattr(source_sync, "ensure_mariadb_settings", lambda **kw: None)
    monkeypatch.setattr(source_sync, "local_position", lambda kind, database: {"gtid": ""})

    def broken_dump(ds):
        raise ApiError(503, "database_unavailable", "dump broke")

    monkeypatch.setattr(device_moves, "dump_source", broken_dump)

    def handler(method, params):
        if method == "datasource.provision":
            return {"database_name": params["database_name"]}
        if method == "datasource.drop":
            return {}
        raise AssertionError(method)

    fd = fake_device(t["device"].id, handler)
    resp = client.post(_url(t, "/replicas"), json={"device_id": t["device"].id}, headers=auth_headers(u["cohost"]))
    assert dict(jobs.run_queued())[resp.json()["job"]["id"]] == "failed"
    db.expire_all()
    rep = db.get(SourceReplica, resp.json()["replica"]["id"])
    assert rep.status == "error" and "dump broke" in rep.error
    assert [m for m, _ in fd.calls] == ["datasource.provision", "datasource.drop"]


def test_replica_actions_roles(client, db, team, auth_headers):
    t, u = team, team["users"]
    rep = _replica(db, t)
    base = _url(t, f"/replicas/{rep.id}")
    assert client.post(base + "/pause", headers=auth_headers(u["dev"])).status_code == 403
    assert client.post(base + "/pause", headers=auth_headers(u["cohost"])).json()["replica"]["status"] == "paused"
    assert client.post(base + "/resume", headers=auth_headers(u["admin"])).json()["replica"]["status"] == "syncing"
    assert client.post(base + "/resume", headers=auth_headers(u["admin"])).status_code == 409
    assert client.post(base + "/recopy", headers=auth_headers(u["cohost"])).status_code == 503  # device offline
    device_rpc.mark_online(t["device"].id, "c")
    resp = client.post(base + "/recopy", headers=auth_headers(u["cohost"]))
    assert resp.status_code == 200 and resp.json()["job"]["type"] == "replica.copy"
    assert resp.json()["replica"]["status"] == "copying"
    assert client.get(_url(t, "/replicas"), headers=auth_headers(u["viewer"])).json()[0]["status"] == "copying"
    assert client.delete(base, headers=auth_headers(u["dev"])).status_code == 403
    assert client.delete(base, headers=auth_headers(u["admin"])).json() == {"ok": True}
    db.expire_all()
    assert db.scalar(select(SourceReplica.id)) is None
    actions = {a.action for a in db.scalars(select(AuditLog))}
    assert {"replica.pause", "replica.resume", "replica.recopy", "replica.delete"} <= actions


def test_moving_a_replicated_source_is_refused(client, db, team, auth_headers):
    t = team
    _replica(db, t)
    device_rpc.mark_online(t["device"].id, "c")
    resp = client.post(_url(t, "/move"), json={"device_id": t["device"].id}, headers=auth_headers(t["users"]["owner"]))
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "has_replicas"


# --- conflicts & history -------------------------------------------------------------------------------


@pytest.fixture
def conflicted(db, team, monkeypatch):
    rep = _replica(db, team)
    primary, replica = FakeSide(), FakeSide()
    monkeypatch.setattr(source_sync, "sides_for", lambda r, d: (primary, replica))
    base = {"id": 1, "name": "ana", "email": "a@x"}
    key = {"id": 1}
    primary.rows[("users", key_hash(key))] = {**base, "name": "ANA"}
    replica.rows[("users", key_hash(key))] = {**base, "email": "b@x"}
    conflict = SyncConflict(
        replica_id=rep.id,
        table_name="users",
        key_json=key,
        key_hash=key_hash(key),
        status="open",
        base_json=base,
        primary_json={**base, "name": "ANA"},
        replica_json={**base, "email": "b@x"},
        op_primary="update",
        op_replica="update",
    )
    db.add(conflict)
    db.commit()
    device_rpc.mark_online(team["device"].id, "c")
    return {**team, "rep": rep, "conflict": conflict, "primary": primary, "replica": replica, "key": key}


def test_conflict_list_diff_and_suggestion(client, conflicted, auth_headers):
    t, u = conflicted, conflicted["users"]
    assert client.get(_url(t, "/sync-conflicts"), headers=auth_headers(u["viewer"])).status_code == 403
    (item,) = client.get(_url(t, "/sync-conflicts?status=open"), headers=auth_headers(u["dev"])).json()
    assert item["table"] == "users" and item["key"] == {"id": 1}
    assert item["fields"] == [
        {"name": "email", "base": "a@x", "primary": "a@x", "replica": "b@x", "changed_by": "replica"},
        {"name": "name", "base": "ana", "primary": "ANA", "replica": "ana", "changed_by": "primary"},
    ]
    assert item["suggested"] == {"id": 1, "name": "ANA", "email": "b@x"}
    one = client.get(_url(t, f"/sync-conflicts/{item['id']}"), headers=auth_headers(u["dev"])).json()
    assert one["id"] == item["id"]
    assert client.get(_url(t, "/sync-conflicts?status=resolved"), headers=auth_headers(u["dev"])).json() == []


@pytest.mark.parametrize("choice", ["primary", "replica", "manual"])
def test_resolve_applies_to_both_sides(client, db, conflicted, auth_headers, choice):
    t, u = conflicted, conflicted["users"]
    url = _url(t, f"/sync-conflicts/{t['conflict'].id}/resolve")
    body = {"choice": choice}
    if choice == "manual":
        body["value"] = {"id": 1, "name": "ANA", "email": "b@x"}
    assert client.post(url, json=body, headers=auth_headers(u["dev"])).status_code == 403  # not the co-host
    resp = client.post(url, json=body, headers=auth_headers(u["cohost"]))
    assert resp.status_code == 200, resp.text
    expected = {
        "primary": {"id": 1, "name": "ANA", "email": "a@x"},
        "replica": {"id": 1, "name": "ana", "email": "b@x"},
        "manual": {"id": 1, "name": "ANA", "email": "b@x"},
    }[choice]
    assert resp.json()["status"] == "resolved" and resp.json()["resolution"] == choice
    for side in (t["primary"], t["replica"]):
        assert side.row("users", t["key"]) == expected
        assert side.log == []  # written without echo
    db.expire_all()
    (version,) = db.scalars(select(SyncVersion))
    assert version.origin == "resolution" and version.json == expected
    assert db.scalar(select(AuditLog).where(AuditLog.action == "sync.conflict_resolve")) is not None
    assert client.post(url, json=body, headers=auth_headers(u["cohost"])).status_code == 409


def test_resolve_delete_and_bad_values(client, db, conflicted, auth_headers):
    t, u = conflicted, conflicted["users"]
    url = _url(t, f"/sync-conflicts/{t['conflict'].id}/resolve")
    h = auth_headers(u["admin"])
    resp = client.post(url, json={"choice": "manual", "value": {"id": 2, "name": "x"}}, headers=h)
    assert resp.status_code == 422  # can't change the key
    device_rpc.mark_offline(t["device"].id, "c")
    assert client.post(url, json={"choice": "manual", "value": None}, headers=h).status_code == 503
    device_rpc.mark_online(t["device"].id, "c")
    resp = client.post(url, json={"choice": "manual", "value": None}, headers=h)
    assert resp.status_code == 200 and resp.json()["resolved"] is None
    assert t["primary"].row("users", t["key"]) is None and t["replica"].row("users", t["key"]) is None


def test_history_and_restore(client, db, conflicted, auth_headers):
    t, u = conflicted, conflicted["users"]
    rep_id = t["rep"].id
    v1 = source_sync.add_version(db, rep_id, "users", t["key"], {"id": 1, "name": "one", "email": "a@x"}, "primary")
    db.commit()
    source_sync.add_version(db, rep_id, "users", t["key"], {"id": 1, "name": "two", "email": "a@x"}, "replica")
    db.commit()
    key = json.dumps(t["key"])
    url = _url(t, f"/sync-history?table=users&key={key}")
    assert client.get(url, headers=auth_headers(u["viewer"])).status_code == 403
    items = client.get(url, headers=auth_headers(u["dev"])).json()
    assert [i["value"]["name"] for i in items] == ["two", "one"]
    assert client.get(_url(t, "/sync-history?table=users&key=5"), headers=auth_headers(u["dev"])).status_code == 422

    restore = {"table": "users", "key": t["key"], "version_id": v1.id}
    assert (
        client.post(_url(t, "/sync-history/restore"), json=restore, headers=auth_headers(u["dev"])).status_code == 403
    )
    resp = client.post(_url(t, "/sync-history/restore"), json=restore, headers=auth_headers(u["cohost"]))
    assert resp.status_code == 200 and resp.json()["resolved_conflict_id"] == t["conflict"].id
    for side in (t["primary"], t["replica"]):
        assert side.row("users", t["key"])["name"] == "one"
    items = client.get(url, headers=auth_headers(u["dev"])).json()
    assert items[0]["type"] in ("version", "conflict") and {i["origin"] for i in items} >= {"restore", "manual"}
    assert db.scalar(select(AuditLog).where(AuditLog.action == "sync.history_restore")) is not None
    bad = {"table": "orders", "key": t["key"], "version_id": v1.id}
    assert client.post(_url(t, "/sync-history/restore"), json=bad, headers=auth_headers(u["admin"])).status_code == 404
