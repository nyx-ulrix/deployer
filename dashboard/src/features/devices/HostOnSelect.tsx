import type { ManagedEngine, PlacementOption } from "../../api/types";
import { Field, Select } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { errorMessage } from "../../api/client";
import { placementDisplay } from "./eligibility";

/**
 * "Host on" select fed by GET /projects/{id}/placement-options. Ineligible options stay visible but
 * disabled, with the reason in the label (native <option> can't show tooltips on touch devices).
 */
export function HostOnSelect({
  options,
  engine,
  value,
  onChange,
  loading = false,
  error,
  label = "Host on",
  hint,
  excludeDeviceId,
}: {
  options: readonly PlacementOption[] | undefined;
  engine: ManagedEngine | null;
  value: string;
  onChange: (value: string) => void;
  loading?: boolean;
  error?: unknown;
  label?: string;
  hint?: string;
  /** Hide the current host when choosing a move target (`""` = main server). */
  excludeDeviceId?: string;
}) {
  const displays = (options ?? [])
    .map((o) => placementDisplay(o, engine))
    .filter((d) => excludeDeviceId === undefined || d.value !== excludeDeviceId);
  const selected = displays.find((d) => d.value === value);
  return (
    <Field
      label={label}
      error={error ? `Couldn't load hosts: ${errorMessage(error)}` : undefined}
      hint={
        selected?.reason ??
        hint ??
        "Where the database files live. Host devices are other PCs attached to this Deployer."
      }
    >
      {(id) =>
        loading ? (
          <div className="flex h-10 items-center gap-2 text-sm text-muted">
            <Spinner className="size-4" /> Loading hosts…
          </div>
        ) : (
          <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={displays.length === 0}>
            {displays.map((d) => (
              <option key={d.value || "main"} value={d.value} disabled={d.disabled}>
                {d.label}
              </option>
            ))}
          </Select>
        )
      }
    </Field>
  );
}
