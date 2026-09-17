import { describe, expect, it } from "vitest";
import type { Backup } from "../../api/types";
import { dayKey, groupByDay, lastSuccessful, nextScheduledAt, retentionReasons, weekKey } from "./timeline";

let seq = 0;
function backup(at: Date, over: Partial<Backup> = {}): Backup {
  seq += 1;
  return {
    id: over.id ?? `b${seq}`,
    trigger: "scheduled",
    status: "succeeded",
    label: null,
    pinned: false,
    size_bytes: 1000,
    started_at: at.toISOString(),
    finished_at: at.toISOString(),
    verified_at: null,
    verify_status: null,
    copies: [],
    row_counts: null,
    expires_at: null,
    job_id: null,
    ...over,
  };
}

// Local-time constructors keep these tests independent of the machine's time zone.
const local = (d: number, h: number, m = 0, month = 8, year = 2026) => new Date(year, month, d, h, m);

describe("groupByDay", () => {
  it("groups by local day, newest first, with relative labels", () => {
    const now = local(16, 12);
    const items = [
      backup(local(15, 23, 30), { id: "y" }),
      backup(local(16, 1), { id: "t1" }),
      backup(local(16, 11), { id: "t2" }),
      backup(local(10, 8), { id: "old" }),
    ];
    const groups = groupByDay(items, now);
    expect(groups.map((g) => g.key)).toEqual(["2026-09-16", "2026-09-15", "2026-09-10"]);
    expect(groups[0].label).toBe("Today");
    expect(groups[1].label).toBe("Yesterday");
    expect(groups[2].label).not.toMatch(/Today|Yesterday/);
    expect(groups[0].items.map((b) => b.id)).toEqual(["t2", "t1"]);
  });

  it("returns an empty list for no versions", () => {
    expect(groupByDay([])).toEqual([]);
  });
});

describe("weekKey", () => {
  it("uses Monday-start ISO weeks", () => {
    expect(weekKey(new Date(2026, 8, 14))).toBe(weekKey(new Date(2026, 8, 20))); // Mon..Sun
    expect(weekKey(new Date(2026, 8, 20))).not.toBe(weekKey(new Date(2026, 8, 21)));
    expect(weekKey(new Date(2021, 0, 3))).toBe("2020-W53");
    expect(dayKey(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("retentionReasons (GFS)", () => {
  const policy = { keep_hourly: 2, keep_daily: 2, keep_weekly: 1, keep_monthly: 1 };

  it("keeps the newest version per bucket for the most recent N buckets", () => {
    const now = local(16, 12);
    const items = [
      backup(local(16, 11, 30), { id: "h11b" }),
      backup(local(16, 11, 0), { id: "h11a" }),
      backup(local(16, 10, 0), { id: "h10" }),
      backup(local(16, 9, 0), { id: "h9" }),
      backup(local(15, 9, 0), { id: "d15" }),
      backup(local(14, 9, 0), { id: "d14" }),
    ];
    const r = retentionReasons(items, policy, now);
    expect(r.get("h11b")).toEqual(["hourly", "daily", "weekly", "monthly"]);
    expect(r.get("h11a")).toEqual([]);
    expect(r.get("h10")).toEqual(["hourly"]);
    expect(r.get("h9")).toEqual([]);
    expect(r.get("d15")).toEqual(["daily"]);
    expect(r.get("d14")).toEqual([]);
  });

  it("always keeps pinned versions and recent safety snapshots, ignores failed ones", () => {
    const now = local(16, 12);
    const items = [
      backup(local(16, 11), { id: "new" }),
      backup(local(16, 11, 5), { id: "failed", status: "failed" }),
      backup(local(1, 11), { id: "pinned", pinned: true }),
      backup(local(10, 11), { id: "safety", trigger: "pre_drop" }),
      backup(local(1, 11, 0, 5), { id: "old-safety", trigger: "pre_restore" }),
    ];
    const r = retentionReasons(items, { keep_hourly: 1, keep_daily: 0, keep_weekly: 0, keep_monthly: 0 }, now);
    expect(r.has("failed")).toBe(false);
    expect(r.get("pinned")).toContain("pinned");
    expect(r.get("safety")).toEqual(["safety"]);
    expect(r.get("old-safety")).toEqual([]);
  });
});

describe("nextScheduledAt / lastSuccessful", () => {
  it("adds the schedule interval to the last scheduled run, never in the past", () => {
    const now = local(16, 12, 10);
    const items = [backup(local(16, 12, 0)), backup(local(16, 12, 5), { trigger: "manual" })];
    expect(nextScheduledAt({ enabled: true, schedule: "hourly" }, items, now)?.getTime()).toBe(local(16, 13).getTime());
    expect(nextScheduledAt({ enabled: true, schedule: "hourly" }, [backup(local(16, 8))], now)?.getTime()).toBe(
      local(16, 13).getTime(),
    );
    expect(nextScheduledAt({ enabled: false, schedule: "daily" }, items, now)).toBeNull();
  });

  it("finds the newest successful version", () => {
    const items = [backup(local(16, 9), { id: "a" }), backup(local(16, 10), { id: "b", status: "failed" })];
    expect(lastSuccessful(items)?.id).toBe("a");
    expect(lastSuccessful([])).toBeNull();
  });
});
