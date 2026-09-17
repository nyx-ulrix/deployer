import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, qk } from "../../api/endpoints";
import { usePlacementOptions } from "../../api/hooks";
import type { BackupPolicy, BackupSchedule, DataSource, PlacementOption } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { Alert, ErrorAlert } from "../../components/ui/States";
import { useToast } from "../../components/ui/toast-context";
import { formatBytes, formatDateTime } from "../../lib/format";
import { SCHEDULE_LABELS } from "./timeline";

const NONE = "none";
const PRIMARY = "primary";

function copyTargetValue(p: Pick<BackupPolicy, "copy_to_primary" | "copy_to_device_id">): string {
  if (p.copy_to_primary) return PRIMARY;
  return p.copy_to_device_id ?? NONE;
}

type CopyOption = { value: string; label: string; disabled: boolean };

/** Copy targets: none, the main server (unless the database already lives there) or a suitable device. */
function copyOptions(options: readonly PlacementOption[], source: DataSource): CopyOption[] {
  const list: CopyOption[] = [{ value: NONE, label: "No extra copy", disabled: false }];
  const onMain = !source.device_id;
  list.push({
    value: PRIMARY,
    label: onMain ? "Main server — already hosts this database" : "Main server",
    disabled: onMain,
  });
  for (const o of options) {
    if (o.device_id === null) continue;
    const storage = o.roles?.includes("backup_storage") ?? false;
    if (!storage && !o.eligible) continue;
    const same = o.device_id === source.device_id;
    const details = [o.online ? "online" : "offline"];
    if (o.disk_free_bytes !== null && o.disk_free_bytes !== undefined) details.push(`${formatBytes(o.disk_free_bytes)} free`);
    if (storage) details.push("backup storage");
    list.push({
      value: o.device_id,
      label: `${o.name} · ${details.join(" · ")}${same ? " — hosts this database" : ""}`,
      disabled: same,
    });
  }
  return list;
}

function clampInt(value: string, min: number, max: number): number {
  const n = Math.round(Number(value));
  if (!Number.isFinite(n)) return min;
  return Math.min(max, Math.max(min, n));
}

