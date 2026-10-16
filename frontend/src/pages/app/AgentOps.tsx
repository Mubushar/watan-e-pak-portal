import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlarmClock, Bot, Boxes, CheckCircle2, Cpu, Flame, History, Lock, Play, Sparkles, Target, TimerReset, UserRound, Zap } from "lucide-react";
import type { AgentRun, SmartAction } from "@/types";
import { useApi, useMutate } from "@/hooks/useApi";
import { get, post } from "@/lib/api";
import { pkrShort, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import {
  Badge,
  Bars,
  Button,
  ButtonLink,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  Donut,
  Drawer,
  EmptyState,
  Legendish,
  PageHeader,
  PALETTE,
  Progress,
  QueryState,
  ScoreRing,
  Skeleton,
  StatCard,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { AUTONOMY, runProgress } from "@/components/agents/AgentBits";
import { RunView } from "@/components/agents/RunPanel";

interface Overview {
  counts: { agents: number; products: number; autonomous: number; runs_recorded: number };
  by_category: Record<string, number>;
  by_autonomy: Record<string, number>;
  by_priority: Record<string, number>;
  config: { smart_action_sla_hours: Record<string, number> };
}
interface Lead {
  id: string;
  name: string;
  status: string;
  source?: string;
  budget_max?: number | null;
  interest_category?: string | null;
}
interface MoveLikelihood {
  lead: { id: string; name: string; status: string };
  move_likelihood: { score: number; band: string; reasons: string[]; recommended_action: string; components: Record<string, number> };
}

const BANDS = [
  { key: "urgent", label: "Urgent", icon: Flame, ring: "from-red-500 to-orange-400", tone: "red" as const },
  { key: "high", label: "High", icon: Zap, ring: "from-gold-500 to-gold-300", tone: "gold" as const },
  { key: "normal", label: "Normal", icon: TimerReset, ring: "from-brand-600 to-brand-400", tone: "green" as const },
];

function dueText(h: number) {
  if (h < 0) {
    const a = Math.abs(h);
    return a >= 48 ? `${Math.round(a / 24)}d overdue` : `${a}h overdue`;
  }
  return h >= 48 ? `due in ${Math.round(h / 24)}d` : `due in ${h}h`;
}

function SmartActions() {
  const user = useAuth((s) => s.user);
  const nav = useNavigate();
  // NB: the backend currently ignores user_id (the brief is portfolio-wide).
  const q = useApi<{ count: number; by_band: Record<string, number>; actions: SmartAction[] }>("/agents/smart-actions", { user_id: user?.id, limit: 30 });
  return (
    <Card>
      <CardHeader title="Smart Actions · morning brief" subtitle="Prioritised by impact × urgency, with SLA per band" icon={<AlarmClock className="h-4 w-4" />} action={q.data && <Badge tone="gray">{q.data.count} actions</Badge>} />
      <CardBody>
        <QueryState
          q={q}
          skeleton={
            <div className="grid gap-4 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-64" />
              ))}
            </div>
          }
        >
          {(d) => (
            <div className="grid gap-4 lg:grid-cols-3">
              {BANDS.map((b) => {
                const list = d.actions.filter((a) => a.band === b.key);
                return (
                  <div key={b.key} className="flex min-w-0 flex-col rounded-2xl bg-black/[0.02] p-3 dark:bg-white/[0.03]">
                    <div className="mb-3 flex items-center gap-2">
                      <span className={cn("flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br text-white", b.ring)}>
                        <b.icon className="h-4 w-4" />
                      </span>
                      <span className="font-display font-semibold">{b.label}</span>
                      <Badge tone={b.tone}>{d.by_band?.[b.key] ?? list.length}</Badge>
                      {list[0] && <span className="ms-auto text-[11px] text-ink-mute">SLA {list[0].sla_hours}h</span>}
                    </div>
                    <div className="max-h-[440px] space-y-2 overflow-y-auto pe-1">
                      {list.length ? (
                        list.map((a, i) => (
                          <motion.div
                            key={`${a.entity_id}-${a.title}-${i}`}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: Math.min(i, 10) * 0.03 }}
                            className="group rounded-xl border border-black/5 bg-white p-3 shadow-sm transition hover:shadow-soft dark:border-white/10 dark:bg-white/5"
                          >
                            <p className="text-sm font-semibold leading-snug">{a.title}</p>
                            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                              <Badge tone="gray">{titleCase(a.entity_type)}</Badge>
                              <span className={cn("font-semibold", a.due_in_hours < 0 ? "text-red-600 dark:text-red-400" : "text-ink-mute")}>{dueText(a.due_in_hours)}</span>
                              <span className="text-ink-mute">· {a.reason}</span>
                            </div>
                            {a.suggested_agent && (
                              <Button
                                variant="soft"
                                size="sm"
                                className="mt-2 w-full justify-center"
                                icon={<Play className="h-3.5 w-3.5" />}
                                onClick={() => nav(`/ai/agents/${a.suggested_agent}?objective=${encodeURIComponent(a.title)}`)}
                              >
                                Run {titleCase(a.suggested_agent)}
                              </Button>
                            )}
                          </motion.div>
                        ))
                      ) : (
                        <p className="rounded-xl border border-dashed border-black/10 px-3 py-6 text-center text-xs text-ink-mute dark:border-white/10">
                          <CheckCircle2 className="mx-auto mb-1 h-5 w-5 text-brand-500" />
                          Nothing {b.label.toLowerCase()} — nice.
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </QueryState>
      </CardBody>
    </Card>
  );
}

function Runs() {
  const user = useAuth((s) => s.user);
  const q = useApi<{ count: number; runs: AgentRun[] }>("/agents/runs");
  const [open, setOpen] = useState<AgentRun | null>(null);
  const approve = useMutate((id: string) => post<AgentRun>(`/agents/runs/${id}/approve`, undefined, { approver: user?.name || user?.email || "dashboard", execute: true }), {
    invalidate: ["/agents/runs", "/agents/overview"],
    success: "Approved — run continued",
    onSuccess: (r) => setOpen((o) => (o && o.id === r.id ? r : o)),
  });
  const rows = useMemo(() => [...(q.data?.runs ?? [])].sort((a, b) => (b.created_at > a.created_at ? 1 : -1)), [q.data]);
  const awaiting = rows.filter((r) => r.status === "awaiting_approval").length;
  const cols: Column<AgentRun>[] = [
    {
      key: "agent_key",
      header: "Agent",
      value: (r) => r.agent_name ?? r.agent_key,
      render: (r) => (
        <span className="flex items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-white">
            <Bot className="h-4 w-4" />
          </span>
          <span className="min-w-0">
            <span className="block truncate font-semibold">{r.agent_name ?? titleCase(r.agent_key)}</span>
            <span className="block font-mono text-[10px] text-ink-mute">{r.id}</span>
          </span>
        </span>
      ),
    },
    { key: "objective", header: "Objective", render: (r) => <span className="line-clamp-2 max-w-xs text-sm">{r.objective || "—"}</span> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    {
      key: "progress",
      header: "Steps",
      value: (r) => runProgress(r).pct,
      render: (r) => {
        const p = runProgress(r);
        return (
          <span className="flex min-w-[110px] items-center gap-2">
            <Progress value={p.pct} tone={r.status === "awaiting_approval" ? "gold" : "green"} className="h-1.5" />
            <span className="text-xs tabular-nums text-ink-mute">
              {p.done}/{p.total}
            </span>
          </span>
        );
      },
    },
    { key: "created_at", header: "Started", render: (r) => <span className="whitespace-nowrap text-xs text-ink-mute">{timeAgo(r.created_at.replace(" ", "T"))}</span> },
    {
      key: "actions",
      header: "",
      sortable: false,
      render: (r) =>
        r.status === "awaiting_approval" ? (
          <Button
            variant="gold"
            size="sm"
            icon={<Lock className="h-3.5 w-3.5" />}
            loading={approve.isPending && approve.variables === r.id}
            onClick={(e) => {
              e.stopPropagation();
              approve.mutate(r.id);
            }}
          >
            Approve
          </Button>
        ) : null,
    },
  ];
  return (
    <Card>
      <CardHeader
        title="Agent runs"
        subtitle="Full audit trail — click a run for its step timeline"
        icon={<History className="h-4 w-4" />}
        action={awaiting > 0 && <Badge tone="gold" icon={<Lock className="h-3 w-3" />}>{awaiting} awaiting approval</Badge>}
      />
      <div className="p-3 sm:p-4">
        <QueryState q={q} skeleton={<Skeleton className="h-64" />}>
          {() => (
            <DataTable
              rows={rows}
              columns={cols}
              search
              pageSize={8}
              onRowClick={(r) => setOpen(r)}
              empty={<EmptyState title="No runs yet" hint="Run an agent from the AI Hub or a Smart Action." action={<ButtonLink to="/ai" size="sm">Open AI Hub</ButtonLink>} />}
            />
          )}
        </QueryState>
      </div>
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open?.agent_name ?? "Run"} width="max-w-2xl">
        {open && (
          <div className="space-y-4 p-5">
            <RunView run={open} onApprove={() => approve.mutate(open.id)} approving={approve.isPending} />
            <ButtonLink to={`/ai/agents/${open.agent_key}`} variant="outline" size="sm" icon={<Bot className="h-4 w-4" />}>
              Open agent
            </ButtonLink>
          </div>
        )}
      </Drawer>
    </Card>
  );
}

function LeadIntent() {
  const leads = useApi<{ count: number; leads: Lead[] }>("/crm/leads");
  const list = (leads.data?.leads ?? []).slice(0, 12);
  const scores = useQueries({
    queries: list.map((l) => ({ queryKey: ["/agents/move-likelihood", l.id], queryFn: () => get<MoveLikelihood>(`/agents/move-likelihood/${l.id}`), staleTime: 60_000 })),
  });
  return (
    <Card>
      <CardHeader title="Lead intent" subtitle="Move-likelihood score per CRM lead (0–100)" icon={<Target className="h-4 w-4" />} action={<ButtonLink to="/app/crm" variant="ghost" size="sm">CRM</ButtonLink>} />
      <CardBody>
        <QueryState q={leads} skeleton={<Skeleton className="h-48" />} empty={(d) => !d.leads?.length}>
          {() => (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {list.map((l, i) => {
                const s = scores[i];
                const m = s?.data?.move_likelihood;
                return (
                  <motion.div key={l.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="flex gap-3 rounded-2xl border border-black/5 p-3 dark:border-white/10">
                    {m ? <ScoreRing value={m.score} size={72} stroke={7} label={m.band} /> : <Skeleton className="h-[72px] w-[72px] rounded-full" />}
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-1.5 truncate font-semibold">
                        <UserRound className="h-3.5 w-3.5 shrink-0 text-ink-mute" /> {l.name}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        <StatusBadge status={l.status} />
                        {l.budget_max ? <Badge tone="gray">≤ {pkrShort(l.budget_max, false)}</Badge> : null}
                      </div>
                      {m ? (
                        <>
                          <p className="mt-1.5 text-xs font-medium text-brand-700 dark:text-brand-300">{m.recommended_action}</p>
                          <p className="truncate text-[11px] text-ink-mute" title={m.reasons.join(", ")}>
                            {m.reasons.join(" · ")}
                          </p>
                        </>
                      ) : s?.error ? (
                        <p className="mt-1.5 text-xs text-red-600">Couldn’t score</p>
                      ) : null}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </QueryState>
      </CardBody>
    </Card>
  );
}

export default function AgentOps() {
  const ov = useApi<Overview>("/agents/overview");
  const d = ov.data;
  const autonomy = d ? Object.entries(d.by_autonomy).map(([k, v], i) => ({ name: AUTONOMY[k]?.label ?? titleCase(k), value: v, color: [PALETTE[0], PALETTE[1], PALETTE[2]][i % 3] })) : [];
  const cats = d ? Object.entries(d.by_category).map(([k, v]) => ({ category: titleCase(k), agents: v })) : [];
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Agentic OS"
        title="Agent Ops"
        subtitle="Your agents, today’s priorities and every run waiting on a human."
        actions={
          <>
            <ButtonLink to="/ai#catalog" variant="outline" icon={<Boxes className="h-4 w-4" />}>
              Agent catalogue
            </ButtonLink>
            <ButtonLink to="/ai/mcp" variant="soft" icon={<Cpu className="h-4 w-4" />}>
              MCP console
            </ButtonLink>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {ov.isLoading ? (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)
        ) : (
          <>
            <StatCard label="Agents" value={d?.counts.agents ?? "—"} icon={<Bot className="h-5 w-5" />} hint="product + specialist" />
            <StatCard label="Products" value={d?.counts.products ?? "—"} icon={<Boxes className="h-5 w-5" />} tone="gold" hint={d ? `${d.by_priority.P0 ?? 0} at P0` : undefined} />
            <StatCard label="Autonomous" value={d?.counts.autonomous ?? "—"} icon={<Zap className="h-5 w-5" />} tone="blue" hint="no human gate" />
            <StatCard label="Runs recorded" value={d?.counts.runs_recorded ?? "—"} icon={<Sparkles className="h-5 w-5" />} tone="purple" hint="audit trail" />
          </>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Autonomy mix" subtitle="How much each agent may do alone" />
          <CardBody>
            {d ? (
              <>
                <Donut
                  data={autonomy}
                  height={210}
                  center={
                    <>
                      <span className="font-display text-2xl font-bold">{d.counts.agents}</span>
                      <span className="text-[10px] uppercase text-ink-mute">agents</span>
                    </>
                  }
                />
                <div className="mt-3">
                  <Legendish data={autonomy} />
                </div>
              </>
            ) : (
              <Skeleton className="h-60" />
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Agents by category" />
          <CardBody>{d ? <Bars data={cats} x="category" series={[{ key: "agents", label: "Agents" }]} colorByIndex height={260} format={(v) => String(v)} /> : <Skeleton className="h-64" />}</CardBody>
        </Card>
      </div>

      <SmartActions />
      <Runs />
      <LeadIntent />
    </div>
  );
}
