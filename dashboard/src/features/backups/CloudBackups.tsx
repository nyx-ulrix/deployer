import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CloudCog, History, RotateCcw } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import { invalidateProjectSources } from "../../api/hooks";
import type { CloudBackup, CloudPitr, CloudRestoreBody, DataSource } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { Alert, Card, EmptyState, ErrorState } from "../../components/ui/States";
import { PageSpinner } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/toast-context";
import { formatBytes, formatDateTime, localTimeZone, relativeTime } from "../../lib/format";
import { JobProgressPanel } from "../jobs/JobProgress";
import { useProjectContext } from "../projects/project-context";
import { combineLocal, inputConstraints, toDateInput, toTimeInput } from "./pitr";

type RestoreFrom = { backup: CloudBackup } | { pitr: CloudPitr };

/** docs/CLOUD.md "C2-2": a DynamoDB database's on-demand backups and point-in-time recovery, kept by AWS
 * (billable, so confirmed), and restores into a new table that becomes a new database. */
export function CloudBackups({ source }: { source: DataSource }) {
  const { project, can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = ["projects", project.id, "cloud-backups", source.id];
  const backups = useQuery({
    queryKey: key,
    queryFn: () => api.cloud.backups(project.id, source.id),
    refetchInterval: (q) => (q.state.data?.backups.some((b) => b.status === "CREATING") ? 5000 : false),
  });
  const [open, setOpen] = useState(false);
  const [table, setTable] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [switching, setSwitching] = useState<CloudPitr | null>(null);
  const [restoring, setRestoring] = useState<RestoreFrom | null>(null);
  const tables = source.cloud?.tables ?? [];
  const admin = can("admin");
  const create = useMutation({
    mutationFn: () => api.cloud.backup(project.id, source.id, { table: table || undefined, confirm_billing: agreed }),
    onSuccess: (out) => {
      setOpen(false);
      setAgreed(false);
      void queryClient.invalidateQueries({ queryKey: key });
      toast.success(`AWS is backing up ${out.backups.map((b) => b.table).join(", ")}.`);
    },
  });

  if (backups.isPending) return <PageSpinner />;
  if (backups.isError) return <ErrorState error={backups.error} onRetry={() => void backups.refetch()} />;
  const info = backups.data;
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <CloudCog className="size-4 text-nosql" /> {source.name}
        </span>
      }
      description="On-demand backups in your AWS account. AWS keeps each one until you delete it; Deployer never deletes them."
      actions={
        admin && (
          <Button size="sm" variant="primary" icon={<Camera className="size-3.5" />} onClick={() => setOpen(true)}>
            Back up now
          </Button>
        )
      }
    >
      <div className="space-y-3">
        {info.backups.length === 0 ? (
          <EmptyState title="No backups yet" description="Back up now to keep a copy of the tables as they are today." />
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border">
            {info.backups.map((b) => (
              <li key={b.arn} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate font-mono text-xs">{b.name}</span>
                <span className="text-muted">{b.table}</span>
                <Badge tone={b.status === "AVAILABLE" ? "success" : "neutral"}>{(b.status ?? "unknown").toLowerCase()}</Badge>
                <span className="text-xs text-muted tabular-nums">{formatBytes(b.size_bytes)}</span>
                <span className="text-xs text-muted" title={formatDateTime(b.created_at)}>
                  {relativeTime(b.created_at)}
                </span>
                {admin && b.status === "AVAILABLE" && (
                  <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => setRestoring({ backup: b })}>
                    Restore
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted">{info.restore}</p>

        <div className="border-t border-border pt-3">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <History className="size-4 text-muted" /> Point-in-time recovery
          </h3>
          <p className="mt-1 text-xs text-muted">
            When it is on, you can restore a table as it was at any second of the last 35 days - handy after a mistake
            nobody backed up for. It is off unless you turn it on, because AWS bills it.
          </p>
          <ul className="mt-2 divide-y divide-border rounded-xl border border-border">
            {info.pitr.map((p) => (
              <li key={p.table} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate">{p.table}</span>
                {p.status === null ? (
                  <span className="text-xs text-warning">{p.problem}</span>
                ) : (
                  <>
                    <Badge tone={p.status === "ENABLED" ? "success" : "neutral"}>{p.status === "ENABLED" ? "on" : "off"}</Badge>
                    {p.status === "ENABLED" && (
                      <span className="text-xs text-muted">
                        Restorable from {formatDateTime(p.earliest)} to {formatDateTime(p.latest)}
                      </span>
                    )}
                    {admin && (
                      <Button size="sm" onClick={() => setSwitching(p)}>
                        {p.status === "ENABLED" ? "Turn off" : "Turn on"}
                      </Button>
                    )}
                    {admin && p.status === "ENABLED" && p.earliest && p.latest && (
                      <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => setRestoring({ pitr: p })}>
                        Restore to a time
                      </Button>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Back up now"
        description="AWS copies the whole table without slowing it down. It usually takes a minute or two."
        footer={
          <>
            <Button onClick={() => setOpen(false)} disabled={create.isPending}>
              Cancel
            </Button>
            <Button variant="primary" loading={create.isPending} disabled={!agreed} onClick={() => create.mutate()}>
              Back up
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {tables.length > 1 && (
            <Field label="Table">
              {(id) => (
                <Select id={id} value={table} onChange={(e) => setTable(e.target.value)}>
                  <option value="">Every table ({tables.length})</option>
                  {tables.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          )}
          <Alert tone="warning" title="AWS bills you for this">
            {info.cost}
            <Checkbox
              className="mt-2"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              label="I understand AWS charges my account for the backup"
            />
          </Alert>
          {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
        </div>
      </Dialog>
      {switching && (
        <PitrDialog
          source={source}
          pitr={switching}
          cost={info.pitr_cost}
          onClose={() => setSwitching(null)}
          onDone={() => void queryClient.invalidateQueries({ queryKey: key })}
        />
      )}
      {restoring && (
        <RestoreCloudDialog source={source} from={restoring} cost={info.restore_cost} onClose={() => setRestoring(null)} />
      )}
    </Card>
  );
}

function PitrDialog({
  source,
  pitr,
  cost,
  onClose,
  onDone,
}: {
  source: DataSource;
  pitr: CloudPitr;
  cost: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const { project } = useProjectContext();
  const toast = useToast();
  const enable = pitr.status !== "ENABLED";
  const [agreed, setAgreed] = useState(false);
  const save = useMutation({
    mutationFn: () =>
      api.cloud.setPitr(project.id, source.id, { table: pitr.table, enabled: enable, confirm_billing: enable && agreed }),
    onSuccess: () => {
      onDone();
      onClose();
      toast.success(`Point-in-time recovery is ${enable ? "on" : "off"} for ${pitr.table}.`);
    },
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title={`${enable ? "Turn on" : "Turn off"} point-in-time recovery for ${pitr.table}`}
      footer={
        <>
          <Button onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            variant={enable ? "primary" : "danger"}
            loading={save.isPending}
            disabled={enable && !agreed}
            onClick={() => save.mutate()}
          >
            {enable ? "Turn on" : "Turn off"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {enable ? (
          <Alert tone="warning" title="AWS bills you for this">
            {cost}
            <Checkbox
              className="mt-2"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              label="I understand AWS charges my account while it is on"
            />
          </Alert>
        ) : (
          <Alert tone="warning">
            AWS deletes the restorable history of {pitr.table}: you can no longer restore it to a time before you turn
            it on again. On-demand backups are not affected.
          </Alert>
        )}
        {save.error && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
      </div>
    </Dialog>
  );
}

function RestoreCloudDialog({
  source,
  from,
  cost,
  onClose,
}: {
  source: DataSource;
  from: RestoreFrom;
  cost: string;
  onClose: () => void;
}) {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const toast = useToast();
  const pitr = "pitr" in from ? from.pitr : null;
  const bounds =
    pitr?.earliest && pitr.latest ? { earliest: new Date(pitr.earliest), latest: new Date(pitr.latest) } : null;
  const tableName = "backup" in from ? from.backup.table : (pitr?.table ?? "");
  const [name, setName] = useState(`${tableName} restored`.slice(0, 63));
  const [latest, setLatest] = useState(true);
  const [date, setDate] = useState(bounds ? toDateInput(bounds.latest) : "");
  const [time, setTime] = useState(bounds ? toTimeInput(bounds.latest) : "");
  const [agreed, setAgreed] = useState(false);
  const at = pitr && !latest ? combineLocal(date, time) : null;
  const constraints = bounds ? inputConstraints(bounds, date) : null;
  const restore = useMutation({
    mutationFn: () => {
      const body: CloudRestoreBody = { name: name.trim(), confirm_billing: agreed };
      if ("backup" in from) body.backup_arn = from.backup.arn;
      else if (latest) Object.assign(body, { table: tableName, latest: true });
      else Object.assign(body, { table: tableName, point_in_time: at?.toISOString() });
      return api.cloud.restore(project.id, source.id, body);
    },
    onSuccess: () => invalidateProjectSources(queryClient, project.id),
  });
  const job = restore.data?.job;
  const ready = name.trim() !== "" && agreed && (latest || !pitr || at !== null);
  return (
    <Dialog
      open
      onClose={onClose}
      title={"backup" in from ? `Restore the backup ${from.backup.name}` : `Restore ${tableName} to a point in time`}
      description="AWS copies the data into a new table, added here as a new database. The original table is not changed."
      footer={
        job ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={restore.isPending}>
              Cancel
            </Button>
            <Button variant="primary" loading={restore.isPending} disabled={!ready} onClick={() => restore.mutate()}>
              Restore into a new table
            </Button>
          </>
        )
      }
    >
      {job ? (
        <JobProgressPanel
          projectId={project.id}
          jobId={job.id}
          title="Restoring in AWS (minutes to hours, depending on the table's size)"
          onFinished={(j) => {
            invalidateProjectSources(queryClient, project.id);
            if (j.status === "succeeded") toast.success(`${restore.data?.data_source.name} is ready on the Databases tab.`);
          }}
        />
      ) : (
        <div className="space-y-3">
          <Field label="Name of the new database" hint="You can close this dialog: the restore keeps going in AWS.">
            {(id) => <Input id={id} value={name} maxLength={63} onChange={(e) => setName(e.target.value)} />}
          </Field>
          {pitr && bounds && constraints && (
            <>
              <Checkbox
                checked={latest}
                onChange={(e) => setLatest(e.target.checked)}
                label="The latest restorable time"
                description={`About ${relativeTime(pitr.latest)}; anything from ${formatDateTime(pitr.earliest)} can be picked instead.`}
              />
              {!latest && (
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
                      />
                    )}
                  </Field>
                </div>
              )}
            </>
          )}
          <Alert tone="warning" title="AWS bills you for this">
            {cost}
            <Checkbox
              className="mt-2"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              label="I understand AWS charges my account for the restore and the new table"
            />
          </Alert>
          {restore.error && <Alert tone="danger">{errorMessage(restore.error)}</Alert>}
        </div>
      )}
    </Dialog>
  );
}
