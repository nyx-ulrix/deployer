import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Cloud, Database, HardDrive, Leaf, XCircle } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { ConnectionTestResult, DataSourceInput, DataSourceKind, SqlExternalEngine } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";

type Mode = "managed" | "external";

const DEFAULT_PORTS: Record<SqlExternalEngine, number> = { mariadb: 3306, mysql: 3306, postgresql: 5432 };

function Choice({
  selected,
  onClick,
  icon,
  title,
  description,
  tone,
}: {
  selected: boolean;
  onClick: () => void;
  icon: ReactNode;
  title: string;
  description: string;
  tone?: "sql" | "nosql";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors",
        selected ? "border-accent bg-accent-soft/50 ring-1 ring-accent" : "border-border hover:bg-surface-2",
      )}
    >
      <span
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-lg",
          tone === "sql" ? "bg-sql-soft text-sql" : tone === "nosql" ? "bg-nosql-soft text-nosql" : "bg-surface-2 text-accent",
        )}
      >
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold">{title}</span>
        <span className="mt-0.5 block text-xs text-muted">{description}</span>
      </span>
    </button>
  );
}

export function AddDatabaseDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<DataSourceKind>("sql");
  const [mode, setMode] = useState<Mode>("managed");
  const [name, setName] = useState("");
  // External SQL
  const [engine, setEngine] = useState<SqlExternalEngine>("mysql");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [database, setDatabase] = useState("");
  const [tls, setTls] = useState(false);
  // External Mongo
  const [uri, setUri] = useState("");
  const [mongoDb, setMongoDb] = useState("");

  const [test, setTest] = useState<{ key: string; result: ConnectionTestResult } | null>(null);

  const buildInput = (): DataSourceInput => {
    const n = name.trim() || defaultName();
    if (mode === "managed") {
      return kind === "sql"
        ? { kind: "sql", mode: "managed", engine: "mariadb", name: n }
        : { kind: "nosql", mode: "managed", engine: "mongodb", name: n };
    }
    if (kind === "sql") {
      return {
        kind: "sql",
        mode: "external",
        engine,
        name: n,
        config: {
          host: host.trim(),
          port: port ? Number(port) : undefined,
          username: username.trim(),
          password,
          database: database.trim(),
          tls,
        },
      };
    }
    return { kind: "nosql", mode: "external", engine: "mongodb", name: n, config: { uri: uri.trim(), database: mongoDb.trim() } };
  };

  function defaultName() {
    if (mode === "managed") return kind === "sql" ? "MariaDB" : "MongoDB";
    return kind === "sql" ? { mariadb: "MariaDB", mysql: "MySQL", postgresql: "PostgreSQL" }[engine] : "MongoDB";
  }

  const configKey = JSON.stringify(mode === "external" ? { ...buildInput(), name: "" } : null);
  const testPassed = mode === "managed" || (test?.key === configKey && test.result.ok);

  const externalValid =
    kind === "sql"
      ? Boolean(host.trim() && username.trim() && database.trim()) && (!port || /^\d+$/.test(port))
      : Boolean(uri.trim() && mongoDb.trim());
  const formValid = mode === "managed" || externalValid;

  const testMutation = useMutation({
    mutationFn: () => api.dataSources.test(projectId, buildInput()),
    onSuccess: (result) => setTest({ key: configKey, result }),
    onError: (e) => setTest({ key: configKey, result: { ok: false, message: errorMessage(e), server_version: null } }),
  });

  const create = useMutation({
    mutationFn: () => api.dataSources.create(projectId, buildInput()),
    onSuccess: (source) => {
      void queryClient.invalidateQueries({ queryKey: qk.dataSources(projectId) });
      void queryClient.invalidateQueries({ queryKey: qk.schema(projectId) });
      void queryClient.invalidateQueries({ queryKey: qk.project(projectId) });
      void queryClient.invalidateQueries({ queryKey: qk.projects });
      toast.success(`${source.name} added.`);
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (formValid && testPassed) create.mutate();
  };

  const busy = create.isPending || testMutation.isPending;
  const currentTest = test?.key === configKey ? test.result : null;

  return (
    <Dialog
      open
      onClose={onClose}
      title="Add database"
      description="A project can use SQL and NoSQL databases together."
      size="lg"
      dismissible={!busy}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          {mode === "external" && (
            <Button
              onClick={() => testMutation.mutate()}
              loading={testMutation.isPending}
              disabled={!externalValid || create.isPending}
            >
              Test connection
            </Button>
          )}
          <Button
            type="submit"
            form="add-db"
            variant="primary"
            loading={create.isPending}
            disabled={!formValid || !testPassed || testMutation.isPending}
            title={!testPassed ? "Test the connection first" : undefined}
          >
            {mode === "managed" ? "Create database" : "Save connection"}
          </Button>
        </>
      }
    >
      <form id="add-db" className="space-y-5" onSubmit={onSubmit}>
        <div>
          <p className="mb-2 text-sm font-medium">Type</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Choice
              selected={kind === "sql"}
              onClick={() => setKind("sql")}
              icon={<Database className="size-4" />}
              title="SQL"
              description="Tables, columns, foreign keys."
              tone="sql"
            />
            <Choice
              selected={kind === "nosql"}
              onClick={() => setKind("nosql")}
              icon={<Leaf className="size-4" />}
              title="NoSQL"
              description="MongoDB collections of JSON documents."
              tone="nosql"
            />
          </div>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Where</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Choice
              selected={mode === "managed"}
              onClick={() => setMode("managed")}
              icon={<HardDrive className="size-4" />}
              title="Managed"
              description={kind === "sql" ? "New MariaDB database on this machine." : "New MongoDB database on this machine."}
            />
            <Choice
              selected={mode === "external"}
              onClick={() => setMode("external")}
              icon={<Cloud className="size-4" />}
              title="External"
              description={
                kind === "sql" ? "Connect existing MariaDB, MySQL or PostgreSQL." : "Connect MongoDB Atlas or another server."
              }
            />
          </div>
        </div>

        <Field label="Display name" optional hint={`Defaults to “${defaultName()}”.`}>
          {(id) => <Input id={id} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />}
        </Field>

        {mode === "external" && kind === "sql" && (
          <div className="grid gap-3 sm:grid-cols-6">
            <Field label="Engine" className="sm:col-span-2">
              {(id) => (
                <Select
                  id={id}
                  value={engine}
                  onChange={(e) => setEngine(e.target.value as SqlExternalEngine)}
                >
                  <option value="mysql">MySQL</option>
                  <option value="mariadb">MariaDB</option>
                  <option value="postgresql">PostgreSQL</option>
                </Select>
              )}
            </Field>
            <Field label="Host" className="sm:col-span-3">
              {(id) => (
                <Input
                  id={id}
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="db.example.com"
                  autoCapitalize="off"
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <Field label="Port" className="sm:col-span-1">
              {(id) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  value={port}
                  onChange={(e) => setPort(e.target.value.replace(/[^\d]/g, ""))}
                  placeholder={String(DEFAULT_PORTS[engine])}
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
                  autoCapitalize="off"
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <Field label="Password" className="sm:col-span-3">
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
                  autoCapitalize="off"
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <div className="flex items-end pb-2 sm:col-span-2">
              <Checkbox checked={tls} onChange={(e) => setTls(e.target.checked)} label="Use TLS" />
            </div>
          </div>
        )}

        {mode === "external" && kind === "nosql" && (
          <div className="space-y-3">
            <Field label="Connection URI">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  value={uri}
                  onChange={(e) => setUri(e.target.value)}
                  placeholder="mongodb+srv://user:password@cluster0.abcde.mongodb.net"
                  autoComplete="off"
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <Field label="Database">
              {(id) => (
                <Input
                  id={id}
                  value={mongoDb}
                  onChange={(e) => setMongoDb(e.target.value)}
                  autoCapitalize="off"
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <Alert tone="info" title="Using MongoDB Atlas?">
              In Atlas, open <em>Connect → Drivers</em> and copy the <code>mongodb+srv://</code> string (replace{" "}
              <code>&lt;password&gt;</code>). Under <em>Network Access</em>, allow this machine's public IP address, or
              the connection test will time out.
            </Alert>
          </div>
        )}

        {mode === "external" && currentTest && (
          <div
            className={cn(
              "flex items-start gap-2 rounded-xl px-3 py-2.5 text-sm",
              currentTest.ok ? "bg-success-soft" : "bg-danger-soft",
            )}
            role="status"
          >
            {currentTest.ok ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />
            )}
            <div className="min-w-0 break-words">
              <p className="font-medium">{currentTest.ok ? "Connection successful" : "Connection failed"}</p>
              <p className="text-fg/80">
                {currentTest.message}
                {currentTest.server_version ? ` (server ${currentTest.server_version})` : ""}
              </p>
            </div>
          </div>
        )}
        {mode === "external" && !currentTest && (
          <p className="text-xs text-muted">Test the connection before saving.</p>
        )}
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
