import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  BookOpenCheck,
  Building2,
  Calculator,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  FileText,
  GitCompareArrows,
  HardHat,
  Layers,
  Leaf,
  Package,
  Save,
  Scale,
  ShieldCheck,
  Sparkles,
  Stamp,
  ThumbsDown,
  ThumbsUp,
  Timer,
  Wand2,
} from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { post } from "@/lib/api";
import { date, num, pkr, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Badge,
  Bars,
  BarList,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  Donut,
  EmptyState,
  Field,
  Input,
  Legendish,
  Modal,
  PageHeader,
  PALETTE,
  QueryState,
  Segmented,
  Select,
  Skeleton,
  Slider,
  Tabs,
  Textarea,
  type Column,
} from "@/components/ui";
import { Accordion, GlowPanel, ok, today } from "@/components/collab/kit";

// ---------------------------------------------------------------- types
interface Overview {
  config: { currency_symbol: string; default_city: string; quality_base_rate_sqft: Record<string, number>; city_multipliers: Record<string, number> };
  building_types: Record<string, string>;
  quality_tiers: Record<string, string>;
  cities: string[];
  counts: Record<string, number>;
}
interface Estimate {
  inputs: Record<string, unknown>;
  assumptions: { base_rate_sqft: number; effective_rate_sqft: number; city_factor: number; system_factor: number; floor_factor: number; building_type_factor: number };
  cost: {
    subtotal_construction: number;
    preliminaries: number;
    contingency: number;
    consultancy_and_approvals: number;
    contractor_overhead_profit: number;
    escalation: number;
    total: number;
    cost_per_sqft: number;
    total_text: string;
    cost_per_sqft_text: string;
  };
  elements: { element: string; label: string; category: string; share_pct: number; amount: number }[];
  timeline: Timeline;
  takeoff: { lines: { material: string; name: string; unit: string; quantity_with_wastage: number; unit_rate: number; estimated_cost: number }[] };
  system: { key: string; name: string };
}
interface Timeline {
  total_days: number;
  total_months: number;
  phases: { key: string; name: string; days: number; weight_pct: number; depends_on: string[] }[];
}
interface Technique {
  key: string;
  name: string;
  category: string;
  cost_factor: number;
  speed_floors_per_month: number;
  description: string;
  suitable_for: string[];
  min_floors: number;
  max_floors: number;
  seismic_rating: string;
  sustainability: string;
  warranty_years: number;
  pros: string[];
  cons: string[];
  skill_level: string;
  code_refs?: string[];
}
interface Material {
  key: string;
  name: string;
  category: string;
  unit: string;
  unit_rate: number;
  wastage_pct: number;
  lead_time_days: number;
  availability: string;
  alternatives: string[];
  eco_rating: string;
}
interface Saved {
  id: string;
  title: string;
  building_type: string;
  quality_tier: string;
  system: string;
  city: string;
  covered_area_sqft: number;
  floors: number;
  total_cost: number;
  cost_per_sqft: number;
  duration_days: number;
  created_at: string;
  budget_text: string;
  type_label: string;
  tier_label: string;
}

function useDebounced<T>(v: T, ms = 350): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

type Tab = "estimate" | "techniques" | "materials" | "planning" | "standards";

export default function Construction() {
  const [tab, setTab] = useState<Tab>("estimate");
  const ov = useApi<Overview>("/construction/overview", undefined, { staleTime: 30 * 60_000 });
  const [inp, setInp] = useState({ covered_area: 2250, floors: 2, building_type: "house", quality_tier: "standard", system: "rcc_frame", city: "Lahore", plot_area: 2722, escalation_years: 0 });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Construction"
        subtitle="Estimate, compare techniques, price materials and plan approvals — then hand over to the PMO."
        crumbs={[{ label: "Dashboard", to: "/app" }, { label: "Construction" }]}
      />
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "estimate", label: "Cost estimator", icon: <Calculator className="h-4 w-4" /> },
          { value: "techniques", label: "Techniques", icon: <Layers className="h-4 w-4" />, count: ov.data?.counts.systems },
          { value: "materials", label: "Materials", icon: <Package className="h-4 w-4" />, count: ov.data?.counts.materials },
          { value: "planning", label: "Planning & approvals", icon: <Stamp className="h-4 w-4" /> },
          { value: "standards", label: "QA · HSE · Codes", icon: <ShieldCheck className="h-4 w-4" /> },
        ]}
      />
      <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
        {tab === "estimate" && <Estimator ov={ov.data} inp={inp} setInp={setInp} />}
        {tab === "techniques" && <Techniques inp={inp} />}
        {tab === "materials" && <Materials />}
        {tab === "planning" && <Planning ov={ov.data} inp={inp} />}
        {tab === "standards" && <Standards />}
      </motion.div>
    </div>
  );
}

