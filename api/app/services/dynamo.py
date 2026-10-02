"""Amazon DynamoDB as a NoSQL engine (docs/CLOUD.md "C2-2 as built").

A DynamoDB data source is an `external` source with engine `dynamodb` on an AWS cloud connection: one or
more tables (`cloud_state.tables`) in the connection's region. Every call uses the connection's own
credentials (`cloud_aws.AwsClient.ddb`, the one seam tests fake); the source keeps no secret of its own
(`config_encrypted` is `{}`). A source only ever reaches its own tables, so the project's API keys can't
read the account's other tables.

- Items are plain JSON both ways: numbers as numbers, binary as `{"$base64": ...}`, string / number /
  binary sets as `{"$set": [...]}` (so saving an edited item keeps a set a set).
- Documents endpoints: Query when the filter names the partition key (plus the sort key), Scan otherwise;
  equality filters only; paging with `cursor` (DynamoDB's LastEvaluatedKey). `doc_id` is the item's key
  as JSON (`{"pk": "a", "sk": 1}`) or, for a table with only a partition key, its plain value.
- Query console: one JSON request `{"operation": "Query", "TableName": ..., <AWS parameters>}` with plain
  JSON values; read-only roles may only Query, Scan and GetItem (docs/QUERY_CONSOLE.md).
- Schema: key schema, indexes and fields inferred from a sampled Scan (`introspection.analyze_documents`).
- On-demand backups (CreateBackup / ListBackups) for the backups tab, point-in-time recovery per table
  (Describe / UpdateContinuousBackups) and the checks before a restore into a new table (the restore itself is
  the `data_source.cloud_restore` job in services/cloud_db.py).

Creating and deleting tables Deployer owns are jobs in services/cloud_db.py.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from boto3.dynamodb.types import Binary, TypeDeserializer, TypeSerializer

from app.errors import ApiError, CloudError
from app.models import CloudConnection, DataSource
from app.serializers import iso

ENGINE = "dynamodb"
KEY_TYPES = {"S": "Text", "N": "Number", "B": "Binary"}
READ_OPERATIONS = ("Query", "Scan", "GetItem")
WRITE_OPERATIONS = ("PutItem", "UpdateItem", "DeleteItem")
MAX_PAGES = 5  # filtered browsing: DynamoDB applies Limit before the filter, so read a few pages
_FIELD_TYPES = {"S": "string", "N": "number", "B": "binData"}
_serializer, _deserializer = TypeSerializer(), TypeDeserializer()


def tables_of(ds: DataSource) -> list[str]:
    return list((ds.cloud_state or {}).get("tables") or [])


def aws_for(ds: DataSource):
    """The AWS client of the source's connection (its own session: safe from introspection threads)."""
    from app.db import get_sessionmaker
    from app.services import cloud, cloud_aws, connections

    connections.load_config(ds)  # 409 cloud_database_creating while the table is being created
    with get_sessionmaker()() as s:
        conn = s.get(CloudConnection, ds.cloud_connection_id) if ds.cloud_connection_id else None
        config = cloud.config_of(conn) if conn is not None else None
    if config is None:
        raise ApiError(409, "cloud_connection_missing", "This DynamoDB database's AWS account is no longer connected")
    # ponytail: a client (and with a role, an AssumeRole) per request; cache per connection if it shows.
    return cloud_aws.client(config)


def _error(exc: CloudError) -> ApiError:
    if exc.code in ("ResourceNotFoundException", "BackupNotFoundException", "TableNotFoundException"):
        return ApiError(404, "not_found", exc.message)
    if exc.code == "ConditionalCheckFailedException":
        return ApiError(409, "condition_failed", exc.message)
    if exc.code in ("ValidationException", "SerializationException"):
        return ApiError(400, "query_failed", exc.message)
    return ApiError(502, "cloud_error", exc.message)


def call(aws, operation: str, **params) -> dict:
    try:
        return aws.ddb(operation, **params)
    except CloudError as exc:
        raise _error(exc) from None


# --- values ----------------------------------------------------------------------------------------


