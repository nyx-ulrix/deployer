import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, HardDrive } from "lucide-react";
import { isApiError } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { DeviceEnrollment } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { AuthShell } from "../../components/layout/AppLayout";
import { Button } from "../../components/ui/Button";
import { Field, Input } from "../../components/ui/Input";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatDateTime, relativeTime } from "../../lib/format";
import { CapabilityList } from "./DeviceBits";
import { DeviceSettingsFields } from "./DeviceSettingsFields";
import { deviceSettingsValid, type DeviceSettingsValue } from "./eligibility";

const CODE_RE = /^[A-Z0-9]{4}-[A-Z0-9]{4}$/;

function normalizeCode(input: string): string {
  const raw = input.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  return raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw;
}

/** `/devices/approve?code=ABCD-EFGH` on the main Deployer (requires sign-in). */
export function ApproveDevicePage() {
  const [params, setParams] = useSearchParams();
  const code = normalizeCode(params.get("code") ?? "");
  return (
    <AuthShell wide>
      <div className="mb-5 flex items-center gap-3">
        <span className="flex size-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <HardDrive className="size-5" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Approve a host device</h1>
          <p className="text-sm text-muted">Let another PC host databases for your projects.</p>
        </div>
      </div>
      {CODE_RE.test(code) ? (
        <EnrollmentApproval key={code} code={code} onChangeCode={() => setParams({}, { replace: true })} />
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
      <p className="text-sm text-muted">
        Enter the code shown on the device's Deployer dashboard under <em>Make this PC a host device</em>.
      </p>
      <Field label="Device code">
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

function EnrollmentApproval({ code, onChangeCode }: { code: string; onChangeCode: () => void }) {
  const enrollment = useQuery({
    queryKey: qk.enrollment(code),
    queryFn: () => api.devices.enrollmentByCode(code),
    retry: false,
  });

  if (enrollment.isPending) return <PageSpinner label="Looking up the device…" />;
  if (enrollment.isError) {
    const notFound = isApiError(enrollment.error) && enrollment.error.status === 404;
    return (
      <div className="space-y-4">
        {notFound ? (
          <Alert tone="danger" title="No device is waiting with this code">
            Check the code on the device. Codes expire after 15 minutes — start again on the device if needed.
          </Alert>
        ) : (
          <ErrorAlert error={enrollment.error} />
        )}
        <div className="flex gap-2">
          <Button onClick={onChangeCode}>Enter a different code</Button>
          {!notFound && <Button onClick={() => void enrollment.refetch()}>Try again</Button>}
        </div>
      </div>
    );
  }
  const e = enrollment.data;
  // Compare with when the enrollment was fetched (render must stay pure).
  const lapsed = Date.parse(e.expires_at) < enrollment.dataUpdatedAt;
  if (e.status !== "pending" || lapsed) {
    const expired = e.status === "expired" || (e.status === "pending" && lapsed);
    return (
      <div className="space-y-4">
        <Alert tone={expired ? "warning" : "info"} title={expired ? "This code has expired" : "Already handled"}>
          {expired
            ? "Start again on the device to get a new code."
            : e.status === "denied"
              ? "This device request was denied."
              : "This device has already been approved."}
        </Alert>
        <Button onClick={onChangeCode}>Enter a different code</Button>
      </div>
    );
  }
  return <ApprovalForm enrollment={e} />;
}

function ApprovalForm({ enrollment }: { enrollment: DeviceEnrollment }) {
  const user = useCurrentUser();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [settings, setSettings] = useState<DeviceSettingsValue>({
    name: enrollment.name,
    roles: ["database_host"],
    sharing_mode: "my_projects",
    project_ids: [],
  });
  const [confirmed, setConfirmed] = useState(false);
  const [done, setDone] = useState<"approved" | "denied" | null>(null);

  const approve = useMutation({
    mutationFn: () =>
      api.devices.approve(enrollment.id, {
        user_code: enrollment.user_code,
        name: settings.name.trim(),
        roles: settings.roles,
        sharing_mode: settings.sharing_mode,
        project_ids: settings.sharing_mode === "selected" ? settings.project_ids : [],
      }),
    onSuccess: () => {
      setDone("approved");
      void queryClient.invalidateQueries({ queryKey: qk.devicesAll });
    },
  });
  const deny = useMutation({
    mutationFn: () => api.devices.deny(enrollment.id, enrollment.user_code),
    onSuccess: () => {
      setDone("denied");
      toast.info("Device request denied.");
    },
  });

  if (done === "approved") {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center" role="status">
        <CheckCircle2 className="size-12 text-success" />
        <h2 className="text-xl font-semibold">{settings.name.trim()} is approved</h2>
        <p className="max-w-md text-sm text-muted">
          You can close this tab; the device will connect in a few seconds. It will appear under{" "}
          <Link to="/settings/devices" className="font-medium text-accent hover:underline">
            Settings → Devices
          </Link>
          .
        </p>
      </div>
    );
  }
  if (done === "denied") {
    return (
      <Alert tone="info" title="Request denied">
        The device won't be attached. You can close this tab.
      </Alert>
    );
  }

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    if (confirmed && deviceSettingsValid(settings)) approve.mutate();
  };
  const busy = approve.isPending || deny.isPending;

  return (
    <form className="space-y-5" onSubmit={onSubmit}>
      <Card title="Device" bodyClassName="space-y-4">
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div className="min-w-0">
            <dt className="text-xs text-muted">Name</dt>
            <dd className="truncate font-medium">{enrollment.name}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted">Hostname</dt>
            <dd className="truncate font-mono">{enrollment.hostname ?? "—"}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted">Operating system</dt>
            <dd className="truncate">{enrollment.os ?? "—"}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted">Deployer version</dt>
            <dd className="truncate">{enrollment.version ?? "—"}</dd>
          </div>
        </dl>
        <div>
          <p className="mb-1.5 text-xs text-muted">Capabilities</p>
          <CapabilityList capabilities={enrollment.capabilities} />
        </div>
        <p className="text-xs text-muted">
          Requested <span title={formatDateTime(enrollment.created_at)}>{relativeTime(enrollment.created_at)}</span> ·
          code expires {relativeTime(enrollment.expires_at)}
        </p>
      </Card>

      <div className="rounded-xl border-2 border-dashed border-accent/50 p-4 text-center">
        <p className="text-sm text-muted">Make sure the device shows exactly this code</p>
        <code className="mt-1 block font-mono text-3xl font-bold tracking-[0.2em]">{enrollment.user_code}</code>
        <label className="mt-3 inline-flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[var(--accent)]"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          The code matches the one on my device
        </label>
      </div>

      <Card title="Settings">
        <DeviceSettingsFields value={settings} onChange={setSettings} />
      </Card>

      <Alert tone="info" title="What the device gets">
        The device will be owned by <strong>{user.display_name || user.email}</strong>. It only receives a device token
        for hosting databases — never your password or access to your account.
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
          disabled={busy || !confirmed || !deviceSettingsValid(settings)}
          title={!confirmed ? "Confirm the code first" : undefined}
        >
          Approve device
        </Button>
      </div>
    </form>
  );
}
