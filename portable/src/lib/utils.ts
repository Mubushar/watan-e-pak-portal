import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Resolve a file in public/ relative to the app (works under Capacitor, Electron and Vite). */
export function asset(path: string): string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\//, "")}`;
}

/** True when the string contains Arabic-script (Urdu) characters. */
export function isUrdu(text: string): boolean {
  return /[\u0600-\u06FF]/.test(text);
}

/** Escape a value for HTML strings handed to Leaflet (tooltips, popups, divIcon html). */
export function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

/** A link target that is safe to render: http(s), mailto, tel, relative paths and #anchors only. */
export function safeHref(href: string | null | undefined): string | null {
  const h = (href ?? "").trim();
  if (!h) return null;
  // Ignore control characters / whitespace that browsers skip inside a scheme ("java\tscript:").
  // eslint-disable-next-line no-control-regex
  const probe = h.replace(/[\x00-\x20\x7f]+/g, "").toLowerCase();
  const scheme = probe.match(/^([a-z][a-z0-9+.-]*):/);
  if (!scheme) return probe.startsWith("//") ? `https:${h}` : h;
  return ["http", "https", "mailto", "tel"].includes(scheme[1]!) ? h : null;
}
