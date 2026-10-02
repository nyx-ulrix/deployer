# Data API with API keys

Project **API keys** let your own apps and scripts read and write a project's databases through
Deployer's REST API without a user login. Keys are created by project admins in the dashboard
(project → API keys) or with `POST /projects/{id}/api-keys` (see [API.md](API.md)).

| Role | Acts as | Use it for |
|---|---|---|
| `anon` | viewer: read rows/documents/schema of **every** table and collection (no query endpoint) | read-only scripts, dashboards and agents you trust; public clients only if all the project's data is public |
| `service` | developer: everything `anon` can plus insert/update/delete and queries (read and write) | servers, cron jobs, backends |

**Never ship a `service` key to a browser or a mobile app.** Anyone who can open the app can extract it.

**An `anon` key can read ALL data in the project** - every table and collection, including users,
emails, password hashes and orders. It cannot write, but it is not a "public" key: there is no per-table
or per-row restriction yet. Only put it in a browser, a mobile app or a public repository if everything
in the project is meant to be public. Otherwise keep the key on a server (a backend or serverless
function) that calls Deployer and returns only what the page needs.
Keys are project-scoped and only work on the data, query and schema endpoints listed below, on the
MCP endpoint for AI agents ([MCP.md](MCP.md)) and - service keys only - on deleting a cloud database
(`DELETE /projects/{id}/cloud/databases/{sid}?confirm_name=<name>&confirm_delete=true`, [CLOUD.md](CLOUD.md)
"Deleting a cloud database over the API and MCP"); every other endpoint answers `401 api_key_not_allowed`.

## Sending the key

```
Authorization: Bearer dpl_anon_...        (or dpl_service_...)
```

Base URL: `<public_url>/v1`, e.g. `http://localhost:8080/v1` on a fresh install or
`https://deployer.example.com/v1` with remote access. All bodies and responses are JSON.

### Calling from a browser

The rows, documents (Firestore subcollection paths and listings included), Realtime Database, query and schema endpoints answer CORS requests from any origin (no cookies:
`Access-Control-Allow-Credentials` is never sent), so a web page on another origin can `fetch` them
with the `Authorization` and `Content-Type` headers. No other endpoint sends CORS headers, and the MCP
endpoint is for agents, not browsers. A page served over `https` can only call an `https` Deployer URL
(remote access, [REMOTE_ACCESS.md](REMOTE_ACCESS.md)); `http://localhost:8080` works only from pages
on the same PC or LAN over plain `http`. Everything above about the `anon` key still applies: a key in
a page is readable by every visitor.

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

### Databases in the cloud (AWS / Firebase)

Databases that live in the user's own AWS account or Firebase project ([CLOUD.md](CLOUD.md) "C2") are data
sources like any other, with `cloud` set in `GET .../data-sources` (provider, service, whether Deployer
created it). The same keys and endpoints reach them, through this PC, so **the data API needs the PC on**;
apps hosted in the same cloud reach their databases directly instead and keep working with the PC off.

- **RDS / Aurora** (MySQL, MariaDB, PostgreSQL) are SQL sources: the rows, schema and query endpoints above
  work unchanged. While AWS is still creating one, they answer `409 cloud_database_creating`.
- **DynamoDB**, **Firestore** and the **Realtime Database** are NoSQL sources with their own rules, below.

### DynamoDB tables

A DynamoDB database ([CLOUD.md](CLOUD.md) "C2-2") uses the same documents endpoints with `{name}` = a
table of the source (any other table is `404`):

- `GET`: `filter` = **equality** only (`{"status": "open"}`; naming the partition key reads just that
  partition), `limit`, and **`cursor`** instead of `skip`. Response: `{"documents": [...], "total": n |
  null, "key": ["customer", "n"], "next_cursor": "..." | null}` - pass `next_cursor` as `cursor` for the
  next page; `total` is DynamoDB's estimate (refreshed every few hours), `null` with a filter.
