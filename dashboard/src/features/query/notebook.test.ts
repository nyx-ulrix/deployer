import { beforeEach, describe, expect, it } from "vitest";
import type { QueryRun, SavedQuery } from "../../api/types";
import {
  attachSaved,
  closeTab,
  detachSaved,
  EMPTY_NOTEBOOK,
  historyRow,
  insertCellAfter,
  loadNotebook,
  moveCell,
  nextUntitledNumber,
  notebookKey,
  openSaved,
  openUntitled,
  parseDocument,
  removeCell,
  saveNotebook,
  serializeDocument,
  setCells,
  splitFolderName,
  tabTitle,
  type NotebookState,
} from "./notebook";

const saved = (over: Partial<SavedQuery> = {}): SavedQuery => ({
  id: "sq1",
  project_id: "p1",
  data_source_id: "s1",
  owner_id: "u1",
  owner_email: "u1@example.com",
  name: "monthly",
  folder: "reports",
  query_text: "SELECT 1;",
  kind: "sql",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  ...over,
});

describe("document ⇄ query_text", () => {
  it("round-trips cells with their ids", () => {
    const cells = [
      { id: "a", text: "SELECT 1;" },
      { id: "b", text: "SELECT 2;" },
    ];
    expect(parseDocument(serializeDocument(cells))).toEqual(cells);
  });

  it("treats a plain snippet as one cell", () => {
    const [cell, ...rest] = parseDocument("SELECT * FROM users;");
    expect(rest).toEqual([]);
    expect(cell.text).toBe("SELECT * FROM users;");
    expect(cell.id).toBeTruthy();
  });

  it("treats malformed or foreign JSON as one cell", () => {
    expect(parseDocument('{"cells": [')).toHaveLength(1);
    expect(parseDocument('{"cells": [')[0].text).toBe('{"cells": [');
    expect(parseDocument('{"foo": 1}')[0].text).toBe('{"foo": 1}');
    expect(parseDocument("[1,2]")[0].text).toBe("[1,2]");
  });

  it("gives an empty document one empty cell and drops malformed cells", () => {
    expect(parseDocument('{"cells": []}')).toEqual([{ id: expect.any(String), text: "" }]);
    expect(parseDocument('{"cells": [{"id": "a", "text": "x"}, {"id": 1}]}')).toEqual([{ id: "a", text: "x" }]);
  });
});

describe("cells", () => {
  const cells = [
    { id: "a", text: "1" },
    { id: "b", text: "2" },
  ];

  it("inserts after a cell, or at the end", () => {
    expect(insertCellAfter(cells, "a", { id: "c", text: "" }).map((c) => c.id)).toEqual(["a", "c", "b"]);
    expect(insertCellAfter(cells, null, { id: "c", text: "" }).map((c) => c.id)).toEqual(["a", "b", "c"]);
    expect(insertCellAfter(cells, "missing", { id: "c", text: "" }).map((c) => c.id)).toEqual(["a", "b", "c"]);
  });

  it("removing the last cell leaves one empty cell", () => {
    expect(removeCell(cells, "a").map((c) => c.id)).toEqual(["b"]);
    const left = removeCell([cells[0]], "a");
    expect(left).toHaveLength(1);
    expect(left[0].text).toBe("");
  });

  it("moves within bounds", () => {
    expect(moveCell(cells, "b", -1).map((c) => c.id)).toEqual(["b", "a"]);
    expect(moveCell(cells, "a", -1).map((c) => c.id)).toEqual(["a", "b"]);
    expect(moveCell(cells, "b", 1).map((c) => c.id)).toEqual(["a", "b"]);
  });
});

