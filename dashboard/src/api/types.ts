// Types copied from docs/API.md (the HTTP contract). Keep in sync with the API.

export type ProviderName = "google" | "github";

export type User = {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  is_instance_owner: boolean;
  has_password: boolean;
  created_at: string;
  identities: Identity[];
};

export type Identity = {
  id: string;
  provider: ProviderName;
  provider_email: string | null;
  provider_username: string | null;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
};

export type Role = "owner" | "admin" | "developer" | "viewer";

export type Project = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  owner_id: string;
  my_role: Role;
  created_at: string;
  updated_at: string;
  data_source_counts: { sql: number; nosql: number };
};

export type Member = {
  user_id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  role: Role;
  created_at: string;
};

export type Invite = {
  id: string;
  email: string | null;
  role: Exclude<Role, "owner">;
  invited_by: string;
  expires_at: string;
  created_at: string;
};

export type DataSourceKind = "sql" | "nosql";
export type DataSourceEngine = "mariadb" | "mysql" | "postgresql" | "mongodb";

export type DataSource = {
  id: string;
  project_id: string;
  name: string;
  kind: DataSourceKind;
  engine: DataSourceEngine;
  mode: "managed" | "external";
  database_name: string;
  status: "ok" | "error" | "unknown";
  status_message: string | null;
  last_checked_at: string | null;
  display: { host: string | null; port: number | null; username: string | null; tls: boolean };
  created_at: string;
  /** Host device (docs/DEVICES.md). `null`/absent = main server. */
  device_id?: string | null;
  /** Name of the host device (DEVICES.md); the dashboard looks the device up itself if absent. */
  device_name?: string | null;
};

export type ApiKeyRole = "anon" | "service";

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  role: ApiKeyRole;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  /** False for keys created before Deployer kept secrets: they can't be revealed, only replaced. */
  revealable: boolean;
};

/** `GET /projects/{pid}/api-keys/{id}/config`: a ready-to-use client config (docs/DATA_API.md). */
export type ApiKeyConfig = {
  deployer: {
    url: string;
    project_id: string;
    project: string;
    role: ApiKeyRole;
    api_key: string;
    data_sources: { id: string; name: string; kind: DataSourceKind; engine: string }[];
    endpoints: { rows: string; documents: string; query: string; schema: string };
    generated_at: string;
  };
};

// ---- Health & setup ----

export type Health = {
  status: "ok";
  version: string;
  services: { mariadb: boolean; mongodb: boolean; redis: boolean };
};

export type SetupStatus = {
  initialized: boolean;
  version: string;
  public_url: string;
  providers: { google: boolean; github: boolean };
  allow_signup: boolean;
  /** docs/DEVICES.md: "host" when this installation is attached to another Deployer. */
  device_mode?: "standalone" | "host";
};

export type ImportSummary = {
  users?: number;
  projects?: number;
  data_sources?: number;
  rows?: number;
  documents?: number;
};

export type SetupImportResponse = { ok: true; summary: ImportSummary };

// ---- Auth ----

export type ProvidersResponse = { google: boolean; github: boolean; allow_signup: boolean };

export type OAuthErrorCode =
  | "oauth_failed"
  | "oauth_state_invalid"
  | "account_exists_link_required"
  | "identity_in_use"
  | "signup_disabled"
  | "provider_not_configured"
  | "email_not_verified";

// ---- Instance ----

export type ProviderSettings = {
  client_id: string | null;
  secret_set: boolean;
  configured: boolean;
  callback_url: string;
};

export type InstanceSettings = {
  public_url: string;
  allow_signup: boolean;
  google: ProviderSettings;
  github: ProviderSettings;
};

/** Empty string clears a value. */
export type InstanceSettingsUpdate = {
  public_url?: string;
  allow_signup?: boolean;
  google_client_id?: string;
  google_client_secret?: string;
  github_client_id?: string;
  github_client_secret?: string;
};

// ---- Projects ----

export type ProjectCreate = {
  name: string;
  description?: string;
  /** `device_id` (DEVICES.md): where the managed databases are placed; null = main server. */
  provision?: { sql: boolean; nosql: boolean; device_id?: string | null };
};

