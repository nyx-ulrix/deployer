import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import type { DataSource, SqlQueryResponse } from "../../api/types";
import { CellOutput, type CellResult } from "./NotebookConsole";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const response: SqlQueryResponse = {
  kind: "sql",
  engine: "mariadb",
  duration_ms: 5,
  results: [{ type: "rows", statement: "SELECT id FROM t", columns: ["id"], rows: [[1]], row_count: 100, truncated: true, duration_ms: 3 }],
};

describe("CellOutput", () => {
  it("shows the row limit the run used, not the live setting (A-174)", async () => {
    document.body.innerHTML = "";
    const el = document.createElement("div");
    document.body.appendChild(el);
    const result: CellResult = {
      run: { status: "done", response, request: { query: "SELECT id FROM t", max_rows: 100, timeout_seconds: 30 } },
      at: "2026-09-01T00:00:00Z",
      text: "SELECT id FROM t",
      collapsed: false,
    };
    await act(async () => {
      createRoot(el).render(<CellOutput result={result} source={{ name: "Main" } as DataSource} onToggle={() => {}} onCancel={() => {}} />);
    });
    expect(el.textContent).toContain("truncated at 100");
  });
});
