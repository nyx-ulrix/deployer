import { describe, expect, it } from "vitest";
import { oauthErrorMessage } from "./oauthErrors";

describe("oauthErrorMessage", () => {
  it("tells the user to start from the public URL instead of blaming tampering", () => {
    const text = oauthErrorMessage("oauth_state_invalid", "https://deploy.example.com");
    expect(text).toContain("Open Deployer at https://deploy.example.com");
    expect(text).not.toMatch(/tamper/i);
  });

  it("falls back to this page's address when the public URL is unknown", () => {
    expect(oauthErrorMessage("oauth_state_invalid")).toContain(window.location.origin);
  });

  it("explains not_initialized", () => {
    expect(oauthErrorMessage("not_initialized")).toMatch(/set up/);
  });

  it("keeps the generic fallback and ignores empty codes", () => {
    expect(oauthErrorMessage("weird_code")).toBe("Sign-in failed (weird_code).");
    expect(oauthErrorMessage(null)).toBeNull();
  });
});
