import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, ExternalLink, Globe, KeyRound, Link2, RefreshCw, Trash2, XCircle } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import type { CloudflareVerifyResult, CloudflareZone, Domain, PublicUrlRequest, RemoteAccess } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyButton, CopyField } from "../../components/ui/CopyField";
import { Field, Input, Select } from "../../components/ui/Input";
import { StatusDot } from "../../components/ui/Progress";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { buildHostname, normalizeSubdomain, previewUrl, validateSubdomain } from "./hostname";
import { SignInAppsBox } from "./PublicUrlDialogs";
import {
  CLOUDFLARE_TOKEN_TEMPLATE_URL,
  dnsRecordsFrom,
  openedVia,
  permissionFix,
  remoteAccessError,
  REQUIRED_PERMISSIONS,
  type DnsRecord,
} from "./remoteAccess";
import { connectorHint, deriveSteps, sameUrl, STEP_TITLES, tunnelHealthy, type StepStatus } from "./steps";

const ext = "inline-flex items-center gap-1 font-medium text-accent hover:underline";

function ExtLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={ext}>
      {children} <ExternalLink className="size-3" />
    </a>
  );
}

/** One collapsible step. Open while it's the current step; the user can open any other one. */
function StepCard({ n, status, summary, children }: { n: number; status: StepStatus; summary?: ReactNode; children: ReactNode }) {
  const title = STEP_TITLES[n - 1];
  return (
    <details open={status === "current"} className="group rounded-xl border border-border bg-surface open:shadow-xs">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-3 select-none sm:px-4 [&::-webkit-details-marker]:hidden">
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
            status === "done" && "border-accent bg-accent text-accent-fg",
            status === "current" && "border-accent bg-surface text-accent",
            status === "todo" && "border-border bg-surface text-muted",
          )}
          aria-hidden="true"
        >
          {status === "done" ? <Check className="size-4" /> : n}
        </span>
        <span className="min-w-0 flex-1">
          <span className={cn("block font-semibold", status === "todo" && "text-muted")}>
            <span className="sr-only">Step {n}, {status === "done" ? "done" : status === "current" ? "current step" : "to do"}: </span>
            {title}
          </span>
          {summary && <span className="block truncate text-xs text-muted">{summary}</span>}
        </span>
        <Badge tone={status === "done" ? "success" : status === "current" ? "accent" : "neutral"}>
          {status === "done" ? "Done" : status === "current" ? "Now" : "To do"}
        </Badge>
      </summary>
      <div className="border-t border-border px-3 py-3 text-sm sm:px-4">{children}</div>
    </details>
  );
}

