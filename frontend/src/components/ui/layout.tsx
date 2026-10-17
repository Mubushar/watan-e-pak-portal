import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { AlertTriangle, ChevronRight, Inbox, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button, Skeleton } from "./primitives";

// ------------------------------------------------------------------ Card
export function Card({ className, children, hover, ...rest }: { className?: string; children: ReactNode; hover?: boolean } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("card", hover && "card-hover", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  icon,
  action,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-3 border-b border-black/5 px-5 py-4 dark:border-white/10", className)}>
      <div className="flex min-w-0 items-center gap-3">
        {icon && <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">{icon}</span>}
        <div className="min-w-0">
          <h3 className="truncate font-display text-base font-semibold text-ink dark:text-white">{title}</h3>
          {subtitle && <p className="truncate text-xs text-ink-mute dark:text-slate-400">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("p-5", className)}>{children}</div>;
}

// ------------------------------------------------------------------ PageHeader
export interface Crumb {
  label: string;
  to?: string;
}

export function PageHeader({
  title,
  subtitle,
  eyebrow,
  crumbs,
  actions,
  image,
  className,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  eyebrow?: ReactNode;
  crumbs?: Crumb[];
  actions?: ReactNode;
  /** When given, renders a full-bleed hero with the image behind a brand overlay. */
  image?: string;
  className?: string;
  children?: ReactNode;
}) {
  if (image) {
    return (
      <section className={cn("relative isolate overflow-hidden bg-brand-950 text-white", className)}>
        <img src={image} alt="" className="absolute inset-0 -z-10 h-full w-full object-cover opacity-60" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-r from-brand-950 via-brand-950/80 to-brand-900/30" />
        <div className="container py-14 sm:py-20">
          {crumbs && <Breadcrumbs crumbs={crumbs} light />}
          {eyebrow && <p className="section-eyebrow mt-4 !text-gold-300">{eyebrow}</p>}
          <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mt-2 max-w-3xl text-4xl font-bold sm:text-5xl">
            {title}
          </motion.h1>
          {subtitle && <p className="mt-4 max-w-2xl text-lg text-white/80">{subtitle}</p>}
          {actions && <div className="mt-6 flex flex-wrap gap-3">{actions}</div>}
          {children}
        </div>
      </section>
    );
  }
  return (
    <div className={cn("mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        {crumbs && <Breadcrumbs crumbs={crumbs} />}
        {eyebrow && <p className="section-eyebrow mt-2">{eyebrow}</p>}
        <h1 className="mt-1 font-display text-2xl font-bold text-brand-900 sm:text-3xl dark:text-white">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-mute dark:text-slate-400">{subtitle}</p>}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Breadcrumbs({ crumbs, light }: { crumbs: Crumb[]; light?: boolean }) {
  return (
    <nav className={cn("flex flex-wrap items-center gap-1 text-xs font-medium", light ? "text-white/70" : "text-ink-mute dark:text-slate-400")}>
      {crumbs.map((c, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3 w-3 rtl:rotate-180" />}
          {c.to ? (
            <Link to={c.to} className={cn("hover:underline", light ? "hover:text-white" : "hover:text-brand-700")}>
              {c.label}
            </Link>
          ) : (
            <span className={light ? "text-white" : "text-ink dark:text-slate-200"}>{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

// ------------------------------------------------------------------ Section
export function Section({
  eyebrow,
  title,
  subtitle,
  action,
  className,
  children,
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("container py-12 sm:py-16", className)}>
      {(title || eyebrow) && (
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            {eyebrow && <p className="section-eyebrow">{eyebrow}</p>}
            {title && <h2 className="section-title mt-2">{title}</h2>}
            {subtitle && <p className="mt-2 max-w-2xl text-ink-mute dark:text-slate-400">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

// ------------------------------------------------------------------ states
export function EmptyState({ title = "Nothing here yet", hint, icon, action }: { title?: string; hint?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-black/10 px-6 py-12 text-center dark:border-white/10">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-white/5">{icon ?? <Inbox className="h-6 w-6" />}</span>
      <p className="font-semibold text-ink dark:text-white">{title}</p>
      {hint && <p className="max-w-sm text-sm text-ink-mute">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-red-200 bg-red-50/60 px-6 py-10 text-center dark:border-red-500/20 dark:bg-red-500/5">
      <AlertTriangle className="h-7 w-7 text-red-500" />
      <p className="font-semibold text-red-700 dark:text-red-300">Couldn’t load this</p>
      <p className="max-w-md text-sm text-red-700/80 dark:text-red-300/80">{msg}</p>
      {onRetry && (
        <Button variant="outline" size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

/**
 * Render loading / error / data for a React Query result.
 *   <QueryState q={q}>{(data) => <List items={data.items}/>}</QueryState>
 */
export function QueryState<T>({
  q,
  children,
  skeleton,
  empty,
}: {
  q: { data: T | undefined; isLoading: boolean; error: unknown; refetch: () => unknown };
  children: (data: T) => ReactNode;
  skeleton?: ReactNode;
  empty?: (data: T) => boolean;
}) {
  if (q.isLoading) return <>{skeleton ?? <Skeleton className="h-40 w-full" />}</>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.data === undefined) return null;
  if (empty?.(q.data)) return <EmptyState />;
  return <>{children(q.data)}</>;
}

export function KeyValue({ items, cols = 2 }: { items: { label: ReactNode; value: ReactNode }[]; cols?: 1 | 2 | 3 | 4 }) {
  const grid = { 1: "grid-cols-1", 2: "grid-cols-2", 3: "grid-cols-2 sm:grid-cols-3", 4: "grid-cols-2 sm:grid-cols-4" }[cols];
  return (
    <dl className={cn("grid gap-3", grid)}>
      {items.map((it, i) => (
        <div key={i} className="rounded-xl bg-brand-50/50 px-3 py-2.5 dark:bg-white/5">
          <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-mute dark:text-slate-400">{it.label}</dt>
          <dd className="mt-0.5 font-semibold text-ink dark:text-white">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
