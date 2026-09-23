"""Co-hosting sync engine (docs/COHOSTING.md) with in-process fakes for both copies.

A `FakeSide` is one copy: rows in memory plus a change log its "app" writes append to. Changes the
sync applies go through the real `source_sync.apply_changes` and are *not* logged in SQL mode (like
`sql_log_bin = 0` / the skipped origin server_id); in MongoDB mode they are logged, like a change
stream, so echo suppression by version hash is exercised.
"""

import copy
import json
import time

import pytest
from sqlalchemy import select

from app.crypto import encrypt_json
from app.errors import ApiError
from app.models import DataSource, SourceReplica, SyncConflict, SyncVersion
from app.services import device_host, device_rpc, source_sync
from app.services.source_sync import key_hash
from tests import devices_support

make_device = devices_support.make_device  # shared fixtures
fake_device = devices_support.fake_device


class FakeStore:
    def __init__(self, side):
        self.side = side

    def get(self, table, key):
        return copy.deepcopy(self.side.rows.get((table, key_hash(key))))

    def put(self, table, key, row, exists):
        if self.side.reject:
            raise source_sync.WriteRejected(self.side.reject)
        self.side._set(table, key, row, log=self.side.kind == "nosql")

    def commit(self):
        pass

    def rollback(self):
        pass


class FakeSide:
    def __init__(self, kind="sql"):
        self.kind = kind
        self.rows = {}
        self.log = []
        self.skipped = []
        self.fail = None
        self.reject = None
        self.applied_batches = []

    def _set(self, table, key, row, *, log=True):
        k = (table, key_hash(key))
        before = self.rows.get(k)
        if row is None:
            self.rows.pop(k, None)
        else:
            self.rows[k] = copy.deepcopy(row)
        if log:
            self.log.append(
                {
                    "table": table,
                    "key": key,
                    "op": "insert" if before is None else "delete" if row is None else "update",
                    "before": copy.deepcopy(before) if self.kind == "sql" else None,
                    "after": copy.deepcopy(row),
                    "ts": int(time.time()),
                }
            )

    def write(self, table, key, row):  # an app writing to this copy
        self._set(table, key, row)

    def row(self, table, key):
        return self.rows.get((table, key_hash(key)))

    def changes(self, since, limit):
        i = (since or {}).get("i", 0)
        batch = self.log[i : i + limit]
        return {
            "changes": copy.deepcopy(batch),
            "position": {"i": i + len(batch)},
            "skipped_tables": list(self.skipped),
            "more": len(self.log) > i + limit,
        }

    def apply(self, changes):
        if self.fail:
            raise self.fail
        self.applied_batches.append(changes)
        return source_sync.apply_changes(FakeStore(self), copy.deepcopy(changes), self.kind)


@pytest.fixture
def world(db, owner, make_project, make_device, monkeypatch):
    def build(kind="sql"):
        project = make_project(owner, "Shop")
        device, _ = make_device(owner)
        ds = DataSource(
            project_id=project.id,
            name=f"main-{kind}",
            kind=kind,
            engine="mariadb" if kind == "sql" else "mongodb",
            mode="managed",
            database_name="p_shop_abc123",
            config_encrypted=encrypt_json({}),
            status="ok",
        )
        db.add(ds)
        db.flush()
        rep = SourceReplica(
            data_source_id=ds.id,
            device_id=device.id,
            status="syncing",
            position_primary={"i": 0},
            position_replica={"i": 0},
            id_offset=2,
        )
        db.add(rep)
        db.commit()
        primary, replica = FakeSide(kind), FakeSide(kind)
        monkeypatch.setattr(source_sync, "sides_for", lambda r, d: (primary, replica))
        device_rpc.mark_online(device.id, "conn")
        return {"project": project, "device": device, "ds": ds, "rep": rep, "primary": primary, "replica": replica}

    return build


def _seed(w, table, key, row):
    """Same row on both copies, already in sync (positions past it)."""
    for side in (w["primary"], w["replica"]):
        side.rows[(table, key_hash(key))] = copy.deepcopy(row)


def _replica(db, w):
    db.expire_all()
    return db.get(SourceReplica, w["rep"].id)


def _conflicts(db, w, status="open"):
    db.expire_all()
    return list(
        db.scalars(select(SyncConflict).where(SyncConflict.replica_id == w["rep"].id, SyncConflict.status == status))
    )


# --- values & pure helpers ---------------------------------------------------------------------------