export function CloudflareSetup({
  data,
  onUsePublicUrl,
  usingPublicUrl,
  onTurnOffQuick,
}: {
  data: RemoteAccess;
  onUsePublicUrl: (body: PublicUrlRequest) => void;
  usingPublicUrl: boolean;
  onTurnOffQuick: () => void;
}) {
  const cf = data.cloudflare;
  const [token, setToken] = useState("");
  const [verified, setVerified] = useState<{ token: string; result: CloudflareVerifyResult } | null>(null);
  const [replacing, setReplacing] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);

  const linked = cf.linked && !replacing;
  const current = verified?.token === token ? verified.result : null;
  const zones: CloudflareZone[] =
    (cf.zones?.length ? cf.zones : null) ??
    (verified?.result.zones.filter((z) => !cf.account || z.account_id === cf.account.id) ?? []);
  const steps = deriveSteps(data, { accountAcknowledged: acknowledged, verifiedOk: Boolean(current?.ok), replacing });
  const publicDomain = cf.domains.find((d) => sameUrl(d.url, data.public_url)) ?? null;

  return (
    <div className="space-y-3">
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
          hostnames until you paste a new token (step 2).
        </Alert>
      )}
      {cf.linked && cf.token_valid === null && (
        <Alert tone="warning" title="Couldn't reach Cloudflare">
          Live tunnel status is unavailable right now. Deployer will retry automatically.
        </Alert>
      )}

      <StepCard n={1} status={steps[0]} summary={zones.length > 0 ? zones.map((z) => z.name).join(", ") : "Free plan is enough"}>
        <AccountStep zones={zones} done={steps[0] === "done"} onAcknowledge={() => setAcknowledged(true)} />
      </StepCard>

      <StepCard n={2} status={steps[1]} summary={linked ? "Token stored (encrypted)" : "Four permissions, one paste"}>
        {linked ? (
          <p className="text-muted">
            Your token is stored encrypted on this PC.{" "}
            <button type="button" className={ext} onClick={() => setReplacing(true)}>
              Replace token
            </button>
          </p>
        ) : (
          <TokenStep
            token={token}
            setToken={setToken}
            verified={current}
            onVerified={(result) => setVerified({ token, result })}
            onCancel={cf.linked ? () => setReplacing(false) : undefined}
          />
        )}
      </StepCard>

      <StepCard n={3} status={steps[2]} summary={linked ? `${cf.account?.name ?? "—"} · ${cf.tunnel?.name ?? "tunnel"}` : "One click"}>
        {linked ? (
          <p className="text-muted">
            Linked to <strong className="text-fg">{cf.account?.name ?? "—"}</strong>
            {cf.tunnel && (
              <>
                {" "}
                with tunnel <code className="font-mono">{cf.tunnel.name}</code>
              </>
            )}
            . To switch accounts, unlink in the danger zone below.
          </p>
        ) : current?.ok ? (
          <LinkStep
            token={token}
            result={current}
            currentAccountId={cf.account?.id ?? null}
            onLinked={() => {
              setReplacing(false);
              setToken("");
              setVerified(null);
            }}
          />
        ) : (
          <p className="text-muted">Verify a token with all four permissions in step 2 first.</p>
        )}
      </StepCard>

      <StepCard n={4} status={steps[3]} summary={cf.domains.length ? cf.domains.map((d) => d.hostname).join(", ") : "e.g. deployer.example.com"}>
        {linked ? (
          <HostnameStep data={data} zones={zones} onNeedZones={() => setReplacing(true)} />
        ) : (
          <p className="text-muted">Link your account in step 3 first.</p>
        )}
      </StepCard>

      <StepCard n={5} status={steps[4]} summary={tunnelSummary(data)}>
        <TunnelStep data={data} onTurnOffQuick={onTurnOffQuick} />
      </StepCard>

      <StepCard n={6} status={steps[5]} summary={publicDomain ? publicDomain.url : "Sign-in, invites and host devices use it"}>
        <PublicUrlStep data={data} publicDomain={publicDomain} onUse={(id) => onUsePublicUrl({ domain_id: id })} busy={usingPublicUrl} />
      </StepCard>
    </div>
  );
}

function tunnelSummary(data: RemoteAccess): string {
  const t = data.cloudflare.tunnel;
  if (!t) return "Starts after linking";
  if (tunnelHealthy(data)) return `Healthy · ${t.connections} connection${t.connections === 1 ? "" : "s"}`;
  return data.connector.running ? "Connecting…" : "Connector not running";
}

function AccountStep({ zones, done, onAcknowledge }: { zones: CloudflareZone[]; done: boolean; onAcknowledge: () => void }) {
  return (
    <div className="space-y-3">
      <ol className="list-decimal space-y-1.5 pl-5 text-fg/90">
        <li>
          Sign up at <ExtLink href="https://dash.cloudflare.com/sign-up">dash.cloudflare.com</ExtLink> — the free plan is
          all you need.
        </li>
        <li>
          In Cloudflare choose <strong>Add a domain</strong>, type your domain (e.g. <code>example.com</code>) and pick the{" "}
          <strong>Free</strong> plan.
        </li>
        <li>
          Cloudflare shows two nameservers. Log in where you bought the domain (your registrar) and replace its
          nameservers with those two.
        </li>
        <li>
          Wait until the domain shows <Badge tone="success">Active</Badge> under <em>Websites</em> in Cloudflare. That
          usually takes minutes, sometimes up to a day. Cloudflare emails you when it's ready.
        </li>
      </ol>
      {zones.length > 0 ? (
        <p className="text-muted">
          Domains found in your account:{" "}
          {zones.map((z) => (
            <span key={z.id} className="mr-1.5 inline-flex items-center gap-1">
              <code className="font-mono text-fg">{z.name}</code>
              {z.status !== "active" && <Badge tone="warning">{z.status}</Badge>}
            </span>
          ))}
        </p>
      ) : (
        !done && (
          <Button variant="primary" icon={<Check className="size-4" />} onClick={onAcknowledge}>
            I've done this
          </Button>
        )
      )}
    </div>
  );
}

