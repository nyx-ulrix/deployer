"""Firebase Realtime Database as a NoSQL engine (docs/CLOUD.md "C2-4 as built").

A Realtime Database source is an `external` source with engine `firebase_rtdb` on a Firebase cloud connection:
one database instance of the connection's Google project (`cloud_state.instance`, `.url`). Every call goes to
the database's own REST API (`<url>/<path>.json`) through `cloud_gcp.GcpClient.rtdb` with the connection's
service-account token (scopes firebase.database + userinfo.email) - the seam tests fake; the source keeps no
secret of its own (`config_encrypted` is `{}`). That token has admin access: security rules do not apply to it.

- The data is one JSON tree addressed by paths: `users/ann/name`; "" is the root. Keys are text without
  `. $ # [ ] /` (Firebase's rule). Reads may be `shallow` (each child's value cut to `true`, or kept when it is
  a plain value) - how the dashboard browses lazily - or filtered with Firebase's REST query parameters
  (`orderBy` + `startAt` / `endAt` / `equalTo` / `limitToFirst` / `limitToLast`); Firebase returns those
  unsorted, so `children` lists them in Firebase's order.
- Writes: `set` (PUT, replaces the value at a path), `update` (PATCH, sets the given children - keys may be
  deeper paths - and leaves the others), `push` (POST, a new child with a Firebase-made, time-ordered key),
  `delete`. Replacing or deleting the root is refused.
- Query console: one JSON request (docs/QUERY_CONSOLE.md "Realtime Database"); read-only roles may only `get`.
- Schema: the top-level keys as collections, fields inferred from their first 20 children. Export: the JSON at a
  path (default the whole database), up to `cloud_gcp.RTDB_MAX_BYTES`.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

from app.errors import ApiError, CloudError
from app.models import DataSource
from app.serializers import iso

ENGINE = "firebase_rtdb"
# Where Firebase offers Realtime Databases (the location cannot change later).
LOCATIONS = {"us-central1": "United States (Iowa)", "europe-west1": "Belgium", "asia-southeast1": "Singapore"}
QUERY_PARAMS = ("orderBy", "startAt", "endAt", "equalTo", "limitToFirst", "limitToLast")
CONSOLE_KEYS = ("operation", "path", "shallow", "value", *QUERY_PARAMS)
WRITE_OPERATIONS = ("set", "update", "push", "delete")
SPECIAL_KEYS = (".sv", ".priority", ".value")  # Firebase's own keys: server values and priorities
ORDER_SPECIAL = ("$key", "$value", "$priority")
MAX_DEPTH = 32  # Firebase's nesting limit
ENTITY_LIMIT = 50  # top-level keys the schema describes
SCHEMA_SAMPLE = 20  # children read per top-level key (whole subtrees, so far fewer than for documents)
_BAD_KEY = re.compile(r"[.$#\[\]/\x00-\x1f\x7f]")
NO_COLLECTION_CHANGES = (
    "A Realtime Database is one JSON tree, not collections: read and write any path with the Data tab's tree, "
    "the rtdb endpoints (GET/PUT/PATCH/POST/DELETE .../data-sources/<id>/rtdb?path=...) or the MCP tools "
    "rtdb_read / rtdb_write."
)


def url_of(ds: DataSource) -> str:
    return str((ds.cloud_state or {}).get("url") or "")


def _gcp(ds: DataSource):
    from app.services.firestore import gcp_for  # the source's Firebase connection, its own session

    return gcp_for(ds)


def _error(exc: CloudError) -> ApiError:
    if exc.code == "TOO_LARGE":
        return ApiError(413, "too_large", exc.message)
    if exc.status in (401, 403):
        return ApiError(
            502,
            "cloud_error",
            exc.message + " - the Firebase service account needs the Firebase Realtime Database Admin role "
            "(Settings -> Cloud accounts shows how).",
        )
    if exc.status == 400:
        hint = (
            ' - add the index in the Firebase console -> Realtime Database -> Rules, e.g. "users": {".indexOn": '
            '["age"]}, or order by "$key"'
            if "indexOn" in exc.message
            else ""
        )
        return ApiError(400, "query_failed", exc.message + hint)
    if exc.status in (404, 423):
        return ApiError(
            404,
            "not_found",
            exc.message + " - the database may have been deleted or disabled in the Firebase console",
        )
    return ApiError(502, "cloud_error", exc.message)


def call(ds: DataSource, method: str, parts: list[str], body: Any = None, params: Any = None, gcp=None) -> Any:
    path = "".join("/" + quote(p, safe="") for p in parts)
    try:
        return (gcp or _gcp(ds)).rtdb(method, url_of(ds), path, body, params)
    except CloudError as exc:
        raise _error(exc) from None


# --- paths and values --------------------------------------------------------------------------------------


def check_key(key: Any) -> str:
    if not isinstance(key, str) or not key or _BAD_KEY.search(key) or len(key.encode()) > 768:
        raise ApiError(
            400, "invalid_path", f"Not a Realtime Database key (text without . $ # [ ] /): {str(key)[:100]!r}"
        )
    return key


def check_path(path: Any) -> list[str]:
    """`users/ann` -> ["users", "ann"]; "" or "/" is the root (no parts)."""
    if path is None:
        path = ""
    if not isinstance(path, str):
        raise ApiError(400, "invalid_path", "A path is text, e.g. users/ann")
    clean = path.strip().strip("/")
    parts = clean.split("/") if clean else []
    if len(parts) > MAX_DEPTH:
        raise ApiError(400, "invalid_path", f"A path has at most {MAX_DEPTH} keys")
    for p in parts:
        check_key(p)
    return parts


def check_value(value: Any, depth: int = 0) -> None:
    """JSON Firebase stores: keys without . $ # [ ] / (but .sv / .priority / .value), finite numbers, <= 32 deep."""
    if depth > MAX_DEPTH:
        raise ApiError(400, "invalid_value", f"Data is nested more than {MAX_DEPTH} levels deep")
    if isinstance(value, float) and not math.isfinite(value):
        raise ApiError(400, "invalid_value", "Numbers cannot be NaN or infinite")
    if isinstance(value, list):
        for v in value:
            check_value(v, depth + 1)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in SPECIAL_KEYS:
                try:
                    check_key(k)
                except ApiError:
                    raise ApiError(400, "invalid_value", f"Invalid key {str(k)[:100]!r}: no . $ # [ ] /") from None
            check_value(v, depth + 1)
    elif not (value is None or isinstance(value, str | int | float | bool)):
        raise ApiError(400, "invalid_value", f"Unsupported value: {value!r}"[:200])


