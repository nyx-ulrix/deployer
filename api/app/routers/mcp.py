"""MCP server for AI agents (docs/MCP.md): Streamable HTTP transport, JSON responses only (no SSE).

Implemented directly instead of with the `mcp` SDK: the SDK's HTTP transport is its own ASGI app with a
session manager that needs its own lifespan, while all we need is JSON-RPC over one POST route that
reuses the project API key auth and calls the existing route functions (same checks, audit and query
log as the REST API).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app import __version__
from app.deps import DbSession, ProjectAccess, require_role
from app.errors import ApiError
from app.routers import apps as apps_router
from app.routers import query as query_router
from app.routers import schema as schema_router
from app.services import audit, cloud, deployments, introspection, rate_limit, source_ops
from app.services.sources import get_source, project_sources

log = logging.getLogger(__name__)
router = APIRouter(tags=["mcp"])

Access = Annotated[ProjectAccess, Depends(require_role("viewer", api_keys=True))]

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first
MAX_BODY = 1024 * 1024
MAX_ROWS = 200
MAX_TEXT = 256 * 1024
LOG_TAIL_LINES = 100
CALL_LIMIT, CALL_WINDOW_S = 60, 60  # tool calls per key (or user) per minute

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603

INSTRUCTIONS = (
    "Tools for one Deployer project: its databases (SQL tables, MongoDB collections) and its apps "
    "(push-to-deploy websites). Start with list_data_sources and get_schema, or list_apps. "
    "Ids come from those tools. Results are compact JSON, capped at 200 rows / 256 KB."
)


# --- tools ---------------------------------------------------------------------------------------


def _schema(required: list[str] | None = None, **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


def _p(type_: str, description: str, **extra: Any) -> dict:
    return {"type": type_, "description": description, **extra}


SOURCE = _p("string", "Data source id (from list_data_sources)")
TABLE = _p("string", "SQL table name")
COLLECTION = _p("string", "MongoDB collection name")
DOC_ID = _p("string", "String form of the document's _id: ObjectId hex, an integer, or the raw string")
APP = _p("string", "App id (from list_apps)")
LIMIT = _p("integer", f"Max rows to return (1-{MAX_ROWS}, default 50)", minimum=1, maximum=MAX_ROWS)


def _limit(args: dict, default: int = 50) -> int:
    return max(1, min(int(args.get("limit", default)), MAX_ROWS))


def _sql(ctx: Ctx, args: dict):
    ds = get_source(ctx.db, ctx.access.project.id, args["source_id"], kind="sql")
    ctx.db.commit()  # don't hold the platform DB transaction open during project queries
    return ds


def _mongo(ctx: Ctx, args: dict):
    ds = get_source(ctx.db, ctx.access.project.id, args["source_id"], kind="nosql")
    ctx.db.commit()
    return ds


def t_list_data_sources(ctx: Ctx, args: dict) -> Any:
    return [
        {"id": ds.id, "name": ds.name, "kind": ds.kind, "engine": ds.engine, "status": ds.status}
        for ds in project_sources(ctx.db, ctx.access.project.id)
    ]


def t_get_schema(ctx: Ctx, args: dict) -> Any:
    return schema_router.get_schema(
        ctx.access, ctx.db, source_id=args.get("source_id"), sample=introspection.DEFAULT_SAMPLE
    )


def t_run_query(ctx: Ctx, args: dict) -> Any:
    body = query_router.QueryRequest(query=args["query"], max_rows=min(int(args.get("max_rows", MAX_ROWS)), MAX_ROWS))
    return query_router.run_query(args["source_id"], body, ctx.access, ctx.db, ctx.request)


def t_list_rows(ctx: Ctx, args: dict) -> Any:
    sort = args.get("sort") or ""
    return source_ops.list_rows(
        _sql(ctx, args),
        args["table"],
        limit=_limit(args),
        offset=max(0, int(args.get("offset", 0))),
        order_by=sort.lstrip("-") or None,
        order="desc" if sort.startswith("-") else "asc",
        **({"filters": args["filters"]} if args.get("filters") else {}),
    )


def t_insert_row(ctx: Ctx, args: dict) -> Any:
    return source_ops.insert_row(_sql(ctx, args), args["table"], args["values"])


def t_update_row(ctx: Ctx, args: dict) -> Any:
    return source_ops.update_row(_sql(ctx, args), args["table"], args["pk"], args["values"])


def t_delete_row(ctx: Ctx, args: dict) -> Any:
    return source_ops.delete_row(_sql(ctx, args), args["table"], args["pk"])


def t_list_documents(ctx: Ctx, args: dict) -> Any:
    flt = args.get("filter")
    return source_ops.list_documents(
        _mongo(ctx, args),
        args["collection"],
        filter_json=json.dumps(flt) if flt else None,
        limit=_limit(args),
        skip=max(0, int(args.get("skip", 0))),
    )


def t_insert_document(ctx: Ctx, args: dict) -> Any:
    return source_ops.insert_document(_mongo(ctx, args), args["collection"], args["document"])


def t_update_document(ctx: Ctx, args: dict) -> Any:
    return source_ops.update_document(
        _mongo(ctx, args), args["collection"], args["document_id"], args.get("set") or {}, args.get("unset")
    )


def t_delete_document(ctx: Ctx, args: dict) -> Any:
    return source_ops.delete_document(_mongo(ctx, args), args["collection"], args["document_id"])


def t_list_apps(ctx: Ctx, args: dict) -> Any:
    return apps_router.list_apps(ctx.access, ctx.db)


def t_get_app(ctx: Ctx, args: dict) -> Any:
    return apps_router.get_app(args["app_id"], ctx.access, ctx.db)


def _where(ctx: Ctx, app_id: str) -> dict:
    """docs/CLOUD.md: the app's target and the URL it serves on there."""
    app = deployments.get_app(ctx.db, ctx.access.project.id, app_id)
    cloud_info = deployments.cloud_out(ctx.db, app)
    return {"target": app.target, "cloud_url": cloud_info["url"] if cloud_info else None}


