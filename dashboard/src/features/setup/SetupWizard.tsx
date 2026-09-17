import { useState, type FormEvent, type ReactNode } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Check, Globe, HardDrive, KeyRound, PartyPopper, ShieldCheck, UserPlus } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useInstanceSettings, useSetupStatus } from "../../api/hooks";
import type { ImportSummary } from "../../api/types";
import { useAuth } from "../../auth/auth-context";
import { AuthShell } from "../../components/layout/AppLayout";
import { Button } from "../../components/ui/Button";
import { Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, ErrorState } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { MIN_PASSPHRASE, MIN_PASSWORD } from "../../lib/constants";
import { OAuthProviderCard } from "../settings/OAuthProviderCard";
import { ImportSummaryList } from "../settings/ImportSummaryList";
import { EnrollDeviceFlow } from "../devices/EnrollDeviceFlow";

type Step = "choose" | "restore" | "device" | "owner" | "url" | "providers" | "done";

const STEPS: { key: Step; label: string }[] = [
  { key: "choose", label: "Start" },
  { key: "owner", label: "Owner" },
  { key: "url", label: "Public URL" },
  { key: "providers", label: "Sign-in" },
  { key: "done", label: "Done" },
];

function Stepper({ step }: { step: Step }) {
  const current = STEPS.findIndex((s) => s.key === (step === "restore" || step === "device" ? "choose" : step));
  return (
    <ol className="mb-6 flex items-center gap-1.5 overflow-x-auto text-xs sm:gap-2">
      {STEPS.map((s, i) => (
        <li key={s.key} className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <span
            className={cn(
              "flex size-6 items-center justify-center rounded-full border text-[11px] font-semibold",
              i < current && "border-accent bg-accent text-accent-fg",
              i === current && "border-accent text-accent",
              i > current && "border-border text-muted",
            )}
          >
            {i < current ? <Check className="size-3.5" /> : i + 1}
          </span>
          <span className={cn("hidden sm:inline", i === current ? "font-medium text-fg" : "text-muted")}>
            {s.label}
          </span>
          {i < STEPS.length - 1 && <span className="h-px w-4 bg-border sm:w-6" />}
        </li>
      ))}
    </ol>
  );
}

