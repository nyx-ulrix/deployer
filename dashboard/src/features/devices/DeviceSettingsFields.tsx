import type { DeviceRole } from "../../api/types";
import { useProjects } from "../../api/hooks";
import { Checkbox, Field, Input } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { ErrorAlert } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { hasRole, ROLE_LABELS as PROJECT_ROLE_LABELS } from "../../lib/roles";
import { ROLE_HINTS, ROLE_LABELS, SHARING_LABELS, type DeviceSettingsValue } from "./eligibility";

/** Name, roles and sharing controls shared by the approval page and the edit dialog. */
export function DeviceSettingsFields({
  value,
  onChange,
}: {
  value: DeviceSettingsValue;
  onChange: (next: DeviceSettingsValue) => void;
}) {
  const projects = useProjects();
  const eligibleProjects = (projects.data ?? []).filter((p) => hasRole(p.my_role, "developer"));
  const set = (patch: Partial<DeviceSettingsValue>) => onChange({ ...value, ...patch });
  const toggleRole = (role: DeviceRole, on: boolean) =>
    set({ roles: on ? [...new Set([...value.roles, role])] : value.roles.filter((r) => r !== role) });
  const toggleProject = (id: string, on: boolean) =>
    set({ project_ids: on ? [...new Set([...value.project_ids, id])] : value.project_ids.filter((p) => p !== id) });

  return (
    <div className="space-y-4">
      <Field label="Device name" hint="Shown in “Host on” lists, e.g. “Office PC”.">
        {(id) => (
          <Input id={id} required maxLength={80} value={value.name} onChange={(e) => set({ name: e.target.value })} />
        )}
      </Field>

      <fieldset className="space-y-2.5">
        <legend className="mb-2 text-sm font-medium">Roles</legend>
        {(["database_host", "backup_storage"] as const).map((role) => (
          <Checkbox
            key={role}
            checked={value.roles.includes(role)}
            onChange={(e) => toggleRole(role, e.target.checked)}
            label={ROLE_LABELS[role]}
            description={ROLE_HINTS[role]}
          />
        ))}
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-medium">Which projects can use it</legend>
        {(["my_projects", "selected"] as const).map((mode) => (
          <label
            key={mode}
            className={cn(
              "flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 text-sm",
              value.sharing_mode === mode ? "border-accent bg-accent-soft/40" : "border-border hover:bg-surface-2",
            )}
          >
            <input
              type="radio"
              name="sharing_mode"
              className="mt-0.5 size-4 accent-[var(--accent)]"
              checked={value.sharing_mode === mode}
              onChange={() => set({ sharing_mode: mode })}
            />
            <span>
              <span className="font-medium">{SHARING_LABELS[mode]}</span>
              <span className="mt-0.5 block text-xs text-muted">
                {mode === "my_projects"
                  ? "Projects you own or administer can place databases here."
                  : "Only the projects you pick below."}
              </span>
            </span>
          </label>
        ))}
        {value.sharing_mode === "selected" && (
          <div className="rounded-xl border border-border p-3">
            {projects.isPending ? (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Spinner className="size-4" /> Loading projects…
              </div>
            ) : projects.isError ? (
              <ErrorAlert error={projects.error} />
            ) : eligibleProjects.length === 0 ? (
              <p className="text-sm text-muted">You aren't a developer or above in any project yet.</p>
            ) : (
              <div className="max-h-56 space-y-2 overflow-y-auto">
                {eligibleProjects.map((p) => (
                  <Checkbox
                    key={p.id}
                    checked={value.project_ids.includes(p.id)}
                    onChange={(e) => toggleProject(p.id, e.target.checked)}
                    label={p.name}
                    description={`Your role: ${PROJECT_ROLE_LABELS[p.my_role]}`}
                  />
                ))}
              </div>
            )}
            {value.project_ids.length === 0 && eligibleProjects.length > 0 && (
              <p className="mt-2 text-xs text-warning">Pick at least one project.</p>
            )}
          </div>
        )}
      </fieldset>
    </div>
  );
}
