import { describe, expect, it } from "vitest";
import type { Backup } from "../../api/types";
import { dayKey, groupByDay, lastSuccessful, nextScheduledAt } from "./timeline";

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
    kept_as: null,
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

describe("dayKey", () => {
  it("uses the local calendar date", () => {
    expect(dayKey(new Date(2026, 0, 5))).toBe("2026-01-05");
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