describe("tabs", () => {
  it("opening a saved query twice focuses the existing tab", () => {
    let s = openSaved(EMPTY_NOTEBOOK, saved(), null);
    s = openUntitled(s, "s1");
    expect(s.tabs).toHaveLength(2);
    expect(s.activeId).toBe(s.tabs[1].id);
    s = openSaved(s, saved(), null);
    expect(s.tabs).toHaveLength(2);
    expect(s.activeId).toBe(s.tabs[0].id);
    expect(s.tabs[0].cells[0].text).toBe("SELECT 1;");
    expect(s.tabs[0].sourceId).toBe("s1");
  });

  it("falls back to the given source when the snippet has none", () => {
    const s = openSaved(EMPTY_NOTEBOOK, saved({ data_source_id: null }), "s9");
    expect(s.tabs[0].sourceId).toBe("s9");
  });

  it("numbers untitled tabs skipping the numbers in use", () => {
    let s = openUntitled(EMPTY_NOTEBOOK, null);
    s = openUntitled(s, null);
    s = openUntitled(s, null);
    expect(s.tabs.map(tabTitle)).toEqual(["Untitled 1", "Untitled 2", "Untitled 3"]);
    s = closeTab(s, s.tabs[1].id);
    s = openUntitled(s, null);
    expect(s.tabs.map(tabTitle)).toEqual(["Untitled 1", "Untitled 3", "Untitled 2"]);
    expect(nextUntitledNumber(s.tabs)).toBe(4);
  });

  it("closing picks the neighbour that takes its place, or the previous one at the end", () => {
    let s = openUntitled(EMPTY_NOTEBOOK, null);
    s = openUntitled(s, null);
    s = openUntitled(s, null);
    const [a, b, c] = s.tabs.map((t) => t.id);
    s = { ...s, activeId: b };
    s = closeTab(s, b);
    expect(s.tabs.map((t) => t.id)).toEqual([a, c]);
    expect(s.activeId).toBe(c);
    s = closeTab(s, c);
    expect(s.activeId).toBe(a);
    s = closeTab(s, a);
    expect(s).toEqual({ tabs: [], activeId: null });
  });

  it("closing an inactive tab keeps the active one", () => {
    let s = openUntitled(EMPTY_NOTEBOOK, null);
    s = openUntitled(s, null);
    const [a, b] = s.tabs.map((t) => t.id);
    s = closeTab(s, a);
    expect(s.activeId).toBe(b);
    expect(closeTab(s, "nope")).toBe(s);
  });

  it("tracks dirty: edits set it, save clears it, deletion of the snippet detaches", () => {
    let s = openSaved(EMPTY_NOTEBOOK, saved(), null);
    const id = s.tabs[0].id;
    expect(s.tabs[0].dirty).toBe(false);
    s = setCells(s, id, [{ id: "a", text: "SELECT 2;" }]);
    expect(s.tabs[0].dirty).toBe(true);
    s = attachSaved(s, id, { id: "sq1", name: "renamed", folder: null });
    expect(s.tabs[0]).toMatchObject({ dirty: false, name: "renamed", folder: null, savedId: "sq1" });
    s = detachSaved(s, "sq1");
    expect(s.tabs[0]).toMatchObject({ dirty: true, savedId: null, name: null, untitled: 1 });
    expect(tabTitle(s.tabs[0])).toBe("Untitled 1");
    expect(detachSaved(s, "other")).toBe(s);
  });
});

describe("splitFolderName", () => {
  it("splits folder/name typed into the name field", () => {
    expect(splitFolderName("reports/monthly sales")).toEqual({ folder: "reports", name: "monthly sales" });
    expect(splitFolderName(" a/b /c ", "ignored")).toEqual({ folder: "a/b", name: "c" });
  });

  it("keeps the folder field for plain names and blanks empty folders", () => {
    expect(splitFolderName("monthly", "reports")).toEqual({ folder: "reports", name: "monthly" });
    expect(splitFolderName("monthly", "  ")).toEqual({ folder: null, name: "monthly" });
    expect(splitFolderName("/monthly")).toEqual({ folder: null, name: "monthly" });
  });
});

describe("historyRow", () => {
  const run = (over: Partial<QueryRun> = {}): QueryRun => ({
    id: "r1",
    project_id: "p1",
    data_source_id: "s1",
    source_name: "main",
    kind: "sql",
    engine: "mariadb",
    user_id: "u1",
    user_email: "u1@example.com",
    query_text: "\n  \nSELECT *\nFROM users;",
    status: "ok",
    statements: 1,
    rows: 3,
    affected_rows: null,
    duration_ms: 8,
    error_message: null,
    read_only: true,
    layout: "editor",
    created_at: "2026-09-22T10:00:00Z",
    ...over,
  });

  it("shows the first non-blank line, a tone, the duration and a relative time", () => {
    const now = Date.parse("2026-09-22T10:05:00Z");
    expect(historyRow(run(), now)).toEqual({ line: "SELECT *", tone: "success", duration: "8 ms", when: "5 minutes ago" });
    expect(historyRow(run({ status: "error" }), now).tone).toBe("danger");
    expect(historyRow(run({ status: "timeout" }), now).tone).toBe("warning");
    expect(historyRow(run({ status: "refused" }), now).tone).toBe("muted");
  });

  it("truncates very long first lines", () => {
    const { line } = historyRow(run({ query_text: "x".repeat(400) }));
    expect(line).toHaveLength(160);
    expect(line.endsWith("…")).toBe(true);
  });
});

describe("persistence", () => {
  beforeEach(() => window.localStorage.clear());

  it("round-trips tabs and the active tab, and skips oversized cells", () => {
    let s: NotebookState = openSaved(EMPTY_NOTEBOOK, saved(), null);
    s = openUntitled(s, "s2", [
      { id: "small", text: "SELECT 1;" },
      { id: "huge", text: "x".repeat(200_001) },
    ]);
    saveNotebook("p1", s);
    const back = loadNotebook("p1");
    expect(back.activeId).toBe(s.activeId);
    expect(back.tabs).toHaveLength(2);
    expect(back.tabs[0]).toEqual(s.tabs[0]);
    expect(back.tabs[1].cells.map((c) => c.id)).toEqual(["small"]);
  });

  it("ignores corrupt storage and removes the key when no tabs are left", () => {
    window.localStorage.setItem(notebookKey("p1"), "{not json");
    expect(loadNotebook("p1")).toEqual(EMPTY_NOTEBOOK);
    window.localStorage.setItem(notebookKey("p1"), JSON.stringify({ tabs: [{ id: "t", cells: "nope", dirty: false }], activeId: "t" }));
    expect(loadNotebook("p1")).toEqual(EMPTY_NOTEBOOK);
    saveNotebook("p1", EMPTY_NOTEBOOK);
    expect(window.localStorage.getItem(notebookKey("p1"))).toBeNull();
  });
});
