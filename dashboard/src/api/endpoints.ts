import { client } from "./client";
import type {
  ApiKey,
  ApiKeyConfig,
  ApiKeyCreateResponse,
  ApiKeyRole,
  App,
  CohostEligibility,
  ConflictChoice,
  Replica,
  ReplicaResponse,
  SyncConflict,
  SyncHistoryItem,
  AppCreated,
  AppDetectDraft,
  AppInput,
  AppLogs,
  AppPatch,
  AppWebhook,
  AuthResponse,
  Deployment,
  DeploymentPage,
  Backup,
  BackupPolicy,
  BackupPolicyUpdate,
  CloudflareVerifyResult,
  ConnectionDetails,
  DeletedSource,
  Device,
  DeviceApproval,
  DeviceEnrollment,
  DeviceUpdate,
  Domain,
  EnrollStartResponse,
  GitHubRepo,
  GitHubStatus,
  EnrollStatus,
  InstanceBackups,
  Job,
  JobResponse,
  LocalDeviceStatus,
  PlacementOption,
  PublicUrlRequest,
  PublicUrlResponse,
  RecoveryWindow,
  RemoteAccess,
  RestoreRequest,
  SchemaDiff,
  SourceSchema,
  ConnectionTestResult,
  DataSource,
  DataSourceInput,
  DocumentsResponse,
  Entity,
  Health,
  InstanceSettings,
  InstanceSettingsUpdate,
  Invite,
  InviteCreate,
  InviteCreateResponse,
  InvitePreview,
  JsonObject,
  Member,
  Ok,
  Project,
  ProjectCreate,
  ProjectSchema,
  ProjectsImportResponse,
  ProviderName,
  ProvidersResponse,
  QueryLogPage,
  QueryLogParams,
  QueryRequest,
  QueryResponse,
  QueryRun,
  SavedQuery,
  SavedQueryInput,
  SavedQueryRestore,
  SavedQueryUpdate,
  SavedQueryVersion,
  Role,
  RowsResponse,
  SchemaExportFormat,
  SchemaLink,
  SchemaLinkCreate,
  SetupImportResponse,
  SetupStatus,
  TableSpec,
  User,
} from "./types";

const e = encodeURIComponent;

function importForm(file: File, passphrase: string): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("passphrase", passphrase);
  return form;
}

/** QUERY_CONSOLE.md: `POST /projects/{id}/data-sources/{sid}/query` (SQL or MongoDB shell code). */
export function runQuery(projectId: string, sid: string, body: QueryRequest, signal?: AbortSignal) {
  return client.post<QueryResponse>(`/projects/${e(projectId)}/data-sources/${e(sid)}/query`, body, { signal });
}

