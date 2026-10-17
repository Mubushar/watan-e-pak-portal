import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, GripVertical } from "lucide-react";
import { toast } from "sonner";
import { put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { date, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Avatar, ErrorState, Skeleton } from "@/components/ui";
import { MiniStat, ensure } from "./ops-kit";
import { DEAL_STAGES, type Agent, type Deal, type DealsRes, type Pipeline } from "./crm-types";

const DEALS_KEY = ["/crm/deals", {}] as const;

const STAGE_ACCENT: Record<string, string> = {
  prospecting: "bg-sky-500",
  qualification: "bg-violet-500",
  proposal: "bg-gold-500",
  negotiation: "bg-orange-500",
  contract: "bg-teal-500",
  closed_won: "bg-brand-600",
  closed_lost: "bg-red-500",
};

/** Kanban of deals by stage with native HTML5 drag-and-drop and optimistic moves. */
export function CrmPipelineBoard({ agents }: { agents: Agent[] }) {
  const qc = useQueryClient();
  const deals = useApi<DealsRes>("/crm/deals");
  const pipeline = useApi<Pipeline>("/crm/pipeline");
  const [dragId, setDragId] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);

  const move = useMutation<unknown, Error, { id: string; stage: string }, { prev?: DealsRes }>({
    mutationFn: ({ id, stage }) => put(`/crm/deals/${id}/stage`, { stage }).then(ensure),
    onMutate: async ({ id, stage }) => {
      await qc.cancelQueries({ queryKey: DEALS_KEY });
      const prev = qc.getQueryData<DealsRes>(DEALS_KEY);
      qc.setQueryData<DealsRes>(DEALS_KEY, (old) =>
        old
          ? {
              ...old,
              deals: old.deals.map((d) =>
                d.id === id ? { ...d, stage, probability: stage === "closed_won" ? 100 : stage === "closed_lost" ? 0 : d.probability } : d,
              ),
            }
          : old,
      );
      return { prev };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(DEALS_KEY, ctx.prev);
      toast.error(e.message || "Couldn’t move the deal");
    },
    onSuccess: (_r, v) => toast.success(`Moved to ${titleCase(v.stage)}`),
    onSettled: () =>
      qc.invalidateQueries({
        predicate: (q) => typeof q.queryKey[0] === "string" && ["/crm", "/broker", "/portal", "/agents"].some((p) => (q.queryKey[0] as string).startsWith(p)),
      }),
  });

  const columns = useMemo(() => {
    const list = deals.data?.deals ?? [];
    return DEAL_STAGES.map((stage) => {
      const items = list.filter((d) => d.stage === stage);
      return {
        stage,
        items,
        value: items.reduce((s, d) => s + d.amount, 0),
        weighted: items.reduce((s, d) => s + (d.amount * d.probability) / 100, 0),
      };
    });
  }, [deals.data]);

  const drop = (stage: string, id: string | null) => {
    setOver(null);
    setDragId(null);
    if (!id) return;
    const d = deals.data?.deals.find((x) => x.id === id);
    if (d && d.stage !== stage) move.mutate({ id, stage });
  };

  if (deals.error) return <ErrorState error={deals.error} onRetry={() => deals.refetch()} />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="Open pipeline" value={pipeline.data ? pkrShort(pipeline.data.open_pipeline_value, false) : "…"} tone="green" />
        <MiniStat label="Weighted" value={pkrShort(columns.filter((c) => !c.stage.startsWith("closed")).reduce((s, c) => s + c.weighted, 0), false)} tone="gold" />
        <MiniStat label="Won" value={pipeline.data ? pkrShort(pipeline.data.won_value, false) : "…"} tone="blue" />
        <MiniStat label="Deals" value={pipeline.data?.total_deals ?? deals.data?.count ?? "…"} />
      </div>
      <p className="text-xs text-ink-mute dark:text-slate-400">Drag a card to another column to change its stage. On touch devices use the stage menu on each card.</p>

      <div className="no-scrollbar -mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-3 sm:mx-0 sm:px-0">
        {columns.map((col) => (
          <div
            key={col.stage}
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
              if (over !== col.stage) setOver(col.stage);
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver((o) => (o === col.stage ? null : o));
            }}
            onDrop={(e) => {
              e.preventDefault();
              drop(col.stage, e.dataTransfer.getData("text/plain") || dragId);
            }}
            className={cn(
              "flex w-[270px] shrink-0 snap-start flex-col rounded-2xl border bg-black/[.02] transition-colors dark:bg-white/[.02]",
              over === col.stage ? "border-brand-400 bg-brand-50/70 ring-4 ring-brand-500/10 dark:border-brand-500/60 dark:bg-brand-500/10" : "border-black/5 dark:border-white/10",
            )}
          >
            <div className="border-b border-black/5 px-3 py-3 dark:border-white/10">
              <div className="flex items-center gap-2">
                <span className={cn("h-2.5 w-2.5 rounded-full", STAGE_ACCENT[col.stage])} />
                <span className="text-sm font-semibold">{titleCase(col.stage)}</span>
                <span className="ms-auto rounded-full bg-black/5 px-2 py-0.5 text-[11px] font-bold tabular-nums dark:bg-white/10">{col.items.length}</span>
              </div>
              <div className="mt-1.5 flex justify-between text-[11px] text-ink-mute dark:text-slate-400">
                <span>{pkrShort(col.value, false)}</span>
                <span>wtd {pkrShort(col.weighted, false)}</span>
              </div>
            </div>
            <div className="flex min-h-[180px] flex-1 flex-col gap-2 p-2">
              {deals.isLoading
                ? [0, 1].map((i) => <Skeleton key={i} className="h-24" />)
                : col.items.map((d) => (
                    <DealCard
                      key={d.id}
                      deal={d}
                      agent={d.agent_id ? agentName[d.agent_id] : undefined}
                      dragging={dragId === d.id}
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", d.id);
                        e.dataTransfer.effectAllowed = "move";
                        setDragId(d.id);
                      }}
                      onDragEnd={() => {
                        setDragId(null);
                        setOver(null);
                      }}
                      onMove={(stage) => move.mutate({ id: d.id, stage })}
                    />
                  ))}
              {!deals.isLoading && col.items.length === 0 && (
                <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-black/10 p-4 text-center text-xs text-ink-mute dark:border-white/10">
                  Drop deals here
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DealCard({
  deal,
  agent,
  dragging,
  onDragStart,
  onDragEnd,
  onMove,
}: {
  deal: Deal;
  agent?: string;
  dragging: boolean;
  onDragStart: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragEnd: () => void;
  onMove: (stage: string) => void;
}) {
  return (
    <motion.div layout transition={{ type: "spring", bounce: 0.15, duration: 0.35 }}>
      <div
        draggable
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        className={cn(
          "group cursor-grab rounded-xl border border-black/5 bg-white p-3 shadow-sm transition-all hover:shadow-soft active:cursor-grabbing dark:border-white/10 dark:bg-[#0d1f16]",
          dragging && "rotate-1 opacity-50",
        )}
      >
        <div className="flex items-start gap-2">
          <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-ink-mute/50 group-hover:text-ink-mute" />
          <p className="min-w-0 flex-1 text-sm font-semibold leading-snug">{deal.title}</p>
        </div>
        <div className="mt-2 flex items-baseline justify-between gap-2">
          <span className="font-display text-base font-bold text-brand-800 dark:text-brand-200">{pkrShort(deal.amount, false)}</span>
          <span className="text-[11px] font-semibold text-ink-mute">{deal.probability}%</span>
        </div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
          <div className="h-full rounded-full bg-gradient-to-r from-brand-600 to-gold-400" style={{ width: `${deal.probability}%` }} />
        </div>
        <div className="mt-2.5 flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-ink-mute">
            {agent && <Avatar name={agent} size={18} />}
            <span className="truncate">{agent ?? "Unassigned"}</span>
          </span>
          {deal.expected_close_date && (
            <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-ink-mute">
              <CalendarDays className="h-3 w-3" />
              {date(deal.expected_close_date, { day: "numeric", month: "short" })}
            </span>
          )}
        </div>
        <label className="mt-2 block">
          <span className="sr-only">Move to stage</span>
          <select
            value={deal.stage}
            onChange={(e) => onMove(e.target.value)}
            onMouseDown={(e) => e.stopPropagation()}
            className="w-full rounded-lg border border-black/5 bg-black/[.02] px-2 py-1 text-[11px] font-medium text-ink-soft focus:outline-none focus:ring-2 focus:ring-brand-500/30 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"
          >
            {DEAL_STAGES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
        </label>
      </div>
    </motion.div>
  );
}
