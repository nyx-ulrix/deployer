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
from app.routers import cloud as cloud_router
from app.routers import data as data_router
from app.routers import query as query_router
from app.routers import schema as schema_router
from app.services import audit, cloud, cloud_db, deployments, introspection, rate_limit, rtdb, source_ops
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
    "Tools for one Deployer project: its databases (SQL tables, MongoDB collections, DynamoDB tables, "
    "Firestore collections, Firebase Realtime Database JSON trees - rtdb_read / rtdb_write) and its apps "
    "(push-to-deploy websites). Start with list_data_sources and get_schema, or list_apps. Ids come from those "
    "tools. Databases can also live in the user's own AWS account - RDS SQL or DynamoDB (cloud_database_options; "
    "creating one is billable and needs the user's agreement) - or in the user's Firebase project: its Cloud "
    "Firestore database or its Realtime Database (connect_cloud_database / create_cloud_database). "
    "Results are compact JSON, capped at 200 rows / 256 KB."
)


# --- tools ---------------------------------------------------------------------------------------


def _schema(required: list[str] | None = None, **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


def _p(type_: str, description: str, **extra: Any) -> dict:
    return {"type": type_, "description": description, **extra}


SOURCE = _p("string", "Data source id (from list_data_sources)")
TABLE = _p("string", "SQL table name")
COLLECTION = _p(
    "string",
    "MongoDB collection, DynamoDB table, or Firestore collection path (users, or users/u1/orders); "
    "a Realtime Database has no collections (use rtdb_read / rtdb_write)",
)
DOC_ID = _p(
    "string",
    "MongoDB: the _id as ObjectId hex, an integer or the raw string. DynamoDB: the item's key as JSON "
    '(e.g. {"pk": "a", "sk": 1}), or the plain partition key value when the table has no sort key. '
    "Firestore: the document id (_id)",
)
TABLE_KEY = _p(
    "object",
    'DynamoDB key: {"name": "id", "type": "S"} (S text, N number, B binary)',
    properties={"name": {"type": "string"}, "type": {"type": "string", "enum": ["S", "N", "B"]}},
    required=["name"],
)
APP = _p("string", "App id (from list_apps)")
CONNECTION = _p("string", "Cloud connection id (from list_cloud_connections)")
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
    out = []
    for ds in project_sources(ctx.db, ctx.access.project.id):
        row = {"id": ds.id, "name": ds.name, "kind": ds.kind, "engine": ds.engine, "status": ds.status}
        if ds.cloud_connection_id or ds.cloud_state:  # docs/CLOUD.md "C2": where it lives
            c = cloud_db.cloud_out(ds, ctx.db)
            row["cloud"] = {k: c[k] for k in ("provider", "service", "created", "resource_id", "region")}
        out.append(row)
    return out


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
        **({"cursor": args["cursor"]} if args.get("cursor") else {}),
    )


def t_list_subcollections(ctx: Ctx, args: dict) -> Any:
    return data_router.list_subcollections(
        args["source_id"], args["collection"], args["document_id"], ctx.access, ctx.db
    )


def t_export_documents(ctx: Ctx, args: dict) -> Any:
    ds = get_source(ctx.db, ctx.access.project.id, args["source_id"])
    if ds.engine == rtdb.ENGINE:
        return cloud_router.export_rtdb(args["source_id"], ctx.request, ctx.access, ctx.db, path=args.get("path", ""))
    return cloud_router.export_firestore(
        args["source_id"], ctx.request, ctx.access, ctx.db, collection=args.get("collections"), limit=_limit(args, 200)
    )


def t_rtdb_read(ctx: Ctx, args: dict) -> Any:
    ds = data_router._rtdb_source(ctx.db, ctx.access, args["source_id"])
    query = {k: args.get(k) for k in ("shallow", *rtdb.QUERY_PARAMS)}
    if query["orderBy"] is not None and query["limitToFirst"] is None and query["limitToLast"] is None:
        query["limitToFirst"] = MAX_ROWS  # the result cap: only what fits
    return rtdb.read(ds, args.get("path", ""), query)


def t_rtdb_write(ctx: Ctx, args: dict) -> Any:
    ds = data_router._rtdb_source(ctx.db, ctx.access, args["source_id"])
    return rtdb.write(ds, args["operation"], args.get("path", ""), args.get("value"))


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


