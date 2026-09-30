import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { InstanceSettings, InstanceSettingsUpdate, ProviderName, ProviderSettings } from "../../api/types";
import { ProviderIcon } from "../../components/layout/Brand";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { CopyField } from "../../components/ui/CopyField";
import { ExtLink } from "../../components/ui/ExtLink";
import { Field, Input } from "../../components/ui/Input";
import { Alert } from "../../components/ui/States";
import { StepCard, type StepStatus } from "../../components/ui/StepCard";
import { useToast } from "../../components/ui/toast-context";
import { PROVIDER_LABELS } from "../../lib/oauthErrors";
import { isLocalUrl } from "../../lib/url";
import {
  callbackUrls,
  deriveSigninSteps,
  githubPrefillUrl,
  GITHUB_STEP_TITLES,
  GOOGLE_STEP_TITLES,
  oauthValueError,
} from "./signinSteps";

/** "I've done this" for steps that happen in Google's/GitHub's console, where Deployer can't see progress. */
function DoneButton({ status, onClick }: { status: StepStatus; onClick: () => void }) {
  if (status === "done") return null;
  return (
    <Button size="sm" variant="primary" icon={<Check className="size-4" />} onClick={onClick}>
      I've done this
    </Button>
  );
}

function CallbackFields({ urls, label }: { urls: string[]; label: string }) {
  return (
    <div className="space-y-2">
      {urls.map((url, i) => (
        <CopyField key={url} label={i === 0 ? label : `${label} (this PC)`} value={url} />
      ))}
    </div>
  );
}

type GuideProps = {
  steps: StepStatus[];
  ack: (step: number) => void;
  homepage: string;
  callbacks: string[];
  paste: ReactNode;
  configured: boolean;
};

function GitHubGuide({ steps, ack, homepage, callbacks, paste, configured }: GuideProps) {
  return (
    <>
      <StepCard n={1} title={GITHUB_STEP_TITLES[0]} status={steps[0]} summary="GitHub's form opens pre-filled">
        <div className="space-y-3">
          <p className="text-muted">
            This opens GitHub's <em>Register a new OAuth app</em> form with the name, homepage and callback URL filled
            in. Check them, then click <strong>Register application</strong>. For an organization, use the
            organization's <em>Settings → Developer settings → OAuth Apps</em> instead.
          </p>
          <a
            href={githubPrefillUrl(homepage)}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-transparent bg-accent px-3.5 text-sm font-medium text-accent-fg shadow-sm hover:bg-accent-hover"
          >
            Open GitHub's form <ExternalLink className="size-4" />
          </a>
          <p className="text-xs text-muted">If a field comes up empty, copy it from here:</p>
          <CopyField label="Application name" value="Deployer" />
          <CopyField label="Homepage URL" value={homepage} />
          <CallbackFields urls={callbacks.slice(0, 1)} label="Authorization callback URL" />
          {callbacks.length > 1 && (
            <div className="space-y-2">
              <p className="text-muted">
                GitHub accepts up to 10 callback URLs. After registering, click <em>Add redirect URI</em> on the app's
                page and add this one too, so sign-in on the Deployer PC keeps working if the public URL changes back:
              </p>
              <CopyField label="Callback URL (this PC)" value={callbacks[1]} />
            </div>
          )}
          <DoneButton status={steps[0]} onClick={() => ack(0)} />
        </div>
      </StepCard>
      <StepCard n={2} title={GITHUB_STEP_TITLES[1]} status={steps[1]} summary="GitHub shows it only once">
        <div className="space-y-3">
          <p className="text-fg/90">
            On the app's page, copy the <strong>Client ID</strong>. Then, under <em>Client secrets</em>, click{" "}
            <strong>Generate a new client secret</strong> and copy it right away — GitHub shows it only once. Lost it?
            Generate another one.
          </p>
          <DoneButton status={steps[1]} onClick={() => ack(1)} />
        </div>
      </StepCard>
      <StepCard n={3} title={GITHUB_STEP_TITLES[2]} status={steps[2]} open={configured || undefined}>
        {paste}
      </StepCard>
    </>
  );
}