def _bad(message: str) -> ApiError:
    return ApiError(400, "invalid_value", message)


def to_python(value: Any) -> Any:
    """Plain JSON -> what boto3's TypeSerializer takes (Decimal numbers, Binary, sets)."""
    if value is None or isinstance(value, bool | str | int | Decimal):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise _bad("DynamoDB numbers cannot be NaN or infinite")
        return Decimal(repr(value))
    if isinstance(value, dict):
        if set(value) == {"$base64"}:
            try:
                return Binary(base64.b64decode(str(value["$base64"]), validate=True))
            except (binascii.Error, ValueError) as exc:
                raise _bad("Invalid base64 value") from exc
        if set(value) == {"$set"}:
            items = [to_python(v) for v in value["$set"] or []] if isinstance(value["$set"], list) else None
            if not items:
                raise _bad('A set needs a non-empty list: {"$set": ["a", "b"]}')
            return set(items)
        return {str(k): to_python(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_python(v) for v in value]
    raise _bad(f"Unsupported value: {value!r}"[:200])


def serialize(value: Any) -> dict:
    try:
        return _serializer.serialize(to_python(value))
    except (TypeError, ValueError) as exc:
        raise _bad(str(exc)[:300]) from None


def serialize_item(doc: dict) -> dict:
    return {str(k): serialize(v) for k, v in doc.items()}


def plain(value: Any, *, for_schema: bool = False) -> Any:
    """Deserialized DynamoDB value -> JSON (`for_schema`: sets as lists, binary as bytes, for inference)."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Binary):
        value = value.value
    if isinstance(value, bytes | bytearray):
        return bytes(value) if for_schema else {"$base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, set):
        items = sorted(
            (plain(v, for_schema=for_schema) for v in value), key=lambda v: str(v) if isinstance(v, dict) else v
        )
        return items if for_schema else {"$set": items}
    if isinstance(value, dict):
        return {k: plain(v, for_schema=for_schema) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v, for_schema=for_schema) for v in value]
    return value


def item_out(raw: dict, *, for_schema: bool = False) -> dict:
    return {k: plain(_deserializer.deserialize(v), for_schema=for_schema) for k, v in raw.items()}


def _json_object(value: Any, what: str) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ApiError(400, "invalid_json", f"Invalid {what}: {exc}") from None
    if not isinstance(value, dict):
        raise ApiError(400, "invalid_json", f"{what} must be a JSON object")
    return value


# --- tables and keys ---------------------------------------------------------------------------------


def _table(ds: DataSource, name: str) -> None:
    if name not in tables_of(ds):
        raise ApiError(404, "not_found", f"Table '{name}' is not part of this database")


def describe(aws, table: str) -> dict:
    return call(aws, "DescribeTable", TableName=table)["Table"]


def key_names(desc: dict) -> list[str]:
    """[partition key, sort key?]."""
    return [k["AttributeName"] for k in sorted(desc["KeySchema"], key=lambda k: k["KeyType"] != "HASH")]


def key_of(desc: dict, doc_id: str) -> dict:
    """The typed Key of an item from its URL id: the key as JSON, or the plain value of a partition-only key."""
    names = key_names(desc)
    types = {a["AttributeName"]: a["AttributeType"] for a in desc.get("AttributeDefinitions") or []}
    try:
        parsed = json.loads(doc_id)
    except ValueError:
        parsed = None
    key = parsed if isinstance(parsed, dict) else ({names[0]: doc_id} if len(names) == 1 else None)
    if key is None or set(key) != set(names):
        example = json.dumps({n: "..." for n in names})
        raise ApiError(400, "invalid_document_id", f"The document id must be the item's key as JSON, e.g. {example}")
    out = {}
    for n in names:
        value = key[n]
        if types.get(n) == "N":
            try:
                value = Decimal(str(value))
            except InvalidOperation:
                raise _bad(f"{n} is a number key") from None
        elif types.get(n) == "B":
            value = value if isinstance(value, dict) else {"$base64": value}
        elif not isinstance(value, str):
            value = str(value)
        out[n] = serialize(value)
    return out


def _cursor_out(key: dict | None) -> str | None:
    """LastEvaluatedKey as an opaque string (plain JSON inside, so binary keys survive)."""
    return base64.urlsafe_b64encode(json.dumps(item_out(key)).encode()).decode() if key else None


def _cursor_in(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, binascii.Error):
        raise ApiError(400, "invalid_cursor", "Invalid cursor: pass next_cursor from the previous page") from None
    if not isinstance(key, dict):
        raise ApiError(400, "invalid_cursor", "Invalid cursor: pass next_cursor from the previous page")
    return serialize_item(key)


# --- data browser / data API ---------------------------------------------------------------------------


def list_documents(ds: DataSource, name: str, *, filter_json: Any, limit: int = 50, cursor: str | None = None) -> dict:
    _table(ds, name)
    aws = aws_for(ds)
    desc = describe(aws, name)
    keys = key_names(desc)
    flt = _json_object(filter_json, "filter") if filter_json not in (None, "") else {}
    names: dict[str, str] = {}
    values: dict[str, dict] = {}

    def equals(field: str, value: Any) -> str:
        i = len(names)
        names[f"#f{i}"], values[f":v{i}"] = field, serialize(value)
        return f"#f{i} = :v{i}"

    params: dict[str, Any] = {"TableName": name}
    operation, rest = "Scan", dict(flt)
    if keys[0] in flt:  # the partition key is named: read just that partition (Query), not the table
        operation = "Query"
        on_key = [k for k in keys if k in flt]
        params["KeyConditionExpression"] = " AND ".join(equals(k, rest.pop(k)) for k in on_key)
    if rest:
        params["FilterExpression"] = " AND ".join(equals(k, v) for k, v in rest.items())
    if names:
        params.update(ExpressionAttributeNames=names, ExpressionAttributeValues=values)
    limit = max(1, int(limit))
    start, items = _cursor_in(cursor), []
    for _ in range(MAX_PAGES):
        page = call(
            aws, operation, **params, Limit=limit - len(items), **({"ExclusiveStartKey": start} if start else {})
        )
        items += [item_out(i) for i in page.get("Items") or []]
        start = page.get("LastEvaluatedKey")
        if not start or len(items) >= limit:
            break
    return {
        "documents": items,
        # DynamoDB's own count (refreshed about every 6 hours); unknown with a filter.
        "total": None if flt else desc.get("ItemCount"),
        "key": keys,
        "next_cursor": _cursor_out(start),
    }


def insert_document(ds: DataSource, name: str, document: Any) -> dict:
    _table(ds, name)
    aws = aws_for(ds)
    keys = key_names(describe(aws, name))
    doc = _json_object(document, "document")
    missing = [k for k in keys if k not in doc]
    if missing:
        raise ApiError(
            400, "missing_key", f"Every item needs its key: {', '.join(keys)} (missing {', '.join(missing)})"
        )
    item = serialize_item(doc)
    try:
        call(
            aws,
            "PutItem",
            TableName=name,
            Item=item,
            ConditionExpression="attribute_not_exists(#k)",
            ExpressionAttributeNames={"#k": keys[0]},
        )
    except ApiError as exc:
        if exc.code == "condition_failed":
            raise ApiError(409, "document_exists", "An item with this key already exists; edit that one") from None
        raise
    return {"document": item_out(item)}


def update_document(ds: DataSource, name: str, doc_id: str, set_values: Any, unset: list[str] | None) -> dict:
    _table(ds, name)
    aws = aws_for(ds)
    desc = describe(aws, name)
    keys = key_names(desc)
    set_doc = _json_object(set_values or {}, "set")
    unset = unset or []
    if not all(isinstance(u, str) and u for u in unset):
        raise ApiError(422, "validation_error", "unset must be a list of attribute names")
    if any(k in keys for k in [*set_doc, *unset]):
        raise ApiError(
            400, "immutable_field", f"The key ({', '.join(keys)}) cannot change: insert a new item and delete this one"
        )
    if not set_doc and not unset:
        raise ApiError(400, "empty_update", "Nothing to update")
    names, values = {"#k": keys[0]}, {}
    sets = []
    for i, (field, value) in enumerate(set_doc.items()):
        names[f"#s{i}"], values[f":s{i}"] = field, serialize(value)
        sets.append(f"#s{i} = :s{i}")
    removes = []
    for i, field in enumerate(unset):
        names[f"#r{i}"] = field
        removes.append(f"#r{i}")
    expression = " ".join(
        part
        for part in ("SET " + ", ".join(sets) if sets else "", "REMOVE " + ", ".join(removes) if removes else "")
        if part
    )
    try:
        out = call(
            aws,
            "UpdateItem",
            TableName=name,
            Key=key_of(desc, doc_id),
            UpdateExpression=expression,
            ConditionExpression="attribute_exists(#k)",
            ExpressionAttributeNames=names,
            **({"ExpressionAttributeValues": values} if values else {}),
            ReturnValues="ALL_NEW",
        )
    except ApiError as exc:
        if exc.code == "condition_failed":
            raise ApiError(404, "document_not_found", "Document not found") from None
        raise
    return {"document": item_out(out.get("Attributes") or {})}


def delete_document(ds: DataSource, name: str, doc_id: str) -> dict:
    _table(ds, name)
    aws = aws_for(ds)
    desc = describe(aws, name)
    try:
        call(
            aws,
            "DeleteItem",
            TableName=name,
            Key=key_of(desc, doc_id),
            ConditionExpression="attribute_exists(#k)",
            ExpressionAttributeNames={"#k": key_names(desc)[0]},
        )
    except ApiError as exc:
        if exc.code == "condition_failed":
            raise ApiError(404, "document_not_found", "Document not found") from None
        raise
    return {"ok": True}


NO_COLLECTION_CHANGES = (
    "Tables of a DynamoDB database are added in AWS: create one with Add database -> In your AWS account, or "
    "create it in the AWS console and connect it. Delete tables in the AWS console, or remove this database."
)


def run_op(ds: DataSource, op: str, args: dict) -> Any:
    """source_ops' documents operations on DynamoDB items (services/source_ops.py)."""
    name = args.get("name") or ""
    if op == "documents.list":
        return list_documents(
            ds, name, filter_json=args.get("filter"), limit=int(args.get("limit", 50)), cursor=args.get("cursor")
        )
    if op == "documents.insert":
        return insert_document(ds, name, args.get("document"))
    if op == "documents.update":
        return update_document(ds, name, str(args.get("doc_id") or ""), args.get("set") or {}, args.get("unset"))
    if op == "documents.delete":
        return delete_document(ds, name, str(args.get("doc_id") or ""))
    raise ApiError(400, "not_supported", NO_COLLECTION_CHANGES)


# --- schema ------------------------------------------------------------------------------------------


def table_entity(aws, table: str, sample: int) -> dict:
    from app.services.introspection import analyze_documents

    desc = describe(aws, table)
    keys = key_names(desc)
    items = (call(aws, "Scan", TableName=table, Limit=sample).get("Items") or []) if sample > 0 else []
    fields = analyze_documents([item_out(i, for_schema=True) for i in items])
    types = {a["AttributeName"]: a["AttributeType"] for a in desc.get("AttributeDefinitions") or []}
    indexes = [{"name": "primary key", "fields": keys, "unique": True}]
    for ix in (desc.get("GlobalSecondaryIndexes") or []) + (desc.get("LocalSecondaryIndexes") or []):
        ix_keys = [k["AttributeName"] for k in sorted(ix["KeySchema"], key=lambda k: k["KeyType"] != "HASH")]
        indexes.append({"name": ix["IndexName"], "fields": ix_keys, "unique": False})
    by_name = {f["name"]: f for f in fields}
    for k in reversed(keys):  # key attributes first, even when the sample was empty
        f = by_name.pop(k, None) or {
            "name": k,
            "data_type": _FIELD_TYPES.get(types.get(k, ""), "string"),
            "default": None,
            "foreign_key": None,
            "occurrence": 1.0,
        }
        fields = [f, *[x for x in fields if x["name"] != k]]
    indexed = {ix["fields"][0] for ix in indexes}
    for f in fields:
        f["primary_key"] = f["name"] in keys
        f["unique"] = keys == [f["name"]]
        f["indexed"] = f["name"] in indexed
        if f["primary_key"]:
            f["nullable"] = False
    return {
        "name": table,
        "type": "collection",
        "row_count": desc.get("ItemCount"),
        "fields": fields,
        "indexes": indexes,
        "validator": None,
    }


def introspect(ds: DataSource, sample: int, only: str | None = None) -> list[dict]:
    from app.services.introspection import MAX_SAMPLE

    aws = aws_for(ds)
    sample = max(0, min(int(sample), MAX_SAMPLE))
    return [table_entity(aws, t, sample) for t in sorted(tables_of(ds)) if only in (None, t)]


def entity(ds: DataSource, name: str, sample: int) -> dict | None:
    if name not in tables_of(ds):
        return None
    return introspect(ds, sample, only=name)[0]


def check(ds: DataSource) -> tuple[bool, str, str | None]:
    """`connections.try_source` for DynamoDB: every table answers DescribeTable."""
    try:
        aws = aws_for(ds)
        states = [describe(aws, t).get("TableStatus") for t in tables_of(ds)]
    except ApiError as exc:
        return False, exc.message, None
    if not states:
        return False, "No tables", None
    busy = [s for s in states if s != "ACTIVE"]
    noun = "table" if len(states) == 1 else "tables"
    return True, f"Connected ({len(states)} {noun}{', ' + busy[0].lower() if busy else ''})", None


def export_script(ds: DataSource) -> str:
    """The schema export's chunk: each table's key schema and indexes, as CreateTable input JSON."""
    aws = aws_for(ds)
    lines = [f"// DynamoDB source {ds.name} ({(ds.cloud_state or {}).get('region')}): CreateTable input per table"]
    for t in sorted(tables_of(ds)):
        desc = describe(aws, t)
        spec = {
            "TableName": t,
            "KeySchema": desc["KeySchema"],
            "AttributeDefinitions": desc.get("AttributeDefinitions"),
            "BillingMode": (desc.get("BillingModeSummary") or {}).get("BillingMode", "PROVISIONED"),
        }
        for kind in ("GlobalSecondaryIndexes", "LocalSecondaryIndexes"):
            if desc.get(kind):
                spec[kind] = [{k: ix[k] for k in ("IndexName", "KeySchema", "Projection")} for ix in desc[kind]]
        lines += ["// " + line for line in json.dumps(spec, indent=2).splitlines()]
    return "\n".join(lines) + "\n"


# --- query console -----------------------------------------------------------------------------------


def run_console(ds: DataSource, query: str, *, max_rows: int, read_only: bool) -> dict:
    """docs/QUERY_CONSOLE.md "DynamoDB": one JSON request; the answer has the MongoDB console's shape."""
    started = time.monotonic()

    def out(result: Any = None, docs: list | None = None, output: str = "", truncated=False, error=None) -> dict:
        return {
            "kind": "nosql",
            "engine": ENGINE,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "output": output,
            "result": result,
            "result_docs": docs,
            "truncated": truncated,
            "error": {"code": "query_failed", "message": error} if error else None,
        }

    try:
        request = _json_object(query, "request")
    except ApiError as exc:
        return out(error=exc.message + ' - write one JSON object, e.g. {"operation": "Scan", "TableName": "..."}')
    request = dict(request)
    operation = request.pop("operation", None)
    if operation not in READ_OPERATIONS + WRITE_OPERATIONS:
        allowed = ", ".join(READ_OPERATIONS + WRITE_OPERATIONS)
        return out(error=f'"operation" must be one of {allowed}')
    if read_only and operation not in READ_OPERATIONS:
        raise ApiError(403, "read_only_role", f"Viewers may only run {', '.join(READ_OPERATIONS)} ({operation} writes)")
    if request.get("TableName") not in tables_of(ds):
        return out(error=f"TableName must be one of this database's tables: {', '.join(tables_of(ds))}")
    try:
        for field in ("Key", "Item", "ExclusiveStartKey", "ExpressionAttributeValues"):
            if field in request:
                request[field] = serialize_item(_json_object(request[field], field))
    except ApiError as exc:
        return out(error=exc.message)
    if operation in ("Query", "Scan"):
        try:
            request["Limit"] = max(1, min(int(request.get("Limit") or max_rows), max_rows))
        except (TypeError, ValueError):
            return out(error="Limit must be a number")
    aws = aws_for(ds)
    try:
        raw = aws.ddb(operation, **request)
    except CloudError as exc:
        return out(error=exc.message)
    result: dict[str, Any] = {}
    docs: list[dict] = []
    for field in ("Items", "Item", "Attributes", "LastEvaluatedKey"):
        if field == "Items" and field in raw:
            docs = [item_out(i) for i in raw["Items"]]
            result["Items"] = docs
        elif field in raw:
            result[field] = item_out(raw[field])
            if field != "LastEvaluatedKey":
                docs = [result[field]]
    for field in ("Count", "ScannedCount", "ConsumedCapacity"):
        if field in raw:
            result[field] = plain(raw[field])
    more = "LastEvaluatedKey" in raw
    lines = [f"{operation}: {len(docs)} item{'' if len(docs) == 1 else 's'}"]
    if "ScannedCount" in raw:
        lines[0] += f" ({raw['ScannedCount']} read)"
    if more:
        lines.append("More items: send LastEvaluatedKey (above) as ExclusiveStartKey for the next page.")
    reads = operation in READ_OPERATIONS
    return out(result=result, docs=docs if reads or docs else None, output="\n".join(lines), truncated=more)


# --- connection details ---------------------------------------------------------------------------------


def display(ds: DataSource) -> dict:
    region = (ds.cloud_state or {}).get("region")
    return {"host": f"dynamodb.{region}.amazonaws.com", "port": 443, "username": None, "tls": True}


def connection_info(ds: DataSource) -> dict:
    """No password: apps use AWS credentials (App Runner: its instance role)."""
    from app.services import connections

    connections.load_config(ds)
    state = ds.cloud_state or {}
    tables = list(state.get("tables") or [])
    return {
        "uri": None,
        "host": f"dynamodb.{state.get('region')}.amazonaws.com",
        "port": 443,
        "username": None,
        "password": None,
        "database": tables[0] if tables else None,
        "region": state.get("region"),
        "tables": tables,
        "external_hint": (
            "DynamoDB has no password: use an AWS SDK with the region and table names. Apps on AWS App Runner "
            "with Database access get DEPLOYER_DB_<NAME>_TABLE / _TABLES / _REGION and an IAM role allowed "
            "to use exactly these tables. Anywhere else, use AWS credentials that may access them."
        ),
    }


# --- on-demand backups ---------------------------------------------------------------------------------


def backup_name(table: str) -> str:
    return f"{table}-{datetime.now(UTC):%Y%m%d%H%M%S}"[:255]


def _backup_out(table: str, b: dict) -> dict:
    created = b.get("BackupCreationDateTime")
    return {
        "table": table,
        "arn": b.get("BackupArn"),
        "name": b.get("BackupName"),
        "status": b.get("BackupStatus"),
        "type": b.get("BackupType"),
        "size_bytes": b.get("BackupSizeBytes"),
        "created_at": iso(created.astimezone(UTC).replace(tzinfo=None)) if isinstance(created, datetime) else created,
    }


def list_backups(ds: DataSource) -> list[dict]:
    aws = aws_for(ds)
    out = []
    for t in tables_of(ds):
        out += [_backup_out(t, b) for b in call(aws, "ListBackups", TableName=t).get("BackupSummaries") or []]
    return sorted(out, key=lambda b: str(b["created_at"] or ""), reverse=True)


def create_backups(ds: DataSource, table: str | None = None) -> list[dict]:
    if table is not None:
        _table(ds, table)
    aws = aws_for(ds)
    out = []
    for t in [table] if table else tables_of(ds):
        details = call(aws, "CreateBackup", TableName=t, BackupName=backup_name(t))["BackupDetails"]
        out.append(_backup_out(t, details))
    return out


# --- point-in-time recovery and restores (docs/CLOUD.md "C2-2", "Point-in-time recovery and restores") -----


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _iso_utc(value: Any) -> str | None:
    when = _utc(value)
    return iso(when.replace(tzinfo=None)) if when else None


def _pitr_out(table: str, description: dict) -> dict:
    d = description.get("PointInTimeRecoveryDescription") or {}
    return {
        "table": table,
        "status": d.get("PointInTimeRecoveryStatus") or "DISABLED",  # ENABLED / DISABLED
        "earliest": _iso_utc(d.get("EarliestRestorableDateTime")),
        "latest": _iso_utc(d.get("LatestRestorableDateTime")),
        "days": d.get("RecoveryPeriodInDays"),
        "problem": None,
    }


def _pitr_raw(aws, table: str) -> dict:
    return call(aws, "DescribeContinuousBackups", TableName=table)["ContinuousBackupsDescription"]


def pitr_status(ds: DataSource) -> list[dict]:
    """Point-in-time recovery of each table; `problem` instead when AWS refuses to say (e.g. an older policy)."""
    aws = aws_for(ds)
    out = []
    for t in tables_of(ds):
        try:
            out.append(_pitr_out(t, _pitr_raw(aws, t)))
        except ApiError as exc:
            empty = dict.fromkeys(("status", "earliest", "latest", "days"))
            out.append({"table": t, **empty, "problem": exc.message})
    return out


def set_pitr(ds: DataSource, table: str, enabled: bool) -> dict:
    _table(ds, table)
    out = call(
        aws_for(ds),
        "UpdateContinuousBackups",
        TableName=table,
        PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": enabled},
    )
    return _pitr_out(table, out["ContinuousBackupsDescription"])


def restore_spec(
    ds: DataSource, *, backup_arn: str | None, table: str | None, point_in_time: datetime | None, latest: bool
) -> dict:
    """What a restore will copy, checked against this source's own tables (a source never reaches another
    table's backups): an AVAILABLE backup of one of its tables, or a time inside a table's recovery window."""
    aws = aws_for(ds)
    if backup_arn:
        desc = call(aws, "DescribeBackup", BackupArn=backup_arn)["BackupDescription"]
        source_table = (desc.get("SourceTableDetails") or {}).get("TableName")
        if source_table not in tables_of(ds):
            raise ApiError(404, "not_found", "This backup is not of one of this database's tables")
        details = desc.get("BackupDetails") or {}
        if details.get("BackupStatus") != "AVAILABLE":
            raise ApiError(409, "backup_not_ready", "AWS is still making this backup: restore it once it is available")
        return {"kind": "backup", "table": source_table, "backup_arn": backup_arn, "backup": details.get("BackupName")}
    if not table:
        raise ApiError(422, "validation_error", "Pick a backup, or a table and a time", {"field": "backup_arn"})
    _table(ds, table)
    d = _pitr_raw(aws, table).get("PointInTimeRecoveryDescription") or {}
    if d.get("PointInTimeRecoveryStatus") != "ENABLED":
        raise ApiError(
            409,
            "pitr_not_enabled",
            f"Point-in-time recovery is off for {table}: turn it on first (it only covers the time after that)",
        )
    if latest:
        return {"kind": "point_in_time", "table": table, "latest": True}
    when = _utc(point_in_time)
    earliest, newest = _utc(d.get("EarliestRestorableDateTime")), _utc(d.get("LatestRestorableDateTime"))
    if when is None or (earliest and when < earliest) or (newest and when > newest):
        raise ApiError(
            400,
            "invalid_restore_time",
            f"Pick a time between {_iso_utc(earliest)} and {_iso_utc(newest)} (UTC)",
            {"field": "point_in_time"},
        )
    return {"kind": "point_in_time", "table": table, "time": when.isoformat()}  # exact: the job sends it as is
