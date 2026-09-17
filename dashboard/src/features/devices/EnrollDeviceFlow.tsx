import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, Laptop, RotateCcw } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { EnrollStartResponse, EnrollState } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { CopyButton } from "../../components/ui/CopyField";
import { Field, Input } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { reachabilityWarning } from "./eligibility";

const POLL_MS = 2000;

/** A readable default device name from the browser, e.g. "Windows PC". */
function defaultDeviceName(): string {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  const platform = nav.userAgentData?.platform || navigator.platform || "";
  if (/win/i.test(platform)) return "Windows PC";
  if (/mac/i.test(platform)) return "Mac";
  if (/linux/i.test(platform)) return "Linux PC";
  return "Host device";
}

function normalizeUrl(input: string): string | null {
  const raw = input.trim().replace(/\/+$/, "");
  if (!raw) return null;
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    const u = new URL(withScheme);
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    return `${u.protocol}//${u.host}${u.pathname.replace(/\/+$/, "")}`;
  } catch {
    return null;
  }
}

const TERMINAL: Record<Exclude<EnrollState, "idle" | "pending" | "approved">, { title: string; body: string }> = {
  denied: { title: "The request was denied", body: "Someone on the main Deployer denied this device." },
  expired: { title: "The code expired", body: "Codes are valid for 15 minutes. Start again to get a new one." },
  error: { title: "Something went wrong", body: "The device couldn't finish enrolling." },
};

/**
 * On the would-be host device: enter the main Deployer URL, get a code, approve it there, and wait.
 * Uses the device-local API (`/v1/device/enroll/*`).
 */