export type ProjectsImportResponse = { ok: true; projects: Project[]; summary: ImportSummary };

// ---- Invites ----

export type InviteRole = Exclude<Role, "owner">;
export type InviteCreate = { email?: string; role: InviteRole; expires_in_days?: number };
export type InviteCreateResponse = { invite: Invite; invite_url: string };
export type InvitePreview = {
  project_name: string;
  role: Role;
  invited_by_name: string | null;
  email: string | null;
  expires_at: string;
};

// ---- API keys ----

export type ApiKeyCreateResponse = { api_key: ApiKey; secret: string };

// ---- Data sources ----

export type SqlExternalEngine = "mariadb" | "mysql" | "postgresql";

export type DataSourceInput =
  | { kind: "sql"; mode: "managed"; engine: "mariadb"; name: string; device_id?: string | null }
  | { kind: "nosql"; mode: "managed"; engine: "mongodb"; name: string; device_id?: string | null }
  | {
      kind: "sql";
      mode: "external";
      engine: SqlExternalEngine;
      name: string;
      config: {
        host: string;
        port?: number;
        username: string;
        password: string;
        database: string;
        tls?: boolean;
      };
    }
  | {
      kind: "nosql";
      mode: "external";
      engine: "mongodb";
      name: string;
      config: { uri: string; database: string };
    };

export type ConnectionTestResult = { ok: boolean; message: string; server_version: string | null };

export type ConnectionDetails = {
  uri: string;
  host: string;
  port: number | null;
  username: string;
  password: string;
  database: string;
  external_hint?: string | null;
};

// ---- Schema ----

export type ProjectSchema = {
  sources: SourceSchema[];
  links: SchemaLink[];
  conventions: ConventionIssue[];
  generated_at: string;
};

export type SourceSchema = {
  source_id: string;
  name: string;
  kind: DataSourceKind;
  engine: string;
  status: "ok" | "error";
  error: string | null;
  entities: Entity[];
  relationships: Relationship[];
};

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject;
export type JsonObject = { [key: string]: JsonValue };

export type EntityIndex = { name: string; fields: string[]; unique: boolean };

export type Entity = {
  name: string;
  type: "table" | "collection";
  row_count: number | null;
  fields: Field[];
  indexes: EntityIndex[];
  validator: JsonObject | null; // Mongo $jsonSchema, if any
};

export type Field = {
  name: string; // nested Mongo fields use dot paths: "address.city"
  data_type: string;
  nullable: boolean;
  default: string | null;
  primary_key: boolean;
  unique: boolean;
  indexed: boolean;
  foreign_key: { entity: string; field: string } | null;
  occurrence: number | null; // Mongo only: 0..1 share of sampled docs containing the field
};

export type RelationshipCardinality = "one_to_one" | "many_to_one";

export type Relationship = {
  from_entity: string;
  from_fields: string[]; // the "many" / referencing side
  to_entity: string;
  to_fields: string[];
  cardinality: RelationshipCardinality;
  origin: "foreign_key" | "inferred";
};

export type LinkCardinality = "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many";

export type SchemaLink = {
  id: string;
  from_source_id: string;
  from_entity: string;
  from_field: string;
  to_source_id: string;
  to_entity: string;
  to_field: string;
  cardinality: LinkCardinality;
  note: string | null;
  created_at: string;
};

export type SchemaLinkCreate = Omit<SchemaLink, "id" | "created_at">;

export type ConventionIssue = {
  rule: string; // e.g. "N1" - see docs/CONVENTIONS.md
  severity: "warning" | "info";
  source_id: string | null;
  entity: string | null;
  field: string | null;
  message: string;
};

export type ForeignKeyAction = "cascade" | "set null" | "restrict";

export type ColumnSpec = {
  name: string;
  type: string;
  nullable?: boolean;
  default?: string | null;
  primary_key?: boolean;
  unique?: boolean;
  auto_increment?: boolean;
  references?: { table: string; column: string; on_delete?: ForeignKeyAction };
};

