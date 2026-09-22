import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Code2, Download, Eye, KeyRound, Plus, Trash2 } from "lucide-react";
import { errorMessage, isApiError } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useDataSources, useSetupStatus, useSourceSchema } from "../../api/hooks";
import type { ApiKey, ApiKeyRole, Project } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyButton, CopyField } from "../../components/ui/CopyField";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { Tabs } from "../../components/ui/Tabs";
import { useToast } from "../../components/ui/toast-context";
import { formatDate, relativeTime } from "../../lib/format";
import { downloadText } from "../query/csv";
import { buildSnippets, SNIPPET_LANGS, type SnippetLang } from "./apiSnippets";
import { useProjectContext } from "./project-context";

const ROLE_HELP: Record<ApiKeyRole, string> = {
  anon: "Public key for client apps. Limited to what anonymous users may do.",
  service: "Full access to the project's data. Keep it on servers only — never ship it to browsers or phones.",
};

const DOCS_URL = "https://github.com/nyx-ulrix/deployer/blob/main/docs/DATA_API.md";
const NOT_REVEALABLE = "This key was created before Deployer kept secrets. Create a new key to reveal or export it.";

/** The API's 409 codes for reveal/config get a fuller explanation than their one-line message. */
function keyErrorMessage(e: unknown): string {
  return isApiError(e) && e.code === "not_revealable" ? NOT_REVEALABLE : errorMessage(e);
}

