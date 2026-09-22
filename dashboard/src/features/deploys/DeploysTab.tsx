import { useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Plus, Rocket } from "lucide-react";
import { useApps } from "../../api/hooks";
import type { App } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { StatusDot } from "../../components/ui/Progress";
import { PageSpinner } from "../../components/ui/Spinner";
import { EmptyState, ErrorState } from "../../components/ui/States";
import { relativeTime } from "../../lib/format";
import { useProjectContext } from "../projects/project-context";
import { isActive, PRESETS } from "./deploys";
import { NewAppDialog } from "./NewAppDialog";

/** Live status: green when routed, amber pulse while a deploy runs, grey otherwise. */
export function AppStatusDot({ app, active = false }: { app: App; active?: boolean }) {
  const live = app.live_deployment?.status === "live";
  const busy = active || isActive(app.live_deployment?.status);
  return <StatusDot tone={busy ? "warning" : live ? "success" : "muted"} pulse={busy} />;
}

export function DeploysTab() {
  const { project, can } = useProjectContext();
  const apps = useApps(project.id);
  const [creating, setCreating] = useState(false);
  const base = `/projects/${project.id}/deploys`;

  const newApp = can("developer") && (
    <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
      New app
    </Button>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted">
          Apps are built from a Git repository and run on this PC next to the project's databases. Push to deploy, roll back
          in one click.
        </p>
        {newApp}
      </div>

      {apps.isPending ? (
        <PageSpinner />
      ) : apps.isError ? (
        <ErrorState error={apps.error} onRetry={() => void apps.refetch()} />
      ) : apps.data.length === 0 ? (
        <EmptyState
          icon={<Rocket className="size-5" />}
          title="No apps yet"
          description={can("developer") ? "Connect a repository to build and run it here." : "A developer or admin can add the first app."}
          action={newApp || undefined}
        />
      ) : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
          {apps.data.map((a) => (
            <li key={a.id}>
              <Link to={`${base}/${a.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 hover:bg-surface-2">
                <AppStatusDot app={a} />
                <span className="min-w-0 flex-1 basis-40 truncate font-medium">{a.name}</span>
                <Badge>{PRESETS[a.preset].label}</Badge>
                <span className="truncate font-mono text-xs text-muted">{a.branch}</span>
                <span className="basis-full text-xs text-muted sm:basis-auto sm:ml-auto">
                  {a.live_deployment ? `Deployed ${relativeTime(a.live_deployment.finished_at ?? a.live_deployment.created_at)}` : "Never deployed"}
                </span>
                <a
                  href={a.urls[0] ?? a.local_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex items-center gap-1 font-mono text-xs text-accent hover:underline"
                >
                  {(a.urls[0] ?? a.local_url).replace(/^https?:\/\//, "")}
                  <ExternalLink className="size-3" />
                </a>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {creating && <NewAppDialog projectId={project.id} isAdmin={can("admin")} onClose={() => setCreating(false)} />}
    </div>
  );
}
