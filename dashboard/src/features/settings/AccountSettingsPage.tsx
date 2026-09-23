import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Link2, NotebookPen, Terminal, Unlink } from "lucide-react";
import { errorMessage, isApiError } from "../../api/client";
import { api } from "../../api/endpoints";
import { useProviders } from "../../api/hooks";
import type { Identity, ProviderName, User } from "../../api/types";
import { useAuth, useCurrentUser } from "../../auth/auth-context";
import { ProviderIcon } from "../../components/layout/Brand";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Field, Input } from "../../components/ui/Input";
import { Card, PageHeader } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { QUERY_CONSOLE_MODES, useQueryConsoleMode, type QueryConsoleMode } from "../../lib/consoleMode";
import { MIN_PASSWORD } from "../../lib/constants";
import { formatDate } from "../../lib/format";
import { GitHubAccountCard } from "../deploys/GitHubConnect";
import { oauthErrorMessage, PROVIDER_LABELS } from "../../lib/oauthErrors";

export function AccountSettingsPage() {
  const user = useCurrentUser();
  const { setUser } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const handled = useRef(false);

  // Handle the redirect back from an OAuth link flow (?linked=google or ?error=code).
  useEffect(() => {
    if (handled.current) return;
    const linked = params.get("linked");
    const error = params.get("error");
    if (!linked && !error) return;
    handled.current = true;
    if (linked) {
      const label = PROVIDER_LABELS[linked as ProviderName] ?? linked;
      toast.success(`${label} account linked. You can now sign in with it.`);
      void api.auth.me().then(setUser, () => undefined);
    }
    if (error) toast.error(oauthErrorMessage(error) ?? error, "Couldn't link account");
    setParams({}, { replace: true });
  }, [params, setParams, toast, setUser]);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader title="Account settings" description={user.email} />
      <div className="space-y-5">
        <ProfileCard user={user} key={user.display_name ?? ""} />
        <PreferencesCard />
        <PasswordCard user={user} />
        <LinkedAccountsCard user={user} />
        <GitHubAccountCard />
      </div>
    </div>
  );
}

const MODE_ICONS: Record<QueryConsoleMode, typeof Terminal> = { terminal: Terminal, editor: NotebookPen };

function PreferencesCard() {
  const [mode, setMode] = useQueryConsoleMode();
  return (
    <Card title="Preferences" description="Saved in this browser only.">
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Query console</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {QUERY_CONSOLE_MODES.map((m) => {
            const Icon = MODE_ICONS[m.value];
            const active = mode === m.value;
            return (
              <label
                key={m.value}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors",
                  active ? "border-accent bg-accent-soft/40" : "border-border hover:bg-surface-2",
                )}
              >
                <input
                  type="radio"
                  name="query-console-mode"
                  value={m.value}
                  checked={active}
                  onChange={() => setMode(m.value)}
                  className="mt-1 size-4 accent-[var(--accent)]"
                />
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    <Icon className="size-4 text-muted" />
                    {m.label}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted">{m.description}</span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
    </Card>
  );
}

function ProfileCard({ user }: { user: User }) {
  const { setUser } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(user.display_name ?? "");
  const save = useMutation({
    mutationFn: () => api.auth.updateMe({ display_name: name.trim() }),
    onSuccess: (u) => {
      setUser(u);
      toast.success("Profile updated.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't update profile"),
  });
  const dirty = name.trim() !== (user.display_name ?? "");
  return (
    <Card title="Profile">
      <form
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty) save.mutate();
        }}
      >
        <Field label="Display name" className="flex-1">
          {(id) => <Input id={id} value={name} maxLength={100} autoComplete="name" onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Button type="submit" variant="primary" loading={save.isPending} disabled={!dirty}>
          Save
        </Button>
      </form>
      <p className="mt-3 text-xs text-muted">
        Email: {user.email} · Member since {formatDate(user.created_at)}
      </p>
    </Card>
  );
}

function PasswordCard({ user }: { user: User }) {
  const { setUser } = useAuth();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && confirm !== next;

  const save = useMutation({
    mutationFn: () =>
      api.auth.setPassword({ current_password: user.has_password ? current : undefined, new_password: next }),
    onSuccess: () => {
      toast.success(user.has_password ? "Password changed." : "Password set. You can now sign in with your email.");
      setCurrent("");
      setNext("");
      setConfirm("");
      if (!user.has_password) setUser({ ...user, has_password: true });
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't update password"),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (next.length >= MIN_PASSWORD && next === confirm) save.mutate();
  };

  return (
    <Card
      title={user.has_password ? "Change password" : "Set a password"}
      description={
        user.has_password
          ? undefined
          : "You currently sign in only with a linked provider. Set a password to also sign in with your email."
      }
    >
      <form className="space-y-4" onSubmit={onSubmit}>
        {user.has_password && (
          <Field label="Current password">
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="current-password"
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            )}
          </Field>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="New password" hint={`At least ${MIN_PASSWORD} characters.`}>
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD}
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            )}
          </Field>
          <Field label="Confirm new password" error={mismatch ? "Passwords don't match." : undefined}>
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="new-password"
                required
                aria-invalid={mismatch}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            )}
          </Field>
        </div>
        <Button
          type="submit"
          variant="primary"
          loading={save.isPending}
          disabled={mismatch || next.length < MIN_PASSWORD || (user.has_password && !current)}
        >
          {user.has_password ? "Change password" : "Set password"}
        </Button>
      </form>
    </Card>
  );
}

