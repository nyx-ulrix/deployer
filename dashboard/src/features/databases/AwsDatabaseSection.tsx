import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Database, Plug, Plus } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { invalidateProjectSources } from "../../api/hooks";
import type { CloudDatabaseOptions, SqlExternalEngine } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { engineLabel } from "../../lib/format";
import { Choice } from "./Choice";

/** docs/CLOUD.md "C2": a database in the project's AWS account, created new (billable, confirmed) or connected. */
export function AwsDatabaseSection({
  projectId,
  name,
  options,
  onDone,
}: {
  projectId: string;
  name: string;
  options: CloudDatabaseOptions["aws"];
  onDone: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const connections = useQuery({
    queryKey: qk.projectCloudConnections(projectId),
    queryFn: () => api.cloud.projectConnections(projectId),
  });
  const aws = (connections.data ?? []).filter((c) => c.provider === "aws" && c.status === "ok");
  const [chosenConnection, setConnectionId] = useState("");
  const connectionId = chosenConnection || aws[0]?.id || "";
  const [action, setAction] = useState<"create" | "connect">("create");
  // Create
  const [engine, setEngine] = useState<SqlExternalEngine>("mysql");
  const [instanceClass, setInstanceClass] = useState(options.default_instance_class);
  const [agreed, setAgreed] = useState(false);
  // Connect
  const [resourceId, setResourceId] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [database, setDatabase] = useState("");

  const listing = useQuery({
    queryKey: ["projects", projectId, "cloud", "connections", connectionId, "databases"],
    queryFn: () => api.cloud.connectionDatabases(projectId, connectionId),
    enabled: action === "connect" && Boolean(connectionId),
  });

  const done = (message: string) => {
    invalidateProjectSources(queryClient, projectId);
    toast.success(message);
    onDone();
  };
  const create = useMutation({
    mutationFn: () =>
      api.cloud.createDatabase(projectId, {
        connection_id: connectionId,
        name,
        engine,
        instance_class: instanceClass,
        confirm_billing: agreed,
      }),
    onSuccess: (out) => done(`${out.data_source.name} is being created in AWS. This takes 5-15 minutes.`),
  });
  const connect = useMutation({
    mutationFn: () =>
      api.cloud.connectDatabase(projectId, {
        connection_id: connectionId,
        name,
        resource_id: resourceId,
        username: username.trim(),
        password,
        database: database.trim() || undefined,
      }),
    onSuccess: (source) => done(`${source.name} connected.`),
  });

  if (connections.isPending) return <PageSpinner />;
  if (connections.isError) return <ErrorState error={connections.error} onRetry={() => void connections.refetch()} />;
  if (aws.length === 0) {
    return (
      <Alert tone="info" title="No AWS account connected yet">
        The instance owner connects one in{" "}
        <Link to="/settings/cloud" className="underline">
          Settings → Cloud accounts
        </Link>{" "}
        (a step-by-step guide shows exactly what to create in AWS). Then come back here.
      </Alert>
    );
  }

  const picked = listing.data?.databases.find((d) => d.id === resourceId);
  return (
    <div className="space-y-4">
      {aws.length > 1 && (
        <Field label="AWS account">
          {(id) => (
            <Select id={id} value={connectionId} onChange={(e) => setConnectionId(e.target.value)}>
              {aws.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.account.account_id}, {c.account.region})
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <Choice
          selected={action === "create"}
          onClick={() => setAction("create")}
          icon={<Plus className="size-4" />}
          title="Create a new database"
          description="AWS sets up a new MySQL, MariaDB or PostgreSQL server for you, with daily backups."
        />
        <Choice
          selected={action === "connect"}
          onClick={() => setAction("connect")}
          icon={<Plug className="size-4" />}
          title="Connect one you already have"
          description="Pick an RDS or Aurora database that is already in this AWS account."
        />
      </div>

      {action === "create" ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Engine" hint="Not sure? MySQL works with most website tools.">
              {(id) => (
                <Select id={id} value={engine} onChange={(e) => setEngine(e.target.value as SqlExternalEngine)}>
                  {options.engines.map((en) => (
                    <option key={en} value={en}>
                      {engineLabel(en)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Size" hint={options.instance_classes.find((c) => c.id === instanceClass)?.description}>
              {(id) => (
                <Select id={id} value={instanceClass} onChange={(e) => setInstanceClass(e.target.value)}>
                  {options.instance_classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <p className="text-xs text-muted">
            {options.storage_gb} GB of storage, backups kept {options.backup_days} days, protected against accidental
            deletion, encrypted. It keeps running when this PC is off.
          </p>
          <Alert tone="info" title="How apps and this PC reach it">
            {options.network}
          </Alert>
          <Alert tone="warning" title="AWS bills you for this">
            {options.cost}
            <Checkbox
              className="mt-2"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              label="I understand AWS charges my account for this database"
            />
          </Alert>
          {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
          <div className="flex justify-end">
            <Button
              variant="primary"
              icon={<Database className="size-4" />}
              loading={create.isPending}
              disabled={!agreed || !connectionId}
              onClick={() => create.mutate()}
              title={agreed ? undefined : "Tick the cost box first"}
            >
              Create in AWS
            </Button>
          </div>
        </div>
      ) : listing.isPending ? (
        <PageSpinner />
      ) : listing.isError ? (
        <ErrorState error={listing.error} onRetry={() => void listing.refetch()} />
      ) : (
        <div className="space-y-3">
          {listing.data.databases.length === 0 ? (
            <Alert tone="info">No RDS or Aurora databases in {listing.data.region} yet. Create a new one instead.</Alert>
          ) : (
            <div className="grid gap-2">
              {listing.data.databases.map((d) => (
                <Choice
                  key={d.id}
                  selected={resourceId === d.id}
                  disabled={Boolean(d.problem)}
                  onClick={() => {
                    setResourceId(d.id);
                    setUsername(d.username ?? "");
                    setDatabase(d.database ?? "");
                  }}
                  icon={<Database className="size-4" />}
                  title={`${d.id} (${d.kind === "cluster" ? "Aurora cluster" : "instance"})`}
                  description={d.problem ?? `${d.engine} · ${d.status ?? "unknown"} · ${d.host}:${d.port}`}
                />
              ))}
            </div>
          )}
          <p className="text-xs text-muted">
            Deployer only connects to it; it never changes that database or its firewall. Its security group must allow
            port {picked?.port ?? "3306 / 5432"} from this PC{listing.data.pc_ip ? ` (${listing.data.pc_ip})` : ""}.
          </p>
          {picked && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Database user">
                {(id) => (
                  <Input id={id} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" spellCheck={false} />
                )}
              </Field>
              <Field label="Password">
                {(id) => (
                  <Input id={id} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
                )}
              </Field>
              <Field label="Database name">
                {(id) => (
                  <Input id={id} value={database} onChange={(e) => setDatabase(e.target.value)} spellCheck={false} />
                )}
              </Field>
            </div>
          )}
          {connect.error && <Alert tone="danger">{errorMessage(connect.error)}</Alert>}
          <div className="flex justify-end">
            <Button
              variant="primary"
              icon={<Plug className="size-4" />}
              loading={connect.isPending}
              disabled={!picked || !username.trim()}
              onClick={() => connect.mutate()}
            >
              Connect
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
