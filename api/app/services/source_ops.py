"""Data source operations that work for sources on the main server *and* on host devices.

Routers call these functions with a `DataSource`. When `data_source.device_id` is set the operation
is sent to the device (`datasource.call` RPC, docs/DEVICES.md) which runs the very same local
service function (`run_local`) against its own managed database; otherwise it runs here.

A device that is not connected makes these calls raise `503 device_offline` (schema introspection
and DDL export degrade to an error entry / comment instead, like any unreachable source).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import DataSource, utcnow
from app.services import (
    connections,
    data_browser,
    ddl_export,
    device_rpc,
    introspection,
    query_console,
    schema_ops,
)

OPS = (
    "introspect",
    "entity",
    "ddl_export",
    "query",
    "rows.list",
    "rows.insert",
    "rows.update",
    "rows.delete",
    "documents.list",
    "documents.insert",
    "documents.update",
    "documents.delete",
    "table.create",
    "table.drop",
    "collection.create",
    "collection.drop",
    "connection_info",
)
SQL_OPS = {"rows.list", "rows.insert", "rows.update", "rows.delete", "table.create", "table.drop"}
NOSQL_OPS = {
    "documents.list",
    "documents.insert",
    "documents.update",
    "documents.delete",
    "collection.create",
    "collection.drop",
}
REMOTE_TIMEOUT = 60.0


def is_remote(ds: DataSource) -> bool:
    return bool(ds.device_id)


# ---------------------------------------------------------------------------------------------
# local execution (main server, or the device executing an RPC)
# ---------------------------------------------------------------------------------------------


def _str_arg(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ApiError(422, "validation_error", f"{key} is required")
    return value


def run_local(ds: DataSource, op: str, args: dict | None = None) -> Any:
    """Executes `op` against a data source reachable from this process."""
    args = args or {}
    if op not in OPS:
        raise ApiError(400, "unknown_operation", f"Unknown data source operation: {op}")
    if op in SQL_OPS and ds.kind != "sql":
        raise ApiError(400, "wrong_source_kind", "This operation needs a SQL data source")
    if op in NOSQL_OPS and ds.kind != "nosql":
        raise ApiError(400, "wrong_source_kind", "This operation needs a NoSQL (MongoDB) data source")
    if op == "introspect":
        return introspection.introspect_source(ds, int(args.get("sample", introspection.DEFAULT_SAMPLE)))
    if op == "entity":
        name = _str_arg(args, "name")
        if ds.kind == "sql":
            return introspection.sql_entity(ds, name)
        return introspection.mongo_entity(ds, name)
    if op == "ddl_export":
        return ddl_export.export_sql_source(ds) if ds.kind == "sql" else ddl_export.export_mongo_source(ds)
    if op == "connection_info":
        return connections.connection_info(ds)
    if op == "query":
        # docs/QUERY_CONSOLE.md: `read_only` is decided by the caller's role (on the primary).
        return query_console.run_query(
            ds,
            _str_arg(args, "query"),
            max_rows=int(args.get("max_rows") or query_console.DEFAULT_MAX_ROWS),
            timeout_seconds=int(args.get("timeout_seconds") or query_console.DEFAULT_TIMEOUT_SECONDS),
            read_only=bool(args.get("read_only", True)),
        )
    if ds.kind == "sql":
        engine = connections.get_sql_engine(ds)
        table = _str_arg(args, "table") if op.startswith("rows.") else None
        if op == "rows.list":
            return data_browser.list_rows(
                engine,
                table,
                limit=int(args.get("limit", 50)),
                offset=int(args.get("offset", 0)),
                order_by=args.get("order_by") or None,
                order=args.get("order") or "asc",
            )
        if op == "rows.insert":
            return data_browser.insert_row(engine, table, args.get("values") or {})
        if op == "rows.update":
            return data_browser.update_row(engine, table, args.get("pk") or {}, args.get("values") or {})
        if op == "rows.delete":
            return data_browser.delete_row(engine, table, args.get("pk") or {})
        if op == "table.create":
            spec = args.get("spec")
            if not isinstance(spec, dict):
                raise ApiError(422, "validation_error", "spec is required")
            schema_ops.create_table(engine, spec)
            return {"ok": True}
        if op == "table.drop":
            schema_ops.drop_table(engine, _str_arg(args, "name"))
            return {"ok": True}
    database = connections.get_mongo_db(ds)
    if op == "documents.list":
        return data_browser.list_documents(
            database,
            _str_arg(args, "name"),
            filter_json=args.get("filter"),
            limit=int(args.get("limit", 50)),
            skip=int(args.get("skip", 0)),
        )
    if op == "documents.insert":
        return data_browser.insert_document(database, _str_arg(args, "name"), args.get("document"))
    if op == "documents.update":
        return data_browser.update_document(
            database, _str_arg(args, "name"), _str_arg(args, "doc_id"), args.get("set") or {}, args.get("unset")
        )
    if op == "documents.delete":
        return data_browser.delete_document(database, _str_arg(args, "name"), _str_arg(args, "doc_id"))
    if op == "collection.create":
        schema_ops.create_collection(database, _str_arg(args, "name"), args.get("validator"))
        return {"ok": True}
    if op == "collection.drop":
        schema_ops.drop_collection(database, _str_arg(args, "name"))
        return {"ok": True}
    raise ApiError(400, "unknown_operation", f"Unknown data source operation: {op}")  # pragma: no cover


# ---------------------------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------------------------


def remote_params(ds: DataSource, **extra: Any) -> dict:
    return {"kind": ds.kind, "database_name": ds.database_name, "source_name": ds.name, **extra}


def run(ds: DataSource, op: str, args: dict | None = None, *, timeout: float = REMOTE_TIMEOUT) -> Any:
    if is_remote(ds):
        return device_rpc.call(
            ds.device_id, "datasource.call", remote_params(ds, op=op, args=args or {}), timeout=timeout
        )
    return run_local(ds, op, args)


# --- schema --------------------------------------------------------------------------------------


def _remote_introspect(ds: DataSource, sample: int) -> dict:
    try:
        out = run(ds, "introspect", {"sample": sample})
        if not isinstance(out, dict):
            raise ApiError(502, "device_error", "Malformed schema from host device")
    except ApiError as exc:
        out = {"status": "error", "error": exc.message, "entities": [], "relationships": []}
    out.update({"source_id": ds.id, "name": ds.name, "kind": ds.kind, "engine": ds.engine})
    return out


def introspect_sources(sources: list[DataSource], sample: int = introspection.DEFAULT_SAMPLE) -> list[dict]:
    if not any(is_remote(s) for s in sources):
        return introspection.introspect_sources(sources, sample)
    from concurrent.futures import ThreadPoolExecutor

    def one(ds: DataSource) -> dict:
        return _remote_introspect(ds, sample) if is_remote(ds) else introspection.introspect_source(ds, sample)

    with ThreadPoolExecutor(max_workers=min(4, len(sources))) as pool:
        return list(pool.map(one, sources))


def sql_entity(ds: DataSource, table: str) -> dict | None:
    return run(ds, "entity", {"name": table}) if is_remote(ds) else introspection.sql_entity(ds, table)


def mongo_entity(ds: DataSource, name: str) -> dict | None:
    return run(ds, "entity", {"name": name}) if is_remote(ds) else introspection.mongo_entity(ds, name)


def export_sources(sources: list[DataSource], kind: str, now: datetime | None = None) -> str:
    """Like `ddl_export.export_sources`, fetching scripts of device-hosted sources from the device."""
    if not any(is_remote(s) for s in sources):
        return ddl_export.export_sources(sources, kind, now)
    chunks = []
    for ds in sources:
        if ds.kind != kind:
            continue
        if not is_remote(ds):
            chunks.append(ddl_export.export_sources([ds], kind, now))
            continue
        try:
            text = run(ds, "ddl_export", {})
            if not isinstance(text, str):
                raise ApiError(502, "device_error", "Malformed export from host device")
            chunks.append(text)
        except ApiError as exc:
            prefix = "--" if kind == "sql" else "//"
            chunks.append(
                f"{prefix} Source {ddl_export._comment_safe(ds.name)} could not be exported: "
                f"{ddl_export._comment_safe(exc.message)}\n"
            )
    if not chunks:
        return ("-- " if kind == "sql" else "// ") + "No " + ("SQL" if kind == "sql" else "MongoDB") + " data sources\n"
    return "\n".join(chunks)


def _to_copies(ds: DataSource, op: str, args: dict) -> None:
    """docs/COHOSTING.md: schema changes made through Deployer are repeated on co-host copies."""
    if not is_remote(ds) and ds.mode == "managed":
        from app.services import cohosting

        cohosting.fan_out_schema_change(ds, op, args)


def create_table(ds: DataSource, spec: dict) -> None:
    if is_remote(ds):
        run(ds, "table.create", {"spec": spec})
    else:
        schema_ops.create_table(connections.get_sql_engine(ds), spec)
        _to_copies(ds, "table.create", {"spec": spec})


def drop_table(ds: DataSource, name: str) -> None:
    if is_remote(ds):
        run(ds, "table.drop", {"name": name})
    else:
        schema_ops.drop_table(connections.get_sql_engine(ds), name)
        _to_copies(ds, "table.drop", {"name": name})


def create_collection(ds: DataSource, name: str, validator: Any = None) -> None:
    if is_remote(ds):
        run(ds, "collection.create", {"name": name, "validator": validator})
    else:
        schema_ops.create_collection(connections.get_mongo_db(ds), name, validator)
        _to_copies(ds, "collection.create", {"name": name, "validator": validator})


def drop_collection(ds: DataSource, name: str) -> None:
    if is_remote(ds):
        run(ds, "collection.drop", {"name": name})
    else:
        schema_ops.drop_collection(connections.get_mongo_db(ds), name)
        _to_copies(ds, "collection.drop", {"name": name})


# --- query console ---------------------------------------------------------------------------------


def run_query(ds: DataSource, query: str, *, max_rows: int, timeout_seconds: int, read_only: bool) -> dict:
    """docs/QUERY_CONSOLE.md: the SQL / mongosh runner, on the device for device-hosted sources."""
    if not is_remote(ds):
        return query_console.run_query(
            ds, query, max_rows=max_rows, timeout_seconds=timeout_seconds, read_only=read_only
        )
    out = run(
        ds,
        "query",
        {"query": query, "max_rows": max_rows, "timeout_seconds": timeout_seconds, "read_only": read_only},
        timeout=timeout_seconds + 15,
    )
    if not isinstance(out, dict):
        raise ApiError(502, "device_error", "Malformed query result from host device")
    return out


# --- status & connection ---------------------------------------------------------------------------


def check_status(db: Session, ds: DataSource) -> DataSource:
    """`connections.check_status` for any source. Caller commits."""
    if not is_remote(ds):
        return connections.check_status(db, ds)
    _ = db
    try:
        result = device_rpc.call(
            ds.device_id, "datasource.check", {"kind": ds.kind, "database_name": ds.database_name}, timeout=30
        )
        ok = bool(result.get("ok"))
        message = str(result.get("message") or "")
        version = result.get("server_version")
    except ApiError as exc:
        ok, message, version = False, exc.message, None
    ds.status = "ok" if ok else "error"
    ds.status_message = (f"Connected (server {version})" if version else "Connected") if ok else message[:2000]
    ds.last_checked_at = utcnow()
    return ds


def connection_info(ds: DataSource) -> dict:
    if not is_remote(ds):
        return connections.connection_info(ds)
    info = run(ds, "connection_info", {})
    if not isinstance(info, dict):
        raise ApiError(502, "device_error", "Malformed connection info from host device")
    info["external_hint"] = (
        "This database runs on a host device. The host above is only valid on that device's Docker "
        f"network (host '{info.get('host')}'); from other machines use the device's LAN or Tailscale "
        "address, which Deployer does not know. The database port is not published by default."
    )
    info["device_id"] = ds.device_id
    return info


# --- data browser -------------------------------------------------------------------------------


def list_rows(ds: DataSource, table: str, **kwargs: Any) -> dict:
    if is_remote(ds):
        return run(ds, "rows.list", {"table": table, **kwargs})
    return data_browser.list_rows(connections.get_sql_engine(ds), table, **kwargs)


def insert_row(ds: DataSource, table: str, values: dict) -> dict:
    if is_remote(ds):
        return run(ds, "rows.insert", {"table": table, "values": values})
    return data_browser.insert_row(connections.get_sql_engine(ds), table, values)


def update_row(ds: DataSource, table: str, pk: dict, values: dict) -> dict:
    if is_remote(ds):
        return run(ds, "rows.update", {"table": table, "pk": pk, "values": values})
    return data_browser.update_row(connections.get_sql_engine(ds), table, pk, values)


def delete_row(ds: DataSource, table: str, pk: dict) -> dict:
    if is_remote(ds):
        return run(ds, "rows.delete", {"table": table, "pk": pk})
    return data_browser.delete_row(connections.get_sql_engine(ds), table, pk)


def list_documents(ds: DataSource, name: str, *, filter_json: str | None, limit: int = 50, skip: int = 0) -> dict:
    if is_remote(ds):
        return run(ds, "documents.list", {"name": name, "filter": filter_json, "limit": limit, "skip": skip})
    return data_browser.list_documents(
        connections.get_mongo_db(ds), name, filter_json=filter_json, limit=limit, skip=skip
    )


def insert_document(ds: DataSource, name: str, document: Any) -> dict:
    if is_remote(ds):
        return run(ds, "documents.insert", {"name": name, "document": document})
    return data_browser.insert_document(connections.get_mongo_db(ds), name, document)


def update_document(ds: DataSource, name: str, doc_id: str, set_values: Any, unset: list[str] | None) -> dict:
    if is_remote(ds):
        return run(ds, "documents.update", {"name": name, "doc_id": doc_id, "set": set_values, "unset": unset})
    return data_browser.update_document(connections.get_mongo_db(ds), name, doc_id, set_values, unset)


def delete_document(ds: DataSource, name: str, doc_id: str) -> dict:
    if is_remote(ds):
        return run(ds, "documents.delete", {"name": name, "doc_id": doc_id})
    return data_browser.delete_document(connections.get_mongo_db(ds), name, doc_id)
