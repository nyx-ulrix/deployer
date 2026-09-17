import { HardDrive, Laptop, Server } from "lucide-react";
import type { BackupCopy, BackupTrigger } from "../../api/types";
import { Badge, type BadgeTone } from "../../components/ui/Badge";
import { cn } from "../../lib/cn";
import { formatDateTime } from "../../lib/format";
import type { TimelineBar } from "./pitr";
import { TRIGGER_LABELS } from "./timeline";

const TRIGGER_TONES: Record<BackupTrigger, BadgeTone> = {
  scheduled: "neutral",
  manual: "accent",
  pre_restore: "warning",
  pre_drop: "warning",
  pre_delete: "warning",
  pre_move: "info",
  final: "danger",
};

export function TriggerBadge({ trigger }: { trigger: BackupTrigger }) {
  return <Badge tone={TRIGGER_TONES[trigger]}>{TRIGGER_LABELS[trigger]}</Badge>;
}

const COPY_ICONS = { local: HardDrive, device: Laptop, primary: Server };
const COPY_LABELS = { local: "On the host", device: "Copy on a device", primary: "Copy on the main server" };

/** Little icons for where copies of a version live, coloured by copy status. */
export function CopyIcons({
  copies,
  deviceName,
}: {
  copies: BackupCopy[];
  deviceName?: (id: string | null) => string | null;
}) {
  if (copies.length === 0) return <span className="text-xs text-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-1">
      {copies.map((c, i) => {
        const Icon = COPY_ICONS[c.location] ?? HardDrive;
        const where = c.location === "device" && deviceName ? deviceName(c.device_id) : null;
        const label = `${COPY_LABELS[c.location] ?? c.location}${where ? ` (${where})` : ""}: ${c.status}`;
        return (
          <span
            key={`${c.location}-${c.device_id ?? ""}-${i}`}
            title={label}
            aria-label={label}
            className={cn(
              "inline-flex size-5 items-center justify-center rounded",
              c.status === "ok" && "bg-success-soft text-success",
              c.status === "pending" && "bg-surface-2 text-muted",
              c.status !== "ok" && c.status !== "pending" && "bg-danger-soft text-danger",
            )}
          >
            <Icon className="size-3" />
          </span>
        );
      })}
    </span>
  );
}

/** Small horizontal bar: PITR range as a band, snapshots as ticks, optional selected marker. */
export function RecoveryTimelineBar({
  bar,
  selected,
  className,
}: {
  bar: TimelineBar | null;
  selected?: number | null;
  className?: string;
}) {
  if (!bar) return null;
  const pos = selected !== null && selected !== undefined && bar.end > bar.start
    ? Math.min(100, Math.max(0, ((selected - bar.start) / (bar.end - bar.start)) * 100))
    : null;
  return (
    <div className={cn("space-y-1", className)}>
      <div className="relative h-5 rounded-md bg-surface-2" role="img" aria-label="Recovery timeline">
        {bar.pitr && (
          <div
            className="absolute inset-y-1 rounded bg-accent-soft ring-1 ring-accent/40"
            style={{ left: `${bar.pitr.left}%`, width: `${bar.pitr.width}%` }}
            title="Point-in-time recovery window"
          />
        )}
        {bar.marks.map((m) => (
          <span
            key={m.id}
            className="absolute inset-y-0.5 w-0.5 -translate-x-1/2 rounded bg-fg/60"
            style={{ left: `${m.left}%` }}
            title={formatDateTime(m.at)}
          />
        ))}
        {pos !== null && (
          <span
            className="absolute -inset-y-1 w-1 -translate-x-1/2 rounded bg-accent shadow"
            style={{ left: `${pos}%` }}
            title="Selected restore point"
          />
        )}
      </div>
      <div className="flex justify-between gap-2 text-[11px] text-muted">
        <span>{formatDateTime(new Date(bar.start).toISOString())}</span>
        <span className="hidden items-center gap-3 sm:inline-flex">
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-0.5 rounded bg-fg/60" /> version
          </span>
          {bar.pitr && (
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-3 rounded-sm bg-accent-soft ring-1 ring-accent/40" /> any point in time
            </span>
          )}
        </span>
        <span>{formatDateTime(new Date(bar.end).toISOString())}</span>
      </div>
    </div>
  );
}
