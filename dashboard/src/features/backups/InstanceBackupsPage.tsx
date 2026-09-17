import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, DatabaseBackup, HardDrive, Server } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useDevices } from "../../api/hooks";
import type { InstanceBackupSource } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ProgressBar } from "../../components/ui/Progress";
import { PageSpinner } from "../../components/ui/Spinner";
import { Card, EmptyState, ErrorState, PageHeader } from "../../components/ui/States";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { engineLabel, formatBytes, formatDateTime, localTimeZone, relativeTime } from "../../lib/format";
import { InstanceNav } from "../settings/InstanceNav";

const STALE_MS = 26 * 3_600_000;

/** A source is unhealthy if its last attempt failed or it hasn't succeeded for over a day. */
function health(s: InstanceBackupSource, now = Date.now()): "ok" | "failing" | "stale" | "never" {
  const success = s.last_success_at ? Date.parse(s.last_success_at) : null;
  const failure = s.last_failure_at ? Date.parse(s.last_failure_at) : null;
  if (failure !== null && (success === null || failure > success)) return "failing";
  if (success === null) return "never";
  if (now - success > STALE_MS) return "stale";
  return "ok";
}

const HEALTH_BADGE = {
  ok: { tone: "success", label: "Healthy" },
  failing: { tone: "danger", label: "Failing" },
  stale: { tone: "warning", label: "Overdue" },
  never: { tone: "warning", label: "No backup yet" },
} as const;

