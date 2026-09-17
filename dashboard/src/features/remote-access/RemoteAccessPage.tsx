import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cloud, FlaskConical, Home, Power, RefreshCw } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import type { PublicUrlRequest, PublicUrlResponse, RemoteAccess, RemoteAccessMode } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { StatusDot } from "../../components/ui/Progress";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, ErrorState, PageHeader } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatDateTime, relativeTime } from "../../lib/format";
import { InstanceNav } from "../settings/InstanceNav";
import { CloudflareSetup } from "./CloudflareSetup";
import { PublicUrlResultDialog, UnlinkDialog } from "./PublicUrlDialogs";
import { currentDomain, isLocalUrl, openedViaQuickTunnel, remoteAccessError } from "./remoteAccess";

const MODE_LABELS: Record<RemoteAccessMode, string> = {
  off: "Off",
  cloudflare: "Cloudflare Tunnel",
  quick: "Quick tunnel",
};

export function RemoteAccessPage() {
  const query = useQuery({
    queryKey: qk.remoteAccess,
    queryFn: api.remoteAccess.get,
    refetchInterval: 10_000,
  });

  return (
    <div className="mx-auto w-full max-w-4xl">
      <InstanceNav />
      <PageHeader
        title="Domains & remote access"
        description="Reach this Deployer from anywhere with your own domain through your Cloudflare account — no port forwarding or certificates."
      />
      {query.isPending ? (
        <PageSpinner />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <RemoteAccessContent data={query.data} refreshing={query.isFetching} onRefresh={() => void query.refetch()} />
      )}
    </div>
  );
}

