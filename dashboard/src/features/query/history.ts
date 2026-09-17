import { readJson, writeStorage } from "../../lib/storage";

/** One run kept in the per-source history (QUERY_CONSOLE.md: last 50 queries with time and duration). */
export type HistoryEntry = {
  id: string;
  query: string;
  /** ISO time the query was started. */
  at: string;
  /** Server-side duration when known, otherwise the round-trip time; null if unknown. */
  duration_ms: number | null;
  ok: boolean;
  /** Short error title when `ok` is false. */
  error?: string;
};

export const HISTORY_LIMIT = 50;

export function historyKey(projectId: string, sourceId: string): string {
  return `deployer.query.history.${projectId}.${sourceId}`;
}

function isEntry(v: unknown): v is HistoryEntry {
  if (typeof v !== "object" || v === null) return false;
  const e = v as Record<string, unknown>;
  return (
    typeof e.id === "string" &&
    typeof e.query === "string" &&
    typeof e.at === "string" &&
    (typeof e.duration_ms === "number" || e.duration_ms === null) &&
    typeof e.ok === "boolean"
  );
}

function newId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Newest first. Corrupt or missing storage yields an empty list. */
export function loadHistory(projectId: string, sourceId: string): HistoryEntry[] {
  const raw = readJson<unknown>(historyKey(projectId, sourceId));
  if (!Array.isArray(raw)) return [];
  return raw.filter(isEntry).slice(0, HISTORY_LIMIT);
}

/**
 * Prepend a run. An earlier entry with the same query text is replaced (so re-running a query moves
 * it to the top instead of filling the list), and the list is capped at `HISTORY_LIMIT`.
 */
export function addHistoryEntry(projectId: string, sourceId: string, entry: Omit<HistoryEntry, "id">): HistoryEntry[] {
  const current = loadHistory(projectId, sourceId);
  const next = [{ id: newId(), ...entry }, ...current.filter((h) => h.query !== entry.query)].slice(0, HISTORY_LIMIT);
  writeStorage(historyKey(projectId, sourceId), JSON.stringify(next));
  return next;
}

export function clearHistory(projectId: string, sourceId: string): void {
  writeStorage(historyKey(projectId, sourceId), null);
}
