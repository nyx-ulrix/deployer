# MCP server for AI agents

Every project has a [Model Context Protocol](https://modelcontextprotocol.io) server, so an AI agent
(Claude Code, Claude Desktop, or any MCP client) can look at the project's databases, read and change
data, and deploy its apps. The agent signs in with a project **API key**, exactly like an app using the
[data API](DATA_API.md).

```
POST <public_url>/v1/projects/<project_id>/mcp
Authorization: Bearer <key>
```

Transport: MCP **Streamable HTTP**, one JSON-RPC 2.0 message per `POST`, answered with
`application/json` (no SSE stream: `GET` and `DELETE` answer `405`). Supported protocol versions:
`2025-06-18` (latest), `2025-03-26`, `2024-11-05`; a client asking for another version gets the latest.
Methods: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`. Sessions are
not used (no `Mcp-Session-Id`); batches are refused.

## Connecting

Create a key in the dashboard (project → **API keys** → *Create key*), then open **Show usage** on it
and pick the **AI agents (MCP)** tab: it has both snippets below with your URL and project id filled in
(and the key too, once you *Reveal* it).

Claude Code:

```bash
claude mcp add --transport http deployer <public_url>/v1/projects/<project_id>/mcp \
  --header "Authorization: Bearer <key>"
```

Other clients take a JSON config such as this one (the file and the exact keys vary by client):

```json
{
  "mcpServers": {
    "deployer": {
      "type": "http",
      "url": "<public_url>/v1/projects/<project_id>/mcp",
      "headers": { "Authorization": "Bearer <key>" }
    }
  }
}
```

An agent on another machine needs to reach the instance: see "Reaching Deployer from other devices"
in the README (LAN access, or a Cloudflare hostname for the internet).

## Tools

Results are text content holding compact JSON. API errors come back as tool results with
`isError: true` and `{"error": {"code", "message", "details"}}` (the same codes as the REST API).

| Tool | Arguments | Role | What it does |
|---|---|---|---|
| `list_data_sources` | – | anon | databases: `id`, `name`, `kind`, `engine`, `status` |
| `get_schema` | `source_id?` | anon | tables/collections, columns/fields, keys, relationships (`GET /schema`) |
| `run_query` | `source_id`, `query`, `max_rows?` | service | SQL script or `mongosh` code (the query console); a viewer session may only read |
| `list_rows` | `source_id`, `table`, `limit?`, `offset?`, `filters?`, `sort?` | anon | rows + `total`; `filters` = `{column: value}` equality, ANDed; `sort` = `"column"` or `"-column"` |
| `insert_row` | `source_id`, `table`, `values` | service | inserts a row, returns it |
| `update_row` | `source_id`, `table`, `pk`, `values` | service | updates the row with that primary key |
| `delete_row` | `source_id`, `table`, `pk` | service | deletes the row with that primary key |
| `list_documents` | `source_id`, `collection`, `filter?`, `limit?`, `skip?` | anon | documents (relaxed Extended JSON) + `total` |
| `insert_document` | `source_id`, `collection`, `document` | service | inserts a document, returns it with `_id` |
| `update_document` | `source_id`, `collection`, `document_id`, `set?`, `unset?` | service | `$set` / `$unset` on one document |
| `delete_document` | `source_id`, `collection`, `document_id` | service | deletes one document |
| `list_apps` | – | service | the project's apps (push-to-deploy, [DEPLOYMENTS.md](DEPLOYMENTS.md)) with their `target` |
| `get_app` | `app_id` | service | one app: settings, `target`, `cloud` (`url`, `resources`), URLs, hostnames, live deployment |
| `deploy_app` | `app_id` | service | starts a deployment from the app's branch on the app's target; adds `target` and `cloud_url` |
| `deployment_status` | `app_id`, `deployment_id` | service | status, error, `target`, `target_url` (the cloud URL it went live on), `cloud_url` and the last 100 log lines |
| `list_cloud_connections` | – | service | the AWS / Firebase accounts the project's apps may use ([CLOUD.md](CLOUD.md)): `id`, `provider`, `name`, account id / project id, region, `status` - never credentials |
| `list_cloud_targets` | – | service | where an app can run (`local`, `aws_static`, `aws_app`, `firebase_hosting`, `firebase_app`): what each is for, that cloud targets keep serving with the PC off, cost drivers, `available` for this project |
| `app_logs` | `app_id`, `tail?` | service | runtime log lines of the live container (1..500, default 100) |

Tools a key's role can't use are **not listed** by `tools/list` and calling them is a JSON-RPC error
(`-32602 Unknown tool`). Signing in with a dashboard session token (JWT) also works; the member's
project role decides the tools (viewer = anon's tools plus read-only `run_query`, developer and up = all).

## Roles and security

- `anon` key → the agent can **only read**: schema, rows and documents (no `run_query`: queries need a service key). App tools
  (settings, build and runtime logs) need a `service` key. An anon key still reads every table and collection in the project, so
  treat it as a secret unless all the project's data is public ([DATA_API.md](DATA_API.md)).
- `service` key → the agent can also **write data** (rows, documents, any query, including `DROP`)
  and **read and deploy apps**. Give an agent a service key only if you would let it change production data;
  use an `anon` key for read-only agents.
- Keys are project-scoped: a key for another project gets `404`, a missing or unknown key `401`,
  a revoked one `401 api_key_revoked`. Revoke a key to cut an agent off immediately.
- Every `tools/call` is audited as `mcp.call` with the tool name, key id and outcome - never the
  arguments. Queries also land in the project's query log with `layout = "api"`, like any key-driven
  run ([QUERY_EDITOR.md](QUERY_EDITOR.md)).
- Keys never change app settings and never reach members, env values, backups or any other endpoint.
  Putting an app on a cloud target (billed to that cloud account) is a dashboard action for project
  admins; agents can list the targets and connections and deploy apps already on one.

## Limits

| Limit | Value |
|---|---|
| Rows per `list_rows` / `list_documents` / `run_query` statement | 200 (larger `limit` / `max_rows` are lowered) |
| Text per tool result | 256 KB, then cut with a `[truncated: ...]` note |
| Tool calls | 60 per minute per key (per user for sessions); over it: `isError` with `rate_limited` and `retry_after` |
| Request body | 1 MB (`413`) |
| Query timeout | 30 seconds (the query console default) |

## JSON-RPC errors

| Code | When |
|---|---|
| `-32700` (HTTP 400) | the body is not JSON |
| `-32600` (HTTP 400) | not a JSON-RPC 2.0 object, a batch, a bad `id`, or an unsupported `MCP-Protocol-Version` header |
| `-32601` | unknown method |
| `-32602` | unknown tool (or not allowed for the key), missing/unknown/mistyped arguments |
| `-32603` | internal error |

Authentication failures are plain HTTP `401` / `404` with the REST error body.
