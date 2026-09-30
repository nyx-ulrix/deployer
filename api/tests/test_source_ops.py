"""source_ops: local and device-hosted sources share one dispatcher, so the two paths cannot drift (A-108)."""

from types import SimpleNamespace

from app.errors import ApiError
from app.services import ddl_export, device_rpc, introspection, source_ops


def _ds(kind: str, device_id: str | None = None):
    return SimpleNamespace(
        id="ds1", kind=kind, name="main", engine="mariadb", database_name="db1", device_id=device_id, mode="managed"
    )


CALLS = [
    ("sql", "list_rows", ("t",), {"limit": 5}, "rows.list", {"table": "t", "limit": 5}),
    ("sql", "insert_row", ("t", {"a": 1}), {}, "rows.insert", {"table": "t", "values": {"a": 1}}),
    (
        "sql",
        "update_row",
        ("t", {"id": 1}, {"a": 2}),
        {},
        "rows.update",
        {"table": "t", "pk": {"id": 1}, "values": {"a": 2}},
    ),
    ("sql", "delete_row", ("t", {"id": 1}), {}, "rows.delete", {"table": "t", "pk": {"id": 1}}),
    ("sql", "sql_entity", ("t",), {}, "entity", {"name": "t"}),
    ("nosql", "mongo_entity", ("c",), {}, "entity", {"name": "c"}),
    (
        "nosql",
        "list_documents",
        ("c",),
        {"filter_json": None, "limit": 3},
        "documents.list",
        {"name": "c", "filter": None, "limit": 3, "skip": 0},
    ),
    ("nosql", "insert_document", ("c", {"x": 1}), {}, "documents.insert", {"name": "c", "document": {"x": 1}}),
    (
        "nosql",
        "update_document",
        ("c", "id1", {"x": 2}, None),
        {},
        "documents.update",
        {"name": "c", "doc_id": "id1", "set": {"x": 2}, "unset": None},
    ),
    ("nosql", "delete_document", ("c", "id1"), {}, "documents.delete", {"name": "c", "doc_id": "id1"}),
]


def test_wrappers_send_the_same_op_locally_and_to_the_device(monkeypatch):
    local, remote = [], []
    monkeypatch.setattr(source_ops, "run_local", lambda ds, op, args=None: local.append((op, args)) or {})
    monkeypatch.setattr(device_rpc, "call", lambda dev, method, params, timeout: remote.append(params) or {})
    for kind, fn, args, kwargs, op, expected in CALLS:
        local.clear()
        remote.clear()
        getattr(source_ops, fn)(_ds(kind), *args, **kwargs)
        getattr(source_ops, fn)(_ds(kind, "dev1"), *args, **kwargs)
        assert local == [(op, expected)], fn
        assert remote[0]["op"] == op and remote[0]["args"] == expected, fn


def test_export_and_introspect_mix_local_and_device_sources(monkeypatch):
    monkeypatch.setattr(ddl_export, "export_sql_source", lambda ds, now=None: "-- local\n")
    monkeypatch.setattr(introspection, "introspect_source", lambda ds, sample: {"status": "ok", "local": True})

    def device(dev, method, params, timeout):
        if dev == "bad":
            raise ApiError(503, "device_offline", "The host device is offline")
        return 42 if params["op"] == "ddl_export" else {"status": "ok", "entities": []}

    monkeypatch.setattr(device_rpc, "call", device)
    sources = [_ds("sql"), _ds("sql", "dev1"), _ds("sql", "bad")]
    text = source_ops.export_sources(sources, "sql")
    assert text.startswith("-- local\n")
    assert "could not be exported: Malformed export from host device" in text
    assert "could not be exported: The host device is offline" in text

    out = source_ops.introspect_sources(sources)
    assert out[0] == {"status": "ok", "local": True}
    assert out[1]["status"] == "ok" and out[1]["source_id"] == "ds1"
    assert out[2]["status"] == "error" and out[2]["error"] == "The host device is offline"
