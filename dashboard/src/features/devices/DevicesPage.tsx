import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Download, HardDrive, Laptop, MoreVertical, Pencil, Play, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import { useDevices, useSetupStatus } from "../../api/hooks";
import type { Device } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { CopyField } from "../../components/ui/CopyField";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox } from "../../components/ui/Input";
import { Menu, MenuItem } from "../../components/ui/Menu";
import { PageSpinner } from "../../components/ui/Spinner";
import { Alert, Card, EmptyState, ErrorAlert, ErrorState, PageHeader } from "../../components/ui/States";
import { Tabs } from "../../components/ui/Tabs";
import { useToast } from "../../components/ui/toast-context";
import { formatDate } from "../../lib/format";
import { InstanceNav } from "../settings/InstanceNav";
import { OnlineIndicator, RoleBadges, UsageBars } from "./DeviceBits";
import { DeviceSettingsFields } from "./DeviceSettingsFields";
import {
  deviceSettingsValid,
  isDeviceOnline,
  reachabilityWarning,
  removalCheck,
  SHARING_LABELS,
  type DeviceSettingsValue,
} from "./eligibility";
import { EnrollDeviceFlow } from "./EnrollDeviceFlow";

const RELEASES_URL = "https://github.com/nyx-ulrix/deployer/releases/latest";

type Scope = "mine" | "all";

export function DevicesPage() {
  const user = useCurrentUser();
  const [scope, setScope] = useState<Scope>("mine");
  const effectiveScope: Scope = user.is_instance_owner ? scope : "mine";
  const devices = useDevices(effectiveScope);
  const setup = useSetupStatus();

  return (
    <div className="mx-auto w-full max-w-4xl">
      {user.is_instance_owner && <InstanceNav />}
      <PageHeader
        title="Devices"
        description="Other PCs attached to this Deployer. Projects can host their managed databases on them."
      />
      <div className="space-y-5">
        {user.is_instance_owner && (
          <Tabs<Scope>
            value={scope}
            onChange={setScope}
            items={[
              { value: "mine", label: "Your devices" },
              { value: "all", label: "All devices" },
            ]}
          />
        )}

        {devices.isPending ? (
          <PageSpinner />
        ) : devices.isError ? (
          <ErrorState error={devices.error} onRetry={() => void devices.refetch()} />
        ) : devices.data.length === 0 ? (
          <EmptyState
            icon={<HardDrive className="size-5" />}
            title={effectiveScope === "all" ? "No devices on this instance" : "You haven't attached any devices"}
            description="Follow the steps below on the PC you want to add."
          />
        ) : (
          <ul className="space-y-3">
            {devices.data.map((d) => (
              <li key={d.id}>
                <DeviceCard device={d} showOwner={effectiveScope === "all"} />
              </li>
            ))}
          </ul>
        )}

        <AddDevicePanel publicUrl={setup.data?.public_url ?? window.location.origin} isOwner={user.is_instance_owner} />

        {user.is_instance_owner && setup.data?.device_mode !== "host" && <AttachThisDeployerCard />}
      </div>
    </div>
  );
}

