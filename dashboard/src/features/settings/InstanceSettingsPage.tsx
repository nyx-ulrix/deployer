import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useInstanceSettings } from "../../api/hooks";
import type { InstanceSettings } from "../../api/types";
import { Avatar } from "../../components/layout/Brand";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Checkbox, Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, ErrorState, PageHeader } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatDate } from "../../lib/format";
import { PROVIDER_LABELS } from "../../lib/oauthErrors";
import { OAuthProviderCard } from "./OAuthProviderCard";

export function InstanceSettingsPage() {
  const settings = useInstanceSettings();
  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="Instance settings"
        description="Settings for this Deployer installation. Only you, the instance owner, can see this page."
      />
      {settings.isPending ? (
        <PageSpinner />
      ) : settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
      ) : (
        <div className="space-y-5">
          <GeneralCard settings={settings.data} key={`${settings.data.public_url}|${settings.data.allow_signup}`} />
          <section className="space-y-3">
            <div>
              <h2 className="font-semibold">Sign-in providers</h2>
              <p className="text-sm text-muted">
                Deployer ships no shared OAuth keys. Each installation uses its own Google and GitHub OAuth apps.
              </p>
            </div>
            <OAuthProviderCard provider="google" settings={settings.data} defaultExpanded={!settings.data.google.configured} />
            <OAuthProviderCard provider="github" settings={settings.data} defaultExpanded={!settings.data.github.configured} />
          </section>
          <UsersCard />
        </div>
      )}
    </div>
  );
}

function GeneralCard({ settings }: { settings: InstanceSettings }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState(settings.public_url);
  const [allowSignup, setAllowSignup] = useState(settings.allow_signup);
  const urlChanged = url.trim().replace(/\/+$/, "") !== settings.public_url.replace(/\/+$/, "");
  const dirty = urlChanged || allowSignup !== settings.allow_signup;
  const anyProvider = settings.google.configured || settings.github.configured;

  let valid = false;
  try {
    const u = new URL(url);
    valid = u.protocol === "http:" || u.protocol === "https:";
  } catch {
    valid = false;
  }

  const save = useMutation({
    mutationFn: () =>
      api.instance.updateSettings({ public_url: url.trim().replace(/\/+$/, ""), allow_signup: allowSignup }),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.instanceSettings, data);
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
      void queryClient.invalidateQueries({ queryKey: qk.providers });
      toast.success(
        urlChanged && anyProvider
          ? "Saved. Update the callback URLs in your OAuth apps to match the new public URL."
          : "Instance settings saved.",
      );
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't save settings"),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (dirty && valid) save.mutate();
  };

  return (
    <Card title="General">
      <form className="space-y-4" onSubmit={onSubmit}>
        <Field
          label="Public URL"
          hint="The address others use to reach this Deployer (e.g. a Tailscale or Cloudflare Tunnel URL). Invite links and OAuth callbacks are built from it."
          error={url && !valid ? "Enter a full URL starting with http:// or https://" : undefined}
        >
          {(id) => (
            <Input
              id={id}
              type="url"
              inputMode="url"
              value={url}
              aria-invalid={Boolean(url) && !valid}
              onChange={(e) => setUrl(e.target.value)}
              spellCheck={false}
              autoCapitalize="off"
            />
          )}
        </Field>
        {urlChanged && anyProvider && (
          <Alert tone="warning">
            Changing the public URL changes your OAuth callback URLs. After saving, update them in your{" "}
            {[settings.google.configured && PROVIDER_LABELS.google, settings.github.configured && PROVIDER_LABELS.github]
              .filter(Boolean)
              .join(" and ")}{" "}
            OAuth app settings, or sign-in with those providers will fail.
          </Alert>
        )}
        {url !== window.location.origin && (
          <p className="text-xs text-muted">
            You're currently using <code className="font-mono">{window.location.origin}</code>.{" "}
            <button type="button" className="text-accent hover:underline" onClick={() => setUrl(window.location.origin)}>
              Use this address
            </button>
          </p>
        )}
        <Checkbox
          checked={allowSignup}
          onChange={(e) => setAllowSignup(e.target.checked)}
          label="Allow anyone who can reach this instance to sign up"
          description="When off, new people can only join with an invite link."
        />
        <Button type="submit" variant="primary" loading={save.isPending} disabled={!dirty || !valid}>
          Save changes
        </Button>
      </form>
    </Card>
  );
}

function UsersCard() {
  const users = useQuery({ queryKey: qk.instanceUsers, queryFn: api.instance.users });
  return (
    <Card
      title="Users"
      description={users.data ? `${users.data.length} account${users.data.length === 1 ? "" : "s"} on this instance.` : undefined}
      bodyClassName="p-0 sm:p-0"
    >
      {users.isPending ? (
        <PageSpinner />
      ) : users.isError ? (
        <ErrorState className="m-4 border-0" error={users.error} onRetry={() => void users.refetch()} />
      ) : (
        <ul className="divide-y divide-border">
          {users.data.map((u) => (
            <li key={u.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
              <Avatar name={u.display_name || u.email} src={u.avatar_url} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{u.display_name || u.email}</p>
                <p className="truncate text-xs text-muted">
                  {u.email} · joined {formatDate(u.created_at)}
                </p>
              </div>
              <div className="flex flex-wrap gap-1">
                {u.is_instance_owner && <Badge tone="accent">Instance owner</Badge>}
                {u.has_password && <Badge>Password</Badge>}
                {u.identities.map((i) => (
                  <Badge key={i.id}>{PROVIDER_LABELS[i.provider]}</Badge>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
