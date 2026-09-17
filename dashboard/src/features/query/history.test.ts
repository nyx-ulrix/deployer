import { beforeEach, describe, expect, it } from "vitest";
import { addHistoryEntry, clearHistory, HISTORY_LIMIT, historyKey, loadHistory } from "./history";
import {
  DEFAULT_PREFS,
  loadDraft,
  loadPrefs,
  loadSelectedSource,
  saveDraft,
  savePrefs,
  saveSelectedSource,
} from "./prefs";

const run = (query: string, over: Partial<{ ok: boolean; duration_ms: number | null; error: string }> = {}) => ({
  query,
  at: "2026-09-17T10:00:00.000Z",
  duration_ms: 12,
  ok: true,
  ...over,
});

describe("query history", () => {
  beforeEach(() => window.localStorage.clear());

  it("starts empty and keeps the newest entry first", () => {
    expect(loadHistory("p1", "s1")).toEqual([]);
    addHistoryEntry("p1", "s1", run("SELECT 1"));
    const list = addHistoryEntry("p1", "s1", run("SELECT 2", { ok: false, error: "Query failed" }));
    expect(list.map((h) => h.query)).toEqual(["SELECT 2", "SELECT 1"]);
    expect(list[0]).toMatchObject({ ok: false, error: "Query failed", duration_ms: 12 });
    expect(list[0].id).not.toBe(list[1].id);
    expect(loadHistory("p1", "s1")).toEqual(list);
  });

  it("is kept per project and source", () => {
    addHistoryEntry("p1", "s1", run("SELECT 1"));
    addHistoryEntry("p1", "s2", run("db.users.find()"));
    expect(loadHistory("p1", "s1").map((h) => h.query)).toEqual(["SELECT 1"]);
    expect(loadHistory("p1", "s2").map((h) => h.query)).toEqual(["db.users.find()"]);
    expect(loadHistory("p2", "s1")).toEqual([]);
  });

  it("moves a re-run query to the top instead of duplicating it", () => {
    addHistoryEntry("p1", "s1", run("SELECT 1"));
    addHistoryEntry("p1", "s1", run("SELECT 2"));
    const list = addHistoryEntry("p1", "s1", run("SELECT 1", { duration_ms: 99 }));
    expect(list.map((h) => h.query)).toEqual(["SELECT 1", "SELECT 2"]);
    expect(list[0].duration_ms).toBe(99);
  });

  it("caps the list at the limit", () => {
    for (let i = 0; i < HISTORY_LIMIT + 10; i++) addHistoryEntry("p1", "s1", run(`SELECT ${i}`));
    const list = loadHistory("p1", "s1");
    expect(list).toHaveLength(HISTORY_LIMIT);
    expect(list[0].query).toBe(`SELECT ${HISTORY_LIMIT + 9}`);
    expect(list[HISTORY_LIMIT - 1].query).toBe("SELECT 10");
  });

  it("ignores corrupt storage and malformed entries", () => {
    window.localStorage.setItem(historyKey("p1", "s1"), "{not json");
    expect(loadHistory("p1", "s1")).toEqual([]);
    window.localStorage.setItem(
      historyKey("p1", "s1"),
      JSON.stringify([{ id: "a", query: "SELECT 1", at: "t", duration_ms: null, ok: true }, { bogus: true }, 42]),
    );
    expect(loadHistory("p1", "s1").map((h) => h.query)).toEqual(["SELECT 1"]);
  });

  it("clears", () => {
    addHistoryEntry("p1", "s1", run("SELECT 1"));
    clearHistory("p1", "s1");
    expect(loadHistory("p1", "s1")).toEqual([]);
  });
});

describe("console preferences", () => {
  beforeEach(() => window.localStorage.clear());

  it("remembers drafts per source and drops empty ones", () => {
    saveDraft("p1", "s1", "SELECT 1");
    saveDraft("p1", "s2", "db.x.find()");
    expect(loadDraft("p1", "s1")).toBe("SELECT 1");
    expect(loadDraft("p1", "s2")).toBe("db.x.find()");
    saveDraft("p1", "s1", "");
    expect(loadDraft("p1", "s1")).toBe("");
  });

  it("remembers the selected source per project", () => {
    expect(loadSelectedSource("p1")).toBeNull();
    saveSelectedSource("p1", "s2");
    expect(loadSelectedSource("p1")).toBe("s2");
    expect(loadSelectedSource("p2")).toBeNull();
  });

  it("falls back to defaults for unknown or missing preferences", () => {
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
    savePrefs({ maxRows: 2000, timeoutSeconds: 120 });
    expect(loadPrefs()).toEqual({ maxRows: 2000, timeoutSeconds: 120 });
    window.localStorage.setItem("deployer.query.prefs", JSON.stringify({ maxRows: 7, timeoutSeconds: "x" }));
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
  });
});
