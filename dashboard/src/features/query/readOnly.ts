import type { DataSourceKind } from "../../api/types";

// Client-side mirror of the API's viewer rule (QUERY_CONSOLE.md → Roles). The API is the real guard;
// this only powers the read-only badge and a hint before an obviously-write query is sent.

const SQL_READ_KEYWORDS = new Set(["select", "with", "show", "explain", "describe", "desc", "table", "values"]);

/** Method/identifier names the API refuses for viewers (checked as whole words anywhere in the code). */
export const MONGO_WRITE_NAMES = [
  "insert",
  "insertOne",
  "insertMany",
  "update",
  "updateOne",
  "updateMany",
  "replaceOne",
  "delete",
  "deleteOne",
  "deleteMany",
  "remove",
  "drop",
  "dropDatabase",
  "dropIndex",
  "createCollection",
  "createIndex",
  "renameCollection",
  "bulkWrite",
  "findOneAndUpdate",
  "findOneAndReplace",
  "findOneAndDelete",
  "findAndModify",
  "runCommand",
  "adminCommand",
  "getSiblingDB",
  "getMongo",
  "load",
  "require",
  "process",
  "fs",
  "child_process",
] as const;

const MONGO_WRITE_RE = new RegExp(`(?<![\\w$])(${MONGO_WRITE_NAMES.join("|")})(?![\\w$])`);

/**
 * Split SQL into statements on `;`, skipping comments (`-- …`, `# …`, `/* … *\/`) and quoted strings
 * (`'…'`, `"…"`, `` `…` `` with doubled quotes or backslash escapes). Blank statements are dropped.
 */
export function splitSqlStatements(text: string): string[] {
  const out: string[] = [];
  let cur = "";
  let i = 0;
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    const next = text[i + 1];
    if ((ch === "-" && next === "-") || ch === "#") {
      while (i < n && text[i] !== "\n") i++;
      continue;
    }
    if (ch === "/" && next === "*") {
      const end = text.indexOf("*/", i + 2);
      i = end === -1 ? n : end + 2;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === "`") {
      let j = i + 1;
      let s = ch;
      while (j < n) {
        const c = text[j];
        if (c === "\\" && ch !== "`" && j + 1 < n) {
          s += c + text[j + 1];
          j += 2;
          continue;
        }
        s += c;
        j++;
        if (c === ch) {
          if (text[j] === ch) {
            s += ch;
            j++;
            continue;
          }
          break;
        }
      }
      cur += s;
      i = j;
      continue;
    }
    if (ch === ";") {
      out.push(cur);
      cur = "";
      i++;
      continue;
    }
    cur += ch;
    i++;
  }
  out.push(cur);
  return out.map((s) => s.trim()).filter((s) => s.length > 0);
}

/** Lower-cased first word of a statement ("" when it doesn't start with a word). */
export function firstKeyword(statement: string): string {
  const m = /^\s*([A-Za-z_]+)/.exec(statement);
  return m ? m[1].toLowerCase() : "";
}

export type ReadOnlyCheck = { readOnly: true } | { readOnly: false; reason: string };

/** Every statement must start with SELECT, WITH, SHOW, EXPLAIN, DESCRIBE, DESC, TABLE or VALUES. */
export function checkSqlReadOnly(text: string): ReadOnlyCheck {
  for (const statement of splitSqlStatements(text)) {
    const kw = firstKeyword(statement);
    if (!SQL_READ_KEYWORDS.has(kw)) {
      const what = kw ? kw.toUpperCase() : statement.slice(0, 20);
      return { readOnly: false, reason: `A statement starting with “${what}” isn't read-only.` };
    }
  }
  return { readOnly: true };
}

/** The code must not contain any write/restricted name (as a whole word, anywhere). */
export function checkMongoReadOnly(code: string): ReadOnlyCheck {
  const m = MONGO_WRITE_RE.exec(code);
  return m ? { readOnly: false, reason: `“${m[1]}” is a write or restricted method.` } : { readOnly: true };
}

export function checkReadOnly(kind: DataSourceKind, text: string): ReadOnlyCheck {
  return kind === "sql" ? checkSqlReadOnly(text) : checkMongoReadOnly(text);
}
