import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Download,
  GitCompare,
  Loader2,
  MoreVertical,
  Pin,
  RotateCcw,
  ShieldAlert,
  Tag,
  Trash2,
  XCircle,
} from "lucide-react";
import { errorMessage, saveBlob } from "../../api/client";
import { api, qk } from "../../api/endpoints";
import type { Backup, BackupPolicy, DataSource } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input } from "../../components/ui/Input";
import { Menu, MenuItem } from "../../components/ui/Menu";
import { useToast } from "../../components/ui/toast-context";
import { cn } from "../../lib/cn";
import { formatBytes, formatDateTime, formatTime, relativeTime } from "../../lib/format";
import { CopyIcons, TriggerBadge } from "./BackupBits";
import { groupByDay, RETENTION_LABELS, retentionReasons } from "./timeline";

export type TimelineActions = {
  onCompare: (backup: Backup) => void;
  onRestore: (backup: Backup) => void;
};

export function VersionsTimeline({
  projectId,
  source,
  backups,
  policy,
  can,
  deviceName,
  actions,
}: {
  projectId: string;
  source: DataSource;
  backups: Backup[];
  policy: BackupPolicy | undefined;
  can: { developer: boolean; admin: boolean; owner: boolean };
  deviceName: (id: string | null) => string | null;
  actions: TimelineActions;
}) {
  const groups = groupByDay(backups);
  const reasons = policy ? retentionReasons(backups, policy) : null;
  const [labelling, setLabelling] = useState<Backup | null>(null);
  const [deleting, setDeleting] = useState<Backup | null>(null);

  return (
    <div className="space-y-5">
      {groups.map((g) => (
        <section key={g.key} aria-labelledby={`day-${g.key}`}>
          <h3
            id={`day-${g.key}`}
            className="sticky top-14 z-10 mb-2 bg-bg/90 py-1 text-xs font-semibold tracking-wide text-muted uppercase backdrop-blur"
          >
            {g.label} <span className="font-normal normal-case">· {g.items.length}</span>
          </h3>
          <ol className="relative space-y-2 border-l border-border pl-4">
            {g.items.map((b) => (
              <li key={b.id} className="relative">
                <span
                  className={cn(
                    "absolute top-4 -left-[21px] size-2.5 rounded-full ring-2 ring-bg",
                    b.status === "succeeded" ? (b.pinned ? "bg-accent" : "bg-success") : b.status === "failed" ? "bg-danger" : "bg-info",
                  )}
                  aria-hidden="true"
                />
                <VersionRow
                  projectId={projectId}
                  source={source}
                  backup={b}
                  keptAs={reasons?.get(b.id) ?? null}
                  can={can}
                  deviceName={deviceName}
                  onCompare={() => actions.onCompare(b)}
                  onRestore={() => actions.onRestore(b)}
                  onLabel={() => setLabelling(b)}
                  onDelete={() => setDeleting(b)}
                />
              </li>
            ))}
          </ol>
        </section>
      ))}
      {labelling && (
        <LabelDialog projectId={projectId} sourceId={source.id} backup={labelling} onClose={() => setLabelling(null)} />
      )}
      {deleting && (
        <DeleteVersionDialog projectId={projectId} sourceId={source.id} backup={deleting} onClose={() => setDeleting(null)} />
      )}
    </div>
  );
}

