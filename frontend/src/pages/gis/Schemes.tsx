import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { GeoJSON, Marker, Popup } from "react-leaflet";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  Building2,
  CalendarDays,
  ChevronRight,
  Compass,
  Eye,
  FileBarChart,
  Grid3x3,
  Home,
  LandPlot,
  Layers,
  LineChart,
  MapPin,
  Network,
  Search,
  Sparkles,
  Users,
} from "lucide-react";
import type { Property, PropertyList, Scheme } from "@/types";
import { useApi } from "@/hooks/useApi";
import { compact, num, pct, pkrShort, titleCase } from "@/lib/format";
import { HERO, themedImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Input, JsonView, PageHeader, ScoreRing, Skeleton, StatCard } from "@/components/ui";
import { PropertyCard } from "@/components/property/PropertyCard";
import { PortalMap, pin } from "@/components/map/PortalMap";
import { FactorBars, ForecastChart, MiniStat, ReportButton, ReportModal, bandTone, type ReportRef } from "@/components/gis/kit";
import type { GisAreaAnalysis, HierarchyCity, HierarchyScheme, Scenarios } from "@/components/gis/types";

interface SchemeForecast {
  name: string;
  forecast: {
    horizon_years: number;
    composite_index: number;
    index_band: string;
    factors: Record<string, number>;
    weights: Record<string, number>;
    news_momentum: number;
    base_cagr: number;
    scenarios: Scenarios;
  };
  error?: string;
}

const AREA_TONE: Record<string, "green" | "blue" | "gold" | "purple" | "gray"> = { residential: "green", commercial: "blue", luxury: "gold", mixed: "purple" };

