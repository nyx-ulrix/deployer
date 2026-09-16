"""DDL export: SQL scripts, mongosh scripts and the zip bundle (docs/CONVENTIONS.md "DDL export")."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

from bson import json_util
from sqlalchemy import Engine, MetaData, inspect
from sqlalchemy.schema import CreateIndex, CreateTable

from app.models import DataSource
from app.services import connections
from app.services.conventions import split_type_union
from app.services.introspection import DEFAULT_SAMPLE, analyze_documents

# ---------------------------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------------------------


def topo_sort_tables(tables: list[str], deps: dict[str, set[str]]) -> list[str]:
    """Orders tables so referenced tables come first. Cycles / self references are tolerated:
    remaining tables are appended alphabetically (FK checks are disabled around the script)."""
    remaining = {t: {d for d in deps.get(t, set()) if d != t and d in tables} for t in tables}
    ordered: list[str] = []
    while remaining:
        ready = sorted(t for t, d in remaining.items() if not d)
        if not ready:
            ready = [sorted(remaining)[0]]
        for t in ready:
            ordered.append(t)
            remaining.pop(t)
        for d in remaining.values():
            d.difference_update(ready)
    return ordered


def _now_text(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M:%S UTC")


def _comment_safe(value: str) -> str:
    return str(value).replace("\n", " ").replace("\r", " ")


def render_sql_script(
    *, source_name: str, engine: str, database: str, statements: list[str], now: datetime | None = None
) -> str:
    mysql = engine in ("mariadb", "mysql")
    lines = [
        "-- Deployer schema export",
        f"-- Source: {_comment_safe(source_name)} ({engine})",
        f"-- Database: {_comment_safe(database)}",
        f"-- Generated: {_now_text(now)}",
        "",
    ]
    if mysql:
        lines += ["SET FOREIGN_KEY_CHECKS=0;", ""]
    if not statements:
        lines.append("-- (no tables)")
        lines.append("")
    for stmt in statements:
        s = stmt.strip().rstrip(";")
        lines.append(s + ";")
        lines.append("")
    if mysql:
        lines += ["SET FOREIGN_KEY_CHECKS=1;", ""]
    return "\n".join(lines)


def ejson(value: Any, indent: int | None = 2) -> str:
    return json_util.dumps(value, json_options=json_util.RELAXED_JSON_OPTIONS, indent=indent)


def _js_string(value: str) -> str:
    return json.dumps(value)


def _commented(block: str) -> str:
    return "\n".join("// " + line for line in block.splitlines())


_BSON_ALIASES = {"uuid": "binData"}


def inferred_json_schema(fields: list[dict]) -> dict:
    """Builds a `$jsonSchema` from inferred Field dicts (dot paths -> nested properties)."""
    root: dict[str, Any] = {"bsonType": "object", "properties": {}}
    by_path = {f["name"]: f for f in fields}

    def node_for(path: str) -> dict:
        parts = path.split(".")
        node = root
        for i, part in enumerate(parts):
            props = node.setdefault("properties", {})
            if part not in props:
                props[part] = {}
            node = props[part]
            if i < len(parts) - 1:
                node.setdefault("bsonType", "object")
        return node

    for f in fields:
        node = node_for(f["name"])
        types = []
        for t in split_type_union(f.get("data_type") or ""):
            base = t.split("<", 1)[0]
            base = _BSON_ALIASES.get(base, base)
            if base not in types:
                types.append(base)
        if f.get("nullable") and "null" not in types and (f.get("occurrence") or 0) >= 1:
            types.append("null")
        if types:
            node["bsonType"] = types[0] if len(types) == 1 else types

    def add_required(node: dict, prefix: str) -> None:
        props = node.get("properties")
        if not props:
            return
        req = [k for k in props if (by_path.get(prefix + k) or {}).get("occurrence") == 1]
        if req:
            node["required"] = req
        for k, child in props.items():
            add_required(child, prefix + k + ".")

    add_required(root, "")
    return {"$jsonSchema": root}


_INDEX_SKIP_OPTIONS = {"key", "v", "ns", "textIndexVersion", "2dsphereIndexVersion"}


def index_key_and_options(name: str, info: dict) -> tuple[dict, dict]:
    if "weights" in info:
        key = {f: "text" for f in info["weights"]}
        for k, v in info.get("key", []):
            if k not in ("_fts", "_ftsx"):
                key = {k: v, **key}
    else:
        key = {k: v for k, v in info.get("key", [])}
    options = {"name": name}
    for k, v in info.items():
        if k not in _INDEX_SKIP_OPTIONS:
            options[k] = v
    return key, options


def render_mongo_script(
    *, source_name: str, database: str, collections: list[dict], now: datetime | None = None
) -> str:
    """collections: [{name, type?, options, indexes: {name: info}, fields: [...]}]"""
    lines = [
        "// Deployer MongoDB schema export (run with mongosh)",
        f"// Source: {_comment_safe(source_name)}",
        f"// Database: {_comment_safe(database)}",
        f"// Generated: {_now_text(now)}",
        "",
        f"const database = db.getSiblingDB({_js_string(database)});",
        "",
    ]
    if not collections:
        lines += ["// (no collections)", ""]
    for coll in collections:
        name = coll["name"]
        options = dict(coll.get("options") or {})
        lines.append(f"// --- {_comment_safe(name)}")
        if coll.get("type") == "view":
            view_on = options.get("viewOn")
            pipeline = options.get("pipeline", [])
            lines.append(
                f"database.createView({_js_string(name)}, {_js_string(view_on or '')}, "
                f"EJSON.deserialize({ejson(pipeline)}));"
            )
            lines.append("")
            continue
        validator = options.pop("validator", None)
        options.pop("uuid", None)
        if validator:
            options = {"validator": validator, **options}
        if options:
            lines.append(f"database.createCollection({_js_string(name)}, EJSON.deserialize({ejson(options)}));")
        else:
            lines.append(f"database.createCollection({_js_string(name)});")
        if not validator and coll.get("fields"):
            schema = inferred_json_schema(coll["fields"])
            lines.append("// Validator inferred from sampled documents - review, then uncomment to enable:")
            lines.append(
                _commented(
                    f"database.runCommand({{ collMod: {_js_string(name)}, "
                    f"validator: EJSON.deserialize({ejson(schema)}) }});"
                )
            )
        for ix_name, info in (coll.get("indexes") or {}).items():
            if ix_name == "_id_":
                continue
            key, ix_options = index_key_and_options(ix_name, info)
            lines.append(
                f"database.getCollection({_js_string(name)}).createIndex("
                f"EJSON.deserialize({ejson(key, None)}), EJSON.deserialize({ejson(ix_options, None)}));"
            )
        lines.append("")
    return "\n".join(lines)


BUNDLE_README = """# Deployer schema bundle

