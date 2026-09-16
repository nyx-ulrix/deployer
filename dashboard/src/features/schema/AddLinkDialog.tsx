import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { LinkCardinality, ProjectSchema } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Select, Textarea } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { engineLabel } from "../../lib/format";

type End = { sourceId: string; entity: string; field: string };

const CARDINALITIES: { value: LinkCardinality; label: string }[] = [
  { value: "many_to_one", label: "Many to one (e.g. orders.user_id → users.id)" },
  { value: "one_to_one", label: "One to one" },
  { value: "one_to_many", label: "One to many" },
  { value: "many_to_many", label: "Many to many" },
];

function EndPicker({
  label,
  schema,
  value,
  onChange,
}: {
  label: string;
  schema: ProjectSchema;
  value: End;
  onChange: (v: End) => void;
}) {
  const sources = schema.sources.filter((s) => s.status === "ok");
  const source = sources.find((s) => s.source_id === value.sourceId);
  const entity = source?.entities.find((e) => e.name === value.entity);
  return (
    <fieldset className="space-y-2 rounded-xl border border-border p-3">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      <div className="grid gap-2 sm:grid-cols-3">
        <Select
          aria-label={`${label} source`}
          value={value.sourceId}
          onChange={(e) => onChange({ sourceId: e.target.value, entity: "", field: "" })}
        >
          <option value="">Database…</option>
          {sources.map((s) => (
            <option key={s.source_id} value={s.source_id}>
              {s.name} ({engineLabel(s.engine)})
            </option>
          ))}
        </Select>
        <Select
          aria-label={`${label} entity`}
          value={value.entity}
          disabled={!source}
          onChange={(e) => {
            const ent = source?.entities.find((x) => x.name === e.target.value);
            const pk = ent?.fields.find((f) => f.primary_key)?.name ?? "";
            onChange({ ...value, entity: e.target.value, field: pk });
          }}
        >
          <option value="">{source?.kind === "nosql" ? "Collection…" : "Table…"}</option>
          {source?.entities.map((e) => (
            <option key={e.name} value={e.name}>
              {e.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label={`${label} field`}
          value={value.field}
          disabled={!entity}
          onChange={(e) => onChange({ ...value, field: e.target.value })}
        >
          <option value="">Field…</option>
          {entity?.fields.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name} ({f.data_type})
            </option>
          ))}
        </Select>
      </div>
    </fieldset>
  );
}

export function AddLinkDialog({
  projectId,
  schema,
  initialFrom,
  onClose,
}: {
  projectId: string;
  schema: ProjectSchema;
  initialFrom?: { sourceId: string; entity: string } | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const sqlFirst = schema.sources.find((s) => s.kind === "sql" && s.status === "ok");
  const nosqlFirst = schema.sources.find((s) => s.kind === "nosql" && s.status === "ok");
  const [from, setFrom] = useState<End>({
    sourceId: initialFrom?.sourceId ?? nosqlFirst?.source_id ?? "",
    entity: initialFrom?.entity ?? "",
    field: "",
  });
  const [to, setTo] = useState<End>({ sourceId: sqlFirst?.source_id ?? "", entity: "", field: "" });
  const [cardinality, setCardinality] = useState<LinkCardinality>("many_to_one");
  const [note, setNote] = useState("");

  const complete = (e: End) => Boolean(e.sourceId && e.entity && e.field);
  const same = from.sourceId === to.sourceId && from.entity === to.entity && from.field === to.field;
  const valid = complete(from) && complete(to) && !same;
  const crossDb = from.sourceId !== to.sourceId;

  const create = useMutation({
    mutationFn: () =>
      api.schema.createLink(projectId, {
        from_source_id: from.sourceId,
        from_entity: from.entity,
        from_field: from.field,
        to_source_id: to.sourceId,
        to_entity: to.entity,
        to_field: to.field,
        cardinality,
        note: note.trim() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
      toast.success("Link added.");
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
      title="Add link"
      description="Declare a relationship the databases can't enforce themselves — typically between a SQL column and a MongoDB field."
      size="lg"
      dismissible={!create.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="add-link" variant="primary" loading={create.isPending} disabled={!valid}>
            Add link
          </Button>
        </>
      }
    >
      <form id="add-link" className="space-y-3" onSubmit={onSubmit}>
        <EndPicker label="From (referencing field)" schema={schema} value={from} onChange={setFrom} />
        <div className="flex justify-center text-muted">
          <ArrowDown className="size-4" />
        </div>
        <EndPicker label="To (referenced field)" schema={schema} value={to} onChange={setTo} />
        <Field label="Cardinality">
          {(id) => (
            <Select id={id} value={cardinality} onChange={(e) => setCardinality(e.target.value as LinkCardinality)}>
              {CARDINALITIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Note" optional>
          {(id) => (
            <Textarea
              id={id}
              rows={2}
              className="min-h-14"
              value={note}
              maxLength={500}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. events.user_id stores users.id as a string"
            />
          )}
        </Field>
        {same && <Alert tone="warning">A field can't link to itself.</Alert>}
        {complete(from) && complete(to) && !crossDb && !same && (
          <Alert tone="info">
            Both ends are in the same database. Consider a real foreign key instead, if the engine supports it.
          </Alert>
        )}
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
