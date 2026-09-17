import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CopyPlus, History, RotateCcw } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import { usePlacementOptions } from "../../api/hooks";
import type { Backup, DataSource, Job, RecoveryWindow, RestoreMode, RestoreRequest } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input, Select } from "../../components/ui/Input";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatDateTime, localTimeZone, relativeTime } from "../../lib/format";
import { deviceIdFromValue, defaultPlacement, engineForKind, placementDisplay, placementValue } from "../devices/eligibility";
import { HostOnSelect } from "../devices/HostOnSelect";
import { JobProgressPanel } from "../jobs/JobProgress";
import { RecoveryTimelineBar } from "./BackupBits";
import {
  baseSnapshotFor,
  inputConstraints,
  pitrBounds,
  timelineBar,
  toDateInput,
  toTimeInput,
  validatePointInTime,
} from "./pitr";
import { TRIGGER_LABELS } from "./timeline";

type Target = "version" | "time";

function defaultNewName(source: DataSource): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${source.name}-restored-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
}

function RadioCard({
  checked,
  onChange,
  disabled,
  title,
  description,
  icon,
  danger,
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  title: string;
  description: ReactNode;
  icon: ReactNode;
  danger?: boolean;
}) {
  return (
    <label
      className={cn(
        "flex items-start gap-3 rounded-xl border p-3 text-sm",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
        checked
          ? danger
            ? "border-danger bg-danger-soft/50 ring-1 ring-danger"
            : "border-accent bg-accent-soft/50 ring-1 ring-accent"
          : "border-border hover:bg-surface-2",
      )}
    >
      <input type="radio" className="sr-only" checked={checked} onChange={onChange} disabled={disabled} />
      <span className={cn("mt-0.5 shrink-0", danger ? "text-danger" : "text-accent")}>{icon}</span>
      <span className="min-w-0">
        <span className="block font-semibold">{title}</span>
        <span className="mt-0.5 block text-xs text-muted">{description}</span>
      </span>
    </label>
  );
}

