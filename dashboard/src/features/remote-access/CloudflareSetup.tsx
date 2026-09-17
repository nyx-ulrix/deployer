import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, ExternalLink, Globe, KeyRound, Link2, Trash2, Unlink, XCircle } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import type { CloudflareVerifyResult, CloudflareZone, Domain, PublicUrlRequest, RemoteAccess } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyButton } from "../../components/ui/CopyField";
import { Field, Input, Select } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { Table, TBody, Td, Th, THead, Tr } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { normalizeSubdomain, previewUrl, validateSubdomain, buildHostname } from "./hostname";
import { UnlinkDialog } from "./PublicUrlDialogs";
import {
  CLOUDFLARE_TOKEN_TEMPLATE_URL,
  dnsRecordsFrom,
  openedVia,
  permissionFix,
  remoteAccessError,
  REQUIRED_PERMISSIONS,
  type DnsRecord,
} from "./remoteAccess";

function StepShell({
  n,
  title,
  done,
  active,
  children,
  last = false,
}: {
  last?: boolean;
  n: number;
  title: string;
  done: boolean;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <li className="relative flex gap-3 pb-6 last:pb-0">
      {!last && <span className="absolute top-8 bottom-0 left-[13px] w-px bg-border" aria-hidden="true" />}
      <span
        className={cn(
          "relative z-[1] flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
          done && "border-accent bg-accent text-accent-fg",
          !done && active && "border-accent bg-surface text-accent",
          !done && !active && "border-border bg-surface text-muted",
        )}
        aria-hidden="true"
      >
        {done ? <Check className="size-4" /> : n}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className={cn("mt-0.5 font-semibold", !active && !done && "text-muted")}>
          <span className="sr-only">Step {n}{done ? " (done)" : ""}: </span>
          {title}
        </h3>
        <div className="mt-2">{children}</div>
      </div>
    </li>
  );
}

