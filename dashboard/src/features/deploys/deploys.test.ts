import { describe, expect, it } from "vitest";
import type { App } from "../../api/types";
import {
  canRollback,
  databaseEnvNames,
  deploymentDuration,
  DEPLOYMENT_STATUS,
  draftErrors,
  draftToInput,
  draftToPatch,
  emptyDraft,
  isActive,
  parseEnv,
  reachableSources,
  rowsToEnv,
  shortSha,
  slugify,
} from "./deploys";

describe("slugify", () => {
  it("lowercases and replaces runs of other characters with one dash", () => {
    expect(slugify("My Shop  App!")).toBe("my-shop-app");
    expect(slugify("Hello_World.v2")).toBe("hello-world-v2");
  });
  it("strips leading/trailing dashes and caps at 63 chars", () => {
    expect(slugify("--shop--")).toBe("shop");
    expect(slugify("a".repeat(62) + "-b")).toBe("a".repeat(62));
    expect(slugify("x".repeat(80)).length).toBe(63);
  });
  it("is empty when nothing DNS-safe remains", () => {
    expect(slugify("!!!")).toBe("");
  });
});

describe("parseEnv", () => {
  it("handles comments, blank lines, export, CRLF and quotes", () => {
    const text = [
      "# comment",
      "",
      "export API_URL=https://example.com",
      'GREETING="hello world" # trailing',
      "SINGLE='a b'",
      "PLAIN=value # comment",
      'MULTI="a\\nb"',
      "bad line",
      "=novalue",
      "EMPTY=",
    ].join("\r\n");
    expect(parseEnv(text)).toEqual([
      { key: "API_URL", value: "https://example.com" },
      { key: "GREETING", value: "hello world" },
      { key: "SINGLE", value: "a b" },
      { key: "PLAIN", value: "value" },
      { key: "MULTI", value: "a\nb" },
      { key: "EMPTY", value: "" },
    ]);
  });
  it("keeps '=' inside values", () => {
    // No user:password@ in the URL: the repository's secret scanner would flag even a fake one.
    expect(parseEnv("DSN=postgres://db.example.test/app?sslmode=require&x=1")).toEqual([
      { key: "DSN", value: "postgres://db.example.test/app?sslmode=require&x=1" },
    ]);
  });
  it("rowsToEnv drops blank keys and lets later duplicates win", () => {
    expect(
      rowsToEnv([
        { key: " A ", value: "1" },
        { key: "", value: "x" },
        { key: "A", value: "2" },
      ]),
    ).toEqual({ A: "2" });
  });
});

describe("deployment status helpers", () => {
  it("maps every status to a label and tone", () => {
    expect(DEPLOYMENT_STATUS.live).toEqual({ label: "Live", tone: "success" });
    expect(DEPLOYMENT_STATUS.failed.tone).toBe("danger");
    expect(DEPLOYMENT_STATUS.building.tone).toBe("info");
  });
  it("isActive only for queued/building/deploying", () => {
    expect(["queued", "building", "deploying"].every(isActive)).toBe(true);
    expect(["live", "failed", "cancelled", "superseded", undefined].some(isActive)).toBe(false);
  });
  it("deploymentDuration uses finished_at, or now while active", () => {
    const started_at = "2026-01-01T00:00:00Z";
    expect(deploymentDuration({ status: "live", started_at, finished_at: "2026-01-01T00:01:30Z" })).toBe(90);
    expect(
      deploymentDuration({ status: "building", started_at, finished_at: null }, Date.parse("2026-01-01T00:00:10Z")),
    ).toBe(10);
    expect(deploymentDuration({ status: "queued", started_at: null, finished_at: null })).toBeNull();
    expect(deploymentDuration({ status: "cancelled", started_at, finished_at: null })).toBeNull();
  });
  it("canRollback needs a superseded deployment with an image", () => {
    expect(canRollback({ status: "superseded", image_tag: "deployer-app/x:y" })).toBe(true);
    expect(canRollback({ status: "live", image_tag: "deployer-app/x:y" })).toBe(false);
    expect(canRollback({ status: "superseded", image_tag: null })).toBe(false);
  });
  it("shortSha", () => {
    expect(shortSha("0123456789abcdef")).toBe("0123456");
    expect(shortSha(null)).toBe("—");
  });
});

