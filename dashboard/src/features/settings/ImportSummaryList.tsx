import type { ImportSummary } from "../../api/types";
import { formatNumber } from "../../lib/format";

const LABELS: { key: keyof ImportSummary; label: string }[] = [
  { key: "users", label: "Users" },
  { key: "projects", label: "Projects" },
  { key: "data_sources", label: "Data sources" },
  { key: "rows", label: "SQL rows" },
  { key: "documents", label: "Documents" },
];

export function ImportSummaryList({ summary }: { summary: ImportSummary }) {
  const items = LABELS.filter((l) => typeof summary[l.key] === "number");
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {items.map((l) => (
        <div key={l.key} className="rounded-lg border border-border bg-surface-2 px-3 py-2">
          <dt className="text-xs text-muted">{l.label}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatNumber(summary[l.key])}</dd>
        </div>
      ))}
    </dl>
  );
}
