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
  /** Called by the API client on a 401 for an authenticated request. */
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
      expire: () => set({ token: null, expiresAt: null, user: null }),
      can: (p) => {
        const u = get().user;
        if (!u) return false;
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

/** Seeded demo accounts from docs/USER_MANUAL.md §2.2. */
export const DEMO_ACCOUNTS = [
  { role: "Super admin", email: "admin@portal.pk", password: "Admin@12345" },
  { role: "Agent", email: "agent@portal.pk", password: "Agent@12345" },
  { role: "Finance", email: "finance@portal.pk", password: "Finance@12345" },
  { role: "Developer", email: "developer@portal.pk", password: "Developer@12345" },
  { role: "Investor", email: "investor@portal.pk", password: "Investor@12345" },
  { role: "Buyer", email: "bilal@example.com", password: "Buyer@12345" },
  { role: "Landlord", email: "landlord@portal.pk", password: "Landlord@12345" },
  { role: "Ad manager", email: "ads@portal.pk", password: "Ads@12345" },
];