function StepHeader({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="mb-5">
      <div className="mb-3 flex size-11 items-center justify-center rounded-xl bg-accent-soft text-accent">{icon}</div>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {children && <div className="mt-1.5 space-y-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function SetupWizard() {
  const status = useSetupStatus();
  const auth = useAuth();
  // Decide the starting step once; the setup status flips to initialized midway through the wizard.
  const [step, setStep] = useState<Step | null>(null);

  if (status.isPending || auth.status === "loading") {
    return (
      <AuthShell>
        <PageSpinner />
      </AuthShell>
    );
  }
  if (status.isError) {
    return (
      <AuthShell>
        <ErrorState error={status.error} onRetry={() => void status.refetch()} />
      </AuthShell>
    );
  }

  const initialized = status.data.initialized;
  if (step === null && initialized) {
    if (auth.status === "anonymous") return <Navigate to="/login?redirect=%2Fsetup" replace />;
    if (!auth.user?.is_instance_owner) return <Navigate to="/" replace />;
  }
  const active: Step = step ?? (initialized ? "url" : "choose");

  return (
    <AuthShell wide>
      <Stepper step={active} />
      {active === "choose" && <ChooseStep onChoose={setStep} />}
      {active === "restore" && <RestoreStep onBack={() => setStep("choose")} />}
      {active === "device" && <DeviceStep onBack={() => setStep("choose")} />}
      {active === "owner" && <OwnerStep onBack={() => setStep("choose")} onDone={() => setStep("url")} />}
      {active === "url" && <PublicUrlStep onDone={() => setStep("providers")} />}
      {active === "providers" && <ProvidersStep onBack={() => setStep("url")} onDone={() => setStep("done")} />}
      {active === "done" && <DoneStep />}
    </AuthShell>
  );
}

function ChooseStep({ onChoose }: { onChoose: (s: Step) => void }) {
  const option = (icon: ReactNode, title: string, description: string, target: Step) => (
    <button
      type="button"
      onClick={() => onChoose(target)}
      className="flex w-full items-start gap-4 rounded-xl border border-border bg-surface p-4 text-left shadow-xs transition-colors hover:border-accent hover:bg-accent-soft/40"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-accent">
        {icon}
      </span>
      <span>
        <span className="block font-semibold">{title}</span>
        <span className="mt-0.5 block text-sm text-muted">{description}</span>
      </span>
    </button>
  );
  return (
    <>
      <StepHeader icon={<ShieldCheck className="size-5" />} title="Welcome to Deployer">
        <p>
          This is your own, self-hosted backend. Nothing here is shared with the Deployer authors — no accounts, no
          API keys, no OAuth apps. Let's set it up.
        </p>
      </StepHeader>
      <div className="space-y-3">
        {option(
          <UserPlus className="size-5" />,
          "Create owner account",
          "Start fresh. You'll be the owner of this Deployer instance.",
          "owner",
        )}
        {option(
          <ArchiveRestore className="size-5" />,
          "Restore from export",
          "Moving from another device? Upload an instance export (.json) to restore all users, projects and database data.",
          "restore",
        )}
        {option(
          <HardDrive className="size-5" />,
          "Make this PC a host device",
          "Already use Deployer on another PC? Attach this one so projects there can host databases here.",
          "device",
        )}
      </div>
    </>
  );
}

function DeviceStep({ onBack }: { onBack: () => void }) {
  return (
    <>
      <StepHeader icon={<HardDrive className="size-5" />} title="Make this PC a host device">
        <p>
          This PC will run databases for your <strong>main Deployer</strong>. You'll manage everything from the main
          Deployer's dashboard; this one will only show the device's status.
        </p>
        <p>
          The device connects out to the main Deployer, so no port forwarding is needed — this PC just has to be able
          to open its URL.
        </p>
      </StepHeader>
      <EnrollDeviceFlow onCancel={onBack} />
    </>
  );
}

function RestoreStep({ onBack }: { onBack: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  const restore = useMutation({
    mutationFn: () => api.setup.importInstance(file as File, passphrase),
    onSuccess: (res) => {
      setSummary(res.summary);
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
    },
  });

  if (summary) {
    return (
      <>
        <StepHeader icon={<Check className="size-5" />} title="Restore complete">
          <p>Everything from your export has been restored on this device.</p>
        </StepHeader>
        <ImportSummaryList summary={summary} />
        <Alert tone="info" className="mt-4" title="Next: check your public URL and OAuth apps">
          If this device is reached at a different address, sign in as the instance owner to update the public URL.
          The wizard will then show the new callback URLs to paste into your Google/GitHub OAuth apps.
        </Alert>
        <div className="mt-5 flex justify-end">
          <Button variant="primary" onClick={() => navigate("/login?redirect=%2Fsetup", { replace: true })}>
            Sign in to continue
          </Button>
        </div>
      </>
    );
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (file && passphrase.length >= MIN_PASSPHRASE) restore.mutate();
  };

  return (
    <>
      <StepHeader icon={<ArchiveRestore className="size-5" />} title="Restore from export">
        <p>
          Upload an <strong>instance export</strong> made on another Deployer installation (Settings → Export &amp;
          import). It contains all settings, users, projects and the data inside every managed database.
        </p>
      </StepHeader>
      <form className="space-y-4" onSubmit={onSubmit}>
        <Field label="Export file" hint="A deployer-instance-….json file.">
          {(id) => (
            <Input
              id={id}
              type="file"
              accept=".json,application/json"
              required
              className="py-1.5 file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-2.5 file:py-1 file:text-sm file:font-medium file:text-fg"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          )}
        </Field>
        <Field label="Passphrase" hint="The passphrase chosen when the export was created.">
          {(id) => (
            <Input
              id={id}
              type="password"
              autoComplete="off"
              required
              minLength={MIN_PASSPHRASE}
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
            />
          )}
        </Field>
        {restore.error && <Alert tone="danger">{errorMessage(restore.error)}</Alert>}
        <div className="flex justify-between gap-2">
          <Button onClick={onBack} disabled={restore.isPending}>
            Back
          </Button>
          <Button
            type="submit"
            variant="primary"
            loading={restore.isPending}
            disabled={!file || passphrase.length < MIN_PASSPHRASE}
          >
            {restore.isPending ? "Restoring…" : "Restore"}
          </Button>
        </div>
      </form>
    </>
  );
}

function OwnerStep({ onBack, onDone }: { onBack: () => void; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && confirm !== password;

  const create = useMutation({
    mutationFn: api.setup.createOwner,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
      onDone();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) return;
    create.mutate({ email: email.trim(), password, display_name: name.trim() || undefined });
  };

  return (
    <>
      <StepHeader icon={<UserPlus className="size-5" />} title="Create the owner account">
        <p>The owner manages instance settings, sign-in providers and users. You can link Google or GitHub later.</p>
      </StepHeader>
      <form className="space-y-4" onSubmit={onSubmit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" optional>
            {(id) => <Input id={id} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label="Email">
            {(id) => (
              <Input
                id={id}
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field label="Password" hint={`At least ${MIN_PASSWORD} characters.`}>
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          <Field label="Confirm password" error={mismatch ? "Passwords don't match." : undefined}>
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
        {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
        <div className="flex justify-between gap-2">
          <Button onClick={onBack} disabled={create.isPending}>
            Back
          </Button>
          <Button type="submit" variant="primary" loading={create.isPending} disabled={mismatch}>
            Create owner
          </Button>
        </div>
      </form>
    </>
  );
}

function PublicUrlStep({ onDone }: { onDone: () => void }) {
  const settings = useInstanceSettings();
  if (settings.isPending) return <PageSpinner />;
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />;
  return <PublicUrlForm current={settings.data.public_url} onDone={onDone} />;
}

function PublicUrlForm({ current, onDone }: { current: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [url, setUrl] = useState(window.location.origin);
  const save = useMutation({
    mutationFn: (public_url: string) => api.instance.updateSettings({ public_url }),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.instanceSettings, data);
      void queryClient.invalidateQueries({ queryKey: qk.setupStatus });
      toast.success("Public URL saved.");
      onDone();
    },
  });

  let valid = false;
  try {
    const u = new URL(url);
    valid = u.protocol === "http:" || u.protocol === "https:";
  } catch {
    valid = false;
  }

  return (
    <>
      <StepHeader icon={<Globe className="size-5" />} title="Public URL">
        <p>
          This must be the address <strong>other people and devices</strong> use to reach this Deployer — for example
          a Tailscale (<code>https://my-pc.tailnet-name.ts.net</code>) or Cloudflare Tunnel address, not{" "}
          <code>localhost</code> if you'll use it from your phone.
        </p>
        <p>
          Invite links and the <strong>OAuth callback URLs</strong> for Google/GitHub sign-in are built from it, so if
          you change it later you'll need to update your OAuth apps too.
        </p>
      </StepHeader>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate(url.trim().replace(/\/+$/, ""));
        }}
      >
        <Field
          label="Public URL"
          hint={current && current !== url ? `Currently saved: ${current}` : "Prefilled with the address you're using now."}
          error={url && !valid ? "Enter a full URL starting with http:// or https://" : undefined}
        >
          {(id) => (
            <Input
              id={id}
              type="url"
              inputMode="url"
              required
              value={url}
              aria-invalid={Boolean(url) && !valid}
              onChange={(e) => setUrl(e.target.value)}
              spellCheck={false}
              autoCapitalize="off"
            />
          )}
        </Field>
        {save.error && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
        <div className="flex justify-end gap-2">
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!valid}>
            Save and continue
          </Button>
        </div>
      </form>
    </>
  );
}

function ProvidersStep({ onBack, onDone }: { onBack: () => void; onDone: () => void }) {
  const settings = useInstanceSettings();
  return (
    <>
      <StepHeader icon={<KeyRound className="size-5" />} title="Sign-in providers (optional)">
        <p>
          Let people sign in with Google or GitHub. Deployer ships <strong>no shared keys</strong> — every
          installation creates <strong>its own</strong> OAuth app, which takes about five minutes each. Email and
          password sign-in always works, so you can skip this and come back later in Instance settings.
        </p>
      </StepHeader>
      {settings.isPending ? (
        <PageSpinner />
      ) : settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
      ) : (
        <div className="space-y-4">
          <OAuthProviderCard provider="google" settings={settings.data} defaultExpanded={false} />
          <OAuthProviderCard provider="github" settings={settings.data} defaultExpanded={false} />
        </div>
      )}
      <div className="mt-5 flex justify-between gap-2">
        <Button onClick={onBack}>Back</Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onDone}>
            Skip for now
          </Button>
          <Button variant="primary" onClick={onDone}>
            Continue
          </Button>
        </div>
      </div>
    </>
  );
}

function DoneStep() {
  const navigate = useNavigate();
  return (
    <>
      <StepHeader icon={<PartyPopper className="size-5" />} title="You're all set">
        <p>Deployer is ready. Create your first project to get a managed MariaDB and MongoDB database.</p>
      </StepHeader>
      <ul className="mb-5 space-y-2 text-sm">
        <li className="flex gap-2">
          <Check className="mt-0.5 size-4 shrink-0 text-success" /> Change the public URL, sign-up policy and providers
          any time in <strong>Instance settings</strong>.
        </li>
        <li className="flex gap-2">
          <Check className="mt-0.5 size-4 shrink-0 text-success" /> Move everything to another device with{" "}
          <strong>Export &amp; import</strong>.
        </li>
      </ul>
      <div className="flex justify-end">
        <Button variant="primary" onClick={() => navigate("/", { replace: true })}>
          Go to dashboard
        </Button>
      </div>
    </>
  );
}
