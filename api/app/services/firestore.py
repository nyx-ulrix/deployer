"""Cloud Firestore as a NoSQL engine (docs/CLOUD.md "C2-3 as built").

A Firestore data source is an `external` source with engine `firestore` on a Firebase cloud connection: one
Firestore database - `(default)` or a named one - of the connection's Google project (`cloud_state.database`).
Every call uses the connection's service-account key through `cloud_gcp.GcpClient.firestore` (the seam tests
fake); the source keeps no secret of its own (`config_encrypted` is `{}`).

- Documents are plain JSON both ways with the document id as `_id`: timestamps `{"$timestamp": "<RFC 3339>"}`,
  bytes `{"$base64": ...}`, references `{"$ref": "users/u1"}` (a document path in the same database), geo
  points `{"$geo": {"latitude": .., "longitude": ..}}`; whole numbers are integers, others doubles.
- Collections are paths: `users`, or a subcollection `users/u1/orders`. The schema and the Data tab list the
  top-level collections; `subcollections` lists one document's own.
- Documents endpoints: equality filters (dotted names reach into maps, `_id` is the document id), ordered by
  document id, paged with `cursor`; `total` comes from a count aggregation.
- Query console: one JSON request, a subset of Firestore's structuredQuery (docs/QUERY_CONSOLE.md
  "Firestore"); read-only roles may only `query`, `count` and `get`.
- Schema: top-level collections, fields inferred from sampled documents, composite indexes.
- Export: every document of the top-level collections (or the given collection paths) as one JSON object.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from app.errors import ApiError, CloudError
from app.models import CloudConnection, DataSource
from app.serializers import iso

ENGINE = "firestore"
DEFAULT_DATABASE = "(default)"
DATABASE_ID = re.compile(r"^(\(default\)|[a-z][a-z0-9-]{2,61}[a-z0-9])$")
READ_OPERATIONS = ("query", "count", "get")
WRITE_OPERATIONS = ("create", "update", "delete")
QUERY_KEYS = ("from", "where", "orderBy", "select", "limit", "offset")
EXPORT_LIMIT = 10_000  # documents per export call (the answer is one JSON object in memory)
PAGE = 300
OPS = {
    "==": "EQUAL",
    "!=": "NOT_EQUAL",
    "<": "LESS_THAN",
    "<=": "LESS_THAN_OR_EQUAL",
    ">": "GREATER_THAN",
    ">=": "GREATER_THAN_OR_EQUAL",
    "array-contains": "ARRAY_CONTAINS",
    "array-contains-any": "ARRAY_CONTAINS_ANY",
    "in": "IN",
    "not-in": "NOT_IN",
}
UNARY = ("IS_NULL", "IS_NAN", "IS_NOT_NULL", "IS_NOT_NAN")
NO_COLLECTION_CHANGES = (
    "Firestore creates a collection with its first document: open the collection by name (Data tab -> Open a "
    "collection path) and insert a document. Delete collections in the Firebase console."
)
_SIMPLE_FIELD = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
_BY_ID = [{"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}]


def database_of(ds: DataSource) -> str:
    return (ds.cloud_state or {}).get("database") or DEFAULT_DATABASE


def root_of(ds: DataSource) -> str:
    """The resource name documents live under (references are full names in Firestore)."""
    return f"projects/{(ds.cloud_state or {}).get('project_id')}/databases/{database_of(ds)}/documents"


def gcp_for(ds: DataSource):
    """The Google client of the source's Firebase connection (its own session: safe from introspection threads)."""
    from app.db import get_sessionmaker
    from app.services import cloud, cloud_gcp, connections

    connections.load_config(ds)
    with get_sessionmaker()() as s:
        conn = s.get(CloudConnection, ds.cloud_connection_id) if ds.cloud_connection_id else None
        config = cloud.config_of(conn) if conn is not None else None
    if config is None:
        raise ApiError(
            409, "cloud_connection_missing", "This Firestore database's Firebase project is no longer connected"
        )
    return cloud_gcp.client(config)