export function RestoreDialog({
  projectId,
  source,
  backups,
  recovery,
  initialBackupId,
  initialTarget,
  canInPlace,
  onClose,
}: {
  projectId: string;
  source: DataSource;
  backups: Backup[];
  recovery: RecoveryWindow | undefined;
  initialBackupId?: string;
  initialTarget?: Target;
  canInPlace: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const versions = backups.filter((b) => b.status === "succeeded");
  const bounds = pitrBounds(recovery);

  const [target, setTarget] = useState<Target>(initialTarget ?? "version");
  const [backupId, setBackupId] = useState(initialBackupId ?? versions[0]?.id ?? "");
  const [date, setDate] = useState(bounds ? toDateInput(bounds.latest) : "");
  const [time, setTime] = useState(bounds ? toTimeInput(bounds.latest) : "");
  const [mode, setMode] = useState<RestoreMode>("new_source");
  const [newName, setNewName] = useState(() => defaultNewName(source));
  const [confirmName, setConfirmName] = useState("");
  const [job, setJob] = useState<Job | null>(null);

  const placement = usePlacementOptions(projectId, mode === "new_source");
  const engine = engineForKind(source.kind);
  const [hostChoice, setHostChoice] = useState<string | null>(null);
  const hostDisplays = (placement.data ?? []).map((o) => placementDisplay(o, engine));
  const preferred = hostChoice ?? placementValue(source.device_id);
  const host = hostDisplays.some((d) => d.value === preferred && !d.disabled)
    ? preferred
    : defaultPlacement(placement.data ?? [], engine);
  const showHost = (placement.data?.length ?? 0) > 1;

  const pit = target === "time" ? validatePointInTime(date, time, bounds) : null;
  const constraints = bounds ? inputConstraints(bounds, date) : null;
  const bar = timelineBar(bounds, backups);
  const selectedVersion = versions.find((b) => b.id === backupId) ?? null;
  const selectedAt =
    target === "time" ? (pit?.ok ? pit.value.getTime() : null) : selectedVersion ? Date.parse(selectedVersion.started_at) : null;
  const base = pit?.ok ? baseSnapshotFor(pit.value, versions) : null;

  const targetValid = target === "version" ? Boolean(selectedVersion) : Boolean(pit?.ok);
  const modeValid =
    mode === "new_source"
      ? newName.trim().length > 0 && (!showHost || hostDisplays.some((d) => d.value === host && !d.disabled))
      : canInPlace && confirmName.trim() === source.name;
  const valid = targetValid && modeValid;

  const restore = useMutation({
    mutationFn: () => {
      const body: RestoreRequest = { mode };
      if (target === "version") body.backup_id = backupId;
      else if (pit?.ok) body.point_in_time = pit.value.toISOString();
      if (mode === "new_source") {
        body.new_name = newName.trim();
        if (showHost) body.device_id = deviceIdFromValue(host);
      }
      return api.backups.restore(projectId, source.id, body);
    },
    onSuccess: ({ job: j }) => {
      setJob(j);
      void queryClient.invalidateQueries({ queryKey: qk.jobs(projectId) });
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) restore.mutate();
  };

  const newSourceId = (j: Job) => (typeof j.result?.data_source_id === "string" ? j.result.data_source_id : null);

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Restore ${source.name}`}
      description={`Times are shown in ${localTimeZone()}.`}
      dismissible={!restore.isPending}
      footer={
        job ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={restore.isPending}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="restore-form"
              variant={mode === "in_place" ? "danger" : "primary"}
              loading={restore.isPending}
              disabled={!valid}
            >
              {mode === "in_place" ? "Replace current data" : "Restore as new database"}
            </Button>
          </>
        )
      }
    >
      {job ? (
        <JobProgressPanel
          projectId={projectId}
          jobId={job.id}
          title={mode === "in_place" ? `Restoring ${source.name}` : `Restoring into ${newName.trim()}`}
          onFinished={(j) => {
            void queryClient.invalidateQueries({ queryKey: qk.dataSources(projectId) });
            void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
            void queryClient.invalidateQueries({ queryKey: qk.backupsFor(projectId, source.id) });
            if (j.status === "succeeded") toast.success("Restore finished.");
            else if (j.status === "failed") toast.error(j.error ?? "The restore failed.", "Restore failed");
          }}
          result={(j) => {
            const id = mode === "in_place" ? source.id : newSourceId(j);
            return (
              <p className="text-sm">
                {mode === "in_place" ? "The live database now contains the restored data. " : "The restored copy is ready. "}
                <Link
                  to={`/projects/${projectId}/data${id ? `?source=${encodeURIComponent(id)}` : ""}`}
                  className="font-medium text-accent hover:underline"
                  onClick={onClose}
                >
                  Open {mode === "in_place" ? source.name : "the new data source"}
                </Link>
              </p>
            );
          }}
        />
      ) : (
        <form id="restore-form" className="space-y-5" onSubmit={onSubmit}>
          <fieldset className="space-y-3">
            <legend className="mb-2 text-sm font-medium">Restore to</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard
                checked={target === "version"}
                onChange={() => setTarget("version")}
                icon={<History className="size-4" />}
                title="A saved version"
                description={`${versions.length} version${versions.length === 1 ? "" : "s"} available.`}
                disabled={versions.length === 0}
              />
              <RadioCard
                checked={target === "time"}
                onChange={() => setTarget("time")}
                icon={<RotateCcw className="size-4" />}
                title="A point in time"
                description={
                  bounds
                    ? `Any second from ${formatDateTime(bounds.earliest.toISOString())} to ${formatDateTime(bounds.latest.toISOString())}.`
                    : recovery?.pitr_enabled
                      ? "Not enough recovery logs yet."
                      : "Point-in-time recovery is off for this database."
                }
                disabled={!bounds}
              />
            </div>

            {target === "version" ? (
              <Field label="Version">
                {(id) => (
                  <Select id={id} value={backupId} onChange={(e) => setBackupId(e.target.value)}>
                    {versions.map((b) => (
                      <option key={b.id} value={b.id}>
                        {formatDateTime(b.started_at)} · {b.label ?? TRIGGER_LABELS[b.trigger]}
                        {b.pinned ? " · pinned" : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            ) : (
              constraints && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Date">
                    {(id) => (
                      <Input
                        id={id}
                        type="date"
                        value={date}
                        min={constraints.minDate}
                        max={constraints.maxDate}
                        onChange={(e) => setDate(e.target.value)}
                        required
                      />
                    )}
                  </Field>
                  <Field label="Time" hint={localTimeZone()}>
                    {(id) => (
                      <Input
                        id={id}
                        type="time"
                        step={1}
                        value={time}
                        min={constraints.minTime}
                        max={constraints.maxTime}
                        onChange={(e) => setTime(e.target.value)}
                        required
                        aria-invalid={pit !== null && !pit.ok}
                      />
                    )}
                  </Field>
                  <div className="text-xs sm:col-span-2">
                    {pit && !pit.ok ? (
                      <p className="text-danger">{pit.error}</p>
                    ) : pit?.ok ? (
                      <p className="text-muted">
                        Restores the version from {base ? formatDateTime(base.started_at) : "before this point"} and
                        replays changes up to {formatDateTime(pit.value.toISOString())} ({relativeTime(pit.value.toISOString())}).
                      </p>
                    ) : null}
                  </div>
                </div>
              )
            )}
            <RecoveryTimelineBar bar={bar} selected={selectedAt} />
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="mb-2 text-sm font-medium">How</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioCard
                checked={mode === "new_source"}
                onChange={() => setMode("new_source")}
                icon={<CopyPlus className="size-4" />}
                title="Restore as a new database"
                description="Recommended. Nothing existing is touched."
              />
              <RadioCard
                checked={mode === "in_place"}
                onChange={() => setMode("in_place")}
                icon={<RotateCcw className="size-4" />}
                title="Replace current data"
                description={canInPlace ? "Overwrites the live database." : "Project owners only."}
                disabled={!canInPlace}
                danger
              />
            </div>

            {mode === "new_source" ? (
              <div className="space-y-3">
                <Field label="New database name">
                  {(id) => <Input id={id} value={newName} maxLength={100} onChange={(e) => setNewName(e.target.value)} />}
                </Field>
                {showHost && (
                  <HostOnSelect
                    options={placement.data}
                    engine={engine}
                    value={host}
                    onChange={setHostChoice}
                    loading={placement.isPending}
                    error={placement.error}
                  />
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <Alert tone="danger" title="This replaces everything in the live database">
                  Deployer first takes a safety version of the current data (you can restore it later), then replaces
                  the contents. Apps connected to {source.name} are briefly disconnected.
                </Alert>
                <Field label={<>Type <code className="rounded bg-surface-2 px-1 font-mono">{source.name}</code> to confirm</>}>
                  {(id) => (
                    <Input
                      id={id}
                      value={confirmName}
                      onChange={(e) => setConfirmName(e.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  )}
                </Field>
              </div>
            )}
          </fieldset>

          {restore.error && <ErrorAlert error={restore.error} />}
        </form>
      )}
    </Dialog>
  );
}
