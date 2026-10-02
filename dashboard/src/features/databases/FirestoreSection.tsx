import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Database, Plug } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { invalidateProjectSources } from "../../api/hooks";
import type { CloudDatabaseOptions } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";

/** docs/CLOUD.md "C2-3": connect the Cloud Firestore database of a Firebase project the project may use (free, so no
 * billing box; Google bills reads and writes, which the cost note says), or create a new one ("Firestore backups":
 * billable, so the cost box). */
export function FirestoreSection({
  projectId,
  name,
  options,
  onDone,
}: {
  projectId: string;
  name: string;
  options: CloudDatabaseOptions["firestore"];
  onDone: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const connections = useQuery({
    queryKey: qk.projectCloudConnections(projectId),
    queryFn: () => api.cloud.projectConnections(projectId),
  });
  const firebase = (connections.data ?? []).filter((c) => c.provider === "firebase" && c.status === "ok");
  const [chosenConnection, setConnectionId] = useState("");
  const connectionId = chosenConnection || firebase[0]?.id || "";
  const [database, setDatabase] = useState("(default)");
  const listing = useQuery({
    queryKey: ["projects", projectId, "cloud", "connections", connectionId, "databases"],
    queryFn: () => api.cloud.connectionDatabases(projectId, connectionId),
    enabled: Boolean(connectionId),
  });
  const done = (message: string) => {
    invalidateProjectSources(queryClient, projectId);
    toast.success(message);
    onDone();
  };
  const connect = useMutation({
    mutationFn: () => api.cloud.connectDatabase(projectId, { connection_id: connectionId, name, database: database.trim() }),
    onSuccess: (source) => done(`${source.name} connected.`),
  });
  // docs/CLOUD.md "Firestore backups": a new database in the project (billable once used, so the cost box).
  const [location, setLocation] = useState(options.locations[0]?.id ?? "nam5");
  const [newId, setNewId] = useState("");
  const [agreed, setAgreed] = useState(false);
  const create = useMutation({
    mutationFn: () =>
      api.cloud.createDatabase(projectId, {
        connection_id: connectionId,
        name,
        engine: "firestore",
        location,
        database: newId.trim() || undefined,
        confirm_billing: agreed,
      }),
    onSuccess: (out) => done(`${out.data_source.name} is being created in your Firebase project (about a minute).`),
  });

  if (connections.isPending) return <PageSpinner />;
  if (connections.isError) return <ErrorState error={connections.error} onRetry={() => void connections.refetch()} />;
  if (firebase.length === 0) {
    return (
      <Alert tone="info" title="No Firebase project connected yet">
        The instance owner connects one in{" "}
        <Link to="/settings/cloud" className="underline">
          Settings → Cloud accounts
        </Link>{" "}
        (a step-by-step guide shows exactly what to turn on in Google Cloud). Then come back here.
      </Alert>
    );
  }

  const found = listing.data?.firestore ?? [];
  const picked = found.find((d) => d.id === database.trim());
  return (
    <div className="space-y-4">
      {firebase.length > 1 && (
        <Field label="Firebase project">
          {(id) => (
            <Select id={id} value={connectionId} onChange={(e) => setConnectionId(e.target.value)}>
              {firebase.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.account.project_id})
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      <Alert tone="info" title="What is Cloud Firestore?">
        {options.what}
      </Alert>
      <p className="text-xs text-muted">{options.connect}</p>
      <Field
        label="Database"
        hint={
          listing.isPending
            ? "Looking up the project's databases…"
            : found.length
              ? `In this project: ${found.map((d) => d.id).join(", ")}.`
              : "Most projects have one database, called (default)."
        }
      >
        {(id) => (
          <>
            <Input
              id={id}
              list="firestore-databases"
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
              spellCheck={false}
              autoCapitalize="off"
            />
            <datalist id="firestore-databases">
              {found.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.location ?? ""}
                </option>
              ))}
            </datalist>
          </>
        )}
      </Field>
      {listing.data?.firestore_problem && (
        <Alert tone="warning" title="Couldn't list the databases">
          {listing.data.firestore_problem} You can still type the database id. If connecting fails too, the service account
          may need the Cloud Datastore User role and the Cloud Firestore API (Settings → Cloud accounts).
        </Alert>
      )}
      {picked?.problem && <Alert tone="danger">{picked.problem}</Alert>}
      {listing.isSuccess && !listing.data.firestore_problem && found.length === 0 && (
        <Alert tone="info">This Firebase project has no Firestore database yet: create one below.</Alert>
      )}
      <Alert tone="info" title="How apps and this PC reach it">
        {options.network}
      </Alert>
      <Alert tone="warning" title="Google bills reads and writes">
        {options.cost}
      </Alert>
      {connect.error && <Alert tone="danger">{errorMessage(connect.error)}</Alert>}
      <div className="flex justify-end">
        <Button
          variant="primary"
          icon={<Plug className="size-4" />}
          loading={connect.isPending}
          disabled={!connectionId || !database.trim() || Boolean(picked?.problem)}
          onClick={() => connect.mutate()}
        >
          Connect database
        </Button>
      </div>
      <div className="space-y-3 rounded-xl border border-border p-3">
        <p className="text-sm font-medium">Or create a new Firestore database</p>
        <Field label="Location" hint="Pick the one nearest your users; it can't be changed later.">
          {(id) => (
            <Select id={id} value={location} onChange={(e) => setLocation(e.target.value)}>
              {options.locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label} ({l.id})
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Database id" optional hint="Lowercase letters, digits and hyphens. Empty: Deployer picks one (deployer-…).">
          {(id) => <Input id={id} value={newId} onChange={(e) => setNewId(e.target.value)} spellCheck={false} autoCapitalize="off" />}
        </Field>
        <Alert tone="warning" title="Google bills what it stores and reads">
          {options.create_cost}
          <Checkbox
            className="mt-2"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            label="I understand Google may charge my Firebase project for this database"
          />
        </Alert>
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
        <div className="flex justify-end">
          <Button
            variant="primary"
            icon={<Database className="size-4" />}
            loading={create.isPending}
            disabled={!agreed || !connectionId}
            title={agreed ? undefined : "Tick the cost box first"}
            onClick={() => create.mutate()}
          >
            Create in Firebase
          </Button>
        </div>
      </div>
    </div>
  );
}
