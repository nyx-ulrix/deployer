import type { Backup, BackupPolicy, BackupSchedule, BackupTrigger, KeptAs } from "../../api/types";

export const TRIGGER_LABELS: Record<BackupTrigger, string> = {
  scheduled: "Scheduled",
  manual: "Manual",
  pre_restore: "Before restore",
  pre_drop: "Before drop",
  pre_delete: "Before delete",
  pre_move: "Before move",
  final: "Final",
};

export const SCHEDULE_LABELS: Record<BackupSchedule, string> = {
  hourly: "Every hour",
  every_6h: "Every 6 hours",
  daily: "Every day",
};

const SCHEDULE_MS: Record<BackupSchedule, number> = {
  hourly: 3_600_000,
  every_6h: 6 * 3_600_000,
  daily: 24 * 3_600_000,
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** Local calendar day, "YYYY-MM-DD". */
export function dayKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export type DayGroup = { key: string; label: string; items: Backup[] };

/** Label a local day relative to `now`: "Today", "Yesterday", or a short date. */
export function dayLabel(key: string, now: Date = new Date()): string {
  if (key === dayKey(now)) return "Today";
  const y = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (key === dayKey(y)) return "Yesterday";
  const [yy, mm, dd] = key.split("-").map(Number);
  const d = new Date(yy, mm - 1, dd);
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: yy === now.getFullYear() ? undefined : "numeric",
  });
}

/** Group versions by local day, newest day first and newest version first inside each day. */
export function groupByDay(backups: readonly Backup[], now: Date = new Date()): DayGroup[] {
  const sorted = [...backups].sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at));
  const groups: DayGroup[] = [];
  const byKey = new Map<string, DayGroup>();
  for (const b of sorted) {
    const key = dayKey(new Date(b.started_at));
    let group = byKey.get(key);
    if (!group) {
      group = { key, label: dayLabel(key, now), items: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    group.items.push(b);
  }
  return groups;
}

/** Labels for the server's retention reason (`Backup.kept_as`, from the same rules the prune job uses). */
export const KEPT_AS_LABELS: Record<KeptAs, string> = {
  pinned: "Pinned",
  safety: "Safety (30 days)",
  hourly: "Hourly",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  latest: "Latest",
  running: "Running",
  recent_failure: "Recent failure",
};

/** Latest successful version, if any. */
export function lastSuccessful(backups: readonly Backup[]): Backup | null {
  let best: Backup | null = null;
  for (const b of backups) {
    if (b.status !== "succeeded") continue;
    if (!best || Date.parse(b.started_at) > Date.parse(best.started_at)) best = b;
  }
  return best;
}

/** Estimated next scheduled snapshot: last scheduled run + interval, never in the past. */
export function nextScheduledAt(
  policy: Pick<BackupPolicy, "enabled" | "schedule">,
  backups: readonly Backup[],
  now: Date = new Date(),
): Date | null {
  if (!policy.enabled) return null;
  const interval = SCHEDULE_MS[policy.schedule];
  let last = -Infinity;
  for (const b of backups) {
    if (b.trigger === "scheduled") last = Math.max(last, Date.parse(b.started_at));
  }
  if (!Number.isFinite(last)) return new Date(now.getTime() + Math.min(interval, 3_600_000));
  let next = last + interval;
  while (next < now.getTime()) next += interval;
  return new Date(next);
}

/** One-line health of the copies of the latest version. */
export function copiesSummary(backup: Backup | null): { tone: "success" | "warning" | "danger" | "neutral"; text: string } {
  if (!backup) return { tone: "neutral", text: "No versions yet" };
  const extra = backup.copies.filter((c) => c.location !== "local");
  const bad = backup.copies.filter((c) => c.status !== "ok" && c.status !== "pending");
  if (bad.length > 0) return { tone: "danger", text: `${bad.length} copy missing` };
  if (extra.length === 0) return { tone: "warning", text: "Only on the host (no copy)" };
  if (extra.some((c) => c.status === "pending")) return { tone: "neutral", text: "Copy in progress" };
  return { tone: "success", text: `Copied (${extra.length + 1} locations)` };
}
