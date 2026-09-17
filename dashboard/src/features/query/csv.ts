import { saveBlob } from "../../api/client";
import type { JsonValue } from "../../api/types";

/** A grid value: JSON from the API, or `undefined` for a key a document doesn't have. */
export type Cell = JsonValue | undefined;

/** One CSV field (RFC 4180): quoted when it holds a comma, quote or line break; null/missing → empty; objects → JSON. */
export function csvField(v: Cell): string {
  if (v === null || v === undefined) return "";
  const s = typeof v === "string" ? v : typeof v === "number" || typeof v === "boolean" ? String(v) : JSON.stringify(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Header row + data rows, CRLF line endings, trailing newline. */
export function toCsv(columns: readonly string[], rows: readonly (readonly Cell[])[]): string {
  const lines = [columns.map(csvField).join(",")];
  for (const row of rows) lines.push(columns.map((_, i) => csvField(row[i])).join(","));
  return `${lines.join("\r\n")}\r\n`;
}

/** Rows as objects keyed by column, for JSON export. Duplicate column names keep the last value. */
export function rowsToObjects(columns: readonly string[], rows: readonly (readonly Cell[])[]): Record<string, Cell>[] {
  return rows.map((row) => {
    const o: Record<string, Cell> = {};
    columns.forEach((c, i) => {
      o[c] = row[i];
    });
    return o;
  });
}

/** `users-2.csv` from a free-form base (statement text, collection name…). */
export function exportFilename(base: string, ext: "csv" | "json", index?: number): string {
  const slug =
    base
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40)
      .replace(/-+$/, "") || "result";
  return `${slug}${index === undefined ? "" : `-${index + 1}`}.${ext}`;
}

/** A rows result (or documents table) ready to export. */
export type ExportTable = { columns: string[]; rows: Cell[][]; base: string; index?: number };

export function exportCsv({ columns, rows, base, index }: ExportTable): void {
  downloadText(exportFilename(base, "csv", index), toCsv(columns, rows), "text/csv");
}

export function exportJson({ columns, rows, base, index }: ExportTable): void {
  downloadText(exportFilename(base, "json", index), JSON.stringify(rowsToObjects(columns, rows), null, 2), "application/json");
}

const BOM = String.fromCharCode(0xfeff);

/** Trigger a download of text. CSV gets a UTF-8 BOM so spreadsheets read accents correctly. */
export function downloadText(filename: string, text: string, type: "text/csv" | "application/json"): void {
  const body = type === "text/csv" ? BOM + text : text;
  saveBlob({ blob: new Blob([body], { type: `${type};charset=utf-8` }), filename });
}
