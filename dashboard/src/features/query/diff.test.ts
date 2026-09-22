import { describe, expect, it } from "vitest";
import { DIFF_MAX_LINES, diffStats, lineDiff } from "./diff";

const render = (a: string, b: string) => lineDiff(a, b)?.map((l) => `${{ same: " ", add: "+", del: "-" }[l.kind]}${l.text}`);

describe("lineDiff", () => {
  it("marks identical text as unchanged", () => {
    expect(render("a\nb", "a\nb")).toEqual([" a", " b"]);
  });

  it("finds additions, deletions and edits", () => {
    expect(render("a\nb\nc", "a\nb\nx\nc")).toEqual([" a", " b", "+x", " c"]);
    expect(render("a\nb\nc", "a\nc")).toEqual([" a", "-b", " c"]);
    expect(render("SELECT 1;\n-- cell --\nSELECT 2;", "SELECT 1;\n-- cell --\nSELECT 3;")).toEqual([
      " SELECT 1;",
      " -- cell --",
      "-SELECT 2;",
      "+SELECT 3;",
    ]);
  });

  it("handles changes at both ends and in the middle", () => {
    expect(render("x\na\nb\ny", "a\nb")).toEqual(["-x", " a", " b", "-y"]);
    expect(render("a\nb", "x\na\nb\ny")).toEqual(["+x", " a", " b", "+y"]);
  });

  it("treats empty inputs as zero lines", () => {
    expect(lineDiff("", "")).toEqual([]);
    expect(render("", "a")).toEqual(["+a"]);
    expect(render("a", "")).toEqual(["-a"]);
  });

  it("gives up above the cap", () => {
    const big = Array.from({ length: DIFF_MAX_LINES + 1 }, (_, i) => `line ${i}`).join("\n");
    expect(lineDiff(big, "a")).toBeNull();
    expect(lineDiff("a", big)).toBeNull();
    expect(lineDiff(big.split("\n").slice(1).join("\n"), "a")).not.toBeNull();
  });

  it("counts adds and dels", () => {
    expect(diffStats(lineDiff("a\nb", "a\nc\nd") ?? [])).toEqual({ add: 2, del: 1 });
  });
});
