import { Code, Eye, Terminal } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { QUERY_CONSOLE_MODES, useQueryConsoleMode } from "../../lib/consoleMode";
import { formatNumber } from "../../lib/format";
import { MAX_ROWS_OPTIONS, TIMEOUT_OPTIONS } from "./prefs";

// Small pieces shared by the terminal and editor layouts' header bars.

function withCurrent(options: readonly number[], current: number): number[] {
  return options.includes(current) ? [...options] : [...options, current].sort((a, b) => a - b);
}

// The selects sit in a fixed-width box: `Select` is `w-full` by design.
export function RowsSelect({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="w-32">
      <Select aria-label="Maximum rows" className="h-8 text-xs" value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {withCurrent(MAX_ROWS_OPTIONS, value).map((n) => (
          <option key={n} value={n}>
            {formatNumber(n)} rows
          </option>
        ))}
      </Select>
    </div>
  );
}

export function TimeoutSelect({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="w-34">
      <Select aria-label="Timeout" className="h-8 text-xs" value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {withCurrent(TIMEOUT_OPTIONS, value).map((n) => (
          <option key={n} value={n}>
            {n} s timeout
          </option>
        ))}
      </Select>
    </div>
  );
}

export function ReadOnlyBadge() {
  return (
    <Badge tone="warning" title="Viewers can only run read-only queries; anything else is refused by the API.">
      <Eye className="size-3" /> Read-only
    </Badge>
  );
}

/** Terminal / Editor layout switch (the same preference as Settings → Account → Preferences). */
export function ModeSwitch() {
  const [mode, setMode] = useQueryConsoleMode();
  return (
    <div role="group" aria-label="Console layout" className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {QUERY_CONSOLE_MODES.map((m) => {
        const Icon = m.value === "terminal" ? Terminal : Code;
        const active = m.value === mode;
        return (
          <button
            key={m.value}
            type="button"
            aria-pressed={active}
            aria-label={`${m.label} layout`}
            title={`${m.label} — ${m.description}`}
            onClick={() => setMode(m.value)}
            className={cn(
              "inline-flex size-7 items-center justify-center rounded-md transition-colors",
              active ? "bg-surface text-fg shadow-xs" : "text-muted hover:text-fg",
            )}
          >
            <Icon className="size-3.5" />
          </button>
        );
      })}
    </div>
  );
}

/** Viewer hint shown before an obviously-write query is sent (the API is the real guard). */
export function PendingWriteAlert({
  reason,
  onCancel,
  onConfirm,
}: {
  reason: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Alert
      tone="warning"
      title="This looks like a write query"
      action={
        <div className="flex gap-2">
          <Button size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" variant="primary" onClick={onConfirm}>
            Run anyway
          </Button>
        </div>
      }
    >
      {reason} Viewers can only run read-only queries, so the API will refuse it.
    </Alert>
  );
}
