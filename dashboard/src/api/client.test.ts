import { describe, expect, it, vi } from "vitest";
import { ApiError, buildQuery, createApiClient, filenameFromDisposition } from "./client";
import type { AuthResponse } from "./types";

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function authResponse(token: string): AuthResponse {
  return {
    access_token: token,
    token_type: "bearer",
    expires_in: 900,
    user: {
      id: "u1",
      email: "owner@example.com",
      display_name: "Owner",
      avatar_url: null,
      is_instance_owner: true,
      has_password: true,
      created_at: "2026-01-01T00:00:00Z",
      identities: [],
    },
  };
}

type Call = { url: string; init?: RequestInit };

function authHeader(call: Call): string | null {
  return new Headers(call.init?.headers).get("Authorization");
}

describe("api client refresh logic", () => {
  it("refreshes once on 401 and retries the original request with the new token", async () => {
    const calls: Call[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === "/v1/auth/refresh") return json(200, authResponse("fresh"));
      const auth = new Headers(init?.headers).get("Authorization");
      if (auth === "Bearer fresh") return json(200, [{ id: "p1" }]);
      return json(401, { error: { code: "unauthorized", message: "Token expired" } });
    });
    const c = createApiClient({ fetch: fetchMock });
    c.setSession(authResponse("stale"));

    const result = await c.get<{ id: string }[]>("/projects");

    expect(result).toEqual([{ id: "p1" }]);
    expect(calls.map((x) => x.url)).toEqual(["/v1/projects", "/v1/auth/refresh", "/v1/projects"]);
    expect(authHeader(calls[0])).toBe("Bearer stale");
    expect(authHeader(calls[2])).toBe("Bearer fresh");
    expect(calls[1].init?.credentials).toBe("include");
    expect(c.getAccessToken()).toBe("fresh");
  });

  it("uses a single in-flight refresh for concurrent 401s", async () => {
    let refreshCalls = 0;
    let releaseRefresh: () => void = () => {};
    const refreshGate = new Promise<void>((r) => (releaseRefresh = r));
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/v1/auth/refresh") {
        refreshCalls += 1;
        await refreshGate;
        return json(200, authResponse("fresh"));
      }
      const auth = new Headers(init?.headers).get("Authorization");
      if (auth === "Bearer fresh") return json(200, { ok: true, url });
      return json(401, { error: { code: "unauthorized", message: "expired" } });
    });
    const c = createApiClient({ fetch: fetchMock });
    c.setSession(authResponse("stale"));

    const pending = Promise.all([c.get("/a"), c.get("/b"), c.get("/c")]);
    await new Promise((r) => setTimeout(r, 0));
    releaseRefresh();
    const results = await pending;

    expect(refreshCalls).toBe(1);
    expect(results).toHaveLength(3);
  });

  it("throws a typed ApiError and clears the session when refresh fails", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/v1/auth/refresh") return json(401, { error: { code: "unauthorized", message: "No session" } });
      return json(401, { error: { code: "unauthorized", message: "Not signed in" } });
    });
    const c = createApiClient({ fetch: fetchMock });
    const seen: (string | null)[] = [];
    c.subscribe((u) => seen.push(u?.id ?? null));
    c.setSession(authResponse("stale"));

    const err = await c.get("/auth/me").catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    expect((err as ApiError).code).toBe("unauthorized");
    expect((err as ApiError).message).toBe("Not signed in");
    expect(c.getAccessToken()).toBeNull();
    expect(seen).toEqual(["u1", null]);
    // original + refresh, no second retry
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not refresh for unauthenticated requests", async () => {
    const fetchMock = vi.fn(async () =>
      json(401, { error: { code: "invalid_credentials", message: "Wrong email or password" } }),
    );
    const c = createApiClient({ fetch: fetchMock });
    const err = await c.post("/auth/login", { email: "a", password: "b" }, { auth: false }).catch((e: unknown) => e);
    expect((err as ApiError).code).toBe("invalid_credentials");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("parses error envelopes with details", async () => {
    const fetchMock = vi.fn(async () =>
      json(422, { error: { code: "validation_error", message: "Invalid", details: { field: "name" } } }),
    );
    const c = createApiClient({ fetch: fetchMock });
    const err = (await c.post("/projects", {}).catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(422);
    expect(err.details).toEqual({ field: "name" });
  });

  it("downloads blobs with the filename from Content-Disposition", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response("hello", {
          status: 200,
          headers: { "Content-Disposition": 'attachment; filename="deployer-instance-20260916-1000.json"' },
        }),
    );
    const c = createApiClient({ fetch: fetchMock });
    const res = await c.download("POST", "/instance/export", "fallback.json", { body: { passphrase: "x" } });
    expect(res.filename).toBe("deployer-instance-20260916-1000.json");
    expect(await res.blob.text()).toBe("hello");
  });
});

describe("helpers", () => {
  it("parses Content-Disposition variants", () => {
    expect(filenameFromDisposition(null, "f.txt")).toBe("f.txt");
    expect(filenameFromDisposition("attachment; filename=schema.sql", "f")).toBe("schema.sql");
    expect(filenameFromDisposition("attachment; filename*=UTF-8''sch%C3%A9ma.zip", "f")).toBe("schéma.zip");
  });

  it("builds query strings skipping empty values", () => {
    expect(buildQuery({ a: 1, b: "", c: undefined, d: false, e: null })).toBe("?a=1&d=false");
    expect(buildQuery({})).toBe("");
  });
});
