import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

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
        {options?.map((o) => (typeof o === "string" ? <option key={o} value={o}>{o}</option> : <option key={o.value} value={o.value}>{o.label}</option>))}
        {children}
      </select>
    );
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn("input min-h-[96px] resize-y", className)} {...rest} />;
});

/** Single-thumb slider with a filled track. */
export function Slider({
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  className,
}: {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
  className?: string;
}) {
  const fill = ((value - min) / (max - min)) * 100;
  return (
    <input
      type="range"
      className={cn("range-single", className)}
      style={{ ["--fill" as string]: `${fill}%` }}
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  );
}

/** Dual-thumb range slider (e.g. price min/max). */
export function RangeSlider({
  min,
  max,
  step = 1,
  value,
  onChange,
  format = (v) => String(v),
}: {
  min: number;
  max: number;
  step?: number;
  value: [number, number];
  onChange: (v: [number, number]) => void;
  format?: (v: number) => string;
}) {
  const [lo, hi] = value;
  const left = ((lo - min) / (max - min)) * 100;
  const right = ((hi - min) / (max - min)) * 100;
  return (
    <div>
      <div className="relative h-6">
        <div className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full bg-brand-100 dark:bg-white/10" />
        <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-brand-600" style={{ left: `${left}%`, width: `${right - left}%` }} />
        <input type="range" className="range" min={min} max={max} step={step} value={lo} onChange={(e) => onChange([Math.min(Number(e.target.value), hi - step), hi])} />
        <input type="range" className="range" min={min} max={max} step={step} value={hi} onChange={(e) => onChange([lo, Math.max(Number(e.target.value), lo + step)])} />
      </div>
      <div className="mt-1 flex justify-between text-xs font-semibold text-brand-800 dark:text-brand-200">
        <span>{format(lo)}</span>
        <span>{format(hi)}</span>
      </div>
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="inline-flex items-center gap-2 text-sm">
      <span className={cn("relative h-6 w-11 rounded-full transition", checked ? "bg-brand-600" : "bg-black/15 dark:bg-white/15")}>
        <span className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", checked ? "start-[22px]" : "start-0.5")} />
      </span>
      {label}
    </button>
  );
}

/** Pill-style segmented control with an animated active indicator. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  className,
  size = "md",
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; icon?: ReactNode }[];
  className?: string;
  size?: "sm" | "md";
}) {
  const id = useId();
  return (
    <div className={cn("inline-flex rounded-2xl bg-black/5 p-1 dark:bg-white/5", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={cn(
              "relative inline-flex items-center gap-2 rounded-xl font-semibold transition-colors",
              size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm",
              active ? "text-white" : "text-ink-soft hover:text-brand-800 dark:text-slate-300",
            )}
          >
            {active && <motion.span layoutId={`seg-${id}`} className="absolute inset-0 rounded-xl bg-brand-700 shadow-soft" transition={{ type: "spring", bounce: 0.2, duration: 0.45 }} />}
            <span className="relative z-10 inline-flex items-center gap-2">
              {o.icon}
              {o.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
