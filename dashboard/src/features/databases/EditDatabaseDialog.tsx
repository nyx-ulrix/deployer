import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { DataSource } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";

/** A-030: edit a source in place (same id, so links, API key configs and saved queries keep working). */
export function EditDatabaseDialog({
  projectId,
  source,
  onClose,
}: {
  projectId: string;
  source: DataSource;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const d = source.display;
  // DynamoDB / Firestore / Realtime Database have no connection settings of their own (their cloud account's key is
  // used): rename only.
  const external = source.mode === "external" && !["dynamodb", "firestore", "firebase_rtdb"].includes(source.engine);
  const sql = source.kind === "sql";
  const [name, setName] = useState(source.name);
  const [host, setHost] = useState(d.host ?? "");
  const [port, setPort] = useState(d.port ? String(d.port) : "");
  const [username, setUsername] = useState(d.username ?? "");
  const [password, setPassword] = useState("");
  const [database, setDatabase] = useState(source.database_name);
  const [tls, setTls] = useState(d.tls);
  const [uri, setUri] = useState("");

  const buildConfig = (): Record<string, unknown> | undefined => {
    if (!external) return undefined;
    // Blank secrets keep the stored ones, so a rename or host change needs no password.
    const config: Record<string, unknown> = sql
      ? {
          host: host.trim(),
          port: port ? Number(port) : undefined,
          username: username.trim(),
          database: database.trim(),
          tls,
        }
      : { database: database.trim() };
    if (sql && password) config.password = password;
    if (!sql && uri.trim()) config.uri = uri.trim();
    return config;
  };

  const save = useMutation({
    mutationFn: () =>
      api.dataSources.update(projectId, source.id, {
        name: name.trim(),
        config: buildConfig(),
      }),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({
        queryKey: qk.dataSources(projectId),
      });
      void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
      toast.success(`${updated.name} saved.`);
      onClose();
    },
  });

  const valid =
    Boolean(name.trim()) &&
    (!external || Boolean(database.trim())) &&
    (!external ||
      !sql ||
      (Boolean(host.trim() && username.trim()) &&
        (!port || /^\d+$/.test(port))));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Edit ${source.name}`}
      description={
        external
          ? "Changed connection settings are tested before they are saved."
          : undefined
      }
      size="lg"
      dismissible={!save.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="edit-db"
            variant="primary"
            loading={save.isPending}
            disabled={!valid}
          >
            Save
          </Button>
        </>
      }
    >
      <form id="edit-db" className="space-y-4" onSubmit={onSubmit}>
        <Field
          label="Display name"
          hint={
            // Apps with database access get DEPLOYER_DB_<NAME>_* for managed sources (docs/DEPLOYMENTS.md).
            !external && name.trim() !== source.name
              ? `Apps with database access get ${envPrefix(name)}* instead of ${envPrefix(source.name)}* from their next deploy; update any app that reads the old names.`
              : undefined
          }
        >
          {(id) => (
            <Input
              id={id}
              value={name}
              maxLength={63}
              onChange={(e) => setName(e.target.value)}
              required
            />
          )}
        </Field>
        {external && sql && (
          <div className="grid gap-3 sm:grid-cols-6">
            <Field
              label="Host"
              className="sm:col-span-4"
              hint="On this PC? Use its network IP (ipconfig), not localhost."
            >
              {(id) => (
                <Input
                  id={id}
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <Field label="Port" className="sm:col-span-2">
              {(id) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  value={port}
                  onChange={(e) =>
                    setPort(e.target.value.replace(/[^\d]/g, ""))
                  }
                />
              )}
            </Field>
            <Field label="Username" className="sm:col-span-3">
              {(id) => (
                <Input
                  id={id}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <Field
              label="New password"
              optional
              className="sm:col-span-3"
              hint="Leave blank to keep the current one."
            >
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                />
              )}
            </Field>
            <Field label="Database" className="sm:col-span-4">
              {(id) => (
                <Input
                  id={id}
                  value={database}
                  onChange={(e) => setDatabase(e.target.value)}
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <div className="flex items-end pb-2 sm:col-span-2">
              <Checkbox
                checked={tls}
                onChange={(e) => setTls(e.target.checked)}
                label="Use TLS"
              />
            </div>
          </div>
        )}
        {external && !sql && (
          <>
            <Field
              label="New connection URI"
              optional
              hint="Leave blank to keep the current one."
            >
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  value={uri}
                  onChange={(e) => setUri(e.target.value)}
                  placeholder="mongodb+srv://<user>:<password>@<cluster>.mongodb.net"
                  autoComplete="off"
                  spellCheck={false}
                />
              )}
            </Field>
            <Field label="Database">
              {(id) => (
                <Input
                  id={id}
                  value={database}
                  onChange={(e) => setDatabase(e.target.value)}
                  spellCheck={false}
                  required
                />
              )}
            </Field>
          </>
        )}
        {save.error && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
      </form>
    </Dialog>
  );
}

const envPrefix = (name: string) =>
  `DEPLOYER_DB_${name
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "_")}_`;
