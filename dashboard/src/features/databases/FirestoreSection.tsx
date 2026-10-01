import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plug } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { invalidateProjectSources } from "../../api/hooks";
import type { CloudDatabaseOptions } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";

/** docs/CLOUD.md "C2-3": connect the Cloud Firestore database of a Firebase project the project may use. Connecting
 * creates nothing (so there is no billing box); Google bills reads and writes, which the cost note says. */
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
  const connect = useMutation({
    mutationFn: () => api.cloud.connectDatabase(projectId, { connection_id: connectionId, name, database: database.trim() }),
    onSuccess: (source) => {
      invalidateProjectSources(queryClient, projectId);
      toast.success(`${source.name} connected.`);
      onDone();
    },
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
        <Alert tone="info">
          This Firebase project has no Firestore database yet. Create one in the{" "}
          <a href="https://console.firebase.google.com/" target="_blank" rel="noreferrer" className="underline">
            Firebase console
          </a>{" "}
          (Build → Firestore Database → Create database), then connect it here.
        </Alert>
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
    </div>
  );
}
