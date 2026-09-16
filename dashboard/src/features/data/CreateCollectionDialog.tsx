import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { DataSource, JsonObject } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { parseJsonObject } from "./json";
import { JsonEditor } from "./JsonEditor";

const EXAMPLE = `{
  "bsonType": "object",
  "required": ["email"],
  "properties": {
    "email": { "bsonType": "string" },
    "user_id": { "bsonType": "long" }
  }
}`;

export function CreateCollectionDialog({
  projectId,
  source,
  onClose,
  onCreated,
}: {
  projectId: string;
  source: DataSource;
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [schemaText, setSchemaText] = useState("");
  const parsed = parseJsonObject(schemaText, { allowEmpty: true });
  const nameValid = /^[A-Za-z_][A-Za-z0-9_.-]*$/.test(name) && !name.startsWith("system.");

  const create = useMutation({
    mutationFn: () => {
      let validator: JsonObject | undefined;
      if (parsed.ok && parsed.value) {
        validator = "$jsonSchema" in parsed.value ? parsed.value : { $jsonSchema: parsed.value };
      }
      return api.schema.createCollection(projectId, source.id, { name: name.trim(), validator });
    },
    onSuccess: (entity) => {
      void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
      toast.success(`Collection ${entity.name} created.`);
      onCreated(entity.name);
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (nameValid && parsed.ok) create.mutate();
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Create collection in ${source.name}`}
      size="lg"
      dismissible={!create.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="create-collection" variant="primary" loading={create.isPending} disabled={!nameValid || !parsed.ok}>
            Create collection
          </Button>
        </>
      }
    >
      <form id="create-collection" className="space-y-4" onSubmit={onSubmit}>
        <Field
          label="Name"
          hint="Plural snake_case is recommended (conventions N1, N2), e.g. order_items."
          error={name && !nameValid ? "Use letters, digits and underscores; start with a letter." : undefined}
        >
          {(id) => (
            <Input
              id={id}
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoCapitalize="off"
              spellCheck={false}
              className="font-mono"
            />
          )}
        </Field>
        <JsonEditor
          label="$jsonSchema validator (optional)"
          value={schemaText}
          onChange={setSchemaText}
          allowEmpty
          rows={10}
          placeholder={EXAMPLE}
          hint="MongoDB rejects inserts and updates that don't match this schema. Leave empty for no validation."
        />
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
