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
  email_verified?: boolean;
  mobile_verified?: boolean;
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
  /** The session ended on its own: a 401 from the API, or the token's expiry passed. */
  expire: () => void;
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
    }),
    { name: "watanepak-app-auth" },
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

/** Roles a person can pick when creating an account (subset of backend SIGNUP_ROLES). */
export const SIGNUP_ROLES = [
  { value: "buyer", label: "Buyer", hint: "Find a home or plot" },
  { value: "seller", label: "Seller", hint: "Sell your property" },
  { value: "investor", label: "Investor", hint: "Grow your portfolio" },
  { value: "agent", label: "Agent", hint: "List & manage clients" },
  { value: "landlord", label: "Landlord", hint: "Rent out property" },
  { value: "tenant", label: "Tenant", hint: "Find a place to rent" },
] as const;

export type SignupRole = (typeof SIGNUP_ROLES)[number]["value"];

export function roleLabel(role?: string | null): string {
  if (!role) return "Member";
  return SIGNUP_ROLES.find((r) => r.value === role)?.label ?? role.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