- Items are plain JSON: numbers, strings, booleans, `null`, lists, maps; binary is `{"$base64": "..."}`
  and sets are `{"$set": [...]}` - send the same shapes when writing.
- `{doc_id}` is the item's key as JSON, URL-encoded (`{"customer":"c1","n":2}`), or the plain value for a
  table with only a partition key. `POST` needs the key (`400 missing_key`) and refuses an existing one
  (`409 document_exists`); `PATCH` can't change the key (`400 immutable_field`); an unknown item is `404
  document_not_found`.

```js
const items = `${base}/projects/${PID}/data-sources/${SID}/collections/orders/documents`;
let page = await fetch(`${items}?limit=50`, { headers }).then((r) => r.json());
while (page.next_cursor) {
  page = await fetch(`${items}?limit=50&cursor=${encodeURIComponent(page.next_cursor)}`, { headers }).then((r) => r.json());
}
const id = encodeURIComponent(JSON.stringify({ customer: "c1", n: 2 }));
await fetch(`${items}/${id}`, { method: "PATCH", headers, body: JSON.stringify({ set: { status: "paid" } }) });
```

An app on AWS App Runner doesn't need this API for its own tables: with *Database access* it gets
`DEPLOYER_DB_<NAME>_TABLE` / `_REGION` and an AWS role for the SDK, and keeps working when the PC is off.

### Firestore collections

A Firestore database ([CLOUD.md](CLOUD.md) "C2-3") uses the same documents endpoints with `{name}` = a
**collection path**: `users`, or a subcollection `users/u1/orders` (URL-encode it as one segment or send
the slashes as they are):

- `GET`: `filter` = **equality** only (`{"status": "open"}`; dotted names reach into maps,
  `{"address.city": "Oslo"}`; `{"_id": "u1"}` is the document id), `limit`, and **`cursor`** instead of
  `skip`. Response: `{"documents": [...], "total": n, "next_cursor": "..." | null}` - documents are ordered
  by id, `total` is an exact count (with the filter).
- Documents are plain JSON with the id as `_id`; Firestore's own types are `{"$timestamp":
  "2026-01-01T00:00:00Z"}`, `{"$ref": "users/u1"}`, `{"$base64": "..."}` and `{"$geo": {"latitude": 1.5,
  "longitude": 2.5}}` - send the same shapes when writing. Whole numbers are stored as integers.
- `POST` takes `_id` in the document to pick the id (else Firestore makes one; an existing id is `409
  document_exists`); `PATCH .../documents/{doc_id}` sets / removes top-level fields (`_id` can't change);
  an unknown document is `404 document_not_found`. Deleting a document leaves its subcollections.
- `GET .../collections/{name}/documents/{doc_id}/collections` lists a document's subcollections as paths:
  `{"collections": ["users/u1/orders"]}`.

```js
const orders = `${base}/projects/${PID}/data-sources/${SID}/collections/${encodeURIComponent("users/u1/orders")}/documents`;
const page = await fetch(`${orders}?limit=50&filter=${encodeURIComponent('{"status":"open"}')}`, { headers }).then((r) => r.json());
await fetch(orders, { method: "POST", headers, body: JSON.stringify({ document: { total: 9.5, at: { $timestamp: new Date().toISOString() } } }) });
```

An app on Firebase (Cloud Run) doesn't need this API: with *Database access* it gets
`DEPLOYER_DB_<NAME>_PROJECT` / `_DATABASE` and uses the Firebase Admin SDK as its own service account.

### Realtime Database (JSON tree)

A Firebase Realtime Database ([CLOUD.md](CLOUD.md) "C2-4") is one JSON tree, read and written **by path**
(`users/ann/name`; empty is the root) at `/projects/{pid}/data-sources/{sid}/rtdb` - the documents and
collections endpoints answer `400 not_supported` for it. Keys can't contain `. $ # [ ] /`.

