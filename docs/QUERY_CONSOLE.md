# Query Console

A code editor + results terminal in the dashboard (project tab **Query**) to run SQL against a
project's SQL data sources and MongoDB shell code against its NoSQL data sources. The user picks the
database from a selector; everything runs through the control plane with the project's roles.

## API

`POST /v1/projects/{project_id}/data-sources/{sid}/query` (SQL, MongoDB shell code, or one DynamoDB,
Firestore or Realtime Database request as JSON - "DynamoDB", "Firestore" and "Realtime Database" below)

| Field | Type | Notes |
|---|---|---|
| `query` | string (1..200 000 chars) | SQL text (several statements allowed) or MongoDB shell code |
| `max_rows` | int 1..5000, default 500 | rows returned per result set / documents printed |
| `timeout_seconds` | int 1..120, default 30 | per statement (SQL) or for the whole script (MongoDB) |

Every role: MongoDB shell code may not name a Node.js escape hatch - `require`, `process`,
`child_process`, `fs`, `module`, `global`, `globalThis`, `eval`, `Function`, `constructor`, `Reflect`,
`import`, `load`, `snippet` - matched as whole identifiers anywhere, strings and comments included
(`{kind: "import"}` is refused too; `{kind: "imp" + "ort"}` is the workaround), otherwise
`403 shell_code_refused`. This is a speed bump; the boundary is the `query-shell` sidecar the shell
runs in, which holds no Deployer secrets (below, and [SECURITY.md](../SECURITY.md) "Query console").

Roles: **developer+** can run anything else. **viewer** may run only read-only queries, otherwise
`403 read_only_role`. The classification below is textual and best effort, an early refusal. SQL runs
are also enforced by the database: the console connection is switched to read-only mode first
(`SET SESSION TRANSACTION READ ONLY` on MariaDB/MySQL; on PostgreSQL `SET SESSION CHARACTERISTICS AS
TRANSACTION READ ONLY` plus one `START TRANSACTION READ ONLY` around the whole script), so a write that
slips past the text check fails as a statement error. If that mode cannot be set the run is refused
with `503 read_only_unavailable`. MongoDB has no such mode: there the source's database user is the
real boundary (use an external source with a read-only user for strict enforcement):
- SQL: every statement must start with `SELECT`, `WITH`, `SHOW`, `EXPLAIN`, `DESCRIBE`, `DESC`,
  `TABLE`, `VALUES` (after stripping comments, leading parentheses entered; checked with `sqlparse`)
  and, except for `SHOW ...`, must not contain a writing keyword anywhere outside strings and
  comments (`INSERT`, `UPDATE`, `DELETE`, `REPLACE`, `MERGE`, `INTO`, `CREATE`, `ALTER`, `DROP`,
  `TRUNCATE`, `GRANT`, `LOCK`, `SET`, `CALL`, `LOAD`, `COPY`, `OUTFILE`, transaction control, ...).
  This also stops PostgreSQL data-modifying CTEs (`WITH d AS (DELETE ...) SELECT`),
  `SELECT ... FOR UPDATE` and `SELECT ... INTO OUTFILE`. Side-effecting functions are refused by
  name too (`setval`, `nextval`, `set_config`, `pg_terminate_backend`, `pg_cancel_backend`,
  `pg_reload_conf`, `pg_rotate_logfile`, `pg_notify`, `dblink`, `dblink_exec`), since a read-only
  transaction does not stop all of them. A column or table named like one of these keywords
  (`start`, `copy`, `release`...) must be quoted (`` `start` `` on MariaDB/MySQL, `"start"` on
  PostgreSQL); the `read_only_role` message names the word that tripped the check.
