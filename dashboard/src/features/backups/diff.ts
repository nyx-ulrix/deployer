import type { DiffChange, Field, SchemaDiff, SchemaDiffEntity } from "../../api/types";
import { formatNumber } from "../../lib/format";

export type AttributeChange = { attribute: string; before: string; after: string };

function fkText(field: Field): string {
  return field.foreign_key ? `${field.foreign_key.entity}.${field.foreign_key.field}` : "none";
}

function yesNo(v: boolean): string {
  return v ? "yes" : "no";
}

/** Attribute-level differences between two versions of a field (type, nullability, keys, default). */
export function fieldAttributeChanges(before: Field | null, after: Field | null): AttributeChange[] {
  if (!before || !after) return [];
  const changes: AttributeChange[] = [];
  const push = (attribute: string, a: string, b: string) => {
    if (a !== b) changes.push({ attribute, before: a, after: b });
  };
  push("Type", before.data_type, after.data_type);
  push("Nullable", yesNo(before.nullable), yesNo(after.nullable));
  push("Primary key", yesNo(before.primary_key), yesNo(after.primary_key));
  push("Unique", yesNo(before.unique), yesNo(after.unique));
  push("Indexed", yesNo(before.indexed), yesNo(after.indexed));
  push("Foreign key", fkText(before), fkText(after));
  push("Default", before.default ?? "none", after.default ?? "none");
  return changes;
}

/** Compact one-line description of a field, e.g. "bigint(20) · NOT NULL · PK · FK → users.id". */
export function fieldSummary(field: Field): string {
  const parts = [field.data_type];
  parts.push(field.nullable ? "NULL" : "NOT NULL");
  if (field.primary_key) parts.push("PK");
  if (field.unique && !field.primary_key) parts.push("UQ");
  if (field.indexed && !field.unique && !field.primary_key) parts.push("IDX");
  if (field.foreign_key) parts.push(`FK → ${field.foreign_key.entity}.${field.foreign_key.field}`);
  if (field.default !== null) parts.push(`default ${field.default}`);
  return parts.join(" · ");
}

export type RowDelta = { text: string; tone: "neutral" | "success" | "danger" };

/** "1,200 → 1,350 (+150)". */
export function rowCountDelta(rc: SchemaDiffEntity["row_count"]): RowDelta | null {
  const { before, after } = rc;
  if (before === null && after === null) return null;
  if (before === null) return { text: `${formatNumber(after)} rows`, tone: "neutral" };
  if (after === null) return { text: `${formatNumber(before)} rows before`, tone: "neutral" };
  const delta = after - before;
  if (delta === 0) return { text: `${formatNumber(after)} rows (no change)`, tone: "neutral" };
  const sign = delta > 0 ? "+" : "−";
  return {
    text: `${formatNumber(before)} → ${formatNumber(after)} (${sign}${formatNumber(Math.abs(delta))})`,
    tone: delta > 0 ? "success" : "danger",
  };
}

export type DiffSummary = {
  entities: Record<DiffChange, number>;
  fields: Record<DiffChange, number>;
  indexes: number;
  validators: number;
  rowChanges: number;
  empty: boolean;
};

export function summarizeDiff(diff: SchemaDiff): DiffSummary {
  const entities: Record<DiffChange, number> = { added: 0, removed: 0, changed: 0 };
  const fields: Record<DiffChange, number> = { added: 0, removed: 0, changed: 0 };
  let indexes = 0;
  let validators = 0;
  let rowChanges = 0;
  for (const e of diff.entities) {
    entities[e.change] += 1;
    for (const f of e.fields) fields[f.change] += 1;
    indexes += e.indexes.length;
    if (e.validator_changed) validators += 1;
    if (e.row_count.before !== e.row_count.after) rowChanges += 1;
  }
  const empty = diff.entities.length === 0;
  return { entities, fields, indexes, validators, rowChanges, empty };
}

const CHANGE_ORDER: Record<DiffChange, number> = { removed: 0, changed: 1, added: 2 };

/** Entities ordered removed → changed → added, then by name; schema-only changes first within each. */
export function sortDiffEntities(entities: readonly SchemaDiffEntity[]): SchemaDiffEntity[] {
  return [...entities].sort((a, b) => CHANGE_ORDER[a.change] - CHANGE_ORDER[b.change] || a.name.localeCompare(b.name));
}

/** True when a "changed" entity only differs by row count (no structural change). */
export function isDataOnlyChange(entity: SchemaDiffEntity): boolean {
  return (
    entity.change === "changed" &&
    entity.fields.length === 0 &&
    entity.indexes.length === 0 &&
    !entity.validator_changed
  );
}

export const CHANGE_LABELS: Record<DiffChange, string> = { added: "Added", removed: "Removed", changed: "Changed" };
