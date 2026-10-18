import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Bot,
  CalendarCheck,
  Inbox,
  Gauge,
  RadioTower,
  CalendarClock,
  CheckCircle2,
  Circle,
  Handshake,
  KanbanSquare,
  ListTodo,
  Mail,
  MapPin,
  Phone,
  Plus,
  Radar,
  Trophy,
  UserRound,
  Users,
  Wallet,
} from "lucide-react";
import { post, put } from "@/lib/api";
import { useApi, useMutate } from "@/hooks/useApi";
import { date, num, pct, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Avatar, Badge, BarList, Button, Card, DataTable, EmptyState, Field, Input, Modal, PageHeader, Progress, QueryState, ScoreRing, Segmented, Select, Skeleton, StatCard, StatusBadge, Tabs, Textarea, type Column } from "@/components/ui";
import { Bars } from "@/components/ui/charts";
import { FormGrid, MiniStat, Panel, ScoreBar, SkeletonGrid, Stars, bandTone, crShort, sentence, ensure, isoDay, numOr, stagger, useFormState, rs } from "@/components/biz/ops-kit";
import { CrmLeadDrawer } from "@/components/biz/CrmLeadDrawer";
import { CrmPipelineBoard } from "@/components/biz/CrmPipelineBoard";
import { CrmInboxTab } from "@/components/crm/CrmInboxTab";
import { CrmChannelsTab } from "@/components/crm/CrmChannelsTab";
import { CrmCopilot } from "@/components/crm/CrmCopilot";
import {
  LEAD_SOURCES,
  LEAD_STATUSES,
  TASK_PRIORITIES,
  type Agent,
  type AgentsRes,
  type Appointment,
  type Customer,
  type Deal,
  type DealsRes,
  type Lead,
  type LeadsRes,
  type Task,
} from "@/components/biz/crm-types";
import type { City } from "@/types";

type TabKey = "leads" | "pipeline" | "deals" | "customers" | "agents" | "tasks" | "appointments" | "inbox" | "channels" | "broker";
const TAB_KEYS: TabKey[] = ["leads", "pipeline", "deals", "customers", "agents", "tasks", "appointments", "inbox", "channels", "broker"];

interface CrmDashboard {
  agents: number;
  leads: { total: number; by_status: Record<string, number> };
  customers: number;
  deals: { total: number; open_value: number; won_value: number };
  tasks: { total: number; open: number };
  appointments: number;
}

const INVALIDATE = ["/crm", "/broker", "/portal", "/agents", "/marketing"];

