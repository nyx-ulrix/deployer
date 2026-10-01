import type {
  App,
  AppDetectDraft,
  AppInput,
  AppPatch,
  AppPreset,
  AppTarget,
  CloudTarget,
  DataSource,
  Deployment,
  DeploymentStatus,
  DeploymentTrigger,
  GitHubDispatch,
  GitHubRepo,
} from "../../api/types";
import type { BadgeTone } from "../../components/ui/Badge";

/** DNS-safe slug preview matching the API's rules: lowercase `[a-z0-9-]`, no leading/trailing `-`, max 63. */
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63)
    .replace(/-+$/, "");
}

export type EnvRow = { key: string; value: string };

/** Parse `.env` text: comments, blank lines, `export` prefixes, CRLF, single/double quotes, inline `# comments`. */
export function parseEnv(text: string): EnvRow[] {
  const rows: EnvRow[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/^export\s+/, "");
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_.-]*$/.test(key)) continue;
    let value = line.slice(eq + 1).trim();
    const q = value[0];
    if ((q === '"' || q === "'") && value.length >= 2 && value.lastIndexOf(q) > 0) {
      value = value.slice(1, value.lastIndexOf(q));
      if (q === '"') value = value.replace(/\\n/g, "\n").replace(/\\"/g, '"');
    } else {
      value = value.replace(/\s+#.*$/, "");
    }
    rows.push({ key, value });
  }
  return rows;
}

/** Rows → object; later duplicates win, blank keys are dropped. */
export function rowsToEnv(rows: EnvRow[]): Record<string, string> {
  const env: Record<string, string> = {};
  for (const r of rows) {
    const key = r.key.trim();
    if (key) env[key] = r.value;
  }
  return env;
}

export function envToRows(env: Record<string, string>): EnvRow[] {
  return Object.entries(env).map(([key, value]) => ({ key, value }));
}

export const DEPLOYMENT_STATUS: Record<DeploymentStatus, { label: string; tone: BadgeTone }> = {
  queued: { label: "Queued", tone: "neutral" },
  building: { label: "Building", tone: "info" },
  deploying: { label: "Deploying", tone: "info" },
  live: { label: "Live", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  superseded: { label: "Superseded", tone: "neutral" },
};

export const TRIGGER_LABELS: Record<DeploymentTrigger, string> = {
  manual: "Manual",
  webhook: "Push",
  rollback: "Rollback",
  github: "GitHub Actions",
};

/** docs/CLOUD.md "C3": the "Where it builds" choices, in plain words (the API's github_actions.LOCATIONS). */
export const BUILD_LOCATIONS = {
  pc: {
    label: "This PC",
    what: "Deployer clones and builds the app here, then uploads it to the cloud.",
    whenPcOff: "Pushes wait until the PC is on again; the app keeps serving.",
    cost: "Free.",
  },
  github: {
    label: "GitHub Actions",
    what: "Deployer adds a workflow file to the repository: GitHub builds every push on its own computers and uploads it to the cloud, signing in with a short-lived token instead of a stored key.",
    whenPcOff: "Pushes still deploy when this PC is off (the run shows up here once it is on).",
    cost: "GitHub bills the build minutes: free for public repositories; private ones use your GitHub account's free minutes (2,000 a month on the Free plan), then GitHub charges for more. The sign-in pieces Deployer adds to your cloud account are free.",
  },
} as const;

/** `POST .../deploy` answered that the app's GitHub Actions workflow was started (no deployment row yet). */
export function isGitHubDispatch(value: object): value is GitHubDispatch {
  return "github_actions" in value;
}

/** Queued, building or deploying: the deployment still changes, keep polling. */
export function isActive(status: string | undefined | null): boolean {
  return status === "queued" || status === "building" || status === "deploying";
}

/** Seconds spent building/deploying; runs against `now` while active, `null` before it starts. */
export function deploymentDuration(
  d: Pick<Deployment, "status" | "started_at" | "finished_at">,
  now = Date.now(),
): number | null {
  if (!d.started_at) return null;
  const start = new Date(d.started_at).getTime();
  const end = d.finished_at ? new Date(d.finished_at).getTime() : isActive(d.status) ? now : NaN;
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 1000);
}

/** Only a superseded deployment with an image can be re-run without a build. */
export function canRollback(d: Pick<Deployment, "status" | "image_tag">): boolean {
  return d.status === "superseded" && Boolean(d.image_tag);
}

export function shortSha(sha: string | null): string {
  return sha ? sha.slice(0, 7) : "—";
}

