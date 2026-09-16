import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import { errorMessage, saveBlob } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { Project } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Field, Input, Textarea } from "../../components/ui/Input";
import { Alert, Card } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { PassphraseFields } from "../settings/PassphraseFields";
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
  const exportMutation = useMutation({
    mutationFn: () => api.projects.export([project.id], pass.passphrase),
    onSuccess: (file) => {
      saveBlob(file);
      pass.reset();
      toast.success(`Downloaded ${file.filename}.`);
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
    </Card>
  );
}

function DangerCard({ project }: { project: Project }) {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.projects.remove(project.id, project.slug),
    onSuccess: () => {
      queryClient.setQueryData<Project[]>(qk.projects, (list) => list?.filter((p) => p.id !== project.id));
      queryClient.removeQueries({ queryKey: qk.project(project.id) });
      toast.success(`Project “${project.name}” deleted.`);
      navigate("/", { replace: true });
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete project"),
  });

  return (
    <Card title={<span className="text-danger">Danger zone</span>} className="border-danger/40">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-sm">
          <p className="font-medium">Delete this project</p>
          <p className="text-muted">Removes the project and permanently drops its managed databases.</p>
        </div>
        <Button variant="outline-danger" icon={<Trash2 className="size-4" />} onClick={() => setOpen(true)}>
          Delete project
        </Button>
      </div>
      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        onConfirm={() => remove.mutate()}
        loading={remove.isPending}
        title={`Delete ${project.name}?`}
        description="All managed databases and their data, members, invites and API keys will be permanently deleted. External databases are only disconnected. This cannot be undone."
        confirmText={project.slug}
        confirmLabel="Delete project"
      />
    </Card>
  );
}