export const api = {
  health: () => client.get<Health>("/health", { auth: false }),

  setup: {
    status: () => client.get<SetupStatus>("/setup/status", { auth: false }),
    createOwner: async (body: { email: string; password: string; display_name?: string }) => {
      const res = await client.post<AuthResponse>("/setup/owner", body, { auth: false });
      client.setSession(res);
      return res;
    },
    importInstance: (file: File, passphrase: string) =>
      client.upload<SetupImportResponse>("/setup/import", importForm(file, passphrase), { auth: false }),
  },

  auth: {
    providers: () => client.get<ProvidersResponse>("/auth/providers", { auth: false }),
    login: async (body: { email: string; password: string }) => {
      const res = await client.post<AuthResponse>("/auth/login", body, { auth: false });
      client.setSession(res);
      return res;
    },
    signup: async (body: { email: string; password: string; display_name?: string; invite_token?: string }) => {
      const res = await client.post<AuthResponse>("/auth/signup", body, { auth: false });
      client.setSession(res);
      return res;
    },
    logout: async () => {
      try {
        await client.post<Ok>("/auth/logout", undefined, { auth: false });
      } finally {
        client.clearSession();
      }
    },
    me: () => client.get<User>("/auth/me"),
    updateMe: (body: { display_name?: string }) => client.patch<User>("/auth/me", body),
    setPassword: (body: { current_password?: string; new_password: string }) =>
      client.post<Ok>("/auth/password", body),
    oauthStartUrl: (provider: ProviderName, redirect: string, inviteToken?: string) => {
      const params = new URLSearchParams({ redirect });
      if (inviteToken) params.set("invite_token", inviteToken);
      return `/v1/auth/oauth/${provider}/start?${params.toString()}`;
    },
    linkProvider: (provider: ProviderName, redirect = "/settings/account") =>
      client.post<{ authorize_url: string }>(`/auth/oauth/${provider}/link`, { redirect }),
    unlinkIdentity: (identityId: string) => client.del<User>(`/auth/identities/${e(identityId)}`),
  },

  instance: {
    settings: () => client.get<InstanceSettings>("/instance/settings"),
    updateSettings: (body: InstanceSettingsUpdate) => client.put<InstanceSettings>("/instance/settings", body),
    users: () => client.get<User[]>("/instance/users"),
    export: (passphrase: string) =>
      client.download("POST", "/instance/export", "deployer-instance.json", { body: { passphrase } }),
  },

  projects: {
    list: () => client.get<Project[]>("/projects"),
    create: (body: ProjectCreate) => client.post<Project>("/projects", body),
    get: (id: string) => client.get<Project>(`/projects/${e(id)}`),
    update: (id: string, body: { name?: string; description?: string }) =>
      client.patch<Project>(`/projects/${e(id)}`, body),
    remove: (id: string, slug: string) => client.del<Ok>(`/projects/${e(id)}`, { query: { confirm: slug } }),
    export: (projectIds: string[], passphrase: string) =>
      client.download("POST", "/projects/export", "deployer-projects.json", {
        body: { project_ids: projectIds, passphrase },
      }),
    import: (file: File, passphrase: string) =>
      client.upload<ProjectsImportResponse>("/projects/import", importForm(file, passphrase)),
  },

  members: {
    list: (pid: string) => client.get<Member[]>(`/projects/${e(pid)}/members`),
    update: (pid: string, userId: string, role: Exclude<Role, "owner">) =>
      client.patch<Member>(`/projects/${e(pid)}/members/${e(userId)}`, { role }),
    remove: (pid: string, userId: string) => client.del<Ok>(`/projects/${e(pid)}/members/${e(userId)}`),
  },

  invites: {
    list: (pid: string) => client.get<Invite[]>(`/projects/${e(pid)}/invites`),
    create: (pid: string, body: InviteCreate) =>
      client.post<InviteCreateResponse>(`/projects/${e(pid)}/invites`, body),
    revoke: (pid: string, inviteId: string) => client.del<Ok>(`/projects/${e(pid)}/invites/${e(inviteId)}`),
    preview: (token: string) => client.get<InvitePreview>(`/invites/${e(token)}`, { auth: false }),
    accept: (token: string) => client.post<{ project_id: string }>(`/invites/${e(token)}/accept`),
  },

  apiKeys: {
    list: (pid: string) => client.get<ApiKey[]>(`/projects/${e(pid)}/api-keys`),
    create: (pid: string, body: { name: string; role: ApiKeyRole }) =>
      client.post<ApiKeyCreateResponse>(`/projects/${e(pid)}/api-keys`, body),
    revoke: (pid: string, keyId: string) => client.del<Ok>(`/projects/${e(pid)}/api-keys/${e(keyId)}`),
    reveal: (pid: string, keyId: string) =>
      client.get<{ secret: string }>(`/projects/${e(pid)}/api-keys/${e(keyId)}/reveal`),
    // Served as a download by the API; fetched as JSON so auth/refresh apply and the dashboard names the file.
    config: (pid: string, keyId: string) =>
      client.get<ApiKeyConfig>(`/projects/${e(pid)}/api-keys/${e(keyId)}/config`),
  },

  dataSources: {
    list: (pid: string) => client.get<DataSource[]>(`/projects/${e(pid)}/data-sources`),
    test: (pid: string, body: DataSourceInput) =>
      client.post<ConnectionTestResult>(`/projects/${e(pid)}/data-sources/test`, body),
    create: (pid: string, body: DataSourceInput) => client.post<DataSource>(`/projects/${e(pid)}/data-sources`, body),
    check: (pid: string, sid: string) =>
      client.post<DataSource>(`/projects/${e(pid)}/data-sources/${e(sid)}/check`),
    connection: (pid: string, sid: string) =>
      client.get<ConnectionDetails>(`/projects/${e(pid)}/data-sources/${e(sid)}/connection`),
    remove: (pid: string, sid: string, drop: boolean) =>
      client.del<Ok>(`/projects/${e(pid)}/data-sources/${e(sid)}`, { query: { drop } }),
    /** DEVICES.md: `POST .../data-sources/{sid}/move`. `device_id: null` = main server. */
    move: (pid: string, sid: string, deviceId: string | null) =>
      client.post<JobResponse>(`/projects/${e(pid)}/data-sources/${e(sid)}/move`, { device_id: deviceId }),
    placementOptions: (pid: string) => client.get<PlacementOption[]>(`/projects/${e(pid)}/placement-options`),
    deleted: (pid: string) => client.get<DeletedSource[]>(`/projects/${e(pid)}/deleted-sources`),
    restoreDeleted: (pid: string, sid: string, name?: string) =>
      client.post<JobResponse>(`/projects/${e(pid)}/deleted-sources/${e(sid)}/restore`, name ? { name } : {}),
  },

  // Primary-side device management. Paths follow DEVICES.md naming (`/devices`, `/devices/enrollments`).
  devices: {
    list: (scope: "mine" | "all" = "mine") =>
      client.get<Device[]>("/devices", { query: { scope: scope === "all" ? "all" : undefined } }),
    update: (id: string, body: DeviceUpdate) => client.patch<Device>(`/devices/${e(id)}`, body),
    remove: (id: string, force = false) => client.del<Ok>(`/devices/${e(id)}`, { query: { force: force || undefined } }),
    enrollmentByCode: (code: string) => client.get<DeviceEnrollment>("/devices/enrollments", { query: { code } }),
    approve: (enrollmentId: string, body: DeviceApproval) =>
      client.post<Device>(`/devices/enrollments/${e(enrollmentId)}/approve`, body),
    deny: (enrollmentId: string, userCode: string) =>
      client.post<Ok>(`/devices/enrollments/${e(enrollmentId)}/deny`, { user_code: userCode }),
  },

  /** Device-local API of *this* installation (DEVICES.md → Device-local API). */
  deviceLocal: {
    status: () => client.get<LocalDeviceStatus>("/device/status", { auth: false }),
    enrollStart: (body: { primary_url: string; device_name: string }) =>
      client.post<EnrollStartResponse>("/device/enroll/start", body),
    enrollStatus: () => client.get<EnrollStatus>("/device/enroll/status"),
    enrollCancel: () => client.post<Ok>("/device/enroll/cancel"),
  },

  backups: {
    policy: (pid: string, sid: string) =>
      client.get<BackupPolicy>(`/projects/${e(pid)}/data-sources/${e(sid)}/backup-policy`),
    updatePolicy: (pid: string, sid: string, body: BackupPolicyUpdate) =>
      client.put<BackupPolicy>(`/projects/${e(pid)}/data-sources/${e(sid)}/backup-policy`, body),
    list: (pid: string, sid: string, limit = 100) =>
      client.get<Backup[]>(`/projects/${e(pid)}/data-sources/${e(sid)}/backups`, { query: { limit } }),
    create: (pid: string, sid: string, label?: string) =>
      client.post<{ job: Job; backup_id: string }>(
        `/projects/${e(pid)}/data-sources/${e(sid)}/backups`,
        label ? { label } : {},
      ),
    update: (pid: string, sid: string, backupId: string, body: { label?: string | null; pinned?: boolean }) =>
      client.patch<Backup>(`/projects/${e(pid)}/data-sources/${e(sid)}/backups/${e(backupId)}`, body),
    remove: (pid: string, sid: string, backupId: string) =>
      client.del<Ok>(`/projects/${e(pid)}/data-sources/${e(sid)}/backups/${e(backupId)}`),
    schema: (pid: string, sid: string, backupId: string) =>
      client.get<SourceSchema>(`/projects/${e(pid)}/data-sources/${e(sid)}/backups/${e(backupId)}/schema`),
    diff: (pid: string, sid: string, from: string, to: string) =>
      client.get<SchemaDiff>(`/projects/${e(pid)}/data-sources/${e(sid)}/backups/diff`, { query: { from, to } }),
    download: (pid: string, sid: string, backupId: string) =>
      client.download("GET", `/projects/${e(pid)}/data-sources/${e(sid)}/backups/${e(backupId)}/download`, "backup.bin"),
    recoveryWindow: (pid: string, sid: string) =>
      client.get<RecoveryWindow>(`/projects/${e(pid)}/data-sources/${e(sid)}/recovery-window`),
    restore: (pid: string, sid: string, body: RestoreRequest) =>
      client.post<JobResponse>(`/projects/${e(pid)}/data-sources/${e(sid)}/restore`, body),
  },

  jobs: {
    list: (pid: string, limit = 50) => client.get<Job[]>(`/projects/${e(pid)}/jobs`, { query: { limit } }),
    get: (pid: string, jobId: string) => client.get<Job>(`/projects/${e(pid)}/jobs/${e(jobId)}`),
    cancel: (pid: string, jobId: string) => client.post<Job>(`/projects/${e(pid)}/jobs/${e(jobId)}/cancel`),
  },

  instanceBackups: {
    get: () => client.get<InstanceBackups>("/instance/backups"),
    platformNow: () => client.post<JobResponse>("/instance/backups/platform"),
  },

  remoteAccess: {
    get: () => client.get<RemoteAccess>("/instance/remote-access"),
    verify: (apiToken: string) =>
      client.post<CloudflareVerifyResult>("/instance/remote-access/cloudflare/verify", { api_token: apiToken }),
    link: (apiToken: string, accountId: string) =>
      client.post<RemoteAccess>("/instance/remote-access/cloudflare/link", { api_token: apiToken, account_id: accountId }),
    addHostname: (body: { zone_id: string; hostname: string; overwrite?: boolean }) =>
      client.post<Domain>("/instance/remote-access/cloudflare/hostnames", body),
    removeHostname: (domainId: string) =>
      client.del<Ok>(`/instance/remote-access/cloudflare/hostnames/${e(domainId)}`),
    unlink: (body: { delete_dns: boolean; delete_tunnel: boolean }) =>
      client.post<RemoteAccess>("/instance/remote-access/cloudflare/unlink", body),
    quick: (enabled: boolean) => client.post<RemoteAccess>("/instance/remote-access/quick", { enabled }),
    usePublicUrl: (body: PublicUrlRequest) =>
      client.post<PublicUrlResponse>("/instance/remote-access/public-url", body),
  },

  schema: {
    get: (pid: string, params: { source_id?: string; sample?: number } = {}) =>
      client.get<ProjectSchema>(`/projects/${e(pid)}/schema`, { query: params }),
    export: (pid: string, format: SchemaExportFormat, sourceId?: string) =>
      client.download(
        "GET",
        `/projects/${e(pid)}/schema/export`,
        format === "sql" ? "schema.sql" : format === "mongo" ? "schema.mongo.js" : "schema.zip",
        { query: { format, source_id: sourceId } },
      ),
    links: (pid: string) => client.get<SchemaLink[]>(`/projects/${e(pid)}/schema/links`),
    createLink: (pid: string, body: SchemaLinkCreate) =>
      client.post<SchemaLink>(`/projects/${e(pid)}/schema/links`, body),
    deleteLink: (pid: string, linkId: string) => client.del<Ok>(`/projects/${e(pid)}/schema/links/${e(linkId)}`),
    createTable: (pid: string, sid: string, spec: TableSpec) =>
      client.post<Entity>(`/projects/${e(pid)}/data-sources/${e(sid)}/tables`, spec),
    dropTable: (pid: string, sid: string, table: string) =>
      client.del<Ok>(`/projects/${e(pid)}/data-sources/${e(sid)}/tables/${e(table)}`),
    createCollection: (pid: string, sid: string, body: { name: string; validator?: JsonObject }) =>
      client.post<Entity>(`/projects/${e(pid)}/data-sources/${e(sid)}/collections`, body),
    dropCollection: (pid: string, sid: string, name: string) =>
      client.del<Ok>(`/projects/${e(pid)}/data-sources/${e(sid)}/collections/${e(name)}`),
  },

  rows: {
    list: (
      pid: string,
      sid: string,
      table: string,
      params: { limit: number; offset: number; order_by?: string; order?: "asc" | "desc" },
    ) =>
      client.get<RowsResponse>(`/projects/${e(pid)}/data-sources/${e(sid)}/tables/${e(table)}/rows`, {
        query: params,
      }),
    insert: (pid: string, sid: string, table: string, values: JsonObject) =>
      client.post<{ row: JsonObject }>(`/projects/${e(pid)}/data-sources/${e(sid)}/tables/${e(table)}/rows`, {
        values,
      }),
    update: (pid: string, sid: string, table: string, pk: JsonObject, values: JsonObject) =>
      client.patch<{ row: JsonObject }>(`/projects/${e(pid)}/data-sources/${e(sid)}/tables/${e(table)}/rows`, {
        pk,
        values,
      }),
    remove: (pid: string, sid: string, table: string, pk: JsonObject) =>
      client.request<Ok>("DELETE", `/projects/${e(pid)}/data-sources/${e(sid)}/tables/${e(table)}/rows`, {
        body: { pk },
      }),
  },

  query: {
    run: runQuery,
  },

  // QUERY_EDITOR.md: snippets (POST needs developer+; PATCH/DELETE the snippet's owner or admin+).
  savedQueries: {
    list: (pid: string) => client.get<SavedQuery[]>(`/projects/${e(pid)}/saved-queries`),
    create: (pid: string, body: SavedQueryInput) => client.post<SavedQuery>(`/projects/${e(pid)}/saved-queries`, body),
    update: (pid: string, id: string, body: SavedQueryUpdate) =>
      client.patch<SavedQuery>(`/projects/${e(pid)}/saved-queries/${e(id)}`, body),
    remove: (pid: string, id: string) => client.del<Ok>(`/projects/${e(pid)}/saved-queries/${e(id)}`),
    versions: (pid: string, id: string) =>
      client.get<{ versions: SavedQueryVersion[] }>(`/projects/${e(pid)}/saved-queries/${e(id)}/versions`),
    version: (pid: string, id: string, n: number) =>
      client.get<SavedQueryVersion & { query_text: string }>(`/projects/${e(pid)}/saved-queries/${e(id)}/versions/${n}`),
    /** A new version holding an old version's text; 409 when `current_version` is stale. */
    restore: (pid: string, id: string, body: SavedQueryRestore) =>
      client.post<SavedQuery>(`/projects/${e(pid)}/saved-queries/${e(id)}/restore`, body),
  },

  // QUERY_EDITOR.md: the server-side log of every run (`user=all` needs admin+; clear is owner-only).
  queryLog: {
    list: (pid: string, params: QueryLogParams) =>
      client.get<QueryLogPage>(`/projects/${e(pid)}/query-log`, { query: params }),
    get: (pid: string, runId: string) => client.get<QueryRun>(`/projects/${e(pid)}/query-log/${e(runId)}`),
    clear: (pid: string, before: string) =>
      client.del<{ deleted: number }>(`/projects/${e(pid)}/query-log`, { query: { before } }),
  },

  documents: {
    list: (pid: string, sid: string, collection: string, params: { filter?: string; limit: number; skip: number }) =>
      client.get<DocumentsResponse>(
        `/projects/${e(pid)}/data-sources/${e(sid)}/collections/${e(collection)}/documents`,
        { query: params },
      ),
    insert: (pid: string, sid: string, collection: string, document: JsonObject) =>
      client.post<{ document: JsonObject }>(
        `/projects/${e(pid)}/data-sources/${e(sid)}/collections/${e(collection)}/documents`,
        { document },
      ),
    update: (pid: string, sid: string, collection: string, docId: string, set: JsonObject, unset?: string[]) =>
      client.patch<{ document: JsonObject }>(
        `/projects/${e(pid)}/data-sources/${e(sid)}/collections/${e(collection)}/documents/${e(docId)}`,
        { set, unset },
      ),
    remove: (pid: string, sid: string, collection: string, docId: string) =>
      client.del<Ok>(`/projects/${e(pid)}/data-sources/${e(sid)}/collections/${e(collection)}/documents/${e(docId)}`),
  },

  // DEPLOYMENTS.md: apps built from a Git repo and served next to the project's databases.
  apps: {
    list: (pid: string) => client.get<App[]>(`/projects/${e(pid)}/apps`),
    create: (pid: string, body: AppInput) => client.post<AppCreated>(`/projects/${e(pid)}/apps`, body),
    detect: (pid: string, repo_url: string, branch?: string) =>
      client.post<AppDetectDraft>(`/projects/${e(pid)}/apps/detect`, branch ? { repo_url, branch } : { repo_url }),
    get: (pid: string, id: string) => client.get<App>(`/projects/${e(pid)}/apps/${e(id)}`),
    update: (pid: string, id: string, body: AppPatch) => client.patch<App>(`/projects/${e(pid)}/apps/${e(id)}`, body),
    remove: (pid: string, id: string) => client.del<{ job_id: string }>(`/projects/${e(pid)}/apps/${e(id)}`),
    env: (pid: string, id: string) => client.get<{ env: Record<string, string> }>(`/projects/${e(pid)}/apps/${e(id)}/env`),
    webhook: (pid: string, id: string) => client.get<AppWebhook>(`/projects/${e(pid)}/apps/${e(id)}/webhook`),
    rotateWebhook: (pid: string, id: string) => client.post<AppWebhook>(`/projects/${e(pid)}/apps/${e(id)}/webhook/rotate`),
    deploy: (pid: string, id: string, branch?: string) =>
      client.post<Deployment>(`/projects/${e(pid)}/apps/${e(id)}/deploy`, branch ? { branch } : {}),
    deployments: (pid: string, id: string, params: { limit?: number; before?: string } = {}) =>
      client.get<DeploymentPage>(`/projects/${e(pid)}/apps/${e(id)}/deployments`, { query: params }),
    deployment: (pid: string, id: string, dep: string, log = false) =>
      client.get<Deployment>(`/projects/${e(pid)}/apps/${e(id)}/deployments/${e(dep)}`, { query: { log: log ? 1 : undefined } }),
    cancel: (pid: string, id: string, dep: string) =>
      client.post<Deployment>(`/projects/${e(pid)}/apps/${e(id)}/deployments/${e(dep)}/cancel`),
    rollback: (pid: string, id: string, dep: string) =>
      client.post<Deployment>(`/projects/${e(pid)}/apps/${e(id)}/deployments/${e(dep)}/rollback`),
    logs: (pid: string, id: string, tail = 200) =>
      client.get<AppLogs>(`/projects/${e(pid)}/apps/${e(id)}/logs`, { query: { tail } }),
    addDomain: (pid: string, id: string, hostname: string) =>
      client.post<Domain>(`/projects/${e(pid)}/apps/${e(id)}/domains`, { hostname }),
    removeDomain: (pid: string, id: string, domainId: string) =>
      client.del<Ok>(`/projects/${e(pid)}/apps/${e(id)}/domains/${e(domainId)}`),
  },

  // DEPLOYMENTS.md "Connect a Git repository": the signed-in user's GitHub connection.
  github: {
    status: () => client.get<GitHubStatus>("/integrations/github"),
    connect: () => client.post<{ url: string }>("/integrations/github/connect"),
    disconnect: () => client.del<{ ok: true; apps_using_connection: number; message: string }>("/integrations/github"),
    repos: (q = "") => client.get<GitHubRepo[]>("/integrations/github/repos", { query: { q: q || undefined } }),
  },

  // COHOSTING.md: live copies of managed databases on members' own PCs, sync conflicts, per-key history.
  cohosting: {
    setMemberCohost: (pid: string, userId: string, canCohost: boolean) =>
      client.patch<Member>(`/projects/${e(pid)}/members/${e(userId)}`, { can_cohost: canCohost }),
    eligibility: (pid: string) => client.get<CohostEligibility>(`/projects/${e(pid)}/cohosting/eligibility`),
    replicas: (pid: string, sid: string) =>
      client.get<Replica[]>(`/projects/${e(pid)}/data-sources/${e(sid)}/replicas`),
    createReplica: (pid: string, sid: string, deviceId: string) =>
      client.post<Required<ReplicaResponse>>(`/projects/${e(pid)}/data-sources/${e(sid)}/replicas`, {
        device_id: deviceId,
      }),
    replicaAction: (pid: string, sid: string, rid: string, action: "pause" | "resume" | "recopy") =>
      client.post<ReplicaResponse>(`/projects/${e(pid)}/data-sources/${e(sid)}/replicas/${e(rid)}/${action}`),
    removeReplica: (pid: string, sid: string, rid: string, drop: boolean) =>
      client.del<Ok>(`/projects/${e(pid)}/data-sources/${e(sid)}/replicas/${e(rid)}`, { query: { drop } }),
    conflicts: (pid: string, sid: string, status: "open" | "resolved") =>
      client.get<SyncConflict[]>(`/projects/${e(pid)}/data-sources/${e(sid)}/sync-conflicts`, { query: { status } }),
    conflict: (pid: string, sid: string, cid: string) =>
      client.get<SyncConflict>(`/projects/${e(pid)}/data-sources/${e(sid)}/sync-conflicts/${e(cid)}`),
    resolve: (pid: string, sid: string, cid: string, body: { choice: ConflictChoice; value?: JsonObject | null }) =>
      client.post<SyncConflict>(`/projects/${e(pid)}/data-sources/${e(sid)}/sync-conflicts/${e(cid)}/resolve`, body),
    history: (pid: string, sid: string, table: string, key: JsonObject) =>
      client.get<SyncHistoryItem[]>(`/projects/${e(pid)}/data-sources/${e(sid)}/sync-history`, {
        query: { table, key: JSON.stringify(key) },
      }),
    restore: (pid: string, sid: string, body: { table: string; key: JsonObject; version_id: string }) =>
      client.post<{ ok: true; resolved_conflict_id: string | null }>(
        `/projects/${e(pid)}/data-sources/${e(sid)}/sync-history/restore`,
        body,
      ),
  },
};