def t_deploy_app(ctx: Ctx, args: dict) -> Any:
    return {**apps_router.deploy(args["app_id"], ctx.request, ctx.access, ctx.db, None), **_where(ctx, args["app_id"])}


def t_deployment_status(ctx: Ctx, args: dict) -> Any:
    out = apps_router.get_deployment(args["app_id"], args["deployment_id"], ctx.access, ctx.db, log=1)
    out["log_tail"] = "\n".join((out.pop("log") or "").splitlines()[-LOG_TAIL_LINES:])
    return {**out, **_where(ctx, args["app_id"])}


def t_list_cloud_connections(ctx: Ctx, args: dict) -> Any:
    return [cloud.connection_out(c) for c in cloud.list_connections(ctx.db, ctx.access.project.id)]


def t_list_cloud_targets(ctx: Ctx, args: dict) -> Any:
    return {"targets": cloud.targets_out(ctx.db, ctx.access.project.id), "note": cloud.CLOUD_ENV_NOTE}


def t_app_logs(ctx: Ctx, args: dict) -> Any:
    tail = max(1, min(int(args.get("tail", 100)), 500))
    return apps_router.runtime_logs(args["app_id"], ctx.access, ctx.db, tail=tail, device_id=None)


# name: (minimum project role, description, input schema, handler)
TOOLS: dict[str, tuple[str, str, dict, Any]] = {
    "list_data_sources": (
        "viewer",
        "List the project's databases (data sources): id, name, kind (sql or nosql), engine, status.",
        _schema(),
        t_list_data_sources,
    ),
    "get_schema": (
        "viewer",
        "Tables/collections with their columns/fields, keys, indexes and relationships. "
        "Pass source_id for one data source, or omit it for all.",
        _schema(source_id=SOURCE),
        t_get_schema,
    ),
    "run_query": (
        "viewer",
        "Run SQL (a script, several statements allowed) or MongoDB shell code (`db` is the database) "
        f"against a data source. Returns up to {MAX_ROWS} rows per statement. Read-only keys may only read.",
        _schema(
            ["source_id", "query"],
            source_id=SOURCE,
            query=_p("string", "SQL, or mongosh code such as db.orders.find({status: 'open'})"),
            max_rows=_p("integer", f"Max rows per statement (1-{MAX_ROWS})", minimum=1, maximum=MAX_ROWS),
        ),
        t_run_query,
    ),
    "list_rows": (
        "viewer",
        "Read rows of a SQL table, with the total count. Page with limit/offset.",
        _schema(
            ["source_id", "table"],
            source_id=SOURCE,
            table=TABLE,
            limit=LIMIT,
            offset=_p("integer", "Rows to skip (default 0)", minimum=0),
            filters=_p("object", 'Equality filters ANDed together, e.g. {"status": "open"}; null matches NULL'),
            sort=_p("string", 'Column to sort by; prefix with "-" for descending. Default: primary key'),
        ),
        t_list_rows,
    ),
    "insert_row": (
        "developer",
        "Insert a row into a SQL table; returns the stored row with defaults filled in.",
        _schema(
            ["source_id", "table", "values"],
            source_id=SOURCE,
            table=TABLE,
            values=_p("object", "Column values"),
        ),
        t_insert_row,
    ),
    "update_row": (
        "developer",
        "Update one row of a SQL table, found by its primary key.",
        _schema(
            ["source_id", "table", "pk", "values"],
            source_id=SOURCE,
            table=TABLE,
            pk=_p("object", 'Exactly the primary key columns, e.g. {"id": 1}'),
            values=_p("object", "Columns to change"),
        ),
        t_update_row,
    ),
    "delete_row": (
        "developer",
        "Delete one row of a SQL table, found by its primary key.",
        _schema(
            ["source_id", "table", "pk"],
            source_id=SOURCE,
            table=TABLE,
            pk=_p("object", 'Exactly the primary key columns, e.g. {"id": 1}'),
        ),
        t_delete_row,
    ),
    "list_documents": (
        "viewer",
        "Read documents of a MongoDB collection (relaxed Extended JSON), with the total count.",
        _schema(
            ["source_id", "collection"],
            source_id=SOURCE,
            collection=COLLECTION,
            filter=_p("object", 'MongoDB query filter, e.g. {"status": "open"} ($where is refused)'),
            limit=LIMIT,
            skip=_p("integer", "Documents to skip (default 0)", minimum=0),
        ),
        t_list_documents,
    ),
    "insert_document": (
        "developer",
        "Insert a document into a MongoDB collection; returns it with its _id.",
        _schema(
            ["source_id", "collection", "document"],
            source_id=SOURCE,
            collection=COLLECTION,
            document=_p("object", "The document"),
        ),
        t_insert_document,
    ),
    "update_document": (
        "developer",
        "Set and/or unset fields of one MongoDB document; _id cannot change.",
        _schema(
            ["source_id", "collection", "document_id"],
            source_id=SOURCE,
            collection=COLLECTION,
            document_id=DOC_ID,
            set=_p("object", "Fields to set"),
            unset=_p("array", "Field names to remove", items={"type": "string"}),
        ),
        t_update_document,
    ),
    "delete_document": (
        "developer",
        "Delete one MongoDB document.",
        _schema(
            ["source_id", "collection", "document_id"], source_id=SOURCE, collection=COLLECTION, document_id=DOC_ID
        ),
        t_delete_document,
    ),
    "list_apps": (
        "developer",
        "List the project's apps (websites deployed from Git): id, name, repo, target (local or a cloud "
        "target), URLs, live deployment.",
        _schema(),
        t_list_apps,
    ),
    "get_app": (
        "developer",
        "One app's settings, target (where it runs: this PC or AWS / Firebase), cloud URL and resources, "
        "URLs, hostnames and live deployment.",
        _schema(["app_id"], app_id=APP),
        t_get_app,
    ),
    "deploy_app": (
        "developer",
        "Start a new deployment of an app from its branch, on the app's target (this PC, or its AWS / "
        "Firebase account: cloud targets keep serving when the PC is off). Poll deployment_status with the "
        "returned id.",
        _schema(["app_id"], app_id=APP),
        t_deploy_app,
    ),
    "deployment_status": (
        "developer",
        f"A deployment's status (queued, building, deploying, live, failed, cancelled, superseded), "
        f"error, target and target_url (the cloud URL it went live on) and the last {LOG_TAIL_LINES} log lines.",
        _schema(["app_id", "deployment_id"], app_id=APP, deployment_id=_p("string", "Deployment id")),
        t_deployment_status,
    ),
    "list_cloud_connections": (
        "developer",
        "The AWS / Firebase accounts this project's apps may deploy to: id, provider, name, account id / "
        "project id, region, status. Never any credentials. Choosing one for an app is done by a project "
        "admin in the dashboard (it is billed to that account).",
        _schema(),
        t_list_cloud_connections,
    ),
    "list_cloud_targets": (
        "developer",
        "Where an app can run: local (this PC) and the cloud targets aws_static, aws_app, firebase_hosting, "
        "firebase_app, with what each is for, cost drivers, and whether this project has a connection for it.",
        _schema(),
        t_list_cloud_targets,
    ),
    "app_logs": (
        "developer",
        "Recent runtime log lines of an app's live container.",
        _schema(
            ["app_id"], app_id=APP, tail=_p("integer", "Lines to return (1-500, default 100)", minimum=1, maximum=500)
        ),
        t_app_logs,
    ),
}


