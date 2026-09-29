import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Eye, Globe, Plus, RefreshCw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { App, AppPatch, AppReplica, AppWebhook, DnsRecord, Domain } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { Checkbox, Input } from "../../components/ui/Input";
import { Alert, Card, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { relativeTime } from "../../lib/format";
import { JobProgressPanel } from "../jobs/JobProgress";
import { AppFormFields } from "./AppForm";
import { draftErrors, draftToPatch, emptyDraft, envToRows, rowsToEnv, TARGET_SHORT, type EnvRow } from "./deploys";
import { EnvEditor } from "./EnvEditor";

type Props = { projectId: string; app: App; canEdit: boolean; isAdmin: boolean };

export function AppSettings(props: Props) {
  return (
    <div className="space-y-4">
      <GeneralCard {...props} />
      <EnvCard {...props} />
      <WebhookCard {...props} />
      <DomainsCard {...props} />
      {(props.isAdmin || props.app.cohost) && props.app.target === "local" && <CohostCard {...props} />}
      {props.isAdmin && <DeleteCard {...props} />}
    </div>
  );
}

function GeneralCard({ projectId, app, canEdit, isAdmin }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(() => emptyDraft(app));
  const [submitted, setSubmitted] = useState(false);
  const [confirmMove, setConfirmMove] = useState(false);
  const [teardownJob, setTeardownJob] = useState<string | null>(null);
  const errors = submitted ? draftErrors(draft) : {};
  const moving =
    draft.target !== app.target || (draft.target !== "local" && draft.cloud_connection_id !== (app.cloud_connection_id ?? ""));
  const save = useMutation({
    mutationFn: () => api.apps.update(projectId, app.id, draftToPatch(draft, app)),
    onSuccess: ({ teardown_job_id, warnings, ...updated }) => {
      queryClient.setQueryData(qk.app(projectId, app.id), updated);
      setDraft(emptyDraft(updated));
      setSubmitted(false);
      setConfirmMove(false);
      if (teardown_job_id) setTeardownJob(teardown_job_id);
      toast.success(moving ? "Target changed. Deploy to publish the app there." : "Settings saved. They apply on the next deploy.");
      for (const w of warnings ?? []) toast.info(w, "GitHub webhook");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't save"),
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(draftErrors(draft)).length > 0) return;
    if (moving) setConfirmMove(true);
    else save.mutate();
  };
  return (
    <Card title="General" description="Repository, preset and build settings. Changes apply on the next deploy.">
      <form onSubmit={onSubmit} className="space-y-4">
        {app.github && !app.has_repo_token && (
          <p className="text-xs text-muted">
            Cloned with the GitHub connection of {app.github.connected_by_email}. Tick “Private repository” and add a token to use a token instead.
          </p>
        )}
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
      {teardownJob && <JobProgressPanel projectId={projectId} jobId={teardownJob} title="Removing the previous target's resources" />}
      <ConfirmDialog
        open={confirmMove}
        onClose={() => setConfirmMove(false)}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        title={`Move “${app.name}” to ${TARGET_SHORT[draft.target]}?`}
        description="The app stops being served where it runs now; deploy afterwards to publish it on the new target. Earlier deployments can no longer be rolled back to."
        confirmLabel="Move app"
      >
        <TeardownList app={app} />
      </ConfirmDialog>
    </Card>
  );
}

/** What moving / deleting removes (docs/CLOUD.md): listed before confirming; failures are reported by the job. */
function TeardownList({ app }: { app: App }) {
  if (app.target === "local") {
    return <p className="text-sm text-muted">Its container on this PC is stopped and removed.</p>;
  }
  const resources = app.cloud?.resources ?? [];
  if (resources.length === 0) return <p className="text-sm text-muted">Nothing was created in the cloud account yet.</p>;
  return (
    <div className="text-sm">
      <p className="font-medium">Deleted from the {app.cloud?.connection_name ?? "cloud"} account:</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">
        {resources.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">Removal runs as a job; anything that can't be removed is reported there, never skipped silently.</p>
    </div>
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
      description={
        app.target === "local"
          ? "Stored encrypted; PORT, DEPLOYER_URL and DEPLOYER_PROJECT_ID are always added."
          : "Stored encrypted and sent to the cloud service as its environment: only these, nothing from Deployer (no DEPLOYER_* variables)."
      }
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
      if (h.hook_active) toast.success("Secret rotated and updated on GitHub.");
      else toast.success("Secret rotated. Update it on GitHub.");
      for (const w of h.warnings ?? []) toast.info(w);
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
      {app.github?.hook_active ? (
        <p className="mt-4 text-sm text-muted">Deployer added this webhook to the GitHub repository for you; rotating the secret updates it there too.</p>
      ) : (
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
      )}
      <ConfirmDialog
        open={confirmRotate}
        onClose={() => setConfirmRotate(false)}
        onConfirm={async () => {
          await rotate.mutateAsync();
          setConfirmRotate(false);
        }}
        loading={rotate.isPending}
        title="Rotate the webhook secret?"
        description={
          app.github?.hook_active
            ? "Deployer updates the secret on GitHub too."
            : "GitHub keeps sending with the old secret until you update it there; those pushes are rejected."
        }
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
  const cloud = app.target !== "local";
  const add = useMutation({
    mutationFn: () => api.apps.addDomain(projectId, app.id, hostname.trim()),
    onSuccess: (d) => {
      setHostname("");
      void refresh();
      toast.success(cloud ? `${d.hostname} added. Validation can take a few minutes.` : `${d.hostname} added. DNS can take a minute.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't add the hostname"),
  });
  const remove = useMutation({
    mutationFn: (d: Domain) => api.apps.removeDomain(projectId, app.id, d.id),
    onSuccess: (r) => {
      setRemoving(null);
      for (const w of r.warnings ?? []) toast.info(w, "Finish by hand");
      void refresh();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't remove the hostname"),
  });
  const check = useMutation({
    mutationFn: (d: Domain) => api.apps.checkDomain(projectId, app.id, d.id),
    onSuccess: () => toast.info("Checking again; the status updates in a moment."),
    onError: (e) => toast.error(errorMessage(e), "Couldn't check"),
  });
  const reachable = cloud ? app.cloud?.url : app.local_url;
  return (
    <Card
      title="Domains"
      description={
        cloud
          ? `${reachable ? `Always reachable at ${reachable}. ` : ""}Add your own domain: with Cloudflare linked Deployer creates the DNS records, otherwise it lists them for you to add.`
          : `On this PC: ${reachable}. Add a Cloudflare hostname to reach it from the internet.`
      }
    >
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
              {isAdmin && cloud && d.status !== "active" && (
                <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} loading={check.isPending} onClick={() => check.mutate(d)}>
                  Check again
                </Button>
              )}
              {isAdmin && (
                <Button size="icon-sm" variant="ghost" aria-label={`Remove ${d.hostname}`} onClick={() => setRemoving(d)}>
                  <Trash2 className="size-4" />
                </Button>
              )}
              {cloud && d.status_message && <p className="w-full text-xs text-muted">{d.status_message}</p>}
              {cloud && (d.dns_records ?? []).length > 0 && <DnsRecords records={d.dns_records ?? []} />}
            </li>
          ))}
        </ul>
      )}
      {!isAdmin ? (
        app.domains.length === 0 && <p className="text-sm text-muted">No custom hostnames. Admins can add one.</p>
      ) : linked || cloud ? (
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
          description={
            cloud
              ? "The hostname is detached from the cloud target and the DNS records Deployer created are deleted."
              : "The DNS record and tunnel route are deleted; the app stays reachable on its local URL."
          }
          confirmLabel="Remove"
        />
      )}
    </Card>
  );
}

const REPLICA_TONE: Record<AppReplica["status"], "success" | "danger" | "warning" | "neutral"> = {
  live: "success",
  failed: "danger",
  pending: "warning",
  building: "warning",
  stopped: "neutral",
};

/** docs/COHOSTING.md "Websites on both PCs". */
function CohostCard({ projectId, app, isAdmin }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (patch: AppPatch) => api.apps.update(projectId, app.id, patch),
    onSuccess: (updated) => queryClient.setQueryData(qk.app(projectId, app.id), updated),
    onError: (e) => toast.error(errorMessage(e), "Couldn't change co-hosting"),
  });
  const privateRepo = app.has_repo_token || Boolean(app.github);
  return (
    <Card
      title="Co-host this app"
      description="Also run the app on the project's co-host PCs. Visitors keep one address; Cloudflare sends them to whichever PC is up."
    >
      <div className="space-y-3">
        <Checkbox
          label="Co-host this app"
          description={
            isAdmin
              ? "Each co-host PC builds the live commit and serves it with its own copy of the databases; writes there sync back like any other change."
              : "Only project admins can change this."
          }
          checked={app.cohost}
          disabled={!isAdmin || save.isPending}
          onChange={(e) => save.mutate({ cohost: e.target.checked })}
        />
        {privateRepo && (
          <Checkbox
            label="Let co-hosts clone this private repository"
            description="Sends the repository token to each co-host PC. Whoever controls that PC can read it; without it their copies can't be built."
            checked={app.cohost_share_repo_access}
            disabled={!isAdmin || save.isPending}
            onChange={(e) => save.mutate({ cohost_share_repo_access: e.target.checked })}
          />
        )}
        {app.cohost &&
          (app.replicas.length === 0 ? (
            <p className="text-sm text-muted">No co-host PC yet: a member with co-hosting on shares their PC with this project (and copies its databases when the app uses them).</p>
          ) : (
            <ul className="divide-y divide-border">
              {app.replicas.map((r) => (
                <li key={r.device_id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">{r.device_name ?? r.device_id}</span>
                  {!r.online && <Badge>offline</Badge>}
                  <Badge tone={REPLICA_TONE[r.status]}>{r.status}</Badge>
                  {r.last_seen_at && <span className="text-xs text-muted">seen {relativeTime(r.last_seen_at)}</span>}
                  {r.error && <p className="w-full text-xs text-danger">{r.error}</p>}
                </li>
              ))}
            </ul>
          ))}
      </div>
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
      setJobId(r.teardown_job_id ?? r.job_id); // cloud apps: follow the teardown so its errors are shown
      for (const w of r.warnings ?? []) toast.info(w, "Cloudflare");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete the app"),
  });
  return (
    <Card
      title="Delete app"
      description={
        app.target === "local"
          ? "Stops and removes the containers, images, routes and hostnames. Deployments are gone for good."
          : "Deletes everything Deployer created in the cloud account, and the app's deployments, for good."
      }
    >
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
      >
        {app.target !== "local" && <TeardownList app={app} />}
      </ConfirmDialog>
    </Card>
  );
}

/** docs/CLOUD.md "Custom domains": the records the cloud target asks for. */
function DnsRecords({ records }: { records: DnsRecord[] }) {
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full text-left font-mono text-xs">
        <thead className="text-muted">
          <tr>
            <th className="py-1 pr-3 font-normal">Type</th>
            <th className="py-1 pr-3 font-normal">Name</th>
            <th className="py-1 pr-3 font-normal">Value</th>
            <th className="py-1 font-normal">
              <span className="sr-only">Status</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={`${r.type} ${r.name} ${r.value}`} className="align-top">
              <td className="py-1 pr-3">{r.type}</td>
              <td className="break-all py-1 pr-3">{r.name}</td>
              <td className="break-all py-1 pr-3">{r.value}</td>
              <td className="py-1 font-sans">
                {r.created ? <Badge tone="success">in Cloudflare</Badge> : r.error ? <span className="text-danger">{r.error}</span> : <Badge>add by hand</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