Project: {project}
Generated: {generated}

Files:

- `schema.sql` - SQL DDL for every SQL data source (MariaDB/MySQL scripts disable foreign-key checks
  while tables are created). Run it against an empty database, e.g.
  `mysql -u <user> -p <database> < schema.sql` or `psql -d <database> -f schema.sql`.
- `schema.mongo.js` - a mongosh script that creates collections, validators and indexes:
  `mongosh "<connection uri>" schema.mongo.js`.
- `links.json` - cross-database links (SQL column <-> MongoDB field) declared in Deployer. These are
  documentation only; databases do not enforce them.

Order: run `schema.sql` first, then `schema.mongo.js`. The scripts contain structure only, no data.
"""


def build_bundle(
    *, project_name: str, sql_text: str, mongo_text: str, links: list[dict], now: datetime | None = None
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("schema.sql", sql_text)
        zf.writestr("schema.mongo.js", mongo_text)
        zf.writestr("links.json", json.dumps(links, indent=2))
        zf.writestr("README.md", BUNDLE_README.format(project=project_name, generated=_now_text(now)))
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------
# live exports
# ---------------------------------------------------------------------------------------------


def mysql_table_order(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        tables = [
            _s(r[0])
            for r in conn.exec_driver_sql(
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
            )
        ]
        deps: dict[str, set[str]] = {}
        for tname, ref in conn.exec_driver_sql(
            "SELECT TABLE_NAME, REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL "
            "AND (REFERENCED_TABLE_SCHEMA IS NULL OR REFERENCED_TABLE_SCHEMA = DATABASE())"
        ):
            deps.setdefault(_s(tname), set()).add(_s(ref))
    return topo_sort_tables(tables, deps)


def _s(value: Any) -> Any:
    return value.decode("utf-8", "replace") if isinstance(value, bytes | bytearray) else value


def show_create_table(conn: Any, dialect: Any, table: str) -> str:
    q = dialect.identifier_preparer.quote_identifier(table).replace("%", "%%")
    row = conn.exec_driver_sql(f"SHOW CREATE TABLE {q}").first()
    return _s(row[1])


def sql_create_statements(engine: Engine) -> list[str]:
    if engine.dialect.name in ("mysql", "mariadb"):
        order = mysql_table_order(engine)
        with engine.connect() as conn:
            return [show_create_table(conn, engine.dialect, t) for t in order]
    metadata = MetaData()
    metadata.reflect(bind=engine)
    insp = inspect(engine)
    names = insp.get_table_names()
    deps = {t: {fk["referred_table"] for fk in insp.get_foreign_keys(t) if fk.get("referred_table")} for t in names}
    statements = []
    for tname in topo_sort_tables(names, deps):
        table = metadata.tables.get(tname)
        if table is None:
            continue
        statements.append(str(CreateTable(table).compile(dialect=engine.dialect)).strip())
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            statements.append(str(CreateIndex(index).compile(dialect=engine.dialect)).strip())
    return statements


def export_sql_source(ds: DataSource, now: datetime | None = None) -> str:
    engine = connections.get_sql_engine(ds)
    return render_sql_script(
        source_name=ds.name,
        engine=ds.engine,
        database=ds.database_name,
        statements=sql_create_statements(engine),
        now=now,
    )


def mongo_collection_specs(database: Any, sample: int = DEFAULT_SAMPLE) -> list[dict]:
    specs = []
    infos = [i for i in database.list_collections() if not i["name"].startswith("system.")]
    infos.sort(key=lambda i: (i.get("type") == "view", i["name"]))
    for info in infos:
        coll = database[info["name"]]
        spec = {"name": info["name"], "type": info.get("type", "collection"), "options": info.get("options") or {}}
        if spec["type"] != "view":
            spec["indexes"] = coll.index_information()
            if not spec["options"].get("validator") and sample > 0:
                docs = list(coll.aggregate([{"$sample": {"size": sample}}], maxTimeMS=30000))
                spec["fields"] = analyze_documents(docs)
        specs.append(spec)
    return specs


def export_mongo_source(ds: DataSource, now: datetime | None = None) -> str:
    database = connections.get_mongo_db(ds)
    config = connections.load_config(ds)
    return render_mongo_script(
        source_name=ds.name,
        database=config.get("database") or ds.database_name,
        collections=mongo_collection_specs(database),
        now=now,
    )


def export_sources(sources: list[DataSource], kind: str, now: datetime | None = None) -> str:
    """Concatenates scripts for every source of `kind`; failing sources become comments."""
    chunks = []
    for ds in sources:
        if ds.kind != kind:
            continue
        try:
            chunks.append(export_sql_source(ds, now) if kind == "sql" else export_mongo_source(ds, now))
        except Exception as exc:  # noqa: BLE001
            prefix = "--" if kind == "sql" else "//"
            msg = connections.redact(str(getattr(exc, "orig", None) or exc))
            chunks.append(f"{prefix} Source {_comment_safe(ds.name)} could not be exported: {_comment_safe(msg)}\n")
    if not chunks:
        return ("-- " if kind == "sql" else "// ") + "No " + ("SQL" if kind == "sql" else "MongoDB") + " data sources\n"
    return "\n".join(chunks)
