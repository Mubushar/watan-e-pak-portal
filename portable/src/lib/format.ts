/** Formatting helpers tuned for the Pakistani market (crore / lakh, marla / kanal). */

const CRORE = 10_000_000;
const LAKH = 100_000;

/** 45000000 -> "4.5 Crore"; 750000 -> "7.5 Lakh"; 9500 -> "9,500". */
export function pkrShort(v?: number | null, withPrefix = true): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  const p = withPrefix ? "PKR " : "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= CRORE) return `${p}${sign}${trim(a / CRORE)} Crore`;
  if (a >= LAKH) return `${p}${sign}${trim(a / LAKH)} Lakh`;
  return `${p}${sign}${Math.round(a).toLocaleString("en-PK")}`;
}

/** Full grouped amount: "PKR 45,000,000". */
export function pkr(v?: number | null, digits = 0): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return `PKR ${v.toLocaleString("en-PK", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
}

/** Compact international: 1.2M, 34K. */
export function compact(v?: number | null): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

export function num(v?: number | null, digits = 0): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-PK", { maximumFractionDigits: digits });
}

/** 0.1234 -> "12.3%"; pass `isFraction=false` when the value is already a percent. */
export function pct(v?: number | null, digits = 1, isFraction = true): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return `${(isFraction ? v * 100 : v).toFixed(digits)}%`;
}

function trim(n: number) {
  return n >= 100 ? Math.round(n).toString() : n.toFixed(2).replace(/\.?0+$/, "");
}

export function area(p: { marla_area?: number | null; kanal_area?: number | null; total_area?: number | null }): string {
  if (p.kanal_area && p.kanal_area >= 1) return `${trim(p.kanal_area)} Kanal`;
  if (p.marla_area) return `${trim(p.marla_area)} Marla`;
  if (p.total_area) return `${num(p.total_area)} sqft`;
  return "—";
}

export function titleCase(s?: string | null): string {
  if (!s) return "";
  return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function date(v?: string | null, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleDateString("en-GB", opts);
}

export function timeAgo(v?: string | null): string {
  if (!v) return "";
  const d = new Date(v).getTime();
  if (Number.isNaN(d)) return "";
  const s = Math.round((Date.now() - d) / 1000);
  const abs = Math.abs(s);
  const fmt = (n: number, u: string) => `${n}${u} ${s >= 0 ? "ago" : "from now"}`;
  if (abs < 60) return "just now";
  if (abs < 3600) return fmt(Math.round(abs / 60), "m");
  if (abs < 86400) return fmt(Math.round(abs / 3600), "h");
  if (abs < 86400 * 30) return fmt(Math.round(abs / 86400), "d");
  return date(v);
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}
