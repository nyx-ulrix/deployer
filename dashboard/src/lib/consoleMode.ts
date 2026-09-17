import { useSyncExternalStore } from "react";
import { readStorage, writeStorage } from "./storage";

/** How the project Query tab is laid out: a shell-style transcript or an editor above a results panel. */
export type QueryConsoleMode = "terminal" | "editor";

export const QUERY_CONSOLE_MODE_KEY = "deployer.queryConsoleMode";
export const DEFAULT_QUERY_CONSOLE_MODE: QueryConsoleMode = "terminal";

export const QUERY_CONSOLE_MODES: { value: QueryConsoleMode; label: string; description: string }[] = [
  {
    value: "terminal",
    label: "Terminal",
    description: "A shell-style transcript with the prompt at the bottom, like the mysql and mongosh shells.",
  },
  {
    value: "editor",
    label: "Editor",
    description: "A multi-line editor above a results panel, one card per statement.",
  },
];

const listeners = new Set<() => void>();

export function loadQueryConsoleMode(): QueryConsoleMode {
  const v = readStorage(QUERY_CONSOLE_MODE_KEY);
  return v === "editor" || v === "terminal" ? v : DEFAULT_QUERY_CONSOLE_MODE;
}

/** Persist the mode (per browser) and tell every mounted `useQueryConsoleMode` about it. */
export function saveQueryConsoleMode(mode: QueryConsoleMode): void {
  writeStorage(QUERY_CONSOLE_MODE_KEY, mode);
  for (const l of listeners) l();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key === QUERY_CONSOLE_MODE_KEY) cb();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

/** The preferred query-console layout; changes apply immediately everywhere it is used. */
export function useQueryConsoleMode(): [QueryConsoleMode, (mode: QueryConsoleMode) => void] {
  const mode = useSyncExternalStore(subscribe, loadQueryConsoleMode, () => DEFAULT_QUERY_CONSOLE_MODE);
  return [mode, saveQueryConsoleMode];
}
