import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Workflow, Wrench } from "lucide-react";
import type { AgentDef } from "@/types";
import { titleCase } from "@/lib/format";
import { ApprovalGate, AutonomyBadge, CategoryIcon, PriorityBadge } from "./AgentBits";

export function AgentCard({ a, i = 0 }: { a: AgentDef; i?: number }) {
  return (
    <motion.div layout initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }} transition={{ delay: Math.min(i, 10) * 0.035 }}>
      <Link
        to={`/ai/agents/${a.key}`}
        className="card card-hover group relative flex h-full flex-col overflow-hidden p-5 hover:border-gold-300/60 dark:hover:border-gold-500/30"
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-brand-600 via-gold-400 to-brand-600 opacity-0 transition group-hover:opacity-100" />
        <div className="flex items-start justify-between gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-soft transition group-hover:shadow-glow">
            <CategoryIcon category={a.category} />
          </span>
          <div className="flex flex-wrap justify-end gap-1">
            <PriorityBadge priority={a.priority} />
            <AutonomyBadge autonomy={a.autonomy} />
          </div>
        </div>
        <h3 className="mt-4 font-display text-lg font-semibold leading-snug text-ink group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300">{a.name}</h3>
        <p className="mt-0.5 text-[11px] font-semibold uppercase tracking-wider text-ink-mute">{titleCase(a.category)}</p>
        <p className="mt-2 line-clamp-3 flex-1 text-sm text-ink-mute dark:text-slate-400">{a.summary}</p>
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-black/5 pt-3 text-xs text-ink-mute dark:border-white/10">
          <span className="inline-flex items-center gap-1">
            <Wrench className="h-3 w-3" /> {a.tool_count ?? a.tools?.length ?? 0} tools
          </span>
          <span className="inline-flex items-center gap-1">
            <Workflow className="h-3 w-3" /> {a.workflow_steps ?? a.workflow?.length ?? 0} steps
          </span>
          <ApprovalGate required={a.requires_approval} compact />
          <ArrowRight className="ms-auto h-4 w-4 text-brand-600 transition group-hover:translate-x-1 rtl:rotate-180 rtl:group-hover:-translate-x-1" />
        </div>
      </Link>
    </motion.div>
  );
}
