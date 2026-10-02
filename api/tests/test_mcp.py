"""MCP server for AI agents (docs/MCP.md): JSON-RPC over POST /v1/projects/{id}/mcp."""

import json

import pytest
from sqlalchemy import select

from app.main import app as fastapi_app
from app.models import AuditLog, Deployment, QueryRun, role_rank
from app.routers import mcp
from app.services import connections, deployments, source_ops
from tests.apps_support import make_app

READ_TOOLS = {
    "list_data_sources",
    "get_schema",
    "run_query",
    "list_rows",
    "list_documents",
    "list_cloud_backups",
    "list_subcollections",
    "rtdb_read",
}
# App tools need a service key (or a developer+ session): anon keys only get the read-only data tools.
APP_TOOLS = {
    "list_apps",
    "get_app",
    "deployment_status",
    "app_logs",
    "deploy_app",
    "list_github_runs",
    "list_cloud_targets",
    "cloud_database_options",
    "export_documents",
}
# The cloud account tools: admin-only, like the REST routes they wrap (service keys act as developer).
ADMIN_TOOLS = {
    "list_cloud_connections",
    "list_cloud_databases",
    "create_cloud_database",
    "connect_cloud_database",
    "create_cloud_backup",
    "set_point_in_time_recovery",
    "restore_cloud_backup",
    "set_build_location",
    "set_app_target",
    "set_app_secrets_store",
}
# Admin tools whose route also takes a service key (require_role(..., service_keys=True)): not developers.
KEY_ADMIN_TOOLS = {"delete_cloud_database"}
WRITE_TOOLS = {
    "insert_row",
    "update_row",
    "delete_row",
    "insert_document",
    "update_document",
    "delete_document",
    "rtdb_write",
}


@pytest.fixture
def env(client, db, project_setup, sqlite_engine, monkeypatch, make_source):
    monkeypatch.setattr(connections, "get_sql_engine", lambda ds: sqlite_engine)
    project = project_setup["project"]
    ds = make_source(project)

    def make_key(role: str) -> dict:
        resp = client.post(
            f"/v1/projects/{project.id}/api-keys",
            json={"name": f"{role} key", "role": role},
            headers=project_setup["owner"],
        )
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['secret']}"}

    url = f"/v1/projects/{project.id}/mcp"

    def rpc(headers: dict, method: str, params: dict | None = None, *, msg_id=1, status: int = 200) -> dict:
        body = {"jsonrpc": "2.0", "id": msg_id, "method": method, **({"params": params} if params else {})}
        resp = client.post(url, json=body, headers=headers)
        assert resp.status_code == status, resp.text
        out = resp.json()
        assert out["jsonrpc"] == "2.0" and out["id"] == msg_id
        return out

    def call(headers: dict, tool: str, **arguments) -> tuple[bool, object]:
        """Returns (is_error, parsed text content) of a tools/call."""
        result = rpc(headers, "tools/call", {"name": tool, "arguments": arguments})["result"]
        text = result["content"][0]["text"]
        return result["isError"], json.loads(text)

    return {
        **project_setup,
        "ds": ds,
        "url": url,
        "anon": make_key("anon"),
        "service": make_key("service"),
        "rpc": rpc,
        "call": call,
    }


def test_initialize_negotiates_version_and_notifications(client, env):
    for asked, answered in [("2025-06-18", "2025-06-18"), ("2025-03-26", "2025-03-26"), ("1999-01-01", "2025-06-18")]:
        out = env["rpc"](env["anon"], "initialize", {"protocolVersion": asked, "capabilities": {}})["result"]
        assert out["protocolVersion"] == answered
        assert out["capabilities"] == {"tools": {"listChanged": False}}
        assert out["serverInfo"]["name"] == "deployer" and "Shop" in out["instructions"]
    note = client.post(env["url"], json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=env["anon"])
    assert note.status_code == 202 and note.content == b""
    assert env["rpc"](env["anon"], "ping", msg_id="p")["result"] == {}
    assert client.get(env["url"], headers=env["anon"]).status_code == 405


