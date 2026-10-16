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
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      expiresAt: null,
      user: null,
      setSession: (s) => set({ token: s.token, expiresAt: s.expires_at ?? null, user: s.user }),
      setUser: (user) => set({ user }),
      logout: () => set({ token: null, expiresAt: null, user: null }),
    }),
    { name: "arzepak-app-auth" },
  ),
);

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
