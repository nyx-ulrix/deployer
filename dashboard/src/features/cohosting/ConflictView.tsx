import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, GitMerge, History, RotateCcw } from "lucide-react";
import { errorMessage, isApiError, isDeviceOffline } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useSyncConflict, useSyncHistory } from "../../api/hooks";
import type { ConflictChoice, DataSource, JsonObject, JsonValue, SyncConflict, SyncHistoryItem, SyncSide } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, EmptyState, ErrorState } from "../../components/ui/States";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatDateTime, relativeTime } from "../../lib/format";
import { JsonEditor } from "../data/JsonEditor";
import { parseJsonObject, pretty } from "../data/json";
import { useProjectContext } from "../projects/project-context";
import {
  buildCombined,
  canCombine,
  defaultPicks,
  deletionNote,
  deviceOf,
  diffRows,
  displayValue,
  historyLabel,
  keyText,
  RESOLUTION_LABELS,
  type Picks,
} from "./cohosting";
import { useCanManage, useMemberNames } from "./hooks";

type Resolution = { choice: ConflictChoice; value?: JsonObject | null };

function offlineAware(e: unknown, device: string): string {
  return isDeviceOffline(e) ? `${device} is offline. Nothing was changed; try again once it's back.` : errorMessage(e);
}

/**
 * One conflict, shown like a Git merge conflict: base / main server ("ours") / co-host ("theirs") per
 * field. Nothing is ever resolved automatically; the chosen version is written to both copies.
 */