# --- queries -------------------------------------------------------------------------------------------------


def query_params(q: dict) -> dict:
    """Firebase REST query parameters from `{shallow, orderBy, startAt, endAt, equalTo, limitToFirst,
    limitToLast}` (plain JSON values; this JSON-encodes them as the REST API wants)."""
    given = [k for k in QUERY_PARAMS if q.get(k) is not None]
    if q.get("shallow"):
        if given:
            raise ApiError(400, "query_failed", "shallow cannot be combined with orderBy, startAt, ... (Firebase rule)")
        return {"shallow": "true"}
    order = q.get("orderBy")
    if order is None:
        if given:
            raise ApiError(
                400,
                "query_failed",
                'startAt, endAt, equalTo and the limits need "orderBy": "$key", "$value", "$priority" or a child '
                'path such as "age" or "address/city"',
            )
        return {}
    if order not in ORDER_SPECIAL:
        if not check_path(order):
            raise ApiError(400, "query_failed", "orderBy is $key, $value, $priority or a child path")
    out = {"orderBy": json.dumps(order)}
    for k in ("startAt", "endAt", "equalTo"):
        v = q.get(k)
        if v is not None:
            if not isinstance(v, str | int | float | bool):
                raise ApiError(400, "query_failed", f"{k} is a text, number or true/false")
            out[k] = json.dumps(v)
    for k in ("limitToFirst", "limitToLast"):
        if q.get(k) is not None:
            try:
                n = int(q[k])
            except (TypeError, ValueError):
                n = 0
            if n < 1:
                raise ApiError(400, "query_failed", f"{k} is a whole number, 1 or more")
            out[k] = str(n)
    if "limitToFirst" in out and "limitToLast" in out:
        raise ApiError(400, "query_failed", "Use limitToFirst or limitToLast, not both")
    return out


