import { useEffect, useMemo, useRef, useState } from "react";
import { isDeviceOffline } from "../../api/client";
import { api } from "../../api/endpoints";
import { useSourceSchema } from "../../api/hooks";
import type { DataSource, Entity, Project, QueryRequest } from "../../api/types";
import { useToast } from "../../components/ui/toast-context";
import { engineLabel } from "../../lib/format";
import { useDeviceNames } from "../devices/useDeviceNames";
import { addHistoryEntry, clearHistory, loadHistory, type HistoryEntry } from "./history";
import {
  loadDraft,
  loadPrefs,
  loadSelectedSource,
  saveDraft,
  savePrefs,
  saveSelectedSource,
  type QueryPrefs,
} from "./prefs";
import type { QueryEditorHandle } from "./QueryEditor";
import { checkReadOnly } from "./readOnly";
import { describeQueryError, firstError, starterQuery } from "./results";
import { findSource, parseCommand, promptLabel, type ConsoleCommand, type ConsoleEntry, type RunEntry } from "./terminal";

const NO_ENTITIES: Entity[] = [];
const DESKTOP = "(min-width: 1024px)";

export const isDesktop = () => typeof window.matchMedia === "function" && window.matchMedia(DESKTOP).matches;

type DistributiveOmit<T, K extends keyof T> = T extends unknown ? Omit<T, K> : never;

export type PendingWrite = { text: string; reason: string };

/**
 * Everything both console layouts share: the selected source, per-source drafts and history, the
 * transcript of runs, preferences, the viewer guard and the in-flight requests. Layouts stay thin.
 */