def t_cloud_database_options(ctx: Ctx, args: dict) -> Any:
    return cloud_db.options()


def t_list_cloud_databases(ctx: Ctx, args: dict) -> Any:
    return cloud_db.list_resources(ctx.db, ctx.access.project.id, args["connection_id"])


def t_create_cloud_database(ctx: Ctx, args: dict) -> Any:
    body = cloud_router.CloudDatabaseCreate(**args)
    return cloud_router.create_database(body, ctx.request, ctx.access, ctx.db)


def t_connect_cloud_database(ctx: Ctx, args: dict) -> Any:
    body = cloud_router.CloudDatabaseConnect(**args)
    return cloud_router.connect_database(body, ctx.request, ctx.access, ctx.db)


def t_list_cloud_backups(ctx: Ctx, args: dict) -> Any:
    return cloud_router.list_cloud_backups(args["source_id"], ctx.access, ctx.db)


def t_create_cloud_backup(ctx: Ctx, args: dict) -> Any:
    body = cloud_router.CloudBackupCreate(**{k: v for k, v in args.items() if k != "source_id"})
    return cloud_router.create_cloud_backup(args["source_id"], body, ctx.request, ctx.access, ctx.db)


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
        "Run SQL (a script, several statements allowed), MongoDB shell code (`db` is the database), one "
        'DynamoDB request as JSON ({"operation": "Query", "TableName": ..., plus AWS parameters with plain JSON '
        'values}) or one Firestore request as JSON ({"from": "orders", "where": [{"field": "status", "op": "==", '
        '"value": "open"}], "orderBy": [{"field": "total", "direction": "desc"}], "limit": 20}; operation count, '
        'get, create, update, delete) or one Realtime Database request as JSON ({"path": "users", "orderBy": '
        '"age", "startAt": 18, "limitToFirst": 20}; operation set, update, push, delete with "value") against a '
        f"data source. Returns up to {MAX_ROWS} rows per statement. Viewer sessions may only read (DynamoDB: "
        "Query, Scan, GetItem; Firestore: query, count, get; Realtime Database: get).",
        _schema(
            ["source_id", "query"],
            source_id=SOURCE,
            query=_p(
                "string",
                "SQL, mongosh code such as db.orders.find({status: 'open'}), a DynamoDB request such as "
                '{"operation": "Query", "TableName": "orders", "KeyConditionExpression": "customer = :c", '
                '"ExpressionAttributeValues": {":c": "c1"}}, or a Firestore request such as '
                '{"from": "orders", "where": {"field": "total", "op": ">", "value": 10}, "limit": 20}',
            ),
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
        "Read documents of a MongoDB collection (relaxed Extended JSON), items of a DynamoDB table or documents "
        "of a Firestore collection path, with the total count. DynamoDB / Firestore: equality filters only "
        "(DynamoDB: naming the partition key reads just that partition; Firestore: dotted names reach into maps, "
        "_id is the document id), page with next_cursor -> cursor; DynamoDB's `key` lists the table's key "
        'attributes. Firestore values: {"$timestamp": ...}, {"$ref": "users/u1"}, {"$base64": ...}, {"$geo": ...}.',
        _schema(
            ["source_id", "collection"],
            source_id=SOURCE,
            collection=COLLECTION,
            filter=_p("object", 'Query filter, e.g. {"status": "open"} (MongoDB: $where is refused)'),
            limit=LIMIT,
            skip=_p("integer", "MongoDB: documents to skip (default 0)", minimum=0),
            cursor=_p("string", "DynamoDB / Firestore: next_cursor of the previous page"),
        ),
        t_list_documents,
    ),
    "list_subcollections": (
        "viewer",
        "Firestore: the collections under one document, as collection paths (users/u1/orders) the document tools take.",
        _schema(
            ["source_id", "collection", "document_id"], source_id=SOURCE, collection=COLLECTION, document_id=DOC_ID
        ),
        t_list_subcollections,
    ),
    "export_documents": (
        "developer",
        "Firestore: every document of the top-level collections (or the given collection paths) as JSON, up to "
        f"`limit` documents (default 200, max {MAX_ROWS} here; the dashboard exports up to 10,000); `truncated` "
        "says when more were left. Subcollections are exported by naming their path. Realtime Database: the JSON "
        "at `path` (default the whole database; results over 256 KB are cut, so export a smaller path).",
        _schema(
            ["source_id"],
            source_id=SOURCE,
            collections=_p("array", "Collection paths (default: every top-level collection)", items={"type": "string"}),
            limit=LIMIT,
            path=_p("string", "Realtime Database: the path to export, e.g. users (default: the whole database)"),
        ),
        t_export_documents,
    ),
    "rtdb_read": (
        "viewer",
        "Firebase Realtime Database: read the JSON at a path (users/ann; empty for the root). shallow: true lists "
        "only the children's keys (each value cut to true, or kept when plain) - use it to explore a big tree. "
        'Filter with orderBy ("$key", "$value" or a child path such as "age") plus startAt / endAt / equalTo / '
        f"limitToFirst / limitToLast (limitToFirst defaults to {MAX_ROWS} with orderBy); ordered reads also return "
        "`children` as [{key, value}] in order. Ordering by a child needs an .indexOn rule in Firebase.",
        _schema(
            ["source_id"],
            source_id=SOURCE,
            path=_p("string", "Path in the tree, e.g. users or users/ann (default: the root)"),
            shallow=_p("boolean", "Only the children's keys (not combinable with the filters)"),
            orderBy=_p("string", '"$key", "$value", "$priority" or a child path such as "age"'),
            startAt={"description": "Smallest value (or key) to include: text, number or boolean"},
            endAt={"description": "Largest value (or key) to include: text, number or boolean"},
            equalTo={"description": "Only children whose orderBy value equals this: text, number or boolean"},
            limitToFirst=_p("integer", "Only the first N children (in orderBy order)", minimum=1),
            limitToLast=_p("integer", "Only the last N children (in orderBy order)", minimum=1),
        ),
        t_rtdb_read,
    ),
    "rtdb_write": (
        "developer",
        "Firebase Realtime Database: write at a path. operation set replaces the value at path; update sets the "
        'given children of path ({"name": "Ann", "address/city": "Oslo"}) and keeps the others; push adds value as '
        "a new child with a Firebase-made, time-ordered key (returned as `key`); delete removes path and everything "
        "under it. Setting or deleting the root is refused. Keys cannot contain . $ # [ ] /.",
        _schema(
            ["source_id", "operation", "path"],
            source_id=SOURCE,
            operation=_p("string", "set, update, push or delete", enum=list(rtdb.WRITE_OPERATIONS)),
            path=_p("string", "Path in the tree, e.g. users/ann"),
            value={"description": "Any JSON (set, push); an object of child paths to values (update)"},
        ),
        t_rtdb_write,
    ),
    "insert_document": (
        "developer",
        "Insert a document into a MongoDB collection (returns it with its _id), an item into a DynamoDB "
        "table (it must contain the table's key; an existing key is refused) or a document into a Firestore "
        "collection path (_id in the document picks its id, else Firestore generates one).",
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
        "Set and/or unset top-level fields of one MongoDB document, DynamoDB item or Firestore document; _id / "
        "the key cannot change.",
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
        "Delete one MongoDB document, DynamoDB item or Firestore document (its subcollections stay).",
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
    "cloud_database_options": (
        "developer",
        "Where a database can live (this PC, another server, the user's AWS account, Firebase) in plain "
        "language - what each means, cost, and whether it stays up when the PC is off - plus the sizes, cost "
        "and networking of a new AWS database. Explain these to the user before creating one.",
        _schema(),
        t_cloud_database_options,
    ),
    "list_cloud_databases": (
        "developer",
        "The RDS / Aurora databases in an AWS connection's region (from list_cloud_connections), with which "
        "ones Deployer can connect to (`problem` says why not) and this PC's public IP, plus the region's "
        "DynamoDB `tables`; for a Firebase connection, its project's Firestore databases (`firestore`) and "
        "Realtime Databases (`rtdb`, with their URLs).",
        _schema(["connection_id"], connection_id=CONNECTION),
        t_list_cloud_databases,
    ),
    "create_cloud_database": (
        "developer",
        "BILLABLE: create a new RDS database (MySQL, MariaDB or PostgreSQL; default db.t4g.micro, 20 GB, backups, "
        "deletion protection, encrypted; 5-15 minutes) or a DynamoDB table (engine dynamodb: on-demand billing, "
        "deletion protection; under a minute) in the user's AWS account. It stays up when the PC is off and AWS "
        "bills the user (see cloud_database_options for the cost). With a Firebase connection, engine "
        "firebase_rtdb creates the project's default Realtime Database in `location` (or connects it when it "
        "exists; free quota, then Google bills storage and downloads; ready at once, job is null). Only call "
        "after the user agreed to the cost, with confirm_billing: true. Returns the data source (status creating "
        "for AWS) and a job. Apps on aws_app / firebase_app with database_access then get DEPLOYER_DB_<NAME>_*.",
        _schema(
            ["connection_id", "name", "engine", "confirm_billing"],
            connection_id=CONNECTION,
            name=_p("string", "Data source name, unique in the project"),
            engine=_p(
                "string",
                "mysql, mariadb, postgresql or dynamodb (AWS), firebase_rtdb (Firebase)",
                enum=["mysql", "mariadb", "postgresql", "dynamodb", "firebase_rtdb"],
            ),
            instance_class=_p("string", "RDS: db.t4g.micro (default), db.t4g.small or db.t4g.medium"),
            location=_p(
                "string",
                "Realtime Database: us-central1 (default), europe-west1 or asia-southeast1 - cannot change later",
                enum=list(rtdb.LOCATIONS),
            ),
            partition_key={**TABLE_KEY, "description": "DynamoDB: the partition key (default a text id)"},
            sort_key={**TABLE_KEY, "description": "DynamoDB: an optional sort key"},
            confirm_billing=_p("boolean", "Must be true: the user agreed to the cloud charges"),
        ),
        t_create_cloud_database,
    ),
    "connect_cloud_database": (
        "developer",
        "Connect an existing RDS / Aurora database (resource_id from list_cloud_databases) with the user's "
        "database login, existing DynamoDB tables (tables from list_cloud_databases), or - with a Firebase "
        "connection - the project's Cloud Firestore database (database: (default) or a named one; free to "
        "connect, Google bills reads and writes) or, with instance, its Realtime Database (an id from "
        "list_cloud_databases' rtdb). Deployer only connects; it never changes that database, its "
        "firewall or the tables' settings. Apps on firebase_app with database_access then get "
        "DEPLOYER_DB_<NAME>_PROJECT / _DATABASE (Realtime Database: also _URL).",
        _schema(
            ["connection_id", "name"],
            connection_id=CONNECTION,
            name=_p("string", "Data source name, unique in the project"),
            resource_id=_p("string", "Instance or cluster id from list_cloud_databases"),
            username=_p("string", "Database user"),
            password=_p("string", "Database password"),
            database=_p(
                "string", 'RDS: database name (defaults to the instance\'s own); Firestore: "(default)" or an id'
            ),
            tables=_p("array", "DynamoDB: table names (instead of resource_id)", items={"type": "string"}),
            instance=_p("string", "Realtime Database: the instance id from list_cloud_databases (rtdb)"),
        ),
        t_connect_cloud_database,
    ),
    "list_cloud_backups": (
        "viewer",
        "On-demand backups in AWS of a DynamoDB data source's tables, newest first, with how to restore one.",
        _schema(["source_id"], source_id=SOURCE),
        t_list_cloud_backups,
    ),
    "create_cloud_backup": (
        "developer",
        "BILLABLE (about US$0.10 per GB per month until deleted in AWS): take an on-demand backup of a DynamoDB "
        "data source's tables (or one table). Only call after the user agreed, with confirm_billing: true.",
        _schema(
            ["source_id", "confirm_billing"],
            source_id=SOURCE,
            table=_p("string", "One table (default: every table of the data source)"),
            confirm_billing=_p("boolean", "Must be true: the user agreed to the AWS charges"),
        ),
        t_create_cloud_backup,
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


_TYPES = {"string": str, "integer": int, "object": dict, "array": list, "boolean": bool}


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
        expected = _TYPES.get(prop.get("type"))  # untyped: any JSON (Realtime Database values)
        if (
            expected is not None
            and value is not None
            and (not isinstance(value, expected) or (isinstance(value, bool) and expected is not bool))
        ):
            raise RpcError(INVALID_PARAMS, f"Argument {key} must be of type {prop['type']}")
    return {k: v for k, v in args.items() if v is not None}


def _visible(access: ProjectAccess) -> list[str]:
    # run_query refuses anon keys (A-031), so they don't see it.
    return [
        name
        for name, (role, *_) in TOOLS.items()
        if access.at_least(role) and not (name == "run_query" and access.is_anon_key)
    ]


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
