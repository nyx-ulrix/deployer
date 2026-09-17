import type { SqlQueryResponse, SqlStatementResult } from "../../api/types";
import { Badge, type BadgeTone } from "../../components/ui/Badge";
import { Alert, EmptyState } from "../../components/ui/States";
import { formatNumber } from "../../lib/format";
import { ExportMenu, ResultsGrid } from "./ResultsGrid";
import { formatMs, statementLabel } from "./results";

const TYPES: Record<SqlStatementResult["type"], { label: string; tone: BadgeTone }> = {
  rows: { label: "Rows", tone: "sql" },
  count: { label: "Changed", tone: "accent" },
  empty: { label: "OK", tone: "success" },
  error: { label: "Error", tone: "danger" },
};

/** One card per statement (QUERY_CONSOLE.md → Results). */
export function SqlResults({ response, maxRows }: { response: SqlQueryResponse; maxRows: number }) {
  if (response.results.length === 0) {
    return <EmptyState title="Nothing ran" description="The text didn't contain any SQL statement." />;
  }
  const lastIndex = response.results.length - 1;
  return (
    <div className="space-y-3">
      {response.results.map((r, i) => (
        <StatementCard key={i} index={i} result={r} maxRows={maxRows} stoppedEarly={r.type === "error" && i < lastIndex} />
      ))}
    </div>
  );
}

function StatementCard({
  index,
  result,
  maxRows,
  stoppedEarly,
}: {
  index: number;
  result: SqlStatementResult;
  maxRows: number;
  stoppedEarly: boolean;
}) {
  const type = TYPES[result.type];
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-surface shadow-xs" aria-label={`Statement ${index + 1}`}>
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border px-3 py-2">
        <span className="text-xs text-muted tabular-nums">#{index + 1}</span>
        <Badge tone={type.tone}>{type.label}</Badge>
        <code className="min-w-0 flex-1 basis-40 truncate font-mono text-xs text-muted" title={result.statement}>
          {statementLabel(result.statement)}
        </code>
        {result.type === "rows" && (
          <span className="text-xs tabular-nums">
            {formatNumber(result.row_count)} {result.row_count === 1 ? "row" : "rows"}
          </span>
        )}
        {result.type === "rows" && result.truncated && (
          <Badge tone="warning" title={`Only the first ${formatNumber(maxRows)} rows were fetched. Raise "max rows" or narrow the query.`}>
            truncated at {formatNumber(maxRows)}
          </Badge>
        )}
        {result.type !== "error" && <span className="text-xs text-muted tabular-nums">{formatMs(result.duration_ms)}</span>}
        {result.type === "rows" && result.rows.length > 0 && (
          <ExportMenu columns={result.columns} rows={result.rows} base={result.statement} index={index} />
        )}
      </header>

      {result.type === "rows" &&
        (result.rows.length === 0 ? (
          <p className="px-3 py-3 text-sm text-muted">No rows returned.</p>
        ) : (
          <ResultsGrid columns={result.columns} rows={result.rows} label={`Rows of statement ${index + 1}`} />
        ))}
      {result.type === "count" && (
        <p className="px-3 py-3 text-sm">
          <span className="font-semibold tabular-nums">{formatNumber(result.affected_rows)}</span>{" "}
          {result.affected_rows === 1 ? "row" : "rows"} affected
        </p>
      )}
      {result.type === "empty" && <p className="px-3 py-3 text-sm font-medium text-success">OK</p>}
      {result.type === "error" && (
        <div className="p-3">
          <Alert tone="danger" title={result.error.code === "query_failed" ? "Statement failed" : result.error.code}>
            <span className="font-mono text-xs whitespace-pre-wrap">{result.error.message}</span>
            {stoppedEarly && <p className="mt-1 text-xs">Execution stopped here; the statements before it were kept.</p>}
          </Alert>
        </div>
      )}
    </section>
  );
}
