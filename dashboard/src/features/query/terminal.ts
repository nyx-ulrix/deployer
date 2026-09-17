import type {
  DataSource,
  DataSourceKind,
  MongoQueryResponse,
  QueryRequest,
  QueryResponse,
  SqlStatementResult,
} from "../../api/types";
import { pretty } from "../data/json";
import type { Cell } from "./csv";
import type { QueryPrefs } from "./prefs";
import { docsToTable, formatCell, outputLines, statementLabel, type QueryFailure } from "./results";

// ---- Transcript entries (shared by the terminal and editor layouts) ----

export type RunState =
  | { status: "running"; request: QueryRequest }
  | { status: "done"; response: QueryResponse; request: QueryRequest }
  | { status: "failed"; failure: QueryFailure; error: unknown; request: QueryRequest };

export type EchoInput = { prompt: string; text: string };

export type RunEntry = {
  id: number;
  kind: "run";
  sourceId: string;
  sourceName: string;
  sourceKind: DataSourceKind;
  prompt: string;
  query: string;
  /** ISO time the query was started. */
  at: string;
  run: RunState;
};

export type ConsoleEntry =
  | { id: number; kind: "help"; input?: EchoInput }
  | { id: number; kind: "message"; tone: "info" | "error"; text: string; input?: EchoInput }
  | RunEntry;

// ---- Prompt ----

/** `main-sql›` / `docs-nosql›`: the source name slugified plus its kind. */
export function promptLabel(source: Pick<DataSource, "name" | "kind">): string {
  const slug =
    source.name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "db";
  const suffix = `-${source.kind}`;
  return `${slug.endsWith(suffix) ? slug : slug + suffix}›`;
}