def _error(exc: CloudError) -> ApiError:
    if exc.code == "NOT_FOUND" or exc.status == 404:
        return ApiError(404, "not_found", exc.message)
    if exc.code == "ALREADY_EXISTS" or exc.status == 409:
        return ApiError(409, "document_exists", "A document with this id already exists; edit that one")
    if exc.code in ("INVALID_ARGUMENT", "FAILED_PRECONDITION") or exc.status == 400:
        return ApiError(400, "query_failed", exc.message)  # FAILED_PRECONDITION: a missing index, with its link
    if exc.code == "PERMISSION_DENIED" or exc.status == 403:
        return ApiError(
            502,
            "cloud_error",
            exc.message + " - the Firebase service account needs the Cloud Datastore User role and the Cloud "
            "Firestore API turned on (Settings -> Cloud accounts shows how).",
        )
    return ApiError(502, "cloud_error", exc.message)


def call(gcp, method: str, path: str, body: Any = None, params: Any = None) -> Any:
    try:
        return gcp.firestore(method, path, body, params)
    except CloudError as exc:
        raise _error(exc) from None


# --- paths -------------------------------------------------------------------------------------------


def check_path(path: Any, kind: str) -> list[str]:
    """`users` / `users/u1/orders` (collection: odd segments) or `users/u1` (document: even)."""
    parts = str(path or "").strip("/").split("/")
    if (
        not isinstance(path, str)
        or any(p in ("", ".", "..") or len(p.encode()) > 1500 for p in parts)
        or (len(parts) % 2 == 1) != (kind == "collection")
    ):
        example = "users, or users/u1/orders for a subcollection" if kind == "collection" else "users/u1"
        raise ApiError(400, "invalid_path", f"Not a Firestore {kind} path (e.g. {example}): {str(path)[:200]!r}")
    return parts


def _doc_id(value: Any) -> str:
    if not isinstance(value, str) or "/" in value:
        raise ApiError(400, "invalid_document_id", "A document id is text without '/'")
    return check_path(f"x/{value}", "document")[1]


def url(ds: DataSource, parts: list[str] | tuple = (), verb: str = "") -> str:
    """The REST path under projects/<project>/ (each id percent-encoded, so `:` or `#` in an id stay ids)."""
    tail = "".join("/" + quote(p, safe="") for p in parts)
    return f"databases/{quote(database_of(ds), safe='()')}/documents{tail}" + (f":{verb}" if verb else "")


def _segment(name: str) -> str:
    """One field name as a field path segment: backticks around anything but letters, digits and _."""
    if _SIMPLE_FIELD.match(name):
        return name
    return "`" + name.replace("\\", "\\\\").replace("`", "\\`") + "`"


def field_path(dotted: str) -> str:
    """A filter / order field: dots reach into maps (`address.city`)."""
    if not isinstance(dotted, str) or not dotted:
        raise ApiError(400, "query_failed", "A field name is required")
    return ".".join(_segment(s) for s in dotted.split("."))


# --- values ------------------------------------------------------------------------------------------


def _bad(message: str) -> ApiError:
    return ApiError(400, "invalid_value", message)


def to_value(v: Any, root: str) -> dict:
    """Plain JSON (with the `$` forms above) -> a Firestore Value."""
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        if not -(2**63) <= v < 2**63:
            raise _bad("Whole numbers must fit in 64 bits")
        return {"integerValue": str(v)}
    if isinstance(v, float):
        if not math.isfinite(v):
            raise _bad("Numbers cannot be NaN or infinite")
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, list | tuple):
        return {"arrayValue": {"values": [to_value(x, root) for x in v]}}
    if isinstance(v, dict):
        if len(v) == 1:
            ((k, x),) = v.items()
            if k == "$timestamp":
                if not isinstance(x, str):
                    raise _bad('A timestamp is {"$timestamp": "2026-01-01T00:00:00Z"}')
                return {"timestampValue": x}
            if k == "$base64":
                try:
                    base64.b64decode(str(x), validate=True)
                except (binascii.Error, ValueError):
                    raise _bad("Invalid base64 value") from None
                return {"bytesValue": str(x)}
            if k == "$ref":
                return {"referenceValue": f"{root}/{'/'.join(check_path(x, 'document'))}"}
            if k == "$geo":
                if not (
                    isinstance(x, dict) and all(isinstance(x.get(c), int | float) for c in ("latitude", "longitude"))
                ):
                    raise _bad('A geo point is {"$geo": {"latitude": 1.5, "longitude": 2.5}}')
                return {"geoPointValue": {"latitude": float(x["latitude"]), "longitude": float(x["longitude"])}}
        return {"mapValue": {"fields": {str(k): to_value(x, root) for k, x in v.items()}}}
    raise _bad(f"Unsupported value: {v!r}"[:200])