def test_tools_list_depends_on_role(env):
    def names(headers):
        tools = env["rpc"](headers, "tools/list")["result"]["tools"]
        for tool in tools:
            assert tool["description"] and tool["inputSchema"]["type"] == "object"
        return {t["name"] for t in tools}

    assert names(env["anon"]) == READ_TOOLS - {"run_query"}  # A-031: queries need a service key
    assert names(env["service"]) == READ_TOOLS | WRITE_TOOLS | APP_TOOLS | KEY_ADMIN_TOOLS
    assert names(env["viewer"]) == READ_TOOLS  # JWT sessions work too, with the member's role
    assert names(env["dev"]) == READ_TOOLS | WRITE_TOOLS | APP_TOOLS
    assert names(env["owner"]) == READ_TOOLS | WRITE_TOOLS | APP_TOOLS | ADMIN_TOOLS | KEY_ADMIN_TOOLS


def test_admin_tools_refuse_service_keys_and_developers(env):
    for headers in (env["service"], env["dev"]):
        for tool in ADMIN_TOOLS:
            out = env["rpc"](headers, "tools/call", {"name": tool, "arguments": {"connection_id": "c"}})
            assert out["error"]["code"] == mcp.INVALID_PARAMS and "Unknown tool" in out["error"]["message"]
    is_error, out = env["call"](
        env["owner"], "create_cloud_database", connection_id="c", name="x", engine="dynamodb", confirm_billing=False
    )
    assert is_error and out["error"]["code"] == "billing_not_confirmed"  # admins reach the route's own checks


# Every tool and the REST route(s) it wraps: the tool's role may never be below the route's (C2-1 review).
TOOL_ROUTES = {
    "list_data_sources": [("GET", "/data-sources")],
    "get_schema": [("GET", "/schema")],
    "run_query": [("POST", "/data-sources/{source_id}/query")],
    "list_rows": [("GET", "/data-sources/{source_id}/tables/{table}/rows")],
    "insert_row": [("POST", "/data-sources/{source_id}/tables/{table}/rows")],
    "update_row": [("PATCH", "/data-sources/{source_id}/tables/{table}/rows")],
    "delete_row": [("DELETE", "/data-sources/{source_id}/tables/{table}/rows")],
    "list_documents": [("GET", "/data-sources/{source_id}/collections/{name:path}/documents")],
    "insert_document": [("POST", "/data-sources/{source_id}/collections/{name:path}/documents")],
    "update_document": [("PATCH", "/data-sources/{source_id}/collections/{name:path}/documents/{doc_id}")],
    "delete_document": [("DELETE", "/data-sources/{source_id}/collections/{name:path}/documents/{doc_id}")],
    "list_subcollections": [
        ("GET", "/data-sources/{source_id}/collections/{name:path}/documents/{doc_id}/collections")
    ],
    "export_documents": [
        ("GET", "/data-sources/{source_id}/firestore/export"),
        ("GET", "/data-sources/{source_id}/rtdb-export"),
    ],
    "rtdb_read": [("GET", "/data-sources/{source_id}/rtdb")],
    "rtdb_write": [(m, "/data-sources/{source_id}/rtdb") for m in ("PUT", "PATCH", "POST", "DELETE")],
    "list_apps": [("GET", "/apps")],
    "get_app": [("GET", "/apps/{app_id}")],
    "deploy_app": [("POST", "/apps/{app_id}/deploy")],
    "set_build_location": [("PUT", "/apps/{app_id}/build")],
    "set_app_target": [("PATCH", "/apps/{app_id}")],
    "set_app_secrets_store": [("PATCH", "/apps/{app_id}")],
    "list_github_runs": [("GET", "/apps/{app_id}/github-runs")],
    "deployment_status": [("GET", "/apps/{app_id}/deployments/{deployment_id}")],
    "app_logs": [("GET", "/apps/{app_id}/logs")],
    "list_cloud_connections": [("GET", "/cloud/connections")],
    "list_cloud_targets": [("GET", "/cloud/targets")],
    "cloud_database_options": [("GET", "/cloud/databases/options")],
    "list_cloud_databases": [("GET", "/cloud/connections/{connection_id}/databases")],
    "create_cloud_database": [("POST", "/cloud/databases")],
    "connect_cloud_database": [("POST", "/cloud/databases/connect")],
    "list_cloud_backups": [("GET", "/data-sources/{source_id}/cloud-backups")],
    "create_cloud_backup": [("POST", "/data-sources/{source_id}/cloud-backups")],
    "delete_cloud_database": [("DELETE", "/cloud/databases/{source_id}")],
    "set_point_in_time_recovery": [("PUT", "/data-sources/{source_id}/cloud-backups/pitr")],
    "restore_cloud_backup": [("POST", "/data-sources/{source_id}/cloud-backups/restore")],
}


