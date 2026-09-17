# Query Console

A code editor + results terminal in the dashboard (project tab **Query**) to run SQL against a
project's SQL data sources and MongoDB shell code against its NoSQL data sources. The user picks the
database from a selector; everything runs through the control plane with the project's roles.

## API

`POST /v1/projects/{project_id}/data-sources/{sid}/query`

| Field | Type | Notes |
|---|---|---|
| `query` | string (1..200 000 chars) | SQL text (several statements allowed) or MongoDB shell code |
| `max_rows` | int 1..5000, default 500 | rows returned per result set / documents printed |
| `timeout_seconds` | int 1..120, default 30 | per statement (SQL) or for the whole script (MongoDB) |

Roles: **developer+** can run anything. **viewer** may run only read-only queries, otherwise
`403 read_only_role`. The classification is textual and best effort (the source's database user is
the real boundary; use an external source with a read-only user for strict enforcement):
- SQL: every statement must start with `SELECT`, `WITH`, `SHOW`, `EXPLAIN`, `DESCRIBE`, `DESC`,
  `TABLE`, `VALUES` (after stripping comments, leading parentheses entered; checked with `sqlparse`)
  and, except for `SHOW ...`, must not contain a writing keyword anywhere outside strings and
  comments (`INSERT`, `UPDATE`, `DELETE`, `REPLACE`, `MERGE`, `INTO`, `CREATE`, `ALTER`, `DROP`,
  `TRUNCATE`, `GRANT`, `LOCK`, `SET`, `CALL`, `LOAD`, `COPY`, `OUTFILE`, transaction control, ...).
  This also stops PostgreSQL data-modifying CTEs (`WITH d AS (DELETE ...) SELECT`),
  `SELECT ... FOR UPDATE` and `SELECT ... INTO OUTFILE`.
- MongoDB: the code must not contain any of these names as a whole identifier, anywhere (strings and
  comments included - over-matching is the safe direction): `insert`, `insertOne`, `insertMany`,
  `update`, `updateOne`, `updateMany`, `replaceOne`, `delete`, `deleteOne`, `deleteMany`, `remove`,
  `save`, `drop`, `dropDatabase`, `dropIndex`, `dropIndexes`, `createCollection`, `createIndex`,
  `createIndexes`, `createView`, `renameCollection`, `convertToCapped`, `reIndex`, `bulkWrite`,
  `findOneAndUpdate`, `findOneAndReplace`, `findOneAndDelete`, `findAndModify`, `mapReduce`, `$out`,
  `$merge`, `runCommand`, `adminCommand`, `createUser`, `updateUser`, `dropUser`, `createRole`,
  `getSiblingDB`, `getMongo`, `load`, `require`, `process`, `fs`, `child_process`, `eval`,
  `Function`, `constructor`, `globalThis`, `Reflect`, `import`.
  Regardless of role the script always starts against the source's own database only (`db` is bound
  to it by the wrapper) with the source's own credentials, never root.

Errors: `404 not_found`, `403 forbidden` / `read_only_role`, `422 validation_error` (also for a SQL
script without any statement), `503 device_offline`, `503 database_unavailable` (cannot connect /
authenticate), `504 query_timeout` (MongoDB script killed), `501 mongosh_unavailable`,
`429 too_many_queries` (MongoDB, more than 4 shells at once). Query errors are **not** HTTP errors:
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
- Timeouts, best effort per engine, set on the connection before the script: MariaDB
  `SET SESSION max_statement_time`, MySQL `SET SESSION max_execution_time` (ms, SELECT only),
  PostgreSQL `SET statement_timeout`. A statement stopped by the engine is reported as a per-statement
  error with `code: "query_timeout"` (MariaDB 1969, MySQL 3024, PostgreSQL 57014); the following
  statements do not run. Engines without such a setting run the statement to the end.
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
`downloads.mongodb.com`, SHA-256 verified in `api/Dockerfile`, amd64 only; report
`501 mongosh_unavailable` when the binary is missing, e.g. on other architectures).
`/etc/mongosh.conf` turns telemetry, update checks and log files off. Execution, as verified against
the real binary (`tests/integration/test_query_console.py`):

- `mongosh --nodb --quiet --norc --eval <wrapper>` with a private temporary directory as `HOME`
  (mongosh's own config/history land there and are deleted with it). The wrapper
  (`query_console.WRAPPER_JS`) is a fixed script without secrets or user code; everything variable
  comes from the child's environment - `DEPLOYER_QUERY_URI` (the source's own URI, with connect /
  server-selection timeouts of 5 s added unless the URI sets them), `DEPLOYER_QUERY_DB`,
  `DEPLOYER_QUERY_FILE` (the user's code, written to a 0600 file in that directory),
  `DEPLOYER_QUERY_MARKER`, `DEPLOYER_QUERY_BATCH` (`max_rows + 1`). Nothing else of the API's
  environment is passed (a script can read `process.env`). The wrapper sets
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
- Kill the process at `timeout_seconds` → `504 query_timeout`. At most 4 concurrent shells per API
  process (semaphore); more → `429 too_many_queries`. Output is capped at 8 MiB (1 MiB stderr): the
  shell is killed and the result is an in-band `query_failed` error.
- The shell's stderr is appended to `output`. Output, error messages **and the result** are redacted
  with `connections.redact` (the source's password and any `scheme://user:password@` become `***`).

### Device-hosted sources

Op `query` in `app/services/source_ops.py` (`OPS`, kind-agnostic): args
`{query, max_rows, timeout_seconds, read_only}`; `run_local` runs the same SQL runner / mongosh
runner with the local credentials (the device's API image contains mongosh too); remote goes through
the existing `datasource.call` RPC with timeout `timeout_seconds + 15`. `read_only` is decided on the
primary from the caller's role and defaults to true on the device. Documented in `docs/DEVICES.md`.

### Audit

`query.run` with `data_source_id`, `kind`, `statements` (count of SQL statements, 1 for MongoDB,
null when the run was refused or failed before anything ran), `read_only` (bool), `duration_ms`,
`ok` (bool: no statement / script error). Never log query text or results.

## Dashboard

New project tab **Query** at `/projects/:projectId/query` (viewer+; viewers see a *read-only* badge and
their write queries are refused by the API).

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

## Docs & repo

- `docs/API.md`: add the console to the feature table.
- `docs/DEVICES.md`: op `query`.
- `README.md`: feature bullet "Query console: SQL and MongoDB shell in the browser, per database".
- `api/Dockerfile`: `mongosh` (pinned, SHA256 verified).