function TokenStep({
  token,
  setToken,
  verified,
  onVerified,
  onCancel,
}: {
  token: string;
  setToken: (t: string) => void;
  verified: CloudflareVerifyResult | null;
  onVerified: (r: CloudflareVerifyResult) => void;
  onCancel?: () => void;
}) {
  // The token only lives in this component's state and the verify/link requests; it's never persisted or logged.
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
    <div className="space-y-3">
      <p className="text-muted">
        An API token lets Deployer create the tunnel and DNS record in your account — nothing else. Deployer never asks
        for your Cloudflare password, and the token is stored encrypted.
      </p>
      <ol className="list-decimal space-y-1.5 pl-5 text-fg/90">
        <li>
          <ExtLink href={CLOUDFLARE_TOKEN_TEMPLATE_URL}>
            <KeyRound className="size-3.5" /> Open the Cloudflare token page
          </ExtLink>{" "}
          (signed in as the account that owns the domain). It pre-fills three of the four permissions.
        </li>
        <li>
          Click <em>+ Add more</em> and add <strong>Account → Cloudflare Tunnel → Edit</strong> by hand — Cloudflare's
          link can't pre-fill this one.
        </li>
        <li>
          <strong>Account Resources</strong>: Include → the account that owns your domain. <strong>Zone Resources</strong>:
          All zones, or just your domain.
        </li>
        <li>
          <em>Continue to summary</em> → <em>Create Token</em>. Copy the token — Cloudflare shows it only once — and paste
          it below.
        </li>
      </ol>

      <ul className="space-y-1 rounded-lg border border-border p-3">
        {REQUIRED_PERMISSIONS.map((p) => {
          const isMissing = missing.has(p.name.toLowerCase());
          return (
            <li key={p.name} className={cn("flex flex-wrap items-center gap-x-2 gap-y-0.5", isMissing && "text-danger")}>
              {verified ? (
                isMissing ? (
                  <XCircle className="size-4 shrink-0 text-danger" />
                ) : (
                  <CheckCircle2 className="size-4 shrink-0 text-success" />
                )
              ) : (
                <span className="inline-block size-4 shrink-0 rounded border border-border" aria-hidden="true" />
              )}
              <span>
                {p.scope} → <strong>{p.permission}</strong> → {p.access}
              </span>
              {!p.prefilled && (
                <Badge tone="warning" title="The template link can't pre-fill this one">
                  add by hand
                </Badge>
              )}
              {isMissing && <span className="basis-full pl-6 text-xs">{permissionFix(p.name)}</span>}
            </li>
          );
        })}
        {verified?.missing_permissions
          .filter((m) => !REQUIRED_PERMISSIONS.some((p) => p.name.toLowerCase() === m.toLowerCase()))
          .map((m) => (
            <li key={m} className="flex items-center gap-2 text-danger">
              <XCircle className="size-4 shrink-0" /> {m} — {permissionFix(m)}
            </li>
          ))}
      </ul>
      <p className="text-xs text-muted">
        A token with only <em>Read</em> on Tunnel or DNS passes Verify but fails later when Deployer creates the tunnel
        or DNS record.
      </p>

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
              <div className="flex gap-2">
                <Button type="submit" variant="primary" loading={verify.isPending} disabled={!token.trim()}>
                  Verify
                </Button>
                {onCancel && (
                  <Button variant="ghost" onClick={onCancel}>
                    Keep current token
                  </Button>
                )}
              </div>
            </div>
          )}
        </Field>
        {verify.error && <Alert tone="danger">{remoteAccessError(verify.error)}</Alert>}
      </form>

      {verified &&
        (verified.ok ? (
          <Alert tone="success" title="Token verified">
            Found {verified.accounts.length} account{verified.accounts.length === 1 ? "" : "s"} and {verified.zones.length}{" "}
            domain{verified.zones.length === 1 ? "" : "s"}
            {verified.zones.length > 0 && <> ({verified.zones.map((z) => z.name).join(", ")})</>}. Continue with step 3.
          </Alert>
        ) : (
          <Alert tone="danger" title="The token is missing permissions">
            Fix the items marked red above: open the token in Cloudflare (<em>Edit</em>), add the permission, save, then
            click Verify again — the token value stays the same.
          </Alert>
        ))}
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
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (accountId) link.mutate();
      }}
    >
      {result.accounts.length > 1 && (
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
      )}
      <p className="text-muted">
        Deployer creates a tunnel named <code className="font-mono">deployer-…</code> in{" "}
        <strong className="text-fg">{result.accounts.find((a) => a.id === accountId)?.name ?? "your account"}</strong>{" "}
        (or reuses it if it exists), stores your token encrypted on this PC and starts the connector. Nothing is
        reachable from the internet until you add a hostname in step 4.
      </p>
      {link.error && <Alert tone="danger">{remoteAccessError(link.error)}</Alert>}
      <Button type="submit" variant="primary" icon={<Link2 className="size-4" />} loading={link.isPending} disabled={!accountId}>
        Link account
      </Button>
    </form>
  );
}

