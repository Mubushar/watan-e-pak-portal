import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";

// ------------------------------------------------------------------ Button
export type ButtonVariant = "primary" | "gold" | "outline" | "ghost" | "soft" | "danger";
export type ButtonSize = "sm" | "md" | "lg" | "icon";

const variantClass: Record<ButtonVariant, string> = {
  primary: "btn-primary",
  gold: "btn-gold",
  outline: "btn-outline",
  ghost: "btn-ghost",
  soft: "btn-soft",
  danger: "btn-danger",
};
const sizeClass: Record<ButtonSize, string> = { sm: "btn-sm", md: "", lg: "btn-lg", icon: "btn-icon" };

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} className={cn("btn", variantClass[variant], sizeClass[size], className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export function ButtonLink({
  variant = "primary",
  size = "md",
  icon,
  className,
  children,
  ...rest
}: LinkProps & { variant?: ButtonVariant; size?: ButtonSize; icon?: ReactNode }) {
  return (
    <Link className={cn("btn", variantClass[variant], sizeClass[size], className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

// ------------------------------------------------------------------ Badge
export type Tone = "green" | "gold" | "red" | "blue" | "gray" | "purple" | "orange";
const toneClass: Record<Tone, string> = {
  green: "bg-brand-50 text-brand-700 ring-brand-600/15 dark:bg-brand-500/15 dark:text-brand-200",
  gold: "bg-gold-50 text-gold-700 ring-gold-600/20 dark:bg-gold-500/15 dark:text-gold-200",
  red: "bg-red-50 text-red-700 ring-red-600/15 dark:bg-red-500/15 dark:text-red-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-600/15 dark:bg-sky-500/15 dark:text-sky-200",
  gray: "bg-slate-100 text-slate-700 ring-slate-600/10 dark:bg-white/10 dark:text-slate-300",
  purple: "bg-violet-50 text-violet-700 ring-violet-600/15 dark:bg-violet-500/15 dark:text-violet-200",
  orange: "bg-orange-50 text-orange-700 ring-orange-600/15 dark:bg-orange-500/15 dark:text-orange-200",
};

export function Badge({ tone = "green", className, children, icon }: { tone?: Tone; className?: string; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={cn("chip ring-1 ring-inset", toneClass[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

/** Pick a tone for common status words (active, overdue, red, won, …). */
export function toneFor(status?: string | null): Tone {
  const s = (status ?? "").toLowerCase();
  if (/(active|done|paid|won|completed|green|positive|approved|healthy|online|closed_won|listed|available|live|ok)/.test(s)) return "green";
  if (/(overdue|red|negative|failed|lost|rejected|urgent|critical|high_risk|cancel|bad)/.test(s)) return "red";
  if (/(amber|pending|awaiting|warning|soon|negotiation|proposal|draft|partial|medium|watch)/.test(s)) return "gold";
  if (/(new|open|planned|sent|info|prospecting|routine|neutral)/.test(s)) return "blue";
  if (/(under_construction|in_progress|progress|running)/.test(s)) return "orange";
  return "gray";
}

export function StatusBadge({ status, className }: { status?: string | null; className?: string }) {
  return (
    <Badge tone={toneFor(status)} className={className}>
      {(status ?? "—").replace(/_/g, " ")}
    </Badge>
  );
}

// ------------------------------------------------------------------ Avatar
const AVATAR_BG = ["bg-brand-600", "bg-gold-500", "bg-sky-600", "bg-violet-600", "bg-rose-600", "bg-teal-600", "bg-orange-500"];
export function Avatar({ name, size = 36, className, online }: { name?: string | null; size?: number; className?: string; online?: boolean }) {
  const idx = [...(name ?? "?")].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_BG.length;
  return (
    <span className={cn("relative inline-flex shrink-0", className)} style={{ width: size, height: size }}>
      <span
        className={cn("inline-flex h-full w-full items-center justify-center rounded-full font-semibold text-white", AVATAR_BG[idx])}
        style={{ fontSize: size * 0.38 }}
      >
        {initials(name)}
      </span>
      {online !== undefined && (
        <span className={cn("absolute bottom-0 end-0 h-2.5 w-2.5 rounded-full ring-2 ring-white dark:ring-[#0d1f16]", online ? "bg-emerald-500" : "bg-slate-400")} />
      )}
    </span>
  );
}

// ------------------------------------------------------------------ Skeleton / Spinner
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("relative overflow-hidden rounded-xl bg-black/5 dark:bg-white/5", className)}>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/50 to-transparent dark:via-white/10" />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-brand-600", className)} />;
}

// ------------------------------------------------------------------ Progress / ScoreRing
export function Progress({ value, max = 100, tone = "green", className }: { value: number; max?: number; tone?: "green" | "gold" | "red" | "blue"; className?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const bar = { green: "bg-brand-600", gold: "bg-gold-500", red: "bg-red-500", blue: "bg-sky-500" }[tone];
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-black/5 dark:bg-white/10", className)}>
      <div className={cn("h-full rounded-full transition-all duration-700", bar)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ScoreRing({ value, size = 84, label, stroke = 8 }: { value: number; size?: number; label?: string; stroke?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value));
  const color = v >= 70 ? "#146f45" : v >= 45 ? "#c99a22" : "#dc2626";
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} className="fill-none stroke-black/5 dark:stroke-white/10" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          fill="none"
          stroke={color}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (v / 100) * c}
          style={{ transition: "stroke-dashoffset .8s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-lg font-bold leading-none text-ink dark:text-white">{Math.round(v)}</span>
        {label && <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-mute">{label}</span>}
      </div>
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}
