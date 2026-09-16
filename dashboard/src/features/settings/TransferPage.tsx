import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileUp, Server } from "lucide-react";
import { errorMessage, saveBlob } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useProjects } from "../../api/hooks";
import type { ProjectsImportResponse } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { Button } from "../../components/ui/Button";
import { Checkbox, Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, EmptyState, ErrorState, PageHeader } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { MIN_PASSPHRASE } from "../../lib/constants";
import { ImportSummaryList } from "./ImportSummaryList";
import { PassphraseFields } from "./PassphraseFields";
import { usePassphrase } from "./usePassphrase";

export function TransferPage() {
  const user = useCurrentUser();
  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="Export & import"
        description="Move projects — or this whole installation — to another device."
      />
      <Alert tone="info" className="mb-5" title="Exports include your data">
        An export file contains everything, <strong>including the data in your managed databases</strong> (tables,
        rows, collections and documents), plus members, API keys and connection secrets. Importing it on another
        Deployer sets everything up again. Files are encrypted with the passphrase you choose — keep both safe.
      </Alert>
      <div className="space-y-5">
        {user.is_instance_owner && <InstanceExportCard />}
        <ProjectsExportCard />
        <ProjectsImportCard />
      </div>
    </div>
  );
}

function InstanceExportCard() {
  const toast = useToast();
  const pass = usePassphrase();
  const exportMutation = useMutation({
    mutationFn: () => api.instance.export(pass.passphrase),
    onSuccess: (file) => {
      saveBlob(file);
      pass.reset();
      toast.success(`Downloaded ${file.filename}.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Export failed"),
  });
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Server className="size-4 text-accent" /> Whole instance
        </span>
      }
      description="Settings, all users, all projects and all managed data. Restore it on a fresh install with the setup wizard's “Restore from export”."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (pass.valid) exportMutation.mutate();
        }}
      >
        <PassphraseFields state={pass} />
        <Button
          type="submit"
          variant="primary"
          icon={<Download className="size-4" />}
          loading={exportMutation.isPending}
          disabled={!pass.valid}
        >
          {exportMutation.isPending ? "Exporting… (large databases take a while)" : "Export instance"}
        </Button>
      </form>
    </Card>
  );
}

function ProjectsExportCard() {
  const user = useCurrentUser();
  const toast = useToast();
  const projects = useProjects();
  const pass = usePassphrase();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const owned = projects.data?.filter((p) => p.my_role === "owner") ?? [];

  const exportMutation = useMutation({
    mutationFn: () => api.projects.export([...selected], pass.passphrase),
    onSuccess: (file) => {
      saveBlob(file);
      pass.reset();
      toast.success(`Downloaded ${file.filename}.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Export failed"),
  });

  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (pass.valid && selected.size > 0) exportMutation.mutate();
  };

  return (
    <Card title="Export projects" description="Pick projects you own. Anyone can import them on another Deployer — they'll own the copies.">
      {projects.isPending ? (
        <PageSpinner />
      ) : projects.isError ? (
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
      ) : owned.length === 0 ? (
        <EmptyState title="No projects you own" description={`Only project owners can export. You're signed in as ${user.email}.`} />
      ) : (
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="rounded-xl border border-border">
            <div className="flex items-center justify-between border-b border-border px-3 py-2 text-xs text-muted">
              <span>
                {selected.size} of {owned.length} selected
              </span>
              <button
                type="button"
                className="font-medium text-accent hover:underline"
                onClick={() =>
                  setSelected(selected.size === owned.length ? new Set() : new Set(owned.map((p) => p.id)))
                }
              >
                {selected.size === owned.length ? "Select none" : "Select all"}
              </button>
            </div>
            <ul className="max-h-64 divide-y divide-border overflow-y-auto">
              {owned.map((p) => (
                <li key={p.id} className="px-3 py-2.5">
                  <Checkbox
                    checked={selected.has(p.id)}
                    onChange={(e) => toggle(p.id, e.target.checked)}
                    label={p.name}
                    description={`${p.data_source_counts.sql} SQL · ${p.data_source_counts.nosql} NoSQL`}
                  />
                </li>
              ))}
            </ul>
          </div>
          <PassphraseFields state={pass} />
          <Button
            type="submit"
            variant="primary"
            icon={<Download className="size-4" />}
            loading={exportMutation.isPending}
            disabled={!pass.valid || selected.size === 0}
          >
            Export {selected.size > 0 ? selected.size : ""} project{selected.size === 1 ? "" : "s"}
          </Button>
        </form>
      )}
    </Card>
  );
}

function ProjectsImportCard() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [result, setResult] = useState<ProjectsImportResponse | null>(null);
  const [inputKey, setInputKey] = useState(0);

  const importMutation = useMutation({
    mutationFn: () => api.projects.import(file as File, passphrase),
    onSuccess: (res) => {
      setResult(res);
      setFile(null);
      setPassphrase("");
      setInputKey((k) => k + 1);
      void queryClient.invalidateQueries({ queryKey: qk.projects });
      toast.success(`Imported ${res.projects.length} project${res.projects.length === 1 ? "" : "s"}.`);
    },
  });

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <FileUp className="size-4 text-accent" /> Import projects
        </span>
      }
      description="Upload a projects export (deployer-projects-….json). The projects and their data are recreated here, owned by you."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (file && passphrase.length >= MIN_PASSPHRASE) importMutation.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Export file">
            {(id) => (
              <Input
                key={inputKey}
                id={id}
                type="file"
                accept=".json,application/json"
                className="py-1.5 file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-2.5 file:py-1 file:text-sm file:font-medium file:text-fg"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            )}
          </Field>
          <Field label="Passphrase">
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="off"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
              />
            )}
          </Field>
        </div>
        <p className="text-xs text-muted">
          Instance exports can only be restored on a fresh installation from the setup wizard.
        </p>
        {importMutation.error && <Alert tone="danger">{errorMessage(importMutation.error)}</Alert>}
        <Button
          type="submit"
          variant="primary"
          icon={<FileUp className="size-4" />}
          loading={importMutation.isPending}
          disabled={!file || passphrase.length < MIN_PASSPHRASE}
        >
          Import
        </Button>
      </form>
      {result && (
        <div className="mt-5 space-y-3 border-t border-border pt-4">
          <h3 className="text-sm font-semibold">Import summary</h3>
          <ImportSummaryList summary={result.summary} />
          <ul className="space-y-1 text-sm">
            {result.projects.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.id}`} className="font-medium text-accent hover:underline">
                  {p.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
