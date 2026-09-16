from app.services import conventions as c


def field(name, data_type="int", **kw):
    base = {
        "name": name,
        "data_type": data_type,
        "nullable": False,
        "default": None,
        "primary_key": False,
        "unique": False,
        "indexed": False,
        "foreign_key": None,
        "occurrence": None,
    }
    base.update(kw)
    return base


def entity(name, fields, type_="table"):
    return {"name": name, "type": type_, "row_count": 0, "fields": fields, "indexes": [], "validator": None}


def sql_source(entities, sid="s1"):
    return {
        "source_id": sid,
        "name": "db",
        "kind": "sql",
        "engine": "mariadb",
        "status": "ok",
        "error": None,
        "entities": entities,
        "relationships": [],
    }


def mongo_source(entities, rels=None, sid="m1"):
    return {
        "source_id": sid,
        "name": "mongo",
        "kind": "nosql",
        "engine": "mongodb",
        "status": "ok",
        "error": None,
        "entities": entities,
        "relationships": rels or [],
    }


def rules(issues):
    return sorted({(i["rule"], i["entity"], i["field"]) for i in issues})


def ts_fields():
    return [field("created_at", "datetime"), field("updated_at", "datetime")]


# --- inflection -----------------------------------------------------------------------------


def test_pluralize_and_singularize():
    assert c.pluralize("user") == "users"
    assert c.pluralize("category") == "categories"
    assert c.pluralize("key") == "keys"
    assert c.pluralize("address") == "addresses"
    assert c.pluralize("box") == "boxes"
    assert c.pluralize("person") == "people"
    assert c.pluralize("order_item") == "order_items"
    assert c.pluralize("data") == "data"
    assert c.singularize("users") == "user"
    assert c.singularize("categories") == "category"
    assert c.singularize("statuses") == "status"
    assert c.singularize("addresses") == "address"
    assert c.singularize("people") == "person"
    assert c.singularize("order_items") == "order_item"
    assert c.singularize("status") == "status"


def test_is_plural():
    for name in ("users", "order_items", "people", "data", "categories", "news"):
        assert c.is_plural(name), name
    for name in ("user", "status", "address", "person", "analysis"):
        assert not c.is_plural(name), name


def test_match_entity():
    names = ["users", "categories", "order_items", "people"]
    assert c.match_entity("user_id", names) == "users"
    assert c.match_entity("category_id", names) == "categories"
    assert c.match_entity("userId", names) == "users"
    assert c.match_entity("orderItemId", names) == "order_items"
    assert c.match_entity("person_id", names) == "people"
    assert c.match_entity("profile.user_id", names) == "users"
    assert c.match_entity("id", names) is None
    assert c.match_entity("userId", names, snake_only=True) is None
    assert c.match_entity("team_id", names) is None


def test_split_type_union():
    assert c.split_type_union("int|array<int|string>|null") == ["int", "array<int|string>", "null"]


# --- naming ---------------------------------------------------------------------------------


def test_n1_n2_n3_n4():
    src = sql_source(
        [
            entity(
                "UserAccount",
                [
                    field("id", primary_key=True, indexed=True),
                    field("firstName", "varchar(10)"),
                    field("order", "int"),
                    *ts_fields(),
                ],
            ),
        ]
    )
    found = rules(c.check_conventions([src]))
    assert ("N1", "UserAccount", None) in found
    assert ("N2", "UserAccount", None) in found
    assert ("N3", "UserAccount", "firstName") in found
    assert ("N4", "UserAccount", "order") in found


def test_n4_reserved_table_name_and_no_false_positives():
    src = sql_source([entity("order", [field("id", primary_key=True), *ts_fields()])])
    found = rules(c.check_conventions([src]))
    assert ("N4", "order", None) in found
    good = sql_source([entity("orders", [field("id", primary_key=True), *ts_fields()])])
    assert c.check_conventions([good]) == []


def test_n5_fk_naming():
    users = entity("users", [field("id", "bigint", primary_key=True), *ts_fields()])
    posts = entity(
        "posts",
        [
            field("id", "bigint", primary_key=True),
            field("author", "bigint", indexed=True, foreign_key={"entity": "users", "field": "id"}),
            field("user_id", "bigint", indexed=True, foreign_key={"entity": "users", "field": "id"}),
            field("editor_user_id", "bigint", indexed=True, foreign_key={"entity": "users", "field": "id"}),
            *ts_fields(),
        ],
    )
    found = rules(c.check_conventions([sql_source([users, posts])]))
    assert ("N5", "posts", "author") in found
    assert ("N5", "posts", "user_id") not in found
    assert ("N5", "posts", "editor_user_id") not in found


def test_n6_boolean_prefix():
    src = sql_source(
        [
            entity(
                "users",
                [
                    field("id", primary_key=True),
                    field("active", "tinyint(1)"),
                    field("is_admin", "tinyint(1)"),
                    *ts_fields(),
                ],
            )
        ]
    )
    found = rules(c.check_conventions([src]))
    assert ("N6", "users", "active") in found
    assert ("N6", "users", "is_admin") not in found
    m = mongo_source(
        [entity("users", [field("_id", "objectId", primary_key=True), field("verified", "bool")], "collection")]
    )
    assert ("N6", "users", "verified") in rules(c.check_conventions([m]))


