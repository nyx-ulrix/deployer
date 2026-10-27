import { useState, type CSSProperties, type FormEvent } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, Eye, EyeOff, LayoutDashboard, Terminal } from "lucide-react";
import { isApiError } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { CliInput, CliInputField } from "../../api/types";
import { useAuth } from "../../auth/auth-context";
import { AuthShell } from "../../components/layout/AppLayout";
import { Button } from "../../components/ui/Button";
import { Input, Textarea } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { formatDateTime, relativeTime } from "../../lib/format";
import { cn } from "../../lib/cn";

// Maps, not plain objects: field keys come from the command line and may be "__proto__", "constructor", …
type Values = ReadonlyMap<string, string>;
type Errors = ReadonlyMap<string, string>;

/** The fixed, non-overridable notice (docs/CLI.md "Input requests"): a request can't change or hide it. */
const PHISHING_NOTICE = "Deployer never asks for your account password or a sign-in approval code on this page.";

/** Tells password managers and browsers this is not a sign-in form (no autofill, no "save password"). */
const NOT_A_LOGIN = {
  autoComplete: "off",
  "data-1p-ignore": true,
  "data-lpignore": "true",
  "data-bwignore": true,
  "data-form-type": "other",
} as const;

const MASKED = { WebkitTextSecurity: "disc" } as CSSProperties;

function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** Where the values end up: the apps' Environment, or straight back to the waiting command line. */
function destination(input: Pick<CliInput, "apps">, done: boolean): string {
  if (input.apps.length > 0) {
    // App names are unique only per project, so always say which project.
    const names = joinNames(input.apps.map((a) => `${a.project_name} / ${a.name}`));
    return done ? `Saved to the Environment of ${names}` : `Will be saved to the Environment of ${names}`;
  }
  return done ? "Sent to the command line that asked for it" : "Will be sent to the command line that asked for it";
}

/** Who made the request, as recorded by the server when it was created. */
function requester(by: CliInput["requested_by"]): string {
  if (by.kind === "session") return "Asked from a dashboard session";
  const name = by.name ? ` '${by.name}'` : "";
  const prefix = by.prefix ? ` (${by.prefix}…)` : "";
  return `Asked by command line${name}${prefix}`;
}

/**
 * Check of one value. `pattern` is a browser-side hint only (the server never runs it), so this is the only
 * pattern check. It is compiled with the `u` flag so Python-only syntax (\A, \Z, {,n}) throws instead of meaning
 * something else, and `.` counts code points; a pattern JS can't compile is skipped.
 */
function validateField(field: CliInputField, raw: string): string | null {
  const value = raw.trim();
  if (!value) return field.optional ? null : `Enter ${field.label}.`;
  if (field.pattern) {
    let re: RegExp | null;
    try {
      re = new RegExp(`^(?:${field.pattern})$`, "u");
    } catch {
      re = null;
    }
    if (re && !re.test(value)) return `${field.label} doesn't look right. Check it and try again.`;
  }
  return null;
}

/** `/input/:id`: fill in what a command line asked for (docs/CLI.md "Input requests"; requires sign-in). */
export function InputRequestPage() {
  const { id = "" } = useParams();
  const [done, setDone] = useState(false);
  const input = useQuery({
    queryKey: qk.input(id),
    queryFn: () => api.inputs.get(id),
    retry: false,
    refetchOnWindowFocus: false,
    enabled: !done,
  });

  return (
    <AuthShell wide>
      {input.isPending ? (
        <PageSpinner label="Loading the request…" />
      ) : input.isError ? (
        <LoadError error={input.error} onRetry={() => void input.refetch()} />
      ) : (
        <RequestBody input={input.data} done={done} onDone={() => setDone(true)} />
      )}
    </AuthShell>
  );
}

function LoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (isApiError(error) && error.status === 404) return <NotFound />;
  return (
    <div className="space-y-4">
      <ErrorAlert error={error} />
      <Button onClick={onRetry}>Try again</Button>
    </div>
  );
}

/** 404: mistyped, gone, or made by another account. Offer to switch account and come back to this link. */
function NotFound() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [busy, setBusy] = useState(false);

  const switchAccount = async () => {
    setBusy(true);
    const here = location.pathname + location.search;
    try {
      await logout();
    } catch {
      // The session is cleared locally even when the API call fails.
    }
    navigate(`/login?redirect=${encodeURIComponent(here)}`, { replace: true });
  };

  return (
    <div className="space-y-4">
      <Alert tone="danger" title="This request doesn't exist">
        The link may be mistyped, or the request was made by a different account. Sign in as the person who ran the
        command, or run it again for a new link.
      </Alert>
      {user && (
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface px-4 py-3 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <p className="min-w-0 text-sm text-muted">
            Signed in as <span className="font-medium break-all text-fg">{user.email}</span>
          </p>
          <Button className="shrink-0 justify-center" loading={busy} onClick={() => void switchAccount()}>
            Sign in with a different account
          </Button>
        </div>
      )}
    </div>
  );
}

