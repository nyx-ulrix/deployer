import { describe, expect, it } from "vitest";
import { childPath, cleanRtdbPath, isBranch, isRtdbKey, parentPath, preview } from "./rtdb";

describe("Realtime Database paths (docs/CLOUD.md C2-4)", () => {
  it("accepts Firebase keys and paths", () => {
    expect(isRtdbKey("-NxPush01")).toBe(true);
    for (const bad of ["", "a.b", "a$", "a#", "a[0]", "a/b"]) expect(isRtdbKey(bad)).toBe(false);
    expect(cleanRtdbPath(" /users/ann/ ")).toBe("users/ann");
    expect(cleanRtdbPath("/")).toBe("");
    expect(cleanRtdbPath("users//ann")).toBeNull();
    expect(cleanRtdbPath("users/a.b")).toBeNull();
  });
  it("walks the tree", () => {
    expect(childPath("", "users")).toBe("users");
    expect(childPath("users", "ann")).toBe("users/ann");
    expect(parentPath("users/ann")).toBe("users");
    expect(parentPath("users")).toBe("");
  });
  it("tells branches from plain values in a shallow read", () => {
    expect(isBranch(true)).toBe(true);
    expect(isBranch({ a: 1 })).toBe(true);
    expect(isBranch("x")).toBe(false);
    expect(isBranch(false)).toBe(false);
    expect(preview("x".repeat(200)).length).toBe(118);
  });
});