export function ApiKeysTab() {
  const { project, can } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const keys = useQuery({
    queryKey: qk.apiKeys(project.id),
    queryFn: () => api.apiKeys.list(project.id),
    enabled: can("admin"),
  });
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);
  // Secrets revealed this session, by key id; they fill the usage snippets and skip a second reveal request.
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [showing, setShowing] = useState<ApiKey | null>(null);
  const [usageFor, setUsageFor] = useState<ApiKey | null>(null);

  const revoke = useMutation({
    mutationFn: (k: ApiKey) => api.apiKeys.revoke(project.id, k.id),
    onSuccess: (_d, k) => {
      void queryClient.invalidateQueries({ queryKey: qk.apiKeys(project.id) });
      setRevoking(null);
      toast.success(`Key “${k.name}” revoked.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't revoke key"),
  });

  const reveal = useMutation({
    mutationFn: (k: ApiKey) => api.apiKeys.reveal(project.id, k.id),
    onSuccess: (res, k) => setSecrets((s) => ({ ...s, [k.id]: res.secret })),
    onError: (e) => toast.error(keyErrorMessage(e), "Couldn't reveal key"),
  });

  const config = useMutation({
    mutationFn: (k: ApiKey) => api.apiKeys.config(project.id, k.id),
    onSuccess: (data, k) =>
      downloadText(`deployer-${project.slug}-${k.role}.json`, JSON.stringify(data, null, 2), "application/json"),
    onError: (e) => toast.error(keyErrorMessage(e), "Couldn't download config"),
  });

  const showSecret = (k: ApiKey) => {
    setShowing(k);
    if (!secrets[k.id]) reveal.mutate(k);
  };

  if (!can("admin")) {
    return <Alert tone="info">Only project admins and owners can manage API keys.</Alert>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted">
          API keys let your apps call this project's data API. Admins can reveal a key's secret or download a config
          file for it at any time.{" "}
          <a href={DOCS_URL} target="_blank" rel="noreferrer" className="text-accent hover:underline">
            Full tutorial →
          </a>
        </p>
        <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
          Create key
        </Button>
      </div>

      {keys.isPending ? (
        <PageSpinner />
      ) : keys.isError ? (
        <ErrorState error={keys.error} onRetry={() => void keys.refetch()} />
      ) : keys.data.length === 0 ? (
        <EmptyState icon={<KeyRound className="size-5" />} title="No API keys" description="Create a key to connect an app." />
      ) : (
        <Table>
          <THead>
            <Tr>
              <Th>Name</Th>
              <Th>Key</Th>
              <Th>Role</Th>
              <Th className="hidden sm:table-cell">Created</Th>
              <Th className="hidden sm:table-cell">Last used</Th>
              <Th>
                <span className="sr-only">Actions</span>
              </Th>
            </Tr>
          </THead>
          <TBody>
            {keys.data.map((k) => (
              <Tr key={k.id} className={k.revoked_at ? "opacity-60" : undefined}>
                <Td className="font-medium">{k.name}</Td>
                <Td>
                  <code className="font-mono text-xs whitespace-nowrap">{k.prefix}…</code>
                  {!k.revoked_at && !k.revealable && (
                    <p className="mt-0.5 max-w-48 text-xs text-muted">
                      Created before secrets were kept — create a new key to reveal
                    </p>
                  )}
                </Td>
                <Td>
                  <Badge tone={k.role === "service" ? "warning" : "info"}>{k.role}</Badge>
                </Td>
                <Td className="hidden whitespace-nowrap text-muted sm:table-cell">{formatDate(k.created_at)}</Td>
                <Td className="hidden whitespace-nowrap text-muted sm:table-cell">{relativeTime(k.last_used_at)}</Td>
                <Td className="text-right">
                  {k.revoked_at ? (
                    <Badge tone="danger">Revoked</Badge>
                  ) : (
                    // Plain icon buttons: the table scrolls horizontally, which would clip a dropdown menu.
                    <div className="flex items-center justify-end gap-0.5">
                      {k.revealable && (
                        <Button size="icon" variant="ghost" aria-label={`Reveal ${k.name}`} title="Reveal secret" onClick={() => showSecret(k)}>
                          <Eye className="size-4" />
                        </Button>
                      )}
                      <Button size="icon" variant="ghost" aria-label={`Show usage for ${k.name}`} title="Show usage" onClick={() => setUsageFor(k)}>
                        <Code2 className="size-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Download config for ${k.name}`}
                        title="Download config JSON"
                        loading={config.isPending && config.variables?.id === k.id}
                        onClick={() => config.mutate(k)}
                      >
                        <Download className="size-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="text-danger"
                        aria-label={`Revoke ${k.name}`}
                        title="Revoke"
                        onClick={() => setRevoking(k)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  )}
                </Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      )}

      {creating && <CreateKeyDialog projectId={project.id} onClose={() => setCreating(false)} />}
      {revoking && (
        <ConfirmDialog
          open
          onClose={() => setRevoking(null)}
          onConfirm={() => revoke.mutate(revoking)}
          loading={revoke.isPending}
          title={`Revoke “${revoking.name}”?`}
          description="Apps using this key will stop working immediately. This cannot be undone."
          confirmLabel="Revoke key"
        />
      )}
      {showing && (
        <Dialog open onClose={() => setShowing(null)} title={`Secret for “${showing.name}”`} size="sm">
          {secrets[showing.id] ? (
            <div className="space-y-3">
              <CopyField label="Secret" value={secrets[showing.id]} secret />
              {showing.role === "service" && <p className="text-xs text-danger">{ROLE_HELP.service}</p>}
            </div>
          ) : reveal.isError ? (
            <Alert tone="danger">{keyErrorMessage(reveal.error)}</Alert>
          ) : (
            <PageSpinner />
          )}
        </Dialog>
      )}
      {usageFor && (
        <UsageDialog
          project={project}
          apiKey={usageFor}
          secret={secrets[usageFor.id] ?? null}
          revealing={reveal.isPending}
          onReveal={() => reveal.mutate(usageFor)}
          onClose={() => setUsageFor(null)}
        />
      )}
    </div>
  );
}