describe("app draft", () => {
  it("validates required fields per preset", () => {
    const d = { ...emptyDraft(), name: "Shop", repo_url: "https://github.com/me/shop" };
    expect(draftErrors(d)).toEqual({});
    expect(draftErrors({ ...d, repo_url: "git@github.com:me/shop.git" }).repo_url).toBeTruthy();
    expect(draftErrors({ ...d, preset: "python" }).start_command).toBeTruthy();
    expect(draftErrors({ ...d, preset: "dockerfile", container_port: "70000" }).container_port).toBeTruthy();
    expect(draftErrors({ ...d, preset: "dockerfile", container_port: "8080" })).toEqual({});
  });
  it("only sends the fields of the chosen preset and the token when private", () => {
    const d = {
      ...emptyDraft(),
      name: " Shop ",
      repo_url: "https://github.com/me/shop",
      preset: "node" as const,
      start_command: "node server.js",
      output_dir: "dist",
      private_repo: true,
      repo_token: "ghp_x",
    };
    const body = draftToInput(d, [{ key: "A", value: "1" }]);
    expect(body).toMatchObject({
      name: "Shop",
      branch: "main",
      root_dir: ".",
      start_command: "node server.js",
      output_dir: null,
      container_port: null,
      env: { A: "1" },
      api_key_id: null,
      repo_token: "ghp_x",
    });
    expect(draftToInput({ ...d, private_repo: false }, []).repo_token).toBeUndefined();
  });
  it("patch clears the token when the private toggle is switched off", () => {
    const app = { has_repo_token: true } as App;
    const d = { ...emptyDraft(), name: "Shop", repo_url: "https://x", private_repo: false };
    const patch = draftToPatch(d, app);
    expect(patch.repo_token).toBeNull();
    expect("env" in patch).toBe(false);
    expect(draftToPatch({ ...d, private_repo: true }, app).repo_token).toBeUndefined();
  });
});

describe("database access", () => {
  it("names variables like the worker (upper-case, non-alphanumerics to _)", () => {
    expect(databaseEnvNames({ name: "shop-db", kind: "sql" })).toEqual([
      "DEPLOYER_DB_SHOP_DB_HOST",
      "DEPLOYER_DB_SHOP_DB_PORT",
      "DEPLOYER_DB_SHOP_DB_USER",
      "DEPLOYER_DB_SHOP_DB_PASSWORD",
      "DEPLOYER_DB_SHOP_DB_DATABASE",
      "DEPLOYER_DB_SHOP_DB_URL",
    ]);
    expect(databaseEnvNames({ name: "Docs Store", kind: "nosql" })).toEqual(["DEPLOYER_DB_DOCS_STORE_URL", "DEPLOYER_DB_DOCS_STORE_DATABASE"]);
  });
  it("only managed sources on the main server are reachable", () => {
    const rows = [
      { id: "a", mode: "managed" as const, device_id: null },
      { id: "b", mode: "managed" as const, device_id: "dev" },
      { id: "c", mode: "external" as const, device_id: null },
    ];
    expect(reachableSources(rows).map((r) => r.id)).toEqual(["a"]);
  });
  it("draft carries the flag", () => {
    const d = { ...emptyDraft({ database_access: true } as App), name: "Shop", repo_url: "https://x" };
    expect(draftToInput(d, []).database_access).toBe(true);
    expect(draftToPatch({ ...d, database_access: false }, { has_repo_token: false } as App).database_access).toBe(false);
  });
});
