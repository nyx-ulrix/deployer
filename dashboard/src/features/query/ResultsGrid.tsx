import { useState } from "react";
import { ChevronDown, Download } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Menu, MenuItem } from "../../components/ui/Menu";
import { cn } from "../../lib/cn";
import { formatNumber } from "../../lib/format";
import { exportCsv, exportJson, type Cell, type ExportTable } from "./csv";
import { expandedCellText, formatCell } from "./results";

const PAGE = 200;
const SHORT = 60;

export type GridVariant = "panel" | "terminal";

/**
 * Rows grid: monospace cells, long values truncated with click-to-expand, rows revealed in pages.
 * `panel` (editor layout) scrolls inside itself with a sticky header; `terminal` (transcript) is a
 * bordered zebra table that only scrolls horizontally.
 */
export function ResultsGrid({
  columns,
  rows,
  label,
  variant = "panel",
}: {
  columns: string[];
  rows: Cell[][];
  label: string;
  variant?: GridVariant;
}) {
  const [visible, setVisible] = useState(PAGE);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const shown = rows.length > visible ? rows.slice(0, visible) : rows;
  const terminal = variant === "terminal";

  return (
    <div className={cn(terminal && "my-1 inline-block max-w-full rounded-md border border-border bg-surface/60")}>
      <div className={terminal ? "overflow-x-auto" : "max-h-[28rem] overflow-auto"}>
        <table className="w-full border-collapse text-left text-xs" aria-label={label}>
          <thead className={cn("bg-surface-2 text-[11px]", !terminal && "sticky top-0 z-10")}>
            <tr>
              <th scope="col" className="border-b border-border px-2 py-1.5 text-right font-normal text-muted">
                #
              </th>
              {columns.map((c, i) => (
                <th key={i} scope="col" className="border-b border-border px-3 py-1.5 font-mono font-semibold whitespace-nowrap">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-mono">
            {shown.map((row, r) => (
              <tr key={r} className={cn("align-top", terminal ? "even:bg-surface-2/50" : "hover:bg-surface-2/60")}>
                <td className="px-2 py-1 text-right text-muted tabular-nums select-none">{r + 1}</td>
                {columns.map((_, c) => (
                  <GridCell key={c} value={row[c]} expanded={expanded.has(`${r}:${c}`)} onToggle={() => toggle(`${r}:${c}`)} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > shown.length && (
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2 text-xs text-muted">
          <span>
            Showing {formatNumber(shown.length)} of {formatNumber(rows.length)} rows
          </span>
          <Button size="sm" onClick={() => setVisible((v) => v + PAGE * 5)}>
            Show {formatNumber(Math.min(PAGE * 5, rows.length - shown.length))} more
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setVisible(rows.length)}>
            Show all
          </Button>
        </div>
      )}
    </div>
  );
}

function GridCell({ value, expanded, onToggle }: { value: Cell; expanded: boolean; onToggle: () => void }) {
  const { text, kind } = formatCell(value);
  const expandable = kind === "json" || text.length > SHORT || text.includes("\n");
  const tone =
    kind === "null" || kind === "missing"
      ? "text-muted italic"
      : kind === "number"
        ? "tabular-nums"
        : kind === "boolean"
          ? "text-warning"
          : kind === "binary"
            ? "text-muted"
            : "";
  if (!expandable) {
    return <td className={cn("px-3 py-1 whitespace-nowrap", tone)}>{kind === "missing" ? "—" : text}</td>;
  }
  return (
    <td className={cn("px-3 py-1", tone)}>
      <button
        type="button"
        onClick={onToggle}
        title={expanded ? "Click to collapse" : "Click to expand"}
        aria-expanded={expanded}
        className={cn("block text-left", expanded ? "max-w-[44rem] whitespace-pre-wrap break-all" : "max-w-80 truncate")}
      >
        {expanded ? expandedCellText(value) : text}
      </button>
    </td>
  );
}

/** Export CSV / JSON dropdown for one rows result (or a documents table). */
export function ExportMenu(table: ExportTable) {
  return (
    <Menu
      align="end"
      trigger={({ toggle, open }) => (
        <Button size="sm" variant="ghost" onClick={toggle} aria-expanded={open} icon={<Download className="size-3.5" />}>
          Export <ChevronDown className="size-3.5" />
        </Button>
      )}
    >
      {(close) => (
        <>
          <MenuItem
            icon={<Download />}
            onClick={() => {
              close();
              exportCsv(table);
            }}
          >
            Export CSV
          </MenuItem>
          <MenuItem
            icon={<Download />}
            onClick={() => {
              close();
              exportJson(table);
            }}
          >
            Export JSON
          </MenuItem>
        </>
      )}
    </Menu>
  );
}
