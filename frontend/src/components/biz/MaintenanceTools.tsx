/** Maintenance-wing calculators (condition, estimate, lifecycle, repair-or-replace, schedule, defects). */
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarDays, CheckCircle2, Hammer, RefreshCcw, Search, ShieldAlert, Wrench } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { num, pkr, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, EmptyState, Field, Input, QueryState, Select, Skeleton, Slider } from "@/components/ui";
import { Bars, Donut, Legendish } from "@/components/ui/charts";
import { MiniStat, Panel, bandTone, crShort, numOr, useDebounced } from "./ops-kit";

export const PROPERTY_TYPES = ["house", "apartment", "building", "floor", "office", "shop", "space", "warehouse", "shed"];
export const CITIES = ["Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta"];
const QUALITIES = ["basic", "standard", "premium"];
const TIERS = [
  { value: "basic", label: "Basic (on-call)" },
  { value: "standard", label: "Standard AMC" },
  { value: "comprehensive", label: "Comprehensive AMC" },
];
const BAND_COLOR: Record<string, string> = {
  excellent: "from-brand-500 to-brand-700",
  good: "from-brand-400 to-brand-600",
  fair: "from-gold-400 to-gold-600",
  poor: "from-orange-400 to-orange-600",
  critical: "from-red-500 to-red-700",
};

export interface Component {
  key: string;
  name: string;
  category: string;
  service_life_years: number;
  criticality: string;
  frequency: string;
  tasks: string[];
}
export interface Defect {
  key: string;
  name: string;
  category: string;
  severity: string;
  urgency: string;
  symptoms: string[];
  causes: string[];
  affected_components: string[];
  diagnosis: string;
  repair: string;
  unit: string;
  cost_low: number;
  cost_high: number;
  prevention: string;
}

function TwoCol({ form, result }: { form: React.ReactNode; result: React.ReactNode }) {
  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <div className="lg:col-span-2">{form}</div>
      <div className="min-w-0 lg:col-span-3">{result}</div>
    </div>
  );
}

// ------------------------------------------------------------------ condition
const RATING_KEYS = ["structural", "envelope", "mep", "finishes", "safety"] as const;