export type PresetField = "install_command" | "build_command" | "start_command" | "output_dir" | "container_port";

export const PRESETS: Record<
  AppPreset,
  { label: string; description: string; fields: PresetField[]; placeholders: Partial<Record<PresetField, string>> }
> = {
  static: {
    label: "Static site",
    description: "Build with npm, serve the output folder with nginx (SPA fallback to index.html).",
    fields: ["install_command", "build_command", "output_dir"],
    placeholders: { install_command: "npm ci", build_command: "npm run build", output_dir: "dist" },
  },
  node: {
    label: "Node.js",
    description: "node:22 — install, optional build, then a start command listening on $PORT (3000).",
    fields: ["install_command", "build_command", "start_command"],
    placeholders: { install_command: "npm ci", build_command: "npm run build", start_command: "npm start" },
  },
  python: {
    label: "Python",
    description: "python:3.12 — pip install -r requirements.txt, then your start command on port 8000.",
    fields: ["install_command", "start_command"],
    placeholders: { install_command: "pip install -r requirements.txt", start_command: "uvicorn main:app --host 0.0.0.0 --port 8000" },
  },
  dockerfile: {
    label: "Dockerfile",
    description: "Build the repository's own Dockerfile and run its CMD.",
    fields: ["container_port"],
    placeholders: { container_port: "8080" },
  },
};

export const FIELD_LABELS: Record<PresetField, { label: string; hint: string }> = {
  install_command: { label: "Install command", hint: "Leave blank for the default (npm ci, npm install without a lockfile, or pip install -r requirements.txt)." },
  build_command: { label: "Build command", hint: "Defaults to npm run build when package.json has one." },
  start_command: { label: "Start command", hint: "Runs inside the container; listen on $PORT." },
  output_dir: { label: "Output directory", hint: "Defaults to the first of dist, build, out, public." },
  container_port: { label: "Container port", hint: "The port the image's CMD listens on." },
};

/** Which per-preset fields the API requires (the rest have defaults). */
export const REQUIRED_FIELDS: Partial<Record<AppPreset, PresetField[]>> = {
  python: ["start_command"],
  dockerfile: ["container_port"],
};

export type AppDraft = {
  name: string;
  repo_url: string;
  branch: string;
  root_dir: string;
  preset: AppPreset;
  install_command: string;
  build_command: string;
  start_command: string;
  output_dir: string;
  container_port: string;
  private_repo: boolean;
  repo_token: string;
  api_key_id: string;
  database_access: boolean;
  /** New app only: clone + webhook through the creator's GitHub connection (no token field). */
  use_github_connection: boolean;
  /** docs/CLOUD.md: where it runs ("" connection = none picked yet). */
  target: AppTarget;
  cloud_connection_id: string;
  /** Where it runs now (new app: this PC): moving onto a cloud target or account needs `confirm_billing`. */
  saved_target: AppTarget;
  saved_connection_id: string;
  confirm_billing: boolean;
};

export function emptyDraft(app?: App): AppDraft {
  return {
    name: app?.name ?? "",
    repo_url: app?.repo_url ?? "",
    branch: app?.branch ?? "main",
    root_dir: app?.root_dir ?? ".",
    preset: app?.preset ?? "static",
    install_command: app?.install_command ?? "",
    build_command: app?.build_command ?? "",
    start_command: app?.start_command ?? "",
    output_dir: app?.output_dir ?? "",
    container_port: app?.container_port ? String(app.container_port) : "",
    private_repo: app?.has_repo_token ?? false,
    repo_token: "",
    api_key_id: app?.api_key_id ?? "",
    database_access: app?.database_access ?? false,
    use_github_connection: false,
    target: app?.target ?? "local",
    cloud_connection_id: app?.cloud_connection_id ?? "",
    saved_target: app?.target ?? "local",
    saved_connection_id: app?.cloud_connection_id ?? "",
    confirm_billing: false,
  };
}

/** docs/CLOUD.md: the draft puts the app on a cloud target or account it isn't billed to yet. */
export function movesToCloud(d: AppDraft): boolean {
  return d.target !== "local" && (d.target !== d.saved_target || d.cloud_connection_id !== d.saved_connection_id);
}

