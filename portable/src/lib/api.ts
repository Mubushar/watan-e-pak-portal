/**
 * Fetch wrapper around the Arz-e-Pak FastAPI backend (same API as the web portal).
 *
 * - Base URL comes from Profile → Server, else VITE_API_BASE, else a platform default.
 * - The bearer token from the auth store is attached automatically.
 * - On Android/iOS, Capacitor's native HTTP (CapacitorHttp) carries the request,
 *   so there is no CORS or mixed-content issue; desktop relies on backend CORS.
 * - Browse GETs fall back to a small bundled snapshot when the backend is down,
 *   so the app stays explorable offline.
 */
import { sessionExpired, useAuth } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { DEFAULT_API_BASE } from "./config";

export type Query = Record<string, string | number | boolean | null | undefined>;

export interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
  /** Skip the offline snapshot fallback. */
  noFallback?: boolean;
  timeoutMs?: number;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
  /** Machine-readable `code` from an auth-style error body, e.g. "email_taken". */
  get code(): string | undefined {
    const d = this.detail as { code?: string } | undefined;
    return typeof d === "object" && d ? d.code : undefined;
  }
}

export function apiBase(): string {
  return usePrefs.getState().serverUrl || DEFAULT_API_BASE;
}

// ------------------------------------------------------------- connectivity
type Listener = (offline: boolean) => void;
let offline = false;
const listeners = new Set<Listener>();
function setOffline(v: boolean) {
  if (v === offline) return;
  offline = v;
  listeners.forEach((l) => l(v));
}
export const connectivity = {
  get offline() {
    return offline;
  },
  subscribe(l: Listener) {
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  },
};

// ------------------------------------------------------------- snapshot
type Snapshot = { responses: Record<string, unknown> };
let snapshotPromise: Promise<Snapshot> | null = null;

async function fromSnapshot<T>(path: string, query?: Query): Promise<T | undefined> {
  snapshotPromise ??= import("@/seed/snapshot.json").then((m) => (m.default ?? m) as unknown as Snapshot);
  const snap = await snapshotPromise;
  const props = (snap.responses["/properties"] as { results: { id: string; featured?: boolean; category?: string; city_name?: string }[] } | undefined)?.results ?? [];
  if (path === "/search") {
    let r = props;
    if (query?.featured) r = r.filter((p) => p.featured);
    if (query?.category) r = r.filter((p) => p.category === query.category);
    if (query?.city) r = r.filter((p) => p.city_name?.toLowerCase() === String(query.city).toLowerCase());
    return { count: r.length, returned: r.length, results: r } as T;
  }
  const detail = path.match(/^\/properties\/([^/]+)$/);
  if (detail) return (props.find((p) => p.id === detail[1]) ?? undefined) as T | undefined;
  const hit = snap.responses[path];
  return hit === undefined ? undefined : (structuredClone(hit) as T);
}

// ------------------------------------------------------------- core
export function buildUrl(path: string, query?: Query) {
  const qs = new URLSearchParams();
  if (query)
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      qs.set(k, String(v));
    }
  const s = qs.toString();
  return `${path}${s ? (path.includes("?") ? "&" : "?") + s : ""}`;
}

function errorMessage(detail: unknown, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? `${(d as { loc?: unknown[] }).loc?.slice(-1)[0] ?? ""}: ${(d as { msg: string }).msg}` : String(d)))
      .join("; ");
  if (typeof detail === "object" && detail && "error" in detail) {
    // Our engine reports {"error": "..."}; OpenAI-style bodies are {"error": {"message": "..."}}.
    const err = (detail as { error: unknown }).error;
    if (typeof err === "object" && err && "message" in err) return String((err as { message: unknown }).message);
    return String(err);
  }
  return fallback;
}

export async function api<T = unknown>(path: string, opts: ApiOptions = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined ? "POST" : "GET");
  const rel = buildUrl(path, opts.query);
  const canFallback = method === "GET" && !opts.noFallback;

  const headers: Record<string, string> = { Accept: "application/json" };
  let token = useAuth.getState().token;
  // An expired session is a signed-out one: drop it rather than send a token the server will refuse.
  if (token && sessionExpired(useAuth.getState().expiresAt)) {
    useAuth.getState().expire();
    token = null;
  }
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 20_000);
  opts.signal?.addEventListener("abort", () => ctrl.abort());

  let res: Response;
  try {
    res = await fetch(`${apiBase()}${rel}`, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    if (opts.signal?.aborted) throw e;
    setOffline(true);
    if (canFallback) {
      const s = await fromSnapshot<T>(path, opts.query);
      if (s !== undefined) return s;
    }
    throw new ApiError(`Can't reach the Arz-e-Pak server (${apiBase()}). Check Profile → Server.`, 0);
  } finally {
    clearTimeout(timer);
  }

  // A gateway/proxy error page means the backend is down; a JSON error is the backend itself
  // reporting an upstream problem (e.g. OpenAI over quota) and its message should be shown.
  const isJson = (res.headers.get("content-type") ?? "").includes("json");
  if ([502, 503, 504].includes(res.status) && !isJson) {
    setOffline(true);
    if (canFallback) {
      const s = await fromSnapshot<T>(path, opts.query);
      if (s !== undefined) return s;
    }
    throw new ApiError("The Arz-e-Pak server is unavailable right now.", res.status);
  }
  setOffline(false);

  const ct = res.headers.get("content-type") ?? "";
  const payload: unknown = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = typeof payload === "object" && payload && "detail" in payload ? (payload as { detail: unknown }).detail : payload;
    if (res.status === 401 && token) useAuth.getState().expire();
    throw new ApiError(errorMessage(detail, `${res.status} ${res.statusText}`), res.status, detail);
  }
  // Many engine functions report failures as a 200 with `{"error": "..."}`.
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const obj = payload as Record<string, unknown>;
    if (typeof obj.error === "string" && Object.keys(obj).length <= 3) throw new ApiError(obj.error, 422, obj);
  }
  return payload as T;
}

export const get = <T = unknown>(path: string, query?: Query, opts: Omit<ApiOptions, "query" | "method"> = {}) =>
  api<T>(path, { ...opts, query, method: "GET" });
export const post = <T = unknown>(path: string, body?: unknown, opts: Omit<ApiOptions, "body" | "method"> = {}) =>
  api<T>(path, { ...opts, method: "POST", body: body ?? {} });
export const put = <T = unknown>(path: string, body?: unknown) => api<T>(path, { method: "PUT", body: body ?? {} });
export const del = <T = unknown>(path: string) => api<T>(path, { method: "DELETE" });