function HostnameStep({ data, zones, onNeedZones }: { data: RemoteAccess; zones: CloudflareZone[]; onNeedZones: () => void }) {
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
  const tunnelId = data.cloudflare.tunnel?.id;

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
    <div className="space-y-4">
      <p className="text-muted">
        Pick the address people will type. A subdomain like <code>deployer.example.com</code> keeps the rest of your
        domain free for other things. Deployer adds a DNS record for it in Cloudflare — you don't need to touch DNS
        yourself.
      </p>
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
          Deployer couldn't load your domain list from Cloudflare. Paste your API token again in step 2 and verify it to
          choose a domain.
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
                      {z.status !== "active" ? ` (${z.status} — finish step 1)` : ""}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-2 px-3 py-2" aria-live="polite">
            <Globe className="size-4 text-muted" />
            <span className="text-xs text-muted">Your address will be</span>
            <code className={cn("min-w-0 flex-1 truncate font-mono", !preview && "text-muted")}>{preview ?? "—"}</code>
          </div>
          {add.error && !dnsRecordsFrom(add.error) && <Alert tone="danger">{remoteAccessError(add.error)}</Alert>}
          <Button type="submit" variant="primary" loading={add.isPending && conflict === null} disabled={!zone || Boolean(error)}>
            Add hostname
          </Button>
        </form>
      )}

      {data.cloudflare.domains.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {data.cloudflare.domains.map((d) => (
            <li key={d.id} className="space-y-1.5 px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <a href={d.url} target="_blank" rel="noopener noreferrer" className="font-mono font-medium hover:text-accent hover:underline">
                  {d.hostname}
                </a>
                <CopyButton value={d.url} label={`Copy ${d.url}`} className="size-7" />
                <Badge tone={d.status === "active" ? "success" : d.status === "error" ? "danger" : "warning"}>{d.status}</Badge>
                {sameUrl(d.url, data.public_url) && <Badge tone="accent">Public URL</Badge>}
                <Button size="sm" variant="ghost" className="ml-auto text-danger" icon={<Trash2 className="size-3.5" />} onClick={() => setRemoving(d)}>
                  Remove
                </Button>
              </div>
              {d.status_message && <p className="text-xs text-danger">{d.status_message}</p>}
              <p className="truncate font-mono text-xs text-muted" title="The DNS record Deployer created in Cloudflare (proxied)">
                CNAME {d.hostname} → {tunnelId ? `${tunnelId}.cfargotunnel.com` : "your tunnel"}
              </p>
            </li>
          ))}
        </ul>
      )}

      {conflict && (
        <ConfirmDialog
          open
          onClose={() => setConflict(null)}
          onConfirm={() => add.mutate(true)}
          loading={add.isPending}
          title={`${buildHostname(normalized, zoneName)} already has DNS records`}
          confirmLabel="Overwrite records"
          description="Something already uses this name (for example an old website's A record). Deployer can replace it with a CNAME to your tunnel — only do that if nothing else needs it. Otherwise close this and pick another subdomain."
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
          {sameUrl(removing.url, data.public_url) && (
            <Alert tone="warning">It's the current public URL, which will revert to the local address.</Alert>
          )}
        </ConfirmDialog>
      )}
    </div>
  );
}

