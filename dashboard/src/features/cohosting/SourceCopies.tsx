import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CopyPlus, HardDrive, MoreVertical, Pause, Play, RotateCcw, Trash2 } from "lucide-react";
import { errorMessage } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { CohostEligibility, DataSource, Replica } from "../../api/types";
import { useCurrentUser } from "../../auth/auth-context";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox } from "../../components/ui/Input";
import { Menu, MenuItem } from "../../components/ui/Menu";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatDateTime, relativeTime } from "../../lib/format";
import { JobProgressPanel } from "../jobs/JobProgress";
import { useProjectContext } from "../projects/project-context";
import { canManageReplica, copyTargets, lagText, replicaBadge, syncPath, type CopyTarget } from "./cohosting";

/**
 * The "Copies" block of a source card: its co-host copies, and "Copy to my device" for eligible members.
 * Renders nothing when there are no copies and nothing to offer, so co-hosting stays invisible to everyone
 * who doesn't use it. Pass `eligibility` undefined to never show the offer (e.g. on the Sync page).
 */
export function SourceCopies({
  source,
  allSources,
  eligibility,
}: {
  source: DataSource;
  allSources: DataSource[];
  eligibility: CohostEligibility | undefined;
}) {
  const me = useCurrentUser();
  // Targets are frozen when the dialog opens: once the copy exists they vanish, but the dialog must stay
  // open to show the job's progress.
  const [copying, setCopying] = useState<CopyTarget[] | null>(null);
  const replicas = source.replicas ?? [];
  const targets = copyTargets(eligibility, source, allSources, me.id);
  if (replicas.length === 0 && !targets && !copying) return null;

  return (
    <div className="mt-3 space-y-2 border-t border-border pt-3">
      {replicas.length > 0 && (
        <>
          <p className="text-xs font-medium text-muted">Copies</p>
          <ul className="space-y-2">
            {replicas.map((r) => (
              <ReplicaRow key={r.id} source={source} replica={r} />
            ))}
          </ul>
        </>
      )}
      {targets && (
        <Button size="sm" icon={<CopyPlus className="size-3.5" />} onClick={() => setCopying(targets)}>
          Copy to my device
        </Button>
      )}
      {copying && <CopyToDeviceDialog source={source} targets={copying} onClose={() => setCopying(null)} />}
    </div>
  );
}

type Pending = "recopy" | "remove" | null;

