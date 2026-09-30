# Query Notebook, Saved Queries & Query Log

Extends the Query Console ([QUERY_CONSOLE.md](QUERY_CONSOLE.md)) with a **Notebook** mode next to the
**Terminal** mode, for both SQL and NoSQL data sources, with **saved queries** (snippets, versioned) and
a **server-side query log** of every command run through the console (both modes).

## Data model (migration `0003_query_editor`)

| Table | Columns |
|---|---|
| `query_runs` | `id`, `project_id` (FK cascade), `data_source_id` (String(36), no FK: keep after source deletion), `source_name`, `kind` (`sql`/`nosql`), `engine`, `user_id` (String(36)), `user_email` (snapshot), `query_text` (Text, the first 20 000 chars as sent, with password literals such as `IDENTIFIED BY '…'`, `PASSWORD '…'`, Mongo `pwd: "…"` masked to `'***'`; requests allow 200 000), `status` (`ok`/`error`/`timeout`/`refused`), `statements` (int), `rows` (int, rows returned or documents), `affected_rows` (int, nullable), `duration_ms` (int), `error_message` (Text, nullable, redacted), `read_only` (bool), `layout` (`terminal`/`editor`/`api`), `created_at` (indexed) |
| `saved_queries` | `id`, `project_id` (FK cascade), `data_source_id` (nullable, SET NULL), `owner_id` (FK users), `name` (120), `folder` (120, nullable), `query_text` (Text), `kind` (`sql`/`nosql`/`any`), `version` (int, current version number; migration `0004`), `created_at`, `updated_at` (indexed by project) |
| `saved_query_versions` (migration `0004_saved_query_versions`) | `id`, `saved_query_id` (FK cascade), `version` (int, unique per saved query, indexed), `query_text` (Text), `author_id` (String(36), snapshot), `author_email` (snapshot), `message` (200, nullable), `created_at`. Append-only; `0004` backfills one version-1 row per existing saved query (author = owner, message "Imported from before version history"). |

Retention: the worker prunes `query_runs` older than **90 days** and keeps at most **10 000 rows per
project** (oldest first) — daily scheduler task `query_log.prune`. Logging a run also trims its project
back to 10 000 once it is 500 over, so a busy key can't grow the log for a day.

## API

All under `/v1/projects/{project_id}`.

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| POST | `/data-sources/{sid}/query` | viewer+ (API keys: service only) | as before, plus optional `layout: "terminal" \| "editor"` | as before, plus `run_id` (the log row id). **Every** call is logged — success, error, timeout and viewer refusals (`status: refused`, HTTP 403 still returned). |
| GET | `/query-log?source_id=&user=me\|all&limit=50&before=<created_at>&before_id=<id>` | viewer+ (`user=all` needs admin+) | – | `{runs: QueryRun[], has_more}` newest first; `query_text` truncated to 2 000 chars in list responses. Next page: pass the last row's `created_at` and `id` (keyset on both, so same-second runs are not skipped); `before` alone is a plain `created_at <` cutoff |
| GET | `/query-log/{run_id}` | own run: viewer+; others: admin+ | – | `QueryRun` (full text) |
| DELETE | `/query-log?before=<iso>` | owner | – | `{deleted: n}` |
| GET | `/saved-queries` | viewer+ | – | `SavedQuery[]` without `query_text` (all of the project, folder-sorted; the dashboard polls it every 30 s) |
| GET | `/saved-queries/{id}` | viewer+ | – | `SavedQuery` incl. `query_text` (fetched when a snippet is opened, diffed or reloaded) |
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

## Dashboard — Query tab modes

The Query tab has two layouts, switched by the **Terminal / Notebook** toggle in its toolbar or under
Account settings → *Query console* (per browser; default Terminal; the Notebook mode's stored value is
`"editor"`, which is also the `layout` its runs log). Both share the source selector, rows and timeout
selects, the viewer *read-only* badge and the result renderers from [QUERY_CONSOLE.md](QUERY_CONSOLE.md).

### Terminal

A shell-style transcript with the prompt pinned at the bottom (`main-sql›`), like the mysql and mongosh
clients. Enter runs once the SQL ends with `;` or the MongoDB code has balanced brackets (Shift+Enter
adds a newline, Ctrl/Cmd+Enter always runs); ↑/↓ browse this browser's history for the source (last
50, `localStorage`); built-ins `\use <name>`, `\list`, `\rows <n>`, `\timeout <s>`, `\clear`, `\help`;
a Tables/Collections panel; **Copy transcript**. Runs send `layout: "terminal"`.

### Notebook

One scrolling document per tab: a *cell* per command with its output (result grid, Mongo output,
errors) directly below it, then the next cell.

- **Cells**: run (Ctrl/Cmd+Enter; Shift+Enter runs and moves to the next cell, adding one at the end),
  cancel, move up/down, add below, delete (confirmed when it has text), collapse the output. **Run
  all** runs top to bottom and stops at the first failure. Outputs stay in memory only.
- **Tabs**: one per open document (`Untitled N` or a snippet name), unsaved dot, close (confirmed when
  dirty), New tab. Tabs, their cells and each tab's data source persist per project in `localStorage`
  (`deployer.notebook.<project>`, text only).
- **Saving** (developer+): Save (Ctrl/Cmd+S; name/folder dialog the first time, `folder/name` sets the
  folder) and Save as…, with an optional "What changed?" message. A document is stored as
  `query_text = {"cells":[{id,text}]}`; a plain-text snippet opens as one cell.
- **Collaboration** (Phase 2 above): the snippet list is polled every 30 s; a clean tab follows a
  teammate's newer version silently, a dirty one shows a banner (view diff / reload theirs / keep
  editing). A save or restore that loses the race (`409 version_conflict`) opens a diff with *Reload
  theirs* or *Keep mine* (saves on top as the next version). No silent overwrites.
- **Sidebar** (260 px, collapsible; a drawer below desktop width): **Snippets** grouped by folder
  with search, rename/delete row menu and New query; **Versions** of the active tab's snippet (author,
  message, time, diff against the tab, restore as a new version); **History** of this user's runs on
  the selected source from `/query-log?user=me` (admins: *Show everyone's*; owners: *Clear query
  history*, which deletes the whole project's log), click inserts the text as a new cell; **Schema**
  tree, click inserts a starter query into the active cell.

## Tests

- API: model/migration, logging of ok/error/timeout/refused runs (incl. text preserved, redaction),
  list/get permissions (own vs all), delete, saved-query CRUD + permissions, prune job, export
  includes saved queries. Versions (`tests/test_saved_query_versions.py`): create makes v1, text
  patch bumps with author/message, metadata patch keeps the version, stale/missing `version`
  (409/422), two developers editing the same snippet, viewer 403, restore (new version, 409 when
  stale, 404 unknown), list order and `chars`, delete cascades, export/import carry versions,
  migration `0004` backfill on a scratch SQLite database.
- Dashboard: `notebook.test.ts` (document ⇄ `query_text`, cells, tabs, versions, `folder/name`
  parsing, history rows, persistence), `NotebookConsole.test.tsx` (cell output), `terminal.test.ts`
  (prompt, commands, Enter rule, ↑/↓ history, shell-style output), `diff.test.ts`.
