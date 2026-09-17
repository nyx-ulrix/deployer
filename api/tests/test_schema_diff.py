from app.services.schema_diff import apply_row_counts, diff_schemas


def field(name, data_type="int(11)", nullable=False, **kw):
    base = {
        "name": name,
        "data_type": data_type,
        "nullable": nullable,
        "default": None,
        "primary_key": False,
        "unique": False,
        "indexed": False,
        "foreign_key": None,
        "occurrence": None,
    }
    base.update(kw)
    return base


def entity(name, fields, indexes=None, row_count=0, validator=None, type_="table"):
    return {
        "name": name,
        "type": type_,
        "row_count": row_count,
        "fields": fields,
        "indexes": indexes or [],
        "validator": validator,
    }


def schema(*entities):
    return {
        "source_id": "s",
        "name": "db",
        "kind": "sql",
        "engine": "mariadb",
        "status": "ok",
        "error": None,
        "entities": list(entities),
        "relationships": [],
    }


def test_identical_schemas_have_no_changes():
    s = schema(entity("users", [field("id", primary_key=True)]))
    assert diff_schemas(s, s) == []


def test_added_removed_and_changed_entities():
    before = schema(
        entity(
            "users",
            [field("id", primary_key=True), field("email", "varchar(100)"), field("old")],
            indexes=[
                {"name": "PRIMARY", "fields": ["id"], "unique": True},
                {"name": "ix_email", "fields": ["email"], "unique": False},
            ],
            row_count=3,
        ),
        entity("gone", [field("id")]),
    )
    after = schema(
        entity(
            "users",
            [
                field("id", primary_key=True),
                field("email", "varchar(255)", nullable=True),
                field("created_at", "datetime"),
            ],
            indexes=[
                {"name": "PRIMARY", "fields": ["id"], "unique": True},
                {"name": "ix_email", "fields": ["email"], "unique": True},
                {"name": "ix_created", "fields": ["created_at"], "unique": False},
            ],
            row_count=5,
        ),
        entity("orders", [field("id")]),
    )
    out = {e["name"]: e for e in diff_schemas(before, after)}
    assert [e["name"] for e in diff_schemas(before, after)] == ["gone", "orders", "users"]
    assert out["gone"]["change"] == "removed" and out["orders"]["change"] == "added"
    assert out["orders"]["row_count"] == {"before": None, "after": 0}
    users = out["users"]
    assert users["change"] == "changed"
    fields = {f["name"]: f for f in users["fields"]}
    assert fields["created_at"]["change"] == "added" and fields["created_at"]["before"] is None
    assert fields["old"]["change"] == "removed" and fields["old"]["after"] is None
    assert fields["email"]["change"] == "changed"
    assert fields["email"]["before"]["data_type"] == "varchar(100)" and fields["email"]["after"]["nullable"] is True
    assert "id" not in fields
    assert {i["name"]: i["change"] for i in users["indexes"]} == {"ix_created": "added", "ix_email": "changed"}
    assert users["row_count"] == {"before": 3, "after": 5}
    assert users["validator_changed"] is False


def test_validator_and_row_count_only_changes():
    v1 = {"$jsonSchema": {"required": ["a"]}}
    before = schema(entity("items", [field("_id", "objectId")], validator=v1, row_count=1, type_="collection"))
    after = schema(
        entity("items", [field("_id", "objectId", occurrence=0.5)], validator=None, row_count=1, type_="collection")
    )
    [items] = diff_schemas(before, after)
    assert items["validator_changed"] is True and items["fields"] == []  # occurrence noise ignored
    only_rows = schema(entity("items", [field("_id", "objectId")], validator=v1, row_count=9, type_="collection"))
    [rows] = diff_schemas(before, only_rows)
    assert rows["change"] == "changed" and rows["row_count"] == {"before": 1, "after": 9}


def test_apply_row_counts_and_none_inputs():
    s = schema(entity("users", [], row_count=100), entity("logs", [], row_count=None))
    exact = apply_row_counts(s, {"users": 7})
    assert [e["row_count"] for e in exact["entities"]] == [7, None]
    assert s["entities"][0]["row_count"] == 100  # not mutated
    assert apply_row_counts(None, {"a": 1}) is None
    assert [e["change"] for e in diff_schemas(None, s)] == ["added", "added"]