def test_value_encoding_round_trips_and_hashes_stably():
    from datetime import date, datetime, timedelta
    from decimal import Decimal

    row = {
        "d": Decimal("1.50"),
        "t": datetime(2026, 9, 23, 1, 2, 3),
        "day": date(2026, 9, 23),
        "dur": timedelta(seconds=90),
        "blob": b"\x00\xff",
        "tags": {"b", "a"},
        "n": None,
    }
    encoded = source_sync.enc_row(row)
    json.dumps(encoded)  # JSON-safe
    assert encoded["tags"] == "a,b"
    assert {k: source_sync.dec(v) for k, v in encoded.items() if k != "tags"} == {
        k: v for k, v in row.items() if k != "tags"
    }
    # TEXT read as bytes on one side and str on the other, and FLOAT noise, hash the same.
    assert source_sync.row_hash({"s": {"$b64": "aGk="}, "f": 0.10000000149011612}) == source_sync.row_hash(
        {"s": "hi", "f": 0.1}
    )


def test_primary_key_update_becomes_delete_and_insert():
    out = source_sync.row_changes("t", ["id"], {"id": 1, "v": "a"}, {"id": 2, "v": "a"}, 5)
    assert [(c["op"], c["key"]) for c in out] == [("delete", {"id": 1}), ("insert", {"id": 2})]


def test_reapplying_a_batch_is_a_no_op():
    """Crash between apply and position update: the replay changes nothing and opens no conflict."""
    source, target = FakeSide(), FakeSide()
    source.write("t", {"id": 1}, {"id": 1, "v": "a"})
    source.write("t", {"id": 1}, {"id": 1, "v": "b"})
    source.write("t", {"id": 2}, {"id": 2, "v": "x"})
    source.write("t", {"id": 2}, None)
    batch = source.changes(None, 100)["changes"]
    first = target.apply(batch)
    # Row 2 was inserted and deleted again: the target already holds the final state (no row).
    assert [o["result"] for o in first] == ["applied", "applied", "skipped", "skipped"]
    again = target.apply(batch)
    assert [o["result"] for o in again] == ["skipped"] * 4
    assert target.row("t", {"id": 1}) == {"id": 1, "v": "b"} and target.row("t", {"id": 2}) is None


# --- rounds -------------------------------------------------------------------------------------------


def test_changes_flow_both_ways_without_echo(db, world):
    w = world()
    w["primary"].write("users", {"id": 1}, {"id": 1, "name": "ana"})
    w["replica"].write("users", {"id": 2}, {"id": 2, "name": "bo"})
    stats = source_sync.sync_round(w["rep"].id)
    assert stats == {"applied": 2, "conflicts": 0}
    for side in (w["primary"], w["replica"]):
        assert side.row("users", {"id": 1}) == {"id": 1, "name": "ana"}
        assert side.row("users", {"id": 2}) == {"id": 2, "name": "bo"}
    rep = _replica(db, w)
    assert rep.status == "syncing" and rep.position_primary == {"i": 1} and rep.position_replica == {"i": 1}
    assert rep.lag_seconds == 0.0 and rep.last_synced_at is not None
    # Nothing comes back: the next round has nothing to do.
    assert source_sync.sync_round(w["rep"].id) == {"applied": 0, "conflicts": 0}
    assert len(w["primary"].log) == 1 and len(w["replica"].log) == 1
    origins = sorted(v.origin for v in db.scalars(select(SyncVersion)))
    assert origins == ["primary", "replica"]


def test_concurrent_edit_opens_conflict_and_other_keys_keep_syncing(db, world):
    w = world()
    base = {"id": 1, "name": "ana", "email": "a@x"}
    _seed(w, "users", {"id": 1}, base)
    w["primary"].write("users", {"id": 1}, {**base, "name": "ANA"})
    w["replica"].write("users", {"id": 1}, {**base, "name": "Ana B"})
    w["primary"].write("users", {"id": 2}, {"id": 2, "name": "cy", "email": "c@x"})
    source_sync.sync_round(w["rep"].id)

    # Neither side overwritten; the other key synced.
    assert w["primary"].row("users", {"id": 1})["name"] == "ANA"
    assert w["replica"].row("users", {"id": 1})["name"] == "Ana B"
    assert w["replica"].row("users", {"id": 2}) == {"id": 2, "name": "cy", "email": "c@x"}
    (conflict,) = _conflicts(db, w)
    assert conflict.table_name == "users" and conflict.key_json == {"id": 1}
    assert conflict.base_json == base
    assert conflict.primary_json["name"] == "ANA" and conflict.replica_json["name"] == "Ana B"
    assert (conflict.op_primary, conflict.op_replica) == ("update", "update")
    assert _replica(db, w).status == "syncing"

    # Later changes to that key update the open conflict instead of syncing.
    w["primary"].write("users", {"id": 1}, {**base, "name": "ANA 2"})
    source_sync.sync_round(w["rep"].id)
    assert w["replica"].row("users", {"id": 1})["name"] == "Ana B"
    (conflict,) = _conflicts(db, w)
    assert conflict.primary_json["name"] == "ANA 2"


