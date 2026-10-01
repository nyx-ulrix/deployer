import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileUp, Server } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useProjects } from "../../api/hooks";
import { useCurrentUser } from "../../auth/auth-context";
import { Button } from "../../components/ui/Button";
import { Checkbox, Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, EmptyState, ErrorState, PageHeader } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { MIN_PASSPHRASE } from "../../lib/constants";
import { PassphraseFields } from "./PassphraseFields";
import { RecentTransfers } from "./TransferJobs";
import { usePassphrase } from "./usePassphrase";

/** Starting an export or import only queues a job; it shows up under "Recent exports & imports". */
function useStartTransfer<T>(start: (input: T) => Promise<unknown>, what: string, onStarted: () => void) {
  const toast = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: start,
    onSuccess: () => {
      onStarted();
      void queryClient.invalidateQueries({ queryKey: qk.transfers });
      toast.info(`${what} started. Follow it under “Recent exports & imports”.`);
    },
  });
}

export function TransferPage() {
  const user = useCurrentUser();
  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="Export & import"
        description="Move projects — or this whole installation — to another device."
      />
      <Alert tone="info" className="mb-5" title="Exports include your data">
        An export file contains your projects <strong>and the data in your managed databases</strong> (tables,
        rows, collections and documents), plus members, API keys, apps and connection secrets. Files are encrypted
        with the passphrase you choose — keep both safe.
      </Alert>
      <Alert tone="warning" className="mb-5" title="Not included">
        MariaDB views, triggers, stored routines and events (the import summary lists any that were left out —
        recreate them from a SQL dump), backups and their version / point-in-time history, deployment history, query
        runs and the audit log. Imports are unpacked in memory, so one can hold at most a sixth of the API's free memory
        (roughly 80 MB with the default 768 MB API_MEM_LIMIT, never over 1 GB) — move bigger databases with a SQL dump.
        Exports and imports run in the background, also through remote access; uploading or downloading a big file
        still takes as long as your connection needs.
      </Alert>
      <div className="space-y-5">
        <RecentTransfers />
        {user.is_instance_owner && <InstanceExportCard />}
        <ProjectsExportCard />
        <ProjectsImportCard />
      </div>
    </div>
  );
}

function InstanceExportCard() {
  const pass = usePassphrase();
  const exportMutation = useStartTransfer((p: string) => api.transfers.exportInstance(p), "Export", pass.reset);
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
          if (pass.valid) exportMutation.mutate(pass.passphrase);
        }}
      >
        <PassphraseFields state={pass} />
        {exportMutation.error && <Alert tone="danger">{errorMessage(exportMutation.error)}</Alert>}
        <Button
          type="submit"
          variant="primary"
          icon={<Download className="size-4" />}
          loading={exportMutation.isPending}
          disabled={!pass.valid}
        >
          Export instance
        </Button>
      </form>
    </Card>
  );
}

function ProjectsExportCard() {
  const user = useCurrentUser();
  const projects = useProjects();
  const pass = usePassphrase();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const owned = projects.data?.filter((p) => p.my_role === "owner") ?? [];

  const exportMutation = useStartTransfer(
    ({ ids, passphrase }: { ids: string[]; passphrase: string }) => api.transfers.exportProjects(ids, passphrase),
    "Export",
    pass.reset,
  );

  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (pass.valid && selected.size > 0) exportMutation.mutate({ ids: [...selected], passphrase: pass.passphrase });
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
          {exportMutation.error && <Alert tone="danger">{errorMessage(exportMutation.error)}</Alert>}
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
  const [file, setFile] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [inputKey, setInputKey] = useState(0);

  const importMutation = useStartTransfer(
    (input: { file: File; passphrase: string }) => api.transfers.importProjects(input.file, input.passphrase),
    "Import",
    () => {
      setFile(null);
      setPassphrase("");
      setInputKey((k) => k + 1);
    },
  );

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
          if (file && passphrase.length >= MIN_PASSPHRASE) importMutation.mutate({ file, passphrase });
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
          {importMutation.isPending ? "Uploading…" : "Import"}
        </Button>
      </form>
    </Card>
  );
}
