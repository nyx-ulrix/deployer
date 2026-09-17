import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Cloud, Database, History, Leaf, RotateCcw, Settings2 } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import { useDataSources, useDevices } from "../../api/hooks";
import type { Backup, DataSource, Job } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner, Spinner } from "../../components/ui/Spinner";
import { Alert, Card, EmptyState, ErrorAlert, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { engineLabel, formatDateTime, localTimeZone, relativeTime } from "../../lib/format";
import { DeviceBadge } from "../devices/DeviceBits";
import { useDeviceNames } from "../devices/useDeviceNames";
import { JobProgressPanel } from "../jobs/JobProgress";
import { useProjectContext } from "../projects/project-context";
import { RecoveryTimelineBar } from "./BackupBits";
import { CompareDialog } from "./CompareDialog";
import { pitrBounds, timelineBar } from "./pitr";
import { PolicyDialog } from "./PolicyDialog";
import { RestoreDialog } from "./RestoreDialog";
import { copiesSummary, lastSuccessful, nextScheduledAt, SCHEDULE_LABELS } from "./timeline";
import { VersionsTimeline } from "./VersionsTimeline";

export function BackupsTab() {
  const { project } = useProjectContext();
  const sources = useDataSources(project.id);
  const [params, setParams] = useSearchParams();

  if (sources.isPending) return <PageSpinner />;
  if (sources.isError) return <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />;
  if (sources.data.length === 0) {
    return (
      <EmptyState
        icon={<History className="size-5" />}
        title="No databases yet"
        description="Add a managed database on the Databases tab. It's backed up automatically."
      />
    );
  }

  const requested = params.get("source");
  const managed = sources.data.filter((s) => s.mode === "managed");
  const source = sources.data.find((s) => s.id === requested) ?? managed[0] ?? sources.data[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Select
          aria-label="Database"
          className="sm:max-w-sm"
          value={source.id}
          onChange={(e) => setParams({ source: e.target.value }, { replace: true })}
        >
          {sources.data.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({engineLabel(s.engine)}
              {s.mode === "external" ? " · external" : ""})
            </option>
          ))}
        </Select>
        <p className="text-xs text-muted">Times are shown in {localTimeZone()}.</p>
      </div>
      {source.mode === "external" ? (
        <EmptyState
          icon={<Cloud className="size-5" />}
          title="Backups for external databases are up to their provider"
          description={`${source.name} is hosted elsewhere (${engineLabel(source.engine)}), so Deployer doesn't back it up. Use your provider's backups — for example MongoDB Atlas snapshots or your host's database backups.`}
        />
      ) : (
        <SourceBackups key={source.id} source={source} />
      )}
    </div>
  );
}

