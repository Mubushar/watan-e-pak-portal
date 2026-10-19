import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Safely parse the JSON-string `output` fields that agent steps return. */
export function tryJson<T = unknown>(v: unknown): T | unknown {
  if (typeof v !== "string") return v;
  try {
    return JSON.parse(v) as T;
  } catch {
    return v;
  }
}

export function downloadText(filename: string, text: string, type = "text/plain") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