function TunnelStep({ data, onTurnOffQuick }: { data: RemoteAccess; onTurnOffQuick: () => void }) {
  const t = data.cloudflare.tunnel;
  const healthy = tunnelHealthy(data);
  const hint = connectorHint(data);
  if (!t) return <p className="text-muted">The tunnel starts on this PC as soon as you link your account.</p>;
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2">
        {healthy ? <StatusDot tone="success" pulse /> : data.connector.running ? <RefreshCw className="size-4 animate-spin text-muted" /> : <StatusDot tone="danger" />}
        <span className="font-medium">{tunnelSummary(data)}</span>
        {t.status && <Badge tone={healthy ? "success" : "warning"}>{t.status}</Badge>}
      </p>
      <p className="text-muted">
        The connector on this PC keeps an outgoing connection to Cloudflare open; visitors reach you through it, so no
        router or firewall changes are needed. Status refreshes every 10 seconds.
      </p>
      {healthy ? (
        <Alert tone="success">Your hostname{data.cloudflare.domains.length === 1 ? " is" : "s are"} reachable. Continue with step 6.</Alert>
      ) : (
        hint && (
          <Alert
            tone={data.connector.running ? "warning" : "danger"}
            title={hint.title}
            action={
              data.mode === "quick" ? (
                <Button size="sm" onClick={onTurnOffQuick}>
                  Turn off quick tunnel
                </Button>
              ) : undefined
            }
          >
            <span className="break-words">{hint.body}</span>
          </Alert>
        )
      )}
      {!healthy && data.connector.last_error && !hint?.body.includes(data.connector.last_error) && (
        <p className="font-mono text-xs break-words text-muted">{data.connector.last_error}</p>
      )}
      <p className="text-xs text-muted">
        Browser shows Cloudflare error 1033? DNS is fine but no connector is running (see above). Error 502/504? The
        connector can't reach Deployer's web server — make sure the <code>caddy</code> container is running.
      </p>
    </div>
  );
}

function PublicUrlStep({
  data,
  publicDomain,
  onUse,
  busy,
}: {
  data: RemoteAccess;
  publicDomain: Domain | null;
  onUse: (domainId: string) => void;
  busy: boolean;
}) {
  const settings = useQuery({ queryKey: qk.instanceSettings, queryFn: api.instance.settings, enabled: publicDomain !== null });
  const candidates = data.cloudflare.domains.filter((d) => !sameUrl(d.url, data.public_url));
  const ready = tunnelHealthy(data);
  return (
    <div className="space-y-3">
      <p className="text-muted">
        The public URL is the address Deployer uses for invite links, Google/GitHub sign-in callbacks and host devices.
        Until you switch it, those still use <code>{data.public_url}</code>.
      </p>
      {publicDomain && (
        <>
          <CopyField label="Public URL" value={publicDomain.url} />
          {settings.data && (
            <SignInAppsBox callbacks={{ google: settings.data.google.callback_url, github: settings.data.github.callback_url }} />
          )}
        </>
      )}
      {candidates.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {candidates.map((d) => (
            <Button
              key={d.id}
              variant={publicDomain ? "secondary" : "primary"}
              loading={busy}
              disabled={d.status !== "active" || !ready}
              title={d.status !== "active" ? "Available once the hostname is active" : !ready ? "Wait for the tunnel (step 5)" : undefined}
              onClick={() => onUse(d.id)}
            >
              Use {d.hostname} as public URL
            </Button>
          ))}
        </div>
      )}
      {candidates.length === 0 && !publicDomain && <p className="text-muted">Add a hostname in step 4 first.</p>}
      <Alert tone="info" title="What changes for host devices">
        Devices attached to this Deployer talk to the public URL. Re-enroll a device if it was attached with the old
        address; new invite links use the new URL too. Your sign-in cookie becomes <em>Secure</em> with an https URL, so
        use the dashboard at the new address from now on.
      </Alert>
    </div>
  );
}
