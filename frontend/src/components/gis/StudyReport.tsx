/**
 * Case-study report for an area drawn on the map (POST /geo/study-area).
 * A full-height panel: grade & scores, a map of the area, summary, people, facilities, market, master plan,
 * economics, 5-year outlook, risks and news. Print / save as PDF, save the area as an area of
 * interest, or ask the AI assistant about it.
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { AlertTriangle, Bot, Building2, CheckCircle2, Coins, Construction, Download, FileText, Landmark, LineChart, Map as MapIcon, MapPin, Newspaper, Printer, Save, Users, X } from "lucide-react";
import { toast } from "sonner";
import { post } from "@/lib/api";
import { compact, num, pkrShort } from "@/lib/format";
import { cn, safeHref } from "@/lib/utils";
import { BarList, Button, Input, ScoreRing, Skeleton } from "@/components/ui";
import type { StudyShape } from "./AreaDraw";
import { megaColor, StatusPill, type MegaProject } from "./MegaProjects";
import { studyMapImage, type StudyMapBase } from "./studyMapImage";

const AreaTrend = lazy(() => import("@/components/ui/charts").then((m) => ({ default: m.AreaTrend })));

/* eslint-disable @typescript-eslint/no-explicit-any */
export type StudyReportData = Record<string, any>;
/* eslint-enable @typescript-eslint/no-explicit-any */

const SCORE_LABELS: Record<string, string> = {
  amenities: "Everyday amenities",
  livability: "Facilities per resident",
  development: "Development level",
  market: "Portal market activity",
  outlook: "5-year outlook",
  infrastructure: "Mega-project pipeline",
};
const GRADE_COLOR: Record<string, string> = {
  A: "bg-emerald-600",
  B: "bg-lime-600",
  C: "bg-amber-500",
  D: "bg-orange-600",
  E: "bg-red-600",
};

