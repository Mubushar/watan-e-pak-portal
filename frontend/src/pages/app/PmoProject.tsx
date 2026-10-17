import { useMemo, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  BarChart3,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  Coins,
  FileText,
  Flag,
  GanttChartSquare,
  Gauge,
  GitPullRequest,
  HardHat,
  LayoutDashboard,
  ListChecks,
  MapPin,
  NotebookPen,
  Plus,
  ShieldAlert,
  Sun,
  Users,
  XCircle,
} from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { apiUrl, post, put } from "@/lib/api";
import { date, num, pct, pkr, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import {
  AreaTrend,
  Badge,
  Bars,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  Input,
  KeyValue,
  Modal,
  PageHeader,
  Progress,
  QueryState,
  Select,
  Skeleton,
  Slider,
  StatCard,
  StatusBadge,
  Tabs,
  Textarea,
  type Column,
} from "@/components/ui";
import { apiErr, ok, RAG_HEX, RagPill, Ring, today } from "@/components/collab/kit";
import { Gantt, type GanttRow } from "@/components/collab/Gantt";

// ---------------------------------------------------------------- types
interface Project {
  id: string;
  code: string;
  name: string;
  project_type: string;
  description?: string | null;
  city?: string | null;
  scheme?: string | null;
  client?: string | null;
  status: string;
  priority: string;
  start_date?: string | null;
  end_date?: string | null;
  budget: number;
  contract_value: number;
}
interface Health {
  overall: string;
  bands: Record<string, string>;
  schedule_slip_days: number;
  spi: number;
  cpi: number;
  progress_pct: number;
  planned_pct: number;
  cost_overrun_pct: number;
  max_open_risk_score: number;
  quality_index: number;
  verdict: string;
}
interface Evm {
  as_of: string;
  PV: number;
  EV: number;
  AC: number;
  SV: number;
  CV: number;
  SPI: number;
  CPI: number;
  EAC: number;
  ETC: number;
  VAC: number;
  TCPI: number;
  planned_pct: number;
  actual_pct: number;
  performance?: { schedule: string; cost: string };
  eac_method?: string;
}
interface CostStatus {
  baseline_budget: number;
  approved_changes: number;
  revised_budget: number;
  contract_value: number;
  actual_cost: number;
  committed_cost: number;
  exposure: number;
  forecast_to_complete: number;
  forecast_final: number;
  variance_at_completion: number;
  spent_pct: number;
  by_category: Record<string, { actual: number; committed: number }>;
}
interface Kpi {
  schedule_performance_index: number;
  cost_performance_index: number;
  progress_pct: number;
  planned_pct: number;
  spent_pct: number;
  budget_variance: number;
  milestones_total: number;
  milestones_met: number;
  milestones_at_risk: number;
  open_risks: number;
  high_risks: number;
  open_changes: number;
  open_actions: number;
  critical_tasks: number;
  health: string;
}
interface Milestone {
  id: string;
  name: string;
  phase_key?: string | null;
  planned_date?: string | null;
  forecast_date?: string | null;
  actual_date?: string | null;
  status: string;
  billable_amount: number;
  slip_days: number;
}
interface Dashboard {
  project: Project;
  health: Health;
  kpi: Kpi;
  progress: { actual_pct: number; planned_pct: number; variance_pct: number; tasks: number; by_status: Record<string, number>; schedule_finish?: string };
  cost: CostStatus;
  evm: Evm;
  milestones: Milestone[];
  alerts: { level: string; kind: string; message: string }[];
  resources: { resource_id: string; name: string; role: string; utilisation_pct: number; over_allocated: boolean }[];
}
interface Task {
  id: string;
  wbs?: string | null;
  name: string;
  phase_key?: string | null;
  duration_days: number;
  progress_pct: number;
  status: string;
  priority: string;
  cost_budget: number;
  planned_start?: string;
  planned_finish?: string;
  float_days?: number;
  is_critical?: boolean;
  assignee_id?: string | null;
}
interface Risk {
  id: string;
  kind: string;
  title: string;
  category?: string | null;
  probability: number;
  impact: number;
  owner?: string | null;
  mitigation?: string | null;
  status: string;
  due_on?: string | null;
  score: number;
  band: string;
}
interface PmoMeta {
  cost_categories: string[];
  risk_categories: string[];
  raid_kinds: string[];
  quality_areas: string[];
}

const TASK_STATUSES = ["not_started", "in_progress", "blocked", "done"];
const BAND_TONE: Record<string, "green" | "gold" | "orange" | "red"> = { low: "green", medium: "gold", high: "orange", extreme: "red" };
const BAND_BG: Record<string, string> = {
  low: "bg-emerald-100 dark:bg-emerald-500/20",
  medium: "bg-amber-100 dark:bg-amber-500/20",
  high: "bg-orange-200 dark:bg-orange-500/30",
  extreme: "bg-red-200 dark:bg-red-500/35",
};
const bandOf = (score: number) => (score >= 16 ? "extreme" : score >= 10 ? "high" : score >= 5 ? "medium" : "low");

type Tab = "overview" | "schedule" | "tasks" | "risks" | "costs" | "milestones" | "diary" | "inspections" | "changes" | "kpi";

// ---------------------------------------------------------------- page
export default function PmoProject() {
  const { id = "" } = useParams();
  const base = `/pmo/projects/${id}`;
  const dash = useApi<Dashboard>(id ? `${base}/dashboard` : null);
  const [tab, setTab] = useState<Tab>("overview");
  const d = dash.data;
  const err = apiErr(d);

  if (dash.isLoading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
        <Skeleton className="h-80" />
      </div>
    );
  if (dash.error || err || !d) return <ErrorState error={dash.error ?? err ?? "Project not found"} onRetry={() => dash.refetch()} />;

  const p = d.project;
  const h = d.health;
  const tabs: { value: Tab; label: string; icon: ReactNode; count?: number }[] = [
    { value: "overview", label: "Overview", icon: <LayoutDashboard className="h-4 w-4" /> },
    { value: "schedule", label: "Schedule", icon: <GanttChartSquare className="h-4 w-4" /> },
    { value: "tasks", label: "Tasks", icon: <ListChecks className="h-4 w-4" />, count: d.progress?.tasks },
    { value: "risks", label: "Risks", icon: <ShieldAlert className="h-4 w-4" />, count: d.kpi?.open_risks },
    { value: "costs", label: "Costs", icon: <Coins className="h-4 w-4" /> },
    { value: "milestones", label: "Milestones", icon: <Flag className="h-4 w-4" />, count: d.milestones?.length },
    { value: "diary", label: "Site diary", icon: <NotebookPen className="h-4 w-4" /> },
    { value: "inspections", label: "Inspections", icon: <ClipboardCheck className="h-4 w-4" /> },
    { value: "changes", label: "Change requests", icon: <GitPullRequest className="h-4 w-4" />, count: d.kpi?.open_changes },
    { value: "kpi", label: "KPI scorecard", icon: <Gauge className="h-4 w-4" /> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={p.name}
        crumbs={[{ label: "Dashboard", to: "/app" }, { label: "Projects", to: "/app/pmo" }, { label: p.code }]}
        actions={
          <a href={apiUrl("/pmo/report.html", { project_id: p.id })} target="_blank" rel="noreferrer" className="btn btn-outline">
            <FileText className="h-4 w-4" /> Status report
          </a>
        }
      >
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-mute">
          <span className="font-mono text-xs font-semibold">{p.code}</span>
          <RagPill rag={h.overall} label={`${h.overall} health`} />
          <StatusBadge status={p.status} />
          <Badge tone="gray">{titleCase(p.project_type)}</Badge>
          {p.city && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" /> {[p.scheme, p.city].filter(Boolean).join(", ")}
            </span>
          )}
          {p.client && <span>· Client: {p.client}</span>}
        </div>
      </PageHeader>

      {/* hero strip */}
      <div className="relative overflow-hidden rounded-3xl bg-brand-gradient p-5 text-white shadow-soft sm:p-6">
        <div className="pointer-events-none absolute -end-16 -top-20 h-64 w-64 rounded-full bg-gold-400/25 blur-3xl" />
        <div className="relative grid items-center gap-6 md:grid-cols-[auto_1fr]">
          <Ring value={d.progress?.actual_pct ?? h.progress_pct} size={116} stroke={10} color="#e8c35a">
            <span className="font-display text-2xl font-bold text-white">{Math.round(d.progress?.actual_pct ?? h.progress_pct)}%</span>
            <span className="text-[10px] uppercase tracking-wider text-white/70">complete</span>
          </Ring>
          <div>
            <p className="text-xs font-bold uppercase tracking-[.2em] text-gold-300">Verdict</p>
            <p className="mt-1 font-display text-xl font-semibold">{h.verdict}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Object.entries(h.bands ?? {}).map(([k, v]) => (
                <div key={k} className="rounded-2xl bg-white/10 px-3 py-2 backdrop-blur">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-white/60">{k}</p>
                  <p className="mt-0.5 flex items-center gap-1.5 font-semibold capitalize">
                    <span className="h-2.5 w-2.5 rounded-full ring-2 ring-white/30" style={{ background: RAG_HEX[v] }} />
                    {v}
                  </p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-white/70">
              {date(p.start_date)} → {date(p.end_date)} · planned {pct(h.planned_pct, 1, false)} · slip {h.schedule_slip_days} day(s)
            </p>
          </div>
        </div>
      </div>

      <Tabs tabs={tabs} value={tab} onChange={setTab} />

      <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        {tab === "overview" && <Overview d={d} base={base} />}
        {tab === "schedule" && <Schedule base={base} />}
        {tab === "tasks" && <Tasks base={base} />}
        {tab === "risks" && <Risks base={base} />}
        {tab === "costs" && <Costs base={base} />}
        {tab === "milestones" && <Milestones base={base} />}
        {tab === "diary" && <Diary base={base} />}
        {tab === "inspections" && <Inspections base={base} />}
        {tab === "changes" && <Changes base={base} />}
        {tab === "kpi" && <KpiTab base={base} />}
      </motion.div>
    </div>
  );
}

// ---------------------------------------------------------------- overview
function Overview({ d, base }: { d: Dashboard; base: string }) {
  const curve = useApi<{ weeks: { week: string; planned_pct: number; actual_pct: number }[] }>(`${base}/s-curve`);
  const evm = useApi<Evm>(`${base}/earned-value`);
  const e = evm.data ?? d.evm;
  const k = d.kpi;
  const pctFmt = (v: number) => `${Math.round(v)}%`;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Progress" value={pct(d.progress.actual_pct, 1, false)} icon={<BarChart3 className="h-5 w-5" />} delta={d.progress.variance_pct} hint={`vs ${pct(d.progress.planned_pct, 1, false)} planned`} />
        <StatCard label="Spent" value={pkrShort(d.cost.actual_cost)} tone="gold" icon={<Coins className="h-5 w-5" />} hint={`${pct(d.cost.spent_pct, 1, false)} of ${pkrShort(d.cost.revised_budget)}`} />
        <StatCard label="SPI · CPI" value={`${num(e.SPI, 2)} · ${num(e.CPI, 2)}`} tone={e.SPI >= 0.95 && e.CPI >= 0.95 ? "green" : "red"} icon={<Gauge className="h-5 w-5" />} hint={e.performance ? `${titleCase(e.performance.schedule)} · ${titleCase(e.performance.cost)}` : undefined} />
        <StatCard label="Forecast final" value={pkrShort(d.cost.forecast_final)} tone={d.cost.variance_at_completion < 0 ? "red" : "green"} icon={<CalendarClock className="h-5 w-5" />} hint={`VAC ${pkrShort(d.cost.variance_at_completion)}`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader title="S-curve" subtitle="Planned vs actual cumulative progress" icon={<BarChart3 className="h-5 w-5" />} />
          <CardBody>
            <QueryState q={curve} skeleton={<Skeleton className="h-72" />}>
              {(c) =>
                c.weeks?.length ? (
                  <AreaTrend
                    data={c.weeks.map((w) => ({ ...w, label: date(w.week, { day: "numeric", month: "short" }) }))}
                    x="label"
                    height={290}
                    format={pctFmt}
                    series={[
                      { key: "planned_pct", label: "Planned", color: "#2c7fb8" },
                      { key: "actual_pct", label: "Actual", color: "#146f45" },
                    ]}
                  />
                ) : (
                  <EmptyState title="No S-curve yet" />
                )
              }
            </QueryState>
          </CardBody>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title="Earned value" subtitle={`As of ${date(e.as_of)} · EAC by ${e.eac_method ?? "CPI"}`} icon={<Gauge className="h-5 w-5" />} />
          <CardBody>
            <KeyValue
              items={[
                { label: "Planned value (PV)", value: pkrShort(e.PV) },
                { label: "Earned value (EV)", value: pkrShort(e.EV) },
                { label: "Actual cost (AC)", value: pkrShort(e.AC) },
                { label: "Schedule var. (SV)", value: <span className={e.SV >= 0 ? "text-emerald-600" : "text-red-600"}>{pkrShort(e.SV)}</span> },
                { label: "Cost var. (CV)", value: <span className={e.CV >= 0 ? "text-emerald-600" : "text-red-600"}>{pkrShort(e.CV)}</span> },
                { label: "SPI", value: <span className={e.SPI >= 1 ? "text-emerald-600" : "text-red-600"}>{num(e.SPI, 3)}</span> },
                { label: "CPI", value: <span className={e.CPI >= 1 ? "text-emerald-600" : "text-red-600"}>{num(e.CPI, 3)}</span> },
                { label: "TCPI", value: num(e.TCPI, 3) },
                { label: "EAC", value: pkrShort(e.EAC) },
                { label: "ETC", value: pkrShort(e.ETC) },
              ]}
            />
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Task status" icon={<ListChecks className="h-5 w-5" />} />
          <CardBody className="space-y-3">
            {Object.entries(d.progress.by_status ?? {}).map(([s, n]) => (
              <div key={s}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="font-medium capitalize">{s.replace(/_/g, " ")}</span>
                  <span className="font-semibold">{n}</span>
                </div>
                <Progress value={n} max={d.progress.tasks || 1} tone={s === "done" ? "green" : s === "blocked" ? "red" : s === "in_progress" ? "gold" : "blue"} />
              </div>
            ))}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Alerts" icon={<ShieldAlert className="h-5 w-5" />} />
          <CardBody>
            {d.alerts?.length ? (
              <ul className="space-y-2">
                {d.alerts.map((a, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: RAG_HEX[a.level] ?? RAG_HEX.gray }} />
                    <span>{a.message}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-mute">No alerts — inside tolerance.</p>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Team load" icon={<Users className="h-5 w-5" />} />
          <CardBody className="space-y-3">
            {d.resources?.length ? (
              d.resources.map((r) => (
                <div key={r.resource_id}>
                  <div className="mb-1 flex justify-between gap-2 text-xs">
                    <span className="truncate font-medium">
                      {r.name} <span className="text-ink-mute">· {titleCase(r.role)}</span>
                    </span>
                    <span className={cn("font-semibold", r.over_allocated && "text-red-600")}>{Math.round(r.utilisation_pct)}%</span>
                  </div>
                  <Progress value={r.utilisation_pct} tone={r.over_allocated ? "red" : "green"} />
                </div>
              ))
            ) : (
              <p className="text-sm text-ink-mute">No resources allocated.</p>
            )}
          </CardBody>
        </Card>
      </div>
      <KpiCards k={k} />
    </div>
  );
}

// ---------------------------------------------------------------- schedule
function Schedule({ base }: { base: string }) {
  const g = useApi<{ start: string; finish: string; critical_count: number; rows: GanttRow[] }>(`${base}/gantt`);
  const cp = useApi<{ duration_days: number; critical_count: number; critical_path: { wbs?: string; name: string; start: string; finish: string }[] }>(`${base}/critical-path`);
  const critical = useMemo(() => new Set((cp.data?.critical_path ?? []).map((c) => c.name)), [cp.data]);
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Gantt schedule"
        subtitle={g.data ? `${date(g.data.start)} → ${date(g.data.finish)}${cp.data ? ` · ${cp.data.duration_days} working days` : ""}` : undefined}
        icon={<GanttChartSquare className="h-5 w-5" />}
        action={cp.data && <Badge tone={cp.data.critical_count ? "gold" : "green"}>{cp.data.critical_count} critical task(s)</Badge>}
      />
      <CardBody>
        <QueryState q={g} skeleton={<Skeleton className="h-96" />}>
          {(data) => (data.rows?.length ? <Gantt rows={data.rows} start={data.start} finish={data.finish} critical={critical} /> : <EmptyState title="No tasks scheduled" />)}
        </QueryState>
        {cp.data && cp.data.critical_count === 0 && (
          <p className="mt-3 text-xs text-ink-mute">No zero-float chain right now — every open task has schedule float before the contractual finish date.</p>
        )}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------- tasks
function Tasks({ base }: { base: string }) {
  const q = useApi<{ count: number; tasks: Task[] }>(`${base}/tasks`);
  const [edit, setEdit] = useState<Task | null>(null);
  const cols: Column<Task>[] = [
    { key: "wbs", header: "WBS", render: (t) => <span className="font-mono text-xs text-ink-mute">{t.wbs ?? "—"}</span> },
    {
      key: "name",
      header: "Task",
      render: (t) => (
        <div className="min-w-[200px]">
          <p className={cn("font-semibold", t.is_critical ? "text-gold-700 dark:text-gold-300" : "text-ink dark:text-white")}>{t.name}</p>
          <p className="text-xs text-ink-mute">{titleCase(t.phase_key ?? "")}</p>
        </div>
      ),
    },
    { key: "planned_start", header: "Dates", render: (t) => <span className="whitespace-nowrap text-xs">{date(t.planned_start, { day: "numeric", month: "short" })} → {date(t.planned_finish, { day: "numeric", month: "short" })}</span> },
    { key: "duration_days", header: "Days", align: "right" },
    {
      key: "progress_pct",
      header: "Progress",
      render: (t) => (
        <div className="flex min-w-[120px] items-center gap-2">
          <Progress value={t.progress_pct} tone={t.progress_pct >= 100 ? "green" : "gold"} />
          <span className="w-9 text-end text-xs font-semibold tabular-nums">{Math.round(t.progress_pct)}%</span>
        </div>
      ),
    },
    { key: "float_days", header: "Float", align: "right", render: (t) => <span className={cn(t.float_days === 0 && "font-bold text-gold-700")}>{t.float_days ?? "—"}</span> },
    { key: "cost_budget", header: "Budget", align: "right", render: (t) => pkrShort(t.cost_budget, false) },
    { key: "status", header: "Status", render: (t) => <StatusBadge status={t.status} /> },
  ];
  return (
    <Card className="overflow-hidden">
      <CardHeader title="Work breakdown" subtitle="Click a task to update progress or status" icon={<ListChecks className="h-5 w-5" />} />
      <QueryState q={q} skeleton={<Skeleton className="m-5 h-72" />}>
        {(d) => <DataTable rows={d.tasks} columns={cols} search pageSize={20} onRowClick={setEdit} />}
      </QueryState>
      {edit && <TaskEditor task={edit} onClose={() => setEdit(null)} />}
    </Card>
  );
}

function TaskEditor({ task, onClose }: { task: Task; onClose: () => void }) {
  const [progress, setProgress] = useState(Math.round(task.progress_pct));
  const [status, setStatus] = useState(task.status);
  const [notes, setNotes] = useState("");
  const m = useMutate(
    () => ok(put(`/pmo/tasks/${task.id}`, { updates: { progress_pct: progress, status, ...(notes ? { notes } : {}) } })),
    { invalidate: ["/pmo"], success: "Task updated", onSuccess: onClose },
  );
  return (
    <Modal
      open
      onClose={onClose}
      title={task.name}
      subtitle={`WBS ${task.wbs ?? "—"} · ${task.duration_days} days`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} onClick={() => m.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="label !mb-0">Progress</span>
            <span className="font-display text-2xl font-bold text-brand-700 dark:text-gold-300">{progress}%</span>
          </div>
          <Slider value={progress} min={0} max={100} step={5} onChange={setProgress} />
          <div className="mt-2 flex gap-1.5">
            {[0, 25, 50, 75, 100].map((v) => (
              <button key={v} onClick={() => setProgress(v)} className={cn("rounded-lg px-2.5 py-1 text-xs font-semibold", progress === v ? "bg-brand-700 text-white" : "bg-black/5 dark:bg-white/10")}>
                {v}%
              </button>
            ))}
          </div>
        </div>
        <Field label="Status">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {TASK_STATUSES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStatus(s)}
                className={cn("rounded-xl border px-3 py-2 text-xs font-semibold capitalize transition", status === s ? "border-brand-600 bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-brand-100" : "border-black/10 dark:border-white/10")}
              >
                {s.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Note (optional)">
          <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- risks
function Risks({ base }: { base: string }) {
  const matrix = useApi<{ count: number; by_band: Record<string, number>; cells: Record<string, { id: string; title: string; kind: string; score: number; band: string }[]> }>(`${base}/risk-matrix`);
  const risks = useApi<{ count: number; risks: Risk[] }>(`${base}/risks`);
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const cols: Column<Risk>[] = [
    {
      key: "title",
      header: "Item",
      render: (r) => (
        <div className="min-w-[180px]">
          <p className="font-semibold">{r.title}</p>
          <p className="text-xs text-ink-mute">
            {titleCase(r.kind)}
            {r.category ? ` · ${titleCase(r.category)}` : ""}
          </p>
        </div>
      ),
    },
    { key: "score", header: "Score", render: (r) => <Badge tone={BAND_TONE[r.band] ?? "gray"}>{r.probability}×{r.impact} = {r.score}</Badge> },
    { key: "owner", header: "Owner" },
    { key: "mitigation", header: "Mitigation", render: (r) => <span className="line-clamp-2 max-w-[260px] text-xs text-ink-mute">{r.mitigation ?? "—"}</span> },
    { key: "due_on", header: "Due", render: (r) => date(r.due_on) },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
  ];
  const rows = (risks.data?.risks ?? []).filter((r) => !sel || `${r.probability}x${r.impact}` === sel);
  return (
    <div className="grid gap-6 xl:grid-cols-5">
      <Card className="xl:col-span-2">
        <CardHeader title="Risk heat-map" subtitle="Probability × impact (click a cell to filter)" icon={<ShieldAlert className="h-5 w-5" />} />
        <CardBody>
          <QueryState q={matrix} skeleton={<Skeleton className="h-72" />}>
            {(m) => (
              <div>
                <div className="flex gap-2">
                  <div className="flex w-5 items-center justify-center">
                    <span className="-rotate-90 whitespace-nowrap text-[10px] font-bold uppercase tracking-widest text-ink-mute">Impact →</span>
                  </div>
                  <div className="grid flex-1 grid-cols-5 gap-1.5">
                    {[5, 4, 3, 2, 1].map((imp) =>
                      [1, 2, 3, 4, 5].map((prob) => {
                        const key = `${prob}x${imp}`;
                        const items = m.cells?.[key] ?? [];
                        const band = bandOf(prob * imp);
                        return (
                          <button
                            key={key}
                            onClick={() => setSel(sel === key ? null : key)}
                            title={items.map((i) => i.title).join("\n") || `P${prob} × I${imp}`}
                            className={cn(
                              "relative flex aspect-square flex-col items-center justify-center rounded-xl text-xs transition hover:scale-105",
                              BAND_BG[band],
                              sel === key && "ring-2 ring-brand-700 ring-offset-2 dark:ring-gold-400 dark:ring-offset-[#0d1f16]",
                            )}
                          >
                            <span className="text-[10px] text-ink-mute">{prob * imp}</span>
                            {items.length > 0 && (
                              <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-brand-950 text-[11px] font-bold text-white shadow dark:bg-white dark:text-brand-950">
                                {items.length}
                              </motion.span>
                            )}
                          </button>
                        );
                      }),
                    )}
                  </div>
                </div>
                <p className="mt-2 text-center text-[10px] font-bold uppercase tracking-widest text-ink-mute">Probability →</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {["low", "medium", "high", "extreme"].map((b) => (
                    <Badge key={b} tone={BAND_TONE[b]}>
                      {titleCase(b)} · {m.by_band?.[b] ?? 0}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </QueryState>
        </CardBody>
      </Card>
      <Card className="overflow-hidden xl:col-span-3">
        <CardHeader
          title="RAID log"
          subtitle={sel ? `Filtered to cell ${sel.replace("x", " × ")}` : "Risks, assumptions, issues, dependencies"}
          icon={<ClipboardList className="h-5 w-5" />}
          action={
            <div className="flex gap-2">
              {sel && (
                <Button size="sm" variant="ghost" onClick={() => setSel(null)}>
                  Clear
                </Button>
              )}
              <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>
                Add item
              </Button>
            </div>
          }
        />
        <QueryState q={risks} skeleton={<Skeleton className="m-5 h-60" />}>
          {() => <DataTable rows={rows} columns={cols} pageSize={10} />}
        </QueryState>
      </Card>
      {open && <AddRisk base={base} onClose={() => setOpen(false)} />}
    </div>
  );
}

function usePmoMeta() {
  return useApi<PmoMeta>("/pmo/overview", undefined, { staleTime: 10 * 60_000 });
}

function AddRisk({ base, onClose }: { base: string; onClose: () => void }) {
  const meta = usePmoMeta();
  const [f, setF] = useState({ title: "", kind: "risk", category: "", probability: 3, impact: 3, owner: "", mitigation: "", due_on: "", description: "" });
  const m = useMutate(
    () =>
      ok(
        post(`${base}/risks`, {
          ...f,
          category: f.category || null,
          owner: f.owner || null,
          mitigation: f.mitigation || null,
          due_on: f.due_on || null,
          description: f.description || null,
        }),
      ),
    { invalidate: ["/pmo"], success: "RAID item added", onSuccess: onClose },
  );
  const score = f.probability * f.impact;
  return (
    <Modal
      open
      onClose={onClose}
      title="Add RAID item"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} disabled={!f.title.trim()} onClick={() => m.mutate()}>
            Add
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title" className="sm:col-span-2">
          <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} autoFocus />
        </Field>
        <Field label="Kind">
          <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} options={(meta.data?.raid_kinds ?? ["risk", "issue", "assumption", "dependency"]).map((k) => ({ value: k, label: titleCase(k) }))} />
        </Field>
        <Field label="Category">
          <Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            <option value="">—</option>
            {(meta.data?.risk_categories ?? []).map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={`Probability · ${f.probability}`}>
          <Slider value={f.probability} min={1} max={5} onChange={(v) => setF({ ...f, probability: v })} />
        </Field>
        <Field label={`Impact · ${f.impact}`}>
          <Slider value={f.impact} min={1} max={5} onChange={(v) => setF({ ...f, impact: v })} />
        </Field>
        <div className="sm:col-span-2">
          <Badge tone={BAND_TONE[bandOf(score)]}>
            Score {score} · {bandOf(score)}
          </Badge>
        </div>
        <Field label="Owner">
          <Input value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} />
        </Field>
        <Field label="Due on">
          <Input type="date" value={f.due_on} onChange={(e) => setF({ ...f, due_on: e.target.value })} />
        </Field>
        <Field label="Mitigation" className="sm:col-span-2">
          <Textarea rows={2} value={f.mitigation} onChange={(e) => setF({ ...f, mitigation: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- costs
interface CostEntry {
  id: string;
  date: string;
  category: string;
  description: string;
  amount: number;
  kind: string;
  vendor?: string | null;
  invoice_ref?: string | null;
}
function Costs({ base }: { base: string }) {
  const status = useApi<CostStatus>(`${base}/cost-status`);
  const costs = useApi<{ count: number; entries: CostEntry[]; total: number }>(`${base}/costs`);
  const [open, setOpen] = useState(false);
  const cols: Column<CostEntry>[] = [
    { key: "date", header: "Date", render: (c) => date(c.date) },
    {
      key: "description",
      header: "Description",
      render: (c) => (
        <div>
          <p className="font-semibold">{c.description || "—"}</p>
          <p className="text-xs text-ink-mute">{c.vendor ?? ""}</p>
        </div>
      ),
    },
    { key: "category", header: "Category", render: (c) => <Badge tone="gray">{titleCase(c.category)}</Badge> },
    { key: "kind", header: "Kind", render: (c) => <Badge tone={c.kind === "actual" ? "green" : "blue"}>{c.kind}</Badge> },
    { key: "amount", header: "Amount", align: "right", render: (c) => <span className="font-semibold">{pkr(c.amount)}</span> },
  ];
  return (
    <div className="space-y-6">
      <QueryState q={status} skeleton={<Skeleton className="h-40" />}>
        {(s) => (
          <div className="grid gap-6 xl:grid-cols-5">
            <Card className="xl:col-span-2">
              <CardHeader title="Cost control" subtitle={`${pct(s.spent_pct, 1, false)} of revised budget spent`} icon={<Coins className="h-5 w-5" />} />
              <CardBody className="space-y-4">
                <div>
                  <div className="mb-1 flex justify-between text-xs">
                    <span>Exposure (actual + committed)</span>
                    <span className="font-semibold">{pkrShort(s.exposure)} / {pkrShort(s.revised_budget)}</span>
                  </div>
                  <Progress value={s.exposure} max={s.revised_budget || 1} tone={s.exposure > s.revised_budget ? "red" : "green"} />
                </div>
                <KeyValue
                  items={[
                    { label: "Baseline budget", value: pkrShort(s.baseline_budget) },
                    { label: "Approved changes", value: pkrShort(s.approved_changes) },
                    { label: "Revised budget", value: pkrShort(s.revised_budget) },
                    { label: "Contract value", value: pkrShort(s.contract_value) },
                    { label: "Actual cost", value: pkrShort(s.actual_cost) },
                    { label: "Committed", value: pkrShort(s.committed_cost) },
                    { label: "Forecast to complete", value: pkrShort(s.forecast_to_complete) },
                    { label: "Forecast final", value: pkrShort(s.forecast_final) },
                    { label: "Variance at completion", value: <span className={s.variance_at_completion < 0 ? "text-red-600" : "text-emerald-600"}>{pkrShort(s.variance_at_completion)}</span> },
                    { label: "Margin (contract − forecast)", value: pkrShort(s.contract_value - s.forecast_final) },
                  ]}
                />
              </CardBody>
            </Card>
            <Card className="xl:col-span-3">
              <CardHeader title="By category" subtitle="Actual vs committed" icon={<BarChart3 className="h-5 w-5" />} />
              <CardBody>
                <Bars
                  data={Object.entries(s.by_category ?? {}).map(([k, v]) => ({ name: titleCase(k), actual: v.actual, committed: v.committed }))}
                  x="name"
                  stacked
                  height={300}
                  format={(v) => pkrShort(v, false)}
                  series={[
                    { key: "actual", label: "Actual", color: "#146f45" },
                    { key: "committed", label: "Committed", color: "#c99a22" },
                  ]}
                />
              </CardBody>
            </Card>
          </div>
        )}
      </QueryState>
      <Card className="overflow-hidden">
        <CardHeader
          title="Cost ledger"
          subtitle={costs.data ? `${costs.data.count} entries · ${pkr(costs.data.total)}` : undefined}
          icon={<FileText className="h-5 w-5" />}
          action={
            <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>
              Record cost
            </Button>
          }
        />
        <QueryState q={costs} skeleton={<Skeleton className="m-5 h-48" />}>
          {(d) => <DataTable rows={d.entries} columns={cols} search pageSize={10} />}
        </QueryState>
      </Card>
      {open && <AddCost base={base} onClose={() => setOpen(false)} />}
    </div>
  );
}

function AddCost({ base, onClose }: { base: string; onClose: () => void }) {
  const meta = usePmoMeta();
  const user = useAuth((s) => s.user);
  const [f, setF] = useState({ amount: "", category: "structure", description: "", kind: "actual", date: today(), vendor: "", invoice_ref: "" });
  const m = useMutate(
    () =>
      ok(
        post(`${base}/costs`, {
          ...f,
          amount: Number(f.amount),
          vendor: f.vendor || null,
          invoice_ref: f.invoice_ref || null,
          recorded_by: user?.name ?? user?.email ?? null,
        }),
      ),
    { invalidate: ["/pmo"], success: "Cost recorded", onSuccess: onClose },
  );
  return (
    <Modal
      open
      onClose={onClose}
      title="Record a cost"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} disabled={!(Number(f.amount) > 0)} onClick={() => m.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Amount (PKR)" hint={f.amount ? pkrShort(Number(f.amount)) : undefined}>
          <Input type="number" min={0} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} autoFocus />
        </Field>
        <Field label="Kind">
          <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} options={[{ value: "actual", label: "Actual (paid / invoiced)" }, { value: "committed", label: "Committed (PO / contract)" }]} />
        </Field>
        <Field label="Category">
          <Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} options={(meta.data?.cost_categories ?? ["structure", "other"]).map((c) => ({ value: c, label: titleCase(c) }))} />
        </Field>
        <Field label="Date">
          <Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
        </Field>
        <Field label="Description" className="sm:col-span-2">
          <Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        <Field label="Vendor">
          <Input value={f.vendor} onChange={(e) => setF({ ...f, vendor: e.target.value })} />
        </Field>
        <Field label="Invoice ref">
          <Input value={f.invoice_ref} onChange={(e) => setF({ ...f, invoice_ref: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- milestones
function Milestones({ base }: { base: string }) {
  const q = useApi<{ count: number; milestones: Milestone[] }>(`${base}/milestones`);
  return (
    <QueryState q={q} skeleton={<Skeleton className="h-60" />}>
      {(d) =>
        d.milestones.length === 0 ? (
          <EmptyState title="No milestones" icon={<Flag className="h-6 w-6" />} />
        ) : (
          <div className="relative space-y-4 ps-8 before:absolute before:inset-y-2 before:start-3 before:w-0.5 before:bg-gradient-to-b before:from-brand-600 before:to-gold-400">
            {d.milestones.map((ms, i) => (
              <motion.div key={ms.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }} className="relative">
                <span
                  className={cn(
                    "absolute -start-[26px] top-5 flex h-5 w-5 items-center justify-center rounded-full ring-4 ring-white dark:ring-[#0b1a12]",
                    ms.status === "met" ? "bg-emerald-500" : ms.status === "missed" ? "bg-red-500" : ms.status === "at_risk" ? "bg-amber-500" : "bg-brand-300",
                  )}
                >
                  {ms.status === "met" && <CheckCircle2 className="h-3.5 w-3.5 text-white" />}
                </span>
                <Card className="p-4 transition hover:shadow-soft">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-display font-semibold">{ms.name}</p>
                      <p className="text-xs text-ink-mute">{titleCase(ms.phase_key ?? "")}</p>
                    </div>
                    <StatusBadge status={ms.status} />
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                    <span>
                      <span className="text-ink-mute">Planned</span> <b>{date(ms.planned_date)}</b>
                    </span>
                    <span>
                      <span className="text-ink-mute">Forecast</span> <b>{date(ms.forecast_date)}</b>
                    </span>
                    <span>
                      <span className="text-ink-mute">Billable</span> <b>{pkrShort(ms.billable_amount)}</b>
                    </span>
                    <span>
                      <span className="text-ink-mute">Slip</span> <b className={ms.slip_days > 0 ? "text-red-600" : ""}>{ms.slip_days} d</b>
                    </span>
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
        )
      }
    </QueryState>
  );
}

// ---------------------------------------------------------------- site diary
interface SiteLog {
  id: string;
  date: string;
  weather?: string | null;
  manpower: number;
  equipment?: string[];
  work_done?: string | null;
  issues?: string | null;
  safety_incidents: number;
  visitors?: string | null;
  by?: string | null;
}
function Diary({ base }: { base: string }) {
  const q = useApi<{ count: number; logs: SiteLog[]; manpower_total: number; safety_incidents: number }>(`${base}/site-logs`);
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {q.data && (
            <>
              <Badge tone="green" icon={<Users className="h-3 w-3" />}>
                {num(q.data.manpower_total)} man-days
              </Badge>
              <Badge tone={q.data.safety_incidents ? "red" : "green"} icon={<HardHat className="h-3 w-3" />}>
                {q.data.safety_incidents} safety incident(s)
              </Badge>
            </>
          )}
        </div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>
          New diary entry
        </Button>
      </div>
      <QueryState q={q} skeleton={<Skeleton className="h-48" />}>
        {(d) =>
          d.logs.length === 0 ? (
            <EmptyState title="No diary entries yet" icon={<NotebookPen className="h-6 w-6" />} />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {d.logs.map((l) => (
                <Card key={l.id} className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-display text-lg font-semibold">{date(l.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</p>
                      <p className="text-xs text-ink-mute">by {l.by ?? "—"}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {l.weather && (
                        <Badge tone="blue" icon={<Sun className="h-3 w-3" />}>
                          {l.weather}
                        </Badge>
                      )}
                      <Badge tone="gray" icon={<Users className="h-3 w-3" />}>
                        {l.manpower} workers
                      </Badge>
                    </div>
                  </div>
                  {l.work_done && <p className="mt-3 text-sm">{l.work_done}</p>}
                  {l.issues && <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-200">⚠ {l.issues}</p>}
                  {!!l.equipment?.length && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {l.equipment.map((e) => (
                        <Badge key={e} tone="gray">
                          {e}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-ink-mute">
                    <span className={l.safety_incidents ? "font-semibold text-red-600" : ""}>{l.safety_incidents} safety incident(s)</span>
                    {l.visitors && <span>Visitors: {l.visitors}</span>}
                  </div>
                </Card>
              ))}
            </div>
          )
        }
      </QueryState>
      {open && <AddLog base={base} onClose={() => setOpen(false)} />}
    </div>
  );
}

function AddLog({ base, onClose }: { base: string; onClose: () => void }) {
  const user = useAuth((s) => s.user);
  const [f, setF] = useState({ date: today(), weather: "", manpower: "0", equipment: "", work_done: "", issues: "", safety_incidents: "0", visitors: "" });
  const m = useMutate(
    () =>
      ok(
        post(`${base}/site-logs`, {
          date: f.date,
          weather: f.weather || null,
          manpower: Number(f.manpower) || 0,
          equipment: f.equipment
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          work_done: f.work_done || null,
          issues: f.issues || null,
          safety_incidents: Number(f.safety_incidents) || 0,
          visitors: f.visitors || null,
          by: user?.name ?? null,
        }),
      ),
    { invalidate: ["/pmo"], success: "Diary entry saved", onSuccess: onClose },
  );
  return (
    <Modal
      open
      onClose={onClose}
      title="Site diary entry"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} onClick={() => m.mutate()}>
            Save entry
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Date">
          <Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
        </Field>
        <Field label="Weather">
          <Input value={f.weather} onChange={(e) => setF({ ...f, weather: e.target.value })} placeholder="Clear, 34°C" />
        </Field>
        <Field label="Manpower">
          <Input type="number" min={0} value={f.manpower} onChange={(e) => setF({ ...f, manpower: e.target.value })} />
        </Field>
        <Field label="Work done" className="sm:col-span-3">
          <Textarea rows={3} value={f.work_done} onChange={(e) => setF({ ...f, work_done: e.target.value })} />
        </Field>
        <Field label="Issues" className="sm:col-span-3">
          <Textarea rows={2} value={f.issues} onChange={(e) => setF({ ...f, issues: e.target.value })} />
        </Field>
        <Field label="Equipment (comma separated)" className="sm:col-span-2">
          <Input value={f.equipment} onChange={(e) => setF({ ...f, equipment: e.target.value })} placeholder="Tower crane, Concrete pump" />
        </Field>
        <Field label="Safety incidents">
          <Input type="number" min={0} value={f.safety_incidents} onChange={(e) => setF({ ...f, safety_incidents: e.target.value })} />
        </Field>
        <Field label="Visitors" className="sm:col-span-3">
          <Input value={f.visitors} onChange={(e) => setF({ ...f, visitors: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- inspections
interface Inspection {
  id: string;
  title: string;
  phase_key?: string | null;
  area?: string | null;
  inspector?: string | null;
  date?: string | null;
  checklist: { item: string; result: string; note?: string | null }[];
  status: string;
  notes?: string | null;
}
function Inspections({ base }: { base: string }) {
  const q = useApi<{ count: number; inspections: Inspection[]; quality_index: { score: number; items: number; passed: number; failures: { inspection: string; item: string; note?: string }[] } }>(`${base}/inspections`);
  return (
    <QueryState q={q} skeleton={<Skeleton className="h-60" />}>
      {(d) => (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="p-6 text-center">
            <p className="label">Quality index</p>
            <div className="mt-2 flex justify-center">
              <Ring value={d.quality_index?.score ?? 0} size={130} stroke={11} color={(d.quality_index?.score ?? 0) >= 85 ? "#146f45" : (d.quality_index?.score ?? 0) >= 70 ? "#c99a22" : "#dc2626"}>
                <span className="font-display text-3xl font-bold">{Math.round(d.quality_index?.score ?? 0)}</span>
                <span className="text-[10px] uppercase text-ink-mute">/ 100</span>
              </Ring>
            </div>
            <p className="mt-3 text-sm text-ink-mute">
              {d.quality_index?.passed ?? 0} of {d.quality_index?.items ?? 0} checks passed across {d.count} inspection(s)
            </p>
            {!!d.quality_index?.failures?.length && (
              <div className="mt-4 space-y-2 text-start">
                {d.quality_index.failures.map((f, i) => (
                  <div key={i} className="rounded-xl bg-red-50 px-3 py-2 text-xs dark:bg-red-500/10">
                    <p className="font-semibold text-red-700 dark:text-red-300">{f.item}</p>
                    {f.note && <p className="text-red-700/80 dark:text-red-300/80">{f.note}</p>}
                  </div>
                ))}
              </div>
            )}
          </Card>
          <div className="space-y-4 lg:col-span-2">
            {d.inspections.length === 0 && <EmptyState title="No inspections recorded" />}
            {d.inspections.map((ins) => (
              <Card key={ins.id} className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-display font-semibold">{ins.title}</p>
                    <p className="text-xs text-ink-mute">
                      {titleCase(ins.area ?? ins.phase_key ?? "")} · {ins.inspector ?? "—"} · {date(ins.date)}
                    </p>
                  </div>
                  <StatusBadge status={ins.status} />
                </div>
                <ul className="mt-3 divide-y divide-black/5 dark:divide-white/10">
                  {ins.checklist.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 py-2 text-sm">
                      {c.result === "pass" ? <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : c.result === "fail" ? <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" /> : <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-slate-400" />}
                      <div>
                        <p>{c.item}</p>
                        {c.note && <p className="text-xs text-ink-mute">{c.note}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        </div>
      )}
    </QueryState>
  );
}

// ---------------------------------------------------------------- changes
interface Change {
  id: string;
  title: string;
  description?: string | null;
  reason?: string | null;
  cost_impact: number;
  schedule_impact_days: number;
  status: string;
  requested_by?: string | null;
  decided_by?: string | null;
  decided_on?: string | null;
  decision_note?: string | null;
  raised_on?: string | null;
}
function Changes({ base }: { base: string }) {
  const q = useApi<{ count: number; changes: Change[]; approved_cost_impact: number; approved_schedule_impact_days: number }>(`${base}/changes`);
  const [decide, setDecide] = useState<{ c: Change; approve: boolean } | null>(null);
  return (
    <div className="space-y-4">
      {q.data && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard label="Change requests" value={q.data.count} icon={<GitPullRequest className="h-5 w-5" />} />
          <StatCard label="Approved cost impact" value={pkrShort(q.data.approved_cost_impact)} tone="gold" icon={<Coins className="h-5 w-5" />} />
          <StatCard label="Approved delay" value={`${q.data.approved_schedule_impact_days} d`} tone="blue" icon={<CalendarClock className="h-5 w-5" />} />
        </div>
      )}
      <QueryState q={q} skeleton={<Skeleton className="h-48" />}>
        {(d) =>
          d.changes.length === 0 ? (
            <EmptyState title="No change requests" icon={<GitPullRequest className="h-6 w-6" />} />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {d.changes.map((c) => {
                const pending = c.status === "submitted" || c.status === "draft";
                return (
                  <Card key={c.id} className="flex flex-col p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-display font-semibold">{c.title}</p>
                        <p className="text-xs text-ink-mute">
                          {c.requested_by ?? "—"} · raised {date(c.raised_on)}
                        </p>
                      </div>
                      <StatusBadge status={c.status} />
                    </div>
                    {c.description && <p className="mt-3 text-sm">{c.description}</p>}
                    {c.reason && <p className="mt-1 text-xs text-ink-mute">Reason: {c.reason}</p>}
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      <div className="rounded-xl bg-gold-50 px-3 py-2 dark:bg-gold-500/10">
                        <p className="text-[10px] font-bold uppercase text-gold-700 dark:text-gold-300">Cost impact</p>
                        <p className="font-semibold">{pkrShort(c.cost_impact)}</p>
                      </div>
                      <div className="rounded-xl bg-sky-50 px-3 py-2 dark:bg-sky-500/10">
                        <p className="text-[10px] font-bold uppercase text-sky-700 dark:text-sky-300">Schedule impact</p>
                        <p className="font-semibold">{c.schedule_impact_days} days</p>
                      </div>
                    </div>
                    {c.decided_by && (
                      <p className="mt-3 text-xs text-ink-mute">
                        Decided by {c.decided_by} on {date(c.decided_on)}
                        {c.decision_note ? ` — “${c.decision_note}”` : ""}
                      </p>
                    )}
                    {pending && (
                      <div className="mt-auto flex gap-2 pt-4">
                        <Button size="sm" icon={<CheckCircle2 className="h-4 w-4" />} onClick={() => setDecide({ c, approve: true })}>
                          Approve
                        </Button>
                        <Button size="sm" variant="outline" icon={<XCircle className="h-4 w-4" />} onClick={() => setDecide({ c, approve: false })}>
                          Reject
                        </Button>
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )
        }
      </QueryState>
      {decide && <DecideChange change={decide.c} approve={decide.approve} onClose={() => setDecide(null)} />}
    </div>
  );
}

function DecideChange({ change, approve, onClose }: { change: Change; approve: boolean; onClose: () => void }) {
  const user = useAuth((s) => s.user);
  const [note, setNote] = useState("");
  const m = useMutate(() => ok(post(`/pmo/changes/${change.id}/decide`, { approve, by: user?.name ?? user?.email ?? null, note: note || null })), {
    invalidate: ["/pmo"],
    success: approve ? "Change approved — budget updated" : "Change rejected",
    onSuccess: onClose,
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={`${approve ? "Approve" : "Reject"} change request`}
      subtitle={change.title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={approve ? "primary" : "danger"} loading={m.isPending} onClick={() => m.mutate()}>
            Confirm {approve ? "approval" : "rejection"}
          </Button>
        </>
      }
    >
      {approve && (
        <p className="mb-4 rounded-xl bg-gold-50 px-4 py-3 text-sm text-gold-800 dark:bg-gold-500/10 dark:text-gold-200">
          Approving adds {pkrShort(change.cost_impact)} to the revised budget and {change.schedule_impact_days} day(s) to the schedule.
        </p>
      )}
      <Field label="Decision note">
        <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
    </Modal>
  );
}

// ---------------------------------------------------------------- KPI
function KpiTab({ base }: { base: string }) {
  const q = useApi<Kpi>(`${base}/kpi`);
  return <QueryState q={q} skeleton={<Skeleton className="h-60" />}>{(k) => <KpiCards k={k} big />}</QueryState>;
}

function KpiCards({ k, big }: { k: Kpi; big?: boolean }) {
  if (!k) return null;
  const tiles: { label: string; value: string; good: boolean | null; hint?: string }[] = [
    { label: "SPI", value: num(k.schedule_performance_index, 3), good: k.schedule_performance_index >= 0.95, hint: "≥ 0.95 green" },
    { label: "CPI", value: num(k.cost_performance_index, 3), good: k.cost_performance_index >= 0.95, hint: "≥ 0.95 green" },
    { label: "Progress", value: pct(k.progress_pct, 1, false), good: k.progress_pct >= k.planned_pct, hint: `plan ${pct(k.planned_pct, 1, false)}` },
    { label: "Spent", value: pct(k.spent_pct, 1, false), good: k.spent_pct <= k.progress_pct + 5, hint: "of budget" },
    { label: "Budget variance", value: pkrShort(k.budget_variance), good: k.budget_variance >= 0 },
    { label: "Milestones met", value: `${k.milestones_met}/${k.milestones_total}`, good: k.milestones_at_risk === 0, hint: `${k.milestones_at_risk} at risk` },
    { label: "Open risks", value: String(k.open_risks), good: k.high_risks === 0, hint: `${k.high_risks} high` },
    { label: "Open changes", value: String(k.open_changes), good: k.open_changes === 0 },
    { label: "Open actions", value: String(k.open_actions), good: k.open_actions === 0 },
    { label: "Open tasks", value: String(k.critical_tasks), good: null, hint: "not yet done" },
  ];
  return (
    <div>
      {big && (
        <div className="mb-4 flex items-center gap-3">
          <RagPill rag={k.health} label={`Overall ${k.health}`} className="text-sm" />
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {tiles.map((t) => (
          <div
            key={t.label}
            className={cn(
              "card relative overflow-hidden p-4",
              t.good === true && "border-emerald-200 dark:border-emerald-500/20",
              t.good === false && "border-red-200 dark:border-red-500/20",
            )}
          >
            <span className={cn("absolute inset-y-0 start-0 w-1", t.good === true ? "bg-emerald-500" : t.good === false ? "bg-red-500" : "bg-slate-300")} />
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-mute">{t.label}</p>
            <p className={cn("mt-1 font-display font-bold text-ink dark:text-white", big ? "text-2xl" : "text-xl")}>{t.value}</p>
            {t.hint && <p className="text-[11px] text-ink-mute">{t.hint}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