def _rank(v: Any) -> tuple:
    """Firebase's order of values: null, false, true, numbers, text, then objects."""
    if v is None:
        return (0, 0)
    if isinstance(v, bool):
        return (1 + v, 0)
    if isinstance(v, int | float):
        return (3, v)
    if isinstance(v, str):
        return (4, v)
    return (5, 0)


def _key_rank(k: str) -> tuple:
    """Keys that are 32-bit whole numbers first, by value; then the others as text."""
    if re.fullmatch(r"-?(0|[1-9]\d{0,9})", k) and -(2**31) <= int(k) < 2**31:
        return (0, int(k), "")
    return (1, 0, k)


def _child(value: Any, path: list[str]) -> Any:
    for p in path:
        value = value.get(p) if isinstance(value, dict) else None
    return value


def ordered(value: Any, order_by: str | None) -> list[tuple[str, Any]] | None:
    """The children of an object (or array) in Firebase's order for `order_by` (default: by key); None for
    a plain value."""
    if isinstance(value, list):  # Firebase answers keys 0, 1, 2... as an array
        value = {str(i): v for i, v in enumerate(value) if v is not None}
    if not isinstance(value, dict):
        return None
    items = list(value.items())
    if order_by == "$value":
        return sorted(items, key=lambda kv: (_rank(kv[1]), _key_rank(kv[0])))
    if order_by in (None, "$key", "$priority"):  # priorities are not returned: key order
        return sorted(items, key=lambda kv: _key_rank(kv[0]))
    path = order_by.split("/")
    return sorted(items, key=lambda kv: (_rank(_child(kv[1], path)), _key_rank(kv[0])))


# --- data API ------------------------------------------------------------------------------------------------


def read(ds: DataSource, path: Any, query: dict | None = None) -> dict:
    """`{path, value}`, plus `children: [{key, value}]` in Firebase's order for shallow or ordered reads."""
    q = query or {}
    parts = check_path(path)
    params = query_params(q)
    value = call(ds, "GET", parts, params=params or None)
    out: dict[str, Any] = {"path": "/".join(parts), "value": value}
    children = ordered(value, q.get("orderBy"))
    if params and children is not None:  # a plain value has no children (the tree shows it as a leaf)
        out["children"] = [{"key": k, "value": v} for k, v in children]
    return out


def write(ds: DataSource, operation: str, path: Any, value: Any = None) -> dict:
    """set (replace), update (set the given children), push (new child, Firebase-made key) or delete."""
    parts = check_path(path)
    where = "/".join(parts)
    if operation not in WRITE_OPERATIONS:
        raise ApiError(400, "query_failed", f'"operation" must be get, {", ".join(WRITE_OPERATIONS)}')
    if not parts and operation in ("set", "delete"):
        raise ApiError(
            400,
            "root_write",
            "Replacing or deleting the whole database is refused here: pick a path (or delete the top-level keys "
            "one by one)",
        )
    if operation == "delete":
        call(ds, "DELETE", parts)
        return {"path": where, "deleted": True}
    if value is None:
        raise ApiError(400, "invalid_value", 'A "value" is required (to remove data, use delete)')
    if operation == "update":
        if not isinstance(value, dict) or not value:
            raise ApiError(400, "invalid_value", 'update takes an object: {"name": "Ann", "address/city": "Oslo"}')
        for k, v in value.items():
            if not check_path(k):
                raise ApiError(400, "invalid_value", "update keys are child paths, e.g. name or address/city")
            check_value(v)
        return {"path": where, "value": call(ds, "PATCH", parts, value)}
    check_value(value)
    if operation == "push":
        key = str((call(ds, "POST", parts, value) or {}).get("name") or "")
        return {"path": where, "key": key}
    return {"path": where, "value": call(ds, "PUT", parts, value)}


def export(ds: DataSource, path: Any = "") -> dict:
    """The JSON at `path` (default the whole database), with priorities (format=export), as one object."""
    parts = check_path(path)
    state = ds.cloud_state or {}
    data = call(ds, "GET", parts, params={"format": "export"})
    return {
        "project_id": state.get("project_id"),
        "instance": state.get("instance"),
        "url": url_of(ds),
        "path": "/".join(parts),
        "exported_at": iso(datetime.now(UTC).replace(tzinfo=None)),
        "data": data,
    }


