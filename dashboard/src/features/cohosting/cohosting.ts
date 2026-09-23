import type {
  CohostEligibility,
  ConflictField,
  DataSource,
  JsonObject,
  JsonValue,
  Replica,
  ReplicaStatus,
  SyncConflict,
  SyncHistoryItem,
  SyncSide,
} from "../../api/types";
import type { BadgeTone } from "../../components/ui/Badge";
import { formatDuration } from "../../lib/format";

// Pure helpers for the co-hosting screens (docs/COHOSTING.md). Wording: the master is "the main server"
// and the member's PC is "the co-host"; conflicts use Git's ours (main server) / theirs (co-host).

export function syncPath(projectId: string, sourceId: string): string {
  return `/projects/${projectId}/databases/${sourceId}/sync`;
}

export function deviceOf(source: Pick<DataSource, "replicas">, replicaId: string): string {
  return source.replicas?.find((r) => r.id === replicaId)?.device_name ?? "the co-host";
}

export const SIDE_LABELS: Record<SyncSide, string> = { primary: "Main server", replica: "Co-host" };

// ---- replica status ----

export const REPLICA_STATUS: Record<ReplicaStatus, { label: string; tone: BadgeTone }> = {
  copying: { label: "Copying", tone: "info" },
  syncing: { label: "Syncing", tone: "success" },
  paused: { label: "Paused", tone: "neutral" },
  error: { label: "Error", tone: "danger" },
};

/** A syncing copy whose device is off isn't broken: it catches up on reconnect, so say "offline", not error. */
export function replicaBadge(r: Pick<Replica, "status" | "online">): { label: string; tone: BadgeTone } {
  if (r.status === "syncing" && !r.online) return { label: "Device offline", tone: "warning" };
  return REPLICA_STATUS[r.status];
}

/** "in sync" under 10 s (a sync round runs every 2 s, so a few seconds is normal), else "3m behind". */
export function lagText(r: Pick<Replica, "status" | "lag_seconds">): string {
  if (r.status === "copying") return "copying…";
  if (r.status === "paused") return "paused";
  if (r.lag_seconds === null) return "not synced yet";
  if (r.lag_seconds < 10) return "in sync";
  return `${formatDuration(r.lag_seconds)} behind`;
}

/** Only the co-host who owns the copy's device or a project admin may act on it (router `_require_owner_or_admin`). */
export function canManageReplica(r: Pick<Replica, "owner_id">, userId: string, isAdmin: boolean): boolean {
  return isAdmin || r.owner_id === userId;
}

// ---- "Copy to my device" ----

export type CopyTarget = {
  id: string;
  name: string;
  disabled: boolean;
  /** Why it can't be picked right now; `not_shared` gets a link to the device's sharing settings. */
  reason: "not_shared" | "offline" | "other_device" | null;
};

/**
 * What "Copy to my device" shows for one source, or null for nothing at all. Co-hosting is optional:
 * without `offer` (no permission or no device) the member sees no co-hosting UI.
 */
export function copyTargets(
  eligibility: CohostEligibility | undefined,
  source: DataSource,
  allSources: DataSource[],
  userId: string,
): CopyTarget[] | null {
  if (!eligibility?.offer) return null;
  // Only managed databases on the main server can be copied (409 replica_unsupported otherwise).
  if (source.mode !== "managed" || source.device_id) return null;
  if (source.replicas?.some((r) => r.owner_id === userId)) return null;
  // One co-host device per member per project (409 one_device_per_member).
  const myDevice = allSources.flatMap((s) => s.replicas ?? []).find((r) => r.owner_id === userId)?.device_id;
  return eligibility.devices.map((d) => {
    const reason = !d.granted ? "not_shared" : myDevice && d.id !== myDevice ? "other_device" : !d.online ? "offline" : null;
    return { id: d.id, name: d.name, disabled: reason !== null, reason };
  });
}

// ---- values & keys ----

const TAGS = ["$dec", "$dt", "$date", "$time", "$td", "$b64", "$oid", "$numberLong", "$numberDecimal", "$numberInt", "$numberDouble", "$uuid"];

