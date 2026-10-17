/**
 * Small building blocks shared by the business-ops dashboard pages
 * (Overview, CRM, Accounting, Transactions, Leasing, Maintenance, Marketing).
 */
import { useEffect, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Check, Star } from "lucide-react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardHeader, Skeleton } from "@/components/ui";

/**
 * Many backend write routes answer 200/201 with `{"error": "..."}` instead of a 4xx.
 * Pipe write results through this so useMutate surfaces them as error toasts.
 */
export function ensure<T>(res: T): T {
  if (res && typeof res === "object" && "error" in (res as object)) {
    const e = (res as { error?: unknown }).error;
    if (e) throw new ApiError(String(e), 400, res);
  }
  return res;
}

/** Parse a form string into a number, or undefined when blank / invalid. */
export function numOr(v: string | number | undefined | null, fallback?: number): number | undefined {
  if (v === "" || v === undefined || v === null) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/** ISO date (yyyy-mm-dd) offset from today. */
export function isoDay(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

/** Tiny form-state helper: const [f, set] = useFormState({...}); set("name")(value). */
export function useFormState<T extends Record<string, unknown>>(initial: T) {
  const [state, setState] = useState<T>(initial);
  const set =
    <K extends keyof T>(k: K) =>
    (v: T[K]) =>
      setState((s) => ({ ...s, [k]: v }));
  const reset = () => setState(initial);
  return [state, set, reset, setState] as const;
}

/** A Card with a header and padded body. */
export function Panel({
  title,
  subtitle,
  icon,
  action,
  children,
  className,
  bodyClass,
  flush,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
  /** No body padding (tables, lists). */
  flush?: boolean;
}) {
  return (
    <Card className={cn("flex min-w-0 flex-col overflow-hidden", className)}>
      <CardHeader title={title} subtitle={subtitle} icon={icon} action={action} />
      <div className={cn("min-w-0 flex-1", !flush && "p-5", bodyClass)}>{children}</div>
    </Card>
  );
}

/** Compact metric for use inside cards / drawers. */
export function MiniStat({
  label,
  value,
  hint,
  tone = "default",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "green" | "gold" | "red" | "blue";
  className?: string;
}) {
  const t = {
    default: "text-ink dark:text-white",
    green: "text-brand-700 dark:text-brand-300",
    gold: "text-gold-700 dark:text-gold-300",
    red: "text-red-600 dark:text-red-400",
    blue: "text-sky-700 dark:text-sky-300",
  }[tone];
  return (
    <div className={cn("min-w-0 rounded-xl border border-black/5 bg-white/60 px-3 py-2.5 dark:border-white/10 dark:bg-white/[.03]", className)}>
      <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-ink-mute dark:text-slate-400">{label}</p>
      <p className={cn("mt-0.5 truncate font-display text-lg font-bold tabular-nums", t)}>{value}</p>
      {hint && <p className="truncate text-[11px] text-ink-mute dark:text-slate-400">{hint}</p>}
    </div>
  );
}

export function Stars({ value, max = 5, className }: { value: number; max?: number; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-0.5", className)} aria-label={`${value} of ${max}`}>
      {Array.from({ length: max }, (_, i) => {
        const fill = Math.max(0, Math.min(1, value - i));
        return (
          <span key={i} className="relative inline-block h-3.5 w-3.5">
            <Star className="absolute inset-0 h-3.5 w-3.5 text-black/10 dark:text-white/15" fill="currentColor" strokeWidth={0} />
            <span className="absolute inset-y-0 start-0 overflow-hidden" style={{ width: `${fill * 100}%` }}>
              <Star className="h-3.5 w-3.5 text-gold-500" fill="currentColor" strokeWidth={0} />
            </span>
          </span>
        );
      })}
    </span>
  );
}

/** Horizontal stage stepper (dots + connecting bars). */
export function Stepper({ steps, current, compact }: { steps: string[]; current: number; compact?: boolean }) {
  return (
    <div className="flex w-full items-center">
      {steps.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={s} className={cn("flex items-center", i < steps.length - 1 && "flex-1")}>
            <div className="group relative flex flex-col items-center">
              <span
                className={cn(
                  "flex items-center justify-center rounded-full border-2 transition-colors",
                  compact ? "h-4 w-4" : "h-6 w-6",
                  done && "border-brand-600 bg-brand-600 text-white",
                  active && "border-gold-500 bg-gold-50 text-gold-700 ring-4 ring-gold-400/20 dark:bg-gold-500/20",
                  !done && !active && "border-black/10 bg-white dark:border-white/15 dark:bg-white/5",
                )}
              >
                {done && <Check className={compact ? "h-2.5 w-2.5" : "h-3.5 w-3.5"} strokeWidth={3} />}
                {active && <span className={cn("rounded-full bg-gold-500", compact ? "h-1.5 w-1.5" : "h-2 w-2")} />}
              </span>
              <span className="pointer-events-none absolute top-full z-10 mt-1 hidden whitespace-nowrap rounded-md bg-brand-950 px-2 py-0.5 text-[10px] font-semibold text-white group-hover:block">
                {s.replace(/_/g, " ")}
              </span>
            </div>
            {i < steps.length - 1 && <span className={cn("mx-1 h-0.5 flex-1 rounded-full", i < current ? "bg-brand-600" : "bg-black/10 dark:bg-white/10")} />}
          </div>
        );
      })}
    </div>
  );
}

