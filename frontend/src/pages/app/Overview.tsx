import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlarmClock,
  ArrowUpRight,
  AtSign,
  Bell,
  Bot,
  BriefcaseBusiness,
  Building2,
  Calculator,
  CalendarClock,
  CircleDollarSign,
  Gauge,
  HardHat,
  KeyRound,
  LineChart,
  ListChecks,
  Megaphone,
  MessagesSquare,
  PiggyBank,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Wallet,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/store/auth";
import { compact, num, pct, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Bars, ButtonLink, Donut, EmptyState, Legendish, PageHeader, Progress, QueryState, Skeleton, StatCard, StatusBadge } from "@/components/ui";
import { MiniStat, Panel, SkeletonGrid, bandTone, crShort, stagger, rs } from "@/components/biz/ops-kit";
import type { SmartAction } from "@/types";

// ------------------------------------------------------------------ types
interface PortalStats {
  inventory: { properties: number; cities: number; schemes: number };
  portfolio: {
    total_market_value: number;
    avg_price: number;
    by_category: Record<string, number>;
    by_city: { city: string; properties: number; value: number }[];
  };
  finance: { revenue: number; net_profit: number; overdue_invoices: number; cash_and_bank: number };
  crm: { agents: number; leads: number; customers: number; deals: number; weighted_pipeline_value: number };
  transactions?: { open: number; gross_value_open: number };
  maintenance?: { open_work_orders: number };
}
interface PnlLine {
  code: string;
  name: string;
  amount: number;
}
interface Pnl {
  income: PnlLine[];
  expenses: PnlLine[];
  total_income: number;
  total_expenses: number;
  net_profit: number;
  net_margin: number;
}
interface PmoPortfolio {
  projects: number;
  by_health: Record<string, number>;
  financials: { total_budget: number; total_actual: number; total_committed: number };
  portfolio_spi: number;
  portfolio_cpi: number;
  open_risks: number;
  alerts: number;
  rows: { id: string; code: string; name: string; city: string; progress_pct: number; health: string; budget: number; actual_cost: number }[];
}
interface Deadline {
  transaction_id: string;
  code: string;
  milestone: string;
  name: string;
  due_date: string;
  days_left: number;
  owner: string;
  blocking: boolean;
  overdue: boolean;
}
interface Unread {
  conversations_unread: number;
  mentions: number;
  notifications_unread: number;
  open_actions: number;
  overdue_actions: number;
}

