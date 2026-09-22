import { describe, expect, it } from "vitest";
import type { RemoteAccess } from "../../api/types";
import { connectorHint, deriveSteps, sameUrl, tunnelHealthy } from "./steps";

const off: RemoteAccess = {
  mode: "off",
  public_url: "http://localhost:8080",
  connector: { running: false, started_at: null, last_error: null },
  cloudflare: { linked: false, token_valid: null, account: null, tunnel: null, domains: [], zones: [] },
  quick: { url: null },
};

const linked: RemoteAccess = {
  ...off,
  mode: "cloudflare",
  connector: { running: true, started_at: "2026-01-01T00:00:00Z", last_error: null },
  cloudflare: {
    linked: true,
    token_valid: true,
    account: { id: "a1", name: "Acme" },
    tunnel: { id: "t1", name: "deployer-12345678", status: "healthy", connections: 4 },
    domains: [],
    zones: [{ id: "z1", name: "example.com", account_id: "a1", status: "active" }],
  },
};

const domain = {
  id: "d1",
  hostname: "deployer.example.com",
  zone_id: "z1",
  zone_name: "example.com",
  target_type: "dashboard" as const,
  project_id: null,
  status: "active" as const,
  status_message: null,
  url: "https://deployer.example.com",
};

const none = { accountAcknowledged: false, verifiedOk: false, replacing: false };

describe("deriveSteps", () => {
  it("starts at step 1 and advances on acknowledge / verify", () => {
    expect(deriveSteps(off, none)).toEqual(["current", "todo", "todo", "todo", "todo", "todo"]);
    expect(deriveSteps(off, { ...none, accountAcknowledged: true })[1]).toBe("current");
    expect(deriveSteps(off, { ...none, verifiedOk: true })).toEqual(["done", "done", "current", "todo", "todo", "todo"]);
  });

  it("linked without hostnames sits at step 4", () => {
    expect(deriveSteps(linked, none)).toEqual(["done", "done", "done", "current", "todo", "todo"]);
  });

  it("replacing the token reopens step 2 but keeps the account step done", () => {
    expect(deriveSteps(linked, { ...none, replacing: true })).toEqual(["done", "current", "todo", "todo", "todo", "todo"]);
  });

  it("waits for the tunnel, then the public URL", () => {
    const withDomain = { ...linked, cloudflare: { ...linked.cloudflare, domains: [domain] } };
    expect(deriveSteps(withDomain, none)).toEqual(["done", "done", "done", "done", "done", "current"]);
    const down = { ...withDomain, connector: { ...withDomain.connector, running: false } };
    expect(deriveSteps(down, none)[4]).toBe("current");
    const live = { ...withDomain, public_url: "https://deployer.example.com/" };
    expect(deriveSteps(live, none).every((s) => s === "done")).toBe(true);
  });
});

describe("tunnel health and hints", () => {
  it("is healthy with a healthy status or any connection", () => {
    expect(tunnelHealthy(linked)).toBe(true);
    const zero = { ...linked, cloudflare: { ...linked.cloudflare, tunnel: { ...linked.cloudflare.tunnel!, status: "down", connections: 0 } } };
    expect(tunnelHealthy(zero)).toBe(false);
    expect(connectorHint(zero)?.body).toMatch(/7844/);
  });

  it("names the container, token and volume problems", () => {
    expect(connectorHint({ ...linked, connector: { running: false, started_at: null, last_error: null } })?.body).toMatch(/docker compose up/);
    expect(connectorHint({ ...linked, connector: { running: false, started_at: null, last_error: "cloudflared exited with code 1: Unauthorized" } })?.title).toMatch(/token/);
    expect(connectorHint({ ...linked, connector: { running: false, started_at: null, last_error: "Could not write /tunnel/desired.json" } })?.body).toMatch(/chown/);
    expect(connectorHint({ ...linked, mode: "quick" })?.title).toMatch(/quick tunnel/);
    expect(connectorHint(linked)).toBeNull();
  });

  it("compares URLs ignoring trailing slashes and case", () => {
    expect(sameUrl("https://A.example.com/", "https://a.example.com")).toBe(true);
    expect(sameUrl("https://a.example.com", "https://b.example.com")).toBe(false);
  });
});