def _route_role(method: str, path: str, var: str = "minimum"):
    """The `minimum` (or another argument, e.g. `service_keys`) of the route's require_role dependency."""
    full = "/v1/projects/{project_id}" + path
    route = next(r for r in fastapi_app.routes if getattr(r, "path", None) == full and method in r.methods)
    for dep in route.dependant.dependencies:
        call = dep.call
        if call.__name__ == "dependency" and "minimum" in call.__code__.co_freevars:
            return call.__closure__[call.__code__.co_freevars.index(var)].cell_contents
    raise AssertionError(f"no role dependency on {method} {full}")


def test_every_tool_needs_at_least_its_routes_role():
    assert set(TOOL_ROUTES) == set(mcp.TOOLS)  # a new tool names its route here
    for tool, routes in TOOL_ROUTES.items():
        needed = max((_route_role(m, p) for m, p in routes), key=role_rank)
        assert role_rank(mcp.TOOLS[tool][0]) >= role_rank(needed), (tool, needed)
        # A service key gets an admin tool only when every route it wraps takes one too.
        if tool in mcp.SERVICE_KEY_TOOLS:
            assert all(_route_role(m, p, "service_keys") for m, p in routes), tool


def test_anon_cannot_write(env):
    out = env["rpc"](env["anon"], "tools/call", {"name": "insert_row", "arguments": {}})
    assert out["error"]["code"] == mcp.INVALID_PARAMS and "Unknown tool" in out["error"]["message"]
    out = env["rpc"](env["anon"], "tools/call", {"name": "run_query", "arguments": {}})
    assert out["error"]["code"] == mcp.INVALID_PARAMS and "Unknown tool" in out["error"]["message"]
    is_error, body = env["call"](env["viewer"], "run_query", source_id=env["ds"].id, query="DELETE FROM items")
    assert is_error and body["error"]["code"] == "read_only_role"


def test_data_tools(env, db):
    call, service, sid = env["call"], env["service"], env["ds"].id
    is_error, sources = call(env["anon"], "list_data_sources")
    assert not is_error and sources == [
        {"id": sid, "name": "main-sql", "kind": "sql", "engine": "mariadb", "status": "ok"}
    ]
    _, schema = call(env["anon"], "get_schema", source_id=sid)
    assert schema["sources"][0]["entities"][0]["name"] == "items"

    _, page = call(env["anon"], "list_rows", source_id=sid, table="items", limit=2, sort="-id")
    assert [r["id"] for r in page["rows"]] == [7, 6] and page["total"] == 7
    _, filtered = call(env["anon"], "list_rows", source_id=sid, table="items", filters={"name": "item 3"})
    assert [r["id"] for r in filtered["rows"]] == [3] and filtered["total"] == 1
    is_error, bad = call(env["anon"], "list_rows", source_id=sid, table="items", filters={"nope": 1})
    assert is_error and bad["error"]["code"] == "unknown_column"

    _, inserted = call(service, "insert_row", source_id=sid, table="items", values={"name": "new"})
    assert inserted["row"] == {**inserted["row"], "id": 8, "name": "new"}
    _, updated = call(service, "update_row", source_id=sid, table="items", pk={"id": 8}, values={"name": "renamed"})
    assert updated["row"]["name"] == "renamed"
    assert call(service, "delete_row", source_id=sid, table="items", pk={"id": 8}) == (False, {"ok": True})
    is_error, missing = call(service, "delete_row", source_id=sid, table="items", pk={"id": 8})
    assert is_error and missing["error"]["code"] == "row_not_found"

    _, result = call(service, "run_query", source_id=sid, query="SELECT COUNT(*) AS n FROM items")
    assert result["results"][0]["rows"] == [[7]] and result["run_id"]
    db.expire_all()
    runs = list(db.scalars(select(QueryRun)))
    assert [(r.layout, r.status) for r in runs] == [("api", "ok")]

    audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "mcp.call")))
    assert len(audits) == 10 and {a.details["tool"] for a in audits} >= {"run_query", "insert_row"}
    assert all("renamed" not in json.dumps(a.details) and "SELECT" not in json.dumps(a.details) for a in audits)


