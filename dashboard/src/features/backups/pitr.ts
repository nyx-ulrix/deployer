import type { Backup, RecoveryWindow } from "../../api/types";

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** Local "YYYY-MM-DD" for a date input. */
export function toDateInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Local "HH:MM:SS" for a time input with step=1. */
export function toTimeInput(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Combine local date ("YYYY-MM-DD") and time ("HH:MM" or "HH:MM:SS") inputs into a Date. */
export function combineLocal(date: string, time: string): Date | null {
  const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const tm = /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(time);
  if (!dm || !tm) return null;
  const [y, mo, d] = [Number(dm[1]), Number(dm[2]), Number(dm[3])];
  const [h, mi, s] = [Number(tm[1]), Number(tm[2]), Number(tm[3] ?? 0)];
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return null;
  const result = new Date(y, mo - 1, d, h, mi, s);
  // Reject overflow like 2026-02-31.
  if (result.getMonth() !== mo - 1 || result.getDate() !== d) return null;
  return result;
}

export type PitrBounds = { earliest: Date; latest: Date };

/** The usable PITR range, or null when point-in-time recovery isn't available. */
export function pitrBounds(window: RecoveryWindow | undefined | null): PitrBounds | null {
  if (!window || !window.pitr_enabled || !window.earliest || !window.latest) return null;
  const earliest = new Date(window.earliest);
  const latest = new Date(window.latest);
  if (Number.isNaN(earliest.getTime()) || Number.isNaN(latest.getTime()) || earliest > latest) return null;
  return { earliest, latest };
}

export function clampToBounds(d: Date, bounds: PitrBounds): Date {
  if (d < bounds.earliest) return new Date(bounds.earliest);
  if (d > bounds.latest) return new Date(bounds.latest);
  return d;
}

/**
 * min/max attributes for the date input and, for the chosen day, the time input. Seconds are rounded
 * inwards so any time accepted by the inputs lies inside the window.
 */
export function inputConstraints(
  bounds: PitrBounds,
  date: string,
): { minDate: string; maxDate: string; minTime?: string; maxTime?: string } {
  const minDate = toDateInput(bounds.earliest);
  const maxDate = toDateInput(bounds.latest);
  const out: { minDate: string; maxDate: string; minTime?: string; maxTime?: string } = { minDate, maxDate };
  if (date === minDate) {
    const e = new Date(bounds.earliest);
    if (e.getMilliseconds() > 0) e.setSeconds(e.getSeconds() + 1, 0);
    out.minTime = toTimeInput(e);
  }
  if (date === maxDate) out.maxTime = toTimeInput(bounds.latest);
  return out;
}

export type PitrValidation = { ok: true; value: Date } | { ok: false; error: string };

export function validatePointInTime(date: string, time: string, bounds: PitrBounds | null): PitrValidation {
  if (!bounds) return { ok: false, error: "Point-in-time recovery isn't available for this database." };
  if (!date || !time) return { ok: false, error: "Choose a date and time." };
  const value = combineLocal(date, time);
  if (!value) return { ok: false, error: "Enter a valid date and time." };
  // Inputs have 1 s resolution; compare at that resolution.
  const earliest = Math.ceil(bounds.earliest.getTime() / 1000) * 1000;
  const latest = Math.floor(bounds.latest.getTime() / 1000) * 1000;
  if (value.getTime() < earliest) return { ok: false, error: "That's before the start of the recovery window." };
  if (value.getTime() > latest) return { ok: false, error: "That's after the latest recoverable point." };
  return { ok: true, value };
}

export type TimelineBar = {
  start: number;
  end: number;
  pitr: { left: number; width: number } | null;
  marks: { id: string; left: number; at: string }[];
};

/** Percent position of `t` between `start` and `end`, clamped to 0–100. */
export function percentOf(t: number, start: number, end: number): number {
  if (end <= start) return 100;
  return Math.min(100, Math.max(0, ((t - start) / (end - start)) * 100));
}

/** Layout for the small timeline bar: the PITR range plus a tick for every successful snapshot. */
export function timelineBar(bounds: PitrBounds | null, backups: readonly Backup[]): TimelineBar | null {
  const ok = backups.filter((b) => b.status === "succeeded" && Number.isFinite(Date.parse(b.started_at)));
  const times = ok.map((b) => Date.parse(b.started_at));
  if (bounds) times.push(bounds.earliest.getTime(), bounds.latest.getTime());
  if (times.length === 0) return null;
  const start = Math.min(...times);
  const end = Math.max(...times);
  const pitr = bounds
    ? (() => {
        const left = percentOf(bounds.earliest.getTime(), start, end);
        const right = percentOf(bounds.latest.getTime(), start, end);
        return { left, width: Math.max(0.5, right - left) };
      })()
    : null;
  return {
    start,
    end,
    pitr,
    marks: ok.map((b) => ({ id: b.id, left: percentOf(Date.parse(b.started_at), start, end), at: b.started_at })),
  };
}

/** Closest successful snapshot at or before `t` (restores replay logs from it). */
export function baseSnapshotFor(t: Date, backups: readonly Backup[]): Backup | null {
  let best: Backup | null = null;
  for (const b of backups) {
    if (b.status !== "succeeded") continue;
    const at = Date.parse(b.started_at);
    if (at <= t.getTime() && (!best || at > Date.parse(best.started_at))) best = b;
  }
  return best;
}
