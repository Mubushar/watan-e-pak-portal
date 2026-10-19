import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Activity, ArrowRight, BadgePercent, Banknote, BarChart3, Building2, Compass, Gauge, Landmark, LineChart, Newspaper, PieChart, Scale, Sparkles, Target, TrendingDown, TrendingUp, Trophy } from "lucide-react";
import type { City, PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { compact, num, pct, pkrShort, titleCase } from "@/lib/format";
import { HERO, cityImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { Badge, ButtonLink, Card, CardBody, CardHeader, DataTable, ErrorState, PageHeader, QueryState, ScoreRing, Skeleton, StatCard, type Column } from "@/components/ui";
import { Bars, Donut, Legendish } from "@/components/ui/charts";
import { PropertyRow } from "@/components/property/PropertyCard";
import { AdSlot } from "@/components/ads/AdSlot";
import { FactorBars, FilterChip, ForecastChart, SENTIMENT_COLOR, bandTone, entriesToDonut } from "@/components/gis/kit";
import type { MarketIntelligence, MarketTrends, NewsImpact } from "@/components/gis/types";

interface PortalStats {
  inventory: Record<string, number>;
  portfolio: { total_market_value: number; avg_price: number; by_city: { city: string; properties: number; value: number }[]; by_category: Record<string, number> };
}
interface Bargain {
  id: string;
  title: string;
  group: string;
  price: number;
  group_mean: number;
  z_score: number;
  deviation_pct: number;
  tag: string;
}
interface InvestPick {
  id: string;
  title: string;
  city: string;
  cap_rate: number;
  dscr: number;
  irr: number | null;
  cash_flow: number;
  score: number;
  grade: string;
  rank: number;
}

const fade = { initial: { opacity: 0, y: 16 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-60px" }, transition: { duration: 0.45 } };

export default function Insights() {
  const citiesQ = useApi<{ cities: City[] }>("/cities");
  const cities = citiesQ.data?.cities ?? [];
  const [city, setCity] = useState<string>("");
  useEffect(() => {
    if (!city && cities.length) setCity(cities[0]!.name);
  }, [cities, city]);

  const trendsQ = useApi<MarketTrends>(city ? "/portal/market-trends" : null, { city });
  const miCityQ = useApi<MarketIntelligence>(city ? "/property-intelligence/market-intelligence" : null, { region: city });
  const statsQ = useApi<PortalStats>("/portal/statistics");
  const impactQ = useApi<NewsImpact>("/news/impact");
  const miQ = useApi<MarketIntelligence>("/property-intelligence/market-intelligence");
  const anomQ = useApi<{ bargains: Bargain[]; all: Bargain[]; scanned: number; bargain_count: number }>("/intelligence/buyer/anomalies");
  const screenQ = useApi<{ top_picks: InvestPick[]; considered: number; passed: number; pass_rate_pct: number }>("/intelligence/investment/screen", { limit: 10 });
  const propsQ = useApi<PropertyList>("/properties", { limit: 200 });
  const propById = useMemo(() => new Map((propsQ.data?.results ?? []).map((p) => [p.id, p])), [propsQ.data]);

  const t = trendsQ.data;
  const cityImg = cityImage(city);

  return (
    <div className="pb-16">
      <PageHeader
        image={HERO.aiMap}
        eyebrow="Market intelligence"
        title={
          <>
            Pakistan property <span className="text-gradient">insights</span>
          </>
        }
        subtitle="Live pricing, composite market health, factor scores and five-year scenarios — computed from the portal's listing book, news flow and GIS engine."
        crumbs={[{ label: "Home", to: "/" }, { label: "Insights" }]}
        actions={
          <>
            <ButtonLink to="/map" variant="gold" icon={<Compass className="h-4 w-4" />}>
              Open GIS explorer
            </ButtonLink>
            <ButtonLink to="/news" variant="outline" className="!border-white/30 !bg-white/10 !text-white hover:!bg-white/20" icon={<Newspaper className="h-4 w-4" />}>
              News impact
            </ButtonLink>
          </>
        }
      />

      {/* city switcher */}
      <div className="sticky top-[72px] z-30 border-b border-black/5 bg-white/80 backdrop-blur-xl dark:border-white/10 dark:bg-[#0b1a12]/80">
        <div className="container flex items-center gap-3 py-3">
          <span className="hidden text-xs font-bold uppercase tracking-wider text-ink-mute sm:block">City</span>
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto">
            {citiesQ.isLoading
              ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8 w-24 rounded-full" />)
              : cities.map((c) => (
                  <FilterChip key={c.id} active={city === c.name} onClick={() => setCity(c.name)} count={c.properties}>
                    {c.name}
                  </FilterChip>
                ))}
          </div>
          {city && (
            <Link to={`/cities/${encodeURIComponent(city)}`} className="ms-auto hidden shrink-0 items-center gap-1 text-xs font-semibold text-brand-700 hover:underline sm:inline-flex dark:text-brand-300">
              {city} profile <ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" />
            </Link>
          )}
        </div>
      </div>

      <div className="container mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-6">
          {citiesQ.error && <ErrorState error={citiesQ.error} onRetry={() => citiesQ.refetch()} />}

          {/* ---------------------------------------------------------- KPIs */}
          {trendsQ.isLoading || !city ? (
            <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : trendsQ.error ? (
            <ErrorState error={trendsQ.error} onRetry={() => trendsQ.refetch()} />
          ) : t ? (
            <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
              <StatCard label="Average price" value={pkrShort(t.pricing.avg_price)} icon={<Banknote className="h-5 w-5" />} hint={`${t.supply.listings} listings`} />
              <StatCard label="Median price" value={pkrShort(t.pricing.median_price)} icon={<Scale className="h-5 w-5" />} tone="gold" />
              <StatCard label="Price / marla" value={pkrShort(t.pricing.price_per_marla)} icon={<Target className="h-5 w-5" />} tone="blue" delta={t.forecast.base_cagr * 100} hint="base CAGR" />
              <StatCard label="Total value" value={pkrShort(t.pricing.total_market_value)} icon={<Landmark className="h-5 w-5" />} tone="purple" hint={t.yield ? `${pct(t.yield.blended_yield)} yield` : undefined} />
            </div>
          ) : null}

          {/* ---------------------------------------------------------- index + factors */}
          {t && (
            <motion.div {...fade} className="grid gap-6 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
              <Card className="relative overflow-hidden">
                <img src={cityImg} alt="" className="absolute inset-0 h-full w-full object-cover opacity-20" />
                <div className="absolute inset-0 bg-gradient-to-br from-brand-950/95 via-brand-900/90 to-brand-800/80" />
                <div className="relative flex h-full flex-col p-6 text-white">
                  <p className="section-eyebrow !text-gold-300">Composite market index</p>
                  <p className="mt-1 font-display text-2xl font-bold">{city}</p>
                  <div className="my-5 flex items-center gap-5">
                    <div className="rounded-full bg-white p-1.5 shadow-glow dark:bg-[#0d1f16]">
                      <ScoreRing value={t.factors.index.composite} size={112} stroke={10} label="index" />
                    </div>
                    <div className="space-y-2">
                      <Badge tone={bandTone(t.factors.index.band)} className="text-sm capitalize">
                        {t.factors.index.band}
                      </Badge>
                      {miCityQ.data && (
                        <p className="flex items-center gap-1.5 text-sm font-semibold capitalize text-white/90">
                          {miCityQ.data.direction === "expanding" ? <TrendingUp className="h-4 w-4 text-emerald-300" /> : miCityQ.data.direction === "contracting" ? <TrendingDown className="h-4 w-4 text-red-300" /> : <Activity className="h-4 w-4 text-gold-300" />}
                          {miCityQ.data.direction} market
                        </p>
                      )}
                      <p className="text-xs text-white/70">Base CAGR {pct(t.forecast.base_cagr)}</p>
                    </div>
                  </div>
                  {miCityQ.data?.recommendation && (
                    <p className="mt-auto rounded-xl bg-white/10 p-3 text-sm text-white/90 backdrop-blur">
                      <Sparkles className="me-1.5 inline h-4 w-4 text-gold-300" />
                      {titleCase(miCityQ.data.recommendation.split(" — ")[0])}
                      {miCityQ.data.recommendation.includes(" — ") && <span className="text-white/70"> — {miCityQ.data.recommendation.split(" — ")[1]}</span>}
                    </p>
                  )}
                </div>
              </Card>
              <Card>
                <CardHeader title="Factor scores" subtitle="Seven weighted drivers behind the composite index" icon={<Gauge className="h-5 w-5" />} />
                <CardBody>
                  <FactorBars scores={t.factors.scores} weights={t.factors.index.weights} />
                </CardBody>
              </Card>
            </motion.div>
          )}

          {/* ---------------------------------------------------------- forecast */}
          {t && (
            <motion.div {...fade}>
              <Card>
                <CardHeader title="Five-year price-per-marla scenarios" subtitle={`${city} · optimistic, base and pessimistic paths`} icon={<LineChart className="h-5 w-5" />} />
                <CardBody>
                  <ForecastChart scenarios={t.forecast.scenarios} height={300} />
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {(["optimistic", "base", "pessimistic", "stress"] as const).map((k) => {
                      const s = t.forecast.scenarios[k];
                      if (!s) return null;
                      const last = s.series[s.series.length - 1];
                      return (
                        <div key={k} className="rounded-xl bg-brand-50/60 p-3 dark:bg-white/5">
                          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">
                            {s.label} · {Math.round(s.probability * 100)}%
                          </p>
                          <p className={cn("mt-0.5 font-display text-lg font-bold", s.price_cagr >= 0 ? "text-brand-700 dark:text-brand-300" : "text-red-600")}>{pct(s.price_cagr)} / yr</p>
                          {last && <p className="text-[11px] text-ink-mute">{pkrShort(last.price_per_marla)} by {last.year}</p>}
                        </div>
                      );
                    })}
                  </div>
                </CardBody>
              </Card>
            </motion.div>
          )}

          {/* ---------------------------------------------------------- news + supply */}
          {t && (
            <motion.div {...fade} className="grid gap-6 md:grid-cols-2">
              <Card>
                <CardHeader title="News sentiment" subtitle={`${t.news.count} stories feeding the ${city} outlook`} icon={<Newspaper className="h-5 w-5" />} action={<Badge tone={t.news.net_sentiment === "positive" ? "green" : t.news.net_sentiment === "negative" ? "red" : "gray"}>{t.news.net_sentiment}</Badge>} />
                <CardBody className="space-y-4">
                  <div className="flex h-3 overflow-hidden rounded-full">
                    {(["positive", "neutral", "negative"] as const).map((k) =>
                      t.news[k] ? <motion.div key={k} initial={{ width: 0 }} whileInView={{ width: `${(t.news[k] / Math.max(1, t.news.count)) * 100}%` }} viewport={{ once: true }} transition={{ duration: 0.8 }} style={{ background: SENTIMENT_COLOR[k] }} /> : null,
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    {(["positive", "neutral", "negative"] as const).map((k) => (
                      <div key={k} className="rounded-xl bg-black/[.03] py-3 dark:bg-white/5">
                        <p className="font-display text-2xl font-bold" style={{ color: SENTIMENT_COLOR[k] }}>
                          {t.news[k]}
                        </p>
                        <p className="text-[11px] font-semibold capitalize text-ink-mute">{k}</p>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between rounded-xl border border-black/5 px-4 py-3 text-sm dark:border-white/10">
                    <span className="text-ink-mute">Average impact</span>
                    <span className={cn("font-bold", t.news.avg_impact >= 0 ? "text-emerald-600" : "text-red-600")}>{t.news.avg_impact > 0 ? "+" : ""}{num(t.news.avg_impact, 1)}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl border border-black/5 px-4 py-3 text-sm dark:border-white/10">
                    <span className="text-ink-mute">Momentum on outlook</span>
                    <span className="font-bold text-ink dark:text-white">{pct(t.news.momentum)}</span>
                  </div>
                </CardBody>
              </Card>
              <Card>
                <CardHeader title="Supply by category" subtitle={`${t.supply.listings} active listings`} icon={<PieChart className="h-5 w-5" />} />
                <CardBody>
                  {Object.keys(t.supply.by_category).length ? (
                    <>
                      <Donut
                        data={entriesToDonut(t.supply.by_category)}
                        height={210}
                        format={(v) => `${v} listings`}
                        center={
                          <>
                            <span className="font-display text-3xl font-bold text-ink dark:text-white">{t.supply.listings}</span>
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-mute">listings</span>
                          </>
                        }
                      />
                      <div className="mt-4">
                        <Legendish data={entriesToDonut(t.supply.by_category)} />
                      </div>
                      <div className="mt-4 flex flex-wrap gap-1.5">
                        {Object.entries(t.supply.by_use_type).map(([k, v]) => (
                          <Badge key={k} tone={k === "commercial" ? "blue" : k === "residential" ? "green" : "gold"}>
                            {titleCase(k)} · {v}
                          </Badge>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="py-10 text-center text-sm text-ink-mute">No listings in {city} yet.</p>
                  )}
                </CardBody>
              </Card>
            </motion.div>
          )}

          {/* ========================================================== national */}
          <div className="pt-6">
            <p className="section-eyebrow">Nationwide</p>
            <h2 className="section-title mt-1 !text-2xl sm:!text-3xl">The national picture</h2>
          </div>

          <motion.div {...fade}>
            <QueryState q={miQ} skeleton={<Skeleton className="h-36" />}>
              {(mi) => (
                <div className="relative overflow-hidden rounded-2xl bg-brand-gradient p-6 text-white shadow-soft">
                  <div className="absolute -end-16 -top-16 h-56 w-56 rounded-full bg-gold-400/20 blur-3xl" />
                  <div className="relative grid gap-6 sm:grid-cols-[auto_1fr] sm:items-center">
                    <div className="flex items-center gap-4">
                      <div className="rounded-full bg-white p-1.5 dark:bg-[#0d1f16]">
                        <ScoreRing value={mi.market_index.composite} size={96} label="national" />
                      </div>
                      <div>
                        <Badge tone={bandTone(mi.market_index.band)} className="capitalize">
                          {mi.market_index.band}
                        </Badge>
                        <p className="mt-1.5 text-sm font-semibold capitalize">{mi.direction} market</p>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {[
                        ["Avg price", pkrShort(mi.pricing.avg_price)],
                        ["Median", pkrShort(mi.pricing.median_price)],
                        ["Listings", mi.supply.listings],
                        ["Blended yield", mi.yield ? pct(mi.yield.blended_yield) : "—"],
                      ].map(([l, v]) => (
                        <div key={String(l)} className="rounded-xl bg-white/10 p-3 backdrop-blur">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-gold-200">{l}</p>
                          <p className="mt-0.5 font-display text-lg font-bold">{v}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <p className="relative mt-4 text-sm text-white/85">
                    <Sparkles className="me-1.5 inline h-4 w-4 text-gold-300" />
                    {mi.recommendation}
                  </p>
                </div>
              )}
            </QueryState>
          </motion.div>

          <motion.div {...fade} className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader title="Portfolio value by city" subtitle="Listed market value (PKR)" icon={<BarChart3 className="h-5 w-5" />} />
              <CardBody>
                <QueryState q={statsQ} skeleton={<Skeleton className="h-64" />}>
                  {(s) => (
                    <>
                      <Bars data={s.portfolio.by_city as unknown as Record<string, unknown>[]} x="city" series={[{ key: "value", label: "Value" }]} height={240} format={(v) => pkrShort(v, false)} colorByIndex />
                      <div className="mt-3 flex flex-wrap gap-3 text-xs text-ink-mute">
                        {s.portfolio.by_city.map((c) => (
                          <span key={c.city}>
                            <b className="text-ink dark:text-white">{c.city}</b> · {c.properties} listings
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                </QueryState>
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="News impact by category" subtitle="Average impact score, last 120 days" icon={<Activity className="h-5 w-5" />} />
              <CardBody>
                <QueryState q={impactQ} skeleton={<Skeleton className="h-64" />}>
                  {(im) => {
                    const rows = Object.entries(im.by_category)
                      .map(([k, v]) => ({ category: titleCase(k), impact: v.avg_impact, count: v.count }))
                      .sort((a, b) => b.impact - a.impact);
                    return (
                      <>
                        <Bars data={rows} x="category" series={[{ key: "impact", label: "Avg impact" }]} height={240} horizontal format={(v) => num(v, 0)} colorByIndex />
                        {im.effect_on_outlook && (
                          <p className="mt-3 text-xs text-ink-mute">
                            Momentum <b className="text-ink dark:text-white">{pct(im.effect_on_outlook.momentum)}</b> — {im.effect_on_outlook.interpretation}.
                          </p>
                        )}
                      </>
                    );
                  }}
                </QueryState>
              </CardBody>
            </Card>
          </motion.div>

          <motion.div {...fade} className="grid gap-6 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <Card>
              <CardHeader title="Bargain radar" subtitle="Listings priced well below their city mean" icon={<BadgePercent className="h-5 w-5" />} />
              <CardBody className="p-3">
                <QueryState q={anomQ} skeleton={<Skeleton className="h-60" />}>
                  {(a) => {
                    const list = (a.bargains.length ? a.bargains : a.all.slice(0, 5)).slice(0, 6);
                    return (
                      <div className="space-y-1">
                        <p className="px-2 pb-1 text-xs text-ink-mute">
                          {a.bargain_count} flagged of {a.scanned} scanned
                        </p>
                        {list.map((b) => {
                          const p = propById.get(b.id);
                          return (
                            <PropertyRow
                              key={b.id}
                              p={{ ...(p ?? {}), id: b.id, title: b.title, price: b.price, category: p?.category ?? "house", city_name: p?.city_name ?? b.group }}
                              extra={
                                <span className="flex shrink-0 flex-col items-end gap-1">
                                  <Badge tone={b.tag === "underpriced" ? "green" : "gray"}>{b.deviation_pct.toFixed(0)}%</Badge>
                                  <span className="text-[10px] text-ink-mute">z {b.z_score}</span>
                                </span>
                              }
                            />
                          );
                        })}
                      </div>
                    );
                  }}
                </QueryState>
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Investment screen — top picks" subtitle="Risk-adjusted shortlist at 4.5% gross yield, 16% financing" icon={<Trophy className="h-5 w-5" />} />
              <CardBody className="p-0">
                <QueryState q={screenQ} skeleton={<Skeleton className="m-5 h-60" />}>
                  {(s) => <DataTable rows={s.top_picks} columns={PICK_COLUMNS} pageSize={6} dense />}
                </QueryState>
              </CardBody>
            </Card>
          </motion.div>
        </div>

        {/* ---------------------------------------------------------- sidebar */}
        <aside className="space-y-6 lg:sticky lg:top-[140px] lg:self-start">
          <AdSlot slot="sidebar" />
          <Card>
            <CardHeader title="Explore a city" icon={<Building2 className="h-5 w-5" />} />
            <CardBody className="space-y-2 p-3">
              {cities.map((c) => (
                <Link key={c.id} to={`/cities/${encodeURIComponent(c.name)}`} className="group flex items-center gap-3 rounded-xl p-2 transition hover:bg-brand-50 dark:hover:bg-white/5">
                  <img src={cityImage(c.name, c.image)} alt="" className="h-12 w-16 rounded-lg object-cover" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-ink group-hover:text-brand-700 dark:text-white">{c.name}</span>
                    <span className="block text-[11px] text-ink-mute">
                      {c.schemes} societies · {compact(c.properties)} listings
                    </span>
                  </span>
                  <ArrowRight className="h-4 w-4 text-ink-mute transition group-hover:translate-x-0.5 rtl:rotate-180" />
                </Link>
              ))}
            </CardBody>
          </Card>
        </aside>
      </div>
    </div>
  );
}

const GRADE_TONE: Record<string, "green" | "gold" | "orange" | "red" | "gray"> = { A: "green", B: "green", C: "gold", D: "orange", E: "red", F: "red" };

const PICK_COLUMNS: Column<InvestPick>[] = [
  { key: "rank", header: "#", align: "center", className: "w-10" },
  {
    key: "title",
    header: "Listing",
    render: (r) => (
      <Link to={`/properties/${r.id}`} className="font-semibold text-ink hover:text-brand-700 dark:text-white">
        {r.title}
        <span className="block text-[11px] font-normal text-ink-mute">{r.city}</span>
      </Link>
    ),
  },
  { key: "cap_rate", header: "Cap rate", align: "right", render: (r) => pct(r.cap_rate) },
  { key: "dscr", header: "DSCR", align: "right", render: (r) => <span className={r.dscr >= 1.2 ? "text-emerald-600" : "text-red-600"}>{num(r.dscr, 2)}</span> },
  { key: "cash_flow", header: "Cash flow", align: "right", render: (r) => <span className={r.cash_flow >= 0 ? "text-emerald-600" : "text-red-600"}>{pkrShort(r.cash_flow, false)}</span> },
  { key: "grade", header: "Grade", align: "center", render: (r) => <Badge tone={GRADE_TONE[r.grade] ?? "gray"}>{r.grade}</Badge> },
];