function GoogleGuide({ steps, ack, homepage, callbacks, paste, configured }: GuideProps) {
  const gcp = (path: string) => `https://console.cloud.google.com/${path}`;
  return (
    <>
      <StepCard n={1} title={GOOGLE_STEP_TITLES[0]} status={steps[0]} summary="Free; no billing account needed">
        <div className="space-y-3">
          <p className="text-fg/90">
            <ExtLink href={gcp("projectcreate")}>Create a project</ExtLink> named e.g. “Deployer”. Already have
            one? Pick it in the project selector at the top of the console instead. The next links open in whichever
            project is selected there.
          </p>
          <DoneButton status={steps[0]} onClick={() => ack(0)} />
        </div>
      </StepCard>
      <StepCard n={2} title={GOOGLE_STEP_TITLES[1]} status={steps[1]} summary="What people see on Google's consent screen">
        <div className="space-y-3">
          <p className="text-fg/90">
            Open <ExtLink href={gcp("auth/branding")}>Google Auth Platform → Branding</ExtLink> (click{" "}
            <em>Get started</em> if Google asks). Fill in the <strong>App name</strong> (“Deployer”), your{" "}
            <strong>User support email</strong> and the <strong>Developer contact</strong> email, then save. Skip the
            logo: uploading one makes Google review the app.
          </p>
          <DoneButton status={steps[1]} onClick={() => ack(1)} />
        </div>
      </StepCard>
      <StepCard n={3} title={GOOGLE_STEP_TITLES[2]} status={steps[2]} summary="External · Testing or published">
        <div className="space-y-3">
          <p className="text-fg/90">
            On <ExtLink href={gcp("auth/audience")}>Audience</ExtLink> choose <strong>External</strong>, then decide:
          </p>
          <ul className="list-disc space-y-1.5 pl-5 text-fg/90">
            <li>
              <strong>Testing</strong> — only Google accounts you add under <em>Test users</em> (up to 100) can sign in.
              Fine for you and a few friends; add yourself first.
            </li>
            <li>
              <strong>Publish app</strong> — any Google account can use the button (Deployer's own sign-up and invite
              rules still apply). Needs the Branding page filled in; Deployer only asks for basic sign-in (name,
              email, profile picture), so Google doesn't review it.
            </li>
          </ul>
          <DoneButton status={steps[2]} onClick={() => ack(2)} />
        </div>
      </StepCard>
      <StepCard n={4} title={GOOGLE_STEP_TITLES[3]} status={steps[3]} summary="Web application + redirect URI">
        <div className="space-y-3">
          <p className="text-fg/90">
            Open <ExtLink href={gcp("auth/clients/create")}>Clients → Create client</ExtLink>, choose{" "}
            <strong>Web application</strong> and name it “Deployer”. Under <strong>Authorized redirect URIs</strong>{" "}
            click <em>Add URI</em> for each of these (JavaScript origins can stay empty), then click{" "}
            <strong>Create</strong>.
          </p>
          <CallbackFields urls={callbacks} label="Authorized redirect URI" />
          {!homepage.startsWith("https://") && !isLocalUrl(homepage) && (
            <Alert tone="warning">
              Your public URL isn't HTTPS. Google only accepts <code>http://localhost</code> redirect URIs without
              HTTPS; use a Tailscale Funnel or Cloudflare Tunnel address for access from other devices.
            </Alert>
          )}
          <DoneButton status={steps[3]} onClick={() => ack(3)} />
        </div>
      </StepCard>
      <StepCard n={5} title={GOOGLE_STEP_TITLES[4]} status={steps[4]} summary="Google shows the secret only once">
        <div className="space-y-3">
          <p className="text-fg/90">
            The dialog after <em>Create</em> shows the <strong>Client ID</strong> and <strong>Client secret</strong>.
            Copy both now (or download the JSON) — Google shows the secret only once. Lost it? Open the client and
            click <em>Add secret</em>.
          </p>
          <DoneButton status={steps[4]} onClick={() => ack(4)} />
        </div>
      </StepCard>
      <StepCard n={6} title={GOOGLE_STEP_TITLES[5]} status={steps[5]} open={configured || undefined}>
        {paste}
      </StepCard>
    </>
  );
}

