/**
 * Shared plumbing for the live calculators on /tools/:key:
 * debounced backend calls, slider+number fields, the input/result shell and
 * "Save as project".
 */
import { useEffect, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { FolderPlus, SlidersHorizontal, Sparkles } from "lucide-react";
import { api, post, type Query } from "@/lib/api";
import { useMutate } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { Button, Card, ErrorState, Field, Input, Modal, Skeleton, Slider, Spinner, Textarea } from "@/components/ui";

export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  const key = JSON.stringify(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ms]);
  return v;
}

/**
 * Recalculate on the backend whenever `body` changes (debounced ~350ms).
 * Keeps the previous result on screen while the next one loads.
 */
export function useCalc<T = any>(path: string, body: Record<string, unknown>, opts: { method?: "GET" | "POST"; enabled?: boolean } = {}) {
  const method = opts.method ?? "POST";
  const debounced = useDebounced(body);
  return useQuery<T, Error>({
    queryKey: ["calc", path, method, debounced],
    queryFn: ({ signal }) =>
      method === "GET" ? api<T>(path, { method: "GET", query: debounced as Query, signal, noFallback: true }) : api<T>(path, { method: "POST", body: debounced, signal }),
    placeholderData: keepPreviousData,
    enabled: opts.enabled ?? true,
    retry: false,
    staleTime: 60_000,
  });
}

/** Label + live value + slider + exact numeric input. */
export function NumField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  display,
  suffix,
  hint,
}: {
  label: ReactNode;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  display?: (v: number) => string;
  suffix?: string;
  hint?: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-end justify-between gap-2">
        <span className="label !mb-0">{label}</span>
        <span className="font-display text-sm font-bold text-brand-800 dark:text-brand-200">{display ? display(value) : `${value}${suffix ?? ""}`}</span>
      </div>
      <div className="flex items-center gap-3">
        <Slider value={Math.min(max, Math.max(min, value))} min={min} max={max} step={step} onChange={onChange} className="flex-1" />
        <input
          type="number"
          className="input !w-28 !px-2.5 !py-1.5 text-end text-sm tabular-nums"
          value={Number.isFinite(value) ? value : ""}
          step={step}
          min={0}
          onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
          aria-label={typeof label === "string" ? label : undefined}
        />
      </div>
      {hint && <p className="mt-1 text-xs text-ink-mute">{hint}</p>}
    </div>
  );
}

export function SaveProjectButton({ tool, inputs, outputs, defaultName }: { tool: string; inputs: Record<string, unknown>; outputs?: unknown; defaultName?: string }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(defaultName ?? "");
  const [notes, setNotes] = useState("");
  const m = useMutate(
    () =>
      post("/tools/projects", {
        name: name.trim() || defaultName || `${tool} project`,
        tool,
        inputs,
        outputs: outputs && typeof outputs === "object" && !Array.isArray(outputs) ? outputs : { result: outputs },
        notes: notes.trim() || undefined,
      }),
    { invalidate: ["/tools/projects"], success: "Saved to your tool projects", onSuccess: () => setOpen(false) },
  );
  return (
    <>
      <Button variant="soft" size="sm" icon={<FolderPlus className="h-4 w-4" />} onClick={() => setOpen(true)} disabled={!outputs}>
        Save as project
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Save as project"
        subtitle="Keep these inputs and results to reopen or share later."
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button loading={m.isPending} onClick={() => m.mutate()}>
              Save project
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Field label="Project name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={defaultName} autoFocus />
          </Field>
          <Field label="Notes (optional)">
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="min-h-[72px]" />
          </Field>
        </div>
      </Modal>
    </>
  );
}

/** Two-column calculator layout: sticky inputs card + live results. */
export function CalcShell({
  form,
  children,
  q,
  save,
  aside,
}: {
  form: ReactNode;
  children: ReactNode;
  q?: { isFetching: boolean; isLoading?: boolean; error: unknown; data?: unknown; refetch: () => unknown };
  save?: { tool: string; inputs: Record<string, unknown>; outputs?: unknown; name?: string };
  aside?: ReactNode;
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <div className="space-y-4 xl:sticky xl:top-24 xl:self-start">
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-black/5 bg-brand-50/60 px-5 py-3 dark:border-white/10 dark:bg-white/5">
            <SlidersHorizontal className="h-4 w-4 text-brand-700 dark:text-brand-300" />
            <span className="text-sm font-semibold text-brand-900 dark:text-white">Inputs</span>
            <span className="ms-auto inline-flex items-center gap-1 text-[11px] font-medium text-ink-mute">
              <Sparkles className="h-3 w-3 text-gold-500" /> Live
            </span>
          </div>
          <div className="space-y-5 p-5">{form}</div>
        </Card>
        {aside}
      </div>
      <div className="min-w-0 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-mute">
            Results
            {q?.isFetching && <Spinner className="h-3.5 w-3.5" />}
          </div>
          {save && <SaveProjectButton tool={save.tool} inputs={save.inputs} outputs={save.outputs} defaultName={save.name} />}
        </div>
        {q?.error && !q.data ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q && q.data === undefined ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
            <Skeleton className="h-72" />
          </div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={cn("space-y-5 transition-opacity", q?.isFetching && "opacity-80")}>
            {children}
          </motion.div>
        )}
      </div>
    </div>
  );
}

export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: 2 | 3 | 4 }) {
  const c = { 2: "sm:grid-cols-2", 3: "sm:grid-cols-3", 4: "sm:grid-cols-2 2xl:grid-cols-4" }[cols];
  return <div className={cn("grid gap-4", c)}>{children}</div>;
}

export function ChoiceChips<T extends string | number>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-full px-3 py-1.5 text-xs font-semibold transition",
            o.value === value ? "bg-brand-700 text-white shadow-soft" : "bg-black/5 text-ink-soft hover:bg-brand-50 hover:text-brand-800 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
