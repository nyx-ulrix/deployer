import { ChevronDown, History, Trash2 } from "lucide-react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Menu, MenuItem } from "../../components/ui/Menu";
import { StatusDot } from "../../components/ui/Progress";
import { formatDateTime, relativeTime } from "../../lib/format";
import type { HistoryEntry } from "./history";
import { formatMs } from "./results";

/** Per-source history (last 50 runs); clicking an entry loads it into the editor. */
export function HistoryMenu({
  entries,
  onPick,
  onClear,
}: {
  entries: HistoryEntry[];
  onPick: (query: string) => void;
  onClear: () => void;
}) {
  return (
    <Menu
      align="start"
      className="w-[min(92vw,30rem)]"
      trigger={({ toggle, open }) => (
        <Button size="sm" onClick={toggle} aria-expanded={open} icon={<History className="size-3.5" />}>
          History {entries.length > 0 && <Badge>{entries.length}</Badge>}
          <ChevronDown className="size-3.5" />
        </Button>
      )}
    >
      {(close) =>
        entries.length === 0 ? (
          <p className="px-3 py-3 text-sm text-muted">Queries you run on this database show up here.</p>
        ) : (
          <>
            <ul className="max-h-80 overflow-y-auto" aria-label="Query history">
              {entries.map((h) => (
                <li key={h.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onPick(h.query);
                      close();
                    }}
                    className="flex w-full flex-col gap-0.5 rounded-lg px-2.5 py-2 text-left hover:bg-surface-2"
                  >
                    <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted">
                      <StatusDot tone={h.ok ? "success" : "danger"} />
                      <span title={formatDateTime(h.at)}>{relativeTime(h.at)}</span>
                      <span>·</span>
                      <span className="tabular-nums">{formatMs(h.duration_ms)}</span>
                      {!h.ok && h.error && <span className="min-w-0 truncate text-danger">· {h.error}</span>}
                    </span>
                    <code className="line-clamp-2 font-mono text-xs break-all whitespace-pre-wrap text-fg">{h.query.trim()}</code>
                  </button>
                </li>
              ))}
            </ul>
            <div className="mt-1 border-t border-border pt-1">
              <MenuItem
                icon={<Trash2 />}
                danger
                onClick={() => {
                  onClear();
                  close();
                }}
              >
                Clear history
              </MenuItem>
            </div>
          </>
        )
      }
    </Menu>
  );
}
