import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { MongoQueryResponse, SqlQueryResponse } from "../../api/types";
import {
  describeQueryError,
  docsToTable,
  ejsonLeaf,
  expandedCellText,
  firstError,
  formatCell,
  formatMs,
  mongoSummaryText,
  outputLines,
  pickRunnable,
  sqlSummaryText,
  starterQuery,
  statementLabel,
  summarizeSql,
} from "./results";

describe("formatCell", () => {
  it("classifies values the way the grid renders them", () => {
    expect(formatCell(null)).toEqual({ text: "NULL", kind: "null" });
    expect(formatCell(undefined)).toEqual({ text: "", kind: "missing" });
    expect(formatCell("hi")).toEqual({ text: "hi", kind: "string" });
    expect(formatCell(3.5)).toEqual({ text: "3.5", kind: "number" });
    expect(formatCell(false)).toEqual({ text: "false", kind: "boolean" });
    expect(formatCell({ a: [1] })).toEqual({ text: '{"a":[1]}', kind: "json" });
  });

  it("shows encoded bytes as a size instead of base64 noise", () => {
    expect(formatCell({ $base64: "AAECAwQ=" })).toEqual({ text: "<binary, 5 bytes>", kind: "binary" });
    // Not the encode_value shape → plain JSON.
    expect(formatCell({ $base64: "AAEC", other: 1 }).kind).toBe("json");
  });

  it("pretty-prints objects when expanded", () => {
    expect(expandedCellText({ a: 1 })).toBe('{\n  "a": 1\n}');
    expect(expandedCellText("plain")).toBe("plain");
  });
});

describe("ejsonLeaf", () => {
  it("renders relaxed Extended JSON wrappers like mongosh", () => {
    expect(ejsonLeaf({ $oid: "65f0c0ffee0000000000abcd" })).toBe('ObjectId("65f0c0ffee0000000000abcd")');
    expect(ejsonLeaf({ $date: "2026-09-17T10:00:00Z" })).toBe('ISODate("2026-09-17T10:00:00Z")');
    expect(ejsonLeaf({ $date: { $numberLong: "1700000000000" } })).toBe("Date(1700000000000)");
    expect(ejsonLeaf({ $numberDecimal: "19.99" })).toBe('Decimal128("19.99")');
    expect(ejsonLeaf({ $binary: { base64: "AAECAwQ=", subType: "00" } })).toBe("Binary(5 bytes)");
    expect(ejsonLeaf({ $regularExpression: { pattern: "^a", options: "i" } })).toBe("/^a/i");
  });

  it("leaves ordinary objects alone", () => {
    expect(ejsonLeaf({ $oid: 1 })).toBeNull();
    expect(ejsonLeaf({ a: 1 })).toBeNull();
    expect(ejsonLeaf({ $oid: "x", extra: 1 })).toBeNull();
    expect(ejsonLeaf([1])).toBeNull();
    expect(ejsonLeaf("s")).toBeNull();
  });
});

describe("statementLabel", () => {
  it("collapses whitespace and truncates", () => {
    expect(statementLabel("SELECT   *\n  FROM users")).toBe("SELECT * FROM users");
    expect(statementLabel("SELECT * FROM a_very_long_table_name", 12)).toBe("SELECT * FR…");
  });
});

describe("summarizeSql", () => {
  const res: SqlQueryResponse = {
    kind: "sql",
    engine: "mariadb",
    duration_ms: 20,
    results: [
      { type: "rows", statement: "SELECT 1", columns: ["a"], rows: [[1], [2]], row_count: 2, truncated: false, duration_ms: 3 },
      { type: "count", statement: "UPDATE t", affected_rows: 5, duration_ms: 4 },
      { type: "empty", statement: "CREATE TABLE x (id int)", duration_ms: 8 },
      { type: "error", statement: "SELEC", error: { code: "query_failed", message: "syntax" } },
    ],
  };

  it("counts rows, affected rows and errors", () => {
    const s = summarizeSql(res);
    expect(s).toEqual({ statements: 4, rowSets: 1, rows: 2, affected: 5, errors: 1 });
    expect(sqlSummaryText(s)).toBe("4 statements · 2 rows · 5 affected · 1 error");
    expect(sqlSummaryText(summarizeSql({ ...res, results: [res.results[2]] }))).toBe("1 statement");
  });

  it("finds the first failed statement", () => {
    expect(firstError(res)).toBe("syntax");
    expect(firstError({ ...res, results: res.results.slice(0, 2) })).toBeNull();
  });
});

