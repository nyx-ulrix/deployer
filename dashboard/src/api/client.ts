import type { ApiErrorBody, AuthResponse, User } from "./types";

/** An error returned by the Deployer API (`{error:{code,message,details}}`) or a network failure. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

/** Human-readable message for any thrown value. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong";
}

export type QueryValue = string | number | boolean | null | undefined;

export type RequestOptions = {
  body?: unknown;
  query?: Record<string, QueryValue>;
  /** Attach the bearer token and handle 401 → refresh → retry. Default true. */
  auth?: boolean;
  signal?: AbortSignal;
};

export type DownloadResult = { blob: Blob; filename: string };

export type SessionListener = (user: User | null) => void;

type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

export type ApiClientOptions = {
  baseUrl?: string;
  fetch?: FetchFn;
};

function isErrorBody(v: unknown): v is ApiErrorBody {
  if (typeof v !== "object" || v === null || !("error" in v)) return false;
  const err = (v as { error: unknown }).error;
  return typeof err === "object" && err !== null && "code" in err && "message" in err;
}

export async function parseError(res: Response): Promise<ApiError> {
  let body: unknown;
  try {
    const text = await res.text();
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (isErrorBody(body)) {
    return new ApiError(res.status, body.error.code, body.error.message, body.error.details ?? {});
  }
  // FastAPI default shape (e.g. {detail: "..."}) as a fallback.
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return new ApiError(res.status, codeForStatus(res.status), detail);
  }
  return new ApiError(res.status, codeForStatus(res.status), res.statusText || `Request failed (${res.status})`);
}

function codeForStatus(status: number): string {
  switch (status) {
    case 400:
      return "bad_request";
    case 401:
      return "unauthorized";
    case 403:
      return "forbidden";
    case 404:
      return "not_found";
    case 409:
      return "conflict";
    case 422:
      return "validation_error";
    case 429:
      return "rate_limited";
    default:
      return status >= 500 ? "server_error" : "http_error";
  }
}

/** Parse a filename from a Content-Disposition header (supports RFC 5987 `filename*`). */
export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*\s*=\s*(?:UTF-8|utf-8)?''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* fall through */
    }
  }
  const plain = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(header);
  if (plain) return (plain[2] ?? plain[1]).trim();
  return fallback;
}

export function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = options.baseUrl ?? "/v1";
  const doFetch: FetchFn = options.fetch ?? ((input, init) => fetch(input, init));

  let accessToken: string | null = null;
  let refreshInFlight: Promise<AuthResponse | null> | null = null;
  const listeners = new Set<SessionListener>();

  function emit(user: User | null) {
    for (const l of listeners) l(user);
  }

  function setSession(auth: AuthResponse | null) {
    accessToken = auth?.access_token ?? null;
    emit(auth?.user ?? null);
  }

  /** Exchange the HttpOnly refresh cookie for a new access token. Concurrent callers share one request. */
  function refresh(): Promise<AuthResponse | null> {
    if (!refreshInFlight) {
      refreshInFlight = (async () => {
        try {
          const res = await doFetch(`${baseUrl}/auth/refresh`, {
            method: "POST",
            credentials: "include",
            headers: { Accept: "application/json" },
          });
          if (!res.ok) {
            accessToken = null;
            emit(null);
            return null;
          }
          const auth = (await res.json()) as AuthResponse;
          setSession(auth);
          return auth;
        } catch {
          // Network error: keep whatever state we had, but report no session.
          return null;
        } finally {
          refreshInFlight = null;
        }
      })();
    }
    return refreshInFlight;
  }

  async function send(method: string, path: string, init: RequestInit, opts: RequestOptions): Promise<Response> {
    const auth = opts.auth ?? true;
    const url = `${baseUrl}${path}${buildQuery(opts.query)}`;

    const attempt = async (): Promise<Response> => {
      const headers = new Headers(init.headers);
      headers.set("Accept", headers.get("Accept") ?? "application/json");
      if (auth && accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
      try {
        return await doFetch(url, { ...init, method, headers, credentials: "include", signal: opts.signal });
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") throw e;
        throw new ApiError(0, "network_error", "Could not reach the Deployer API. Is it running?");
      }
    };

    if (auth && !accessToken && refreshInFlight) await refreshInFlight;

    let res = await attempt();
    if (res.status === 401 && auth) {
      const refreshed = await refresh();
      if (refreshed) res = await attempt();
    }
    return res;
  }

  async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const init: RequestInit = {};
    if (opts.body !== undefined) {
      init.body = JSON.stringify(opts.body);
      init.headers = { "Content-Type": "application/json" };
    }
    const res = await send(method, path, init, opts);
    if (!res.ok) throw await parseError(res);
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  async function upload<T>(path: string, form: FormData, opts: RequestOptions = {}): Promise<T> {
    const res = await send("POST", path, { body: form }, opts);
    if (!res.ok) throw await parseError(res);
    return (await res.json()) as T;
  }

  async function download(
    method: "GET" | "POST",
    path: string,
    fallbackName: string,
    opts: RequestOptions = {},
  ): Promise<DownloadResult> {
    const init: RequestInit = {};
    if (opts.body !== undefined) {
      init.body = JSON.stringify(opts.body);
      init.headers = { "Content-Type": "application/json", Accept: "*/*" };
    } else {
      init.headers = { Accept: "*/*" };
    }
    const res = await send(method, path, init, opts);
    if (!res.ok) throw await parseError(res);
    const blob = await res.blob();
    return { blob, filename: filenameFromDisposition(res.headers.get("Content-Disposition"), fallbackName) };
  }

  return {
    request,
    get: <T>(path: string, opts?: RequestOptions) => request<T>("GET", path, opts),
    post: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("POST", path, { ...opts, body }),
    put: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("PUT", path, { ...opts, body }),
    patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("PATCH", path, { ...opts, body }),
    del: <T>(path: string, opts?: RequestOptions) => request<T>("DELETE", path, opts),
    upload,
    download,
    refresh,
    setSession,
    getAccessToken: () => accessToken,
    clearSession: () => setSession(null),
    subscribe(listener: SessionListener): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** Trigger a browser download for a blob. */
export function saveBlob({ blob, filename }: DownloadResult): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const client = createApiClient();
