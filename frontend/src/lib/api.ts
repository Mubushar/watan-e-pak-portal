/**
 * Thin fetch wrapper around the Arz-e-Pak FastAPI backend.
 *
 * - Every call goes to `${API_BASE}${path}` (default `/api`, proxied by Vite).
 * - The bearer token from the auth store is attached automatically.
 * - GET requests fall back to the bundled snapshot (src/seed/snapshot.json)
 *   when the backend is unreachable, so the UI stays explorable offline.
 */
import { useAuth } from "@/store/auth";

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api";
const FORCE_SEED = import.meta.env.VITE_FORCE_SEED === "1";

export type Query = Record<string, string | number | boolean | null | undefined>;

export interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
  /** Return the raw text body instead of parsing JSON. */
  text?: boolean;
  /** Skip the offline snapshot fallback. */
  noFallback?: boolean;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

// ------------------------------------------------------------- connectivity
type Listener = (offline: boolean) => void;
let offline = FORCE_SEED;
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
    return () => listeners.delete(l);
  },
};

// ------------------------------------------------------------- snapshot
type Snapshot = { responses: Record<string, unknown>; seed_user_id?: string; generated_at: string };
let snapshotPromise: Promise<Snapshot> | null = null;
export function loadSnapshot(): Promise<Snapshot> {
  snapshotPromise ??= import("@/seed/snapshot.json").then((m) => (m.default ?? m) as unknown as Snapshot);
  return snapshotPromise;
}

async function fromSnapshot<T>(path: string): Promise<T | undefined> {
  const snap = await loadSnapshot();
  const [bare] = path.split("?");
  const hit = snap.responses[path] ?? snap.responses[bare];
  if (hit !== undefined) return structuredClone(hit) as T;
  // Detail-style routes: fall back to the closest collection entry.
  const m = bare.match(/^\/properties\/([^/]+)$/);
  if (m) {
    const list = (snap.responses["/properties"] as { results: { id: string }[] } | undefined)?.results ?? [];
    return (list.find((p) => p.id === m[1]) ?? list[0]) as T | undefined;
  }
  return undefined;
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

/** Absolute URL (through the proxy) — for <iframe>, <a target=_blank>, downloads. */
export function apiUrl(path: string, query?: Query) {
  return `${API_BASE}${buildUrl(path, query)}`;
}

function errorMessage(detail: unknown, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? `${(d as { loc?: unknown[] }).loc?.slice(-1)[0] ?? ""}: ${(d as { msg: string }).msg}` : String(d)))
      .join("; ");
  if (typeof detail === "object" && detail && "error" in detail) return String((detail as { error: unknown }).error);
  return fallback;
}

export async function api<T = any>(path: string, opts: ApiOptions = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined ? "POST" : "GET");
  const rel = buildUrl(path, opts.query);
  const canFallback = method === "GET" && !opts.noFallback && !opts.text;

  if (offline && FORCE_SEED && canFallback) {
    const s = await fromSnapshot<T>(rel);
    if (s !== undefined) return s;
  }

  const headers: Record<string, string> = { Accept: opts.text ? "text/html, */*" : "application/json" };
  const token = useAuth.getState().token;
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${rel}`, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    setOffline(true);
    if (canFallback) {
      const s = await fromSnapshot<T>(rel);
      if (s !== undefined) return s;
    }
    throw new ApiError("The portal backend is unreachable. Start it with `uv run python main.py` in backend/.", 0);
  }

  // Vite's proxy answers 502/504 (or 500 with an ECONNREFUSED body) when the backend is down.
  if ([502, 503, 504].includes(res.status) || (res.status === 500 && !res.headers.get("content-type")?.includes("json"))) {
    setOffline(true);
    if (canFallback) {
      const s = await fromSnapshot<T>(rel);
      if (s !== undefined) return s;
    }
    throw new ApiError("The portal backend is unreachable.", res.status);
  }
  setOffline(false);

  const ct = res.headers.get("content-type") ?? "";
  const payload: unknown = opts.text ? await res.text() : ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = typeof payload === "object" && payload && "detail" in payload ? (payload as { detail: unknown }).detail : payload;
    if (res.status === 401 && token) useAuth.getState().expire();
    throw new ApiError(errorMessage(detail, `${res.status} ${res.statusText}`), res.status, detail);
  }
  // Many engine functions report failures as a 200 with `{"error": "..."}`.
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const obj = payload as Record<string, unknown>;
    if (typeof obj.error === "string" && Object.keys(obj).length <= 2) throw new ApiError(obj.error, 422, obj);
  }
  return payload as T;
}

export const get = <T = any>(path: string, query?: Query, opts: Omit<ApiOptions, "query" | "method"> = {}) =>
  api<T>(path, { ...opts, query, method: "GET" });
export const post = <T = any>(path: string, body?: unknown, query?: Query) => api<T>(path, { method: "POST", body: body ?? {}, query });
export const put = <T = any>(path: string, body?: unknown, query?: Query) => api<T>(path, { method: "PUT", body: body ?? {}, query });
export const del = <T = any>(path: string, query?: Query) => api<T>(path, { method: "DELETE", query });

/** WebSocket URL through the dev proxy (ws://host/api/ws/...). */
export function wsUrl(path: string, query?: Query) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${API_BASE}${buildUrl(path, query)}`;
}