class Ctx:
    def __init__(self, access: ProjectAccess, db, request: Request):
        self.access, self.db, self.request = access, db, request


# --- JSON-RPC ------------------------------------------------------------------------------------


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


_TYPES = {"string": str, "integer": int, "object": dict, "array": list}


def _check_args(schema: dict, args: Any) -> dict:
    if not isinstance(args, dict):
        raise RpcError(INVALID_PARAMS, "arguments must be an object")
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        raise RpcError(INVALID_PARAMS, f"Missing argument(s): {', '.join(missing)}")
    for key, value in args.items():
        prop = schema["properties"].get(key)
        if prop is None:
            raise RpcError(INVALID_PARAMS, f"Unknown argument: {key}")
        expected = _TYPES[prop["type"]]
        if value is not None and (not isinstance(value, expected) or isinstance(value, bool)):
            raise RpcError(INVALID_PARAMS, f"Argument {key} must be of type {prop['type']}")
    return {k: v for k, v in args.items() if v is not None}


def _visible(access: ProjectAccess) -> list[str]:
    return [name for name, (role, *_) in TOOLS.items() if access.at_least(role)]


def _text_result(value: Any, *, is_error: bool = False) -> dict:
    text = json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)
    raw = text.encode("utf-8")
    if len(raw) > MAX_TEXT:
        text = raw[:MAX_TEXT].decode("utf-8", errors="ignore") + (
            f"\n[truncated: the result is over {MAX_TEXT // 1024} KB; narrow it with limit, filters or a smaller query]"
        )
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _error_result(exc: ApiError) -> dict:
    return _text_result({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}, is_error=True)