export function useQueryConsole(project: Project, sources: DataSource[], readOnly: boolean) {
  const toast = useToast();
  const deviceName = useDeviceNames(
    project.id,
    sources.some((s) => Boolean(s.device_id)),
  );

  const [selectedId, setSelectedId] = useState<string | null>(() => loadSelectedSource(project.id));
  const source = sources.find((s) => s.id === selectedId) ?? sources[0];
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [histories, setHistories] = useState<Record<string, HistoryEntry[]>>({});
  const [entries, setEntries] = useState<ConsoleEntry[]>(() => [{ id: 0, kind: "help" }]);
  /** Latest run per source (the terminal's `current`). */
  const [lastRun, setLastRun] = useState<Record<string, number | null>>({});
  const [prefs, setPrefsState] = useState<QueryPrefs>(loadPrefs);
  const [sidebarOpen, setSidebarOpen] = useState(isDesktop);
  const [pendingWrite, setPendingWrite] = useState<PendingWrite | null>(null);
  /** Shell-style ↑/↓ browsing: index into `history` and the input as it was before browsing. */
  const [browse, setBrowse] = useState<{ index: number; stash: string } | null>(null);

  const editorRef = useRef<QueryEditorHandle | null>(null);
  /** For the layout's `<QueryEditor onHandle>`; the handle stays private to this hook. */
  const registerEditor = (handle: QueryEditorHandle | null) => {
    editorRef.current = handle;
  };
  const inflight = useRef(new Map<string, AbortController>());
  const draftTimer = useRef<{ timer: number; sid: string; text: string } | null>(null);
  const nextId = useRef(1);

  const schema = useSourceSchema(project.id, source.id);
  const entities = schema.data?.entities ?? NO_ENTITIES;
  const offline = isDeviceOffline(schema.error);

  const text = useMemo(() => drafts[source.id] ?? loadDraft(project.id, source.id), [drafts, project.id, source.id]);
  const history = useMemo(
    () => histories[source.id] ?? loadHistory(project.id, source.id),
    [histories, project.id, source.id],
  );
  const currentId = lastRun[source.id] ?? null;
  const current = useMemo(
    () => (currentId === null ? null : (entries.find((e): e is RunEntry => e.kind === "run" && e.id === currentId) ?? null)),
    [entries, currentId],
  );
  const running = entries.some((e) => e.kind === "run" && e.sourceId === source.id && e.run.status === "running");

  // Flush a pending draft save and abort in-flight runs when leaving the tab.
  useEffect(() => {
    const controllers = inflight.current;
    return () => {
      const pending = draftTimer.current;
      if (pending) {
        window.clearTimeout(pending.timer);
        saveDraft(project.id, pending.sid, pending.text);
      }
      for (const c of controllers.values()) c.abort();
    };
  }, [project.id]);

  const setText = (value: string) => {
    setDrafts((d) => ({ ...d, [source.id]: value }));
    if (draftTimer.current) window.clearTimeout(draftTimer.current.timer);
    const sid = source.id;
    const timer = window.setTimeout(() => {
      saveDraft(project.id, sid, value);
      draftTimer.current = null;
    }, 400);
    draftTimer.current = { timer, sid, text: value };
  };

  /** Set the input from code (history, commands): state + the editor document, cursor at the end. */
  const replaceInput = (value: string) => {
    setText(value);
    editorRef.current?.setDoc(value);
  };

  const selectSource = (id: string) => {
    setSelectedId(id);
    saveSelectedSource(project.id, id);
    setPendingWrite(null);
    setBrowse(null);
  };

  const setPrefs = (next: QueryPrefs) => {
    setPrefsState(next);
    savePrefs(next);
  };

  const pushHistory = (sid: string, entry: Omit<HistoryEntry, "id">) => {
    const list = addHistoryEntry(project.id, sid, entry);
    setHistories((h) => ({ ...h, [sid]: list }));
  };

  const addEntry = (entry: DistributiveOmit<ConsoleEntry, "id">): number => {
    const id = nextId.current++;
    setEntries((list) => [...list, { ...entry, id }]);
    return id;
  };

  const updateRun = (id: number, patch: (e: RunEntry) => RunEntry) =>
    setEntries((list) => list.map((e) => (e.kind === "run" && e.id === id ? patch(e) : e)));

  const execute = async (target: DataSource, queryText: string) => {
    inflight.current.get(target.id)?.abort();
    const controller = new AbortController();
    inflight.current.set(target.id, controller);
    const request: QueryRequest = { query: queryText, max_rows: prefs.maxRows, timeout_seconds: prefs.timeoutSeconds, layout: "terminal" };
    const startedAt = Date.now();
    const at = new Date(startedAt).toISOString();
    const id = addEntry({
      kind: "run",
      sourceId: target.id,
      sourceName: target.name,
      sourceKind: target.kind,
      prompt: promptLabel(target),
      query: queryText,
      at,
      run: { status: "running", request },
    });
    setLastRun((m) => ({ ...m, [target.id]: id }));
    try {
      const response = await api.query.run(project.id, target.id, request, controller.signal);
      if (controller.signal.aborted) return;
      updateRun(id, (e) => ({ ...e, run: { status: "done", response, request } }));
      const problem = firstError(response);
      pushHistory(target.id, { query: queryText, at, duration_ms: response.duration_ms, ok: problem === null, error: problem ?? undefined });
      if (problem) toast.error(problem, response.kind === "sql" ? "A statement failed" : "The script failed");
    } catch (e) {
      if (controller.signal.aborted) return;
      const failure = describeQueryError(e, { timeoutSeconds: prefs.timeoutSeconds });
      updateRun(id, (entry) => ({ ...entry, run: { status: "failed", failure, error: e, request } }));
      pushHistory(target.id, { query: queryText, at, duration_ms: Date.now() - startedAt, ok: false, error: failure.title });
      toast.error(failure.message, failure.title);
    } finally {
      if (inflight.current.get(target.id) === controller) inflight.current.delete(target.id);
    }
  };

  /** Abort the running query of the selected source (client-side; the database may still finish it). */
  const cancel = () => {
    const controller = inflight.current.get(source.id);
    if (!controller) return;
    controller.abort();
    inflight.current.delete(source.id);
    const failure = describeQueryError(new DOMException("cancelled", "AbortError"), { timeoutSeconds: prefs.timeoutSeconds });
    setEntries((list) =>
      list.map((e) =>
        e.kind === "run" && e.sourceId === source.id && e.run.status === "running"
          ? { ...e, run: { status: "failed", failure, error: null, request: e.run.request } }
          : e,
      ),
    );
    toast.info(failure.message, "Cancelled");
  };

  /** Viewer guard: true when the text may be sent; otherwise the hint is shown instead. */
  const guard = (queryText: string): boolean => {
    if (!readOnly) return true;
    const check = checkReadOnly(source.kind, queryText);
    if (check.readOnly) return true;
    setPendingWrite({ text: queryText, reason: check.reason });
    return false;
  };

  /** Editor layout: run the selection if there is one, else the whole editor. */
  const runEditor = () => {
    if (running) return;
    const queryText = editorRef.current?.runnable() ?? text;
    if (!queryText.trim()) return;
    setPendingWrite(null);
    if (!guard(queryText)) return;
    void execute(source, queryText);
  };

  const say = (tone: "info" | "error", body: string, echo: string) =>
    addEntry({ kind: "message", tone, text: body, input: { prompt: promptLabel(source), text: echo } });

  const runCommand = (cmd: ConsoleCommand, echo: string) => {
    switch (cmd.type) {
      case "help":
        addEntry({ kind: "help", input: { prompt: promptLabel(source), text: echo } });
        return;
      case "list": {
        const width = Math.max(...sources.map((s) => s.name.length));
        const lines = sources.map((s) => {
          const where = deviceName(s);
          const status = s.status === "ok" ? "healthy" : s.status === "error" ? `error${s.status_message ? `: ${s.status_message}` : ""}` : "unknown";
          return `${s.id === source.id ? "*" : " "} ${s.name.padEnd(width)}  ${engineLabel(s.engine)} · ${s.kind === "sql" ? "SQL" : "NoSQL"}${where ? ` · on ${where}` : ""} · ${status}`;
        });
        say("info", `${lines.join("\n")}\n\n* = current. Switch with \\use <name>.`, echo);
        return;
      }
      case "use": {
        if (!cmd.name) {
          say("error", "Usage: \\use <database name>. Type \\list to see the names.", echo);
          return;
        }
        const target = findSource(sources, cmd.name);
        if (!target) {
          say("error", `No database named “${cmd.name}”. Type \\list to see them.`, echo);
          return;
        }
        say("info", `Switched to ${target.name} (${engineLabel(target.engine)} · ${target.kind === "sql" ? "SQL" : "NoSQL"}).`, echo);
        selectSource(target.id);
        return;
      }
      case "clear":
        setEntries([]);
        setLastRun({});
        return;
      case "rows":
        if (cmd.value === null) {
          say("error", `Usage: \\rows <1–5000> (now ${prefs.maxRows}).`, echo);
        } else {
          setPrefs({ ...prefs, maxRows: cmd.value });
          say("info", `Max rows per result set to ${cmd.value}.`, echo);
        }
        return;
      case "timeout":
        if (cmd.value === null) {
          say("error", `Usage: \\timeout <1–120> seconds (now ${prefs.timeoutSeconds}).`, echo);
        } else {
          setPrefs({ ...prefs, timeoutSeconds: cmd.value });
          say("info", `Timeout set to ${cmd.value} s.`, echo);
        }
        return;
      case "unknown":
        say("error", `Unknown command \\${cmd.name}. Type \\help for the list.`, echo);
        return;
    }
  };

  /** Terminal layout: run (or execute a built-in command for) the whole prompt, then clear it. */
  const submitPrompt = () => {
    const queryText = (editorRef.current?.doc() ?? text).trim();
    if (!queryText) return;
    setBrowse(null);
    const cmd = parseCommand(queryText);
    if (cmd) {
      runCommand(cmd, queryText);
      replaceInput("");
      editorRef.current?.focus();
      return;
    }
    if (running) {
      toast.info("Wait for the running query to finish, or cancel it.");
      return;
    }
    setPendingWrite(null);
    if (!guard(queryText)) return;
    void execute(source, queryText);
    replaceInput("");
    editorRef.current?.focus();
  };

  const confirmPendingWrite = ({ clearInput = false }: { clearInput?: boolean } = {}) => {
    const pending = pendingWrite;
    if (!pending) return;
    setPendingWrite(null);
    void execute(source, pending.text);
    if (clearInput) replaceInput("");
    editorRef.current?.focus();
  };

  const cancelPendingWrite = () => setPendingWrite(null);

  const clearResults = () => setLastRun((m) => ({ ...m, [source.id]: null }));

  const clearTranscript = () => {
    setEntries([]);
    setLastRun({});
  };

  const clearHistoryFor = () => {
    clearHistory(project.id, source.id);
    setHistories((h) => ({ ...h, [source.id]: [] }));
    setBrowse(null);
  };

  const loadFromHistory = (query: string) => {
    setBrowse(null);
    replaceInput(query);
    editorRef.current?.focus();
  };

  /** ↑ (older, -1) / ↓ (newer, +1) through this source's history, like a shell. */
  const browseHistory = (direction: -1 | 1) => {
    if (history.length === 0) return;
    const index = browse ? browse.index : -1;
    const next = direction === -1 ? index + 1 : index - 1;
    if (next >= history.length) return;
    if (next < 0) {
      if (browse) {
        replaceInput(browse.stash);
        setBrowse(null);
      }
      return;
    }
    setBrowse({ index: next, stash: browse ? browse.stash : text });
    replaceInput(history[next].query);
  };

  const insertStarter = (entityName: string) => {
    editorRef.current?.insert(starterQuery(source.kind, source.engine, entityName));
  };

  return {
    project,
    sources,
    source,
    selectSource,
    readOnly,
    deviceName,
    schema,
    entities,
    offline,
    text,
    setText,
    registerEditor,
    history,
    clearHistoryFor,
    loadFromHistory,
    browseHistory,
    prefs,
    setPrefs,
    entries,
    current,
    running,
    runEditor,
    submitPrompt,
    cancel,
    pendingWrite,
    confirmPendingWrite,
    cancelPendingWrite,
    clearResults,
    clearTranscript,
    sidebarOpen,
    setSidebarOpen,
    insertStarter,
  };
}

export type ConsoleApi = ReturnType<typeof useQueryConsole>;
