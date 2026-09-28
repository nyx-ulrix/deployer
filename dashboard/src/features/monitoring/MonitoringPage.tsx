import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff, Check, Send } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useInstanceSettings } from "../../api/hooks";
import type {
  ContainerStat,
  HostMetrics,
  InstanceAlert,
  InstanceMetrics,
  InstanceSettings,
  MetricsPoint,
  MetricsWindow,
  RequestTotals,
} from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import {
  Alert,
  Card,
  ErrorState,
  PageHeader,
} from "../../components/ui/States";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  relativeTime,
} from "../../lib/format";
import { InstanceNav } from "../settings/InstanceNav";
import { linePath } from "./chart";

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${v.toFixed(1)} %`;
const ms = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${Math.round(v)} ms`;

export function MonitoringPage() {
  const [range, setRange] = useState<MetricsWindow>("1h");
  const metrics = useQuery({
    queryKey: qk.metrics(range),
    queryFn: () => api.monitoring.metrics(range),
    refetchInterval: 30_000,
  });
  const alerts = useQuery({
    queryKey: qk.alerts,
    queryFn: api.monitoring.alerts,
    refetchInterval: 30_000,
  });

  return (
    <div className="mx-auto w-full max-w-6xl">
      <InstanceNav />
      <PageHeader
        title="Monitoring"
        description="Host, containers and API health of this Deployer installation, sampled every 15 seconds."
        actions={
          <Select
            aria-label="Time window"
            value={range}
            onChange={(e) => setRange(e.target.value as MetricsWindow)}
            className="w-auto"
          >
            <option value="1h">Last hour</option>
            <option value="6h">Last 6 hours</option>
            <option value="24h">Last 24 hours</option>
          </Select>
        }
      />
      <div className="space-y-5">
        <AlertsCard alerts={alerts.data ?? []} loading={alerts.isPending} />
        {metrics.isPending ? (
          <PageSpinner />
        ) : metrics.isError ? (
          <ErrorState
            error={metrics.error}
            onRetry={() => void metrics.refetch()}
          />
        ) : (
          <>
            {!metrics.data.current && (
              <Alert tone="warning" title="No recent host sample">
                The worker samples host metrics every 15 seconds. It may be
                starting or stopped.
              </Alert>
            )}
            <HostTiles
              points={metrics.data.points}
              current={metrics.data.current}
            />
            <RequestsCard
              points={metrics.data.points}
              totals={metrics.data.requests}
              routes={metrics.data.routes}
            />
            <ContainersCard snapshot={metrics.data.containers} />
          </>
        )}
        <AlertSettingsCard />
      </div>
    </div>
  );
}