def test_document_tools(env, db, monkeypatch, make_source):
    ds = make_source(env["project"], kind="nosql")
    calls = []

    def recorder(name):
        def fn(source, *args, **kwargs):
            calls.append((name, source.id, *args, kwargs))
            return {"ok": name}

        return fn

    for name in ("list_documents", "insert_document", "update_document", "delete_document"):
        monkeypatch.setattr(source_ops, name, recorder(name))
    call, service = env["call"], env["service"]
    assert call(env["anon"], "list_documents", source_id=ds.id, collection="orders", filter={"s": 1}, limit=999) == (
        False,
        {"ok": "list_documents"},
    )
    call(service, "insert_document", source_id=ds.id, collection="orders", document={"s": 1})
    call(service, "update_document", source_id=ds.id, collection="orders", document_id="7", set={"s": 2}, unset=["x"])
    call(service, "delete_document", source_id=ds.id, collection="orders", document_id="7")
    assert calls == [
        ("list_documents", ds.id, "orders", {"filter_json": '{"s": 1}', "limit": 200, "skip": 0}),
        ("insert_document", ds.id, "orders", {"s": 1}, {}),
        ("update_document", ds.id, "orders", "7", {"s": 2}, ["x"], {}),
        ("delete_document", ds.id, "orders", "7", {}),
    ]
    is_error, wrong = call(env["anon"], "list_rows", source_id=ds.id, table="orders")
    assert is_error and wrong["error"]["code"] == "wrong_source_kind"


def test_mongo_query_through_fake_shell(env, db, fake_mongosh, make_source):
    ds = make_source(env["project"], kind="nosql")
    is_error, out = env["call"](env["service"], "run_query", source_id=ds.id, query="db.items.find()", max_rows=2)
    assert not is_error and out["kind"] == "nosql" and len(out["result_docs"]) == 2 and out["truncated"] is True


def test_app_tools(env, db, fake_redis):
    app = make_app(db, env["project"])
    call = env["call"]
    for tool in APP_TOOLS | ADMIN_TOOLS:  # build/runtime logs and app settings never reach an anon (public) key
        out = env["rpc"](env["anon"], "tools/call", {"name": tool, "arguments": {"app_id": app.id}})
        assert out["error"]["code"] == mcp.INVALID_PARAMS and "Unknown tool" in out["error"]["message"]
    _, apps = call(env["service"], "list_apps")
    assert [a["id"] for a in apps] == [app.id]
    _, one = call(env["service"], "get_app", app_id=app.id)
    assert one["name"] == "Shop"
    is_error, missing = call(env["service"], "get_app", app_id="nope")
    assert is_error and missing["error"]["code"] == "not_found"

    _, dep = call(env["service"], "deploy_app", app_id=app.id)
    assert dep["status"] == "queued" and dep["trigger"] == "manual"
    row = db.get(Deployment, dep["id"])
    row.log = "\n".join(f"line {i}" for i in range(150))
    db.commit()
    _, status = call(env["service"], "deployment_status", app_id=app.id, deployment_id=dep["id"])
    lines = status["log_tail"].splitlines()
    assert status["status"] == "queued" and "log" not in status
    assert len(lines) == mcp.LOG_TAIL_LINES and lines[-1] == "line 149"

    fake_redis.rpush(deployments.logs_key(app.id), "a", "b", "c")
    assert call(env["service"], "app_logs", app_id=app.id, tail=2)[1] == {"lines": ["b", "c"], "container": None}


