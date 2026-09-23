import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, GitMerge } from "lucide-react";
import { useDataSourcesWithReplicas, useSyncConflicts } from "../../api/hooks";
import type { DataSource, JsonObject, SyncConflict, SyncOp } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { Tabs } from "../../components/ui/Tabs";
import { formatDateTime, relativeTime } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";
import { deviceOf, keyText, RESOLUTION_LABELS } from "./cohosting";
import { ConflictView, HistoryView } from "./ConflictView";
import { useMemberNames } from "./hooks";
import { SourceCopies } from "./SourceCopies";

type Tab = "open" | "resolved";

/**
 * `/projects/:id/databases/:sid/sync`: a source's copies and its sync conflicts. The open conflict, the
 * per-row history and the tab live in the query string so each view can be linked and survives a reload.
 */
export function SyncPage() {
  const { project, can } = useProjectContext();
  const { sourceId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const sources = useDataSourcesWithReplicas(project.id);
  const source = sources.data?.find((s) => s.id === sourceId);
  const back = (
    <Link to={`/projects/${project.id}/databases`} className="inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
      <ArrowLeft className="size-4" /> Databases
    </Link>
  );

  if (!can("developer")) {
    return (
      <div className="space-y-4">
        {back}
        <EmptyState title="Developers only" description="Sync conflicts and history need the Developer role or higher." />
      </div>
    );
  }
  if (sources.isPending) return <PageSpinner />;
  if (sources.isError) return <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />;
  if (!source) {
    return (
      <div className="space-y-4">
        {back}
        <EmptyState title="Database not found" description="It may have been removed from this project." />
      </div>
    );
  }

  const tab: Tab = params.get("tab") === "resolved" ? "resolved" : "open";
  const conflictId = params.get("conflict");
  const historyTable = params.get("table");
  const historyKey = parseKey(params.get("key"));
  const go = (next: Record<string, string>) => setParams(next);

  return (
    <div className="space-y-4">
      {back}
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <GitMerge className="size-5 text-accent" /> Sync · {source.name}
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Copies of this database on co-hosts' PCs. When the same row changes on both sides before they sync, nothing
          is overwritten: the row waits here until someone picks a version, which is then written to both.
        </p>
      </div>
      <div className="rounded-xl border border-border bg-surface p-4 shadow-xs">
        {(source.replicas ?? []).length === 0 ? (
          <p className="text-sm text-muted">This database has no copies right now.</p>
        ) : (
          <SourceCopies source={source} allSources={sources.data} eligibility={undefined} />
        )}
      </div>

      {conflictId ? (
        <ConflictView
          source={source}
          conflictId={conflictId}
          onBack={() => go({ tab })}
          onHistory={(table, key) => go({ tab, table, key: JSON.stringify(key) })}
        />
      ) : historyTable && historyKey ? (
        <HistoryView source={source} table={historyTable} rowKey={historyKey} onBack={() => go({ tab })} />
      ) : (
        <>
          <Tabs<Tab>
            value={tab}
            onChange={(t) => go({ tab: t })}
            items={[
              { value: "open", label: "Open" },
              { value: "resolved", label: "Resolved" },
            ]}
          />
          <ConflictList source={source} status={tab} onOpen={(c) => go({ tab, conflict: c.id })} />
        </>
      )}
    </div>
  );
}

function parseKey(raw: string | null): JsonObject | null {
  if (!raw) return null;
  try {
    const v: unknown = JSON.parse(raw);
    return v && typeof v === "object" && !Array.isArray(v) ? (v as JsonObject) : null;
  } catch {
    return null;
  }
}

function SideChange({ op, at }: { op: SyncOp | null; at: string | null }) {
  if (!op) return <span className="text-muted">—</span>;
  return (
    <span className="whitespace-nowrap" title={formatDateTime(at)}>
      <Badge tone={op === "delete" ? "danger" : op === "insert" ? "success" : "info"}>{op}</Badge>{" "}
      <span className="text-xs text-muted">{relativeTime(at)}</span>
    </span>
  );
}

function ConflictList({ source, status, onOpen }: { source: DataSource; status: Tab; onOpen: (c: SyncConflict) => void }) {
  const { project } = useProjectContext();
  const conflicts = useSyncConflicts(project.id, source.id, status);
  const nameOf = useMemberNames(project.id);
  const multi = (source.replicas ?? []).length > 1;

  if (conflicts.isPending) return <PageSpinner />;
  if (conflicts.isError) return <ErrorState error={conflicts.error} onRetry={() => void conflicts.refetch()} />;
  if (conflicts.data.length === 0) {
    return (
      <EmptyState
        icon={<GitMerge className="size-5" />}
        title={status === "open" ? "No open conflicts" : "No resolved conflicts"}
        description={
          status === "open"
            ? "Every row is syncing. Conflicts show up here when the same row changes on both copies before they sync."
            : "Conflicts you resolve are listed here with who picked which version."
        }
      />
    );
  }
  return (
    <>
      {status === "open" && (
        <Alert tone="warning">
          These rows don't sync until resolved; every other row keeps syncing. Each copy keeps its own version meanwhile.
        </Alert>
      )}
      <Table>
        <THead>
          <Tr>
            <Th>Table / collection</Th>
            <Th>Row</Th>
            {multi && <Th>Copy</Th>}
            {status === "open" ? (
              <>
                <Th>Main server</Th>
                <Th>Co-host</Th>
              </>
            ) : (
              <>
                <Th>Resolution</Th>
                <Th>Resolved</Th>
              </>
            )}
            <Th>
              <span className="sr-only">Open</span>
            </Th>
          </Tr>
        </THead>
        <TBody>
          {conflicts.data.map((c) => (
            <Tr key={c.id} className="cursor-pointer hover:bg-surface-2" onClick={() => onOpen(c)}>
              <Td className="font-mono text-xs">{c.table}</Td>
              <Td className="max-w-56 truncate font-mono text-xs" title={keyText(c.key)}>
                {keyText(c.key)}
              </Td>
              {multi && <Td className="text-xs">{deviceOf(source, c.replica_id)}</Td>}
              {status === "open" ? (
                <>
                  <Td>
                    <SideChange op={c.op_primary} at={c.primary_changed_at} />
                  </Td>
                  <Td>
                    <SideChange op={c.op_replica} at={c.replica_changed_at} />
                  </Td>
                </>
              ) : (
                <>
                  <Td className="text-xs whitespace-nowrap">{RESOLUTION_LABELS[c.resolution ?? ""] ?? "—"}</Td>
                  <Td className="text-xs whitespace-nowrap" title={formatDateTime(c.resolved_at)}>
                    {nameOf(c.resolved_by_id)} · {relativeTime(c.resolved_at)}
                  </Td>
                </>
              )}
              <Td className="text-right">
                <Button size="sm" onClick={() => onOpen(c)}>
                  {status === "open" ? "Resolve" : "View"}
                </Button>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </>
  );
}