- `GET ?path=users` -> `{"path": "users", "value": ...}`. `shallow=true` cuts each child to `true` (or keeps
  a plain value) - list a big branch cheaply. Firebase's query parameters filter children: `orderBy` (`$key`,
  `$value`, `$priority` or a child path such as `age` or `address/city`) with `startAt`, `endAt`, `equalTo`
  (JSON - `18`, `true`, `"18"` - or plain text: `Oslo`), `limitToFirst`, `limitToLast`. Shallow and ordered
  reads also return `children: [{"key", "value"}]` **in Firebase's order** (use it: `value` is an object, whose
  key order JSON doesn't keep). Ordering by a child needs an `.indexOn` rule in the database's rules (else
  `400 query_failed` says how to add it). Over 32 MB at a path is `413 too_large`.
- `PUT` `{"path", "value"}` replaces the value at the path; `PATCH` `{"path", "value": {"name": "Ann",
  "address/city": "Oslo"}}` sets those children and keeps the others; `POST` `{"path", "value"}` adds a child
  under a Firebase-made, time-ordered key (returned as `key`; good for lists such as messages); `DELETE
  ?path=` removes the path and everything under it. Replacing or deleting the root is refused (`400
  root_write`).
- Anon keys read; writes need a service key. Deployer's access is admin, so the database's own security
  rules don't apply here - the project's roles do.

```js
const rt = `${base}/projects/${PID}/data-sources/${SID}/rtdb`;
const adults = await fetch(`${rt}?path=users&orderBy=age&startAt=18&limitToFirst=20`, { headers }).then((r) => r.json());
await fetch(rt, { method: "POST", headers, body: JSON.stringify({ path: "rooms/lobby/messages", value: { text: "hi" } }) });
```

A Firebase full app with *Database access* gets `DEPLOYER_DB_<NAME>_URL` / `_PROJECT` instead and uses the
Firebase Admin SDK (`databaseURL`) as its own service account.

## Queries

`POST /projects/{pid}/data-sources/{sid}/query` with `{"query": "...", "max_rows": 500, "timeout_seconds": 30}`
(`max_rows` 1..5000, `timeout_seconds` 1..120). SQL sources take an SQL script (several statements
allowed); MongoDB sources take `mongosh` code with `db` bound to the database. Queries need a `service` key:
an `anon` key gets `403 forbidden` here, because it may sit in a public client and each run can hold one of a
few query slots for up to 120 s; anon keys read through the rows/documents endpoints above.
Full response formats: [QUERY_CONSOLE.md](QUERY_CONSOLE.md).

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
`layout = "api"`; the log keeps the first 20 000 characters of each query.

## Schema

`GET /projects/{pid}/schema?source_id=&sample=200` returns every data source's tables/collections,
columns/fields, relationships and the project's cross-database links; `source_id` narrows it to one
source. `GET /projects/{pid}/schema/export?format=sql|mongo|bundle` downloads DDL (tables and indexes; the header lists
views, triggers and routines it skipped), and
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
| 401 | `api_key_not_allowed` | a key was used outside the data, query, schema, cloud database delete and MCP endpoints |
| 403 | `forbidden` | an `anon` key on a write endpoint or the query endpoint (the message says the key is read-only; use a `service` key) |
| 403 | `shell_code_refused` | MongoDB shell code named a Node.js escape hatch (`require`, `process`, ...; any key) |
| 404 | `not_found` | wrong project id for this key, unknown data source, table or collection |
| 422 | `validation_error` | malformed body or query parameters (`details.errors` says which) |
| 429 | `rate_limited` | more than 600 requests in a minute with this key (instance setting `api_key_rate_limit`, [MONITORING.md](MONITORING.md)); wait `details.retry_after` seconds (also the `Retry-After` header) |

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

Removing a member, or demoting an admin, does not stop the keys they created or revealed: they may have
kept a copy. The dashboard lists those keys and offers **Revoke these keys**; rotate them as above. A key
whose creator has left the project is credited to the project owner in audit and query logs.
