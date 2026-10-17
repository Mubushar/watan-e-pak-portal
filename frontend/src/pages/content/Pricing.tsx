import { useMemo, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Bot, Building, Check, Crown, Gauge, HelpCircle, Home, KeyRound, LineChart, Megaphone, Minus, Server, Sparkles, Target, Users, Wand2 } from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { post } from "@/lib/api";
import { compact, num, titleCase } from "@/lib/format";
import { HERO } from "@/lib/images";
import { cn } from "@/lib/utils";
import { Badge, Button, ButtonLink, Card, Field, Input, PageHeader, QueryState, Section, Select, Skeleton, Slider } from "@/components/ui";
import { Accordion, Chip, ok, stagger } from "@/components/collab/kit";

interface Plan {
  key: string;
  product: string;
  name: string;
  price: number;
  interval: string;
  included_units: number;
  overage_rate: number;
  seats: number;
  white_label?: boolean;
}
interface Product {
  key: string;
  name: string;
  priority: string;
  segment: string;
  pricing_models: string[];
  positioning: string;
  agents: string[];
  price_from: number;
  unit: string;
  model_labels: string[];
  plan_count: number;
}
interface Matrix {
  currency: string;
  models: Record<string, string>;
  rows: { product: string; key: string; priority: string; models: string[]; from: number; unit: string }[];
  gtm?: { priorities: { tier: string; product: string; reason: string }[]; principles: { name: string; detail: string }[] };
}
interface Recommendation {
  segment: string;
  seats: number;
  expected_calls: number;
  currency: string;
  recommended_plan: { plan: string; plan_key: string; product: string; monthly_estimate: number; included_units: number; overage_rate: number; fit: number } | null;
  alternatives: { plan: string; plan_key: string; product: string; monthly_estimate: number; included_units: number; overage_rate: number; fit: number }[];
}

const PRODUCT_ICON: Record<string, ReactNode> = {
  property_intelligence_mcp: <Server className="h-5 w-5" />,
  broker_ai_workspace: <Users className="h-5 w-5" />,
  mcp_for_brokers: <Bot className="h-5 w-5" />,
  conversational_homebuying_agent: <Home className="h-5 w-5" />,
  seller_pricing_marketing_agent: <Target className="h-5 w-5" />,
  autonomous_leasing_agent: <KeyRound className="h-5 w-5" />,
  agentic_investment_screener: <LineChart className="h-5 w-5" />,
  ai_marketing_conductor: <Megaphone className="h-5 w-5" />,
};
const PRIORITY_TONE: Record<string, "gold" | "green" | "blue"> = { P0: "gold", P1: "green", P2: "blue" };

const usd = (v: number, digits = 0) => `$${v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: Math.max(digits, v < 1 ? 3 : 2) })}`;

const FAQ = [
  { q: "Which currency are plans billed in?", a: "Platform products are priced in US dollars so that enterprise and overseas clients get one consistent rate card. Property transactions on the portal itself remain in Pakistani rupees." },
  { q: "What counts as a unit?", a: "A unit is the thing the product meters — an MCP tool call, a qualified lead, a listing or a rental unit. Each plan includes a monthly allowance; anything above it is billed at the overage rate shown on the card." },
  { q: "Can I mix subscription and usage pricing?", a: "Yes. Hybrid plans combine a seat subscription with usage overage and an optional performance share, so you only pay more when the platform is doing more work for you." },
  { q: "Do per-seat plans scale with my team?", a: "Per-seat plans are multiplied by the number of seats you need. Team plans include several seats at a lower per-seat price." },
  { q: "Is there a free tier?", a: "The MCP Starter plan is free and includes 1,000 tool calls a month — enough to connect an AI client and evaluate the property-intelligence tools." },
  { q: "Can I white-label the platform?", a: "The Enterprise licence includes white-label rights, 50 seats and a million included calls a month. Contact sales for custom terms." },
];

