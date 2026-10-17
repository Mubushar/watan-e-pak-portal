import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, ArrowRightLeft, Calculator, Cpu, Landmark, Layers, Ruler, Search, Sparkles, Wrench } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { num, pkr, pkrShort, titleCase } from "@/lib/format";
import { Badge, ButtonLink, Card, CardBody, CardHeader, Input, QueryState, Select, Skeleton, Tabs } from "@/components/ui";
import { CATEGORY_ICON, EXTRA_TOOLS, INTERACTIVE_TOOLS, phaseTone, ToolIcon, type ToolCard } from "@/components/tools/toolMeta";
import { NumField, useCalc } from "@/components/tools/CalcKit";
import { AREA_UNITS } from "@/components/tools/AreaCalcs";

interface Overview {
  counts: { tools: number; categories: number; calculators: number; crs_systems: number; saved_projects: number };
  by_phase: Record<string, number>;
  native_tools: number;
  optional_dependency_tools: number;
  config: { disclaimer: string; default_marla_sqft: number };
}

function QuickArea() {
  const [value, setValue] = useState(10);
  const [from, setFrom] = useState("marla");
  const [to, setTo] = useState("sqft");
  const q = useCalc<{ result: { value: number; unit: string }; all_units: Record<string, number> }>("/tools/convert/area", { value, from_unit: from, to_unit: to }, { method: "GET", enabled: value > 0 });
  return (
    <Card className="overflow-hidden">
      <CardHeader title="Quick area converter" subtitle="Marla, kanal, sqft and more" icon={<Ruler className="h-4 w-4" />} action={<ButtonLink to="/tools/area" variant="ghost" size="sm">Full tool</ButtonLink>} />
      <CardBody className="space-y-4">
        <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
          <div className="space-y-2">
            <Input type="number" min={0} step="any" value={value} onChange={(e) => setValue(Number(e.target.value))} aria-label="Area value" />
            <Select value={from} onChange={(e) => setFrom(e.target.value)} options={AREA_UNITS} aria-label="From unit" />
          </div>
          <button
            type="button"
            onClick={() => {
              setFrom(to);
              setTo(from);
              if (q.data) setValue(Number(q.data.result.value.toFixed(4)));
            }}
            className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-gold-gradient text-brand-950 shadow-glow transition hover:rotate-180"
            aria-label="Swap units"
          >
            <ArrowRightLeft className="h-4 w-4" />
          </button>
          <div className="space-y-2">
            <div className="input flex items-center bg-brand-50/70 font-display font-bold text-brand-900 dark:bg-white/5 dark:text-white">{q.data ? num(q.data.result.value, 4) : "…"}</div>
            <Select value={to} onChange={(e) => setTo(e.target.value)} options={AREA_UNITS} aria-label="To unit" />
          </div>
        </div>
        {q.data && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(q.data.all_units)
              .filter(([u]) => u !== from && u !== to)
              .map(([u, v]) => (
                <span key={u} className="chip bg-brand-50 text-brand-800 dark:bg-white/5 dark:text-brand-200">
                  {num(v, 3)} {u}
                </span>
              ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function QuickMortgage() {
  const [price, setPrice] = useState(20_000_000);
  const [rate, setRate] = useState(18);
  const [years, setYears] = useState(20);
  const q = useCalc<{ monthly_payment: number; total_interest: number; loan_amount: number }>("/tools/calculators/mortgage", { price, down_payment: price * 0.2, annual_rate: rate / 100, years });
  return (
    <Card className="overflow-hidden">
      <CardHeader title="Mini mortgage" subtitle="20% down · live from the backend" icon={<Landmark className="h-4 w-4" />} action={<ButtonLink to="/tools/mortgage" variant="ghost" size="sm">Full tool</ButtonLink>} />
      <CardBody className="space-y-4">
        <NumField label="Price" value={price} onChange={setPrice} min={2_000_000} max={200_000_000} step={500_000} display={(v) => pkrShort(v)} />
        <div className="grid gap-4 sm:grid-cols-2">
          <NumField label="Rate" value={rate} onChange={setRate} min={5} max={30} step={0.5} suffix="%" />
          <NumField label="Years" value={years} onChange={setYears} min={5} max={30} />
        </div>
        <div className="flex items-center justify-between rounded-2xl bg-brand-gradient px-4 py-3 text-white">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-white/60">Monthly</p>
            <p className="font-display text-2xl font-bold">{q.data ? pkr(q.data.monthly_payment) : "…"}</p>
          </div>
          <div className="text-end text-xs text-white/70">
            <p>Loan {q.data ? pkrShort(q.data.loan_amount) : "…"}</p>
            <p>Interest {q.data ? pkrShort(q.data.total_interest) : "…"}</p>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function ToolTile({ t, i }: { t: ToolCard; i: number }) {
  const live = INTERACTIVE_TOOLS.has(t.key);
  return (
    <motion.div layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }} transition={{ delay: Math.min(i, 12) * 0.03 }}>
      <Link to={`/tools/${t.key}`} className="card card-hover group relative flex h-full flex-col overflow-hidden p-5">
        <div className="pointer-events-none absolute -end-10 -top-10 h-32 w-32 rounded-full bg-gradient-to-br from-gold-300/0 to-gold-300/0 transition duration-500 group-hover:from-gold-300/25 group-hover:to-brand-400/10" />
        <div className="flex items-start justify-between gap-3">
          <ToolIcon toolKey={t.key} category={t.category} />
          <div className="flex flex-wrap justify-end gap-1">
            {live && (
              <Badge tone="gold" icon={<Sparkles className="h-3 w-3" />}>
                Live
              </Badge>
            )}
            <Badge tone={phaseTone(t.phase)}>P{t.phase}</Badge>
          </div>
        </div>
        <h3 className="mt-4 font-display text-lg font-semibold text-ink group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300">{t.name}</h3>
        <p className="mt-1 flex-1 text-sm text-ink-mute dark:text-slate-400">{t.blurb}</p>
        <div className="mt-4 flex items-center justify-between gap-2">
          {t.mcp_tool ? (
            <code className="truncate rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600 dark:bg-white/10 dark:text-slate-300">{t.mcp_tool}</code>
          ) : (
            <span />
          )}
          <ArrowRight className="h-4 w-4 shrink-0 text-brand-600 transition group-hover:translate-x-1 rtl:rotate-180 rtl:group-hover:-translate-x-1" />
        </div>
      </Link>
    </motion.div>
  );
}

export default function ToolsCenter() {
  const ov = useApi<Overview>("/tools/overview");
  const cats = useApi<{ categories: { key: string; label: string; count: number }[] }>("/tools/categories");
  const cat = useApi<{ count: number; tools: ToolCard[] }>("/tools/catalog");
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");

  const tools = useMemo(() => {
    const base = [...(cat.data?.tools ?? [])];
    for (const e of EXTRA_TOOLS) if (!base.some((t) => t.key === e.key)) base.push(e);
    return base;
  }, [cat.data]);
  const filtered = tools.filter((t) => (tab === "all" || t.category === tab) && (!search.trim() || `${t.name} ${t.blurb} ${t.key}`.toLowerCase().includes(search.toLowerCase())));
  const tabs = [
    { value: "all", label: "All tools", icon: <Layers className="h-4 w-4" />, count: tools.length },
    ...(cats.data?.categories ?? []).map((c) => {
      const I = CATEGORY_ICON[c.key] ?? Wrench;
      return { value: c.key, label: c.label, icon: <I className="h-4 w-4" />, count: tools.filter((t) => t.category === c.key).length };
    }),
  ];
  const c = ov.data?.counts;

  return (
    <div className="pb-16">
      {/* hero */}
      <section className="relative isolate overflow-hidden bg-brand-gradient text-white">
        <div aria-hidden className="absolute inset-0 -z-10 bg-mesh" />
        <div
          aria-hidden
          className="absolute inset-0 -z-10 opacity-[0.08]"
          style={{ backgroundImage: "linear-gradient(rgba(255,255,255,.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.6) 1px, transparent 1px)", backgroundSize: "36px 36px" }}
        />
        <motion.div aria-hidden className="absolute -end-24 -top-24 -z-10 h-96 w-96 rounded-full bg-gold-400/25 blur-3xl" animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 10, repeat: Infinity }} />
        <div className="container grid gap-10 py-14 lg:grid-cols-[minmax(0,1fr)_420px] lg:items-center lg:py-20">
          <div>
            <p className="section-eyebrow !text-gold-300">Tools & Utilities</p>
            <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mt-3 font-display text-4xl font-bold leading-tight sm:text-5xl">
              Every property calculation, <span className="bg-gold-gradient bg-clip-text text-transparent">one place</span>.
            </motion.h1>
            <p className="mt-4 max-w-xl text-lg text-white/75">Mortgages, marla maths, stamp duty, build costs, Hijri dates and on-map measurement — live from the Arz-e-Pak engines and callable by AI agents over MCP.</p>
            <div className="mt-6 max-w-md">
              <Input icon={<Search className="h-4 w-4" />} placeholder="Search tools — e.g. stamp duty, marla, CGT" value={search} onChange={(e) => setSearch(e.target.value)} className="!border-white/20 !bg-white/95 !text-ink" />
            </div>
            <div className="mt-8 grid max-w-lg grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: "Tools", value: c?.tools },
                { label: "Calculators", value: c?.calculators },
                { label: "Categories", value: c?.categories },
                { label: "Native", value: ov.data?.native_tools },
              ].map((s) => (
                <div key={s.label} className="glass-dark rounded-2xl px-3 py-3">
                  <p className="font-display text-2xl font-bold text-gold-200">{s.value ?? "–"}</p>
                  <p className="text-[11px] uppercase tracking-wider text-white/60">{s.label}</p>
                </div>
              ))}
            </div>
          </div>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="text-ink dark:text-slate-100">
            <QuickMortgage />
          </motion.div>
        </div>
      </section>

      <div className="container mt-10 space-y-8">
        <Tabs tabs={tabs} value={tab} onChange={setTab} />
        <QueryState
          q={cat}
          skeleton={
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-52" />
              ))}
            </div>
          }
        >
          {() =>
            filtered.length ? (
              <motion.div layout className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                <AnimatePresence mode="popLayout">
                  {filtered.map((t, i) => (
                    <ToolTile key={t.key} t={t} i={i} />
                  ))}
                </AnimatePresence>
              </motion.div>
            ) : (
              <Card>
                <CardBody className="py-12 text-center text-sm text-ink-mute">No tools match “{search}”.</CardBody>
              </Card>
            )
          }
        </QueryState>

        <div className="grid gap-6 lg:grid-cols-2">
          <QuickArea />
          <Card className="relative overflow-hidden">
            <div aria-hidden className="absolute inset-0 bg-mesh opacity-60" />
            <CardBody className="relative flex h-full flex-col justify-between gap-6">
              <div>
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-700 text-white">
                  <Cpu className="h-5 w-5" />
                </span>
                <h3 className="mt-4 font-display text-xl font-bold">Every tool is an MCP tool</h3>
                <p className="mt-2 text-sm text-ink-mute dark:text-slate-400">
                  Claude, ChatGPT or Cursor can call these calculators directly through the portal’s Model Context Protocol server — the same engines, the same numbers.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <ButtonLink to="/ai/mcp" icon={<Cpu className="h-4 w-4" />}>
                  Open MCP console
                </ButtonLink>
                <ButtonLink to="/ai" variant="outline" icon={<Calculator className="h-4 w-4" />}>
                  Ask the AI
                </ButtonLink>
              </div>
            </CardBody>
          </Card>
        </div>

        {ov.data?.config.disclaimer && <p className="text-xs text-ink-mute">{ov.data.config.disclaimer}</p>}
        {ov.data?.by_phase && (
          <div className="flex flex-wrap gap-2 text-xs text-ink-mute">
            {Object.entries(ov.data.by_phase).map(([k, v]) => (
              <Badge key={k} tone="gray">
                {titleCase(k)}: {v}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
