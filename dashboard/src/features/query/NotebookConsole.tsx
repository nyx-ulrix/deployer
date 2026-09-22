import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Eraser,
  FilePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  Plus,
  Save,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { errorMessage, isDeviceOffline } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useSavedQueries, useSourceSchema } from "../../api/hooks";
import type { DataSource, Entity, Project, QueryRequest, SavedQuery } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Dialog } from "../../components/ui/Dialog";
import { Spinner } from "../../components/ui/Spinner";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { engineLabel, formatTime, relativeTime } from "../../lib/format";
import { useDeviceNames } from "../devices/useDeviceNames";
import { ModeSwitch, PendingWriteAlert, ReadOnlyBadge, RowsSelect, TimeoutSelect } from "./ConsoleBits";
import { DiffDialog } from "./DiffView";
import { MongoResults } from "./MongoResults";
import {
  attachSaved,
  closeTab,
  detachSaved,
  insertCellAfter,
  isBehind,
  joinCells,
  loadNotebook,
  moveCell,
  newCell,
  openSaved,
  openUntitled,
  parseDocument,
  patchTab,
  refreshSaved,
  removeCell,
  saveNotebook,
  serializeDocument,
  setCells,
  tabTitle,
  versionConflict,
  type NotebookCell,
  type NotebookState,
  type NotebookTab,
} from "./notebook";
import { NotebookSidebar } from "./NotebookSidebar";
import { loadPrefs, loadSelectedSource, MOD_KEY, savePrefs, saveSelectedSource, type QueryPrefs } from "./prefs";
import { QueryEditor, type ConsoleAction, type QueryEditorHandle } from "./QueryEditor";
import { checkReadOnly } from "./readOnly";
import { describeQueryError, firstError, formatMs, mongoSummaryText, sqlSummaryText, starterQuery, summarizeSql } from "./results";
import { SnippetDialog } from "./SnippetDialog";
import { SourceSelect } from "./SourceSelect";
import { SqlResults } from "./SqlResults";
import type { RunState } from "./terminal";
import { isDesktop } from "./useQueryConsole";

const NO_ENTITIES: Entity[] = [];

/** Output of one cell: session state only, never persisted or saved. */
type CellResult = { run: RunState; at: string; /** The text that was run, for the "edited since" hint. */ text: string; collapsed: boolean };

type PendingWrite = { cellId: string; text: string; reason: string };

/**
 * The server copy of a tab's snippet shown side by side with the tab (QUERY_EDITOR.md → phase 2).
 * "save": our PATCH lost a race; "restore": a restore did; "remote": someone saved while we were editing.
 */
type Conflict = { tabId: string; current: SavedQuery; mode: "save" | "restore" | "remote" };

/** Everything a cell can ask the notebook to do, keyed by cell id (keeps the cell's props short). */
type CellActions = {
  change: (id: string, text: string) => void;
  run: (id: string, moveOn: boolean) => void;
  cancel: (id: string) => void;
  remove: (id: string) => void;
  move: (id: string, direction: -1 | 1) => void;
  addBelow: (id: string) => void;
  toggle: (id: string) => void;
  focus: (id: string) => void;
  handle: (id: string, handle: QueryEditorHandle | null) => void;
  confirmWrite: () => void;
  cancelWrite: () => void;
};

function initialState(projectId: string): NotebookState {
  const stored = loadNotebook(projectId);
  return stored.tabs.length > 0 ? stored : openUntitled(stored, loadSelectedSource(projectId));
}

/**
 * Notebook layout (QUERY_EDITOR.md → Revised direction): tabs of documents, each a stack of cells with
 * the cell's output right below it, like a database shell you can edit and re-run.
 */