export type TableSpec = {
  name: string;
  columns: ColumnSpec[];
  timestamps?: boolean; // adds created_at / updated_at
};

export type SchemaExportFormat = "sql" | "mongo" | "bundle";

// ---- Data browser ----

export type RowsResponse = {
  columns: string[];
  primary_key: string[];
  rows: JsonObject[];
  total: number;
};

export type DocumentsResponse = { documents: JsonObject[]; total: number };

export type Ok = { ok: true };

export type ApiErrorBody = {
  error: { code: string; message: string; details?: Record<string, unknown> };
};

// ---- Host devices (docs/DEVICES.md) ----
// Shapes follow DEVICES.md (primary-side management API, data model and device-local API). Fields
// that older API versions may omit are optional so the dashboard stays tolerant.

export type DeviceRole = "database_host" | "backup_storage";
export type DeviceSharingMode = "my_projects" | "selected";
export type ManagedEngine = "mariadb" | "mongodb";

export type EngineAvailability = Partial<Record<ManagedEngine, boolean>>;

export type DeviceMetrics = {
  cpu_percent?: number | null;
  memory_used_bytes?: number | null;
  memory_total_bytes?: number | null;
  disk_free_bytes?: number | null;
  disk_total_bytes?: number | null;
  uptime_seconds?: number | null;
  engines?: EngineAvailability;
  version?: string | null;
};

export type DeviceCapabilities = {
  engines?: EngineAvailability;
  avx?: boolean;
  [key: string]: unknown;
};

export type Device = {
  id: string;
  name: string;
  owner_id: string;
  owner_email?: string | null;
  owner_name?: string | null;
  status: "active" | "disabled";
  roles: DeviceRole[];
  sharing_mode: DeviceSharingMode;
  /** Projects granted when `sharing_mode = "selected"`. */
  project_ids?: string[];
  hostname: string | null;
  os: string | null;
  version: string | null;
  capabilities: DeviceCapabilities | null;
  metrics: DeviceMetrics | null;
  online?: boolean;
  last_seen_at: string | null;
  created_at: string;
  hosted_sources_count?: number;
};

export type DeviceUpdate = {
  name?: string;
  roles?: DeviceRole[];
  sharing_mode?: DeviceSharingMode;
  project_ids?: string[];
  status?: "active" | "disabled";
};

export type DeviceEnrollmentStatus = "pending" | "approved" | "denied" | "expired" | "consumed";

export type DeviceEnrollment = {
  id: string;
  user_code: string;
  name: string;
  hostname: string | null;
  os: string | null;
  version: string | null;
  capabilities: DeviceCapabilities | null;
  status: DeviceEnrollmentStatus;
  expires_at: string;
  created_at: string;
};

export type DeviceApproval = {
  user_code: string;
  name: string;
  roles: DeviceRole[];
  sharing_mode: DeviceSharingMode;
  project_ids: string[];
};

export type PlacementOption = {
  /** `null` = main server. */
  device_id: string | null;
  name: string;
  online: boolean;
  eligible: boolean;
  reason?: string | null;
  disk_free_bytes?: number | null;
  engines?: EngineAvailability;
  roles?: DeviceRole[];
};

// Device-local API (served by this installation when it is, or becomes, a host device).

export type LocalHostedSource = {
  database_name: string;
  kind: DataSourceKind;
  size_bytes: number | null;
  last_backup_at?: string | null;
};

export type LocalDeviceStatus = {
  mode: "standalone" | "host";
  primary_url: string | null;
  device_id: string | null;
  device_name: string | null;
  connected: boolean;
  last_error: string | null;
  last_connected_at: string | null;
  hosted_sources: LocalHostedSource[];
  metrics: DeviceMetrics | null;
};

export type EnrollStartResponse = { user_code: string; verification_url: string; expires_in: number };

export type EnrollState = "idle" | "pending" | "approved" | "denied" | "expired" | "error";

export type EnrollStatus = { status: EnrollState; message: string | null };