- MongoDB: the code must not contain any of these names as a whole identifier, anywhere (strings and
  comments included - over-matching is the safe direction): `insert`, `insertOne`, `insertMany`,
  `update`, `updateOne`, `updateMany`, `replaceOne`, `delete`, `deleteOne`, `deleteMany`, `remove`,
  `save`, `drop`, `dropDatabase`, `dropIndex`, `dropIndexes`, `createCollection`, `createIndex`,
  `createIndexes`, `ensureIndex`, `createView`, `renameCollection`, `convertToCapped`, `reIndex`, `bulkWrite`,
  `findOneAndUpdate`, `findOneAndReplace`, `findOneAndDelete`, `findAndModify`, `mapReduce`, `$out`,
  `$merge`, `runCommand`, `adminCommand`, bulk and search/encryption index helpers (`removeOne`,
  `initializeOrderedBulkOp`, `hideIndex`, `createSearchIndex`, ...), every user and role helper
  (`createUser`, `dropAllUsers`, `changeUserPassword`, `grantRolesToUser`, `dropRole`, ...), server
  helpers (`shutdownServer`, `fsyncLock`, `killOp`, `setProfilingLevel`, ...), the `rs`, `sh` and
  `sp` globals, `getSiblingDB`, `getMongo`, `Mongo`, `connect` and the shell internals `_mongo`,
  `_serviceProvider`, `_run*Command` (full list: `MONGO_WRITE_NAMES` in
  `api/app/services/query_console.py`; plus the Node.js names above). This is a textual blocklist:
  the source's database user is still `dbOwner` on its database, so a determined viewer who builds a
  name from strings gets that user's rights.
  Regardless of role the script always starts against the source's own database only (`db` is bound
  to it by the wrapper) with the source's own credentials, never root.

Errors: `404 not_found`, `403 forbidden` / `read_only_role` / `shell_code_refused`, `422 validation_error` (also for a SQL
script without any statement), `503 device_offline`, `503 database_unavailable` (cannot connect /
authenticate), `503 read_only_unavailable` (viewer SQL run, read-only mode could not be set), `504 query_timeout` (MongoDB script killed), `501 mongosh_unavailable`,
`429 too_many_queries` (MongoDB: more than 4 shells at once; SQL: the source's connection pool, 2+3 connections shared with the data browser, stayed full for 10 s). Query errors are **not** HTTP errors:
a SQL syntax/runtime error is reported per statement (`type: "error"`, HTTP 200) and a MongoDB error
in the `error` field (HTTP 200), so earlier results and printed output are kept.

### SQL response

```json
{
  "kind": "sql", "engine": "mariadb", "duration_ms": 12,
  "results": [
    {"statement": "SELECT ...", "type": "rows", "columns": ["id", "email"], "rows": [[1, "a@b.c"]],
     "row_count": 1, "truncated": false, "duration_ms": 3},
    {"statement": "UPDATE ...", "type": "count", "affected_rows": 2, "duration_ms": 1},
    {"statement": "CREATE TABLE ...", "type": "empty", "duration_ms": 8},
    {"statement": "SELEC ...", "type": "error", "error": {"code": "query_failed", "message": "..."}, "duration_ms": 1}
  ]
}
```

- Statements are split with `sqlparse` (strings and comments respected; comments ahead of a statement
  stay with it, chunks holding only comments or `;` are dropped) and run **sequentially on one
  connection** in autocommit mode; execution stops at the first error (that statement carries the
  error, earlier results are kept). `statement` is the statement text as written. Values are encoded
  like the data browser (`encode_value`: bytes → `{"$base64": ...}`, decimals as strings, dates as ISO
  strings). `columns` may repeat names, which is why `rows` are arrays.
- `type` is `rows` when the statement returned a result set, `count` for INSERT/UPDATE/DELETE/REPLACE/
  MERGE/LOAD/COPY (also when 0 rows were affected) or any other statement with a positive row count,
  `empty` otherwise (DDL, `SET`, ...).
- `rows` holds at most `max_rows` rows; `truncated` is true when more existed (`max_rows + 1` are
  fetched). With PyMySQL (MariaDB/MySQL) rows are streamed, so `SELECT * FROM huge` costs
  `max_rows + 1` rows of memory; psycopg (PostgreSQL) fetches the whole result client-side - use `LIMIT`.
- Timeouts, per statement: the engine's own setting is tried first on the connection (MariaDB
  `SET SESSION max_statement_time`, MySQL `SET SESSION max_execution_time` - ms, SELECT only -,
  PostgreSQL `SET statement_timeout`), and a watchdog timer backs it up for every statement, also
  writes and when that `SET` failed: at `timeout_seconds` it sends PostgreSQL a cancel request,
  MariaDB/MySQL a `KILL QUERY <thread id>` from a separate connection, SQLite an interrupt. Either
  way the statement is reported as a per-statement error with `code: "query_timeout"` and the
  following statements do not run. A statement that completes just as the timer fires keeps its
  result, because it did run.
