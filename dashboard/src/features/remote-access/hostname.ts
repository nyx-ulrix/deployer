const LABEL = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

/** Lower-case, trim, drop a trailing dot and a pasted zone suffix ("deployer.example.com" → "deployer"). */
export function normalizeSubdomain(input: string, zone: string): string {
  let s = input.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/\.+$/, "");
  const z = zone.toLowerCase();
  if (z && s === z) return "";
  if (z && s.endsWith(`.${z}`)) s = s.slice(0, -(z.length + 1));
  return s;
}

/** Validation message for a subdomain inside `zone`, or null when valid. Empty = the zone apex. */
export function validateSubdomain(sub: string, zone: string): string | null {
  if (!zone) return "Choose a domain first.";
  if (sub === "") return null;
  if (sub.includes("*")) return "Wildcards aren't supported.";
  const labels = sub.split(".");
  for (const label of labels) {
    if (label.length === 0) return "Remove the empty part between dots.";
    if (label.length > 63) return "Each part can be at most 63 characters.";
    if (!LABEL.test(label)) return "Use letters, numbers and hyphens only (not at the start or end).";
  }
  if (buildHostname(sub, zone).length > 253) return "The full hostname is too long.";
  return null;
}

export function buildHostname(sub: string, zone: string): string {
  return sub ? `${sub}.${zone}` : zone;
}

/** Live preview for the hostname field, e.g. "https://deployer.example.com". */
export function previewUrl(sub: string, zone: string): string | null {
  if (!zone || validateSubdomain(sub, zone)) return null;
  return `https://${buildHostname(sub, zone)}`;
}

export function hostnameInZone(hostname: string, zone: string): boolean {
  const h = hostname.toLowerCase();
  const z = zone.toLowerCase();
  return h === z || h.endsWith(`.${z}`);
}
