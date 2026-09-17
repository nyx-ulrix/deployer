import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_QUERY_CONSOLE_MODE,
  loadQueryConsoleMode,
  QUERY_CONSOLE_MODE_KEY,
  QUERY_CONSOLE_MODES,
  saveQueryConsoleMode,
} from "./consoleMode";

describe("query console mode preference", () => {
  beforeEach(() => window.localStorage.clear());

  it("defaults to the terminal layout", () => {
    expect(DEFAULT_QUERY_CONSOLE_MODE).toBe("terminal");
    expect(loadQueryConsoleMode()).toBe("terminal");
  });

  it("persists the chosen mode in localStorage", () => {
    saveQueryConsoleMode("editor");
    expect(window.localStorage.getItem(QUERY_CONSOLE_MODE_KEY)).toBe("editor");
    expect(loadQueryConsoleMode()).toBe("editor");
    saveQueryConsoleMode("terminal");
    expect(loadQueryConsoleMode()).toBe("terminal");
  });

  it("falls back to the default for unknown stored values", () => {
    window.localStorage.setItem(QUERY_CONSOLE_MODE_KEY, "spreadsheet");
    expect(loadQueryConsoleMode()).toBe("terminal");
  });

  it("describes every selectable mode", () => {
    expect(QUERY_CONSOLE_MODES.map((m) => m.value)).toEqual(["terminal", "editor"]);
    for (const m of QUERY_CONSOLE_MODES) expect(m.description.length).toBeGreaterThan(10);
  });
});
