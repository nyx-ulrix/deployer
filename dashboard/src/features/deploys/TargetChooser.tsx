import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Cloud, Monitor } from "lucide-react";
import { api, qk } from "../../api/endpoints";
import type { CloudTarget } from "../../api/types";
import { Badge } from "../../components/ui/Badge";
import { Field, Select } from "../../components/ui/Input";
import { cn } from "../../lib/cn";
import { recommendedTarget, targetFits, type AppDraft } from "./deploys";

/**
 * docs/CLOUD.md "Where should this run?": this PC or one of the cloud targets, each explained in plain words
 * (what it's for, that it keeps running with the PC off, what it costs), with the recommended one for the preset
 * and the cloud account to use. Only project admins can change it (cloud targets are billed to that account).
 */
export function TargetChooser({
  projectId,
  draft,
  onChange,
  isAdmin,
  error,
  disabled = false,
}: {
  projectId: string;
  draft: AppDraft;
  onChange: (patch: Partial<AppDraft>) => void;
  isAdmin: boolean;
  error?: string;
  disabled?: boolean;
}) {
  const targets = useQuery({ queryKey: qk.cloudTargets(projectId), queryFn: () => api.cloud.targets(projectId) });
  const connections = useQuery({
    queryKey: qk.projectCloudConnections(projectId),
    queryFn: () => api.cloud.projectConnections(projectId),
    enabled: isAdmin,
  });
  const list = targets.data ?? [];
  const recommended = recommendedTarget(draft.preset, list);
  const selected = list.find((t) => t.id === draft.target);
  const usable = (connections.data ?? []).filter((c) => c.provider === selected?.provider);
  const locked = disabled || !isAdmin;

  const pick = (t: CloudTarget) => {
    const first = (connections.data ?? []).find((c) => c.provider === t.provider);
    onChange({ target: t.id, cloud_connection_id: t.provider ? (first?.id ?? "") : "" });
  };

  return (
    <fieldset className="space-y-2" disabled={locked}>
      <legend className="mb-1 text-sm font-medium">Where should this run?</legend>
      {!isAdmin && (
        <p className="text-xs text-muted">Only project admins can change where an app runs (cloud targets are billed to a cloud account).</p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        {list.map((t) => {
          const fits = targetFits(t.id, draft.preset);
          const blocked = !fits || !t.available;
          const active = draft.target === t.id;
          return (
            <label
              key={t.id}
              className={cn(
                "flex cursor-pointer flex-col gap-1 rounded-xl border p-3 text-sm",
                active ? "border-accent bg-accent-soft/40" : "border-border bg-surface",
                (blocked || locked) && !active && "cursor-not-allowed opacity-60",
              )}
            >
              <span className="flex flex-wrap items-center gap-2">
                <input
                  type="radio"
                  name="target"
                  className="accent-[var(--accent)]"
                  checked={active}
                  disabled={(blocked && !active) || locked}
                  onChange={() => pick(t)}
                />
                {t.provider ? <Cloud className="size-4 text-muted" /> : <Monitor className="size-4 text-muted" />}
                <span className="font-medium">{t.label}</span>
                {t.id === recommended && t.id !== "local" && <Badge tone="accent">Recommended</Badge>}
              </span>
              <span className="text-xs text-muted">{t.for}</span>
              <span className={cn("text-xs", t.provider ? "text-success" : "text-muted")}>{t.when_pc_off}</span>
              <span className="text-xs text-muted">
                <span className="text-fg">Cost:</span> {t.cost}
              </span>
              {!fits && <span className="text-xs text-warning">Needs the Static site preset.</span>}
              {fits && !t.available && (
                <span className="text-xs text-warning">
                  No {t.provider === "aws" ? "AWS" : "Firebase"} account connected yet — the instance owner adds one under{" "}
                  <Link to="/settings/cloud" className="underline">
                    Settings → Cloud accounts
                  </Link>
                  .
                </span>
              )}
            </label>
          );
        })}
      </div>
      {selected?.provider && (
        <>
          {isAdmin && (
            <Field label="Cloud account" error={error}>
              {(id) => (
                <Select id={id} value={draft.cloud_connection_id} onChange={(e) => onChange({ cloud_connection_id: e.target.value })}>
                  <option value="">Choose…</option>
                  {usable.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.account.account_id ?? c.account.project_id}
                      {c.account.region ? `, ${c.account.region}` : ""})
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          )}
          <p className="text-xs text-muted">
            Built on this PC, then served entirely from the cloud: it keeps running when this PC is off. The app gets only its own
            environment variables — no <code className="font-mono">DEPLOYER_URL</code>, <code className="font-mono">DEPLOYER_API_KEY</code>{" "}
            or <code className="font-mono">DEPLOYER_DB_*</code>, because those point at this PC. Deploying again, rollbacks and settings
            still need this PC on.
          </p>
        </>
      )}
      {!selected?.provider && error && <p className="text-xs text-danger">{error}</p>}
    </fieldset>
  );
}

