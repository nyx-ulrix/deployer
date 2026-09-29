import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useInstanceSettings } from "../../api/hooks";
import type { InstanceSettings, User } from "../../api/types";
import { Avatar } from "../../components/layout/Brand";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Checkbox, Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, ErrorState, PageHeader } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatDate } from "../../lib/format";
import { PROVIDER_LABELS } from "../../lib/oauthErrors";
import { InstanceNav } from "./InstanceNav";
import { OAuthProviderCard } from "./OAuthProviderCard";

export function InstanceSettingsPage() {
  const settings = useInstanceSettings();
  return (
    <div className="mx-auto w-full max-w-3xl">
      <InstanceNav />
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
          <GeneralCard settings={settings.data} key={`${settings.data.public_url}|${settings.data.allow_signup}|${settings.data.owner_only_projects}`} />
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
          <ProjectsCard />
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
  const [ownerOnly, setOwnerOnly] = useState(settings.owner_only_projects);
  const urlChanged = url.trim().replace(/\/+$/, "") !== settings.public_url.replace(/\/+$/, "");
  const dirty = urlChanged || allowSignup !== settings.allow_signup || ownerOnly !== settings.owner_only_projects;
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
      api.instance.updateSettings({
        public_url: url.trim().replace(/\/+$/, ""),
        allow_signup: allowSignup,
        owner_only_projects: ownerOnly,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.instanceSettings, data);
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
      void queryClient.invalidateQueries({ queryKey: qk.providers });
      toast.success(
        urlChanged && anyProvider
          ? "Saved. Update the callback URLs in your OAuth apps to match the new public URL."
          : "Instance settings saved.",
      );
      for (const w of data.warnings ?? []) toast.info(w, "GitHub webhooks");
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
        <Checkbox
          checked={ownerOnly}
          onChange={(e) => setOwnerOnly(e.target.checked)}
          label="Only I can create projects"
          description="Projects get databases and apps on this PC. When off, anyone with an account can create them."
        />
        <Button type="submit" variant="primary" loading={save.isPending} disabled={!dirty || !valid}>
          Save changes
        </Button>
      </form>
    </Card>
  );
}

function UsersCard() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: qk.instanceUsers, queryFn: api.instance.users });
  const [disabling, setDisabling] = useState<User | null>(null);
  const setActive = useMutation({
    mutationFn: ({ user, active }: { user: User; active: boolean }) => api.instance.setUserActive(user.id, active),
    onSuccess: (user) => {
      setDisabling(null);
      void queryClient.invalidateQueries({ queryKey: qk.instanceUsers });
      toast.success(user.is_active ? `${user.email} can sign in again.` : `${user.email} is disabled and signed out.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't update the account"),
  });
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
              <div className="flex flex-wrap items-center gap-1">
                {u.is_instance_owner && <Badge tone="accent">Instance owner</Badge>}
                {!u.is_active && <Badge tone="danger">Disabled</Badge>}
                {u.has_password && <Badge>Password</Badge>}
                {u.identities.map((i) => (
                  <Badge key={i.id}>{PROVIDER_LABELS[i.provider]}</Badge>
                ))}
                {!u.is_instance_owner &&
                  (u.is_active ? (
                    <Button size="sm" variant="outline-danger" onClick={() => setDisabling(u)}>
                      Disable
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      loading={setActive.isPending && setActive.variables?.user.id === u.id}
                      onClick={() => setActive.mutate({ user: u, active: true })}
                    >
                      Enable
                    </Button>
                  ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={disabling !== null}
        onClose={() => setDisabling(null)}
        onConfirm={() => {
          if (disabling) setActive.mutate({ user: disabling, active: false });
        }}
        title={`Disable ${disabling?.email ?? "this account"}?`}
        description="They are signed out everywhere and can't sign in again, and the API keys of projects they own stop working. Their projects and data are kept; you can enable the account again later."
        confirmLabel="Disable"
        loading={setActive.isPending}
      />
    </Card>
  );
}

function ProjectsCard() {
  const projects = useQuery({ queryKey: qk.instanceProjects, queryFn: api.instance.projects });
  return (
    <Card
      title="All projects"
      description="Every project on this instance, including ones you aren't a member of."
      bodyClassName="p-0 sm:p-0"
    >
      {projects.isPending ? (
        <PageSpinner />
      ) : projects.isError ? (
        <ErrorState className="m-4 border-0" error={projects.error} onRetry={() => void projects.refetch()} />
      ) : projects.data.length === 0 ? (
        <p className="px-4 py-3 text-sm text-muted sm:px-5">No projects yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {projects.data.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {p.my_role ? (
                    <Link to={`/projects/${p.id}`} className="text-link hover:underline">
                      {p.name}
                    </Link>
                  ) : (
                    p.name
                  )}
                </p>
                <p className="truncate text-xs text-muted">
                  Owner {p.owner_email ?? "unknown"} · {p.member_count} member{p.member_count === 1 ? "" : "s"} · created{" "}
                  {formatDate(p.created_at)}
                </p>
              </div>
              <div className="flex flex-wrap gap-1">
                {p.data_source_counts.sql > 0 && <Badge tone="sql">SQL {p.data_source_counts.sql}</Badge>}
                {p.data_source_counts.nosql > 0 && <Badge tone="nosql">NoSQL {p.data_source_counts.nosql}</Badge>}
                {!p.my_role && <Badge>Not a member</Badge>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
