import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { FileJson, RefreshCw, Search, Table2, X } from "lucide-react";
import type { DataSource, SourceSchema } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { formatNumber } from "../../lib/format";

/** Tables/collections of the selected source with row counts; a click inserts a starter query. */
export function EntitySidebar({
  source,
  schema,
  onInsert,
  onClose,
  className,
}: {
  source: DataSource;
  schema: UseQueryResult<SourceSchema | null>;
  onInsert: (entityName: string) => void;
  /** Shows a close button when given (the sidebar can be hidden); omit inside a drawer. */
  onClose?: () => void;
  className?: string;
}) {
  const [filter, setFilter] = useState("");
  const isSql = source.kind === "sql";
  const noun = isSql ? "tables" : "collections";
  const entities = schema.data?.entities ?? [];
  const q = filter.trim().toLowerCase();
  const shown = q ? entities.filter((e) => e.name.toLowerCase().includes(q)) : entities;

  return (
    <aside
      className={cn("flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-xs", className)}
      aria-label={isSql ? "Tables" : "Collections"}
    >
      <div className="flex items-center gap-1.5 border-b border-border py-1.5 pr-1 pl-3">
        {isSql ? <Table2 className="size-3.5 text-sql" /> : <FileJson className="size-3.5 text-nosql" />}
        <span className="text-xs font-semibold tracking-wide text-muted uppercase">{noun}</span>
        {schema.data && <span className="text-xs text-muted tabular-nums">{entities.length}</span>}
        <div className="ml-auto flex items-center">
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`Refresh ${noun}`}
            title="Refresh"
            onClick={() => void schema.refetch()}
          >
            <RefreshCw className={cn("size-3.5", schema.isFetching && "animate-spin")} />
          </Button>
          {onClose && (
            <Button size="icon-sm" variant="ghost" aria-label="Hide sidebar" title="Hide" onClick={onClose}>
              <X className="size-3.5" />
            </Button>
          )}
        </div>
      </div>

      {entities.length > 8 && (
        <div className="relative border-b border-border p-1.5">
          <Search className="pointer-events-none absolute top-1/2 left-4 size-3.5 -translate-y-1/2 text-muted" />
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={`Filter ${noun}…`}
            aria-label={`Filter ${noun}`}
            className="h-8 w-full rounded-lg border border-border bg-surface pr-2 pl-8 text-base focus:border-accent focus:ring-3 focus:ring-ring focus:outline-none sm:text-xs"
          />
        </div>
      )}

      <div className="max-h-72 min-h-0 overflow-y-auto p-1 lg:max-h-[min(60dvh,34rem)]">
        {schema.isPending ? (
          <PageSpinner label={`Reading ${noun}…`} />
        ) : schema.isError ? (
          <ErrorAlert error={schema.error} className="m-1" />
        ) : schema.data === null ? (
          <p className="px-2 py-3 text-sm text-muted">Schema unavailable for this database.</p>
        ) : schema.data.status === "error" ? (
          <Alert tone="danger" title="Database unreachable" className="m-1">
            {schema.data.error ?? "Couldn't read this database."}
          </Alert>
        ) : entities.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted">No {noun} yet.</p>
        ) : shown.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted">No matches.</p>
        ) : (
          shown.map((e) => (
            <button
              key={e.name}
              type="button"
              onClick={() => onInsert(e.name)}
              title={`Insert a starter query for ${e.name}`}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface-2"
            >
              {isSql ? <Table2 className="size-3.5 shrink-0 text-muted" /> : <FileJson className="size-3.5 shrink-0 text-muted" />}
              <span className="min-w-0 flex-1 truncate font-mono text-xs">{e.name}</span>
              {e.row_count !== null && <span className="text-xs text-muted tabular-nums">{formatNumber(e.row_count)}</span>}
            </button>
          ))
        )}
      </div>
      <p className="border-t border-border px-3 py-1.5 text-[11px] text-muted">Click one to insert a starter query at the cursor.</p>
    </aside>
  );
}
