# Data API with API keys

Project **API keys** let your own apps and scripts read and write a project's databases through
Deployer's REST API without a user login. Keys are created by project admins in the dashboard
(project → API keys) or with `POST /projects/{id}/api-keys` (see [API.md](API.md)).

| Role | Acts as | Use it for |
|---|---|---|
| `anon` | viewer: read rows/documents/schema, **read-only** queries | browsers, mobile apps, public clients |
| `service` | developer: everything `anon` can plus insert/update/delete and write queries | servers, cron jobs, backends |

**Never ship a `service` key to a browser or a mobile app.** Anyone who can open the app can extract it.
Keys are project-scoped and only work on the data, query and schema endpoints listed below; every other
endpoint answers `401 api_key_not_allowed`.

## Sending the key

```
Authorization: Bearer dpl_anon_...        (or dpl_service_...)
```

Base URL: `<public_url>/v1`, e.g. `http://localhost:8080/v1` on a fresh install or
`https://deployer.example.com/v1` with remote access. All bodies and responses are JSON.

Path parameters used below: `{pid}` project id, `{sid}` data source id (both are in the config file,
see the end of this page), `{table}` SQL table name, `{name}` MongoDB collection name.

## Rows (SQL sources)

`GET /projects/{pid}/data-sources/{sid}/tables/{table}/rows` — query parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `limit` | 50 | rows per page, 1..500 |
| `offset` | 0 | rows to skip |
| `order_by` | primary key | column to sort by (`400 unknown_column` if it does not exist) |
| `order` | `asc` | `asc` or `desc` |

Response: `{"columns": ["id", "name"], "primary_key": ["id"], "rows": [{"id": 1, "name": "..."}], "total": 42}`.
Binary values come back as `{"$base64": "..."}`, decimals as strings, dates and times as ISO strings.
Send the same shapes when writing. Tables without a primary key are read-only.

```bash
curl -H "Authorization: Bearer $DEPLOYER_KEY" \
  "http://localhost:8080/v1/projects/$PID/data-sources/$SID/tables/items/rows?limit=20&order_by=id&order=desc"
```

```js
const base = "http://localhost:8080/v1";
const headers = { Authorization: `Bearer ${process.env.DEPLOYER_KEY}`, "Content-Type": "application/json" };

const page = await fetch(`${base}/projects/${PID}/data-sources/${SID}/tables/items/rows?limit=20`, { headers })
  .then((r) => r.json());
console.log(page.total, page.rows);
```

```python
import os, requests

base = "http://localhost:8080/v1"
s = requests.Session()
s.headers["Authorization"] = f"Bearer {os.environ['DEPLOYER_KEY']}"

page = s.get(f"{base}/projects/{PID}/data-sources/{SID}/tables/items/rows", params={"limit": 20}).json()
print(page["total"], page["rows"])
```

Writes (`service` key only) use the same path:

| Method | Body | Response |
|---|---|---|
| `POST` | `{"values": {"name": "Widget", "price": "9.99"}}` | `{"row": {...}}` (the inserted row, defaults filled in) |
| `PATCH` | `{"pk": {"id": 1}, "values": {"name": "Widget 2"}}` | `{"row": {...}}` |
| `DELETE` | `{"pk": {"id": 1}}` | `{"ok": true}` (`404 row_not_found` if it did not exist) |

`pk` must contain exactly the primary key columns (`400 invalid_primary_key`).

```bash
curl -X POST -H "Authorization: Bearer $DEPLOYER_KEY" -H "Content-Type: application/json" \
  -d '{"values": {"name": "Widget", "price": "9.99"}}' \
  "http://localhost:8080/v1/projects/$PID/data-sources/$SID/tables/items/rows"
curl -X PATCH ... -d '{"pk": {"id": 1}, "values": {"name": "Widget 2"}}' "$ROWS_URL"
curl -X DELETE ... -d '{"pk": {"id": 1}}' "$ROWS_URL"
```

```js
const rows = `${base}/projects/${PID}/data-sources/${SID}/tables/items/rows`;
await fetch(rows, { method: "POST", headers, body: JSON.stringify({ values: { name: "Widget" } }) });
await fetch(rows, { method: "PATCH", headers, body: JSON.stringify({ pk: { id: 1 }, values: { name: "Widget 2" } }) });
await fetch(rows, { method: "DELETE", headers, body: JSON.stringify({ pk: { id: 1 } }) });
```