def _call_tool(ctx: Ctx, params: dict) -> dict:
    name = params.get("name")
    access = ctx.access
    ok, code = False, None
    try:
        allowed, retry_after = rate_limit.hit(
            f"rl:mcp:{access.api_key_id or 'user:' + access.user.id}", CALL_LIMIT, CALL_WINDOW_S
        )
        if not allowed:
            raise ApiError(
                429,
                "rate_limited",
                f"Too many tool calls (limit {CALL_LIMIT} per minute); try again later",
                {"retry_after": retry_after},
            )
        # Tools the caller's role can't use are not listed and are unknown here.
        if not isinstance(name, str) or name not in _visible(access):
            raise RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        _, _, schema, handler = TOOLS[name]
        args = _check_args(schema, params.get("arguments") or {})
        try:
            result = _text_result(handler(ctx, args))
        except ValidationError as exc:
            raise ApiError(
                422, "validation_error", "Invalid arguments", {"errors": exc.errors(include_url=False)}
            ) from exc
        ok = True
        return result
    except RpcError:
        code = "invalid_params"
        raise
    except ApiError as exc:
        ctx.db.rollback()
        code = exc.code
        return _error_result(exc)
    except Exception:
        ctx.db.rollback()
        code = "internal_error"
        raise
    finally:
        # Tool name and outcome only: arguments can hold queries, row values or secrets.
        audit.record(
            ctx.db,
            "mcp.call",
            request=ctx.request,
            user_id=access.user.id,
            project_id=access.project.id,
            api_key_id=access.api_key_id,
            tool=str(name)[:100] if name is not None else None,
            ok=ok,
            error=code,
        )
        ctx.db.commit()