export default function Pricing() {
  const plans = useApi<{ count: number; plans: Plan[] }>("/commercial/plans");
  const products = useApi<{ count: number; products: Product[] }>("/commercial/products");
  const matrix = useApi<Matrix>("/commercial/pricing");
  const [product, setProduct] = useState("all");
  const [rec, setRec] = useState<Recommendation | null>(null);

  const prodBy = useMemo(() => Object.fromEntries((products.data?.products ?? []).map((p) => [p.key, p])), [products.data]);
  const shown = (plans.data?.plans ?? []).filter((p) => product === "all" || p.product === product);
  const highlight = rec?.recommended_plan?.plan_key ?? (plans.data?.plans.find((p) => /growth/.test(p.key)) ?? plans.data?.plans.find((p) => /team|pro/.test(p.key)))?.key;

  return (
    <div>
      <PageHeader
        image={HERO.aiMap}
        eyebrow="Products & pricing"
        title={
          <>
            Agentic real-estate software, <span className="text-gradient">priced to scale.</span>
          </>
        }
        subtitle="Subscriptions, metered usage and performance share — pick a plan, or let us recommend one for your team."
        crumbs={[{ label: "Home", to: "/" }, { label: "Pricing" }]}
        actions={
          <>
            <a href="#recommend" className="btn btn-gold btn-lg">
              <Wand2 className="h-4 w-4" /> Find my plan
            </a>
            <a href="#products" className="btn btn-lg bg-white/10 text-white hover:bg-white/20">
              Browse products
            </a>
          </>
        }
      />

      {/* plans */}
      <Section eyebrow="Plans" title="Simple, transparent plans" subtitle="Every plan includes a monthly allowance; overage is billed per unit at the rate shown.">
        <div className="no-scrollbar -mx-4 mb-8 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0">
          <Chip active={product === "all"} onClick={() => setProduct("all")} className="shrink-0">
            All plans
          </Chip>
          {(products.data?.products ?? [])
            .filter((p) => p.plan_count > 0)
            .map((p) => (
              <Chip key={p.key} active={product === p.key} onClick={() => setProduct(p.key)} className="shrink-0">
                {p.name}
              </Chip>
            ))}
        </div>
        <QueryState
          q={plans}
          skeleton={
            <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-[420px]" />
              ))}
            </div>
          }
        >
          {() => (
            <motion.div variants={stagger.container} initial="hidden" animate="show" key={product} className="grid items-stretch gap-6 md:grid-cols-2 xl:grid-cols-3">
              {shown.map((p) => (
                <motion.div key={p.key} variants={stagger.item}>
                  <PlanCard plan={p} product={prodBy[p.product]} featured={p.key === highlight} recommended={rec?.recommended_plan?.plan_key === p.key} />
                </motion.div>
              ))}
            </motion.div>
          )}
        </QueryState>
      </Section>

      {/* recommender */}
      <section id="recommend" className="scroll-mt-24 bg-brand-50/50 py-14 dark:bg-white/[.02]">
        <div className="container grid gap-8 lg:grid-cols-2">
          <div>
            <p className="section-eyebrow">Plan finder</p>
            <h2 className="section-title mt-2">Find my plan</h2>
            <p className="mt-2 text-ink-mute">Tell us who you are and how much you expect to use the platform. We’ll recommend the best-fit plan and estimate your monthly bill.</p>
            <Recommender products={products.data?.products ?? []} onResult={setRec} />
          </div>
          <div className="lg:pt-14">
            {rec?.recommended_plan ? (
              <motion.div key={rec.recommended_plan.plan_key + rec.seats + rec.expected_calls} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <div className="relative overflow-hidden rounded-3xl bg-brand-gradient p-7 text-white shadow-glow">
                  <div className="pointer-events-none absolute -end-12 -top-12 h-48 w-48 rounded-full bg-gold-400/30 blur-3xl" />
                  <p className="inline-flex items-center gap-1.5 rounded-full bg-gold-gradient px-3 py-1 text-xs font-bold text-brand-950">
                    <Crown className="h-3.5 w-3.5" /> Recommended for you
                  </p>
                  <h3 className="mt-4 font-display text-3xl font-bold">{rec.recommended_plan.plan}</h3>
                  <p className="text-white/70">{rec.recommended_plan.product}</p>
                  <p className="mt-6 text-xs font-semibold uppercase tracking-wider text-white/60">Estimated monthly bill</p>
                  <p className="font-display text-5xl font-bold text-gold-300">
                    {usd(rec.recommended_plan.monthly_estimate)}
                    <span className="text-base font-medium text-white/60"> / month</span>
                  </p>
                  <div className="mt-5 grid grid-cols-3 gap-3 text-center text-sm">
                    <div className="rounded-2xl bg-white/10 p-3">
                      <p className="font-bold">{rec.seats}</p>
                      <p className="text-[10px] uppercase text-white/60">seats</p>
                    </div>
                    <div className="rounded-2xl bg-white/10 p-3">
                      <p className="font-bold">{compact(rec.recommended_plan.included_units)}</p>
                      <p className="text-[10px] uppercase text-white/60">included</p>
                    </div>
                    <div className="rounded-2xl bg-white/10 p-3">
                      <p className="font-bold">{usd(rec.recommended_plan.overage_rate, 2)}</p>
                      <p className="text-[10px] uppercase text-white/60">overage</p>
                    </div>
                  </div>
                </div>
                {rec.alternatives.length > 1 && (
                  <Card className="mt-4 p-4">
                    <p className="label">Alternatives</p>
                    <ul className="divide-y divide-black/5 dark:divide-white/10">
                      {rec.alternatives
                        .filter((a) => a.plan_key !== rec.recommended_plan?.plan_key)
                        .map((a) => (
                          <li key={a.plan_key} className="flex items-center justify-between gap-3 py-2 text-sm">
                            <span className="min-w-0">
                              <span className="block truncate font-semibold">{a.plan}</span>
                              <span className="block truncate text-xs text-ink-mute">
                                {a.product} · fit {Math.round(a.fit * 100)}%
                              </span>
                            </span>
                            <span className="shrink-0 font-display font-bold">{usd(a.monthly_estimate)}</span>
                          </li>
                        ))}
                    </ul>
                  </Card>
                )}
              </motion.div>
            ) : (
              <div className="flex h-full min-h-[300px] flex-col items-center justify-center rounded-3xl border-2 border-dashed border-brand-200 p-8 text-center dark:border-white/10">
                <Sparkles className="h-10 w-10 text-gold-500" />
                <p className="mt-3 font-display text-lg font-semibold">Your recommendation appears here</p>
                <p className="mt-1 max-w-xs text-sm text-ink-mute">Fill in the form and press “Recommend a plan”.</p>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* products */}
      <div id="products" className="scroll-mt-20">
        <Section eyebrow="Catalogue" title="The product line-up" subtitle="Each product is a module of the Arz-e-Pak Agentic OS — built on the same MCP server and data.">
          <QueryState q={products} skeleton={<Skeleton className="h-80" />}>
            {(d) => (
              <motion.div variants={stagger.container} initial="hidden" whileInView="show" viewport={{ once: true }} className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
                {[...d.products]
                  .sort((a, b) => a.priority.localeCompare(b.priority))
                  .map((p) => (
                    <motion.div key={p.key} variants={stagger.item} className="card group flex flex-col p-5 transition hover:-translate-y-1 hover:shadow-glow">
                      <div className="flex items-start justify-between">
                        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-soft transition group-hover:scale-110">{PRODUCT_ICON[p.key] ?? <Building className="h-5 w-5" />}</span>
                        <Badge tone={PRIORITY_TONE[p.priority] ?? "gray"}>{p.priority}</Badge>
                      </div>
                      <h3 className="mt-4 font-display text-base font-semibold leading-snug">{p.name}</h3>
                      <p className="text-xs font-semibold uppercase tracking-wide text-gold-600 dark:text-gold-300">{p.segment}</p>
                      <p className="mt-2 flex-1 text-sm text-ink-mute">{p.positioning}</p>
                      <div className="mt-4 flex flex-wrap gap-1.5">
                        {p.pricing_models.map((m) => (
                          <Badge key={m} tone="gray">
                            {m}
                          </Badge>
                        ))}
                      </div>
                      <div className="mt-4 flex items-end justify-between border-t border-black/5 pt-3 dark:border-white/10">
                        <div>
                          <p className="text-[10px] uppercase text-ink-mute">From</p>
                          <p className="font-display text-xl font-bold">{p.price_from ? usd(p.price_from, p.price_from < 1 ? 2 : 0) : "Free"}</p>
                          <p className="text-[11px] text-ink-mute">{p.unit}</p>
                        </div>
                        <span className="text-[11px] text-ink-mute">{p.agents.length} agents</span>
                      </div>
                    </motion.div>
                  ))}
              </motion.div>
            )}
          </QueryState>
        </Section>
      </div>

      {/* matrix */}
      <Section eyebrow="Compare" title="Pricing models at a glance" className="!pt-0">
        <QueryState q={matrix} skeleton={<Skeleton className="h-80" />}>
          {(m) => {
            const models = Object.keys(m.models);
            return (
              <Card className="overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-sm">
                    <thead>
                      <tr className="border-b border-black/5 bg-brand-50/60 text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:border-white/10 dark:bg-white/5">
                        <th className="sticky start-0 bg-brand-50 px-5 py-3 text-start dark:bg-[#10241a]">Product</th>
                        {models.map((k) => (
                          <th key={k} className="px-3 py-3 text-center" title={m.models[k]}>
                            {titleCase(k)}
                          </th>
                        ))}
                        <th className="px-5 py-3 text-end">From</th>
                      </tr>
                    </thead>
                    <tbody>
                      {m.rows.map((r) => (
                        <tr key={r.key} className="border-b border-black/5 transition last:border-0 hover:bg-brand-50/40 dark:border-white/5 dark:hover:bg-white/[.03]">
                          <td className="sticky start-0 bg-white px-5 py-3 dark:bg-[#0d1f16]">
                            <div className="flex items-center gap-2">
                              <Badge tone={PRIORITY_TONE[r.priority] ?? "gray"}>{r.priority}</Badge>
                              <span className="font-semibold">{r.product}</span>
                            </div>
                          </td>
                          {models.map((k) => (
                            <td key={k} className="px-3 py-3 text-center">
                              {r.models.includes(k) ? (
                                <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-white">
                                  <Check className="h-3.5 w-3.5" />
                                </span>
                              ) : (
                                <Minus className="mx-auto h-4 w-4 text-ink-mute/40" />
                              )}
                            </td>
                          ))}
                          <td className="whitespace-nowrap px-5 py-3 text-end">
                            <b>{r.from ? usd(r.from, r.from < 1 ? 2 : 0) : "Free"}</b> <span className="text-xs text-ink-mute">{r.unit}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="grid gap-3 border-t border-black/5 p-5 sm:grid-cols-2 lg:grid-cols-5 dark:border-white/10">
                  {models.map((k) => (
                    <div key={k} className="text-xs">
                      <p className="font-semibold">{titleCase(k)}</p>
                      <p className="text-ink-mute">{m.models[k]}</p>
                    </div>
                  ))}
                </div>
              </Card>
            );
          }}
        </QueryState>
      </Section>

      {/* FAQ */}
      <Section eyebrow="FAQ" title="Questions about pricing" className="!pt-0">
        <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
          <Accordion items={FAQ.map((f) => ({ title: f.q, icon: <HelpCircle className="h-4 w-4" />, content: <p className="leading-relaxed">{f.a}</p> }))} />
          <div className="relative overflow-hidden rounded-3xl bg-brand-gradient p-6 text-white shadow-soft">
            <div className="pointer-events-none absolute -end-10 -top-10 h-40 w-40 rounded-full bg-gold-400/30 blur-2xl" />
            <Gauge className="h-8 w-8 text-gold-300" />
            <h3 className="mt-3 font-display text-xl font-bold">Need something custom?</h3>
            <p className="mt-2 text-sm text-white/75">Enterprise licences, white-label deployments and revenue-share partnerships are available.</p>
            <div className="mt-5 flex flex-col gap-2">
              <ButtonLink to="/pages/commercial" variant="gold">
                Read about our products <ArrowRight className="h-4 w-4 rtl:rotate-180" />
              </ButtonLink>
              <ButtonLink to="/ai" className="bg-white/10 text-white hover:bg-white/20" icon={<Bot className="h-4 w-4" />}>
                Ask the AI
              </ButtonLink>
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------- plan card
function PlanCard({ plan, product, featured, recommended }: { plan: Plan; product?: Product; featured?: boolean; recommended?: boolean }) {
  const perSeat = /seat/.test(product?.unit ?? "") || plan.seats > 1;
  const features = [
    plan.included_units ? `${compact(plan.included_units)} ${unitName(product?.unit)} included / month` : "Pay only for what you use",
    plan.overage_rate ? `${usd(plan.overage_rate, 2)} per extra ${unitName(product?.unit, true)}` : "No overage charges",
    `${plan.seats} seat${plan.seats === 1 ? "" : "s"}${plan.seats > 1 ? " included" : ""}`,
    ...(product?.model_labels ?? []).slice(0, 2),
    ...(product?.agents.length ? [`${product.agents.length} AI agents: ${product.agents.slice(0, 3).map((a) => titleCase(a)).join(", ")}${product.agents.length > 3 ? "…" : ""}`] : []),
    ...(plan.white_label ? ["White-label licence"] : []),
  ];
  return (
    <div
      className={cn(
        "relative flex h-full flex-col rounded-3xl p-6 transition duration-300 hover:-translate-y-1",
        featured
          ? "bg-brand-gradient text-white shadow-glow ring-2 ring-gold-400/80 lg:scale-[1.02]"
          : "card hover:shadow-soft",
      )}
    >
      {featured && (
        <>
          <div className="pointer-events-none absolute -inset-px -z-10 rounded-3xl bg-gold-gradient opacity-40 blur-xl" />
          <span className="absolute -top-3 start-1/2 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-gold-gradient px-3 py-1 text-xs font-bold text-brand-950 shadow-glow rtl:translate-x-1/2">
            <Crown className="h-3.5 w-3.5" /> {recommended ? "Recommended for you" : "Most popular"}
          </span>
        </>
      )}
      <div className="flex items-center gap-3">
        <span className={cn("flex h-10 w-10 items-center justify-center rounded-2xl", featured ? "bg-white/15 text-gold-300" : "bg-brand-50 text-brand-700 dark:bg-white/5 dark:text-brand-200")}>
          {PRODUCT_ICON[plan.product] ?? <Building className="h-5 w-5" />}
        </span>
        <div className="min-w-0">
          <h3 className="truncate font-display text-lg font-bold">{plan.name}</h3>
          <p className={cn("truncate text-xs", featured ? "text-white/70" : "text-ink-mute")}>{product?.name ?? titleCase(plan.product)}</p>
        </div>
      </div>
      <div className="mt-6 flex items-end gap-1">
        <span className={cn("font-display text-5xl font-bold", featured ? "text-gold-300" : "text-brand-900 dark:text-white")}>{plan.price ? usd(plan.price) : plan.included_units || !plan.overage_rate ? "Free" : "Usage"}</span>
        {plan.price > 0 && <span className={cn("pb-2 text-sm", featured ? "text-white/70" : "text-ink-mute")}>/ {perSeat && plan.seats === 1 ? "seat / " : ""}{plan.interval === "monthly" ? "mo" : plan.interval}</span>}
      </div>
      <p className={cn("mt-1 text-xs", featured ? "text-white/70" : "text-ink-mute")}>{product?.segment ? `For ${product.segment}` : " "}</p>
      <ul className="mt-6 flex-1 space-y-2.5 text-sm">
        {features.map((f) => (
          <li key={f} className="flex gap-2.5">
            <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full", featured ? "bg-gold-400 text-brand-950" : "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200")}>
              <Check className="h-3 w-3" />
            </span>
            <span className={featured ? "text-white/90" : "text-ink-soft dark:text-slate-300"}>{f}</span>
          </li>
        ))}
      </ul>
      <ButtonLink to={`/signup?plan=${plan.key}`} variant={featured ? "gold" : "outline"} className="mt-7 w-full justify-center">
        {plan.price ? "Start subscription" : "Get started"} <ArrowRight className="h-4 w-4 rtl:rotate-180" />
      </ButtonLink>
    </div>
  );
}

function unitName(unit?: string, singular = false) {
  const u = (unit ?? "").toLowerCase();
  const base = /tool call/.test(u) ? "tool call" : /lead/.test(u) ? "lead" : /listing/.test(u) ? "listing" : /unit/.test(u) ? "rental unit" : /buyer/.test(u) ? "buyer" : "AI call";
  return singular ? base : `${base}s`;
}

// ---------------------------------------------------------------- recommender
function Recommender({ products, onResult }: { products: Product[]; onResult: (r: Recommendation) => void }) {
  const segments = useMemo(() => [...new Set(products.flatMap((p) => p.segment.split("/").map((s) => s.trim())))].filter(Boolean), [products]);
  const [f, setF] = useState({ segment: "brokerage", seats: 5, expected_calls: 20000, product: "" });
  const m = useMutate(() => ok(post<Recommendation>("/commercial/recommend", { segment: f.segment, seats: f.seats, expected_calls: f.expected_calls, product: f.product || null })), {
    onSuccess: onResult,
  });
  return (
    <form
      className="card mt-6 space-y-5 p-6"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
    >
      <Field label="I am a…">
        <div className="flex flex-wrap gap-2">
          {(segments.length ? segments : ["brokerage", "consumer", "investor", "landlord", "platform", "enterprise"]).map((s) => (
            <Chip key={s} active={f.segment === s} onClick={() => setF({ ...f, segment: s })}>
              {titleCase(s)}
            </Chip>
          ))}
        </div>
      </Field>
      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="label !mb-0">Seats</span>
          <span className="font-display text-lg font-bold text-brand-700 dark:text-gold-300">{f.seats}</span>
        </div>
        <Slider value={f.seats} min={1} max={100} onChange={(v) => setF({ ...f, seats: v })} />
      </div>
      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="label !mb-0">Expected calls / units per month</span>
          <span className="font-display text-lg font-bold text-brand-700 dark:text-gold-300">{num(f.expected_calls)}</span>
        </div>
        <Slider value={f.expected_calls} min={0} max={1_000_000} step={1000} onChange={(v) => setF({ ...f, expected_calls: v })} />
        <Input type="number" min={0} value={f.expected_calls} onChange={(e) => setF({ ...f, expected_calls: Math.max(0, Number(e.target.value) || 0) })} className="mt-2" />
      </div>
      <Field label="Limit to a product (optional)">
        <Select value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })}>
          <option value="">Any product</option>
          {products.map((p) => (
            <option key={p.key} value={p.key}>
              {p.name}
            </option>
          ))}
        </Select>
      </Field>
      <Button type="submit" variant="gold" size="lg" className="w-full justify-center" loading={m.isPending} icon={<Wand2 className="h-4 w-4" />}>
        Recommend a plan
      </Button>
    </form>
  );
}