# --- structure ------------------------------------------------------------------------------


def test_s1_s2_s5_s6():
    src = sql_source(
        [
            entity("logs", [field("message", "text")]),
            entity("users", [field("user_key", "int", primary_key=True, nullable=True)]),
        ]
    )
    found = rules(c.check_conventions([src]))
    assert ("S1", "logs", None) in found
    assert ("S2", "users", "user_key") in found
    assert ("S5", "logs", None) in found
    assert ("S6", "users", "user_key") in found


def test_s3_s4():
    users = entity("users", [field("id", primary_key=True, indexed=True), *ts_fields()])
    orders = entity(
        "orders",
        [
            field("id", primary_key=True, indexed=True),
            field("user_id", foreign_key={"entity": "users", "field": "id"}),
            *ts_fields(),
        ],
    )
    items = entity(
        "order_items",
        [
            field("id", primary_key=True, indexed=True),
            field("order_id"),
            field("sku_id"),
            *ts_fields(),
        ],
    )
    found = rules(c.check_conventions([sql_source([users, orders, items])]))
    assert ("S3", "orders", "user_id") in found
    assert ("S4", "order_items", "order_id") in found
    assert ("S4", "order_items", "sku_id") not in found


def test_mongo_s4_s7_s8():
    users = entity("users", [field("_id", "objectId", primary_key=True, indexed=True, unique=True)], "collection")
    orders = entity(
        "orders",
        [
            field("_id", "objectId", primary_key=True, indexed=True, unique=True),
            field("user_id", "objectId", occurrence=1.0),
            field("userId", "objectId", occurrence=0.5),
            field("total", "int|string"),
            field("tags", "array<int|string>"),
        ],
        "collection",
    )
    rels = [
        {
            "from_entity": "orders",
            "from_fields": ["user_id"],
            "to_entity": "users",
            "to_fields": ["_id"],
            "cardinality": "many_to_one",
            "origin": "inferred",
        },
        {
            "from_entity": "orders",
            "from_fields": ["userId"],
            "to_entity": "users",
            "to_fields": ["_id"],
            "cardinality": "many_to_one",
            "origin": "inferred",
        },
    ]
    found = rules(c.check_conventions([mongo_source([users, orders], rels)]))
    assert ("S4", "orders", "user_id") in found
    assert ("S8", "orders", "user_id") not in found  # already reported as S4
    assert ("S8", "orders", "userId") in found
    assert ("S7", "orders", "total") in found
    assert ("S7", "orders", "tags") not in found
    assert ("N3", "orders", "userId") in found
    assert not any(r[0] in ("S1", "S5") for r in found)


def test_errored_sources_are_skipped():
    src = sql_source([entity("BadName", [])])
    src["status"] = "error"
    assert c.check_conventions([src]) == []


# --- links ----------------------------------------------------------------------------------


def _link(**kw):
    base = {
        "id": "l1",
        "from_source_id": "m1",
        "from_entity": "orders",
        "from_field": "user_id",
        "to_source_id": "s1",
        "to_entity": "users",
        "to_field": "id",
        "cardinality": "many_to_one",
        "note": None,
        "created_at": None,
    }
    base.update(kw)
    return base


def test_x1_x2_x3():
    sql = sql_source(
        [
            entity(
                "users",
                [
                    field("id", "bigint(20) unsigned", primary_key=True, indexed=True),
                    field("uuid", "char(36)"),
                    *ts_fields(),
                ],
            )
        ]
    )
    mongo = mongo_source(
        [
            entity(
                "orders",
                [
                    field("_id", "objectId", primary_key=True, indexed=True),
                    field("user_id", "long"),
                    field("user_uuid", "string"),
                    field("user_oid", "objectId"),
                ],
                "collection",
            )
        ]
    )
    links = [
        _link(),
        _link(id="l2", from_field="user_uuid", to_field="uuid"),
        _link(id="l3", from_field="user_oid", to_field="id"),
        _link(id="l4", from_field="missing"),
        _link(id="l5", to_source_id="nope"),
    ]
    found = rules(c.check_links([sql, mongo], links))
    assert ("X3", "orders", "user_id") in found
    assert ("X2", "orders", "user_id") not in found
    assert ("X2", "orders", "user_uuid") not in found
    assert ("X2", "orders", "user_oid") in found
    assert ("X1", "orders", "missing") in found
    assert ("X1", "users", "id") in found  # l5: unknown source


def test_types_compatible():
    assert c.types_compatible("bigint(20)", "sql", "int", "nosql")
    assert c.types_compatible("char(36)", "sql", "string", "nosql")
    assert c.types_compatible("varchar(24)", "sql", "objectId", "nosql")
    assert not c.types_compatible("datetime", "sql", "string", "nosql")
    assert c.types_compatible("timestamp", "sql", "date", "nosql")
    assert c.types_compatible("uuid", "sql", "string|null", "nosql")
