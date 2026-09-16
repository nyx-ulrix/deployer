import { client } from "./client";
import type {
  ApiKey,
  ApiKeyCreateResponse,
  ApiKeyRole,
  AuthResponse,
  ConnectionDetails,
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
  rows: (id: string, sid: string, table: string, params: object) =>
    ["projects", id, "rows", sid, table, params] as const,
  documents: (id: string, sid: string, coll: string, params: object) =>
    ["projects", id, "documents", sid, coll, params] as const,
  invite: (token: string) => ["invite", token] as const,
};