def from_value(v: dict, root: str, for_schema: bool = False) -> Any:
    """A Firestore Value -> plain JSON (`for_schema`: datetimes, bytes and plain paths, for inference)."""
    if "booleanValue" in v:
        return bool(v["booleanValue"])
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        d = float(v["doubleValue"])
        return d if math.isfinite(d) else str(v["doubleValue"])  # "NaN" / "Infinity" are not JSON numbers
    if "timestampValue" in v:
        ts = str(v["timestampValue"])
        if for_schema:
            try:
                return datetime.fromisoformat(ts)
            except ValueError:
                return ts
        return {"$timestamp": ts}
    if "stringValue" in v:
        return v["stringValue"]
    if "bytesValue" in v:
        return base64.b64decode(v["bytesValue"]) if for_schema else {"$base64": v["bytesValue"]}
    if "referenceValue" in v:
        ref = str(v["referenceValue"])
        rel = ref.removeprefix(root + "/")
        return rel if for_schema else {"$ref": rel}
    if "geoPointValue" in v:
        g = v["geoPointValue"] or {}
        return {"$geo": {"latitude": g.get("latitude", 0.0), "longitude": g.get("longitude", 0.0)}}
    if "arrayValue" in v:
        return [from_value(x, root, for_schema) for x in (v["arrayValue"] or {}).get("values") or []]
    if "mapValue" in v:
        return {k: from_value(x, root, for_schema) for k, x in ((v["mapValue"] or {}).get("fields") or {}).items()}
    return None  # nullValue


def doc_out(doc: dict, root: str, *, for_schema: bool = False, path: bool = False) -> dict:
    """`{"_id": <document id>, ...fields}` (`path`: also `_path`, the document's path, for console answers).
    A stored field literally named `_id` is not shown (the id wins)."""
    name = str(doc.get("name") or "")
    out: dict[str, Any] = {"_id": name.rsplit("/", 1)[-1]}
    if path:
        out["_path"] = name.removeprefix(root + "/")
    for k, v in (doc.get("fields") or {}).items():
        if k not in out:
            out[k] = from_value(v, root, for_schema)
    return out


def _fields(doc: dict, root: str) -> dict:
    return {str(k): to_value(v, root) for k, v in doc.items()}


def _json_object(value: Any, what: str) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ApiError(400, "invalid_json", f"Invalid {what}: {exc}") from None
    if not isinstance(value, dict):
        raise ApiError(400, "invalid_json", f"{what} must be a JSON object")
    return value


# --- queries -----------------------------------------------------------------------------------------


def _documents(gcp, ds: DataSource, parent: list[str], query: dict) -> list[dict]:
    out = call(gcp, "POST", url(ds, parent, "runQuery"), {"structuredQuery": query})
    return [r["document"] for r in out or [] if isinstance(r, dict) and r.get("document")]


def _count(gcp, ds: DataSource, parent: list[str], query: dict) -> int:
    body = {"structuredAggregationQuery": {"structuredQuery": query, "aggregations": [{"alias": "n", "count": {}}]}}
    for r in call(gcp, "POST", url(ds, parent, "runAggregationQuery"), body) or []:
        fields = ((r or {}).get("result") or {}).get("aggregateFields") or {}
        if "n" in fields:
            return int(fields["n"].get("integerValue") or 0)
    return 0


