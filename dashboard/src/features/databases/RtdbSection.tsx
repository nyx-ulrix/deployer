import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Database, Plug } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { invalidateProjectSources } from "../../api/hooks";
import type { CloudDatabaseOptions } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Checkbox, Field, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { Choice } from "./Choice";

/** docs/CLOUD.md "C2-4": connect a Firebase project's Realtime Database, or create the project's default one when it
 * has none (billed by use beyond the free quota, so the cost box must be ticked). */
export function RtdbSection({
  projectId,
  name,
  options,
  onDone,
}: {
  projectId: string;
  name: string;
  options: CloudDatabaseOptions["rtdb"];
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
  const [chosen, setChosen] = useState("");
  const [location, setLocation] = useState(options.locations[0]?.id ?? "us-central1");
  const [agreed, setAgreed] = useState(false);
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
  const instances = listing.data?.rtdb ?? [];
  const instance = chosen || instances.find((i) => !i.problem)?.id || "";
  const connect = useMutation({
    mutationFn: () => api.cloud.connectDatabase(projectId, { connection_id: connectionId, name, instance }),
    onSuccess: (source) => done(`${source.name} connected.`),
  });
  const create = useMutation({
    mutationFn: () =>
      api.cloud.createDatabase(projectId, { connection_id: connectionId, name, engine: "firebase_rtdb", location, confirm_billing: agreed }),
    onSuccess: (out) => done(`${out.data_source.name} is ready in your Firebase project.`),
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

  const hasDefault = instances.some((i) => i.type === "DEFAULT_DATABASE");
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
      <Alert tone="info" title="What is the Realtime Database?">
        {options.what}
      </Alert>
      <p className="text-xs text-muted">{options.connect}</p>
      {listing.isPending ? (
        <p className="text-xs text-muted">Looking up the project&apos;s Realtime Databases…</p>
      ) : listing.isError ? (
        <ErrorState error={listing.error} onRetry={() => void listing.refetch()} />
      ) : listing.data.rtdb_problem ? (
        <Alert tone="warning" title="Couldn't list the Realtime Databases">
          {listing.data.rtdb_problem} The Firebase service account needs the Firebase Realtime Database Admin role and the
          Firebase Realtime Database Management API turned on (Settings → Cloud accounts shows how).
        </Alert>
      ) : (
        instances.length > 0 && (
          <div className="grid gap-2">
            {instances.map((i) => (
              <Choice
                key={i.id}
                selected={instance === i.id}
                disabled={Boolean(i.problem)}
                onClick={() => setChosen(i.id)}
                icon={<Database className="size-4" />}
                title={i.id}
                description={i.problem ?? `${i.url ?? ""} · ${i.location ?? ""}${i.type === "DEFAULT_DATABASE" ? " · the default database" : ""}`}
              />
            ))}
          </div>
        )
      )}
      <Alert tone="info" title="How apps and this PC reach it">
        {options.network}
      </Alert>
      {listing.isSuccess && !listing.data.rtdb_problem && !hasDefault ? (
        <div className="space-y-3 rounded-xl border border-border p-3">
          <p className="text-sm font-medium">
            {instances.length ? "Or create the project's default database" : "This project has no Realtime Database yet: create its default one"}
          </p>
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
          <Alert tone="warning" title="Google bills what it stores and sends">
            {options.cost}
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
      ) : (
        <Alert tone="warning" title="Google bills what it stores and sends">
          {options.cost}
        </Alert>
      )}
      {connect.error && <Alert tone="danger">{errorMessage(connect.error)}</Alert>}
      {instances.length > 0 && (
        <div className="flex justify-end">
          <Button variant="primary" icon={<Plug className="size-4" />} loading={connect.isPending} disabled={!instance} onClick={() => connect.mutate()}>
            Connect database
          </Button>
        </div>
      )}
    </div>
  );
}
