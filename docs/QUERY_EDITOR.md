# Query Editor (Supabase-style) & Query Log

Extends the Query Console ([QUERY_CONSOLE.md](QUERY_CONSOLE.md)). The **Editor** layout becomes a
Supabase-style SQL editor that works for both SQL and NoSQL data sources, with **saved queries**
(snippets) and a **server-side query log** of every command run through the console (both layouts).

## Data model (migration `0003_query_editor`)

| Table | Columns |
|---|---|
| `query_runs` | `id`, `project_id` (FK cascade), `data_source_id` (String(36), no FK: keep after source deletion), `source_name`, `kind` (`sql`/`nosql`), `engine`, `user_id` (String(36)), `user_email` (snapshot), `query_text` (Text, full text as sent, max 200 000 chars), `status` (`ok`/`error`/`timeout`/`refused`), `statements` (int), `rows` (int, rows returned or documents), `affected_rows` (int, nullable), `duration_ms` (int), `error_message` (Text, nullable, redacted), `read_only` (bool), `layout` (`terminal`/`editor`/`api`), `created_at` (indexed) |
| `saved_queries` | `id`, `project_id` (FK cascade), `data_source_id` (nullable, SET NULL), `owner_id` (FK users), `name` (120), `folder` (120, nullable), `query_text` (Text), `kind` (`sql`/`nosql`/`any`), `version` (int, current version number; migration `0004`), `created_at`, `updated_at` (indexed by project) |
| `saved_query_versions` (migration `0004_saved_query_versions`) | `id`, `saved_query_id` (FK cascade), `version` (int, unique per saved query, indexed), `query_text` (Text), `author_id` (String(36), snapshot), `author_email` (snapshot), `message` (200, nullable), `created_at`. Append-only; `0004` backfills one version-1 row per existing saved query (author = owner, message "Imported from before version history"). |

Retention: the worker prunes `query_runs` older than **90 days** and keeps at most **10 000 rows per
project** (oldest first) — daily scheduler task `query_log.prune`.

## API

All under `/v1/projects/{project_id}`.

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| POST | `/data-sources/{sid}/query` | viewer+ | as before, plus optional `layout: "terminal" \| "editor"` | as before, plus `run_id` (the log row id). **Every** call is logged — success, error, timeout and viewer refusals (`status: refused`, HTTP 403 still returned). |
| GET | `/query-log?source_id=&user=me\|all&limit=50&before=<created_at>` | viewer+ (`user=all` needs admin+) | – | `{runs: QueryRun[], has_more}` newest first; `query_text` truncated to 2 000 chars in list responses |
| GET | `/query-log/{run_id}` | own run: viewer+; others: admin+ | – | `QueryRun` (full text) |
| DELETE | `/query-log?before=<iso>` | owner | – | `{deleted: n}` |
| GET | `/saved-queries` | viewer+ | – | `SavedQuery[]` (all of the project, folder-sorted) |
| POST | `/saved-queries` | developer+ | `{name, folder?, query_text, data_source_id?, kind}` | `SavedQuery` |
| PATCH | `/saved-queries/{id}` | developer+ | partial, **`version` required** (see Phase 2) | `SavedQuery` |
| DELETE | `/saved-queries/{id}` | owner of the snippet or admin+ | – | `{ok:true}` |

```ts
type QueryRun = { id: string; project_id: string; data_source_id: string; source_name: string; kind: "sql"|"nosql"; engine: string;
  user_id: string; user_email: string; query_text: string; query_truncated?: true;  // only in list responses, when cut at 2 000 chars
  status: "ok"|"error"|"timeout"|"refused";
  statements: number; rows: number; affected_rows: number|null; duration_ms: number; error_message: string|null;
  read_only: boolean; layout: "terminal"|"editor"|"api"; created_at: string };
type SavedQuery = { id: string; project_id: string; data_source_id: string|null; owner_id: string; owner_email: string;
  name: string; folder: string|null; query_text: string; kind: "sql"|"nosql"|"any";
  version: number; updated_by_email: string;  // author of the latest version row
  created_at: string; updated_at: string };
type VersionSummary = { id: string; version: number; author_id: string; author_email: string; message: string|null;
  created_at: string; chars: number };            // no text
type Version = VersionSummary & { query_text: string };
```

### Phase 2 — versions (strict version control, no silent overwrites)

