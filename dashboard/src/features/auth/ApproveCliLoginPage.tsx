import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { isApiError } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { CliLogin } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { AuthShell } from "../../components/layout/AppLayout";
import { Button } from "../../components/ui/Button";
import { Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, ErrorAlert } from "../../components/ui/States";
import { formatDateTime, relativeTime } from "../../lib/format";

const CODE_RE = /^[A-Z0-9]{4}-[A-Z0-9]{4}$/;

function normalizeCode(input: string): string {
  const raw = input.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  return raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw;
}

/** `/cli/approve?code=ABCD-EFGH`: approve `deployer login` from any device (docs/CLI.md; requires sign-in). */
export function ApproveCliLoginPage() {
  const [params, setParams] = useSearchParams();
  const code = normalizeCode(params.get("code") ?? "");
  return (
    <AuthShell wide>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in the command line</h1>
        <p className="text-sm text-muted">
          Approve <code>deployer login</code> running on a server, so it can work as you without a browser there.
        </p>
      </div>
      {CODE_RE.test(code) ? (
        <LoginApproval key={code} code={code} onChangeCode={() => setParams({}, { replace: true })} />
      ) : (
        <CodeForm initial={code} onSubmit={(c) => setParams({ code: c }, { replace: true })} />
      )}
    </AuthShell>
  );
}

function CodeForm({ initial, onSubmit }: { initial: string; onSubmit: (code: string) => void }) {
  const [value, setValue] = useState(initial);
  const valid = CODE_RE.test(value);
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onSubmit(value);
      }}
    >
      <Field label="Code shown by deployer login">
        {(id) => (
          <Input
            id={id}
            value={value}
            onChange={(e) => setValue(normalizeCode(e.target.value))}
            placeholder="ABCD-EFGH"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            className="font-mono text-lg tracking-widest uppercase"
          />
        )}
      </Field>
      <Button type="submit" variant="primary" disabled={!valid}>
        Continue
      </Button>
    </form>
  );
}

function LoginApproval({ code, onChangeCode }: { code: string; onChangeCode: () => void }) {
  const login = useQuery({
    queryKey: qk.cliLogin(code),
    queryFn: () => api.auth.cliLoginByCode(code),
    retry: false,
  });

  if (login.isPending) return <PageSpinner label="Looking up the code…" />;
  if (login.isError) {
    const notFound = isApiError(login.error) && login.error.status === 404;
    return (
      <div className="space-y-4">
        {notFound ? (
          <Alert tone="danger" title="No command line is waiting with this code">
            Check the code in your terminal. Codes expire after 10 minutes; run <code>deployer login</code> again if
            needed.
          </Alert>
        ) : (
          <ErrorAlert error={login.error} />
        )}
        <div className="flex gap-2">
          <Button onClick={onChangeCode}>Enter a different code</Button>
          {!notFound && <Button onClick={() => void login.refetch()}>Try again</Button>}
        </div>
      </div>
    );
  }
  const l = login.data;
  // Compare with when the login was fetched (render must stay pure).
  const lapsed = Date.parse(l.expires_at) < login.dataUpdatedAt;
  if (l.status !== "pending" || lapsed) {
    const expired = l.status === "expired" || (l.status === "pending" && lapsed);
    return (
      <div className="space-y-4">
        <Alert tone={expired ? "warning" : "info"} title={expired ? "This code has expired" : "Already handled"}>
          {expired
            ? "Run deployer login again to get a new code."
            : l.status === "denied"
              ? "This sign-in was denied."
              : "This sign-in has already been approved."}
        </Alert>
        <Button onClick={onChangeCode}>Enter a different code</Button>
      </div>
    );
  }
  return <ApprovalForm login={l} />;
}

function ApprovalForm({ login }: { login: CliLogin }) {
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const [confirmed, setConfirmed] = useState(false);
  const [done, setDone] = useState<"approved" | "denied" | null>(null);

  const approve = useMutation({
    mutationFn: () => api.auth.approveCliLogin(login.id, login.user_code),
    onSuccess: () => {
      setDone("approved");
      void queryClient.invalidateQueries({ queryKey: qk.cliTokens });
    },
  });
  const deny = useMutation({
    mutationFn: () => api.auth.denyCliLogin(login.id, login.user_code),
    onSuccess: () => setDone("denied"),
  });

  if (done === "approved") {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center" role="status">
        <CheckCircle2 className="size-12 text-success" />
        <h2 className="text-xl font-semibold">The command line is signed in</h2>
        <p className="max-w-md text-sm text-muted">
          You can close this tab; your terminal finishes on its own in a few seconds. Revoke it any time under{" "}
          <Link to="/settings/account" className="font-medium text-accent hover:underline">
            Account settings
          </Link>
          .
        </p>
      </div>
    );
  }
  if (done === "denied") {
    return (
      <Alert tone="info" title="Sign-in denied">
        The command line gets nothing. You can close this tab.
      </Alert>
    );
  }

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    if (confirmed) approve.mutate();
  };
  const busy = approve.isPending || deny.isPending;

  return (
    <form className="space-y-5" onSubmit={onSubmit}>
      <Card title="Request">
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div className="col-span-2 min-w-0 sm:col-span-1">
            <dt className="text-xs text-muted">Name</dt>
            <dd className="truncate font-medium">{login.name}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted">Computer</dt>
            <dd className="truncate">{login.hostname ?? "—"}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted">System</dt>
            <dd className="truncate">{login.os ?? "—"}</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-muted">
          Requested <span title={formatDateTime(login.created_at)}>{relativeTime(login.created_at)}</span> · code
          expires {relativeTime(login.expires_at)}
        </p>
      </Card>

      <div className="rounded-xl border-2 border-dashed border-accent/50 p-4 text-center">
        <p className="text-sm text-muted">Make sure your terminal shows exactly this code</p>
        <code className="mt-1 block font-mono text-3xl font-bold tracking-[0.2em]">{login.user_code}</code>
        <label className="mt-3 inline-flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[var(--accent)]"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          The code matches the one in my terminal
        </label>
      </div>

      <Alert tone="warning" title="Only approve a code you started yourself">
        The command line will act as <strong>{user.display_name || user.email}</strong>: it can manage your projects,
        apps and their settings until you revoke it in Account settings. It can't change your password or approve other
        sign-ins.
      </Alert>

      {(approve.error || deny.error) && <ErrorAlert error={approve.error ?? deny.error} />}

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline-danger" onClick={() => deny.mutate()} loading={deny.isPending} disabled={busy}>
          Deny
        </Button>
        <Button
          type="submit"
          variant="primary"
          loading={approve.isPending}
          disabled={busy || !confirmed}
          title={!confirmed ? "Confirm the code first" : undefined}
        >
          Approve
        </Button>
      </div>
    </form>
  );
}