const MODULES: { to: string; label: string; hint: string; icon: LucideIcon; tone: string }[] = [
  { to: "/app/crm", label: "CRM", hint: "Leads, deals & pipeline", icon: Users, tone: "from-brand-500 to-brand-700" },
  { to: "/app/accounting", label: "Accounting", hint: "Ledger, invoices, P&L", icon: Calculator, tone: "from-gold-400 to-gold-600" },
  { to: "/app/pmo", label: "PMO", hint: "Projects & delivery", icon: BriefcaseBusiness, tone: "from-sky-500 to-sky-700" },
  { to: "/app/messages", label: "Messages", hint: "Team inbox & alerts", icon: MessagesSquare, tone: "from-violet-500 to-violet-700" },
  { to: "/app/ads", label: "Ads", hint: "Campaigns & slots", icon: Megaphone, tone: "from-orange-400 to-orange-600" },
  { to: "/app/leasing", label: "Leasing", hint: "Units, tenants, renewals", icon: KeyRound, tone: "from-teal-500 to-teal-700" },
  { to: "/app/maintenance", label: "Maintenance", hint: "Work orders & reserves", icon: Wrench, tone: "from-rose-500 to-rose-700" },
  { to: "/app/construction", label: "Construction", hint: "Estimates & materials", icon: HardHat, tone: "from-amber-500 to-amber-700" },
  { to: "/app/marketing", label: "Marketing", hint: "Funnel, content, routing", icon: Target, tone: "from-fuchsia-500 to-fuchsia-700" },
  { to: "/ai", label: "AI Hub", hint: "Agents & assistant", icon: Sparkles, tone: "from-brand-600 to-gold-500" },
];

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export default function Overview() {
  const user = useAuth((s) => s.user);
  const stats = useApi<PortalStats>("/portal/statistics");
  const pnl = useApi<Pnl>("/accounting/profit-and-loss");
  const actions = useApi<{ count: number; by_band: Record<string, number>; actions: SmartAction[] }>("/agents/smart-actions", { user_id: user?.id, limit: 6 });
  const pmo = useApi<PmoPortfolio>("/pmo/portfolio");
  const deadlines = useApi<{ count: number; overdue: number; deadlines: Deadline[] }>("/transactions/deadlines");
  const unread = useApi<Unread>(user ? `/messaging/unread-summary/${encodeURIComponent(user.id)}` : null);

  const firstName = (user?.name ?? "there").split(/\s+/)[0];
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle="Your portfolio, pipeline and operations at a glance"
        actions={
          <>
            <ButtonLink to="/app/listings/new" variant="outline" size="sm">
              List a property
            </ButtonLink>
            <ButtonLink to="/app/agents" variant="gold" size="sm" icon={<Bot className="h-4 w-4" />}>
              Agentic OS
            </ButtonLink>
          </>
        }
      />

      {/* -------------------------------------------------- greeting banner */}
      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative isolate overflow-hidden rounded-3xl bg-brand-gradient p-6 text-white shadow-soft sm:p-8"
      >
        <div className="pointer-events-none absolute inset-0 -z-10 bg-mesh opacity-70" />
        <div className="pointer-events-none absolute -end-16 -top-20 -z-10 h-64 w-64 rounded-full bg-gold-400/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 start-1/3 -z-10 h-56 w-56 rounded-full bg-brand-400/20 blur-3xl" />
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[.2em] text-gold-200">{today}</p>
            <h2 className="mt-2 font-display text-2xl font-bold sm:text-3xl">
              {greeting()}, <span className="text-gradient">{firstName}</span>
            </h2>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-white/80">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold ring-1 ring-inset ring-white/15">
                {titleCase(user?.role ?? "member")}
              </span>
              {user?.email && <span className="truncate text-xs text-white/60">{user.email}</span>}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:gap-3">
            <BannerPill icon={Zap} label="Smart actions" value={actions.data?.count} loading={actions.isLoading} />
            <BannerPill icon={AlarmClock} label="Overdue" value={deadlines.data?.overdue} loading={deadlines.isLoading} warn />
            <BannerPill icon={Bell} label="Unread" value={unread.data ? unread.data.conversations_unread + unread.data.notifications_unread : undefined} loading={unread.isLoading} />
          </div>
        </div>
      </motion.section>

      {/* -------------------------------------------------- KPIs */}
      <QueryState q={stats} skeleton={<SkeletonGrid n={6} className="lg:grid-cols-3" />}>
        {(s) => (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard label="Market value" value={rs(s.portfolio.total_market_value)} icon={<Building2 className="h-5 w-5" />} hint={`avg ${pkrShort(s.portfolio.avg_price)}`} />
            <StatCard label="Listings" value={num(s.inventory.properties)} icon={<LineChart className="h-5 w-5" />} hint={`${s.inventory.cities} cities · ${s.inventory.schemes} schemes`} tone="blue" />
            <StatCard label="Revenue" value={rs(s.finance.revenue)} icon={<CircleDollarSign className="h-5 w-5" />} hint="year to date" tone="gold" />
            <StatCard
              label="Net profit"
              value={rs(s.finance.net_profit)}
              icon={<PiggyBank className="h-5 w-5" />}
              delta={s.finance.revenue ? (s.finance.net_profit / s.finance.revenue) * 100 : undefined}
              hint="margin"
              tone={s.finance.net_profit >= 0 ? "green" : "red"}
            />
            <StatCard label="Weighted pipeline" value={rs(s.crm.weighted_pipeline_value)} icon={<TrendingUp className="h-5 w-5" />} hint={`${s.crm.deals} open deals`} tone="purple" />
            <StatCard label="Leads" value={num(s.crm.leads)} icon={<Users className="h-5 w-5" />} hint={`${s.crm.customers} customers · ${s.crm.agents} agents`} tone="green" />
          </div>
        )}
      </QueryState>

      {/* -------------------------------------------------- portfolio charts */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Portfolio value by city" subtitle="Listed market value" icon={<Building2 className="h-4 w-4" />} className="lg:col-span-2">
          <QueryState q={stats} skeleton={<Skeleton className="h-[260px]" />}>
            {(s) =>
              s.portfolio.by_city.length ? (
                <Bars data={s.portfolio.by_city} x="city" series={[{ key: "value", label: "Value" }]} format={crShort} colorByIndex />
              ) : (
                <EmptyState title="No listings yet" />
              )
            }
          </QueryState>
        </Panel>
        <Panel title="Mix by category" subtitle="Active listings" icon={<Gauge className="h-4 w-4" />}>
          <QueryState q={stats} skeleton={<Skeleton className="h-[260px]" />}>
            {(s) => {
              const data = Object.entries(s.portfolio.by_category)
                .map(([name, value]) => ({ name: titleCase(name), value }))
                .sort((a, b) => b.value - a.value);
              return (
                <div className="space-y-4">
                  <Donut
                    data={data}
                    height={200}
                    format={(v) => `${v} listings`}
                    center={
                      <>
                        <span className="font-display text-2xl font-bold">{s.inventory.properties}</span>
                        <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-mute">listings</span>
                      </>
                    }
                  />
                  <Legendish data={data} />
                </div>
              );
            }}
          </QueryState>
        </Panel>
      </div>

      {/* -------------------------------------------------- P&L + smart actions */}
      <div className="grid gap-6 lg:grid-cols-5">
        <Panel
          title="Income vs expenses"
          subtitle="Profit & loss by account"
          icon={<Wallet className="h-4 w-4" />}
          className="lg:col-span-3"
          action={
            <Link to="/app/accounting" className="link inline-flex items-center gap-1 text-xs">
              Accounting <ArrowUpRight className="h-3.5 w-3.5 rtl:-scale-x-100" />
            </Link>
          }
        >
          <QueryState q={pnl} skeleton={<Skeleton className="h-[300px]" />}>
            {(p) => {
              const rows = [
                ...p.income.map((l) => ({ name: l.name.replace(/ Income$/, ""), income: l.amount, expenses: 0 })),
                ...p.expenses.map((l) => ({ name: l.name.replace(/ Expense$/, ""), income: 0, expenses: l.amount })),
              ];
              return (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-2">
                    <MiniStat label="Income" value={pkrShort(p.total_income, false)} tone="green" />
                    <MiniStat label="Expenses" value={pkrShort(p.total_expenses, false)} tone="gold" />
                    <MiniStat label="Net margin" value={pct(p.net_margin)} tone={p.net_profit >= 0 ? "green" : "red"} hint={pkrShort(p.net_profit)} />
                  </div>
                  <Bars
                    data={rows}
                    x="name"
                    horizontal
                    stacked
                    height={Math.max(240, rows.length * 26)}
                    series={[
                      { key: "income", label: "Income", color: "#146f45" },
                      { key: "expenses", label: "Expenses", color: "#c99a22" },
                    ]}
                    format={crShort}
                  />
                </div>
              );
            }}
          </QueryState>
        </Panel>

        <Panel
          title="Smart actions"
          subtitle="Prioritised by the agentic OS"
          icon={<Zap className="h-4 w-4" />}
          className="lg:col-span-2"
          flush
          action={
            <Link to="/app/agents" className="link inline-flex items-center gap-1 text-xs">
              Open <ArrowUpRight className="h-3.5 w-3.5 rtl:-scale-x-100" />
            </Link>
          }
        >
          <QueryState q={actions} skeleton={<div className="space-y-3 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>}>
            {(a) =>
              a.actions.length ? (
                <motion.ul variants={stagger.container} initial="hidden" animate="show" className="divide-y divide-black/5 dark:divide-white/5">
                  {a.actions.slice(0, 6).map((x, i) => (
                    <motion.li key={`${x.entity_id}-${i}`} variants={stagger.item}>
                      <Link to="/app/agents" className="flex items-start gap-3 px-5 py-3 transition-colors hover:bg-brand-50/60 dark:hover:bg-white/5">
                        <span
                          className={cn(
                            "mt-1 h-2 w-2 shrink-0 rounded-full",
                            x.band === "urgent" ? "bg-red-500 shadow-[0_0_0_4px_rgba(239,68,68,.15)]" : x.band === "high" ? "bg-orange-500" : "bg-sky-500",
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="line-clamp-2 text-sm font-semibold text-ink dark:text-white">{x.title}</p>
                          <p className="mt-0.5 truncate text-xs text-ink-mute dark:text-slate-400">
                            {x.reason} · {titleCase(x.suggested_agent)}
                          </p>
                        </div>
                        <Badge tone={bandTone(x.band)} className="shrink-0 capitalize">
                          {x.band}
                        </Badge>
                      </Link>
                    </motion.li>
                  ))}
                </motion.ul>
              ) : (
                <div className="p-5">
                  <EmptyState title="All clear" hint="No actions need your attention right now." icon={<Sparkles className="h-6 w-6" />} />
                </div>
              )
            }
          </QueryState>
        </Panel>
      </div>

      {/* -------------------------------------------------- PMO / deadlines / inbox */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel
          title="Project portfolio"
          subtitle="PMO health & earned value"
          icon={<BriefcaseBusiness className="h-4 w-4" />}
          action={
            <Link to="/app/pmo" className="link inline-flex items-center gap-1 text-xs">
              PMO <ArrowUpRight className="h-3.5 w-3.5 rtl:-scale-x-100" />
            </Link>
          }
        >
          <QueryState q={pmo} skeleton={<Skeleton className="h-56" />}>
            {(p) => {
              const spent = p.financials.total_budget ? (p.financials.total_actual / p.financials.total_budget) * 100 : 0;
              return (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-2">
                    <MiniStat label="Projects" value={p.projects} />
                    <MiniStat label="SPI" value={p.portfolio_spi?.toFixed(2) ?? "—"} tone={p.portfolio_spi >= 1 ? "green" : "red"} />
                    <MiniStat label="CPI" value={p.portfolio_cpi?.toFixed(2) ?? "—"} tone={p.portfolio_cpi >= 1 ? "green" : "red"} />
                  </div>
                  <div>
                    <div className="mb-1.5 flex justify-between text-xs">
                      <span className="font-medium text-ink-soft dark:text-slate-300">Budget used</span>
                      <span className="font-semibold tabular-nums">
                        {pkrShort(p.financials.total_actual, false)} / {pkrShort(p.financials.total_budget, false)}
                      </span>
                    </div>
                    <Progress value={spent} tone={spent > 95 ? "red" : spent > 80 ? "gold" : "green"} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(["green", "amber", "red"] as const).map((h) => (
                      <Badge key={h} tone={h === "amber" ? "gold" : h}>
                        {p.by_health[h] ?? 0} {h}
                      </Badge>
                    ))}
                    <Badge tone="orange">{p.open_risks} open risks</Badge>
                  </div>
                  <ul className="space-y-2">
                    {p.rows.slice(0, 3).map((r) => (
                      <li key={r.id}>
                        <Link to={`/app/pmo/${r.id}`} className="block rounded-xl border border-black/5 p-3 transition-colors hover:border-brand-300 dark:border-white/10">
                          <div className="flex items-center justify-between gap-2">
                            <p className="truncate text-sm font-semibold">{r.name}</p>
                            <StatusBadge status={r.health} />
                          </div>
                          <div className="mt-2 flex items-center gap-2">
                            <Progress value={r.progress_pct} className="h-1.5" />
                            <span className="text-xs font-semibold tabular-nums">{Math.round(r.progress_pct)}%</span>
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            }}
          </QueryState>
        </Panel>

        <Panel
          title="Upcoming deadlines"
          subtitle="Transaction milestones · next 14 days"
          icon={<CalendarClock className="h-4 w-4" />}
          flush
          action={
            <Link to="/app/transactions" className="link inline-flex items-center gap-1 text-xs">
              All <ArrowUpRight className="h-3.5 w-3.5 rtl:-scale-x-100" />
            </Link>
          }
        >
          <QueryState q={deadlines} skeleton={<div className="space-y-3 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>}>
            {(d) =>
              d.deadlines.length ? (
                <ul className="divide-y divide-black/5 dark:divide-white/5">
                  {d.deadlines.slice(0, 7).map((x) => (
                    <li key={`${x.transaction_id}-${x.milestone}`} className="flex items-center gap-3 px-5 py-2.5">
                      <span
                        className={cn(
                          "flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-xl text-[10px] font-bold leading-tight",
                          x.overdue ? "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300" : x.days_left <= 2 ? "bg-gold-50 text-gold-700 dark:bg-gold-500/15 dark:text-gold-200" : "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200",
                        )}
                      >
                        <span className="font-display text-sm">{Math.abs(x.days_left)}</span>
                        <span>{x.overdue ? "late" : "days"}</span>
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">{x.name}</p>
                        <p className="truncate text-xs text-ink-mute dark:text-slate-400">
                          {x.code} · {titleCase(x.owner)}
                          {x.blocking && " · blocking"}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="p-5">
                  <EmptyState title="Nothing due" hint="No milestones in the next two weeks." />
                </div>
              )
            }
          </QueryState>
        </Panel>

        <Panel
          title="Inbox"
          subtitle="Messages & notifications"
          icon={<MessagesSquare className="h-4 w-4" />}
          action={
            <Link to="/app/messages" className="link inline-flex items-center gap-1 text-xs">
              Open <ArrowUpRight className="h-3.5 w-3.5 rtl:-scale-x-100" />
            </Link>
          }
        >
          <QueryState q={unread} skeleton={<Skeleton className="h-48" />}>
            {(u) => (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <InboxTile icon={MessagesSquare} label="Unread chats" value={u.conversations_unread} />
                  <InboxTile icon={AtSign} label="Mentions" value={u.mentions} />
                  <InboxTile icon={Bell} label="Notifications" value={u.notifications_unread} />
                  <InboxTile icon={ListChecks} label="Open actions" value={u.open_actions} warn={u.overdue_actions > 0} hint={u.overdue_actions ? `${u.overdue_actions} overdue` : undefined} />
                </div>
                <ButtonLink to="/app/messages" variant="soft" size="sm" className="w-full justify-center">
                  Go to messages
                </ButtonLink>
              </div>
            )}
          </QueryState>
          {!user && <EmptyState title="Sign in to see your inbox" />}
        </Panel>
      </div>

      {/* -------------------------------------------------- quick launch */}
      <section>
        <div className="mb-3 flex items-end justify-between">
          <div>
            <p className="section-eyebrow">Quick launch</p>
            <h3 className="mt-1 font-display text-lg font-semibold">Jump into a module</h3>
          </div>
        </div>
        <motion.div variants={stagger.container} initial="hidden" animate="show" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {MODULES.map((m) => (
            <motion.div key={m.to} variants={stagger.item}>
              <Link to={m.to} className="card card-hover group flex h-full flex-col gap-3 p-4">
                <span className={cn("flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-soft", m.tone)}>
                  <m.icon className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="flex items-center gap-1 font-display font-semibold text-ink dark:text-white">
                    {m.label}
                    <ArrowUpRight className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100 rtl:-scale-x-100" />
                  </p>
                  <p className="truncate text-xs text-ink-mute dark:text-slate-400">{m.hint}</p>
                </div>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      </section>
    </div>
  );
}

function BannerPill({ icon: Icon, label, value, loading, warn }: { icon: LucideIcon; label: string; value?: number; loading?: boolean; warn?: boolean }) {
  return (
    <div className="glass-dark min-w-[92px] rounded-2xl px-3 py-2.5 sm:px-4">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-white/70">
        <Icon className={cn("h-3.5 w-3.5", warn && value ? "text-gold-300" : "")} />
        <span className="truncate">{label}</span>
      </div>
      <p className={cn("mt-1 font-display text-2xl font-bold tabular-nums", warn && value ? "text-gold-200" : "text-white")}>{loading ? "…" : value ?? "—"}</p>
    </div>
  );
}

function InboxTile({ icon: Icon, label, value, warn, hint }: { icon: LucideIcon; label: string; value: number; warn?: boolean; hint?: string }) {
  return (
    <div className={cn("rounded-xl border p-3", warn ? "border-red-200 bg-red-50/60 dark:border-red-500/20 dark:bg-red-500/5" : "border-black/5 bg-brand-50/40 dark:border-white/10 dark:bg-white/5")}>
      <Icon className={cn("h-4 w-4", warn ? "text-red-600" : "text-brand-600 dark:text-brand-300")} />
      <p className="mt-2 font-display text-xl font-bold tabular-nums">{value}</p>
      <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-ink-mute dark:text-slate-400">{label}</p>
      {hint && <p className="text-[11px] font-semibold text-red-600">{hint}</p>}
    </div>
  );
}