/** Readable text for a synced value; JSON tags (`{"$dec": "1.50"}`, Extended JSON) show their payload. */
export function displayValue(v: JsonValue | undefined): string {
  if (v === undefined) return "—";
  if (v === null) return "NULL";
  if (typeof v === "string") return v;
  if (typeof v !== "object") return String(v);
  if (!Array.isArray(v)) {
    const keys = Object.keys(v);
    if (keys.length === 1 && TAGS.includes(keys[0])) {
      const inner = v[keys[0]];
      if (keys[0] === "$date" && inner && typeof inner === "object") return displayValue(inner);
      return keys[0] === "$b64" ? `(binary, ${String(inner).length} base64 chars)` : displayValue(inner);
    }
  }
  return JSON.stringify(v);
}

export function keyText(key: JsonObject): string {
  return Object.entries(key)
    .map(([k, v]) => `${k} = ${displayValue(v)}`)
    .join(", ");
}

/** Order-insensitive equality for JSON values (object key order differs between engines). */
export function sameValue(a: JsonValue | undefined, b: JsonValue | undefined): boolean {
  return stable(a) === stable(b);
}

function stable(v: JsonValue | undefined): string {
  if (v === undefined) return "undefined";
  if (v === null || typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stable).join(",")}]`;
  return `{${Object.keys(v)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${stable(v[k])}`)
    .join(",")}}`;
}

// ---- conflict diff ----

/**
 * How one field row renders: `conflict` = both sides changed it differently (the only rows that need a
 * human, highlighted); `same` = both made the identical change; `primary` / `replica` = one side only.
 */
export type FieldKind = "conflict" | "same" | SyncSide;

export type DiffRow = ConflictField & { kind: FieldKind };

export function diffRows(conflict: Pick<SyncConflict, "fields">): DiffRow[] {
  return conflict.fields.map((f) => ({
    ...f,
    kind: f.changed_by !== "both" ? f.changed_by : sameValue(f.primary, f.replica) ? "same" : "conflict",
  }));
}

/** Which side deleted the row, in words; null when neither did. */
export function deletionNote(c: Pick<SyncConflict, "primary" | "replica" | "op_primary" | "op_replica">): string | null {
  const pDel = c.primary === null || c.op_primary === "delete";
  const rDel = c.replica === null || c.op_replica === "delete";
  if (pDel && rDel) return "Both copies deleted this row.";
  if (pDel) return "The main server deleted this row while the co-host changed it. Keeping the main server deletes it on both copies.";
  if (rDel) return "The co-host deleted this row while the main server changed it. Keeping the co-host deletes it on both copies.";
  return null;
}

/** Combining needs a row on both sides; for delete-vs-update the user keeps one side instead. */
export function canCombine(c: Pick<SyncConflict, "primary" | "replica">): boolean {
  return c.primary !== null && c.replica !== null;
}

export type Picks = Record<string, SyncSide>;

/** Per changed field, the side the merge takes by default: the side that changed it (main server when both did). */
export function defaultPicks(c: Pick<SyncConflict, "fields">): Picks {
  return Object.fromEntries(c.fields.map((f) => [f.name, f.changed_by === "replica" ? "replica" : "primary"]));
}

/**
 * The whole row for `choice: "manual"`: starts from the server's `suggested` merge when there is one (else
 * the main server's row), applies the per-field picks (a field missing on the picked side is dropped) and
 * forces the key back, since key fields can't change.
 */
export function buildCombined(c: Pick<SyncConflict, "fields" | "suggested" | "primary" | "replica" | "key">, picks: Picks): JsonObject {
  const out: JsonObject = { ...(c.suggested ?? c.primary ?? c.replica ?? {}) };
  for (const f of c.fields) {
    const side = picks[f.name] ?? (f.changed_by === "replica" ? "replica" : "primary");
    const row = side === "primary" ? c.primary : c.replica;
    if (row && f.name in row) out[f.name] = row[f.name];
    else delete out[f.name];
  }
  return { ...out, ...c.key };
}

// ---- history ----

export function historyLabel(item: Pick<SyncHistoryItem, "type" | "origin">): string {
  if (item.type === "conflict") {
    if (item.origin === "primary") return "Conflict resolved: kept main server";
    if (item.origin === "replica") return "Conflict resolved: kept co-host";
    return "Conflict resolved: combined";
  }
  switch (item.origin) {
    case "primary":
      return "Changed on the main server";
    case "replica":
      return "Changed on the co-host";
    case "resolution":
      return "Chosen when resolving a conflict";
    case "restore":
      return "Restored from history";
    default:
      return "Version";
  }
}

export const RESOLUTION_LABELS: Record<string, string> = {
  primary: "Kept main server",
  replica: "Kept co-host",
  manual: "Combined",
};
