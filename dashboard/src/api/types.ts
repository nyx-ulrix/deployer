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
  provision?: { sql: boolean; nosql: boolean };
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
  | { kind: "sql"; mode: "managed"; engine: "mariadb"; name: string }
  | { kind: "nosql"; mode: "managed"; engine: "mongodb"; name: string }
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