function LineChart({
  values,
  max,
  label,
}: {
  values: (number | null)[];
  max?: number;
  label: string;
}) {
  return (
    <svg
      viewBox="0 0 300 48"
      preserveAspectRatio="none"
      className="h-12 w-full text-accent"
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      <line
        x1="0"
        y1="47.5"
        x2="300"
        y2="47.5"
        className="stroke-border"
        strokeWidth="1"
        vectorEffect="non-scaling-stroke"
      />
      <path
        d={linePath(values, 300, 46, max)}
        transform="translate(0 1)"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Tile({
  label,
  value,
  detail,
  children,
  danger,
}: {
  label: string;
  value: string;
  detail?: string;
  children?: ReactNode;
  danger?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-surface p-4 shadow-xs">
      <p className="text-xs text-muted">{label}</p>
      <p
        className={cn(
          "text-lg font-semibold tabular-nums",
          danger && "text-danger",
        )}
      >
        {value}
      </p>
      {detail && <p className="truncate text-xs text-muted">{detail}</p>}
      {children && <div className="mt-2">{children}</div>}
    </div>
  );
}

function HostTiles({
  points,
  current,
}: {
  points: MetricsPoint[];
  current: HostMetrics | null;
}) {
  const memPct =
    current?.memory_used_bytes != null && current.memory_total_bytes
      ? (100 * current.memory_used_bytes) / current.memory_total_bytes
      : null;
  const diskPct =
    current?.disk_free_bytes != null && current.disk_total_bytes
      ? (100 * current.disk_free_bytes) / current.disk_total_bytes
      : null;
  const diskLow =
    current?.disk_free_bytes != null &&
    (current.disk_free_bytes < 5 * 1024 ** 3 || (diskPct ?? 100) < 10);
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile label="CPU" value={pct(current?.cpu_percent)}>
        <LineChart
          values={points.map((p) => p.cpu_percent)}
          max={100}
          label="CPU % over time"
        />
      </Tile>
      <Tile
        label="Memory"
        value={pct(memPct)}
        detail={
          current
            ? `${formatBytes(current.memory_used_bytes)} of ${formatBytes(current.memory_total_bytes)}`
            : undefined
        }
        danger={(memPct ?? 0) > 90}
      >
        <LineChart
          values={points.map((p) => p.memory_percent)}
          max={100}
          label="Memory % over time"
        />
      </Tile>
      <Tile
        label="Disk free (Docker data)"
        value={formatBytes(current?.disk_free_bytes)}
        detail={
          diskPct !== null
            ? `${diskPct.toFixed(0)} % of ${formatBytes(current?.disk_total_bytes)}`
            : undefined
        }
        danger={diskLow}
      >
        <LineChart
          values={points.map((p) => p.disk_free_bytes)}
          max={current?.disk_total_bytes ?? undefined}
          label="Disk free over time"
        />
      </Tile>
      <Tile
        label="Uptime"
        value={formatDuration(current?.uptime_seconds)}
        detail={
          current ? `Sampled ${relativeTime(current.collected_at)}` : undefined
        }
      />
    </div>
  );
}

function RequestsCard({
  points,
  totals,
  routes,
}: {
  points: MetricsPoint[];
  totals: RequestTotals;
  routes: InstanceMetrics["routes"];
}) {
  const minutes = points.length ? points.length : 1;
  const perMin = points.reduce((n, p) => n + p.requests_per_min, 0) / minutes;
  return (
    <Card
      title="API requests"
      description="Counted per route by the API; the health check is excluded."
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Tile
          label="Requests / min"
          value={perMin.toFixed(1)}
          detail={`${totals.requests} in this window`}
        >
          <LineChart
            values={points.map((p) => p.requests_per_min)}
            label="Requests per minute over time"
          />
        </Tile>
        <Tile
          label="5xx error rate"
          value={
            totals.error_rate === null
              ? "—"
              : `${(100 * totals.error_rate).toFixed(2)} %`
          }
          detail={`${totals.errors_5xx} server errors`}
          danger={(totals.error_rate ?? 0) > 0.05}
        >
          <LineChart
            values={points.map((p) =>
              p.error_rate === null ? null : 100 * p.error_rate,
            )}
            label="Error rate % over time"
          />
        </Tile>
        <Tile label="p95 latency" value={ms(totals.p95_ms)}>
          <LineChart
            values={points.map((p) => p.p95_ms)}
            label="p95 latency over time"
          />
        </Tile>
      </div>
      {routes.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium">
            Busiest routes
          </summary>
          <Table className="mt-2">
            <THead>
              <Tr>
                <Th>Route</Th>
                <Th className="text-right">Requests</Th>
                <Th className="text-right">5xx</Th>
                <Th className="text-right">p95</Th>
              </Tr>
            </THead>
            <TBody>
              {routes.map((r) => (
                <Tr key={r.route}>
                  <Td
                    className="max-w-80 truncate font-mono text-xs"
                    title={r.route}
                  >
                    {r.route}
                  </Td>
                  <Td className="text-right tabular-nums">{r.requests}</Td>
                  <Td
                    className={cn(
                      "text-right tabular-nums",
                      r.errors_5xx > 0 && "text-danger",
                    )}
                  >
                    {r.errors_5xx}
                  </Td>
                  <Td className="text-right whitespace-nowrap tabular-nums">
                    {ms(r.p95_ms)}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </details>
      )}
    </Card>
  );
}

function statusTone(c: ContainerStat) {
  if (
    c.status === "restarting" ||
    c.status === "dead" ||
    c.health === "unhealthy"
  )
    return "danger" as const;
  if (c.status === "running")
    return c.health === "starting"
      ? ("warning" as const)
      : ("success" as const);
  return "neutral" as const;
}

function ContainersCard({
  snapshot,
}: {
  snapshot: InstanceMetrics["containers"];
}) {
  const rows = snapshot?.containers ?? [];
  return (
    <Card
      title="Containers"
      description={
        snapshot
          ? `Deployer services and deployed apps · sampled ${relativeTime(snapshot.collected_at)}`
          : undefined
      }
      bodyClassName="p-0 sm:p-0"
    >
      {!snapshot ? (
        <p className="p-4 text-sm text-muted">
          No container stats yet (the worker needs the Docker socket).
        </p>
      ) : (
        <Table className="rounded-none border-0">
          <THead>
            <Tr>
              <Th>Name</Th>
              <Th>Status</Th>
              <Th className="text-right">CPU</Th>
              <Th className="text-right">Memory</Th>
              <Th className="text-right">Restarts</Th>
            </Tr>
          </THead>
          <TBody>
            {rows.map((c) => (
              <Tr key={c.name}>
                <Td className="min-w-40">
                  <p className="font-medium">{c.service ?? c.name}</p>
                  <p className="text-xs text-muted">
                    {c.app_id ? "App" : "Service"} · {c.name}
                  </p>
                </Td>
                <Td>
                  <Badge tone={statusTone(c)}>
                    {[c.status ?? "unknown", c.health]
                      .filter(Boolean)
                      .join(" · ")}
                  </Badge>
                </Td>
                <Td className="text-right whitespace-nowrap tabular-nums">
                  {pct(c.cpu_percent)}
                </Td>
                <Td className="text-right whitespace-nowrap tabular-nums">
                  {formatBytes(c.memory_bytes)}
                  {c.memory_limit_bytes ? (
                    <span className="text-muted">
                      {" "}
                      / {formatBytes(c.memory_limit_bytes)}
                    </span>
                  ) : null}
                </Td>
                <Td
                  className={cn(
                    "text-right tabular-nums",
                    (c.restarts ?? 0) > 0 && "text-warning",
                  )}
                >
                  {c.restarts ?? "—"}
                </Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      )}
    </Card>
  );
}

function AlertsCard({
  alerts,
  loading,
}: {
  alerts: InstanceAlert[];
  loading: boolean;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: qk.alerts });
    void queryClient.invalidateQueries({ queryKey: qk.metricsSummary });
  };
  const act = useMutation({
    mutationFn: ({ id, minutes }: { id: string; minutes?: number }) =>
      minutes ? api.monitoring.snooze(id, minutes) : api.monitoring.dismiss(id),
    onSuccess: refresh,
    onError: (e) => toast.error(errorMessage(e), "Couldn't update the alert"),
  });
  return (
    <Card
      title="Alerts"
      description="Checked every minute. Dismissed and snoozed alerts stay listed until they resolve."
    >
      {loading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : alerts.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-success">
          <Check className="size-4" /> No active alerts.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {alerts.map((a) => (
            <li
              key={a.id}
              className={cn(
                "flex flex-wrap items-start gap-3 py-3 first:pt-0 last:pb-0",
                (a.dismissed || a.snoozed_until) && "opacity-60",
              )}
            >
              <Badge tone={a.severity === "critical" ? "danger" : "warning"}>
                {a.severity}
              </Badge>
              <div className="min-w-0 flex-1 basis-60">
                <p className="text-sm font-medium break-words">{a.message}</p>
                <p
                  className="text-xs text-muted"
                  title={formatDateTime(a.first_seen)}
                >
                  Since {relativeTime(a.first_seen)}
                  {a.snoozed_until &&
                    ` · snoozed until ${formatDateTime(a.snoozed_until)}`}
                  {a.dismissed && " · dismissed"}
                </p>
              </div>
              {!a.dismissed && (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    icon={<BellOff className="size-4" />}
                    onClick={() => act.mutate({ id: a.id, minutes: 60 })}
                  >
                    Snooze 1 h
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => act.mutate({ id: a.id })}
                  >
                    Dismiss
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AlertSettingsCard() {
  const settings = useInstanceSettings();
  if (!settings.data) return null;
  return (
    <AlertSettingsForm
      settings={settings.data}
      key={`${settings.data.alert_webhook_url}|${settings.data.api_key_rate_limit}`}
    />
  );
}

function AlertSettingsForm({ settings }: { settings: InstanceSettings }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState(settings.alert_webhook_url ?? "");
  const [limit, setLimit] = useState(String(settings.api_key_rate_limit));
  const urlValid =
    url.trim() === "" || /^https:\/\/[^\s/@#]+(\/[^\s#]*)?$/i.test(url.trim());
  const limitValid = /^\d+$/.test(limit) && Number(limit) <= 100_000;
  const dirty =
    url.trim() !== (settings.alert_webhook_url ?? "") ||
    limit !== String(settings.api_key_rate_limit);

  const save = useMutation({
    mutationFn: () =>
      api.instance.updateSettings({
        alert_webhook_url: url.trim(),
        api_key_rate_limit: Number(limit),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.instanceSettings, data);
      toast.success("Monitoring settings saved.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't save"),
  });
  const test = useMutation({
    mutationFn: () => api.monitoring.testWebhook(url.trim() || undefined),
    onSuccess: (r) =>
      r.ok
        ? toast.success(`Test alert delivered (${r.detail}).`)
        : toast.error(`Delivery failed: ${r.detail}`),
    onError: (e) => toast.error(errorMessage(e), "Couldn't send the test"),
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <Card title="Alert delivery and limits">
      <form onSubmit={onSubmit} className="space-y-4">
        <Field
          label="Alert webhook URL"
          optional
          hint="Deployer POSTs JSON when an alert opens or resolves (Slack, Discord, ntfy or your own endpoint). https only."
          error={urlValid ? undefined : "Enter an https:// URL"}
        >
          {(id) => (
            <Input
              id={id}
              type="url"
              inputMode="url"
              placeholder="https://hooks.example.com/…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              aria-invalid={!urlValid}
            />
          )}
        </Field>
        <Field
          label="API key rate limit (requests per minute, per key)"
          hint="Applies to project API keys on the data, query, schema and MCP endpoints. 0 = unlimited."
          error={limitValid ? undefined : "Enter a whole number up to 100000"}
        >
          {(id) => (
            <Input
              id={id}
              inputMode="numeric"
              value={limit}
              onChange={(e) => setLimit(e.target.value.trim())}
              aria-invalid={!limitValid}
              className="max-w-40"
            />
          )}
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            variant="primary"
            disabled={!dirty || !urlValid || !limitValid}
            loading={save.isPending}
          >
            Save
          </Button>
          <Button
            type="button"
            icon={<Send className="size-4" />}
            disabled={!url.trim() || !urlValid}
            loading={test.isPending}
            onClick={() => test.mutate()}
          >
            Send test
          </Button>
        </div>
      </form>
    </Card>
  );
}