export default function Schemes() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("scheme");
  const select = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("scheme", id);
    else next.delete("scheme");
    setParams(next, { replace: false });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const hierQ = useApi<{ tree: HierarchyCity[] }>("/hierarchy");
  const schemesQ = useApi<{ schemes: Scheme[] }>("/schemes");
  const propsQ = useApi<PropertyList>("/properties", { limit: 200 });
  const schemes = schemesQ.data?.schemes ?? [];
  const scheme = schemes.find((s) => s.id === selected);
  const hScheme = useMemo(() => {
    for (const c of hierQ.data?.tree ?? []) {
      const s = c.schemes.find((x) => x.id === selected);
      if (s) return { ...s, city: c.name };
    }
    return undefined;
  }, [hierQ.data, selected]);

  return (
    <div className="pb-16">
      <PageHeader
        image={HERO.panorama}
        eyebrow="Housing schemes"
        title={
          <>
            Explore every <span className="text-gradient">society & block</span>
          </>
        }
        subtitle="Navigate the City → Scheme → Block hierarchy, see live listings on the map, and open GIS-grade analysis for any scheme."
        crumbs={[{ label: "Home", to: "/" }, { label: "Schemes", to: "/schemes" }, ...(scheme ? [{ label: scheme.name }] : [])]}
      />

      <div className="container mt-8 grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-[96px] lg:self-start">
          <HierarchyTree tree={hierQ.data?.tree} loading={hierQ.isLoading} error={hierQ.error} retry={() => hierQ.refetch()} selected={selected} onSelect={select} />
        </aside>

        <main className="min-w-0">
          <AnimatePresence mode="wait">
            {selected ? (
              <motion.div key={selected} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.3 }}>
                {schemesQ.isLoading ? (
                  <Skeleton className="h-80" />
                ) : schemesQ.error ? (
                  <ErrorState error={schemesQ.error} onRetry={() => schemesQ.refetch()} />
                ) : !scheme ? (
                  <EmptyState title="Scheme not found" hint="It may have been removed — pick another from the tree." action={<Button variant="outline" size="sm" onClick={() => select(null)}>Browse all schemes</Button>} />
                ) : (
                  <SchemeDetail scheme={scheme} h={hScheme} properties={(propsQ.data?.results ?? []).filter((p) => p.scheme_id === scheme.id)} propsLoading={propsQ.isLoading} onBack={() => select(null)} />
                )}
              </motion.div>
            ) : (
              <motion.div key="all" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <BrowseAll schemes={schemes} tree={hierQ.data?.tree} loading={schemesQ.isLoading} error={schemesQ.error} retry={() => schemesQ.refetch()} onSelect={select} />
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

// ======================================================================= tree
function HierarchyTree({
  tree,
  loading,
  error,
  retry,
  selected,
  onSelect,
}: {
  tree?: HierarchyCity[];
  loading: boolean;
  error: unknown;
  retry: () => void;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [mobileOpen, setMobileOpen] = useState(false);

  // expand the city / scheme holding the current selection
  useEffect(() => {
    if (!tree) return;
    setOpen((prev) => {
      const n = new Set(prev);
      if (!prev.size) tree.forEach((c) => n.add(c.id));
      tree.forEach((c) => c.schemes.forEach((s) => s.id === selected && (n.add(c.id), n.add(s.id))));
      return n;
    });
  }, [tree, selected]);

  const toggle = (id: string) =>
    setOpen((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const s = q.trim().toLowerCase();
  const filtered = (tree ?? [])
    .map((c) => ({
      ...c,
      schemes: c.schemes.filter((sc) => !s || c.name.toLowerCase().includes(s) || sc.name.toLowerCase().includes(s) || sc.blocks.some((b) => b.name.toLowerCase().includes(s))),
    }))
    .filter((c) => !s || c.schemes.length || c.name.toLowerCase().includes(s));

  return (
    <Card className="overflow-hidden">
      <button className="flex w-full items-center justify-between gap-3 border-b border-black/5 px-4 py-3.5 text-start dark:border-white/10 lg:pointer-events-none" onClick={() => setMobileOpen((o) => !o)}>
        <span className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-gradient text-white">
            <Network className="h-4 w-4" />
          </span>
          <span>
            <span className="block font-display text-sm font-bold text-ink dark:text-white">Hierarchy</span>
            <span className="block text-[11px] text-ink-mute">City → Scheme → Block</span>
          </span>
        </span>
        <ChevronRight className={cn("h-4 w-4 text-ink-mute transition lg:hidden", mobileOpen && "rotate-90")} />
      </button>
      <div className={cn("p-3", !mobileOpen && "hidden lg:block")}>
        <Input icon={<Search className="h-4 w-4" />} placeholder="Filter schemes or blocks" value={q} onChange={(e) => setQ(e.target.value)} />
        <button
          onClick={() => onSelect(null)}
          className={cn("mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm font-semibold transition", !selected ? "bg-brand-700 text-white" : "text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/5")}
        >
          <Grid3x3 className="h-4 w-4" /> All schemes
        </button>
        <div className="mt-1 max-h-[60vh] overflow-y-auto pe-1">
          {loading ? (
            <div className="space-y-2 p-1">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-7" />
              ))}
            </div>
          ) : error ? (
            <ErrorState error={error} onRetry={retry} />
          ) : (
            <ul className="space-y-0.5">
              {filtered.map((c) => {
                const cOpen = open.has(c.id) || !!s;
                return (
                  <li key={c.id}>
                    <button onClick={() => toggle(c.id)} className="flex w-full items-center gap-1.5 rounded-lg px-1.5 py-2 text-start text-sm font-bold text-brand-900 transition hover:bg-brand-50 dark:text-white dark:hover:bg-white/5">
                      <ChevronRight className={cn("h-4 w-4 shrink-0 text-ink-mute transition rtl:rotate-180", cOpen && "rotate-90 rtl:rotate-90")} />
                      <MapPin className="h-4 w-4 shrink-0 text-gold-600" />
                      <span className="flex-1 truncate">{c.name}</span>
                      <span className="text-[10px] font-semibold text-ink-mute">{c.schemes.length}</span>
                    </button>
                    <AnimatePresence initial={false}>
                      {cOpen && (
                        <motion.ul initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="ms-4 overflow-hidden border-s border-black/10 ps-2 dark:border-white/10">
                          {!c.schemes.length && <li className="px-2 py-1.5 text-xs text-ink-mute">No schemes yet</li>}
                          {c.schemes.map((sc) => (
                            <SchemeNode key={sc.id} sc={sc} active={sc.id === selected} expanded={open.has(sc.id) || !!s} onToggle={() => toggle(sc.id)} onSelect={() => onSelect(sc.id)} />
                          ))}
                        </motion.ul>
                      )}
                    </AnimatePresence>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}

function SchemeNode({ sc, active, expanded, onToggle, onSelect }: { sc: HierarchyScheme; active: boolean; expanded: boolean; onToggle: () => void; onSelect: () => void }) {
  return (
    <li>
      <div className={cn("flex items-center rounded-lg transition", active ? "bg-brand-700 text-white shadow-soft" : "hover:bg-brand-50 dark:hover:bg-white/5")}>
        <button onClick={onToggle} className="p-1.5" aria-label={expanded ? "Collapse blocks" : "Expand blocks"}>
          <ChevronRight className={cn("h-3.5 w-3.5 transition rtl:rotate-180", expanded && "rotate-90 rtl:rotate-90", active ? "text-white/80" : "text-ink-mute")} />
        </button>
        <button onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pe-2 text-start text-[13px] font-semibold">
          <span className={cn("flex-1 truncate", !active && "text-ink-soft dark:text-slate-200")}>{sc.name}</span>
          {sc.properties > 0 && <span className={cn("rounded-full px-1.5 text-[10px]", active ? "bg-white/20" : "bg-brand-50 text-brand-700 dark:bg-white/10 dark:text-brand-200")}>{sc.properties}</span>}
        </button>
      </div>
      {expanded && (
        <ul className="ms-6 space-y-0.5 py-1">
          {sc.blocks.map((b) => (
            <li key={b.id} className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-ink-mute">
              <span className={cn("h-1.5 w-1.5 rounded-full", b.area_type === "commercial" ? "bg-sky-500" : b.area_type === "luxury" ? "bg-gold-500" : "bg-brand-500")} />
              <span className="flex-1 truncate">{b.name}</span>
              {b.properties > 0 && <span className="font-semibold">{b.properties}</span>}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

// ======================================================================= browse all
function BrowseAll({
  schemes,
  tree,
  loading,
  error,
  retry,
  onSelect,
}: {
  schemes: Scheme[];
  tree?: HierarchyCity[];
  loading: boolean;
  error: unknown;
  retry: () => void;
  onSelect: (id: string) => void;
}) {
  const listings = useMemo(() => {
    const m = new Map<string, number>();
    (tree ?? []).forEach((c) => c.schemes.forEach((s) => m.set(s.id, s.properties)));
    return m;
  }, [tree]);
  const cities = [...new Set(schemes.map((s) => s.city))];
  const [city, setCity] = useState("");
  const list = schemes.filter((s) => !city || s.city === city);
  return (
    <div>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="section-eyebrow">Browse</p>
          <h2 className="mt-1 font-display text-2xl font-bold text-brand-900 dark:text-white">All housing schemes</h2>
          <p className="text-sm text-ink-mute">{schemes.length} schemes across {cities.length} cities</p>
        </div>
        <div className="no-scrollbar flex gap-1.5 overflow-x-auto">
          {["", ...cities].map((c) => (
            <button
              key={c || "all"}
              onClick={() => setCity(c)}
              className={cn("shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold transition", city === c ? "bg-brand-700 text-white shadow-soft" : "bg-black/5 text-ink-soft hover:bg-brand-50 dark:bg-white/5 dark:text-slate-300")}
            >
              {c || "All cities"}
            </button>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-72" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={retry} />
      ) : !list.length ? (
        <EmptyState title="No schemes yet" />
      ) : (
        <motion.div layout className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          <AnimatePresence>
            {list.map((s, i) => (
              <motion.button
                layout
                key={s.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.35, delay: Math.min(i, 9) * 0.04 }}
                onClick={() => onSelect(s.id)}
                className="card card-hover group overflow-hidden text-start"
              >
                <div className="relative aspect-[16/10] overflow-hidden">
                  <img src={themedImage(s.id, s.name)} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110" />
                  <div className="absolute inset-0 bg-gradient-to-t from-brand-950/80 via-brand-950/10 to-transparent" />
                  <span className="chip absolute start-3 top-3 bg-white/90 text-brand-800 shadow dark:bg-black/50 dark:text-white">
                    <MapPin className="h-3 w-3 text-gold-600" /> {s.city}
                  </span>
                  {(listings.get(s.id) ?? 0) > 0 && <span className="chip absolute end-3 top-3 bg-gold-gradient text-brand-950 shadow">{listings.get(s.id)} listings</span>}
                  <h3 className="absolute bottom-3 start-4 end-4 font-display text-xl font-bold text-white drop-shadow">{s.name}</h3>
                </div>
                <div className="grid grid-cols-3 divide-x divide-black/5 text-center rtl:divide-x-reverse dark:divide-white/10">
                  {[
                    ["Units", compact(s.total_units)],
                    ["Since", s.established_year ?? "—"],
                    ["Blocks", s.blocks ?? "—"],
                  ].map(([l, v]) => (
                    <div key={String(l)} className="py-3">
                      <p className="font-display text-base font-bold text-ink dark:text-white">{v}</p>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-mute">{l}</p>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between border-t border-black/5 px-4 py-2.5 text-xs font-semibold text-brand-700 dark:border-white/10 dark:text-brand-300">
                  Explore scheme <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-1 rtl:rotate-180 rtl:group-hover:-translate-x-1" />
                </div>
              </motion.button>
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  );
}

// ======================================================================= detail
function SchemeDetail({
  scheme,
  h,
  properties,
  propsLoading,
  onBack,
}: {
  scheme: Scheme;
  h?: HierarchyScheme & { city: string };
  properties: Property[];
  propsLoading: boolean;
  onBack: () => void;
}) {
  const [report, setReport] = useState<ReportRef | null>(null);
  const anaQ = useApi<GisAreaAnalysis>(`/gis/analysis/scheme/${scheme.id}`);
  const fcQ = useApi<SchemeForecast>(`/gis/analysis/scheme/${scheme.id}/forecast`);
  const ana = anaQ.data && !anaQ.data.error ? anaQ.data : undefined;
  const fc = fcQ.data && !fcQ.data.error ? fcQ.data.forecast : undefined;
  const pts = properties.filter((p) => p.latitude != null && p.longitude != null).map((p) => [p.latitude!, p.longitude!] as [number, number]);
  const geomPts = useMemo(() => {
    const g = ana?.geometry;
    if (g?.type === "Polygon") return g.coordinates[0]!.map(([lon, lat]) => [lat!, lon!] as [number, number]);
    return [];
  }, [ana]);
  const fit = [...pts, ...geomPts];

  return (
    <div className="space-y-6">
      {/* hero */}
      <div className="relative overflow-hidden rounded-3xl bg-brand-950 text-white shadow-soft">
        <img src={themedImage(scheme.id, scheme.name)} alt="" className="absolute inset-0 h-full w-full object-cover opacity-55" />
        <div className="absolute inset-0 bg-gradient-to-r from-brand-950 via-brand-950/80 to-brand-900/20 rtl:bg-gradient-to-l" />
        <div className="relative p-6 sm:p-8">
          <button onClick={onBack} className="inline-flex items-center gap-1 text-xs font-semibold text-white/70 transition hover:text-white">
            <ArrowLeft className="h-3.5 w-3.5 rtl:rotate-180" /> All schemes
          </button>
          <p className="section-eyebrow mt-4 !text-gold-300">
            <Link to={`/cities/${encodeURIComponent(scheme.city)}`} className="hover:underline">
              {scheme.city}
            </Link>
          </p>
          <h2 className="mt-1 font-display text-3xl font-bold sm:text-4xl">{scheme.name}</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {scheme.established_year && (
              <span className="chip bg-white/15 text-white backdrop-blur">
                <CalendarDays className="h-3 w-3" /> Est. {scheme.established_year}
              </span>
            )}
            <span className="chip bg-white/15 text-white backdrop-blur">
              <Home className="h-3 w-3" /> {num(scheme.total_units)} units
            </span>
            {ana?.area && (
              <span className="chip bg-white/15 text-white backdrop-blur">
                <LandPlot className="h-3 w-3" /> {num(ana.area.area_acres, 0)} acres
              </span>
            )}
            {fc && (
              <Badge tone={bandTone(fc.index_band)} className="capitalize">
                {fc.index_band} market
              </Badge>
            )}
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button variant="gold" icon={<FileBarChart className="h-4 w-4" />} onClick={() => setReport({ title: `${scheme.name} — GIS analysis report`, path: `/gis/report/scheme/${scheme.id}` })}>
              GIS report
            </Button>
            <Button variant="outline" className="!border-white/30 !bg-white/10 !text-white hover:!bg-white/20" icon={<Eye className="h-4 w-4" />} onClick={() => setReport({ title: `${scheme.name} — investment outlook`, path: `/gis/outlook/scheme/${scheme.id}` })}>
              Investment outlook
            </Button>
          </div>
        </div>
      </div>

      {/* stats */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="Total units" value={compact(scheme.total_units)} icon={<Building2 className="h-5 w-5" />} />
        <StatCard label="Established" value={scheme.established_year ?? "—"} icon={<CalendarDays className="h-5 w-5" />} tone="gold" hint={scheme.established_year ? `${new Date().getFullYear() - scheme.established_year} yrs` : undefined} />
        <StatCard label="Blocks" value={scheme.blocks ?? h?.blocks.length ?? "—"} icon={<Layers className="h-5 w-5" />} tone="blue" />
        <StatCard label="Live listings" value={h?.properties ?? properties.length} icon={<Home className="h-5 w-5" />} tone="purple" hint={ana?.properties ? pkrShort(ana.properties.total_market_value) : undefined} />
      </div>

      {/* blocks */}
      {h && h.blocks.length > 0 && (
        <Card>
          <CardHeader title="Blocks & zones" subtitle={`${h.blocks.length} in ${scheme.name}`} icon={<Grid3x3 className="h-5 w-5" />} />
          <CardBody className="flex flex-wrap gap-2">
            {h.blocks.map((b, i) => (
              <motion.span key={b.id} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.04 }} className="inline-flex items-center gap-2 rounded-xl border border-black/5 bg-white px-3 py-2 text-sm shadow-sm dark:border-white/10 dark:bg-white/5">
                <span className="font-semibold text-ink dark:text-white">{b.name}</span>
                <Badge tone={AREA_TONE[b.area_type] ?? "gray"}>{b.area_type}</Badge>
                <span className="text-xs text-ink-mute">{b.properties} listing{b.properties === 1 ? "" : "s"}</span>
              </motion.span>
            ))}
          </CardBody>
        </Card>
      )}

      {/* map + GIS analysis */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Card className="overflow-hidden">
          <CardHeader title="On the map" subtitle="Scheme footprint and live listings" icon={<MapPin className="h-5 w-5" />} action={<Link to="/map" className="btn btn-ghost btn-sm"><Compass className="h-3.5 w-3.5" /> Explorer</Link>} />
          {anaQ.isLoading ? (
            <Skeleton className="h-[380px] rounded-none" />
          ) : (
            <PortalMap height={380} className="rounded-none" fit={fit.length ? fit : undefined} zoom={fit.length ? 13 : 5}>
              {ana?.geometry && <GeoJSON key={scheme.id} data={ana.geometry} style={() => ({ color: "#c99a22", weight: 3, fillColor: "#c99a22", fillOpacity: 0.12, dashArray: "6 4" })} />}
              {properties.map((p) =>
                p.latitude != null && p.longitude != null ? (
                  <Marker key={p.id} position={[p.latitude, p.longitude]} icon={pin(p.featured ? "featured" : p.use_type === "commercial" ? "commercial" : "property")}>
                    <Popup>
                      <div className="p-3">
                        <p className="text-sm font-semibold">{p.title}</p>
                        <p className="text-sm font-bold text-brand-700">{pkrShort(p.price)}</p>
                        <Link to={`/properties/${p.id}`} className="mt-1 inline-block text-xs font-semibold text-brand-700 hover:underline">
                          View details →
                        </Link>
                      </div>
                    </Popup>
                  </Marker>
                ) : null,
              )}
            </PortalMap>
          )}
        </Card>

        <Card>
          <CardHeader title="GIS analysis" subtitle="Area, population, cost & economic impact" icon={<Sparkles className="h-5 w-5" />} />
          <CardBody className="space-y-4">
            {anaQ.isLoading ? (
              <Skeleton className="h-64" />
            ) : anaQ.error ? (
              <ErrorState error={anaQ.error} onRetry={() => anaQ.refetch()} />
            ) : anaQ.data?.error ? (
              <EmptyState title="No analysis available" hint={anaQ.data.error} />
            ) : ana ? (
              <>
                <div className="grid grid-cols-2 gap-2">
                  {ana.area && <MiniStat label="Land area" value={`${num(ana.area.area_acres, 0)} acres`} hint={`${num(ana.area.area_kanal, 0)} kanal`} />}
                  {ana.population?.projected && <MiniStat label="Projected population" value={compact(ana.population.projected.population)} hint={`${compact(ana.population.projected.dwelling_units)} dwellings`} />}
                  {ana.properties && <MiniStat label="Market value" value={pkrShort(ana.properties.total_market_value)} hint={`avg ${pkrShort(ana.properties.avg_price)}`} />}
                  {ana.development_cost && <MiniStat label="Development cost" value={pkrShort(ana.development_cost.total)} />}
                  {ana.economic_impact && <MiniStat label="Economic output" value={pkrShort(ana.economic_impact.total_economic_output)} hint={`×${ana.economic_impact.economic_multiplier} multiplier`} />}
                  {ana.economic_impact && <MiniStat label="Jobs supported" value={num(ana.economic_impact.jobs_total)} hint={`${pkrShort(ana.economic_impact.annual_rental_value)} rent / yr`} />}
                </div>
                <details className="group rounded-xl border border-black/5 p-3 dark:border-white/10">
                  <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-semibold text-ink-mute">
                    <ChevronRight className="h-3.5 w-3.5 transition group-open:rotate-90" /> Raw analysis data
                  </summary>
                  <div className="mt-2 max-h-72 overflow-auto">
                    <JsonView data={Object.fromEntries(Object.entries(ana).filter(([k]) => k !== "geometry"))} />
                  </div>
                </details>
              </>
            ) : null}
            <div className="space-y-2">
              <ReportButton onClick={() => setReport({ title: `${scheme.name} — GIS analysis report`, path: `/gis/report/scheme/${scheme.id}` })} icon={<FileBarChart className="h-4 w-4" />}>
                Printable GIS report
              </ReportButton>
              <ReportButton onClick={() => setReport({ title: `${scheme.name} — investment outlook`, path: `/gis/outlook/scheme/${scheme.id}` })} icon={<Briefcase className="h-4 w-4" />}>
                Investment outlook & risks
              </ReportButton>
            </div>
          </CardBody>
        </Card>
      </div>

      {/* outlook */}
      <Card>
        <CardHeader title="Five-year outlook" subtitle="Composite index, factor drivers and price scenarios" icon={<LineChart className="h-5 w-5" />} />
        <CardBody>
          {fcQ.isLoading ? (
            <Skeleton className="h-72" />
          ) : fcQ.error ? (
            <ErrorState error={fcQ.error} onRetry={() => fcQ.refetch()} />
          ) : fc ? (
            <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <ScoreRing value={fc.composite_index} size={96} label="index" />
                  <div className="space-y-1 text-sm">
                    <Badge tone={bandTone(fc.index_band)} className="capitalize">
                      {fc.index_band}
                    </Badge>
                    <p className="text-ink-mute">
                      Base CAGR <b className="text-ink dark:text-white">{pct(fc.base_cagr)}</b>
                    </p>
                    <p className="text-ink-mute">
                      News momentum <b className="text-ink dark:text-white">{pct(fc.news_momentum)}</b>
                    </p>
                  </div>
                </div>
                <FactorBars scores={fc.factors} weights={fc.weights} />
              </div>
              <ForecastChart scenarios={fc.scenarios} height={300} />
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-ink-mute">No forecast available for this scheme.</p>
          )}
        </CardBody>
      </Card>

      {/* properties */}
      <div>
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <p className="section-eyebrow">Listings</p>
            <h3 className="mt-1 font-display text-xl font-bold text-brand-900 dark:text-white">Properties in {scheme.name}</h3>
          </div>
          <Link to="/properties" className="link text-sm">
            All properties
          </Link>
        </div>
        {propsLoading ? (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-72" />
            ))}
          </div>
        ) : !properties.length ? (
          <EmptyState title="No live listings in this scheme" hint="Check back soon or browse nearby schemes." icon={<Users className="h-6 w-6" />} />
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {properties.map((p) => (
              <PropertyCard key={p.id} p={p} />
            ))}
          </div>
        )}
      </div>

      <ReportModal report={report} onClose={() => setReport(null)} />
    </div>
  );
}