def collection_ids(gcp, ds: DataSource, parent: list[str]) -> list[str]:
    """The collections directly under `parent` (the database itself when empty), all pages."""
    ids, token = [], None
    for _ in range(50):
        body = {"pageSize": PAGE, **({"pageToken": token} if token else {})}
        out = call(gcp, "POST", url(ds, parent, "listCollectionIds"), body) or {}
        ids += out.get("collectionIds") or []
        token = out.get("nextPageToken")
        if not token:
            break
    return sorted(ids)


def _and(filters: list[dict]) -> dict | None:
    if not filters:
        return None
    return filters[0] if len(filters) == 1 else {"compositeFilter": {"op": "AND", "filters": filters}}


def _equality(flt: dict, root: str, parts: list[str]) -> dict | None:
    filters = []
    for k, v in flt.items():
        if k == "_id":
            field, value = "__name__", {"referenceValue": f"{root}/{'/'.join([*parts, _doc_id(v)])}"}
        else:
            field, value = field_path(k), to_value(v, root)
        filters.append({"fieldFilter": {"field": {"fieldPath": field}, "op": "EQUAL", "value": value}})
    return _and(filters)


def _cursor_out(doc: dict) -> str:
    return base64.urlsafe_b64encode(str(doc["name"]).rsplit("/", 1)[-1].encode()).decode()


