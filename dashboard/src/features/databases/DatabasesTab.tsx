import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, Database, History, Leaf, Plug, Plus, RefreshCw, Trash2 } from "lucide-react";
import { errorMessage, isDeviceOffline } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useCohostEligibility, useDataSourcesWithReplicas } from "../../api/hooks";
import type { CohostEligibility, DataSource } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { relativeTime } from "../../lib/format";
import { RecentlyDeletedCard } from "../backups/RecentlyDeleted";
import { SourceCopies } from "../cohosting/SourceCopies";
import { DeviceBadge } from "../devices/DeviceBits";
import { MoveDatabaseDialog } from "../devices/MoveDatabaseDialog";
import { useDeviceNames } from "../devices/useDeviceNames";
import { useProjectContext } from "../projects/project-context";
import { AddDatabaseDialog } from "./AddDatabaseDialog";
import { EngineBadge, KindBadge, ModeBadge, StatusBadge } from "./SourceBadges";

export function DatabasesTab() {
  const { project, can } = useProjectContext();
  const sources = useDataSourcesWithReplicas(project.id);
  // COHOSTING.md: decides whether "Copy to my device" appears at all; most members never see it.
  const eligibility = useCohostEligibility(project.id);
  const [adding, setAdding] = useState(false);
  const [connectionFor, setConnectionFor] = useState<DataSource | null>(null);
  const [deleting, setDeleting] = useState<DataSource | null>(null);
  const [moving, setMoving] = useState<DataSource | null>(null);
  const anyOnDevice = sources.data?.some((s) => s.device_id) ?? false;
  const deviceName = useDeviceNames(project.id, anyOnDevice);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl text-sm text-muted">
          Attach <strong className="text-sql">SQL</strong> and <strong className="text-nosql">NoSQL</strong> databases
          to this project. A project can use both together — for example MariaDB for relational data and MongoDB for
          flexible documents. Managed databases run on this server or one of your host devices and are backed up
          automatically; external ones (MySQL, PostgreSQL, MongoDB Atlas…) are connected, not copied.
        </div>
        {can("admin") && (
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
            Add database
          </Button>
        )}
      </div>

      {sources.isPending ? (
        <PageSpinner />
      ) : sources.isError ? (
        <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
      ) : sources.data.length === 0 ? (
        <EmptyState
          icon={<Database className="size-5" />}
          title="No databases yet"
          description="Add a managed database on this machine or connect an external one."
          action={
            can("admin") ? (
              <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
                Add database
              </Button>
            ) : undefined
          }
        />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {sources.data.map((s) => (
            <li key={s.id}>
              <SourceCard
                source={s}
                allSources={sources.data}
                eligibility={eligibility.data}
                deviceName={deviceName(s)}
                onConnection={() => setConnectionFor(s)}
                onDelete={() => setDeleting(s)}
                onMove={() => setMoving(s)}
              />
            </li>
          ))}
        </ul>
      )}

      {can("admin") && <RecentlyDeletedCard projectId={project.id} />}

      {moving && <MoveDatabaseDialog projectId={project.id} source={moving} onClose={() => setMoving(null)} />}
      {adding && <AddDatabaseDialog projectId={project.id} onClose={() => setAdding(false)} />}
      {connectionFor && (
        <ConnectionDialog projectId={project.id} source={connectionFor} onClose={() => setConnectionFor(null)} />
      )}
      {deleting && (
        <DeleteSourceDialog
          projectId={project.id}
          source={deleting}
          canDrop={can("owner")}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}

function SourceCard({
  source,
  allSources,
  eligibility,
  deviceName,
  onConnection,
  onDelete,
  onMove,
}: {
  source: DataSource;
  allSources: DataSource[];
  eligibility: CohostEligibility | undefined;
  deviceName: string | null;
  onConnection: () => void;
  onDelete: () => void;
  onMove: () => void;
}) {
  const { project, can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const check = useMutation({
    mutationFn: () => api.dataSources.check(project.id, source.id),
    onSuccess: (updated) => {
      queryClient.setQueryData<DataSource[]>(qk.dataSources(project.id), (list) =>
        list?.map((s) => (s.id === updated.id ? updated : s)),
      );
      if (updated.status === "ok") toast.success(`${updated.name} is reachable.`);
      else toast.error(updated.status_message ?? "The database is not reachable.", updated.name);
    },
    onError: (e) =>
      toast.error(
        isDeviceOffline(e) ? `${deviceName ?? "The host device"} is offline.` : errorMessage(e),
        "Status check failed",
      ),
  });

  const d = source.display;
  const location = d.host ? `${d.host}${d.port ? `:${d.port}` : ""}` : null;
  const Icon = source.kind === "sql" ? Database : Leaf;

  return (
    <article className="flex h-full flex-col rounded-xl border border-border bg-surface p-4 shadow-xs">
      <div className="flex items-start gap-3">
        <span
          className={
            "flex size-9 shrink-0 items-center justify-center rounded-lg " +
            (source.kind === "sql" ? "bg-sql-soft text-sql" : "bg-nosql-soft text-nosql")
          }
        >
          <Icon className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold">{source.name}</h3>
          <p className="truncate font-mono text-xs text-muted">{source.database_name}</p>
        </div>
        <StatusBadge status={source.status} message={source.status_message} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <KindBadge kind={source.kind} />
        <EngineBadge engine={source.engine} />
        <ModeBadge mode={source.mode} />
        {d.tls && <ModeTls />}
        <DeviceBadge name={deviceName} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        {location && (
          <div className="col-span-2 min-w-0">
            <dt className="text-muted">Host</dt>
            <dd className="truncate font-mono">{location}</dd>
          </div>
        )}
        {d.username && (
          <div className="min-w-0">
            <dt className="text-muted">User</dt>
            <dd className="truncate font-mono">{d.username}</dd>
          </div>
        )}
        <div>
          <dt className="text-muted">Last checked</dt>
          <dd>{relativeTime(source.last_checked_at)}</dd>
        </div>
      </dl>
      {source.status === "error" && source.status_message && (
        <Alert tone="danger" className="mt-3 text-xs">
          {source.status_message}
        </Alert>
      )}
      <SourceCopies source={source} allSources={allSources} eligibility={eligibility} />
      <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-3">
        <Button size="sm" icon={<RefreshCw className="size-3.5" />} loading={check.isPending} onClick={() => check.mutate()}>
          Check status
        </Button>
        {can("developer") && (
          <Button size="sm" icon={<Plug className="size-3.5" />} onClick={onConnection}>
            Connection details
          </Button>
        )}
        {source.mode === "managed" && (
          <Link
            to={`/projects/${project.id}/backups?source=${encodeURIComponent(source.id)}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 text-xs font-medium shadow-sm hover:bg-surface-2"
          >
            <History className="size-3.5" /> Backups
          </Link>
        )}
        {can("admin") && source.mode === "managed" && (
          <Button size="sm" icon={<ArrowRightLeft className="size-3.5" />} onClick={onMove}>
            Move
          </Button>
        )}
        {can("admin") && (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto text-danger"
            icon={<Trash2 className="size-3.5" />}
            onClick={onDelete}
          >
            Remove
          </Button>
        )}
      </div>
    </article>
  );
}

function ModeTls() {
  return (
    <span className="inline-flex items-center rounded-md border border-border px-1.5 py-0.5 text-[11px] leading-4 font-semibold text-muted">
      TLS
    </span>
  );
}

function ConnectionDialog({
  projectId,
  source,
  onClose,
}: {
  projectId: string;
  source: DataSource;
  onClose: () => void;
}) {
  const conn = useQuery({
    queryKey: ["projects", projectId, "connection", source.id],
    queryFn: () => api.dataSources.connection(projectId, source.id),
    gcTime: 0,
    staleTime: 0,
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Connection details — ${source.name}`}
      description="Use these in your apps. Treat the password like any other secret."
      size="lg"
      footer={<Button onClick={onClose}>Close</Button>}
    >
      {conn.isPending ? (
        <PageSpinner />
      ) : conn.isError ? (
        <ErrorState error={conn.error} onRetry={() => void conn.refetch()} />
      ) : (
        <div className="space-y-3">
          {source.mode === "managed" && (
            <Alert tone="info">
              These values work from inside the Deployer Docker network (e.g. apps deployed by Deployer).
              {conn.data.external_hint ? ` ${conn.data.external_hint}` : ""}
            </Alert>
          )}
          {source.mode === "external" && conn.data.external_hint && <Alert tone="info">{conn.data.external_hint}</Alert>}
          <CopyField label="Connection URI" value={conn.data.uri} secret />
          <div className="grid gap-3 sm:grid-cols-2">
            <CopyField label="Host" value={conn.data.host} />
            <CopyField label="Port" value={conn.data.port === null ? "" : String(conn.data.port)} />
            <CopyField label="Username" value={conn.data.username} />
            <CopyField label="Password" value={conn.data.password} secret />
            <CopyField label="Database" value={conn.data.database} className="sm:col-span-2" />
          </div>
        </div>
      )}
    </Dialog>
  );
}

function DeleteSourceDialog({
  projectId,
  source,
  canDrop,
  onClose,
}: {
  projectId: string;
  source: DataSource;
  canDrop: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [drop, setDrop] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.dataSources.remove(projectId, source.id, drop),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.dataSources(projectId) });
      void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) });
      void queryClient.invalidateQueries({ queryKey: qk.projects });
      toast.success(drop ? `${source.name} removed and its data dropped.` : `${source.name} removed from the project.`);
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't remove database"),
  });

  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={() => remove.mutate()}
      loading={remove.isPending}
      title={`Remove ${source.name}?`}
      confirmLabel={drop ? "Remove and drop data" : "Remove"}
      confirmText={drop ? source.name : undefined}
      description={
        drop
          ? "The database and all of its data will be dropped. A final version and its recovery logs are kept for 30 days under Recently deleted, then purged."
          : "The database is detached from this project. Its data is kept" +
            (source.mode === "external" ? " on the external server." : " on this machine.")
      }
    >
      {canDrop && source.mode === "managed" && (
        <Checkbox
          checked={drop}
          onChange={(e) => setDrop(e.target.checked)}
          label="Also drop the database and all its data"
          description="Owner only. Export the project first if you might need the data."
        />
      )}
    </ConfirmDialog>
  );
}