export function NotebookConsole({ project, sources, readOnly }: { project: Project; sources: DataSource[]; readOnly: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const deviceName = useDeviceNames(
    project.id,
    sources.some((s) => Boolean(s.device_id)),
  );

  const [state, setState] = useState<NotebookState>(() => initialState(project.id));
  const [prefs, setPrefsState] = useState<QueryPrefs>(loadPrefs);
  const [results, setResults] = useState<Record<string, CellResult>>({});
  const [pendingWrite, setPendingWrite] = useState<PendingWrite | null>(null);
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  /** Cell that should take focus when it mounts (a freshly added one). */
  const [focusCellId, setFocusCellId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(isDesktop);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [saveDialog, setSaveDialog] = useState(false);
  const [closing, setClosing] = useState<NotebookTab | null>(null);
  const [deletingCell, setDeletingCell] = useState<string | null>(null);
  /** Optional "What changed?" line sent with the next save of a snippet. */
  const [message, setMessage] = useState("");
  const [conflict, setConflict] = useState<Conflict | null>(null);
  /** The banner's "Reload theirs" confirms before it throws local edits away. */
  const [reloading, setReloading] = useState<SavedQuery | null>(null);
  /** Per tab, the remote version the user chose to keep editing over (hides the banner until the next one). */
  const [dismissed, setDismissed] = useState<Record<string, number>>({});

  const inflight = useRef(new Map<string, AbortController>());
  const handles = useRef(new Map<string, QueryEditorHandle>());
  const latest = useRef(state);

  const tab = state.tabs.find((t) => t.id === state.activeId) ?? state.tabs[0];
  const sourceOf = (t: NotebookTab) => sources.find((s) => s.id === t.sourceId) ?? sources[0];
  const source = sourceOf(tab);
  const schema = useSourceSchema(project.id, source.id);
  const entities = schema.data?.entities ?? NO_ENTITIES;
  const offline = isDeviceOffline(schema.error);
  const anyRunning = Object.values(results).some((r) => r.run.status === "running");
  const activeCell = activeCellId && tab.cells.some((c) => c.id === activeCellId) ? activeCellId : tab.cells[0].id;
  // The list is polled (useSavedQueries), which is how a tab notices that a teammate saved a newer version.
  const savedList = useSavedQueries(project.id);
  const saved = savedList.data?.find((x) => x.id === tab.savedId);
  const behind = saved && isBehind(tab, saved) ? saved : undefined;
  const conflictTab = conflict ? state.tabs.find((t) => t.id === conflict.tabId) : undefined;

  // Persist text (debounced while typing) and flush on the way out; results never leave memory.
  useEffect(() => {
    latest.current = state;
    const timer = window.setTimeout(() => saveNotebook(project.id, state), 400);
    return () => window.clearTimeout(timer);
  }, [project.id, state]);
  useEffect(() => {
    const controllers = inflight.current;
    return () => {
      saveNotebook(project.id, latest.current);
      for (const c of controllers.values()) c.abort();
    };
  }, [project.id]);

  // Clean tabs follow the server silently; dirty ones get the banner below instead (never an auto-merge).
  useEffect(() => {
    const list = savedList.data;
    if (!list) return;
    const s = latest.current;
    const newer = s.tabs.flatMap((t) => {
      const sv = list.find((x) => x.id === t.savedId);
      return !t.dirty && sv && isBehind(t, sv) ? [{ t, sv }] : [];
    });
    if (newer.length === 0) return;
    setState((prev) => newer.reduce((acc, { sv }) => refreshSaved(acc, sv), prev));
    const active = newer.find(({ t }) => t.id === s.activeId);
    if (active) toast.info(`Updated to v${active.sv.version} by ${active.sv.updated_by_email}`);
  }, [savedList.data, toast]);

  const setPrefs = (next: QueryPrefs) => {
    setPrefsState(next);
    savePrefs(next);
  };

  // ---- Tabs ----

  const activate = (id: string) => {
    setState((s) => ({ ...s, activeId: id }));
    setActiveCellId(null);
    setFocusCellId(null);
    setPendingWrite(null);
  };

  const newTab = () => {
    const next = openUntitled(state, source.id);
    setState(next);
    setFocusCellId(next.tabs[next.tabs.length - 1].cells[0].id);
    setPendingWrite(null);
  };

  const forgetCells = (cells: readonly NotebookCell[]) => {
    for (const c of cells) {
      inflight.current.get(c.id)?.abort();
      inflight.current.delete(c.id);
    }
    setResults((r) => {
      const next = { ...r };
      for (const c of cells) delete next[c.id];
      return next;
    });
  };

  const doClose = (t: NotebookTab) => {
    forgetCells(t.cells);
    let next = closeTab(state, t.id);
    if (next.tabs.length === 0) next = openUntitled(next, source.id);
    setState(next);
    setClosing(null);
  };

  const requestClose = (t: NotebookTab) => {
    if (t.dirty && t.cells.some((c) => c.text.trim())) setClosing(t);
    else doClose(t);
  };

  const selectSource = (id: string) => {
    setState((s) => patchTab(s, tab.id, { sourceId: id }));
    saveSelectedSource(project.id, id);
    setPendingWrite(null);
  };

  // ---- Cells ----

  const addCellBelow = (afterId: string | null, text = "") => {
    const cell = newCell(text);
    setState((s) => {
      const t = s.tabs.find((x) => x.id === tab.id);
      return t ? setCells(s, t.id, insertCellAfter(t.cells, afterId, cell)) : s;
    });
    setActiveCellId(cell.id);
    setFocusCellId(cell.id);
  };

  const runCell = async (cellId: string, override?: { text: string }): Promise<boolean> => {
    const t = latest.current.tabs.find((x) => x.cells.some((c) => c.id === cellId));
    const cell = t?.cells.find((c) => c.id === cellId);
    if (!t || !cell) return false;
    const target = sourceOf(t);
    // The editor's document is fresher than state while a keystroke is still being flushed.
    const text = override?.text ?? handles.current.get(cellId)?.doc() ?? cell.text;
    if (!text.trim()) return true;
    setPendingWrite(null);
    if (!override && readOnly) {
      const check = checkReadOnly(target.kind, text);
      if (!check.readOnly) {
        setPendingWrite({ cellId, text, reason: check.reason });
        return false;
      }
    }
    inflight.current.get(cellId)?.abort();
    const controller = new AbortController();
    inflight.current.set(cellId, controller);
    const request: QueryRequest = { query: text, max_rows: prefs.maxRows, timeout_seconds: prefs.timeoutSeconds, layout: "editor" };
    const at = new Date().toISOString();
    setResults((r) => ({ ...r, [cellId]: { run: { status: "running", request }, at, text, collapsed: false } }));
    try {
      const response = await api.query.run(project.id, target.id, request, controller.signal);
      if (controller.signal.aborted) return false;
      setResults((r) => ({ ...r, [cellId]: { run: { status: "done", response, request }, at, text, collapsed: false } }));
      return firstError(response) === null;
    } catch (e) {
      if (controller.signal.aborted) return false;
      const failure = describeQueryError(e, { timeoutSeconds: prefs.timeoutSeconds });
      setResults((r) => ({ ...r, [cellId]: { run: { status: "failed", failure, error: e, request }, at, text, collapsed: false } }));
      return false;
    } finally {
      if (inflight.current.get(cellId) === controller) inflight.current.delete(cellId);
      // Every run is logged server-side; refresh the sidebar's history.
      void queryClient.invalidateQueries({ queryKey: qk.queryLogFor(project.id, target.id) });
    }
  };

  /** Top to bottom, stopping at the first cell that fails (or needs the viewer's confirmation). */
  const runAll = async () => {
    for (const cell of tab.cells) {
      if (!(await runCell(cell.id))) break;
    }
  };

  const cancelCell = (cellId: string) => {
    const controller = inflight.current.get(cellId);
    if (!controller) return;
    controller.abort();
    inflight.current.delete(cellId);
    const failure = describeQueryError(new DOMException("cancelled", "AbortError"), { timeoutSeconds: prefs.timeoutSeconds });
    setResults((r) => {
      const cur = r[cellId];
      return cur && cur.run.status === "running"
        ? { ...r, [cellId]: { ...cur, run: { status: "failed", failure, error: null, request: cur.run.request } } }
        : r;
    });
  };

  const cell: CellActions = {
    change: (id, text) =>
      setState((s) => {
        const t = s.tabs.find((x) => x.cells.some((c) => c.id === id));
        return t ? setCells(s, t.id, t.cells.map((c) => (c.id === id ? { ...c, text } : c))) : s;
      }),
    run: (id, moveOn) => {
      void runCell(id);
      if (!moveOn) return;
      const i = tab.cells.findIndex((c) => c.id === id);
      if (i === tab.cells.length - 1) addCellBelow(id);
      else handles.current.get(tab.cells[i + 1].id)?.focus();
    },
    cancel: cancelCell,
    remove: (id) => {
      const target = tab.cells.find((c) => c.id === id);
      if (target?.text.trim()) setDeletingCell(id);
      else removeCellNow(id);
    },
    move: (id, direction) => setState((s) => setCells(s, tab.id, moveCell(tab.cells, id, direction))),
    addBelow: (id) => addCellBelow(id),
    toggle: (id) => setResults((r) => (r[id] ? { ...r, [id]: { ...r[id], collapsed: !r[id].collapsed } } : r)),
    focus: setActiveCellId,
    handle: (id, handle) => {
      if (handle) handles.current.set(id, handle);
      else handles.current.delete(id);
    },
    confirmWrite: () => {
      if (pendingWrite) void runCell(pendingWrite.cellId, { text: pendingWrite.text });
    },
    cancelWrite: () => setPendingWrite(null),
  };

  const removeCellNow = (id: string) => {
    forgetCells(tab.cells.filter((c) => c.id === id));
    setState((s) => setCells(s, tab.id, removeCell(tab.cells, id)));
    setDeletingCell(null);
  };

  const clearOutputs = () => setResults((r) => Object.fromEntries(Object.entries(r).filter(([, v]) => v.run.status === "running")));

  // ---- Saving (developer+; PATCH silently after the first save, carrying the version the tab loaded) ----

  const save = useMutation({
    /** `version` overrides the tab's own: "Keep mine" after a conflict saves on top of the version that won. */
    mutationFn: ({ tab: t, name, folder, version }: { tab: NotebookTab; name?: string; folder?: string | null; version?: number }) => {
      const src = sourceOf(t);
      const body = { query_text: serializeDocument(t.cells), data_source_id: src.id, kind: src.kind };
      return t.savedId && name === undefined
        ? api.savedQueries.update(project.id, t.savedId, { ...body, version: version ?? t.version ?? 0, message: message.trim() || undefined })
        : api.savedQueries.create(project.id, { ...body, name: name ?? tabTitle(t), folder });
    },
    onSuccess: (result, { tab: t }) => {
      setState((s) => attachSaved(s, t.id, result));
      void queryClient.invalidateQueries({ queryKey: qk.savedQueries(project.id) });
      void queryClient.invalidateQueries({ queryKey: qk.savedQueryVersions(project.id, result.id) });
      setSaveDialog(false);
      setConflict(null);
      setMessage("");
      toast.success(`Saved “${result.name}” as v${result.version}.`);
    },
    onError: (e, { tab: t }) => {
      const current = versionConflict(e);
      if (current && current.id === t.savedId) setConflict({ tabId: t.id, current, mode: "save" });
      else toast.error(errorMessage(e), "Couldn't save the query");
    },
  });

  /** Replace a tab's document with the server copy — the user has seen the diff or confirmed the reload. */
  const reloadTheirs = (current: SavedQuery) => {
    setState((s) => refreshSaved(s, current, true));
    setConflict(null);
    setReloading(null);
    toast.info(`Reloaded v${current.version} by ${current.updated_by_email}.`);
  };

  const requestSave = () => {
    if (readOnly || save.isPending) return;
    if (tab.savedId) save.mutate({ tab });
    else setSaveDialog(true);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      requestSave();
    }
  };

  // ---- Sidebar ----

  const insertIntoActiveCell = (text: string) => {
    const handle = handles.current.get(activeCell);
    if (handle) handle.insert(text);
    else cell.change(activeCell, `${tab.cells.find((c) => c.id === activeCell)?.text ?? ""}${text}`);
    if (!isDesktop()) setDrawerOpen(false);
  };

  const sidebar = (inDrawer: boolean) => (
    <NotebookSidebar
      project={project}
      source={source}
      schema={schema}
      openSavedId={tab.savedId}
      onOpenSaved={(saved) => {
        setState((s) => openSaved(s, saved, source.id));
        setActiveCellId(null);
        if (inDrawer) setDrawerOpen(false);
      }}
      onNew={() => {
        newTab();
        if (inDrawer) setDrawerOpen(false);
      }}
      onRenamed={(renamed) =>
        setState((s) => {
          const t = s.tabs.find((x) => x.savedId === renamed.id);
          return t ? patchTab(s, t.id, { name: renamed.name, folder: renamed.folder, version: renamed.version }) : s;
        })
      }
      onDeleted={(id) => setState((s) => detachSaved(s, id))}
      tab={tab}
      kind={source.kind}
      onRestored={(restored) => {
        setState((s) => refreshSaved(s, restored, true));
        toast.success(`Restored as v${restored.version}.`);
      }}
      onRestoreConflict={(current) => setConflict({ tabId: tab.id, current, mode: "restore" })}
      onInsertHistory={(text) => {
        addCellBelow(activeCell, text);
        if (inDrawer) setDrawerOpen(false);
      }}
      onInsertEntity={(name) => insertIntoActiveCell(starterQuery(source.kind, source.engine, name))}
      onClose={inDrawer ? undefined : () => setSidebarOpen(false)}
      className={inDrawer ? undefined : "hidden lg:flex lg:w-[260px] lg:shrink-0"}
    />
  );

  return (
    <div className="flex flex-1 flex-col gap-3" onKeyDown={onKeyDown}>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <SourceSelect sources={sources} value={source} onChange={selectSource} deviceName={deviceName} className="w-full sm:w-auto sm:min-w-64" />
        <Button
          variant="primary"
          size="sm"
          icon={<Play className="size-3.5" />}
          onClick={() => void runAll()}
          loading={anyRunning}
          disabled={!tab.cells.some((c) => c.text.trim())}
          title="Run every cell from the top; stops at the first one that fails"
        >
          Run all
        </Button>
        {!readOnly && (
          <>
            <Button size="sm" icon={<Save className="size-3.5" />} onClick={requestSave} loading={save.isPending} title={`Save (${MOD_KEY}+S)`}>
              Save
            </Button>
            <Button size="sm" variant="ghost" icon={<FilePlus className="size-3.5" />} onClick={() => setSaveDialog(true)} disabled={save.isPending}>
              Save as…
            </Button>
            {tab.savedId && (
              <input
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    requestSave();
                  }
                }}
                placeholder="What changed? (optional)"
                aria-label="What changed? Saved with the next version"
                title="A one-line note stored with the next version"
                maxLength={200}
                autoComplete="off"
                className="h-8 w-full rounded-lg border border-border bg-surface px-2.5 text-base focus:border-accent focus:ring-3 focus:ring-ring focus:outline-none sm:w-52 sm:text-xs"
              />
            )}
          </>
        )}
        <RowsSelect value={prefs.maxRows} onChange={(n) => setPrefs({ ...prefs, maxRows: n })} />
        <TimeoutSelect value={prefs.timeoutSeconds} onChange={(n) => setPrefs({ ...prefs, timeoutSeconds: n })} />
        <Button size="sm" variant="ghost" icon={<Eraser className="size-3.5" />} onClick={clearOutputs} disabled={Object.keys(results).length === 0}>
          Clear all outputs
        </Button>
        {readOnly && <ReadOnlyBadge />}
        <div className="ml-auto flex items-center gap-1">
          <ModeSwitch />
          <Button
            size="icon"
            variant="ghost"
            aria-label={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            aria-pressed={sidebarOpen}
            onClick={() => (isDesktop() ? setSidebarOpen((o) => !o) : setDrawerOpen(true))}
          >
            {sidebarOpen ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
          </Button>
        </div>
      </div>

      {offline && <ErrorAlert error={schema.error} />}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
        {sidebarOpen && sidebar(false)}

        <div className="flex min-w-0 flex-1 flex-col gap-3">
          {/* Tabs */}
          <div
            role="tablist"
            aria-label="Open documents"
            className="-mx-4 flex items-end overflow-x-auto border-b border-border px-4 [scrollbar-width:none] sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden"
          >
            {state.tabs.map((t) => {
              const active = t.id === tab.id;
              return (
                <div
                  key={t.id}
                  role="tab"
                  aria-selected={active}
                  onMouseDown={(e) => e.button === 1 && e.preventDefault()}
                  onAuxClick={(e) => e.button === 1 && requestClose(t)}
                  className={cn(
                    "group flex shrink-0 items-center gap-0.5 rounded-t-lg border border-b-0 py-1 pr-1 pl-2.5 text-sm",
                    active ? "border-border bg-surface text-fg" : "border-transparent text-muted hover:bg-surface-2 hover:text-fg",
                  )}
                >
                  <button type="button" onClick={() => activate(t.id)} className="flex min-w-0 items-center gap-1.5 py-1" title={tabTitle(t)}>
                    {t.folder && <span className="hidden text-[11px] text-muted sm:inline">{t.folder}/</span>}
                    <span className="max-w-40 truncate font-medium">{tabTitle(t)}</span>
                    {t.dirty && <span className="size-1.5 shrink-0 rounded-full bg-accent" title="Unsaved changes" />}
                  </button>
                  <button
                    type="button"
                    aria-label={`Close ${tabTitle(t)}`}
                    onClick={() => requestClose(t)}
                    className="rounded-md p-1 text-muted hover:bg-surface-2 hover:text-fg"
                  >
                    <X className="size-3" />
                  </button>
                </div>
              );
            })}
            <Button size="icon-sm" variant="ghost" aria-label="New tab" title="New tab" onClick={newTab} className="mb-1 ml-1">
              <Plus className="size-4" />
            </Button>
          </div>

          {saved && (
            <p className="-mt-1 text-xs text-muted" title={saved.updated_at}>
              v{saved.version} · last saved by {saved.updated_by_email} · {relativeTime(saved.updated_at)}
            </p>
          )}

          {behind && tab.dirty && dismissed[tab.id] !== behind.version && (
            <Alert
              tone="warning"
              action={
                <div className="flex flex-wrap gap-1">
                  <Button size="sm" onClick={() => setConflict({ tabId: tab.id, current: behind, mode: "remote" })}>
                    Show diff
                  </Button>
                  <Button size="sm" onClick={() => setReloading(behind)}>
                    Reload theirs
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDismissed((d) => ({ ...d, [tab.id]: behind.version }))}>
                    Keep editing
                  </Button>
                </div>
              }
            >
              {behind.updated_by_email} saved v{behind.version} while you were editing.
            </Alert>
          )}

          {/* Cells */}
          {tab.cells.map((c, i) => (
            <NotebookCell
              key={c.id}
              cell={c}
              index={i}
              count={tab.cells.length}
              source={source}
              entities={entities}
              result={results[c.id]}
              pendingWrite={pendingWrite?.cellId === c.id ? pendingWrite.reason : null}
              autoFocus={c.id === focusCellId}
              maxRows={prefs.maxRows}
              on={cell}
            />
          ))}
          <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" />} onClick={() => addCellBelow(tab.cells[tab.cells.length - 1].id)} className="self-start">
            Add cell
          </Button>
        </div>
      </div>

      <Dialog open={drawerOpen} onClose={() => setDrawerOpen(false)} placement="right" size="sm" title="Snippets, history and schema">
        {drawerOpen && sidebar(true)}
      </Dialog>

      <SnippetDialog
        open={saveDialog}
        title={tab.savedId ? "Save as a new snippet" : "Save query"}
        confirmLabel="Save"
        initialName={tab.name ?? ""}
        initialFolder={tab.folder}
        loading={save.isPending}
        onClose={() => setSaveDialog(false)}
        onSubmit={(name, folder) => save.mutate({ tab, name, folder })}
      />
      <ConfirmDialog
        open={closing !== null}
        onClose={() => setClosing(null)}
        onConfirm={() => {
          if (closing) doClose(closing);
        }}
        title={`Close “${closing ? tabTitle(closing) : ""}”?`}
        description="It has unsaved changes. They are lost when the tab closes."
        confirmLabel="Close without saving"
      />
      <ConfirmDialog
        open={reloading !== null}
        onClose={() => setReloading(null)}
        onConfirm={() => {
          if (reloading) reloadTheirs(reloading);
        }}
        title={`Reload v${reloading?.version}?`}
        description={`Your unsaved edits in this tab are replaced by what ${reloading?.updated_by_email} saved.`}
        confirmLabel="Reload theirs"
      />
      {conflict && conflictTab && (
        <DiffDialog
          open
          onClose={() => setConflict(null)}
          loading={save.isPending}
          title={
            conflict.mode === "save"
              ? "Someone saved first"
              : conflict.mode === "restore"
                ? "The snippet changed since you opened it"
                : `${conflict.current.updated_by_email} saved v${conflict.current.version}`
          }
          description={`${conflict.current.updated_by_email} saved v${conflict.current.version} ${relativeTime(conflict.current.updated_at)}. Red lines are theirs, green lines are yours.`}
          a={joinCells(parseDocument(conflict.current.query_text), source.kind)}
          b={joinCells(conflictTab.cells, source.kind)}
          footer={
            <>
              <Button onClick={() => setConflict(null)} disabled={save.isPending}>
                {conflict.mode === "remote" ? "Keep editing" : "Cancel"}
              </Button>
              <Button onClick={() => reloadTheirs(conflict.current)} disabled={save.isPending}>
                Reload theirs
              </Button>
              {conflict.mode === "save" && !readOnly && (
                <>
                  <Button
                    onClick={() => {
                      setConflict(null);
                      setSaveDialog(true);
                    }}
                    disabled={save.isPending}
                  >
                    Save as copy
                  </Button>
                  <Button
                    variant="primary"
                    loading={save.isPending}
                    onClick={() => save.mutate({ tab: conflictTab, version: conflict.current.version })}
                    title={`Saves your text as v${conflict.current.version + 1}; theirs stays in the history`}
                  >
                    Keep mine
                  </Button>
                </>
              )}
            </>
          }
        />
      )}
      <ConfirmDialog
        open={deletingCell !== null}
        onClose={() => setDeletingCell(null)}
        onConfirm={() => {
          if (deletingCell) removeCellNow(deletingCell);
        }}
        title="Delete this cell?"
        description="Its text and output are removed from the document."
        confirmLabel="Delete cell"
      />
    </div>
  );
}

