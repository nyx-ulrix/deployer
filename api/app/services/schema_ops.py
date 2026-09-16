"""Structure changes from the dashboard: create/drop SQL tables and Mongo collections.

`build_create_table` is pure (takes a SQLAlchemy dialect) so the generated DDL can be unit-tested.
Identifiers are validated with a strict regex *and* quoted with the dialect's preparer; column
types must match an allowlist; defaults must be simple literals or well-known functions.
"""

from __future__ import annotations

import re
from typing import Any

from bson import json_util
from pymongo.errors import CollectionInvalid, PyMongoError
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import SQLAlchemyError

from app.errors import ApiError

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
COLLECTION_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,119}$")

_INT = r"(?:TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT)(?:\s*\(\s*\d{1,3}\s*\))?(?:\s+UNSIGNED)?(?:\s+ZEROFILL)?"
_NUM = r"(?:DECIMAL|NUMERIC|DEC)(?:\s*\(\s*\d{1,2}\s*(?:,\s*\d{1,2}\s*)?\))?(?:\s+UNSIGNED)?"
_FLOAT = r"(?:FLOAT|DOUBLE(?:\s+PRECISION)?|REAL)(?:\s*\(\s*\d{1,2}\s*(?:,\s*\d{1,2}\s*)?\))?(?:\s+UNSIGNED)?"
_CHAR = r"(?:CHAR|VARCHAR|CHARACTER(?:\s+VARYING)?|BINARY|VARBINARY|BIT)(?:\s*\(\s*\d{1,5}\s*\))?"
_TEXT = r"(?:TINYTEXT|TEXT|MEDIUMTEXT|LONGTEXT|TINYBLOB|BLOB|MEDIUMBLOB|LONGBLOB|JSON|BOOLEAN|BOOL|UUID|DATE|YEAR)"
_TIME = r"(?:DATETIME|TIMESTAMP|TIME)(?:\s*\(\s*[0-6]\s*\))?"
MYSQL_TYPE_RE = re.compile(rf"^(?:{_INT}|{_NUM}|{_FLOAT}|{_CHAR}|{_TEXT}|{_TIME})$", re.IGNORECASE)

_PG_INT = r"(?:SMALLINT|INTEGER|INT|BIGINT|INT2|INT4|INT8|SMALLSERIAL|SERIAL|BIGSERIAL)"
_PG_NUM = r"(?:DECIMAL|NUMERIC)(?:\s*\(\s*\d{1,3}\s*(?:,\s*\d{1,3}\s*)?\))?"
_PG_FLOAT = r"(?:REAL|DOUBLE\s+PRECISION|FLOAT4|FLOAT8|FLOAT(?:\s*\(\s*\d{1,2}\s*\))?)"
_PG_CHAR = r"(?:CHAR|VARCHAR|CHARACTER(?:\s+VARYING)?)(?:\s*\(\s*\d{1,5}\s*\))?"
_PG_OTHER = (
    r"(?:TEXT|CITEXT|BYTEA|JSON|JSONB|UUID|BOOLEAN|BOOL|DATE|INTERVAL|INET|CIDR|MACADDR|MONEY|TIMESTAMPTZ|TIMETZ)"
)
_PG_TIME = r"(?:TIMESTAMP|TIME)(?:\s*\(\s*[0-6]\s*\))?(?:\s+(?:WITH|WITHOUT)\s+TIME\s+ZONE)?"
PG_TYPE_RE = re.compile(
    rf"^(?:{_PG_INT}|{_PG_NUM}|{_PG_FLOAT}|{_PG_CHAR}|{_PG_OTHER}|{_PG_TIME})(?:\s*\[\s*\])?$", re.IGNORECASE
)

_DEFAULT_KEYWORDS = re.compile(
    r"^(?:NULL|TRUE|FALSE|CURRENT_TIMESTAMP(?:\s*\(\s*[0-6]?\s*\))?|CURRENT_DATE|NOW\(\)|UUID\(\)|gen_random_uuid\(\))$",
    re.IGNORECASE,
)
_DEFAULT_NUMBER = re.compile(r"^-?\d{1,30}(?:\.\d{1,30})?$")
_DEFAULT_STRING = re.compile(r"^[A-Za-z0-9 _.,:;@/+#=()\[\]{}!?*&%<>|~^$-]{0,255}$")