function RemoteAccessContent({
  data,
  refreshing,
  onRefresh,
}: {
  data: RemoteAccess;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [view, setView] = useState<RemoteAccessMode>(data.mode === "off" && data.cloudflare.linked ? "cloudflare" : data.mode);
  const [result, setResult] = useState<PublicUrlResponse | null>(null);
  const [confirmQuick, setConfirmQuick] = useState<boolean | null>(null);
  const [unlinking, setUnlinking] = useState(false);

  const publicUrl = useMutation({
    mutationFn: (body: PublicUrlRequest) => api.remoteAccess.usePublicUrl(body),
    onSuccess: (res) => {
      queryClient.setQueryData(qk.instanceSettings, res.settings);
      void queryClient.invalidateQueries({ queryKey: qk.remoteAccess });
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
      setResult(res);
    },
    onError: (e) => toast.error(remoteAccessError(e), "Couldn't change the public URL"),
  });

  const quick = useMutation({
    mutationFn: (enabled: boolean) => api.remoteAccess.quick(enabled),
    onSuccess: (res, enabled) => {
      queryClient.setQueryData(qk.remoteAccess, res);
      void queryClient.invalidateQueries({ queryKey: qk.instanceSettings });
      setConfirmQuick(null);
      toast.success(enabled ? "Quick tunnel starting. The URL appears in a few seconds." : "Quick tunnel turned off.");
    },
    onError: (e) => toast.error(remoteAccessError(e), "Couldn't change the quick tunnel"),
  });

  const via = currentDomain(data);
  const viaQuick = openedViaQuickTunnel();

  return (
    <div className="space-y-5">
      <StatusCard
        data={data}
        refreshing={refreshing}
        onRefresh={onRefresh}
        onUseLocal={() => publicUrl.mutate({ local: true })}
        usingLocal={publicUrl.isPending}
      />

      <fieldset>
        <legend className="mb-2 text-sm font-medium">How should people reach this Deployer?</legend>
        <div className="grid gap-2 md:grid-cols-3">
          <OptionCard
            selected={view === "off"}
            active={data.mode === "off"}
            onClick={() => setView("off")}
            icon={<Home className="size-4" />}
            title="Off"
            description="Only on this PC and your local network."
          />
          <OptionCard
            selected={view === "cloudflare"}
            active={data.mode === "cloudflare"}
            onClick={() => setView("cloudflare")}
            icon={<Cloud className="size-4" />}
            title="Cloudflare Tunnel with your domain"
            badge={<Badge tone="accent">Recommended</Badge>}
            description="A stable https://deployer.example.com for sign-in, invites and host devices."
          />
          <OptionCard
            selected={view === "quick"}
            active={data.mode === "quick"}
            onClick={() => setView("quick")}
            icon={<FlaskConical className="size-4" />}
            title="Quick tunnel"
            badge={<Badge tone="warning">Testing</Badge>}
            description="A random trycloudflare.com address. No account needed; changes on restart."
          />
        </div>
      </fieldset>

      {view === "off" && (
        <Card title="Local only">
          <div className="space-y-3 text-sm">
            <p className="text-muted">
              With remote access off, Deployer is reachable at <code>http://localhost</code> on this PC or its LAN
              address. Other devices outside your network can't reach it.
            </p>
            {data.mode === "quick" && (
              <Button icon={<Power className="size-4" />} loading={quick.isPending} onClick={() => setConfirmQuick(false)}>
                Turn off quick tunnel
              </Button>
            )}
            {data.cloudflare.linked && (
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline-danger" onClick={() => setUnlinking(true)}>
                  Unlink Cloudflare…
                </Button>
                <span className="text-xs text-muted">Stops the tunnel and removes the stored token.</span>
              </div>
            )}
            {data.mode === "off" && !data.cloudflare.linked && <Alert tone="success">Remote access is off.</Alert>}
          </div>
        </Card>
      )}

      {view === "cloudflare" && (
        <Card
          title="Cloudflare Tunnel"
          description="Uses your own free Cloudflare account. Deployer creates the tunnel and DNS records for you."
        >
          {data.mode === "quick" && data.cloudflare.linked && (
            <Alert tone="warning" className="mb-4" title="The quick tunnel is running instead">
              Your Cloudflare tunnel is configured but its connector is stopped while the quick tunnel runs.{" "}
              <button type="button" className="font-medium text-accent hover:underline" onClick={() => setConfirmQuick(false)}>
                Turn off quick tunnel
              </button>
            </Alert>
          )}
          <CloudflareSetup data={data} onUsePublicUrl={(b) => publicUrl.mutate(b)} usingPublicUrl={publicUrl.isPending} />
        </Card>
      )}

      {view === "quick" && (
        <Card title="Quick tunnel" description="For trying things out.">
          <div className="space-y-3 text-sm">
            <Alert tone="warning" title="Not for everyday use">
              The address is random and changes whenever the tunnel restarts, so it doesn't work for Google/GitHub
              sign-in or host devices. Anyone with the link can reach your sign-in page.
            </Alert>
            {data.mode === "quick" ? (
              <>
                {data.quick.url ? (
                  <CopyField label="Quick tunnel URL" value={data.quick.url} />
                ) : (
                  <p className="flex items-center gap-2 text-muted">
                    <RefreshCw className="size-4 animate-spin" /> Waiting for Cloudflare to assign a URL…
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  {data.quick.url && data.public_url.replace(/\/+$/, "") !== data.quick.url.replace(/\/+$/, "") && (
                    <Button loading={publicUrl.isPending} onClick={() => publicUrl.mutate({ quick: true })}>
                      Use as public URL
                    </Button>
                  )}
                  <Button icon={<Power className="size-4" />} loading={quick.isPending} onClick={() => setConfirmQuick(false)}>
                    Turn off
                  </Button>
                </div>
              </>
            ) : (
              <Button variant="primary" icon={<FlaskConical className="size-4" />} loading={quick.isPending} onClick={() => setConfirmQuick(true)}>
                Start quick tunnel
              </Button>
            )}
          </div>
        </Card>
      )}

      {confirmQuick !== null && (
        <ConfirmDialog
          open
          onClose={() => setConfirmQuick(null)}
          onConfirm={() => quick.mutate(confirmQuick)}
          loading={quick.isPending}
          destructive={Boolean((confirmQuick && via) || (!confirmQuick && viaQuick))}
          title={confirmQuick ? "Start a quick tunnel?" : "Turn off the quick tunnel?"}
          confirmLabel={confirmQuick ? "Start quick tunnel" : "Turn off"}
          description={
            confirmQuick
              ? data.cloudflare.linked
                ? "Your Cloudflare tunnel's connector stops while the quick tunnel runs, so your own hostnames stop working until you turn it off."
                : "Cloudflare assigns a random trycloudflare.com URL that changes on every restart."
              : data.cloudflare.linked
                ? "Your Cloudflare tunnel starts again."
                : "The trycloudflare.com address stops working. If it's the public URL, that reverts to the local address."
          }
        >
          {confirmQuick && via && (
            <Alert tone="danger" title="You're using this page through Cloudflare">
              This page is open at {via.hostname}, which stops working when the quick tunnel starts. Continue from the
              quick tunnel URL or <code>http://localhost</code> on the Deployer PC.
            </Alert>
          )}
          {!confirmQuick && viaQuick && (
            <Alert tone="danger" title="You're using this page through the quick tunnel">
              This page will lose its connection. Continue from <code>http://localhost</code> on the Deployer PC.
            </Alert>
          )}
        </ConfirmDialog>
      )}
      {unlinking && <UnlinkDialog data={data} onClose={() => setUnlinking(false)} />}
      {result && <PublicUrlResultDialog result={result} onClose={() => setResult(null)} />}
    </div>
  );
}

function StatusCard({
  data,
  refreshing,
  onRefresh,
  onUseLocal,
  usingLocal,
}: {
  data: RemoteAccess;
  refreshing: boolean;
  onRefresh: () => void;
  onUseLocal: () => void;
  usingLocal: boolean;
}) {
  const connectorExpected = data.mode !== "off";
  return (
    <Card
      title="Status"
      actions={
        <Button size="icon-sm" variant="ghost" onClick={onRefresh} aria-label="Refresh status" title="Refreshes every 10 seconds">
          <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
        </Button>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <CopyField label="Public URL" value={data.public_url} />
          {!isLocalUrl(data.public_url) && (
            <button type="button" className="text-xs font-medium text-accent hover:underline disabled:opacity-50" onClick={onUseLocal} disabled={usingLocal}>
              Use local URL instead
            </button>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-muted">Mode</dt>
            <dd className="font-medium">{MODE_LABELS[data.mode]}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Connector</dt>
            <dd className="flex items-center gap-1.5">
              {connectorExpected ? (
                <>
                  <StatusDot tone={data.connector.running ? "success" : "danger"} pulse={data.connector.running} />
                  <span className="font-medium">{data.connector.running ? "Running" : "Not running"}</span>
                </>
              ) : (
                <>
                  <StatusDot tone="muted" />
                  <span className="text-muted">Stopped</span>
                </>
              )}
            </dd>
            {data.connector.running && data.connector.started_at && (
              <p className="text-xs text-muted" title={formatDateTime(data.connector.started_at)}>
                since {relativeTime(data.connector.started_at)}
              </p>
            )}
          </div>
        </dl>
      </div>
      {connectorExpected && !data.connector.running && !data.connector.last_error && (
        <Alert tone="warning" className="mt-3" title="The tunnel connector hasn't reported recently">
          Its status is older than 45 seconds, so the tunnel container may not be running. Check{" "}
          <code>docker compose ps tunnel</code> and start it with <code>docker compose up -d tunnel</code>.
        </Alert>
      )}
      {connectorExpected && data.connector.last_error && (
        <Alert tone={data.connector.running ? "warning" : "danger"} className="mt-3" title="Connector error">
          <span className="font-mono text-xs">{data.connector.last_error}</span>
          {!data.connector.running && (
            <p className="mt-1 text-xs">
              If the tunnel container isn't running, start it with <code>docker compose up -d tunnel</code>.
            </p>
          )}
        </Alert>
      )}
    </Card>
  );
}

function OptionCard({
  selected,
  active,
  onClick,
  icon,
  title,
  description,
  badge,
}: {
  selected: boolean;
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  title: string;
  description: string;
  badge?: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "flex h-full w-full flex-col items-start gap-2 rounded-xl border p-3 text-left transition-colors",
        selected ? "border-accent bg-accent-soft/50 ring-1 ring-accent" : "border-border bg-surface hover:bg-surface-2",
      )}
    >
      <span className="flex w-full items-center gap-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-accent">{icon}</span>
        {badge}
        {active && (
          <Badge tone="success" className="ml-auto">
            Active
          </Badge>
        )}
      </span>
      <span className="text-sm font-semibold">{title}</span>
      <span className="text-xs text-muted">{description}</span>
    </button>
  );
}
