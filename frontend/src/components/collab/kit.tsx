/**
 * Small shared helpers for the collaboration / delivery / admin screens
 * (PMO, messaging, ads, construction, admin, profile, content pages).
 */
import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Many backend business functions answer HTTP 200 with `{ "error": "…" }`.
 * Wrap a write call with `ok(...)` so `useMutate` treats it as a failure (and toasts it).
 */
export async function ok<T>(p: Promise<T>): Promise<T> {
  const res = await p;
  if (res && typeof res === "object" && !Array.isArray(res) && "error" in (res as object)) {
    const err = (res as unknown as { error: unknown }).error;
    if (err) throw new ApiError(typeof err === "string" ? err : JSON.stringify(err), 200, err);
  }
  return res;
}

/** True when a GET answered `{error: …}` instead of data. */
export function apiErr(d: unknown): string | null {
  if (d && typeof d === "object" && "error" in (d as object)) {
    const e = (d as { error: unknown }).error;
    if (e) return typeof e === "string" ? e : JSON.stringify(e);
  }
  return null;
}

// ------------------------------------------------------------------ RAG
export type Rag = "green" | "amber" | "red" | string;
export const RAG_HEX: Record<string, string> = { green: "#1b9e4b", amber: "#e6a100", red: "#d81f2a", gray: "#94a3b8" };

export function ragClasses(r?: Rag | null) {
  switch (r) {
    case "green":
      return "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/15 dark:text-emerald-200";
    case "amber":
      return "bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/15 dark:text-amber-200";
    case "red":
      return "bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-500/15 dark:text-red-200";
    default:
      return "bg-slate-100 text-slate-700 ring-slate-600/10 dark:bg-white/10 dark:text-slate-300";
  }
}

export function RagPill({ rag, label, className }: { rag?: Rag | null; label?: ReactNode; className?: string }) {
  return (
    <span className={cn("chip ring-1 ring-inset capitalize", ragClasses(rag), className)}>
      <span className="h-2 w-2 rounded-full" style={{ background: RAG_HEX[rag ?? "gray"] ?? RAG_HEX.gray }} />
      {label ?? rag ?? "—"}
    </span>
  );
}

// ------------------------------------------------------------------ Ring
export function Ring({ value, size = 64, stroke = 7, color = "#146f45", children }: { value: number; size?: number; stroke?: number; color?: string; children?: ReactNode }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value || 0));
  return (
    <div className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} className="fill-none stroke-black/5 dark:stroke-white/10" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          fill="none"
          stroke={color}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - (v / 100) * c }}
          transition={{ duration: 0.9, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children ?? <span className="text-sm font-bold">{Math.round(v)}%</span>}</div>
    </div>
  );
}

// ------------------------------------------------------------------ Accordion
export function Accordion({
  items,
  defaultOpen = 0,
  className,
}: {
  items: { title: ReactNode; content: ReactNode; icon?: ReactNode; meta?: ReactNode }[];
  defaultOpen?: number | null;
  className?: string;
}) {
  const [open, setOpen] = useState<number | null>(defaultOpen);
  return (
    <div className={cn("divide-y divide-black/5 overflow-hidden rounded-2xl border border-black/5 bg-white/60 dark:divide-white/10 dark:border-white/10 dark:bg-white/[.03]", className)}>
      {items.map((it, i) => {
        const isOpen = open === i;
        return (
          <div key={i}>
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : i)}
              className={cn("flex w-full items-center gap-3 px-5 py-4 text-start transition hover:bg-brand-50/60 dark:hover:bg-white/5", isOpen && "bg-brand-50/40 dark:bg-white/5")}
              aria-expanded={isOpen}
            >
              {it.icon && <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">{it.icon}</span>}
              <span className="min-w-0 flex-1 font-semibold text-ink dark:text-white">{it.title}</span>
              {it.meta}
              <ChevronDown className={cn("h-4 w-4 shrink-0 text-ink-mute transition-transform", isOpen && "rotate-180")} />
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.25 }} className="overflow-hidden">
                  <div className="px-5 pb-5 pt-1 text-sm text-ink-soft dark:text-slate-300">{it.content}</div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ misc
/** Gradient hero strip for dashboard pages. */
export function GlowPanel({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("relative overflow-hidden rounded-3xl bg-brand-gradient p-6 text-white shadow-soft", className)}>
      <div className="pointer-events-none absolute -end-16 -top-16 h-56 w-56 rounded-full bg-gold-400/25 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-20 start-10 h-48 w-48 rounded-full bg-emerald-300/20 blur-3xl" />
      <div className="relative">{children}</div>
    </div>
  );
}

export function Chip({ active, onClick, children, className }: { active?: boolean; onClick?: () => void; children: ReactNode; className?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition",
        active
          ? "border-brand-700 bg-brand-700 text-white shadow-soft dark:border-brand-500 dark:bg-brand-600"
          : "border-black/10 bg-white text-ink-soft hover:border-brand-300 hover:text-brand-800 dark:border-white/10 dark:bg-white/5 dark:text-slate-300",
        className,
      )}
    >
      {children}
    </button>
  );
}

/** Stagger container for card grids. */
export const stagger = {
  container: { hidden: {}, show: { transition: { staggerChildren: 0.05 } } },
  item: { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } },
};

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}
