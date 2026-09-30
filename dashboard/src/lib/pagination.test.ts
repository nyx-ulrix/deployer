import { describe, expect, it } from "vitest";
import { clampOffset } from "./pagination";

describe("clampOffset (A-175: no empty page after deleting the last row)", () => {
  it("steps back to the last page when the offset is past the end", () => {
    expect(clampOffset(50, 50, 50)).toBe(0);
    expect(clampOffset(100, 75, 25)).toBe(50);
    expect(clampOffset(50, 0, 50)).toBe(0);
  });

  it("keeps an offset that still has rows", () => {
    expect(clampOffset(0, 0, 50)).toBe(0);
    expect(clampOffset(50, 51, 50)).toBe(50);
  });
});