export function ConditionScorer() {
  const [age, setAge] = useState("12");
  const [ptype, setPtype] = useState("house");
  const [ratings, setRatings] = useState<Record<string, number>>({ structural: 4, envelope: 3, mep: 3, finishes: 4, safety: 4 });
  const params = useDebounced({ age_years: age, property_type: ptype, ratings: JSON.stringify(ratings) });
  const q = useApi<{
    score: number;
    band: string;
    band_label: string;
    recommended_action: string;
    actions: { component: string; defect: string; urgency: string; repair: string }[];
    scale: { rating: number; label: string; band: string; action: string }[];
  }>(numOr(params.age_years) !== undefined ? "/maintenance/condition" : null, params);

  return (
    <TwoCol
      form={
        <Panel title="Condition survey" subtitle="Rate each element 1 (critical) – 5 (excellent)" icon={<ShieldAlert className="h-4 w-4" />}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Building age (yrs)">
                <Input type="number" min={0} value={age} onChange={(e) => setAge(e.target.value)} />
              </Field>
              <Field label="Property type">
                <Select value={ptype} onChange={(e) => setPtype(e.target.value)} options={PROPERTY_TYPES.map((p) => ({ value: p, label: titleCase(p) }))} />
              </Field>
            </div>
            {RATING_KEYS.map((k) => (
              <div key={k}>
                <div className="mb-1.5 flex justify-between text-xs font-semibold">
                  <span>{k === "mep" ? "MEP (mechanical, electrical, plumbing)" : titleCase(k)}</span>
                  <span className={cn("tabular-nums", ratings[k] <= 2 ? "text-red-600" : ratings[k] === 3 ? "text-gold-700" : "text-brand-700")}>{ratings[k]} / 5</span>
                </div>
                <Slider value={ratings[k]} min={1} max={5} onChange={(v) => setRatings((r) => ({ ...r, [k]: v }))} />
              </div>
            ))}
          </div>
        </Panel>
      }
      result={
        <QueryState q={q} skeleton={<Skeleton className="h-96" />}>
          {(c) => (
            <div className="space-y-4">
              <div className={cn("flex flex-wrap items-center gap-5 rounded-2xl bg-gradient-to-br p-5 text-white", BAND_COLOR[c.band] ?? "from-slate-500 to-slate-700")}>
                <div className="flex h-24 w-24 flex-col items-center justify-center rounded-full bg-white/15 ring-4 ring-white/20">
                  <span className="font-display text-3xl font-bold">{c.score.toFixed(1)}</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-white/75">of 5</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold uppercase tracking-wider text-white/75">Condition</p>
                  <p className="font-display text-2xl font-bold">{c.band_label}</p>
                  <p className="mt-1 text-sm text-white/85">{c.recommended_action}</p>
                </div>
              </div>
              <div className="flex gap-1">
                {[...c.scale]
                  .sort((a, b) => a.rating - b.rating)
                  .map((s) => (
                    <div key={s.band} className={cn("flex-1 rounded-lg px-2 py-1.5 text-center text-[11px] font-semibold transition-all", s.band === c.band ? "bg-brand-700 text-white shadow-soft" : "bg-black/5 text-ink-mute dark:bg-white/5")}>
                      {titleCase(s.band)}
                    </div>
                  ))}
              </div>
              <Panel title="Recommended works" subtitle={`${c.actions.length} actions from the weakest elements`} icon={<Hammer className="h-4 w-4" />} flush>
                {c.actions.length ? (
                  <ul className="divide-y divide-black/5 dark:divide-white/5">
                    {c.actions.map((a, i) => (
                      <li key={i} className="flex items-start gap-3 px-5 py-3">
                        <Badge tone={bandTone(a.urgency)} className="mt-0.5 shrink-0 capitalize">
                          {a.urgency}
                        </Badge>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold">
                            {titleCase(a.defect)} <span className="font-normal text-ink-mute">· {titleCase(a.component)}</span>
                          </p>
                          <p className="text-xs text-ink-mute">{a.repair}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="p-5">
                    <EmptyState title="Nothing urgent" hint="Keep up routine preventive maintenance." icon={<CheckCircle2 className="h-6 w-6" />} />
                  </div>
                )}
              </Panel>
            </div>
          )}
        </QueryState>
      }
    />
  );
}

// ------------------------------------------------------------------ shared building inputs
function useBuildingInputs(initial?: Partial<{ covered_area: string; property_type: string; quality: string; age_years: string; city: string }>) {
  const [b, setB] = useState({ covered_area: "2500", property_type: "house", quality: "standard", age_years: "10", city: "Lahore", ...initial });
  const set = (k: keyof typeof b) => (v: string) => setB((s) => ({ ...s, [k]: v }));
  const fields = (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Covered area (sqft)">
        <Input type="number" min={100} value={b.covered_area} onChange={(e) => set("covered_area")(e.target.value)} />
      </Field>
      <Field label="Age (yrs)">
        <Input type="number" min={0} value={b.age_years} onChange={(e) => set("age_years")(e.target.value)} />
      </Field>
      <Field label="Property type">
        <Select value={b.property_type} onChange={(e) => set("property_type")(e.target.value)} options={PROPERTY_TYPES.map((p) => ({ value: p, label: titleCase(p) }))} />
      </Field>
      <Field label="Quality">
        <Select value={b.quality} onChange={(e) => set("quality")(e.target.value)} options={QUALITIES.map((p) => ({ value: p, label: titleCase(p) }))} />
      </Field>
      <Field label="City" className="col-span-2">
        <Select value={b.city} onChange={(e) => set("city")(e.target.value)} options={CITIES} />
      </Field>
    </div>
  );
  return { b, fields };
}

// ------------------------------------------------------------------ estimate
export function AnnualEstimate() {
  const { b, fields } = useBuildingInputs();
  const [tier, setTier] = useState("standard");
  const [floors, setFloors] = useState("1");
  const params = useDebounced({ ...b, tier, floors });
  const q = useApi<{
    annual: { total: number; per_sqft_year: number; monthly: number };
    assumptions: { base_rate_sqft_year: number; city_factor: number; tier_multiplier: number; age_factor: number; effective_rate_sqft_year: number };
    category_breakdown: { category: string; share_pct: number; annual_cost: number }[];
    reserve: { build_value: number; annual_reserve: number; monthly_reserve: number; components: { component: string; name: string; service_life_years: number; replacement_cost: number; annual_reserve: number }[] };
  }>(numOr(params.covered_area) ? "/maintenance/estimate" : null, params);

  return (
    <TwoCol
      form={
        <Panel title="Building profile" subtitle="Annual maintenance budget & sinking fund" icon={<Wrench className="h-4 w-4" />}>
          <div className="space-y-3">
            {fields}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Service tier">
                <Select value={tier} onChange={(e) => setTier(e.target.value)} options={TIERS} />
              </Field>
              <Field label="Floors">
                <Input type="number" min={1} value={floors} onChange={(e) => setFloors(e.target.value)} />
              </Field>
            </div>
          </div>
        </Panel>
      }
      result={
        <QueryState q={q} skeleton={<Skeleton className="h-96" />}>
          {(e) => {
            const donut = e.category_breakdown.map((c) => ({ name: titleCase(c.category), value: c.annual_cost }));
            return (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <MiniStat label="Annual upkeep" value={pkrShort(e.annual.total, false)} tone="green" />
                  <MiniStat label="Monthly" value={pkrShort(e.annual.monthly, false)} />
                  <MiniStat label="Per sqft / yr" value={`Rs ${e.annual.per_sqft_year.toFixed(1)}`} />
                  <MiniStat label="Reserve / yr" value={pkrShort(e.reserve.annual_reserve, false)} tone="gold" hint={`${pkrShort(e.reserve.monthly_reserve, false)} / month`} />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <Panel title="Where the money goes" icon={<Wrench className="h-4 w-4" />}>
                    <Donut data={donut} height={200} format={(v) => pkrShort(v, false)} center={<span className="font-display text-lg font-bold">{pkrShort(e.annual.total, false)}</span>} />
                    <div className="mt-3">
                      <Legendish data={donut.map((d) => ({ ...d, value: Math.round((d.value / Math.max(1, e.annual.total)) * 100) }))} />
                    </div>
                  </Panel>
                  <Panel title="Assumptions" icon={<Search className="h-4 w-4" />}>
                    <dl className="space-y-2 text-sm">
                      {Object.entries(e.assumptions).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-2 border-b border-black/5 pb-1.5 last:border-0 dark:border-white/5">
                          <dt className="text-ink-mute">{titleCase(k)}</dt>
                          <dd className="font-semibold tabular-nums">{typeof v === "number" ? num(v, 2) : String(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  </Panel>
                </div>
                <Panel title="Sinking-fund components" subtitle={`Build value ${pkrShort(e.reserve.build_value)}`} icon={<RefreshCcw className="h-4 w-4" />} flush>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-brand-50/50 text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:bg-white/5">
                          <th className="px-4 py-2 text-start">Component</th>
                          <th className="px-4 py-2 text-end">Life</th>
                          <th className="px-4 py-2 text-end">Replacement</th>
                          <th className="px-4 py-2 text-end">Reserve / yr</th>
                        </tr>
                      </thead>
                      <tbody>
                        {e.reserve.components.map((c) => (
                          <tr key={c.component} className="border-t border-black/5 dark:border-white/5">
                            <td className="px-4 py-2">{c.name}</td>
                            <td className="px-4 py-2 text-end tabular-nums">{c.service_life_years}y</td>
                            <td className="px-4 py-2 text-end tabular-nums">{num(c.replacement_cost)}</td>
                            <td className="px-4 py-2 text-end font-semibold tabular-nums">{num(c.annual_reserve)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>
            );
          }}
        </QueryState>
      }
    />
  );
}

// ------------------------------------------------------------------ lifecycle
export function LifecycleReserve() {
  const { b, fields } = useBuildingInputs({ age_years: "0" });
  const [years, setYears] = useState(30);
  const params = useDebounced({ covered_area: b.covered_area, property_type: b.property_type, quality: b.quality, age_years: b.age_years, city: b.city, years });
  const q = useApi<{
    build_value: number;
    total_replacement_cost: number;
    annualised: number;
    horizon_years: number;
    by_year: { year: number; items: { component: string; name: string; cost: number }[]; total: number }[];
    note?: string;
  }>(numOr(params.covered_area) ? "/maintenance/lifecycle" : null, params);

  return (
    <TwoCol
      form={
        <Panel title="Reserve study" subtitle="Capital replacements over the building's life" icon={<RefreshCcw className="h-4 w-4" />}>
          <div className="space-y-4">
            {fields}
            <Field label={`Horizon · ${years} years`}>
              <Slider value={years} min={5} max={50} step={5} onChange={setYears} />
            </Field>
          </div>
        </Panel>
      }
      result={
        <QueryState q={q} skeleton={<Skeleton className="h-96" />}>
          {(l) => {
            // Fill the gaps so the chart reads as a continuous timeline.
            const byYear = new Map(l.by_year.map((y) => [y.year, y.total]));
            const data = Array.from({ length: l.horizon_years }, (_, i) => ({ year: `Y${i + 1}`, spend: byYear.get(i + 1) ?? 0 }));
            const peak = [...l.by_year].sort((a, b) => b.total - a.total)[0];
            return (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <MiniStat label="Build value" value={pkrShort(l.build_value, false)} />
                  <MiniStat label={`${l.horizon_years}-yr replacements`} value={pkrShort(l.total_replacement_cost, false)} tone="gold" />
                  <MiniStat label="Annualised reserve" value={pkrShort(l.annualised, false)} tone="green" />
                  <MiniStat label="Peak year" value={peak ? `Year ${peak.year}` : "—"} hint={peak ? pkrShort(peak.total, false) : undefined} tone="red" />
                </div>
                <Panel title="Replacement spend by year" subtitle={l.note} icon={<CalendarDays className="h-4 w-4" />}>
                  <Bars data={data} x="year" series={[{ key: "spend", label: "Spend", color: "#c99a22" }]} height={240} format={crShort} />
                </Panel>
                <Panel title="Replacement timeline" icon={<Hammer className="h-4 w-4" />} flush>
                  <ol className="max-h-[340px] divide-y divide-black/5 overflow-y-auto dark:divide-white/5">
                    {l.by_year.map((y) => (
                      <li key={y.year} className="flex gap-4 px-5 py-3">
                        <span className="flex h-10 w-12 shrink-0 flex-col items-center justify-center rounded-xl bg-brand-50 text-brand-800 dark:bg-white/5 dark:text-brand-200">
                          <span className="text-[9px] font-bold uppercase">Year</span>
                          <span className="font-display font-bold leading-none">{y.year}</span>
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap gap-1.5">
                            {y.items.map((it, i) => (
                              <span key={i} className="rounded-full bg-black/5 px-2 py-0.5 text-[11px] font-medium dark:bg-white/10">
                                {it.name}
                              </span>
                            ))}
                          </div>
                        </div>
                        <span className="shrink-0 text-sm font-semibold tabular-nums">{pkrShort(y.total, false)}</span>
                      </li>
                    ))}
                  </ol>
                </Panel>
              </div>
            );
          }}
        </QueryState>
      }
    />
  );
}

// ------------------------------------------------------------------ repair or replace
export function RepairOrReplace({ components }: { components: Component[] }) {
  const [component, setComponent] = useState("hvac");
  const [age, setAge] = useState("12");
  const [condition, setCondition] = useState("");
  const [area, setArea] = useState("1000");
  const [quality, setQuality] = useState("standard");
  const [city, setCity] = useState("Lahore");
  const params = useDebounced({ component, age_years: age, condition: condition || undefined, covered_area: area, quality, city });
  const q = useApi<{
    name: string;
    age_years: number;
    service_life_years: number;
    life_used_pct: number;
    condition: string;
    decision: "repair" | "replace" | string;
    repair_cost: number;
    replace_cost: number;
    five_year: { repair_path: number; replace_path: number };
    rationale: string;
    criticality: string;
  }>(component && numOr(params.age_years) !== undefined ? "/maintenance/repair-or-replace" : null, params);

  return (
    <TwoCol
      form={
        <Panel title="Component" subtitle="Repair vs replace over a 5-year horizon" icon={<Hammer className="h-4 w-4" />}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Component" className="col-span-2">
              <Select value={component} onChange={(e) => setComponent(e.target.value)}>
                {components.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Age (yrs)">
              <Input type="number" min={0} value={age} onChange={(e) => setAge(e.target.value)} />
            </Field>
            <Field label="Condition">
              <Select value={condition} onChange={(e) => setCondition(e.target.value)}>
                <option value="">Infer from age</option>
                {["excellent", "good", "fair", "poor", "critical"].map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Covered area (sqft)">
              <Input type="number" min={100} value={area} onChange={(e) => setArea(e.target.value)} />
            </Field>
            <Field label="Quality">
              <Select value={quality} onChange={(e) => setQuality(e.target.value)} options={QUALITIES.map((p) => ({ value: p, label: titleCase(p) }))} />
            </Field>
            <Field label="City" className="col-span-2">
              <Select value={city} onChange={(e) => setCity(e.target.value)} options={CITIES} />
            </Field>
          </div>
        </Panel>
      }
      result={
        <QueryState q={q} skeleton={<Skeleton className="h-80" />}>
          {(r) => {
            const replace = r.decision === "replace";
            const saving = Math.abs(r.five_year.repair_path - r.five_year.replace_path);
            return (
              <div className="space-y-4">
                <motion.div key={r.decision} initial={{ scale: 0.97, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className={cn("rounded-2xl bg-gradient-to-br p-5 text-white", replace ? "from-gold-500 to-gold-700" : "from-brand-600 to-brand-800")}>
                  <p className="text-xs font-semibold uppercase tracking-wider text-white/75">Recommendation for {r.name}</p>
                  <p className="mt-1 font-display text-3xl font-bold">{replace ? "Replace" : "Repair"}</p>
                  <p className="mt-2 text-sm text-white/85">{r.rationale}</p>
                  <p className="mt-3 text-xs text-white/75">Saves about {pkr(saving)} over five years</p>
                </motion.div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <MiniStat label="Life used" value={`${Math.round(r.life_used_pct)}%`} tone={r.life_used_pct >= 75 ? "red" : "default"} hint={`${r.age_years} of ${r.service_life_years} yrs`} />
                  <MiniStat label="Condition" value={titleCase(r.condition)} />
                  <MiniStat label="Repair now" value={pkrShort(r.repair_cost, false)} />
                  <MiniStat label="Replace now" value={pkrShort(r.replace_cost, false)} />
                </div>
                <Panel title="5-year cost comparison" icon={<RefreshCcw className="h-4 w-4" />}>
                  <Bars
                    data={[
                      { path: "Repair path", cost: r.five_year.repair_path },
                      { path: "Replace path", cost: r.five_year.replace_path },
                    ]}
                    x="path"
                    series={[{ key: "cost", label: "5-yr cost" }]}
                    colorByIndex
                    height={200}
                    format={crShort}
                  />
                </Panel>
              </div>
            );
          }}
        </QueryState>
      }
    />
  );
}

// ------------------------------------------------------------------ schedule
export function PreventiveSchedule() {
  const [ptype, setPtype] = useState("house");
  const [age, setAge] = useState("5");
  const [horizon, setHorizon] = useState("12");
  const params = useDebounced({ property_type: ptype, age_years: age, horizon_months: horizon });
  const q = useApi<{ task_count: number; tasks: { month: number; component: string; name: string; category: string; frequency: string; criticality: string; tasks: string[] }[] }>("/maintenance/schedule", params);
  const start = new Date();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Property type" className="w-40">
          <Select value={ptype} onChange={(e) => setPtype(e.target.value)} options={PROPERTY_TYPES.map((p) => ({ value: p, label: titleCase(p) }))} />
        </Field>
        <Field label="Age (yrs)" className="w-28">
          <Input type="number" min={0} value={age} onChange={(e) => setAge(e.target.value)} />
        </Field>
        <Field label="Horizon" className="w-32">
          <Select value={horizon} onChange={(e) => setHorizon(e.target.value)} options={["6", "12", "18", "24"].map((h) => ({ value: h, label: `${h} months` }))} />
        </Field>
        {q.data && <Badge tone="green">{q.data.task_count} visits planned</Badge>}
      </div>
      <QueryState q={q} skeleton={<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-40" />)}</div>}>
        {(s) => {
          const months = Array.from(new Set(s.tasks.map((t) => t.month))).sort((a, b) => a - b);
          return months.length ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {months.map((m) => {
                const d = new Date(start.getFullYear(), start.getMonth() + m - 1, 1);
                const items = s.tasks.filter((t) => t.month === m);
                const critical = items.filter((t) => t.criticality === "critical").length;
                return (
                  <div key={m} className="rounded-2xl border border-black/5 p-4 dark:border-white/10">
                    <div className="mb-3 flex items-center justify-between">
                      <div>
                        <p className="font-display font-semibold">{d.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}</p>
                        <p className="text-xs text-ink-mute">Month {m}</p>
                      </div>
                      <div className="flex gap-1.5">
                        {critical > 0 && <Badge tone="red">{critical} critical</Badge>}
                        <Badge tone="gray">{items.length}</Badge>
                      </div>
                    </div>
                    <ul className="space-y-2">
                      {items.map((t, i) => (
                        <li key={i} className="group rounded-lg bg-black/[.025] px-2.5 py-1.5 dark:bg-white/5" title={t.tasks.join(" · ")}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-xs font-semibold">{t.name}</span>
                            <span className={cn("h-2 w-2 shrink-0 rounded-full", t.criticality === "critical" ? "bg-red-500" : t.criticality === "high" ? "bg-orange-500" : "bg-brand-500")} />
                          </div>
                          <p className="truncate text-[11px] text-ink-mute">
                            {titleCase(t.frequency)} · {t.tasks[0]}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState title="No visits in this horizon" />
          );
        }}
      </QueryState>
    </div>
  );
}

// ------------------------------------------------------------------ defects
export function DefectsCatalogue() {
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [qText, setQText] = useState("");
  const q = useApi<{ count: number; defects: Defect[] }>("/maintenance/defects", { category: category || undefined, severity: severity || undefined });
  const all = useApi<{ defects: Defect[] }>("/maintenance/defects");
  const categories = useMemo(() => Array.from(new Set((all.data?.defects ?? []).map((d) => d.category))).sort(), [all.data]);
  const rows = (q.data?.defects ?? []).filter((d) => !qText.trim() || `${d.name} ${d.symptoms.join(" ")} ${d.causes.join(" ")}`.toLowerCase().includes(qText.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full max-w-xs">
          <Input icon={<Search className="h-4 w-4" />} placeholder="Search symptoms, causes…" value={qText} onChange={(e) => setQText(e.target.value)} />
        </div>
        <Select className="w-40" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c === "mep" ? "MEP" : titleCase(c)}
            </option>
          ))}
        </Select>
        <Select className="w-36" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">Any severity</option>
          {["low", "medium", "high"].map((s) => (
            <option key={s} value={s}>
              {titleCase(s)}
            </option>
          ))}
        </Select>
      </div>
      <QueryState q={q} skeleton={<div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-48" />)}</div>}>
        {() =>
          rows.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              {rows.map((d) => (
                <details key={d.key} className="group rounded-2xl border border-black/5 p-4 open:shadow-soft dark:border-white/10">
                  <summary className="flex cursor-pointer list-none items-start gap-3">
                    <span className={cn("mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", d.severity === "high" ? "bg-red-50 text-red-600 dark:bg-red-500/15" : d.severity === "medium" ? "bg-gold-50 text-gold-700 dark:bg-gold-500/15" : "bg-sky-50 text-sky-700 dark:bg-sky-500/15")}>
                      <AlertTriangle className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">{d.name}</p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        <Badge tone="gray">{d.category === "mep" ? "MEP" : titleCase(d.category)}</Badge>
                        <Badge tone={d.severity === "high" ? "red" : d.severity === "medium" ? "gold" : "blue"}>{d.severity}</Badge>
                        <Badge tone={bandTone(d.urgency)}>{d.urgency}</Badge>
                      </div>
                    </div>
                    <span className="shrink-0 text-end text-xs">
                      <span className="block font-semibold">
                        Rs {num(d.cost_low)}–{num(d.cost_high)}
                      </span>
                      <span className="text-ink-mute">per {d.unit}</span>
                    </span>
                  </summary>
                  <div className="mt-4 space-y-3 border-t border-black/5 pt-3 text-sm dark:border-white/10">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Symptoms</p>
                      <p>{d.symptoms.join(" · ")}</p>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Likely causes</p>
                      <p>{d.causes.join(" · ")}</p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Diagnosis</p>
                        <p>{d.diagnosis}</p>
                      </div>
                      <div>
                        <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Repair</p>
                        <p>{d.repair}</p>
                      </div>
                    </div>
                    <p className="rounded-lg bg-brand-50/60 px-3 py-2 text-xs text-brand-800 dark:bg-white/5 dark:text-brand-200">
                      <strong>Prevention:</strong> {d.prevention}
                    </p>
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <EmptyState title="No defects match" />
          )
        }
      </QueryState>
    </div>
  );
}

