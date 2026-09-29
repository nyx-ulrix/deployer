"""Audit A-049: device imports / moves restore a gzip `data` entry streamed, not json.load'ed whole."""

import gzip
import io
import json
import tracemalloc
from types import SimpleNamespace

from app.models import DataSource
from app.services import transfer


class Trickle(io.StringIO):
    """Returns at most 7 characters per read, so every token straddles a buffer boundary."""

    def read(self, n=-1):
        return super().read(7)


def materialize(entry):
    key = "tables" if "tables" in entry else "collections"
    bulk = "rows" if key == "tables" else "documents"
    return {**entry, key: [{**p, bulk: list(p[bulk])} if bulk in p else p for p in entry[key]]}


def test_lazy_entry_matches_json_load():
    entry = {
        "kind": "sql",
        "engine": "mariadb",
        "database_name": "p_x",
        "tables": [
            {"name": "a", "create_sql": "CREATE TABLE a (id int)", "columns": [{"name": "id"}], "rows": [[1], [22]]},
            {"name": "empty", "create_sql": "CREATE TABLE e (id int)", "columns": [], "rows": []},
            {
                "name": "b",
                "columns": [{"name": "v"}],
                "rows": [[123456789], [-1.5e3], ['é " ] } ,'], [{"$base64": "AA=="}]],
            },
            {"name": "no-rows"},
        ],
        "skipped": {"views": 1},
    }
    for text in (json.dumps(entry), json.dumps(entry, indent=2)):
        lazy = transfer.read_data_entry(Trickle(text))
        assert materialize(lazy) == {k: v for k, v in entry.items() if k != "skipped"}


def test_bare_numbers_cut_by_the_buffer():
    entry = {"kind": "sql", "a": 1.25, "b": 1e5, "c": -12.5e-3, "tables": []}
    for pad in range(8):  # shift every cut point across the numbers
        lazy = transfer.read_data_entry(Trickle(" " * pad + json.dumps(entry)))
        assert {**lazy, "tables": list(lazy["tables"])} == entry


def test_unread_rows_are_skipped_in_order():
    entry = {"kind": "nosql", "collections": [{"name": "a", "documents": [{"x": 1}]}, {"name": "b", "documents": []}]}
    names = [c["name"] for c in transfer.read_data_entry(Trickle(json.dumps(entry)))["collections"]]
    assert names == ["a", "b"]


class FakeConn:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def exec_driver_sql(self, sql, params=None):
        self.log.append((sql, len(params) if params else None))

    def commit(self):
        pass


def fake_engine(log):
    return SimpleNamespace(
        dialect=SimpleNamespace(identifier_preparer=SimpleNamespace(quote_identifier=lambda n: f"`{n}`")),
        connect=lambda: FakeConn(log),
        dispose=lambda: None,
    )


def _dump(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write('{"kind":"sql","engine":"mariadb","database_name":"p_x","tables":[')
        fh.write('{"name":"t","create_sql":"CREATE TABLE t (id int, note text)",')
        fh.write('"columns":[{"name":"id"},{"name":"note"}],"rows":[')
        for i in range(rows):
            fh.write(("," if i else "") + json.dumps([i, f"row {i} " + "x" * 80]))
        fh.write("]}]}")


def test_restore_file_streams_in_bounded_memory(tmp_path, monkeypatch):
    log = []
    monkeypatch.setattr(transfer, "decrypt_json", lambda _: {})
    monkeypatch.setattr(transfer.connections, "build_sql_engine", lambda *a, **k: fake_engine(log))
    ds = DataSource(id="d", kind="sql", engine="mariadb", config_encrypted="x", device_id=None)
    rows = 60_000  # ~6 MB of JSON; json.load of it peaks at several times that
    path = tmp_path / "dump.json.gz"
    _dump(path, rows)

    tracemalloc.start()
    try:
        assert transfer.restore_file(ds, path) == (rows, 0)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 3 * 2**20, f"restore peaked at {peak / 2**20:.1f} MB"
    inserts = [n for sql, n in log if sql.startswith("INSERT")]
    assert sum(inserts) == rows and max(inserts) == transfer.BATCH
    assert log[1][0].startswith("CREATE TABLE t")
