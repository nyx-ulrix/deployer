import { readJson, readStorage, writeStorage } from "../../lib/storage";

// Everything the console remembers between visits, all in localStorage (never throws).

export const MAX_ROWS_OPTIONS = [100, 500, 2000] as const;
export const TIMEOUT_OPTIONS = [10, 30, 120] as const;

export type QueryPrefs = { maxRows: number; timeoutSeconds: number };

export const DEFAULT_PREFS: QueryPrefs = { maxRows: 500, timeoutSeconds: 30 };

/** Label of the platform's command modifier for shortcut hints ("⌘+Enter" / "Ctrl+Enter"). */
export const MOD_KEY = typeof navigator !== "undefined" && /Mac|iPhone|iPad/i.test(navigator.userAgent) ? "⌘" : "Ctrl";

const PREFS_KEY = "deployer.query.prefs";
/** Drafts above this size aren't persisted (the API accepts 200 000 chars; storage is precious). */
const DRAFT_MAX = 100_000;

export function draftKey(projectId: string, sourceId: string): string {
  return `deployer.query.draft.${projectId}.${sourceId}`;
}

export function loadDraft(projectId: string, sourceId: string): string {
  return readStorage(draftKey(projectId, sourceId)) ?? "";
}

export function saveDraft(projectId: string, sourceId: string, text: string): void {
  if (text.length > DRAFT_MAX) return;
  writeStorage(draftKey(projectId, sourceId), text || null);
}

export function selectedSourceKey(projectId: string): string {
  return `deployer.query.source.${projectId}`;
}

export function loadSelectedSource(projectId: string): string | null {
  return readStorage(selectedSourceKey(projectId));
}

export function saveSelectedSource(projectId: string, sourceId: string): void {
  writeStorage(selectedSourceKey(projectId), sourceId);
}

export function loadPrefs(): QueryPrefs {
  const raw = readJson<Partial<QueryPrefs>>(PREFS_KEY);
  const maxRows = MAX_ROWS_OPTIONS.find((n) => n === raw?.maxRows) ?? DEFAULT_PREFS.maxRows;
  const timeoutSeconds = TIMEOUT_OPTIONS.find((n) => n === raw?.timeoutSeconds) ?? DEFAULT_PREFS.timeoutSeconds;
  return { maxRows, timeoutSeconds };
}

export function savePrefs(prefs: QueryPrefs): void {
  writeStorage(PREFS_KEY, JSON.stringify(prefs));
}
