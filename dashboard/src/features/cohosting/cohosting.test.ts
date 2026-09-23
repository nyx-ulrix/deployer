import { describe, expect, it } from "vitest";
import type { CohostEligibility, DataSource, Replica, SyncConflict } from "../../api/types";
import {
  buildCombined,
  canCombine,
  copyTargets,
  defaultPicks,
  deletionNote,
  diffRows,
  displayValue,
  keyText,
  lagText,
  replicaBadge,
  sameValue,
} from "./cohosting";

const replica = (over: Partial<Replica> = {}): Replica => ({
  id: "r1",
  data_source_id: "s1",
  device_id: "d1",
  device_name: "Alice's PC",
  owner_id: "alice",
  online: true,
  status: "syncing",
  lag_seconds: 2,
  last_synced_at: null,
  error: null,
  warnings: [],
  open_conflicts: 0,
  created_at: "2026-09-23T00:00:00Z",
  ...over,
});

const source = (over: Partial<DataSource> = {}): DataSource => ({
  id: "s1",
  project_id: "p1",
  name: "main",
  kind: "sql",
  engine: "mariadb",
  mode: "managed",
  database_name: "main",
  status: "ok",
  status_message: null,
  last_checked_at: null,
  display: { host: null, port: null, username: null, tls: false },
  created_at: "2026-09-01T00:00:00Z",
  device_id: null,
  replicas: [],
  ...over,
});

const conflict = (over: Partial<SyncConflict> = {}): SyncConflict => ({
  id: "c1",
  replica_id: "r1",
  table: "users",
  key: { id: 5 },
  status: "open",
  base: { id: 5, name: "Ann", email: "a@x", age: 30 },
  primary: { id: 5, name: "Anne", email: "a@x", age: 31 },
  replica: { id: 5, name: "Ann", email: "ann@x", age: 32 },
  op_primary: "update",
  op_replica: "update",
  primary_changed_at: null,
  replica_changed_at: null,
  resolution: null,
  resolved: null,
  resolved_by_id: null,
  resolved_at: null,
  created_at: "",
  updated_at: "",
  fields: [
    { name: "age", base: 30, primary: 31, replica: 32, changed_by: "both" },
    { name: "email", base: "a@x", primary: "a@x", replica: "ann@x", changed_by: "replica" },
    { name: "name", base: "Ann", primary: "Anne", replica: "Ann", changed_by: "primary" },
  ],
  suggested: null,
  ...over,
});

describe("lagText / replicaBadge", () => {
  it("says in sync under 10 s and how far behind otherwise", () => {
    expect(lagText(replica({ lag_seconds: 9 }))).toBe("in sync");
    expect(lagText(replica({ lag_seconds: 45 }))).toBe("45s behind");
    expect(lagText(replica({ lag_seconds: 190 }))).toBe("3m behind");
    expect(lagText(replica({ lag_seconds: null }))).toBe("not synced yet");
    expect(lagText(replica({ status: "copying" }))).toBe("copying…");
  });
  it("shows an offline syncing copy as a warning, not an error", () => {
    expect(replicaBadge(replica({ online: false }))).toEqual({ label: "Device offline", tone: "warning" });
    expect(replicaBadge(replica({ status: "error" })).tone).toBe("danger");
    expect(replicaBadge(replica({ status: "paused", online: false })).label).toBe("Paused");
  });
});

describe("copyTargets", () => {
  const elig = (over: Partial<CohostEligibility> = {}): CohostEligibility => ({
    can_cohost: true,
    offer: true,
    devices: [
      { id: "d1", name: "PC", online: true, granted: true },
      { id: "d2", name: "Laptop", online: false, granted: true },
      { id: "d3", name: "NAS", online: true, granted: false },
    ],
    ...over,
  });
  it("shows nothing without an offer (co-hosting stays invisible)", () => {
    expect(copyTargets(undefined, source(), [], "alice")).toBeNull();
    expect(copyTargets(elig({ offer: false }), source(), [], "alice")).toBeNull();
  });
  it("hides for external, device-hosted and already-copied sources", () => {
    expect(copyTargets(elig(), source({ mode: "external" }), [], "alice")).toBeNull();
    expect(copyTargets(elig(), source({ device_id: "d9" }), [], "alice")).toBeNull();
    expect(copyTargets(elig(), source({ replicas: [replica()] }), [], "alice")).toBeNull();
  });
  it("explains unshared and offline devices", () => {
    const t = copyTargets(elig(), source(), [], "alice");
    expect(t?.map((d) => d.reason)).toEqual([null, "offline", "not_shared"]);
    expect(t?.[0].disabled).toBe(false);
  });
  it("keeps a member on the device they already co-host with", () => {
    const other = source({ id: "s2", replicas: [replica({ data_source_id: "s2", device_id: "d2" })] });
    const t = copyTargets(elig(), source(), [source(), other], "alice");
    expect(t?.map((d) => d.reason)).toEqual(["other_device", "offline", "not_shared"]);
  });
});

describe("values", () => {
  it("unwraps JSON tags", () => {
    expect(displayValue({ $dec: "1.50" })).toBe("1.50");
    expect(displayValue({ $date: { $numberLong: "5" } })).toBe("5");
    expect(displayValue(null)).toBe("NULL");
    expect(displayValue({ a: 1 })).toBe('{"a":1}');
    expect(keyText({ id: 5, tenant: "x" })).toBe("id = 5, tenant = x");
  });
  it("compares objects regardless of key order", () => {
    expect(sameValue({ a: 1, b: [1, { c: 2 }] }, { b: [1, { c: 2 }], a: 1 })).toBe(true);
    expect(sameValue({ a: 1 }, { a: 2 })).toBe(false);
  });
});

describe("diff & merge", () => {
  it("classifies fields and highlights only true both-side conflicts", () => {
    const rows = diffRows(
      conflict({
        fields: [
          ...conflict().fields,
          { name: "role", base: "a", primary: "b", replica: "b", changed_by: "both" },
        ],
      }),
    );
    expect(rows.map((r) => [r.name, r.kind])).toEqual([
      ["age", "conflict"],
      ["email", "replica"],
      ["name", "primary"],
      ["role", "same"],
    ]);
  });
  it("builds the combined row from picks and keeps the key", () => {
    const c = conflict();
    expect(buildCombined(c, defaultPicks(c))).toEqual({ id: 5, name: "Anne", email: "ann@x", age: 31 });
    expect(buildCombined(c, { ...defaultPicks(c), age: "replica" }).age).toBe(32);
  });
  it("starts from the server's suggestion when present", () => {
    const c = conflict({
      fields: [conflict().fields[1]],
      suggested: { id: 5, name: "Anne", email: "ann@x", age: 30, extra: true },
    });
    expect(buildCombined(c, {})).toEqual({ id: 5, name: "Anne", email: "ann@x", age: 30, extra: true });
  });
  it("drops a field missing on the picked side", () => {
    const c = conflict({
      replica: { id: 5, name: "Ann", age: 32 },
      fields: [{ name: "email", base: "a@x", primary: "a@x", replica: null, changed_by: "replica" }],
    });
    expect("email" in buildCombined(c, { email: "replica" })).toBe(false);
  });
  it("explains deletes and refuses to combine them", () => {
    const c = conflict({ replica: null, op_replica: "delete" });
    expect(deletionNote(c)).toMatch(/co-host deleted/);
    expect(canCombine(c)).toBe(false);
    expect(deletionNote(conflict())).toBeNull();
  });
});