def test_delete_versus_update_is_a_conflict(db, world):
    w = world()
    _seed(w, "users", {"id": 1}, {"id": 1, "name": "ana"})
    w["primary"].write("users", {"id": 1}, None)
    w["replica"].write("users", {"id": 1}, {"id": 1, "name": "ana!"})
    source_sync.sync_round(w["rep"].id)
    (conflict,) = _conflicts(db, w)
    assert conflict.primary_json is None and conflict.op_primary == "delete"
    assert conflict.replica_json == {"id": 1, "name": "ana!"}
    assert w["primary"].row("users", {"id": 1}) is None
    assert w["replica"].row("users", {"id": 1}) == {"id": 1, "name": "ana!"}


def test_rejected_write_becomes_a_conflict(db, world):
    w = world()
    w["primary"].write("users", {"id": 3}, {"id": 3, "email": "dup@x"})
    w["replica"].reject = "Duplicate entry 'dup@x' for key 'email'"
    source_sync.sync_round(w["rep"].id)
    (conflict,) = _conflicts(db, w)
    assert conflict.key_json == {"id": 3} and conflict.replica_json is None
    assert _replica(db, w).position_primary == {"i": 1}


def test_tables_without_primary_key_are_reported(db, world):
    w = world()
    w["replica"].skipped = ["logs"]
    source_sync.sync_round(w["rep"].id)
    source_sync.sync_round(w["rep"].id)
    assert _replica(db, w).warnings == [
        {"table": "logs", "message": "No primary key: changes to this table are not synced"}
    ]


def test_positions_advance_only_after_apply(db, world):
    w = world()
    w["primary"].write("users", {"id": 1}, {"id": 1, "name": "ana"})
    w["replica"].fail = ApiError(500, "device_internal_error", "disk full")
    with pytest.raises(ApiError):
        source_sync.sync_round(w["rep"].id)
    rep = _replica(db, w)
    assert rep.position_primary == {"i": 0} and rep.position_replica == {"i": 0}

    # Through the loop: status error with the message, retried later with backoff.
    source_sync._backoff.clear()
    assert source_sync.run_due(now=1000.0) == 1
    rep = _replica(db, w)
    assert rep.status == "error" and "disk full" in rep.error
    assert source_sync.run_due(now=1001.0) == 0  # backing off

    w["replica"].fail = None
    assert source_sync.run_due(now=1000.0 + source_sync.MAX_BACKOFF_S) == 1
    rep = _replica(db, w)
    assert rep.status == "syncing" and rep.error is None and rep.position_primary == {"i": 1}
    assert w["replica"].row("users", {"id": 1}) == {"id": 1, "name": "ana"}


def test_offline_device_keeps_positions_and_status(db, world):
    w = world()
    rep = _replica(db, w)
    rep.last_synced_at = source_sync.utcnow().replace(microsecond=0) - source_sync.timedelta(minutes=5)
    db.commit()
    device_rpc.mark_offline(w["device"].id, "conn")
    w["primary"].write("users", {"id": 1}, {"id": 1})
    assert source_sync.sync_round(w["rep"].id) is None
    rep = _replica(db, w)
    assert rep.status == "syncing" and rep.position_primary == {"i": 0}
    assert rep.lag_seconds >= 300
    assert w["replica"].applied_batches == []

    # Dropping mid-round is not an error either: status unchanged, retried soon.
    device_rpc.mark_online(w["device"].id, "conn")
    w["replica"].fail = device_rpc.offline_error()
    source_sync._backoff.clear()
    source_sync.run_due(now=5000.0)
    assert _replica(db, w).status == "syncing"


