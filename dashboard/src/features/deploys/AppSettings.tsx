import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Eye, Globe, Plus, RefreshCw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { App, AppWebhook, Domain } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { Input } from "../../components/ui/Input";
import { Alert, Card, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { JobProgressPanel } from "../jobs/JobProgress";
import { AppFormFields } from "./AppForm";
import { draftErrors, draftToPatch, emptyDraft, envToRows, rowsToEnv, type EnvRow } from "./deploys";
import { EnvEditor } from "./EnvEditor";

type Props = { projectId: string; app: App; canEdit: boolean; isAdmin: boolean };

export function AppSettings(props: Props) {
  return (
    <div className="space-y-4">
      <GeneralCard {...props} />
      <EnvCard {...props} />
      <WebhookCard {...props} />
      <DomainsCard {...props} />
      {props.isAdmin && <DeleteCard {...props} />}
    </div>
  );
}

function GeneralCard({ projectId, app, canEdit, isAdmin }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(() => emptyDraft(app));
  const [submitted, setSubmitted] = useState(false);
  const errors = submitted ? draftErrors(draft) : {};
  const save = useMutation({
    mutationFn: () => api.apps.update(projectId, app.id, draftToPatch(draft, app)),
    onSuccess: (updated) => {
      queryClient.setQueryData(qk.app(projectId, app.id), updated);
      setDraft(emptyDraft(updated));
      setSubmitted(false);
      toast.success("Settings saved. They apply on the next deploy.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't save"),
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(draftErrors(draft)).length === 0) save.mutate();
  };
  return (
    <Card title="General" description="Repository, preset and build settings. Changes apply on the next deploy.">
      <form onSubmit={onSubmit} className="space-y-4">
        <AppFormFields
          projectId={projectId}
          draft={draft}
          errors={errors}
          onChange={(p) => setDraft((d) => ({ ...d, ...p }))}
          isAdmin={isAdmin}
          disabled={!canEdit || save.isPending}
          hasRepoToken={app.has_repo_token}
          showSlug={false}
        />
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted">Slug</dt>
            <dd className="font-mono">{app.slug}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Port</dt>
            <dd className="font-mono">{app.port}</dd>
          </div>
        </dl>
        {canEdit && (
          <div className="flex justify-end">
            <Button variant="primary" type="submit" loading={save.isPending}>
              Save
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

function EnvCard({ projectId, app, isAdmin }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<EnvRow[] | null>(null);
  const reveal = useMutation({
    mutationFn: () => api.apps.env(projectId, app.id),
    onSuccess: (r) => setRows(envToRows(r.env)),
    onError: (e) => toast.error(errorMessage(e), "Couldn't reveal variables"),
  });
  const save = useMutation({
    mutationFn: () => api.apps.update(projectId, app.id, { env: rowsToEnv(rows ?? []) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(qk.app(projectId, app.id), updated);
      setRows(null);
      toast.success("Variables saved. They apply on the next deploy.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't save variables"),
  });
  return (
    <Card
      title="Environment variables"
      description="Stored encrypted; PORT, DEPLOYER_URL and DEPLOYER_PROJECT_ID are always added."
      actions={
        isAdmin && rows === null ? (
          <Button size="sm" icon={<Eye className="size-3.5" />} loading={reveal.isPending} onClick={() => reveal.mutate()}>
            Reveal &amp; edit
          </Button>
        ) : undefined
      }
    >
      {rows ? (
        <div className="space-y-3">
          <EnvEditor rows={rows} onChange={setRows} secret disabled={save.isPending} />
          <div className="flex justify-end gap-2">
            <Button onClick={() => setRows(null)} disabled={save.isPending}>
              Cancel
            </Button>
            <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
              Save variables
            </Button>
          </div>
        </div>
      ) : app.env_keys.length === 0 ? (
        <p className="text-sm text-muted">No variables.</p>
      ) : (
        <ul className="space-y-1 font-mono text-xs">
          {app.env_keys.map((k) => (
            <li key={k}>
              {k}=<span className="text-muted">••••••••</span>
            </li>
          ))}
        </ul>
      )}
      {!isAdmin && <p className="mt-2 text-xs text-muted">Project admins can reveal and edit values.</p>}
    </Card>
  );
}

function WebhookCard({ projectId, app, canEdit }: Props) {
  const toast = useToast();
  const [hook, setHook] = useState<AppWebhook | null>(null);
  const reveal = useMutation({
    mutationFn: () => api.apps.webhook(projectId, app.id),
    onSuccess: setHook,
    onError: (e) => toast.error(errorMessage(e), "Couldn't load the webhook"),
  });
  const rotate = useMutation({
    mutationFn: () => api.apps.rotateWebhook(projectId, app.id),
    onSuccess: (h) => {
      setHook(h);
      toast.success("Secret rotated. Update it on GitHub.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't rotate the secret"),
  });
  const [confirmRotate, setConfirmRotate] = useState(false);
  return (
    <Card
      title="Push to deploy"
      description={`Every push to ${app.branch} deploys automatically once GitHub calls this webhook.`}
      actions={
        canEdit && !hook ? (
          <Button size="sm" icon={<Eye className="size-3.5" />} loading={reveal.isPending} onClick={() => reveal.mutate()}>
            Show webhook
          </Button>
        ) : canEdit ? (
          <Button size="sm" icon={<RefreshCw className="size-3.5" />} onClick={() => setConfirmRotate(true)}>
            Rotate secret
          </Button>
        ) : undefined
      }
    >
      {!canEdit ? (
        <p className="text-sm text-muted">Developers and admins can view the webhook URL and secret.</p>
      ) : hook ? (
        <div className="space-y-3">
          <CopyField label="Payload URL" value={hook.url} />
          <CopyField label="Secret" value={hook.secret} secret />
        </div>
      ) : null}
      <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm text-muted">
        <li>
          On GitHub open the repository → <b>Settings</b> → <b>Webhooks</b> → <b>Add webhook</b>.
        </li>
        <li>Paste the payload URL and set content type to <code className="font-mono">application/json</code>.</li>
        <li>Paste the secret.</li>
        <li>
          Choose <b>Just the push event</b> and save. GitHub sends a ping; pushes to <code className="font-mono">{app.branch}</code>{" "}
          then deploy.
        </li>
      </ol>
      <ConfirmDialog
        open={confirmRotate}
        onClose={() => setConfirmRotate(false)}
        onConfirm={async () => {
          await rotate.mutateAsync();
          setConfirmRotate(false);
        }}
        loading={rotate.isPending}
        title="Rotate the webhook secret?"
        description="GitHub keeps sending with the old secret until you update it there; those pushes are rejected."
        confirmLabel="Rotate"
      />
    </Card>
  );
}

function DomainsCard({ projectId, app, isAdmin }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const remote = useQuery({ queryKey: qk.remoteAccess, queryFn: api.remoteAccess.get, enabled: isAdmin, retry: false, staleTime: 60_000 });
  const linked = remote.data?.cloudflare.linked ?? false;
  const [hostname, setHostname] = useState("");
  const [removing, setRemoving] = useState<Domain | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: qk.app(projectId, app.id) });
  const add = useMutation({
    mutationFn: () => api.apps.addDomain(projectId, app.id, hostname.trim()),
    onSuccess: (d) => {
      setHostname("");
      void refresh();
      toast.success(`${d.hostname} added. DNS can take a minute.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't add the hostname"),
  });
  const remove = useMutation({
    mutationFn: (d: Domain) => api.apps.removeDomain(projectId, app.id, d.id),
    onSuccess: () => {
      setRemoving(null);
      void refresh();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't remove the hostname"),
  });
  return (
    <Card title="Domains" description={`Always reachable at ${app.local_url}. Add a Cloudflare hostname for the public internet.`}>
      {app.domains.length > 0 && (
        <ul className="mb-3 divide-y divide-border">
          {app.domains.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <Globe className="size-4 text-muted" />
              <a href={d.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate font-mono text-accent hover:underline">
                {d.hostname}
              </a>
              <Badge tone={d.status === "active" ? "success" : d.status === "error" ? "danger" : "warning"} title={d.status_message ?? undefined}>
                {d.status}
              </Badge>
              {isAdmin && (
                <Button size="icon-sm" variant="ghost" aria-label={`Remove ${d.hostname}`} onClick={() => setRemoving(d)}>
                  <Trash2 className="size-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!isAdmin ? (
        app.domains.length === 0 && <p className="text-sm text-muted">No custom hostnames. Admins can add one.</p>
      ) : linked ? (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (hostname.trim()) add.mutate();
          }}
        >
          <Input value={hostname} onChange={(e) => setHostname(e.target.value)} placeholder="shop.example.com" className="min-w-48 flex-1" spellCheck={false} aria-label="Hostname" />
          <Button variant="primary" type="submit" icon={<Plus className="size-4" />} loading={add.isPending} disabled={!hostname.trim()}>
            Add hostname
          </Button>
        </form>
      ) : remote.isPending ? null : (
        <Alert tone="info">
          Public hostnames need a Cloudflare zone. Link one under{" "}
          <Link to="/settings/remote-access" className="font-medium underline">
            Settings → Domains &amp; remote access
          </Link>
          .
        </Alert>
      )}
      {removing && (
        <ConfirmDialog
          open
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing)}
          loading={remove.isPending}
          title={`Remove ${removing.hostname}?`}
          description="The DNS record and tunnel route are deleted; the app stays reachable on its local URL."
          confirmLabel="Remove"
        />
      )}
    </Card>
  );
}

function DeleteCard({ projectId, app }: Props) {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: () => api.apps.remove(projectId, app.id),
    onSuccess: (r) => {
      setConfirming(false);
      setJobId(r.job_id);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete the app"),
  });
  return (
    <Card title="Delete app" description="Stops and removes the containers, images, routes and hostnames. Deployments are gone for good.">
      {jobId ? (
        <JobProgressPanel
          projectId={projectId}
          jobId={jobId}
          title={`Removing ${app.name}`}
          onFinished={(job) => {
            void queryClient.invalidateQueries({ queryKey: qk.apps(projectId) });
            if (job.status === "succeeded") {
              toast.success(`${app.name} deleted.`);
              void navigate(`/projects/${projectId}/deploys`);
            }
          }}
        />
      ) : (
        <Button variant="outline-danger" icon={<Trash2 className="size-4" />} onClick={() => setConfirming(true)}>
          Delete app
        </Button>
      )}
      {remove.isError && <ErrorAlert error={remove.error} className="mt-3" />}
      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={() => remove.mutate()}
        loading={remove.isPending}
        title={`Delete “${app.name}”?`}
        description="This cannot be undone."
        confirmText={app.slug}
        confirmLabel="Delete app"
      />
    </Card>
  );
}
