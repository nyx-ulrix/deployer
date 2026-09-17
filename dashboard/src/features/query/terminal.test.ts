import { describe, expect, it } from "vitest";
import type { DataSource, MongoQueryResponse, SqlQueryResponse } from "../../api/types";
import {
  asciiTable,
  bracketsBalanced,
  findSource,
  helpText,
  mongoText,
  parseCommand,
  promptLabel,
  runOutputText,
  shouldSubmitOnEnter,
  sqlStatementFooter,
  transcriptText,
} from "./terminal";

const source = (over: Partial<DataSource>): DataSource => ({
  id: "s1",
  project_id: "p1",
  name: "Main SQL",
  kind: "sql",
  engine: "mariadb",
  mode: "managed",
  database_name: "p_shop",
  status: "ok",
  status_message: null,
  last_checked_at: null,
  display: { host: null, port: null, username: null, tls: false },
  created_at: "2026-09-01T00:00:00Z",
  ...over,
});

describe("promptLabel", () => {
  it("slugs the name and appends the kind once", () => {
    expect(promptLabel({ name: "Shop", kind: "sql" })).toBe("shop-sql›");
    expect(promptLabel({ name: "Orders DB", kind: "nosql" })).toBe("orders-db-nosql›");
    expect(promptLabel({ name: "Main SQL", kind: "sql" })).toBe("main-sql›");
    expect(promptLabel({ name: "???", kind: "sql" })).toBe("db-sql›");
  });
});

describe("findSource", () => {
  const sources = [source({}), source({ id: "s2", name: "Docs", kind: "nosql", engine: "mongodb" }), source({ id: "s3", name: "Docs archive" })];
  it("matches by name, id, prompt slug or a unique partial name", () => {
    expect(findSource(sources, "main sql")?.id).toBe("s1");
    expect(findSource(sources, '"Docs"')?.id).toBe("s2");
    expect(findSource(sources, "s3")?.id).toBe("s3");
    expect(findSource(sources, "docs-nosql")?.id).toBe("s2");
    expect(findSource(sources, "archive")?.id).toBe("s3");
    expect(findSource(sources, "doc")).toBeNull();
    expect(findSource(sources, "")).toBeNull();
  });
});

describe("parseCommand", () => {
  it("recognises the built-in commands and their aliases", () => {
    expect(parseCommand("\\use Main SQL")).toEqual({ type: "use", name: "Main SQL" });
    expect(parseCommand("use docs;")).toEqual({ type: "use", name: "docs" });
    expect(parseCommand("USE docs")).toEqual({ type: "use", name: "docs" });
    expect(parseCommand("\\list")).toEqual({ type: "list" });
    expect(parseCommand("\\l")).toEqual({ type: "list" });
    expect(parseCommand("\\clear")).toEqual({ type: "clear" });
    expect(parseCommand("\\help")).toEqual({ type: "help" });
    expect(parseCommand("\\?")).toEqual({ type: "help" });
    expect(parseCommand("help")).toEqual({ type: "help" });
    expect(parseCommand("\\rows 2000")).toEqual({ type: "rows", value: 2000, raw: "2000" });
    expect(parseCommand("\\rows 9000")).toEqual({ type: "rows", value: null, raw: "9000" });
    expect(parseCommand("\\timeout 60")).toEqual({ type: "timeout", value: 60, raw: "60" });
    expect(parseCommand("\\timeout abc")).toEqual({ type: "timeout", value: null, raw: "abc" });
    expect(parseCommand("\\nope 1")).toEqual({ type: "unknown", name: "nope" });
  });

  it("treats everything else as a query", () => {
    expect(parseCommand("SELECT 1;")).toBeNull();
    expect(parseCommand("db.users.find()")).toBeNull();
    expect(parseCommand("use x\nSELECT 1")).toBeNull();
    expect(parseCommand("   ")).toBeNull();
    expect(parseCommand("user_count")).toBeNull();
  });
});

describe("bracketsBalanced", () => {
  it("checks brackets while ignoring strings and comments", () => {
    expect(bracketsBalanced("db.users.find({ a: [1, 2] })")).toBe(true);
    expect(bracketsBalanced("db.users.find({ a: [1, 2]")).toBe(false);
    expect(bracketsBalanced("db.users.find({ a: ')' })")).toBe(true);
    expect(bracketsBalanced("db.users.find({ a: '(' ")).toBe(false);
    expect(bracketsBalanced("x = ( // ) comment\n1)")).toBe(true);
    expect(bracketsBalanced("/* ( */ [ ]")).toBe(true);
    expect(bracketsBalanced("/* unterminated ")).toBe(false);
    expect(bracketsBalanced("'open string")).toBe(false);
    expect(bracketsBalanced("`multi\nline`")).toBe(true);
    expect(bracketsBalanced("( ]")).toBe(false);
    expect(bracketsBalanced("")).toBe(true);
  });
});

describe("shouldSubmitOnEnter", () => {
  it("runs SQL only when it ends with a semicolon", () => {
    expect(shouldSubmitOnEnter("sql", "SELECT 1;")).toBe(true);
    expect(shouldSubmitOnEnter("sql", "SELECT 1;  ")).toBe(true);
    expect(shouldSubmitOnEnter("sql", "SELECT 1")).toBe(false);
    expect(shouldSubmitOnEnter("sql", "SELECT *\nFROM t")).toBe(false);
    expect(shouldSubmitOnEnter("sql", "")).toBe(false);
  });

  it("runs MongoDB code when brackets and quotes are balanced", () => {
    expect(shouldSubmitOnEnter("nosql", "db.users.find({})")).toBe(true);
    expect(shouldSubmitOnEnter("nosql", "db.users.find({")).toBe(false);
    expect(shouldSubmitOnEnter("nosql", 'db.users.find({ name: "x')).toBe(false);
  });

  it("always runs built-in commands", () => {
    expect(shouldSubmitOnEnter("sql", "\\help")).toBe(true);
    expect(shouldSubmitOnEnter("sql", "use docs")).toBe(true);
    expect(shouldSubmitOnEnter("nosql", "\\rows 100")).toBe(true);
  });
});