export const qk = {
  setupStatus: ["setup-status"] as const,
  providers: ["auth-providers"] as const,
  me: ["me"] as const,
  instanceSettings: ["instance", "settings"] as const,
  instanceUsers: ["instance", "users"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["projects", id] as const,
  members: (id: string) => ["projects", id, "members"] as const,
  invites: (id: string) => ["projects", id, "invites"] as const,
  apiKeys: (id: string) => ["projects", id, "api-keys"] as const,
  dataSources: (id: string) => ["projects", id, "data-sources"] as const,
  schema: (id: string) => ["projects", id, "schema"] as const,
  /** Schema of one source (`?source_id=`); a prefix of `schema` so both invalidate together. */
  sourceSchema: (id: string, sid: string) => ["projects", id, "schema", "source", sid] as const,
  rows: (id: string, sid: string, table: string, params: object) =>
    ["projects", id, "rows", sid, table, params] as const,
  documents: (id: string, sid: string, coll: string, params: object) =>
    ["projects", id, "documents", sid, coll, params] as const,
  invite: (token: string) => ["invite", token] as const,
  devices: (scope: "mine" | "all") => ["devices", scope] as const,
  devicesAll: ["devices"] as const,
  enrollment: (code: string) => ["device-enrollment", code] as const,
  localDevice: ["device-local", "status"] as const,
  enrollStatus: ["device-local", "enroll-status"] as const,
  placement: (id: string) => ["projects", id, "placement-options"] as const,
  deletedSources: (id: string) => ["projects", id, "deleted-sources"] as const,
  backupsFor: (id: string, sid: string) => ["projects", id, "backups", sid] as const,
  backups: (id: string, sid: string) => ["projects", id, "backups", sid, "list"] as const,
  backupPolicy: (id: string, sid: string) => ["projects", id, "backups", sid, "policy"] as const,
  recoveryWindow: (id: string, sid: string) => ["projects", id, "backups", sid, "window"] as const,
  backupDiff: (id: string, sid: string, from: string, to: string) =>
    ["projects", id, "backups", sid, "diff", from, to] as const,
  backupSchema: (id: string, sid: string, backupId: string) =>
    ["projects", id, "backups", sid, "schema", backupId] as const,
  jobs: (id: string) => ["projects", id, "jobs"] as const,
  savedQueries: (id: string) => ["projects", id, "saved-queries"] as const,
  savedQueryVersions: (id: string, sqId: string) => ["projects", id, "saved-queries", sqId, "versions"] as const,
  savedQueryVersion: (id: string, sqId: string, n: number) => ["projects", id, "saved-queries", sqId, "versions", n] as const,
  /** Every log listing of one source (prefix of `queryLog`), invalidated after each run. */
  queryLogFor: (id: string, sid: string) => ["projects", id, "query-log", sid] as const,
  queryLog: (id: string, sid: string, user: "me" | "all") => ["projects", id, "query-log", sid, user] as const,
  job: (id: string, jobId: string) => ["projects", id, "jobs", jobId] as const,
  instanceBackups: ["instance", "backups"] as const,
  remoteAccess: ["instance", "remote-access"] as const,
  apps: (id: string) => ["projects", id, "apps"] as const,
  app: (id: string, appId: string) => ["projects", id, "apps", appId] as const,
  deployments: (id: string, appId: string) => ["projects", id, "apps", appId, "deployments"] as const,
  deployment: (id: string, appId: string, dep: string) => ["projects", id, "apps", appId, "deployments", dep] as const,
  appLogs: (id: string, appId: string) => ["projects", id, "apps", appId, "logs"] as const,
  github: ["integrations", "github"] as const,
  githubRepos: (q: string) => ["integrations", "github", "repos", q] as const,
  cohostEligibility: (id: string) => ["projects", id, "cohosting", "eligibility"] as const,
  /** Everything sync-related of one source (prefix of the keys below), invalidated after each resolve/restore. */
  syncFor: (id: string, sid: string) => ["projects", id, "sync", sid] as const,
  syncConflicts: (id: string, sid: string, status: "open" | "resolved") =>
    ["projects", id, "sync", sid, "conflicts", status] as const,
  syncConflict: (id: string, sid: string, cid: string) => ["projects", id, "sync", sid, "conflict", cid] as const,
  syncHistory: (id: string, sid: string, table: string, key: string) =>
    ["projects", id, "sync", sid, "history", table, key] as const,
};
