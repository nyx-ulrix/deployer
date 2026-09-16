import io
import json
import zipfile
from datetime import UTC, datetime

from bson import ObjectId

from app.services import ddl_export
from app.services.introspection import analyze_documents

NOW = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)


def test_topo_sort_tables():
    tables = ["order_items", "orders", "products", "users", "categories"]
    deps = {
        "order_items": {"orders", "products"},
        "orders": {"users"},
        "products": {"categories"},
        "users": {"users"},  # self reference
    }
    order = ddl_export.topo_sort_tables(tables, deps)
    assert sorted(order) == sorted(tables)
    for table, needs in deps.items():
        for dep in needs - {table}:
            assert order.index(dep) < order.index(table)


def test_topo_sort_cycle_is_tolerated():
    order = ddl_export.topo_sort_tables(["a", "b", "c"], {"a": {"b"}, "b": {"a"}, "c": {"a"}})
    assert sorted(order) == ["a", "b", "c"]
    assert order.index("c") > order.index("a")


def test_render_sql_script_mysql():
    text = ddl_export.render_sql_script(
        source_name="main",
        engine="mariadb",
        database="p_demo_abc123",
        statements=["CREATE TABLE `users` (\n  `id` int NOT NULL\n)", "CREATE TABLE `posts` (`id` int);"],
        now=NOW,
    )
    assert text.startswith("-- Deployer schema export\n-- Source: main (mariadb)")
    assert "-- Generated: 2026-09-16 10:00:00 UTC" in text
    assert text.index("SET FOREIGN_KEY_CHECKS=0;") < text.index("CREATE TABLE `users`")
    assert text.index("CREATE TABLE `posts` (`id` int);") < text.index("SET FOREIGN_KEY_CHECKS=1;")
    assert ";;" not in text


def test_render_sql_script_postgres_has_no_fk_checks():
    text = ddl_export.render_sql_script(source_name="pg", engine="postgresql", database="app", statements=[], now=NOW)
    assert "FOREIGN_KEY_CHECKS" not in text
    assert "(no tables)" in text


def test_inferred_json_schema():
    docs = [
        {"_id": ObjectId(), "name": "a", "age": 3, "address": {"city": "x"}},
        {"_id": ObjectId(), "name": "b", "address": {"city": "y", "zip": "1"}},
    ]
    schema = ddl_export.inferred_json_schema(analyze_documents(docs))["$jsonSchema"]
    assert schema["bsonType"] == "object"
    assert set(schema["required"]) == {"_id", "name", "address"}
    assert schema["properties"]["_id"]["bsonType"] == "objectId"
    assert schema["properties"]["age"]["bsonType"] == "int"
    addr = schema["properties"]["address"]
    assert addr["bsonType"] == "object"
    assert addr["required"] == ["city"]
    assert addr["properties"]["zip"]["bsonType"] == "string"


def test_render_mongo_script():
    fields = analyze_documents([{"_id": ObjectId(), "email": "a@b.c"}])
    text = ddl_export.render_mongo_script(
        source_name="docs",
        database="p_demo_abc123",
        collections=[
            {
                "name": "users",
                "options": {},
                "indexes": {
                    "_id_": {"key": [("_id", 1)], "v": 2},
                    "email_1": {"key": [("email", 1)], "unique": True, "v": 2},
                },
                "fields": fields,
            },
            {
                "name": "orders",
                "options": {"validator": {"$jsonSchema": {"bsonType": "object", "required": ["total"]}}},
                "indexes": {"_id_": {"key": [("_id", 1)], "v": 2}},
            },
            {"name": "active_users", "type": "view", "options": {"viewOn": "users", "pipeline": [{"$match": {}}]}},
        ],
        now=NOW,
    )
    assert 'const database = db.getSiblingDB("p_demo_abc123");' in text
    assert 'database.createCollection("users");' in text
    # inferred validator is commented out
    inferred = [ln for ln in text.splitlines() if "collMod" in ln]
    assert inferred and all(ln.startswith("// ") for ln in inferred)
    assert 'database.getCollection("users").createIndex(EJSON.deserialize({"email": 1}), ' in text
    assert '"unique": true' in text
    assert "_id_" not in text
    assert 'database.createCollection("orders", EJSON.deserialize({' in text
    assert '"$jsonSchema"' in text
    assert 'database.createView("active_users", "users"' in text
    # the orders collection has a validator, so no inferred one for it
    assert text.count("collMod") == 1


def test_index_key_and_options_text_index():
    key, options = ddl_export.index_key_and_options(
        "title_text",
        {
            "key": [("_fts", "text"), ("_ftsx", 1)],
            "weights": {"title": 1},
            "default_language": "english",
            "textIndexVersion": 3,
            "v": 2,
        },
    )
    assert key == {"title": "text"}
    assert options == {"name": "title_text", "weights": {"title": 1}, "default_language": "english"}


def test_build_bundle():
    data = ddl_export.build_bundle(
        project_name="Demo", sql_text="-- sql", mongo_text="// js", links=[{"id": "l1"}], now=NOW
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert sorted(zf.namelist()) == ["README.md", "links.json", "schema.mongo.js", "schema.sql"]
        assert zf.read("schema.sql") == b"-- sql"
        assert json.loads(zf.read("links.json")) == [{"id": "l1"}]
        assert b"schema.sql" in zf.read("README.md")
