import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useApps, useDataSources } from "../../api/hooks";
import type { Project } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Field, Input, Textarea } from "../../components/ui/Input";
import { Alert, Card } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { JobProgressPanel } from "../jobs/JobProgress";
import { PassphraseFields } from "../settings/PassphraseFields";
import { DownloadExportButton } from "../settings/TransferJobs";
import { usePassphrase } from "../settings/usePassphrase";
import { useProjectContext } from "./project-context";

export function ProjectSettingsTab() {
  const { project, can } = useProjectContext();
  if (!can("admin")) {
    return <Alert tone="info">Only project admins and owners can change project settings.</Alert>;
  }
  return (
    <div className="max-w-3xl space-y-5">
      <GeneralCard project={project} key={project.updated_at} />
      {can("owner") && <ExportCard project={project} />}
      {can("owner") && <DangerCard project={project} />}
    </div>
  );
}

function GeneralCard({ project }: { project: Project }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const dirty = name.trim() !== project.name || description.trim() !== (project.description ?? "");

  const save = useMutation({
    mutationFn: () => api.projects.update(project.id, { name: name.trim(), description: description.trim() }),
    onSuccess: (p) => {
      queryClient.setQueryData(qk.project(p.id), p);
      void queryClient.invalidateQueries({ queryKey: qk.projects, exact: true });
      toast.success("Project updated.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't update project"),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (dirty && name.trim()) save.mutate();
  };

  return (
    <Card title="General">
      <form className="space-y-4" onSubmit={onSubmit}>
        <Field label="Name">
          {(id) => <Input id={id} required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Description" optional>
          {(id) => <Textarea id={id} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />}
        </Field>
        <p className="text-xs text-muted">
          Slug: <code className="font-mono">{project.slug}</code> (doesn't change when you rename)
        </p>
        <Button type="submit" variant="primary" loading={save.isPending} disabled={!dirty || !name.trim()}>
          Save changes
        </Button>
      </form>
    </Card>
  );
}

function ExportCard({ project }: { project: Project }) {
  const toast = useToast();
  const pass = usePassphrase();
  const [jobId, setJobId] = useState<string | null>(null);
  const exportMutation = useMutation({
    mutationFn: () => api.transfers.exportProjects([project.id], pass.passphrase),
    onSuccess: (res) => {
      setJobId(res.job.id);
      pass.reset();
    },
    onError: (e) => toast.error(errorMessage(e), "Export failed"),
  });

  return (
    <Card
      title="Export this project"
      description="One encrypted file with the project's settings, members, API keys, schema links and all data in its managed databases."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (pass.valid) exportMutation.mutate();
        }}
      >
        <PassphraseFields state={pass} />
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            variant="primary"
            icon={<Download className="size-4" />}
            loading={exportMutation.isPending}
            disabled={!pass.valid}
          >
            Export project
          </Button>
          <Link to="/settings/transfer" className="text-sm text-accent hover:underline">
            Import or export several projects
          </Link>
        </div>
      </form>
      {jobId && (
        <JobProgressPanel
          key={jobId}
          className="mt-4"
          projectId={project.id}
          jobId={jobId}
          title="Export project"
          result={(job) => (
            <div className="flex flex-wrap items-center gap-3">
              <DownloadExportButton jobId={job.id} />
              <span className="text-xs text-muted">Kept for 24 hours, also under Settings → Export &amp; import.</span>
            </div>
          )}
        />
      )}
    </Card>
  );
}

function DangerCard({ project }: { project: Project }) {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [cloudChoice, setCloudChoice] = useState<"keep" | "delete" | null>(null);
  const sources = useDataSources(project.id);
  const apps = useApps(project.id);
  // docs/CLOUD.md "C2-5": what Deployer created in the user's AWS / Firebase account is billed there, so the
  // owner decides what happens to it; nothing is deleted (or left running) without that choice.
  const inCloud = [
    ...(sources.data ?? [])
      .filter((s) => s.cloud?.created)
      .map((s) => ({ id: s.id, label: `Database “${s.name}”`, resources: s.cloud?.resources ?? [] })),
    ...(apps.data ?? [])
      .filter((a) => a.cloud && a.cloud.resources.length > 0)
      .map((a) => ({ id: a.id, label: `App “${a.name}”`, resources: a.cloud?.resources ?? [] })),
  ];
  const remove = useMutation({
    mutationFn: () => api.projects.remove(project.id, project.slug, inCloud.length ? (cloudChoice ?? undefined) : undefined),
    onSuccess: () => {
      queryClient.setQueryData<Project[]>(qk.projects, (list) => list?.filter((p) => p.id !== project.id));
      queryClient.removeQueries({ queryKey: qk.project(project.id) });
      toast.success(
        inCloud.length === 0
          ? `Project “${project.name}” deleted.`
          : cloudChoice === "delete"
            ? `Project “${project.name}” deleted. Deployer is removing its cloud resources; a failure shows up as an alert.`
            : `Project “${project.name}” deleted. Its cloud resources keep running in your account (and keep being billed).`,
      );
      navigate("/", { replace: true });
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete project"),
  });

  return (
    <Card title={<span className="text-danger">Danger zone</span>} className="border-danger/40">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-sm">
          <p className="font-medium">Delete this project</p>
          <p className="text-muted">Removes the project and drops its managed databases.</p>
        </div>
        <Button
          variant="outline-danger"
          icon={<Trash2 className="size-4" />}
          onClick={() => {
            setCloudChoice(null);
            setOpen(true);
          }}
        >
          Delete project
        </Button>
      </div>
      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        onConfirm={() => remove.mutate()}
        loading={remove.isPending}
        disabled={sources.isPending || apps.isPending || (inCloud.length > 0 && cloudChoice === null)}
        title={`Delete ${project.name}?`}
        description="The project, its members, invites and API keys are deleted, and its managed databases are dropped. External databases are only disconnected. For 30 days the instance owner can restore the project, with the last version of each managed database, or download those versions (Settings → Backups)."
        confirmText={project.slug}
        confirmLabel="Delete project"
      >
        {inCloud.length > 0 && (
          <fieldset className="space-y-2 rounded-lg border border-border p-3">
            <legend className="px-1 font-medium text-fg">In your cloud account</legend>
            <p className="text-muted">
              Deployer created these in your AWS / Firebase account. They are billed there, so choose what happens to
              them:
            </p>
            <ul className="list-disc space-y-1 pl-5 text-muted">
              {inCloud.map((thing) => (
                <li key={thing.id}>
                  <span className="text-fg">{thing.label}</span>
                  {thing.resources.length > 0 && <span>: {thing.resources.join("; ")}</span>}
                </li>
              ))}
            </ul>
            {(
              [
                [
                  "delete",
                  "Delete them from my cloud account",
                  "Databases get a final snapshot / backup first, which stays in your account (billed for storage until you delete it in the AWS console). Nothing else is left running.",
                ],
                [
                  "keep",
                  "Keep them running in my cloud account",
                  "They keep working and keep being billed by AWS / Google. Deployer forgets them: manage or delete them in the provider's console.",
                ],
              ] as const
            ).map(([value, label, hint]) => (
              <label key={value} className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-2.5 hover:bg-surface-2">
                <input
                  type="radio"
                  name="project-cloud-choice"
                  className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
                  checked={cloudChoice === value}
                  onChange={() => setCloudChoice(value)}
                />
                <span className="min-w-0">
                  <span className="block font-medium text-fg">{label}</span>
                  <span className="mt-0.5 block text-xs text-muted">{hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
        )}
      </ConfirmDialog>
    </Card>
  );
}
