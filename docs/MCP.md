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
| `list_data_sources` | – | anon | databases: `id`, `name`, `kind`, `engine`, `status`, and `cloud` (`provider`, `service`, `created`, `resource_id`, `region`) for databases in the user's AWS account or Firebase project |
| `get_schema` | `source_id?` | anon | tables/collections, columns/fields, keys, relationships (`GET /schema`) |
| `run_query` | `source_id`, `query`, `max_rows?` | service | SQL script, `mongosh` code or one DynamoDB / Firestore / Realtime Database request as JSON (the query console); a viewer session may only read |
| `list_rows` | `source_id`, `table`, `limit?`, `offset?`, `filters?`, `sort?` | anon | rows + `total`; `filters` = `{column: value}` equality, ANDed; `sort` = `"column"` or `"-column"` |
| `insert_row` | `source_id`, `table`, `values` | service | inserts a row, returns it |
| `update_row` | `source_id`, `table`, `pk`, `values` | service | updates the row with that primary key |
| `delete_row` | `source_id`, `table`, `pk` | service | deletes the row with that primary key |
| `list_documents` | `source_id`, `collection`, `filter?`, `limit?`, `skip?`, `cursor?` | anon | documents (relaxed Extended JSON) + `total`; DynamoDB tables: items, `key`, `next_cursor` (pass as `cursor`), equality filters only; Firestore: `collection` is a path (`users/u1/orders`), documents carry `_id`, `next_cursor` / equality filters as DynamoDB |
| `insert_document` | `source_id`, `collection`, `document` | service | inserts a document, returns it with `_id` (DynamoDB: the item must contain its key; Firestore: `_id` picks the id) |
| `update_document` | `source_id`, `collection`, `document_id`, `set?`, `unset?` | service | `$set` / `$unset` on one document (DynamoDB: `document_id` is the item's key as JSON) |
| `delete_document` | `source_id`, `collection`, `document_id` | service | deletes one document or DynamoDB item |
| `list_subcollections` | `source_id`, `collection`, `document_id` | anon | Firestore: the collections under one document, as paths (`users/u1/orders`) the document tools take |
| `export_documents` | `source_id`, `collections?`, `limit?`, `path?` | service | Firestore: every document of the top-level collections (or the given paths) as JSON, up to `limit` (default 200); `truncated` when more were left. Realtime Database: the JSON at `path` (default the whole database; over 256 KB is cut) |
| `rtdb_read` | `source_id`, `path?`, `shallow?`, `orderBy?`, `startAt?`, `endAt?`, `equalTo?`, `limitToFirst?`, `limitToLast?` | anon | Firebase Realtime Database ([CLOUD.md](CLOUD.md) "C2-4"): the JSON at a path; `shallow` lists only the children's keys; Firebase's query parameters filter children (`limitToFirst` defaults to 200 with `orderBy`) and add `children` in order |
| `rtdb_write` | `source_id`, `operation`, `path`, `value?` | service | Realtime Database: `set` (replace), `update` (children by path), `push` (new child, returns `key`) or `delete` at a path; the root can't be replaced or deleted |
| `list_apps` | – | service | the project's apps (push-to-deploy, [DEPLOYMENTS.md](DEPLOYMENTS.md)) with their `target` |
| `get_app` | `app_id` | service | one app: settings, `target`, `cloud` (`url`, `resources`), `build` (where it builds: `pc` or `github` with its setup status and links), URLs, hostnames, live deployment |
| `deploy_app` | `app_id` | service | starts a deployment from the app's branch on the app's target; adds `target` and `cloud_url`. An app that builds on GitHub Actions runs its workflow there instead: `{github_actions: true, status: "dispatched", runs_url}` (follow it with `list_github_runs`) |
| `set_build_location` | `app_id`, `location` (`pc` or `github`), `confirm_billing?` | admin | where a cloud app builds ([CLOUD.md](CLOUD.md) "C3"): `github` commits a workflow to the app's GitHub repository that builds every push on GitHub and deploys it straight to the cloud with a short-lived OIDC sign-in, so pushes deploy while the PC is off. Needs the app deployed once, the admin's GitHub connection with the `workflow` permission and `confirm_billing: true` after the user agreed GitHub may bill build minutes (free for public repositories, 2,000 minutes a month free for private ones); returns `build`, the setup `job_id` and the plain-language `locations`. `pc` removes the workflow and the sign-in |
| `set_app_secrets_store` | `app_id`, `enabled`, `confirm_billing?` | admin | keep an App Runner / Cloud Run app's variables and database passwords in AWS Secrets Manager / Google Secret Manager instead of the service's plain environment ([CLOUD.md](CLOUD.md) "G1"; one secret per variable, read only by the app's own identity, values never shown). **Billable** (AWS about US$0.40 per secret per month; Google a small per-version cost beyond its free tier): `enabled: true` needs `confirm_billing: true` after the user agreed. Either way the live version is republished at once (`env_deployment_id`); `false` deletes the stored secrets |
| `set_app_target` | `app_id`, `target`, `connection_id?`, `confirm_billing?`, `confirm_teardown?` | admin | where an app runs ([CLOUD.md](CLOUD.md)): `local` (this PC) or a cloud target in the user's account (`aws_static` / `firebase_hosting` for static sites, `aws_app` / `firebase_app` for servers) with a `connection_id` of its provider. **Billable**: a cloud target needs `confirm_billing: true` after the user agreed to the cost (`list_cloud_targets` has it). Moving an app off a cloud target where it has resources answers `teardown_not_confirmed` with `details.resources` until `confirm_teardown: true` (they are deleted, with the rollback history). Needs no running deployment and no custom domains; deploy afterwards with `deploy_app` |
| `list_github_runs` | `app_id` | service | the newest GitHub Actions runs of an app that builds there (status, conclusion, commit, link) - also runs while the PC was off |
| `deployment_status` | `app_id`, `deployment_id` | service | status, error, `target`, `target_url` (the cloud URL it went live on), `cloud_url` and the last 100 log lines |
| `list_cloud_connections` | – | admin | the AWS / Firebase accounts the project's apps may use ([CLOUD.md](CLOUD.md)): `id`, `provider`, `name`, account id / project id, region, `status` - never credentials |
| `list_cloud_targets` | – | service | where an app can run (`local`, `aws_static`, `aws_app`, `firebase_hosting`, `firebase_app`): what each is for, that cloud targets keep serving with the PC off, cost drivers, `available` for this project |
| `cloud_database_options` | – | service | where a database can live (this PC, another server, the user's AWS account, Firebase) in plain language, and the sizes, cost and networking of a new AWS database ([CLOUD.md](CLOUD.md) "C2-1"), DynamoDB, Firestore and the Realtime Database (`firestore` / `rtdb`: what each is, one sentence on how they differ, cost, how apps reach it) |
| `list_cloud_databases` | `connection_id` | admin | the RDS / Aurora databases in that AWS connection's region, `problem` when Deployer can't connect one, this PC's public IP, and the region's DynamoDB `tables`; for a Firebase connection the project's Firestore databases (`firestore`) and Realtime Databases (`rtdb`, with URLs) |
| `create_cloud_database` | `connection_id`, `name`, `engine`, `instance_class?`, `partition_key?`, `sort_key?`, `location?`, `database?`, `confirm_billing` | admin | **billable**: creates an RDS database (`mysql`, `mariadb`, `postgresql`) or a DynamoDB table (`dynamodb`, keys `{name, type: S\|N\|B}`, default a text `id`) in the user's AWS account (stays up with the PC off), or with a Firebase connection `firebase_rtdb` (the project's default Realtime Database in `location`; `job` null) or `firestore` (a new Firestore database in `location`, default `nam5`, with id `database`, default `deployer-<name>-<id8>`; `creating` for about a minute); refused unless `confirm_billing` is `true` - ask the user first. Returns the data source (`creating`) and the job |
| `connect_cloud_database` | `connection_id`, `name`, `resource_id?`, `username?`, `password?`, `database?`, `tables?`, `instance?` | admin | connects an existing RDS / Aurora database (`resource_id` + login), existing DynamoDB `tables`, or - with a Firebase `connection_id` - the project's Firestore database (`database`, default `(default)`; free to connect, Google bills reads and writes) or a Realtime Database (`instance`, an id from `list_cloud_databases`' `rtdb`); never changes them |
| `list_cloud_backups` | `source_id` | anon | a DynamoDB database's on-demand backups in AWS, newest first, each table's point-in-time recovery (`pitr: [{table, status, earliest, latest, days, problem}]`) and the cost notes |
| `create_cloud_backup` | `source_id`, `table?`, `confirm_billing` | admin | **billable** (about US$0.10 per GB per month until deleted in AWS): an on-demand backup of the tables (or one) - ask the user first |
| `delete_cloud_database` | `source_id`, `confirm_name`, `confirm_delete` | admin or service key | **destructive**: deletes a database in the user's AWS account or Firebase project ([CLOUD.md](CLOUD.md) "Deleting a cloud database over the API and MCP"). One Deployer created (RDS, DynamoDB) is deleted in AWS by a cleanup job after a final snapshot / backup that stays there (billed for storage until the user deletes it); a connected one (Firestore, Realtime Database, connected RDS / DynamoDB) is only forgotten. Without `confirm_name` equal to the database's exact name and `confirm_delete: true` it answers `delete_not_confirmed` with `details: {name, removes, keeps}` - call it that way first, show the user the list and only after their yes call again confirmed. Returns `{ok, job?, name, removes, keeps}`; `not_a_cloud_database` for a database on this PC |
| `set_point_in_time_recovery` | `source_id`, `table`, `enabled`, `confirm_billing?` | admin | point-in-time recovery of one table on (**billable**, about US$0.20 per GB of table per month: `confirm_billing: true` after the user agreed) or off (deletes the restore window) |
| `restore_cloud_backup` | `source_id`, `name`, `backup_arn?` or `table` + (`point_in_time` or `latest: true`), `confirm_billing` | admin | **billable** (about US$0.15 per GB restored, then the new table): restores a backup of one of the source's tables, or a table at a time in its window, into a **new** `deployer-*` table that becomes the new data source `name` (`creating` until the job finishes); the original is never changed - ask the user first |
| `list_firestore_backups` | `source_id` | anon | a Firestore database's backup `schedules`, its `backups` (each `name` restorable), recent managed exports / imports (`operations`, with their `gs://` folder), the exports stored in its `deployer-*` bucket (`exports`), `status` (point-in-time recovery, `earliest_version_time`, `delete_protection`), the cost notes, and `problems` when the service account may not read a list ([CLOUD.md](CLOUD.md) "Firestore backups") |
| `firestore_export` | `source_id`, `bucket?`, `create_bucket?`, `collections?`, `confirm_billing` | admin | **billable** (one read per document, plus Cloud Storage for the files until deleted): starts a managed export to a bucket the user made, or (`create_bucket: true`) to `deployer-<project>-firestore`; returns the `operation` and its `output_uri` |
| `firestore_import` | `source_id`, `input_uri`, `name`, `database?`, `location?`, `collections?`, `confirm_billing` | admin | **billable**: loads an export (`input_uri`, its `gs://` folder) into a **new** Firestore database, added as data source `name` (`creating`); never over existing data |
| `set_firestore_backup_schedule` | `source_id`, `recurrence` (`daily` / `weekly`), `day?`, `retention_days`, `confirm_billing` | admin | **billable** (backup storage): a scheduled backup Google takes by itself (one daily and one weekly at most; kept up to 7 / 98 days) |
| `delete_firestore_backup_schedule` | `source_id`, `schedule_id` | admin | stops a schedule; backups already taken stay until they expire |
| `restore_firestore_backup` | `source_id`, `backup`, `name`, `database?`, `confirm_billing` | admin | **billable**: restores a backup (`name` from `list_firestore_backups`) into a **new** Firestore database, added as data source `name` (`creating`); the original is not touched |
| `set_firestore_point_in_time_recovery` | `source_id`, `enabled`, `confirm_billing?` | admin | point-in-time recovery on (**billable**: 7 days of versions instead of 1 hour, billed as storage; `confirm_billing: true`) or off ([CLOUD.md](CLOUD.md) "Firestore point-in-time recovery and deletes") |
| `restore_firestore_to_time` | `source_id`, `point_in_time`, `name`, `database?`, `confirm_billing` | admin | **billable**: copies the database as it was at a minute since `status.earliest_version_time` into a **new** database, added as data source `name` (`creating`); `invalid_restore_time` outside the window |
| `delete_firestore_database` | `source_id`, `confirm_name`, `confirm_delete` | admin | **destructive, no undo**: deletes the Firestore database in Google (every document; `delete_protected` while Google's delete protection is on), then the data source; backups already taken stay until they expire. Without the exact name and `confirm_delete: true` it answers `delete_not_confirmed` with `details: {name, removes, keeps}` - call it that way first and ask the user. Not for service keys |
| `delete_firestore_backup` | `source_id`, `backup`, `confirm_name`, `confirm_delete` | admin | **destructive**: deletes one backup of the database (same confirmation) |
| `delete_firestore_export` | `source_id`, `uri`, `confirm_name`, `confirm_delete` | admin | **destructive**: deletes the files of one export Deployer made of the database in a `deployer-*` bucket (`uri` from `list_firestore_backups`' `exports`; same confirmation) |
| `app_logs` | `app_id`, `tail?` | service | runtime log lines of the live container (1..500, default 100) |

Tools a key's role can't use are **not listed** by `tools/list` and calling them is a JSON-RPC error
(`-32602 Unknown tool`). Signing in with a dashboard session token (JWT) also works; the member's
project role decides the tools (viewer = anon's tools plus read-only `run_query`, developer = the service
key's tools, admin and owner = all). The **Role** column is never below the role of the REST route a tool
wraps (a test compares them): the `admin` tools - the user's cloud accounts and creating / connecting cloud
databases, which bill or reach those accounts - need a project admin's session; service keys act as
developer and don't get them. The one exception is `delete_cloud_database` ("admin or service key"): its
REST route takes an admin's session or a service key (not a developer's session), so the tool does too.

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
  Agents with a service key can list the cloud targets and deploy apps already on one. With a project
  **admin's** session an agent can also put an app on a cloud target or move it back (`set_app_target`,
  billable: only with `confirm_billing: true` - ask the user first), list the cloud connections and their databases, create a database
  in the user's AWS account (`create_cloud_database`, billable, only with `confirm_billing: true` - ask the
  user first; with a Firebase connection, `engine: "firebase_rtdb"` creates the project's default Realtime
  Database, same rule), connect an existing one (also a Firebase project's Firestore database or Realtime
  Database, `instance`), create a Firestore database (`engine: "firestore"`, same rule), back up DynamoDB
  tables (`create_cloud_backup`, same rule), switch on their point-in-time recovery or restore a backup / point in time into a new table (`set_point_in_time_recovery`,
  `restore_cloud_backup`, same rule), export, schedule backups of and restore Firestore databases
  (`firestore_export`, `firestore_import`, `set_firestore_backup_schedule`, `restore_firestore_backup`, same
  rule; restores and imports always make a new database), switch on a Firestore database's point-in-time recovery
  or copy it as it was at a minute into a new database (`set_firestore_point_in_time_recovery`,
  `restore_firestore_to_time`, same rule), delete a Firestore database, backup or export in Google
  (`delete_firestore_database`, `delete_firestore_backup`, `delete_firestore_export`: dry run first, then the
  exact name and `confirm_delete: true` after the user's yes), move a cloud app's
  builds to GitHub Actions (`set_build_location`, same rule for GitHub's build minutes) or keep an app's
  variables in the cloud secret store (`set_app_secrets_store`, same rule). A service key can
  read and change the data of every cloud database the project has (the data tools above, the same as for
  databases on this PC), export Firestore / Realtime Database JSON (`export_documents`) and delete a cloud
  database (`delete_cloud_database`: only after the user said yes, with its exact name and
  `confirm_delete: true`; the final snapshot / backup stays in AWS). Deleting a project is a dashboard action.

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