// ---- One cell: editor with a small toolbar, and its output right below ----

function NotebookCell({
  cell,
  index,
  count,
  source,
  entities,
  result,
  pendingWrite,
  autoFocus,
  maxRows,
  on,
}: {
  cell: NotebookCell;
  index: number;
  count: number;
  source: DataSource;
  entities: readonly Entity[];
  result: CellResult | undefined;
  pendingWrite: string | null;
  autoFocus: boolean;
  maxRows: number;
  on: CellActions;
}) {
  const running = result?.run.status === "running";
  const edited = result !== undefined && !running && result.text !== cell.text;
  const onAction = (action: ConsoleAction) => {
    if (action === "submit" || action === "submit-next") on.run(cell.id, action === "submit-next");
  };
  const iconButton = (label: string, icon: React.ReactNode, onClick: () => void, disabled = false) => (
    <Button size="icon-sm" variant="ghost" aria-label={label} title={label} onClick={onClick} disabled={disabled}>
      {icon}
    </Button>
  );

  return (
    <section
      aria-label={`Cell ${index + 1}`}
      onFocus={() => on.focus(cell.id)}
      className="flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-xs focus-within:border-accent focus-within:ring-3 focus-within:ring-ring"
    >
      <header className="flex items-center gap-1 border-b border-border bg-surface-2 px-1.5 py-1">
        {running ? (
          <Button size="sm" variant="ghost" icon={<Square className="size-3.5" />} onClick={() => on.cancel(cell.id)}>
            Cancel
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            icon={<Play className="size-3.5 text-accent" />}
            onClick={() => on.run(cell.id, false)}
            disabled={!cell.text.trim()}
            title={`Run this cell (${MOD_KEY}+Enter; Shift+Enter runs and moves to the next cell)`}
          >
            Run
          </Button>
        )}
        <span className="text-[11px] text-muted tabular-nums">[{index + 1}]</span>
        {edited && <span className="text-[11px] text-muted italic">edited since last run</span>}
        <div className="ml-auto flex items-center">
          {iconButton("Move cell up", <ArrowUp className="size-3.5" />, () => on.move(cell.id, -1), index === 0)}
          {iconButton("Move cell down", <ArrowDown className="size-3.5" />, () => on.move(cell.id, 1), index === count - 1)}
          {iconButton("Add cell below", <Plus className="size-3.5" />, () => on.addBelow(cell.id))}
          {iconButton("Delete cell", <Trash2 className="size-3.5" />, () => on.remove(cell.id))}
        </div>
      </header>

      <QueryEditor
        value={cell.text}
        onChange={(text) => on.change(cell.id, text)}
        kind={source.kind}
        engine={source.engine}
        entities={entities}
        mode="editor"
        maxHeight="24rem"
        autoFocus={autoFocus}
        onAction={onAction}
        onHandle={(h) => on.handle(cell.id, h)}
      />

      {pendingWrite && (
        <div className="border-t border-border p-2">
          <PendingWriteAlert reason={pendingWrite} onCancel={on.cancelWrite} onConfirm={on.confirmWrite} />
        </div>
      )}

      {result && <CellOutput result={result} source={source} maxRows={maxRows} onToggle={() => on.toggle(cell.id)} onCancel={() => on.cancel(cell.id)} />}
    </section>
  );
}