export function draftErrors(d: AppDraft): Partial<Record<keyof AppDraft, string>> {
  const errors: Partial<Record<keyof AppDraft, string>> = {};
  if (!d.name.trim()) errors.name = "Name is required.";
  else if (!slugify(d.name)) errors.name = "Name needs at least one letter or digit.";
  if (!/^https:\/\/\S+$/.test(d.repo_url.trim())) errors.repo_url = "Use an https:// repository URL.";
  if (!d.branch.trim()) errors.branch = "Branch is required.";
  for (const f of REQUIRED_FIELDS[d.preset] ?? []) if (!d[f].trim()) errors[f] = "Required for this preset.";
  if (!targetFits(d.target, d.preset)) errors.target = "This target serves static files: pick the Static site preset or a full-app target.";
  else if (d.target !== "local" && !d.cloud_connection_id) errors.target = "Pick the cloud account to deploy to.";
  else if (movesToCloud(d) && !d.confirm_billing) errors.target = "Tick the box to confirm the cloud account pays for this.";
  if (d.preset === "dockerfile" && d.container_port.trim()) {
    const n = Number(d.container_port);
    if (!Number.isInteger(n) || n < 1 || n > 65535) errors.container_port = "Port must be 1–65535.";
  }
  return errors;
}

const blank = (s: string) => (s.trim() ? s.trim() : null);

/** Draft → `POST /apps` body (fields outside the preset become null so the API applies its defaults). */
export function draftToInput(d: AppDraft, env: EnvRow[]): AppInput {
  const fields = new Set<PresetField>(PRESETS[d.preset].fields);
  const body: AppInput = {
    name: d.name.trim(),
    repo_url: d.repo_url.trim(),
    branch: d.branch.trim() || "main",
    root_dir: d.root_dir.trim() || ".",
    preset: d.preset,
    install_command: fields.has("install_command") ? blank(d.install_command) : null,
    build_command: fields.has("build_command") ? blank(d.build_command) : null,
    start_command: fields.has("start_command") ? blank(d.start_command) : null,
    output_dir: fields.has("output_dir") ? blank(d.output_dir) : null,
    container_port: fields.has("container_port") && d.container_port.trim() ? Number(d.container_port) : null,
    env: rowsToEnv(env),
    // Cloud targets never get this PC's data API key or databases (docs/CLOUD.md); on App Runner,
    // database access means the project's AWS databases instead.
    api_key_id: d.target === "local" ? d.api_key_id || null : null,
    database_access: (d.target === "local" || CLOUD_DATABASE_TARGETS.includes(d.target)) && d.database_access,
    target: d.target,
    cloud_connection_id: d.target === "local" ? null : d.cloud_connection_id || null,
  };
  if (movesToCloud(d)) body.confirm_billing = d.confirm_billing;
  if (d.use_github_connection) body.use_github_connection = true;
  else if (d.private_repo && d.repo_token.trim()) body.repo_token = d.repo_token.trim();
  return body;
}

/** Draft → `PATCH /apps/{id}` body (env is edited separately; the token only when typed or cleared). */
export function draftToPatch(d: AppDraft, app: App): AppPatch {
  const { env: _env, repo_token: _t, use_github_connection: _c, ...rest } = draftToInput(d, []);
  const patch: AppPatch = rest;
  if (d.private_repo && d.repo_token.trim()) patch.repo_token = d.repo_token.trim();
  else if (!d.private_repo && app.has_repo_token) patch.repo_token = null;
  return patch;
}

/** Cloud targets where "database access" means the project's databases in the same cloud account (docs/CLOUD.md "C2"). */
export const CLOUD_DATABASE_TARGETS: AppTarget[] = ["aws_app", "firebase_app"];

/** Variable names "database access" injects for a source (mirrors `deployments.database_env`). Values are never shown. */
export function databaseEnvNames(source: Pick<DataSource, "name" | "kind"> & { engine?: string }): string[] {
  const prefix = `DEPLOYER_DB_${source.name.toUpperCase().replace(/[^A-Z0-9]/g, "_")}_`;
  const suffixes =
    source.engine === "dynamodb" // docs/CLOUD.md "C2-2": table names and region; the app's IAM role grants access
      ? ["TABLE", "TABLES", "REGION", "DATABASE"]
      : source.engine === "firestore" // "C2-3": the Google project and database id; Cloud Run signs in as itself
        ? ["PROJECT", "DATABASE"]
        : source.engine === "firebase_rtdb" // "C2-4": also the database URL the Firebase Admin SDK takes
          ? ["PROJECT", "URL", "DATABASE"]
        : source.kind === "sql"
        ? ["HOST", "PORT", "USER", "PASSWORD", "DATABASE", "URL"]
        : ["URL", "DATABASE"];
  return suffixes.map((s) => prefix + s);
}

