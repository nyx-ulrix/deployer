import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CloudCog, Database, FileJson, Flame, HardDrive, Leaf, Network, Server, XCircle } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api } from "../../api/endpoints";
import { invalidateProjectSources, usePlacementOptions } from "../../api/hooks";
import type {
  ConnectionTestResult,
  DataSourceInput,
  DataSourceKind,
  DatabaseLocation,
  SqlExternalEngine,
} from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { defaultPlacement, deviceIdFromValue, engineForKind, placementDisplay } from "../devices/eligibility";
import { HostOnSelect } from "../devices/HostOnSelect";
import { AwsDatabaseSection } from "./AwsDatabaseSection";
import { Choice } from "./Choice";
import { FirestoreSection } from "./FirestoreSection";
import { RtdbSection } from "./RtdbSection";

type Mode = "managed" | "external";
type Where = DatabaseLocation["id"];

const WHERE_ICONS = {
  local: <HardDrive className="size-4" />,
  external: <Server className="size-4" />,
  aws: <CloudCog className="size-4" />,
  firebase: <Flame className="size-4" />,
};

const DEFAULT_PORTS: Record<SqlExternalEngine, number> = { mariadb: 3306, mysql: 3306, postgresql: 5432 };

export function AddDatabaseDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<DataSourceKind>("sql");
  // docs/CLOUD.md "C2": on this PC (managed), another server (external), the user's AWS or Firebase.
  const [where, setWhere] = useState<Where>("local");
  const mode: Mode = where === "local" ? "managed" : "external";
  // docs/CLOUD.md "C2-3", "C2-4": a Firebase project has two databases; the user picks which one.
  const [firebaseDb, setFirebaseDb] = useState<"firestore" | "rtdb">("firestore");
  const options = useQuery({
    queryKey: ["projects", projectId, "cloud", "databases", "options"],
    queryFn: () => api.cloud.databaseOptions(projectId),
    staleTime: Infinity,
  });
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

  // Placement ("Host on") for managed databases.
  const placement = usePlacementOptions(projectId);
  const [hostChoice, setHostChoice] = useState<string | null>(null);
  const engineForPlacement = engineForKind(kind);
  const hostDisplays = (placement.data ?? []).map((o) => placementDisplay(o, engineForPlacement));
  const chosenHost = hostDisplays.find((d) => d.value === hostChoice && !d.disabled);
  const hostValue = chosenHost ? chosenHost.value : defaultPlacement(placement.data ?? [], engineForPlacement);
  const hostUsable = hostDisplays.length === 0 || hostDisplays.some((d) => d.value === hostValue && !d.disabled);
  const showHostOn = mode === "managed" && (placement.isError || (placement.data?.length ?? 0) > 1);

  const buildInput = (): DataSourceInput => {
    const n = name.trim() || defaultName();
    if (mode === "managed") {
      const device_id = showHostOn ? deviceIdFromValue(hostValue) : undefined;
      return kind === "sql"
        ? { kind: "sql", mode: "managed", engine: "mariadb", name: n, device_id }
        : { kind: "nosql", mode: "managed", engine: "mongodb", name: n, device_id };
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
    if (where === "aws") return kind === "sql" ? "AWS database" : "DynamoDB";
    if (where === "firebase") return firebaseDb === "rtdb" ? "Realtime Database" : "Firestore";
    if (mode === "managed") return kind === "sql" ? "MariaDB" : "MongoDB";
    return kind === "sql" ? { mariadb: "MariaDB", mysql: "MySQL", postgresql: "PostgreSQL" }[engine] : "MongoDB";
  }

  const configKey = JSON.stringify(mode === "external" ? { ...buildInput(), name: "" } : null);
  const testPassed = mode === "managed" || (test?.key === configKey && test.result.ok);

  // A-117: the API defaults the database to the one named in the URI path (mongodb://host/<database>).
  const uriDatabase = /^mongodb(?:\+srv)?:\/\/[^/?]*\/([^?]+)/.exec(uri.trim())?.[1] ?? "";
  const externalValid =
    kind === "sql"
      ? Boolean(host.trim() && username.trim() && database.trim()) && (!port || /^\d+$/.test(port))
      : Boolean(uri.trim() && (mongoDb.trim() || uriDatabase));
  const formValid = mode === "managed" ? !showHostOn || hostUsable : externalValid;

  const testMutation = useMutation({
    mutationFn: () => api.dataSources.test(projectId, buildInput()),
    onSuccess: (result) => setTest({ key: configKey, result }),
    onError: (e) => setTest({ key: configKey, result: { ok: false, message: errorMessage(e), server_version: null } }),
  });

  const create = useMutation({
    mutationFn: () => api.dataSources.create(projectId, buildInput()),
    onSuccess: (source) => {
      invalidateProjectSources(queryClient, projectId);
      toast.success(`${source.name} added.`);
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (where !== "local" && where !== "external") return; // cloud databases have their own buttons
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
          {where === "external" && (
            <Button
              onClick={() => testMutation.mutate()}
              loading={testMutation.isPending}
              disabled={!externalValid || create.isPending}
            >
              Test connection
            </Button>
          )}
          {(where === "local" || where === "external") && (
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
          )}
        </>
      }
    >
      <form id="add-db" className="space-y-5" onSubmit={onSubmit}>
        <div>
          <p className="mb-2 text-sm font-medium">Type</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <Choice
              selected={kind === "sql"}
              onClick={() => {
                setKind("sql");
                if (where === "firebase") setWhere("local"); // Firebase databases are NoSQL
              }}
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
              description="JSON data: MongoDB (here or elsewhere), DynamoDB (in AWS), Cloud Firestore or Realtime Database (Firebase)."
              tone="nosql"
            />
          </div>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Where should it live?</p>
          {options.isPending ? (
            <p className="text-xs text-muted">Loading the options…</p>
          ) : options.isError ? (
            <Alert tone="danger">{errorMessage(options.error)}</Alert>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {options.data.locations.map((loc) => {
                const unavailable = loc.available === false || (loc.only !== undefined && loc.only !== kind);
                return (
                  <Choice
                    key={loc.id}
                    selected={where === loc.id}
                    onClick={() => setWhere(loc.id)}
                    disabled={unavailable}
                    icon={WHERE_ICONS[loc.id]}
                    title={loc.label}
                    description={loc.what}
                  >
                    <span className="mt-1 block text-xs text-muted">
                      <strong className="font-medium text-fg/80">PC off:</strong> {loc.when_pc_off}{" "}
                      <strong className="font-medium text-fg/80">Cost:</strong> {loc.cost}
                    </span>
                    {loc.note && <span className="mt-1 block text-xs font-medium text-accent">{loc.note}</span>}
                  </Choice>
                );
              })}
            </div>
          )}
        </div>

        {showHostOn && (
          <HostOnSelect
            options={placement.data}
            engine={engineForPlacement}
            value={hostValue}
            onChange={setHostChoice}
            loading={placement.isPending}
            error={placement.error}
          />
        )}

        <Field label="Display name" optional hint={`Defaults to “${defaultName()}”.`}>
          {(id) => <Input id={id} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />}
        </Field>

        {where === "aws" && options.data && (
          <AwsDatabaseSection
            key={kind}
            projectId={projectId}
            kind={kind}
            name={name.trim() || defaultName()}
            options={options.data.aws}
            dynamodb={options.data.dynamodb}
            onDone={onClose}
          />
        )}

        {where === "firebase" && kind === "nosql" && options.data && (
          <div>
            <p className="mb-2 text-sm font-medium">Which Firebase database?</p>
            <div className="grid gap-2 sm:grid-cols-2">
              <Choice
                selected={firebaseDb === "firestore"}
                onClick={() => setFirebaseDb("firestore")}
                icon={<FileJson className="size-4" />}
                title="Cloud Firestore"
                description={options.data.firestore.short}
              />
              <Choice
                selected={firebaseDb === "rtdb"}
                onClick={() => setFirebaseDb("rtdb")}
                icon={<Network className="size-4" />}
                title="Realtime Database"
                description={options.data.rtdb.short}
              />
            </div>
          </div>
        )}

        {where === "firebase" && kind === "nosql" && options.data && firebaseDb === "firestore" && (
          <FirestoreSection
            projectId={projectId}
            name={name.trim() || defaultName()}
            options={options.data.firestore}
            onDone={onClose}
          />
        )}

        {where === "firebase" && kind === "nosql" && options.data && firebaseDb === "rtdb" && (
          <RtdbSection projectId={projectId} name={name.trim() || defaultName()} options={options.data.rtdb} onDone={onClose} />
        )}

        {where === "external" && kind === "sql" && (
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
            <Field label="Host" className="sm:col-span-3" hint="On this PC? Use its network IP (ipconfig), not localhost.">
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

        {where === "external" && kind === "nosql" && (
          <div className="space-y-3">
            <Field label="Connection URI">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  value={uri}
                  onChange={(e) => setUri(e.target.value)}
                  placeholder="mongodb+srv://<user>:<password>@<cluster>.mongodb.net"
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
                  placeholder={uriDatabase ? `${uriDatabase} (from the URI)` : undefined}
                  autoCapitalize="off"
                  spellCheck={false}
                  required={!uriDatabase}
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

        {where === "external" && currentTest && (
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
        {where === "external" && !currentTest && (
          <p className="text-xs text-muted">Test the connection before saving.</p>
        )}
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
