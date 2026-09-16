import datetime as dt
import decimal

import pytest
from bson import ObjectId
from sqlalchemy import create_engine

from app.errors import ApiError
from app.services import data_browser as b


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'data.db').as_posix()}")
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(50) NOT NULL, "
            "price NUMERIC(10,2), blob BLOB, seen_at DATETIME)"
        )
        conn.exec_driver_sql("CREATE TABLE logs (message TEXT)")
        conn.exec_driver_sql("INSERT INTO logs (message) VALUES ('hi')")
    yield eng
    eng.dispose()


def test_encode_value():
    assert b.encode_value(b"\x00\x01") == {"$base64": "AAE="}
    assert b.encode_value(decimal.Decimal("1.50")) == "1.50"
    assert b.encode_value(dt.datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02T03:04:05"
    assert b.encode_value(dt.date(2024, 1, 2)) == "2024-01-02"
    assert b.encode_value(dt.timedelta(hours=26, minutes=3, seconds=4)) == "26:03:04"
    assert b.encode_value(float("nan")) == "nan"


def test_sql_crud(engine):
    inserted = b.insert_row(
        engine,
        "items",
        {"name": "Widget", "price": "9.99", "blob": {"$base64": "AAE="}, "seen_at": "2024-05-01T10:00:00"},
    )["row"]
    assert inserted["id"] == 1
    assert inserted["name"] == "Widget"
    assert inserted["blob"] == {"$base64": "AAE="}
    assert inserted["seen_at"] == "2024-05-01T10:00:00"
    b.insert_row(engine, "items", {"name": "Gadget"})

    page = b.list_rows(engine, "items", limit=1, offset=0, order_by="name", order="asc")
    assert page["columns"] == ["id", "name", "price", "blob", "seen_at"]
    assert page["primary_key"] == ["id"]
    assert page["total"] == 2
    assert [r["name"] for r in page["rows"]] == ["Gadget"]

    updated = b.update_row(engine, "items", {"id": 1}, {"name": "Widget 2"})["row"]
    assert updated["name"] == "Widget 2"
    assert b.delete_row(engine, "items", {"id": 1}) == {"ok": True}
    with pytest.raises(ApiError) as err:
        b.delete_row(engine, "items", {"id": 1})
    assert err.value.code == "row_not_found"


def test_sql_validation(engine):
    with pytest.raises(ApiError) as err:
        b.list_rows(engine, "items", order_by="name; DROP TABLE items")
    assert err.value.code == "unknown_column"
    with pytest.raises(ApiError) as err:
        b.insert_row(engine, "items", {"nope": 1})
    assert err.value.code == "unknown_column"
    with pytest.raises(ApiError) as err:
        b.update_row(engine, "items", {"name": "x"}, {"name": "y"})
    assert err.value.code == "invalid_primary_key"
    with pytest.raises(ApiError) as err:
        b.list_rows(engine, "missing")
    assert err.value.status_code == 404
    with pytest.raises(ApiError) as err:
        b.insert_row(engine, "items", {"name": None})
    assert err.value.code == "query_failed"


def test_tables_without_pk_are_read_only(engine):
    page = b.list_rows(engine, "logs")
    assert page["rows"] == [{"message": "hi"}] and page["primary_key"] == []
    for call in (
        lambda: b.insert_row(engine, "logs", {"message": "x"}),
        lambda: b.update_row(engine, "logs", {}, {"message": "x"}),
        lambda: b.delete_row(engine, "logs", {}),
    ):
        with pytest.raises(ApiError) as err:
            call()
        assert err.value.status_code == 409 and err.value.code == "no_primary_key"


def test_list_rows_limit_is_capped(engine):
    assert b.list_rows(engine, "items", limit=10_000)["rows"] == []


@pytest.mark.parametrize(
    "value",
    [
        {"$where": "sleep(100)"},
        {"a": {"$function": {"body": "x", "args": [], "lang": "js"}}},
        {"$expr": {"$eq": [{"$function": {"body": "x"}}, 1]}},
        {"$or": [{"a": 1}, {"$where": "1"}]},
        [{"$group": {"_id": None, "x": {"$accumulator": {}}}}],
    ],
)
def test_forbidden_operators(value):
    assert b.find_forbidden_operator(value)
    with pytest.raises(ApiError) as err:
        b.parse_ejson(value, "filter")
    assert err.value.code == "forbidden_operator"


def test_parse_ejson_relaxed_and_ids():
    oid = ObjectId()
    parsed = b.parse_ejson(
        '{"_id": {"$oid": "' + str(oid) + '"}, "n": {"$numberLong": "5"}, "d": {"$date": "2024-01-01T00:00:00Z"}}',
        "filter",
    )
    assert parsed["_id"] == oid and parsed["n"] == 5
    assert isinstance(parsed["d"], dt.datetime)
    assert b.find_forbidden_operator({"a": {"$gt": 1}, "b": {"$in": [1, 2]}}) is None
    with pytest.raises(ApiError) as err:
        b.parse_ejson("{not json", "filter")
    assert err.value.code == "invalid_json"
    assert b.id_candidates(str(oid)) == [oid, str(oid)]
    assert b.id_candidates("custom-id") == ["custom-id"]
    relaxed = b.to_relaxed({"_id": oid, "d": dt.datetime(2024, 1, 1)})
    assert relaxed["_id"] == {"$oid": str(oid)}
    assert "$date" in relaxed["d"]