function DeviceCard({ device, showOwner }: { device: Device; showOwner: boolean }) {
  const user = useCurrentUser();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const isOwner = device.owner_id === user.id;
  // `?edit=<id>` opens the settings straight away (linked from "Copy to my device" when a device isn't shared).
  const [editing, setEditing] = useState(() => isOwner && params.get("edit") === device.id);
  const [removing, setRemoving] = useState(false);
  const online = isDeviceOnline(device);
  const hosted = device.hosted_sources_count ?? 0;

  const toggleDisabled = useMutation({
    mutationFn: () => api.devices.update(device.id, { status: device.status === "active" ? "disabled" : "active" }),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: qk.devicesAll });
      toast.success(d.status === "disabled" ? `${d.name} disabled.` : `${d.name} enabled.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't update device"),
  });

  const canManage = isOwner || user.is_instance_owner;

  return (
    <article className="rounded-xl border border-border bg-surface p-4 shadow-xs">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-accent">
          <Laptop className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-semibold">{device.name}</h3>
            {device.status === "disabled" && <Badge tone="danger">Disabled</Badge>}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <OnlineIndicator online={online} lastSeen={device.last_seen_at} />
            <span className="truncate text-xs text-muted">
              {[device.hostname, device.os, device.version && `Deployer ${device.version}`].filter(Boolean).join(" · ")}
            </span>
          </div>
        </div>
        {canManage && (
          <Menu
            trigger={({ toggle, open }) => (
              <Button size="icon-sm" variant="ghost" onClick={toggle} aria-expanded={open} aria-label={`Actions for ${device.name}`}>
                <MoreVertical className="size-4" />
              </Button>
            )}
          >
            {(close) => (
              <>
                {isOwner && (
                  <MenuItem
                    icon={<Pencil />}
                    onClick={() => {
                      close();
                      setEditing(true);
                    }}
                  >
                    Edit name, roles &amp; sharing
                  </MenuItem>
                )}
                {user.is_instance_owner && (
                  <MenuItem
                    icon={device.status === "active" ? <Ban /> : <Play />}
                    onClick={() => {
                      close();
                      toggleDisabled.mutate();
                    }}
                  >
                    {device.status === "active" ? "Disable device" : "Enable device"}
                  </MenuItem>
                )}
                <MenuItem
                  danger
                  icon={<Trash2 />}
                  onClick={() => {
                    close();
                    setRemoving(true);
                  }}
                >
                  Remove device
                </MenuItem>
              </>
            )}
          </Menu>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <RoleBadges roles={device.roles} />
        <Badge>{SHARING_LABELS[device.sharing_mode]}</Badge>
        <Badge tone={hosted > 0 ? "accent" : "neutral"}>
          {hosted} database{hosted === 1 ? "" : "s"} hosted
        </Badge>
        {showOwner && (
          <Badge tone="neutral" title="Owner">
            {device.owner_name || device.owner_email || (isOwner ? "You" : "Another user")}
          </Badge>
        )}
      </div>

      <UsageBars metrics={device.metrics} className="mt-4" />
      <p className="mt-3 text-xs text-muted">Added {formatDate(device.created_at)}</p>

      {editing && <EditDeviceDialog device={device} onClose={() => setEditing(false)} />}
      {removing && <RemoveDeviceDialog device={device} onClose={() => setRemoving(false)} />}
    </article>
  );
}

function EditDeviceDialog({ device, onClose }: { device: Device; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [value, setValue] = useState<DeviceSettingsValue>({
    name: device.name,
    roles: device.roles,
    sharing_mode: device.sharing_mode,
    project_ids: device.project_ids ?? [],
  });
  const save = useMutation({
    mutationFn: () =>
      api.devices.update(device.id, {
        name: value.name.trim(),
        roles: value.roles,
        sharing_mode: value.sharing_mode,
        project_ids: value.sharing_mode === "selected" ? value.project_ids : [],
      }),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: qk.devicesAll });
      toast.success(`${d.name} updated.`);
      onClose();
    },
  });
  const droppingHost = device.roles.includes("database_host") && !value.roles.includes("database_host");
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Edit ${device.name}`}
      dismissible={!save.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="edit-device"
            variant="primary"
            loading={save.isPending}
            disabled={!deviceSettingsValid(value)}
          >
            Save
          </Button>
        </>
      }
    >
      <form
        id="edit-device"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (deviceSettingsValid(value)) save.mutate();
        }}
      >
        <DeviceSettingsFields value={value} onChange={setValue} />
        {droppingHost && (device.hosted_sources_count ?? 0) > 0 && (
          <Alert tone="warning">
            Databases already on this device stay there. New databases just can't be placed on it anymore.
          </Alert>
        )}
        {save.error && <ErrorAlert error={save.error} />}
      </form>
    </Dialog>
  );
}

