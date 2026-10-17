/**
 * Lightweight Gantt chart: horizontal bars on a date axis, phase groups, progress fill,
 * critical-path tasks in gold and a "today" marker. RTL-safe (uses inline-start offsets).
 */
import { useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface GanttRow {
  phase?: string | null;
  task: string;
  wbs?: string | null;
  start: string;
  finish: string;
  duration_days?: number;
  progress_pct: number;
  is_critical?: boolean;
  float_days?: number;
}

const DAY = 86_400_000;
const toDay = (s: string) => {
  const d = new Date(s + (s.length === 10 ? "T00:00:00" : ""));
  return Math.floor(d.getTime() / DAY);
};

export function Gantt({ rows, start, finish, critical }: { rows: GanttRow[]; start?: string; finish?: string; critical?: Set<string> }) {
  const { min, max, months, groups } = useMemo(() => {
    const starts = rows.map((r) => toDay(r.start));
    const ends = rows.map((r) => toDay(r.finish));
    let min = Math.min(...starts, start ? toDay(start) : Infinity);
    let max = Math.max(...ends, finish ? toDay(finish) : -Infinity);
    if (!Number.isFinite(min) || !Number.isFinite(max)) {
      min = Math.floor(Date.now() / DAY);
      max = min + 30;
    }
    max += 1;
    const months: { label: string; at: number; year: boolean }[] = [];
    const d = new Date(min * DAY);
    d.setUTCDate(1);
    while (Math.floor(d.getTime() / DAY) <= max) {
      const at = Math.floor(d.getTime() / DAY);
      if (at >= min) months.push({ label: d.toLocaleDateString("en-GB", { month: "short" }), at, year: d.getUTCMonth() === 0 });
      d.setUTCMonth(d.getUTCMonth() + 1);
    }
    const groups: { phase: string; rows: GanttRow[] }[] = [];
    rows.forEach((r) => {
      const ph = r.phase ?? "Tasks";
      const g = groups.find((x) => x.phase === ph);
      if (g) g.rows.push(r);
      else groups.push({ phase: ph, rows: [r] });
    });
    return { min, max, months, groups };
  }, [rows, start, finish]);

  const span = Math.max(1, max - min);
  const pos = (day: number) => `${((day - min) / span) * 100}%`;
  const today = Math.floor(Date.now() / DAY);
  const showToday = today >= min && today <= max;
  const width = Math.max(720, span * 3.2);
  const isCrit = (r: GanttRow) => !!r.is_critical || !!critical?.has(r.task);

  return (
    <div className="overflow-hidden rounded-2xl border border-black/5 dark:border-white/10">
      <div className="flex">
        {/* names */}
        <div className="w-40 shrink-0 border-e border-black/5 bg-white dark:border-white/10 dark:bg-[#0d1f16] sm:w-60">
          <div className="flex h-10 items-center border-b border-black/5 px-3 text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:border-white/10">Task</div>
          {groups.map((g) => (
            <div key={g.phase}>
              <div className="flex h-8 items-center truncate bg-brand-50/70 px-3 text-xs font-bold text-brand-800 dark:bg-white/5 dark:text-brand-200">{g.phase}</div>
              {g.rows.map((r, i) => (
                <div key={i} className="flex h-9 items-center gap-2 border-b border-black/[.03] px-3 text-xs dark:border-white/5" title={r.task}>
                  {r.wbs && <span className="font-mono text-[10px] text-ink-mute">{r.wbs}</span>}
                  <span className={cn("truncate", isCrit(r) ? "font-semibold text-gold-700 dark:text-gold-300" : "text-ink-soft dark:text-slate-300")}>{r.task}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
        {/* timeline */}
        <div className="min-w-0 flex-1 overflow-x-auto">
          <div className="relative" style={{ width }}>
            <div className="relative h-10 border-b border-black/5 dark:border-white/10">
              {months.map((m) => (
                <div key={m.at} className="absolute top-0 flex h-full items-center border-s border-black/5 ps-1.5 text-[11px] font-semibold text-ink-mute dark:border-white/10" style={{ insetInlineStart: pos(m.at) }}>
                  {m.label}
                  {m.year && <span className="ms-1 text-gold-600">{new Date(m.at * DAY).getUTCFullYear()}</span>}
                </div>
              ))}
            </div>
            {/* grid lines */}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 top-10">
              {months.map((m) => (
                <div key={m.at} className="absolute inset-y-0 border-s border-dashed border-black/5 dark:border-white/5" style={{ insetInlineStart: pos(m.at) }} />
              ))}
              {showToday && (
                <div className="absolute inset-y-0 z-10 w-0.5 bg-red-500/80" style={{ insetInlineStart: pos(today) }}>
                  <span className="absolute -top-0 start-1 whitespace-nowrap rounded bg-red-500 px-1 text-[9px] font-bold uppercase text-white">Today</span>
                </div>
              )}
            </div>
            {groups.map((g) => (
              <div key={g.phase}>
                <div className="h-8 bg-brand-50/40 dark:bg-white/[.02]" />
                {g.rows.map((r, i) => {
                  const s = toDay(r.start);
                  const e = toDay(r.finish) + 1;
                  const crit = isCrit(r);
                  return (
                    <div key={i} className="relative h-9 border-b border-black/[.03] dark:border-white/5">
                      <motion.div
                        initial={{ opacity: 0, scaleX: 0.6 }}
                        animate={{ opacity: 1, scaleX: 1 }}
                        transition={{ duration: 0.4, delay: i * 0.02 }}
                        className={cn(
                          "group absolute top-1.5 h-6 overflow-hidden rounded-lg shadow-sm ring-1 ring-inset",
                          crit ? "bg-gold-200 ring-gold-500/50 dark:bg-gold-500/30" : "bg-brand-100 ring-brand-600/20 dark:bg-brand-500/20",
                        )}
                        style={{ insetInlineStart: pos(s), width: `${((e - s) / span) * 100}%`, transformOrigin: "left" }}
                        title={`${r.task}\n${r.start} → ${r.finish}\n${Math.round(r.progress_pct)}% complete${r.float_days !== undefined ? ` · float ${r.float_days}d` : ""}`}
                      >
                        <div className={cn("h-full", crit ? "bg-gold-gradient" : "bg-gradient-to-r from-brand-700 to-brand-500")} style={{ width: `${Math.max(0, Math.min(100, r.progress_pct))}%` }} />
                        <span className={cn("absolute inset-0 flex items-center px-2 text-[10px] font-bold", r.progress_pct >= 30 ? "text-white drop-shadow" : "text-brand-900 dark:text-white")}>{Math.round(r.progress_pct)}%</span>
                      </motion.div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-4 border-t border-black/5 px-4 py-2.5 text-xs text-ink-mute dark:border-white/10">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-6 rounded bg-gradient-to-r from-brand-700 to-brand-500" /> Progress
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-6 rounded bg-gold-gradient" /> Critical path
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-0.5 bg-red-500" /> Today
        </span>
      </div>
    </div>
  );
}