def _cursor_in(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        return _doc_id(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, binascii.Error, ApiError):
        raise ApiError(400, "invalid_cursor", "Invalid cursor: pass next_cursor from the previous page") from None


# --- data browser / data API ---------------------------------------------------------------------------


def list_documents(ds: DataSource, name: str, *, filter_json: Any, limit: int = 50, cursor: str | None = None) -> dict:
    parts = check_path(name, "collection")
    root = root_of(ds)
    flt = _json_object(filter_json, "filter") if filter_json not in (None, "") else {}
    where = _equality(flt, root, parts)
    start = _cursor_in(cursor)
    gcp = gcp_for(ds)
    query: dict[str, Any] = {"from": [{"collectionId": parts[-1]}], **({"where": where} if where else {})}
    limit = max(1, int(limit))
    page = {**query, "orderBy": _BY_ID, "limit": limit + 1}
    if start:
        page["startAt"] = {"values": [{"referenceValue": f"{root}/{name.strip('/')}/{start}"}], "before": False}
    docs = _documents(gcp, ds, parts[:-1], page)
    more = len(docs) > limit
    docs = docs[:limit]
    return {
        "documents": [doc_out(d, root) for d in docs],
        "total": _count(gcp, ds, parts[:-1], query),
        "next_cursor": _cursor_out(docs[-1]) if more and docs else None,
    }


def insert_document(ds: DataSource, name: str, document: Any) -> dict:
    """`_id` in the document is its id; without one Firestore generates it."""
    parts = check_path(name, "collection")
    doc = dict(_json_object(document, "document"))
    doc_id = _doc_id(doc.pop("_id")) if "_id" in doc else None
    root = root_of(ds)
    out = call(
        gcp_for(ds),
        "POST",
        url(ds, parts),
        {"fields": _fields(doc, root)},
        {"documentId": doc_id} if doc_id else None,
    )
    return {"document": doc_out(out, root)}


def update_document(ds: DataSource, name: str, doc_id: str, set_values: Any, unset: list[str] | None) -> dict:
    """Sets / removes top-level fields of an existing document (an update mask of exactly those fields)."""
    parts = [*check_path(name, "collection"), _doc_id(doc_id)]
    set_doc = _json_object(set_values or {}, "set")
    unset = unset or []
    if not all(isinstance(u, str) and u for u in unset):
        raise ApiError(422, "validation_error", "unset must be a list of field names")
    if "_id" in set_doc or "_id" in unset:
        raise ApiError(
            400, "immutable_field", "The document id cannot change: insert a new document and delete this one"
        )
    if not set_doc and not unset:
        raise ApiError(400, "empty_update", "Nothing to update")
    root = root_of(ds)
    params = [("updateMask.fieldPaths", _segment(k)) for k in [*set_doc, *unset]]
    params.append(("currentDocument.exists", "true"))
    try:
        out = call(gcp_for(ds), "PATCH", url(ds, parts), {"fields": _fields(set_doc, root)}, params)
    except ApiError as exc:
        if exc.code == "not_found":  # currentDocument.exists failed
            raise ApiError(404, "document_not_found", "Document not found") from None
        raise
    return {"document": doc_out(out, root)}


def delete_document(ds: DataSource, name: str, doc_id: str) -> dict:
    parts = [*check_path(name, "collection"), _doc_id(doc_id)]
    try:
        call(gcp_for(ds), "DELETE", url(ds, parts), params={"currentDocument.exists": "true"})
    except ApiError as exc:
        if exc.code == "not_found":  # currentDocument.exists failed
            raise ApiError(404, "document_not_found", "Document not found") from None
        raise
    return {"ok": True}


def subcollections(ds: DataSource, name: str, doc_id: str) -> dict:
    """The collections under one document, as paths the documents endpoints take."""
    parts = [*check_path(name, "collection"), _doc_id(doc_id)]
    prefix = "/".join(parts)
    return {"collections": [f"{prefix}/{c}" for c in collection_ids(gcp_for(ds), ds, parts)]}


def run_op(ds: DataSource, op: str, args: dict) -> Any:
    """source_ops' documents operations (services/source_ops.py)."""
    name = args.get("name")
    if op == "documents.list":
        return list_documents(
            ds, name, filter_json=args.get("filter"), limit=int(args.get("limit", 50)), cursor=args.get("cursor")
        )
    if op == "documents.insert":
        return insert_document(ds, name, args.get("document"))
    if op == "documents.update":
        return update_document(ds, name, args.get("doc_id"), args.get("set") or {}, args.get("unset"))
    if op == "documents.delete":
        return delete_document(ds, name, args.get("doc_id"))
    raise ApiError(400, "not_supported", NO_COLLECTION_CHANGES)


# --- schema ------------------------------------------------------------------------------------------


def composite_indexes(gcp, ds: DataSource) -> dict[str, list[dict]] | None:
    """Composite indexes by collection group (None when the service account may not list them)."""
    out: dict[str, list[dict]] = {}
    token = None
    path = f"databases/{quote(database_of(ds), safe='()')}/collectionGroups/-/indexes"
    for _ in range(20):
        try:
            page = gcp.firestore("GET", path, None, {"pageToken": token} if token else None) or {}
        except CloudError:
            return None
        for ix in page.get("indexes") or []:
            group = str(ix.get("name") or "").split("/collectionGroups/")[-1].split("/")[0]
            out.setdefault(group, []).append(ix)
        token = page.get("nextPageToken")
        if not token:
            break
    return out


def collection_entity(gcp, ds: DataSource, path: str, sample: int, indexes: list[dict]) -> dict:
    from app.services.introspection import analyze_documents

    parts = check_path(path, "collection")
    root = root_of(ds)
    query = {"from": [{"collectionId": parts[-1]}]}
    docs = _documents(gcp, ds, parts[:-1], {**query, "limit": sample}) if sample > 0 else []
    fields = analyze_documents([doc_out(d, root, for_schema=True) for d in docs])
    if not fields:
        fields = analyze_documents([{"_id": ""}])
    for f in fields:
        f["indexed"] = True  # Firestore indexes every field by itself (unless exempted in the console)
        if f["name"] == "_id":
            f["data_type"], f["nullable"], f["occurrence"] = "string", False, 1.0
    out_indexes = [{"name": "document id", "fields": ["_id"], "unique": True}]
    for ix in indexes:
        names = [f.get("fieldPath") for f in ix.get("fields") or [] if f.get("fieldPath") != "__name__"]
        out_indexes.append({"name": str(ix.get("name") or "").rsplit("/", 1)[-1], "fields": names, "unique": False})
    return {
        "name": path,
        "type": "collection",
        "row_count": _count(gcp, ds, parts[:-1], query),
        "fields": fields,
        "indexes": out_indexes,
        "validator": None,
    }


def introspect(ds: DataSource, sample: int, only: str | None = None) -> list[dict]:
    from app.services.introspection import MAX_SAMPLE

    gcp = gcp_for(ds)
    sample = max(0, min(int(sample), MAX_SAMPLE))
    names = [only] if only else collection_ids(gcp, ds, [])
    indexes = composite_indexes(gcp, ds) or {}
    return [collection_entity(gcp, ds, n, sample, indexes.get(n.rsplit("/", 1)[-1], [])) for n in names]


def entity(ds: DataSource, name: str, sample: int) -> dict | None:
    """Any collection path (a subcollection too)."""
    return introspect(ds, sample, only=name)[0]


def database_problem(info: dict) -> str | None:
    if info.get("type") == "DATASTORE_MODE":
        return "This database is in Datastore mode: Deployer works with Firestore (native mode) databases"
    return None


def describe(gcp, database: str) -> dict:
    return call(gcp, "GET", f"databases/{quote(database, safe='()')}")


def check(ds: DataSource) -> tuple[bool, str, str | None]:
    """`connections.try_source` for Firestore: the database answers and is in native mode."""
    try:
        info = describe(gcp_for(ds), database_of(ds))
    except ApiError as exc:
        return False, exc.message, None
    problem = database_problem(info)
    return (False, problem, None) if problem else (True, f"Connected ({info.get('locationId') or 'Firestore'})", None)


def list_databases(gcp) -> list[dict]:
    """The Firestore databases of the connection's project, with why Deployer can't use one (`problem`)."""
    out = gcp.firestore("GET", "databases") or {}
    return [
        {
            "id": str(d.get("name") or "").rsplit("/", 1)[-1],
            "location": d.get("locationId"),
            "type": d.get("type"),
            "problem": database_problem(d),
        }
        for d in out.get("databases") or []
    ]


def export_script(ds: DataSource) -> str:
    """The schema export's chunk: the collections and composite indexes as firestore.indexes.json."""
    gcp = gcp_for(ds)
    names = collection_ids(gcp, ds, [])
    indexes = composite_indexes(gcp, ds)
    spec = {
        "indexes": [
            {
                "collectionGroup": group,
                "queryScope": ix.get("queryScope", "COLLECTION"),
                "fields": [f for f in ix.get("fields") or [] if f.get("fieldPath") != "__name__"],
            }
            for group, found in sorted((indexes or {}).items())
            for ix in found
        ],
        "fieldOverrides": [],
    }
    state = ds.cloud_state or {}
    lines = [
        f"// Firestore source {ds.name} (project {state.get('project_id')}, database {database_of(ds)})",
        f"// Collections: {', '.join(names) or '(none yet)'}",
        "// Composite indexes as firestore.indexes.json (deploy with: firebase deploy --only firestore:indexes)"
        if indexes is not None
        else "// Composite indexes: the service account may not list them",
    ]
    lines += ["// " + line for line in json.dumps(spec, indent=2).splitlines()]
    return "\n".join(lines) + "\n"


# --- export ----------------------------------------------------------------------------------------------


def export_documents(ds: DataSource, collections: list[str] | None = None, limit: int = EXPORT_LIMIT) -> dict:
    """Every document of the top-level collections (or the given collection paths) as plain JSON, up to `limit`
    documents in all (`truncated` says when more were left). Subcollections are exported by their own path."""
    gcp = gcp_for(ds)
    root = root_of(ds)
    paths = [p.strip("/") for p in collections] if collections else collection_ids(gcp, ds, [])
    out: dict[str, list[dict]] = {}
    count, truncated = 0, False
    for path in paths:
        parts = check_path(path, "collection")
        docs = out.setdefault(path, [])
        start = None
        while not truncated:
            query: dict[str, Any] = {"from": [{"collectionId": parts[-1]}], "orderBy": _BY_ID, "limit": PAGE}
            if start:
                query["startAt"] = {"values": [{"referenceValue": start}], "before": False}
            page = _documents(gcp, ds, parts[:-1], query)
            for d in page:
                if count >= limit:
                    truncated = True
                    break
                docs.append(doc_out(d, root))
                count += 1
            if len(page) < PAGE:
                break
            start = page[-1]["name"]
        if truncated:
            break
    state = ds.cloud_state or {}
    return {
        "project_id": state.get("project_id"),
        "database": database_of(ds),
        "exported_at": iso(datetime.now(UTC).replace(tzinfo=None)),
        "documents": count,
        "truncated": truncated,
        "collections": out,
    }


# --- query console -----------------------------------------------------------------------------------------


def _op(op: Any) -> str:
    if op in OPS:
        return OPS[op]
    if isinstance(op, str) and (op.upper() in OPS.values() or op.upper() in UNARY):
        return op.upper()
    raise ApiError(400, "query_failed", f"Unknown op {op!r}: use one of {', '.join(OPS)} or {', '.join(UNARY)}")


def _filter(f: Any, root: str) -> dict:
    if isinstance(f, list):
        if not f:
            raise ApiError(400, "query_failed", '"where" is empty')
        return _and([_filter(x, root) for x in f])
    if isinstance(f, dict) and len(f) == 1 and next(iter(f)) in ("and", "or"):
        ((kind, items),) = f.items()
        if not isinstance(items, list) or not items:
            raise ApiError(400, "query_failed", f'"{kind}" takes a list of filters')
        return {"compositeFilter": {"op": kind.upper(), "filters": [_filter(x, root) for x in items]}}
    if not isinstance(f, dict) or "field" not in f or "op" not in f:
        raise ApiError(400, "query_failed", 'A filter is {"field": "status", "op": "==", "value": "open"}')
    op = _op(f["op"])
    field = {"fieldPath": field_path(f["field"])}
    if op in UNARY:
        return {"unaryFilter": {"op": op, "field": field}}
    if "value" not in f:
        raise ApiError(400, "query_failed", f'The filter on {f["field"]} needs a "value"')
    return {"fieldFilter": {"field": field, "op": op, "value": to_value(f["value"], root)}}


def _order(item: Any) -> dict:
    if isinstance(item, str):
        item = {"field": item}
    if not isinstance(item, dict) or "field" not in item:
        raise ApiError(400, "query_failed", 'orderBy takes field names or {"field": "total", "direction": "desc"}')
    direction = str(item.get("direction") or "asc").lower()
    if direction not in ("asc", "desc", "ascending", "descending"):
        raise ApiError(400, "query_failed", "direction is asc or desc")
    return {
        "field": {"fieldPath": field_path(item["field"])},
        "direction": "DESCENDING" if direction.startswith("desc") else "ASCENDING",
    }


def structured_query(request: dict, root: str) -> tuple[list[str], dict]:
    """(parent document path, structuredQuery) from the console's JSON request."""
    unknown = sorted(set(request) - set(QUERY_KEYS))
    if unknown:
        raise ApiError(400, "query_failed", f"Unknown field {unknown[0]!r}: a query takes {', '.join(QUERY_KEYS)}")
    frm = request.get("from")
    if isinstance(frm, str):
        parts = check_path(frm, "collection")
        parent, selector = parts[:-1], {"collectionId": parts[-1]}
    elif isinstance(frm, dict) and isinstance(frm.get("collectionId"), str) and "/" not in frm["collectionId"]:
        parent, selector = (
            [],
            {"collectionId": frm["collectionId"], "allDescendants": bool(frm.get("allDescendants", True))},
        )
    else:
        raise ApiError(
            400,
            "query_failed",
            '"from" is a collection path ("orders", "users/u1/orders") or {"collectionId": "orders", '
            '"allDescendants": true} for every collection named orders',
        )
    query: dict[str, Any] = {"from": [selector]}
    if "where" in request:
        query["where"] = _filter(request["where"], root)
    if "orderBy" in request:
        items = request["orderBy"] if isinstance(request["orderBy"], list) else [request["orderBy"]]
        query["orderBy"] = [_order(i) for i in items]
    if "select" in request:
        if not isinstance(request["select"], list) or not all(isinstance(s, str) for s in request["select"]):
            raise ApiError(400, "query_failed", "select is a list of field names")
        query["select"] = {"fields": [{"fieldPath": field_path(s)} for s in request["select"]]}
    if "offset" in request:
        try:
            query["offset"] = max(0, int(request["offset"]))
        except (TypeError, ValueError):
            raise ApiError(400, "query_failed", "offset must be a number") from None
    return parent, query


def run_console(ds: DataSource, query: str, *, max_rows: int, read_only: bool) -> dict:
    """docs/QUERY_CONSOLE.md "Firestore": one JSON request; the answer has the MongoDB console's shape."""
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
        request = dict(_json_object(query, "request"))
    except ApiError as exc:
        return out(error=exc.message + ' - write one JSON object, e.g. {"from": "orders", "limit": 20}')
    operation = request.pop("operation", "query")
    if operation not in READ_OPERATIONS + WRITE_OPERATIONS:
        return out(error=f'"operation" must be one of {", ".join(READ_OPERATIONS + WRITE_OPERATIONS)}')
    if read_only and operation not in READ_OPERATIONS:
        raise ApiError(403, "read_only_role", f"Viewers may only run {', '.join(READ_OPERATIONS)} ({operation} writes)")
    root = root_of(ds)
    try:
        if operation in ("query", "count"):
            limit = request.pop("limit", None)
            parent, structured = structured_query(request, root)
            gcp = gcp_for(ds)
            if operation == "count":
                n = _count(gcp, ds, parent, structured)
                return out(result={"count": n}, output=f"count: {n}")
            try:
                limit = max(1, min(int(limit or max_rows), max_rows))
            except (TypeError, ValueError):
                return out(error="limit must be a number")
            docs = _documents(gcp, ds, parent, {**structured, "limit": limit + 1})
            more = len(docs) > limit
            found = [doc_out(d, root, path=True) for d in docs[:limit]]
            lines = [f"query: {len(found)} document{'' if len(found) == 1 else 's'}"]
            if more:
                lines.append('More documents: add "offset" (or narrow "where") for the next ones.')
            return out(result={"documents": found}, docs=found, output="\n".join(lines), truncated=more)
        path = request.get("path")
        if operation == "get":
            parts = check_path(path, "document")
            doc = doc_out(call(gcp_for(ds), "GET", url(ds, parts)), root, path=True)
            return out(result={"document": doc}, docs=[doc], output="get: 1 document")
        if operation == "create":
            data = dict(_json_object(request.get("data") or {}, "data"))
            if request.get("id") is not None:
                data["_id"] = request["id"]
            doc = insert_document(ds, request.get("collection"), data)["document"]
            return out(result={"document": doc}, docs=[doc], output=f"created {request.get('collection')}/{doc['_id']}")
        parts = check_path(path, "document")
        collection, doc_id = "/".join(parts[:-1]), parts[-1]
        if operation == "update":
            doc = update_document(ds, collection, doc_id, request.get("data") or {}, request.get("unset"))["document"]
            return out(result={"document": doc}, docs=[doc], output=f"updated {path}")
        delete_document(ds, collection, doc_id)
        return out(result={"deleted": path}, output=f"deleted {path}")
    except ApiError as exc:
        return out(error=exc.message)


# --- connection details ---------------------------------------------------------------------------------


def display(ds: DataSource) -> dict:
    return {"host": "firestore.googleapis.com", "port": 443, "username": None, "tls": True}


def connection_info(ds: DataSource) -> dict:
    from app.services import connections

    connections.load_config(ds)
    state = ds.cloud_state or {}
    return {
        "uri": None,
        "host": "firestore.googleapis.com",
        "port": 443,
        "username": None,
        "password": None,
        "database": database_of(ds),
        "project_id": state.get("project_id"),
        "region": state.get("location"),
        "external_hint": (
            "Firestore has no password: use a Firebase Admin / Google Cloud SDK with the project id and database id. "
            "Firebase full apps (Cloud Run) with Database access get DEPLOYER_DB_<NAME>_PROJECT / _DATABASE and sign "
            "in as their service account, which needs the Cloud Datastore User role. Anywhere else, use a "
            "service-account key that may access it."
        ),
    }
