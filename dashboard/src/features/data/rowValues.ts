import type { Field as SchemaField, JsonValue } from "../../api/types";

// BOOLEAN on MariaDB/MySQL is stored (and reported) as TINYINT(1).
export const BOOLEAN = /^(bool|boolean|tinyint\(1\)( unsigned)?|bit\(1\))$/i;
const NUMERIC = /^(tinyint|smallint|mediumint|int|integer|bigint|float|double|real|serial|bigserial|smallserial)\b/i;

export function toText(v: JsonValue | undefined): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Convert edited text back to a JSON value, using the column type and original value as hints. */
export function fromText(text: string, field: SchemaField | undefined, original: JsonValue | undefined): JsonValue {
  const type = field?.data_type ?? "";
  if (typeof original === "object" && original !== null) {
    try {
      return JSON.parse(text) as JsonValue;
    } catch {
      return text;
    }
  }
  if (typeof original === "boolean" || BOOLEAN.test(type)) {
    if (/^(true|1)$/i.test(text)) return true;
    if (/^(false|0)$/i.test(text)) return false;
  }
  if ((typeof original === "number" || NUMERIC.test(type)) && /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(text.trim())) {
    const n = Number(text);
    if (Number.isSafeInteger(n) || !Number.isInteger(n)) return n;
  }
  return text;
}
