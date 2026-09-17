import { useMemo, useState, type ReactNode } from "react";
import { FileJson, FileSpreadsheet } from "lucide-react";
import type { MongoQueryResponse, SqlStatementResult } from "../../api/types";
import { CopyButton } from "../../components/ui/CopyField";
import { Spinner } from "../../components/ui/Spinner";
import { cn } from "../../lib/cn";
import { pretty } from "../data/json";
import { exportCsv, exportJson, type ExportTable } from "./csv";
import type { QueryPrefs } from "./prefs";
import { ResultsGrid } from "./ResultsGrid";
import { docsToTable, outputLines, statementLabel } from "./results";
import {
  helpText,
  mongoFooter,
  mongoText,
  sqlStatementFooter,
  sqlStatementText,
  type ConsoleEntry,
  type EchoInput,
  type RunEntry,
} from "./terminal";

/** The shell transcript: prompt echoes followed by their output blocks. */
export function Transcript({ entries, prefs }: { entries: ConsoleEntry[]; prefs: QueryPrefs }) {
  return (
    <div className="space-y-3">
      {entries.map((e) => (
        <EntryView key={e.id} entry={e} prefs={prefs} />
      ))}
    </div>
  );
}

function Echo({ input }: { input?: EchoInput }) {
  if (!input) return null;
  return (
    <div className="flex gap-2">
      <span className="shrink-0 font-semibold text-accent select-none">{input.prompt}</span>
      <pre className="min-w-0 flex-1 break-words whitespace-pre-wrap">{input.text}</pre>
    </div>
  );
}

function EntryView({ entry, prefs }: { entry: ConsoleEntry; prefs: QueryPrefs }) {
  if (entry.kind === "help") {
    return (
      <div>
        <Echo input={entry.input} />
        <pre className="break-words whitespace-pre-wrap text-muted">{helpText(prefs)}</pre>
      </div>
    );
  }
  if (entry.kind === "message") {
    return (
      <div>
        <Echo input={entry.input} />
        <pre className={cn("break-words whitespace-pre-wrap", entry.tone === "error" ? "text-danger" : "text-muted")}>{entry.text}</pre>
      </div>
    );
  }
  return <RunView entry={entry} prefs={prefs} />;
}

function RunView({ entry, prefs }: { entry: RunEntry; prefs: QueryPrefs }) {
  const { run } = entry;
  const maxRows = run.request.max_rows ?? prefs.maxRows;
  const response = run.status === "done" ? run.response : null;
  const sqlResults = response?.kind === "sql" ? response.results : null;
  const mongo = response?.kind === "nosql" ? response : null;
  return (
    <div className="space-y-1">
      <Echo input={{ prompt: entry.prompt, text: entry.query }} />
      {run.status === "running" && (
        <p className="flex items-center gap-2 text-muted">
          <Spinner className="size-3.5" /> running…
        </p>
      )}
      {run.status === "failed" && (
        <Block text={`ERROR: ${run.failure.message}`}>
          <pre className="break-words whitespace-pre-wrap text-danger">ERROR: {run.failure.message}</pre>
        </Block>
      )}
      {sqlResults?.map((r, i) => <SqlBlock key={i} result={r} index={i} many={sqlResults.length > 1} maxRows={maxRows} />)}
      {mongo && <MongoBlock response={mongo} maxRows={maxRows} />}
    </div>
  );
}

/** One output block with its hover menu: Copy, and Export CSV / JSON when it is a table. */
function Block({ text, table, children }: { text: string; table?: ExportTable; children: ReactNode }) {
  return (
    <div className="group relative">
      {children}
      <div
        className={cn(
          "absolute -top-1 right-0 flex items-center gap-0.5 rounded-md border border-border bg-surface p-0.5 shadow-sm",
          "opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100",
        )}
      >
        <CopyButton value={text} label="Copy output" className="size-6" />
        {table && (
          <>
            <button
              type="button"
              onClick={() => exportCsv(table)}
              title="Export CSV"
              aria-label="Export CSV"
              className="inline-flex size-6 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg"
            >
              <FileSpreadsheet className="size-3.5" />
            </button>
            <button
              type="button"
              onClick={() => exportJson(table)}
              title="Export JSON"
              aria-label="Export JSON"
              className="inline-flex size-6 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg"
            >
              <FileJson className="size-3.5" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function SqlBlock({ result, index, many, maxRows }: { result: SqlStatementResult; index: number; many: boolean; maxRows: number }) {
  const table: ExportTable | undefined =
    result.type === "rows" && result.rows.length > 0
      ? { columns: result.columns, rows: result.rows, base: result.statement, index }
      : undefined;
  const truncated = result.type === "rows" && result.truncated;
  const footer = truncated ? sqlStatementFooter({ ...result, truncated: false }, maxRows) : sqlStatementFooter(result, maxRows);
  return (
    <Block text={sqlStatementText(result, maxRows)} table={table}>
      {many && <p className="text-muted">-- #{index + 1} {statementLabel(result.statement, 60)}</p>}
      {table && <ResultsGrid variant="terminal" columns={table.columns} rows={table.rows} label={`Rows of statement ${index + 1}`} />}
      <p className={cn("break-words whitespace-pre-wrap", result.type === "error" ? "text-danger" : "text-muted")}>
        {footer}
        {truncated && <span className="text-warning"> · truncated at {maxRows.toLocaleString()} rows</span>}
      </p>
    </Block>
  );
}

function MongoBlock({ response, maxRows }: { response: MongoQueryResponse; maxRows: number }) {
  const [asTable, setAsTable] = useState(false);
  const lines = outputLines(response.output);
  const docs = response.result_docs;
  const table = useMemo(() => (docs && docs.length > 0 ? docsToTable(docs) : null), [docs]);
  const footer = mongoFooter(response, maxRows);
  const showTable = asTable && table !== null;
  return (
    <Block
      text={mongoText(response, maxRows, showTable)}
      table={table ? { columns: table.columns, rows: table.rows, base: "documents" } : undefined}
    >
      {lines.length > 0 && <pre className="break-words whitespace-pre-wrap">{lines.join("\n")}</pre>}
      {response.error && <pre className="break-words whitespace-pre-wrap text-danger">ERROR: {response.error.message}</pre>}
      {response.result !== null &&
        (showTable && table ? (
          <ResultsGrid variant="terminal" columns={table.columns} rows={table.rows} label="Documents" />
        ) : (
          <pre className="break-words whitespace-pre-wrap text-fg/90">{pretty(response.result)}</pre>
        ))}
      <p className="flex flex-wrap items-center gap-2 text-muted">
        {table && (
          <span role="group" aria-label="Result view" className="inline-flex rounded border border-border bg-surface-2 p-0.5 text-[11px]">
            {(["json", "table"] as const).map((v) => {
              const active = v === "table" ? showTable : !showTable;
              return (
                <button
                  key={v}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setAsTable(v === "table")}
                  className={cn("rounded px-1.5 leading-4", active ? "bg-surface text-fg" : "text-muted hover:text-fg")}
                >
                  {v === "json" ? "JSON" : "Table"}
                </button>
              );
            })}
          </span>
        )}
        {footer && <span className={cn(response.truncated && "text-warning")}>{footer}</span>}
      </p>
    </Block>
  );
}
