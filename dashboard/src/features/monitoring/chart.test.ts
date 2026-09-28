import { describe, expect, it } from "vitest";
import { linePath } from "./chart";

describe("linePath", () => {
  it("scales to the box and starts a new segment after a gap", () => {
    expect(linePath([0, 50, null, 100], 30, 10, 100)).toBe("M0 10L10 5M30 0");
  });
  it("defaults max to the largest value and clamps above it", () => {
    expect(linePath([2, 4], 10, 10)).toBe("M0 5L10 0");
    expect(linePath([200], 10, 10, 100)).toBe("M0 0");
    expect(linePath([null, null], 10, 10)).toBe("");
  });
});
