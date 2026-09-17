import type {
  DataSourceKind,
  Device,
  DeviceCapabilities,
  DeviceMetrics,
  DeviceRole,
  DeviceSharingMode,
  EngineAvailability,
  ManagedEngine,
  PlacementOption,
} from "../../api/types";
import { engineLabel, formatBytes } from "../../lib/format";

/** The primary marks a device offline after 60 s without a heartbeat (DEVICES.md). */
export const OFFLINE_AFTER_MS = 60_000;

export const ROLE_LABELS: Record<DeviceRole, string> = {
  database_host: "Database host",
  backup_storage: "Backup storage",
};

export const ROLE_HINTS: Record<DeviceRole, string> = {
  database_host: "Projects can place managed MariaDB/MongoDB databases on this PC.",
  backup_storage: "Stores encrypted backup copies of databases hosted elsewhere. It can't read them.",
};

export const SHARING_LABELS = {
  my_projects: "All my projects",
  selected: "Selected projects",
} as const;

export function engineForKind(kind: DataSourceKind): ManagedEngine {
  return kind === "sql" ? "mariadb" : "mongodb";
}

export function isDeviceOnline(device: Pick<Device, "online" | "last_seen_at">, now: number = Date.now()): boolean {
  if (typeof device.online === "boolean") return device.online;
  if (!device.last_seen_at) return false;
  const t = Date.parse(device.last_seen_at);
  return Number.isFinite(t) && now - t < OFFLINE_AFTER_MS;
}

/** Engines from metrics (live) take precedence over enrollment capabilities. */
export function engineAvailability(
  metrics: Pick<DeviceMetrics, "engines"> | null | undefined,
  capabilities: DeviceCapabilities | null | undefined,
): EngineAvailability {
  return { ...(capabilities?.engines ?? {}), ...(metrics?.engines ?? {}) };
}

/** Why an engine can't run on a device, or null if it can (or we don't know). */
export function engineUnavailableReason(
  engines: EngineAvailability | undefined,
  engine: ManagedEngine,
  capabilities?: DeviceCapabilities | null,
): string | null {
  if (!engines || engines[engine] !== false) return null;
  if (engine === "mongodb" && capabilities?.avx !== true) return "MongoDB not available on this PC (no AVX)";
  return `${engineLabel(engine)} not available on this PC`;
}

/** Human-readable capability notes for the approval page. */
export function capabilityNotes(capabilities: DeviceCapabilities | null | undefined): { ok: boolean; text: string }[] {
  if (!capabilities) return [];
  const notes: { ok: boolean; text: string }[] = [];
  const engines = capabilities.engines ?? {};
  for (const engine of ["mariadb", "mongodb"] as const) {
    if (engines[engine] === undefined) continue;
    const reason = engineUnavailableReason(engines, engine, capabilities);
    notes.push(reason ? { ok: false, text: reason } : { ok: true, text: `${engineLabel(engine)} available` });
  }
  return notes;
}

export type PlacementDisplay = {
  value: string; // "" = main server
  label: string;
  disabled: boolean;
  reason: string | null;
};

export const MAIN_SERVER_VALUE = "";

export function placementValue(deviceId: string | null | undefined): string {
  return deviceId ?? MAIN_SERVER_VALUE;
}

export function deviceIdFromValue(value: string): string | null {
  return value === MAIN_SERVER_VALUE ? null : value;
}

/**
 * How a "Host on" option is shown for a given engine: disabled when the API says it isn't eligible,
 * when the device is offline, or when the engine can't run there. The label carries online state and
 * free disk.
 */
export function placementDisplay(option: PlacementOption, engine: ManagedEngine | null): PlacementDisplay {
  const isMain = option.device_id === null;
  const details: string[] = [];
  if (!isMain) details.push(option.online ? "online" : "offline");
  if (option.disk_free_bytes !== null && option.disk_free_bytes !== undefined) {
    details.push(`${formatBytes(option.disk_free_bytes)} free`);
  }
  let reason: string | null = null;
  if (!option.eligible) reason = option.reason || "Not available for this project";
  else if (!option.online) reason = isMain ? "Main server is unavailable" : "Device is offline";
  else if (engine) reason = engineUnavailableReason(option.engines, engine);
  const label = `${option.name}${details.length ? ` · ${details.join(" · ")}` : ""}${reason ? ` — ${reason}` : ""}`;
  return { value: placementValue(option.device_id), label, disabled: reason !== null, reason };
}

