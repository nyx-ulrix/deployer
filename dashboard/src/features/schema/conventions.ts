/** Short descriptions of the rules in docs/CONVENTIONS.md, keyed by rule ID. */
export const CONVENTION_RULES: Record<string, { title: string; description: string }> = {
  N1: { title: "snake_case names", description: "Table and collection names are snake_case, e.g. order_items." },
  N2: { title: "Plural names", description: "Table and collection names are plural (users, order_items)." },
  N3: { title: "snake_case fields", description: "Column and field names are snake_case. Mongo's _id is exempt." },
  N4: { title: "No reserved words", description: "Avoid SQL reserved words (order, group, user…) as table or column names." },
  N5: {
    title: "FK naming",
    description: "Foreign-key columns are named <singular_referenced_table>_id, e.g. user_id → users.id.",
  },
  N6: { title: "Boolean prefixes", description: "Boolean columns start with is_, has_ or can_." },
  S1: { title: "Primary key", description: "Every SQL table has a primary key (required to edit rows safely)." },
  S2: { title: "PK named id", description: "A single-column primary key is named id." },
  S3: { title: "Index FKs", description: "Every foreign-key column is indexed so joins and deletes stay fast." },
  S4: {
    title: "Declare references",
    description:
      "Columns named *_id that match a table have a declared FK constraint (SQL) or an index (Mongo).",
  },
  S5: { title: "Timestamps", description: "Tables have created_at and updated_at timestamps." },
  S6: { title: "PK not null", description: "Primary-key columns are not nullable." },
  S7: { title: "Consistent types", description: "A Mongo field has one consistent type across sampled documents." },
  S8: {
    title: "Index references",
    description: "Mongo collections queried by a reference field have an index on it.",
  },
  X1: { title: "Link ends exist", description: "Both ends of a cross-database link exist in the current schema." },
  X2: {
    title: "Compatible types",
    description: "Linked field types are compatible, e.g. BIGINT ↔ int/long, CHAR(36) ↔ string.",
  },
  X3: { title: "Index the many side", description: "The “many” side of a cross-database link is indexed." },
};

export function ruleInfo(rule: string) {
  return CONVENTION_RULES[rule] ?? { title: rule, description: "See docs/CONVENTIONS.md." };
}
