import { useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { ChevronRight, Copy, TrendingDown, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ StatCard
export function StatCard({
  label,
  value,
  icon,
  hint,
  delta,
  tone = "green",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  icon?: ReactNode;
  hint?: ReactNode;
  /** Positive/negative change, shown with an arrow (already formatted or a number in %). */
  delta?: number | string;
  tone?: "green" | "gold" | "blue" | "red" | "purple";
  className?: string;
}) {
  const ring = {
    green: "from-brand-500/15 text-brand-700 dark:text-brand-200",
    gold: "from-gold-400/20 text-gold-700 dark:text-gold-200",
    blue: "from-sky-400/20 text-sky-700 dark:text-sky-200",
    red: "from-red-400/20 text-red-700 dark:text-red-200",
    purple: "from-violet-400/20 text-violet-700 dark:text-violet-200",
  }[tone];
  const up = typeof delta === "number" ? delta >= 0 : typeof delta === "string" ? !delta.trim().startsWith("-") : true;
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("card relative overflow-hidden p-5", className)}>
      <div className={cn("pointer-events-none absolute -end-8 -top-8 h-28 w-28 rounded-full bg-gradient-to-br to-transparent", ring)} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-slate-400">{label}</p>
          <p className="mt-2 truncate font-display text-2xl font-bold text-ink dark:text-white">{value}</p>
        </div>
        {icon && <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br", ring)}>{icon}</span>}
      </div>
      {(hint || delta !== undefined) && (
        <div className="mt-3 flex items-center gap-2 text-xs">
          {delta !== undefined && (
            <span className={cn("inline-flex items-center gap-0.5 font-semibold", up ? "text-emerald-600" : "text-red-600")}>
              {up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {typeof delta === "number" ? `${Math.abs(delta).toFixed(1)}%` : delta}
            </span>
          )}
          {hint && <span className="text-ink-mute dark:text-slate-400">{hint}</span>}
        </div>
      )}
    </motion.div>
  );
}

// ------------------------------------------------------------------ JsonView
/** Collapsible pretty-printer for arbitrary JSON (agent outputs, MCP results). */
export function JsonView({ data, depth = 0, name, defaultOpen = 1 }: { data: unknown; depth?: number; name?: string; defaultOpen?: number }) {
  const [open, setOpen] = useState(depth < defaultOpen);
  const isObj = data !== null && typeof data === "object";
  const keyEl = name !== undefined && <span className="text-brand-700 dark:text-brand-300">{name}: </span>;
  if (!isObj) {
    const cls = typeof data === "number" ? "text-sky-700 dark:text-sky-300" : typeof data === "boolean" ? "text-violet-700 dark:text-violet-300" : data === null ? "text-slate-400" : "text-gold-700 dark:text-gold-300";
    return (
      <div className="font-mono text-xs leading-6">
        {keyEl}
        <span className={cls}>{typeof data === "string" ? `"${data}"` : String(data)}</span>
      </div>
    );
  }
  const entries = Array.isArray(data) ? data.map((v, i) => [String(i), v] as const) : Object.entries(data as Record<string, unknown>);
  return (
    <div className="font-mono text-xs leading-6">
      <button type="button" onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 hover:text-brand-700">
        <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
        {keyEl}
        <span className="text-ink-mute">{Array.isArray(data) ? `[${entries.length}]` : `{${entries.length}}`}</span>
      </button>
      {open && (
        <div className="ms-3 border-s border-black/10 ps-3 dark:border-white/10">
          {entries.slice(0, 200).map(([k, v]) => (
            <JsonView key={k} name={k} data={v} depth={depth + 1} defaultOpen={defaultOpen} />
          ))}
          {entries.length > 200 && <div className="text-ink-mute">… {entries.length - 200} more</div>}
        </div>
      )}
    </div>
  );
}

export function CopyButton({ text, className }: { text: string; className?: string }) {
  return (
    <button
      type="button"
      className={cn("btn btn-ghost btn-sm", className)}
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => toast.success("Copied"));
      }}
    >
      <Copy className="h-3.5 w-3.5" /> Copy
    </button>
  );
}

/** Horizontal labelled bar list — quick breakdowns without a chart library. */
export function BarList({ items, format = (v) => String(v), tone = "green" }: { items: { label: ReactNode; value: number }[]; format?: (v: number) => string; tone?: "green" | "gold" }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="space-y-2.5">
      {items.map((it, i) => (
        <div key={i}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="font-medium text-ink-soft dark:text-slate-300">{it.label}</span>
            <span className="font-semibold tabular-nums">{format(it.value)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(it.value / max) * 100}%` }}
              transition={{ duration: 0.8, delay: i * 0.05 }}
              className={cn("h-full rounded-full", tone === "green" ? "bg-gradient-to-r from-brand-600 to-brand-400" : "bg-gold-gradient")}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