```python
rows = f"{base}/projects/{PID}/data-sources/{SID}/tables/items/rows"
s.post(rows, json={"values": {"name": "Widget"}}).raise_for_status()
s.patch(rows, json={"pk": {"id": 1}, "values": {"name": "Widget 2"}}).raise_for_status()
s.delete(rows, json={"pk": {"id": 1}}).raise_for_status()
```

## Documents (MongoDB sources)

`GET /projects/{pid}/data-sources/{sid}/collections/{name}/documents` — query parameters `filter`
(a JSON object, MongoDB Extended JSON allowed; query operators such as `$where` are refused),
`limit` (default 50, max 500) and `skip` (default 0). Response: `{"documents": [...], "total": n}` in
relaxed Extended JSON (`_id` of an ObjectId is `{"$oid": "..."}`).

Writes (`service` key only). `{doc_id}` is the string form of `_id`: an ObjectId hex string, an
integer, or the raw string value.

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `.../collections/{name}/documents` | `{"document": {...}}` | `{"document": {...}}` (with its `_id`) |
| `PATCH` | `.../collections/{name}/documents/{doc_id}` | `{"set": {...}, "unset": ["field"]}` | `{"document": {...}}` |
| `DELETE` | `.../collections/{name}/documents/{doc_id}` | – | `{"ok": true}` |

`_id` cannot be changed (`400 immutable_field`); an empty update is `400 empty_update`; an unknown id
is `404 document_not_found`.

```bash
DOCS="http://localhost:8080/v1/projects/$PID/data-sources/$SID/collections/orders/documents"
curl -H "Authorization: Bearer $DEPLOYER_KEY" "$DOCS?filter=%7B%22status%22%3A%22open%22%7D&limit=10"
curl -X POST -H "Authorization: Bearer $DEPLOYER_KEY" -H "Content-Type: application/json" \
  -d '{"document": {"status": "open", "total": 12.5}}' "$DOCS"
curl -X PATCH ... -d '{"set": {"status": "paid"}, "unset": ["note"]}' "$DOCS/665f1c2e9b1d4a0012345678"
curl -X DELETE -H "Authorization: Bearer $DEPLOYER_KEY" "$DOCS/665f1c2e9b1d4a0012345678"
```

```js
const docs = `${base}/projects/${PID}/data-sources/${SID}/collections/orders/documents`;
const open = await fetch(`${docs}?${new URLSearchParams({ filter: JSON.stringify({ status: "open" }), limit: 10 })}`, { headers })
  .then((r) => r.json());
const created = await fetch(docs, { method: "POST", headers, body: JSON.stringify({ document: { status: "open" } }) })
  .then((r) => r.json());
const id = created.document._id.$oid;
await fetch(`${docs}/${id}`, { method: "PATCH", headers, body: JSON.stringify({ set: { status: "paid" } }) });
await fetch(`${docs}/${id}`, { method: "DELETE", headers });
```

```python
import json
docs = f"{base}/projects/{PID}/data-sources/{SID}/collections/orders/documents"
open_orders = s.get(docs, params={"filter": json.dumps({"status": "open"}), "limit": 10}).json()
created = s.post(docs, json={"document": {"status": "open"}}).json()
doc_id = created["document"]["_id"]["$oid"]
s.patch(f"{docs}/{doc_id}", json={"set": {"status": "paid"}, "unset": ["note"]})
s.delete(f"{docs}/{doc_id}")
```

## Queries

`POST /projects/{pid}/data-sources/{sid}/query` with `{"query": "...", "max_rows": 500, "timeout_seconds": 30}`
(`max_rows` 1..5000, `timeout_seconds` 1..120). SQL sources take an SQL script (several statements
allowed); MongoDB sources take `mongosh` code with `db` bound to the database. `anon` keys may only run
read-only statements (`403 read_only_role` otherwise). Full response formats: [QUERY_CONSOLE.md](QUERY_CONSOLE.md).

