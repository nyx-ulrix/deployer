import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CloudUpload, DatabaseBackup, History, RotateCcw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import { invalidateProjectSources } from "../../api/hooks";
import type { DataSource, FirestoreBackup, FirestoreBackups as Overview } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { Alert, Card, EmptyState, ErrorState } from "../../components/ui/States";
import { PageSpinner } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/toast-context";
import { formatBytes, formatDateTime, formatNumber, relativeTime } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";
import { toDateInput, toTimeInput } from "./pitr";

type Open =
  | { kind: "export" }
  | { kind: "schedule" }
  | { kind: "unschedule"; id: string; label: string }
  | { kind: "restore"; backup: FirestoreBackup }
  | { kind: "import"; uri: string }
  | { kind: "pitr"; enable: boolean }
  | { kind: "clone" }
  | { kind: "delete"; what: Deletable; target: string; label: string };

type Deletable = "database" | "backup" | "export";

const title = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

/** docs/CLOUD.md "Firestore backups": a Firestore database's point-in-time recovery (copied to a time into a new
 * database), scheduled backups, its backups (restored into a new database), managed exports to Cloud Storage
 * (imported into a new database) and deleting the database, a backup or an export ("Firestore point-in-time
 * recovery and deletes"). Everything that costs money asks for the ticked cost box; deletes for the typed name. */
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

  const del = (what: Deletable, target: string, label: string) => setOpen({ kind: "delete", what, target, label });
  const pitr = o.status?.pitr ?? false;

  return (
    <div className="space-y-4">
      <Card
        title={
          <span className="flex items-center gap-2">
            <History className="size-4 text-nosql" /> Point-in-time recovery
          </span>
        }
        description={o.notes.pitr}
        actions={
          admin &&
          o.status && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => setOpen({ kind: "pitr", enable: !pitr })}>
                {pitr ? "Turn off…" : "Turn on…"}
              </Button>
              <Button size="sm" variant="primary" icon={<RotateCcw className="size-3.5" />} onClick={() => setOpen({ kind: "clone" })}>
                Restore to a time…
              </Button>
            </div>
          )
        }
      >
        {problem("status")}
        {o.status && (
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone={pitr ? "success" : "neutral"}>{pitr ? "on" : "off"}</Badge>
            <span className="text-muted">
              {pitr ? "Google keeps 7 days of versions." : "Google keeps the last hour only."}
              {o.status.earliest_version_time && ` Restorable from ${formatDateTime(o.status.earliest_version_time)}.`}
            </span>
          </p>
        )}
      </Card>

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
                  {admin && (
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<Trash2 className="size-3.5" />}
                      onClick={() => del("backup", b.name, `the backup from ${formatDateTime(b.snapshot_time)}`)}
                    >
                      Delete…
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
          {problem("exports")}
          {o.exports.length > 0 && (
            <>
              <p className="text-sm font-medium">Stored exports in {o.bucket}</p>
              <ul className="divide-y divide-border rounded-xl border border-border">
                {o.exports.map((x) => (
                  <li key={x.uri} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                    <span className="min-w-0 flex-1 truncate font-mono text-xs" title={x.uri}>
                      {x.uri}
                    </span>
                    <span className="text-xs text-muted" title={formatDateTime(x.created_at)}>
                      {relativeTime(x.created_at)}
                    </span>
                    {admin && (
                      <>
                        <Button size="sm" onClick={() => setOpen({ kind: "import", uri: x.uri })}>
                          Import…
                        </Button>
                        <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => del("export", x.uri, `the export in ${x.uri}`)}>
                          Delete…
                        </Button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </Card>

      {admin && (
        <Card
          title={
            <span className="flex items-center gap-2">
              <Trash2 className="size-4 text-danger" /> Delete this database
            </span>
          }
          description={`Deletes the Firestore database ${o.database} in your Firebase project with every document in it, then removes ${source.name} here. Google has no undo; backups already taken stay until they expire. (Removing it on the Databases tab only forgets it.)`}
          actions={
            <Button
              size="sm"
              variant="danger"
              disabled={!o.status || o.status.delete_protection}
              onClick={() => del("database", o.database, `the Firestore database ${o.database}`)}
            >
              Delete database…
            </Button>
          }
        >
          {o.status?.delete_protection && (
            <Alert tone="info">
              Google's delete protection is on for this database. Turn it off in the Google Cloud console (Firestore → the database →
              Delete protection) to delete it here.
            </Alert>
          )}
        </Card>
      )}

      {open?.kind === "export" && <ExportDialog source={source} overview={o} onClose={() => setOpen(null)} />}
      {open?.kind === "schedule" && <ScheduleDialog source={source} overview={o} onClose={() => setOpen(null)} />}
      {open?.kind === "unschedule" && <UnscheduleDialog source={source} id={open.id} label={open.label} onClose={() => setOpen(null)} />}
      {open?.kind === "restore" && (
        <NewDatabaseDialog source={source} overview={o} restore={open.backup} onClose={() => setOpen(null)} />
      )}
      {open?.kind === "import" && <NewDatabaseDialog source={source} overview={o} importUri={open.uri} onClose={() => setOpen(null)} />}
      {open?.kind === "pitr" && <PitrDialog source={source} overview={o} enable={open.enable} onClose={() => setOpen(null)} />}
      {open?.kind === "clone" && <NewDatabaseDialog source={source} overview={o} toTime onClose={() => setOpen(null)} />}
      {open?.kind === "delete" && (
        <DeleteDialog source={source} what={open.what} target={open.target} label={open.label} onClose={() => setOpen(null)} />
      )}
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
  toTime,
  onClose,
}: {
  source: DataSource;
  overview: Overview;
  restore?: FirestoreBackup;
  importUri?: string;
  /** Point-in-time recovery: the database as it was at a minute of its version window. */
  toTime?: boolean;
  onClose: () => void;
}) {
  const { project } = useProjectContext();
  const toast = useToast();
  const refresh = useRefresh();
  const [name, setName] = useState(`${source.name} ${restore || toTime ? "restored" : "copy"}`.slice(0, 63));
  const [database, setDatabase] = useState("");
  const [when, setWhen] = useState(() => localMinute(new Date(Date.now() - 10 * 60_000)));
  const at = new Date(when);
  const earliest = overview.status?.earliest_version_time;
  const run = useMutation({
    mutationFn: () => {
      const body = { name: name.trim(), database: database.trim() || undefined, confirm_billing: true };
      if (toTime) return api.cloud.firestoreClone(project.id, source.id, { ...body, point_in_time: at.toISOString() });
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
      heading={toTime ? "Restore to a time" : restore ? "Restore into a new database" : "Import into a new database"}
      description={
        toTime
          ? `${source.name} as it was at the minute you pick becomes a new Firestore database; ${source.name} is not touched.`
          : restore
            ? `The backup from ${formatDateTime(restore.snapshot_time)} becomes a new Firestore database; ${source.name} is not touched.`
            : `The export in ${importUri} is loaded into a new Firestore database; ${source.name} is not touched.`
      }
      cost={toTime ? overview.costs.clone : restore ? overview.costs.restore : overview.costs.import}
      confirm={restore || toTime ? "Restore" : "Import"}
      ready={Boolean(name.trim()) && (!toTime || !Number.isNaN(at.getTime()))}
      pending={run.isPending}
      error={run.error}
      onConfirm={() => run.mutate()}
      onClose={onClose}
    >
      {toTime && (
        <Field label="As it was at" hint={earliest ? `Any minute from ${formatDateTime(earliest)} until a minute ago (your time zone).` : undefined}>
          {(id) => (
            <Input
              id={id}
              type="datetime-local"
              step={60}
              min={earliest ? localMinute(new Date(earliest)) : undefined}
              max={localMinute(new Date())}
              value={when}
              onChange={(e) => setWhen(e.target.value)}
            />
          )}
        </Field>
      )}
      <Field label="Name in Deployer">{(id) => <Input id={id} value={name} maxLength={63} onChange={(e) => setName(e.target.value)} />}</Field>
      <Field label="Database id" optional hint="Lowercase letters, digits and hyphens. Empty: Deployer picks one (deployer-…).">
        {(id) => <Input id={id} value={database} onChange={(e) => setDatabase(e.target.value)} spellCheck={false} autoCapitalize="off" />}
      </Field>
    </CostDialog>
  );
}

/** Local "YYYY-MM-DDTHH:MM" for a datetime-local input (Google restores whole minutes). */
function localMinute(d: Date): string {
  return `${toDateInput(d)}T${toTimeInput(d).slice(0, 5)}`;
}

function PitrDialog({ source, overview, enable, onClose }: { source: DataSource; overview: Overview; enable: boolean; onClose: () => void }) {
  const { project } = useProjectContext();
  const toast = useToast();
  const refresh = useRefresh();
  const run = useMutation({
    mutationFn: () => api.cloud.firestoreSetPitr(project.id, source.id, { enabled: enable, confirm_billing: enable }),
    onSuccess: () => {
      refresh();
      toast.success(`Google is turning point-in-time recovery ${enable ? "on" : "off"} for ${source.name}.`);
      onClose();
    },
  });
  if (enable)
    return (
      <CostDialog
        heading="Turn on point-in-time recovery"
        description={overview.notes.pitr}
        cost={overview.costs.pitr}
        confirm="Turn on"
        pending={run.isPending}
        error={run.error}
        onConfirm={() => run.mutate()}
        onClose={onClose}
      />
    );
  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={() => run.mutate()}
      loading={run.isPending}
      title="Turn off point-in-time recovery?"
      description={`Google drops the versions of ${source.name} older than an hour: you can no longer restore it to a time before that.`}
      confirmLabel="Turn off"
    >
      {Boolean(run.error) && <Alert tone="danger">{errorMessage(run.error)}</Alert>}
    </ConfirmDialog>
  );
}

/** Deletes in Google need the database's name typed, like deleting a database (the API's confirm_name). */
function DeleteDialog({
  source,
  what,
  target,
  label,
  onClose,
}: {
  source: DataSource;
  what: Deletable;
  target: string;
  label: string;
  onClose: () => void;
}) {
  const { project } = useProjectContext();
  const toast = useToast();
  const refresh = useRefresh();
  const run = useMutation({
    mutationFn: () =>
      what === "database"
        ? api.cloud.firestoreDeleteDatabase(project.id, source.id, source.name)
        : what === "backup"
          ? api.cloud.firestoreDeleteBackup(project.id, source.id, target, source.name)
          : api.cloud.firestoreDeleteExport(project.id, source.id, target, source.name),
    onSuccess: () => {
      refresh();
      toast.success(what === "database" ? `${source.name} was deleted in your Firebase project.` : `Deleted ${label}.`);
      onClose();
    },
  });
  const keeps =
    what === "database"
      ? `Every document goes, and ${source.name} is removed here. Backups already taken stay until they expire; exports stay in Cloud Storage.`
      : what === "backup"
        ? "The database and its other backups are not touched."
        : "The database is not touched, nor databases already imported from this export.";
  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={() => run.mutate()}
      loading={run.isPending}
      title={`Delete ${label}?`}
      description={`Google deletes it for good: there is no undo. ${keeps}`}
      confirmLabel="Delete"
      confirmText={source.name}
    >
      {Boolean(run.error) && <Alert tone="danger">{errorMessage(run.error)}</Alert>}
    </ConfirmDialog>
  );
}