export default function Crm() {
  const [params, setParams] = useSearchParams();
  const tabParam = params.get("tab") as TabKey | null;
  const tab: TabKey = tabParam && TAB_KEYS.includes(tabParam) ? tabParam : "leads";
  const setTab = (t: TabKey) => setParams((p) => {
    const n = new URLSearchParams(p);
    if (t === "leads") n.delete("tab");
    else n.set("tab", t);
    return n;
  }, { replace: true });
  const [copilot, setCopilot] = useState(false);
  const [copilotQ, setCopilotQ] = useState<string | undefined>();
  const [leadId, setLeadId] = useState<string | null>(null);
  const [newLead, setNewLead] = useState(false);
  const [newTask, setNewTask] = useState(false);

  const dash = useApi<CrmDashboard>("/crm/dashboard");
  const agentsQ = useApi<AgentsRes>("/crm/agents");
  const agents = agentsQ.data?.agents ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="CRM"
        subtitle="Smart sales hub — leads, pipeline, follow-ups, WhatsApp / e-mail / SMS and your AI copilot"
        actions={
          <>
            <Link to="/app/crm-dashboard" className="btn btn-outline btn-sm">
              <Gauge className="h-4 w-4" /> Dashboard
            </Link>
            <Button
              variant="gold"
              size="sm"
              icon={<Bot className="h-4 w-4" />}
              onClick={() => {
                setCopilotQ(undefined);
                setCopilot(true);
              }}
            >
              AI copilot
            </Button>
            <Button variant="outline" size="sm" icon={<ListTodo className="h-4 w-4" />} onClick={() => setNewTask(true)}>
              New task
            </Button>
            <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setNewLead(true)}>
              New lead
            </Button>
          </>
        }
      />

      <QueryState q={dash} skeleton={<SkeletonGrid n={4} />}>
        {(d) => (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Leads" value={num(d.leads.total)} icon={<Users className="h-5 w-5" />} hint={`${d.leads.by_status.new ?? 0} new · ${d.leads.by_status.qualified ?? 0} qualified`} />
            <StatCard label="Open pipeline" value={rs(d.deals.open_value)} icon={<Handshake className="h-5 w-5" />} hint={`${d.deals.total} deals`} tone="gold" />
            <StatCard label="Won value" value={rs(d.deals.won_value)} icon={<Trophy className="h-5 w-5" />} hint={`${d.customers} customers`} tone="blue" />
            <StatCard label="Open tasks" value={num(d.tasks.open)} icon={<ListTodo className="h-5 w-5" />} hint={`${d.appointments} appointments`} tone="purple" />
          </div>
        )}
      </QueryState>

      <Card className="overflow-hidden">
        <Tabs<TabKey>
          className="px-2"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "leads", label: "Leads", icon: <Users className="h-4 w-4" />, count: dash.data?.leads.total },
            { value: "pipeline", label: "Pipeline", icon: <KanbanSquare className="h-4 w-4" /> },
            { value: "deals", label: "Deals", icon: <Handshake className="h-4 w-4" />, count: dash.data?.deals.total },
            { value: "customers", label: "Customers", icon: <UserRound className="h-4 w-4" />, count: dash.data?.customers },
            { value: "agents", label: "Agents", icon: <Trophy className="h-4 w-4" />, count: dash.data?.agents },
            { value: "tasks", label: "Tasks", icon: <ListTodo className="h-4 w-4" />, count: dash.data?.tasks.open },
            { value: "appointments", label: "Appointments", icon: <CalendarClock className="h-4 w-4" />, count: dash.data?.appointments },
            { value: "inbox", label: "Inbox", icon: <Inbox className="h-4 w-4" /> },
            { value: "channels", label: "Channels", icon: <RadioTower className="h-4 w-4" /> },
            { value: "broker", label: "Broker intel", icon: <Radar className="h-4 w-4" /> },
          ]}
        />
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
          {tab === "inbox" && <CrmInboxTab onOpenLead={setLeadId} />}
          {tab === "channels" && <CrmChannelsTab />}
          {tab === "leads" && <LeadsTab agents={agents} onOpen={setLeadId} />}
          {tab === "pipeline" && (
            <div className="p-4 sm:p-5">
              <CrmPipelineBoard agents={agents} />
            </div>
          )}
          {tab === "deals" && <DealsTab agents={agents} />}
          {tab === "customers" && <CustomersTab agents={agents} />}
          {tab === "agents" && <AgentsTab q={agentsQ} />}
          {tab === "tasks" && <TasksTab agents={agents} onNew={() => setNewTask(true)} />}
          {tab === "appointments" && <AppointmentsTab agents={agents} />}
          {tab === "broker" && <BrokerTab agents={agents} onOpen={setLeadId} />}
        </motion.div>
      </Card>

      <CrmLeadDrawer leadId={leadId} agents={agents} onClose={() => setLeadId(null)} />
      <CrmCopilot
        open={copilot}
        initial={copilotQ}
        onClose={() => setCopilot(false)}
        onOpenLead={(id) => {
          setCopilot(false);
          setLeadId(id);
        }}
      />
      <NewLeadModal open={newLead} onClose={() => setNewLead(false)} agents={agents} />
      <NewTaskModal open={newTask} onClose={() => setNewTask(false)} agents={agents} />
    </div>
  );
}