// ---- Jobs, backups & recovery (docs/BACKUPS.md) ----

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type Job = {
  id: string;
  type: string;
  status: JobStatus;
  progress: number;
  message: string | null;
  result: JsonObject | null;
  error: string | null;
  data_source_id: string | null;
  device_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type BackupSchedule = "hourly" | "every_6h" | "daily";

export type BackupPolicy = {
  enabled: boolean;
  schedule: BackupSchedule;
  keep_hourly: number;
  keep_daily: number;
  keep_weekly: number;
  keep_monthly: number;
  pitr_enabled: boolean;
  pitr_window_days: number; // 1..35
  copy_to_primary: boolean;
  copy_to_device_id: string | null; // at most one copy target
  safety_snapshots: boolean;
  updated_at: string;
};

export type BackupPolicyUpdate = Partial<Omit<BackupPolicy, "updated_at">>;

export type BackupTrigger = "scheduled" | "manual" | "pre_restore" | "pre_drop" | "pre_delete" | "pre_move" | "final";

export type BackupCopyLocation = "local" | "device" | "primary";

export type BackupCopy = { location: BackupCopyLocation; device_id: string | null; status: string };

export type Backup = {
  id: string;
  trigger: BackupTrigger;
  status: "running" | "succeeded" | "failed";
  label: string | null;
  pinned: boolean;
  size_bytes: number | null;
  started_at: string;
  finished_at: string | null;
  verified_at: string | null;
  verify_status: "ok" | "failed" | null;
  copies: BackupCopy[];
  row_counts: Record<string, number> | null;
  expires_at: string | null;
  job_id: string | null;
};

export type DiffChange = "added" | "removed" | "changed";

export type FieldDiff = { name: string; change: DiffChange; before: Field | null; after: Field | null };

export type SchemaDiffEntity = {
  name: string;
  change: DiffChange;
  fields: FieldDiff[];
  indexes: { name: string; change: DiffChange }[];
  validator_changed: boolean;
  row_count: { before: number | null; after: number | null };
};

export type SchemaDiff = {
  from: { backup_id: string | null; at: string };
  to: { backup_id: string | null; at: string };
  entities: SchemaDiffEntity[];
};

export type RecoveryWindow = {
  pitr_enabled: boolean;
  earliest: string | null;
  latest: string | null;
  snapshots: number;
};

export type RestoreMode = "new_source" | "in_place";

export type RestoreRequest = {
  backup_id?: string;
  point_in_time?: string;
  mode: RestoreMode;
  new_name?: string;
  device_id?: string | null;
};

export type JobResponse = { job: Job };

export type DeletedSource = DataSource & { deleted_at: string; purge_at: string };

export type InstanceBackupSource = {
  data_source_id: string;
  project_id: string;
  project_name: string;
  name: string;
  engine: string;
  device_id: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  pitr_latest: string | null;
  local_bytes: number | null;
  copy_bytes: number | null;
};

export type InstanceBackups = {
  sources: InstanceBackupSource[];
  platform: { last_success_at: string | null; last_error: string | null };
  storage: { location: string; device_id: string | null; used_bytes: number | null; free_bytes: number | null }[];
};

// ---- Query console (docs/QUERY_CONSOLE.md) ----

export type QueryRequest = {
  /** SQL text (several statements allowed) or MongoDB shell code; 1..200 000 chars. */
  query: string;
  /** Rows returned per result set / documents printed; 1..5000, default 500. */
  max_rows?: number;
  /** Per statement (SQL) or for the whole script (MongoDB); 1..120, default 30. */
  timeout_seconds?: number;
  /** Which console layout sent it; recorded in the query log (QUERY_EDITOR.md). */
  layout?: "terminal" | "editor";
};

export type QueryError = { code: string; message: string };

export type SqlEngine = Exclude<DataSourceEngine, "mongodb">;

/** One entry of `SqlQueryResponse.results`; `rows` values are encoded like the data browser. */
export type SqlStatementResult =
  | {
      type: "rows";
      statement: string;
      columns: string[];
      rows: JsonValue[][];
      row_count: number;
      truncated: boolean;
      duration_ms: number;
    }
  | { type: "count"; statement: string; affected_rows: number; duration_ms: number }
  | { type: "empty"; statement: string; duration_ms: number }
  | { type: "error"; statement: string; error: QueryError; duration_ms?: number };

export type SqlQueryResponse = {
  kind: "sql";
  engine: SqlEngine;
  duration_ms: number;
  results: SqlStatementResult[];
  /** Id of the query-log row (QUERY_EDITOR.md). */
  run_id?: string;
};

export type MongoQueryResponse = {
  kind: "nosql";
  engine: "mongodb";
  duration_ms: number;
  /** Text printed by the shell (print(), warnings, stderr). */
  output: string;
  /** Relaxed Extended JSON of the last expression, or null. */
  result: JsonValue | null;
  /** Set when `result` is an array of documents (cursor batch). */
  result_docs: JsonObject[] | null;
  truncated: boolean;
  error: QueryError | null;
  /** Id of the query-log row (QUERY_EDITOR.md). */
  run_id?: string;
};

export type QueryResponse = SqlQueryResponse | MongoQueryResponse;

// ---- Query editor (docs/QUERY_EDITOR.md) ----

export type SavedQueryKind = "sql" | "nosql" | "any";

/** A snippet: `query_text` is opaque to the API (the notebook stores `{"cells":[…]}` JSON in it). */
export type SavedQuery = {
  id: string;
  project_id: string;
  data_source_id: string | null;
  owner_id: string;
  owner_email: string;
  name: string;
  folder: string | null;
  query_text: string;
  kind: SavedQueryKind;
  created_at: string;
  updated_at: string;
  /** Bumped by every text change; a PATCH must carry the version it was based on (QUERY_EDITOR.md → phase 2). */
  version: number;
  updated_by_email: string;
};

export type SavedQueryInput = {
  name: string;
  folder?: string | null;
  query_text: string;
  data_source_id?: string | null;
  kind: SavedQueryKind;
};

/** A PATCH always carries the version the client loaded; the API answers `409 version_conflict` otherwise. */
export type SavedQueryUpdate = Partial<SavedQueryInput> & { version: number; message?: string };

export type SavedQueryVersion = {
  id: string;
  version: number;
  author_id: string;
  author_email: string;
  message: string | null;
  created_at: string;
  /** Length of that version's `query_text`. */
  chars: number;
};

export type SavedQueryRestore = { version: number; current_version: number; message?: string };

export type QueryRunStatus = "ok" | "error" | "timeout" | "refused";

/** One row of the server-side query log (every console run, both layouts). */
export type QueryRun = {
  id: string;
  project_id: string;
  data_source_id: string;
  source_name: string;
  kind: DataSourceKind;
  engine: string;
  user_id: string;
  user_email: string;
  /** Truncated to 2 000 chars in list responses (`query_truncated`); `GET /query-log/{id}` has the full text. */
  query_text: string;
  query_truncated?: boolean;
  status: QueryRunStatus;
  statements: number;
  rows: number;
  affected_rows: number | null;
  duration_ms: number;
  error_message: string | null;
  read_only: boolean;
  layout: "terminal" | "editor" | "api";
  created_at: string;
};

export type QueryLogPage = { runs: QueryRun[]; has_more: boolean };

export type QueryLogParams = { source_id?: string; user?: "me" | "all"; limit?: number; before?: string };

// ---- Remote access (docs/REMOTE_ACCESS.md) ----

export type Domain = {
  id: string;
  hostname: string;
  zone_id: string;
  zone_name: string;
  target_type: "dashboard" | "project";
  project_id: string | null;
  status: "pending" | "active" | "error";
  status_message: string | null;
  url: string;
};

export type RemoteAccessMode = "off" | "cloudflare" | "quick";

export type RemoteAccess = {
  mode: RemoteAccessMode;
  public_url: string;
  connector: { running: boolean; started_at: string | null; last_error: string | null };
  cloudflare: {
    linked: boolean;
    token_valid: boolean | null;
    account: { id: string; name: string } | null;
    tunnel: { id: string; name: string; status: string | null; connections: number } | null;
    domains: Domain[];
    /** Not in REMOTE_ACCESS.md; used when present so zones survive a page reload after linking. */
    zones?: CloudflareZone[];
  };
  quick: { url: string | null };
};

export type CloudflareZone = { id: string; name: string; account_id: string; status: string };

export type CloudflareVerifyResult = {
  ok: boolean;
  accounts: { id: string; name: string }[];
  zones: CloudflareZone[];
  missing_permissions: string[];
};

export type PublicUrlRequest = { domain_id: string } | { quick: true } | { local: true };

export type PublicUrlResponse = {
  settings: InstanceSettings;
  oauth_callbacks: { google: string; github: string };
  previous_public_url: string;
};

// ---- Deployments / push-to-deploy (docs/DEPLOYMENTS.md) ----

export type AppPreset = "static" | "node" | "python" | "dockerfile";

export type DeploymentStatus = "queued" | "building" | "deploying" | "live" | "failed" | "cancelled" | "superseded";

export type DeploymentTrigger = "manual" | "webhook" | "rollback";

export type Deployment = {
  id: string;
  app_id: string;
  status: DeploymentStatus;
  trigger: DeploymentTrigger;
  commit_sha: string | null;
  commit_message: string | null;
  branch: string;
  image_tag: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  rollback_of: string | null;
  /** Only with `?log=1`. */
  log?: string;
  job_id: string | null;
};

export type App = {
  id: string;
  project_id: string;
  name: string;
  slug: string;
  repo_url: string;
  branch: string;
  root_dir: string;
  preset: AppPreset;
  install_command: string | null;
  build_command: string | null;
  start_command: string | null;
  output_dir: string | null;
  container_port: number | null;
  env_keys: string[];
  has_repo_token: boolean;
  api_key_id: string | null;
  /** docs/DEPLOYMENTS.md "Database access": joins the databases network + DEPLOYER_DB_* env. Admin-only to enable. */
  database_access: boolean;
  /** Set when the app clones (and got its webhook) through someone's GitHub connection. */
  github: { connected_by_email: string; hook_active: boolean } | null;
  port: number;
  local_url: string;
  urls: string[];
  live_deployment: Deployment | null;
  domains: Domain[];
  created_at: string;
  updated_at: string;
};

export type AppInput = {
  name: string;
  repo_url: string;
  branch?: string;
  root_dir?: string;
  preset: AppPreset;
  install_command?: string | null;
  build_command?: string | null;
  start_command?: string | null;
  output_dir?: string | null;
  container_port?: number | null;
  env?: Record<string, string>;
  repo_token?: string;
  api_key_id?: string | null;
  database_access?: boolean;
  /** Clone + add the push webhook with the caller's GitHub connection (instead of `repo_token`). */
  use_github_connection?: boolean;
};

/** `POST /apps` also returns what couldn't be set up automatically (e.g. the webhook). */
export type AppCreated = App & { warnings: string[] };

/** `repo_token: null` clears the stored token. */
export type AppPatch = Partial<Omit<AppInput, "repo_token" | "use_github_connection">> & { repo_token?: string | null };

/** docs/DEPLOYMENTS.md "Connect a Git repository". */
export type GitHubStatus = { connected: boolean; login: string | null; scopes: string[]; configured: boolean };

export type GitHubRepo = {
  full_name: string;
  private: boolean;
  default_branch: string;
  html_url: string;
  clone_url: string;
  pushed_at: string | null;
  description: string | null;
};

/** `POST /apps/detect`: a suggested app, never persisted. */
export type AppDetectDraft = {
  name: string;
  repo_url: string;
  branch: string;
  root_dir: string;
  preset: AppPreset;
  install_command: string | null;
  build_command: string | null;
  start_command: string | null;
  output_dir: string | null;
  container_port: number | null;
  env_keys: string[];
  database_access_suggested: boolean;
  detected: { what: string; from: string }[];
  warnings: string[];
  /** null when the repository isn't on GitHub (not inspected). */
  private: boolean | null;
};

export type DeploymentPage = { deployments: Deployment[]; has_more: boolean };

export type AppWebhook = { url: string; secret: string; hook_active?: boolean; warnings?: string[] };

export type AppLogs = { lines: string[]; container: string | null };