function VersionRow({
  projectId,
  source,
  backup: b,
  keptAs,
  can,
  deviceName,
  onCompare,
  onRestore,
  onLabel,
  onDelete,
}: {
  projectId: string;
  source: DataSource;
  backup: Backup;
  keptAs: string[] | null;
  can: { developer: boolean; admin: boolean; owner: boolean };
  deviceName: (id: string | null) => string | null;
  onCompare: () => void;
  onRestore: () => void;
  onLabel: () => void;
  onDelete: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const ok = b.status === "succeeded";

  const pin = useMutation({
    mutationFn: () => api.backups.update(projectId, source.id, b.id, { pinned: !b.pinned }),
    onSuccess: (updated) => {
      queryClient.setQueryData<Backup[]>(qk.backups(projectId, source.id), (list) =>
        list?.map((x) => (x.id === updated.id ? updated : x)),
      );
      toast.success(updated.pinned ? "Version pinned — it won't be pruned." : "Version unpinned.");
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't change pin"),
  });
  const download = useMutation({
    mutationFn: () => api.backups.download(projectId, source.id, b.id),
    onSuccess: (file) => {
      saveBlob(file);
      toast.success(`Downloaded ${file.filename}.`);
    },
    onError: (e) => toast.error(errorMessage(e), "Download failed"),
  });

  const pruneCandidate = ok && keptAs !== null && keptAs.length === 0;

  return (
    <article className="rounded-xl border border-border bg-surface p-3 shadow-xs">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <time dateTime={b.started_at} title={formatDateTime(b.started_at)} className="font-semibold tabular-nums">
              {formatTime(b.started_at)}
            </time>
            <span className="text-xs text-muted">{relativeTime(b.started_at)}</span>
            <TriggerBadge trigger={b.trigger} />
            {b.status === "running" && (
              <Badge tone="info">
                <Loader2 className="size-3 animate-spin" /> Running
              </Badge>
            )}
            {b.status === "failed" && (
              <Badge tone="danger">
                <XCircle className="size-3" /> Failed
              </Badge>
            )}
            {b.verify_status === "ok" && (
              <Badge tone="success" title={`Verified ${formatDateTime(b.verified_at)}`}>
                <CheckCircle2 className="size-3" /> Verified
              </Badge>
            )}
            {b.verify_status === "failed" && (
              <Badge tone="danger" title={`Verification failed ${formatDateTime(b.verified_at)}`}>
                <ShieldAlert className="size-3" /> Verify failed
              </Badge>
            )}
          </div>
          {b.label && (
            <p className="mt-1 flex items-center gap-1 text-sm font-medium">
              <Tag className="size-3.5 text-muted" /> {b.label}
            </p>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span>{formatBytes(b.size_bytes)}</span>
            <CopyIcons copies={b.copies} deviceName={deviceName} />
            {keptAs && keptAs.length > 0 && (
              <span title="Why this version is kept (retention policy)">
                Kept: {keptAs.map((r) => RETENTION_LABELS[r as keyof typeof RETENTION_LABELS] ?? r).join(", ")}
              </span>
            )}
            {pruneCandidate && <span title="Not needed by the retention policy">May be pruned soon</span>}
            {b.expires_at && <span>Expires {relativeTime(b.expires_at)}</span>}
          </div>
        </div>

        <div className="flex items-center gap-1">
          {can.developer && ok && (
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={() => pin.mutate()}
              disabled={pin.isPending}
              aria-pressed={b.pinned}
              aria-label={b.pinned ? "Unpin version" : "Pin version"}
              title={b.pinned ? "Pinned — click to unpin" : "Pin so it's never pruned"}
              className={b.pinned ? "text-accent" : "text-muted"}
            >
              <Pin className={cn("size-4", b.pinned && "fill-current")} />
            </Button>
          )}
          {ok && (
            <Button size="sm" variant="ghost" className="hidden sm:inline-flex" icon={<GitCompare className="size-3.5" />} onClick={onCompare}>
              Compare
            </Button>
          )}
          {ok && (
            <Menu
              trigger={({ toggle, open }) => (
                <Button size="icon-sm" variant="ghost" onClick={toggle} aria-expanded={open} aria-label="Version actions">
                  <MoreVertical className="size-4" />
                </Button>
              )}
            >
              {(close) => (
                <>
                  <MenuItem icon={<GitCompare />} onClick={() => (close(), onCompare())}>
                    Compare with…
                  </MenuItem>
                  {can.admin && (
                    <MenuItem icon={<RotateCcw />} onClick={() => (close(), onRestore())}>
                      Restore this version…
                    </MenuItem>
                  )}
                  {can.developer && (
                    <MenuItem icon={<Tag />} onClick={() => (close(), onLabel())}>
                      {b.label ? "Edit label" : "Add label"}
                    </MenuItem>
                  )}
                  {can.owner && (
                    <MenuItem icon={<Download />} onClick={() => (close(), download.mutate())}>
                      Download {source.kind === "sql" ? "(.sql.gz)" : "(archive)"}
                    </MenuItem>
                  )}
                  {can.admin && (
                    <MenuItem
                      danger
                      icon={<Trash2 />}
                      onClick={() => {
                        close();
                        if (b.pinned) toast.info("Unpin this version before deleting it.");
                        else onDelete();
                      }}
                    >
                      Delete version
                    </MenuItem>
                  )}
                </>
              )}
            </Menu>
          )}
        </div>
      </div>
    </article>
  );
}

function LabelDialog({
  projectId,
  sourceId,
  backup,
  onClose,
}: {
  projectId: string;
  sourceId: string;
  backup: Backup;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [label, setLabel] = useState(backup.label ?? "");
  const [pinned, setPinned] = useState(backup.label ? backup.pinned : true);
  const save = useMutation({
    mutationFn: () => api.backups.update(projectId, sourceId, backup.id, { label: label.trim() || null, pinned }),
    onSuccess: (updated) => {
      queryClient.setQueryData<Backup[]>(qk.backups(projectId, sourceId), (list) =>
        list?.map((x) => (x.id === updated.id ? updated : x)),
      );
      toast.success("Label saved.");
      onClose();
    },
  });
  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title="Label version"
      description={formatDateTime(backup.started_at)}
      dismissible={!save.isPending}
      footer={
        <>
          <Button onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="label-form" variant="primary" loading={save.isPending}>
            Save
          </Button>
        </>
      }
    >
      <form
        id="label-form"
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Label" hint="e.g. “Before v2 migration”. Leave empty to remove.">
          {(id) => <Input id={id} value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)} />}
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-[var(--accent)]"
            checked={pinned}
            onChange={(e) => setPinned(e.target.checked)}
          />
          Pin (never prune automatically)
        </label>
        {save.error && <p className="text-sm text-danger">{errorMessage(save.error)}</p>}
      </form>
    </Dialog>
  );
}

function DeleteVersionDialog({
  projectId,
  sourceId,
  backup,
  onClose,
}: {
  projectId: string;
  sourceId: string;
  backup: Backup;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.backups.remove(projectId, sourceId, backup.id),
    onSuccess: () => {
      queryClient.setQueryData<Backup[]>(qk.backups(projectId, sourceId), (list) => list?.filter((x) => x.id !== backup.id));
      void queryClient.invalidateQueries({ queryKey: qk.recoveryWindow(projectId, sourceId) });
      toast.success("Version deleted.");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e), "Couldn't delete version"),
  });
  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={() => remove.mutate()}
      loading={remove.isPending}
      title="Delete this version?"
      confirmLabel="Delete version"
      description={`The version from ${formatDateTime(backup.started_at)} and all of its copies will be deleted. Point-in-time recovery before the next older version may no longer be possible.`}
    />
  );
}
