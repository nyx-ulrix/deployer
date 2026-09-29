import type { ImportSummary } from "../../api/types";
import { Alert } from "../../components/ui/States";
import { formatNumber } from "../../lib/format";

const LABELS: { key: Exclude<keyof ImportSummary, "warnings">; label: string }[] = [
  { key: "users", label: "Users" },
  { key: "projects", label: "Projects" },
  { key: "data_sources", label: "Data sources" },
  { key: "rows", label: "SQL rows" },
  { key: "documents", label: "Documents" },
];

export function ImportSummaryList({ summary }: { summary: ImportSummary }) {
  const items = LABELS.filter((l) => typeof summary[l.key] === "number");
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {items.map((l) => (
          <div key={l.key} className="rounded-lg border border-border bg-surface-2 px-3 py-2">
            <dt className="text-xs text-muted">{l.label}</dt>
            <dd className="text-lg font-semibold tabular-nums">{formatNumber(summary[l.key])}</dd>
          </div>
        ))}
      </dl>
      {summary.warnings && summary.warnings.length > 0 && (
        <Alert tone="warning" title="Not everything came across">
          <ul className="list-disc space-y-1 pl-4">
            {summary.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      )}
    </div>
  );
}
