import { CheckCircle2, HardDrive, XCircle } from "lucide-react";
import type { DeviceCapabilities, DeviceMetrics, DeviceRole } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { ProgressBar, StatusDot } from "../../components/ui/Progress";
import { cn } from "../../lib/cn";
import { formatDateTime, relativeTime } from "../../lib/format";
import { capabilityNotes, ROLE_HINTS, ROLE_LABELS, usageBars, usageTone } from "./eligibility";

export function OnlineIndicator({ online, lastSeen }: { online: boolean; lastSeen: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs" title={lastSeen ? formatDateTime(lastSeen) : undefined}>
      <StatusDot tone={online ? "success" : "muted"} pulse={online} />
      <span className={online ? "font-medium text-success" : "text-muted"}>{online ? "Online" : "Offline"}</span>
      {!online && <span className="text-muted">· last seen {relativeTime(lastSeen)}</span>}
    </span>
  );
}

export function RoleBadges({ roles }: { roles: DeviceRole[] }) {
  if (roles.length === 0) return <Badge>No roles</Badge>;
  return (
    <>
      {roles.map((r) => (
        <Badge key={r} tone={r === "database_host" ? "accent" : "info"} title={ROLE_HINTS[r]}>
          {ROLE_LABELS[r]}
        </Badge>
      ))}
    </>
  );
}

export function UsageBars({ metrics, className }: { metrics: DeviceMetrics | null | undefined; className?: string }) {
  const bars = usageBars(metrics);
  if (bars.length === 0) return <p className={cn("text-xs text-muted", className)}>No metrics reported yet.</p>;
  return (
    <dl className={cn("grid gap-2.5 sm:grid-cols-3", className)}>
      {bars.map((b) => (
        <div key={b.key} className="min-w-0">
          <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
            <dt className="font-medium">{b.label}</dt>
            <dd className="truncate text-muted tabular-nums">{b.detail}</dd>
          </div>
          <ProgressBar value={b.percent} tone={usageTone(b.percent)} label={`${b.label} usage`} />
        </div>
      ))}
    </dl>
  );
}

export function CapabilityList({ capabilities }: { capabilities: DeviceCapabilities | null | undefined }) {
  const notes = capabilityNotes(capabilities);
  if (notes.length === 0) return <p className="text-sm text-muted">No capabilities reported.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {notes.map((n) => (
        <li key={n.text} className="flex items-start gap-2">
          {n.ok ? (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
          ) : (
            <XCircle className="mt-0.5 size-4 shrink-0 text-warning" />
          )}
          {n.text}
        </li>
      ))}
    </ul>
  );
}

export function DeviceBadge({ name }: { name: string | null }) {
  if (!name) return null;
  return (
    <Badge tone="neutral" title="Hosted on a host device">
      <HardDrive className="size-3" /> on {name}
    </Badge>
  );
}
