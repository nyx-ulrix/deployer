import { describe, expect, it } from "vitest";
import { callbackUrls, deriveSigninSteps, githubPrefillUrl, oauthValueError } from "./signinSteps";

describe("callback URLs", () => {
  it("adds the localhost callback only when the public URL is elsewhere", () => {
    const local = "http://localhost:8080";
    expect(callbackUrls("google", "http://localhost:8080/", local)).toEqual(["http://localhost:8080/v1/auth/oauth/google/callback"]);
    expect(callbackUrls("github", "https://deployer.example.com", local)).toEqual([
      "https://deployer.example.com/v1/auth/oauth/github/callback",
      "http://localhost:8080/v1/auth/oauth/github/callback",
    ]);
  });

  it("registers the PC's real port, not a hard-coded 8080 (A-081)", () => {
    expect(callbackUrls("github", "https://deployer.example.com", "http://localhost:9090")[1]).toBe(
      "http://localhost:9090/v1/auth/oauth/github/callback",
    );
  });
});

describe("githubPrefillUrl", () => {
  it("encodes every value into GitHub's form field names", () => {
    const raw = githubPrefillUrl("https://deployer.example.com/");
    expect(raw).toContain("https://github.com/settings/applications/new?");
    expect(raw).toContain("oauth_application%5Burl%5D=https%3A%2F%2Fdeployer.example.com&");
    const url = new URL(raw);
    expect(url.searchParams.get("oauth_application[name]")).toBe("Deployer");
    expect(url.searchParams.get("oauth_application[url]")).toBe("https://deployer.example.com");
    expect(url.searchParams.get("oauth_application[callback_url]")).toBe(
      "https://deployer.example.com/v1/auth/oauth/github/callback",
    );
  });
});

describe("deriveSigninSteps", () => {
  const none = { configured: false, clientIdSaved: false, acknowledged: [] };
  it("walks through acknowledged console steps to the paste step", () => {
    expect(deriveSigninSteps(3, none)).toEqual(["current", "todo", "todo"]);
    expect(deriveSigninSteps(3, { ...none, acknowledged: [0] })).toEqual(["done", "current", "todo"]);
    expect(deriveSigninSteps(3, { ...none, acknowledged: [0, 1, 2] })).toEqual(["done", "done", "current"]);
  });

  it("treats a saved Client ID as the console work being done, and configured as all done", () => {
    expect(deriveSigninSteps(6, { ...none, clientIdSaved: true })).toEqual(["done", "done", "done", "done", "done", "current"]);
    expect(deriveSigninSteps(6, { ...none, configured: true }).every((s) => s === "done")).toBe(true);
  });
});

describe("oauthValueError", () => {
  it("accepts well-formed values and empty input", () => {
    expect(oauthValueError("google", "id", " 1234-abc.apps.googleusercontent.com ")).toBeNull();
    expect(oauthValueError("google", "secret", "GOCSPX-abc")).toBeNull();
    expect(oauthValueError("github", "id", "Ov23liAbc123")).toBeNull();
    expect(oauthValueError("github", "secret", "a".repeat(40))).toBeNull();
    expect(oauthValueError("github", "id", "")).toBeNull();
  });

  it("rejects pasted blocks, labels and swapped fields like the API", () => {
    expect(oauthValueError("google", "id", "Client ID: 1234-abc.apps.googleusercontent.com")).toMatch(/whole block/);
    expect(oauthValueError("github", "secret", "abc def")).toMatch(/whole block/);
    expect(oauthValueError("google", "secret", "1234-abc.apps.googleusercontent.com")).toMatch(/looks like the Client ID/);
    expect(oauthValueError("github", "secret", "Ov23liAbc123")).toMatch(/looks like the Client ID/);
    expect(oauthValueError("google", "id", "GOCSPX-abc")).toMatch(/looks like the Client secret/);
    expect(oauthValueError("github", "id", "nope")).toMatch(/not a GitHub Client ID/);
  });
});
