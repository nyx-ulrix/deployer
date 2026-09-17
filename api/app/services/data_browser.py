"""Data browser: row CRUD for SQL tables and document CRUD for Mongo collections.

User input is never interpolated into SQL: tables are reflected, column names are validated against
the reflected table and all values go through SQLAlchemy Core bound parameters. Mongo filters and
documents are parsed as (relaxed) Extended JSON and scanned for server-side JavaScript operators.
"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import json
import re
import uuid
from typing import Any

from bson import ObjectId, json_util
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from sqlalchemy import Engine, MetaData, Table, and_, asc, desc, func, select
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError

from app.errors import ApiError

MAX_LIMIT = 500
FORBIDDEN_OPERATORS = frozenset({"$where", "$function", "$accumulator"})


# =============================================================================================
# value encoding
# =============================================================================================


def encode_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return str(value)
        return value
    if isinstance(value, bytes | bytearray | memoryview):
        return {"$base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        total = int(value.total_seconds())
        sign = "-" if total < 0 else ""
        total = abs(total)
        return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): encode_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [encode_value(v) for v in value]
    return str(value)


def decode_input(value: Any) -> Any:
    """Turns `{"$base64": "..."}` back into bytes; everything else passes through."""
    if isinstance(value, dict) and set(value.keys()) == {"$base64"} and isinstance(value["$base64"], str):
        try:
            return base64.b64decode(value["$base64"], validate=True)
        except ValueError as exc:
            raise ApiError(400, "invalid_value", "Invalid base64 value") from exc
    return value


def _coerce_for_column(column: Any, value: Any) -> Any:
    value = decode_input(value)
    if not isinstance(value, str):
        return value
    try:
        py = column.type.python_type
    except (NotImplementedError, AttributeError):
        return value
    try:
        if py is dt.datetime:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if py is dt.date:
            return dt.date.fromisoformat(value)
        if py is dt.time:
            return dt.time.fromisoformat(value)
        if py is decimal.Decimal:
            return decimal.Decimal(value)
    except (ValueError, decimal.InvalidOperation):
        return value  # let the database decide
    return value


# =============================================================================================
# SQL
# =============================================================================================


def reflect_table(engine: Engine, name: str) -> Table:
    try:
        return Table(name, MetaData(), autoload_with=engine)
    except NoSuchTableError as exc:
        raise ApiError(404, "not_found", f"Table '{name}' not found") from exc


def _db_error(exc: SQLAlchemyError) -> ApiError:
    orig = getattr(exc, "orig", None) or exc
    return ApiError(400, "query_failed", str(orig)[:1000])


def _row_out(row: Any) -> dict:
    return {k: encode_value(v) for k, v in row._mapping.items()}


def _validate_values(table: Table, values: dict, what: str = "values") -> dict:
    if not isinstance(values, dict):
        raise ApiError(422, "validation_error", f"`{what}` must be an object")
    unknown = [k for k in values if k not in table.c]
    if unknown:
        raise ApiError(
            400, "unknown_column", f"Unknown column(s): {', '.join(map(str, unknown))}", {"columns": unknown}
        )
    return {k: _coerce_for_column(table.c[k], v) for k, v in values.items()}


def _pk_columns(table: Table) -> list[Any]:
    return list(table.primary_key.columns)


def _pk_clause(table: Table, pk: dict) -> Any:
    cols = _pk_columns(table)
    if not cols:
        raise ApiError(409, "no_primary_key", "This table has no primary key, so rows are read-only here")
    if not isinstance(pk, dict) or set(pk.keys()) != {c.name for c in cols}:
        raise ApiError(400, "invalid_primary_key", f"`pk` must contain exactly: {', '.join(c.name for c in cols)}")
    return and_(*[c == _coerce_for_column(c, pk[c.name]) for c in cols])


def list_rows(
    engine: Engine,
    table_name: str,
    *,
    limit: int = 50,
    offset: int = 0,
    order_by: str | None = None,
    order: str = "asc",
) -> dict:
    table = reflect_table(engine, table_name)
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    stmt = select(table)
    direction = desc if (order or "asc").lower() == "desc" else asc
    if order_by:
        if order_by not in table.c:
            raise ApiError(400, "unknown_column", f"Unknown column: {order_by}")
        stmt = stmt.order_by(direction(table.c[order_by]))
    elif _pk_columns(table):
        stmt = stmt.order_by(*[direction(c) for c in _pk_columns(table)])
    stmt = stmt.limit(limit).offset(offset)
    try:
        with engine.connect() as conn:
            rows = [_row_out(r) for r in conn.execute(stmt)]
            total = conn.execute(select(func.count()).select_from(table)).scalar_one()
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    return {
        "columns": [c.name for c in table.columns],
        "primary_key": [c.name for c in _pk_columns(table)],
        "rows": rows,
        "total": int(total),
    }


def _fetch_by_pk(conn: Any, table: Table, pk_values: dict) -> dict | None:
    cols = _pk_columns(table)
    row = conn.execute(select(table).where(and_(*[c == pk_values[c.name] for c in cols]))).first()
    return _row_out(row) if row is not None else None


def insert_row(engine: Engine, table_name: str, values: dict) -> dict:
    table = reflect_table(engine, table_name)
    if not _pk_columns(table):
        raise ApiError(409, "no_primary_key", "This table has no primary key, so rows are read-only here")
    clean = _validate_values(table, values)
    try:
        with engine.begin() as conn:
            result = conn.execute(table.insert().values(**clean) if clean else table.insert())
            inserted = result.inserted_primary_key
            pk_values = {}
            for i, c in enumerate(_pk_columns(table)):
                v = inserted[i] if inserted is not None and i < len(inserted) else None
                pk_values[c.name] = v if v is not None else clean.get(c.name)
            row = _fetch_by_pk(conn, table, pk_values) if all(v is not None for v in pk_values.values()) else None
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    return {"row": row if row is not None else encode_value(clean)}


def update_row(engine: Engine, table_name: str, pk: dict, values: dict) -> dict:
    table = reflect_table(engine, table_name)
    where = _pk_clause(table, pk)
    clean = _validate_values(table, values)
    if not clean:
        raise ApiError(400, "empty_update", "`values` must contain at least one column")
    try:
        with engine.begin() as conn:
            result = conn.execute(table.update().where(where).values(**clean))
            new_pk = {c.name: clean.get(c.name, _coerce_for_column(c, pk[c.name])) for c in _pk_columns(table)}
            row = _fetch_by_pk(conn, table, new_pk)
            if row is None and result.rowcount == 0:
                raise ApiError(404, "row_not_found", "No row matches that primary key")
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    return {"row": row}


def delete_row(engine: Engine, table_name: str, pk: dict) -> dict:
    table = reflect_table(engine, table_name)
    where = _pk_clause(table, pk)
    try:
        with engine.begin() as conn:
            result = conn.execute(table.delete().where(where))
    except SQLAlchemyError as exc:
        raise _db_error(exc) from exc
    if result.rowcount == 0:
        raise ApiError(404, "row_not_found", "No row matches that primary key")
    return {"ok": True}


# =============================================================================================
# MongoDB
# =============================================================================================


def find_forbidden_operator(value: Any, _inside_expr: bool = False) -> str | None:
    """Recursively looks for server-side JavaScript operators."""
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key in FORBIDDEN_OPERATORS:
                return key
            found = find_forbidden_operator(child, _inside_expr or key == "$expr")
            if found:
                return found
    elif isinstance(value, list | tuple):
        for child in value:
            found = find_forbidden_operator(child, _inside_expr)
            if found:
                return found
    return None


def check_forbidden(value: Any) -> None:
    op = find_forbidden_operator(value)
    if op:
        raise ApiError(400, "forbidden_operator", f"The {op} operator is not allowed")


def parse_ejson(value: Any, what: str) -> Any:
    """Accepts a JSON string or already-parsed JSON and returns BSON-ready Python values."""
    try:
        text_value = value if isinstance(value, str) else json.dumps(value)
        parsed = json_util.loads(text_value, json_options=json_util.RELAXED_JSON_OPTIONS)
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "invalid_json", f"Invalid {what}: {exc}") from exc
    check_forbidden(parsed)
    return parsed


def to_relaxed(doc: Any) -> Any:
    return json.loads(json_util.dumps(doc, json_options=json_util.RELAXED_JSON_OPTIONS))


def _mongo_error(exc: PyMongoError) -> ApiError:
    return ApiError(400, "query_failed", str(exc)[:1000])


def _collection(database: Any, name: str) -> Any:
    try:
        exists = bool(list(database.list_collections(filter={"name": name})))
    except PyMongoError as exc:
        raise _mongo_error(exc) from exc
    if not exists:
        raise ApiError(404, "not_found", f"Collection '{name}' not found")
    return database[name]


_INT_ID_RE = re.compile(r"-?\d{1,19}")


def id_candidates(doc_id: str) -> list[Any]:
    """Possible `_id` values for the string form used in URLs: ObjectId hex, then a 64-bit integer
    (documents are often keyed by numbers), then the raw string."""
    out: list[Any] = []
    if ObjectId.is_valid(doc_id) and len(doc_id) == 24:
        try:
            out.append(ObjectId(doc_id))
        except InvalidId:
            pass
    if _INT_ID_RE.fullmatch(doc_id) and -(2**63) <= int(doc_id) < 2**63:
        out.append(int(doc_id))
    out.append(doc_id)
    return out


def _find_id(coll: Any, doc_id: str) -> Any:
    for candidate in id_candidates(doc_id):
        if coll.count_documents({"_id": candidate}, limit=1):
            return candidate
    raise ApiError(404, "document_not_found", "Document not found")


def list_documents(database: Any, name: str, *, filter_json: str | None, limit: int = 50, skip: int = 0) -> dict:
    coll = _collection(database, name)
    flt = parse_ejson(filter_json, "filter") if filter_json not in (None, "") else {}
    if not isinstance(flt, dict):
        raise ApiError(400, "invalid_json", "filter must be a JSON object")
    limit = max(1, min(int(limit), MAX_LIMIT))
    skip = max(0, int(skip))
    try:
        docs = [to_relaxed(d) for d in coll.find(flt, max_time_ms=30000).skip(skip).limit(limit)]
        total = coll.count_documents(flt, maxTimeMS=30000) if flt else coll.estimated_document_count()
    except PyMongoError as exc:
        raise _mongo_error(exc) from exc
    return {"documents": docs, "total": int(total)}


def insert_document(database: Any, name: str, document: Any) -> dict:
    coll = _collection(database, name)
    doc = parse_ejson(document, "document")
    if not isinstance(doc, dict):
        raise ApiError(400, "invalid_json", "document must be a JSON object")
    try:
        result = coll.insert_one(doc)
        stored = coll.find_one({"_id": result.inserted_id})
    except PyMongoError as exc:
        raise _mongo_error(exc) from exc
    return {"document": to_relaxed(stored)}


def update_document(database: Any, name: str, doc_id: str, set_values: Any, unset: list[str] | None) -> dict:
    coll = _collection(database, name)
    set_doc = parse_ejson(set_values or {}, "set")
    if not isinstance(set_doc, dict):
        raise ApiError(400, "invalid_json", "set must be a JSON object")
    unset = unset or []
    if not all(isinstance(u, str) and u for u in unset):
        raise ApiError(422, "validation_error", "unset must be a list of field names")
    for key in list(set_doc.keys()) + unset:
        if key == "_id" or key.startswith("_id."):
            raise ApiError(400, "immutable_field", "_id cannot be changed")
        if key.startswith("$"):
            raise ApiError(400, "invalid_field", f"Invalid field name: {key}")
    update: dict[str, Any] = {}
    if set_doc:
        update["$set"] = set_doc
    if unset:
        update["$unset"] = {u: "" for u in unset}
    if not update:
        raise ApiError(400, "empty_update", "Nothing to update")
    try:
        _id = _find_id(coll, doc_id)
        doc = coll.find_one_and_update({"_id": _id}, update, return_document=ReturnDocument.AFTER)
    except PyMongoError as exc:
        raise _mongo_error(exc) from exc
    if doc is None:
        raise ApiError(404, "document_not_found", "Document not found")
    return {"document": to_relaxed(doc)}


def delete_document(database: Any, name: str, doc_id: str) -> dict:
    coll = _collection(database, name)
    try:
        _id = _find_id(coll, doc_id)
        coll.delete_one({"_id": _id})
    except PyMongoError as exc:
        raise _mongo_error(exc) from exc
    return {"ok": True}
