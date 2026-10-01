import type { JsonValue } from "../../api/types";

/** docs/CLOUD.md "C2-4": a Realtime Database key is text without . $ # [ ] / (Firebase's rule). */
export function isRtdbKey(key: string): boolean {
  return key.length > 0 && !/[.$#[\]/]/.test(key) && ![...key].some((c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127);
}

/** "users/ann" from " /users/ann/ "; null when a key in it is not a valid key ("" is the root). */
export function cleanRtdbPath(path: string): string | null {
  const clean = path.trim().replace(/^\/+|\/+$/g, "");
  if (clean === "") return "";
  return clean.split("/").every(isRtdbKey) ? clean : null;
}

export function childPath(path: string, key: string): string {
  return path ? `${path}/${key}` : key;
}

export function parentPath(path: string): string {
  return path.split("/").slice(0, -1).join("/");
}

/** A shallow read cuts objects to `true` (and may keep plain values): `true` means "open it to know". */
export function isBranch(shallowValue: JsonValue): boolean {
  return shallowValue === true || (typeof shallowValue === "object" && shallowValue !== null);
}

/** One-line preview of a plain value. */
export function preview(value: JsonValue): string {
  const text = JSON.stringify(value);
  return text.length > 120 ? `${text.slice(0, 117)}…` : text;
}