ON_DELETE = {"cascade": "CASCADE", "set null": "SET NULL", "restrict": "RESTRICT"}


def check_identifier(name: Any, what: str = "name") -> str:
    if not isinstance(name, str) or not IDENTIFIER_RE.fullmatch(name):
        raise ApiError(
            422,
            "invalid_identifier",
            f"Invalid {what} {name!r}: use letters, digits and underscores (max 64, not starting with a digit)",
        )
    return name


def check_type(type_text: Any, dialect_name: str) -> str:
    if not isinstance(type_text, str):
        raise ApiError(422, "invalid_type", "Column type must be a string")
    normalized = re.sub(r"\s+", " ", type_text.strip())
    regex = PG_TYPE_RE if dialect_name == "postgresql" else MYSQL_TYPE_RE
    if not regex.fullmatch(normalized):
        raise ApiError(422, "invalid_type", f"Unsupported column type: {type_text!r}")
    return normalized.upper()


def render_default(value: Any, dialect: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    if not isinstance(value, str):
        raise ApiError(422, "invalid_default", "Default must be a string, number or boolean")
    v = value.strip()
    if _DEFAULT_KEYWORDS.fullmatch(v):
        if dialect.name == "postgresql" and v.upper() == "UUID()":
            return "gen_random_uuid()"
        if dialect.name != "postgresql" and v.lower() == "gen_random_uuid()":
            return "(UUID())"
        return v.upper() if not v.lower().startswith("gen_random") else v
    if _DEFAULT_NUMBER.fullmatch(v):
        return v
    if _DEFAULT_STRING.fullmatch(value):
        return "'" + value.replace("'", "''") + "'"
    raise ApiError(422, "invalid_default", f"Unsupported default value: {value!r}")


def build_create_table(spec: dict, dialect: Any) -> list[str]:
    """TableSpec -> DDL statements for the dialect. Raises ApiError(422) on invalid input."""
    q = dialect.identifier_preparer.quote_identifier
    pg = dialect.name == "postgresql"
    table = check_identifier(spec.get("name"), "table name")
    columns = spec.get("columns") or []
    if not columns and not spec.get("timestamps"):
        raise ApiError(422, "validation_error", "A table needs at least one column")
    seen: set[str] = set()
    lines: list[str] = []
    pk_cols: list[str] = []
    constraints: list[str] = []
    extra_statements: list[str] = []
    for col in columns:
        name = check_identifier(col.get("name"), "column name")
        if name.lower() in seen:
            raise ApiError(422, "validation_error", f"Duplicate column: {name}")
        seen.add(name.lower())
        ctype = check_type(col.get("type"), dialect.name)
        parts = [q(name), ctype]
        is_pk = bool(col.get("primary_key"))
        nullable = col.get("nullable")
        if nullable is None:
            nullable = not is_pk
        if is_pk:
            pk_cols.append(name)
            nullable = False
        auto = bool(col.get("auto_increment"))
        if auto and not re.match(r"^(TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT|INT2|INT4|INT8)\b", ctype):
            raise ApiError(422, "validation_error", f"auto_increment requires an integer column ({name})")
        if pg and auto:
            parts.append("GENERATED BY DEFAULT AS IDENTITY")
        parts.append("NULL" if nullable else "NOT NULL")
        if col.get("default") is not None and not auto:
            parts.append("DEFAULT " + render_default(col["default"], dialect))
        if auto and not pg:
            parts.append("AUTO_INCREMENT")
        if col.get("unique") and not is_pk:
            parts.append("UNIQUE")
        lines.append(" ".join(parts))
        ref = col.get("references")
        if ref:
            ref_table = check_identifier(ref.get("table"), "referenced table")
            ref_col = check_identifier(ref.get("column"), "referenced column")
            on_delete = ref.get("on_delete")
            fk = (
                f"CONSTRAINT {q(_constraint_name('fk', table, name))} FOREIGN KEY ({q(name)}) "
                f"REFERENCES {q(ref_table)} ({q(ref_col)})"
            )
            if on_delete:
                if on_delete not in ON_DELETE:
                    raise ApiError(422, "validation_error", f"Invalid on_delete: {on_delete}")
                fk += f" ON DELETE {ON_DELETE[on_delete]}"
            constraints.append(fk)
            if pg and not is_pk and not col.get("unique"):
                extra_statements.append(
                    f"CREATE INDEX {q(_constraint_name('ix', table, name))} ON {q(table)} ({q(name)})"
                )
    if spec.get("timestamps"):
        for ts in ("created_at", "updated_at"):
            if ts in seen:
                raise ApiError(422, "validation_error", f"timestamps adds {ts}; remove the explicit column")
        if pg:
            lines.append(f"{q('created_at')} TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
            lines.append(f"{q('updated_at')} TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
        else:
            lines.append(f"{q('created_at')} DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
            lines.append(f"{q('updated_at')} DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    if pk_cols:
        constraints.insert(0, "PRIMARY KEY (" + ", ".join(q(c) for c in pk_cols) + ")")
    body = ",\n  ".join(lines + constraints)
    create = f"CREATE TABLE {q(table)} (\n  {body}\n)"
    if not pg:
        create += " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    return [create, *extra_statements]


def _constraint_name(prefix: str, table: str, column: str) -> str:
    name = f"{prefix}_{table}_{column}"
    if len(name) > 64:
        import hashlib

        name = name[:55] + "_" + hashlib.sha1(name.encode()).hexdigest()[:8]
    return name


def create_table(engine: Engine, spec: dict) -> None:
    statements = build_create_table(spec, engine.dialect)
    if spec["name"] in inspect(engine).get_table_names():
        raise ApiError(409, "already_exists", f"Table '{spec['name']}' already exists")
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.exec_driver_sql(stmt.replace("%", "%%") if engine.dialect.name in ("mysql", "mariadb") else stmt)
    except SQLAlchemyError as exc:
        orig = getattr(exc, "orig", None) or exc
        raise ApiError(400, "query_failed", str(orig)[:1000]) from exc


def drop_table(engine: Engine, name: str) -> None:
    if name not in inspect(engine).get_table_names():
        raise ApiError(404, "not_found", f"Table '{name}' not found")
    q = engine.dialect.identifier_preparer.quote_identifier(name)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                f"DROP TABLE {q}".replace("%", "%%")
                if engine.dialect.name in ("mysql", "mariadb")
                else f"DROP TABLE {q}"
            )
    except SQLAlchemyError as exc:
        orig = getattr(exc, "orig", None) or exc
        raise ApiError(409, "drop_failed", str(orig)[:1000]) from exc


def check_collection_name(name: Any) -> str:
    if not isinstance(name, str) or not COLLECTION_RE.fullmatch(name) or name.startswith("system."):
        raise ApiError(422, "invalid_identifier", f"Invalid collection name {name!r}")
    return name


def normalize_validator(validator: Any) -> dict | None:
    """Accepts `{"$jsonSchema": {...}}` (or any query-style validator) or a bare JSON schema."""
    if validator in (None, {}):
        return None
    if not isinstance(validator, dict):
        raise ApiError(422, "validation_error", "validator must be an object")
    import json

    from app.services.data_browser import check_forbidden

    try:
        parsed = json_util.loads(json.dumps(validator))
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "invalid_json", f"Invalid validator: {exc}") from exc
    check_forbidden(parsed)
    if not any(str(k).startswith("$") for k in parsed):
        parsed = {"$jsonSchema": parsed}
    return parsed


def create_collection(database: Any, name: str, validator: Any = None) -> None:
    check_collection_name(name)
    parsed = normalize_validator(validator)
    try:
        if parsed:
            database.create_collection(name, validator=parsed)
        else:
            database.create_collection(name)
    except CollectionInvalid as exc:
        raise ApiError(409, "already_exists", f"Collection '{name}' already exists") from exc
    except PyMongoError as exc:
        raise ApiError(400, "query_failed", str(exc)[:1000]) from exc


def drop_collection(database: Any, name: str) -> None:
    if not list(database.list_collections(filter={"name": name})):
        raise ApiError(404, "not_found", f"Collection '{name}' not found")
    try:
        database.drop_collection(name)
    except PyMongoError as exc:
        raise ApiError(400, "query_failed", str(exc)[:1000]) from exc