function Header({ input }: { input: CliInput }) {
  const paragraphs = (input.description ?? "")
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  return (
    <div className="mb-5 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight break-words">{input.title}</h1>
      {paragraphs.length > 0 && (
        <div className="mt-1 space-y-2 text-sm break-words whitespace-pre-line text-muted">
          {paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
    </div>
  );
}

/** Provenance plus the fixed notice: shown wherever the user could be asked to type something. */
function Provenance({ input }: { input: CliInput }) {
  const Icon = input.requested_by.kind === "session" ? LayoutDashboard : Terminal;
  return (
    <div className="mb-5 space-y-3">
      <p className="flex min-w-0 items-start gap-2 text-sm text-muted">
        <Icon className="mt-0.5 size-4 shrink-0" />
        <span className="min-w-0 break-words">
          <span className="font-medium text-fg">{requester(input.requested_by)}</span>{" "}
          <span title={formatDateTime(input.created_at)}>{relativeTime(input.created_at)}</span>
        </span>
      </p>
      <Alert tone="warning">{PHISHING_NOTICE}</Alert>
    </div>
  );
}

function RequestBody({ input, done, onDone }: { input: CliInput; done: boolean; onDone: () => void }) {
  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center" role="status">
        <CheckCircle2 className="size-12 text-success" />
        <h1 className="text-xl font-semibold">Saved. You can close this tab; the terminal continues by itself.</h1>
        <p className="max-w-md text-sm break-words text-muted">{destination(input, true)}.</p>
      </div>
    );
  }
  // The server expires requests itself, so its status is the truth (the device clock may be off).
  if (input.status !== "pending") {
    return (
      <>
        <Header input={input} />
        <ClosedNotice status={input.status} />
      </>
    );
  }
  if (input.unavailable_apps > 0) {
    return (
      <>
        <Header input={input} />
        <Provenance input={input} />
        <AppsUnavailable count={input.unavailable_apps} />
      </>
    );
  }
  return (
    <>
      <Header input={input} />
      <Provenance input={input} />
      <InputForm input={input} onDone={onDone} />
    </>
  );
}

function AppsUnavailable({ count }: { count: number }) {
  return (
    <Alert tone="danger" title="This request can't be filled in">
      {count === 1 ? "One of the apps" : `${count} of the apps`} it would save to no longer{" "}
      {count === 1 ? "exists" : "exist"}, or you can no longer change {count === 1 ? "its" : "their"} settings, so
      nothing can be saved. Check the app and its project, then run the command again for a new link.
    </Alert>
  );
}

function ClosedNotice({ status }: { status: CliInput["status"] }) {
  if (status === "expired") {
    return (
      <Alert tone="warning" title="This request has expired">
        Requests stay open for 30 minutes. Run the command again to get a new link.
      </Alert>
    );
  }
  if (status === "cancelled") {
    return (
      <Alert tone="info" title="This request was cancelled">
        The command line stopped waiting for it. You can close this tab.
      </Alert>
    );
  }
  return (
    <Alert tone="info" title="Already filled in">
      This request has been answered. You can close this tab.
    </Alert>
  );
}

function InputForm({ input, onDone }: { input: CliInput; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Values>(() => new Map());
  const [errors, setErrors] = useState<Errors>(() => new Map());

  const submit = useMutation({
    // Values are read from state at call time, so the mutation never keeps a copy of them.
    mutationFn: () =>
      api.inputs.submit(
        input.id,
        Object.fromEntries(
          input.fields
            .map((f) => [f.key, (values.get(f.key) ?? "").trim()] as const)
            .filter(([, v]) => v !== ""),
        ),
      ),
    onSuccess: () => {
      setValues(new Map());
      setErrors(new Map());
      submit.reset();
      // Coming back to this page (Back, a new tab) shows "Already filled in", not the form again.
      queryClient.setQueryData<CliInput>(qk.input(input.id), (d) => d && { ...d, status: "submitted" });
      onDone();
    },
    onError: (err) => {
      if (!isApiError(err)) return;
      const field = typeof err.details.field === "string" ? err.details.field : null;
      if (err.status === 422 && field && input.fields.some((f) => f.key === field)) {
        setErrors(new Map([[field, err.message]]));
      } else if (err.status === 409) {
        if (err.code === "input_apps_unavailable") {
          // An app was deleted or access was lost since the page loaded: show that right away.
          queryClient.setQueryData<CliInput>(
            qk.input(input.id),
            (d) => d && { ...d, unavailable_apps: Math.max(d.unavailable_apps, 1) },
          );
        }
        // No longer fillable: show what it is now (expired, submitted elsewhere, cancelled, apps gone).
        void queryClient.invalidateQueries({ queryKey: qk.input(input.id) });
      }
    },
  });

  // A 422 naming one of the fields is shown next to that field instead of in the banner.
  const err = submit.error;
  const onField =
    isApiError(err) && err.status === 422 && typeof err.details.field === "string" && errors.has(err.details.field);

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    submit.reset();
    const next = new Map<string, string>();
    for (const f of input.fields) {
      const msg = validateField(f, values.get(f.key) ?? "");
      if (msg) next.set(f.key, msg);
    }
    setErrors(next);
    if (next.size > 0) {
      const first = input.fields.find((f) => next.has(f.key));
      if (first) document.getElementById(`input-${first.key}`)?.focus();
      return;
    }
    submit.mutate();
  };

  return (
    <form className="space-y-5" onSubmit={onSubmit} noValidate {...NOT_A_LOGIN}>
      <div className="space-y-4 rounded-xl border border-border bg-surface px-4 py-4 shadow-xs sm:px-5">
        {input.fields.map((f) => (
          <FieldInput
            key={f.key}
            field={f}
            value={values.get(f.key) ?? ""}
            error={errors.get(f.key)}
            onChange={(v) => {
              setValues((s) => new Map(s).set(f.key, v));
              if (errors.has(f.key)) {
                setErrors((s) => {
                  const n = new Map(s);
                  n.delete(f.key);
                  return n;
                });
              }
              // A stale server error must not move from the field into the banner.
              if (submit.isError) submit.reset();
            }}
          />
        ))}
      </div>

      <p className="text-xs break-words text-muted">
        {destination(input, false)}. This link expires{" "}
        <span title={formatDateTime(input.expires_at)}>{relativeTime(input.expires_at)}</span>.
      </p>

      {err && !onField && <ErrorAlert error={err} />}

      <div className="flex justify-end">
        <Button type="submit" variant="primary" loading={submit.isPending} className="w-full justify-center sm:w-auto">
          Submit
        </Button>
      </div>
    </form>
  );
}

function linkHost(link: string): string | null {
  try {
    return new URL(link).host;
  } catch {
    return null;
  }
}

function FieldInput({
  field,
  value,
  error,
  onChange,
}: {
  field: CliInputField;
  value: string;
  error?: string;
  onChange: (v: string) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const id = `input-${field.key}`;
  const errId = `${id}-error`;
  const helpId = `${id}-help`;
  const describedBy = [error ? errId : null, field.help ? helpId : null].filter(Boolean).join(" ") || undefined;
  // Secrets are masked with CSS, never type="password": a password field makes browsers treat the form as a
  // sign-in (offer to save or update the Deployer password, or autofill it here).
  const hidden = !!field.secret && !revealed;
  const common = {
    id,
    name: field.key,
    value,
    placeholder: field.placeholder ?? undefined,
    ...NOT_A_LOGIN,
    spellCheck: false,
    autoCapitalize: "off",
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
    "aria-required": field.optional ? undefined : true,
    className: cn(field.secret && "pr-11"),
    style: hidden ? MASKED : undefined,
  } as const;

  const control = field.multiline ? (
    <Textarea {...common} onChange={(e) => onChange(e.target.value)} />
  ) : (
    <Input {...common} type="text" onChange={(e) => onChange(e.target.value)} />
  );

  const linkLabel = field.link_label || "link";
  const host = field.link ? linkHost(field.link) : null;

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium break-words">
        {field.label}
        {field.optional && <span className="ml-1 font-normal text-muted">(optional)</span>}
      </label>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start">
        <div className="relative min-w-0 flex-1">
          {control}
          {field.secret && (
            <button
              type="button"
              onClick={() => setRevealed((r) => !r)}
              className="absolute top-1 right-1 inline-flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg"
              // Constant name; the state is carried by aria-pressed (WAI-ARIA toggle button pattern).
              aria-label={`Show ${field.label}`}
              aria-pressed={revealed}
              title="Show"
            >
              {revealed ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          )}
        </div>
        {field.link && (
          <a
            href={field.link}
            target="_blank"
            rel="noopener noreferrer"
            title={host ? `Open ${linkLabel} (${host})` : `Open ${linkLabel}`}
            className="inline-flex h-10 min-w-0 items-center justify-center gap-2 rounded-lg border border-border bg-surface px-3.5 text-sm font-medium text-fg shadow-sm transition-colors hover:bg-surface-2 sm:max-w-[45%] sm:shrink-0"
          >
            <span className="min-w-0 truncate">Open {linkLabel}</span>
            <ExternalLink className="size-4 shrink-0" />
          </a>
        )}
      </div>
      {error && (
        <p id={errId} className="text-xs text-danger" role="alert">
          {error}
        </p>
      )}
      {field.help && (
        <p id={helpId} className="text-xs break-words whitespace-pre-line text-muted">
          {field.help}
        </p>
      )}
    </div>
  );
}