def run_op(ds: DataSource, op: str, args: dict) -> Any:
    """source_ops' documents / collections operations: a JSON tree has neither (use read / write)."""
    raise ApiError(400, "not_supported", NO_COLLECTION_CHANGES)


# --- schema ----------------------------------------------------------------------------------------------------


def _top_keys(ds: DataSource, gcp) -> list[str]:
    root = call(ds, "GET", [], params={"shallow": "true"}, gcp=gcp)
    return [k for k, _ in ordered(root, "$key") or []]


def _entity(ds: DataSource, gcp, name: str, sample: int) -> dict:
    from app.services.introspection import analyze_documents

    docs = []
    if sample > 0:
        try:
            value = call(
                ds, "GET", check_path(name), params={"orderBy": '"$key"', "limitToFirst": str(sample)}, gcp=gcp
            )
        except ApiError as exc:
            if exc.code != "too_large":
                raise
            value = None
        for k, v in ordered(value, "$key") or []:
            docs.append({"_id": k, **v} if isinstance(v, dict) else {"_id": k, "_value": v})
    fields = analyze_documents(docs) or analyze_documents([{"_id": ""}])
    for f in fields:
        if f["name"] == "_id":  # each child's key
            f["name"], f["data_type"], f["nullable"], f["occurrence"] = "_key", "string", False, 1.0
    return {
        "name": name,
        "type": "collection",
        "row_count": None,
        "fields": fields,
        "indexes": [{"name": "key", "fields": ["_key"], "unique": True}],
        "validator": None,
    }


def introspect(ds: DataSource, sample: int, only: str | None = None) -> list[dict]:
    """The top-level keys as collections; fields inferred from their first children (up to SCHEMA_SAMPLE)."""
    from app.services.introspection import MAX_SAMPLE

    gcp = _gcp(ds)
    sample = max(0, min(int(sample), MAX_SAMPLE, SCHEMA_SAMPLE))
    names = [only] if only else _top_keys(ds, gcp)[:ENTITY_LIMIT]
    return [_entity(ds, gcp, n, sample) for n in names]


def entity(ds: DataSource, name: str, sample: int) -> dict | None:
    return introspect(ds, sample, only=name)[0]


def check(ds: DataSource) -> tuple[bool, str, str | None]:
    """`connections.try_source`: the database answers a shallow read of its root."""
    try:
        call(ds, "GET", [], params={"shallow": "true"})
    except ApiError as exc:
        if exc.code != "too_large":
            return False, exc.message, None
    return True, f"Connected ({(ds.cloud_state or {}).get('location') or 'Realtime Database'})", None


def instances(gcp) -> list[dict]:
    """The project's Realtime Database instances, with why Deployer can't use one (`problem`)."""
    out = []
    for i in gcp.rtdb_instances() or []:
        name = str(i.get("name") or "")
        state = i.get("state") or "ACTIVE"
        out.append(
            {
                "id": name.rsplit("/", 1)[-1],
                "url": i.get("databaseUrl"),
                "location": name.split("/locations/")[-1].split("/")[0] if "/locations/" in name else None,
                "type": i.get("type"),
                "state": state,
                "problem": None if state == "ACTIVE" else f"This database is {state.lower()} in the Firebase console",
            }
        )
    return out


def export_script(ds: DataSource) -> str:
    """The schema export's chunk: where the database is and its top-level keys (rules live in Firebase)."""
    state = ds.cloud_state or {}
    keys = _top_keys(ds, _gcp(ds))
    return (
        f"// Realtime Database source {ds.name} (project {state.get('project_id')}, database {state.get('instance')})\n"
        f"// URL: {url_of(ds)}\n"
        f"// Top-level keys: {', '.join(keys[:ENTITY_LIMIT]) or '(none yet)'}\n"
        "// Security rules and indexes (.indexOn) are in the Firebase console -> Realtime Database -> Rules\n"
        "// (database.rules.json, deployable with: firebase deploy --only database).\n"
    )


