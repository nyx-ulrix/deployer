import { describe, expect, it } from "vitest";
import { isLocalHostname, isLocalUrl, normalizeUrl } from "./url";

describe("isLocalUrl (A-168: one check for every page)", () => {
  it.each([
    "http://localhost:8080",
    "https://localhost",
    " http://127.0.0.1/ ",
    "http://[::1]:8080",
    "http://deployer.localhost",
    "HTTP://LOCALHOST",
  ])("%s is local", (url) => expect(isLocalUrl(url)).toBe(true));

  it.each(["http://localhost.example.com", "https://deployer.example.com", "http://192.168.1.5:8080", "not a url", ""])(
    "%s is not local",
    (url) => expect(isLocalUrl(url)).toBe(false),
  );

  it("accepts bare and bracketed hostnames", () => {
    expect(isLocalHostname("[::1]")).toBe(true);
    expect(isLocalHostname("::1")).toBe(true);
    expect(isLocalHostname("example.com")).toBe(false);
  });
});

describe("normalizeUrl", () => {
  it("trims whitespace and trailing slashes", () => {
    expect(normalizeUrl("  https://a.example.com//  ")).toBe("https://a.example.com");
    expect(normalizeUrl("https://a.example.com/path/")).toBe("https://a.example.com/path");
  });
});