export function EnrollDeviceFlow({ onCancel }: { onCancel?: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [name, setName] = useState(defaultDeviceName);
  const [started, setStarted] = useState<EnrollStartResponse | null>(null);

  const status = useQuery({
    queryKey: qk.enrollStatus,
    queryFn: api.deviceLocal.enrollStatus,
    refetchInterval: (q) => (q.state.data?.status === "pending" || started ? POLL_MS : false),
    retry: false,
    staleTime: 0,
  });
  const reported: EnrollState = status.data?.status ?? "idle";
  // Right after "Get a code" the status endpoint may still say idle until the next poll.
  const state: EnrollState = reported === "idle" && started ? "pending" : reported;

  useEffect(() => {
    if (state !== "approved") return;
    void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
    const t = setTimeout(() => navigate("/device", { replace: true }), 1200);
    return () => clearTimeout(t);
  }, [state, navigate, queryClient]);

  const start = useMutation({
    mutationFn: (primary_url: string) => api.deviceLocal.enrollStart({ primary_url, device_name: name.trim() }),
    onSuccess: (res) => {
      setStarted(res);
      void queryClient.invalidateQueries({ queryKey: qk.enrollStatus });
    },
  });
  const cancel = useMutation({
    mutationFn: api.deviceLocal.enrollCancel,
    onSettled: () => {
      setStarted(null);
      void queryClient.invalidateQueries({ queryKey: qk.enrollStatus });
    },
  });

  const normalized = normalizeUrl(url);
  const warning = normalized ? reachabilityWarning(normalized) : null;
  const sameOrigin = normalized !== null && new URL(normalized).origin === window.location.origin;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (normalized && name.trim() && !sameOrigin) start.mutate(normalized);
  };

  // ---- waiting for approval ----
  if (state === "approved") {
    return (
      <div className="flex flex-col items-center gap-3 py-6 text-center" role="status">
        <CheckCircle2 className="size-10 text-success" />
        <h2 className="text-lg font-semibold">Approved</h2>
        <p className="text-sm text-muted">This PC is now a host device. Opening its status page…</p>
      </div>
    );
  }

  if (state === "denied" || state === "expired" || state === "error") {
    const t = TERMINAL[state];
    return (
      <div className="space-y-4">
        <Alert tone={state === "expired" ? "warning" : "danger"} title={t.title}>
          {status.data?.message || t.body}
        </Alert>
        <div className="flex flex-wrap justify-between gap-2">
          {onCancel && <Button onClick={onCancel}>Back</Button>}
          <Button
            variant="primary"
            icon={<RotateCcw className="size-4" />}
            loading={cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            Try again
          </Button>
        </div>
      </div>
    );
  }

  if (state === "pending") {
    return (
      <div className="space-y-5">
        {started ? (
          <>
            <div className="rounded-2xl border border-border bg-surface-2 p-5 text-center">
              <p className="text-sm text-muted">Your code</p>
              <div className="mt-1 flex items-center justify-center gap-1">
                <code
                  className="font-mono text-3xl font-bold tracking-[0.2em] sm:text-4xl"
                  aria-label={`Code ${started.user_code.split("").join(" ")}`}
                >
                  {started.user_code}
                </code>
                <CopyButton value={started.user_code} label="Copy code" />
              </div>
              <p className="mt-2 text-xs text-muted">Expires in about {Math.round(started.expires_in / 60)} minutes.</p>
            </div>
            <ol className="list-decimal space-y-1.5 pl-5 text-sm">
              <li>Open the approval page on the main Deployer (it opens in a new tab).</li>
              <li>Sign in there with your usual account — your password never touches this PC.</li>
              <li>Check that the code matches, then click Approve.</li>
            </ol>
            <a
              href={started.verification_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-accent px-3.5 text-sm font-medium text-accent-fg shadow-sm hover:bg-accent-hover"
            >
              Open approval page <ExternalLink className="size-4" />
            </a>
          </>
        ) : (
          <Alert tone="info" title="An enrollment request is already waiting">
            Approve it on the main Deployer, or cancel it to start over with a new code.
          </Alert>
        )}
        <div className="flex items-center justify-between gap-2 text-sm text-muted" role="status" aria-live="polite">
          <span className="inline-flex items-center gap-2">
            <Spinner className="size-4" /> Waiting for approval…
          </span>
          <Button size="sm" variant="ghost" loading={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  // ---- form ----
  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      {status.isError && (
        <Alert tone="warning" title="Couldn't check the enrollment state">
          {errorMessage(status.error)}
        </Alert>
      )}
      <Field
        label="Main Deployer URL"
        hint="The address you use to open the main Deployer, e.g. https://deployer.example.com"
        error={
          url && !normalized
            ? "Enter a URL like https://deployer.example.com"
            : sameOrigin
              ? "That's this Deployer. Enter the address of the other (main) Deployer."
              : undefined
        }
      >
        {(id) => (
          <Input
            id={id}
            type="text"
            inputMode="url"
            required
            placeholder="https://deployer.example.com"
            value={url}
            aria-invalid={Boolean(url) && (!normalized || sameOrigin)}
            onChange={(e) => setUrl(e.target.value)}
            spellCheck={false}
            autoCapitalize="off"
          />
        )}
      </Field>
      {warning && <Alert tone="warning">{warning}</Alert>}
      <Field label="Device name" hint="How this PC appears on the main Deployer. You can rename it later.">
        {(id) => <Input id={id} required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      {start.error && <ErrorAlert error={start.error} />}
      <div className={cn("flex gap-2", onCancel ? "justify-between" : "justify-end")}>
        {onCancel && (
          <Button onClick={onCancel} disabled={start.isPending}>
            Back
          </Button>
        )}
        <Button
          type="submit"
          variant="primary"
          icon={<Laptop className="size-4" />}
          loading={start.isPending}
          disabled={!normalized || !name.trim() || sameOrigin}
        >
          Get a code
        </Button>
      </div>
      {status.isPending && (
        <p className="flex items-center gap-2 text-xs text-muted">
          <Spinner className="size-3" /> Checking for an existing request…
        </p>
      )}
    </form>
  );
}
