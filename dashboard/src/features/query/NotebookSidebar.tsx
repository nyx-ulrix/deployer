import { useMemo, useState } from "react";
import { useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { FileCode, Folder, GitCommitVertical, History, MoreHorizontal, Pencil, Plus, RotateCcw, Search, Trash2, Users, X } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useQueryLog, useSavedQueries, useSavedQueryVersion, useSavedQueryVersions } from "../../api/hooks";
import type { DataSource, DataSourceKind, Project, QueryRun, SavedQuery, SavedQueryVersion, SourceSchema } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Menu, MenuItem } from "../../components/ui/Menu";
import { StatusDot } from "../../components/ui/Progress";
import { PageSpinner } from "../../components/ui/Spinner";
import { ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatDateTime, formatNumber, relativeTime } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";
import { DiffDialog } from "./DiffView";
import { EntitySidebar } from "./EntitySidebar";
import { historyRow, joinCells, parseDocument, versionConflict, type NotebookTab } from "./notebook";
import { SnippetDialog } from "./SnippetDialog";

type Props = {
  project: Project;
  source: DataSource;
  schema: UseQueryResult<SourceSchema | null>;
  /** Saved query of the active tab, highlighted in the list. */
  openSavedId: string | null;
  onOpenSaved: (saved: SavedQuery) => void;
  onNew: () => void;
  onRenamed: (saved: SavedQuery) => void;
  onDeleted: (id: string) => void;
  /** The active tab: its snippet's versions are listed and diffed against its cells. */
  tab: NotebookTab;
  kind: DataSourceKind;
  /** A restore made a new version; the tab takes its text. */
  onRestored: (saved: SavedQuery) => void;
  /** The restore lost a race: the console shows the server copy with a reload option. */
  onRestoreConflict: (current: SavedQuery) => void;
  /** A history row was clicked: its text goes into a new cell. */
  onInsertHistory: (text: string) => void;
  /** A table/collection was clicked: a starter query goes into the active cell. */
  onInsertEntity: (name: string) => void;
  /** Shown as a close button when the sidebar can be hidden; omit inside the drawer. */
  onClose?: () => void;
  className?: string;
};

const NO_FOLDER = "";

/** Snippets grouped by folder (unfiled last), filtered by name or folder. */
function groupSnippets(list: readonly SavedQuery[], query: string): [string, SavedQuery[]][] {
  const q = query.trim().toLowerCase();
  const groups = new Map<string, SavedQuery[]>();
  for (const s of list) {
    if (q && !s.name.toLowerCase().includes(q) && !(s.folder ?? "").toLowerCase().includes(q)) continue;
    const key = s.folder ?? NO_FOLDER;
    groups.set(key, [...(groups.get(key) ?? []), s]);
  }
  return [...groups.entries()].sort(([a], [b]) => (a === NO_FOLDER ? 1 : b === NO_FOLDER ? -1 : a.localeCompare(b)));
}

function SectionHeader({ icon, title, count, children }: { icon: React.ReactNode; title: string; count?: number; children?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 border-b border-border py-1.5 pr-1 pl-3">
      {icon}
      <span className="text-xs font-semibold tracking-wide text-muted uppercase">{title}</span>
      {count !== undefined && <span className="text-xs text-muted tabular-nums">{count}</span>}
      <div className="ml-auto flex items-center">{children}</div>
    </div>
  );
}

const section = "flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-xs";

/** Snippets, this user's history for the selected source and the schema tree (QUERY_EDITOR.md → sidebar). */
export function NotebookSidebar({
  project,
  source,
  schema,
  openSavedId,
  onOpenSaved,
  onNew,
  onRenamed,
  onDeleted,
  tab,
  kind,
  onRestored,
  onRestoreConflict,
  onInsertHistory,
  onInsertEntity,
  onClose,
  className,
}: Props) {
  return (
    <aside className={cn("flex flex-col gap-3", className)} aria-label="Notebook sidebar">
      <Snippets project={project} openSavedId={openSavedId} onOpen={onOpenSaved} onNew={onNew} onRenamed={onRenamed} onDeleted={onDeleted} onClose={onClose} />
      {tab.savedId && (
        <VersionsSection key={tab.savedId} project={project} savedId={tab.savedId} tab={tab} kind={kind} onRestored={onRestored} onConflict={onRestoreConflict} />
      )}
      <HistorySection project={project} source={source} onInsert={onInsertHistory} />
      <EntitySidebar source={source} schema={schema} onInsert={onInsertEntity} />
    </aside>
  );
}