export function InstanceBackupsPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const data = useQuery({ queryKey: qk.instanceBackups, queryFn: api.instanceBackups.get, refetchInterval: 30_000 });
  const devices = useDevices("all");
  const deviceName = (id: string | null) =>
    id ? (devices.data?.find((d) => d.id === id)?.name ?? "Host device") : "Main server";

  const platformNow = useMutation({
    mutationFn: api.instanceBackups.platformNow,
    onSuccess: () => {
      toast.success("Platform backup started. The status updates when it finishes.");
      setTimeout(() => void queryClient.invalidateQueries({ queryKey: qk.instanceBackups }), 5000);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't start platform backup"),
  });

  const sources = data.data?.sources ?? [];
  const sorted = [...sources].sort((a, b) => {
    const order = { failing: 0, never: 1, stale: 2, ok: 3 };
    return order[health(a)] - order[health(b)] || a.project_name.localeCompare(b.project_name);
  });
  const unhealthy = sources.filter((s) => health(s) !== "ok").length;

  return (
    <div className="mx-auto w-full max-w-6xl">
      <InstanceNav />
      <PageHeader
        title="Backups"
        description={`Backup health across every project and device. Times in ${localTimeZone()}.`}
        actions={
          <Button
            variant="primary"
            icon={<DatabaseBackup className="size-4" />}
            loading={platformNow.isPending}
            onClick={() => platformNow.mutate()}
          >
            Back up platform data now
          </Button>
        }
      />

      {data.isPending ? (
        <PageSpinner />
      ) : data.isError ? (
        <ErrorState error={data.error} onRetry={() => void data.refetch()} />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <SummaryTile
              icon={unhealthy ? <AlertTriangle className="size-4" /> : <CheckCircle2 className="size-4" />}
              tone={unhealthy ? "danger" : "success"}
              label="Databases"
              value={`${sources.length - unhealthy} / ${sources.length} healthy`}
            />
            <SummaryTile
              icon={<Server className="size-4" />}
              tone={data.data.platform.last_error ? "danger" : "success"}
              label="Platform data (users, projects, settings)"
              value={data.data.platform.last_success_at ? `Backed up ${relativeTime(data.data.platform.last_success_at)}` : "Never backed up"}
              detail={data.data.platform.last_error ?? undefined}
            />
            <SummaryTile
              icon={<HardDrive className="size-4" />}
              tone="neutral"
              label="Backup storage used"
              value={formatBytes(data.data.storage.reduce((n, s) => n + (s.used_bytes ?? 0), 0))}
            />
          </div>

          <Card title="Databases" bodyClassName="p-0 sm:p-0">
            {sorted.length === 0 ? (
              <EmptyState className="m-4" title="No managed databases yet" />
            ) : (
              <Table className="rounded-none border-0">
                <THead>
                  <Tr>
                    <Th>Database</Th>
                    <Th>Host</Th>
                    <Th>Status</Th>
                    <Th>Last success</Th>
                    <Th>Last failure</Th>
                    <Th>PITR latest</Th>
                    <Th className="text-right">Local</Th>
                    <Th className="text-right">Copies</Th>
                  </Tr>
                </THead>
                <TBody>
                  {sorted.map((s) => {
                    const h = health(s);
                    return (
                      <Tr key={s.data_source_id} className={cn(h === "failing" && "bg-danger-soft/40")}>
                        <Td className="min-w-48">
                          <Link
                            to={`/projects/${s.project_id}/backups?source=${encodeURIComponent(s.data_source_id)}`}
                            className="font-medium hover:text-accent hover:underline"
                          >
                            {s.name}
                          </Link>
                          <p className="text-xs text-muted">
                            {s.project_name} · {engineLabel(s.engine)}
                          </p>
                        </Td>
                        <Td className="whitespace-nowrap">{deviceName(s.device_id)}</Td>
                        <Td>
                          <Badge tone={HEALTH_BADGE[h].tone}>{HEALTH_BADGE[h].label}</Badge>
                        </Td>
                        <Td className="whitespace-nowrap" title={formatDateTime(s.last_success_at)}>
                          {relativeTime(s.last_success_at)}
                        </Td>
                        <Td className="max-w-64">
                          {s.last_failure_at ? (
                            <>
                              <span className={cn("whitespace-nowrap", h === "failing" && "font-medium text-danger")} title={formatDateTime(s.last_failure_at)}>
                                {relativeTime(s.last_failure_at)}
                              </span>
                              {s.last_error && <p className="truncate text-xs text-muted" title={s.last_error}>{s.last_error}</p>}
                            </>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </Td>
                        <Td className="whitespace-nowrap" title={formatDateTime(s.pitr_latest)}>
                          {s.pitr_latest ? relativeTime(s.pitr_latest) : <span className="text-muted">Off</span>}
                        </Td>
                        <Td className="text-right whitespace-nowrap tabular-nums">{formatBytes(s.local_bytes)}</Td>
                        <Td className="text-right whitespace-nowrap tabular-nums">{formatBytes(s.copy_bytes)}</Td>
                      </Tr>
                    );
                  })}
                </TBody>
              </Table>
            )}
          </Card>

          <Card title="Storage by location">
            {data.data.storage.length === 0 ? (
              <p className="text-sm text-muted">No backup storage in use yet.</p>
            ) : (
              <ul className="grid gap-4 sm:grid-cols-2">
                {data.data.storage.map((s) => {
                  const total = (s.used_bytes ?? 0) + (s.free_bytes ?? 0);
                  const pct = total > 0 && s.used_bytes !== null ? ((s.used_bytes ?? 0) / total) * 100 : null;
                  return (
                    <li key={`${s.location}:${s.device_id ?? ""}`} className="min-w-0">
                      <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                        <span className="truncate font-medium">
                          {deviceName(s.device_id)}
                          <span className="ml-1 text-xs font-normal text-muted">({s.location})</span>
                        </span>
                        <span className="text-xs whitespace-nowrap text-muted">
                          {formatBytes(s.used_bytes)} used · {formatBytes(s.free_bytes)} free
                        </span>
                      </div>
                      <ProgressBar value={pct} tone={pct !== null && pct > 90 ? "danger" : "accent"} label="Storage used" />
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

function SummaryTile({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail?: string;
  tone: "success" | "danger" | "neutral";
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-xs">
      <div
        className={cn(
          "mb-2 inline-flex size-8 items-center justify-center rounded-lg",
          tone === "success" && "bg-success-soft text-success",
          tone === "danger" && "bg-danger-soft text-danger",
          tone === "neutral" && "bg-surface-2 text-accent",
        )}
      >
        {icon}
      </div>
      <p className="text-xs text-muted">{label}</p>
      <p className="font-semibold">{value}</p>
      {detail && <p className="mt-1 text-xs break-words text-danger">{detail}</p>}
    </div>
  );
}
