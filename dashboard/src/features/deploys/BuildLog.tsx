import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Pause, Play } from "lucide-react";
import { qk } from "../../api/endpoints";
import { useDeployment } from "../../api/hooks";
import type { Deployment } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { formatDuration } from "../../lib/format";
import { DeploymentStatusBadge } from "./DeploymentsTable";
import { deploymentDuration, isActive, shortSha } from "./deploys";

/** Follows one deployment: polls `?log=1` every 2 s while it runs, auto-scrolls unless paused. */
export function BuildLog({ projectId, appId, deployment }: { projectId: string; appId: string; deployment: Deployment }) {
  const queryClient = useQueryClient();
  const q = useDeployment(projectId, appId, deployment.id, { poll: true });
  const d = q.data ?? deployment;
  const [paused, setPaused] = useState(false);
  const pre = useRef<HTMLPreElement>(null);
  const wasActive = useRef(isActive(d.status));

  useEffect(() => {
    if (!paused && pre.current) pre.current.scrollTop = pre.current.scrollHeight;
  }, [d.log, paused]);

  // When the deployment settles, refresh the app (live badge, URLs) and the list once.
  useEffect(() => {
    const active = isActive(d.status);
    if (wasActive.current && !active) {
      void queryClient.invalidateQueries({ queryKey: qk.app(projectId, appId) });
      void queryClient.invalidateQueries({ queryKey: qk.deployments(projectId, appId) });
    }
    wasActive.current = active;
  }, [d.status, projectId, appId, queryClient]);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <DeploymentStatusBadge status={d.status} />
        <span className="font-mono text-xs">{shortSha(d.commit_sha)}</span>
        {d.commit_message && <span className="min-w-0 flex-1 truncate text-muted">{d.commit_message}</span>}
        <span className="ml-auto text-xs text-muted">{formatDuration(deploymentDuration(d))}</span>
        {isActive(d.status) && (
          <Button size="sm" variant="ghost" icon={paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />} onClick={() => setPaused((p) => !p)}>
            {paused ? "Follow" : "Pause"}
          </Button>
        )}
      </div>
      {q.isError && <ErrorAlert error={q.error} />}
      <pre
        ref={pre}
        className="max-h-96 min-h-24 overflow-auto rounded-xl border border-border bg-surface-2 p-3 font-mono text-xs leading-5 whitespace-pre-wrap break-words"
        aria-live="polite"
        aria-label="Build log"
      >
        {d.log ||
          (q.isPending ? (
            <span className="inline-flex items-center gap-2 text-muted">
              <Spinner className="size-3.5" /> Loading log…
            </span>
          ) : (
            <span className="text-muted">{d.status === "queued" ? "Waiting for the worker…" : "No output."}</span>
          ))}
      </pre>
      {d.error && (
        <Alert tone="danger" title="Deployment failed">
          {d.error}
        </Alert>
      )}
    </div>
  );
}
