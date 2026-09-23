# Deployer HTTP API (v1)

This file covers the foundation endpoints. Feature areas added later document their endpoints next to
their design:

| Area | Endpoints documented in |
|---|---|
| Host devices (enrollment, device management, placement, moving databases, device-local status) | [DEVICES.md](DEVICES.md) |
| Backups, versions, point-in-time restore, jobs, recently deleted | [BACKUPS.md](BACKUPS.md) |
| Cloudflare remote access & custom domains | [REMOTE_ACCESS.md](REMOTE_ACCESS.md) |
| Query console (`POST /projects/{id}/data-sources/{sid}/query`: SQL scripts and MongoDB shell code per data source; `api_keys: true`) | [QUERY_CONSOLE.md](QUERY_CONSOLE.md) |
| Data API for apps: API keys on the data, query and schema routes, reveal / config download | [DATA_API.md](DATA_API.md) |
| Query editor: query log (`/projects/{id}/query-log`) and saved queries (`/projects/{id}/saved-queries`) | [QUERY_EDITOR.md](QUERY_EDITOR.md) |
| Saved-query versions: strict version control (`/projects/{id}/saved-queries/{sid}/versions`, `/restore`, `409 version_conflict`) | [QUERY_EDITOR.md](QUERY_EDITOR.md) "Phase 2 — versions" |
| Push-to-deploy: apps (`/projects/{id}/apps`), deployments, rollback, runtime logs, app hostnames, and the unauthenticated GitHub webhook `POST /hooks/github/{app_id}` (HMAC `X-Hub-Signature-256`). `database_access` (opt-in, admin+ to enable) joins an app to the databases network and injects `DEPLOYER_DB_<NAME>_*` | [DEPLOYMENTS.md](DEPLOYMENTS.md) |

Base path `/v1`. JSON in/out unless noted. Authenticated endpoints need
`Authorization: Bearer <access_token>`. Timestamps are ISO-8601 UTC strings. IDs are UUID strings.

Errors always look like:

```json
{ "error": { "code": "snake_case_code", "message": "Human readable", "details": {} } }
```

Common codes: `unauthorized` (401), `forbidden` (403), `not_found` (404), `validation_error` (422),
`conflict` (409), `rate_limited` (429), `not_initialized` / `already_initialized` (409).

Roles are ordered `viewer < developer < admin < owner`. "admin+" means admin or owner.

## Shared shapes

```ts
type User = {
  id: string; email: string; display_name: string | null; avatar_url: string | null;
  is_instance_owner: boolean; has_password: boolean; created_at: string;
  identities: Identity[];
};
type Identity = {
  id: string; provider: "google" | "github"; provider_email: string | null;
  provider_username: string | null; created_at: string;
};
type AuthResponse = { access_token: string; token_type: "bearer"; expires_in: number; user: User };

type Role = "owner" | "admin" | "developer" | "viewer";
type Project = {
  id: string; slug: string; name: string; description: string | null;
  owner_id: string; my_role: Role; created_at: string; updated_at: string;
  data_source_counts: { sql: number; nosql: number };
};
type Member = { user_id: string; email: string; display_name: string | null;
                avatar_url: string | null; role: Role; created_at: string };
type Invite = { id: string; email: string | null; role: Exclude<Role, "owner">;
                invited_by: string; expires_at: string; created_at: string };

type DataSource = {
  id: string; project_id: string; name: string;
  kind: "sql" | "nosql";
  engine: "mariadb" | "mysql" | "postgresql" | "mongodb";
  mode: "managed" | "external";
  database_name: string;
  status: "ok" | "error" | "unknown"; status_message: string | null; last_checked_at: string | null;
  display: { host: string | null; port: number | null; username: string | null; tls: boolean };
  created_at: string;
};
type ApiKey = { id: string; name: string; prefix: string; role: "anon" | "service";
                created_at: string; last_used_at: string | null; revoked_at: string | null };
```

---

## Health & setup (no auth)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | – | `{status:"ok", version, services:{mariadb:bool, mongodb:bool, redis:bool}}` |
| GET | `/setup/status` | – | `{initialized:boolean, version, public_url, providers:{google:boolean, github:boolean}, allow_signup:boolean, device_mode:"standalone"\|"host"}` (`device_mode`: [DEVICES.md](DEVICES.md)) |
| POST | `/setup/owner` | `{email, password, display_name?}` | `AuthResponse` (+ refresh cookie). 409 `already_initialized` if any user exists |
| POST | `/setup/import` | multipart: `file`, `passphrase` | `{ok:true, summary:{users, projects, data_sources, rows, documents}}`. Only while not initialized; `scope` must be `instance`. 400 `bad_passphrase` / `invalid_export` |