export function ConflictView({
  source,
  conflictId,
  onBack,
  onHistory,
}: {
  source: DataSource;
  conflictId: string;
  onBack: () => void;
  onHistory: (table: string, key: JsonObject) => void;
}) {
  const { project } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const conflict = useSyncConflict(project.id, source.id, conflictId);
  const nameOf = useMemberNames(project.id);
  const canManage = useCanManage(source);
  const [pending, setPending] = useState<Resolution | null>(null);
  const [combining, setCombining] = useState(false);
  const device = conflict.data ? deviceOf(source, conflict.data.replica_id) : "the co-host";

  const resolve = useMutation({
    mutationFn: (body: Resolution) => api.cohosting.resolve(project.id, source.id, conflictId, body),
    onSuccess: (c) => {
      queryClient.setQueryData(qk.syncConflict(project.id, source.id, conflictId), c);
      void queryClient.invalidateQueries({ queryKey: qk.syncFor(project.id, source.id) });
      void queryClient.invalidateQueries({ queryKey: qk.dataSources(project.id) });
      setPending(null);
      setCombining(false);
      toast.success(`${RESOLUTION_LABELS[c.resolution ?? ""] ?? "Resolved"}: written to both copies.`, "Conflict resolved");
    },
    onError: (e) => {
      setPending(null);
      toast.error(offlineAware(e, device), "Couldn't resolve the conflict");
      // Someone else resolved it meanwhile: show their outcome.
      if (isApiError(e) && e.code === "conflict_resolved") void conflict.refetch();
    },
  });

  const backButton = (
    <Button size="sm" variant="ghost" icon={<ArrowLeft className="size-4" />} onClick={onBack}>
      All conflicts
    </Button>
  );
  if (conflict.isPending) return <PageSpinner />;
  if (conflict.isError) {
    return (
      <div className="space-y-3">
        {backButton}
        <ErrorState error={conflict.error} onRetry={() => void conflict.refetch()} />
      </div>
    );
  }

  const c = conflict.data;
  const open = c.status === "open";
  const deleted = deletionNote(c);
  const manage = canManage(c.replica_id);
  const sideRow = (side: SyncSide) => (side === "primary" ? c.primary : c.replica);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {backButton}
        <Button size="sm" variant="ghost" icon={<History className="size-4" />} className="ml-auto" onClick={() => onHistory(c.table, c.key)}>
          History of this row
        </Button>
      </div>

      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{c.table}</span>
            <span className="font-mono text-sm font-normal text-muted">{keyText(c.key)}</span>
            <Badge tone={open ? "warning" : "success"}>{open ? "Open" : "Resolved"}</Badge>
          </span>
        }
        description={`Main server vs ${device} · detected ${relativeTime(c.created_at)}`}
      >
        <div className="space-y-3">
          {open ? (
            <Alert tone="info">
              This row changed on both copies before they synced. Nothing was overwritten: each copy keeps its own
              version and this row doesn't sync until you choose. Every other row keeps syncing.
            </Alert>
          ) : (
            <Alert tone="success" title={`Resolved: ${RESOLUTION_LABELS[c.resolution ?? ""] ?? "—"}`}>
              By {nameOf(c.resolved_by_id)}, {formatDateTime(c.resolved_at)}. The chosen version was written to both
              copies.
            </Alert>
          )}
          {deleted && <Alert tone="warning">{deleted}</Alert>}
          {c.base === null && !deleted && (
            <p className="text-xs text-muted">
              The version both sides started from isn't known, so every field that differs is shown as changed on both.
            </p>
          )}
          <DiffTable conflict={c} device={device} />
          <details className="text-sm">
            <summary className="cursor-pointer text-muted hover:text-fg">Whole rows</summary>
            <div className="mt-2 grid gap-3 md:grid-cols-3">
              <RowJson title="Base" value={c.base} empty="Unknown" />
              <RowJson title="Main server (ours)" value={c.primary} empty="Deleted" />
              <RowJson title={`${device} (theirs)`} value={c.replica} empty="Deleted" />
              {!open && <RowJson title="Resolved to" value={c.resolved} empty="Deleted" />}
            </div>
          </details>
        </div>
      </Card>

      {open && !manage && (
        <Alert tone="info">Only the co-host who owns this copy ({device}) or a project admin can resolve it.</Alert>
      )}
      {open && manage && !combining && (
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => setPending({ choice: "primary" })}>
            Keep main server
          </Button>
          <Button variant="primary" onClick={() => setPending({ choice: "replica" })}>
            Keep co-host
          </Button>
          {canCombine(c) && (
            <Button icon={<GitMerge className="size-4" />} onClick={() => setCombining(true)}>
              Combine…
            </Button>
          )}
        </div>
      )}
      {open && manage && combining && (
        <CombinePanel
          conflict={c}
          device={device}
          onCancel={() => setCombining(false)}
          onSubmit={(value) => setPending({ choice: "manual", value })}
        />
      )}

      {pending && (
        <ConfirmDialog
          open
          destructive={false}
          onClose={() => setPending(null)}
          onConfirm={() => resolve.mutate(pending)}
          loading={resolve.isPending}
          title={
            pending.choice === "primary"
              ? "Keep the main server's version?"
              : pending.choice === "replica"
                ? `Keep ${device}'s version?`
                : "Use the combined version?"
          }
          confirmLabel="Resolve"
          description={
            <>
              It's written to both copies (the main server and {device}) and the row starts syncing again.
              {pending.choice !== "manual" && sideRow(pending.choice) === null && (
                <strong className="text-fg"> That version is a delete: the row is deleted on both copies.</strong>
              )}{" "}
              Both original versions stay in this row's history.
            </>
          }
        />
      )}
    </div>
  );
}

function RowJson({ title, value, empty }: { title: string; value: JsonObject | null; empty: string }) {
  return (
    <div className="min-w-0">
      <p className="mb-1 text-xs font-medium text-muted">{title}</p>
      {value === null ? (
        <p className="text-xs text-muted italic">{empty}</p>
      ) : (
        <pre className="max-h-64 overflow-auto rounded-lg bg-surface-2 p-2 font-mono text-xs">{pretty(value)}</pre>
      )}
    </div>
  );
}

function ValueCell({ value, deleted, changed }: { value: JsonValue; deleted: boolean; changed: boolean }) {
  return (
    <Td className={cn("max-w-64 font-mono text-xs break-words", changed ? "font-semibold text-fg" : "text-muted")}>
      {deleted ? <span className="font-sans text-danger italic">deleted</span> : displayValue(value)}
    </Td>
  );
}

