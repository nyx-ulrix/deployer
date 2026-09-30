import { describe, expect, it } from "vitest";
import { safeRedirect } from "./safeRedirect";

describe("safeRedirect (A-170: open-redirect guard)", () => {
  it.each([null, undefined, "", "https://x", "//x", "/\\x", "/x\\y", "javascript:x", "/\t/x", "/\n/x", "x/y"])(
    "%j falls back",
    (value) => expect(safeRedirect(value, "/home")).toBe("/home"),
  );

  it("keeps same-origin paths with query and hash", () => {
    expect(safeRedirect("/projects/1?tab=a")).toBe("/projects/1?tab=a");
    expect(safeRedirect("/settings#keys")).toBe("/settings#keys");
  });

  it("defaults the fallback to /", () => expect(safeRedirect("//evil.com")).toBe("/"));
});
