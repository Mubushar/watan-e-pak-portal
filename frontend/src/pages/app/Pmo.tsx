import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  BriefcaseBusiness,
  CalendarRange,
  Coins,
  FileText,
  Gauge,
  MapPin,
  Plus,
  ShieldAlert,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { apiUrl, post } from "@/lib/api";
import { date, num, pct, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, type Column, DataTable, EmptyState, Field, Input, Modal, PageHeader, Progress, QueryState, Select, Skeleton, StatCard, StatusBadge, Textarea, Toggle } from "@/components/ui";
import { Bars, Donut, Legendish } from "@/components/ui/charts";
import { ok, RAG_HEX, RagPill, Ring, stagger } from "@/components/collab/kit";

// ---------------------------------------------------------------- types
interface PortfolioRow {
  id: string;
  code: string;
  name: string;
  status: string;
  project_type: string;
  city?: string | null;
  progress_pct: number;
  health: string;
  budget: number;
  actual_cost: number;
  SPI: number;
  CPI: number;
}
interface Portfolio {
  projects: number;
  by_status: Record<string, number>;
  by_health: Record<string, number>;
  financials: { total_budget: number; total_actual: number; total_committed: number };
  portfolio_spi: number;
  portfolio_cpi: number;
  resources: number;
  open_risks: number;
  alerts: number;
  rows: PortfolioRow[];
}
interface ProjectListItem {
  id: string;
  code: string;
  name: string;
  project_type: string;
  city?: string | null;
  status: string;
  priority: string;
  start_date?: string | null;
  end_date?: string | null;
  budget: number;
  progress_pct: number;
  health: string;
}
interface Alert {
  level: string;
  kind: string;
  project_id: string;
  project: string;
  ref?: string;
  message: string;
}
interface Risk {
  id: string;
  project_id: string;
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
interface ResourceLoad {
  resource_id: string;
  name: string;
  role: string;
  capacity_pct: number;
  planned_pct: number;
  utilisation_pct: number;
  over_allocated: boolean;
  tasks: { task: string; units_pct: number; start: string; end: string }[];
}
interface ProjectTypes {
  types: Record<string, { label: string; icon: string }>;
  statuses: string[];
  priorities: string[];
}

const BAND_TONE: Record<string, "green" | "gold" | "orange" | "red"> = { low: "green", medium: "gold", high: "orange", extreme: "red" };

// ---------------------------------------------------------------- page
export default function Pmo() {
  const portfolio = useApi<Portfolio>("/pmo/portfolio");
  const projects = useApi<{ count: number; projects: ProjectListItem[] }>("/pmo/projects", { limit: 100 });
  const alerts = useApi<{ count: number; red: number; amber: number; alerts: Alert[] }>("/pmo/alerts");
  const risks = useApi<{ count: number; risks: Risk[] }>("/pmo/risks");
  const load = useApi<{ count: number; over_allocated: number; resources: ResourceLoad[] }>("/pmo/resource-load");
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("all");
  const nav = useNavigate();

  const p = portfolio.data;
  const nameOf = useMemo(() => {
    const m: Record<string, string> = {};
    (projects.data?.projects ?? []).forEach((x) => (m[x.id] = x.name));
    return m;
  }, [projects.data]);

  const merged = useMemo(() => {
    const rows = p?.rows ?? [];
    const list = projects.data?.projects ?? [];
    const byId = new Map(rows.map((r) => [r.id, r]));
    const ids = new Set([...list.map((x) => x.id), ...rows.map((r) => r.id)]);
    return [...ids].map((id) => {
      const a = list.find((x) => x.id === id);
      const b = byId.get(id);
      return { ...(a ?? {}), ...(b ?? {}) } as ProjectListItem & Partial<PortfolioRow>;
    });
  }, [p, projects.data]);
  const statuses = useMemo(() => ["all", ...new Set(merged.map((m) => m.status))], [merged]);
  const shown = status === "all" ? merged : merged.filter((m) => m.status === status);

  const healthData = p
    ? (["green", "amber", "red"] as const).map((k) => ({ name: titleCase(k), value: p.by_health?.[k] ?? 0, color: RAG_HEX[k] }))
    : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Projects & PMO"
        subtitle="Portfolio health, earned value, risks and resource load across every delivery project."
        crumbs={[{ label: "Dashboard", to: "/app" }, { label: "Projects" }]}
        actions={
          <>
            <a href={apiUrl("/pmo/portal")} target="_blank" rel="noreferrer" className="btn btn-outline">
              <FileText className="h-4 w-4" /> Portfolio report
            </a>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>
              New project
            </Button>
          </>
        }
      />

      {/* KPIs */}
      {portfolio.isLoading ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : p ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
          <StatCard label="Total budget" value={pkrShort(p.financials.total_budget)} icon={<Wallet className="h-5 w-5" />} hint={`${p.projects} project${p.projects === 1 ? "" : "s"}`} />
          <StatCard
            label="Actual cost"
            value={pkrShort(p.financials.total_actual)}
            icon={<Coins className="h-5 w-5" />}
            tone="gold"
            hint={p.financials.total_budget ? `${pct(p.financials.total_actual / p.financials.total_budget)} of budget` : undefined}
          />
          <StatCard label="Committed" value={pkrShort(p.financials.total_committed)} icon={<BriefcaseBusiness className="h-5 w-5" />} tone="blue" hint="open POs & contracts" />
          <StatCard label="Portfolio SPI" value={num(p.portfolio_spi, 2)} icon={<CalendarRange className="h-5 w-5" />} tone={p.portfolio_spi >= 1 ? "green" : p.portfolio_spi >= 0.9 ? "gold" : "red"} hint={p.portfolio_spi >= 1 ? "ahead of plan" : "behind plan"} />
          <StatCard label="Portfolio CPI" value={num(p.portfolio_cpi, 2)} icon={<Gauge className="h-5 w-5" />} tone={p.portfolio_cpi >= 1 ? "green" : p.portfolio_cpi >= 0.9 ? "gold" : "red"} hint={p.portfolio_cpi >= 1 ? "under budget" : "over budget"} />
          <StatCard label="Open risks" value={p.open_risks} icon={<ShieldAlert className="h-5 w-5" />} tone="red" hint={`${p.alerts} active alert${p.alerts === 1 ? "" : "s"}`} />
        </div>
      ) : portfolio.error ? (
        <QueryState q={portfolio}>{() => null}</QueryState>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-3">
        {/* Health distribution */}
        <Card>
          <CardHeader title="Health distribution" subtitle="RAG status of all projects" icon={<Gauge className="h-5 w-5" />} />
          <CardBody>
            {p ? (
              <>
                <Donut
                  data={healthData}
                  height={210}
                  format={(v) => String(v)}
                  center={
                    <>
                      <span className="font-display text-3xl font-bold">{p.projects}</span>
                      <span className="text-xs text-ink-mute">projects</span>
                    </>
                  }
                />
                <div className="mt-3 flex justify-center">
                  <Legendish data={healthData} />
                </div>
                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  {Object.entries(p.by_status ?? {}).map(([k, v]) => (
                    <Badge key={k} tone="gray">
                      {titleCase(k)} · {v}
                    </Badge>
                  ))}
                </div>
              </>
            ) : (
              <Skeleton className="h-60" />
            )}
          </CardBody>
        </Card>

        {/* Alerts */}
        <Card className="xl:col-span-2">
          <CardHeader
            title="Exception alerts"
            subtitle="What needs a decision today"
            icon={<BellRing className="h-5 w-5" />}
            action={alerts.data && <Badge tone={alerts.data.red ? "red" : "gold"}>{alerts.data.red} red · {alerts.data.amber} amber</Badge>}
          />
          <CardBody className="max-h-[360px] overflow-y-auto">
            <QueryState q={alerts} skeleton={<Skeleton className="h-48" />}>
              {(d) =>
                d.alerts.length === 0 ? (
                  <EmptyState title="No alerts" hint="Every project is inside its tolerances." icon={<BellRing className="h-6 w-6" />} />
                ) : (
                  <ul className="space-y-2.5">
                    {d.alerts.map((a, i) => (
                      <motion.li key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                        <Link
                          to={`/app/pmo/${a.project_id}`}
                          className={cn(
                            "group flex items-start gap-3 rounded-2xl border p-3.5 transition hover:shadow-soft",
                            a.level === "red" ? "border-red-200 bg-red-50/60 dark:border-red-500/20 dark:bg-red-500/5" : "border-amber-200 bg-amber-50/60 dark:border-amber-500/20 dark:bg-amber-500/5",
                          )}
                        >
                          <AlertTriangle className={cn("mt-0.5 h-5 w-5 shrink-0", a.level === "red" ? "text-red-600" : "text-amber-600")} />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-ink dark:text-white">{a.message}</p>
                            <p className="mt-0.5 text-xs text-ink-mute">
                              {a.project} · {titleCase(a.kind)}
                            </p>
                          </div>
                          <ArrowRight className="h-4 w-4 shrink-0 text-ink-mute transition group-hover:translate-x-0.5 rtl:rotate-180" />
                        </Link>
                      </motion.li>
                    ))}
                  </ul>
                )
              }
            </QueryState>
          </CardBody>
        </Card>
      </div>

      {/* Projects grid */}
      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-lg font-semibold text-brand-900 dark:text-white">Projects</h2>
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto">
            {statuses.map((s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={cn(
                  "rounded-full px-3 py-1.5 text-xs font-semibold capitalize transition",
                  status === s ? "bg-brand-700 text-white" : "bg-black/5 text-ink-soft hover:bg-brand-50 dark:bg-white/5 dark:text-slate-300",
                )}
              >
                {s.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>
        {projects.isLoading || portfolio.isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-64" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <EmptyState
            title="No projects yet"
            hint="Create a delivery project or convert a saved construction estimate."
            icon={<BriefcaseBusiness className="h-6 w-6" />}
            action={
              <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>
                New project
              </Button>
            }
          />
        ) : (
          <motion.div variants={stagger.container} initial="hidden" animate="show" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {shown.map((pr) => (
              <motion.div key={pr.id} variants={stagger.item}>
                <ProjectCard p={pr} onOpen={() => nav(`/app/pmo/${pr.id}`)} />
              </motion.div>
            ))}
          </motion.div>
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        {/* RAID */}
        <Card className="overflow-hidden xl:col-span-3">
          <CardHeader title="Portfolio RAID log" subtitle="Risks, assumptions, issues & dependencies" icon={<ShieldAlert className="h-5 w-5" />} />
          <QueryState q={risks} skeleton={<Skeleton className="m-5 h-48" />}>
            {(d) => <RaidTable rows={d.risks} projectName={(id) => nameOf[id]} onOpen={(r) => nav(`/app/pmo/${r.project_id}`)} />}
          </QueryState>
        </Card>

        {/* Resource load */}
        <Card className="xl:col-span-2">
          <CardHeader
            title="Resource load"
            subtitle="Planned utilisation vs capacity"
            icon={<Users className="h-5 w-5" />}
            action={load.data && load.data.over_allocated > 0 && <Badge tone="red">{load.data.over_allocated} over-allocated</Badge>}
          />
          <CardBody>
            <QueryState q={load} skeleton={<Skeleton className="h-60" />}>
              {(d) =>
                d.resources.length === 0 ? (
                  <EmptyState title="No allocations" />
                ) : (
                  <>
                    <Bars
                      data={d.resources.map((r) => ({ name: r.name, utilisation: r.utilisation_pct, capacity: r.capacity_pct }))}
                      x="name"
                      horizontal
                      height={Math.max(180, d.resources.length * 56)}
                      format={(v) => `${Math.round(v)}%`}
                      series={[
                        { key: "utilisation", label: "Planned %", color: "#c99a22" },
                        { key: "capacity", label: "Capacity %", color: "#146f45" },
                      ]}
                    />
                    <ul className="mt-4 space-y-2">
                      {d.resources.map((r) => (
                        <li key={r.resource_id} className="flex items-center justify-between gap-3 text-xs">
                          <span className="min-w-0 truncate">
                            <span className="font-semibold text-ink dark:text-white">{r.name}</span> <span className="text-ink-mute">· {titleCase(r.role)} · {r.tasks.length} task(s)</span>
                          </span>
                          <Badge tone={r.over_allocated ? "red" : r.utilisation_pct >= 80 ? "gold" : "green"}>{Math.round(r.utilisation_pct)}%</Badge>
                        </li>
                      ))}
                    </ul>
                  </>
                )
              }
            </QueryState>
          </CardBody>
        </Card>
      </div>

      <NewProjectModal open={open} onClose={() => setOpen(false)} onCreated={(id) => id && nav(`/app/pmo/${id}`)} />
    </div>
  );
}

// ---------------------------------------------------------------- project card
function ProjectCard({ p, onOpen }: { p: ProjectListItem & Partial<PortfolioRow>; onOpen: () => void }) {
  const color = RAG_HEX[p.health] ?? RAG_HEX.gray;
  const spentPct = p.budget ? ((p.actual_cost ?? 0) / p.budget) * 100 : 0;
  return (
    <button onClick={onOpen} className="card group relative flex h-full w-full flex-col overflow-hidden p-5 text-start transition hover:-translate-y-1 hover:shadow-glow">
      <span className="absolute inset-x-0 top-0 h-1" style={{ background: color }} />
      <div className="flex items-start gap-4">
        <Ring value={p.progress_pct} color={color} size={70}>
          <span className="text-sm font-bold text-ink dark:text-white">{Math.round(p.progress_pct)}%</span>
          <span className="text-[9px] uppercase tracking-wide text-ink-mute">done</span>
        </Ring>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[11px] font-semibold text-ink-mute">{p.code}</span>
            <RagPill rag={p.health} />
          </div>
          <h3 className="mt-1 line-clamp-2 font-display text-base font-semibold text-ink group-hover:text-brand-700 dark:text-white dark:group-hover:text-gold-300">{p.name}</h3>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-ink-mute">
            <span>{titleCase(p.project_type)}</span>
            {p.city && (
              <span className="inline-flex items-center gap-0.5">
                <MapPin className="h-3 w-3" />
                {p.city}
              </span>
            )}
          </p>
        </div>
      </div>
      <div className="mt-5 space-y-1.5">
        <div className="flex justify-between text-xs">
          <span className="text-ink-mute">Budget vs actual</span>
          <span className="font-semibold tabular-nums">
            {pkrShort(p.actual_cost ?? 0, false)} / {pkrShort(p.budget, false)}
          </span>
        </div>
        <Progress value={spentPct} tone={spentPct > 100 ? "red" : spentPct > p.progress_pct + 5 ? "gold" : "green"} />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <Mini label="SPI" value={p.SPI !== undefined ? num(p.SPI, 2) : "—"} good={(p.SPI ?? 1) >= 1} />
        <Mini label="CPI" value={p.CPI !== undefined ? num(p.CPI, 2) : "—"} good={(p.CPI ?? 1) >= 1} />
        <Mini label="Priority" value={titleCase(p.priority ?? "—")} />
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-black/5 pt-3 text-xs text-ink-mute dark:border-white/10">
        <span>
          {date(p.start_date)} → {date(p.end_date)}
        </span>
        <StatusBadge status={p.status} />
      </div>
    </button>
  );
}

function Mini({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="rounded-xl bg-brand-50/60 px-2 py-1.5 dark:bg-white/5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-mute">{label}</p>
      <p className={cn("text-sm font-bold", good === undefined ? "text-ink dark:text-white" : good ? "text-emerald-600" : "text-red-600")}>{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------- RAID table
function RaidTable({ rows, projectName, onOpen }: { rows: Risk[]; projectName?: (id: string) => string | undefined; onOpen?: (r: Risk) => void }) {
  const cols: Column<Risk>[] = [
    {
      key: "title",
      header: "Item",
      render: (r) => (
        <div className="min-w-[180px]">
          <p className="font-semibold text-ink dark:text-white">{r.title}</p>
          <p className="text-xs text-ink-mute">
            {titleCase(r.kind)}
            {r.category ? ` · ${titleCase(r.category)}` : ""}
            {projectName?.(r.project_id) ? ` · ${projectName(r.project_id)}` : ""}
          </p>
        </div>
      ),
    },
    { key: "pi", header: "P × I", value: (r) => r.score, render: (r) => <span className="tabular-nums">{r.probability} × {r.impact}</span>, align: "center" },
    { key: "score", header: "Score", align: "center", render: (r) => <Badge tone={BAND_TONE[r.band] ?? "gray"}>{r.score} · {r.band}</Badge> },
    { key: "owner", header: "Owner", render: (r) => <span className="text-xs">{r.owner ?? "—"}</span> },
    { key: "mitigation", header: "Mitigation", render: (r) => <span className="line-clamp-2 max-w-[220px] text-xs text-ink-mute">{r.mitigation ?? "—"}</span> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
  ];
  return <DataTable rows={rows} columns={cols} search pageSize={8} onRowClick={onOpen} empty={<EmptyState title="No RAID items" />} />;
}

// ---------------------------------------------------------------- new project
function NewProjectModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id?: string) => void }) {
  const types = useApi<ProjectTypes>("/pmo/project-types", undefined, { enabled: open, staleTime: 10 * 60_000 });
  const [f, setF] = useState({
    name: "",
    project_type: "construction",
    city: "",
    scheme: "",
    client: "",
    start_date: "",
    end_date: "",
    budget: "",
    contract_value: "",
    priority: "medium",
    status: "planning",
    description: "",
    with_template: true,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }));
  const m = useMutate(
    () =>
      ok(
        post<{ project?: { id: string }; id?: string }>("/pmo/projects", {
          ...f,
          city: f.city || null,
          scheme: f.scheme || null,
          client: f.client || null,
          description: f.description || null,
          start_date: f.start_date || null,
          end_date: f.end_date || null,
          budget: Number(f.budget) || 0,
          contract_value: Number(f.contract_value) || 0,
        }),
      ),
    {
      invalidate: ["/pmo"],
      success: "Project created",
      onSuccess: (res) => {
        onClose();
        onCreated(res?.project?.id ?? res?.id);
      },
    },
  );
  const t = types.data;
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="New delivery project"
      subtitle="Phases and a WBS are seeded from the project-type template."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} disabled={!f.name.trim()} onClick={() => m.mutate()} icon={<TrendingUp className="h-4 w-4" />}>
            Create project
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Project name" className="sm:col-span-2">
          <Input value={f.name} onChange={set("name")} placeholder="e.g. Bahria Heights — Tower B" autoFocus />
        </Field>
        <Field label="Project type">
          <Select value={f.project_type} onChange={set("project_type")}>
            {t ? Object.entries(t.types).map(([k, v]) => <option key={k} value={k}>{v.label}</option>) : <option value="construction">Building construction</option>}
          </Select>
        </Field>
        <Field label="Priority">
          <Select value={f.priority} onChange={set("priority")} options={(t?.priorities ?? ["low", "medium", "high", "critical"]).map((x) => ({ value: x, label: titleCase(x) }))} />
        </Field>
        <Field label="City">
          <Input value={f.city} onChange={set("city")} placeholder="Lahore" />
        </Field>
        <Field label="Scheme / society">
          <Input value={f.scheme} onChange={set("scheme")} placeholder="DHA Phase 6" />
        </Field>
        <Field label="Client">
          <Input value={f.client} onChange={set("client")} />
        </Field>
        <Field label="Status">
          <Select value={f.status} onChange={set("status")} options={(t?.statuses ?? ["planning", "active"]).map((x) => ({ value: x, label: titleCase(x) }))} />
        </Field>
        <Field label="Start date">
          <Input type="date" value={f.start_date} onChange={set("start_date")} />
        </Field>
        <Field label="End date">
          <Input type="date" value={f.end_date} onChange={set("end_date")} />
        </Field>
        <Field label="Budget (PKR)" hint={f.budget ? pkrShort(Number(f.budget)) : undefined}>
          <Input type="number" min={0} value={f.budget} onChange={set("budget")} />
        </Field>
        <Field label="Contract value (PKR)" hint={f.contract_value ? pkrShort(Number(f.contract_value)) : undefined}>
          <Input type="number" min={0} value={f.contract_value} onChange={set("contract_value")} />
        </Field>
        <Field label="Description" className="sm:col-span-2">
          <Textarea value={f.description} onChange={set("description")} rows={3} />
        </Field>
        <div className="sm:col-span-2">
          <Toggle checked={f.with_template} onChange={(v) => setF((s) => ({ ...s, with_template: v }))} label="Seed phases & WBS from the type template" />
        </div>
      </div>
    </Modal>
  );
}
