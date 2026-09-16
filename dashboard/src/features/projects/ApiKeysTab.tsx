import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { ApiKey, ApiKeyRole } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input, Select } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, EmptyState, ErrorState } from "../../components/ui/States";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { formatDate, relativeTime } from "../../lib/format";
import { useProjectContext } from "./project-context";

const ROLE_HELP: Record<ApiKeyRole, string> = {
  anon: "Public key for client apps. Limited to what anonymous users may do.",
  service: "Full access to the project's data. Keep it on servers only — never ship it to browsers or phones.",
};

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

  const revoke = useMutation({
    mutationFn: (k: ApiKey) => api.apiKeys.revoke(project.id, k.id),
    onSuccess: (_d, k) => {
      void queryClient.invalidateQueries({ queryKey: qk.apiKeys(project.id) });
      setRevoking(null);
      toast.success(`Key “${k.name}” revoked.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't revoke key"),
  });

  if (!can("admin")) {
    return <Alert tone="info">Only project admins and owners can manage API keys.</Alert>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted">
          API keys let your apps call this project's data API. Secrets are shown only once when created — Deployer
          stores just a hash.
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
    </div>
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
            I've saved it
          </Button>
        }
      >
        <div className="space-y-3">
          <Alert tone="warning" title="Copy this secret now">
            It won't be shown again. If you lose it, revoke the key and create a new one.
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
