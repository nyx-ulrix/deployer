import type { JsonObject, JsonValue } from "../../api/types";

export type JsonParse<T> = { ok: true; value: T } | { ok: false; error: string };

export function parseJsonObject(text: string, { allowEmpty = false } = {}): JsonParse<JsonObject | null> {
  const trimmed = text.trim();
  if (!trimmed) return allowEmpty ? { ok: true, value: null } : { ok: false, error: "Enter a JSON object." };
  try {
    const v = JSON.parse(trimmed) as JsonValue;
    if (typeof v !== "object" || v === null || Array.isArray(v)) {
      return { ok: false, error: "Must be a JSON object, like { \"key\": \"value\" }." };
    }
    return { ok: true, value: v };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Invalid JSON" };
  }
}

export function pretty(v: unknown): string {
  return JSON.stringify(v, null, 2);
}

/** String form of a Mongo `_id` in relaxed Extended JSON (`{"$oid": "..."}` → hex). */
export function docIdString(id: JsonValue | undefined): string | null {
  if (id === undefined || id === null) return null;
  if (typeof id === "object" && !Array.isArray(id)) {
    const oid = id["$oid"];
    if (typeof oid === "string") return oid;
    const uuid = id["$uuid"];
    if (typeof uuid === "string") return uuid;
    return JSON.stringify(id);
  }
  return String(id);
}
