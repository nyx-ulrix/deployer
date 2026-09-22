import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Home, Power, RefreshCw } from "lucide-react";
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
import { sameUrl, tunnelHealthy } from "./steps";

const MODE_LABELS: Record<RemoteAccessMode, string> = {
  off: "Local only",
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
      <StatusBanner
        data={data}
        refreshing={refreshing}
        onRefresh={onRefresh}
        onUseLocal={() => publicUrl.mutate({ local: true })}
        usingLocal={publicUrl.isPending}
      />

      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            Your own domain with Cloudflare Tunnel <Badge tone="accent">Recommended</Badge>
          </span>
        }
        description="Six steps, about 15 minutes. You need a domain you own and a free Cloudflare account; Deployer does the tunnel and DNS work for you."
      >
        <CloudflareSetup
          data={data}
          onUsePublicUrl={(b) => publicUrl.mutate(b)}
          usingPublicUrl={publicUrl.isPending}
          onTurnOffQuick={() => setConfirmQuick(false)}
        />
      </Card>

      <Card
        title={
          <span className="flex flex-wrap items-center gap-2">
            Try it without a domain <Badge tone="warning">Testing</Badge>
          </span>
        }
        description="A quick tunnel gives you a random trycloudflare.com address in seconds. No account needed."
      >
        <div className="space-y-3 text-sm">
          <Alert tone="warning" title="Not for everyday use">
            The address changes whenever the tunnel restarts, so it doesn't work for Google/GitHub sign-in or host
            devices. Anyone with the link can reach your sign-in page.
            {data.cloudflare.linked && " While it runs, your Cloudflare tunnel's connector stops."}
          </Alert>
          {data.mode === "quick" ? (
            <>
              {data.quick.url ? (
                <CopyField label="Quick tunnel URL" value={data.quick.url} />
              ) : (
                <p className="flex items-center gap-2 text-muted">
                  <RefreshCw className="size-4 animate-spin" /> Waiting for Cloudflare to assign a URL… If it never
                  appears, trycloudflare.com is rate limited; see <code>docker compose logs tunnel</code>.
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {data.quick.url && !sameUrl(data.public_url, data.quick.url) && (
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

      <Card title="Local network" description="Other devices in your home or office, without any tunnel.">
        <div className="space-y-2 text-sm text-muted">
          <p>
            On the Deployer PC itself the dashboard is at <code>http://localhost:8080</code>. Other devices on the same
            Wi-Fi or LAN can open <code>http://&lt;this PC's address&gt;:8080</code> — the address is shown in Deployer
            Control, or run <code>ipconfig</code> and look for IPv4 Address. Allow LAN access with{" "}
            <code>deployer lan on</code> (block it again with <code>deployer lan off</code>).
          </p>
          <p>
            The PC must be awake and signed in for Deployer to answer. Password and email sign-in work over the LAN;
            Google/GitHub sign-in on other devices only works when the public URL above matches the address you're
            using, so for that use your domain or sign in with a password.
          </p>
        </div>
      </Card>

      {data.cloudflare.linked && (
        <Card title="Danger zone" className="border-danger/40">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Button variant="outline-danger" onClick={() => setUnlinking(true)}>
              Unlink Cloudflare…
            </Button>
            <span className="text-muted">
              Stops the tunnel, forgets the API token and hostnames, and optionally deletes the DNS records and tunnel in
              Cloudflare.
            </span>
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

function StatusBanner({
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
  const healthy = tunnelHealthy(data);
  const t = data.cloudflare.tunnel;
  const tunnelLabel =
    data.mode === "cloudflare" && t
      ? healthy
        ? `Healthy · ${t.connections} connection${t.connections === 1 ? "" : "s"}`
        : data.connector.running
          ? "Connecting…"
          : "Down"
      : data.mode === "quick"
        ? data.connector.running
          ? "Quick tunnel running"
          : "Quick tunnel starting"
        : "Not in use";
  return (
    <Card
      title="Where am I?"
      actions={
        <Button size="icon-sm" variant="ghost" onClick={onRefresh} aria-label="Refresh status" title="Refreshes every 10 seconds">
          <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
        </Button>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <CopyField label="Public URL" value={data.public_url} />
          {isLocalUrl(data.public_url) ? (
            <p className="text-xs text-muted">Only this PC (and your LAN) can reach it.</p>
          ) : (
            <Button size="sm" icon={<Home className="size-3.5" />} loading={usingLocal} onClick={onUseLocal}>
              Back to localhost
            </Button>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-muted">Mode</dt>
            <dd className="font-medium">{MODE_LABELS[data.mode]}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Tunnel</dt>
            <dd className="flex items-center gap-1.5">
              <StatusDot
                tone={!connectorExpected ? "muted" : healthy || (data.mode === "quick" && data.connector.running) ? "success" : data.connector.running ? "warning" : "danger"}
                pulse={connectorExpected && data.connector.running}
              />
              <span className={cn("font-medium", !connectorExpected && "text-muted")}>{tunnelLabel}</span>
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
          Its status is older than 45 seconds, so the tunnel container may not be running. On the Deployer PC check{" "}
          <code>docker compose ps tunnel</code> and start it with <code>docker compose up -d tunnel</code>.
        </Alert>
      )}
      {connectorExpected && data.connector.last_error && (
        <Alert tone={data.connector.running ? "warning" : "danger"} className="mt-3" title="Connector error">
          <span className="font-mono text-xs break-words">{data.connector.last_error}</span>
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