SQL: `{"kind": "sql", "results": [{"statement": "...", "type": "rows", "columns": [...], "rows": [[...]], "row_count": n, "truncated": false}, ...]}`
— `rows` are arrays aligned with `columns`; `type` is `count` (with `affected_rows`), `empty` or `error` for other statements.
MongoDB: `{"kind": "nosql", "output": "...", "result": <last expression>, "result_docs": [...] | null, "error": null | {...}}`.

```bash
curl -X POST -H "Authorization: Bearer $DEPLOYER_KEY" -H "Content-Type: application/json" \
  -d '{"query": "SELECT id, name FROM items WHERE price > 10 ORDER BY id LIMIT 20"}' \
  "http://localhost:8080/v1/projects/$PID/data-sources/$SID/query"
```

```js
const res = await fetch(`${base}/projects/${PID}/data-sources/${SID}/query`, {
  method: "POST", headers, body: JSON.stringify({ query: "db.orders.find({ status: 'open' }).limit(5)" }),
}).then((r) => r.json());
console.log(res.result_docs ?? res.results);
```

```python
res = s.post(f"{base}/projects/{PID}/data-sources/{SID}/query", json={"query": "SELECT COUNT(*) AS n FROM items"}).json()
print(res["results"][0]["rows"])   # [[42]]
```

Every key-driven run is kept in the project's query log (visible to admins in the dashboard) with
`layout = "api"`.

## Schema

`GET /projects/{pid}/schema?source_id=&sample=200` returns every data source's tables/collections,
columns/fields, relationships and the project's cross-database links; `source_id` narrows it to one
source. `GET /projects/{pid}/schema/export?format=sql|mongo|bundle` downloads DDL, and
`GET /projects/{pid}/schema/links` lists the links. Creating tables, collections or links needs a user login.

```bash
curl -H "Authorization: Bearer $DEPLOYER_KEY" "http://localhost:8080/v1/projects/$PID/schema?source_id=$SID"
```

## Errors

Every error is `{"error": {"code": "...", "message": "...", "details": {}}}`:

| HTTP | `code` | When |
|---|---|---|
| 401 | `unauthorized` | missing header, or the key does not exist |
| 401 | `api_key_revoked` | the key was revoked; switch to a new key |
| 401 | `api_key_not_allowed` | a key was used outside the data, query and schema endpoints |
| 403 | `forbidden` | an `anon` key on a write endpoint |
| 403 | `read_only_role` | an `anon` key ran a query that writes |
| 404 | `not_found` | wrong project id for this key, unknown data source, table or collection |
| 422 | `validation_error` | malformed body or query parameters (`details.errors` says which) |

Other codes (`unknown_column`, `invalid_primary_key`, `row_not_found`, `query_failed`, `database_unavailable`, ...)
are listed per endpoint in [API.md](API.md) and [QUERY_CONSOLE.md](QUERY_CONSOLE.md).

## Config file

In the dashboard, an admin can **Download config** for a key (`GET /projects/{pid}/api-keys/{key_id}/config`),
which saves `deployer-<project>-<role>.json`:

```json
{"deployer": {
  "url": "https://deployer.example.com/v1",
  "project_id": "…", "project": "shop", "role": "anon",
  "api_key": "dpl_anon_…",
  "data_sources": [{"id": "…", "name": "main", "kind": "sql", "engine": "mariadb"}],
  "endpoints": {"rows": "/projects/{project_id}/data-sources/{source_id}/tables/{table}/rows",
                "documents": "/projects/{project_id}/data-sources/{source_id}/collections/{name}/documents",
                "query": "/projects/{project_id}/data-sources/{source_id}/query",
                "schema": "/projects/{project_id}/schema"},
  "generated_at": "2026-09-22T10:00:00"}}
```

`url` is the base URL, `project_id` and `data_sources[].id` fill the `{project_id}` / `{source_id}`
placeholders of `endpoints`, and `api_key` is the secret. The file contains the secret: keep it out of
version control (add it to `.gitignore`) and load it from disk or an environment variable.

Admins can also **Reveal** a key's secret again (`GET .../api-keys/{key_id}/reveal`). Keys created
before this feature cannot be revealed (`409 not_revealable`): create a new one.

## Rotating a key

1. Create a new key with the same role.
2. Deploy your app with the new key (or download the new config file).
3. Revoke the old key. Requests with it fail immediately with `401 api_key_revoked`.

Each key shows a *last used* time in the dashboard, so you can confirm the old key is idle before revoking it.
