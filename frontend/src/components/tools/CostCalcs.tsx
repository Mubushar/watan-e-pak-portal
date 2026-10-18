/** Cost & tax calculators: construction, transfer, commission, CGT, joint investment. */
import { useState } from "react";
import { motion } from "framer-motion";
import { Banknote, Building2, CalendarRange, HandCoins, HardHat, Hourglass, Percent, Plus, Receipt, Stamp, Trash2, Users, Wallet } from "lucide-react";
import { num, pkr, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button, Card, CardBody, CardHeader, Field, Input, Progress, Select, StatCard, Toggle } from "@/components/ui";
import { Bars, Donut, Legendish, PALETTE } from "@/components/ui/charts";
import { CalcShell, ChoiceChips, NumField, StatGrid, useCalc } from "./CalcKit";

const money = (v: number) => pkrShort(v, false);
const crore = (v: number) => pkrShort(v);

// ================================================================== construction
const BUILDING_TYPES = ["house", "floor", "apartment", "building", "office", "shop", "warehouse", "shed"];
const TIERS = ["economy", "standard", "premium", "luxury"];
const SYSTEMS = [
  { value: "rcc_frame", label: "RCC frame" },
  { value: "load_bearing", label: "Load-bearing brick" },
  { value: "confined_masonry", label: "Confined masonry" },
  { value: "steel_frame", label: "Steel frame" },
  { value: "peb", label: "Pre-engineered (PEB)" },
  { value: "precast", label: "Precast concrete" },
  { value: "aac_blocks", label: "AAC blocks" },
  { value: "green_building", label: "Green / energy-efficient" },
];
const CITIES = ["Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta", "Gujranwala", "Hyderabad"];

interface ConstructionRes {
  assumptions: { effective_rate_sqft: number; city_factor: number };
  cost: Record<string, number | string> & { total: number; cost_per_sqft: number; subtotal_construction: number };
  elements: { element: string; label: string; category: string; share_pct: number; amount: number }[];
  timeline: { total_days: number; total_months: number; phases: { key: string; name: string; days: number; weight_pct: number }[] };
}