Every text change appends a `saved_query_versions` row and bumps `saved_queries.version`; history is
append-only (old rows are never rewritten). Any project member who can edit (developer+) edits any
snippet; viewers are read-only. All under `/v1/projects/{project_id}`.

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| POST | `/saved-queries` | developer+ | as above, plus `message?` (<=200) | `SavedQuery` with `version: 1` and a version-1 row |
| PATCH | `/saved-queries/{id}` | developer+ | partial `{name?, folder?, query_text?, data_source_id?, kind?, message?, version}` — `version` (the client's current one) is required (422 without it) | `SavedQuery`. `version` must equal the row's version, else **409** `version_conflict` ("Someone saved a newer version") with `details.current` = the current `SavedQuery` incl. full `query_text`, so the client can diff and merge. A changed `query_text` bumps `version` and appends a version row (author = caller, `message`); metadata-only patches need the matching `version` too but neither bump it nor add a row. |
| GET | `/saved-queries/{id}/versions` | viewer+ | – | `{versions: VersionSummary[]}` newest first |
| GET | `/saved-queries/{id}/versions/{n}` | viewer+ | – | `Version` (404 for an unknown number) |
| POST | `/saved-queries/{id}/restore` | developer+ | `{version: n, current_version, message?}` | `SavedQuery`: appends a **new** version whose text is version `n`'s (default message "Restored version n"); 409 `version_conflict` as above when `current_version` is stale, 404 for an unknown `n` |

Export/import: `saved_query_versions` travel with instance exports and project exports as a
`saved_query_versions` list; project import remaps them through the saved-query id map (fresh ids),
instance import restores them as-is (only for saved queries that made it).

Audit stays as before (counts only); the query log is the record of the commands themselves. Export
(`/projects/export`, instance export) includes `saved_queries` and `saved_query_versions`; `query_runs` are not exported.

## Dashboard — Editor layout (Supabase-style)

Three-pane layout under the Query tab when the mode is **Editor**:

- **Left sidebar** (collapsible, 260 px): search box; **Snippets** grouped by folder (create folder by
  typing `folder/name` when saving; rename, move, delete via a row menu; "New query" button); below
  it **History**: this user's recent runs for the selected source (from `/query-log?user=me`), each
  showing the first line, status dot, duration and relative time; click loads it into a new tab.
  Admins get a "Show everyone's" toggle. Below history: **Schema** tree (tables/collections → columns)
  with click-to-insert, from the existing schema endpoint.
- **Tabs** across the top of the editor: one per open snippet or untitled query (`Untitled 1`, …),
  unsaved dot, close button, middle-click close; tabs and their contents persist per project in
  `localStorage`. Each tab remembers its data source.
- **Toolbar**: data source selector (SQL/NoSQL badges, device badge, status), **Run** (Ctrl/Cmd+Enter;
  runs the selection when one exists, with the "Run selection" hint), Save (Ctrl/Cmd+S → name/folder
  dialog on first save), rows and timeout selects, Format (SQL only, client-side using the existing
  formatter if present, otherwise skip), read-only badge for viewers, layout switch to Terminal.
- **Editor**: CodeMirror with the existing highlighting/completion; larger, resizable split with the
  results pane (drag handle; persisted).
- **Results pane** with tabs **Results** / **Messages** / **Log**:
  - *Results*: one section per statement (collapsible headers `1 · SELECT … · 12 rows · 8 ms`);
    grid with sticky header, column type hints, client-side pagination (100 per page), column
    resize, cell click to expand, copy cell/row; for MongoDB the document batch as a grid (union of
    top-level keys, nested values shown as JSON) with a JSON toggle; Export CSV/JSON; "truncated at N"
    notice with a button to rerun with a larger limit.
  - *Messages*: status lines like Supabase (`Success. 3 rows returned in 8 ms`, `Query OK, 2 rows
    affected`, shell `output`, errors in red with the failing statement highlighted in the editor).
  - *Log*: the project's query log (`/query-log`), filterable by source/status/user (admin+), with
    "Load into editor" and a details drawer (full text, error).
- Phone width: sidebar becomes a drawer, results stack under the editor.

The Terminal layout is unchanged except that it also sends `layout: "terminal"` and its `\history`
now reads from the server log for the selected source.

## Tests

- API: model/migration, logging of ok/error/timeout/refused runs (incl. text preserved, redaction),
  list/get permissions (own vs all), delete, saved-query CRUD + permissions, prune job, export
  includes saved queries. Versions (`tests/test_saved_query_versions.py`): create makes v1, text
  patch bumps with author/message, metadata patch keeps the version, stale/missing `version`
  (409/422), two developers editing the same snippet, viewer 403, restore (new version, 409 when
  stale, 404 unknown), list order and `chars`, delete cascades, export/import carry versions,
  migration `0004` backfill on a scratch SQLite database.
- Dashboard: tabs store, snippet folder parsing (`folder/name`), pagination helper, message
  formatting, history mapping; typecheck/lint/test/build green.

## Revised direction (2026-09-18, user)

Build order after the weekly reset, in this priority:

1. **Notebook-style editor for SQL and NoSQL** ("like the MariaDB client in a terminal"): each
   command and its output are stacked vertically in one scrolling document — a *cell* per command
   with the result grid / shell output directly below it, then the next command below that. Cells can
   be re-run, edited and deleted; the whole document is a saved query file. **Tabs** let the user
   switch between open files. This replaces the split editor/results layout above; the Terminal
   layout stays as the second mode. Everything else in this spec (saved queries, folders, sidebar,
   history, schema tree, server-side log of every command, results pane features) applies per cell.
2. **Collaboration with strict version control** on those files: project members open the same
   files from the same Deployer; every save creates a `saved_query_versions` row
   (`id, saved_query_id, version, query_text, author_id, author_email, message, created_at`);
   `PATCH /saved-queries/{id}` requires the client's `version` and answers `409 version_conflict`
   with the current version when someone else saved first (the UI shows a diff and lets the user
   merge/reload); version list, diff between versions, restore-as-new-version, and who-changed-what
   in the sidebar; edits limited by project roles (viewer read-only). No silent overwrites, ever.
3. **Deploy pipeline ("Vercel functions")** — only after the user's explicit go-ahead once 1 and 2
   are done (phase 4 in ARCHITECTURE.md).
