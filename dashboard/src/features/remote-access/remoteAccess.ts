import { errorMessage, isApiError } from "../../api/client";
import type { Domain, RemoteAccess } from "../../api/types";

/** Cloudflare's token page with three permissions pre-filled (Tunnel can't be pre-filled; see docs). */
export const CLOUDFLARE_TOKEN_TEMPLATE_URL =
  "https://dash.cloudflare.com/profile/api-tokens?permissionGroupKeys=%5B%7B%22key%22%3A%22account_settings%22%2C%22type%22%3A%22read%22%7D%2C%7B%22key%22%3A%22zone%22%2C%22type%22%3A%22read%22%7D%2C%7B%22key%22%3A%22dns%22%2C%22type%22%3A%22edit%22%7D%5D&accountId=%2A&zoneId=all&name=Deployer";

export const REQUIRED_PERMISSIONS: { scope: string; permission: string; access: string; name: string; prefilled: boolean }[] = [
  { scope: "Account", permission: "Cloudflare Tunnel", access: "Edit", name: "Account / Cloudflare Tunnel / Edit", prefilled: false },
  { scope: "Account", permission: "Account Settings", access: "Read", name: "Account / Account Settings / Read", prefilled: true },
  { scope: "Zone", permission: "DNS", access: "Edit", name: "Zone / DNS / Edit", prefilled: true },
  { scope: "Zone", permission: "Zone", access: "Read", name: "Zone / Zone / Read", prefilled: true },
];

/** How to fix a permission reported in `missing_permissions`. */
export function permissionFix(name: string): string {
  const known = REQUIRED_PERMISSIONS.find((p) => p.name.toLowerCase() === name.toLowerCase());
  if (!known) return "Edit the token in Cloudflare and add this permission.";
  const resources =
    known.scope === "Account"
      ? "and make sure Account Resources include the account that owns your domain"
      : "and make sure Zone Resources include your domain (or all zones)";
  return `Edit the token → add ${known.scope} → ${known.permission} → ${known.access}, ${resources}.`;
}

export const OAUTH_CONSOLES = {
  google: "https://console.cloud.google.com/apis/credentials",
  github: "https://github.com/settings/developers",
} as const;

const MESSAGES: Record<string, string> = {
  cloudflare_auth_failed: "Cloudflare rejected this API token. Check that you copied the whole token and that it hasn't expired or been rolled.",
  cloudflare_permission_missing: "The token is missing a permission Cloudflare needs for this step.",
  cloudflare_api_error: "Cloudflare returned an error or couldn't be reached.",
  account_not_found: "This token can't read that Cloudflare account. Check the token's Account Resources.",
  already_linked:
    "A different Cloudflare account is already linked and still has hostnames. Remove those hostnames or unlink first.",
  zone_not_found: "That domain isn't in the linked Cloudflare account.",
  hostname_not_in_zone: "The hostname must be the domain itself or a subdomain of it.",
  domain_exists: "That hostname is already set up.",
  not_linked: "Link a Cloudflare account first.",
  domain_not_active: "That hostname isn't active yet. Wait for it to finish setting up, then try again.",
  tunnel_not_active: "The tunnel isn't running in Cloudflare mode. Link your account (and turn off the quick tunnel) first.",
  quick_tunnel_not_ready: "The quick tunnel doesn't have a URL yet. Wait a few seconds and try again.",
};

export function remoteAccessError(e: unknown): string {
  if (isApiError(e)) {
    const base = MESSAGES[e.code];
    if (e.code === "cloudflare_api_error" || e.code === "validation_error") return e.message || base || errorMessage(e);
    if (e.code === "cloudflare_permission_missing") {
      const missing = e.details.missing_permissions;
      if (Array.isArray(missing) && missing.length > 0) return `${base} Missing: ${missing.join(", ")}.`;
    }
    if (base) return base;
  }
  return errorMessage(e);
}

export type DnsRecord = { id: string; type: string; content: string };

export function dnsRecordsFrom(e: unknown): DnsRecord[] | null {
  if (!isApiError(e) || e.code !== "dns_record_exists") return null;
  const raw = e.details.records;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((r): DnsRecord[] => {
    if (typeof r !== "object" || r === null) return [];
    const o = r as Record<string, unknown>;
    return [{ id: String(o.id ?? ""), type: String(o.type ?? "?"), content: String(o.content ?? "") }];
  });
}

/** True when this dashboard is currently opened through `hostname`. */
export function openedVia(hostname: string, location: Pick<Location, "hostname"> = window.location): boolean {
  return location.hostname.toLowerCase() === hostname.toLowerCase();
}

/** The Cloudflare domain this page is opened through, if any. */
export function currentDomain(data: RemoteAccess, location: Pick<Location, "hostname"> = window.location): Domain | null {
  return data.cloudflare.domains.find((d) => openedVia(d.hostname, location)) ?? null;
}

export function openedViaQuickTunnel(location: Pick<Location, "hostname"> = window.location): boolean {
  return location.hostname.toLowerCase().endsWith(".trycloudflare.com");
}

export function isLocalUrl(url: string): boolean {
  try {
    const h = new URL(url).hostname;
    return h === "localhost" || h === "127.0.0.1" || h === "::1" || h === "[::1]";
  } catch {
    return false;
  }
}