export function ConstructionCalc() {
  const [area, setArea] = useState(2250);
  const [floors, setFloors] = useState(2);
  const [type, setType] = useState("house");
  const [tier, setTier] = useState("standard");
  const [system, setSystem] = useState("rcc_frame");
  const [city, setCity] = useState("Lahore");
  const [esc, setEsc] = useState(0);
  const body = { covered_area: area, floors, building_type: type, quality_tier: tier, system, city, escalation_years: esc };
  const q = useCalc<ConstructionRes>("/tools/calculators/construction-cost", body, { enabled: area > 0 });
  const d = q.data;
  const costLines = d
    ? (["subtotal_construction", "preliminaries", "contingency", "consultancy_and_approvals", "contractor_overhead_profit", "escalation"] as const)
        .map((k) => ({ name: titleCase(k.replace("subtotal_", "")), value: Math.round(Number(d.cost[k] ?? 0)) }))
        .filter((x) => x.value > 0)
    : [];
  return (
    <CalcShell
      q={q}
      save={{ tool: "construction", inputs: body, outputs: d && { cost: d.cost, assumptions: d.assumptions, timeline: { total_days: d.timeline.total_days, total_months: d.timeline.total_months } }, name: `${num(area)} sqft ${tier} ${type} · ${city}` }}
      form={
        <>
          <NumField label="Covered area (all floors)" value={area} onChange={setArea} min={300} max={30_000} step={50} display={(v) => `${num(v)} sqft`} />
          <NumField label="Floors" value={floors} onChange={setFloors} min={1} max={12} />
          <div>
            <span className="label">Finish quality</span>
            <ChoiceChips value={tier} onChange={setTier} options={TIERS.map((t) => ({ value: t, label: titleCase(t) }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Building type">
              <Select value={type} onChange={(e) => setType(e.target.value)} options={BUILDING_TYPES.map((t) => ({ value: t, label: titleCase(t) }))} />
            </Field>
            <Field label="City">
              <Select value={city} onChange={(e) => setCity(e.target.value)} options={CITIES} />
            </Field>
          </div>
          <Field label="Structural system">
            <Select value={system} onChange={(e) => setSystem(e.target.value)} options={SYSTEMS} />
          </Field>
          <NumField label="Cost escalation horizon" value={esc} onChange={setEsc} min={0} max={5} step={0.5} suffix=" yrs" />
        </>
      }
    >
      {d && (
        <>
          <StatGrid>
            <StatCard label="Total build cost" value={pkrShort(d.cost.total)} icon={<HardHat className="h-5 w-5" />} hint={pkr(d.cost.total)} />
            <StatCard label="All-in per sqft" value={pkr(d.cost.cost_per_sqft)} icon={<Building2 className="h-5 w-5" />} tone="gold" hint={`base ${pkr(d.assumptions.effective_rate_sqft)}`} />
            <StatCard label="Build time" value={`${num(d.timeline.total_months, 1)} months`} icon={<Hourglass className="h-5 w-5" />} tone="blue" hint={`${d.timeline.total_days} working days`} />
            <StatCard label="City factor" value={`× ${num(d.assumptions.city_factor, 2)}`} icon={<CalendarRange className="h-5 w-5" />} tone="purple" hint={city} />
          </StatGrid>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader title="Cost by element" subtitle="Share of construction subtotal" />
              <CardBody>
                <Bars data={d.elements.map((e) => ({ label: e.label.split(" — ")[0].split(",")[0], amount: Math.round(e.amount) }))} x="label" horizontal series={[{ key: "amount", label: "PKR" }]} colorByIndex format={money} height={Math.max(260, d.elements.length * 30)} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Budget build-up" subtitle="Subtotal plus on-costs" />
              <CardBody>
                <Donut data={costLines} format={money} height={210} center={<span className="font-display text-lg font-bold">{pkrShort(d.cost.total, false)}</span>} />
                <div className="mt-3">
                  <Legendish data={costLines.map((c) => ({ ...c, value: Math.round((c.value / d.cost.total) * 100) }))} />
                </div>
              </CardBody>
            </Card>
          </div>
          <Card>
            <CardHeader title="Phase timeline" subtitle={`${d.timeline.phases.length} phases · ${d.timeline.total_days} days`} />
            <CardBody className="space-y-2">
              {d.timeline.phases.map((p, i) => (
                <div key={p.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 sm:grid-cols-[220px_minmax(0,1fr)_70px]">
                  <span className="truncate text-sm font-medium">{p.name}</span>
                  <div className="hidden h-3 overflow-hidden rounded-full bg-black/5 sm:block dark:bg-white/10">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${(p.days / Math.max(...d.timeline.phases.map((x) => x.days))) * 100}%` }} transition={{ delay: i * 0.04 }} className="h-full rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                  </div>
                  <span className="text-end text-xs font-semibold tabular-nums text-ink-mute">{p.days} d</span>
                </div>
              ))}
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== transfer
const PROVINCES = [
  { value: "punjab", label: "Punjab" },
  { value: "sindh", label: "Sindh" },
  { value: "kpk", label: "Khyber Pakhtunkhwa" },
  { value: "islamabad", label: "Islamabad (ICT)" },
  { value: "balochistan", label: "Balochistan" },
];

export function TransferCalc() {
  const [price, setPrice] = useState(25_000_000);
  const [province, setProvince] = useState("punjab");
  const [filer, setFiler] = useState(true);
  const body = { price, province, filer };
  const q = useCalc<{ lines: { component: string; rate_pct: number; amount: number }[]; total_transfer_cost: number; total_pct: number; effective_price: number; note: string }>("/tools/calculators/transfer-costs", body);
  const d = q.data;
  return (
    <CalcShell
      q={q}
      save={{ tool: "transfer", inputs: body, outputs: d, name: `Transfer · ${pkrShort(price)} · ${province}` }}
      form={
        <>
          <NumField label="Declared value" value={price} onChange={setPrice} min={500_000} max={500_000_000} step={250_000} display={crore} />
          <Field label="Province / territory">
            <Select value={province} onChange={(e) => setProvince(e.target.value)} options={PROVINCES} />
          </Field>
          <Toggle checked={filer} onChange={setFiler} label={<span className="font-medium">{filer ? "Active tax filer (ATL)" : "Non-filer — higher withholding"}</span>} />
        </>
      }
    >
      {d && (
        <>
          <StatGrid cols={3}>
            <StatCard label="Total transfer cost" value={pkrShort(d.total_transfer_cost)} icon={<Stamp className="h-5 w-5" />} hint={`${num(d.total_pct, 2)}% of value`} />
            <StatCard label="Effective price" value={pkrShort(d.effective_price)} icon={<Wallet className="h-5 w-5" />} tone="gold" />
            <StatCard label="Withholding" value={pkrShort(d.lines.find((l) => /withholding/i.test(l.component))?.amount ?? 0)} icon={<Receipt className="h-5 w-5" />} tone={filer ? "blue" : "red"} hint={filer ? "Filer rate" : "Non-filer rate"} />
          </StatGrid>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
            <Card>
              <CardHeader title="Line items" />
              <div className="divide-y divide-black/5 dark:divide-white/10">
                {d.lines.map((l, i) => (
                  <div key={l.component} className="flex items-center gap-3 px-5 py-3">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{l.component}</span>
                    <span className="text-xs text-ink-mute">{num(l.rate_pct, 2)}%</span>
                    <span className="w-28 text-end font-semibold tabular-nums">{pkr(l.amount)}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between bg-brand-50/60 px-5 py-3 font-semibold dark:bg-white/5">
                  <span>Total</span>
                  <span className="tabular-nums">{pkr(d.total_transfer_cost)}</span>
                </div>
              </div>
            </Card>
            <Card>
              <CardBody>
                <Donut data={d.lines.map((l) => ({ name: l.component, value: Math.round(l.amount) }))} format={money} height={220} center={<span className="font-display text-lg font-bold">{num(d.total_pct, 1)}%</span>} />
              </CardBody>
            </Card>
          </div>
          <p className="text-xs text-ink-mute">{d.note}</p>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== commission
export function CommissionCalc() {
  const [price, setPrice] = useState(25_000_000);
  const [rate, setRate] = useState(2);
  const [vat, setVat] = useState(true);
  const body = { price, rate: rate / 100, include_vat: vat };
  const q = useCalc<{ rate: number; commission: number; vat_rate: number; vat: number; total_payable: number }>("/tools/calculators/commission", body);
  const d = q.data;
  return (
    <CalcShell
      q={q}
      save={{ tool: "commission", inputs: body, outputs: d, name: `Commission · ${pkrShort(price)} @ ${rate}%` }}
      form={
        <>
          <NumField label="Sale price" value={price} onChange={setPrice} min={500_000} max={500_000_000} step={250_000} display={crore} />
          <NumField label="Commission rate" value={rate} onChange={setRate} min={0.25} max={5} step={0.25} suffix="%" />
          <Toggle checked={vat} onChange={setVat} label={<span className="font-medium">Add sales tax on services</span>} />
        </>
      }
    >
      {d && (
        <>
          <StatGrid cols={3}>
            <StatCard label="Commission" value={pkrShort(d.commission)} icon={<HandCoins className="h-5 w-5" />} hint={pkr(d.commission)} />
            <StatCard label={`Sales tax (${num(d.vat_rate * 100, 0)}%)`} value={pkrShort(d.vat)} icon={<Percent className="h-5 w-5" />} tone="red" />
            <StatCard label="Client pays" value={pkrShort(d.total_payable)} icon={<Banknote className="h-5 w-5" />} tone="gold" hint={pkr(d.total_payable)} />
          </StatGrid>
          <Card>
            <CardHeader title="Commission at other rates" subtitle="Same sale price" />
            <CardBody>
              <Bars data={[1, 1.5, 2, 2.5, 3, 4].map((r) => ({ rate: `${r}%`, commission: Math.round((price * r) / 100) }))} x="rate" series={[{ key: "commission", label: "Commission" }]} format={money} height={220} />
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== capital gains
export function CgtCalc() {
  const [gain, setGain] = useState(5_000_000);
  const [years, setYears] = useState(2);
  const [filer, setFiler] = useState(true);
  const body = { gain, holding_years: years, filer };
  const q = useCalc<{ rate_pct: number; tax: number; net_gain: number; bands: { max_holding_years: number | null; rate: number }[]; note: string }>("/tools/calculators/capital-gains", body);
  const d = q.data;
  const bandIdx = d ? d.bands.findIndex((b) => b.max_holding_years === null || years <= b.max_holding_years) : -1;
  return (
    <CalcShell
      q={q}
      save={{ tool: "cgt", inputs: body, outputs: d, name: `CGT · ${pkrShort(gain)} gain · ${years}y` }}
      form={
        <>
          <NumField label="Capital gain" value={gain} onChange={setGain} min={0} max={200_000_000} step={100_000} display={crore} hint="Sale price minus cost of acquisition" />
          <NumField label="Holding period" value={years} onChange={setYears} min={0} max={10} step={0.5} suffix=" yrs" />
          <Toggle checked={filer} onChange={setFiler} label={<span className="font-medium">{filer ? "Filer" : "Non-filer"}</span>} />
        </>
      }
    >
      {d && (
        <>
          <StatGrid cols={3}>
            <StatCard label="Tax rate" value={`${num(d.rate_pct, 2)}%`} icon={<Percent className="h-5 w-5" />} />
            <StatCard label="Tax payable" value={pkrShort(d.tax)} icon={<Receipt className="h-5 w-5" />} tone="red" hint={pkr(d.tax)} />
            <StatCard label="Net gain" value={pkrShort(d.net_gain)} icon={<Wallet className="h-5 w-5" />} tone="gold" />
          </StatGrid>
          <Card>
            <CardHeader title="Holding-period bands" subtitle="Rate falls the longer you hold" />
            <CardBody className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {d.bands.map((b, i) => {
                const prev = i === 0 ? 0 : d.bands[i - 1].max_holding_years ?? 0;
                const active = i === bandIdx;
                return (
                  <div key={i} className={cn("rounded-2xl border p-4 transition", active ? "border-gold-400 bg-gold-50 shadow-glow dark:bg-gold-500/10" : "border-black/5 dark:border-white/10")}>
                    <p className="text-xs font-semibold uppercase text-ink-mute">{b.max_holding_years === null ? `> ${prev} yrs` : `${prev}–${b.max_holding_years} yrs`}</p>
                    <p className="mt-1 font-display text-2xl font-bold">{num(b.rate * 100, 1)}%</p>
                    <Progress value={b.rate * 100} max={20} tone={active ? "gold" : "green"} className="mt-2" />
                  </div>
                );
              })}
            </CardBody>
          </Card>
          <p className="text-xs text-ink-mute">{d.note}</p>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== joint investment
interface Partner {
  name: string;
  capital: number;
}

export function JointInvestmentCalc() {
  const [partners, setPartners] = useState<Partner[]>([
    { name: "Partner A", capital: 5_000_000 },
    { name: "Partner B", capital: 3_000_000 },
    { name: "Partner C", capital: 2_000_000 },
  ]);
  const [profit, setProfit] = useState(2_500_000);
  const [months, setMonths] = useState(12);
  const valid = partners.filter((p) => p.name.trim() && p.capital > 0);
  const body = { partners: valid, total_profit: profit, months };
  const q = useCalc<{ total_capital: number; partners: { partner: string; capital: number; share_pct: number; profit: number; roi_pct: number; annualised_roi_pct: number }[] }>("/tools/calculators/joint-investment", body, { enabled: valid.length > 0 });
  const d = q.data;
  const upd = (i: number, patch: Partial<Partner>) => setPartners((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <CalcShell
      q={q}
      save={{ tool: "joint_investment", inputs: body, outputs: d, name: `JV split · ${valid.length} partners` }}
      form={
        <>
          <div className="space-y-2">
            <span className="label">Partners & capital</span>
            {partners.map((p, i) => (
              <motion.div key={i} layout initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                <Input value={p.name} onChange={(e) => upd(i, { name: e.target.value })} className="!py-2 text-sm" placeholder="Name" />
                <Input type="number" min={0} value={p.capital} onChange={(e) => upd(i, { capital: Number(e.target.value) })} className="!w-32 !py-2 text-end text-sm tabular-nums" />
                <button type="button" onClick={() => setPartners((ps) => ps.filter((_, j) => j !== i))} className="btn btn-ghost btn-icon !h-8 !w-8 shrink-0" aria-label="Remove partner" disabled={partners.length <= 1}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </motion.div>
            ))}
            <Button variant="outline" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setPartners((ps) => [...ps, { name: `Partner ${String.fromCharCode(65 + ps.length)}`, capital: 1_000_000 }])} disabled={partners.length >= 8}>
              Add partner
            </Button>
          </div>
          <NumField label="Total profit to split" value={profit} onChange={setProfit} min={0} max={100_000_000} step={50_000} display={crore} />
          <NumField label="Investment period" value={months} onChange={setMonths} min={1} max={120} suffix=" months" />
        </>
      }
    >
      {d && (
        <>
          <StatGrid cols={3}>
            <StatCard label="Pooled capital" value={pkrShort(d.total_capital)} icon={<Users className="h-5 w-5" />} />
            <StatCard label="Profit" value={pkrShort(profit)} icon={<HandCoins className="h-5 w-5" />} tone="gold" />
            <StatCard label="Pool ROI" value={`${num(d.partners[0]?.roi_pct ?? 0, 1)}%`} icon={<Percent className="h-5 w-5" />} tone="blue" hint={`${num(d.partners[0]?.annualised_roi_pct ?? 0, 1)}% annualised`} />
          </StatGrid>
          <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
            <Card>
              <CardBody>
                <Donut data={d.partners.map((p) => ({ name: p.partner, value: Math.round(p.profit) }))} format={money} height={220} center={<span className="text-xs font-semibold text-ink-mute">Profit split</span>} />
              </CardBody>
            </Card>
            <Card className="overflow-hidden">
              <div className="scroll-x overflow-x-auto">
                <table className="w-full min-w-[440px] text-sm">
                  <thead className="bg-brand-50/70 text-xs uppercase text-ink-mute dark:bg-white/5">
                    <tr>
                      {["Partner", "Capital", "Share", "Profit", "ROI"].map((h) => (
                        <th key={h} className="px-4 py-2.5 text-start font-semibold">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {d.partners.map((p, i) => (
                      <tr key={p.partner + i} className="border-t border-black/5 dark:border-white/10">
                        <td className="px-4 py-2.5 font-semibold">
                          <span className="me-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                          {p.partner}
                        </td>
                        <td className="px-4 py-2.5 tabular-nums">{pkrShort(p.capital)}</td>
                        <td className="px-4 py-2.5 tabular-nums">{num(p.share_pct, 1)}%</td>
                        <td className="px-4 py-2.5 font-semibold tabular-nums text-brand-700 dark:text-brand-300">{pkrShort(p.profit)}</td>
                        <td className="px-4 py-2.5 tabular-nums">{num(p.roi_pct, 1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      )}
    </CalcShell>
  );
}