## Auth

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/auth/providers` | – | – | `{google:boolean, github:boolean, allow_signup:boolean}` |
| POST | `/auth/signup` | – | `{email, password, display_name?, invite_token?}` | `AuthResponse`. Allowed if `allow_signup` or a valid invite token (email-locked invites must match) |
| POST | `/auth/login` | – | `{email, password}` | `AuthResponse`; 401 `invalid_credentials`; 429 `rate_limited` |
| POST | `/auth/refresh` | cookie | – | `AuthResponse` (rotates cookie); 401 `unauthorized` |
| POST | `/auth/logout` | cookie | – | `{ok:true}` (revokes refresh token, clears cookie) |
| GET | `/auth/me` | bearer | – | `User` |
| PATCH | `/auth/me` | bearer | `{display_name?}` | `User` |
| POST | `/auth/password` | bearer | `{current_password?, new_password}` | `{ok:true}` (`current_password` required if one exists) |
| GET | `/auth/oauth/{provider}/start?redirect=/path&invite_token=` | – | – | **302** to provider (login/signup intent) |
| POST | `/auth/oauth/{provider}/link` | bearer | `{redirect?:"/settings/account"}` | `{authorize_url}` — dashboard navigates to it |
| GET | `/auth/oauth/{provider}/callback?code&state` | – | – | **302** to dashboard (see below) |
| DELETE | `/auth/identities/{identity_id}` | bearer | – | `User`; 409 `last_login_method` |

OAuth callback redirects:
- Success (login): sets refresh cookie, 302 → `{public_url}/auth/complete?redirect=<path>`; the
  dashboard then calls `POST /auth/refresh` to obtain an access token.
- Success (link): 302 → `{public_url}<redirect>?linked=<provider>`.
- Failure: 302 → `{public_url}/login?error=<code>` (login) or `{public_url}<redirect>?error=<code>` (link).
  Codes: `oauth_failed`, `oauth_state_invalid`, `account_exists_link_required`, `identity_in_use`,
  `signup_disabled`, `provider_not_configured`, `email_not_verified`.

Provider callback URLs (shown in the setup wizard):
`{public_url}/v1/auth/oauth/google/callback`, `{public_url}/v1/auth/oauth/github/callback`.

## Instance (instance owner only)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/instance/settings` | – | `InstanceSettings` |
| PUT | `/instance/settings` | `{public_url?, allow_signup?, google_client_id?, google_client_secret?, github_client_id?, github_client_secret?}` (empty string clears) | `InstanceSettings` |
| GET | `/instance/users` | – | `User[]` |
| POST | `/instance/export` | `{passphrase}` | file download `deployer-instance-YYYYMMDD-HHMM.json` |

```ts
type InstanceSettings = {
  public_url: string; allow_signup: boolean;
  google: { client_id: string | null; secret_set: boolean; configured: boolean; callback_url: string };
  github: { client_id: string | null; secret_set: boolean; configured: boolean; callback_url: string };
};
```