export function CloudflareSetup({
  data,
  onUsePublicUrl,
  usingPublicUrl,
}: {
  data: RemoteAccess;
  onUsePublicUrl: (body: PublicUrlRequest) => void;
  usingPublicUrl: boolean;
}) {
  const cf = data.cloudflare;
  const [token, setToken] = useState("");
  const [verified, setVerified] = useState<{ token: string; result: CloudflareVerifyResult } | null>(null);
  const [replacing, setReplacing] = useState(false);
  const [unlinking, setUnlinking] = useState(false);

  const linked = cf.linked && !replacing;
  const zones: CloudflareZone[] =
    cf.zones ??
    (verified?.result.zones.filter((z) => !cf.account || z.account_id === cf.account.id) ?? []);
  const hasActiveDomain = cf.domains.some((d) => d.status === "active");

  return (
    <div className="space-y-4">
      {cf.linked && cf.token_valid === false && !replacing && (
        <Alert
          tone="danger"
          title="Cloudflare rejected the stored API token"
          action={
            <Button size="sm" onClick={() => setReplacing(true)}>
              Replace token
            </Button>
          }
        >
          The token was probably deleted, expired or rolled. The tunnel may keep running, but Deployer can't change
          hostnames until you paste a new token.
        </Alert>
      )}
      {cf.linked && cf.token_valid === null && (
        <Alert tone="warning" title="Couldn't reach Cloudflare">
          Live tunnel status is unavailable right now. Deployer will retry automatically.
        </Alert>
      )}

      <ol>
        <StepShell n={1} title="Create an API token" done={linked || Boolean(verified?.result.ok)} active={!linked}>
          {linked ? (
            <p className="text-sm text-muted">
              Token stored (encrypted).{" "}
              <button type="button" className="font-medium text-accent hover:underline" onClick={() => setReplacing(true)}>
                Replace token
              </button>
            </p>
          ) : (
            <TokenStep
              token={token}
              setToken={setToken}
              verified={verified?.token === token ? verified.result : null}
              onVerified={(result) => setVerified({ token, result })}
            />
          )}
        </StepShell>

        <StepShell n={2} title="Link your Cloudflare account" done={linked} active={!linked && Boolean(verified?.result.ok)}>
          {linked ? (
            <div className="space-y-2 text-sm">
              <p>
                Account <strong>{cf.account?.name ?? "—"}</strong>
                {cf.tunnel && (
                  <>
                    {" "}
                    · tunnel <code className="font-mono">{cf.tunnel.name}</code>{" "}
                    <Badge tone={cf.tunnel.status === "healthy" ? "success" : cf.tunnel.status ? "warning" : "neutral"}>
                      {cf.tunnel.status ?? "unknown"}
                    </Badge>{" "}
                    <span className="text-muted">
                      {cf.tunnel.connections} connection{cf.tunnel.connections === 1 ? "" : "s"}
                    </span>
                  </>
                )}
              </p>
              <Button size="sm" variant="outline-danger" icon={<Unlink className="size-3.5" />} onClick={() => setUnlinking(true)}>
                Unlink Cloudflare…
              </Button>
            </div>
          ) : verified?.token === token && verified.result.ok ? (
            <LinkStep
              token={token}
              result={verified.result}
              currentAccountId={cf.account?.id ?? null}
              onLinked={() => {
                setReplacing(false);
                setToken("");
              }}
            />
          ) : (
            <p className="text-sm text-muted">Verify a token with all four permissions first.</p>
          )}
        </StepShell>

        <StepShell n={3} title="Add a hostname" done={cf.domains.length > 0} active={linked}>
          {linked ? (
            <HostnameStep
              data={data}
              zones={zones}
              onNeedZones={() => setReplacing(true)}
              onUsePublicUrl={(domainId) => onUsePublicUrl({ domain_id: domainId })}
              usingPublicUrl={usingPublicUrl}
            />
          ) : (
            <p className="text-sm text-muted">Link your account first.</p>
          )}
        </StepShell>

        <StepShell
          last
          n={4}
          title="Use it as the public URL"
          done={cf.domains.some((d) => d.url.replace(/\/+$/, "") === data.public_url.replace(/\/+$/, ""))}
          active={linked && hasActiveDomain}
        >
          <p className="text-sm text-muted">
            Invite links, OAuth callbacks and host devices use the public URL. Pick <strong>Use as public URL</strong> on
            an active hostname above once the connector is running.
          </p>
          {linked && hasActiveDomain && !data.connector.running && (
            <Alert tone="warning" className="mt-2">
              The connector isn't running yet, so the hostname won't load. Check the connector status above.
            </Alert>
          )}
          {usingPublicUrl && <p className="mt-2 text-sm text-muted">Switching…</p>}
        </StepShell>
      </ol>

      {unlinking && <UnlinkDialog data={data} onClose={() => setUnlinking(false)} />}
    </div>
  );
}

