import type { LinkCardinality, RelationshipCardinality } from "../../api/types";

/**
 * A crow's-foot line end. The marker drawn next to an entity says how many rows/documents of THAT entity
 * relate to a single row/document on the other end.
 *
 * - `one`          `|│`  exactly one
 * - `zero_or_one`  `o│`  zero or one
 * - `one_or_many`  `│<`  one or many
 * - `zero_or_many` `o<`  zero or many
 */
export type EndMarker = "one" | "zero_or_one" | "one_or_many" | "zero_or_many";

export type Cardinality = RelationshipCardinality | LinkCardinality;

export type EdgeEnds = {
  /** Marker drawn at the `from` (referencing) entity. */
  source: EndMarker;
  /** Marker drawn at the `to` (referenced) entity. */
  target: EndMarker;
};

export const MARKER_NOTATION: Record<EndMarker, string> = {
  one: "|│",
  zero_or_one: "o│",
  one_or_many: "│<",
  zero_or_many: "o<",
};

export const MARKER_LABEL: Record<EndMarker, string> = {
  one: "exactly one",
  zero_or_one: "zero or one",
  one_or_many: "one or many",
  zero_or_many: "zero or many",
};

/**
 * Derive both line ends from a relationship's cardinality and the nullability of the linked fields.
 *
 * `from` is the referencing side (the column holding the foreign key / reference). If that column is
 * nullable (or a Mongo field missing from some documents), a referencing row may point at nothing, so the
 * referenced end becomes "zero or one" instead of "exactly one". The "many" side is always optional:
 * a referenced row may have no referencing rows at all.
 */
export function edgeEnds(
  cardinality: Cardinality,
  { fromNullable, toNullable = false }: { fromNullable: boolean; toNullable?: boolean },
): EdgeEnds {
  const oneFor = (nullable: boolean): EndMarker => (nullable ? "zero_or_one" : "one");
  switch (cardinality) {
    case "many_to_one":
      return { source: "zero_or_many", target: oneFor(fromNullable) };
    case "one_to_many":
      // `from` is the "one" side; each `to` row references exactly one `from` row unless its field is nullable.
      return { source: oneFor(toNullable), target: "zero_or_many" };
    case "one_to_one":
      return { source: "zero_or_one", target: oneFor(fromNullable) };
    case "many_to_many":
      return { source: "zero_or_many", target: "zero_or_many" };
  }
}

/** Human-readable description, e.g. "orders (zero or many) → users (exactly one)". */
export function describeEnds(fromName: string, toName: string, ends: EdgeEnds): string {
  return `${fromName} (${MARKER_LABEL[ends.source]}) → ${toName} (${MARKER_LABEL[ends.target]})`;
}

type Vec = { x: number; y: number };

/**
 * SVG path data for a crow's-foot marker at point `p` (on the entity border), where `dir` is the unit
 * vector pointing from the entity outward along the edge.
 */
export function markerPath(kind: EndMarker, p: Vec, dir: Vec): { lines: string; circle: Vec | null } {
  const perp = { x: -dir.y, y: dir.x };
  const at = (d: number, s = 0): Vec => ({ x: p.x + dir.x * d + perp.x * s, y: p.y + dir.y * d + perp.y * s });
  const seg = (a: Vec, b: Vec) => `M${a.x},${a.y}L${b.x},${b.y}`;
  const bar = (d: number) => seg(at(d, -6), at(d, 6));
  const HALF = 7;

  switch (kind) {
    case "one":
      return { lines: bar(8) + bar(14), circle: null };
    case "zero_or_one":
      return { lines: bar(8), circle: at(19) };
    case "one_or_many":
      return {
        lines: seg(at(14), at(0, -HALF)) + seg(at(14), at(0, HALF)) + seg(at(14), at(0)) + bar(18),
        circle: null,
      };
    case "zero_or_many":
      return {
        lines: seg(at(14), at(0, -HALF)) + seg(at(14), at(0, HALF)) + seg(at(14), at(0)),
        circle: at(19),
      };
  }
}