/** Find a source by name (case-insensitive), id, prompt slug, or a unique partial name. */
export function findSource(sources: readonly DataSource[], name: string): DataSource | null {
  const q = name.trim().replace(/^["'`]|["'`]$/g, "").toLowerCase();
  if (!q) return null;
  const exact = sources.find((s) => s.name.toLowerCase() === q || s.id.toLowerCase() === q);
  if (exact) return exact;
  const bySlug = sources.find((s) => promptLabel(s).replace(/›$/, "") === q || promptLabel(s).replace(/-(sql|nosql)›$/, "") === q);
  if (bySlug) return bySlug;
  const partial = sources.filter((s) => s.name.toLowerCase().includes(q));
  return partial.length === 1 ? partial[0] : null;
}

// ---- Built-in commands ----

export type ConsoleCommand =
  | { type: "use"; name: string }
  | { type: "list" }
  | { type: "clear" }
  | { type: "help" }
  | { type: "rows"; value: number | null; raw: string }
  | { type: "timeout"; value: number | null; raw: string }
  | { type: "unknown"; name: string };

function intIn(raw: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return n >= min && n <= max ? n : null;
}

/**
 * Commands typed at the prompt: `\use <name>` (also `use <name>`), `\list`, `\clear`, `\rows <n>`,
 * `\timeout <s>`, `\help`. Anything else (including multi-line text) is a query → null.
 */
export function parseCommand(text: string): ConsoleCommand | null {
  const t = text.trim().replace(/;\s*$/, "").trim();
  if (!t || t.includes("\n")) return null;
  const bareUse = /^use\s+(.+)$/i.exec(t);
  if (bareUse) return { type: "use", name: bareUse[1].trim() };
  if (/^help$/i.test(t)) return { type: "help" };
  if (!t.startsWith("\\")) return null;
  const m = /^\\(\S*)\s*(.*)$/.exec(t);
  const name = (m?.[1] ?? "").toLowerCase();
  const arg = (m?.[2] ?? "").trim();
  switch (name) {
    case "use":
    case "u":
      return { type: "use", name: arg };
    case "list":
    case "l":
    case "ls":
      return { type: "list" };
    case "clear":
    case "c":
      return { type: "clear" };
    case "help":
    case "h":
    case "?":
      return { type: "help" };
    case "rows":
      return { type: "rows", value: intIn(arg, 1, 5000), raw: arg };
    case "timeout":
      return { type: "timeout", value: intIn(arg, 1, 120), raw: arg };
    default:
      return { type: "unknown", name };
  }
}

// ---- Enter rule ----

/** True when every `(`, `[`, `{` is closed and no string or block comment is left open (JS-aware). */
export function bracketsBalanced(code: string): boolean {
  const pairs: Record<string, string> = { ")": "(", "]": "[", "}": "{" };
  const stack: string[] = [];
  const n = code.length;
  let i = 0;
  while (i < n) {
    const ch = code[i];
    const next = code[i + 1];
    if (ch === "/" && next === "/") {
      while (i < n && code[i] !== "\n") i++;
      continue;
    }
    if (ch === "/" && next === "*") {
      const end = code.indexOf("*/", i + 2);
      if (end === -1) return false;
      i = end + 2;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === "`") {
      let j = i + 1;
      let closed = false;
      while (j < n) {
        const c = code[j];
        if (c === "\\") {
          j += 2;
          continue;
        }
        if (c === ch) {
          closed = true;
          break;
        }
        if (c === "\n" && ch !== "`") break;
        j++;
      }
      if (!closed) return false;
      i = j + 1;
      continue;
    }
    if (ch === "(" || ch === "[" || ch === "{") stack.push(ch);
    else if (ch in pairs && stack.pop() !== pairs[ch]) return false;
    i++;
  }
  return stack.length === 0;
}

/**
 * Whether plain Enter runs the input: commands always; SQL when the text ends with `;`; MongoDB when
 * brackets and quotes are balanced. Otherwise Enter inserts a newline.
 */
export function shouldSubmitOnEnter(kind: DataSourceKind, text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  if (parseCommand(t)) return true;
  if (kind === "sql") return t.endsWith(";");
  return bracketsBalanced(t);
}

// ---- Output text (footers, copy, transcript export) ----

/** "(0.012 s)" like the shells print. */
export function seconds(ms: number | undefined): string {
  return ms === undefined ? "" : ` (${(ms / 1000).toFixed(3)} s)`;
}

/** mysql-style footer for one statement: "3 rows in set (0.012 s)", "Query OK, 2 rows affected (0.003 s)"… */
export function sqlStatementFooter(r: SqlStatementResult, maxRows: number): string {
  switch (r.type) {
    case "rows": {
      const base = r.row_count === 0 ? `Empty set${seconds(r.duration_ms)}` : `${r.row_count.toLocaleString()} ${r.row_count === 1 ? "row" : "rows"} in set${seconds(r.duration_ms)}`;
      return r.truncated ? `${base} · truncated at ${maxRows.toLocaleString()} rows` : base;
    }
    case "count":
      return `Query OK, ${r.affected_rows.toLocaleString()} ${r.affected_rows === 1 ? "row" : "rows"} affected${seconds(r.duration_ms)}`;
    case "empty":
      return `Query OK${seconds(r.duration_ms)}`;
    case "error":
      return `ERROR: ${r.error.message}`;
  }
}

export function mongoFooter(res: MongoQueryResponse, maxRows: number): string {
  const parts: string[] = [];
  if (res.result_docs) {
    const n = res.result_docs.length;
    parts.push(`${n.toLocaleString()} ${n === 1 ? "document" : "documents"}`);
  }
  if (res.truncated) parts.push(`truncated at ${maxRows.toLocaleString()}`);
  return `${parts.join(" · ")}${seconds(res.duration_ms)}`.trim();
}

/** Fixed-width table like the mysql client prints (numbers right-aligned, long cells cut). */
export function asciiTable(
  columns: readonly string[],
  rows: readonly (readonly Cell[])[],
  { maxWidth = 40, maxRows = 500 }: { maxWidth?: number; maxRows?: number } = {},
): string {
  const clip = (s: string) => (s.length > maxWidth ? `${s.slice(0, maxWidth - 1)}…` : s);
  const shown = rows.slice(0, maxRows);
  const cells = shown.map((row) => columns.map((_, i) => formatCell(row[i])));
  const widths = columns.map((c, i) => Math.max(clip(c).length, ...cells.map((r) => clip(r[i].text).length)));
  const line = `+${widths.map((w) => "-".repeat(w + 2)).join("+")}+`;
  const fmt = (text: string, i: number, right: boolean) => {
    const t = clip(text);
    const pad = " ".repeat(widths[i] - t.length);
    return right ? ` ${pad}${t} ` : ` ${t}${pad} `;
  };
  const out = [line, `|${columns.map((c, i) => fmt(c, i, false)).join("|")}|`, line];
  for (const r of cells) out.push(`|${r.map((cell, i) => fmt(cell.text, i, cell.kind === "number")).join("|")}|`);
  if (cells.length > 0) out.push(line);
  if (rows.length > shown.length) out.push(`… ${(rows.length - shown.length).toLocaleString()} more rows`);
  return out.join("\n");
}

export function helpText(prefs: QueryPrefs): string {
  return [
    "Deployer query console — type SQL or MongoDB shell code at the prompt.",
    "",
    "  Enter         runs when the statement ends with ; (SQL) or brackets are balanced (MongoDB)",
    "  Shift+Enter   inserts a newline · Ctrl+Enter always runs · Tab accepts a completion",
    "  ↑ / ↓         browse this database's history · Ctrl+L clears the transcript",
    "",
    "  \\use <name>   switch database (also: use <name>)    \\list         show databases",
    `  \\rows <n>     rows per result (now ${prefs.maxRows})${" ".repeat(Math.max(1, 17 - String(prefs.maxRows).length))}\\timeout <s>  per statement (now ${prefs.timeoutSeconds} s)`,
    "  \\clear        clear the transcript                  \\help         this help",
    "",
    "  Hover a result for Copy · Export CSV · Export JSON.",
  ].join("\n");
}

/** Plain-text output of one SQL statement (for Copy and the transcript export). */
export function sqlStatementText(r: SqlStatementResult, maxRows: number): string {
  if (r.type === "rows" && r.rows.length > 0) return `${asciiTable(r.columns, r.rows)}\n${sqlStatementFooter(r, maxRows)}`;
  return sqlStatementFooter(r, maxRows);
}

/** Plain-text output of a MongoDB run. */
export function mongoText(res: MongoQueryResponse, maxRows: number, asTable = false): string {
  const parts = outputLines(res.output);
  if (res.error) parts.push(`ERROR: ${res.error.message}`);
  if (res.result !== null) {
    parts.push(asTable && res.result_docs ? asciiTable(...tableArgs(res.result_docs)) : pretty(res.result));
  }
  const footer = mongoFooter(res, maxRows);
  if (footer) parts.push(footer);
  return parts.join("\n");
}

function tableArgs(docs: MongoQueryResponse["result_docs"] & object): [string[], Cell[][]] {
  const t = docsToTable(docs);
  return [t.columns, t.rows];
}

/** Text of a run's whole output. */
export function runOutputText(run: RunState, maxRows: number): string {
  if (run.status === "running") return "(running…)";
  if (run.status === "failed") return `ERROR: ${run.failure.message}`;
  const res = run.response;
  if (res.kind === "nosql") return mongoText(res, maxRows);
  const many = res.results.length > 1;
  return res.results
    .map((r, i) => (many ? `-- #${i + 1} ${statementLabel(r.statement, 60)}\n` : "") + sqlStatementText(r, maxRows))
    .join("\n\n");
}

/** The whole transcript as text (prompt echoes + outputs). */
export function transcriptText(entries: readonly ConsoleEntry[], prefs: QueryPrefs): string {
  const echo = (input?: EchoInput) => (input ? `${input.prompt} ${input.text}\n` : "");
  return entries
    .map((e) => {
      if (e.kind === "help") return `${echo(e.input)}${helpText(prefs)}`;
      if (e.kind === "message") return `${echo(e.input)}${e.text}`;
      return `${e.prompt} ${e.query}\n${runOutputText(e.run, e.run.request.max_rows ?? prefs.maxRows)}`;
    })
    .join("\n\n");
}