## Projects

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects` | member | – | `Project[]` |
| POST | `/projects` | any user | `{name, description?, provision?:{sql:boolean, nosql:boolean}}` | `Project` (creates managed MariaDB and/or MongoDB sources when requested) |
| GET | `/projects/{project_id}` | viewer+ | – | `Project` |
| PATCH | `/projects/{project_id}` | admin+ | `{name?, description?}` | `Project` |
| DELETE | `/projects/{project_id}?confirm=<slug>` | owner | – | `{ok:true}` (managed databases get a final snapshot, kept 30 days, then are dropped by a job — [BACKUPS.md](BACKUPS.md)) |
| POST | `/projects/export` | owner of each | `{project_ids:string[], passphrase}` | file download `deployer-projects-YYYYMMDD-HHMM.json` |
| POST | `/projects/import` | any user | multipart: `file`, `passphrase` | `{ok:true, projects:Project[], summary}` (`scope` must be `projects`) |

## Members & invites

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/members` | viewer+ | – | `Member[]` |
| PATCH | `/projects/{id}/members/{user_id}` | admin+ | `{role}` (not `owner`; can't change owner) | `Member` |
| DELETE | `/projects/{id}/members/{user_id}` | admin+ or self | – | `{ok:true}` (owner can't be removed) |
| GET | `/projects/{id}/invites` | admin+ | – | `Invite[]` (pending only) |
| POST | `/projects/{id}/invites` | admin+ | `{email?, role, expires_in_days?:1..30 (default 7)}` | `{invite:Invite, invite_url}` — token only returned here |
| DELETE | `/projects/{id}/invites/{invite_id}` | admin+ | – | `{ok:true}` |
| GET | `/invites/{token}` | – | – | `{project_name, role, invited_by_name, email, expires_at}`; 404 if invalid/expired/used |
| POST | `/invites/{token}/accept` | bearer | – | `{project_id}`; 403 `invite_email_mismatch` |

`invite_url` = `{public_url}/invite/{token}`.

## API keys

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/api-keys` | admin+ | – | `ApiKey[]` |
| POST | `/projects/{id}/api-keys` | admin+ | `{name, role}` | `{api_key:ApiKey, secret}` — secret `dpl_<role>_<random>` shown once |
| DELETE | `/projects/{id}/api-keys/{key_id}` | admin+ | – | `{ok:true}` (revokes) |
| GET | `/projects/{id}/api-keys/{key_id}/reveal` | admin+ | – | `{secret}`; 409 `not_revealable` (key predates stored secrets), 409 `api_key_revoked` |
| GET | `/projects/{id}/api-keys/{key_id}/config` | admin+ | – | app config JSON download `deployer-<slug>-<role>.json` (same 409s) — [DATA_API.md](DATA_API.md) |

`ApiKey` has `revealable: boolean`. Keys (`Authorization: Bearer dpl_...`) are accepted **only** by the
data browser, `POST .../query` and the GET schema routes (marked `api_keys: true` below): `anon` acts
as viewer, `service` as developer; elsewhere they get 401 `api_key_not_allowed`. See [DATA_API.md](DATA_API.md).

## Data sources

| Method | Path | Role | Body | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/data-sources` | viewer+ | – | `DataSource[]` |
| POST | `/projects/{id}/data-sources/test` | admin+ | `DataSourceInput` | `{ok:boolean, message, server_version:string\|null}` |
| POST | `/projects/{id}/data-sources` | admin+ | `DataSourceInput` | `DataSource` (external sources are tested first; 400 `connection_failed`) |
| POST | `/projects/{id}/data-sources/{sid}/check` | viewer+ | – | `DataSource` (refreshes status) |
| GET | `/projects/{id}/data-sources/{sid}/connection` | developer+ | – | `{uri, host, port, username, password, database}` for use in apps (from inside the Docker network for managed sources; `external_hint` explains host access) |
| DELETE | `/projects/{id}/data-sources/{sid}?drop=false` | admin+ (`drop=true`: owner) | – | `{ok:true, job?: Job}` — managed sources are soft-deleted ("Recently deleted", [BACKUPS.md](BACKUPS.md)) with a final snapshot job; 400 `cannot_drop_external` |

```ts
type DataSourceInput =
  | { kind: "sql"; mode: "managed"; engine: "mariadb"; name: string }
  | { kind: "nosql"; mode: "managed"; engine: "mongodb"; name: string }
  | { kind: "sql"; mode: "external"; engine: "mariadb" | "mysql" | "postgresql"; name: string;
      config: { host: string; port?: number; username: string; password: string; database: string; tls?: boolean } }
  | { kind: "nosql"; mode: "external"; engine: "mongodb"; name: string;
      config: { uri: string; database: string } };
```

A project may have any number of SQL and NoSQL sources at once (typically one of each).

## Schema

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/schema?source_id=&sample=200` | viewer+ (`api_keys: true`) | – | `ProjectSchema` |
| GET | `/projects/{id}/schema/export?format=sql\|mongo\|bundle&source_id=` | viewer+ (`api_keys: true`) | – | file: `.sql` / `.js` / `.zip` |
| GET | `/projects/{id}/schema/links` | viewer+ (`api_keys: true`) | – | `SchemaLink[]` |
| POST | `/projects/{id}/schema/links` | developer+ | `Omit<SchemaLink,"id"\|"created_at">` | `SchemaLink` |
| DELETE | `/projects/{id}/schema/links/{link_id}` | developer+ | – | `{ok:true}` |
| POST | `/projects/{id}/data-sources/{sid}/tables` | developer+ | `TableSpec` | `Entity` |
| DELETE | `/projects/{id}/data-sources/{sid}/tables/{table}` | admin+ | – | `{ok:true}` |
| POST | `/projects/{id}/data-sources/{sid}/collections` | developer+ | `{name, validator?:object}` | `Entity` |
| DELETE | `/projects/{id}/data-sources/{sid}/collections/{name}` | admin+ | – | `{ok:true}` |

```ts
type ProjectSchema = {
  sources: SourceSchema[];
  links: SchemaLink[];
  conventions: ConventionIssue[];
  generated_at: string;
};
type SourceSchema = {
  source_id: string; name: string; kind: "sql" | "nosql"; engine: string;
  status: "ok" | "error"; error: string | null;
  entities: Entity[];
  relationships: Relationship[];
};
type Entity = {
  name: string; type: "table" | "collection";
  row_count: number | null;
  fields: Field[];
  indexes: { name: string; fields: string[]; unique: boolean }[];
  validator: object | null;            // Mongo $jsonSchema, if any
};
type Field = {
  name: string;                         // nested Mongo fields use dot paths: "address.city"
  data_type: string;                    // SQL: full column type ("bigint(20) unsigned"); Mongo: "string" | "objectId" | "int|string" ...
  nullable: boolean;
  default: string | null;
  primary_key: boolean;
  unique: boolean;
  indexed: boolean;
  foreign_key: { entity: string; field: string } | null;
  occurrence: number | null;            // Mongo only: 0..1 share of sampled docs containing the field
};
type Relationship = {
  from_entity: string; from_fields: string[];   // the "many" / referencing side
  to_entity: string; to_fields: string[];
  cardinality: "one_to_one" | "many_to_one";
  origin: "foreign_key" | "inferred";
};
type SchemaLink = {
  id: string;
  from_source_id: string; from_entity: string; from_field: string;
  to_source_id: string; to_entity: string; to_field: string;
  cardinality: "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many";
  note: string | null; created_at: string;
};
type ConventionIssue = {
  rule: string;                         // e.g. "N1" — see docs/CONVENTIONS.md
  severity: "warning" | "info";
  source_id: string | null; entity: string | null; field: string | null;
  message: string;
};
type TableSpec = {
  name: string;
  columns: { name: string; type: string; nullable?: boolean; default?: string | null;
             primary_key?: boolean; unique?: boolean; auto_increment?: boolean;
             references?: { table: string; column: string; on_delete?: "cascade" | "set null" | "restrict" } }[];
  timestamps?: boolean;                 // adds created_at / updated_at
};
```

## Data browser

All routes accept API keys (`api_keys: true`, [DATA_API.md](DATA_API.md)). SQL (`kind = sql`):

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/data-sources/{sid}/tables/{table}/rows?limit=50&offset=0&order_by=&order=asc` | viewer+ | – | `{columns:string[], primary_key:string[], rows:object[], total:number}` |
| POST | `.../tables/{table}/rows` | developer+ | `{values:object}` | `{row:object}` |
| PATCH | `.../tables/{table}/rows` | developer+ | `{pk:object, values:object}` | `{row:object}` |
| DELETE | `.../tables/{table}/rows` | developer+ | `{pk:object}` | `{ok:true}` |

MongoDB (`kind = nosql`):

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/projects/{id}/data-sources/{sid}/collections/{name}/documents?filter={json}&limit=50&skip=0` | viewer+ | – | `{documents:object[], total:number}` (relaxed Extended JSON) |
| POST | `.../collections/{name}/documents` | developer+ | `{document:object}` | `{document:object}` |
| PATCH | `.../collections/{name}/documents/{doc_id}` | developer+ | `{set:object, unset?:string[]}` | `{document:object}` |
| DELETE | `.../collections/{name}/documents/{doc_id}` | developer+ | – | `{ok:true}` |

`doc_id` is the string form of `_id` (tried as ObjectId hex, then as a 64-bit integer, then as the raw string).
Binary SQL values are returned as `{"$base64": "..."}`, decimals as strings, datetimes as ISO strings.
