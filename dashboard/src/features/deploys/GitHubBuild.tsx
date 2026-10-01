import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cloud, ExternalLink, GitBranch, Monitor, RefreshCw } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { App, GitHubRun } from "../../api/types";
import { Badge, type BadgeTone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Checkbox } from "../../components/ui/Input";
import { Alert, Card } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { relativeTime } from "../../lib/format";
import { JobProgressPanel } from "../jobs/JobProgress";
import { BUILD_LOCATIONS, shortSha } from "./deploys";

type Location = keyof typeof BUILD_LOCATIONS;

/**
 * docs/CLOUD.md "C3" - "Where it builds" for a cloud app: this PC, or GitHub Actions (a workflow in the
 * repository builds every push and deploys it straight to the cloud, also while this PC is off).
 */
export function BuildCard({ projectId, app, isAdmin }: { projectId: string; app: App; isAdmin: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const build = app.build;
  const [choosing, setChoosing] = useState<Location | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (location: Location) => api.apps.setBuild(projectId, app.id, location, location === "github" && agreed),
    onSuccess: ({ job_id, ...updated }) => {
      queryClient.setQueryData(qk.app(projectId, app.id), updated);
      setChoosing(null);
      setAgreed(false);
      setJobId(job_id);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't change where it builds"),
  });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: qk.app(projectId, app.id) });
  const current: Location = build.location;
  const github = build.location === "github" ? build : null;
  const runningJob = jobId ?? (github?.status === "setting_up" ? github.job_id : null);

  return (
    <Card
      title="Where it builds"
      description="The app always serves from the cloud. This is only about who turns your code into the published app after a push."
    >
      <div className="grid gap-2 sm:grid-cols-2">
        {(Object.keys(BUILD_LOCATIONS) as Location[]).map((loc) => {
          const o = BUILD_LOCATIONS[loc];
          const active = current === loc;
          return (
            <div key={loc} className={cn("flex flex-col gap-1 rounded-xl border p-3 text-sm", active ? "border-accent bg-accent-soft/40" : "border-border bg-surface")}>
              <span className="flex flex-wrap items-center gap-2">
                {loc === "pc" ? <Monitor className="size-4 text-muted" /> : <GitBranch className="size-4 text-muted" />}
                <span className="font-medium">{o.label}</span>
                {active && <Badge tone="accent">Current</Badge>}
              </span>
              <span className="text-xs text-muted">{o.what}</span>
              <span className={cn("text-xs", loc === "github" ? "text-success" : "text-muted")}>{o.whenPcOff}</span>
              <span className="text-xs text-muted">
                <span className="text-fg">Cost:</span> {o.cost}
              </span>
              {isAdmin && !active && (
                <div className="mt-1">
                  <Button size="sm" onClick={() => setChoosing(loc)} disabled={Boolean(runningJob)}>
                    Build on {o.label}
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {!isAdmin && <p className="mt-2 text-xs text-muted">Only project admins can change where an app builds.</p>}

      {github && (
        <div className="mt-3 space-y-2 text-sm">
          {github.status === "ready" && (
            <p className="text-muted">
              Every push to <code className="font-mono">{app.branch}</code> is built by GitHub and deployed to{" "}
              {app.cloud?.connection_name ?? "the cloud"}. Workflow:{" "}
              {github.workflow_url && (
                <a href={github.workflow_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono text-xs text-accent hover:underline">
                  {github.workflow_path}
                  <ExternalLink className="size-3" />
                </a>
              )}
              . Environment variables you change here reach the app with the next <strong>Rollback</strong> to the live deployment (GitHub
              never sees them).
            </p>
          )}
          {github.message && <Alert tone={github.status === "error" ? "danger" : "info"}>{github.message}</Alert>}
          {github.status === "error" && isAdmin && (
            <Button size="sm" icon={<RefreshCw className="size-3.5" />} onClick={() => setChoosing("github")}>
              Set up again
            </Button>
          )}
        </div>
      )}
      {runningJob && (
        <JobProgressPanel
          projectId={projectId}
          jobId={runningJob}
          title={current === "github" ? "Setting up GitHub Actions" : "Removing the GitHub Actions setup"}
          onFinished={(job) => {
            setJobId(null);
            refresh();
            if (job.status === "succeeded") toast.success(current === "github" ? "GitHub Actions builds are ready." : "Builds happen on this PC again.");
          }}
          className="mt-3"
        />
      )}

      <ConfirmDialog
        open={choosing === "github"}
        onClose={() => setChoosing(null)}
        onConfirm={() => change.mutate("github")}
        loading={change.isPending}
        destructive={false}
        disabled={!agreed}
        title="Build on GitHub Actions?"
        description="Deployer will:"
        confirmLabel="Set it up"
      >
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          <li>
            add a workflow file to <span className="font-mono">{app.repo_url.replace("https://github.com/", "")}</span> (a commit on{" "}
            <code className="font-mono">{app.branch}</code>, made with your GitHub connection) - GitHub runs it on every push, starting
            with this commit;
          </li>
          <li>
            <Cloud className="mr-1 inline size-3.5" />
            {app.cloud?.provider === "aws"
              ? "create an IAM role in your AWS account that only this repository's branch can use, allowed to update only this app;"
              : `add a workload identity provider to your Google project that only this repository's branch can use. The workflow then signs in as Deployer's service account, with all the access Deployer has to your Firebase project, so anyone who can push to ${app.branch} gets that access too;`}
          </li>
          <li>stop building pushes on this PC (rollbacks still run here).</li>
        </ul>
        <Alert tone="warning" className="mt-3">
          {BUILD_LOCATIONS.github.cost}
        </Alert>
        <div className="mt-3">
          <Checkbox label="I understand GitHub may bill build minutes" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        </div>
      </ConfirmDialog>
      <ConfirmDialog
        open={choosing === "pc"}
        onClose={() => setChoosing(null)}
        onConfirm={() => change.mutate("pc")}
        loading={change.isPending}
        destructive={false}
        title="Build on this PC again?"
        description="The workflow file is deleted from the repository (a commit) and the sign-in Deployer made for it is removed. The app keeps serving; pushes are built here again."
        confirmLabel="Build on this PC"
      />
    </Card>
  );
}

const RUN_TONE: Record<string, BadgeTone> = { success: "success", failure: "danger", cancelled: "neutral", timed_out: "danger" };

function runBadge(run: GitHubRun): { label: string; tone: BadgeTone } {
  if (run.status !== "completed") return { label: run.status.replace("_", " "), tone: "info" };
  return { label: run.conclusion ?? "done", tone: RUN_TONE[run.conclusion ?? ""] ?? "neutral" };
}

/** The workflow's runs from the GitHub API (also those while this PC was off), next to the deployments. */
export function GitHubRuns({ projectId, app }: { projectId: string; app: App }) {
  const runs = useQuery({
    queryKey: qk.githubRuns(projectId, app.id),
    queryFn: () => api.apps.githubRuns(projectId, app.id),
    refetchInterval: (q) => (q.state.data?.runs.some((r) => r.status !== "completed") ? 10_000 : 60_000),
    retry: false,
  });
  return (
    <Card
      title="GitHub Actions runs"
      description="Builds on GitHub, newest first. A run that finished while this PC was off shows here but not in the deployments below."
      actions={
        runs.data?.runs_url ? (
          <a href={runs.data.runs_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
            All runs <ExternalLink className="size-3" />
          </a>
        ) : undefined
      }
    >
      {runs.isError ? (
        <p className="text-sm text-danger">{errorMessage(runs.error)}</p>
      ) : (runs.data?.runs ?? []).length === 0 ? (
        <p className="text-sm text-muted">{runs.isPending ? "Loading…" : "No runs yet. Push to the branch or press Deploy now."}</p>
      ) : (
        <ul className="divide-y divide-border">
          {runs.data?.runs.map((r) => {
            const badge = runBadge(r);
            return (
              <li key={`${r.id}-${r.attempt}`} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <Badge tone={badge.tone}>{badge.label}</Badge>
                <span className="font-mono text-xs">{shortSha(r.sha)}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted" title={r.message ?? undefined}>
                  {r.message}
                </span>
                {r.created_at && <span className="text-xs text-muted">{relativeTime(r.created_at)}</span>}
                {r.url && (
                  <a href={r.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                    Log <ExternalLink className="size-3" />
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
