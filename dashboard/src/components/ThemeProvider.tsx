import { useCallback, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { THEME_STORAGE_KEY, ThemeContext, type ThemeMode } from "../lib/theme";
import { readStorage, writeStorage } from "../lib/storage";

const query = "(prefers-color-scheme: dark)";

function subscribe(cb: () => void) {
  const mql = window.matchMedia(query);
  mql.addEventListener("change", cb);
  return () => mql.removeEventListener("change", cb);
}

function initialMode(): ThemeMode {
  const v = readStorage(THEME_STORAGE_KEY);
  return v === "light" || v === "dark" ? v : "system";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(initialMode);
  const systemDark = useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
  const resolved = mode === "system" ? (systemDark ? "dark" : "light") : mode;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
  }, [resolved]);

  const setMode = useCallback((m: ThemeMode) => {
    writeStorage(THEME_STORAGE_KEY, m === "system" ? null : m);
    setModeState(m);
  }, []);

  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved, setMode]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