def test_mongo_echo_is_suppressed_by_version(db, world):
    w = world("nosql")
    doc_key = {"_id": {"$oid": "65f000000000000000000001"}}
    w["primary"].write("orders", doc_key, {**doc_key, "total": 5})
    source_sync.sync_round(w["rep"].id)
    assert w["replica"].row("orders", doc_key)["total"] == 5
    assert len(w["replica"].log) == 1  # the applied write shows up in the device's change stream
    assert source_sync.sync_round(w["rep"].id) == {"applied": 0, "conflicts": 0}
    assert len(w["primary"].log) == 1 and not _conflicts(db, w)

    # With a known base a later edit on one side applies; edits on both sides conflict.
    w["replica"].write("orders", doc_key, {**doc_key, "total": 6})
    source_sync.sync_round(w["rep"].id)
    assert w["primary"].row("orders", doc_key)["total"] == 6
    w["primary"].write("orders", doc_key, {**doc_key, "total": 7})
    w["replica"].write("orders", doc_key, {**doc_key, "total": 8})
    source_sync.sync_round(w["rep"].id)
    (conflict,) = _conflicts(db, w)
    assert conflict.base_json["total"] == 6
    assert (conflict.primary_json["total"], conflict.replica_json["total"]) == (7, 8)


def test_prune_forgets_old_agreed_versions_but_not_conflicted_keys(db, world):
    w = world()
    old = source_sync.utcnow() - source_sync.timedelta(days=8)
    for table, key in (("a", {"id": 1}), ("b", {"id": 1})):
        v = source_sync.add_version(db, w["rep"].id, table, key, {"id": 1}, "primary")
        v.synced_at = old
    db.add(
        SyncConflict(
            replica_id=w["rep"].id, table_name="b", key_json={"id": 1}, key_hash=key_hash({"id": 1}), status="open"
        )
    )
    db.commit()
    assert source_sync.prune_versions() == 1
    db.expire_all()
    assert [v.table_name for v in db.scalars(select(SyncVersion))] == ["b"]


def test_device_side_speaks_rpc_and_drops_unexpected_fields(owner, make_device, fake_device):
    device, _ = make_device(owner)
    change = {"table": "t", "key": {"id": 1}, "op": "insert", "before": None, "after": {"id": 1}, "ts": 1}

    def handler(method, params):
        if method == "sync.sql_changes":
            assert params["auto_increment"] == {"increment": source_sync.AUTO_INCREMENT_STEP, "offset": 3}
            return {"changes": [{**change, "force": True}], "position": {"gtid": "0-1-2"}, "skipped_tables": []}
        assert method == "sync.sql_apply"
        return {"outcomes": [{"result": "applied", "current": None}]}

    fake_device(device.id, handler)
    side = source_sync.DeviceSide(device.id, "sql", "p_x_abc123", 3)
    out = side.changes({"gtid": ""}, 10)
    assert out["changes"] == [change] and out["position"] == {"gtid": "0-1-2"}  # no `force` from a device
    assert side.apply(out["changes"]) == [{"result": "applied", "current": None}]
    with pytest.raises(ApiError) as exc:
        side.apply([])  # one outcome for zero changes: malformed
    assert exc.value.code == "device_error"


# --- device side: only hosted databases ----------------------------------------------------------------


def test_device_sync_methods_reject_databases_it_does_not_host(set_setting):
    set_setting(
        "device_hosted_credentials",
        json.dumps({"p_hosted_abc123": {"kind": "sql", "username": "u_0123456789ab", "password": "x" * 32}}),
    )
    ctx = device_host.CallContext()
    for method in ("sync.sql_changes", "sync.sql_apply", "sync.mongo_changes", "sync.mongo_apply"):
        with pytest.raises(ApiError) as exc:
            device_host.dispatch(method, {"database_name": "p_other_abc123", "changes": []}, ctx)
        assert exc.value.code == "not_hosted", method
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("sync.sql_changes", {"database_name": "mysql"}, ctx)
    assert exc.value.code == "not_hosted"
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("sync.position", {"kind": "sql", "database_name": "../etc"}, ctx)
    assert exc.value.code == "validation_error"
    # A hosted SQL database is not a MongoDB one.
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("sync.mongo_apply", {"database_name": "p_hosted_abc123", "changes": []}, ctx)
    assert exc.value.code == "not_hosted"
    # Malformed parameters are refused before any database is touched.
    for params in (
        {"database_name": "p_hosted_abc123", "limit": 10**9},
        {"database_name": "p_hosted_abc123", "auto_increment": {"increment": 10, "offset": 1}},
    ):
        with pytest.raises(ApiError) as exc:
            device_host.dispatch("sync.sql_changes", params, ctx)
        assert exc.value.code == "validation_error"
    with pytest.raises(ApiError) as exc:
        device_host.dispatch("sync.sql_apply", {"database_name": "p_hosted_abc123", "changes": [{"table": 1}]}, ctx)
    assert exc.value.code == "validation_error"
    assert {"sync.position", "sync.sql_changes", "sync.sql_apply", "sync.mongo_changes", "sync.mongo_apply"} <= set(
        device_host.capabilities()["methods"]
    )
