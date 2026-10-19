/** Area converter, price-per-unit and plot-dimension tools. */
import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { MoveDiagonal, Download, Maximize2, MoveHorizontal, MoveVertical, Ruler, Tag } from "lucide-react";
import { num, pkr, pkrShort } from "@/lib/format";
import { downloadText } from "@/lib/utils";
import { Button, Card, CardBody, CardHeader, CopyButton, Field, Input, Select, Skeleton, StatCard } from "@/components/ui";
import { CalcShell, ChoiceChips, NumField, StatGrid, useCalc } from "./CalcKit";

export const AREA_UNITS = [
  { value: "marla", label: "Marla" },
  { value: "kanal", label: "Kanal" },
  { value: "sqft", label: "Square feet" },
  { value: "sqyd", label: "Square yards" },
  { value: "sqm", label: "Square metres" },
  { value: "acre", label: "Acre" },
  { value: "hectare", label: "Hectare" },
];
const UNIT_LABEL: Record<string, string> = Object.fromEntries(AREA_UNITS.map((u) => [u.value, u.label]));

const MARLA_STD = [
  { value: 272.25, label: "272.25 sqft (standard)" },
  { value: 225, label: "225 sqft (old / some societies)" },
];

function MarlaChips({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <span className="label">Marla standard</span>
      <ChoiceChips value={value} onChange={onChange} options={MARLA_STD} />
    </div>
  );
}

