import { Check, ChevronDown, Database, Leaf } from "lucide-react";
import type { DataSource } from "../../api/types";
import { Menu } from "../../components/ui/Menu";
import { StatusDot } from "../../components/ui/Progress";
import { cn } from "../../lib/cn";
import { engineLabel } from "../../lib/format";
import { EngineBadge, KindBadge, ModeBadge } from "../databases/SourceBadges";
import { DeviceBadge } from "../devices/DeviceBits";
import { promptLabel } from "./terminal";

function statusTone(s: DataSource): "success" | "danger" | "muted" {
  return s.status === "ok" ? "success" : s.status === "error" ? "danger" : "muted";
}

/**
 * Database selector: every data source with engine, SQL/NoSQL, host device and status.
 * `field` looks like a form control; `prompt` is the shell prompt label (`shop-sql›`).
 */
export function SourceSelect({
  sources,
  value,
  onChange,
  deviceName,
  variant = "field",
  className,
}: {
  sources: DataSource[];
  value: DataSource;
  onChange: (id: string) => void;
  deviceName: (s: DataSource) => string | null;
  variant?: "field" | "prompt";
  className?: string;
}) {
  const Icon = value.kind === "sql" ? Database : Leaf;
  return (
    <div className={className}>
      <Menu
        align="start"
        className="w-[min(92vw,24rem)]"
        trigger={({ toggle, open }) =>
          variant === "prompt" ? (
            <button
              type="button"
              onClick={toggle}
              aria-haspopup="menu"
              aria-expanded={open}
              aria-label={`Database: ${value.name}. Change database`}
              title={`${value.name} · ${engineLabel(value.engine)} — click to switch database`}
              className="inline-flex max-w-[45vw] shrink-0 items-center gap-1 rounded px-1 py-0.5 font-mono text-[13px] leading-6 font-semibold text-accent hover:bg-surface-2 sm:max-w-none"
            >
              <span className="truncate">{promptLabel(value)}</span>
              <ChevronDown className="size-3 shrink-0 opacity-70" />
            </button>
          ) : (
            <button
              type="button"
              onClick={toggle}
              aria-haspopup="menu"
              aria-expanded={open}
              aria-label={`Database: ${value.name}`}
              title={value.status_message ?? undefined}
              className="flex h-9 w-full min-w-0 items-center gap-2 rounded-lg border border-border bg-surface px-2.5 text-sm shadow-xs hover:bg-surface-2"
            >
              <Icon className={cn("size-4 shrink-0", value.kind === "sql" ? "text-sql" : "text-nosql")} />
              <span className="min-w-0 truncate font-medium">{value.name}</span>
              <span className="hidden text-xs text-muted sm:inline">{engineLabel(value.engine)}</span>
              <StatusDot tone={statusTone(value)} />
              <ChevronDown className="ml-auto size-4 shrink-0 text-muted" />
            </button>
          )
        }
      >
        {(close) =>
          sources.map((s) => {
            const selected = s.id === value.id;
            return (
              <button
                key={s.id}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => {
                  onChange(s.id);
                  close();
                }}
                className={cn(
                  "flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left font-sans text-sm hover:bg-surface-2",
                  selected && "bg-accent-soft/60",
                )}
              >
                <span className="mt-1.5">
                  <StatusDot tone={statusTone(s)} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="min-w-0 truncate font-medium">{s.name}</span>
                    {selected && <Check className="size-3.5 shrink-0 text-accent" />}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-1">
                    <KindBadge kind={s.kind} />
                    <EngineBadge engine={s.engine} />
                    {s.mode === "external" && <ModeBadge mode={s.mode} />}
                    <DeviceBadge name={deviceName(s)} />
                  </span>
                  {s.status === "error" && s.status_message && (
                    <span className="mt-1 block truncate text-xs text-danger">{s.status_message}</span>
                  )}
                </span>
              </button>
            );
          })
        }
      </Menu>
    </div>
  );
}
