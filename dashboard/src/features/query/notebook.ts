import { isApiError } from "../../api/client";
import type { DataSourceKind, QueryRun, SavedQuery } from "../../api/types";
import { relativeTime } from "../../lib/format";
import { readJson, writeStorage } from "../../lib/storage";
import { newId } from "./history";
import { formatMs } from "./results";

// Notebook layout (docs/QUERY_EDITOR.md → Revised direction): a document is an ordered list of cells,
// one command each; open documents are tabs. Everything here is pure so it can be unit-tested.

export type NotebookCell = { id: string; text: string };

export type NotebookTab = {
  id: string;
  /** Saved query this tab edits, or null for an untitled document. */
  savedId: string | null;
  name: string | null;
  folder: string | null;
  /** The N of "Untitled N" while the tab has no saved query. */
  untitled: number | null;
  sourceId: string | null;
  cells: NotebookCell[];
  /** Edited since it was opened or last saved. */
  dirty: boolean;
  /** Version of the saved query this tab's text came from; a PATCH carries it (null = untitled or pre-phase-2 tab). */
  version: number | null;
};

export type NotebookState = { tabs: NotebookTab[]; activeId: string | null };

export const EMPTY_NOTEBOOK: NotebookState = { tabs: [], activeId: null };

/** Cells above this size aren't persisted to localStorage (the API accepts 200 000 chars). */
export const CELL_PERSIST_MAX = 200_000;

export const newCell = (text = ""): NotebookCell => ({ id: newId(), text });

// ---- Document ⇄ saved query text ----

function isCell(v: unknown): v is NotebookCell {
  return typeof v === "object" && v !== null && typeof (v as NotebookCell).id === "string" && typeof (v as NotebookCell).text === "string";
}

/**
 * `query_text` of a saved query → cells. The notebook stores `{"cells":[{id,text}]}`; anything else
 * (a plain snippet, malformed JSON) becomes a single cell holding the whole text.
 */
export function parseDocument(text: string): NotebookCell[] {
  try {
    const v = JSON.parse(text) as { cells?: unknown };
    if (typeof v === "object" && v !== null && Array.isArray(v.cells)) {
      const cells = v.cells.filter(isCell).map((c) => ({ id: c.id, text: c.text }));
      return cells.length > 0 ? cells : [newCell()];
    }
  } catch {
    /* plain text */
  }
  return [{ id: newId(), text }];
}

export function serializeDocument(cells: readonly NotebookCell[]): string {
  return JSON.stringify({ cells: cells.map(({ id, text }) => ({ id, text })) });
}

/** Cells as one text with a comment line between them, so a line diff of two documents reads naturally. */
export function joinCells(cells: readonly NotebookCell[], kind: DataSourceKind): string {
  return cells.map((c) => c.text).join(kind === "nosql" ? "\n// cell //\n" : "\n-- cell --\n");
}

// ---- Cells ----

export function insertCellAfter(cells: readonly NotebookCell[], afterId: string | null, cell: NotebookCell): NotebookCell[] {
  const i = afterId === null ? -1 : cells.findIndex((c) => c.id === afterId);
  const at = i === -1 ? cells.length : i + 1;
  return [...cells.slice(0, at), cell, ...cells.slice(at)];
}

/** Remove a cell; an empty document always shows one empty cell. */
export function removeCell(cells: readonly NotebookCell[], id: string): NotebookCell[] {
  const next = cells.filter((c) => c.id !== id);
  return next.length > 0 ? next : [newCell()];
}