/** Sources an app with database access can reach: managed, on the main server. */
export function reachableSources<T extends Pick<DataSource, "mode" | "device_id">>(sources: T[]): T[] {
  return sources.filter((s) => s.mode === "managed" && !s.device_id);
}

/** docs/CLOUD.md "C2": the AWS databases an App Runner app on `connectionId` gets (same account). */
export function cloudSourcesFor<T extends Pick<DataSource, "cloud">>(sources: T[], connectionId: string): T[] {
  return sources.filter((s) => s.cloud && s.cloud.connection_id === connectionId);
}

// --- "Connect a Git repository" (docs/DEPLOYMENTS.md) -------------------------------------------

/** Repositories matching `q` (name or description, case-insensitive), most recently pushed first. */
export function filterRepos(repos: GitHubRepo[], q: string): GitHubRepo[] {
  const needle = q.trim().toLowerCase();
  return repos
    .filter((r) => !needle || `${r.full_name} ${r.description ?? ""}`.toLowerCase().includes(needle))
    .sort((a, b) => (b.pushed_at ?? "").localeCompare(a.pushed_at ?? ""));
}

/** Detected draft → form draft. `viaConnection`: picked from the connected account's list (no token field). */
export function draftFromDetect(d: AppDetectDraft, viaConnection: boolean, isAdmin: boolean): AppDraft {
  return {
    ...emptyDraft(),
    name: d.name,
    repo_url: d.repo_url,
    branch: d.branch || "main",
    root_dir: d.root_dir || ".",
    preset: d.preset,
    install_command: d.install_command ?? "",
    build_command: d.build_command ?? "",
    start_command: d.start_command ?? "",
    output_dir: d.output_dir ?? "",
    container_port: d.container_port ? String(d.container_port) : "",
    use_github_connection: viaConnection,
    private_repo: !viaConnection && d.private === true,
    database_access: isAdmin && d.database_access_suggested,
  };
}

/** Env rows with every detected key present (empty = still to fill in); values already typed are kept. */
export function seedEnv(keys: string[], rows: EnvRow[]): EnvRow[] {
  const have = new Set(rows.map((r) => r.key));
  return [...rows, ...keys.filter((k) => !have.has(k)).map((key) => ({ key, value: "" }))];
}

/** "Flask app (requirements.txt, app/__init__.py)"; null when nothing was recognised. */
export function detectedSummary(d: Pick<AppDetectDraft, "detected">): string | null {
  return d.detected.length ? d.detected.map((x) => `${x.what} (${x.from})`).join("; ") : null;
}

/** Keys the repository's .env example lists that still have no value. */
export function unfilledKeys(keys: string[], rows: EnvRow[]): string[] {
  const filled = new Set(rows.filter((r) => r.value.trim()).map((r) => r.key.trim()));
  return keys.filter((k) => !filled.has(k));
}

/** "Also running on 2 co-host PCs" (docs/COHOSTING.md); null when no copy is live. */
export function cohostSummary(app: Pick<App, "cohost" | "replicas">): string | null {
  const live = app.cohost ? (app.replicas ?? []).filter((r) => r.status === "live").length : 0;
  return live ? `Also running on ${live} co-host PC${live === 1 ? "" : "s"}` : null;
}

// --- Cloud hosting targets (docs/CLOUD.md) --------------------------------------------------------

export const TARGET_SHORT: Record<AppTarget, string> = {
  local: "This PC",
  aws_static: "AWS S3 + CloudFront",
  aws_app: "AWS App Runner",
  firebase_hosting: "Firebase Hosting",
  firebase_app: "Firebase + Cloud Run",
};

const STATIC_TARGETS: AppTarget[] = ["aws_static", "firebase_hosting"];

/** Static targets serve files only: they need the static preset. */
export function targetFits(target: AppTarget, preset: AppPreset): boolean {
  return !STATIC_TARGETS.includes(target) || preset === "static";
}

/** The cloud target to suggest for a preset: static sites → a CDN, servers → a container service; among the
 * targets this project has an account for. `local` when there is none. */
export function recommendedTarget(preset: AppPreset, targets: Pick<CloudTarget, "id" | "available">[]): AppTarget {
  const order: AppTarget[] = preset === "static" ? ["firebase_hosting", "aws_static"] : ["aws_app", "firebase_app"];
  return order.find((t) => targets.some((x) => x.id === t && x.available)) ?? "local";
}