export function PolicyDialog({
  projectId,
  source,
  policy,
  canEdit,
  onClose,
}: {
  projectId: string;
  source: DataSource;
  policy: BackupPolicy;
  canEdit: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const placement = usePlacementOptions(projectId, canEdit);
  const [draft, setDraft] = useState(() => ({
    enabled: policy.enabled,
    schedule: policy.schedule,
    keep_hourly: String(policy.keep_hourly),
    keep_daily: String(policy.keep_daily),
    keep_weekly: String(policy.keep_weekly),
    keep_monthly: String(policy.keep_monthly),
    pitr_enabled: policy.pitr_enabled,
    pitr_window_days: String(policy.pitr_window_days),
    copy: copyTargetValue(policy),
    safety_snapshots: policy.safety_snapshots,
  }));
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const windowDays = Number(draft.pitr_window_days);
  const windowValid = Number.isInteger(windowDays) && windowDays >= 1 && windowDays <= 35;
  const options = copyOptions(placement.data ?? [], source);
  if (!options.some((o) => o.value === draft.copy)) {
    options.push({ value: draft.copy, label: "Current device (not available)", disabled: false });
  }

  const save = useMutation({
    mutationFn: () =>
      api.backups.updatePolicy(projectId, source.id, {
        enabled: draft.enabled,
        schedule: draft.schedule,
        keep_hourly: clampInt(draft.keep_hourly, 0, 1000),
        keep_daily: clampInt(draft.keep_daily, 0, 1000),
        keep_weekly: clampInt(draft.keep_weekly, 0, 1000),
        keep_monthly: clampInt(draft.keep_monthly, 0, 1000),
        pitr_enabled: draft.pitr_enabled,
        pitr_window_days: clampInt(draft.pitr_window_days, 1, 35),
        copy_to_primary: draft.copy === PRIMARY,
        copy_to_device_id: draft.copy === PRIMARY || draft.copy === NONE ? null : draft.copy,
        safety_snapshots: draft.safety_snapshots,
      }),
    onSuccess: (p) => {
      queryClient.setQueryData(qk.backupPolicy(projectId, source.id), p);
      void queryClient.invalidateQueries({ queryKey: qk.recoveryWindow(projectId, source.id) });
      toast.success("Backup policy saved.");
      onClose();
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (canEdit && windowValid) save.mutate();
  };

  const keepField = (key: "keep_hourly" | "keep_daily" | "keep_weekly" | "keep_monthly", label: string) => (
    <Field label={label}>
      {(id) => (
        <Input
          id={id}
          type="number"
          inputMode="numeric"
          min={0}
          max={1000}
          value={draft[key]}
          disabled={!canEdit}
          onChange={(e) => set(key, e.target.value)}
        />
      )}
    </Field>
  );

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Backup policy — ${source.name}`}
      description={`Last changed ${formatDateTime(policy.updated_at)}.`}
      dismissible={!save.isPending}
      footer={
        canEdit ? (
          <>
            <Button onClick={onClose} disabled={save.isPending}>
              Cancel
            </Button>
            <Button type="submit" form="policy-form" variant="primary" loading={save.isPending} disabled={!windowValid}>
              Save policy
            </Button>
          </>
        ) : (
          <Button onClick={onClose}>Close</Button>
        )
      }
    >
      <form id="policy-form" className="space-y-5" onSubmit={onSubmit}>
        {!canEdit && <Alert tone="info">Only project admins and owners can change the backup policy.</Alert>}

        <section className="space-y-3">
          <Checkbox
            checked={draft.enabled}
            disabled={!canEdit}
            onChange={(e) => set("enabled", e.target.checked)}
            label="Take versions automatically"
            description="Scheduled snapshots of the whole database."
          />
          <Field label="Schedule">
            {(id) => (
              <Select
                id={id}
                value={draft.schedule}
                disabled={!canEdit || !draft.enabled}
                onChange={(e) => set("schedule", e.target.value as BackupSchedule)}
              >
                {(Object.keys(SCHEDULE_LABELS) as BackupSchedule[]).map((s) => (
                  <option key={s} value={s}>
                    {SCHEDULE_LABELS[s]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </section>

        <section>
          <h3 className="text-sm font-medium">Keep</h3>
          <p className="mb-2 text-xs text-muted">
            The newest version in each of the most recent hours, days, weeks and months is kept. Pinned versions and
            safety versions from the last 30 days are never removed automatically.
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {keepField("keep_hourly", "Hourly")}
            {keepField("keep_daily", "Daily")}
            {keepField("keep_weekly", "Weekly")}
            {keepField("keep_monthly", "Monthly")}
          </div>
        </section>

        <section className="space-y-3">
          <Checkbox
            checked={draft.pitr_enabled}
            disabled={!canEdit}
            onChange={(e) => set("pitr_enabled", e.target.checked)}
            label="Point-in-time recovery"
            description="Continuously archives the database's change log so you can restore to any second."
          />
          <Field
            label="Recovery window (days)"
            hint="1–35 days."
            error={draft.pitr_enabled && !windowValid ? "Enter a whole number from 1 to 35." : undefined}
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                inputMode="numeric"
                min={1}
                max={35}
                value={draft.pitr_window_days}
                disabled={!canEdit || !draft.pitr_enabled}
                aria-invalid={draft.pitr_enabled && !windowValid}
                onChange={(e) => set("pitr_window_days", e.target.value)}
                className="sm:max-w-40"
              />
            )}
          </Field>
        </section>

        <section className="space-y-3">
          <Field
            label="Copy each version to"
            hint="Copies are encrypted; the storing device can't read them. Protects against losing the host PC."
          >
            {(id) => (
              <Select id={id} value={draft.copy} disabled={!canEdit} onChange={(e) => set("copy", e.target.value)}>
                {options.map((o) => (
                  <option key={o.value} value={o.value} disabled={o.disabled}>
                    {o.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Checkbox
            checked={draft.safety_snapshots}
            disabled={!canEdit}
            onChange={(e) => set("safety_snapshots", e.target.checked)}
            label="Safety versions"
            description="Take a version automatically before restores, drops, deletes and moves."
          />
        </section>

        <Alert tone="info" title="Disk usage">
          Versions are compressed and encrypted, but each one is a full copy of the database. More versions and a
          longer recovery window use more disk on the host (and on the copy target). Recovery logs grow with how much
          data changes.
        </Alert>

        {save.error && <ErrorAlert error={save.error} />}
      </form>
    </Dialog>
  );
}