/** A grid of skeleton tiles, for loading states of card grids. */
export function SkeletonGrid({ n = 4, className, tile = "h-28" }: { n?: number; className?: string; tile?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-4", className)}>
      {Array.from({ length: n }, (_, i) => (
        <Skeleton key={i} className={tile} />
      ))}
    </div>
  );
}

/** Thin horizontal score bar with the number alongside. */
export function ScoreBar({ value, max = 100, className }: { value: number; max?: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = pct >= 70 ? "from-brand-600 to-brand-400" : pct >= 45 ? "from-gold-600 to-gold-400" : "from-red-600 to-red-400";
  return (
    <div className={cn("flex min-w-[96px] items-center gap-2", className)}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.6 }} className={cn("h-full rounded-full bg-gradient-to-r", color)} />
      </div>
      <span className="w-7 text-end text-xs font-semibold tabular-nums">{Math.round(value)}</span>
    </div>
  );
}

/** Tone for "hot/warm/cool/cold" and "urgent/high/normal" style bands. */
export function bandTone(band?: string | null): "red" | "gold" | "blue" | "gray" | "green" | "orange" {
  switch ((band ?? "").toLowerCase()) {
    case "urgent":
    case "hot":
    case "critical":
    case "emergency":
      return "red";
    case "high":
    case "warm":
    case "soon":
      return "orange";
    case "medium":
    case "cool":
    case "normal":
      return "gold";
    case "low":
    case "cold":
    case "routine":
      return "blue";
    default:
      return "gray";
  }
}

/** Staggered entrance for grids. */
export const stagger = {
  container: { hidden: {}, show: { transition: { staggerChildren: 0.05 } } },
  item: { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } },
};

/** Labelled form grid wrapper. */
export function FormGrid({ children, cols = 2, className }: { children: ReactNode; cols?: 1 | 2 | 3; className?: string }) {
  return <div className={cn("grid gap-4", cols === 2 && "sm:grid-cols-2", cols === 3 && "sm:grid-cols-3", className)}>{children}</div>;
}

/**
 * Open an HTML string in a new tab via a Blob URL (printable reports).
 * Pass a window opened synchronously in the click handler (`window.open("", "_blank")`)
 * to dodge popup blockers when the HTML arrives asynchronously.
 */
export function openHtml(html: string, target?: Window | null) {
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  if (target && !target.closed) target.location.href = url;
  else window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Debounce a value (for calculators that hit the API as you type). */
export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  // Compare structurally so inline objects don't retrigger the timer every render.
  const key = JSON.stringify(value);
  useEffect(() => {
    const t = setTimeout(() => setV(JSON.parse(key) as T), ms);
    return () => clearTimeout(t);
  }, [key, ms]);
  return v;
}

/** Axis-friendly PKR: 45000000 -> "4.5 Cr", 750000 -> "7.5 L", 9500 -> "9.5K". */
export function crShort(v: number): string {
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  const t = (n: number) => (n >= 100 ? Math.round(n).toString() : n.toFixed(1).replace(/\.0$/, ""));
  if (a >= 10_000_000) return `${sign}${t(a / 10_000_000)} Cr`;
  if (a >= 100_000) return `${sign}${t(a / 100_000)} L`;
  if (a >= 1000) return `${sign}${t(a / 1000)}K`;
  return `${sign}${Math.round(a)}`;
}

/** "personal outreach this week" -> "Personal outreach this week". */
export function sentence(s?: string | null): string {
  if (!s) return "";
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Compact money for KPI tiles: 575500000 -> "Rs 57.6 Cr"… kept short so it never truncates. */
export function rs(v?: number | null): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  const t = (n: number) => (n >= 100 ? Math.round(n).toLocaleString("en-PK") : n.toFixed(n >= 10 ? 1 : 2).replace(/\.?0+$/, ""));
  if (a >= 10_000_000) return `Rs ${sign}${t(a / 10_000_000)} Crore`;
  if (a >= 100_000) return `Rs ${sign}${t(a / 100_000)} Lakh`;
  return `Rs ${sign}${Math.round(a).toLocaleString("en-PK")}`;
}