/** Pick a sensible default: the main server if usable, else the first usable option. */
export function defaultPlacement(options: readonly PlacementOption[], engine: ManagedEngine | null): string {
  const displays = options.map((o) => placementDisplay(o, engine));
  const main = displays.find((d) => d.value === MAIN_SERVER_VALUE && !d.disabled);
  return (main ?? displays.find((d) => !d.disabled))?.value ?? MAIN_SERVER_VALUE;
}

/**
 * New-project dialog: there's no project yet, so only the user's own active, database-host devices
 * shared with "all my projects" qualify (the new project will be theirs).
 */
export function newProjectHosts(devices: readonly Device[], userId: string): Device[] {
  return devices.filter(
    (d) =>
      d.owner_id === userId &&
      d.status === "active" &&
      d.sharing_mode === "my_projects" &&
      d.roles.includes("database_host"),
  );
}

export type UsageBar = { key: string; label: string; percent: number | null; detail: string };

function pct(used: number | null | undefined, total: number | null | undefined): number | null {
  if (used === null || used === undefined || !total || total <= 0) return null;
  return Math.min(100, Math.max(0, (used / total) * 100));
}

export function usageBars(metrics: DeviceMetrics | null | undefined): UsageBar[] {
  if (!metrics) return [];
  const bars: UsageBar[] = [];
  if (metrics.cpu_percent !== undefined && metrics.cpu_percent !== null) {
    const p = Math.min(100, Math.max(0, metrics.cpu_percent));
    bars.push({ key: "cpu", label: "CPU", percent: p, detail: `${Math.round(p)}%` });
  }
  if (metrics.memory_total_bytes) {
    bars.push({
      key: "memory",
      label: "Memory",
      percent: pct(metrics.memory_used_bytes, metrics.memory_total_bytes),
      detail: `${formatBytes(metrics.memory_used_bytes)} of ${formatBytes(metrics.memory_total_bytes)}`,
    });
  }
  if (metrics.disk_total_bytes) {
    const used =
      metrics.disk_free_bytes === null || metrics.disk_free_bytes === undefined
        ? null
        : metrics.disk_total_bytes - metrics.disk_free_bytes;
    bars.push({
      key: "disk",
      label: "Disk",
      percent: pct(used, metrics.disk_total_bytes),
      detail: `${formatBytes(metrics.disk_free_bytes)} free of ${formatBytes(metrics.disk_total_bytes)}`,
    });
  }
  return bars;
}

export function usageTone(percent: number | null): "success" | "warning" | "danger" {
  if (percent === null) return "success";
  if (percent >= 90) return "danger";
  if (percent >= 75) return "warning";
  return "success";
}

export type RemovalCheck = { allowed: boolean; force: boolean; reason: string | null };

/** Removing requires no hosted databases; the instance owner may force it. */
export function removalCheck(device: Pick<Device, "hosted_sources_count">, isInstanceOwner: boolean): RemovalCheck {
  const hosted = device.hosted_sources_count ?? 0;
  if (hosted === 0) return { allowed: true, force: false, reason: null };
  const reason = `This device hosts ${hosted} database${hosted === 1 ? "" : "s"}. Move ${
    hosted === 1 ? "it" : "them"
  } to another host first (Databases tab → Move).`;
  return isInstanceOwner ? { allowed: true, force: true, reason } : { allowed: false, force: false, reason };
}

/** Warnings for a Deployer URL that other PCs should use (enrollment target / public URL). */
export function reachabilityWarning(url: string): string | null {
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return null;
  }
  const host = u.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (host === "localhost" || host === "127.0.0.1" || host === "::1" || host.endsWith(".localhost")) {
    return "This URL points at localhost, so other PCs can't reach it. Set up a LAN, Tailscale or Cloudflare address first (Settings → Domains & remote access).";
  }
  if (u.protocol === "http:" && !isPrivateHost(host)) {
    return "Plain http:// is only allowed for localhost, private LAN addresses and *.ts.net. Use https:// for this address.";
  }
  return null;
}

export function isPrivateHost(host: string): boolean {
  if (host === "localhost" || host.endsWith(".ts.net") || host.endsWith(".local") || host.endsWith(".lan")) return true;
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return false;
  const [a, b] = [Number(m[1]), Number(m[2])];
  return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127);
}

export type DeviceSettingsValue = {
  name: string;
  roles: DeviceRole[];
  sharing_mode: DeviceSharingMode;
  project_ids: string[];
};

export function deviceSettingsValid(v: DeviceSettingsValue): boolean {
  return v.name.trim().length > 0 && (v.sharing_mode === "my_projects" || v.project_ids.length > 0);
}