describe("mongoSummaryText", () => {
  const base: MongoQueryResponse = {
    kind: "nosql",
    engine: "mongodb",
    duration_ms: 5,
    output: "",
    result: null,
    result_docs: null,
    truncated: false,
    error: null,
  };

  it("describes documents, plain results, printed lines and errors", () => {
    expect(mongoSummaryText(base)).toBe("no value");
    expect(mongoSummaryText({ ...base, result: [{ a: 1 }], result_docs: [{ a: 1 }], output: "hi\nthere\n" })).toBe(
      "1 document · 2 lines printed",
    );
    expect(mongoSummaryText({ ...base, result: 42 })).toBe("result");
    expect(mongoSummaryText({ ...base, error: { code: "query_failed", message: "x" } })).toBe("error");
    expect(firstError({ ...base, error: { code: "query_failed", message: "boom" } })).toBe("boom");
    expect(firstError(base)).toBeNull();
  });
});

describe("pickRunnable", () => {
  const doc = "SELECT 1;\nSELECT 2;";
  it("runs the selection when there is one, else everything", () => {
    expect(pickRunnable(doc, 0, 0)).toBe(doc);
    expect(pickRunnable(doc, 10, 19)).toBe("SELECT 2;");
    expect(pickRunnable(doc, 19, 10)).toBe("SELECT 2;");
  });
  it("ignores a whitespace-only selection", () => {
    expect(pickRunnable(doc, 9, 10)).toBe(doc);
  });
});

describe("docsToTable", () => {
  it("unions top-level keys, puts _id first and marks missing keys", () => {
    const t = docsToTable([
      { name: "a", _id: { $oid: "1" } },
      { _id: { $oid: "2" }, age: 3, name: null },
    ]);
    expect(t.columns).toEqual(["_id", "name", "age"]);
    expect(t.rows).toEqual([
      [{ $oid: "1" }, "a", undefined],
      [{ $oid: "2" }, null, 3],
    ]);
  });
  it("handles no documents", () => {
    expect(docsToTable([])).toEqual({ columns: [], rows: [] });
  });
});

describe("outputLines", () => {
  it("splits console output and drops trailing newlines", () => {
    expect(outputLines("")).toEqual([]);
    expect(outputLines("a\r\nb\n\n")).toEqual(["a", "b"]);
    expect(outputLines("one")).toEqual(["one"]);
  });
});

describe("starterQuery", () => {
  it("quotes identifiers per engine", () => {
    expect(starterQuery("sql", "mariadb", "users")).toBe("SELECT * FROM `users` LIMIT 100;");
    expect(starterQuery("sql", "mysql", "we`ird")).toBe("SELECT * FROM `we``ird` LIMIT 100;");
    expect(starterQuery("sql", "postgresql", "Users")).toBe('SELECT * FROM "Users" LIMIT 100;');
    expect(starterQuery("nosql", "mongodb", "my-events")).toBe('db.getCollection("my-events").find({}).limit(20)');
  });
});

describe("formatMs", () => {
  it("picks sensible units", () => {
    expect(formatMs(12)).toBe("12 ms");
    expect(formatMs(1234)).toBe("1.23 s");
    expect(formatMs(12345)).toBe("12.3 s");
    expect(formatMs(null)).toBe("—");
  });
});

describe("describeQueryError", () => {
  const ctx = { timeoutSeconds: 30 };
  const api = (status: number, code: string, message = "msg") => new ApiError(status, code, message);

  it("maps the console's error codes to friendly messages", () => {
    expect(describeQueryError(api(403, "read_only_role"), ctx)).toMatchObject({ title: "Read-only access", offline: false });
    expect(describeQueryError(api(503, "device_offline"), ctx)).toMatchObject({ title: "The host device is offline", offline: true });
    expect(describeQueryError(api(503, "database_unavailable"), ctx).title).toBe("Database unavailable");
    expect(describeQueryError(api(504, "query_timeout"), ctx).message).toContain("30 s");
    expect(describeQueryError(api(501, "mongosh_unavailable"), ctx).message).toContain("mongosh");
    expect(describeQueryError(api(429, "too_many_queries"), ctx).title).toBe("Too many queries");
  });

  it("passes the API's own message through for query and validation errors", () => {
    expect(describeQueryError(api(400, "query_failed", "Unknown column 'x'"), ctx).message).toBe("Unknown column 'x'");
    expect(describeQueryError(api(422, "validation_error", "max_rows too big"), ctx).message).toBe("max_rows too big");
    expect(describeQueryError(api(500, "server_error", "boom"), ctx)).toMatchObject({ title: "Query failed", message: "boom" });
  });

  it("recognises a cancelled request and unknown errors", () => {
    expect(describeQueryError(new DOMException("aborted", "AbortError"), ctx).cancelled).toBe(true);
    expect(describeQueryError(new Error("weird"), ctx)).toMatchObject({ title: "Query failed", message: "weird" });
  });
});