export function moveCell(cells: readonly NotebookCell[], id: string, direction: -1 | 1): NotebookCell[] {
  const i = cells.findIndex((c) => c.id === id);
  const j = i + direction;
  if (i === -1 || j < 0 || j >= cells.length) return [...cells];
  const next = [...cells];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

// ---- Tabs ----

export function tabTitle(tab: Pick<NotebookTab, "name" | "untitled">): string {
  return tab.name ?? `Untitled ${tab.untitled ?? 1}`;
}

function withActive(state: NotebookState, tab: NotebookTab): NotebookState {
  return { tabs: [...state.tabs, tab], activeId: tab.id };
}

/** Smallest positive number no untitled tab uses, so closing "Untitled 2" frees the name. */
export function nextUntitledNumber(tabs: readonly Pick<NotebookTab, "untitled">[]): number {
  const used = new Set(tabs.map((t) => t.untitled));
  let n = 1;
  while (used.has(n)) n++;
  return n;
}

export function openUntitled(state: NotebookState, sourceId: string | null, cells: NotebookCell[] = [newCell()]): NotebookState {
  return withActive(state, {
    id: newId(),
    savedId: null,
    name: null,
    folder: null,
    untitled: nextUntitledNumber(state.tabs),
    sourceId,
    cells,
    dirty: false,
    version: null,
  });
}

/** Open a saved query in a tab; if it is already open, just focus that tab. */
export function openSaved(state: NotebookState, saved: SavedQuery, fallbackSourceId: string | null): NotebookState {
  const existing = state.tabs.find((t) => t.savedId === saved.id);
  if (existing) return { ...state, activeId: existing.id };
  return withActive(state, {
    id: newId(),
    savedId: saved.id,
    name: saved.name,
    folder: saved.folder,
    untitled: null,
    sourceId: saved.data_source_id ?? fallbackSourceId,
    cells: parseDocument(saved.query_text),
    dirty: false,
    version: saved.version,
  });
}

/** Close a tab; when it was active, the tab that took its place (or the previous one) becomes active. */
export function closeTab(state: NotebookState, id: string): NotebookState {
  const i = state.tabs.findIndex((t) => t.id === id);
  if (i === -1) return state;
  const tabs = state.tabs.filter((t) => t.id !== id);
  if (state.activeId !== id) return { tabs, activeId: state.activeId };
  const neighbour = tabs[Math.min(i, tabs.length - 1)];
  return { tabs, activeId: neighbour?.id ?? null };
}

export function patchTab(state: NotebookState, id: string, patch: Partial<NotebookTab>): NotebookState {
  return { ...state, tabs: state.tabs.map((t) => (t.id === id ? { ...t, ...patch } : t)) };
}

/** Replace a tab's cells; any change marks the tab unsaved. */
export function setCells(state: NotebookState, id: string, cells: NotebookCell[]): NotebookState {
  return patchTab(state, id, { cells, dirty: true });
}

/** The tab was saved as (or renamed to) this saved query. */
export function attachSaved(state: NotebookState, id: string, saved: Pick<SavedQuery, "id" | "name" | "folder" | "version">): NotebookState {
  return patchTab(state, id, { savedId: saved.id, name: saved.name, folder: saved.folder, untitled: null, dirty: false, version: saved.version });
}

/**
 * The server has a newer copy of a tab's saved query: take its name, folder, text and version. A dirty tab is
 * left alone (the user decides in the UI) unless `force` — "Reload theirs" after a conflict, or a restore.
 */
export function refreshSaved(state: NotebookState, saved: SavedQuery, force = false): NotebookState {
  const tab = state.tabs.find((t) => t.savedId === saved.id);
  if (!tab || (tab.dirty && !force)) return state;
  return patchTab(state, tab.id, { name: saved.name, folder: saved.folder, version: saved.version, cells: parseDocument(saved.query_text), dirty: false });
}

/** A tab whose saved query the server knows a newer version of. */
export function isBehind(tab: Pick<NotebookTab, "savedId" | "version">, saved: Pick<SavedQuery, "id" | "version"> | undefined): boolean {
  return saved !== undefined && tab.savedId === saved.id && saved.version > (tab.version ?? 0);
}

/** The current server copy carried by a `409 version_conflict`, or null for any other error. */
export function versionConflict(e: unknown): SavedQuery | null {
  if (!isApiError(e) || e.code !== "version_conflict") return null;
  const current = e.details.current as SavedQuery | undefined;
  return current && typeof current.version === "number" ? current : null;
}

/** The saved query was deleted elsewhere: its tab lives on as an unsaved untitled document. */
export function detachSaved(state: NotebookState, savedId: string): NotebookState {
  const tab = state.tabs.find((t) => t.savedId === savedId);
  if (!tab) return state;
  return patchTab(state, tab.id, { savedId: null, name: null, folder: null, untitled: nextUntitledNumber(state.tabs), dirty: true, version: null });
}

// ---- Snippet names ----

/** "reports/monthly sales" typed as a name → folder "reports", name "monthly sales". A plain name keeps `folder`. */
export function splitFolderName(name: string, folder: string | null = null): { name: string; folder: string | null } {
  const slash = name.lastIndexOf("/");
  if (slash === -1) return { name: name.trim(), folder: folder?.trim() || null };
  return { name: name.slice(slash + 1).trim(), folder: name.slice(0, slash).trim() || null };
}

// ---- History rows ----

export type HistoryTone = "success" | "danger" | "warning" | "muted";

const STATUS_TONES: Record<QueryRun["status"], HistoryTone> = { ok: "success", error: "danger", timeout: "warning", refused: "muted" };

/** What a history row shows: the first non-blank line, a status dot tone, duration and relative time. */
export function historyRow(run: QueryRun, now = Date.now()): { line: string; tone: HistoryTone; duration: string; when: string } {
  const line = run.query_text.split("\n").find((l) => l.trim())?.trim() ?? "";
  return { line: line.length > 160 ? `${line.slice(0, 159)}…` : line, tone: STATUS_TONES[run.status], duration: formatMs(run.duration_ms), when: relativeTime(run.created_at, now) };
}

// ---- Persistence (per project, per browser) ----

export function notebookKey(projectId: string): string {
  return `deployer.notebook.${projectId}`;
}

function isTab(v: unknown): v is NotebookTab {
  if (typeof v !== "object" || v === null) return false;
  const t = v as Record<string, unknown>;
  return typeof t.id === "string" && Array.isArray(t.cells) && t.cells.every(isCell) && typeof t.dirty === "boolean";
}

export function loadNotebook(projectId: string): NotebookState {
  const raw = readJson<{ tabs?: unknown; activeId?: unknown }>(notebookKey(projectId));
  if (!raw || !Array.isArray(raw.tabs)) return EMPTY_NOTEBOOK;
  const tabs = raw.tabs.filter(isTab).map((t) => ({
    id: t.id,
    savedId: typeof t.savedId === "string" ? t.savedId : null,
    name: typeof t.name === "string" ? t.name : null,
    folder: typeof t.folder === "string" ? t.folder : null,
    untitled: typeof t.untitled === "number" ? t.untitled : null,
    sourceId: typeof t.sourceId === "string" ? t.sourceId : null,
    cells: t.cells.length > 0 ? t.cells : [newCell()],
    dirty: t.dirty,
    version: typeof t.version === "number" ? t.version : null,
  }));
  const activeId = tabs.some((t) => t.id === raw.activeId) ? (raw.activeId as string) : (tabs[0]?.id ?? null);
  return { tabs, activeId };
}

/** Text only, never results; oversized cells are left out. */
export function saveNotebook(projectId: string, state: NotebookState): void {
  const tabs = state.tabs.map((t) => ({ ...t, cells: t.cells.filter((c) => c.text.length <= CELL_PERSIST_MAX) }));
  writeStorage(notebookKey(projectId), tabs.length === 0 ? null : JSON.stringify({ tabs, activeId: state.activeId }));
}
