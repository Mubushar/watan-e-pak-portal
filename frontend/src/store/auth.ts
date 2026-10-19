import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface User {
  id: string;
  name: string | null;
  email: string | null;
  mobile: string | null;
  role: string;
  roles: string[];
  permissions: string[];
  status: string;
  verified: boolean;
  agent_id?: string | null;
  customer_id?: string | null;
  last_login_at?: string | null;
  /** A staff role (agent / developer) asked for at sign-up, waiting for an administrator. */
  requested_role?: string | null;
}

export interface Session {
  token: string;
  expires_at?: string;
  user: User;
}

interface AuthState {
  token: string | null;
  expiresAt: string | null;
  user: User | null;
  setSession: (s: Session) => void;
  setUser: (u: User) => void;
  logout: () => void;
  /** Called by the API client on a 401 for an authenticated request, and when the token's expiry passes. */
  expire: () => void;
  can: (permission: string) => boolean;
  hasRole: (...roles: string[]) => boolean;
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      expiresAt: null,
      user: null,
      setSession: (s) => set({ token: s.token, expiresAt: s.expires_at ?? null, user: s.user }),
      setUser: (user) => set({ user }),
      logout: () => set({ token: null, expiresAt: null, user: null }),
      expire: () => {
        if (!get().token) return;
        set({ token: null, expiresAt: null, user: null });
        expiryListeners.forEach((l) => l());
      },
      can: (p) => {
        const u = get().user;
        if (!u || sessionExpired(get().expiresAt)) return false;
        return u.roles?.includes("super_admin") || u.permissions?.includes(p);
      },
      hasRole: (...roles) => {
        const u = get().user;
        return !!u && roles.some((r) => u.roles?.includes(r) || u.role === r);
      },
    }),
    { name: "arzepak-auth" },
  ),
);

/** True once the session's `expires_at` has passed (the token is then treated as signed out). */
export function sessionExpired(expiresAt: string | null | undefined): boolean {
  if (!expiresAt) return false;
  const t = Date.parse(expiresAt);
  return Number.isFinite(t) && t <= Date.now();
}

const expiryListeners = new Set<() => void>();
/** Run `l` whenever a signed-in session ends on its own (401 from the API, or the token expired). */
export function onSessionExpired(l: () => void): () => void {
  expiryListeners.add(l);
  return () => {
    expiryListeners.delete(l);
  };
}

// Sign out when the stored token's expiry passes (also right away for an already-expired stored session).
let expiryTimer: ReturnType<typeof setTimeout> | undefined;
function scheduleExpiry(expiresAt: string | null) {
  clearTimeout(expiryTimer);
  if (!expiresAt) return;
  const ms = Date.parse(expiresAt) - Date.now();
  if (!Number.isFinite(ms)) return;
  if (ms <= 0) useAuth.getState().expire();
  else expiryTimer = setTimeout(() => useAuth.getState().expire(), Math.min(ms, 2 ** 31 - 1));
}
scheduleExpiry(useAuth.getState().expiresAt);
useAuth.subscribe((s, prev) => {
  if (s.expiresAt !== prev.expiresAt) scheduleExpiry(s.expiresAt);
});

/** A seeded demo account, as listed by `GET /auth/config` → `demo_accounts` (only where the server seeds them). */
export interface DemoAccount {
  email: string;
  password?: string;
  role?: string;
  label?: string;
  name?: string;
}

/** The demo accounts to offer on the sign-in page: only a non-empty list from the server counts. */
export function demoAccountsFrom(cfg: { demo_accounts?: unknown } | undefined): DemoAccount[] {
  const list = cfg?.demo_accounts;
  if (!Array.isArray(list)) return [];
  return list.filter((a): a is DemoAccount => !!a && typeof a === "object" && typeof (a as DemoAccount).email === "string");
}
