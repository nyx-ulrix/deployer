import { describe, expect, it } from "vitest";
import { describeEnds, edgeEnds, MARKER_NOTATION, markerPath } from "./crowsfoot";

describe("crow's-foot cardinality mapping", () => {
  it("many_to_one with a NOT NULL foreign key: zero-or-many → exactly one", () => {
    expect(edgeEnds("many_to_one", { fromNullable: false })).toEqual({ source: "zero_or_many", target: "one" });
  });

  it("many_to_one with a nullable foreign key: zero-or-many → zero-or-one", () => {
    expect(edgeEnds("many_to_one", { fromNullable: true })).toEqual({
      source: "zero_or_many",
      target: "zero_or_one",
    });
  });

  it("one_to_one: optional on the referencing side, required on the referenced side", () => {
    expect(edgeEnds("one_to_one", { fromNullable: false })).toEqual({ source: "zero_or_one", target: "one" });
    expect(edgeEnds("one_to_one", { fromNullable: true })).toEqual({ source: "zero_or_one", target: "zero_or_one" });
  });

  it("one_to_many mirrors many_to_one using the `to` field's nullability", () => {
    expect(edgeEnds("one_to_many", { fromNullable: false, toNullable: false })).toEqual({
      source: "one",
      target: "zero_or_many",
    });
    expect(edgeEnds("one_to_many", { fromNullable: false, toNullable: true })).toEqual({
      source: "zero_or_one",
      target: "zero_or_many",
    });
  });

  it("many_to_many is zero-or-many on both ends", () => {
    expect(edgeEnds("many_to_many", { fromNullable: false })).toEqual({
      source: "zero_or_many",
      target: "zero_or_many",
    });
  });

  it("uses the notation from docs/CONVENTIONS.md", () => {
    expect(MARKER_NOTATION).toEqual({ one: "|│", zero_or_one: "o│", one_or_many: "│<", zero_or_many: "o<" });
  });

  it("describes ends in plain language", () => {
    expect(describeEnds("orders", "users", edgeEnds("many_to_one", { fromNullable: false }))).toBe(
      "orders (zero or many) → users (exactly one)",
    );
  });

  it("draws circles only for optional ends", () => {
    const p = { x: 0, y: 0 };
    const d = { x: 1, y: 0 };
    expect(markerPath("one", p, d).circle).toBeNull();
    expect(markerPath("one_or_many", p, d).circle).toBeNull();
    expect(markerPath("zero_or_one", p, d).circle).toEqual({ x: 19, y: 0 });
    expect(markerPath("zero_or_many", p, d).circle).toEqual({ x: 19, y: 0 });
    // crow's foot prongs spread at the entity border
    expect(markerPath("zero_or_many", p, d).lines).toContain("M14,0L0,-7");
  });
});