# --- query console ---------------------------------------------------------------------------------------------


def _as_doc(key: str, value: Any) -> dict:
    return {"_key": key, **value} if isinstance(value, dict) else {"_key": key, "_value": value}


def run_console(ds: DataSource, query: str, *, max_rows: int, read_only: bool) -> dict:
    """docs/QUERY_CONSOLE.md "Realtime Database": one JSON request; the answer has the MongoDB console's shape."""
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
        request = json.loads(query) if isinstance(query, str) else query
    except ValueError as exc:
        request = None
        problem = f"Invalid request: {exc}"
    else:
        problem = "The request must be a JSON object"
    if not isinstance(request, dict):
        return out(
            error=problem + ' - write one JSON object, e.g. {"path": "users", "orderBy": "$key", "limitToFirst": 20}'
        )
    unknown = sorted(set(request) - set(CONSOLE_KEYS))
    if unknown:
        return out(error=f"Unknown field {unknown[0]!r}: a request takes {', '.join(CONSOLE_KEYS)}")
    operation = request.get("operation", "get")
    if operation not in ("get", *WRITE_OPERATIONS):
        return out(error=f'"operation" must be one of get, {", ".join(WRITE_OPERATIONS)}')
    if read_only and operation != "get":
        raise ApiError(403, "read_only_role", f"Viewers may only run get ({operation} writes)")
    try:
        if operation != "get":
            if any(request.get(k) is not None for k in (*QUERY_PARAMS, "shallow")):
                return out(error="Query parameters only go with get")
            result = write(ds, operation, request.get("path"), request.get("value"))
            verb = {"set": "set", "update": "updated", "push": "pushed", "delete": "deleted"}[operation]
            where = "/" + result["path"]
            line = f"{verb} {where}" + (f" (new key {result['key']})" if operation == "push" else "")
            return out(result=result, output=line)
        q = {k: request.get(k) for k in (*QUERY_PARAMS, "shallow")}
        if q["orderBy"] is not None and q["limitToFirst"] is None and q["limitToLast"] is None:
            q["limitToFirst"] = max_rows + 1  # only what the console shows (plus one, to see there is more)
        got = read(ds, request.get("path"), q)
        children = ordered(got["value"], q["orderBy"])
        where = "/" + got["path"]
        if children is None:
            shown = json.dumps(got["value"])
            return out(
                result=got,
                output=f"get {where}: {shown[:200]}"
                if got["value"] is not None
                else f"get {where}: null (nothing here)",
            )
        docs = [_as_doc(k, v) for k, v in children[:max_rows]]
        more = len(children) > max_rows
        lines = [f"get {where}: {len(docs)} child{'' if len(docs) == 1 else 'ren'}"]
        if more:
            lines.append('More children: narrow it with "orderBy" + "startAt" / "limitToFirst", or a deeper "path".')
        return out(
            result={"path": got["path"], "children": len(children)}, docs=docs, output="\n".join(lines), truncated=more
        )
    except ApiError as exc:
        return out(error=exc.message)


# --- connection details ----------------------------------------------------------------------------------------


def display(ds: DataSource) -> dict:
    return {"host": urlparse(url_of(ds)).hostname, "port": 443, "username": None, "tls": True}


def connection_info(ds: DataSource) -> dict:
    from app.services import connections

    connections.load_config(ds)
    state = ds.cloud_state or {}
    return {
        "uri": url_of(ds),
        "host": urlparse(url_of(ds)).hostname,
        "port": 443,
        "username": None,
        "password": None,
        "database": state.get("instance"),
        "project_id": state.get("project_id"),
        "region": state.get("location"),
        "external_hint": (
            "The Realtime Database has no password: apps use the Firebase SDK with this URL. Websites sign users in "
            "with Firebase Authentication and the database's security rules decide what they may read and write "
            "(Firebase console -> Realtime Database -> Rules). Servers use the Firebase Admin SDK: Firebase full "
            "apps (Cloud Run) with Database access get DEPLOYER_DB_<NAME>_URL / _PROJECT and sign in as their "
            "service account, which needs the Firebase Realtime Database Admin role."
        ),
    }