// ================================================================== area converter
export function AreaCalc() {
  const [value, setValue] = useState(10);
  const [unit, setUnit] = useState("marla");
  const [marla, setMarla] = useState(272.25);
  const body = { value, from_unit: unit, marla_sqft: marla };
  const q = useCalc<{ input: { value: number; unit: string }; conversions: Record<string, number> }>("/tools/convert/area-table", body, { method: "GET", enabled: value > 0 });
  const d = q.data;
  const presets = [3, 5, 7, 10, 20, 40];
  return (
    <CalcShell
      q={q}
      save={{ tool: "area", inputs: body, outputs: d, name: `${value} ${unit} conversions` }}
      form={
        <>
          <Field label="Area">
            <Input type="number" min={0} step="any" value={value} onChange={(e) => setValue(Number(e.target.value))} />
          </Field>
          <Field label="Unit">
            <Select value={unit} onChange={(e) => setUnit(e.target.value)} options={AREA_UNITS} />
          </Field>
          <MarlaChips value={marla} onChange={setMarla} />
          <div>
            <span className="label">Common plot sizes</span>
            <ChoiceChips
              value={unit === "marla" ? value : -1}
              onChange={(v) => {
                setUnit("marla");
                setValue(v);
              }}
              options={presets.map((p) => ({ value: p, label: p >= 20 ? `${p / 20} Kanal` : `${p} Marla` }))}
            />
          </div>
        </>
      }
    >
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {Object.entries(d.conversions).map(([u, v], i) => (
              <motion.div
                key={u}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className={`card group relative overflow-hidden p-4 ${u === unit ? "ring-2 ring-gold-400" : ""}`}
              >
                <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-mute">{UNIT_LABEL[u] ?? u}</p>
                <p className="mt-1 break-all font-display text-xl font-bold text-brand-900 dark:text-white">{num(v, v < 10 ? 4 : 2)}</p>
                <CopyButton text={String(v)} className="absolute end-1 top-1 opacity-0 transition group-hover:opacity-100" />
              </motion.div>
            ))}
          </div>
          <Card>
            <CardHeader title="Quick reference" subtitle={`At ${marla} sqft per marla`} icon={<Ruler className="h-4 w-4" />} />
            <CardBody className="grid gap-2 text-sm sm:grid-cols-2">
              {[
                ["1 Marla", `${marla} sqft · ${num(marla / 9, 2)} sq yd`],
                ["1 Kanal", `20 Marla · ${num(marla * 20, 0)} sqft`],
                ["1 Acre", `8 Kanal · 43,560 sqft (≈ ${num(43560 / marla, 1)} marla)`],
                ["1 Square (murabba)", "25 acres"],
              ].map(([a, b]) => (
                <div key={a} className="flex items-center justify-between gap-3 rounded-xl bg-brand-50/60 px-3 py-2 dark:bg-white/5">
                  <span className="font-semibold">{a}</span>
                  <span className="text-end text-ink-mute">{b}</span>
                </div>
              ))}
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== price per unit
export function PricePerUnitCalc() {
  const [price, setPrice] = useState(30_000_000);
  const [area, setArea] = useState(10);
  const [unit, setUnit] = useState("marla");
  const [marla, setMarla] = useState(272.25);
  const body = { price, area, from_unit: unit, marla_sqft: marla };
  const q = useCalc<{ area_sqft: number; price_per_sqft: number; price_per_sqyd: number; price_per_sqm: number; price_per_marla: number }>("/tools/calculators/price-per-unit", body, { enabled: area > 0 });
  const d = q.data;
  return (
    <CalcShell
      q={q}
      save={{ tool: "price_per_unit", inputs: body, outputs: d, name: `${pkrShort(price)} for ${area} ${unit}` }}
      form={
        <>
          <NumField label="Asking price" value={price} onChange={setPrice} min={500_000} max={500_000_000} step={250_000} display={(v) => pkrShort(v)} />
          <Field label="Area">
            <Input type="number" min={0} step="any" value={area} onChange={(e) => setArea(Number(e.target.value))} />
          </Field>
          <Field label="Unit">
            <Select value={unit} onChange={(e) => setUnit(e.target.value)} options={AREA_UNITS.filter((u) => !["acre", "hectare"].includes(u.value))} />
          </Field>
          <MarlaChips value={marla} onChange={setMarla} />
        </>
      }
    >
      {d && (
        <>
          <StatGrid>
            <StatCard label="Per sqft" value={pkr(d.price_per_sqft)} icon={<Tag className="h-5 w-5" />} />
            <StatCard label="Per marla" value={pkrShort(d.price_per_marla)} icon={<Tag className="h-5 w-5" />} tone="gold" />
            <StatCard label="Per sq yard" value={pkr(d.price_per_sqyd)} icon={<Tag className="h-5 w-5" />} tone="blue" />
            <StatCard label="Per sq metre" value={pkr(d.price_per_sqm)} icon={<Tag className="h-5 w-5" />} tone="purple" />
          </StatGrid>
          <Card>
            <CardBody className="flex flex-wrap items-center gap-3 text-sm text-ink-soft dark:text-slate-300">
              <Maximize2 className="h-4 w-4 text-brand-600" />
              {num(area)} {UNIT_LABEL[unit]} = <b>{num(d.area_sqft)} sqft</b>. Compare the per-sqft figure against nearby listings on the
              <Link className="link" to="/insights">
                market insights
              </Link>
              page.
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== plot dimensions + diagram
interface Dims {
  area_sqft: number;
  length_ft: number;
  width_ft: number;
  length_m: number;
  width_m: number;
  perimeter_ft: number;
  diagonal_ft: number;
}

export function PlotDimensionsCalc() {
  const [area, setArea] = useState(10);
  const [unit, setUnit] = useState("marla");
  const [ratio, setRatio] = useState(2);
  const [marla, setMarla] = useState(272.25);
  const body = { area, from_unit: unit, ratio, marla_sqft: marla };
  const q = useCalc<Dims>("/tools/plot/dimensions", body, { method: "GET", enabled: area > 0 && ratio > 0 });
  const d = q.data;
  const dq = useCalc<{ svg: string }>(
    "/tools/plot/diagram",
    { length_ft: d ? Math.round(d.length_ft * 10) / 10 : 0, width_ft: d ? Math.round(d.width_ft * 10) / 10 : 0, label: `${area} ${UNIT_LABEL[unit] ?? unit}`, marla_sqft: marla },
    { method: "GET", enabled: !!d },
  );
  const svg = dq.data?.svg;
  return (
    <CalcShell
      q={q}
      save={{ tool: "plot_dimensions", inputs: body, outputs: d, name: `${area} ${unit} plot · ${ratio}:1` }}
      form={
        <>
          <Field label="Plot area">
            <Input type="number" min={0} step="any" value={area} onChange={(e) => setArea(Number(e.target.value))} />
          </Field>
          <Field label="Unit">
            <Select value={unit} onChange={(e) => setUnit(e.target.value)} options={AREA_UNITS.slice(0, 5)} />
          </Field>
          <NumField label="Depth : frontage ratio" value={ratio} onChange={setRatio} min={1} max={4} step={0.05} display={(v) => `${v.toFixed(2)} : 1`} hint="Typical society plots are ~1.8–2.25 : 1" />
          <MarlaChips value={marla} onChange={setMarla} />
        </>
      }
    >
      {d && (
        <>
          <StatGrid>
            <StatCard label="Depth (length)" value={`${num(d.length_ft, 1)} ft`} hint={`${num(d.length_m, 2)} m`} icon={<MoveVertical className="h-5 w-5" />} />
            <StatCard label="Frontage (width)" value={`${num(d.width_ft, 1)} ft`} hint={`${num(d.width_m, 2)} m`} icon={<MoveHorizontal className="h-5 w-5" />} tone="gold" />
            <StatCard label="Perimeter" value={`${num(d.perimeter_ft, 1)} ft`} icon={<Ruler className="h-5 w-5" />} tone="blue" />
            <StatCard label="Diagonal" value={`${num(d.diagonal_ft, 1)} ft`} hint={`${num(d.area_sqft)} sqft`} icon={<MoveDiagonal className="h-5 w-5" />} tone="purple" />
          </StatGrid>
          <Card>
            <CardHeader
              title="Plot diagram"
              subtitle="Printable SVG generated by the backend"
              action={svg && <Button variant="ghost" size="sm" icon={<Download className="h-4 w-4" />} onClick={() => downloadText(`plot-${area}${unit}.svg`, svg, "image/svg+xml")}>SVG</Button>}
            />
            <CardBody className="flex justify-center bg-slate-50/60 dark:bg-white/5">
              {svg ? (
                <img src={`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`} alt={`Plot diagram ${num(d.length_ft, 1)} by ${num(d.width_ft, 1)} ft`} className="max-h-[460px] w-auto max-w-full rounded-xl bg-white shadow-card" />
              ) : (
                <Skeleton className="h-80 w-60" />
              )}
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}
