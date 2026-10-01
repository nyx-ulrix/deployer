import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CloudCog } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import type { DataSource } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Select } from "../../components/ui/Input";
import { Alert, Card, EmptyState, ErrorState } from "../../components/ui/States";
import { PageSpinner } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/toast-context";
import { formatBytes, formatDateTime, relativeTime } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";

/** docs/CLOUD.md "C2-2": a DynamoDB database's on-demand backups, kept by AWS (billable, so confirmed). */
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
  const tables = source.cloud?.tables ?? [];
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
  const list = backups.data.backups;
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <CloudCog className="size-4 text-nosql" /> {source.name}
        </span>
      }
      description="On-demand backups in your AWS account. AWS keeps each one until you delete it; Deployer never deletes them."
      actions={
        can("admin") && (
          <Button size="sm" variant="primary" icon={<Camera className="size-3.5" />} onClick={() => setOpen(true)}>
            Back up now
          </Button>
        )
      }
    >
      <div className="space-y-3">
        {list.length === 0 ? (
          <EmptyState title="No backups yet" description="Back up now to keep a copy of the tables as they are today." />
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border">
            {list.map((b) => (
              <li key={b.arn} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate font-mono text-xs">{b.name}</span>
                <span className="text-muted">{b.table}</span>
                <Badge tone={b.status === "AVAILABLE" ? "success" : "neutral"}>{(b.status ?? "unknown").toLowerCase()}</Badge>
                <span className="text-xs text-muted tabular-nums">{formatBytes(b.size_bytes)}</span>
                <span className="text-xs text-muted" title={formatDateTime(b.created_at)}>
                  {relativeTime(b.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted">{backups.data.restore}</p>
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
            {backups.data.cost}
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
    </Card>
  );
}