def _dispatch(ctx: Ctx, method: str, params: dict) -> Any:
    if method == "initialize":
        requested = params.get("protocolVersion")
        return {
            "protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "deployer", "title": "Deployer", "version": __version__},
            "instructions": f"Project '{ctx.access.project.name}'. {INSTRUCTIONS}",
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {
            "tools": [
                {"name": name, "description": TOOLS[name][1], "inputSchema": TOOLS[name][2]}
                for name in _visible(ctx.access)
            ]
        }
    if method == "tools/call":
        return _call_tool(ctx, params)
    raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")


def _rpc_error(msg_id: Any, code: int, message: str, status: int = 200) -> JSONResponse:
    body = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    return JSONResponse(body, status_code=status)


def handle(raw: bytes, request: Request, access: ProjectAccess, db) -> Response:
    if len(raw) > MAX_BODY:
        return _rpc_error(None, INVALID_REQUEST, "Request body is too large (1 MB max)", 413)
    try:
        msg = json.loads(raw)
    except ValueError:
        return _rpc_error(None, PARSE_ERROR, "Parse error: the body is not JSON", 400)
    if isinstance(msg, list):
        return _rpc_error(None, INVALID_REQUEST, "Batch requests are not supported", 400)
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _rpc_error(None, INVALID_REQUEST, "Invalid request: expected a JSON-RPC 2.0 object", 400)
    method, msg_id = msg.get("method"), msg.get("id")
    if method is None and ("result" in msg or "error" in msg):
        return Response(status_code=202)  # a response to a server request; we never send any
    if not isinstance(method, str) or not (msg_id is None or isinstance(msg_id, str | int)):
        return _rpc_error(msg_id if isinstance(msg_id, str | int) else None, INVALID_REQUEST, "Invalid request", 400)
    if "id" not in msg:
        return Response(status_code=202)  # notification (e.g. notifications/initialized): nothing to answer
    version = request.headers.get("MCP-Protocol-Version")
    if method != "initialize" and version and version not in PROTOCOL_VERSIONS:
        return _rpc_error(msg_id, INVALID_REQUEST, f"Unsupported MCP-Protocol-Version: {version}", 400)
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        return _rpc_error(msg_id, INVALID_PARAMS, "params must be an object")
    try:
        result = _dispatch(Ctx(access, db, request), method, params)
    except RpcError as exc:
        return _rpc_error(msg_id, exc.code, exc.message)
    except Exception:  # noqa: BLE001 - answered as a JSON-RPC internal error
        log.exception("MCP %s failed", method)
        db.rollback()
        return _rpc_error(msg_id, INTERNAL_ERROR, "Internal error")
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": result})


@router.post("/projects/{project_id}/mcp")
async def mcp_endpoint(request: Request, access: Access, db: DbSession) -> Response:
    """Streamable HTTP: one JSON-RPC message per POST, answered with application/json. GET (the SSE
    stream) and DELETE (sessions) are not offered, so they get 405."""
    raw = await apps_router.read_body_capped(request, MAX_BODY)  # never buffers more than 1 MB
    return await run_in_threadpool(handle, raw, request, access, db)
