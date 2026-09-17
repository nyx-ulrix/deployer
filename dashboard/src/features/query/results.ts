import { errorMessage, isApiError } from "../../api/client";
import type { DataSourceKind, JsonObject, JsonValue, MongoQueryResponse, QueryResponse, SqlQueryResponse } from "../../api/types";
import type { Cell } from "./csv";

export type CellKind = "null" | "missing" | "string" | "number" | "boolean" | "json" | "binary";

function base64Size(b64: string): number {
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, "");
  return Math.floor((clean.length * 3) / 4);
}

/** Text + kind for a grid cell. `{"$base64": …}` (bytes) shows as a size; objects as compact JSON. */
export function formatCell(v: Cell): { text: string; kind: CellKind } {
  if (v === undefined) return { text: "", kind: "missing" };
  if (v === null) return { text: "NULL", kind: "null" };
  if (typeof v === "string") return { text: v, kind: "string" };
  if (typeof v === "number") return { text: String(v), kind: "number" };
  if (typeof v === "boolean") return { text: v ? "true" : "false", kind: "boolean" };
  if (!Array.isArray(v) && Object.keys(v).length === 1 && typeof v.$base64 === "string") {
    return { text: `<binary, ${base64Size(v.$base64)} bytes>`, kind: "binary" };
  }
  return { text: JSON.stringify(v), kind: "json" };
}

/** Relaxed Extended JSON wrappers shown as one leaf in the JSON tree, e.g. `{"$oid": "…"}` → `ObjectId("…")`. */
export function ejsonLeaf(v: JsonValue): string | null {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return null;
  const keys = Object.keys(v);
  if (keys.length !== 1) return null;
  const key = keys[0];
  const inner = v[key];
  const str = typeof inner === "string" ? inner : null;
  const obj = typeof inner === "object" && inner !== null && !Array.isArray(inner) ? inner : null;
  switch (key) {
    case "$oid":
      return str === null ? null : `ObjectId("${str}")`;
    case "$date":
      if (str !== null) return `ISODate("${str}")`;
      return obj && typeof obj.$numberLong === "string" ? `Date(${obj.$numberLong})` : null;
    case "$numberLong":
      return str === null ? null : `Long("${str}")`;
    case "$numberDecimal":
      return str === null ? null : `Decimal128("${str}")`;
    case "$numberInt":
    case "$numberDouble":
      return str;
    case "$uuid":
      return str === null ? null : `UUID("${str}")`;
    case "$binary":
      return obj && typeof obj.base64 === "string" ? `Binary(${base64Size(obj.base64)} bytes)` : null;
    case "$regularExpression":
      return obj && typeof obj.pattern === "string" ? `/${obj.pattern}/${typeof obj.options === "string" ? obj.options : ""}` : null;
    default:
      return null;
  }
}

/** Full text for an expanded cell (objects pretty-printed). */
export function expandedCellText(v: Cell): string {
  const { text, kind } = formatCell(v);
  return kind === "json" ? JSON.stringify(v, null, 2) : text;
}

/** One-line label for a statement (whitespace collapsed, truncated with an ellipsis). */
export function statementLabel(statement: string, max = 90): string {
  const one = statement.replace(/\s+/g, " ").trim();
  return one.length > max ? `${one.slice(0, Math.max(1, max - 1)).trimEnd()}…` : one;
}

export type SqlSummary = { statements: number; rowSets: number; rows: number; affected: number; errors: number };

export function summarizeSql(res: SqlQueryResponse): SqlSummary {
  const s: SqlSummary = { statements: res.results.length, rowSets: 0, rows: 0, affected: 0, errors: 0 };
  for (const r of res.results) {
    if (r.type === "rows") {
      s.rowSets += 1;
      s.rows += r.row_count;
    } else if (r.type === "count") s.affected += r.affected_rows;
    else if (r.type === "error") s.errors += 1;
  }
  return s;
}

/** Short summary line, e.g. "3 statements · 120 rows · 1 error". */
export function sqlSummaryText(s: SqlSummary): string {
  const parts = [`${s.statements} ${s.statements === 1 ? "statement" : "statements"}`];
  if (s.rowSets > 0) parts.push(`${s.rows.toLocaleString()} ${s.rows === 1 ? "row" : "rows"}`);
  if (s.affected > 0) parts.push(`${s.affected.toLocaleString()} affected`);
  if (s.errors > 0) parts.push(`${s.errors} ${s.errors === 1 ? "error" : "errors"}`);
  return parts.join(" · ");
}

/** Short summary line for a MongoDB run, e.g. "12 documents · 2 lines printed". */
export function mongoSummaryText(res: MongoQueryResponse): string {
  const parts: string[] = [];
  if (res.error) parts.push("error");
  if (res.result_docs) {
    const n = res.result_docs.length;
    parts.push(`${n.toLocaleString()} ${n === 1 ? "document" : "documents"}`);
  } else if (res.result !== null) parts.push("result");
  else if (!res.error) parts.push("no value");
  const lines = outputLines(res.output).length;
  if (lines > 0) parts.push(`${lines} ${lines === 1 ? "line" : "lines"} printed`);
  return parts.join(" · ");
}