// ================================================================== Leads
function LeadsTab({ agents, onOpen }: { agents: Agent[]; onOpen: (id: string) => void }) {
  const [status, setStatus] = useState("");
  const q = useApi<LeadsRes>("/crm/leads", { status: status || undefined });
  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);

  const columns: Column<Lead>[] = [
    {
      key: "name",
      header: "Lead",
      render: (l) => (
        <div className="flex min-w-[180px] items-center gap-3">
          <Avatar name={l.name} size={34} />
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink dark:text-white">{l.name}</p>
            <p className="truncate text-xs text-ink-mute">{l.email ?? l.phone ?? "—"}</p>
          </div>
        </div>
      ),
    },
    { key: "score", header: "Score", render: (l) => <ScoreBar value={l.score} className="w-28" /> },
    { key: "status", header: "Status", render: (l) => <StatusBadge status={l.status} /> },
    {
      key: "interest",
      header: "Interest",
      value: (l) => `${l.interest_category ?? ""} ${l.city_name ?? ""}`,
      render: (l) => (
        <div className="min-w-[120px] text-xs">
          <p className="font-medium text-ink-soft dark:text-slate-300">{titleCase(l.interest_category) || "—"}</p>
          <p className="text-ink-mute">{l.city_name ?? "Any city"}</p>
        </div>
      ),
    },
    {
      key: "budget",
      header: "Budget",
      align: "right",
      value: (l) => l.budget_max ?? 0,
      render: (l) => <span className="whitespace-nowrap text-xs font-semibold">{l.budget_max ? `≤ ${pkrShort(l.budget_max, false)}` : "—"}</span>,
    },
    { key: "source", header: "Source", render: (l) => <span className="text-xs">{titleCase(l.source)}</span> },
    {
      key: "agent",
      header: "Agent",
      value: (l) => l.agent_name ?? (l.assigned_agent_id ? agentName[l.assigned_agent_id] : ""),
      render: (l) => {
        const n = l.agent_name ?? (l.assigned_agent_id ? agentName[l.assigned_agent_id] : null);
        return n ? (
          <span className="inline-flex items-center gap-2 whitespace-nowrap text-xs">
            <Avatar name={n} size={22} />
            {n}
          </span>
        ) : (
          <Badge tone="gray">Unassigned</Badge>
        );
      },
    },
    { key: "created_at", header: "Created", render: (l) => <span className="whitespace-nowrap text-xs text-ink-mute">{timeAgo(l.created_at)}</span> },
  ];

  return (
    <QueryState q={q} skeleton={<div className="space-y-2 p-5">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12" />)}</div>}>
      {(d) => (
        <DataTable
          rows={d.leads}
          columns={columns}
          search
          onRowClick={(l) => onOpen(l.id)}
          toolbar={
            <Select className="w-40 py-2" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {LEAD_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {titleCase(s)}
                </option>
              ))}
            </Select>
          }
          empty={<EmptyState title="No leads" hint="Add a lead or change the status filter." />}
        />
      )}
    </QueryState>
  );
}

// ================================================================== Deals
function DealsTab({ agents }: { agents: Agent[] }) {
  const q = useApi<DealsRes>("/crm/deals");
  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const columns: Column<Deal>[] = [
    { key: "title", header: "Deal", render: (d) => <span className="font-semibold text-ink dark:text-white">{d.title}</span> },
    { key: "amount", header: "Amount", align: "right", render: (d) => <span className="whitespace-nowrap font-semibold">{pkrShort(d.amount)}</span> },
    { key: "stage", header: "Stage", render: (d) => <StatusBadge status={d.stage} /> },
    {
      key: "probability",
      header: "Probability",
      render: (d) => (
        <div className="flex w-28 items-center gap-2">
          <Progress value={d.probability} className="h-1.5" tone={d.probability >= 60 ? "green" : d.probability >= 30 ? "gold" : "red"} />
          <span className="text-xs font-semibold tabular-nums">{d.probability}%</span>
        </div>
      ),
    },
    { key: "weighted", header: "Weighted", align: "right", value: (d) => (d.amount * d.probability) / 100, render: (d) => <span className="whitespace-nowrap text-xs">{pkrShort((d.amount * d.probability) / 100, false)}</span> },
    { key: "commission", header: "Commission", align: "right", render: (d) => <span className="whitespace-nowrap text-xs">{pkrShort(d.commission, false)}</span> },
    { key: "agent_id", header: "Agent", value: (d) => (d.agent_id ? agentName[d.agent_id] : ""), render: (d) => <span className="whitespace-nowrap text-xs">{d.agent_id ? agentName[d.agent_id] ?? "—" : "—"}</span> },
    { key: "expected_close_date", header: "Close", render: (d) => <span className="whitespace-nowrap text-xs text-ink-mute">{date(d.expected_close_date)}</span> },
  ];
  return (
    <QueryState q={q} skeleton={<div className="p-5"><Skeleton className="h-60" /></div>}>
      {(d) => <DataTable rows={d.deals} columns={columns} search empty={<EmptyState title="No deals yet" />} />}
    </QueryState>
  );
}

