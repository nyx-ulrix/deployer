import { useMemo, useState } from "react";
import { Braces, ListTree, Table2, Terminal } from "lucide-react";
import type { MongoQueryResponse } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { CopyButton } from "../../components/ui/CopyField";
import { Alert, EmptyState } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { formatNumber } from "../../lib/format";
import { pretty } from "../data/json";
import { JsonTree } from "./JsonTree";
import { ExportMenu, ResultsGrid } from "./ResultsGrid";
import { docsToTable, outputLines } from "./results";

type View = "tree" | "table" | "raw";

/** Console output, then the result as a JSON tree / table (when it is a cursor batch) / raw text. */
export function MongoResults({ response, maxRows }: { response: MongoQueryResponse; maxRows: number }) {
  const [view, setView] = useState<View>("tree");
  const lines = outputLines(response.output);
  const docs = response.result_docs;
  const table = useMemo(() => (docs && docs.length > 0 ? docsToTable(docs) : null), [docs]);
  const shownView: View = view === "table" && !table ? "tree" : view;

  return (
    <div className="space-y-3">
      {response.error && (
        <Alert tone="danger" title={response.error.code === "query_failed" ? "Script failed" : response.error.code}>
          <span className="font-mono text-xs whitespace-pre-wrap">{response.error.message}</span>
        </Alert>
      )}

      {lines.length > 0 && (
        <section className="overflow-hidden rounded-xl border border-border bg-surface shadow-xs" aria-label="Console output">
          <header className="flex items-center gap-2 border-b border-border px-3 py-1.5">
            <Terminal className="size-3.5 text-muted" />
            <span className="text-xs font-medium">Console</span>
            <span className="text-xs text-muted tabular-nums">
              {lines.length} {lines.length === 1 ? "line" : "lines"}
            </span>
            <CopyButton value={lines.join("\n")} label="Copy output" className="ml-auto size-7" />
          </header>
          <pre className="max-h-64 overflow-auto px-3 py-2 font-mono text-xs leading-5 break-words whitespace-pre-wrap">
            {lines.join("\n")}
          </pre>
        </section>
      )}

      {response.result !== null ? (
        <section className="overflow-hidden rounded-xl border border-border bg-surface shadow-xs" aria-label="Result">
          <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-1.5">
            <span className="text-xs font-medium">Result</span>
            {docs && (
              <span className="text-xs text-muted tabular-nums">
                {formatNumber(docs.length)} {docs.length === 1 ? "document" : "documents"}
              </span>
            )}
            {response.truncated && (
              <Badge tone="warning" title={`Only the first ${formatNumber(maxRows)} documents were printed.`}>
                truncated at {formatNumber(maxRows)}
              </Badge>
            )}
            <div className="ml-auto flex flex-wrap items-center gap-1">
              <ViewToggle value={shownView} onChange={setView} hasTable={table !== null} />
              {shownView === "table" && table && <ExportMenu columns={table.columns} rows={table.rows} base="documents" />}
              <CopyButton value={pretty(response.result)} label="Copy JSON" className="size-7" />
            </div>
          </header>
          {shownView === "tree" && (
            <div className="max-h-[32rem] overflow-auto px-3 py-2">
              <JsonTree value={response.result} />
            </div>
          )}
          {shownView === "table" && table && <ResultsGrid columns={table.columns} rows={table.rows} label="Documents" />}
          {shownView === "raw" && (
            <pre className="max-h-[32rem] overflow-auto px-3 py-2 font-mono text-xs leading-5">{pretty(response.result)}</pre>
          )}
        </section>
      ) : (
        !response.error &&
        lines.length === 0 && (
          <EmptyState title="Nothing returned" description="The script printed nothing and its last expression had no value." />
        )
      )}
    </div>
  );
}

function ViewToggle({ value, onChange, hasTable }: { value: View; onChange: (v: View) => void; hasTable: boolean }) {
  const items: { value: View; label: string; icon: typeof ListTree }[] = [
    { value: "tree", label: "Tree", icon: ListTree },
    ...(hasTable ? [{ value: "table" as const, label: "Table", icon: Table2 }] : []),
    { value: "raw", label: "Raw", icon: Braces },
  ];
  return (
    <div role="group" aria-label="Result view" className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {items.map((item) => {
        const Icon = item.icon;
        const active = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(item.value)}
            className={cn(
              "inline-flex h-6 items-center gap-1 rounded-md px-2 text-xs transition-colors",
              active ? "bg-surface font-medium text-fg shadow-xs" : "text-muted hover:text-fg",
            )}
          >
            <Icon className="size-3" />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