function SourceBackups({ source }: { source: DataSource }) {
  const { project, can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const deviceName = useDeviceNames(project.id, Boolean(source.device_id));
  const devices = useDevices("mine");

  const backups = useQuery({
    queryKey: qk.backups(project.id, source.id),
    queryFn: () => api.backups.list(project.id, source.id),
    refetchInterval: (q) => (q.state.data?.some((b) => b.status === "running") ? 3000 : 60_000),
  });
  const policy = useQuery({
    queryKey: qk.backupPolicy(project.id, source.id),
    queryFn: () => api.backups.policy(project.id, source.id),
  });
  const recovery = useQuery({
    queryKey: qk.recoveryWindow(project.id, source.id),
    queryFn: () => api.backups.recoveryWindow(project.id, source.id),
    refetchInterval: 60_000,
  });

  const [creating, setCreating] = useState(false);
  const [creatingJob, setCreatingJob] = useState<Job | null>(null);
  const [restore, setRestore] = useState<{ backupId?: string } | null>(null);
  const [comparing, setComparing] = useState<Backup | null>(null);
  const [editingPolicy, setEditingPolicy] = useState(false);

  const copyDeviceName = (id: string | null) =>
    id ? (devices.data?.find((d) => d.id === id)?.name ?? "another device") : "main server";

  const list = backups.data ?? [];
  const latest = lastSuccessful(list);
  const bounds = pitrBounds(recovery.data);
  const bar = timelineBar(bounds, list);
  const next = policy.data ? nextScheduledAt(policy.data, list) : null;
  const copies = copiesSummary(latest);

  return (
    <div className="space-y-4">
      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            {source.kind === "sql" ? <Database className="size-4 text-sql" /> : <Leaf className="size-4 text-nosql" />}
            {source.name}
            <DeviceBadge name={deviceName(source)} />
          </span>
        }
        description="Recovery status"
        actions={
          <>
            {can("developer") && (
              <Button variant="primary" size="sm" icon={<Camera className="size-3.5" />} onClick={() => setCreating(true)}>
                Create version now
              </Button>
            )}
            {can("admin") && (
              <Button
                size="sm"
                icon={<RotateCcw className="size-3.5" />}
                onClick={() => setRestore({})}
                disabled={!latest && !bounds}
                title={!latest && !bounds ? "There's nothing to restore yet" : undefined}
              >
                Restore…
              </Button>
            )}
            <Button
              size="sm"
              icon={<Settings2 className="size-3.5" />}
              onClick={() => setEditingPolicy(true)}
              disabled={!policy.data}
            >
              Policy
            </Button>
          </>
        }
      >
        {policy.isError ? (
          <ErrorAlert error={policy.error} />
        ) : (
          <div className="space-y-4">
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Point-in-time recovery">
                {recovery.isPending ? (
                  <Spinner className="size-4" />
                ) : recovery.isError ? (
                  <span className="text-danger">Unavailable</span>
                ) : (
                  <>
                    <Badge tone={bounds ? "success" : recovery.data.pitr_enabled ? "warning" : "neutral"}>
                      {bounds ? "On" : recovery.data.pitr_enabled ? "Starting" : "Off"}
                    </Badge>
                    {bounds ? (
                      <p className="mt-1 text-xs text-muted">
                        Any second from{" "}
                        <span className="text-fg" title={relativeTime(bounds.earliest.toISOString())}>
                          {formatDateTime(bounds.earliest.toISOString())}
                        </span>{" "}
                        to{" "}
                        <span className="text-fg" title={relativeTime(bounds.latest.toISOString())}>
                          {formatDateTime(bounds.latest.toISOString())}
                        </span>
                      </p>
                    ) : (
                      recovery.data.pitr_enabled && (
                        <p className="mt-1 text-xs text-muted">Waiting for the first version and log archive.</p>
                      )
                    )}
                  </>
                )}
              </Stat>
              <Stat label="Last successful version">
                {latest ? (
                  <>
                    <span className="font-medium">{relativeTime(latest.started_at)}</span>
                    <p className="text-xs text-muted">{formatDateTime(latest.started_at)}</p>
                  </>
                ) : backups.isPending ? (
                  <Spinner className="size-4" />
                ) : (
                  <span className="text-warning">None yet</span>
                )}
              </Stat>
              <Stat label="Next scheduled">
                {policy.isPending ? (
                  <Spinner className="size-4" />
                ) : !policy.data?.enabled ? (
                  <Badge tone="warning">Automatic versions off</Badge>
                ) : next ? (
                  <>
                    <span className="font-medium">{relativeTime(next.toISOString())}</span>
                    <p className="text-xs text-muted">{SCHEDULE_LABELS[policy.data.schedule]} (estimated)</p>
                  </>
                ) : null}
              </Stat>
              <Stat label="Copies">
                <Badge tone={copies.tone}>{copies.text}</Badge>
                {policy.data && (
                  <p className="mt-1 text-xs text-muted">
                    Target:{" "}
                    {policy.data.copy_to_primary
                      ? "main server"
                      : policy.data.copy_to_device_id
                        ? copyDeviceName(policy.data.copy_to_device_id)
                        : "none"}
                  </p>
                )}
              </Stat>
            </dl>
            <RecoveryTimelineBar bar={bar} />
          </div>
        )}
      </Card>

      {creatingJob && (
        <JobProgressPanel
          projectId={project.id}
          jobId={creatingJob.id}
          title="Creating version"
          onFinished={(job) => {
            void queryClient.invalidateQueries({ queryKey: qk.backupsFor(project.id, source.id) });
            if (job.status === "succeeded") toast.success("Version created.");
            else if (job.status === "failed") toast.error(job.error ?? "Couldn't create the version.", "Version failed");
          }}
          result={() => (
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-fg/80">The new version is at the top of the timeline.</p>
              <Button size="sm" variant="ghost" onClick={() => setCreatingJob(null)}>
                Dismiss
              </Button>
            </div>
          )}
        />
      )}

      <section className="space-y-3">
        <h2 className="font-semibold">Versions</h2>
        {backups.isPending ? (
          <PageSpinner label="Loading versions…" />
        ) : backups.isError ? (
          <ErrorState error={backups.error} onRetry={() => void backups.refetch()} />
        ) : list.length === 0 ? (
          <EmptyState
            icon={<History className="size-5" />}
            title="No versions yet"
            description={
              policy.data?.enabled
                ? "The first scheduled version will appear here soon."
                : "Automatic versions are off. Create one now or turn them on in Policy."
            }
            action={
              can("developer") ? (
                <Button variant="primary" icon={<Camera className="size-4" />} onClick={() => setCreating(true)}>
                  Create version now
                </Button>
              ) : undefined
            }
          />
        ) : (
          <VersionsTimeline
            projectId={project.id}
            source={source}
            backups={list}
            policy={policy.data}
            can={{ developer: can("developer"), admin: can("admin"), owner: can("owner") }}
            deviceName={(id) => (id ? copyDeviceName(id) : null)}
            actions={{
              onCompare: (b) => setComparing(b),
              onRestore: (b) => setRestore({ backupId: b.id }),
            }}
          />
        )}
      </section>

      {creating && (
        <CreateVersionDialog
          projectId={project.id}
          source={source}
          onClose={() => setCreating(false)}
          onStarted={(job) => {
            setCreating(false);
            setCreatingJob(job);
            void queryClient.invalidateQueries({ queryKey: qk.backups(project.id, source.id) });
          }}
        />
      )}
      {restore && (
        <RestoreDialog
          projectId={project.id}
          source={source}
          backups={list}
          recovery={recovery.data}
          initialBackupId={restore.backupId}
          initialTarget={!restore.backupId && !latest && bounds ? "time" : "version"}
          canInPlace={can("owner")}
          onClose={() => setRestore(null)}
        />
      )}
      {comparing && (
        <CompareDialog
          projectId={project.id}
          source={source}
          backups={list}
          initialFrom={comparing.id}
          onClose={() => setComparing(null)}
        />
      )}
      {editingPolicy && policy.data && (
        <PolicyDialog
          projectId={project.id}
          source={source}
          policy={policy.data}
          canEdit={can("admin")}
          onClose={() => setEditingPolicy(false)}
        />
      )}
    </div>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={cn("min-w-0 rounded-xl bg-surface-2/60 p-3")}>
      <dt className="mb-1 text-xs text-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function CreateVersionDialog({
  projectId,
  source,
  onClose,
  onStarted,
}: {
  projectId: string;
  source: DataSource;
  onClose: () => void;
  onStarted: (job: Job) => void;
}) {
  const [label, setLabel] = useState("");
  const create = useMutation({
    mutationFn: () => api.backups.create(projectId, source.id, label.trim() || undefined),
    onSuccess: ({ job }) => onStarted(job),
  });
  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title="Create version now"
      description={`A full snapshot of ${source.name}.`}
      dismissible={!create.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="create-version" variant="primary" loading={create.isPending}>
            Create version
          </Button>
        </>
      }
    >
      <form
        id="create-version"
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Label" optional hint="Labelled versions are easier to find. Pin them from the timeline to keep them forever.">
          {(id) => (
            <Input
              id={id}
              value={label}
              maxLength={120}
              placeholder="Before v2 migration"
              onChange={(e) => setLabel(e.target.value)}
            />
          )}
        </Field>
        {create.error && <ErrorAlert error={create.error} />}
        <Alert tone="info">Your apps keep working while the version is taken.</Alert>
      </form>
    </Dialog>
  );
}