// ================================================================== Customers
function CustomersTab({ agents }: { agents: Agent[] }) {
  const [type, setType] = useState("");
  const q = useApi<{ count: number; customers: Customer[] }>("/crm/customers", { type: type || undefined });
  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const columns: Column<Customer>[] = [
    {
      key: "name",
      header: "Customer",
      render: (c) => (
        <div className="flex min-w-[180px] items-center gap-3">
          <Avatar name={c.name} size={34} />
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink dark:text-white">{c.name}</p>
            <p className="truncate text-xs text-ink-mute">{c.email ?? "—"}</p>
          </div>
        </div>
      ),
    },
    { key: "type", header: "Type", render: (c) => <Badge tone={c.type === "investor" ? "purple" : c.type === "buyer" ? "green" : "blue"}>{titleCase(c.type)}</Badge> },
    { key: "phone", header: "Phone", render: (c) => <span className="whitespace-nowrap text-xs">{c.phone ?? "—"}</span> },
    { key: "assigned_agent_id", header: "Agent", value: (c) => (c.assigned_agent_id ? agentName[c.assigned_agent_id] : ""), render: (c) => <span className="text-xs">{c.assigned_agent_id ? agentName[c.assigned_agent_id] ?? "—" : "—"}</span> },
    { key: "source_lead_id", header: "Origin", render: (c) => <span className="text-xs text-ink-mute">{c.source_lead_id ? "Converted lead" : "Direct"}</span> },
    { key: "created_at", header: "Since", render: (c) => <span className="whitespace-nowrap text-xs text-ink-mute">{date(c.created_at)}</span> },
  ];
  return (
    <QueryState q={q} skeleton={<div className="p-5"><Skeleton className="h-48" /></div>}>
      {(d) => (
        <DataTable
          rows={d.customers}
          columns={columns}
          search
          toolbar={
            <Select className="w-36 py-2" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All types</option>
              {["buyer", "seller", "tenant", "landlord", "investor"].map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </Select>
          }
          empty={<EmptyState title="No customers" hint="Convert a qualified lead to create one." />}
        />
      )}
    </QueryState>
  );
}

// ================================================================== Agents
function AgentsTab({ q }: { q: ReturnType<typeof useApi<AgentsRes>> }) {
  const proj = useApi<{ by_agent: Record<string, number> }>("/broker/commission-projection");
  return (
    <div className="p-4 sm:p-5">
      <QueryState q={q} skeleton={<SkeletonGrid n={3} className="lg:grid-cols-3" tile="h-56" />}>
        {(d) =>
          d.agents.length ? (
            <motion.div variants={stagger.container} initial="hidden" animate="show" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {[...d.agents]
                .sort((a, b) => b.rating - a.rating)
                .map((a, i) => (
                  <motion.div key={a.id} variants={stagger.item} className="card card-hover relative overflow-hidden p-5">
                    {i === 0 && (
                      <span className="absolute end-4 top-4">
                        <Badge tone="gold" icon={<Trophy className="h-3 w-3" />}>
                          Top rated
                        </Badge>
                      </span>
                    )}
                    <div className="flex items-center gap-3">
                      <Avatar name={a.name} size={52} online={a.active} />
                      <div className="min-w-0">
                        <p className="truncate font-display text-lg font-semibold">{a.name}</p>
                        <p className="flex items-center gap-1 text-xs text-ink-mute">
                          <MapPin className="h-3 w-3" /> {a.region ?? "—"} · {titleCase(a.specialization)}
                        </p>
                        <div className="mt-1 flex items-center gap-1.5">
                          <Stars value={a.rating} />
                          <span className="text-xs font-semibold">{a.rating.toFixed(1)}</span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-3 gap-2">
                      <MiniStat label="Closed" value={a.deals_closed} />
                      <MiniStat label="Comm." value={pct(a.commission_rate)} tone="gold" />
                      <MiniStat label="Pipeline" value={proj.data ? pkrShort(proj.data.by_agent[a.id] ?? 0, false) : "…"} tone="green" hint="wtd comm." />
                    </div>
                    <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 border-t border-black/5 pt-3 text-xs text-ink-mute dark:border-white/10">
                      {a.phone && (
                        <a href={`tel:${a.phone}`} className="inline-flex items-center gap-1 hover:text-brand-700">
                          <Phone className="h-3.5 w-3.5" /> {a.phone}
                        </a>
                      )}
                      {a.email && (
                        <a href={`mailto:${a.email}`} className="inline-flex min-w-0 items-center gap-1 truncate hover:text-brand-700">
                          <Mail className="h-3.5 w-3.5" /> {a.email}
                        </a>
                      )}
                    </div>
                  </motion.div>
                ))}
            </motion.div>
          ) : (
            <EmptyState title="No agents" />
          )
        }
      </QueryState>
    </div>
  );
}

// ================================================================== Tasks
function TasksTab({ agents, onNew }: { agents: Agent[]; onNew: () => void }) {
  const [filter, setFilter] = useState<"open" | "done" | "all">("open");
  const q = useApi<{ count: number; tasks: Task[] }>("/crm/tasks");
  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const toggle = useMutate((t: Task) => put(`/crm/tasks/${t.id}/complete`, { status: t.status === "done" ? "open" : "done" }).then(ensure), {
    invalidate: ["/crm"],
    success: (r: Task) => (r?.status === "done" ? "Task completed" : "Task reopened"),
  });
  const PRI_ORDER: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 };

  return (
    <div className="p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Segmented
          size="sm"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "open", label: "Open" },
            { value: "done", label: "Done" },
            { value: "all", label: "All" },
          ]}
        />
        <Button size="sm" variant="soft" icon={<Plus className="h-4 w-4" />} onClick={onNew}>
          Add task
        </Button>
      </div>
      <QueryState q={q} skeleton={<div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>}>
        {(d) => {
          const rows = d.tasks
            .filter((t) => (filter === "all" ? true : filter === "done" ? t.status === "done" : t.status !== "done" && t.status !== "cancelled"))
            .sort((a, b) => (PRI_ORDER[a.priority] ?? 9) - (PRI_ORDER[b.priority] ?? 9) || String(a.due_date ?? "9").localeCompare(String(b.due_date ?? "9")));
          if (!rows.length) return <EmptyState title={filter === "open" ? "Inbox zero" : "No tasks"} hint={filter === "open" ? "Every follow-up is done." : undefined} icon={<CheckCircle2 className="h-6 w-6" />} />;
          const todayIso = isoDay(0);
          return (
            <ul className="space-y-2">
              {rows.map((t) => {
                const done = t.status === "done";
                const overdue = !done && t.due_date && t.due_date < todayIso;
                return (
                  <li key={t.id} className={cn("flex items-start gap-3 rounded-xl border border-black/5 p-3 transition-colors dark:border-white/10", done && "opacity-60")}>
                    <button
                      type="button"
                      aria-label={done ? "Reopen task" : "Complete task"}
                      disabled={toggle.isPending && toggle.variables?.id === t.id}
                      onClick={() => toggle.mutate(t)}
                      className="mt-0.5 shrink-0 text-brand-600 transition-transform hover:scale-110 disabled:opacity-50"
                    >
                      {done ? <CheckCircle2 className="h-5 w-5" /> : <Circle className="h-5 w-5 text-ink-mute/60 hover:text-brand-600" />}
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className={cn("text-sm font-semibold", done && "line-through")}>{t.title}</p>
                      {t.description && <p className="mt-0.5 text-xs text-ink-mute">{t.description}</p>}
                      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-mute">
                        <Badge tone={bandTone(t.priority)} className="capitalize">
                          {t.priority}
                        </Badge>
                        {t.related_type && <span>{titleCase(t.related_type)}</span>}
                        {t.assigned_agent_id && (
                          <span className="inline-flex items-center gap-1">
                            <Avatar name={agentName[t.assigned_agent_id]} size={16} /> {agentName[t.assigned_agent_id] ?? "Agent"}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className={cn("shrink-0 text-end text-xs font-semibold", overdue ? "text-red-600" : "text-ink-mute")}>
                      {t.due_date ? date(t.due_date, { day: "numeric", month: "short" }) : "No due date"}
                      {overdue && <p className="text-[10px] uppercase">overdue</p>}
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </QueryState>
    </div>
  );
}

// ================================================================== Appointments
function AppointmentsTab({ agents }: { agents: Agent[] }) {
  const q = useApi<{ count: number; appointments: Appointment[] }>("/crm/appointments");
  const leads = useApi<LeadsRes>("/crm/leads");
  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const leadName = useMemo(() => Object.fromEntries((leads.data?.leads ?? []).map((l) => [l.id, l.name])), [leads.data]);
  return (
    <div className="p-4 sm:p-5">
      <QueryState q={q} skeleton={<div className="space-y-2">{[0, 1].map((i) => <Skeleton key={i} className="h-20" />)}</div>}>
        {(d) =>
          d.appointments.length ? (
            <ul className="grid gap-3 md:grid-cols-2">
              {[...d.appointments]
                .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
                .map((a) => {
                  const dt = new Date(a.scheduled_at);
                  return (
                    <li key={a.id} className="flex gap-4 rounded-2xl border border-black/5 p-4 dark:border-white/10">
                      <div className="flex w-14 shrink-0 flex-col items-center justify-center rounded-xl bg-brand-gradient py-2 text-white">
                        <span className="text-[10px] font-semibold uppercase tracking-wide text-gold-200">{dt.toLocaleDateString("en-GB", { month: "short" })}</span>
                        <span className="font-display text-xl font-bold leading-none">{dt.getDate()}</span>
                        <span className="mt-0.5 text-[10px] text-white/70">{dt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-semibold">{a.title}</p>
                          <StatusBadge status={a.status} />
                        </div>
                        <div className="mt-1.5 space-y-1 text-xs text-ink-mute">
                          {a.lead_id && (
                            <p className="flex items-center gap-1.5">
                              <Users className="h-3.5 w-3.5" /> {leadName[a.lead_id] ?? "Lead"}
                            </p>
                          )}
                          {a.agent_id && (
                            <p className="flex items-center gap-1.5">
                              <UserRound className="h-3.5 w-3.5" /> {agentName[a.agent_id] ?? "Agent"}
                            </p>
                          )}
                          <p className="flex items-center gap-1.5">
                            <CalendarCheck className="h-3.5 w-3.5" /> {timeAgo(a.scheduled_at)}
                          </p>
                        </div>
                      </div>
                    </li>
                  );
                })}
            </ul>
          ) : (
            <EmptyState title="No appointments scheduled" />
          )
        }
      </QueryState>
    </div>
  );
}

// ================================================================== Broker intel
interface Contact {
  id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  status: string;
  source: string;
  city?: string | null;
  budget_max?: number | null;
  intent_score: number;
  band: string;
  lifecycle: string;
  days_since_contact: number;
  recommended_action: string;
  reasons: string[];
}
interface Projection {
  horizon_days: number;
  commission_rate: number;
  closed_commission: number;
  weighted_pipeline_commission: number;
  expected_total: number;
  upcoming_closings: { deal_id: string; title: string; amount: number; stage: string; probability: number; days_to_close: number; commission: number; weighted_commission: number }[];
  by_agent: Record<string, number>;
  by_stage: Record<string, number>;
}

function BrokerTab({ agents, onOpen }: { agents: Agent[]; onOpen: (id: string) => void }) {
  const [minIntent, setMinIntent] = useState("");
  const [horizon, setHorizon] = useState("90");
  const contacts = useApi<{ count: number; contacts: Contact[] }>("/broker/contacts", { min_intent_score: minIntent || undefined, limit: 100 });
  const proj = useApi<Projection>("/broker/commission-projection", { horizon_days: horizon });
  const agentName = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);

  const columns: Column<Contact>[] = [
    {
      key: "name",
      header: "Contact",
      render: (c) => (
        <div className="flex min-w-[170px] items-center gap-3">
          <ScoreRing value={c.intent_score} size={42} stroke={5} />
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink dark:text-white">{c.name}</p>
            <p className="truncate text-xs text-ink-mute">
              {c.city ?? "—"} · {titleCase(c.source)}
            </p>
          </div>
        </div>
      ),
      value: (c) => c.name,
    },
    { key: "intent_score", header: "Intent", align: "right", render: (c) => <span className="font-semibold tabular-nums">{c.intent_score.toFixed(1)}</span> },
    { key: "band", header: "Band", render: (c) => <Badge tone={bandTone(c.band)} className="capitalize">{c.band}</Badge> },
    { key: "status", header: "Status", render: (c) => <StatusBadge status={c.status} /> },
    { key: "budget_max", header: "Budget", align: "right", render: (c) => <span className="whitespace-nowrap text-xs">{c.budget_max ? pkrShort(c.budget_max, false) : "—"}</span> },
    { key: "recommended_action", header: "Next best action", render: (c) => <span className="text-xs text-ink-soft dark:text-slate-300">{sentence(c.recommended_action)}</span> },
  ];

  return (
    <div className="grid gap-5 p-4 sm:p-5 2xl:grid-cols-5">
      <div className="min-w-0 2xl:col-span-3">
        <Card className="overflow-hidden">
          <QueryState q={contacts} skeleton={<div className="p-5"><Skeleton className="h-64" /></div>}>
            {(d) => (
              <DataTable
                rows={d.contacts}
                columns={columns}
                search
                onRowClick={(c) => onOpen(c.id)}
                toolbar={
                  <Select className="w-40 py-2" value={minIntent} onChange={(e) => setMinIntent(e.target.value)}>
                    <option value="">Any intent</option>
                    <option value="40">Intent ≥ 40</option>
                    <option value="55">Intent ≥ 55</option>
                    <option value="70">Intent ≥ 70</option>
                  </Select>
                }
                empty={<EmptyState title="No contacts match" />}
              />
            )}
          </QueryState>
        </Card>
      </div>
      <div className="min-w-0 2xl:col-span-2">
        <Panel
          title="Commission projection"
          subtitle="Realised + weighted pipeline"
          icon={<Wallet className="h-4 w-4" />}
          action={
            <Select className="w-28 py-1.5 text-xs" value={horizon} onChange={(e) => setHorizon(e.target.value)}>
              {["30", "60", "90", "180", "365"].map((h) => (
                <option key={h} value={h}>
                  {h} days
                </option>
              ))}
            </Select>
          }
        >
          <QueryState q={proj} skeleton={<Skeleton className="h-72" />}>
            {(p) => (
              <div className="space-y-5">
                <div className="grid grid-cols-3 gap-2">
                  <MiniStat label="Closed" value={pkrShort(p.closed_commission, false)} />
                  <MiniStat label="Weighted" value={pkrShort(p.weighted_pipeline_commission, false)} tone="gold" />
                  <MiniStat label="Expected" value={pkrShort(p.expected_total, false)} tone="green" />
                </div>
                {Object.keys(p.by_agent).length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">By agent</p>
                    <Bars
                      data={Object.entries(p.by_agent).map(([id, v]) => ({ agent: agentName[id]?.split(" ")[0] ?? "Agent", value: v }))}
                      x="agent"
                      series={[{ key: "value", label: "Weighted commission" }]}
                      height={180}
                      colorByIndex
                      format={crShort}
                    />
                  </div>
                )}
                {Object.keys(p.by_stage).length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">By stage</p>
                    <BarList tone="gold" items={Object.entries(p.by_stage).map(([k, v]) => ({ label: titleCase(k), value: v }))} format={(v) => pkrShort(v, false)} />
                  </div>
                )}
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Closing within {p.horizon_days} days</p>
                  {p.upcoming_closings.length ? (
                    <ul className="space-y-2">
                      {p.upcoming_closings.map((c) => (
                        <li key={c.deal_id} className="flex items-center justify-between gap-3 rounded-xl bg-brand-50/50 px-3 py-2 text-sm dark:bg-white/5">
                          <div className="min-w-0">
                            <p className="truncate font-medium">{c.title}</p>
                            <p className="text-xs text-ink-mute">
                              {titleCase(c.stage)} · {c.probability}% · in {c.days_to_close}d
                            </p>
                          </div>
                          <span className="shrink-0 text-end">
                            <span className="block font-semibold text-brand-700 dark:text-brand-300">{pkrShort(c.weighted_commission, false)}</span>
                            <span className="text-[11px] text-ink-mute">of {pkrShort(c.commission, false)}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-ink-mute">No dated closings in this horizon.</p>
                  )}
                </div>
              </div>
            )}
          </QueryState>
        </Panel>
      </div>
    </div>
  );
}

// ================================================================== Modals
function NewLeadModal({ open, onClose, agents }: { open: boolean; onClose: () => void; agents: Agent[] }) {
  const cities = useApi<{ cities: City[] }>(open ? "/cities" : null);
  const [f, set, reset] = useFormState({
    name: "",
    email: "",
    phone: "",
    source: "website",
    interest_use_type: "residential",
    interest_category: "house",
    budget_min: "",
    budget_max: "",
    city_id: "",
    assigned_agent_id: "",
    notes: "",
  });
  const create = useMutate(
    () =>
      post("/crm/leads", {
        name: f.name.trim(),
        email: f.email || undefined,
        phone: f.phone || undefined,
        source: f.source,
        interest_use_type: f.interest_use_type || undefined,
        interest_category: f.interest_category || undefined,
        budget_min: numOr(f.budget_min),
        budget_max: numOr(f.budget_max),
        city_id: f.city_id || undefined,
        assigned_agent_id: f.assigned_agent_id || undefined,
        notes: f.notes || undefined,
      }).then(ensure),
    {
      invalidate: INVALIDATE,
      success: "Lead added",
      onSuccess: () => {
        reset();
        onClose();
      },
    },
  );
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New lead"
      subtitle="Capture a prospect and route it to an agent"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} disabled={!f.name.trim()} onClick={() => create.mutate()}>
            Add lead
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (f.name.trim()) create.mutate();
        }}
      >
        <FormGrid>
          <Field label="Full name *">
            <Input value={f.name} onChange={(e) => set("name")(e.target.value)} placeholder="e.g. Hassan Raza" autoFocus required />
          </Field>
          <Field label="Source">
            <Select value={f.source} onChange={(e) => set("source")(e.target.value)} options={LEAD_SOURCES.map((s) => ({ value: s, label: titleCase(s) }))} />
          </Field>
          <Field label="Email">
            <Input type="email" value={f.email} onChange={(e) => set("email")(e.target.value)} placeholder="name@example.com" />
          </Field>
          <Field label="Phone">
            <Input value={f.phone} onChange={(e) => set("phone")(e.target.value)} placeholder="+92-300-0000000" />
          </Field>
          <Field label="Use type">
            <Select value={f.interest_use_type} onChange={(e) => set("interest_use_type")(e.target.value)} options={["residential", "commercial", "mix"].map((s) => ({ value: s, label: titleCase(s) }))} />
          </Field>
          <Field label="Category">
            <Select
              value={f.interest_category}
              onChange={(e) => set("interest_category")(e.target.value)}
              options={["house", "apartment", "plot", "shop", "office", "floor", "building", "farmhouse"].map((s) => ({ value: s, label: titleCase(s) }))}
            />
          </Field>
          <Field label="Budget min (PKR)" hint={f.budget_min ? pkrShort(Number(f.budget_min)) : undefined}>
            <Input type="number" min={0} value={f.budget_min} onChange={(e) => set("budget_min")(e.target.value)} placeholder="30000000" />
          </Field>
          <Field label="Budget max (PKR)" hint={f.budget_max ? pkrShort(Number(f.budget_max)) : undefined}>
            <Input type="number" min={0} value={f.budget_max} onChange={(e) => set("budget_max")(e.target.value)} placeholder="60000000" />
          </Field>
          <Field label="City">
            <Select value={f.city_id} onChange={(e) => set("city_id")(e.target.value)}>
              <option value="">Any</option>
              {(cities.data?.cities ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Assign to">
            <Select value={f.assigned_agent_id} onChange={(e) => set("assigned_agent_id")(e.target.value)}>
              <option value="">Auto / unassigned</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Notes" className="sm:col-span-2">
            <Textarea value={f.notes} onChange={(e) => set("notes")(e.target.value)} placeholder="Requirements, timeline, preferences…" />
          </Field>
        </FormGrid>
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}

function NewTaskModal({ open, onClose, agents }: { open: boolean; onClose: () => void; agents: Agent[] }) {
  const [f, set, reset] = useFormState({ title: "", description: "", assigned_agent_id: "", priority: "medium", due_date: isoDay(2), related_type: "", related_id: "" });
  const leads = useApi<LeadsRes>(open && f.related_type === "lead" ? "/crm/leads" : null);
  const deals = useApi<DealsRes>(open && f.related_type === "deal" ? "/crm/deals" : null);
  const customers = useApi<{ customers: Customer[] }>(open && f.related_type === "customer" ? "/crm/customers" : null);
  const related: { id: string; label: string }[] =
    f.related_type === "lead"
      ? (leads.data?.leads ?? []).map((l) => ({ id: l.id, label: l.name }))
      : f.related_type === "deal"
        ? (deals.data?.deals ?? []).map((d) => ({ id: d.id, label: d.title }))
        : f.related_type === "customer"
          ? (customers.data?.customers ?? []).map((c) => ({ id: c.id, label: c.name }))
          : [];

  const create = useMutate(
    () =>
      post("/crm/tasks", {
        title: f.title.trim(),
        description: f.description || undefined,
        assigned_agent_id: f.assigned_agent_id || undefined,
        priority: f.priority,
        due_date: f.due_date || undefined,
        related_type: f.related_type || undefined,
        related_id: f.related_type ? f.related_id || undefined : undefined,
      }).then(ensure),
    {
      invalidate: ["/crm"],
      success: "Task created",
      onSuccess: () => {
        reset();
        onClose();
      },
    },
  );
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New task"
      subtitle="Schedule a follow-up for your team"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} disabled={!f.title.trim()} onClick={() => create.mutate()}>
            Create task
          </Button>
        </>
      }
    >
      <FormGrid>
        <Field label="Title *" className="sm:col-span-2">
          <Input value={f.title} onChange={(e) => set("title")(e.target.value)} placeholder="e.g. Send payment plan to Hassan" autoFocus />
        </Field>
        <Field label="Priority">
          <Select value={f.priority} onChange={(e) => set("priority")(e.target.value)} options={TASK_PRIORITIES.map((p) => ({ value: p, label: titleCase(p) }))} />
        </Field>
        <Field label="Due date">
          <Input type="date" value={f.due_date} onChange={(e) => set("due_date")(e.target.value)} />
        </Field>
        <Field label="Assignee">
          <Select value={f.assigned_agent_id} onChange={(e) => set("assigned_agent_id")(e.target.value)}>
            <option value="">Unassigned</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Related to">
          <Select
            value={f.related_type}
            onChange={(e) => {
              set("related_type")(e.target.value);
              set("related_id")("");
            }}
            options={[
              { value: "", label: "Nothing" },
              { value: "lead", label: "Lead" },
              { value: "deal", label: "Deal" },
              { value: "customer", label: "Customer" },
            ]}
          />
        </Field>
        {f.related_type && (
          <Field label={`Which ${f.related_type}?`} className="sm:col-span-2">
            <Select value={f.related_id} onChange={(e) => set("related_id")(e.target.value)}>
              <option value="">Select…</option>
              {related.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Description" className="sm:col-span-2">
          <Textarea value={f.description} onChange={(e) => set("description")(e.target.value)} placeholder="Optional details" />
        </Field>
      </FormGrid>
    </Modal>
  );
}