function DiffTable({ conflict: c, device }: { conflict: SyncConflict; device: string }) {
  const rows = diffRows(c);
  if (rows.length === 0) return <p className="text-sm text-muted">No field differences to show.</p>;
  return (
    <div className="space-y-1.5">
      <Table>
        <THead>
          <Tr>
            <Th>Field</Th>
            <Th>Base</Th>
            <Th>Main server (ours)</Th>
            <Th>{device} (theirs)</Th>
          </Tr>
        </THead>
        <TBody>
          {rows.map((r) => (
            <Tr key={r.name} className={cn(r.kind === "conflict" && "bg-danger-soft/40")}>
              <Td className="font-mono text-xs">
                <span className="flex flex-wrap items-center gap-1.5">
                  {r.name}
                  {r.kind === "conflict" && <Badge tone="danger">changed on both</Badge>}
                  {r.kind === "same" && <Badge>same change</Badge>}
                </span>
              </Td>
              <Td className="max-w-64 font-mono text-xs break-words text-muted">
                {c.base === null ? <span className="font-sans italic">unknown</span> : displayValue(r.base)}
              </Td>
              <ValueCell value={r.primary} deleted={c.primary === null} changed={r.kind !== "replica"} />
              <ValueCell value={r.replica} deleted={c.replica === null} changed={r.kind !== "primary"} />
            </Tr>
          ))}
        </TBody>
      </Table>
      <p className="text-xs text-muted">
        Bold values changed since the base. Red rows changed differently on both sides and need a decision.
      </p>
    </div>
  );
}

/** Manual merge: pick a side per field (pre-filled like the server's `suggested`), then edit the row freely. */
function CombinePanel({
  conflict: c,
  device,
  onCancel,
  onSubmit,
}: {
  conflict: SyncConflict;
  device: string;
  onCancel: () => void;
  onSubmit: (value: JsonObject) => void;
}) {
  const [picks, setPicks] = useState<Picks>(() => defaultPicks(c));
  const [text, setText] = useState(() => pretty(buildCombined(c, defaultPicks(c))));
  const parsed = parseJsonObject(text);
  const pick = (name: string, side: SyncSide) => {
    const next = { ...picks, [name]: side };
    setPicks(next);
    setText(pretty(buildCombined(c, next)));
  };

  return (
    <Card
      title="Combine both versions"
      description={
        c.suggested
          ? "Pre-filled with Deployer's suggestion: each field takes the side that changed it."
          : "Pick a side for each field, then adjust the row if needed."
      }
    >
      <div className="space-y-4">
        <ul className="space-y-2">
          {diffRows(c).map((r) => (
            <li key={r.name} className={cn("rounded-lg border border-border p-2", r.kind === "conflict" && "border-danger")}>
              <p className="mb-1.5 font-mono text-xs font-medium">{r.name}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {(["primary", "replica"] as const).map((side) => (
                  <label
                    key={side}
                    className={cn(
                      "flex cursor-pointer items-start gap-2 rounded-md border border-transparent p-2 text-xs hover:bg-surface-2",
                      picks[r.name] === side && "border-accent bg-accent-soft/40",
                    )}
                  >
                    <input
                      type="radio"
                      name={`pick-${r.name}`}
                      className="mt-0.5 size-3.5 shrink-0 accent-[var(--accent)]"
                      checked={picks[r.name] === side}
                      onChange={() => pick(r.name, side)}
                    />
                    <span className="min-w-0">
                      <span className="block text-muted">{side === "primary" ? "Main server" : device}</span>
                      <span className="block font-mono break-all">{displayValue(side === "primary" ? r.primary : r.replica)}</span>
                    </span>
                  </label>
                ))}
              </div>
            </li>
          ))}
        </ul>
        <JsonEditor
          label="Combined row"
          value={text}
          onChange={setText}
          rows={10}
          hint="Edit freely; key fields can't change. Picking a side above rewrites this text."
        />
        <div className="flex flex-wrap justify-end gap-2">
          <Button onClick={onCancel}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!parsed.ok || parsed.value === null}
            onClick={() => parsed.ok && parsed.value && onSubmit(parsed.value)}
          >
            Use combined version
          </Button>
        </div>
      </div>
    </Card>
  );
}