def test_truncation(env, sqlite_engine, monkeypatch):
    with sqlite_engine.begin() as conn:
        for i in range(8, 300):
            conn.exec_driver_sql("INSERT INTO items (id, name) VALUES (?, ?)", (i, f"item {i}"))
    _, page = env["call"](env["anon"], "list_rows", source_id=env["ds"].id, table="items", limit=500)
    assert len(page["rows"]) == mcp.MAX_ROWS and page["total"] == 299
    _, result = env["call"](env["service"], "run_query", source_id=env["ds"].id, query="SELECT * FROM items")
    assert len(result["results"][0]["rows"]) == mcp.MAX_ROWS and result["results"][0]["truncated"] is True

    monkeypatch.setattr(mcp, "MAX_TEXT", 300)
    out = env["rpc"](
        env["anon"], "tools/call", {"name": "list_rows", "arguments": {"source_id": env["ds"].id, "table": "items"}}
    )
    text = out["result"]["content"][0]["text"]
    assert text.endswith("smaller query]") and "[truncated" in text and len(text) < 500


def test_rate_limit(env, monkeypatch):
    monkeypatch.setattr(mcp, "CALL_LIMIT", 2)
    assert env["call"](env["anon"], "list_data_sources")[0] is False
    assert env["call"](env["anon"], "list_data_sources")[0] is False
    is_error, body = env["call"](env["anon"], "list_data_sources")
    assert is_error and body["error"]["code"] == "rate_limited" and body["error"]["details"]["retry_after"] > 0
    assert env["call"](env["service"], "list_data_sources")[0] is False  # per key


def test_auth(client, env, make_user, make_project):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post(env["url"], json=body).status_code == 401
    unknown = {"Authorization": "Bearer dpl_anon_" + "x" * 43}
    assert client.post(env["url"], json=body, headers=unknown).status_code == 401
    other = make_project(make_user(), "Other")
    resp = client.post(f"/v1/projects/{other.id}/mcp", json=body, headers=env["anon"])
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"


def test_malformed_requests(client, env):
    url, h = env["url"], env["anon"]

    def post(content, status):
        resp = client.post(url, content=content, headers={**h, "Content-Type": "application/json"})
        assert resp.status_code == status, resp.text
        return resp.json()["error"]["code"]

    assert post(b"{not json", 400) == mcp.PARSE_ERROR
    assert post(b"[]", 400) == mcp.INVALID_REQUEST
    assert post(b'{"id": 1, "method": "ping"}', 400) == mcp.INVALID_REQUEST
    assert post(b'{"jsonrpc": "2.0", "id": {}, "method": "ping"}', 400) == mcp.INVALID_REQUEST
    assert post(b"x" * (mcp.MAX_BODY + 1), 413) == mcp.INVALID_REQUEST
    assert env["rpc"](h, "resources/list")["error"]["code"] == mcp.METHOD_NOT_FOUND
    for args in ({}, {"source_id": 1, "query": "x"}, {"source_id": "s", "query": "x", "extra": 1}):
        out = env["rpc"](env["service"], "tools/call", {"name": "run_query", "arguments": args})
        assert out["error"]["code"] == mcp.INVALID_PARAMS
    resp = client.post(
        url, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={**h, "MCP-Protocol-Version": "1999-01-01"}
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == mcp.INVALID_REQUEST
    # A response to a (never sent) server request is accepted and ignored.
    assert client.post(url, json={"jsonrpc": "2.0", "id": 5, "result": {}}, headers=h).status_code == 202
