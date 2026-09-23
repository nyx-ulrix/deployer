import { useDeferredValue, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, GitBranch, Lock, Rocket, Search } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { AppDetectDraft, GitHubRepo } from "../../api/types";
import { GitHubIcon } from "../../components/layout/Brand";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { relativeTime } from "../../lib/format";
import { AppFormFields } from "./AppForm";
import {
  detectedSummary,
  draftErrors,
  draftFromDetect,
  draftToInput,
  emptyDraft,
  filterRepos,
  seedEnv,
  unfilledKeys,
  type AppDraft,
  type EnvRow,
} from "./deploys";
import { EnvEditor } from "./EnvEditor";
import { ConnectGitHubButton } from "./GitHubConnect";

/**
 * docs/DEPLOYMENTS.md "Connect a Git repository": step 1 picks a repository (connected GitHub account
 * or a pasted URL), `POST /apps/detect` pre-fills step 2, which stays fully editable.
 */
export function NewAppDialog({ projectId, isAdmin, onClose }: { projectId: string; isAdmin: boolean; onClose: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<"repo" | "configure">("repo");
  const [draft, setDraft] = useState<AppDraft>(emptyDraft);
  const [env, setEnv] = useState<EnvRow[]>([]);
  const [detected, setDetected] = useState<AppDetectDraft | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const errors = submitted ? draftErrors(draft) : {};

  const detect = useMutation({
    mutationFn: (src: { url: string; viaConnection: boolean }) => api.apps.detect(projectId, src.url),
    onSuccess: (d, src) => {
      setDetected(d);
      setDraft(draftFromDetect(d, src.viaConnection && d.private !== null, isAdmin));
      setEnv(seedEnv(d.env_keys, []));
      setSubmitted(false);
      setStep("configure");
    },
  });

  const createAndDeploy = useMutation({
    mutationFn: async () => {
      const app = await api.apps.create(projectId, draftToInput(draft, env));
      void queryClient.invalidateQueries({ queryKey: qk.apps(projectId) });
      try {
        await api.apps.deploy(projectId, app.id);
      } catch (e) {
        toast.error(errorMessage(e), "App created, but the deployment didn't start");
      }
      return app;
    },
    onSuccess: (app) => {
      for (const w of app.warnings) toast.info(w, "Set up by hand");
      toast.success(`“${app.name}” created — first deployment queued.`);
      void navigate(`/projects/${projectId}/deploys/${app.id}`);
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(draftErrors(draft)).length === 0) createAndDeploy.mutate();
  };

  if (step === "repo") {
    return (
      <Dialog open onClose={onClose} title="New app" description="Choose a repository. Deployer reads it and fills in the build settings for you." size="lg" dismissible={!detect.isPending}>
        <RepoStep
          projectId={projectId}
          busy={detect.isPending}
          error={detect.isError ? errorMessage(detect.error) : null}
          onPick={(url, viaConnection) => detect.mutate({ url, viaConnection })}
          onManual={() => {
            setDraft(emptyDraft());
            setDetected(null);
            setEnv([]);
            setStep("configure");
          }}
        />
      </Dialog>
    );
  }

  const summary = detected ? detectedSummary(detected) : null;
  const missing = detected ? unfilledKeys(detected.env_keys, env) : [];
  const pending = createAndDeploy.isPending;
  return (
    <Dialog
      open
      onClose={onClose}
      title="New app"
      description={draft.repo_url || "Build a web app from a Git repository and run it next to this project's databases."}
      size="lg"
      dismissible={!pending}
      footer={
        <>
          <Button icon={<ArrowLeft className="size-4" />} onClick={() => setStep("repo")} disabled={pending} className="mr-auto">
            Back
          </Button>
          <Button onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="new-app-form" icon={<Rocket className="size-4" />} loading={pending}>
            Create &amp; deploy
          </Button>
        </>
      }
    >
      <form id="new-app-form" onSubmit={onSubmit} className="space-y-5">
        {detected && (
          <div className="space-y-2">
            <Alert tone={summary ? "success" : "info"}>{summary ? <>Detected: {summary}. Everything below is editable.</> : "Nothing recognised automatically — choose a preset and fill in the commands."}</Alert>
            {detected.warnings.map((w) => (
              <Alert key={w} tone="warning">
                {w}
              </Alert>
            ))}
            {detected.database_access_suggested && !isAdmin && (
              <Alert tone="info">This app looks like it uses a database. A project admin can give it access to this project's databases after it's created.</Alert>
            )}
          </div>
        )}
        {draft.use_github_connection && (
          <p className="flex items-center gap-2 text-xs text-muted">
            <GitHubIcon className="size-3.5 shrink-0" />
            Cloned with your GitHub connection; the push webhook is added automatically.
            <button type="button" className="font-medium text-accent hover:underline" onClick={() => setDraft((d) => ({ ...d, use_github_connection: false, private_repo: true }))} disabled={pending}>
              Use a token instead
            </button>
          </p>
        )}
        <AppFormFields
          projectId={projectId}
          draft={draft}
          errors={errors}
          onChange={(p) => setDraft((d) => ({ ...d, ...p }))}
          isAdmin={isAdmin}
          disabled={pending}
          hideRepoAccess={draft.use_github_connection}
        />
        <div className="space-y-1.5">
          <p className="text-sm font-medium">Environment variables</p>
          <p className="text-xs text-muted">
            Stored encrypted and injected at runtime. PORT, DEPLOYER_URL and DEPLOYER_PROJECT_ID are always set.
            {missing.length > 0 && <span className="text-warning"> From the repository's .env example — fill in {missing.length === 1 ? "this value" : `these ${missing.length} values`} (or remove unused ones).</span>}
          </p>
          <EnvEditor rows={env} onChange={setEnv} disabled={pending} required={detected?.env_keys} />
        </div>
        {createAndDeploy.isError && <Alert tone="danger">{errorMessage(createAndDeploy.error)}</Alert>}
      </form>
    </Dialog>
  );
}

function RepoStep({
  projectId,
  busy,
  error,
  onPick,
  onManual,
}: {
  projectId: string;
  busy: boolean;
  error: string | null;
  onPick: (url: string, viaConnection: boolean) => void;
  onManual: () => void;
}) {
  const status = useQuery({ queryKey: qk.github, queryFn: api.github.status });
  const [url, setUrl] = useState("");
  const connected = status.data?.connected ?? false;
  const paste = (e: FormEvent) => {
    e.preventDefault();
    if (url.trim()) onPick(url.trim(), connected && /^https:\/\/github\.com\//i.test(url.trim()));
  };

  return (
    <div className="space-y-5">
      {status.isPending ? (
        <div className="flex justify-center py-6">
          <Spinner className="size-5" />
        </div>
      ) : connected ? (
        <RepoList login={status.data?.login ?? ""} busy={busy} onPick={(r) => onPick(r.html_url, true)} />
      ) : status.data?.configured ? (
        <div className="rounded-xl border border-border bg-surface-2 p-4">
          <p className="flex items-center gap-2 font-medium">
            <GitHubIcon className="size-4" /> Connect GitHub once, then pick a repository
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
            <li>Deployer reads your repositories (including private ones) to detect how to build them and to clone them when deploying.</li>
            <li>It adds a webhook to the repositories you deploy, so every push deploys automatically.</li>
            <li>The token is stored encrypted and only used for apps you create. Disconnect any time in Account settings.</li>
          </ul>
          <div className="mt-3">
            <ConnectGitHubButton returnTo={`/projects/${projectId}/deploys?new=1`} />
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted">
          To pick from your GitHub repositories, the instance owner needs to set up GitHub sign-in (Instance settings → Sign-in apps). Until then, paste a public repository URL.
        </p>
      )}

      <form onSubmit={paste} className="space-y-1.5">
        <Field label={connected ? "Or paste a repository URL" : "Or paste a public repository URL"} hint="https:// only. Private repositories need the GitHub connection or a token.">
          {(id) => (
            <div className="flex gap-2">
              <Input id={id} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/you/repo" spellCheck={false} disabled={busy} className="min-w-0 flex-1" />
              <Button type="submit" disabled={!url.trim()} loading={busy}>
                Continue
              </Button>
            </div>
          )}
        </Field>
      </form>
      {error && <Alert tone="danger">{error}</Alert>}
      <button type="button" onClick={onManual} className="text-sm font-medium text-accent hover:underline" disabled={busy}>
        Skip detection and configure by hand
      </button>
    </div>
  );
}

function RepoList({ login, busy, onPick }: { login: string; busy: boolean; onPick: (r: GitHubRepo) => void }) {
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const deferred = useDeferredValue(q.trim());
  const repos = useQuery({ queryKey: qk.githubRepos(""), queryFn: () => api.github.repos() });
  const local = filterRepos(repos.data ?? [], deferred);
  // Only the 100 most recently pushed are loaded; ask GitHub when those don't match.
  const remote = useQuery({
    queryKey: qk.githubRepos(deferred),
    queryFn: () => api.github.repos(deferred),
    enabled: repos.isSuccess && deferred.length >= 2 && local.length === 0,
  });
  const shown = local.length > 0 || deferred.length < 2 ? local : filterRepos(remote.data ?? [], deferred);
  const loading = repos.isPending || (remote.isFetching && local.length === 0);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">Your repositories</p>
        <p className="truncate text-xs text-muted">
          <GitHubIcon className="mr-1 inline size-3.5 align-[-2px]" />
          {login}
        </p>
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search repositories" className="pl-9" aria-label="Search repositories" data-autofocus />
      </div>
      {repos.isError && <Alert tone="danger">{errorMessage(repos.error)}</Alert>}
      <ul className="max-h-80 divide-y divide-border overflow-y-auto rounded-xl border border-border">
        {loading && (
          <li className="flex justify-center py-6">
            <Spinner className="size-5" />
          </li>
        )}
        {!loading && shown.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted">No repositories match.</li>}
        {shown.map((r) => (
          <li key={r.full_name}>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setPicked(r.full_name);
                onPick(r);
              }}
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2 disabled:opacity-60"
            >
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">{r.full_name}</span>
                  {r.private && (
                    <Badge tone="neutral">
                      <Lock className="mr-1 inline size-3" />
                      Private
                    </Badge>
                  )}
                </span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted">
                  <span>
                    <GitBranch className="mr-0.5 inline size-3 align-[-1px]" />
                    {r.default_branch}
                  </span>
                  {r.pushed_at && <span>pushed {relativeTime(r.pushed_at)}</span>}
                  {r.description && <span className="hidden truncate sm:inline">{r.description}</span>}
                </span>
              </span>
              {busy && picked === r.full_name ? <Spinner className="size-4" /> : <span className="text-xs font-medium text-accent">Select</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
