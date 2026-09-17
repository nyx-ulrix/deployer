import { describe, expect, it } from "vitest";
import { buildHostname, hostnameInZone, normalizeSubdomain, previewUrl, validateSubdomain } from "./hostname";

describe("hostname helpers", () => {
  it("normalizes pasted input", () => {
    expect(normalizeSubdomain("  Deployer ", "example.com")).toBe("deployer");
    expect(normalizeSubdomain("https://deployer.example.com/", "example.com")).toBe("deployer");
    expect(normalizeSubdomain("example.com", "example.com")).toBe("");
    expect(normalizeSubdomain("a.b.example.com.", "example.com")).toBe("a.b");
  });

  it("validates subdomain labels", () => {
    expect(validateSubdomain("deployer", "example.com")).toBeNull();
    expect(validateSubdomain("my-app.dev", "example.com")).toBeNull();
    expect(validateSubdomain("", "example.com")).toBeNull(); // zone apex
    expect(validateSubdomain("-bad", "example.com")).toMatch(/letters/);
    expect(validateSubdomain("bad_name", "example.com")).toMatch(/letters/);
    expect(validateSubdomain("a..b", "example.com")).toMatch(/empty/);
    expect(validateSubdomain("*", "example.com")).toMatch(/Wildcard/);
    expect(validateSubdomain("x".repeat(64), "example.com")).toMatch(/63/);
    expect(validateSubdomain("deployer", "")).toMatch(/domain/);
  });

  it("previews the full URL only when valid", () => {
    expect(previewUrl("deployer", "example.com")).toBe("https://deployer.example.com");
    expect(previewUrl("", "example.com")).toBe("https://example.com");
    expect(previewUrl("bad name", "example.com")).toBeNull();
    expect(buildHostname("a", "b.io")).toBe("a.b.io");
    expect(hostnameInZone("Deployer.Example.com", "example.com")).toBe(true);
    expect(hostnameInZone("notexample.com", "example.com")).toBe(false);
  });
});