function RemoveDeviceDialog({ device, onClose }: { device: Device; onClose: () => void }) {
  const user = useCurrentUser();
  const toast = useToast();
  const queryClient = useQueryClient();
  const check = removalCheck(device, user.is_instance_owner);
  const remove = useMutation({
    mutationFn: () => api.devices.remove(device.id, check.force),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.devicesAll });
      toast.success(`${device.name} removed.`);
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't remove device"),
  });

  if (!check.allowed) {
    return (
      <Dialog
        open
        onClose={onClose}
        title={`Can't remove ${device.name} yet`}
        size="sm"
        footer={<Button onClick={onClose}>OK</Button>}
      >
        <p className="text-sm text-muted">{check.reason}</p>
      </Dialog>
    );
  }

  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={() => remove.mutate()}
      loading={remove.isPending}
      title={`Remove ${device.name}?`}
      confirmLabel={check.force ? "Force remove" : "Remove device"}
      confirmText={check.force ? device.name : undefined}
      description={
        check.force
          ? undefined
          : "The device's token stops working immediately. To use the PC again, enroll it again from its own dashboard."
      }
    >
      {check.force && (
        <Alert tone="danger" title="This device still hosts databases">
          {check.reason} As instance owner you can force removal: the device is detached anyway and those databases are
          marked as errored (“device removed”).
        </Alert>
      )}
    </ConfirmDialog>
  );
}

function AddDevicePanel({ publicUrl, isOwner }: { publicUrl: string; isOwner: boolean }) {
  const warning = reachabilityWarning(publicUrl);
  return (
    <Card
      title="Add a device"
      description="Use a spare PC to host databases. It connects out to this Deployer — no port forwarding needed."
    >
      <ol className="space-y-4 text-sm">
        <Step n={1}>
          <p>
            <strong>Install Deployer on the other PC.</strong> Download the latest installer and run it there.
          </p>
          <a
            href={RELEASES_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 text-xs font-medium shadow-sm hover:bg-surface-2"
          >
            <Download className="size-3.5" /> DeployerSetup.exe (latest release)
          </a>
        </Step>
        <Step n={2}>
          <p>
            <strong>Open its dashboard</strong> (on that PC, usually <code className="font-mono">http://localhost:8080</code>)
            and choose <strong>Make this PC a host device</strong>.
          </p>
        </Step>
        <Step n={3}>
          <p>
            <strong>Enter this Deployer's URL</strong>, then approve the code it shows when this Deployer asks you to
            sign in.
          </p>
          <CopyField className="mt-2" label="This Deployer's URL" value={publicUrl} />
          {warning && (
            <Alert tone="warning" className="mt-2">
              {warning}{" "}
              {isOwner && (
                <Link to="/settings/remote-access" className="font-medium text-accent hover:underline">
                  Open Domains &amp; remote access
                </Link>
              )}
            </Alert>
          )}
        </Step>
      </ol>
    </Card>
  );
}

function Step({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
        {n}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  );
}

function AttachThisDeployerCard() {
  const [open, setOpen] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  return (
    <Card
      title="Attach this Deployer to another Deployer"
      description="Turn this installation into a host device for a main Deployer somewhere else."
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-muted">
          Only do this on a PC you want to dedicate to hosting databases for another Deployer.
        </p>
        <Button icon={<HardDrive className="size-4" />} onClick={() => setOpen(true)}>
          Attach as host device…
        </Button>
      </div>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Make this PC a host device"
        size="lg"
      >
        {acknowledged ? (
          <EnrollDeviceFlow onCancel={() => setOpen(false)} />
        ) : (
          <div className="space-y-4">
            <Alert tone="danger" title="This changes what this Deployer is">
              Once attached, this dashboard only shows the host-device status page. People can no longer sign in here,
              and projects on this instance aren't reachable from this dashboard until you detach it. Export anything you
              need first (Settings → Export &amp; import).
            </Alert>
            <Checkbox
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              label="I understand — continue"
            />
          </div>
        )}
      </Dialog>
    </Card>
  );
}
