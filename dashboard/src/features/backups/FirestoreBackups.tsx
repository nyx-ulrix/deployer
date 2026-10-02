import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CloudUpload, DatabaseBackup, RotateCcw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import { invalidateProjectSources } from "../../api/hooks";
import type { DataSource, FirestoreBackup, FirestoreBackups as Overview } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { Alert, Card, EmptyState, ErrorState } from "../../components/ui/States";
import { PageSpinner } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/toast-context";
import { formatBytes, formatDateTime, formatNumber, relativeTime } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";

type Open =
  | { kind: "export" }
  | { kind: "schedule" }
  | { kind: "unschedule"; id: string; label: string }
  | { kind: "restore"; backup: FirestoreBackup }
  | { kind: "import"; uri: string };

const title = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

/** docs/CLOUD.md "Firestore backups": a Firestore database's scheduled backups, its backups (restored into a new
 * database), and managed exports to Cloud Storage (imported into a new database). Everything that costs money asks
 * for the ticked cost box. */
export function FirestoreBackups({ source }: { source: DataSource }) {
  const { project, can } = useProjectContext();
  const key = ["projects", project.id, "firestore-backups", source.id];
  const data = useQuery({
    queryKey: key,
    queryFn: () => api.cloud.firestoreBackups(project.id, source.id),
    refetchInterval: (q) =>
      q.state.data?.operations.some((o) => !o.done) || q.state.data?.backups.some((b) => b.state === "CREATING") ? 10_000 : false,
  });
  const [open, setOpen] = useState<Open | null>(null);
  const admin = can("admin");

  if (data.isPending) return <PageSpinner />;
  if (data.isError) return <ErrorState error={data.error} onRetry={() => void data.refetch()} />;
  const o = data.data;
  const problem = (k: keyof Overview["problems"]) =>
    o.problems[k] && (
      <Alert tone="warning" title="Google didn't let Deployer read this">
        {o.problems[k]}
      </Alert>
    );

  return (
    <div className="space-y-4">
      <Card
        title={
          <span className="flex items-center gap-2">
            <CalendarClock className="size-4 text-nosql" /> Scheduled backups
          </span>
        }
        description="Google takes these by itself, also while this PC is off, and keeps each one for the days you choose."
        actions={
          admin && (
            <Button size="sm" variant="primary" onClick={() => setOpen({ kind: "schedule" })}>
              Add schedule
            </Button>
          )
        }
      >
        <div className="space-y-3">
          {problem("schedules")}
          {o.schedules.length === 0 ? (
            <p className="text-sm text-muted">No schedule yet: {source.name} is not backed up automatically.</p>
          ) : (
            <ul className="divide-y divide-border rounded-xl border border-border">
              {o.schedules.map((s) => {
                const label = s.recurrence === "weekly" ? `Every ${title(s.day ?? "")}` : "Every day";
                return (
                  <li key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                    <span className="min-w-0 flex-1 font-medium">{label}</span>
                    <span className="text-muted">kept {s.retention_days ?? "?"} days</span>
                    {admin && (
                      <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => setOpen({ kind: "unschedule", id: s.id, label })}>
                        Remove
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>

      <Card
        title={
          <span className="flex items-center gap-2">
            <DatabaseBackup className="size-4 text-nosql" /> Backups
          </span>
        }
        description={o.notes.restore}
      >
        <div className="space-y-3">
          {problem("backups")}
          {o.backups.length === 0 ? (
            <EmptyState title="No backups yet" description="Add a schedule: the first backup appears after its first run." />
          ) : (
            <ul className="divide-y divide-border rounded-xl border border-border">
              {o.backups.map((b) => (
                <li key={b.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1" title={formatDateTime(b.snapshot_time)}>
                    {relativeTime(b.snapshot_time)}
                  </span>
                  <Badge tone={b.state === "READY" ? "success" : "neutral"}>{(b.state ?? "unknown").toLowerCase()}</Badge>
                  <span className="text-xs text-muted tabular-nums">
                    {formatBytes(b.size_bytes)}
                    {b.documents != null && ` · ${formatNumber(b.documents)} documents`}
                  </span>
                  <span className="text-xs text-muted">until {formatDateTime(b.expire_time)}</span>
                  {admin && b.state === "READY" && (
                    <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => setOpen({ kind: "restore", backup: b })}>
                      Restore…
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <Card
        title={
          <span className="flex items-center gap-2">
            <CloudUpload className="size-4 text-nosql" /> Exports to Cloud Storage
          </span>
        }
        description={o.notes.export}
        actions={
          admin && (
            <Button size="sm" variant="primary" onClick={() => setOpen({ kind: "export" })}>
              Export now
            </Button>
          )
        }
      >
        <div className="space-y-3">
          {problem("operations")}
          {o.operations.length === 0 ? (
            <p className="text-sm text-muted">No recent exports or imports (Google lists them for a few days).</p>
          ) : (
            <ul className="divide-y divide-border rounded-xl border border-border">
              {o.operations.map((op) => (
                <li key={op.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                  <Badge tone={op.error ? "danger" : op.done ? "success" : "info"}>
                    {op.kind} · {op.state.toLowerCase()}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate font-mono text-xs" title={op.uri ?? ""}>
                    {op.uri}
                  </span>
                  {op.documents != null && <span className="text-xs text-muted">{formatNumber(op.documents)} documents</span>}
                  <span className="text-xs text-muted" title={formatDateTime(op.started_at)}>
                    {relativeTime(op.started_at)}
                  </span>
                  {op.error && <span className="w-full text-xs text-danger">{op.error}</span>}
                  {admin && op.kind === "export" && op.done && !op.error && op.uri && (
                    <Button size="sm" onClick={() => setOpen({ kind: "import", uri: op.uri ?? "" })}>
                      Import into a new database…
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {open?.kind === "export" && <ExportDialog source={source} overview={o} onClose={() => setOpen(null)} />}
      {open?.kind === "schedule" && <ScheduleDialog source={source} overview={o} onClose={() => setOpen(null)} />}
      {open?.kind === "unschedule" && <UnscheduleDialog source={source} id={open.id} label={open.label} onClose={() => setOpen(null)} />}
      {open?.kind === "restore" && (
        <NewDatabaseDialog source={source} overview={o} restore={open.backup} onClose={() => setOpen(null)} />
      )}
      {open?.kind === "import" && <NewDatabaseDialog source={source} overview={o} importUri={open.uri} onClose={() => setOpen(null)} />}
    </div>
  );
}

/** A dialog for something Google bills: the cost note and the tick that enables the button. */
function CostDialog({
  heading,
  description,
  cost,
  confirm,
  ready = true,
  pending,
  error,
  onConfirm,
  onClose,
  children,
}: {
  heading: string;
  description: string;
  cost: string;
  confirm: string;
  ready?: boolean;
  pending: boolean;
  error: unknown;
  onConfirm: () => void;
  onClose: () => void;
  children?: ReactNode;
}) {
  const [agreed, setAgreed] = useState(false);
  return (
    <Dialog
      open
      onClose={onClose}
      dismissible={!pending}
      title={heading}
      description={description}
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" loading={pending} disabled={!agreed || !ready} onClick={onConfirm}>
            {confirm}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {children}
        <Alert tone="warning" title="Google bills your Firebase project for this">
          {cost}
          <Checkbox
            className="mt-2"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            label="I understand Google charges my Firebase project for this"
          />
        </Alert>
        {Boolean(error) && <Alert tone="danger">{errorMessage(error)}</Alert>}
      </div>
    </Dialog>
  );
}

/** Refreshes the project's databases, which includes this backups list (its key starts with the project's). */
function useRefresh() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  return () => invalidateProjectSources(queryClient, project.id);
}

function ExportDialog({ source, overview, onClose }: { source: DataSource; overview: Overview; onClose: () => void }) {
  const { project } = useProjectContext();
  const toast = useToast();
  const refresh = useRefresh();
  const [makeBucket, setMakeBucket] = useState(!overview.bucket);
  const [bucket, setBucket] = useState(overview.bucket ?? "");
  const [collections, setCollections] = useState("");
  const run = useMutation({
    mutationFn: () =>
      api.cloud.firestoreManagedExport(project.id, source.id, {
        ...(makeBucket ? { create_bucket: true } : { bucket: bucket.trim() }),
        collections: collections.split(",").map((c) => c.trim()).filter(Boolean),
        confirm_billing: true,
      }),
    onSuccess: (out) => {
      refresh();
      toast.success(`Google is exporting ${source.name} to ${out.output_uri}.`);
      onClose();
    },
  });
  return (
    <CostDialog
      heading="Export to Cloud Storage"
      description={overview.notes.export}
      cost={overview.costs.export}
      confirm="Export"
      ready={makeBucket || Boolean(bucket.trim())}
      pending={run.isPending}
      error={run.error}
      onConfirm={() => run.mutate()}
      onClose={onClose}
    >
      <Checkbox
        checked={makeBucket}
        onChange={(e) => setMakeBucket(e.target.checked)}
        label={`Let Deployer make a private bucket for exports (${overview.default_bucket})`}
        description="Or untick and name a bucket you made in the Google Cloud console (Cloud Storage), in the database's location."
      />
      {!makeBucket && (
        <Field label="Bucket">
          {(id) => <Input id={id} value={bucket} onChange={(e) => setBucket(e.target.value)} placeholder="my-firestore-exports" spellCheck={false} />}
        </Field>
      )}
      <Field label="Collections" optional hint="Collection names separated by commas; empty exports everything.">
        {(id) => <Input id={id} value={collections} onChange={(e) => setCollections(e.target.value)} placeholder="users, orders" spellCheck={false} />}
      </Field>
    </CostDialog>
  );
}

function ScheduleDialog({ source, overview, onClose }: { source: DataSource; overview: Overview; onClose: () => void }) {
  const { project } = useProjectContext();
  const toast = useToast();
  const refresh = useRefresh();
  const [recurrence, setRecurrence] = useState<"daily" | "weekly">(overview.schedules.some((s) => s.recurrence === "daily") ? "weekly" : "daily");
  const [day, setDay] = useState(overview.days[6] ?? "SUNDAY");
  const longest = overview.max_retention_days[recurrence];
  const [days, setDays] = useState(7);
  const retention = Math.min(Math.max(1, days || 1), longest);
  const run = useMutation({
    mutationFn: () =>
      api.cloud.firestoreSchedule(project.id, source.id, {
        recurrence,
        ...(recurrence === "weekly" ? { day } : {}),
        retention_days: retention,
        confirm_billing: true,
      }),
    onSuccess: () => {
      refresh();
      toast.success(`${source.name} is now backed up ${recurrence === "daily" ? "every day" : `every ${title(day)}`}.`);
      onClose();
    },
  });
  return (
    <CostDialog
      heading="Add a backup schedule"
      description="One daily and one weekly schedule at most. Google keeps each backup for the days you choose, then deletes it."
      cost={overview.costs.schedule}
      confirm="Add schedule"
      pending={run.isPending}
      error={run.error}
      onConfirm={() => run.mutate()}
      onClose={onClose}
    >
      <Field label="How often">
        {(id) => (
          <Select id={id} value={recurrence} onChange={(e) => setRecurrence(e.target.value as "daily" | "weekly")}>
            <option value="daily">Every day</option>
            <option value="weekly">Every week</option>
          </Select>
        )}
      </Field>
      {recurrence === "weekly" && (
        <Field label="Day">
          {(id) => (
            <Select id={id} value={day} onChange={(e) => setDay(e.target.value)}>
              {overview.days.map((d) => (
                <option key={d} value={d}>
                  {title(d)}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      <Field label="Keep each backup for (days)" hint={`1 to ${longest} days.`}>
        {(id) => <Input id={id} type="number" min={1} max={longest} value={days} onChange={(e) => setDays(Number(e.target.value))} />}
      </Field>
    </CostDialog>
  );
}

function UnscheduleDialog({ source, id, label, onClose }: { source: DataSource; id: string; label: string; onClose: () => void }) {
  const { project } = useProjectContext();
  const toast = useToast();
  const refresh = useRefresh();
  const run = useMutation({
    mutationFn: () => api.cloud.firestoreDeleteSchedule(project.id, source.id, id),
    onSuccess: () => {
      refresh();
      toast.success("Schedule removed.");
      onClose();
    },
  });
  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title="Remove this schedule?"
      description={`${label}: no new backups are taken. The backups already taken stay until they expire.`}
      footer={
        <>
          <Button onClick={onClose} disabled={run.isPending}>
            Cancel
          </Button>
          <Button variant="danger" loading={run.isPending} onClick={() => run.mutate()}>
            Remove
          </Button>
        </>
      }
    >
      {run.error && <Alert tone="danger">{errorMessage(run.error)}</Alert>}
    </Dialog>
  );
}

/** Restore a backup, or import an export, into a NEW database that is added as a new data source. */
function NewDatabaseDialog({
  source,
  overview,
  restore,
  importUri,
  onClose,
}: {
  source: DataSource;
  overview: Overview;
  restore?: FirestoreBackup;
  importUri?: string;
  onClose: () => void;
}) {
  const { project } = useProjectContext();
  const toast = useToast();
  const refresh = useRefresh();
  const [name, setName] = useState(`${source.name} ${restore ? "restored" : "copy"}`.slice(0, 63));
  const [database, setDatabase] = useState("");
  const run = useMutation({
    mutationFn: () => {
      const body = { name: name.trim(), database: database.trim() || undefined, confirm_billing: true };
      return restore
        ? api.cloud.firestoreRestore(project.id, source.id, { ...body, backup: restore.name })
        : api.cloud.firestoreImport(project.id, source.id, { ...body, input_uri: importUri ?? "" });
    },
    onSuccess: (out) => {
      refresh();
      toast.success(`${out.data_source.name} is being made in your Firebase project. It appears under Databases.`);
      onClose();
    },
  });
  return (
    <CostDialog
      heading={restore ? "Restore into a new database" : "Import into a new database"}
      description={
        restore
          ? `The backup from ${formatDateTime(restore.snapshot_time)} becomes a new Firestore database; ${source.name} is not touched.`
          : `The export in ${importUri} is loaded into a new Firestore database; ${source.name} is not touched.`
      }
      cost={restore ? overview.costs.restore : overview.costs.import}
      confirm={restore ? "Restore" : "Import"}
      ready={Boolean(name.trim())}
      pending={run.isPending}
      error={run.error}
      onConfirm={() => run.mutate()}
      onClose={onClose}
    >
      <Field label="Name in Deployer">{(id) => <Input id={id} value={name} maxLength={63} onChange={(e) => setName(e.target.value)} />}</Field>
      <Field label="Database id" optional hint="Lowercase letters, digits and hyphens. Empty: Deployer picks one (deployer-…).">
        {(id) => <Input id={id} value={database} onChange={(e) => setDatabase(e.target.value)} spellCheck={false} autoCapitalize="off" />}
      </Field>
    </CostDialog>
  );
}