- Never interpolate anything into the user's SQL; it runs as given with `exec_driver_sql` and the
  `no_parameters` execution option (so PyMySQL/psycopg treat `%` literally, e.g. `LIKE 'x%'`).
- The connection is **invalidated after every run** (dropped from the pool), so `SET`, `USE`,
  temporary tables, user variables or the statement timeout can never affect other requests. A
  connection failure before the first statement is `503 database_unavailable` (password redacted).

### MongoDB response

```json
{"kind": "nosql", "engine": "mongodb", "duration_ms": 640,
 "output": "text printed by the shell (print(), warnings, stderr)",
 "result": <relaxed Extended JSON of the last expression, or null>,
 "result_docs": [<documents>] | null,
 "truncated": false,
 "error": null | {"code": "query_failed", "message": "MongoServerError: ... [BadValue]"}}
```

The script runs in a real **`mongosh`** installed in the API image (2.11.1, official `.deb` from
`downloads.mongodb.com`, SHA-256 verified in `api/Dockerfile`, amd64 only), but never in the API or
worker containers: it runs in the **`query-shell`** service of `deploy/docker-compose.yml`
(`app/shell_runner.py`, same image, `python -m app.shell_runner` on port 8090). The API (and, for
device-hosted sources, the device's worker) POSTs `{uri, database, code, marker, batch,
timeout_seconds}` to `QUERY_SHELL_URL` (`http://query-shell:8090/run`) and parses the shell's
output that comes back. The sidecar:

- has no Deployer environment (no MASTER_KEY, JWT_SECRET, database root passwords or REDIS_URL), no
  volumes, no Docker socket, a read-only root filesystem with a 64 MiB `/tmp`, all capabilities
  dropped except CHOWN, DAC_OVERRIDE, KILL, SETUID and SETGID (to run each shell under its own uid and
  clean up after it), `no-new-privileges`, 1 CPU, 512 MiB (`QUERY_SHELL_MEM_LIMIT`) and 256 processes;
- is on the internal `query` network, shared only with the API, the worker and MongoDB (not MariaDB,
  Redis or apps), plus `query_egress`, which only it joins, for external MongoDB servers (the
  internet and `host.docker.internal`);
- runs each shell as one of four slot users (uid 20001-20004, created in `api/Dockerfile`), so
  concurrent shells cannot read each other's environment or memory, and the runner itself (root)
  is out of their reach; after every run all processes of that uid are killed (found in `/proc` and
  killed by the runner itself, so a script that used up the process cap cannot block it; an init,
  `init: true`, reaps them) and its files in `/tmp` and `/dev/shm` removed, so a script cannot leave
  anything behind for the next one. A slot with a process that survives is retired (logged by the
  sidecar) instead of reused; restarting the `query-shell` container brings it back.

`501 mongosh_unavailable` when the binary is missing in the image (e.g. on other architectures) or
`QUERY_SHELL_URL` is not set; `503 mongosh_unavailable` when the sidecar cannot be reached.
`/etc/mongosh.conf` turns telemetry, update checks and log files off. Execution, as verified against
the real binary in the sidecar (`tests/integration/test_query_console.py`):