function ReplicaRow({ source, replica: r }: { source: DataSource; replica: Replica }) {
  const { project, can } = useProjectContext();
  const me = useCurrentUser();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<Pending>(null);
  const [drop, setDrop] = useState(false);
  const badge = replicaBadge(r);
  const device = r.device_name ?? "a co-host device";
  const manage = canManageReplica(r, me.id, can("admin"));

  const refresh = () => void queryClient.invalidateQueries({ queryKey: qk.dataSources(project.id) });

  const action = useMutation({
    mutationFn: (a: "pause" | "resume" | "recopy") => api.cohosting.replicaAction(project.id, source.id, r.id, a),
    onSuccess: (_res, a) => {
      refresh();
      if (a === "recopy") void queryClient.invalidateQueries({ queryKey: qk.jobs(project.id) });
      setPending(null);
      toast.success(
        a === "pause" ? `Sync to ${device} paused.` : a === "resume" ? `Sync to ${device} resumed.` : `Copying ${source.name} to ${device} again.`,
      );
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't update the copy"),
  });

  const remove = useMutation({
    mutationFn: () => api.cohosting.removeReplica(project.id, source.id, r.id, drop),
    onSuccess: () => {
      refresh();
      setPending(null);
      toast.success(drop ? `Copy on ${device} removed and deleted.` : `Copy on ${device} removed; its data stays on the device.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't remove the copy"),
  });

  return (
    <li className="rounded-lg bg-surface-2 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <HardDrive className="size-3.5 shrink-0 text-muted" />
        <span className="min-w-0 truncate font-medium">{device}</span>
        <Badge tone={badge.tone}>{badge.label}</Badge>
        <span className="text-muted">{lagText(r)}</span>
        {can("developer") ? (
          <Link
            to={syncPath(project.id, source.id)}
            className={cn("font-medium hover:underline", r.open_conflicts > 0 ? "text-danger" : "text-link")}
          >
            {r.open_conflicts} open conflict{r.open_conflicts === 1 ? "" : "s"}
          </Link>
        ) : (
          r.open_conflicts > 0 && <span className="font-medium text-danger">{r.open_conflicts} open conflicts</span>
        )}
        {manage && (
          <div className="ml-auto">
            <Menu
              trigger={({ toggle, open }) => (
                <Button size="icon-sm" variant="ghost" onClick={toggle} aria-expanded={open} aria-label={`Actions for the copy on ${device}`}>
                  <MoreVertical className="size-4" />
                </Button>
              )}
            >
              {(close) => (
                <>
                  {(r.status === "syncing" || r.status === "error") && (
                    <MenuItem
                      icon={<Pause />}
                      onClick={() => {
                        close();
                        action.mutate("pause");
                      }}
                    >
                      Pause sync
                    </MenuItem>
                  )}
                  {r.status === "paused" && (
                    <MenuItem
                      icon={<Play />}
                      onClick={() => {
                        close();
                        action.mutate("resume");
                      }}
                    >
                      Resume sync
                    </MenuItem>
                  )}
                  {/* Re-copy needs the device online (503 otherwise), so it's only offered then. */}
                  {r.status !== "copying" && r.online && (
                    <MenuItem
                      icon={<RotateCcw />}
                      onClick={() => {
                        close();
                        setPending("recopy");
                      }}
                    >
                      Re-copy
                    </MenuItem>
                  )}
                  <MenuItem
                    danger
                    icon={<Trash2 />}
                    onClick={() => {
                      close();
                      setDrop(false);
                      setPending("remove");
                    }}
                  >
                    Remove copy
                  </MenuItem>
                </>
              )}
            </Menu>
          </div>
        )}
      </div>
      <p className="mt-1 text-muted" title={formatDateTime(r.last_synced_at)}>
        Last synced {relativeTime(r.last_synced_at)}
        {!r.online && r.status !== "syncing" && " · device offline"}
      </p>
      {r.status === "error" && r.error && <p className="mt-1 break-words text-danger">{r.error}</p>}
      {r.warnings.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-warning">
            {r.warnings.length} warning{r.warnings.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-fg/80">
            {r.warnings.map((w, i) => (
              <li key={i} className="break-words">
                <span className="font-mono">{w.table}</span>: {w.message}
              </li>
            ))}
          </ul>
        </details>
      )}

      <ConfirmDialog
        open={pending === "recopy"}
        onClose={() => setPending(null)}
        onConfirm={() => action.mutate("recopy")}
        loading={action.isPending}
        title={`Re-copy ${source.name} to ${device}?`}
        confirmLabel="Re-copy"
        description={
          <>
            The copy on {device} is dropped and copied again from the main server.
            {r.open_conflicts > 0 && (
              <>
                {" "}
                Its {r.open_conflicts} open conflict{r.open_conflicts === 1 ? "" : "s"} end with the{" "}
                <strong>main server's version</strong>; changes only on the co-host side of those rows are lost.
              </>
            )}
          </>
        }
      />
      <ConfirmDialog
        open={pending === "remove"}
        onClose={() => setPending(null)}
        onConfirm={() => remove.mutate()}
        loading={remove.isPending}
        title={`Remove the copy on ${device}?`}
        confirmLabel={drop ? "Remove and delete copy" : "Remove"}
        description="Syncing stops. The main server's database is not touched."
      >
        <Checkbox
          checked={drop}
          disabled={!r.online}
          onChange={(e) => setDrop(e.target.checked)}
          label="Also delete the copy on the device"
          description={
            r.online
              ? "Otherwise the database stays on that PC as a standalone copy that no longer syncs."
              : "The device is offline, so its copy can't be deleted now; it stays there, no longer syncing."
          }
        />
      </ConfirmDialog>
    </li>
  );
}

const REASONS: Record<Exclude<CopyTarget["reason"], null>, string> = {
  not_shared: "Not shared with this project yet.",
  offline: "Device offline. Switch the PC on and make sure Deployer is running.",
  other_device: "You already co-host this project on another device (one device per member).",
};

function CopyToDeviceDialog({
  source,
  targets,
  onClose,
}: {
  source: DataSource;
  targets: CopyTarget[];
  onClose: () => void;
}) {
  const { project } = useProjectContext();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState<string | null>(targets.find((t) => !t.disabled)?.id ?? null);
  const [jobId, setJobId] = useState<string | null>(null);
  const target = targets.find((t) => t.id === choice && !t.disabled) ?? null;

  const create = useMutation({
    mutationFn: (deviceId: string) => api.cohosting.createReplica(project.id, source.id, deviceId),
    onSuccess: ({ job }) => {
      setJobId(job.id);
      void queryClient.invalidateQueries({ queryKey: qk.dataSources(project.id) });
      void queryClient.invalidateQueries({ queryKey: qk.jobs(project.id) });
    },
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Copy ${source.name} to my device`}
      description="Keep a live copy of this database on your own PC. Optional: editing on the web works the same either way."
      dismissible={!create.isPending}
      footer={
        jobId ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={create.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              icon={<CopyPlus className="size-4" />}
              loading={create.isPending}
              disabled={!target}
              onClick={() => target && create.mutate(target.id)}
            >
              Start copying
            </Button>
          </>
        )
      }
    >
      {jobId ? (
        <JobProgressPanel
          projectId={project.id}
          jobId={jobId}
          title={`Copying to ${target?.name ?? "your device"}`}
          onFinished={(job) => {
            void queryClient.invalidateQueries({ queryKey: qk.dataSources(project.id) });
            if (job.status === "succeeded") toast.success(`${source.name} is now copied and syncing.`);
            else if (job.status === "failed") toast.error(job.error ?? "The copy failed.", "Copy failed");
          }}
          result={() => (
            <p className="text-sm text-fg/80">
              Both copies now accept changes and sync both ways. Redeploy apps that write to this database so new ids
              don't collide.
            </p>
          )}
        />
      ) : (
        <div className="space-y-4">
          <fieldset className="space-y-2">
            <legend className="mb-1.5 text-sm font-medium">Your device</legend>
            {targets.map((t) => (
              <label
                key={t.id}
                className={cn(
                  "flex items-start gap-3 rounded-lg border border-border p-3 text-sm",
                  t.disabled ? "bg-surface-2" : "cursor-pointer hover:bg-surface-2",
                  choice === t.id && !t.disabled && "border-accent",
                )}
              >
                <input
                  type="radio"
                  name="cohost-device"
                  className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
                  disabled={t.disabled}
                  checked={choice === t.id && !t.disabled}
                  onChange={() => setChoice(t.id)}
                />
                <span className="min-w-0">
                  <span className={cn("block font-medium", t.disabled && "text-muted")}>{t.name}</span>
                  {t.reason && (
                    <span className="mt-0.5 block text-xs text-muted">
                      {REASONS[t.reason]}{" "}
                      {t.reason === "not_shared" && (
                        <Link to={`/settings/devices?edit=${encodeURIComponent(t.id)}`} className="font-medium text-link hover:underline">
                          Open its sharing settings
                        </Link>
                      )}
                    </span>
                  )}
                </span>
              </label>
            ))}
          </fieldset>
          <Alert tone="info" title="How the copy works">
            Both copies accept changes and sync both ways every few seconds. If the same row changes on both before
            they sync, nothing is overwritten: the row waits until someone picks a version (Databases → Sync). The copy
            on your PC is readable by whoever controls that PC; project secrets are never sent to it.
          </Alert>
          {create.error && <ErrorAlert error={create.error} />}
        </div>
      )}
    </Dialog>
  );
}
