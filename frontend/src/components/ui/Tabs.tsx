import { useId, type ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface TabItem<T extends string = string> {
  value: T;
  label: ReactNode;
  icon?: ReactNode;
  count?: number;
}

/** Underline tabs with an animated indicator. Controlled. */
export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: TabItem<T>[]; value: T; onChange: (v: T) => void; className?: string }) {
  const id = useId();
  return (
    <div className={cn("no-scrollbar flex gap-1 overflow-x-auto border-b border-black/5 dark:border-white/10", className)}>
      {tabs.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            type="button"
            onClick={() => onChange(t.value)}
            className={cn(
              "relative inline-flex shrink-0 items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors",
              active ? "text-brand-800 dark:text-white" : "text-ink-mute hover:text-brand-700 dark:text-slate-400 dark:hover:text-slate-200",
            )}
          >
            {t.icon}
            {t.label}
            {t.count !== undefined && (
              <span className={cn("rounded-full px-1.5 py-0.5 text-[10px]", active ? "bg-brand-700 text-white" : "bg-black/5 dark:bg-white/10")}>{t.count}</span>
            )}
            {active && <motion.span layoutId={`tab-${id}`} className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-gold-gradient" />}
          </button>
        );
      })}
    </div>
  );
}
