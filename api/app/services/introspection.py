"""Schema introspection -> `SourceSchema` dicts (docs/API.md "Schema").

SQL: MariaDB/MySQL use `information_schema` directly (four queries for the whole database, full
`COLUMN_TYPE` text); other dialects (PostgreSQL, sqlite in tests) use SQLAlchemy's inspector.
Both paths produce the same "raw table" dicts which `build_sql_source` turns into entities and
relationships (pure, unit-tested).

MongoDB: `$sample`s documents per collection and infers field paths/types (`analyze_documents`,
pure), plus indexes, `$jsonSchema` validators and estimated counts.
"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import json
import re
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from bson import Binary, Code, Decimal128, Int64, MaxKey, MinKey, ObjectId, Regex, Timestamp, json_util
from bson.dbref import DBRef
from sqlalchemy import Engine, inspect, text

from app.models import DataSource
from app.services import connections
from app.services.conventions import match_entity, reference_base

DEFAULT_SAMPLE = 200
MAX_SAMPLE = 1000
MAX_DEPTH = 4


# =============================================================================================
# SQL
# =============================================================================================


def raw_tables_mysql(engine: Engine, only_table: str | None = None) -> list[dict]:
    where_t = " AND TABLE_NAME = :t" if only_table else ""
    params = {"t": only_table} if only_table else {}
    tables: dict[str, dict] = {}
    with engine.connect() as conn:
        for name, rows in conn.execute(
            text(
                "SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'" + where_t + " ORDER BY TABLE_NAME"
            ),
            params,
        ):
            tables[name] = {
                "name": name,
                "row_count": int(rows) if rows is not None else None,
                "columns": [],
                "pk": [],
                "fks": [],
                "indexes": [],
                "unique_constraints": [],
            }
        for tname, cname, ctype, nullable, default, extra in conn.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
                + where_t
                + " ORDER BY TABLE_NAME, ORDINAL_POSITION"
            ),
            params,
        ):
            if tname not in tables:
                continue
            default_text = None if default is None or (default == "NULL" and nullable == "YES") else str(default)
            tables[tname]["columns"].append(
                {
                    "name": cname,
                    "type": _s(ctype),
                    "nullable": nullable == "YES",
                    "default": default_text,
                    "extra": _s(extra) or "",
                }
            )
        index_cols: dict[tuple[str, str], dict] = {}
        for tname, iname, non_unique, cname in conn.execute(
            text(
                "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE()" + where_t + " ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
            ),
            params,
        ):
            if tname not in tables:
                continue
            if iname == "PRIMARY":
                tables[tname]["pk"].append(cname)
                continue
            key = (tname, iname)
            if key not in index_cols:
                index_cols[key] = {"name": iname, "columns": [], "unique": int(non_unique) == 0}
                tables[tname]["indexes"].append(index_cols[key])
            if cname is not None:
                index_cols[key]["columns"].append(cname)
        fks: dict[tuple[str, str], dict] = {}
        for cname_, tname, col, ref_t, ref_c in conn.execute(
            text(
                "SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE() "
                "AND REFERENCED_TABLE_NAME IS NOT NULL"
                + where_t
                + " ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION"
            ),
            params,
        ):
            if tname not in tables:
                continue
            key = (tname, cname_)
            if key not in fks:
                fks[key] = {"name": cname_, "columns": [], "ref_table": ref_t, "ref_columns": []}
                tables[tname]["fks"].append(fks[key])
            fks[key]["columns"].append(col)
            fks[key]["ref_columns"].append(ref_c)
    return list(tables.values())


def _s(value: Any) -> Any:
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", "replace")
    return value


def _compile_type(col_type: Any, dialect: Any) -> str:
    try:
        return col_type.compile(dialect=dialect)
    except Exception:  # noqa: BLE001
        return str(col_type)


def raw_tables_inspector(engine: Engine, only_table: str | None = None) -> list[dict]:
    insp = inspect(engine)
    names = [only_table] if only_table else insp.get_table_names()
    counts = approximate_row_counts(engine)
    out = []
    for name in names:
        columns = [
            {
                "name": c["name"],
                "type": _compile_type(c["type"], engine.dialect),
                "nullable": bool(c.get("nullable", True)),
                "default": None if c.get("default") is None else str(c.get("default")),
                "extra": "auto_increment" if c.get("autoincrement") is True else "",
            }
            for c in insp.get_columns(name)
        ]
        pk = list((insp.get_pk_constraint(name) or {}).get("constrained_columns") or [])
        fks = [
            {
                "name": fk.get("name"),
                "columns": list(fk["constrained_columns"]),
                "ref_table": fk["referred_table"],
                "ref_columns": list(fk["referred_columns"]),
            }
            for fk in insp.get_foreign_keys(name)
        ]
        indexes = [
            {
                "name": ix.get("name"),
                "columns": [c for c in ix.get("column_names", []) if c],
                "unique": bool(ix.get("unique")),
            }
            for ix in insp.get_indexes(name)
        ]
        try:
            uniques = [
                {"name": u.get("name"), "columns": list(u["column_names"])} for u in insp.get_unique_constraints(name)
            ]
        except NotImplementedError:
            uniques = []
        out.append(
            {
                "name": name,
                "row_count": counts.get(name),
                "columns": columns,
                "pk": pk,
                "fks": fks,
                "indexes": indexes,
                "unique_constraints": uniques,
            }
        )
    return out


def approximate_row_counts(engine: Engine) -> dict[str, int | None]:
    dialect = engine.dialect.name
    try:
        with engine.connect() as conn:
            if dialect == "postgresql":
                rows = conn.execute(
                    text(
                        "SELECT c.relname, c.reltuples::bigint FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p')"
                    )
                ).all()
                return {r[0]: (int(r[1]) if r[1] is not None and r[1] >= 0 else None) for r in rows}
            if dialect in ("mysql", "mariadb"):
                rows = conn.execute(
                    text("SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")
                ).all()
                return {r[0]: (int(r[1]) if r[1] is not None else None) for r in rows}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def build_sql_entities(raw_tables: list[dict]) -> tuple[list[dict], list[dict]]:
    """Raw table dicts -> (entities, relationships). Pure."""
    entities: list[dict] = []
    relationships: list[dict] = []
    table_pks = {t["name"]: t["pk"] for t in raw_tables}

    for t in raw_tables:
        pk = t["pk"]
        unique_sets = [tuple(ix["columns"]) for ix in t["indexes"] if ix["unique"]]
        unique_sets += [tuple(u["columns"]) for u in t.get("unique_constraints", [])]
        unique_single = {cols[0] for cols in unique_sets if len(cols) == 1}
        if len(pk) == 1:
            unique_single.add(pk[0])
        leading = {ix["columns"][0] for ix in t["indexes"] if ix["columns"]}
        leading |= {u["columns"][0] for u in t.get("unique_constraints", []) if u["columns"]}
        if pk:
            leading.add(pk[0])
        fk_by_col: dict[str, dict] = {}
        for fk in t["fks"]:
            for col, ref_col in zip(fk["columns"], fk["ref_columns"], strict=False):
                fk_by_col.setdefault(col, {"entity": fk["ref_table"], "field": ref_col})

        fields = []
        for c in t["columns"]:
            fields.append(
                {
                    "name": c["name"],
                    "data_type": c["type"],
                    "nullable": bool(c["nullable"]),
                    "default": c.get("default"),
                    "primary_key": c["name"] in pk,
                    "unique": c["name"] in unique_single,
                    "indexed": c["name"] in leading,
                    "foreign_key": fk_by_col.get(c["name"]),
                    "occurrence": None,
                }
            )
        seen_names: set[str] = set()
        indexes = []
        for ix in t["indexes"]:
            seen_names.add(ix["name"])
            indexes.append({"name": ix["name"], "fields": list(ix["columns"]), "unique": bool(ix["unique"])})
        for u in t.get("unique_constraints", []):
            if u["name"] not in seen_names:
                indexes.append({"name": u["name"], "fields": list(u["columns"]), "unique": True})
        entities.append(
            {
                "name": t["name"],
                "type": "table",
                "row_count": t.get("row_count"),
                "fields": fields,
                "indexes": indexes,
                "validator": None,
            }
        )

        declared_cols: set[str] = set()
        for fk in t["fks"]:
            declared_cols.update(fk["columns"])
            cols = tuple(fk["columns"])
            one = cols in unique_sets or tuple(pk) == cols
            relationships.append(
                {
                    "from_entity": t["name"],
                    "from_fields": list(fk["columns"]),
                    "to_entity": fk["ref_table"],
                    "to_fields": list(fk["ref_columns"]),
                    "cardinality": "one_to_one" if one else "many_to_one",
                    "origin": "foreign_key",
                }
            )
        for c in t["columns"]:
            name = c["name"]
            if name in declared_cols or not name.endswith("_id") or pk == [name]:
                continue
            target = match_entity(name, table_pks.keys(), snake_only=True)
            if not target or len(table_pks.get(target, [])) != 1:
                continue
            if target == t["name"] and name == table_pks[target][0]:
                continue
            relationships.append(
                {
                    "from_entity": t["name"],
                    "from_fields": [name],
                    "to_entity": target,
                    "to_fields": [table_pks[target][0]],
                    "cardinality": "one_to_one" if name in unique_single else "many_to_one",
                    "origin": "inferred",
                }
            )
    return entities, relationships


def raw_sql_tables(engine: Engine, only_table: str | None = None) -> list[dict]:
    if engine.dialect.name in ("mysql", "mariadb"):
        return raw_tables_mysql(engine, only_table)
    return raw_tables_inspector(engine, only_table)


def introspect_sql(engine: Engine, only_table: str | None = None) -> tuple[list[dict], list[dict]]:
    return build_sql_entities(raw_sql_tables(engine, only_table))


# =============================================================================================
# MongoDB
# =============================================================================================


def bson_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, Int64):
        return "long"
    if isinstance(value, int):
        return "int" if -(2**31) <= value < 2**31 else "long"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, ObjectId):
        return "objectId"
    if isinstance(value, dt.datetime):
        return "date"
    if isinstance(value, Decimal128 | decimal.Decimal):
        return "decimal"
    if isinstance(value, uuid.UUID):
        return "uuid"
    if isinstance(value, Binary):
        return "uuid" if value.subtype in (3, 4) else "binData"
    if isinstance(value, bytes | bytearray):
        return "binData"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list | tuple):
        return "array"
    if isinstance(value, Regex | re.Pattern):
        return "regex"
    if isinstance(value, Timestamp):
        return "timestamp"
    if isinstance(value, Code):
        return "javascript"
    if isinstance(value, DBRef):
        return "dbPointer"
    if isinstance(value, MinKey):
        return "minKey"
    if isinstance(value, MaxKey):
        return "maxKey"
    return type(value).__name__


_TYPE_ORDER = [
    "objectId",
    "int",
    "long",
    "double",
    "decimal",
    "string",
    "bool",
    "date",
    "timestamp",
    "uuid",
    "binData",
    "object",
    "array",
    "regex",
    "javascript",
    "null",
]


def _sort_types(types: Iterable[str]) -> list[str]:
    def key(t: str) -> tuple[int, str]:
        base = t.split("<", 1)[0]
        return (_TYPE_ORDER.index(base) if base in _TYPE_ORDER else len(_TYPE_ORDER), t)

    return sorted(set(types), key=key)


def _value_type(value: Any) -> str:
    name = bson_type_name(value)
    if name == "array":
        elem = [t for t in _sort_types(_value_type(v) for v in value)]
        return f"array<{'|'.join(elem)}>" if elem else "array"
    return name


def analyze_documents(docs: list[dict], max_depth: int = MAX_DEPTH) -> list[dict]:
    """Infers `Field` dicts from sampled documents. Pure."""
    order: list[str] = []
    stats: dict[str, dict[str, Any]] = {}
    total = len(docs)

    def visit(obj: dict, prefix: str, depth: int, seen: set[str]) -> None:
        for key, value in obj.items():
            path = f"{prefix}{key}"
            if path not in stats:
                stats[path] = {"types": set(), "count": 0}
                order.append(path)
            if path not in seen:
                seen.add(path)
                stats[path]["count"] += 1
            stats[path]["types"].add(_value_type(value))
            if isinstance(value, dict) and depth < max_depth:
                visit(value, path + ".", depth + 1, seen)

    for doc in docs:
        visit(doc, "", 1, set())

    if "_id" in order:
        order.remove("_id")
        order.insert(0, "_id")

    fields = []
    for path in order:
        st = stats[path]
        types = _sort_types(st["types"])
        non_null = [t for t in types if t != "null"]
        occurrence = st["count"] / total if total else 0.0
        fields.append(
            {
                "name": path,
                "data_type": "|".join(non_null) if non_null else "null",
                "nullable": "null" in types or occurrence < 1,
                "default": None,
                "primary_key": path == "_id",
                "unique": path == "_id",
                "indexed": path == "_id",
                "foreign_key": None,
                "occurrence": round(occurrence, 4),
            }
        )
    return fields


def mongo_indexes(index_info: dict[str, dict]) -> list[dict]:
    out = []
    for name, info in index_info.items():
        keys = info.get("key", [])
        if "weights" in info:  # text index: real fields are in weights
            fields = list(info["weights"].keys())
        else:
            fields = [k for k, _ in keys]
        out.append({"name": name, "fields": fields, "unique": bool(info.get("unique")) or name == "_id_"})
    return out


def apply_mongo_indexes(fields: list[dict], indexes: list[dict]) -> None:
    by_name = {f["name"]: f for f in fields}
    for ix in indexes:
        if not ix["fields"]:
            continue
        lead = by_name.get(ix["fields"][0])
        if lead is not None:
            lead["indexed"] = True
        if ix["unique"] and len(ix["fields"]) == 1 and lead is not None:
            lead["unique"] = True


def to_relaxed(value: Any) -> Any:
    return json.loads(json_util.dumps(value, json_options=json_util.RELAXED_JSON_OPTIONS))


def infer_mongo_relationships(entities: list[dict]) -> list[dict]:
    names = [e["name"] for e in entities]
    rels = []
    for e in entities:
        for f in e["fields"]:
            if f["name"] == "_id" or reference_base(f["name"]) is None:
                continue
            target = match_entity(f["name"], names)
            if not target:
                continue
            rels.append(
                {
                    "from_entity": e["name"],
                    "from_fields": [f["name"]],
                    "to_entity": target,
                    "to_fields": ["_id"],
                    "cardinality": "one_to_one" if f.get("unique") else "many_to_one",
                    "origin": "inferred",
                }
            )
    return rels


def introspect_mongo_collection(database: Any, info: dict, sample: int) -> dict:
    name = info["name"]
    coll = database[name]
    is_view = info.get("type") == "view"
    options = info.get("options") or {}
    docs = list(coll.aggregate([{"$sample": {"size": sample}}], maxTimeMS=30000)) if sample > 0 else []
    fields = analyze_documents(docs)
    indexes: list[dict] = []
    row_count = None
    if not is_view:
        indexes = mongo_indexes(coll.index_information())
        apply_mongo_indexes(fields, indexes)
        try:
            row_count = coll.estimated_document_count()
        except Exception:  # noqa: BLE001
            row_count = None
    validator = options.get("validator")
    return {
        "name": name,
        "type": "collection",
        "row_count": row_count,
        "fields": fields,
        "indexes": indexes,
        "validator": to_relaxed(validator) if validator else None,
    }


def introspect_mongo(
    database: Any, sample: int = DEFAULT_SAMPLE, only: str | None = None
) -> tuple[list[dict], list[dict]]:
    sample = max(0, min(int(sample), MAX_SAMPLE))
    filt: dict[str, Any] = {"name": only} if only else {}
    infos = [i for i in database.list_collections(filter=filt) if not i["name"].startswith("system.")]
    infos.sort(key=lambda i: i["name"])
    entities = [introspect_mongo_collection(database, info, sample) for info in infos]
    return entities, infer_mongo_relationships(entities)


# =============================================================================================
# Sources
# =============================================================================================


def _source_shell(ds: DataSource) -> dict:
    return {
        "source_id": ds.id,
        "name": ds.name,
        "kind": ds.kind,
        "engine": ds.engine,
        "status": "ok",
        "error": None,
        "entities": [],
        "relationships": [],
    }


def introspect_source(ds: DataSource, sample: int = DEFAULT_SAMPLE) -> dict:
    """Never raises: a failing source comes back with status "error"."""
    out = _source_shell(ds)
    try:
        if ds.kind == "sql":
            entities, rels = introspect_sql(connections.get_sql_engine(ds))
        else:
            entities, rels = introspect_mongo(connections.get_mongo_db(ds), sample)
        out["entities"], out["relationships"] = entities, rels
    except Exception as exc:  # noqa: BLE001
        orig = getattr(exc, "orig", None) or exc
        secrets = []
        try:
            cfg = connections.load_config(ds)
            secrets = [cfg.get("password"), connections.mongo_uri_password(cfg.get("uri", ""))]
        except Exception:  # noqa: BLE001
            pass
        out["status"] = "error"
        out["error"] = connections.redact(str(orig), secrets)
    return out


def introspect_sources(sources: list[DataSource], sample: int = DEFAULT_SAMPLE) -> list[dict]:
    if len(sources) <= 1:
        return [introspect_source(s, sample) for s in sources]
    with ThreadPoolExecutor(max_workers=min(4, len(sources))) as pool:
        return list(pool.map(lambda s: introspect_source(s, sample), sources))


def sql_entity(ds: DataSource, table: str) -> dict | None:
    entities, _ = introspect_sql(connections.get_sql_engine(ds), only_table=table)
    return entities[0] if entities else None


def mongo_entity(ds: DataSource, name: str, sample: int = DEFAULT_SAMPLE) -> dict | None:
    entities, _ = introspect_mongo(connections.get_mongo_db(ds), sample, only=name)
    return entities[0] if entities else None


def encode_b64(value: bytes) -> dict:
    return {"$base64": base64.b64encode(bytes(value)).decode("ascii")}
