import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Trash2 } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import type { DeletedSource, Job } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { Card, ErrorAlert, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatDate, formatDateTime, relativeTime } from "../../lib/format";
import { JobProgressPanel } from "../jobs/JobProgress";
import { EngineBadge, KindBadge } from "../databases/SourceBadges";

/** "Recently deleted" databases (kept 30 days with their final version). Admin+. */
export function RecentlyDeletedCard({ projectId }: { projectId: string }) {
  const deleted = useQuery({
    queryKey: qk.deletedSources(projectId),
    queryFn: () => api.dataSources.deleted(projectId),
    retry: false,
  });
  const [restoring, setRestoring] = useState<DeletedSource | null>(null);

  if (deleted.isPending) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <Spinner className="size-4" /> Checking recently deleted databases…
      </div>
    );
  }
  if (deleted.isError) {
    return <ErrorState title="Couldn't load recently deleted databases" error={deleted.error} onRetry={() => void deleted.refetch()} />;
  }
  if (deleted.data.length === 0) return null;

  return (
    <Card
      title={
        <span className="inline-flex items-center gap-2">
          <Trash2 className="size-4 text-muted" /> Recently deleted
        </span>
      }
      description="Deleted managed databases keep their final version and recovery logs for 30 days."
      bodyClassName="p-0 sm:p-0"
    >
      <ul className="divide-y divide-border">
        {deleted.data.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="truncate font-medium">{s.name}</span>
                <KindBadge kind={s.kind} />
                <EngineBadge engine={s.engine} />
              </div>
              <p className="mt-0.5 text-xs text-muted">
                Deleted <span title={formatDateTime(s.deleted_at)}>{relativeTime(s.deleted_at)}</span> · purged on{" "}
                <span title={formatDateTime(s.purge_at)}>{formatDate(s.purge_at)}</span> ({relativeTime(s.purge_at)})
              </p>
            </div>
            <Button size="sm" icon={<ArchiveRestore className="size-3.5" />} onClick={() => setRestoring(s)}>
              Restore
            </Button>
          </li>
        ))}
      </ul>
      {restoring && <RestoreDeletedDialog projectId={projectId} source={restoring} onClose={() => setRestoring(null)} />}
    </Card>
  );
}

function RestoreDeletedDialog({
  projectId,
  source,
  onClose,
}: {
  projectId: string;
  source: DeletedSource;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState(source.name);
  const [job, setJob] = useState<Job | null>(null);
  const restore = useMutation({
    mutationFn: () => api.dataSources.restoreDeleted(projectId, source.id, name.trim() || undefined),
    onSuccess: (res) => setJob(res.job),
  });
  const newId = (j: Job) => (typeof j.result?.data_source_id === "string" ? j.result.data_source_id : null);

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Restore ${source.name}`}
      description="Brings the database back from its final version."
      dismissible={!restore.isPending}
      footer={
        job ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={restore.isPending}>
              Cancel
            </Button>
            <Button variant="primary" loading={restore.isPending} onClick={() => restore.mutate()}>
              Restore database
            </Button>
          </>
        )
      }
    >
      {job ? (
        <JobProgressPanel
          projectId={projectId}
          jobId={job.id}
          title="Restoring database"
          onFinished={(j) => {
            void queryClient.invalidateQueries({ queryKey: qk.dataSources(projectId) });
            void queryClient.invalidateQueries({ queryKey: qk.deletedSources(projectId) });
            void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
            if (j.status === "succeeded") toast.success(`${source.name} restored.`);
          }}
          result={(j) => (
            <p className="text-sm">
              Restored.{" "}
              <Link
                className="font-medium text-accent hover:underline"
                to={`/projects/${projectId}/data${newId(j) ? `?source=${encodeURIComponent(newId(j) ?? "")}` : ""}`}
                onClick={onClose}
              >
                Open the data
              </Link>
            </p>
          )}
        />
      ) : (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            restore.mutate();
          }}
        >
          <Field label="Name" hint="The restored database is added back to this project under this name.">
            {(id) => <Input id={id} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />}
          </Field>
          {restore.error && <ErrorAlert error={restore.error} />}
        </form>
      )}
    </Dialog>
  );
}
