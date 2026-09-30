import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { errorMessage, isApiError } from "../../api/client";
import { api } from "../../api/endpoints";
import type { DataSource, Entity, Field as SchemaField, JsonObject, JsonValue } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input, Textarea } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";

type CellState = { text: string; isNull: boolean; touched: boolean };

// BOOLEAN on MariaDB/MySQL is stored (and reported) as TINYINT(1).
const BOOLEAN = /^(bool|boolean|tinyint\(1\)( unsigned)?|bit\(1\))$/i;
const NUMERIC = /^(tinyint|smallint|mediumint|int|integer|bigint|float|double|real|serial|bigserial|smallserial)\b/i;

function toText(v: JsonValue | undefined): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Convert edited text back to a JSON value, using the column type and original value as hints. */
function fromText(text: string, field: SchemaField | undefined, original: JsonValue | undefined): JsonValue {
  const type = field?.data_type ?? "";
  if (typeof original === "object" && original !== null) {
    try {
      return JSON.parse(text) as JsonValue;
    } catch {
      return text;
    }
  }
  if (typeof original === "boolean" || BOOLEAN.test(type)) {
    if (/^(true|1)$/i.test(text)) return true;
    if (/^(false|0)$/i.test(text)) return false;
  }
  if ((typeof original === "number" || NUMERIC.test(type)) && /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(text.trim())) {
    const n = Number(text);
    if (Number.isSafeInteger(n) || !Number.isInteger(n)) return n;
  }
  return text;
}

export function RowDialog({
  projectId,
  source,
  entity,
  columns,
  primaryKey,
  row,
  onClose,
  onSaved,
}: {
  projectId: string;
  source: DataSource;
  entity: Entity;
  columns: string[];
  primaryKey: string[];
  row: JsonObject | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isNew = row === null;
  const fields = new Map(entity.fields.map((f) => [f.name, f]));
  const [cells, setCells] = useState<Record<string, CellState>>(() =>
    Object.fromEntries(
      columns.map((c) => {
        const v = row?.[c];
        return [c, { text: toText(v), isNull: !isNew && (v === null || v === undefined), touched: false }];
      }),
    ),
  );

  const update = (col: string, patch: Partial<CellState>) =>
    setCells((prev) => ({ ...prev, [col]: { ...prev[col], ...patch, touched: true } }));

  const save = useMutation({
    mutationFn: () => {
      const values: JsonObject = {};
      for (const c of columns) {
        const cell = cells[c];
        if (!cell.touched) continue;
        if (isNew && !cell.isNull && cell.text === "") continue; // let DB defaults apply
        values[c] = cell.isNull ? null : fromText(cell.text, fields.get(c), row?.[c]);
      }
      if (isNew) return api.rows.insert(projectId, source.id, entity.name, values);
      const pk: JsonObject = Object.fromEntries(primaryKey.map((k) => [k, row[k] ?? null]));
      return api.rows.update(projectId, source.id, entity.name, pk, values);
    },
    onSuccess: () => {
      toast.success(isNew ? "Row added." : "Row updated.");
      onSaved();
      onClose();
    },
  });

  const changed = columns.some((c) => cells[c].touched);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (isNew || changed) save.mutate();
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={isNew ? `Add row to ${entity.name}` : `Edit row in ${entity.name}`}
      description={isNew ? "Leave a field empty to use its default value." : "Only changed fields are saved."}
      size="lg"
      dismissible={!save.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="row-form" variant="primary" loading={save.isPending} disabled={!isNew && !changed}>
            {isNew ? "Add row" : "Save changes"}
          </Button>
        </>
      }
    >
      <form id="row-form" className="space-y-3" onSubmit={onSubmit}>
        {columns.map((c) => {
          const f = fields.get(c);
          const cell = cells[c];
          // From the type and the original value only: keying on the live text would swap
          // Input for Textarea mid-typing and drop focus at the 81st character.
          const long = /text|json|blob/i.test(f?.data_type ?? "") || toText(row?.[c]).length > 80;
          const Control = long ? Textarea : Input;
          const yesNo = typeof row?.[c] === "boolean" || BOOLEAN.test(f?.data_type ?? "");
          return (
            <div key={c} className="space-y-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <label htmlFor={`row-${c}`} className="font-mono text-sm font-medium">
                  {c}
                </label>
                {f && <span className="font-mono text-xs text-muted">{f.data_type}</span>}
                {primaryKey.includes(c) && <Badge tone="warning">PK</Badge>}
                {f && !f.nullable && <Badge>NN</Badge>}
                {f?.nullable && (
                  <label className="ml-auto flex items-center gap-1.5 text-xs text-muted">
                    <input
                      type="checkbox"
                      checked={cell.isNull}
                      onChange={(e) => update(c, { isNull: e.target.checked })}
                      className="accent-[var(--accent)]"
                    />
                    NULL
                  </label>
                )}
              </div>
              {yesNo ? (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    id={`row-${c}`}
                    type="checkbox"
                    checked={!cell.isNull && /^(true|1)$/i.test(cell.text)}
                    disabled={cell.isNull}
                    onChange={(e) => update(c, { text: e.target.checked ? "true" : "false" })}
                    className="accent-[var(--accent)]"
                  />
                  {cell.isNull ? "NULL" : "Yes"}
                  {isNew && !cell.touched && f?.default && (
                    <span className="text-xs text-muted">(default: {f.default})</span>
                  )}
                </label>
              ) : (
                <Control
                  id={`row-${c}`}
                  value={cell.isNull ? "" : cell.text}
                  disabled={cell.isNull}
                  placeholder={cell.isNull ? "NULL" : isNew ? (f?.default ? `default: ${f.default}` : "") : ""}
                  className={long ? "min-h-20 font-mono" : "font-mono"}
                  onChange={(e: { target: { value: string } }) => update(c, { text: e.target.value })}
                />
              )}
            </div>
          );
        })}
        {save.error && (
          <Alert tone="danger">
            {errorMessage(save.error)}
            {isApiError(save.error) && typeof save.error.details.detail === "string" && (
              <details className="mt-1 text-xs">
                <summary className="cursor-pointer">Database message</summary>
                <code className="break-words">{save.error.details.detail}</code>
              </details>
            )}
          </Alert>
        )}
      </form>
    </Dialog>
  );
}
