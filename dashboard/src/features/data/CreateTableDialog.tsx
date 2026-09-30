import { useId, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { ColumnSpec, DataSource, Entity, ForeignKeyAction, TableSpec } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";

type ColumnDraft = {
  key: number;
  name: string;
  type: string;
  nullable: boolean;
  default: string;
  primary_key: boolean;
  unique: boolean;
  auto_increment: boolean;
  refTable: string;
  refColumn: string;
  onDelete: ForeignKeyAction | "";
  advanced: boolean;
};

// Plain-language column kinds shown first; the raw SQL type list stays under "Other (SQL type)".
const FRIENDLY_MYSQL: [string, string][] = [
  ["Text", "VARCHAR(255)"],
  ["Long text", "TEXT"],
  ["Whole number", "BIGINT"],
  ["Decimal number (e.g. prices)", "DECIMAL(10,2)"],
  ["Yes / No", "BOOLEAN"],
  ["Date", "DATE"],
  ["Date and time", "DATETIME"],
  ["ID number", "BIGINT UNSIGNED"],
  ["JSON data", "JSON"],
];
const FRIENDLY_PG: [string, string][] = [
  ["Text", "VARCHAR(255)"],
  ["Long text", "TEXT"],
  ["Whole number", "BIGINT"],
  ["Decimal number (e.g. prices)", "NUMERIC(10,2)"],
  ["Yes / No", "BOOLEAN"],
  ["Date", "DATE"],
  ["Date and time", "TIMESTAMPTZ"],
  ["Unique ID (UUID)", "UUID"],
  ["JSON data", "JSONB"],
];
const ADVANCED = "__advanced";

const TYPES_MYSQL = [
  "BIGINT UNSIGNED",
  "BIGINT",
  "INT",
  "SMALLINT",
  "TINYINT(1)",
  "BOOLEAN",
  "DECIMAL(10,2)",
  "DOUBLE",
  "VARCHAR(255)",
  "CHAR(36)",
  "TEXT",
  "LONGTEXT",
  "JSON",
  "DATE",
  "DATETIME",
  "TIMESTAMP",
  "BLOB",
];
const TYPES_PG = [
  "BIGINT",
  "INTEGER",
  "SMALLINT",
  "BOOLEAN",
  "NUMERIC(10,2)",
  "DOUBLE PRECISION",
  "VARCHAR(255)",
  "UUID",
  "TEXT",
  "JSONB",
  "DATE",
  "TIMESTAMPTZ",
  "BYTEA",
];

const SQL_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

let nextKey = 1;
function newColumn(partial: Partial<ColumnDraft> = {}): ColumnDraft {
  return {
    key: nextKey++,
    name: "",
    type: "VARCHAR(255)",
    nullable: true,
    default: "",
    primary_key: false,
    unique: false,
    auto_increment: false,
    refTable: "",
    refColumn: "",
    onDelete: "",
    advanced: false,
    ...partial,
  };
}

export function CreateTableDialog({
  projectId,
  source,
  entities,
  onClose,
  onCreated,
}: {
  projectId: string;
  source: DataSource;
  entities: Entity[];
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const listId = useId();
  const isPg = source.engine === "postgresql";
  const friendly = isPg ? FRIENDLY_PG : FRIENDLY_MYSQL;
  const isFriendly = (t: string) => friendly.some(([, v]) => v === t.trim().toUpperCase());
  // A link column must have exactly the linked column's type (MySQL refuses the foreign key otherwise).
  const refType = (table: string, column: string) =>
    entities.find((e) => e.name === table)?.fields.find((f) => f.name === column)?.data_type.toUpperCase() ?? "";
  const idType = isPg ? "BIGINT" : "BIGINT UNSIGNED";
  const [name, setName] = useState("");
  const [timestamps, setTimestamps] = useState(true);
  const [columns, setColumns] = useState<ColumnDraft[]>(() => [
    newColumn({ name: "id", type: idType, nullable: false, primary_key: true, auto_increment: true }),
  ]);

  const update = (key: number, patch: Partial<ColumnDraft>) =>
    setColumns((cols) => cols.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  const move = (index: number, dir: -1 | 1) =>
    setColumns((cols) => {
      const next = [...cols];
      const j = index + dir;
      if (j < 0 || j >= next.length) return cols;
      [next[index], next[j]] = [next[j], next[index]];
      return next;
    });

  const names = columns.map((c) => c.name.trim());
  const errors: string[] = [];
  if (name && !SQL_NAME.test(name)) errors.push("Table name must use letters, digits and underscores.");
  if (columns.length === 0) errors.push("Add at least one column.");
  columns.forEach((c, i) => {
    const n = c.name.trim();
    if (!n) errors.push(`Column ${i + 1} needs a name.`);
    else if (!SQL_NAME.test(n)) errors.push(`Column “${n}” has invalid characters.`);
    else if (names.indexOf(n) !== i) errors.push(`Duplicate column “${n}”.`);
    if (!c.type.trim()) errors.push(`Column ${n || i + 1} needs a type.`);
    if (c.refTable && !c.refColumn) errors.push(`Choose which ${c.refTable} column ${n || `column ${i + 1}`} links to.`);
  });
  if (timestamps && (names.includes("created_at") || names.includes("updated_at"))) {
    errors.push("Remove created_at/updated_at columns or untick “Add timestamps”.");
  }
  const noPk = !columns.some((c) => c.primary_key);
  const valid = Boolean(name.trim()) && errors.length === 0;

  const create = useMutation({
    mutationFn: () => {
      const spec: TableSpec = {
        name: name.trim(),
        timestamps,
        columns: columns.map((c): ColumnSpec => {
          const col: ColumnSpec = {
            name: c.name.trim(),
            type: c.type.trim(),
            nullable: c.primary_key ? false : c.nullable,
            default: c.default.trim() === "" ? null : c.default.trim(),
            primary_key: c.primary_key,
            unique: c.unique,
            auto_increment: c.auto_increment,
          };
          if (c.refTable && c.refColumn) {
            col.references = {
              table: c.refTable,
              column: c.refColumn,
              ...(c.onDelete ? { on_delete: c.onDelete } : {}),
            };
          }
          return col;
        }),
      };
      return api.schema.createTable(projectId, source.id, spec);
    },
    onSuccess: (entity) => {
      void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
      toast.success(`Table ${entity.name} created.`);
      onCreated(entity.name);
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) create.mutate();
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Create table in ${source.name}`}
      size="xl"
      dismissible={!create.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="create-table" variant="primary" loading={create.isPending} disabled={!valid}>
            Create table
          </Button>
        </>
      }
    >
      <datalist id={listId}>
        {(isPg ? TYPES_PG : TYPES_MYSQL).map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
      <form id="create-table" className="space-y-4" onSubmit={onSubmit}>
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field label="Table name" hint="Plural snake_case is recommended, e.g. order_items.">
            {(id) => (
              <Input
                id={id}
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="font-mono"
                autoCapitalize="off"
                spellCheck={false}
              />
            )}
          </Field>
          <Checkbox
            className="pb-6"
            checked={timestamps}
            onChange={(e) => setTimestamps(e.target.checked)}
            label="Add timestamps"
            description="created_at / updated_at, filled in automatically"
          />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Columns</p>
          {columns.map((c, i) => {
            const refEntity = entities.find((e) => e.name === c.refTable);
            const showRaw = c.advanced || !isFriendly(c.type);
            return (
              <fieldset key={c.key} className="rounded-xl border border-border bg-surface-2/50 p-3">
                <legend className="sr-only">Column {i + 1}</legend>
                <div className="grid gap-2 sm:grid-cols-12">
                  <Input
                    aria-label="Column name"
                    placeholder="name"
                    value={c.name}
                    onChange={(e) => update(c.key, { name: e.target.value })}
                    className="font-mono sm:col-span-3"
                    autoCapitalize="off"
                    spellCheck={false}
                  />
                  <div className="space-y-2 sm:col-span-3">
                    <Select
                      aria-label="Kind of data"
                      value={showRaw ? ADVANCED : c.type.trim().toUpperCase()}
                      onChange={(e) =>
                        update(
                          c.key,
                          e.target.value === ADVANCED ? { advanced: true } : { type: e.target.value, advanced: false },
                        )
                      }
                    >
                      {friendly.map(([label, t]) => (
                        <option key={t} value={t}>
                          {label}
                        </option>
                      ))}
                      <option value={ADVANCED}>Other (SQL type)…</option>
                    </Select>
                    {showRaw && (
                      <Input
                        aria-label="Column type"
                        placeholder="SQL type, e.g. VARCHAR(100)"
                        list={listId}
                        value={c.type}
                        onChange={(e) => update(c.key, { type: e.target.value })}
                        className="font-mono"
                        autoCapitalize="characters"
                        spellCheck={false}
                      />
                    )}
                  </div>
                  <Input
                    aria-label="Default value"
                    placeholder="Default value (optional)"
                    value={c.default}
                    onChange={(e) => update(c.key, { default: e.target.value })}
                    className="font-mono sm:col-span-3"
                    spellCheck={false}
                  />
                  <div className="flex items-center justify-end gap-1 sm:col-span-3">
                    <Button size="icon-sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                      <ArrowUp className="size-3.5" />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label="Move down"
                      disabled={i === columns.length - 1}
                      onClick={() => move(i, 1)}
                    >
                      <ArrowDown className="size-3.5" />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      className="text-danger"
                      aria-label="Remove column"
                      onClick={() => setColumns((cols) => cols.filter((x) => x.key !== c.key))}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
                  <Checkbox
                    label="Primary key (row ID)"
                    checked={c.primary_key}
                    onChange={(e) =>
                      update(c.key, { primary_key: e.target.checked, nullable: e.target.checked ? false : c.nullable })
                    }
                  />
                  <Checkbox
                    label="Can be empty"
                    checked={c.nullable && !c.primary_key}
                    disabled={c.primary_key}
                    onChange={(e) => update(c.key, { nullable: e.target.checked })}
                  />
                  <Checkbox label="No duplicates" checked={c.unique} onChange={(e) => update(c.key, { unique: e.target.checked })} />
                  <Checkbox
                    label="Auto-numbered"
                    checked={c.auto_increment}
                    onChange={(e) => update(c.key, { auto_increment: e.target.checked })}
                  />
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  <Select
                    aria-label="Links to table"
                    value={c.refTable}
                    onChange={(e) => {
                      const table = e.target.value;
                      const t = entities.find((x) => x.name === table);
                      const pk = table ? (t?.fields.find((f) => f.primary_key)?.name ?? "") : "";
                      const type = pk ? refType(table, pk) : "";
                      update(c.key, { refTable: table, refColumn: pk, ...(type ? { type, advanced: false } : {}) });
                    }}
                  >
                    <option value="">Not linked to another table</option>
                    {entities.map((e) => (
                      <option key={e.name} value={e.name}>
                        Links to {e.name}
                      </option>
                    ))}
                  </Select>
                  {c.refTable && (
                    <>
                      <Select
                        aria-label="Links to column"
                        value={c.refColumn}
                        onChange={(e) => {
                          const type = refType(c.refTable, e.target.value);
                          update(c.key, { refColumn: e.target.value, ...(type ? { type, advanced: false } : {}) });
                        }}
                      >
                        <option value="">Which column…</option>
                        {refEntity?.fields.map((f) => (
                          <option key={f.name} value={f.name}>
                            {f.name} ({f.data_type})
                          </option>
                        ))}
                      </Select>
                      <Select
                        aria-label={`If a ${c.refTable} row is deleted`}
                        value={c.onDelete}
                        onChange={(e) => {
                          const onDelete = e.target.value as ForeignKeyAction | "";
                          // "set null" needs a column that can be empty.
                          update(c.key, onDelete === "set null" ? { onDelete, nullable: true } : { onDelete });
                        }}
                      >
                        <option value="">If the {c.refTable} row is deleted: block it while rows link here</option>
                        <option value="set null">If the {c.refTable} row is deleted: empty this column</option>
                        <option value="cascade">If the {c.refTable} row is deleted: delete these rows too</option>
                      </Select>
                    </>
                  )}
                </div>
                {c.refTable && c.onDelete === "cascade" && (
                  <Alert tone="warning" className="mt-2">
                    Deleting a row in {c.refTable} will also permanently delete every row of this table that links to it,
                    with no further prompt.
                  </Alert>
                )}
              </fieldset>
            );
          })}
          <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setColumns((cols) => [...cols, newColumn()])}>
            Add column
          </Button>
        </div>

        {noPk && (
          <Alert tone="warning">
            No column is ticked as the primary key (row ID). Without one, rows can't be edited or deleted in the data
            browser; an auto-numbered id column is the usual choice.
          </Alert>
        )}
        {name && errors.length > 0 && (
          <Alert tone="danger">
            <ul className="list-disc pl-4">
              {errors.slice(0, 5).map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </Alert>
        )}
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
