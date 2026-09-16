import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { InstanceSettings, InstanceSettingsUpdate, ProviderName } from "../../api/types";
import { ProviderIcon } from "../../components/layout/Brand";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { CopyField } from "../../components/ui/CopyField";
import { Field, Input } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { PROVIDER_LABELS } from "../../lib/oauthErrors";

function ExtLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex items-center gap-0.5 font-medium text-accent hover:underline"
    >
      {children}
      <ExternalLink className="size-3" />
    </a>
  );
}

function Steps({ children }: { children: ReactNode }) {
  return <ol className="space-y-2.5 text-sm [counter-reset:step]">{children}</ol>;
}

function Step({ children }: { children: ReactNode }) {
  return (
    <li className="flex gap-2.5 [counter-increment:step] before:flex before:size-5 before:shrink-0 before:items-center before:justify-center before:rounded-full before:bg-accent-soft before:text-[11px] before:font-semibold before:text-accent before:content-[counter(step)]">
      <div className="min-w-0 flex-1 text-fg/90">{children}</div>
    </li>
  );
}

function GoogleSteps({ homepage, callback }: { homepage: string; callback: string }) {
  return (
    <Steps>
      <Step>
        Open the <ExtLink href="https://console.cloud.google.com/apis/credentials">Google Cloud Console → Credentials</ExtLink>{" "}
        page and <strong>create a project</strong> (or pick an existing one) from the project selector.
      </Step>
      <Step>
        Configure the <strong>OAuth consent screen</strong>: choose <em>External</em>, enter an app name (e.g.
        “Deployer”) and your support email. Add the <code>openid</code>, <code>email</code> and{" "}
        <code>profile</code> scopes. While the app is in <em>Testing</em>, add yourself as a test user.
      </Step>
      <Step>
        Back on Credentials, click <strong>Create credentials → OAuth client ID</strong> and choose application
        type <strong>Web application</strong>.
      </Step>
      <Step>
        Under <strong>Authorized JavaScript origins</strong> add your homepage URL, and under{" "}
        <strong>Authorized redirect URIs</strong> add the callback URL:
        <div className="mt-2 space-y-2">
          <CopyField label="Homepage URL (JavaScript origin)" value={homepage} />
          <CopyField label="Authorized redirect URI" value={callback} />
        </div>
      </Step>
      <Step>
        Click <strong>Create</strong>, then copy the <strong>Client ID</strong> and <strong>Client secret</strong>{" "}
        into the fields below.
      </Step>
    </Steps>
  );
}

function GitHubSteps({ homepage, callback }: { homepage: string; callback: string }) {
  return (
    <Steps>
      <Step>
        Open <ExtLink href="https://github.com/settings/applications/new">GitHub → Register a new OAuth app</ExtLink>{" "}
        (for an organization, use the organization's <em>Developer settings</em> instead).
      </Step>
      <Step>
        Enter an application name (e.g. “Deployer on my PC”) and paste the URLs:
        <div className="mt-2 space-y-2">
          <CopyField label="Homepage URL" value={homepage} />
          <CopyField label="Authorization callback URL" value={callback} />
        </div>
      </Step>
      <Step>
        Click <strong>Register application</strong>. Copy the <strong>Client ID</strong>, then click{" "}
        <strong>Generate a new client secret</strong> and copy it right away — GitHub shows it only once.
      </Step>
      <Step>Paste both values into the fields below and save.</Step>
    </Steps>
  );
}

/** Setup instructions + credential form for one OAuth provider (used by the setup wizard and instance settings). */
export function OAuthProviderCard({
  provider,
  settings,
  defaultExpanded = true,
}: {
  provider: ProviderName;
  settings: InstanceSettings;
  defaultExpanded?: boolean;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const current = settings[provider];
  const [clientId, setClientId] = useState(current.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [expanded, setExpanded] = useState(defaultExpanded);
  const label = PROVIDER_LABELS[provider];
  const homepage = settings.public_url.replace(/\/+$/, "");

  const save = useMutation({
    mutationFn: (body: InstanceSettingsUpdate) => api.instance.updateSettings(body),
    onSuccess: (data, body) => {
      queryClient.setQueryData(qk.instanceSettings, data);
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
      void queryClient.invalidateQueries({ queryKey: qk.providers });
      setSecret("");
      const cleared = body[`${provider}_client_id`] === "";
      if (cleared) setClientId("");
      toast.success(cleared ? `${label} sign-in removed.` : `${label} sign-in saved.`);
    },
    onError: (e) => toast.error(errorMessage(e), `Couldn't save ${label} settings`),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const body: InstanceSettingsUpdate =
      provider === "google"
        ? { google_client_id: clientId.trim(), ...(secret ? { google_client_secret: secret.trim() } : {}) }
        : { github_client_id: clientId.trim(), ...(secret ? { github_client_secret: secret.trim() } : {}) };
    save.mutate(body);
  };

  const clear = () => {
    save.mutate(
      provider === "google"
        ? { google_client_id: "", google_client_secret: "" }
        : { github_client_id: "", github_client_secret: "" },
    );
  };

  const needsSecret = !current.secret_set && !secret;

  return (
    <section className="rounded-xl border border-border bg-surface">
      <header className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
        <span className="flex size-9 items-center justify-center rounded-lg border border-border bg-surface-2">
          <ProviderIcon provider={provider} className="size-5" />
        </span>
        <div className="min-w-0 flex-1 basis-40">
          <h3 className="font-semibold">Sign in with {label}</h3>
          <p className="text-xs text-muted">Uses your own {label} OAuth app.</p>
        </div>
        {current.configured ? <Badge tone="success">Configured</Badge> : <Badge>Not configured</Badge>}
        <Button size="sm" variant="ghost" onClick={() => setExpanded((x) => !x)} aria-expanded={expanded}>
          {expanded ? "Hide" : current.configured ? "Edit" : "Set up"}
        </Button>
      </header>
      {expanded && (
        <div className="space-y-5 border-t border-border px-4 py-4 sm:px-5">
          {provider === "google" ? (
            <GoogleSteps homepage={homepage} callback={current.callback_url} />
          ) : (
            <GitHubSteps homepage={homepage} callback={current.callback_url} />
          )}
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
            <Field label="Client ID">
              {(id) => (
                <Input
                  id={id}
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  required
                />
              )}
            </Field>
            <Field
              label="Client secret"
              hint={current.secret_set ? "A secret is saved. Leave blank to keep it." : undefined}
            >
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  placeholder={current.secret_set ? "•••••••• (saved)" : ""}
                  autoComplete="new-password"
                  spellCheck={false}
                  required={!current.secret_set}
                />
              )}
            </Field>
            {provider === "google" &&
              !settings.public_url.startsWith("https://") &&
              !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?/.test(settings.public_url) && (
              <Alert tone="warning" className="sm:col-span-2">
                Your public URL isn't HTTPS. Google only accepts <code>http://localhost</code> redirect URIs
                without HTTPS; use a Tailscale Funnel or Cloudflare Tunnel address for access from other devices.
              </Alert>
            )}
            <div className="flex flex-wrap gap-2 sm:col-span-2">
              <Button type="submit" variant="primary" loading={save.isPending} disabled={!clientId.trim() || needsSecret}>
                Save {label}
              </Button>
              {(current.client_id || current.secret_set) && (
                <Button variant="outline-danger" onClick={clear} disabled={save.isPending}>
                  Remove
                </Button>
              )}
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
