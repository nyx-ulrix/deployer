import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Rocket } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { App } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { AppFormFields } from "./AppForm";
import { draftErrors, draftToInput, emptyDraft, type AppDraft, type EnvRow } from "./deploys";
import { EnvEditor } from "./EnvEditor";

export function NewAppDialog({ projectId, isAdmin, onClose }: { projectId: string; isAdmin: boolean; onClose: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<AppDraft>(emptyDraft);
  const [env, setEnv] = useState<EnvRow[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const [created, setCreated] = useState<App | null>(null);
  const errors = submitted ? draftErrors(draft) : {};
  const appPath = (a: App) => `/projects/${projectId}/deploys/${a.id}`;

  const create = useMutation({
    mutationFn: () => api.apps.create(projectId, draftToInput(draft, env)),
    onSuccess: (app) => {
      void queryClient.invalidateQueries({ queryKey: qk.apps(projectId) });
      setCreated(app);
    },
  });
  const deploy = useMutation({
    mutationFn: (app: App) => api.apps.deploy(projectId, app.id),
    onSuccess: (_d, app) => {
      toast.success("Deployment queued.");
      void navigate(appPath(app));
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't start the deployment"),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(draftErrors(draft)).length === 0) create.mutate();
  };

  if (created) {
    return (
      <Dialog
        open
        onClose={() => void navigate(appPath(created))}
        title={`“${created.name}” created`}
        description={`It will be reachable at ${created.local_url} once deployed.`}
        size="sm"
        footer={
          <>
            <Button onClick={() => void navigate(appPath(created))} disabled={deploy.isPending}>
              Not now
            </Button>
            <Button variant="primary" icon={<Rocket className="size-4" />} loading={deploy.isPending} onClick={() => deploy.mutate(created)} data-autofocus>
              Deploy now
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          Deploy now clones <code className="font-mono">{created.branch}</code>, builds the image and starts the app. You can also add
          the webhook in Settings so every push deploys automatically.
        </p>
      </Dialog>
    );
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="New app"
      description="Build a web app from a Git repository and run it next to this project's databases."
      size="lg"
      dismissible={!create.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="new-app-form" loading={create.isPending}>
            Create
          </Button>
        </>
      }
    >
      <form id="new-app-form" onSubmit={onSubmit} className="space-y-5">
        <AppFormFields projectId={projectId} draft={draft} errors={errors} onChange={(p) => setDraft((d) => ({ ...d, ...p }))} isAdmin={isAdmin} disabled={create.isPending} />
        <div className="space-y-1.5">
          <p className="text-sm font-medium">Environment variables</p>
          <p className="text-xs text-muted">Stored encrypted and injected at runtime. PORT, DEPLOYER_URL and DEPLOYER_PROJECT_ID are always set.</p>
          <EnvEditor rows={env} onChange={setEnv} disabled={create.isPending} />
        </div>
        {create.isError && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