- `mongosh --nodb --quiet --norc --eval <wrapper>` with a private temporary directory as `HOME`
  (mongosh's own config/history land there and are deleted with it). The wrapper
  (`shell_runner.WRAPPER_JS`) is a fixed script without secrets or user code; everything variable
  comes from the child's environment - `DEPLOYER_QUERY_URI` (the source's own URI, with connect /
  server-selection timeouts of 5 s added unless the URI sets them), `DEPLOYER_QUERY_DB`,
  `DEPLOYER_QUERY_FILE` (the user's code, written to a 0600 file in that directory),
  `DEPLOYER_QUERY_MARKER`, `DEPLOYER_QUERY_BATCH` (`max_rows + 1`). Nothing else is passed (a
  script can read `process.env`). The wrapper sets
  `config.set("displayBatchSize", max_rows + 1)`, does `db = connect(uri).getSiblingDB(db)`, deletes
  those variables from `process.env`, evaluates the user's code through the shell's own evaluator
  (`db.getMongo()._instanceState.evaluationListener.loadExternalCode`, the path `load()` uses, so
  mongosh's async rewriter applies exactly as for `--eval`), turns the raw result into its printable
  form with the shell's `Symbol.for("@@mongosh.asPrintable")` hook (for a cursor a
  `CursorIterationResult` `{cursorHasMore, documents}`, of which the first `displayBatchSize`
  `documents` become the value) and prints **one marker-prefixed relaxed Extended JSON line**
  (`{"phase": "done", "value": ...}`, `{"phase": "error", "error": {...}}` or
  `{"phase": "connect", "error": {...}}`), which the API parses; everything else the shell wrote is
  `output`. Neither the URI nor the query text is ever on the command line (mongosh additionally
  blanks its argv in `/proc/<pid>/cmdline`).
- Why not `--json`: with mongosh 2.11.1 `--json` prints the raw value of the last `--eval`, which fails
  for cursors (`BSONError: Converting circular structure to EJSON`) and would force the user's code
  onto argv; `db` re-binding via `connect()` under `--nodb` does work. The wrapper is an async IIFE
  (`--eval` scripts may not use top-level `await`; the shell awaits a Promise result before it exits)
  and relies on two underscore-prefixed but public mongosh members; the pinned version is checked by
  the integration test whenever it is bumped.
- `result_docs` is set when the JSON result is an array of objects (cursor batch, `toArray()`,
  aggregation) so the dashboard can offer a table view; `truncated` is true when the array had more
  than `max_rows` elements (it is cut to `max_rows`). `undefined` results are `null`.
- Errors of the script (syntax, runtime, server) are in-band: `error.message` is
  `<name>: <message>` plus ` [<codeName>]` for server errors; `result` is null and `output` keeps what
  was printed before. A connection or authentication failure is `503 database_unavailable`.
- Kill the process at `timeout_seconds` → `504 query_timeout`. At most 4 concurrent shells per
  sidecar (one per slot uid); more → `429 too_many_queries`. Output is capped at 8 MiB (1 MiB stderr): the
  shell is killed and the result is an in-band `query_failed` error whose message suggests
  `.limit(20)`, a projection or fewer rows.
- The shell's stderr is appended to `output`. Output, error messages **and the result** are redacted
  with `connections.redact` (the source's password and any `scheme://user:password@` become `***`).

### AWS RDS / Aurora

A SQL database in the user's AWS account ([CLOUD.md](CLOUD.md) "C2-1") is a SQL source like any external
one: the same SQL rules, read-only session for viewers and limits apply, over TLS from this PC (whose IP the
database's firewall lets in). While AWS is still creating it the console answers `409
cloud_database_creating`. The MCP `run_query` tool reaches it the same way ([MCP.md](MCP.md)).

### DynamoDB

For a DynamoDB data source ([CLOUD.md](CLOUD.md) "C2-2") the query is **one JSON object**: `operation`
plus the AWS API's own parameters, with **plain JSON values** (numbers, strings, `{"$set": [...]}`,
`{"$base64": "..."}`) in `Key`, `Item`, `ExclusiveStartKey` and `ExpressionAttributeValues`:

```json
{"operation": "Query", "TableName": "orders",
 "KeyConditionExpression": "customer = :c AND n > :n",
 "ExpressionAttributeValues": {":c": "c1", ":n": 10}}
```

- `operation`: `Query`, `Scan`, `GetItem` (every role) or `PutItem`, `UpdateItem`, `DeleteItem`
  (developer+; a viewer gets `403 read_only_role` - the operation, not the text, decides, so this check is
  exact). Table operations, batches and transactions are not offered.
- `TableName` must be one of the source's tables. `Limit` is capped at `max_rows` (default `max_rows`).
- Runs with the AWS connection's key in the API process (no shell, no sidecar). The answer has the
  MongoDB shape below: `engine: "dynamodb"`, `result` = the response with items as plain JSON (`Items`,
  `Item`, `Attributes`, `LastEvaluatedKey`, `Count`, `ScannedCount`), `result_docs` = the items, `output`
  = a one-line summary (plus how to fetch the next page), `truncated` = more items exist (send
  `LastEvaluatedKey` as `ExclusiveStartKey`).
- Invalid JSON, an unknown operation or table, wrong parameters (botocore names them) and AWS errors
  (`ValidationException`, `ConditionalCheckFailedException`, `AccessDenied...`) are in-band `error`s
  (HTTP 200), like a MongoDB script error.

### Firestore

For a Firestore data source ([CLOUD.md](CLOUD.md) "C2-3") the query is **one JSON object**, a documented
subset of Firestore's `structuredQuery` with plain JSON values (Firestore's own types as `{"$timestamp":
"..."}`, `{"$ref": "users/u1"}`, `{"$base64": "..."}`, `{"$geo": {"latitude": .., "longitude": ..}}`):

```json
{"from": "orders",
 "where": [{"field": "status", "op": "==", "value": "open"}, {"field": "total", "op": ">", "value": 10}],
 "orderBy": [{"field": "total", "direction": "desc"}],
 "select": ["status", "total"],
 "limit": 20}
```

- `from`: a collection path (`"orders"`, a subcollection `"users/u1/orders"`) or `{"collectionId":
  "orders"}` for **every** collection named `orders` (a collection-group query; `"allDescendants": false`
  limits it to top-level ones).
- `where`: one filter `{"field", "op", "value"}`, a list of them (AND), or `{"and": [...]}` / `{"or":
  [...]}` (nestable). `op`: `==`, `!=`, `<`, `<=`, `>`, `>=`, `array-contains`, `array-contains-any`, `in`,
  `not-in` (or Firestore's names, `EQUAL`, `GREATER_THAN`...), and the unary `IS_NULL`, `IS_NAN`,
  `IS_NOT_NULL`, `IS_NOT_NAN` (no `value`). Dotted fields reach into maps (`address.city`); the document
  id is `{"field": "__name__", "op": "==", "value": {"$ref": "orders/o1"}}`.
- `orderBy`: field names or `{"field", "direction": "asc" | "desc"}`; `select`: field names; `limit`
  (capped at `max_rows`); `offset` (the next page: `offset` + `limit`). Any other key is an in-band error
  (typos are not ignored).
- `operation` (default `query`): `count` (the same query, counted), `get` (`{"operation": "get", "path":
  "users/u1"}`) - every role - and the writes, developer+ (`403 read_only_role` for viewers; the operation,
  not the text, decides): `create` (`collection`, `id?`, `data`), `update` (`path`, `data`, `unset?`: sets /
  removes top-level fields of an existing document) and `delete` (`path`).
- Runs with the Firebase connection's service account in the API process (no shell). The answer has the
  MongoDB shape below: `engine: "firestore"`, `result_docs` = the documents (`_id`, `_path`, fields),
  `result` = `{documents}` / `{count}` / `{document}` / `{deleted}`, `output` = a one-line summary,
  `truncated` = more documents match. Bad requests and Firestore's errors - a query that needs a composite
  index comes back with the Firebase console link that creates it - are in-band `error`s (HTTP 200).

### Realtime Database

For a Firebase Realtime Database ([CLOUD.md](CLOUD.md) "C2-4") the query is **one JSON object** naming a
**path** in the tree and, optionally, Firebase's REST query parameters (plain JSON values):

```json
{"path": "users", "orderBy": "age", "startAt": 18, "endAt": 65, "limitToFirst": 20}
```

- `path`: keys separated by `/` (`rooms/lobby/messages`; empty or missing = the root). Keys can't contain
  `. $ # [ ] /`.
- `get` (the default `operation`, every role): the value at `path`. `shallow: true` lists only the children's
  keys (not combinable with the rest). `orderBy`: `"$key"`, `"$value"`, `"$priority"` or a child path
  (`"age"`, `"address/city"`); with it, `startAt` / `endAt` (inclusive bounds), `equalTo` and `limitToFirst`
  / `limitToLast` (one of them; without either, `max_rows + 1` is asked for to tell when there is more).
  Ordering by a child needs `".indexOn": ["age"]` at that path in the database's rules (Firebase console ->
  Realtime Database -> Rules); without it Firebase refuses and the error says so.
- Writes, developer+ (`403 read_only_role` for viewers): `{"operation": "set", "path": "users/ann", "value":
  {...}}` replaces the value, `update` sets the children named in `value` (keys may be child paths:
  `{"address/city": "Oslo"}`) and keeps the others, `push` adds `value` under a new Firebase-made,
  time-ordered key (in `output` and `result.key`), `delete` removes the path and everything under it. Setting
  or deleting the root is refused. Query parameters only go with `get`; any other key is an in-band error.
- Runs with the Firebase connection's service account (admin: the database's security rules don't apply)
  in the API process. The answer has the MongoDB shape below: `engine: "firebase_rtdb"`, `result_docs` = the
  children in Firebase's order (null, false, true, numbers, text, objects; keys that are whole numbers
  first) as `{"_key": "ann", ...fields}` (a plain value as `{"_key", "_value"}`), `result` = `{path,
  children}` / `{path, value}` for a plain value / the write's answer, `output` = a one-line summary,
  `truncated` = more children than `max_rows`. Bad requests and Firebase's errors are in-band `error`s
  (HTTP 200).

### Device-hosted sources

Op `query` in `app/services/source_ops.py` (`OPS`, kind-agnostic): args
`{query, max_rows, timeout_seconds, read_only}`; `run_local` runs the same SQL runner / mongosh
runner with the local credentials (MongoDB code runs in the device's own `query-shell`); remote goes through
the existing `datasource.call` RPC with timeout `timeout_seconds + 15`. `read_only` is decided on the
primary from the caller's role and defaults to true on the device. Documented in `docs/DEVICES.md`.

### Audit

`query.run` with `data_source_id`, `kind`, `statements` (count of SQL statements, 1 for MongoDB,
null when the run was refused or failed before anything ran), `read_only` (bool), `duration_ms`,
`ok` (bool: no statement / script error). Never log query text or results.

## Dashboard

New project tab **Query** at `/projects/:projectId/query` (viewer+; viewers see a *read-only* badge and
their write queries are refused by the API). It has two modes, **Terminal** and **Notebook**, described in
[QUERY_EDITOR.md](QUERY_EDITOR.md); the pieces below are what they share.

- **Database selector**: every data source of the project (name, engine badge, SQL/NoSQL, "on
  <device>" badge, status dot). Selection persisted per project in `localStorage`. Switching sources
  keeps each source's editor text and history.
- **Editor**: CodeMirror 6 (`@uiw/react-codemirror`, `@codemirror/lang-sql` with the MySQL dialect for
  mariadb/mysql and PostgreSQL dialect for postgresql, `@codemirror/lang-javascript` for MongoDB), light
  and dark themes following the app, line numbers, bracket matching. Placeholder examples per engine.
  SQL autocompletion from the schema (`GET /projects/{id}/schema?source_id=`: tables + columns);
  MongoDB: collection names.
- **Toolbar**: Run (Ctrl/Cmd+Enter, runs the selection if there is one, else everything), max rows
  (100 / 500 / 2000), timeout (10 s / 30 s / 120 s), History (per source, last 50 queries with time
  and duration, click to load), Clear results, and a *read-only* badge for viewers.
- **Results**: one card per SQL statement: grid for `rows` (sticky header, monospace cells,
  long values truncated with click-to-expand, `N rows` + `truncated at M` notice + duration),
  `N rows affected` for `count`, `OK` for `empty`, an error card for `error`. **Export CSV / JSON**
  per rows result. MongoDB: console-style output (`output` lines) then the result as a collapsible JSON
  tree (pretty-printed relaxed EJSON), with a **Table** toggle when `result_docs` is present (flat
  columns = union of top-level keys).
- **Entity sidebar** for the selected source: tables/collections with row counts (from the schema
  endpoint); click inserts a starter query at the cursor (`SELECT * FROM \`t\` LIMIT 100;` /
  `db.getCollection("c").find({}).limit(20)`).
- States: no data sources (link to Databases tab), source offline (`device_offline` banner), loading,
  errors as toasts + inline. Works at phone width (editor above results, sidebar collapses).
- Tests (vitest): history store, CSV export, statement/result helpers, viewer read-only detection
  used for the badge.
