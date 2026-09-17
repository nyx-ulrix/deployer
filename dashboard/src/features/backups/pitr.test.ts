import { describe, expect, it } from "vitest";
import type { Backup } from "../../api/types";
import {
  baseSnapshotFor,
  clampToBounds,
  combineLocal,
  inputConstraints,
  percentOf,
  pitrBounds,
  timelineBar,
  toDateInput,
  toTimeInput,
  validatePointInTime,
} from "./pitr";

const earliest = new Date(2026, 8, 9, 14, 30, 15, 500);
const latest = new Date(2026, 8, 16, 11, 45, 10);
const window = { pitr_enabled: true, earliest: earliest.toISOString(), latest: latest.toISOString(), snapshots: 3 };

const snap = (id: string, at: Date, status: Backup["status"] = "succeeded"): Backup => ({
  id,
  trigger: "scheduled",
  status,
  label: null,
  pinned: false,
  size_bytes: null,
  started_at: at.toISOString(),
  finished_at: null,
  verified_at: null,
  verify_status: null,
  copies: [],
  row_counts: null,
  expires_at: null,
  job_id: null,
});

describe("pitrBounds", () => {
  it("is null when PITR is off or the window is incomplete", () => {
    expect(pitrBounds({ ...window, pitr_enabled: false })).toBeNull();
    expect(pitrBounds({ ...window, earliest: null })).toBeNull();
    expect(pitrBounds({ ...window, earliest: window.latest, latest: window.earliest })).toBeNull();
    expect(pitrBounds(window)?.earliest.getTime()).toBe(earliest.getTime());
  });
});

describe("combineLocal / inputs", () => {
  it("round-trips local date and time inputs", () => {
    const d = new Date(2026, 1, 3, 4, 5, 6);
    expect(toDateInput(d)).toBe("2026-02-03");
    expect(toTimeInput(d)).toBe("04:05:06");
    expect(combineLocal("2026-02-03", "04:05:06")?.getTime()).toBe(d.getTime());
    expect(combineLocal("2026-02-03", "04:05")?.getTime()).toBe(new Date(2026, 1, 3, 4, 5).getTime());
  });

  it("rejects malformed or overflowing values", () => {
    expect(combineLocal("2026-02-31", "10:00")).toBeNull();
    expect(combineLocal("2026-13-01", "10:00")).toBeNull();
    expect(combineLocal("2026-02-01", "24:00")).toBeNull();
    expect(combineLocal("", "10:00")).toBeNull();
  });
});

describe("inputConstraints", () => {
  const bounds = pitrBounds(window)!;
  it("limits dates to the window and times on the first/last day", () => {
    expect(inputConstraints(bounds, "2026-09-12")).toEqual({ minDate: "2026-09-09", maxDate: "2026-09-16" });
    // earliest has milliseconds, so the first allowed whole second is rounded up
    expect(inputConstraints(bounds, "2026-09-09").minTime).toBe("14:30:16");
    expect(inputConstraints(bounds, "2026-09-16").maxTime).toBe("11:45:10");
  });

  it("sets both limits when the window is a single day", () => {
    const one = pitrBounds({ ...window, earliest: new Date(2026, 8, 16, 9).toISOString() })!;
    expect(inputConstraints(one, "2026-09-16")).toMatchObject({ minTime: "09:00:00", maxTime: "11:45:10" });
  });
});

describe("validatePointInTime", () => {
  const bounds = pitrBounds(window)!;
  it("accepts times inside the window, including the exact edges", () => {
    expect(validatePointInTime("2026-09-12", "08:00", bounds).ok).toBe(true);
    expect(validatePointInTime("2026-09-16", "11:45:10", bounds).ok).toBe(true);
    expect(validatePointInTime("2026-09-09", "14:30:16", bounds).ok).toBe(true);
  });

  it("rejects times outside the window or when PITR is unavailable", () => {
    expect(validatePointInTime("2026-09-09", "14:30:15", bounds)).toMatchObject({ ok: false });
    expect(validatePointInTime("2026-09-16", "11:45:11", bounds)).toMatchObject({ ok: false });
    expect(validatePointInTime("2026-09-12", "", bounds)).toMatchObject({ ok: false });
    expect(validatePointInTime("2026-09-12", "08:00", null)).toMatchObject({ ok: false });
  });

  it("clamps to the window", () => {
    expect(clampToBounds(new Date(2020, 0, 1), bounds).getTime()).toBe(earliest.getTime());
    expect(clampToBounds(new Date(2030, 0, 1), bounds).getTime()).toBe(latest.getTime());
  });
});

describe("timeline bar", () => {
  it("places snapshots and the PITR range on a 0–100 scale", () => {
    const bounds = pitrBounds(window)!;
    const backups = [
      snap("old", new Date(2026, 8, 2, 12)),
      snap("mid", new Date(2026, 8, 12, 12)),
      snap("bad", new Date(2026, 8, 13, 12), "failed"),
    ];
    const bar = timelineBar(bounds, backups)!;
    expect(bar.marks.map((m) => m.id)).toEqual(["old", "mid"]);
    expect(bar.marks[0].left).toBe(0);
    expect(bar.pitr!.left).toBeGreaterThan(0);
    expect(bar.pitr!.left + bar.pitr!.width).toBeCloseTo(100);
    expect(timelineBar(null, [])).toBeNull();
    expect(percentOf(5, 0, 10)).toBe(50);
    expect(percentOf(20, 0, 10)).toBe(100);
  });

  it("finds the snapshot a point-in-time restore starts from", () => {
    const backups = [snap("a", new Date(2026, 8, 10)), snap("b", new Date(2026, 8, 12)), snap("c", new Date(2026, 8, 11), "failed")];
    expect(baseSnapshotFor(new Date(2026, 8, 11, 12), backups)?.id).toBe("a");
    expect(baseSnapshotFor(new Date(2026, 8, 9), backups)).toBeNull();
  });
});
