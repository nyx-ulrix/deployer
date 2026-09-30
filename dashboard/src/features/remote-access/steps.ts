import type { RemoteAccess } from "../../api/types";
import type { StepStatus } from "../../components/ui/StepCard";
import { normalizeUrl } from "../../lib/url";

export type { StepStatus };

/** Local (non-API) inputs that affect step status. */
export type StepInputs = {
  /** The user clicked "I've done this" on the account step. */
  accountAcknowledged: boolean;
  /** A token was verified in this session and had all permissions. */
  verifiedOk: boolean;
  /** The user chose to replace the stored token (treat as not linked for steps 2–3). */
  replacing: boolean;
};

export const STEP_TITLES = [
  "Get a Cloudflare account and add your domain",
  "Create an API token",
  "Link your Cloudflare account",
  "Choose your hostname",
  "Wait for the tunnel",
  "Use it as the public URL",
] as const;

export function sameUrl(a: string, b: string): boolean {
  return normalizeUrl(a).toLowerCase() === normalizeUrl(b).toLowerCase();
}

export function tunnelHealthy(data: RemoteAccess): boolean {
  const t = data.cloudflare.tunnel;
  return data.mode === "cloudflare" && data.connector.running && Boolean(t && (t.status === "healthy" || t.connections > 0));
}

/** Status of the six Cloudflare setup steps: every completed step is "done", the first open one "current". */
export function deriveSteps(data: RemoteAccess, input: StepInputs): StepStatus[] {
  const cf = data.cloudflare;
  const linked = cf.linked && !input.replacing;
  const zones = cf.zones ?? [];
  const done = [
    linked || zones.length > 0 || input.verifiedOk || input.accountAcknowledged,
    linked || input.verifiedOk,
    linked,
    linked && cf.domains.length > 0,
    linked && cf.domains.length > 0 && tunnelHealthy(data),
    linked && cf.domains.some((d) => sameUrl(d.url, data.public_url)),
  ];
  const current = done.indexOf(false);
  return done.map((d, i) => (d ? "done" : i === current ? "current" : "todo"));
}

/** Plain-language hint when the tunnel isn't healthy, from docs/REMOTE_ACCESS.md → Troubleshooting. */
export function connectorHint(data: RemoteAccess): { title: string; body: string } | null {
  if (tunnelHealthy(data)) return null;
  const err = data.connector.last_error ?? "";
  if (data.mode === "quick") return { title: "The quick tunnel is running instead", body: "Turn it off below so your Cloudflare tunnel's connector starts again." };
  if (!data.connector.running && !err)
    return {
      title: "The tunnel container isn't running",
      body: "Its status is older than 45 seconds. On the Deployer PC open Deployer Control and click Restart (or run `deployer restart`). `deployer logs tunnel` shows why it stopped.",
    };
  if (/invalid token|unauthori[sz]ed/i.test(err))
    return {
      title: "Cloudflare rejected the tunnel's token",
      body: "The tunnel was deleted or its token rotated in the Cloudflare dashboard. Link again with the same account to fetch a fresh one.",
    };
  if (/desired\.json/i.test(err))
    return {
      title: "Deployer can't write the shared tunnel volume",
      body: "Restart Deployer (Deployer Control > Restart, or `deployer restart`): it fixes the volume's permissions when it starts. Then reload this page.",
    };
  if (!data.connector.running) return { title: "The connector stopped", body: err };
  return {
    title: "Connecting to Cloudflare…",
    body: "This usually takes under a minute. If it stays at 0 connections, something on this PC's network is blocking Cloudflare: your router, antivirus, firewall or VPN. Try another network, or check `deployer logs tunnel`.",
  };
}
