/**
 * The CRM dashboard (GET /crm/insights): KPIs, AI quick-ask, lead & activity trend, funnel,
 * "call now" priority leads with next best action, today's agenda, sources, pipeline, channel
 * mix, agent leaderboard and at-risk deals. Period and agent filters.
 */
import { lazy, Suspense, useState } from "react";
import {
  AlarmClock,
  AlertTriangle,
  Bot,
  CalendarClock,
  Clock3,
  Flame,
  Handshake,
  MessageCircle,
  Mic,
  PhoneCall,
  Send,
  Sparkles,
  Target,
  Trophy,
  UserPlus,
  UserX,
  Wallet,
} from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { date, num, pct, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, BarList, Button, EmptyState, ErrorState, Segmented, Select, Skeleton, StatCard } from "@/components/ui";
import { Panel, rs } from "@/components/biz/ops-kit";
import type { Agent } from "@/components/biz/crm-types";
import { ComposeModal } from "./ComposeModal";
import type { CrmInsights, PriorityLead } from "./types";

const AreaTrend = lazy(() => import("@/components/ui/charts").then((m) => ({ default: m.AreaTrend })));
const Bars = lazy(() => import("@/components/ui/charts").then((m) => ({ default: m.Bars })));
const Donut = lazy(() => import("@/components/ui/charts").then((m) => ({ default: m.Donut })));

const URGENCY = { urgent: "red", high: "orange", medium: "gold", low: "gray" } as const;
const TEMP = { hot: "red", warm: "orange", cold: "blue" } as const;
const SOURCE_COLORS = ["#146f45", "#c99a22", "#7c3aed", "#0891b2", "#db2777", "#ea580c", "#475569", "#16a34a"];

function ChartBox({ h = 220, children }: { h?: number; children: React.ReactNode }) {
  return <Suspense fallback={<div style={{ height: h }} className="w-full animate-pulse rounded-xl bg-black/5 dark:bg-white/10" />}>{children}</Suspense>;
}

