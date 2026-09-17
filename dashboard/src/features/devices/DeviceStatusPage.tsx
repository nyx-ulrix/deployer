import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Database, ExternalLink, HardDrive, Leaf, Terminal } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import { AuthShell } from "../../components/layout/AppLayout";
import { StatusDot } from "../../components/ui/Progress";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, EmptyState, ErrorState } from "../../components/ui/States";
import { formatBytes, formatDateTime, formatDuration, relativeTime } from "../../lib/format";
import { UsageBars } from "./DeviceBits";

/** Shown on a host device instead of setup/login (setup status `device_mode: "host"`). */
export function DeviceStatusPage() {
  const status = useQuery({
    queryKey: qk.localDevice,
    queryFn: api.deviceLocal.status,
    refetchInterval: 5000,
    retry: 1,
  });

  return (
    <AuthShell wide>
      <div className="mb-5 flex items-center gap-3">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <HardDrive className="size-5" />
        </span>
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            {status.data?.device_name ?? "Host device"}
          </h1>
          <p className="text-sm text-muted">This PC hosts databases for another Deployer.</p>
        </div>
      </div>

      {status.isPending ? (
        <PageSpinner label="Reading device status…" />
      ) : status.isError ? (
        <ErrorState error={status.error} onRetry={() => void status.refetch()} />
      ) : status.data.mode !== "host" ? (
        <EmptyState
          icon={<HardDrive className="size-5" />}
          title="This Deployer isn't attached to another Deployer"
          description="It runs on its own. To make it a host device, use Settings → Devices or the setup wizard."
          action={
            <Link to="/" className="text-sm font-medium text-accent hover:underline">
              Go to the dashboard
            </Link>
          }
        />
      ) : (
        <div className="space-y-4">
          <Card>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusDot tone={status.data.connected ? "success" : "danger"} pulse={status.data.connected} />
                <span className="font-semibold">{status.data.connected ? "Connected" : "Not connected"}</span>
                <span className="text-sm text-muted">
                  {status.data.connected
                    ? status.data.last_connected_at
                      ? `since ${relativeTime(status.data.last_connected_at)}`
                      : ""
                    : status.data.last_connected_at
                      ? `last connected ${relativeTime(status.data.last_connected_at)}`
                      : "never connected"}
                </span>
              </div>
              {status.data.primary_url && (
                <p className="text-sm">
                  Main Deployer:{" "}
                  <a
                    href={status.data.primary_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium break-all text-accent hover:underline"
                  >
                    {status.data.primary_url} <ExternalLink className="size-3.5 shrink-0" />
                  </a>
                </p>
              )}
              {!status.data.connected && (
                <Alert tone="warning" title="Reconnecting automatically">
                  {status.data.last_error ??
                    "The device retries with increasing delays (up to a minute). Check that this PC can reach the main Deployer's URL."}
                </Alert>
              )}
              {status.data.connected && status.data.last_error && (
                <p className="text-xs text-muted">Last error: {status.data.last_error}</p>
              )}
              <p className="text-sm text-muted">
                Manage projects, data and backups from the main Deployer's dashboard — this page only shows the
                device's health.
              </p>
            </div>
          </Card>

          <Card title="This PC" description={status.data.metrics?.uptime_seconds ? `Up ${formatDuration(status.data.metrics.uptime_seconds)}` : undefined}>
            <UsageBars metrics={status.data.metrics} />
          </Card>

          <Card title="Hosted databases" bodyClassName="p-0 sm:p-0">
            {status.data.hosted_sources.length === 0 ? (
              <p className="px-4 py-4 text-sm text-muted sm:px-5">No databases are hosted on this PC yet.</p>
            ) : (
              <ul className="divide-y divide-border">
                {status.data.hosted_sources.map((s) => (
                  <li key={`${s.kind}:${s.database_name}`} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
                    <span
                      className={
                        "flex size-8 shrink-0 items-center justify-center rounded-lg " +
                        (s.kind === "sql" ? "bg-sql-soft text-sql" : "bg-nosql-soft text-nosql")
                      }
                    >
                      {s.kind === "sql" ? <Database className="size-4" /> : <Leaf className="size-4" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-sm">{s.database_name}</p>
                      <p className="text-xs text-muted">
                        {s.kind === "sql" ? "MariaDB" : "MongoDB"} · {formatBytes(s.size_bytes)}
                        {s.last_backup_at !== undefined && (
                          <>
                            {" "}
                            · last backup{" "}
                            <span title={formatDateTime(s.last_backup_at)}>{relativeTime(s.last_backup_at)}</span>
                          </>
                        )}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={
              <span className="inline-flex items-center gap-2">
                <Terminal className="size-4 text-muted" /> Detach this PC
              </span>
            }
          >
            <div className="space-y-2 text-sm text-muted">
              <p>
                Move this PC's databases to another host from the main Deployer first. Then detach locally (needs
                Windows admin on this PC):
              </p>
              <ul className="list-disc space-y-1 pl-5">
                <li>
                  <strong className="text-fg">Deployer Control</strong> → Host device → Detach, or
                </li>
                <li>
                  run <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-fg">deployer device detach</code>{" "}
                  in an administrator terminal.
                </li>
              </ul>
            </div>
          </Card>
        </div>
      )}
    </AuthShell>
  );
}