function CredentialsForm({ provider, current, homepage }: { provider: ProviderName; current: ProviderSettings; homepage: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [clientId, setClientId] = useState(current.client_id ?? "");
  const [secret, setSecret] = useState("");
  const label = PROVIDER_LABELS[provider];
  const idError = oauthValueError(provider, "id", clientId);
  const secretError = oauthValueError(provider, "secret", secret);

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
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
      <Field label="Client ID" error={idError ?? undefined}>
        {(id) => (
          <Input
            id={id}
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            aria-invalid={Boolean(idError)}
            autoComplete="off"
            spellCheck={false}
            required
          />
        )}
      </Field>
      <Field
        label="Client secret"
        error={secretError ?? undefined}
        hint={current.secret_set ? "A secret is saved. Leave blank to keep it." : undefined}
      >
        {(id) => (
          <Input
            id={id}
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            aria-invalid={Boolean(secretError)}
            placeholder={current.secret_set ? "•••••••• (saved)" : ""}
            autoComplete="new-password"
            spellCheck={false}
            required={!current.secret_set}
          />
        )}
      </Field>
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <Button
          type="submit"
          variant="primary"
          loading={save.isPending}
          disabled={!clientId.trim() || needsSecret || Boolean(idError || secretError)}
        >
          Save {label}
        </Button>
        {(current.client_id || current.secret_set) && (
          <Button variant="outline-danger" onClick={clear} disabled={save.isPending}>
            Remove
          </Button>
        )}
      </div>
      {current.configured && (
        <p className="text-xs text-muted sm:col-span-2">
          {/* On the public URL, because that's where the provider redirects back (and where the sign-in cookie must live). */}
          <ExtLink href={`${homepage}${api.auth.oauthStartUrl(provider, "/")}`}>Test sign-in</ExtLink> opens {label}'s
          sign-in in a new tab.
          {provider === "google" &&
            " Google can take a few minutes to apply redirect URI changes; if it says redirect_uri_mismatch, wait and try again."}
        </p>
      )}
    </form>
  );
}

/** Guided setup + credential form for one OAuth provider (used by the setup wizard and instance settings). */
export function OAuthProviderCard({
  provider,
  settings,
  defaultExpanded = true,
}: {
  provider: ProviderName;
  settings: InstanceSettings;
  defaultExpanded?: boolean;
}) {
  const current = settings[provider];
  const [expanded, setExpanded] = useState(defaultExpanded);
  // Console steps the user ticked off. Component state only: Deployer can't check Google's or GitHub's side.
  const [acknowledged, setAcknowledged] = useState<number[]>([]);
  const label = PROVIDER_LABELS[provider];
  const homepage = settings.public_url.replace(/\/+$/, "");
  const Guide = provider === "google" ? GoogleGuide : GitHubGuide;
  const steps = deriveSigninSteps(provider === "google" ? GOOGLE_STEP_TITLES.length : GITHUB_STEP_TITLES.length, {
    configured: current.configured,
    clientIdSaved: Boolean(current.client_id),
    acknowledged,
  });

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
          {expanded ? "Hide" : current.configured ? "Edit" : "Guided setup"}
        </Button>
      </header>
      {expanded && (
        <div className="space-y-3 border-t border-border px-4 py-4 sm:px-5">
          <p className="text-sm text-muted">
            {provider === "google"
              ? "Google doesn't let apps create sign-in clients for you, so these steps take about 5 minutes."
              : "GitHub's form opens pre-filled, so this takes about 2 minutes."}
          </p>
          {isLocalUrl(homepage) && (
            <Alert tone="info" title="Only this PC can use these callback URLs">
              Your public URL is <code>{homepage}</code>, so friends on other devices can't sign in yet. Set up a public
              address in{" "}
              <Link to="/settings/remote-access" target="_blank" className="font-medium text-accent hover:underline">
                Settings → Domains & remote access
              </Link>
              , then add the new callback URLs to this {label} app.
            </Alert>
          )}
          <Guide
            steps={steps}
            ack={(i) => setAcknowledged((a) => [...a, i])}
            homepage={homepage}
            callbacks={callbackUrls(provider, homepage, settings.local_url)}
            configured={current.configured}
            paste={<CredentialsForm provider={provider} current={current} homepage={homepage} />}
          />
        </div>
      )}
    </section>
  );
}