/** Message of the first failed statement / the script error, or null when everything succeeded. */
export function firstError(res: QueryResponse): string | null {
  if (res.kind === "nosql") return res.error?.message ?? null;
  for (const r of res.results) if (r.type === "error") return r.error.message;
  return null;
}

/** The selection when there is a non-blank one, else the whole document (Run is selection-aware). */
export function pickRunnable(doc: string, from: number, to: number): string {
  const [a, b] = from <= to ? [from, to] : [to, from];
  const selected = doc.slice(a, b);
  return selected.trim() ? selected : doc;
}

/** Flat table for documents: columns = union of top-level keys in first-seen order (`_id` first). */
export function docsToTable(docs: readonly JsonObject[]): { columns: string[]; rows: Cell[][] } {
  const seen = new Set<string>();
  const columns: string[] = [];
  for (const d of docs) {
    for (const k of Object.keys(d)) {
      if (!seen.has(k)) {
        seen.add(k);
        columns.push(k);
      }
    }
  }
  if (seen.has("_id") && columns[0] !== "_id") {
    columns.splice(columns.indexOf("_id"), 1);
    columns.unshift("_id");
  }
  const rows = docs.map((d) => columns.map((c) => (Object.prototype.hasOwnProperty.call(d, c) ? d[c] : undefined)));
  return { columns, rows };
}

/** Console output as lines (trailing newlines dropped; empty output → no lines). */
export function outputLines(output: string): string[] {
  const text = output.replace(/\r\n?/g, "\n").replace(/\n+$/, "");
  return text ? text.split("\n") : [];
}

/** Starter query inserted from the entity sidebar. PostgreSQL quotes identifiers with `"`, MySQL/MariaDB with backticks. */
export function starterQuery(kind: DataSourceKind, engine: string, name: string): string {
  if (kind === "nosql") return `db.getCollection(${JSON.stringify(name)}).find({}).limit(20)`;
  if (engine === "postgresql") return `SELECT * FROM "${name.replace(/"/g, '""')}" LIMIT 100;`;
  return `SELECT * FROM \`${name.replace(/`/g, "``")}\` LIMIT 100;`;
}

/** "12 ms", "1.24 s", "12.5 s". */
export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  return `${s < 10 ? s.toFixed(2) : s.toFixed(1)} s`;
}

export type QueryFailure = {
  code: string;
  title: string;
  message: string;
  /** `device_offline`: the source lives on a host device that isn't connected. */
  offline: boolean;
  /** The request never reached a result because the user cancelled it. */
  cancelled: boolean;
};

const failure = (code: string, title: string, message: string, extra: Partial<QueryFailure> = {}): QueryFailure => ({
  code,
  title,
  message,
  offline: false,
  cancelled: false,
  ...extra,
});

/** Friendly title + message for a failed run (QUERY_CONSOLE.md error codes). */
export function describeQueryError(e: unknown, ctx: { timeoutSeconds: number }): QueryFailure {
  if (e instanceof DOMException && e.name === "AbortError") {
    return failure("cancelled", "Cancelled", "The query was cancelled. The database may still finish the statement it was on.", {
      cancelled: true,
    });
  }
  if (isApiError(e)) {
    switch (e.code) {
      case "read_only_role":
        return failure(
          e.code,
          "Read-only access",
          "Viewers can only run read-only queries (SELECT, SHOW, EXPLAIN…). Ask a developer or admin to run this one.",
        );
      case "device_offline":
        return failure(
          e.code,
          "The host device is offline",
          "This database lives on a host device that isn't connected right now. Make sure the PC is switched on and Deployer is running on it.",
          { offline: true },
        );
      case "database_unavailable":
        return failure(
          e.code,
          "Database unavailable",
          "The database isn't reachable right now. Check it on the Databases tab and try again.",
        );
      case "query_timeout":
        return failure(
          e.code,
          "Query timed out",
          `The query took longer than ${ctx.timeoutSeconds} s and was stopped. Narrow it down or pick a longer timeout.`,
        );
      case "mongosh_unavailable":
        return failure(
          e.code,
          "MongoDB shell unavailable",
          "This server doesn't have the MongoDB shell (mongosh), so shell code can't run here. You can still browse and edit documents on the Data tab.",
        );
      case "too_many_queries":
        return failure(e.code, "Too many queries", "Too many queries are running at the same time. Wait a moment and try again.");
      case "validation_error":
        return failure(e.code, "Invalid request", e.message || "The query or its options were rejected.");
      case "query_failed":
        return failure(e.code, "Query failed", e.message || "The database rejected the query.");
      case "forbidden":
        return failure(e.code, "Not allowed", e.message || "You don't have access to this database.");
      case "not_found":
        return failure(e.code, "Database not found", "This database no longer exists. Pick another one.");
      case "network_error":
        return failure(e.code, "Connection lost", e.message);
      default:
        return failure(e.code, "Query failed", e.message || `Request failed (${e.status}).`);
    }
  }
  return failure("unknown", "Query failed", errorMessage(e));
}