/** Kept versions and resolved conflicts of one row, newest first, with "Restore this version". */
export function HistoryView({
  source,
  table,
  rowKey,
  onBack,
}: {
  source: DataSource;
  table: string;
  rowKey: JsonObject;
  onBack: () => void;
}) {
  const { project } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const history = useSyncHistory(project.id, source.id, table, rowKey);
  const nameOf = useMemberNames(project.id);
  const canManage = useCanManage(source);
  const [restoring, setRestoring] = useState<SyncHistoryItem | null>(null);
  const device = restoring ? deviceOf(source, restoring.replica_id) : "the co-host";

  const restore = useMutation({
    mutationFn: (item: SyncHistoryItem) =>
      api.cohosting.restore(project.id, source.id, { table, key: rowKey, version_id: item.id }),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: qk.syncFor(project.id, source.id) });
      void queryClient.invalidateQueries({ queryKey: qk.dataSources(project.id) });
      setRestoring(null);
      toast.success(
        res.resolved_conflict_id ? "Written to both copies; the open conflict on this row is closed." : "Written to both copies.",
        "Version restored",
      );
    },
    onError: (e) => {
      setRestoring(null);
      toast.error(offlineAware(e, device), "Couldn't restore");
    },
  });

  return (
    <div className="space-y-4">
      <Button size="sm" variant="ghost" icon={<ArrowLeft className="size-4" />} onClick={onBack}>
        All conflicts
      </Button>
      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            <History className="size-4 text-muted" /> History ·<span className="font-mono">{table}</span>
            <span className="font-mono text-sm font-normal text-muted">{keyText(rowKey)}</span>
          </span>
        }
        description="Every version the sync applied or someone chose for this row. Versions are kept for rows changed since the copy was made, until both copies have agreed for 7 days."
        bodyClassName="p-0 sm:p-0"
      >
        {history.isPending ? (
          <PageSpinner />
        ) : history.isError ? (
          <ErrorState className="m-4 border-0" error={history.error} onRetry={() => void history.refetch()} />
        ) : history.data.length === 0 ? (
          <EmptyState className="m-4" title="No kept versions" description="Nothing was recorded for this row, or its versions were pruned." />
        ) : (
          <ol className="divide-y divide-border">
            {history.data.map((item) => (
              <li key={`${item.type}-${item.id}`} className="space-y-1.5 px-4 py-3 sm:px-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{historyLabel(item)}</span>
                  {item.value === null && <Badge tone="danger">deleted</Badge>}
                  <span className="text-xs text-muted" title={formatDateTime(item.at)}>
                    {item.user_id ? `${nameOf(item.user_id)} · ` : ""}
                    {relativeTime(item.at)}
                  </span>
                  {item.type === "version" && canManage(item.replica_id) && (
                    <Button size="sm" className="ml-auto" icon={<RotateCcw className="size-3.5" />} onClick={() => setRestoring(item)}>
                      Restore this version
                    </Button>
                  )}
                </div>
                <details className="text-sm">
                  <summary className="cursor-pointer text-xs text-muted hover:text-fg">Show value</summary>
                  <div className="mt-2 grid gap-3 md:grid-cols-3">
                    <RowJson title={item.type === "conflict" ? "Resolved to" : "Value"} value={item.value} empty="Deleted" />
                    {item.type === "conflict" && (
                      <>
                        <RowJson title="Main server had" value={item.primary ?? null} empty="Deleted" />
                        <RowJson title={`${deviceOf(source, item.replica_id)} had`} value={item.replica ?? null} empty="Deleted" />
                      </>
                    )}
                  </div>
                </details>
              </li>
            ))}
          </ol>
        )}
      </Card>
      <ConfirmDialog
        open={restoring !== null}
        destructive={false}
        onClose={() => setRestoring(null)}
        onConfirm={() => {
          if (restoring) restore.mutate(restoring);
        }}
        loading={restore.isPending}
        title="Restore this version?"
        confirmLabel="Restore on both copies"
        description={
          <>
            The row is set to this version on both copies (the main server and {device}).
            {restoring?.value === null && <strong className="text-fg"> This version is a delete: the row is deleted on both.</strong>}{" "}
            If the row has an open conflict, restoring closes it.
          </>
        }
      />
    </div>
  );
}