function TokenStep({
  token,
  setToken,
  verified,
  onVerified,
}: {
  token: string;
  setToken: (t: string) => void;
  verified: CloudflareVerifyResult | null;
  onVerified: (r: CloudflareVerifyResult) => void;
}) {
  const verify = useMutation({
    mutationFn: () => api.remoteAccess.verify(token.trim()),
    onSuccess: onVerified,
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (token.trim()) verify.mutate();
  };
  const missing = new Set((verified?.missing_permissions ?? []).map((m) => m.toLowerCase()));

  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted">
        Create a <strong>Custom Token</strong> in your Cloudflare profile with these permissions. Deployer never asks
        for your Cloudflare password, and the token is stored encrypted.
      </p>
      <Table>
        <THead>
          <Tr>
            <Th>Scope</Th>
            <Th>Permission</Th>
            <Th>Access</Th>
            {verified && <Th>Check</Th>}
          </Tr>
        </THead>
        <TBody>
          {REQUIRED_PERMISSIONS.map((p) => {
            const isMissing = missing.has(p.name.toLowerCase());
            return (
              <Tr key={p.name} className={cn(isMissing && "bg-danger-soft/50")}>
                <Td>{p.scope}</Td>
                <Td className="font-medium">
                  {p.permission}
                  {!p.prefilled && (
                    <Badge tone="warning" className="ml-1.5" title="The template link can't pre-fill this one">
                      add by hand
                    </Badge>
                  )}
                </Td>
                <Td>{p.access}</Td>
                {verified && (
                  <Td>
                    {isMissing ? (
                      <span className="inline-flex items-center gap-1 text-danger">
                        <XCircle className="size-4" /> Missing
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-success">
                        <CheckCircle2 className="size-4" /> OK
                      </span>
                    )}
                  </Td>
                )}
              </Tr>
            );
          })}
        </TBody>
      </Table>
      <div className="flex flex-wrap items-center gap-2">
        <a
          href={CLOUDFLARE_TOKEN_TEMPLATE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 text-xs font-medium shadow-sm hover:bg-surface-2"
        >
          <KeyRound className="size-3.5" /> Open Cloudflare token page <ExternalLink className="size-3" />
        </a>
        <span className="text-xs text-muted">Pre-fills Account Settings, Zone and DNS.</span>
      </div>
      <Alert tone="warning" title="Add “Account → Cloudflare Tunnel → Edit” yourself">
        Cloudflare's template link can't include the Tunnel permission. On the token page click <em>+ Add more</em>,
        choose <strong>Account → Cloudflare Tunnel → Edit</strong>, and set Account Resources to the account that owns
        your domain. A token with only <em>Read</em> on Tunnel or DNS passes Verify but fails later when Deployer creates
        the tunnel or DNS record.
      </Alert>

      <form className="space-y-2" onSubmit={onSubmit}>
        <Field label="API token">
          {(id) => (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id={id}
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste the token Cloudflare shows once"
              />
              <Button type="submit" variant="primary" loading={verify.isPending} disabled={!token.trim()}>
                Verify
              </Button>
            </div>
          )}
        </Field>
        {verify.error && <Alert tone="danger">{remoteAccessError(verify.error)}</Alert>}
      </form>

      {verified && (
        <div className="space-y-2">
          {verified.ok ? (
            <Alert tone="success" title="Token verified">
              Found {verified.accounts.length} account{verified.accounts.length === 1 ? "" : "s"} and{" "}
              {verified.zones.length} domain{verified.zones.length === 1 ? "" : "s"}.
            </Alert>
          ) : (
            <Alert tone="danger" title="The token is missing permissions">
              <ul className="mt-1 space-y-1">
                {verified.missing_permissions.map((m) => (
                  <li key={m}>
                    <strong className="text-danger">{m}</strong> — {permissionFix(m)}
                  </li>
                ))}
              </ul>
              <p className="mt-1">Fix the token in Cloudflare, then click Verify again (the token value stays the same).</p>
            </Alert>
          )}
          {verified.zones.length > 0 && (
            <p className="text-xs text-muted">
              Domains: {verified.zones.map((z) => `${z.name}${z.status !== "active" ? ` (${z.status})` : ""}`).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function LinkStep({
  token,
  result,
  currentAccountId,
  onLinked,
}: {
  token: string;
  result: CloudflareVerifyResult;
  currentAccountId: string | null;
  onLinked: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState(
    result.accounts.find((a) => a.id === currentAccountId)?.id ?? result.accounts[0]?.id ?? "",
  );
  const link = useMutation({
    mutationFn: () => api.remoteAccess.link(token.trim(), accountId),
    onSuccess: (res) => {
      queryClient.setQueryData(qk.remoteAccess, res);
      toast.success("Cloudflare linked. The tunnel connector is starting.");
      onLinked();
    },
  });
  const zonesIn = result.zones.filter((z) => z.account_id === accountId);
  return (
    <form
      className="space-y-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        if (accountId) link.mutate();
      }}
    >
      <Field label="Account" hint={`${zonesIn.length} domain${zonesIn.length === 1 ? "" : "s"} in this account.`}>
        {(id) => (
          <Select id={id} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            {result.accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <p className="text-muted">
        Deployer finds or creates a tunnel named <code className="font-mono">deployer-…</code> in this account and starts
        the connector on this PC. Nothing is exposed until you add a hostname.
      </p>
      {link.error && <Alert tone="danger">{remoteAccessError(link.error)}</Alert>}
      <Button type="submit" variant="primary" icon={<Link2 className="size-4" />} loading={link.isPending} disabled={!accountId}>
        Link account
      </Button>
    </form>
  );
}

function HostnameStep({
  data,
  zones,
  onNeedZones,
  onUsePublicUrl,
  usingPublicUrl,
}: {
  data: RemoteAccess;
  zones: CloudflareZone[];
  onNeedZones: () => void;
  onUsePublicUrl: (domainId: string) => void;
  usingPublicUrl: boolean;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [zoneId, setZoneId] = useState(zones[0]?.id ?? "");
  const zone = zones.find((z) => z.id === zoneId) ?? zones[0] ?? null;
  const [sub, setSub] = useState("deployer");
  const [conflict, setConflict] = useState<DnsRecord[] | null>(null);
  const [removing, setRemoving] = useState<Domain | null>(null);

  const zoneName = zone?.name ?? "";
  const normalized = normalizeSubdomain(sub, zoneName);
  const error = zone ? validateSubdomain(normalized, zoneName) : null;
  const preview = zone ? previewUrl(normalized, zoneName) : null;

  const add = useMutation({
    mutationFn: (overwrite: boolean) =>
      api.remoteAccess.addHostname({ zone_id: zone?.id ?? "", hostname: buildHostname(normalized, zoneName), overwrite }),
    onSuccess: (domain) => {
      setConflict(null);
      void queryClient.invalidateQueries({ queryKey: qk.remoteAccess });
      toast.success(`${domain.hostname} added.`);
    },
    onError: (e) => {
      const records = dnsRecordsFrom(e);
      if (records) setConflict(records);
    },
  });

  const remove = useMutation({
    mutationFn: (d: Domain) => api.remoteAccess.removeHostname(d.id),
    onSuccess: (_, d) => {
      void queryClient.invalidateQueries({ queryKey: qk.remoteAccess });
      void queryClient.invalidateQueries({ queryKey: qk.instanceSettings });
      toast.success(`${d.hostname} removed.`);
      setRemoving(null);
    },
    onError: (e) => toast.error(remoteAccessError(e), "Couldn't remove hostname"),
  });

  return (
    <div className="space-y-4 text-sm">
      {zones.length === 0 ? (
        <Alert
          tone="info"
          title="Load your domains"
          action={
            <Button size="sm" onClick={onNeedZones}>
              Paste token
            </Button>
          }
        >
          Deployer doesn't keep your domain list. Paste your API token again and verify it to choose a domain.
        </Alert>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (zone && !error) add.mutate(false);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Subdomain" error={sub && error ? error : undefined} hint="Leave empty to use the domain itself.">
              {(id) => (
                <Input
                  id={id}
                  value={sub}
                  onChange={(e) => setSub(e.target.value)}
                  placeholder="deployer"
                  autoCapitalize="off"
                  spellCheck={false}
                  aria-invalid={Boolean(sub && error)}
                />
              )}
            </Field>
            <Field label="Domain">
              {(id) => (
                <Select id={id} value={zone?.id ?? ""} onChange={(e) => setZoneId(e.target.value)}>
                  {zones.map((z) => (
                    <option key={z.id} value={z.id} disabled={z.status !== "active"}>
                      {z.name}
                      {z.status !== "active" ? ` (${z.status})` : ""}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-2 px-3 py-2" aria-live="polite">
            <Globe className="size-4 text-muted" />
            <span className="text-xs text-muted">Preview</span>
            <code className={cn("min-w-0 flex-1 truncate font-mono", !preview && "text-muted")}>
              {preview ?? "—"}
            </code>
          </div>
          {add.error && !dnsRecordsFrom(add.error) && <Alert tone="danger">{remoteAccessError(add.error)}</Alert>}
          <Button type="submit" variant="primary" loading={add.isPending && conflict === null} disabled={!zone || Boolean(error)}>
            Add hostname
          </Button>
        </form>
      )}

      {data.cloudflare.domains.length > 0 && (
        <DomainsTable data={data} onRemove={setRemoving} onUsePublicUrl={onUsePublicUrl} busy={usingPublicUrl} />
      )}

      {conflict && (
        <ConfirmDialog
          open
          onClose={() => setConflict(null)}
          onConfirm={() => add.mutate(true)}
          loading={add.isPending}
          title={`${buildHostname(normalized, zoneName)} already has DNS records`}
          confirmLabel="Overwrite records"
          description="Deployer will replace these with a CNAME to your tunnel. Make sure nothing else uses them."
        >
          {conflict.length > 0 && (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {conflict.map((r) => (
                <li key={r.id || `${r.type}:${r.content}`} className="flex items-center gap-2 px-3 py-2 text-xs">
                  <Badge>{r.type}</Badge>
                  <code className="min-w-0 flex-1 truncate font-mono">{r.content}</code>
                </li>
              ))}
            </ul>
          )}
        </ConfirmDialog>
      )}

      {removing && (
        <ConfirmDialog
          open
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing)}
          loading={remove.isPending}
          title={`Remove ${removing.hostname}?`}
          confirmLabel="Remove hostname"
          description="Deletes its DNS record and stops routing it to this Deployer."
        >
          {openedVia(removing.hostname) && (
            <Alert tone="danger" title="You're using this page through this hostname">
              The page will lose its connection. Continue from <code>http://localhost</code> on the Deployer PC.
            </Alert>
          )}
          {data.public_url.includes(removing.hostname) && (
            <Alert tone="warning">It's the current public URL, which will revert to the local address.</Alert>
          )}
        </ConfirmDialog>
      )}
    </div>
  );
}

function DomainsTable({
  data,
  onRemove,
  onUsePublicUrl,
  busy,
}: {
  data: RemoteAccess;
  onRemove: (d: Domain) => void;
  onUsePublicUrl: (domainId: string) => void;
  busy: boolean;
}) {
  return (
    <Table>
      <THead>
        <Tr>
          <Th>Hostname</Th>
          <Th>Status</Th>
          <Th className="text-right">Actions</Th>
        </Tr>
      </THead>
      <TBody>
        {data.cloudflare.domains.map((d) => {
          const isPublic = d.url.replace(/\/+$/, "") === data.public_url.replace(/\/+$/, "");
          return (
            <Tr key={d.id}>
              <Td className="min-w-48">
                <div className="flex items-center gap-1">
                  <a href={d.url} target="_blank" rel="noopener noreferrer" className="font-mono font-medium hover:text-accent hover:underline">
                    {d.hostname}
                  </a>
                  <CopyButton value={d.url} label={`Copy ${d.url}`} className="size-7" />
                </div>
                {isPublic && <Badge tone="accent">Public URL</Badge>}
              </Td>
              <Td>
                <Badge tone={d.status === "active" ? "success" : d.status === "error" ? "danger" : "warning"}>{d.status}</Badge>
                {d.status_message && <p className="mt-0.5 text-xs text-muted">{d.status_message}</p>}
              </Td>
              <Td className="text-right">
                <div className="flex flex-wrap justify-end gap-1.5">
                  {!isPublic && (
                    <Button
                      size="sm"
                      loading={busy}
                      disabled={d.status !== "active"}
                      title={d.status !== "active" ? "Available once the hostname is active" : undefined}
                      onClick={() => onUsePublicUrl(d.id)}
                    >
                      Use as public URL
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="text-danger" icon={<Trash2 className="size-3.5" />} onClick={() => onRemove(d)}>
                    Remove
                  </Button>
                </div>
              </Td>
            </Tr>
          );
        })}
      </TBody>
    </Table>
  );
}
