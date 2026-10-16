/** Run-related building blocks shared by AgentDetail and Agent Ops. */
import { motion } from "framer-motion";
import { Activity, CheckCircle2, Clock, Hash } from "lucide-react";
import type { AgentRun } from "@/types";
import { useApi } from "@/hooks/useApi";
import { num, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { Field, Progress, Select, StatusBadge } from "@/components/ui";
import { RunTimeline, runProgress } from "./AgentBits";

export const SUBJECT_TYPES = [
  { value: "", label: "No subject" },
  { value: "property", label: "Property" },
  { value: "lead", label: "CRM lead" },
  { value: "transaction", label: "Transaction" },
];

/** Pick a subject id from the live lists (never hard-coded ids). */
export function SubjectPicker({ type, value, onChange }: { type: string; value: string; onChange: (v: string) => void }) {
  const props = useApi<{ results: { id: string; title: string; price: number; city_name?: string }[] }>(type === "property" ? "/properties" : null, { limit: 60 });
  const leads = useApi<{ leads: { id: string; name: string; status: string }[] }>(type === "lead" ? "/crm/leads" : null);
  const txns = useApi<{ transactions: { id: string; code: string; property_title?: string; stage?: string }[] }>(type === "transaction" ? "/transactions" : null);
  if (!type) return null;
  const options =
    type === "property"
      ? (props.data?.results ?? []).map((p) => ({ value: p.id, label: `${p.title} · ${pkrShort(p.price)}` }))
      : type === "lead"
        ? (leads.data?.leads ?? []).map((l) => ({ value: l.id, label: `${l.name} · ${l.status}` }))
        : (txns.data?.transactions ?? []).map((t) => ({ value: t.id, label: `${t.code} · ${t.property_title ?? ""}` }));
  const loading = props.isLoading || leads.isLoading || txns.isLoading;
  return (
    <Field label={`${titleCase(type)}`}>
      <Select value={value} onChange={(e) => onChange(e.target.value)} disabled={loading}>
        <option value="">{loading ? "Loading…" : `Choose a ${type}`}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    </Field>
  );
}

export function RunHeader({ run }: { run: AgentRun }) {
  const p = runProgress(run);
  const m = run.metrics ?? {};
  return (
    <div className="rounded-2xl bg-gradient-to-br from-brand-50 to-white p-4 ring-1 ring-black/5 dark:from-brand-500/10 dark:to-transparent dark:ring-white/10">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={run.status} />
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-ink-mute">
          <Hash className="h-3 w-3" />
          {run.id}
        </span>
        <span className="ms-auto inline-flex items-center gap-1 text-xs text-ink-mute">
          <Clock className="h-3 w-3" /> {timeAgo(run.created_at.replace(" ", "T"))}
        </span>
      </div>
      <p className="mt-2 text-sm font-medium text-ink dark:text-white">“{run.objective || "No objective"}”</p>
      <div className="mt-3 flex items-center gap-3">
        <Progress value={p.pct} tone={run.status === "awaiting_approval" ? "gold" : run.status === "failed" ? "red" : "green"} className="flex-1" />
        <span className="text-xs font-semibold tabular-nums">
          {p.done}/{p.total} steps
        </span>
      </div>
      {Object.keys(m).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-ink-mute">
          {Object.entries(m).map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-1">
              {k === "failed" ? <Activity className="h-3 w-3" /> : <CheckCircle2 className="h-3 w-3 text-brand-600" />}
              {titleCase(k)} <b className="text-ink dark:text-white">{num(v)}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function RunView({ run, onApprove, approving }: { run: AgentRun; onApprove?: () => void; approving?: boolean }) {
  return (
    <motion.div key={run.id + run.status} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
      <RunHeader run={run} />
      <RunTimeline run={run} onApprove={onApprove} approving={approving} />
    </motion.div>
  );
}
