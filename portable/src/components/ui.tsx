/** UI kit — same classes and variants as the web portal's components/ui, sized for touch. */
import { forwardRef, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";
import { BRAND } from "@/lib/images";

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

// ------------------------------------------------------------------ Badge
export type Tone = "green" | "gold" | "red" | "blue" | "gray";
const toneClass: Record<Tone, string> = {
  green: "bg-brand-50 text-brand-700 ring-brand-600/15 dark:bg-brand-500/15 dark:text-brand-200",
  gold: "bg-gold-50 text-gold-700 ring-gold-600/20 dark:bg-gold-500/15 dark:text-gold-200",
  red: "bg-red-50 text-red-700 ring-red-600/15 dark:bg-red-500/15 dark:text-red-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-600/15 dark:bg-sky-500/15 dark:text-sky-200",
  gray: "bg-slate-100 text-slate-700 ring-slate-600/10 dark:bg-white/10 dark:text-slate-300",
};

export function Badge({ tone = "green", className, children, icon }: { tone?: Tone; className?: string; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={cn("chip ring-1 ring-inset", toneClass[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

export function statusTone(status?: string | null): Tone {
  const s = (status ?? "").toLowerCase();
  if (s === "active") return "green";
  if (s === "sold" || s === "rented") return "gold";
  if (s === "pending") return "blue";
  return "gray";
}

// ------------------------------------------------------------------ Forms
export function Field({ label, hint, error, children, className }: { label?: ReactNode; hint?: ReactNode; error?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      {label && <span className="label">{label}</span>}
      {children}
      {error ? <span className="mt-1 block text-xs text-red-600">{error}</span> : hint ? <span className="mt-1 block text-xs text-ink-mute">{hint}</span> : null}
    </label>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }>(function Input({ className, icon, ...rest }, ref) {
  if (!icon) return <input ref={ref} className={cn("input", className)} {...rest} />;
  return (
    <div className="relative">
      <span className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-ink-mute">{icon}</span>
      <input ref={ref} className={cn("input ps-10", className)} {...rest} />
    </div>
  );
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & { options?: (string | { value: string; label: string })[] }>(
  function Select({ className, options, children, ...rest }, ref) {
    return (
      <select ref={ref} className={cn("input", className)} {...rest}>
        {children}
        {options?.map((o) =>
          typeof o === "string" ? (
            <option key={o} value={o}>
              {o}
            </option>
          ) : (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ),
        )}
      </select>
    );
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn("input min-h-[96px] resize-y", className)} {...rest} />;
});

export function Segmented<T extends string>({ value, onChange, options, className }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; icon?: ReactNode }[]; className?: string }) {
  return (
    <div className={cn("seg", className)} role="group">
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Stepper({ value, onChange, min = 0, max = 20, label }: { value: number; onChange: (v: number) => void; min?: number; max?: number; label: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-black/10 bg-white px-3 py-2 dark:border-white/10 dark:bg-white/5">
      <span className="text-sm font-semibold">{label}</span>
      <div className="flex items-center gap-3">
        <button type="button" aria-label={`Fewer ${label}`} className="btn btn-soft h-9 w-9 rounded-full p-0" onClick={() => onChange(Math.max(min, value - 1))}>
          −
        </button>
        <span className="w-6 text-center font-display text-lg font-bold">{value}</span>
        <button type="button" aria-label={`More ${label}`} className="btn btn-soft h-9 w-9 rounded-full p-0" onClick={() => onChange(Math.min(max, value + 1))}>
          +
        </button>
      </div>
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; hint?: ReactNode }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="flex w-full items-center justify-between gap-4 py-3 text-start">
      <span>
        <span className="block text-sm font-semibold">{label}</span>
        {hint && <span className="block text-xs text-ink-mute dark:text-slate-400">{hint}</span>}
      </span>
      <span className={cn("relative h-7 w-12 shrink-0 rounded-full transition", checked ? "bg-brand-600" : "bg-black/15 dark:bg-white/15")}>
        <span className={cn("absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all", checked ? "start-6" : "start-1")} />
      </span>
    </button>
  );
}

// ------------------------------------------------------------------ OTP
/** Six-box one-time-code input with paste and SMS autofill (autocomplete="one-time-code"). */
export function OtpInput({ value, onChange, length = 6, onComplete }: { value: string; onChange: (v: string) => void; length?: number; onComplete?: (v: string) => void }) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length }, (_, i) => value[i] ?? "");
  const commit = (next: string) => {
    const v = next.replace(/\D/g, "").slice(0, length);
    onChange(v);
    if (v.length === length) onComplete?.(v);
  };
  return (
    <div className="flex justify-between gap-2" dir="ltr">
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => (refs.current[i] = el)}
          value={d}
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          autoFocus={i === 0}
          maxLength={i === 0 ? length : 1}
          aria-label={`Digit ${i + 1}`}
          className="input h-14 w-full min-w-0 px-0 text-center font-display text-2xl font-bold"
          onChange={(e) => {
            const raw = e.target.value.replace(/\D/g, "");
            if (raw.length > 1) {
              // SMS autofill / paste lands the whole code in one box.
              commit(raw);
              refs.current[Math.min(raw.length, length) - 1]?.focus();
              return;
            }
            const next = digits.slice();
            next[i] = raw.slice(-1);
            commit(next.join(""));
            if (raw && i < length - 1) refs.current[i + 1]?.focus();
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace" && !d && i > 0) refs.current[i - 1]?.focus();
          }}
          onFocus={(e) => e.target.select()}
        />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ Layout bits
/**
 * The brand wordmark, centred in three lines: وطن پاک (وطن gold, پاک green), WatanePak (green
 * with a gold "e") and "AI Real Estate Portal". `light` is for photos and dark-green backgrounds.
 * Same as frontend/src/components/layout/Chrome.tsx, except WatanePak is in the regular (thinner) weight here.
 */
export function BrandWords({ light }: { light?: boolean }) {
  const green = light ? "text-white" : "text-brand-600 dark:text-brand-300";
  const gold = light ? "text-gold-300" : "text-gold-500 dark:text-gold-300";
  return (
    <span className="flex flex-col items-center leading-none">
      <span lang="ur" dir="rtl" className="mb-0.5 font-urdu text-[18px] font-normal leading-[1.75]">
        <span className={gold}>وطن</span> <span className={green}>پاک</span>
      </span>
      <span className={cn("font-display text-[22px] font-normal tracking-tight", green)}>
        Watan<span className={gold}>e</span>Pak
      </span>
      <span className={cn("mt-0.5 text-[10.5px] font-medium tracking-wide", light ? "text-white/85" : "text-ink dark:text-slate-300")}>AI Real Estate Portal</span>
    </span>
  );
}

export function Logo({ light, compact, className }: { light?: boolean; compact?: boolean; className?: string }) {
  return (
    <span className={cn("flex shrink-0 items-center gap-2.5 whitespace-nowrap", className)}>
      <img src={BRAND.mark} alt="Watan-e-Pak" className={cn("w-auto drop-shadow-sm", compact ? "h-10" : "h-12")} />
      <BrandWords light={light} />
    </span>
  );
}

/** Sticky screen header with optional back button and right-side actions. */
export function TopBar({ title, back, actions, className }: { title?: ReactNode; back?: boolean | string; actions?: ReactNode; className?: string }) {
  const nav = useNavigate();
  return (
    <header className={cn("pt-safe sticky top-0 z-30 border-b border-black/5 bg-[#f6f8f6]/85 backdrop-blur-xl dark:border-white/10 dark:bg-[#07130d]/85", className)}>
      <div className="screen flex h-14 items-center gap-2">
        {back && (
          <button className="btn btn-ghost btn-icon -ms-2" aria-label="Back" onClick={() => (typeof back === "string" ? nav(back) : nav(-1))}>
            <ArrowLeft className="h-5 w-5 rtl:rotate-180" />
          </button>
        )}
        <div className="min-w-0 flex-1 truncate font-display text-lg font-bold text-brand-900 dark:text-white">{title}</div>
        {actions}
      </div>
    </header>
  );
}

export function Avatar({ name, className }: { name?: string | null; className?: string }) {
  return <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gold-gradient font-display font-bold text-brand-950", className)}>{initials(name)}</span>;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-brand-600", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("relative overflow-hidden rounded-xl bg-black/5 dark:bg-white/5", className)}><div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/50 to-transparent dark:via-white/5" /></div>;
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && <span className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-white/5 dark:text-brand-300">{icon}</span>}
      <p className="font-display text-lg font-bold text-brand-900 dark:text-white">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-ink-mute dark:text-slate-400">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function SectionHead({ title, action, to }: { title: ReactNode; action?: ReactNode; to?: string }) {
  return (
    <div className="mb-3 flex items-end justify-between">
      <h2 className="section-title">{title}</h2>
      {to ? (
        <Link to={to} className="text-sm font-semibold text-brand-700 dark:text-brand-300">
          {action ?? "See all"}
        </Link>
      ) : (
        action
      )}
    </div>
  );
}

/** Bottom sheet on phones, centered dialog on wide screens. */
export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 40, opacity: 0 }}
            transition={{ type: "spring", bounce: 0.15, duration: 0.35 }}
            className="card pb-safe relative max-h-[88vh] w-full overflow-y-auto rounded-b-none sm:max-w-lg sm:rounded-b-2xl"
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-black/5 bg-white px-5 py-3 dark:border-white/10 dark:bg-[#0d1f16]">
              <p className="font-display text-lg font-bold">{title}</p>
              <button className="btn btn-ghost btn-icon h-9 w-9" onClick={onClose} aria-label="Close">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-5">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
