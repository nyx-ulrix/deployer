import datetime as dt
import uuid

from bson import Binary, Decimal128, Int64, ObjectId
from sqlalchemy import create_engine

from app.services import introspection as intro


def test_analyze_documents_types_occurrence_and_nesting():
    docs = [
        {"_id": ObjectId(), "name": "a", "age": 1, "address": {"city": "X", "geo": {"lat": 1.5}}, "tags": ["a", 1]},
        {"_id": ObjectId(), "name": "b", "age": "2", "address": {"city": "Y"}, "tags": []},
        {"_id": ObjectId(), "name": None, "big": Int64(5), "created": dt.datetime(2024, 1, 1)},
        {"_id": ObjectId(), "name": "d", "price": Decimal128("1.5"), "uid": uuid.uuid4(), "bin": Binary(b"x", 0)},
    ]
    fields = {f["name"]: f for f in intro.analyze_documents(docs)}
    assert list(fields)[0] == "_id"
    assert fields["_id"]["data_type"] == "objectId" and fields["_id"]["primary_key"]
    assert fields["name"]["data_type"] == "string"
    assert fields["name"]["nullable"] is True
    assert fields["name"]["occurrence"] == 1.0
    assert fields["age"]["data_type"] == "int|string"
    assert fields["age"]["occurrence"] == 0.5
    assert fields["address"]["data_type"] == "object"
    assert fields["address.city"]["occurrence"] == 0.5
    assert fields["address.geo.lat"]["data_type"] == "double"
    assert fields["tags"]["data_type"] == "array|array<int|string>"
    assert fields["big"]["data_type"] == "long"
    assert fields["created"]["data_type"] == "date"
    assert fields["price"]["data_type"] == "decimal"
    assert fields["uid"]["data_type"] == "uuid"
    assert fields["bin"]["data_type"] == "binData"


def test_analyze_documents_depth_limit():
    doc = {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}
    names = [f["name"] for f in intro.analyze_documents([doc], max_depth=4)]
    assert "a.b.c.d" in names
    assert "a.b.c.d.e" not in names


def test_mongo_indexes_and_relationships():
    info = {
        "_id_": {"key": [("_id", 1)], "v": 2},
        "user_id_1": {"key": [("user_id", 1)], "v": 2},
        "email_1": {"key": [("email", 1)], "unique": True, "v": 2},
        "text": {"key": [("_fts", "text"), ("_ftsx", 1)], "weights": {"title": 1, "body": 1}, "v": 2},
    }
    indexes = intro.mongo_indexes(info)
    by = {i["name"]: i for i in indexes}
    assert by["_id_"]["unique"] and by["email_1"]["unique"] and not by["user_id_1"]["unique"]
    assert by["text"]["fields"] == ["title", "body"]

    fields = intro.analyze_documents([{"_id": 1, "user_id": ObjectId(), "email": "x", "authorId": ObjectId()}])
    intro.apply_mongo_indexes(fields, indexes)
    fmap = {f["name"]: f for f in fields}
    assert fmap["user_id"]["indexed"] and not fmap["user_id"]["unique"]
    assert fmap["email"]["unique"]

    entities = [
        {"name": "orders", "fields": fields},
        {"name": "users", "fields": []},
        {"name": "authors", "fields": []},
    ]
    rels = intro.infer_mongo_relationships(entities)
    pairs = {(r["from_fields"][0], r["to_entity"]) for r in rels}
    assert pairs == {("user_id", "users"), ("authorId", "authors")}


def _raw(name, columns, pk=(), fks=(), indexes=(), uniques=()):
    return {
        "name": name,
        "row_count": 3,
        "columns": [{"name": c, "type": t, "nullable": n, "default": None, "extra": ""} for c, t, n in columns],
        "pk": list(pk),
        "fks": list(fks),
        "indexes": list(indexes),
        "unique_constraints": list(uniques),
    }


def test_build_sql_entities():
    raw = [
        _raw(
            "users",
            [("id", "bigint(20) unsigned", False), ("email", "varchar(255)", False)],
            pk=["id"],
            indexes=[{"name": "uq_email", "columns": ["email"], "unique": True}],
        ),
        _raw(
            "profiles",
            [("id", "bigint(20)", False), ("user_id", "bigint(20)", False)],
            pk=["id"],
            fks=[{"name": "fk1", "columns": ["user_id"], "ref_table": "users", "ref_columns": ["id"]}],
            indexes=[{"name": "uq_user", "columns": ["user_id"], "unique": True}],
        ),
        _raw(
            "orders",
            [("id", "int", False), ("user_id", "int", True), ("category_id", "int", True)],
            pk=["id"],
            fks=[{"name": "fk2", "columns": ["user_id"], "ref_table": "users", "ref_columns": ["id"]}],
        ),
        _raw("categories", [("id", "int", False)], pk=["id"]),
    ]
    entities, rels = intro.build_sql_entities(raw)
    users = next(e for e in entities if e["name"] == "users")
    f = {x["name"]: x for x in users["fields"]}
    assert f["id"]["primary_key"] and f["id"]["unique"] and f["id"]["indexed"]
    assert f["email"]["unique"] and f["email"]["data_type"] == "varchar(255)"
    assert users["indexes"] == [{"name": "uq_email", "fields": ["email"], "unique": True}]
    orders = {x["name"]: x for x in next(e for e in entities if e["name"] == "orders")["fields"]}
    assert orders["user_id"]["foreign_key"] == {"entity": "users", "field": "id"}
    assert orders["user_id"]["indexed"] is False
    got = {(r["from_entity"], tuple(r["from_fields"]), r["to_entity"], r["cardinality"], r["origin"]) for r in rels}
    assert ("profiles", ("user_id",), "users", "one_to_one", "foreign_key") in got
    assert ("orders", ("user_id",), "users", "many_to_one", "foreign_key") in got
    assert ("orders", ("category_id",), "categories", "many_to_one", "inferred") in got
    assert len(got) == 3


def test_introspect_sql_with_sqlite_inspector(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, "
            "CONSTRAINT uq_email UNIQUE (email))"
        )
        conn.exec_driver_sql(
            "CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), title TEXT DEFAULT 'x')"
        )
        conn.exec_driver_sql("CREATE INDEX ix_posts_user ON posts (user_id)")
    entities, rels = intro.introspect_sql(engine)
    names = sorted(e["name"] for e in entities)
    assert names == ["posts", "users"]
    posts = {f["name"]: f for f in next(e for e in entities if e["name"] == "posts")["fields"]}
    assert posts["user_id"]["foreign_key"] == {"entity": "users", "field": "id"}
    assert posts["user_id"]["indexed"]
    assert posts["title"]["default"] is not None
    users = {f["name"]: f for f in next(e for e in entities if e["name"] == "users")["fields"]}
    assert users["email"]["unique"] and not users["email"]["nullable"]
    assert rels == [
        {
            "from_entity": "posts",
            "from_fields": ["user_id"],
            "to_entity": "users",
            "to_fields": ["id"],
            "cardinality": "many_to_one",
            "origin": "foreign_key",
        }
    ]
    engine.dispose()