// ---------------------------------------------------------------- estimator
type Inputs = { covered_area: number; floors: number; building_type: string; quality_tier: string; system: string; city: string; plot_area: number; escalation_years: number };

function Estimator({ ov, inp, setInp }: { ov?: Overview; inp: Inputs; setInp: (f: (s: Inputs) => Inputs) => void }) {
  const nav = useNavigate();
  const deb = useDebounced(inp);
  const systems = useApi<{ techniques: Technique[] }>("/construction/techniques", { category: "structure" }, { staleTime: 30 * 60_000 });
  const est = useQuery<Estimate, Error>({
    queryKey: ["/construction/estimate#post", deb],
    queryFn: () => ok(post<Estimate>("/construction/estimate", { ...deb, plot_area: deb.plot_area || null })),
    placeholderData: keepPreviousData,
  });
  const saved = useApi<{ count: number; estimates: Saved[] }>("/construction/estimates");
  const [saveOpen, setSaveOpen] = useState(false);
  const [pmoFrom, setPmoFrom] = useState<Saved | null>(null);
  const set = <K extends keyof Inputs>(k: K, v: Inputs[K]) => setInp((s) => ({ ...s, [k]: v }));
  const e = est.data;

  const breakdown = e
    ? [
        { name: "Construction", value: e.cost.subtotal_construction },
        { name: "Preliminaries", value: e.cost.preliminaries },
        { name: "Contingency", value: e.cost.contingency },
        { name: "Consultancy & approvals", value: e.cost.consultancy_and_approvals },
        { name: "Overhead & profit", value: e.cost.contractor_overhead_profit },
        ...(e.cost.escalation ? [{ name: "Escalation", value: e.cost.escalation }] : []),
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        {/* inputs */}
        <Card className="xl:sticky xl:top-20 xl:self-start">
          <CardHeader title="Project inputs" subtitle="Results update as you move the sliders" icon={<Wand2 className="h-5 w-5" />} />
          <CardBody className="space-y-5">
            <div>
              <div className="mb-2 flex items-baseline justify-between">
                <span className="label !mb-0">Covered area</span>
                <span className="font-display text-lg font-bold text-brand-700 dark:text-gold-300">{num(inp.covered_area)} sqft</span>
              </div>
              <Slider value={inp.covered_area} min={500} max={60000} step={50} onChange={(v) => set("covered_area", v)} />
              <p className="mt-1 text-[11px] text-ink-mute">≈ {num(inp.covered_area / 272.25, 1)} marla · {num(inp.covered_area / 5445, 2)} kanal</p>
            </div>
            <div>
              <div className="mb-2 flex items-baseline justify-between">
                <span className="label !mb-0">Floors</span>
                <span className="font-display text-lg font-bold text-brand-700 dark:text-gold-300">{inp.floors}</span>
              </div>
              <Slider value={inp.floors} min={1} max={30} onChange={(v) => set("floors", v)} />
            </div>
            <Field label="Quality tier">
              <Segmented
                size="sm"
                value={inp.quality_tier}
                onChange={(v) => set("quality_tier", v)}
                className="flex w-full [&>button]:flex-1"
                options={Object.entries(ov?.quality_tiers ?? { economy: "Economy", standard: "Standard", premium: "Premium", luxury: "Luxury" }).map(([k, v]) => ({ value: k, label: v }))}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Building type">
                <Select value={inp.building_type} onChange={(e) => set("building_type", e.target.value)}>
                  {Object.entries(ov?.building_types ?? { house: "House" }).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="City">
                <Select value={inp.city} onChange={(e) => set("city", e.target.value)} options={ov?.cities ?? ["Lahore"]} />
              </Field>
            </div>
            <Field label="Structural system">
              <Select value={inp.system} onChange={(e) => set("system", e.target.value)}>
                {(systems.data?.techniques ?? [{ key: "rcc_frame", name: "RCC frame" } as Technique]).map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Plot area (sqft)">
                <Input type="number" min={0} value={inp.plot_area || ""} onChange={(e) => set("plot_area", Number(e.target.value) || 0)} />
              </Field>
              <Field label={`Escalation · ${inp.escalation_years} yr`}>
                <div className="pt-3">
                  <Slider value={inp.escalation_years} min={0} max={5} step={0.5} onChange={(v) => set("escalation_years", v)} />
                </div>
              </Field>
            </div>
          </CardBody>
        </Card>

        {/* results */}
        <div className="min-w-0 space-y-6">
          {est.error && !e ? (
            <QueryState q={est}>{() => null}</QueryState>
          ) : !e ? (
            <Skeleton className="h-48" />
          ) : (
            <>
              <GlowPanel>
                <div className="flex flex-wrap items-end justify-between gap-6">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[.2em] text-gold-300">Estimated total</p>
                    <motion.p key={e.cost.total} initial={{ opacity: 0.4, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-1 font-display text-4xl font-bold sm:text-5xl">
                      {pkrShort(e.cost.total)}
                    </motion.p>
                    <p className="mt-1 text-sm text-white/75">
                      {pkr(e.cost.total)} · {e.cost.cost_per_sqft_text}
                    </p>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="rounded-2xl bg-white/10 px-3 py-2 backdrop-blur">
                      <p className="text-[10px] uppercase text-white/60">Duration</p>
                      <p className="font-display text-lg font-bold">{num(e.timeline.total_months, 1)} mo</p>
                    </div>
                    <div className="rounded-2xl bg-white/10 px-3 py-2 backdrop-blur">
                      <p className="text-[10px] uppercase text-white/60">Rate</p>
                      <p className="font-display text-lg font-bold">{num(e.assumptions.effective_rate_sqft)}</p>
                    </div>
                    <div className="rounded-2xl bg-white/10 px-3 py-2 backdrop-blur">
                      <p className="text-[10px] uppercase text-white/60">City ×</p>
                      <p className="font-display text-lg font-bold">{num(e.assumptions.city_factor, 2)}</p>
                    </div>
                  </div>
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  <Button variant="gold" icon={<Save className="h-4 w-4" />} onClick={() => setSaveOpen(true)}>
                    Save estimate
                  </Button>
                  <span className="inline-flex items-center gap-1.5 text-xs text-white/70">
                    <Sparkles className="h-3.5 w-3.5" /> {e.system.name} · {titleCase(String(e.inputs.building_type ?? ""))} · {titleCase(String(e.inputs.quality_tier ?? ""))}
                    {est.isFetching && " · updating…"}
                  </span>
                </div>
              </GlowPanel>

              <div className="grid gap-6 lg:grid-cols-2">
                <Card>
                  <CardHeader title="Cost breakdown" icon={<Scale className="h-5 w-5" />} />
                  <CardBody>
                    <Donut data={breakdown} height={220} format={(v) => pkrShort(v)} center={<span className="text-xs font-semibold text-ink-mute">{e.cost.total_text}</span>} />
                    <ul className="mt-4 space-y-1.5">
                      {breakdown.map((b, i) => (
                        <li key={b.name} className="flex items-center gap-2 text-sm">
                          <span className="h-2.5 w-2.5 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                          <span className="flex-1 text-ink-soft dark:text-slate-300">{b.name}</span>
                          <span className="font-semibold tabular-nums">{pkrShort(b.value)}</span>
                        </li>
                      ))}
                    </ul>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="By building element" icon={<Building2 className="h-5 w-5" />} />
                  <CardBody>
                    <BarList items={e.elements.map((el) => ({ label: el.label, value: el.amount }))} format={(v) => pkrShort(v, false)} />
                  </CardBody>
                </Card>
              </div>

              <Card>
                <CardHeader title="Phase durations" subtitle={`${e.timeline.total_days} days end-to-end`} icon={<Timer className="h-5 w-5" />} />
                <CardBody>
                  <Bars data={e.timeline.phases.map((p) => ({ name: p.name.split(/[(&]/)[0]!.trim(), days: p.days }))} x="name" horizontal height={Math.max(260, e.timeline.phases.length * 30)} format={(v) => `${v} d`} series={[{ key: "days", label: "Days", color: "#146f45" }]} />
                </CardBody>
              </Card>

              <Card className="overflow-hidden">
                <CardHeader title="Material take-off" subtitle="Quantities include wastage" icon={<Package className="h-5 w-5" />} />
                <DataTable
                  rows={e.takeoff.lines}
                  rowKey={(r) => r.material}
                  dense
                  pageSize={8}
                  columns={[
                    { key: "name", header: "Material" },
                    { key: "quantity_with_wastage", header: "Qty", align: "right", render: (r) => `${num(r.quantity_with_wastage, 1)} ${r.unit}` },
                    { key: "unit_rate", header: "Rate", align: "right", render: (r) => num(r.unit_rate) },
                    { key: "estimated_cost", header: "Cost", align: "right", render: (r) => <b>{pkrShort(r.estimated_cost, false)}</b> },
                  ]}
                />
              </Card>
            </>
          )}
        </div>
      </div>

      {/* saved */}
      <Card>
        <CardHeader title="Saved estimates" subtitle="Convert any estimate into a tracked PMO project" icon={<FileText className="h-5 w-5" />} />
        <CardBody>
          <QueryState q={saved} skeleton={<Skeleton className="h-40" />}>
            {(d) =>
              d.estimates.length === 0 ? (
                <EmptyState title="No saved estimates yet" />
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {d.estimates.map((s) => (
                    <div key={s.id} className="group rounded-2xl border border-black/5 p-4 transition hover:border-gold-300 hover:shadow-glow dark:border-white/10">
                      <div className="flex items-start justify-between gap-2">
                        <p className="font-display font-semibold">{s.title}</p>
                        <Badge tone="gold">{s.tier_label}</Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-ink-mute">
                        {s.type_label} · {s.city} · {titleCase(s.system)}
                      </p>
                      <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                        <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                          <p className="text-ink-mute">Total</p>
                          <p className="font-bold">{pkrShort(s.total_cost, false)}</p>
                        </div>
                        <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                          <p className="text-ink-mute">Area</p>
                          <p className="font-bold">{num(s.covered_area_sqft)} sqft</p>
                        </div>
                        <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                          <p className="text-ink-mute">Duration</p>
                          <p className="font-bold">{s.duration_days} d</p>
                        </div>
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-2">
                        <span className="text-[11px] text-ink-mute">{date(s.created_at)}</span>
                        <Button size="sm" variant="soft" icon={<HardHat className="h-3.5 w-3.5" />} onClick={() => setPmoFrom(s)}>
                          Create PMO project
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )
            }
          </QueryState>
        </CardBody>
      </Card>

      {saveOpen && <SaveModal inp={inp} onClose={() => setSaveOpen(false)} />}
      {pmoFrom && <PmoFromEstimate est={pmoFrom} onClose={() => setPmoFrom(null)} onCreated={(id) => nav(`/app/pmo/${id}`)} />}
    </div>
  );
}

function SaveModal({ inp, onClose }: { inp: Inputs; onClose: () => void }) {
  const [title, setTitle] = useState(`${num(inp.covered_area)} sqft ${titleCase(inp.building_type)} — ${inp.city}`);
  const [notes, setNotes] = useState("");
  const m = useMutate(() => ok(post("/construction/estimates", { ...inp, plot_area: inp.plot_area || null, title, notes: notes || null })), {
    invalidate: ["/construction/estimates"],
    success: "Estimate saved",
    onSuccess: onClose,
  });
  return (
    <Modal
      open
      onClose={onClose}
      title="Save estimate"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} disabled={!title.trim()} onClick={() => m.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Title">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
        </Field>
        <Field label="Notes">
          <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

function PmoFromEstimate({ est, onClose, onCreated }: { est: Saved; onClose: () => void; onCreated: (id: string) => void }) {
  const [f, setF] = useState({ name: est.title, city: est.city, start_date: today(), contract_value: "" });
  const m = useMutate(
    () =>
      ok(
        post<{ project: { id: string } }>(`/pmo/from-estimate/${est.id}`, undefined, {
          name: f.name || undefined,
          city: f.city || undefined,
          start_date: f.start_date || undefined,
          contract_value: f.contract_value ? Number(f.contract_value) : undefined,
        }),
      ),
    {
      invalidate: ["/pmo"],
      success: "PMO project created",
      onSuccess: (r) => {
        onClose();
        if (r?.project?.id) onCreated(r.project.id);
      },
    },
  );
  return (
    <Modal
      open
      onClose={onClose}
      title="Create PMO project"
      subtitle={`From “${est.title}” · ${est.budget_text}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} onClick={() => m.mutate()} icon={<HardHat className="h-4 w-4" />}>
            Create project
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Project name" className="sm:col-span-2">
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
        <Field label="City">
          <Input value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} />
        </Field>
        <Field label="Start date">
          <Input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
        </Field>
        <Field label="Contract value (PKR)" className="sm:col-span-2" hint={f.contract_value ? pkrShort(Number(f.contract_value)) : "Optional — defaults from the estimate"}>
          <Input type="number" min={0} value={f.contract_value} onChange={(e) => setF({ ...f, contract_value: e.target.value })} />
        </Field>
      </div>
      <p className="mt-4 text-xs text-ink-mute">Phases, budget and the schedule are seeded from the estimate’s timeline.</p>
    </Modal>
  );
}

// ---------------------------------------------------------------- techniques
const RATING_TONE: Record<string, "green" | "gold" | "red" | "blue"> = { "very good": "green", good: "green", excellent: "green", moderate: "gold", low: "red", high: "green" };

function Techniques({ inp }: { inp: Inputs }) {
  const [cat, setCat] = useState("");
  const q = useApi<{ techniques: Technique[]; categories: string[] }>("/construction/techniques", { category: cat }, { staleTime: 30 * 60_000 });
  const [compareCat, setCompareCat] = useState("structure");
  const cmp = useApi<{ cheapest: string; fastest: string; options: { system: string; name: string; total: number; cost_per_sqft: number; duration_days: number; seismic_rating: string; vs_cheapest_pct: number; ecg?: string }[] }>("/construction/compare", {
    covered_area: inp.covered_area,
    floors: inp.floors,
    building_type: inp.building_type,
    quality_tier: inp.quality_tier,
    city: inp.city,
    category: compareCat,
  });
  return (
    <div className="space-y-6">
      <Card className="overflow-hidden">
        <CardHeader
          title="Compare systems for your project"
          subtitle={`${num(inp.covered_area)} sqft · ${inp.floors} floor(s) · ${titleCase(inp.quality_tier)} · ${inp.city}`}
          icon={<GitCompareArrows className="h-5 w-5" />}
          action={
            <Select value={compareCat} onChange={(e) => setCompareCat(e.target.value)} className="w-auto py-2 text-xs">
              {(q.data?.categories ?? ["structure"]).map((c) => (
                <option key={c} value={c}>
                  {titleCase(c)}
                </option>
              ))}
            </Select>
          }
        />
        <QueryState q={cmp} skeleton={<Skeleton className="m-5 h-48" />}>
          {(d) =>
            d.options?.length ? (
              <div className="grid gap-6 p-5 lg:grid-cols-2">
                <Bars
                  data={d.options.map((o) => ({ name: o.name.split(/[(/]/)[0]!.trim(), total: o.total }))}
                  x="name"
                  horizontal
                  height={Math.max(220, d.options.length * 36)}
                  format={(v) => pkrShort(v, false)}
                  series={[{ key: "total", label: "Total cost", color: "#146f45" }]}
                />
                <div className="space-y-2">
                  {d.options.map((o) => (
                    <div key={o.system} className={cn("flex items-center gap-3 rounded-xl border px-3 py-2", o.system === d.cheapest || o.system === d.fastest ? "border-gold-300 bg-gold-50/50 dark:border-gold-500/30 dark:bg-gold-500/5" : "border-black/5 dark:border-white/10")}>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">{o.name}</p>
                        <p className="text-[11px] text-ink-mute">
                          {pkrShort(o.total)} · {num(o.cost_per_sqft)}/sqft · {o.duration_days} d
                        </p>
                      </div>
                      {o.system === d.cheapest && <Badge tone="green">Cheapest</Badge>}
                      {o.system === d.fastest && <Badge tone="gold">Fastest</Badge>}
                      {o.vs_cheapest_pct > 0 && <span className="text-[11px] font-semibold text-ink-mute">+{num(o.vs_cheapest_pct, 1)}%</span>}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="p-5">
                <EmptyState title="No comparable systems for this category" />
              </div>
            )
          }
        </QueryState>
      </Card>

      <div className="no-scrollbar flex gap-1.5 overflow-x-auto">
        {["", ...(q.data?.categories ?? [])].map((c) => (
          <button key={c || "all"} onClick={() => setCat(c)} className={cn("shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold transition", cat === c ? "bg-brand-700 text-white" : "bg-black/5 hover:bg-brand-50 dark:bg-white/5")}>
            {c ? titleCase(c) : "All"}
          </button>
        ))}
      </div>
      <QueryState q={q} skeleton={<Skeleton className="h-72" />}>
        {(d) => (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {d.techniques.map((t, i) => (
              <motion.div key={t.key} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="card flex flex-col p-5 transition hover:-translate-y-1 hover:shadow-glow">
                <div className="flex items-start justify-between gap-2">
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-soft">
                    {t.category === "green" ? <Leaf className="h-5 w-5" /> : <Layers className="h-5 w-5" />}
                  </span>
                  <Badge tone="gray">{titleCase(t.category)}</Badge>
                </div>
                <h3 className="mt-3 font-display text-base font-semibold">{t.name}</h3>
                <p className="mt-1 line-clamp-3 text-sm text-ink-mute">{t.description}</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                    <p className="text-ink-mute">Cost ×</p>
                    <p className="font-bold">{num(t.cost_factor, 2)}</p>
                  </div>
                  <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                    <p className="text-ink-mute">Floors/mo</p>
                    <p className="font-bold">{num(t.speed_floors_per_month, 1)}</p>
                  </div>
                  <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                    <p className="text-ink-mute">Warranty</p>
                    <p className="font-bold">{t.warranty_years}y</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge tone={RATING_TONE[t.seismic_rating] ?? "gray"}>Seismic: {t.seismic_rating}</Badge>
                  <Badge tone={RATING_TONE[t.sustainability] ?? "gray"}>Eco: {t.sustainability}</Badge>
                  <Badge tone="blue">{t.min_floors}–{t.max_floors} floors</Badge>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                  <ul className="space-y-1">
                    {t.pros.slice(0, 3).map((p) => (
                      <li key={p} className="flex gap-1.5">
                        <ThumbsUp className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" />
                        {p}
                      </li>
                    ))}
                  </ul>
                  <ul className="space-y-1">
                    {t.cons.slice(0, 3).map((p) => (
                      <li key={p} className="flex gap-1.5 text-ink-mute">
                        <ThumbsDown className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </QueryState>
    </div>
  );
}

// ---------------------------------------------------------------- materials
function Materials() {
  const [cat, setCat] = useState("");
  const q = useApi<{ materials: Material[]; categories: string[] }>("/construction/materials", { category: cat }, { staleTime: 10 * 60_000 });
  const cols: Column<Material>[] = [
    {
      key: "name",
      header: "Material",
      render: (m) => (
        <div className="min-w-[180px]">
          <p className="font-semibold">{m.name}</p>
          <p className="text-[11px] text-ink-mute">Alt: {m.alternatives.join(", ") || "—"}</p>
        </div>
      ),
    },
    { key: "category", header: "Category", render: (m) => <Badge tone="gray">{titleCase(m.category)}</Badge> },
    { key: "unit_rate", header: "Rate (PKR)", align: "right", render: (m) => <b>{num(m.unit_rate)}</b> },
    { key: "unit", header: "Unit" },
    { key: "wastage_pct", header: "Wastage", align: "right", render: (m) => `${m.wastage_pct}%` },
    { key: "lead_time_days", header: "Lead time", align: "right", render: (m) => `${m.lead_time_days} d` },
    { key: "availability", header: "Availability", render: (m) => <span className="text-xs">{titleCase(m.availability)}</span> },
    { key: "eco_rating", header: "Eco", render: (m) => <Badge tone={RATING_TONE[m.eco_rating] ?? "gray"}>{m.eco_rating}</Badge> },
  ];
  return (
    <Card className="overflow-hidden">
      <CardHeader title="Materials price list" subtitle="Indicative market rates" icon={<Package className="h-5 w-5" />} />
      <QueryState q={q} skeleton={<Skeleton className="m-5 h-72" />}>
        {(d) => (
          <DataTable
            rows={d.materials}
            rowKey={(m) => m.key}
            columns={cols}
            search
            pageSize={15}
            toolbar={
              <Select value={cat} onChange={(e) => setCat(e.target.value)} className="w-auto py-2 text-xs">
                <option value="">All categories</option>
                {(d.categories ?? []).map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </Select>
            }
          />
        )}
      </QueryState>
    </Card>
  );
}

// ---------------------------------------------------------------- planning
const SOILS: Record<string, string> = { rock: "Rock / gravel", sandy_loam: "Sandy loam", sandy: "Loose sand", clay: "Stiff clay", silt: "Silt / soft", reclaimed: "Filled / reclaimed" };
const ZONES: Record<string, string> = { "1": "Zone 1 (low)", "2A": "Zone 2A (moderate)", "2B": "Zone 2B (moderate–high)", "3": "Zone 3 (high)", "4": "Zone 4 (very high)" };

function Planning({ ov, inp }: { ov?: Overview; inp: Inputs }) {
  const [soil, setSoil] = useState("sandy_loam");
  const [zone, setZone] = useState("2A");
  const [city, setCity] = useState(inp.city);
  const tl = useApi<Timeline>("/construction/timeline", { covered_area: inp.covered_area, floors: inp.floors, building_type: inp.building_type, system: inp.system });
  const adv = useApi<{
    soil: { label: string; bearing_capacity_kpa: number; foundation: string };
    seismic_zone: { label: string; factor: number; requirement: string };
    recommended_system: string;
    suitable_systems: { key: string; name: string; cost_factor: number; seismic_rating: string }[];
    foundation_recommendation: string;
    guidelines: { key: string; title: string; authority: string }[];
    safety: { key: string; rule: string }[];
  }>("/construction/advisory", { plot_area: inp.plot_area || inp.covered_area, floors: inp.floors, building_type: inp.building_type, city, soil, seismic_zone: zone });
  const appr = useApi<{ authority: string; steps: { step: number; name: string; authority: string; documents: string[]; duration_days: number; fee_note: string }[]; total_approval_days: number; note: string }>("/construction/approvals", {
    project_type: inp.building_type,
    city,
  });
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Construction timeline" subtitle={tl.data ? `${tl.data.total_days} days · ≈ ${num(tl.data.total_months, 1)} months` : undefined} icon={<Clock className="h-5 w-5" />} />
          <CardBody>
            <QueryState q={tl} skeleton={<Skeleton className="h-72" />}>
              {(t) => {
                const total = t.phases.reduce((a, p) => a + p.days, 0) || 1;
                let cum = 0;
                return (
                  <div className="space-y-2">
                    {t.phases.map((p, i) => {
                      const start = cum;
                      cum += p.days;
                      return (
                        <div key={p.key} className="grid grid-cols-[minmax(0,150px)_1fr_auto] items-center gap-3 text-xs">
                          <span className="truncate font-medium" title={p.name}>
                            {p.name}
                          </span>
                          <div className="relative h-5 rounded-md bg-black/5 dark:bg-white/5">
                            <motion.div
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              transition={{ delay: i * 0.05 }}
                              className="absolute inset-y-0 rounded-md bg-gradient-to-r from-brand-700 to-brand-500"
                              style={{ insetInlineStart: `${(start / total) * 100}%`, width: `${Math.max(1.5, (p.days / total) * 100)}%` }}
                            />
                          </div>
                          <span className="w-12 text-end font-semibold tabular-nums">{p.days} d</span>
                        </div>
                      );
                    })}
                  </div>
                );
              }}
            </QueryState>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Site advisory" subtitle="Soil, seismic zone and the right system" icon={<BookOpenCheck className="h-5 w-5" />} />
          <CardBody className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <Field label="City">
                <Select value={city} onChange={(e) => setCity(e.target.value)} options={ov?.cities ?? [city]} />
              </Field>
              <Field label="Soil">
                <Select value={soil} onChange={(e) => setSoil(e.target.value)} options={Object.entries(SOILS).map(([value, label]) => ({ value, label }))} />
              </Field>
              <Field label="Seismic">
                <Select value={zone} onChange={(e) => setZone(e.target.value)} options={Object.entries(ZONES).map(([value, label]) => ({ value, label }))} />
              </Field>
            </div>
            <QueryState q={adv} skeleton={<Skeleton className="h-48" />}>
              {(a) => (
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl bg-brand-50/60 p-3 dark:bg-white/5">
                      <p className="text-[11px] font-bold uppercase text-ink-mute">{a.soil.label}</p>
                      <p className="mt-0.5 text-sm font-semibold">{a.soil.bearing_capacity_kpa} kPa bearing</p>
                      <p className="text-xs text-ink-mute">{a.foundation_recommendation}</p>
                    </div>
                    <div className="rounded-2xl bg-gold-50/70 p-3 dark:bg-gold-500/10">
                      <p className="text-[11px] font-bold uppercase text-gold-700 dark:text-gold-300">{a.seismic_zone.label}</p>
                      <p className="mt-0.5 text-sm font-semibold">Factor {a.seismic_zone.factor}</p>
                      <p className="text-xs text-ink-mute">{a.seismic_zone.requirement}</p>
                    </div>
                  </div>
                  <p className="label">Suitable systems</p>
                  <div className="flex flex-wrap gap-2">
                    {a.suitable_systems.map((s) => (
                      <Badge key={s.key} tone={s.key === a.recommended_system ? "gold" : "gray"} icon={s.key === a.recommended_system ? <Sparkles className="h-3 w-3" /> : undefined}>
                        {s.name} · ×{s.cost_factor}
                      </Badge>
                    ))}
                  </div>
                  <p className="label">Applicable guidelines</p>
                  <ul className="grid gap-1.5 sm:grid-cols-2">
                    {a.guidelines.map((g) => (
                      <li key={g.key} className="flex gap-1.5 text-xs">
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-600" />
                        <span>
                          {g.title} <span className="text-ink-mute">· {g.authority}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </QueryState>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Approvals & NOC"
          subtitle={appr.data ? `${appr.data.authority} · ≈ ${appr.data.total_approval_days} days` : undefined}
          icon={<Stamp className="h-5 w-5" />}
        />
        <CardBody>
          <QueryState q={appr} skeleton={<Skeleton className="h-48" />}>
            {(a) => (
              <>
                <ol className="relative grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {a.steps.map((s, i) => (
                    <motion.li key={s.step} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="relative rounded-2xl border border-black/5 p-4 dark:border-white/10">
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gold-gradient font-display font-bold text-brand-950 shadow-glow">{i + 1}</span>
                        <div className="min-w-0">
                          <p className="font-semibold leading-tight">{s.name}</p>
                          <p className="text-[11px] text-ink-mute">{s.authority}</p>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {s.documents.map((d) => (
                          <Badge key={d} tone="gray">
                            {d}
                          </Badge>
                        ))}
                      </div>
                      <div className="mt-3 flex items-center justify-between text-xs">
                        <span className="inline-flex items-center gap-1 font-semibold text-brand-700 dark:text-brand-200">
                          <Clock className="h-3.5 w-3.5" /> {s.duration_days} days
                        </span>
                        <span className="text-ink-mute">{s.fee_note}</span>
                      </div>
                    </motion.li>
                  ))}
                </ol>
                <p className="mt-4 text-xs text-ink-mute">{a.note}</p>
              </>
            )}
          </QueryState>
        </CardBody>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- standards
function Standards() {
  const qa = useApi<{ stages: Record<string, string[]> }>("/construction/qa", undefined, { staleTime: 30 * 60_000 });
  const hse = useApi<{ rules: { key: string; rule: string }[] }>("/construction/hse", undefined, { staleTime: 30 * 60_000 });
  const gl = useApi<{ guidelines: { key: string; title: string; category: string; authority: string; code: string; summary: string; rules: string[]; penalty?: string }[] }>("/construction/guidelines", undefined, { staleTime: 30 * 60_000 });
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader title="Quality assurance checklists" subtitle="Stage-by-stage QA" icon={<ClipboardCheck className="h-5 w-5" />} />
          <CardBody>
            <QueryState q={qa} skeleton={<Skeleton className="h-60" />}>
              {(d) => (
                <Accordion
                  items={Object.entries(d.stages).map(([stage, checks]) => ({
                    title: titleCase(stage),
                    icon: <ClipboardCheck className="h-4 w-4" />,
                    meta: <Badge tone="gray">{checks.length}</Badge>,
                    content: (
                      <ul className="space-y-1.5">
                        {checks.map((c) => (
                          <li key={c} className="flex gap-2">
                            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                            {c}
                          </li>
                        ))}
                      </ul>
                    ),
                  }))}
                />
              )}
            </QueryState>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Health, safety & environment" icon={<HardHat className="h-5 w-5" />} />
          <CardBody>
            <QueryState q={hse} skeleton={<Skeleton className="h-48" />}>
              {(d) => (
                <ul className="grid gap-2 sm:grid-cols-2">
                  {d.rules.map((r) => (
                    <li key={r.key} className="flex gap-2 rounded-xl bg-amber-50/70 p-3 text-sm dark:bg-amber-500/10">
                      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                      <span>
                        <b className="block text-xs uppercase tracking-wide text-amber-700 dark:text-amber-300">{titleCase(r.key)}</b>
                        {r.rule}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </QueryState>
          </CardBody>
        </Card>
      </div>
      <Card>
        <CardHeader title="Building codes & guidelines" icon={<BookOpenCheck className="h-5 w-5" />} />
        <CardBody>
          <QueryState q={gl} skeleton={<Skeleton className="h-96" />}>
            {(d) => (
              <>
                <div className="mb-4">
                  <Legendish data={Object.entries(d.guidelines.reduce<Record<string, number>>((a, g) => ((a[titleCase(g.category)] = (a[titleCase(g.category)] ?? 0) + 1), a), {})).map(([name, value]) => ({ name, value }))} />
                </div>
                <Accordion
                  items={d.guidelines.map((g) => ({
                    title: g.title,
                    icon: <BookOpenCheck className="h-4 w-4" />,
                    meta: <Badge tone="gray" className="hidden sm:inline-flex">{titleCase(g.category)}</Badge>,
                    content: (
                      <div className="space-y-2">
                        <p>{g.summary}</p>
                        <p className="text-xs text-ink-mute">
                          {g.authority} · {g.code}
                        </p>
                        <ul className="space-y-1">
                          {g.rules.map((r) => (
                            <li key={r} className="flex gap-2">
                              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                              {r}
                            </li>
                          ))}
                        </ul>
                        {g.penalty && <p className="rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-700 dark:bg-red-500/10 dark:text-red-300">Penalty: {g.penalty}</p>}
                      </div>
                    ),
                  }))}
                />
              </>
            )}
          </QueryState>
        </CardBody>
      </Card>
    </div>
  );
}
