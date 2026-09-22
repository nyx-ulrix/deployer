import { useQuery } from "@tanstack/react-query";
import { api, qk } from "../../api/endpoints";
import type { AppPreset } from "../../api/types";
import { Checkbox, Field, Input, Select } from "../../components/ui/Input";
import { FIELD_LABELS, PRESETS, REQUIRED_FIELDS, slugify, type AppDraft } from "./deploys";

const PRESET_ORDER: AppPreset[] = ["static", "node", "python", "dockerfile"];

/** All app fields except env (edited separately); shared by the New app dialog and Settings. */
export function AppFormFields({
  projectId,
  draft,
  errors,
  onChange,
  isAdmin,
  disabled = false,
  hasRepoToken = false,
  showSlug = true,
}: {
  projectId: string;
  draft: AppDraft;
  errors: Partial<Record<keyof AppDraft, string>>;
  onChange: (patch: Partial<AppDraft>) => void;
  isAdmin: boolean;
  disabled?: boolean;
  /** Settings: a token is stored, so the field is optional ("leave blank to keep"). */
  hasRepoToken?: boolean;
  showSlug?: boolean;
}) {
  const keys = useQuery({ queryKey: qk.apiKeys(projectId), queryFn: () => api.apiKeys.list(projectId), enabled: isAdmin });
  const preset = PRESETS[draft.preset];
  const required = new Set(REQUIRED_FIELDS[draft.preset] ?? []);
  const slug = slugify(draft.name);

  return (
    <div className="space-y-4">
      <Field
        label="Name"
        error={errors.name}
        hint={showSlug ? (slug ? <>Slug: <code className="font-mono">{slug}</code> — used for container and image names.</> : "Letters and digits become the slug.") : undefined}
      >
        {(id) => <Input id={id} value={draft.name} onChange={(e) => onChange({ name: e.target.value })} placeholder="My shop" disabled={disabled} data-autofocus />}
      </Field>

      <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
        <Field label="Repository URL" error={errors.repo_url} hint="A GitHub https:// URL; SSH URLs are not supported.">
          {(id) => (
            <Input id={id} value={draft.repo_url} onChange={(e) => onChange({ repo_url: e.target.value })} placeholder="https://github.com/you/repo" disabled={disabled} spellCheck={false} />
          )}
        </Field>
        <Field label="Branch" error={errors.branch}>
          {(id) => <Input id={id} value={draft.branch} onChange={(e) => onChange({ branch: e.target.value })} disabled={disabled} spellCheck={false} />}
        </Field>
      </div>

      <Checkbox
        label="Private repository"
        description="Deployer clones with a GitHub fine-grained token (Repository permissions → Contents: Read). It is stored encrypted and never logged."
        checked={draft.private_repo}
        onChange={(e) => onChange({ private_repo: e.target.checked })}
        disabled={disabled}
      />
      {draft.private_repo && (
        <Field label="GitHub token" optional={hasRepoToken} hint={hasRepoToken ? "A token is stored. Leave blank to keep it." : undefined}>
          {(id) => (
            <Input id={id} type="password" value={draft.repo_token} onChange={(e) => onChange({ repo_token: e.target.value })} placeholder="github_pat_…" autoComplete="off" disabled={disabled} />
          )}
        </Field>
      )}

      <Field label="Preset" hint={preset.description}>
        {(id) => (
          <Select id={id} value={draft.preset} onChange={(e) => onChange({ preset: e.target.value as AppPreset })} disabled={disabled}>
            {PRESET_ORDER.map((p) => (
              <option key={p} value={p}>
                {PRESETS[p].label}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        {preset.fields.map((f) => (
          <Field key={f} label={FIELD_LABELS[f].label} optional={!required.has(f)} error={errors[f]} hint={FIELD_LABELS[f].hint}>
            {(id) => (
              <Input
                id={id}
                value={draft[f]}
                onChange={(e) => onChange({ [f]: e.target.value })}
                placeholder={preset.placeholders[f]}
                inputMode={f === "container_port" ? "numeric" : undefined}
                className="font-mono text-sm"
                spellCheck={false}
                disabled={disabled}
              />
            )}
          </Field>
        ))}
        <Field label="Root directory" optional hint="Folder inside the repository to build from (monorepos).">
          {(id) => <Input id={id} value={draft.root_dir} onChange={(e) => onChange({ root_dir: e.target.value })} placeholder="." className="font-mono text-sm" spellCheck={false} disabled={disabled} />}
        </Field>
      </div>

      {isAdmin ? (
        <Field label="Attach an API key" optional hint="Injected as DEPLOYER_API_KEY (with DEPLOYER_URL and DEPLOYER_PROJECT_ID) so the app can call this project's data API.">
          {(id) => (
            <Select id={id} value={draft.api_key_id} onChange={(e) => onChange({ api_key_id: e.target.value })} disabled={disabled || keys.isPending}>
              <option value="">None</option>
              {(keys.data ?? [])
                .filter((k) => k.revealable && !k.revoked_at)
                .map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name} ({k.role})
                  </option>
                ))}
            </Select>
          )}
        </Field>
      ) : (
        <p className="text-xs text-muted">Project admins can attach an API key so the app gets DEPLOYER_API_KEY at runtime.</p>
      )}
    </div>
  );
}
