/**
 * Backend location. Order of precedence:
 *   1. the server URL the user saved in Profile → Server,
 *   2. VITE_API_BASE baked in at build time,
 *   3. a sensible per-platform default.
 */
import { runtime } from "./platform";

function platformDefault(): string {
  // `npm run dev` in a browser goes through the Vite proxy.
  if (runtime === "web" && import.meta.env.DEV) return "/api";
  // The Android emulator reaches the host machine on 10.0.2.2.
  if (runtime === "android") return "http://10.0.2.2:8000";
  return "http://127.0.0.1:8000";
}

export const DEFAULT_API_BASE: string = (import.meta.env.VITE_API_BASE || platformDefault()).replace(/\/+$/, "");

export function normalizeServerUrl(raw: string): string {
  let v = raw.trim().replace(/\/+$/, "");
  if (v && v !== "/api" && !/^https?:\/\//i.test(v)) v = `http://${v}`;
  return v;
}