function Snippets({
  project,
  openSavedId,
  onOpen,
  onNew,
  onRenamed,
  onDeleted,
  onClose,
}: Pick<Props, "project" | "openSavedId" | "onNew" | "onRenamed" | "onDeleted" | "onClose"> & { onOpen: Props["onOpenSaved"] }) {
  const { can } = useProjectContext();
  const user = useCurrentUser();
  const toast = useToast();
  const queryClient = useQueryClient();
  const list = useSavedQueries(project.id);
  const [filter, setFilter] = useState("");
  const [renaming, setRenaming] = useState<SavedQuery | null>(null);
  const [deleting, setDeleting] = useState<SavedQuery | null>(null);
  const groups = useMemo(() => groupSnippets(list.data ?? [], filter), [list.data, filter]);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: qk.savedQueries(project.id) });
  // Phase 2: PATCH (rename, move) is for any developer+; DELETE stays with the snippet's owner or admin+.
  const canDelete = (s: SavedQuery) => s.owner_id === user.id || can("admin");

  const rename = useMutation({
    mutationFn: async ({ snippet, name, folder }: { snippet: SavedQuery; name: string; folder: string | null }) => {
      try {
        return await api.savedQueries.update(project.id, snippet.id, { name, folder, version: snippet.version });
      } catch (e) {
        const current = versionConflict(e);
        if (!current) throw e;
        // A rename is metadata-only: retrying on top of whoever saved first changes none of their text, so
        // one retry with the fresh version is safe (a second 409 surfaces as an error like any other).
        return api.savedQueries.update(project.id, snippet.id, { name, folder, version: current.version });
      }
    },
    onSuccess: (saved) => {
      void invalidate();
      onRenamed(saved);
      setRenaming(null);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't rename the snippet"),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.savedQueries.remove(project.id, id),
    onSuccess: (_res, id) => {
      void invalidate();
      onDeleted(id);
      setDeleting(null);
      toast.success("Snippet deleted.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete the snippet"),
  });

  return (
    <section className={section} aria-label="Snippets">
      <SectionHeader icon={<FileCode className="size-3.5 text-accent" />} title="Snippets" count={list.data?.length}>
        <Button size="icon-sm" variant="ghost" aria-label="New query" title="New query" onClick={onNew}>
          <Plus className="size-3.5" />
        </Button>
        {onClose && (
          <Button size="icon-sm" variant="ghost" aria-label="Hide sidebar" title="Hide" onClick={onClose}>
            <X className="size-3.5" />
          </Button>
        )}
      </SectionHeader>
      {(list.data?.length ?? 0) > 5 && (
        <div className="relative border-b border-border p-1.5">
          <Search className="pointer-events-none absolute top-1/2 left-4 size-3.5 -translate-y-1/2 text-muted" />
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search snippets…"
            aria-label="Search snippets"
            className="h-8 w-full rounded-lg border border-border bg-surface pr-2 pl-8 text-base focus:border-accent focus:ring-3 focus:ring-ring focus:outline-none sm:text-xs"
          />
        </div>
      )}
      <div className="max-h-72 min-h-0 overflow-y-auto p-1">
        {list.isPending ? (
          <PageSpinner label="Loading snippets…" />
        ) : list.isError ? (
          <ErrorAlert error={list.error} className="m-1" />
        ) : list.data.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted">Save a query and it shows up here for the whole project.</p>
        ) : groups.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted">No matches.</p>
        ) : (
          groups.map(([folder, items]) => (
            <div key={folder}>
              {folder !== NO_FOLDER && (
                <p className="flex items-center gap-1.5 px-2 pt-2 pb-0.5 text-[11px] font-medium text-muted">
                  <Folder className="size-3" /> {folder}
                </p>
              )}
              {items.map((s) => (
                <div
                  key={s.id}
                  className={cn("group flex items-center rounded-lg pr-0.5 hover:bg-surface-2", s.id === openSavedId && "bg-accent-soft/60")}
                >
                  <button
                    type="button"
                    onClick={() => onOpen(s)}
                    title={`${s.name} — saved by ${s.owner_email}`}
                    className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-sm"
                  >
                    <FileCode className="size-3.5 shrink-0 text-muted" />
                    <span className="min-w-0 flex-1 truncate">{s.name}</span>
                  </button>
                  {can("developer") && (
                    <Menu
                      trigger={({ toggle, open }) => (
                        <Button size="icon-sm" variant="ghost" aria-label={`Actions for ${s.name}`} aria-expanded={open} onClick={toggle}>
                          <MoreHorizontal className="size-3.5" />
                        </Button>
                      )}
                    >
                      {(close) => (
                        <>
                          <MenuItem
                            icon={<Pencil />}
                            onClick={() => {
                              setRenaming(s);
                              close();
                            }}
                          >
                            Rename or move
                          </MenuItem>
                          {canDelete(s) && (
                            <MenuItem
                              icon={<Trash2 />}
                              danger
                              onClick={() => {
                                setDeleting(s);
                                close();
                              }}
                            >
                              Delete
                            </MenuItem>
                          )}
                        </>
                      )}
                    </Menu>
                  )}
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      <SnippetDialog
        open={renaming !== null}
        title="Rename snippet"
        confirmLabel="Rename"
        initialName={renaming?.name}
        initialFolder={renaming?.folder}
        loading={rename.isPending}
        onClose={() => setRenaming(null)}
        onSubmit={(name, folder) => renaming && rename.mutate({ snippet: renaming, name, folder })}
      />
      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (deleting) remove.mutate(deleting.id);
        }}
        title={`Delete “${deleting?.name}”?`}
        description="The snippet is removed for everyone in the project. An open tab keeps its text as an unsaved document."
        confirmLabel="Delete"
        loading={remove.isPending}
      />
    </section>
  );
}

/** Who changed what (QUERY_EDITOR.md → phase 2): every version, diffable against the tab, restorable by developer+. */
function VersionsSection({
  project,
  savedId,
  tab,
  kind,
  onRestored,
  onConflict,
}: {
  project: Project;
  savedId: string;
  tab: NotebookTab;
  kind: DataSourceKind;
  onRestored: (saved: SavedQuery) => void;
  onConflict: (current: SavedQuery) => void;
}) {
  const { can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const versions = useSavedQueryVersions(project.id, savedId);
  const [viewing, setViewing] = useState<SavedQueryVersion | null>(null);
  const [restoring, setRestoring] = useState<SavedQueryVersion | null>(null);
  const viewed = useSavedQueryVersion(project.id, savedId, viewing?.version ?? null);

  const restore = useMutation({
    mutationFn: (v: SavedQueryVersion) =>
      api.savedQueries.restore(project.id, savedId, { version: v.version, current_version: tab.version ?? 0 }),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: qk.savedQueries(project.id) });
      void queryClient.invalidateQueries({ queryKey: qk.savedQueryVersions(project.id, savedId) });
      setRestoring(null);
      onRestored(saved);
    },
    onError: (e) => {
      setRestoring(null);
      const current = versionConflict(e);
      if (current) onConflict(current);
      else toast.error(errorMessage(e), "Couldn't restore that version");
    },
  });

  return (
    <section className={section} aria-label="Versions">
      <SectionHeader icon={<GitCommitVertical className="size-3.5 text-muted" />} title="Versions" count={versions.data?.length} />
      <div className="max-h-72 min-h-0 overflow-y-auto p-1">
        {versions.isPending ? (
          <PageSpinner label="Loading versions…" />
        ) : versions.isError ? (
          <ErrorAlert error={versions.error} className="m-1" />
        ) : versions.data.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted">Every save of this snippet shows up here.</p>
        ) : (
          <ul aria-label="Saved versions">
            {versions.data.map((v) => {
              const current = v.version === tab.version;
              return (
                <li key={v.id} className="group flex items-start gap-1 rounded-lg px-2 py-1.5 hover:bg-surface-2">
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-xs">
                      <span className={cn("font-semibold tabular-nums", current ? "text-accent" : "text-fg")}>v{v.version}</span>
                      <span className="min-w-0 truncate text-muted" title={v.author_email}>
                        {v.author_email}
                      </span>
                    </p>
                    <p className="flex items-center gap-1.5 text-[11px] text-muted">
                      <span title={formatDateTime(v.created_at)}>{relativeTime(v.created_at)}</span>
                      <span>·</span>
                      <span className="tabular-nums">{formatNumber(v.chars)} chars</span>
                    </p>
                    {v.message && <p className="truncate text-xs text-fg/80 italic" title={v.message}>{v.message}</p>}
                  </div>
                  <Button size="icon-sm" variant="ghost" aria-label={`Compare v${v.version} with this tab`} title="View diff" onClick={() => setViewing(v)}>
                    <GitCommitVertical className="size-3.5" />
                  </Button>
                  {can("developer") && !current && (
                    <Button size="icon-sm" variant="ghost" aria-label={`Restore v${v.version}`} title="Restore as a new version" onClick={() => setRestoring(v)}>
                      <RotateCcw className="size-3.5" />
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {viewing && (
        <DiffDialog
          open
          onClose={() => setViewing(null)}
          title={`v${viewing.version} vs this tab`}
          description={`Red lines are v${viewing.version} (${viewing.author_email}, ${relativeTime(viewing.created_at)}), green lines are your tab.`}
          a={viewed.data ? joinCells(parseDocument(viewed.data.query_text), kind) : ""}
          b={joinCells(tab.cells, kind)}
          status={viewed.isPending ? <PageSpinner label="Loading version…" /> : viewed.isError ? <ErrorAlert error={viewed.error} /> : undefined}
          footer={
            <>
              {can("developer") && viewing.version !== tab.version && (
                <Button
                  onClick={() => {
                    setRestoring(viewing);
                    setViewing(null);
                  }}
                >
                  Restore…
                </Button>
              )}
              <Button variant="primary" onClick={() => setViewing(null)}>
                Close
              </Button>
            </>
          }
        />
      )}
      <ConfirmDialog
        open={restoring !== null}
        onClose={() => setRestoring(null)}
        onConfirm={() => {
          if (restoring) restore.mutate(restoring);
        }}
        title={`Restore v${restoring?.version}?`}
        description={`Its text becomes a new version v${(tab.version ?? 0) + 1} and replaces the document in this tab${tab.dirty ? ", including your unsaved edits" : ""}. Nothing is deleted from the history.`}
        confirmLabel="Restore"
        destructive={tab.dirty}
        loading={restore.isPending}
      />
    </section>
  );
}

function HistorySection({ project, source, onInsert }: { project: Project; source: DataSource; onInsert: (text: string) => void }) {
  const { can } = useProjectContext();
  const toast = useToast();
  const [everyone, setEveryone] = useState(false);
  const scope = everyone && can("admin") ? "all" : "me";
  const log = useQueryLog(project.id, source.id, scope);
  const runs = log.data?.pages.flatMap((p) => p.runs) ?? [];

  // List responses truncate long texts; fetch the full row before inserting it.
  const pick = async (run: QueryRun) => {
    if (!run.query_truncated) return onInsert(run.query_text);
    try {
      onInsert((await api.queryLog.get(project.id, run.id)).query_text);
    } catch (e) {
      toast.error(errorMessage(e), "Couldn't load that run");
    }
  };

  return (
    <section className={section} aria-label="History">
      <SectionHeader icon={<History className="size-3.5 text-muted" />} title="History">
        {can("admin") && (
          <Button
            size="icon-sm"
            variant="ghost"
            aria-pressed={everyone}
            aria-label={everyone ? "Show only my runs" : "Show everyone's runs"}
            title={everyone ? "Showing everyone's runs" : "Show everyone's runs"}
            onClick={() => setEveryone((v) => !v)}
            className={cn(everyone && "bg-accent-soft text-accent")}
          >
            <Users className="size-3.5" />
          </Button>
        )}
      </SectionHeader>
      <div className="max-h-72 min-h-0 overflow-y-auto p-1">
        {log.isPending ? (
          <PageSpinner label="Loading history…" />
        ) : log.isError ? (
          <ErrorAlert error={log.error} className="m-1" />
        ) : runs.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted">Queries run on {source.name} show up here.</p>
        ) : (
          <ul aria-label="Recent runs">
            {runs.map((run) => {
              const row = historyRow(run);
              return (
                <li key={run.id}>
                  <button
                    type="button"
                    onClick={() => void pick(run)}
                    title={run.error_message ?? "Insert as a new cell"}
                    className="flex w-full flex-col gap-0.5 rounded-lg px-2 py-1.5 text-left hover:bg-surface-2"
                  >
                    <span className="flex min-w-0 w-full items-center gap-1.5 text-[11px] text-muted">
                      <StatusDot tone={row.tone} />
                      <span title={formatDateTime(run.created_at)}>{row.when}</span>
                      <span>·</span>
                      <span className="tabular-nums">{row.duration}</span>
                      {scope === "all" && <span className="min-w-0 truncate">· {run.user_email}</span>}
                    </span>
                    <code className="w-full truncate font-mono text-xs text-fg">{row.line || "(empty)"}</code>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {log.hasNextPage && (
          <Button size="sm" variant="ghost" className="mt-1 w-full" loading={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()}>
            Load more
          </Button>
        )}
      </div>
    </section>
  );
}