function LinkedAccountsCard({ user }: { user: User }) {
  const providers = useProviders();
  const [unlinking, setUnlinking] = useState<Identity | null>(null);
  const { setUser } = useAuth();
  const toast = useToast();

  const link = useMutation({
    mutationFn: (p: ProviderName) => api.auth.linkProvider(p, "/settings/account"),
    onSuccess: ({ authorize_url }) => {
      window.location.assign(authorize_url);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't start linking"),
  });

  const unlink = useMutation({
    mutationFn: (identity: Identity) => api.auth.unlinkIdentity(identity.id),
    onSuccess: (u, identity) => {
      setUser(u);
      setUnlinking(null);
      toast.success(`${PROVIDER_LABELS[identity.provider]} account unlinked.`);
    },
    onError: (e) => {
      setUnlinking(null);
      if (isApiError(e) && e.code === "last_login_method") {
        toast.error("Set a password or link another provider first — you can't remove your only way to sign in.");
      } else {
        toast.error(errorMessage(e), "Couldn't unlink account");
      }
    },
  });

  return (
    <Card
      title="Linked accounts"
      description="Sign in with Google or GitHub in addition to your password. Linking is never automatic — connect accounts here."
      bodyClassName="p-0 sm:p-0"
    >
      <ul className="divide-y divide-border">
        {(["google", "github"] as ProviderName[]).map((p) => {
          const identity = user.identities.find((i) => i.provider === p);
          const configured = providers.data?.[p] ?? false;
          return (
            <li key={p} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
              <span className="flex size-9 items-center justify-center rounded-lg border border-border bg-surface-2">
                <ProviderIcon provider={p} className="size-4.5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{PROVIDER_LABELS[p]}</p>
                <p className="truncate text-xs text-muted">
                  {identity
                    ? `Connected as ${[identity.provider_username, identity.provider_email].filter(Boolean).join(" · ") || "linked account"}`
                    : configured
                      ? "Not connected"
                      : "Not available — the instance owner hasn't configured this provider"}
                </p>
              </div>
              {identity ? (
                <Button size="sm" variant="outline-danger" icon={<Unlink className="size-3.5" />} onClick={() => setUnlinking(identity)}>
                  Unlink
                </Button>
              ) : (
                <Button
                  size="sm"
                  icon={<Link2 className="size-3.5" />}
                  disabled={!configured}
                  loading={link.isPending && link.variables === p}
                  onClick={() => link.mutate(p)}
                >
                  Connect
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      {unlinking && (
        <ConfirmDialog
          open
          onClose={() => setUnlinking(null)}
          onConfirm={() => unlink.mutate(unlinking)}
          loading={unlink.isPending}
          title={`Unlink ${PROVIDER_LABELS[unlinking.provider]}?`}
          description={`You won't be able to sign in with this ${PROVIDER_LABELS[unlinking.provider]} account anymore. You can link it again later.`}
          confirmLabel="Unlink"
        />
      )}
    </Card>
  );
}
