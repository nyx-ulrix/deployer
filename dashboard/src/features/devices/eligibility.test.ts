import { describe, expect, it } from "vitest";
import type { Device, PlacementOption } from "../../api/types";
import {
  capabilityNotes,
  defaultPlacement,
  deviceIdFromValue,
  isDeviceOnline,
  newProjectHosts,
  placementDisplay,
  reachabilityWarning,
  removalCheck,
  usageBars,
} from "./eligibility";

const option = (over: Partial<PlacementOption> = {}): PlacementOption => ({
  device_id: "d1",
  name: "Gaming PC",
  online: true,
  eligible: true,
  reason: null,
  disk_free_bytes: 50 * 1024 ** 3,
  engines: { mariadb: true, mongodb: true },
  ...over,
});

const device = (over: Partial<Device> = {}): Device => ({
  id: "d1",
  name: "Gaming PC",
  owner_id: "u1",
  status: "active",
  roles: ["database_host"],
  sharing_mode: "my_projects",
  hostname: "gaming",
  os: "Windows 11",
  version: "0.2.0",
  capabilities: null,
  metrics: null,
  last_seen_at: null,
  created_at: "2026-09-01T00:00:00Z",
  ...over,
});

describe("placementDisplay", () => {
  it("shows online state and free disk for usable devices", () => {
    const d = placementDisplay(option(), "mariadb");
    expect(d).toMatchObject({ value: "d1", disabled: false, reason: null });
    expect(d.label).toBe("Gaming PC · online · 50.0 GB free");
  });

  it("labels the main server without online state", () => {
    const d = placementDisplay(option({ device_id: null, name: "Main server", disk_free_bytes: null }), "mongodb");
    expect(d).toMatchObject({ value: "", label: "Main server", disabled: false });
    expect(deviceIdFromValue(d.value)).toBeNull();
  });

  it("disables ineligible, offline and engine-less devices with a reason", () => {
    expect(placementDisplay(option({ eligible: false, reason: "Not shared with this project" }), "mariadb")).toMatchObject({
      disabled: true,
      reason: "Not shared with this project",
    });
    expect(placementDisplay(option({ online: false }), "mariadb")).toMatchObject({ disabled: true, reason: "Device is offline" });
    const noAvx = placementDisplay(option({ engines: { mariadb: true, mongodb: false } }), "mongodb");
    expect(noAvx.disabled).toBe(true);
    expect(noAvx.reason).toMatch(/MongoDB not available.*AVX/);
    expect(noAvx.label).toMatch(/— MongoDB not available/);
    expect(placementDisplay(option({ engines: { mariadb: true, mongodb: false } }), "mariadb").disabled).toBe(false);
  });

  it("defaults to the main server when usable, else the first usable option", () => {
    const main = option({ device_id: null, name: "Main server" });
    expect(defaultPlacement([option(), main], "mariadb")).toBe("");
    expect(defaultPlacement([main, option()].map((o) => (o.device_id === null ? { ...o, online: false } : o)), "mariadb")).toBe("d1");
  });
});

describe("devices", () => {
  it("derives online state from the flag or the 60 s heartbeat window", () => {
    const now = Date.parse("2026-09-16T12:00:00Z");
    expect(isDeviceOnline({ online: false, last_seen_at: "2026-09-16T12:00:00Z" }, now)).toBe(false);
    expect(isDeviceOnline({ last_seen_at: "2026-09-16T11:59:30Z" }, now)).toBe(true);
    expect(isDeviceOnline({ last_seen_at: "2026-09-16T11:58:30Z" }, now)).toBe(false);
    expect(isDeviceOnline({ last_seen_at: null }, now)).toBe(false);
  });

  it("offers only the user's own active host devices shared with all their projects for new projects", () => {
    const list = [
      device({ id: "ok" }),
      device({ id: "other-owner", owner_id: "u2" }),
      device({ id: "selected", sharing_mode: "selected" }),
      device({ id: "disabled", status: "disabled" }),
      device({ id: "storage", roles: ["backup_storage"] }),
    ];
    expect(newProjectHosts(list, "u1").map((d) => d.id)).toEqual(["ok"]);
  });

  it("blocks removal while hosting databases unless the instance owner forces it", () => {
    expect(removalCheck({ hosted_sources_count: 0 }, false)).toEqual({ allowed: true, force: false, reason: null });
    expect(removalCheck({ hosted_sources_count: 2 }, false)).toMatchObject({ allowed: false, force: false });
    expect(removalCheck({ hosted_sources_count: 1 }, true)).toMatchObject({ allowed: true, force: true });
    expect(removalCheck({ hosted_sources_count: 1 }, true).reason).toMatch(/hosts 1 database\./);
  });

  it("builds usage bars from metrics", () => {
    const bars = usageBars({
      cpu_percent: 42.4,
      memory_used_bytes: 8 * 1024 ** 3,
      memory_total_bytes: 16 * 1024 ** 3,
      disk_free_bytes: 25 * 1024 ** 3,
      disk_total_bytes: 100 * 1024 ** 3,
    });
    expect(bars.map((b) => [b.key, Math.round(b.percent ?? -1)])).toEqual([
      ["cpu", 42],
      ["memory", 50],
      ["disk", 75],
    ]);
    expect(usageBars(null)).toEqual([]);
  });

  it("describes capabilities", () => {
    expect(capabilityNotes({ engines: { mariadb: true, mongodb: false }, avx: false })).toEqual([
      { ok: true, text: "MariaDB available" },
      { ok: false, text: "MongoDB not available on this PC (no AVX)" },
    ]);
    expect(capabilityNotes(null)).toEqual([]);
  });

  it("warns about URLs other PCs can't use", () => {
    expect(reachabilityWarning("http://localhost:8080")).toMatch(/localhost/);
    expect(reachabilityWarning("http://127.0.0.1:8080")).toMatch(/localhost/);
    expect(reachabilityWarning("http://192.168.1.20:8080")).toBeNull();
    expect(reachabilityWarning("http://my-pc.tail1234.ts.net")).toBeNull();
    expect(reachabilityWarning("http://deployer.example.com")).toMatch(/https/);
    expect(reachabilityWarning("https://deployer.example.com")).toBeNull();
  });
});
