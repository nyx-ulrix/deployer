/** Trim whitespace and trailing slashes, e.g. " https://a.example.com/ " -> "https://a.example.com". */
export function normalizeUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

/** Loopback hosts only this PC can reach; mirrors reachable_elsewhere in api/app/services/instance_settings.py. */
export function isLocalHostname(hostname: string): boolean {
  const h = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  return h === "localhost" || h === "127.0.0.1" || h === "::1" || h.endsWith(".localhost");
}

/** True when `url` points at this PC (any scheme or port); false for anything that doesn't parse. */
export function isLocalUrl(url: string): boolean {
  try {
    return isLocalHostname(new URL(url.trim()).hostname);
  } catch {
    return false;
  }
}