export function CrmDashboardTab({ agents, onOpenLead, onAsk }: { agents: Agent[]; onOpenLead: (id: string) => void; onAsk: (q: string) => void }) {
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const [agentId, setAgentId] = useState("");
  const [quick, setQuick] = useState("");
  const [compose, setCompose] = useState<PriorityLead | null>(null);
  const q = useApi<CrmInsights>("/crm/insights", { days, agent_id: agentId || undefined }, { refetchInterval: 60_000 });
  const d = q.data;

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const k = d?.kpis;
  return (
    <div className="space-y-5 p-4 sm:p-5">
      {/* ---- filters + AI quick ask */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented<"7" | "30" | "90">
            size="sm"
            value={days}
            onChange={setDays}
            options={[
              { value: "7", label: "7 days" },
              { value: "30", label: "30 days" },
              { value: "90", label: "90 days" },
            ]}
          />
          <Select value={agentId} onChange={(e) => setAgentId(e.target.value)} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">Whole team</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </div>
        <form
          className="flex flex-1 items-center gap-2 rounded-2xl bg-gradient-to-r from-violet-600 to-brand-700 p-1.5 ps-3 shadow-soft"
          onSubmit={(e) => {
            e.preventDefault();
            if (quick.trim()) onAsk(quick.trim());
            setQuick("");
          }}
        >
          <Sparkles className="h-4 w-4 shrink-0 text-gold-300" />
          <input
            value={quick}
            onChange={(e) => setQuick(e.target.value)}
            placeholder="Ask your CRM: who should I call first? which deals are at risk?"
            className="h-9 min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-white/60"
            dir="auto"
          />
          <button type="button" onClick={() => onAsk("")} className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15 text-white hover:bg-white/25" title="Talk to the copilot" aria-label="Talk to the copilot">
            <Mic className="h-4 w-4" />
          </button>
          <button type="submit" className="flex h-9 items-center gap-1.5 rounded-xl bg-white px-3 text-sm font-semibold text-brand-800 hover:bg-gold-50">
            <Send className="h-4 w-4" /> Ask
          </button>
        </form>
      </div>

      {/* ---- KPIs */}
      {!k ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="New leads" value={num(k.leads_new)} icon={<UserPlus className="h-5 w-5" />} hint={`${num(k.leads_open)} open · ${num(k.leads_total)} total`} />
          <StatCard label="Hot leads" value={num(k.leads_hot)} icon={<Flame className="h-5 w-5" />} hint="Score 70+ and still open" tone="red" />
          <StatCard label="Not contacted" value={num(k.leads_uncontacted)} icon={<UserX className="h-5 w-5" />} hint="Open leads with no touch yet" tone={k.leads_uncontacted ? "gold" : "green"} />
          <StatCard
            label="First response"
            value={k.avg_first_response_hours == null ? "—" : k.avg_first_response_hours < 1 ? `${Math.round(k.avg_first_response_hours * 60)} min` : `${k.avg_first_response_hours} h`}
            icon={<Clock3 className="h-5 w-5" />}
            hint="Average time to first contact"
            tone="blue"
          />
          <StatCard label="Weighted pipeline" value={rs(k.pipeline_weighted)} icon={<Handshake className="h-5 w-5" />} hint={`${rs(k.pipeline_open)} open`} tone="gold" />
          <StatCard label="Won" value={rs(k.won_value)} icon={<Trophy className="h-5 w-5" />} hint={`${k.won_count} deals · commission ${rs(k.commission_won)}`} tone="green" />
          <StatCard label="Conversion" value={k.conversion_rate == null ? "—" : pct(k.conversion_rate, 0)} icon={<Target className="h-5 w-5" />} hint="Won ÷ closed leads" tone="purple" />
          <StatCard
            label="Tasks"
            value={`${num(k.tasks_overdue)} overdue`}
            icon={<AlarmClock className="h-5 w-5" />}
            hint={`${k.tasks_due_today} due today · ${k.appointments_week} visits this week`}
            tone={k.tasks_overdue ? "red" : "green"}
          />
        </div>
      )}

      {/* ---- trend + funnel */}
      <div className="grid gap-5 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title="Leads & activity" subtitle={`New leads and touches per day · last ${days} days`} icon={<Wallet className="h-5 w-5" />}>
          {d ? (
            <ChartBox>
              <AreaTrend
                data={d.trend.map((t) => ({ ...t, day: t.date.slice(5) }))}
                x="day"
                height={220}
                series={[
                  { key: "leads", label: "New leads", color: "#146f45" },
                  { key: "touches", label: "Touches", color: "#7c3aed" },
                ]}
              />
            </ChartBox>
          ) : (
            <Skeleton className="h-[220px] w-full" />
          )}
        </Panel>
        <Panel title="Lead funnel" subtitle="Leads that reached each stage" icon={<Target className="h-5 w-5" />}>
          {d ? (
            <div className="space-y-2">
              {d.funnel.map((f, i) => {
                const top = d.funnel[0]?.count || 1;
                return (
                  <div key={f.stage}>
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold capitalize">{f.stage}</span>
                      <span className="tabular-nums text-ink-mute">
                        {f.count}
                        {i > 0 && top ? ` · ${Math.round((100 * f.count) / top)}%` : ""}
                      </span>
                    </div>
                    <div className="mt-1 h-2.5 rounded-full bg-black/5 dark:bg-white/10">
                      <div className="h-full rounded-full bg-gradient-to-r from-brand-600 to-gold-500" style={{ width: `${Math.max(3, (100 * f.count) / top)}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </Panel>
      </div>

      {/* ---- call now + agenda */}
      <div className="grid gap-5 xl:grid-cols-3">
        <Panel
          className="xl:col-span-2"
          title="Call now"
          subtitle="Priority leads with the next best action"
          icon={<PhoneCall className="h-5 w-5" />}
          action={d?.ai ? <Badge tone="purple" icon={<Bot className="h-3 w-3" />}>AI on</Badge> : <Badge tone="gray">Rules</Badge>}
          flush
        >
          {!d ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : !d.priority_leads.length ? (
            <EmptyState title="Nothing urgent" hint="Every open lead has been followed up." />
          ) : (
            <ul className="divide-y divide-black/5 dark:divide-white/10">
              {d.priority_leads.map((l) => (
                <li key={l.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:flex-nowrap">
                  <button type="button" onClick={() => onOpenLead(l.id)} className="min-w-0 flex-1 text-start">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-semibold">{l.name}</span>
                      <Badge tone={TEMP[l.temperature]} className="capitalize">
                        {l.temperature} {l.score}
                      </Badge>
                      <Badge tone="gray" className="capitalize">
                        {l.status}
                      </Badge>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-ink-mute">
                      {[l.city, l.budget_max ? `up to ${rs(l.budget_max)}` : null, l.agent, l.last_contact_days == null ? "never contacted" : `last touch ${l.last_contact_days}d ago`]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <p className="mt-1 flex items-center gap-1.5 text-sm">
                      <Badge tone={URGENCY[l.urgency]} className="shrink-0 capitalize">
                        {l.urgency}
                      </Badge>
                      <span className="truncate">{l.action}</span>
                    </p>
                  </button>
                  <div className="flex shrink-0 gap-1.5">
                    {l.phone && (
                      <a href={`tel:${l.phone}`} className="btn btn-ghost btn-sm" title={`Call ${l.phone}`}>
                        <PhoneCall className="h-4 w-4" />
                      </a>
                    )}
                    <Button size="sm" variant="soft" icon={<MessageCircle className="h-4 w-4" />} onClick={() => setCompose(l)}>
                      Message
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Today's agenda" subtitle="Overdue, due today and upcoming visits" icon={<CalendarClock className="h-5 w-5" />} flush>
          {!d ? (
            <Skeleton className="m-4 h-48" />
          ) : (
            <div className="max-h-[420px] space-y-1 overflow-y-auto p-3">
              {[...d.agenda.overdue, ...d.agenda.today].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => t.related_type === "lead" && t.related_id && onOpenLead(t.related_id)}
                  className="flex w-full items-start gap-2 rounded-xl px-2 py-2 text-start hover:bg-black/[.03] dark:hover:bg-white/5"
                >
                  <AlarmClock className={cn("mt-0.5 h-4 w-4 shrink-0", t.overdue ? "text-red-600" : "text-gold-600")} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{t.title}</span>
                    <span className={cn("block text-[11px]", t.overdue ? "text-red-600" : "text-ink-mute")}>
                      {t.overdue ? "Overdue · " : "Today · "}
                      {t.due_date ? date(t.due_date) : "no date"} · {t.agent ?? "unassigned"}
                    </span>
                  </span>
                  <Badge tone={t.priority === "urgent" ? "red" : t.priority === "high" ? "orange" : "gray"} className="capitalize">
                    {t.priority}
                  </Badge>
                </button>
              ))}
              {d.agenda.appointments.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => a.lead_id && onOpenLead(a.lead_id)}
                  className="flex w-full items-start gap-2 rounded-xl px-2 py-2 text-start hover:bg-black/[.03] dark:hover:bg-white/5"
                >
                  <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{a.title}</span>
                    <span className="block text-[11px] text-ink-mute">
                      {date(a.scheduled_at, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · {a.agent ?? "unassigned"}
                    </span>
                  </span>
                </button>
              ))}
              {!d.agenda.overdue.length && !d.agenda.today.length && !d.agenda.appointments.length && <EmptyState title="All clear" hint="No tasks due and no visits this week." />}
            </div>
          )}
        </Panel>
      </div>

      {/* ---- sources, pipeline, channels */}
      <div className="grid gap-5 lg:grid-cols-3">
        <Panel title="Lead sources" subtitle="Where leads come from" icon={<UserPlus className="h-5 w-5" />}>
          {d ? (
            d.by_source.length ? (
              <ChartBox h={200}>
                <Donut
                  height={200}
                  data={d.by_source.map((s, i) => ({ name: titleCase(s.source), value: s.count, color: SOURCE_COLORS[i % SOURCE_COLORS.length] }))}
                  center={<span className="text-xs font-bold">{num(d.kpis.leads_total)} leads</span>}
                />
              </ChartBox>
            ) : (
              <EmptyState title="No leads yet" />
            )
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </Panel>
        <Panel title="Pipeline by stage" subtitle="Deal value in each stage" icon={<Handshake className="h-5 w-5" />}>
          {d ? (
            <ChartBox h={200}>
              <Bars
                data={d.pipeline.filter((p) => p.count).map((p) => ({ stage: titleCase(p.stage), value: p.value }))}
                x="stage"
                height={200}
                series={[{ key: "value", label: "Value" }]}
                format={(v: number) => rs(v)}
                colorByIndex
              />
            </ChartBox>
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </Panel>
        <Panel title="Channels used" subtitle={`Touches in the last ${days} days`} icon={<MessageCircle className="h-5 w-5" />}>
          {d ? (
            d.channel_mix.length ? (
              <BarList items={d.channel_mix.map((c) => ({ label: titleCase(c.channel), value: c.count }))} />
            ) : (
              <EmptyState title="No activity" hint="Log calls, notes and messages from a lead." />
            )
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </Panel>
      </div>

      {/* ---- team + risk */}
      <div className="grid gap-5 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title="Agent leaderboard" subtitle="Won value, pipeline and follow-up discipline" icon={<Trophy className="h-5 w-5" />} flush>
          {!d ? (
            <Skeleton className="m-4 h-40" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[11px] uppercase tracking-wider text-ink-mute">
                  <tr className="border-b border-black/5 dark:border-white/10">
                    <th className="px-4 py-2 text-start">Agent</th>
                    <th className="px-2 py-2 text-end">Leads</th>
                    <th className="px-2 py-2 text-end">Contacted</th>
                    <th className="px-2 py-2 text-end">Hot</th>
                    <th className="px-2 py-2 text-end">Won</th>
                    <th className="px-2 py-2 text-end">Pipeline</th>
                    <th className="px-4 py-2 text-end">Overdue</th>
                  </tr>
                </thead>
                <tbody>
                  {d.agents.map((a, i) => (
                    <tr key={a.agent_id} className="border-b border-black/5 last:border-0 dark:border-white/10">
                      <td className="px-4 py-2.5">
                        <span className="me-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-gold-100 text-[11px] font-bold text-gold-800 dark:bg-gold-500/20 dark:text-gold-100">{i + 1}</span>
                        <span className="font-semibold">{a.name}</span>
                        {!a.active && <Badge tone="gray" className="ms-2">inactive</Badge>}
                      </td>
                      <td className="px-2 py-2.5 text-end tabular-nums">{a.leads}</td>
                      <td className={cn("px-2 py-2.5 text-end tabular-nums", (a.contacted_pct ?? 100) < 60 && "font-semibold text-red-600")}>{a.contacted_pct == null ? "—" : `${a.contacted_pct}%`}</td>
                      <td className="px-2 py-2.5 text-end tabular-nums">{a.hot}</td>
                      <td className="px-2 py-2.5 text-end tabular-nums">
                        {a.won_count} · {rs(a.won_value)}
                      </td>
                      <td className="px-2 py-2.5 text-end tabular-nums">{rs(a.pipeline)}</td>
                      <td className={cn("px-4 py-2.5 text-end tabular-nums", a.overdue_tasks > 0 && "font-semibold text-red-600")}>{a.overdue_tasks}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel title="Deals at risk" subtitle="Silent or past their close date" icon={<AlertTriangle className="h-5 w-5" />} flush>
          {!d ? (
            <Skeleton className="m-4 h-40" />
          ) : !d.at_risk_deals.length ? (
            <EmptyState title="No deals at risk" hint="Every open deal has recent contact." />
          ) : (
            <ul className="divide-y divide-black/5 dark:divide-white/10">
              {d.at_risk_deals.map((x) => (
                <li key={x.id} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate font-semibold">{x.title}</span>
                    <span className="shrink-0 text-sm font-bold">{rs(x.amount)}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-ink-mute">
                    {titleCase(x.stage)} · {x.probability}% · {x.agent ?? "unassigned"}
                  </p>
                  <p className="mt-1 text-xs text-red-600">{x.reasons.join(" · ")}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <ComposeModal open={!!compose} onClose={() => setCompose(null)} entityId={compose?.id ?? null} name={compose?.name} channel={compose?.phone ? "whatsapp" : "email"} />
    </div>
  );
}
