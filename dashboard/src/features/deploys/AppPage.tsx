import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, ExternalLink, FileText, ListOrdered, Rocket, Settings, Square } from "lucide-react";
import { errorMessage, isApiError } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useApp, useDeployments } from "../../api/hooks";
import type { Deployment } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { PageSpinner } from "../../components/ui/Spinner";
import { Card, EmptyState, ErrorState } from "../../components/ui/States";
import { Tabs } from "../../components/ui/Tabs";
import { useToast } from "../../components/ui/toast-context";
import { useProjectContext } from "../projects/project-context";
import { AppSettings } from "./AppSettings";
import { BuildLog } from "./BuildLog";
import { DeploymentsTable } from "./DeploymentsTable";
import { AppStatusDot } from "./DeploysTab";
import { isActive, PRESETS } from "./deploys";
import { RuntimeLogs } from "./RuntimeLogs";

type Section = "deployments" | "logs" | "settings";

export function AppPage() {
  const { project, can } = useProjectContext();
  const { appId = "" } = useParams();
  const toast = useToast();
  const queryClient = useQueryClient();
  const deployments = useDeployments(project.id, appId);
  const list = deployments.data?.pages.flatMap((p) => p.deployments) ?? [];
  const active = list.find((d) => isActive(d.status)) ?? null;
  const app = useApp(project.id, appId, { poll: Boolean(active) });
  const [section, setSection] = useState<Section>("deployments");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Follow the running deployment unless the user picked another row.
  const selected = (selectedId && list.find((d) => d.id === selectedId)) || active || list[0] || null;

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: qk.deployments(project.id, appId) });
    void queryClient.invalidateQueries({ queryKey: qk.app(project.id, appId) });
  };
  const deploy = useMutation({
    mutationFn: () => api.apps.deploy(project.id, appId),
    onSuccess: (d) => {
      setSelectedId(d.id);
      setSection("deployments");
      refresh();
      toast.success("Deployment queued.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't start the deployment"),
  });
  const cancel = useMutation({
    mutationFn: (d: Deployment) => api.apps.cancel(project.id, appId, d.id),
    onSuccess: () => {
      refresh();
      toast.info("Cancellation requested.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't cancel"),
  });

  if (app.isPending) return <PageSpinner />;
  if (app.isError) {
    const missing = isApiError(app.error) && app.error.status === 404;
    return <ErrorState title={missing ? "App not found" : "Couldn't load app"} error={app.error} onRetry={missing ? undefined : () => void app.refetch()} />;
  }
  const a = app.data;
  const links = [...a.urls, a.local_url];

  return (
    <div className="space-y-4">
      <Link to={`/projects/${project.id}/deploys`} className="inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
        <ChevronLeft className="size-4" /> Apps
      </Link>
      <div className="flex flex-wrap items-center gap-2">
        <AppStatusDot app={a} active={Boolean(active)} />
        <h2 className="min-w-0 truncate text-lg font-semibold">{a.name}</h2>
        <Badge>{PRESETS[a.preset].label}</Badge>
        <Badge tone={a.live_deployment?.status === "live" ? "success" : "neutral"}>{a.live_deployment?.status === "live" ? "Live" : "Not live"}</Badge>
        {can("developer") && (
          <div className="ml-auto flex gap-2">
            {active && (
              <Button icon={<Square className="size-4" />} loading={cancel.isPending} onClick={() => cancel.mutate(active)}>
                Cancel
              </Button>
            )}
            <Button variant="primary" icon={<Rocket className="size-4" />} loading={deploy.isPending} onClick={() => deploy.mutate()}>
              Deploy now
            </Button>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {links.map((u) => (
          <a key={u} href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono text-xs text-accent hover:underline">
            {u.replace(/^https?:\/\//, "")}
            <ExternalLink className="size-3" />
          </a>
        ))}
      </div>

      <Tabs<Section>
        value={section}
        onChange={setSection}
        items={[
          { value: "deployments", label: "Deployments", icon: <ListOrdered className="size-4" /> },
          { value: "logs", label: "Runtime logs", icon: <FileText className="size-4" /> },
          { value: "settings", label: "Settings", icon: <Settings className="size-4" /> },
        ]}
      />

      {section === "deployments" &&
        (deployments.isPending ? (
          <PageSpinner />
        ) : deployments.isError ? (
          <ErrorState error={deployments.error} onRetry={() => void deployments.refetch()} />
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Rocket className="size-5" />}
            title="Not deployed yet"
            description={can("developer") ? "Deploy now to clone, build and start the app." : "Nothing has been deployed."}
          />
        ) : (
          <div className="space-y-4">
            {selected && (
              <Card title="Build log" bodyClassName="px-3 py-3">
                <BuildLog key={selected.id} projectId={project.id} appId={appId} deployment={selected} />
              </Card>
            )}
            <DeploymentsTable projectId={project.id} appId={appId} deployments={list} selectedId={selected?.id ?? null} onSelect={(d) => setSelectedId(d.id)} canDeploy={can("developer")} />
            {deployments.hasNextPage && (
              <div className="flex justify-center">
                <Button size="sm" loading={deployments.isFetchingNextPage} onClick={() => void deployments.fetchNextPage()}>
                  Load older
                </Button>
              </div>
            )}
          </div>
        ))}
      {section === "logs" && <RuntimeLogs projectId={project.id} appId={appId} />}
      {section === "settings" && <AppSettings projectId={project.id} app={a} canEdit={can("developer")} isAdmin={can("admin")} />}
    </div>
  );
}
