import type { RemoteAccess } from "../../api/types";

export type StepStatus = "done" | "current" | "todo";

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
  return a.replace(/\/+$/, "").toLowerCase() === b.replace(/\/+$/, "").toLowerCase();
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
      body: "Its status is older than 45 seconds. On the Deployer PC run `docker compose ps tunnel`, then `docker compose up -d tunnel`.",
    };
  if (/invalid token|unauthori[sz]ed/i.test(err))
    return {
      title: "Cloudflare rejected the tunnel's token",
      body: "The tunnel was deleted or its token rotated in the Cloudflare dashboard. Link again with the same account to fetch a fresh one.",
    };
  if (/desired\.json/i.test(err))
    return {
      title: "Deployer can't write the shared tunnel volume",
      body: "Run `docker compose run --rm --no-deps --user 0 --cap-add CHOWN --entrypoint sh tunnel -c \"chown -R 10001:10001 /tunnel\"`, then reload this page.",
    };
  if (!data.connector.running) return { title: "The connector stopped", body: err };
  return {
    title: "Connecting to Cloudflare…",
    body: "This usually takes under a minute. If it stays at 0 connections, this PC can't reach Cloudflare outbound on port 7844 (UDP or TCP). Firewalls often block QUIC; cloudflared falls back to HTTP/2 by itself.",
  };
}