describe("sqlStatementFooter", () => {
  it("prints mysql-style footers", () => {
    expect(
      sqlStatementFooter({ type: "rows", statement: "", columns: ["a"], rows: [[1]], row_count: 1, truncated: false, duration_ms: 12 }, 500),
    ).toBe("1 row in set (0.012 s)");
    expect(
      sqlStatementFooter({ type: "rows", statement: "", columns: ["a"], rows: [], row_count: 0, truncated: false, duration_ms: 1 }, 500),
    ).toBe("Empty set (0.001 s)");
    expect(
      sqlStatementFooter({ type: "rows", statement: "", columns: ["a"], rows: [[1]], row_count: 500, truncated: true, duration_ms: 40 }, 500),
    ).toBe("500 rows in set (0.040 s) · truncated at 500 rows");
    expect(sqlStatementFooter({ type: "count", statement: "", affected_rows: 2, duration_ms: 3 }, 500)).toBe(
      "Query OK, 2 rows affected (0.003 s)",
    );
    expect(sqlStatementFooter({ type: "empty", statement: "", duration_ms: 8 }, 500)).toBe("Query OK (0.008 s)");
    expect(sqlStatementFooter({ type: "error", statement: "", error: { code: "query_failed", message: "bad" } }, 500)).toBe(
      "ERROR: bad",
    );
  });
});

describe("asciiTable", () => {
  it("draws a bordered table with numbers right-aligned and long values clipped", () => {
    expect(asciiTable(["id", "email"], [[1, "a@b.c"], [22, null]])).toBe(
      ["+----+-------+", "| id | email |", "+----+-------+", "|  1 | a@b.c |", "| 22 | NULL  |", "+----+-------+"].join("\n"),
    );
    const clipped = asciiTable(["v"], [["x".repeat(50)]], { maxWidth: 10 });
    expect(clipped.split("\n")[3]).toBe("| xxxxxxxxx… |");
    expect(asciiTable(["a"], [[1], [2], [3]], { maxRows: 2 })).toContain("… 1 more rows");
  });
});

describe("run output text", () => {
  const sql: SqlQueryResponse = {
    kind: "sql",
    engine: "mariadb",
    duration_ms: 20,
    results: [
      { type: "rows", statement: "SELECT id FROM t", columns: ["id"], rows: [[1]], row_count: 1, truncated: false, duration_ms: 3 },
      { type: "count", statement: "UPDATE t SET a = 1", affected_rows: 5, duration_ms: 4 },
    ],
  };
  const mongo: MongoQueryResponse = {
    kind: "nosql",
    engine: "mongodb",
    duration_ms: 640,
    output: "hello\n",
    result: [{ _id: { $oid: "1" }, n: 1 }],
    result_docs: [{ _id: { $oid: "1" }, n: 1 }],
    truncated: false,
    error: null,
  };
  const request = { query: "", max_rows: 500, timeout_seconds: 30 };

  it("renders SQL results with per-statement headers when there are several", () => {
    const text = runOutputText({ status: "done", response: sql, request }, 500);
    expect(text).toContain("-- #1 SELECT id FROM t");
    expect(text).toContain("| id |");
    expect(text).toContain("1 row in set (0.003 s)");
    expect(text).toContain("-- #2 UPDATE t SET a = 1\nQuery OK, 5 rows affected (0.004 s)");
  });

  it("renders MongoDB output, the pretty result and a footer", () => {
    expect(mongoText(mongo, 500)).toBe(`hello\n${JSON.stringify(mongo.result, null, 2)}\n1 document (0.640 s)`);
    expect(mongoText(mongo, 500, true)).toContain("| _id ");
    expect(mongoText({ ...mongo, result: null, result_docs: null, error: { code: "query_failed", message: "boom" } }, 500)).toBe(
      "hello\nERROR: boom\n(0.640 s)",
    );
  });

  it("renders failures and running entries", () => {
    const failure = { code: "query_timeout", title: "Timed out", message: "too slow", offline: false, cancelled: false };
    expect(runOutputText({ status: "failed", failure, error: null, request }, 500)).toBe("ERROR: too slow");
    expect(runOutputText({ status: "running", request }, 500)).toBe("(running…)");
  });

  it("exports the transcript with prompt echoes", () => {
    const prefs = { maxRows: 500, timeoutSeconds: 30 };
    const text = transcriptText(
      [
        { id: 0, kind: "help" },
        { id: 1, kind: "message", tone: "info", text: "Switched to Docs.", input: { prompt: "main-sql›", text: "\\use Docs" } },
        {
          id: 2,
          kind: "run",
          sourceId: "s2",
          sourceName: "Docs",
          sourceKind: "nosql",
          prompt: "docs-nosql›",
          query: "db.t.find()",
          at: "2026-09-17T10:00:00Z",
          run: { status: "done", response: mongo, request },
        },
      ],
      prefs,
    );
    expect(text.startsWith(helpText(prefs))).toBe(true);
    expect(text).toContain("main-sql› \\use Docs\nSwitched to Docs.");
    expect(text).toContain("docs-nosql› db.t.find()\nhello\n");
    expect(helpText(prefs)).toContain("now 500");
    expect(helpText(prefs)).toContain("now 30 s");
  });
});