function UsageDialog({
  project,
  apiKey,
  secret,
  revealing,
  onReveal,
  onClose,
}: {
  project: Project;
  apiKey: ApiKey;
  secret: string | null;
  revealing: boolean;
  onReveal: () => void;
  onClose: () => void;
}) {
  const setup = useSetupStatus();
  const sources = useDataSources(project.id);
  const [lang, setLang] = useState<SnippetLang>("curl");
  const [sourceId, setSourceId] = useState<string | null>(null);
  const source = sources.data?.find((s) => s.id === sourceId) ?? sources.data?.[0] ?? null;
  const schema = useSourceSchema(project.id, source?.id ?? null);
  const kind = source?.kind ?? "sql";
  const entity = schema.data?.entities[0]?.name ?? (kind === "sql" ? "{table}" : "{collection}");

  const snippets = buildSnippets(lang, {
    baseUrl: setup.data?.public_url || window.location.origin,
    projectId: project.id,
    sourceId: source?.id ?? "{sid}",
    kind,
    entity,
    key: secret,
  });

  return (
    <Dialog open onClose={onClose} title={`How to use “${apiKey.name}”`} size="lg">
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Data source" className="min-w-48 flex-1">
            {(id) => (
              <Select id={id} value={source?.id ?? ""} onChange={(e) => setSourceId(e.target.value)} disabled={!sources.data?.length}>
                {sources.data?.length ? (
                  sources.data.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.engine})
                    </option>
                  ))
                ) : (
                  <option value="">No data sources yet</option>
                )}
              </Select>
            )}
          </Field>
          {!secret && (
            <Button icon={<Eye className="size-4" />} loading={revealing} disabled={!apiKey.revealable} onClick={onReveal}>
              Reveal to fill in
            </Button>
          )}
        </div>
        {!secret && !apiKey.revealable && <p className="text-xs text-muted">{NOT_REVEALABLE}</p>}

        <Tabs<SnippetLang> items={SNIPPET_LANGS} value={lang} onChange={setLang} />

        {snippets.map((s) => (
          <div key={s.title}>
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-sm font-medium">{s.title}</h3>
              <CopyButton value={s.code} label={`Copy ${s.title}`} />
            </div>
            <pre className="overflow-x-auto rounded-lg border border-border bg-surface-2 px-3 py-2 font-mono text-xs leading-5">{s.code}</pre>
          </div>
        ))}

        <p className="text-xs text-muted">
          <span className="font-medium text-fg">anon</span> keys are read-only; <span className="font-medium text-fg">service</span>{" "}
          keys can read and write. Never ship a service key to browsers or phones.{" "}
          <a href={DOCS_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
            <BookOpen className="size-3.5" /> Full tutorial → docs/DATA_API.md
          </a>
        </p>
      </div>
    </Dialog>
  );
}

function CreateKeyDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [role, setRole] = useState<ApiKeyRole>("anon");
  const [secret, setSecret] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.apiKeys.create(projectId, { name: name.trim(), role }),
    onSuccess: (res) => {
      setSecret(res.secret);
      void queryClient.invalidateQueries({ queryKey: qk.apiKeys(projectId) });
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim()) create.mutate();
  };

  if (secret) {
    return (
      <Dialog
        open
        onClose={onClose}
        title="API key created"
        dismissible={false}
        footer={
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
        }
      >
        <div className="space-y-3">
          <Alert tone="info" title="Copy the secret into your app">
            Project admins can reveal it again later from this page, so it's fine to close this now.
          </Alert>
          <CopyField label="Secret" value={secret} />
          {role === "service" && <p className="text-xs text-danger">{ROLE_HELP.service}</p>}
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Create API key"
      dismissible={!create.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="create-key" variant="primary" loading={create.isPending} disabled={!name.trim()}>
            Create key
          </Button>
        </>
      }
    >
      <form id="create-key" className="space-y-4" onSubmit={onSubmit}>
        <Field label="Name" hint="Something that tells you where it's used, e.g. “mobile app”.">
          {(id) => <Input id={id} required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Role" hint={ROLE_HELP[role]}>
          {(id) => (
            <Select id={id} value={role} onChange={(e) => setRole(e.target.value as ApiKeyRole)}>
              <option value="anon">anon — public</option>
              <option value="service">service — full access</option>
            </Select>
          )}
        </Field>
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      </form>
    </Dialog>
  );
}