export function useStudyReport() {
  const [data, setData] = useState<StudyReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const run = useCallback(async (shape: StudyShape, name: string, save = false) => {
    setLoading(true);
    try {
      const body: Record<string, unknown> = { kind: shape.kind, name, save };
      if (shape.kind === "circle") Object.assign(body, { center: shape.center, radius_m: shape.radius_m });
      if (shape.kind === "rectangle") body.coordinates = shape.coordinates;
      if (shape.kind === "polygon") body.coordinates = shape.coordinates;
      const r = await post<StudyReportData>("/geo/study-area", body);
      setData(r);
      return r;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);
  return { data, setData, loading, run };
}

function Section({ icon: Icon, title, children, className }: { icon: typeof Users; title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn("break-inside-avoid rounded-2xl border border-black/5 p-4 dark:border-white/10", className)}>
      <h3 className="mb-3 flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wider text-brand-800 dark:text-brand-200">
        <Icon className="h-4 w-4" /> {title}
      </h3>
      {children}
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl bg-brand-50/60 px-3 py-2.5 dark:bg-white/5">
      <p className="text-[10px] font-bold uppercase tracking-wider text-ink-mute">{label}</p>
      <p className="mt-0.5 font-display text-lg font-bold">{value}</p>
      {hint && <p className="text-[11px] text-ink-mute">{hint}</p>}
    </div>
  );
}

export function StudyReport({
  data,
  loading,
  shape,
  onClose,
  onSave,
}: {
  data: StudyReportData | null;
  loading: boolean;
  shape: StudyShape | null;
  onClose: () => void;
  onSave: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState<string>(data?.name ?? "Study area");
  const [saving, setSaving] = useState(false);

  // Map image of the area (part of the printed report).
  const [mapBase, setMapBase] = useState<StudyMapBase>("streets");
  const [mapImg, setMapImg] = useState<string | null>(null);
  const [mapBusy, setMapBusy] = useState(false);
  useEffect(() => {
    if (!shape || !data) return;
    let live = true;
    setMapBusy(true);
    const points = ((data.market?.listings_sample ?? []) as { latitude?: number; longitude?: number }[])
      .filter((p) => p.latitude != null && p.longitude != null)
      .map((p) => [p.latitude!, p.longitude!] as [number, number]);
    studyMapImage(shape, { base: mapBase, points, title: data.name ?? "Study area" })
      .then((url) => live && setMapImg(url))
      .catch(() => live && setMapImg(null))
      .finally(() => live && setMapBusy(false));
    return () => {
      live = false;
    };
  }, [shape, data, mapBase]);
  const fc = data?.forecast ?? {};
  const trend = useMemo(() => {
    const sc = fc.scenarios as
      | Record<
          string,
          {
            price_cagr: number;
            series: { year: number; offset: number; price_per_marla: number }[];
          }
        >
      | undefined;
    if (!sc?.base) return [];
    const real = sc.base.series.some((r) => r.price_per_marla > 0);
    return sc.base.series.map((r, i) => {
      const val = (k: string) => {
        const s = sc[k];
        if (!s) return undefined;
        return real ? s.series[i]?.price_per_marla : Math.round(100 * (1 + s.price_cagr) ** r.offset);
      };
      return {
        year: r.year,
        optimistic: val("optimistic"),
        base: val("base"),
        pessimistic: val("pessimistic"),
        real,
      };
    });
  }, [fc.scenarios]);
  const realPrices = !!trend[0]?.real;

  if (!loading && !data) return null;
  const d = data ?? {};
  const people = d.people ?? {};
  const fac = d.facilities ?? {};
  const market = d.market ?? {};
  const price = market.price ?? {};
  const econ = d.economics ?? {};
  const impact = econ.economic_impact ?? {};
  const plan = d.master_plan;
  const loc = d.location ?? {};
  const askAi = `/ai?q=${encodeURIComponent(
    `Give me a real-estate case study of the area around ${loc.nearest_city?.name ?? "this location"} (${(d.shape?.center?.latitude ?? 0).toFixed(4)}, ${(d.shape?.center?.longitude ?? 0).toFixed(4)}), about ${d.shape?.area_km2 ?? ""} km². Our score: ${d.overall}/100 (${d.grade}).`,
  )}`;

  return createPortal(
    <div className="study-print-root fixed inset-0 z-[1100] flex justify-end">
      <div className="absolute inset-0 bg-brand-950/40 backdrop-blur-sm print:hidden" onClick={onClose} />
      <aside className="study-print relative flex h-full w-full max-w-3xl flex-col bg-white shadow-2xl dark:bg-[#0b1a12]">
        <header className="flex items-center gap-3 border-b border-black/5 px-5 py-3 dark:border-white/10">
          <FileText className="h-5 w-5 text-brand-700" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Area case study</p>
            <p className="truncate font-display text-lg font-bold">{d.name ?? "Study area"}</p>
          </div>
          <div className="flex items-center gap-1.5 print:hidden">
            <Button variant="ghost" size="sm" icon={<Printer className="h-4 w-4" />} onClick={() => window.print()} disabled={!data}>
              Print / PDF
            </Button>
            <Link to={askAi} className="btn btn-ghost btn-sm">
              <Bot className="h-4 w-4" /> Ask AI
            </Link>
            <button type="button" onClick={onClose} className="btn btn-ghost btn-icon h-9 w-9" aria-label="Close report">
              <X className="h-5 w-5" />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {loading || !data ? (
            <div className="space-y-3">
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-40 w-full" />
              <Skeleton className="h-40 w-full" />
              <p className="text-center text-sm text-ink-mute">Analysing listings, places, population, master plans and the market…</p>
            </div>
          ) : (
            <>
              {/* ---- headline */}
              <div className="flex flex-wrap items-center gap-5 rounded-2xl bg-brand-gradient p-5 text-white">
                <div className={cn("flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-2xl text-white shadow-lg", GRADE_COLOR[d.grade] ?? "bg-slate-500")}>
                  <span className="font-display text-4xl font-black leading-none">{d.grade}</span>
                  <span className="text-[10px] font-bold uppercase">grade</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-display text-3xl font-bold">
                    {d.overall}
                    <span className="text-lg text-white/70">/100</span> <span className="text-base font-semibold capitalize text-white/80">· {d.band}</span>
                  </p>
                  <p className="mt-1 text-sm text-white/80">
                    <MapPin className="me-1 inline h-3.5 w-3.5" />
                    {[loc.province?.name, loc.nearest_city ? `${loc.nearest_city.distance_km} km from ${loc.nearest_city.name}` : null].filter(Boolean).join(" · ")}
                  </p>
                  <p className="text-sm text-white/80">
                    {d.shape?.kind === "circle" && shape?.kind === "circle" ? `Circle, radius ${(shape.radius_m / 1000).toFixed(2)} km · ` : d.shape?.kind === "rectangle" ? "Rectangle · " : "Polygon · "}
                    {d.shape?.area_km2} km² ({num(d.shape?.area?.area_kanal ?? 0)} kanal)
                  </p>
                </div>
              </div>

              {/* ---- map of the study area */}
              <Section icon={MapIcon} title="Location map">
                <div className="mb-2 flex items-center gap-1.5 print:hidden">
                  {(["streets", "satellite"] as StudyMapBase[]).map((b) => (
                    <button
                      key={b}
                      type="button"
                      onClick={() => setMapBase(b)}
                      className={cn("rounded-full px-3 py-1 text-xs font-semibold", mapBase === b ? "bg-brand-700 text-white" : "bg-black/5 hover:bg-black/10 dark:bg-white/10")}
                    >
                      {b === "streets" ? "Streets" : "Satellite"}
                    </button>
                  ))}
                  {mapImg && (
                    <a href={mapImg} download={`${(d.name ?? "study-area").replace(/[^\w-]+/g, "-")}-map.jpg`} className="btn btn-ghost btn-sm ms-auto">
                      <Download className="h-4 w-4" /> Image
                    </a>
                  )}
                </div>
                {mapImg ? (
                  <img src={mapImg} alt={`Map of ${d.name ?? "the study area"}`} className={cn("w-full rounded-xl ring-1 ring-black/5 transition", mapBusy && "opacity-60")} />
                ) : (
                  <Skeleton className="aspect-[880/500] w-full" />
                )}
                <p className="mt-1.5 text-[11px] text-ink-mute">
                  Purple: the study area · gold: its centre{d.market?.listings_sample?.length ? " · green: listings inside" : ""}. The area outside is dimmed.
                </p>
              </Section>

              {/* ---- scores */}
              <Section icon={LineChart} title="Scores">
                <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                  <div className="space-y-2.5">
                    {Object.entries(d.scores ?? {}).map(([k, v]) => (
                      <div key={k}>
                        <div className="flex justify-between text-xs">
                          <span>{SCORE_LABELS[k] ?? k}</span>
                          <span className="font-semibold">{v as number}</span>
                        </div>
                        <div className="mt-1 h-2 rounded-full bg-black/5 dark:bg-white/10">
                          <div
                            className={cn("h-full rounded-full", (v as number) >= 70 ? "bg-emerald-500" : (v as number) >= 40 ? "bg-amber-500" : "bg-red-500")}
                            style={{ width: `${v}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-center">
                    <ScoreRing value={d.overall} label={`Grade ${d.grade}`} size={110} />
                  </div>
                </div>
              </Section>

              {/* ---- summary */}
              <Section icon={CheckCircle2} title="Summary">
                <p className="rounded-xl bg-brand-50/70 p-3 text-sm font-medium dark:bg-white/5">{d.summary?.recommendation}</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div>
                    <p className="mb-1 text-xs font-bold text-emerald-700 dark:text-emerald-400">Strengths</p>
                    <ul className="space-y-1 text-sm">
                      {(d.summary?.strengths ?? []).length ? d.summary.strengths.map((s: string) => <li key={s}>✓ {s}</li>) : <li className="text-ink-mute">—</li>}
                    </ul>
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-bold text-red-700 dark:text-red-400">Concerns</p>
                    <ul className="space-y-1 text-sm">
                      {(d.summary?.concerns ?? []).length ? d.summary.concerns.map((s: string) => <li key={s}>! {s}</li>) : <li className="text-ink-mute">—</li>}
                    </ul>
                  </div>
                </div>
              </Section>

              {/* ---- people */}
              <Section icon={Users} title="People & development">
                <div className="grid gap-2 sm:grid-cols-3">
                  <Stat label="Residents" value={people.population ? compact(people.population) : "—"} hint={people.source} />
                  <Stat label="Density" value={people.density_per_km2 ? `${num(people.density_per_km2)}/km²` : "—"} />
                  <Stat label="Development" value={<span className="text-sm capitalize">{people.development_level}</span>} />
                </div>
                {!!people.neighbourhoods?.length && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {people.neighbourhoods.map((n: { name: string; population?: number }) => (
                      <span key={n.name} className="chip bg-black/5 text-xs dark:bg-white/10">
                        {n.name}
                        {n.population ? ` · ${compact(n.population)}` : ""}
                      </span>
                    ))}
                  </div>
                )}
              </Section>

              {/* ---- facilities */}
              <Section icon={Landmark} title={`Facilities (${fac.total ?? 0} inside)`}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="mb-2 text-xs font-semibold text-ink-mute">Nearest from the centre</p>
                    <table className="w-full text-sm">
                      <tbody>
                        {(fac.nearest ?? []).map((n: { label: string; name: string | null; distance_km: number | null; inside: number }) => (
                          <tr key={n.label} className="border-b border-black/5 last:border-0 dark:border-white/10">
                            <td className="py-1.5 pe-2 text-xs text-ink-mute">{n.label}</td>
                            <td className="truncate py-1.5 pe-2 text-xs">{n.name ?? "—"}</td>
                            <td
                              className={cn(
                                "py-1.5 text-end text-xs font-semibold",
                                n.distance_km == null ? "text-red-600" : n.distance_km <= 1 ? "text-emerald-600" : n.distance_km <= 3 ? "" : "text-amber-600",
                              )}
                            >
                              {n.distance_km == null ? "> 5 km" : `${n.distance_km} km`}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold text-ink-mute">Inside the area</p>
                    {Object.keys(fac.by_category ?? {}).length ? (
                      <BarList
                        items={Object.entries(fac.by_category).map(([label, value]) => ({
                          label,
                          value: value as number,
                        }))}
                      />
                    ) : (
                      <p className="text-sm text-ink-mute">No mapped facilities inside.</p>
                    )}
                  </div>
                </div>
                {!!Object.keys(fac.notable ?? {}).length && (
                  <div className="mt-3 space-y-1 text-sm">
                    {Object.entries(fac.notable).map(([k, names]) => (
                      <p key={k}>
                        <span className="font-semibold">{k}:</span> <span className="text-ink-mute">{(names as string[]).join(", ")}</span>
                      </p>
                    ))}
                  </div>
                )}
              </Section>

              {/* ---- market */}
              <Section icon={Building2} title="Market">
                <div className="grid gap-2 sm:grid-cols-4">
                  <Stat label="Listings" value={market.listings ?? 0} />
                  <Stat
                    label="Median / marla"
                    value={market.price_per_marla?.median ? pkrShort(market.price_per_marla.median) : "—"}
                    hint={market.price_per_marla?.min ? `${pkrShort(market.price_per_marla.min, false)} – ${pkrShort(market.price_per_marla.max, false)}` : undefined}
                  />
                  <Stat label="Avg price" value={price.avg_price ? pkrShort(price.avg_price) : "—"} />
                  <Stat label="Listed value" value={price.total_market_value ? pkrShort(price.total_market_value) : "—"} />
                </div>
                {!!market.schemes?.length && (
                  <p className="mt-3 text-sm">
                    <span className="font-semibold">Housing schemes:</span> {market.schemes.map((s: { name: string }) => s.name).join(", ")}
                  </p>
                )}
                {!!market.listings_sample?.length && (
                  <ul className="mt-3 divide-y divide-black/5 text-sm dark:divide-white/10">
                    {market.listings_sample.map((p: { id: string; title: string; price: number; category: string; marla?: number }) => (
                      <li key={p.id} className="flex items-center gap-2 py-1.5">
                        <Link to={`/properties/${p.id}`} className="link min-w-0 flex-1 truncate">
                          {p.title}
                        </Link>
                        <span className="shrink-0 text-xs text-ink-mute">{p.marla ? `${p.marla} marla · ` : ""}</span>
                        <span className="shrink-0 font-semibold">{pkrShort(p.price)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {!!market.comparables?.length && (
                  <div className="mt-3">
                    <p className="mb-1 text-xs font-semibold text-ink-mute">
                      Nearby comparables (within 10 km)
                      {market.comparable_price_per_marla ? ` · median ${pkrShort(market.comparable_price_per_marla)} / marla` : ""}
                    </p>
                    <ul className="divide-y divide-black/5 text-sm dark:divide-white/10">
                      {market.comparables.map((p: { id: string; title: string; price: number; distance_km: number; marla?: number }) => (
                        <li key={p.id} className="flex items-center gap-2 py-1.5">
                          <Link to={`/properties/${p.id}`} className="link min-w-0 flex-1 truncate">
                            {p.title}
                          </Link>
                          <span className="shrink-0 text-xs text-ink-mute">
                            {p.distance_km} km
                            {p.marla ? ` · ${p.marla} marla` : ""}
                          </span>
                          <span className="shrink-0 font-semibold">{pkrShort(p.price)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Section>

              {/* ---- infrastructure mega projects */}
              <Section icon={Construction} title="Infrastructure & mega projects">
                {d.mega_projects?.projects?.length ? (
                  <ul className="space-y-2.5">
                    {(d.mega_projects.projects as MegaProject[]).map((p) => (
                      <li key={p.id} className="rounded-xl border-s-4 bg-black/[0.02] p-3 dark:bg-white/5" style={{ borderInlineStartColor: megaColor(p.type) }}>
                        <div className="flex flex-wrap items-center gap-2">
                          <Link to={`/infrastructure#${p.id}`} className="link font-semibold">
                            {p.name}
                          </Link>
                          <StatusPill p={p} />
                          <span className="text-xs text-ink-mute">
                            {p.type_label} · {p.inside ? "runs through the area" : `${p.distance_km} km away`} · completion {p.completion ?? "TBA"}
                          </span>
                          <span className="ms-auto text-xs font-bold">Effect {Math.round((p.effect ?? 0) * 100)}%</span>
                        </div>
                        <p className="mt-1 text-xs text-ink-soft dark:text-slate-300">{p.impact}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-ink-mute">No ring road, motorway, transit line, new sector or economic zone in the portal's list reaches this area.</p>
                )}
                <p className="mt-2 text-[11px] text-ink-mute">Effect weighs distance, status (built and under-construction projects count more than plans) and expected uplift.</p>
              </Section>

              {/* ---- master plan */}
              {plan && (plan.plot_sizes?.length || Object.keys(plan.features ?? {}).length) ? (
                <Section icon={MapPin} title={`Master plan${plan.inside_plans?.length ? ` · ${plan.inside_plans.join(", ")}` : ""}`}>
                  {!!plan.plot_sizes?.length && (
                    <div className="flex flex-wrap gap-1.5">
                      {plan.plot_sizes.map((s: { size: string; count: number }) => (
                        <span key={s.size} className="chip bg-black/5 text-xs dark:bg-white/10">
                          {s.size} × {s.count}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 space-y-1 text-sm">
                    {Object.entries(plan.features ?? {})
                      .slice(0, 6)
                      .map(([k, v]) => (
                        <p key={k}>
                          <span className="font-semibold capitalize">{k}:</span> <span className="text-ink-mute">{(v as string[]).join(", ")}</span>
                        </p>
                      ))}
                  </div>
                  <p className="mt-2 text-[11px] text-ink-mute">{plan.note}</p>
                </Section>
              ) : null}

              {/* ---- economics (from listings inside; hidden when there are none) */}
              {!!(econ.development_cost?.total || impact.total_economic_output) && (
                <Section icon={Coins} title="Economics">
                  <div className="grid gap-2 sm:grid-cols-4">
                    <Stat label="Development cost" value={econ.development_cost?.total ? pkrShort(econ.development_cost.total) : "—"} />
                    <Stat label="Economic output" value={impact.total_economic_output ? pkrShort(impact.total_economic_output) : "—"} />
                    <Stat label="Jobs" value={impact.jobs_total ? num(impact.jobs_total) : "—"} />
                    <Stat label="Annual rent value" value={impact.annual_rental_value ? pkrShort(impact.annual_rental_value) : "—"} />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-mute">Computed from the portal's listings inside the area.</p>
                </Section>
              )}

              {/* ---- outlook */}
              <Section icon={LineChart} title="5-year outlook">
                <div className="grid gap-2 sm:grid-cols-3">
                  <Stat label="Base growth" value={fc.base_cagr != null ? `${(fc.base_cagr * 100).toFixed(1)}%/yr` : "—"} />
                  <Stat label="Market index" value={fc.composite_index ?? "—"} hint={<span className="capitalize">{fc.index_band}</span>} />
                  <Stat label="Confidence" value={fc.confidence != null ? `${Math.round(fc.confidence * 100)}%` : "—"} />
                </div>
                {trend.length > 0 && (
                  <div className="mt-3">
                    <p className="mb-1 text-xs text-ink-mute">{realPrices ? "Price per marla by scenario" : "Price index by scenario (today = 100)"}</p>
                    <Suspense fallback={<Skeleton className="h-48 w-full" />}>
                      <AreaTrend
                        data={trend}
                        x="year"
                        height={190}
                        format={(v: number) => (realPrices ? pkrShort(v, false) : String(Math.round(v)))}
                        series={[
                          {
                            key: "optimistic",
                            label: "Optimistic",
                            color: "#c99a22",
                          },
                          { key: "base", label: "Base", color: "#146f45" },
                          {
                            key: "pessimistic",
                            label: "Pessimistic",
                            color: "#94a3b8",
                          },
                        ]}
                      />
                    </Suspense>
                  </div>
                )}
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {!!fc.risk_flags?.length && (
                    <div>
                      <p className="mb-1 flex items-center gap-1 text-xs font-bold text-red-700 dark:text-red-400">
                        <AlertTriangle className="h-3.5 w-3.5" /> Risks
                      </p>
                      <ul className="space-y-1 text-xs">
                        {fc.risk_flags.map((r: string) => (
                          <li key={r}>• {r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {!!fc.recommendations?.length && (
                    <div>
                      <p className="mb-1 text-xs font-bold text-brand-700 dark:text-brand-300">Recommendations</p>
                      <ul className="space-y-1 text-xs">
                        {fc.recommendations.map((r: string) => (
                          <li key={r}>• {r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </Section>

              {/* ---- news */}
              {!!d.news?.length && (
                <Section icon={Newspaper} title="Related news">
                  <ul className="space-y-1.5 text-sm">
                    {d.news.map((n: { title: string; source: string; sentiment: string; url?: string }) => (
                      <li key={n.title} className="flex items-start gap-2">
                        <span
                          className={cn(
                            "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                            n.sentiment === "positive" ? "bg-emerald-500" : n.sentiment === "negative" ? "bg-red-500" : "bg-slate-400",
                          )}
                        />
                        <span>
                          {safeHref(n.url) ? (
                            <a href={safeHref(n.url)!} target="_blank" rel="noreferrer" className="link">
                              {n.title}
                            </a>
                          ) : (
                            n.title
                          )}{" "}
                          <span className="text-xs text-ink-mute">· {n.source}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              <p className="text-[11px] text-ink-mute">
                Method: {d.method}. Population is an estimate; facility counts come from OpenStreetMap and may miss small places; scores are indicative, not financial advice.
              </p>
            </>
          )}
        </div>

        {data && !data.saved && (
          <footer className="flex items-center gap-2 border-t border-black/5 px-5 py-3 print:hidden dark:border-white/10">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name this area" className="max-w-xs" />
            <Button
              icon={<Save className="h-4 w-4" />}
              loading={saving}
              onClick={async () => {
                setSaving(true);
                await onSave(name.trim() || "Study area");
                setSaving(false);
              }}
            >
              Save as area of interest
            </Button>
          </footer>
        )}
      </aside>
    </div>,
    document.body,
  );
}
