import { describe, expect, it } from "vitest";
import type { Field, SchemaDiff, SchemaDiffEntity } from "../../api/types";
import {
  fieldAttributeChanges,
  fieldSummary,
  isDataOnlyChange,
  rowCountDelta,
  sortDiffEntities,
  summarizeDiff,
} from "./diff";

const field = (over: Partial<Field> = {}): Field => ({
  name: "user_id",
  data_type: "int(11)",
  nullable: false,
  default: null,
  primary_key: false,
  unique: false,
  indexed: false,
  foreign_key: null,
  occurrence: null,
  ...over,
});

const entity = (over: Partial<SchemaDiffEntity>): SchemaDiffEntity => ({
  name: "users",
  change: "changed",
  fields: [],
  indexes: [],
  validator_changed: false,
  row_count: { before: null, after: null },
  ...over,
});

describe("fieldAttributeChanges", () => {
  it("lists type, nullability, key and default changes with before/after", () => {
    const before = field();
    const after = field({
      data_type: "bigint(20) unsigned",
      nullable: true,
      indexed: true,
      foreign_key: { entity: "users", field: "id" },
      default: "0",
    });
    expect(fieldAttributeChanges(before, after)).toEqual([
      { attribute: "Type", before: "int(11)", after: "bigint(20) unsigned" },
      { attribute: "Nullable", before: "no", after: "yes" },
      { attribute: "Indexed", before: "no", after: "yes" },
      { attribute: "Foreign key", before: "none", after: "users.id" },
      { attribute: "Default", before: "none", after: "0" },
    ]);
  });

  it("returns nothing for added/removed fields or identical fields", () => {
    expect(fieldAttributeChanges(null, field())).toEqual([]);
    expect(fieldAttributeChanges(field(), null)).toEqual([]);
    expect(fieldAttributeChanges(field(), field())).toEqual([]);
  });
});

describe("fieldSummary", () => {
  it("describes a field compactly", () => {
    expect(fieldSummary(field({ primary_key: true, unique: true }))).toBe("int(11) · NOT NULL · PK");
    expect(fieldSummary(field({ nullable: true, foreign_key: { entity: "users", field: "id" }, indexed: true }))).toBe(
      "int(11) · NULL · IDX · FK → users.id",
    );
  });
});

describe("rowCountDelta", () => {
  it("formats increases, decreases and unknowns", () => {
    expect(rowCountDelta({ before: 1000, after: 1200 })).toMatchObject({ tone: "success" });
    expect(rowCountDelta({ before: 1000, after: 1200 })?.text).toMatch(/\+200/);
    expect(rowCountDelta({ before: 50, after: 20 })).toMatchObject({ tone: "danger" });
    expect(rowCountDelta({ before: 5, after: 5 })?.text).toMatch(/no change/);
    expect(rowCountDelta({ before: null, after: null })).toBeNull();
    expect(rowCountDelta({ before: null, after: 3 })?.tone).toBe("neutral");
  });
});

describe("summarizeDiff / sorting", () => {
  const diff: SchemaDiff = {
    from: { backup_id: "a", at: "2026-09-15T10:00:00Z" },
    to: { backup_id: null, at: "2026-09-16T10:00:00Z" },
    entities: [
      entity({ name: "zeta", change: "added", fields: [{ name: "id", change: "added", before: null, after: field() }] }),
      entity({
        name: "orders",
        change: "changed",
        fields: [
          { name: "total", change: "changed", before: field(), after: field({ data_type: "decimal(10,2)" }) },
          { name: "note", change: "removed", before: field(), after: null },
        ],
        indexes: [{ name: "idx_total", change: "added" }],
        row_count: { before: 10, after: 12 },
      }),
      entity({ name: "legacy", change: "removed" }),
      entity({ name: "events", change: "changed", validator_changed: true }),
      entity({ name: "logs", change: "changed", row_count: { before: 1, after: 9 } }),
    ],
  };

  it("counts entity/field/index/validator/row changes", () => {
    const s = summarizeDiff(diff);
    expect(s.entities).toEqual({ added: 1, removed: 1, changed: 3 });
    expect(s.fields).toEqual({ added: 1, removed: 1, changed: 1 });
    expect(s.indexes).toBe(1);
    expect(s.validators).toBe(1);
    expect(s.rowChanges).toBe(2);
    expect(s.empty).toBe(false);
    expect(summarizeDiff({ ...diff, entities: [] }).empty).toBe(true);
  });

  it("orders removed, changed, added and detects data-only changes", () => {
    expect(sortDiffEntities(diff.entities).map((e) => e.name)).toEqual(["legacy", "events", "logs", "orders", "zeta"]);
    expect(isDataOnlyChange(diff.entities[4])).toBe(true);
    expect(isDataOnlyChange(diff.entities[1])).toBe(false);
    expect(isDataOnlyChange(diff.entities[3])).toBe(false);
  });
});