function CellOutput({
  result,
  source,
  maxRows,
  onToggle,
  onCancel,
}: {
  result: CellResult;
  source: DataSource;
  maxRows: number;
  onToggle: () => void;
  onCancel: () => void;
}) {
  const { run } = result;
  const Chevron = result.collapsed ? ChevronRight : ChevronDown;
  return (
    <div className="border-t border-border" aria-live="polite">
      <div className="flex items-center gap-2 px-2 py-1 text-xs text-muted">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!result.collapsed}
          aria-label={result.collapsed ? "Show output" : "Hide output"}
          className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 rounded-md px-1 py-0.5 text-left hover:bg-surface-2"
        >
          <Chevron className="size-3.5 shrink-0" />
          {run.status === "running" && (
            <>
              <Spinner className="size-3.5" />
              <span>
                Running against {source.name}… up to {run.request.timeout_seconds} s
              </span>
            </>
          )}
          {run.status === "done" && (
            <>
              <Badge tone={run.response.kind === "sql" ? "sql" : "nosql"}>{engineLabel(run.response.engine)}</Badge>
              <span className={firstError(run.response) ? "font-medium text-danger" : "font-medium text-success"}>
                {firstError(run.response) ? "Failed" : "Success"}
              </span>
              <span>· {run.response.kind === "sql" ? sqlSummaryText(summarizeSql(run.response)) : mongoSummaryText(run.response)}</span>
              <span>· {formatMs(run.response.duration_ms)}</span>
              <span>· {formatTime(result.at)}</span>
            </>
          )}
          {run.status === "failed" && (
            <>
              <span className="font-medium text-danger">{run.failure.title}</span>
              <span>· {formatTime(result.at)}</span>
            </>
          )}
        </button>
        {run.status === "running" && (
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
      {!result.collapsed && run.status !== "running" && (
        <div className="px-2 pb-2">
          {run.status === "failed" &&
            (run.failure.offline ? (
              <ErrorAlert error={run.error} />
            ) : (
              <Alert tone={run.failure.code === "read_only_role" ? "warning" : "danger"} title={run.failure.title}>
                {run.failure.message}
              </Alert>
            ))}
          {run.status === "done" &&
            (run.response.kind === "sql" ? (
              <SqlResults response={run.response} maxRows={maxRows} />
            ) : (
              <MongoResults response={run.response} maxRows={maxRows} />
            ))}
        </div>
      )}
    </div>
  );
}
