import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Circle, Marker, Popup, TileLayer } from "react-leaflet";
import {
  Bath,
  BedDouble,
  Building2,
  CalendarCheck,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Compass,
  Expand,
  FileText,
  Footprints,
  Map as MapIcon,
  Layers,
  LineChart,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Printer,
  Ruler,
  Share2,
  ShieldCheck,
  Sparkles,
  Star,
  Tag,
  TrendingUp,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";
import type { MapOverlay, NearbyList, Property, PropertyList } from "@/types";
import { useApi, useMutate } from "@/hooks/useApi";
import { API_BASE, apiUrl, post } from "@/lib/api";
import { area, num, pct, pkr, pkrShort, titleCase } from "@/lib/format";
import { gallery, resolveImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, Carousel, CopyButton, EmptyState, ErrorState, Field, Input, KeyValue, Modal, ScoreRing, Skeleton, Slider, Tabs, Textarea } from "@/components/ui";
import { AreaTrend, Bars } from "@/components/ui/charts";
import { CompareButton, FavoriteButton, PropertyCard } from "@/components/property/PropertyCard";
import { PortalMap, pin } from "@/components/map/PortalMap";
import { AdSlot } from "@/components/ads/AdSlot";
import { Markdown } from "@/components/ai/Markdown";

interface Agent {
  id: string;
  name: string;
  email: string;
  phone: string;
  region: string;
  specialization: string;
  rating: number;
  deals_closed: number;
}

// ---------------------------------------------------------------- gallery
function Gallery({ images, title }: { images: string[]; title: string }) {
  const [i, setI] = useState(0);
  const [open, setOpen] = useState(false);
  const go = (d: number) => setI((x) => (x + d + images.length) % images.length);
  return (
    <>
      <div className="grid gap-3 lg:grid-cols-[1fr_220px]">
        <div className="group relative h-[260px] overflow-hidden rounded-3xl bg-black/5 sm:h-[400px] lg:h-[500px]">
          <AnimatePresence mode="wait">
            <motion.img key={i} src={images[i]} alt={title} initial={{ opacity: 0, scale: 1.02 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }} className="h-full w-full object-cover" />
          </AnimatePresence>
          <button onClick={() => go(-1)} className="absolute start-3 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-brand-800 opacity-0 shadow-soft transition group-hover:opacity-100" aria-label="Previous">
            <ChevronLeft className="h-5 w-5 rtl:rotate-180" />
          </button>
          <button onClick={() => go(1)} className="absolute end-3 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-brand-800 opacity-0 shadow-soft transition group-hover:opacity-100" aria-label="Next">
            <ChevronRight className="h-5 w-5 rtl:rotate-180" />
          </button>
          <button onClick={() => setOpen(true)} className="btn btn-sm absolute bottom-3 end-3 bg-black/50 text-white backdrop-blur hover:bg-black/70">
            <Expand className="h-4 w-4" /> {i + 1} / {images.length}
          </button>
        </div>
        <div className="no-scrollbar flex gap-3 overflow-x-auto lg:h-[500px] lg:flex-col lg:overflow-y-auto">
          {images.map((src, k) => (
            <button key={src + k} onClick={() => setI(k)} className={cn("relative aspect-[16/10] w-36 shrink-0 overflow-hidden rounded-2xl ring-2 ring-offset-2 ring-offset-transparent transition lg:w-full", k === i ? "ring-gold-400" : "ring-transparent opacity-75 hover:opacity-100")}>
              <img src={src} alt="" className="h-full w-full object-cover" />
              {src.includes("/plans/") && <span className="chip absolute bottom-1.5 start-1.5 bg-white/90 text-[10px] text-brand-800">Floor plan</span>}
              {src.includes("/interiors/") && <span className="chip absolute bottom-1.5 start-1.5 bg-white/90 text-[10px] text-brand-800">Interior</span>}
            </button>
          ))}
        </div>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} size="xl" title={title}>
        <Carousel slideClass="basis-full" dots arrows>
          {images.map((src) => (
            <img key={src} src={src} alt="" className="aspect-[16/10] w-full rounded-2xl object-cover" />
          ))}
        </Carousel>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------- location
const POI_ICON: Record<string, string> = { education: "🎓", health: "✚", worship: "🕌", shopping: "🛍", park: "🌳", transport: "🚌", bank: "🏦", restaurant: "🍽", fuel: "⛽", government: "🏛" };
const distance = (km: number) => (km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`);

interface PlanView {
  plan: string;
  plan_key: string;
  snapshot_url: string;
  map?: { overlays?: MapOverlay[] };
  on_the_plan?: { features?: Record<string, string[]>; plot_sizes?: { size: string; count: number }[]; note?: string };
  attribution?: string;
}

/** The closest school, mosque, hospital, market … (GET /properties/{id}/nearby — portal POIs + OpenStreetMap data). */
function ClosestPlaces({ p }: { p: Property }) {
  const q = useApi<NearbyList>(`/properties/${p.id}/nearby`, { radius_km: 3 }, { retry: false });
  const rows = q.data?.nearby ?? [];
  if (q.isLoading) return <Skeleton className="h-28 w-full" />;
  if (!rows.length) return null;
  return (
    <div>
      <p className="mb-2 font-display font-semibold">Closest places</p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {rows.slice(0, 9).map((r) => (
          <div key={r.category} className="flex items-center gap-3 rounded-xl bg-brand-50/60 px-3 py-2.5 dark:bg-white/5">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-sm dark:bg-white/10">{POI_ICON[r.category] ?? "📍"}</span>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-mute">{r.kind}</p>
              <p className="truncate text-sm font-semibold">{r.name}</p>
            </div>
            <span className="shrink-0 text-end text-xs font-semibold text-brand-700 dark:text-brand-300">
              {distance(r.distance_km)}
              <span className="flex items-center justify-end gap-0.5 font-normal text-ink-mute">
                <Footprints className="h-3 w-3" /> {r.walk_minutes} min
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** A close-up of the DHA master plan around the listing, when it sits on a loaded plan (GET /masterplans/view). */
function MasterPlanCard({ view }: { view: PlanView }) {
  const features = Object.entries(view.on_the_plan?.features ?? {}).slice(0, 6);
  const sizes = view.on_the_plan?.plot_sizes ?? [];
  return (
    <div className="overflow-hidden rounded-2xl border border-black/5 dark:border-white/10">
      <div className="grid gap-0 md:grid-cols-[1.2fr_1fr]">
        <a href={`${API_BASE}${view.snapshot_url}`} target="_blank" rel="noreferrer" className="block bg-black/5">
          <img src={`${API_BASE}${view.snapshot_url}`} alt={`${view.plan} master plan around this listing`} className="h-full max-h-80 w-full object-cover" loading="lazy" />
        </a>
        <div className="space-y-3 p-4">
          <p className="flex items-center gap-2 font-display font-semibold">
            <MapIcon className="h-4 w-4 text-gold-600" /> On the {view.plan} master plan
          </p>
          {!!sizes.length && (
            <div>
              <p className="label">Plot sizes nearby</p>
              <div className="flex flex-wrap gap-1.5">
                {sizes.map((s) => (
                  <Badge key={s.size} tone="gray">
                    {s.size} × {s.count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {features.map(([kind, names]) => (
            <p key={kind} className="text-sm">
              <span className="font-semibold capitalize">{kind}:</span> <span className="text-ink-mute">{names.join(", ")}</span>
            </p>
          ))}
          <p className="text-xs text-ink-mute">{view.on_the_plan?.note ?? view.attribution}</p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- tabs
function LocationTab({ p }: { p: Property }) {
  const has = p.latitude && p.longitude;
  const [radius, setRadius] = useState(2);
  const pois = useApi<{ pois: { id: string; name: string; category: string; latitude: number; longitude: number; distance_km: number; rating?: number }[] }>(has ? "/poi/nearby" : null, {
    latitude: p.latitude,
    longitude: p.longitude,
    radius_km: radius,
  });
  const score = useApi<{ composite_score: number; grade: string; dimensions: Record<string, number>; commute_km: number; commute_minutes: number; narrative: string }>("/property-intelligence/gis-score", { property_id: p.id });
  // 404 when the listing isn't on a loaded master plan — then the section is simply left out.
  const plan = useApi<PlanView>(has ? "/masterplans/view" : null, { listing_id: p.id, radius_m: 250 }, { retry: false, staleTime: 10 * 60_000 });
  const overlays = plan.data?.map?.overlays ?? [];
  if (!has) return <EmptyState title="No coordinates on file" hint="This listing hasn’t been geo-tagged yet." />;
  const grouped = (pois.data?.pois ?? []).reduce<Record<string, number>>((a, x) => ((a[x.category] = (a[x.category] ?? 0) + 1), a), {});
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
        <PortalMap center={[p.latitude!, p.longitude!]} zoom={15} height={380} scrollWheelZoom>
          {overlays.map((o) => (
            <TileLayer
              key={o.key}
              url={`${API_BASE}${o.tile_url}`}
              bounds={[
                [o.bounds[0], o.bounds[1]],
                [o.bounds[2], o.bounds[3]],
              ]}
              minZoom={o.min_zoom}
              maxNativeZoom={o.max_native_zoom}
              maxZoom={20}
              opacity={0.75}
              attribution={o.attribution}
            />
          ))}
          <Marker position={[p.latitude!, p.longitude!]} icon={pin("featured", { pulse: true, size: 40 })}>
            <Popup>
              <div className="p-3 font-semibold">{p.title}</div>
            </Popup>
          </Marker>
          <Circle center={[p.latitude!, p.longitude!]} radius={radius * 1000} pathOptions={{ color: "#c99a22", weight: 1.5, fillOpacity: 0.06 }} />
          {(pois.data?.pois ?? []).map((x) => (
            <Marker key={x.id} position={[x.latitude, x.longitude]} icon={pin(x.category, { size: 26 })}>
              <Popup>
                <div className="p-3">
                  <p className="font-semibold">{x.name}</p>
                  <p className="text-xs capitalize text-ink-mute">
                    {x.category} · {x.distance_km.toFixed(2)} km
                  </p>
                </div>
              </Popup>
            </Marker>
          ))}
        </PortalMap>
        <div className="space-y-4">
          <div className="rounded-2xl bg-brand-50/60 p-4 dark:bg-white/5">
            <div className="flex items-center gap-4">
              <ScoreRing value={score.data?.composite_score ?? 0} label={`Grade ${score.data?.grade ?? "–"}`} />
              <div>
                <p className="font-display font-semibold">Location score</p>
                <p className="text-xs text-ink-mute">{score.data?.narrative}</p>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {Object.entries(score.data?.dimensions ?? {}).map(([k, v]) => (
                <div key={k}>
                  <div className="flex justify-between text-xs">
                    <span className="capitalize">{k}</span>
                    <span className="font-semibold">{Math.round(v)}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-black/5 dark:bg-white/10">
                    <div className="h-full rounded-full bg-brand-600" style={{ width: `${v}%` }} />
                  </div>
                </div>
              ))}
            </div>
            {score.data && (
              <p className="mt-3 text-xs text-ink-mute">
                Commute to city centre: <b>{score.data.commute_km.toFixed(1)} km</b> · ~{Math.round(score.data.commute_minutes)} min
              </p>
            )}
          </div>
          <div>
            <p className="label">Search radius · {radius} km</p>
            <Slider value={radius} min={0.5} max={10} step={0.5} onChange={setRadius} />
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(grouped).map(([k, v]) => (
          <Badge key={k} tone="gray" className="capitalize">
            {k}: {v}
          </Badge>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {(pois.data?.pois ?? []).slice(0, 10).map((x) => (
          <div key={x.id} className="flex items-center gap-3 rounded-xl border border-black/5 px-3 py-2.5 dark:border-white/10">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-sm dark:bg-white/5">{POI_ICON[x.category] ?? "📍"}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{x.name}</p>
              <p className="text-xs capitalize text-ink-mute">{x.category}</p>
            </div>
            <span className="text-xs font-semibold text-brand-700 dark:text-brand-300">{distance(x.distance_km)}</span>
          </div>
        ))}
      </div>
      <ClosestPlaces p={p} />
      {plan.data && <MasterPlanCard view={plan.data} />}
    </div>
  );
}

function InvestmentTab({ p }: { p: Property }) {
  const inv = useApi<{ price_per_sqft: number; price_per_marla: number; city_avg_price_per_sqft: number; delta_vs_city_pct: number; verdict: string; estimated_monthly_rent: number; estimated_gross_yield_pct: number }>(`/properties/${p.id}/investment`);
  const snap = useApi<{
    value: number;
    estimated_annual_rent: number;
    net_operating_income: number;
    cap_rate: number;
    roi: { equity_invested: number; loan_amount: number; hold_years: number; terminal_value: number; base: { irr: number; npv: number; equity_multiple: number; cashflows: number[]; annualised_roi: number }; scenarios?: Record<string, { cashflows: number[]; irr?: number }> };
  }>(`/property-intelligence/accounting-snapshot/${p.id}`);
  const flows = useMemo(() => {
    const base = snap.data?.roi.base.cashflows ?? [];
    const sc = snap.data?.roi.scenarios ?? {};
    let cum = 0;
    return base.map((v, i) => {
      cum += v;
      return { year: `Y${i}`, cashflow: v, cumulative: cum, pessimistic: sc.pessimistic?.cashflows[i], optimistic: sc.optimistic?.cashflows[i] };
    });
  }, [snap.data]);
  return (
    <div className="space-y-6">
      {inv.data && (
        <div className="flex flex-col gap-4 rounded-2xl bg-gradient-to-r from-brand-50 to-gold-50 p-5 sm:flex-row sm:items-center dark:from-brand-900/40 dark:to-gold-900/20">
          <TrendingUp className="h-10 w-10 shrink-0 text-brand-700 dark:text-gold-300" />
          <div className="flex-1">
            <p className="font-display text-lg font-semibold capitalize">{inv.data.verdict}</p>
            <p className="text-sm text-ink-soft dark:text-slate-300">
              {pkrShort(inv.data.price_per_sqft)}/sqft vs city average {pkrShort(inv.data.city_avg_price_per_sqft)} ({inv.data.delta_vs_city_pct > 0 ? "+" : ""}
              {inv.data.delta_vs_city_pct}%)
            </p>
          </div>
          <div className="text-end">
            <p className="text-xs uppercase text-ink-mute">Est. rent</p>
            <p className="font-display text-xl font-bold">{pkrShort(inv.data.estimated_monthly_rent)}/mo</p>
            <p className="text-xs text-ink-mute">{inv.data.estimated_gross_yield_pct}% gross yield</p>
          </div>
        </div>
      )}
      {snap.isLoading ? (
        <Skeleton className="h-64" />
      ) : snap.data ? (
        <>
          <KeyValue
            cols={4}
            items={[
              { label: "Net operating income", value: pkrShort(snap.data.net_operating_income) },
              { label: "Cap rate", value: pct(snap.data.cap_rate) },
              { label: `IRR (${snap.data.roi.hold_years}y, leveraged)`, value: pct(snap.data.roi.base.irr) },
              { label: "Equity multiple", value: `${snap.data.roi.base.equity_multiple.toFixed(2)}×` },
              { label: "Equity invested", value: pkrShort(snap.data.roi.equity_invested) },
              { label: "Loan amount", value: pkrShort(snap.data.roi.loan_amount) },
              { label: "Exit value", value: pkrShort(snap.data.roi.terminal_value) },
              { label: "NPV @ 12%", value: pkrShort(snap.data.roi.base.npv) },
            ]}
          />
          <div>
            <p className="mb-2 font-display font-semibold">Cash-flow projection (leveraged)</p>
            <Bars data={flows} x="year" series={[{ key: "cashflow", label: "Annual cash flow" }]} format={(v) => pkrShort(v, false)} height={220} />
          </div>
          <div>
            <p className="mb-2 font-display font-semibold">Cumulative position</p>
            <AreaTrend data={flows} x="year" series={[{ key: "cumulative", label: "Cumulative", color: "#c99a22" }]} format={(v) => pkrShort(v, false)} height={200} />
          </div>
        </>
      ) : (
        <ErrorState error={snap.error} onRetry={() => snap.refetch()} />
      )}
      <p className="text-xs text-ink-mute">Assumes 4.5% gross yield, 30% operating costs and 75% LTV financing. Use the <Link to="/tools/mortgage" className="link">tools center</Link> to model your own terms.</p>
    </div>
  );
}

function PricingTab({ p }: { p: Property }) {
  const cma = useApi<{
    comp_count: number;
    adjusted_comps: { comp_id: string; title: string; raw_price: number; adjusted_price: number; adjust_factor: number }[];
    price_range: { low: number; target: number; high: number };
    recommended_list_price: number;
    confidence: number;
    expected_days_on_market: number;
    pricing_strategy: string;
    rationale: string[];
  }>(`/intelligence/seller/cma/${p.id}`);
  if (cma.isLoading) return <Skeleton className="h-64" />;
  if (cma.error || !cma.data) return <ErrorState error={cma.error} onRetry={() => cma.refetch()} />;
  const d = cma.data;
  const lo = Math.min(d.price_range.low, p.price) * 0.9;
  const hi = Math.max(d.price_range.high, p.price) * 1.1;
  const pos = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;
  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-2xl border border-gold-200 bg-gold-50/60 p-4 dark:border-gold-500/20 dark:bg-gold-500/5">
        <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-gold-600" />
        <p className="text-sm">
          <b>CMA agent:</b> {d.pricing_strategy}. Confidence <b>{Math.round(d.confidence * 100)}%</b> from {d.comp_count} adjusted comparable{d.comp_count === 1 ? "" : "s"}; expected <b>{Math.round(d.expected_days_on_market)} days</b> on market.
        </p>
      </div>
      <div className="px-2 pt-8">
        <div className="relative h-3 rounded-full bg-gradient-to-r from-emerald-300 via-gold-300 to-red-300">
          <div className="absolute -top-8 -translate-x-1/2 text-center text-xs font-semibold rtl:translate-x-1/2" style={{ insetInlineStart: pos(p.price) }}>
            Asking
            <div className="mx-auto mt-1 h-5 w-0.5 bg-ink dark:bg-white" />
          </div>
          {(["low", "target", "high"] as const).map((k) => (
            <div key={k} className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-4 border-white bg-brand-700 shadow rtl:translate-x-1/2" style={{ insetInlineStart: pos(d.price_range[k]) }} />
          ))}
        </div>
        <div className="mt-3 flex justify-between text-xs text-ink-mute">
          <span>Low {pkrShort(d.price_range.low)}</span>
          <span className="font-semibold text-brand-700 dark:text-gold-300">Target {pkrShort(d.price_range.target)}</span>
          <span>High {pkrShort(d.price_range.high)}</span>
        </div>
      </div>
      <KeyValue
        cols={3}
        items={[
          { label: "Asking price", value: pkrShort(p.price) },
          { label: "AI recommended list", value: pkrShort(d.recommended_list_price) },
          { label: "Gap", value: `${(((p.price - d.recommended_list_price) / d.recommended_list_price) * 100).toFixed(1)}%` },
        ]}
      />
      <div>
        <p className="mb-2 font-display font-semibold">Adjusted comparables</p>
        <div className="space-y-2">
          {d.adjusted_comps.map((c) => (
            <Link key={c.comp_id} to={`/properties/${c.comp_id}`} className="flex items-center justify-between rounded-xl border border-black/5 px-4 py-3 hover:bg-brand-50 dark:border-white/10 dark:hover:bg-white/5">
              <span className="font-medium">{c.title}</span>
              <span className="text-sm">
                {pkrShort(c.raw_price)} → <b>{pkrShort(c.adjusted_price)}</b> <span className="text-xs text-ink-mute">×{c.adjust_factor.toFixed(2)}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
      <ul className="list-disc space-y-1 ps-5 text-sm text-ink-soft dark:text-slate-300">
        {d.rationale.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

function ListingKitTab({ p }: { p: Property }) {
  const [tone, setTone] = useState("professional");
  const [lang, setLang] = useState("en");
  const kit = useApi<{ headline: string; description: string; bullets: string[]; social_posts: Record<string, string>; email?: { subject: string; body: string }; video_script?: unknown }>(`/broker/listing-draft/${p.id}`, { tone, lang });
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-2 text-sm font-semibold">
          <Wand2 className="h-4 w-4 text-gold-600" /> Marketing agent draft
        </span>
        <select value={tone} onChange={(e) => setTone(e.target.value)} className="input w-auto py-1.5 text-sm">
          {["professional", "luxury", "friendly", "investor"].map((t) => (
            <option key={t} value={t}>
              {titleCase(t)} tone
            </option>
          ))}
        </select>
        <select value={lang} onChange={(e) => setLang(e.target.value)} className="input w-auto py-1.5 text-sm">
          <option value="en">English</option>
          <option value="ur">اردو</option>
        </select>
      </div>
      {kit.isLoading ? (
        <Skeleton className="h-48" />
      ) : kit.data ? (
        <>
          <div className="rounded-2xl border border-black/5 p-5 dark:border-white/10">
            <div className="flex items-start justify-between gap-3">
              <p className="font-display text-lg font-semibold">{kit.data.headline}</p>
              <CopyButton text={`${kit.data.headline}\n\n${kit.data.description}`} />
            </div>
            <div className="mt-2 text-sm text-ink-soft dark:text-slate-300">
              <Markdown text={kit.data.description} />
            </div>
            <ul className="mt-3 flex flex-wrap gap-2">
              {kit.data.bullets.map((b) => (
                <li key={b} className="chip bg-brand-50 text-brand-700 dark:bg-white/5 dark:text-brand-200">
                  ✓ {b}
                </li>
              ))}
            </ul>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {Object.entries(kit.data.social_posts ?? {}).map(([k, v]) => (
              <div key={k} className="flex flex-col rounded-2xl border border-black/5 p-4 dark:border-white/10">
                <div className="flex items-center justify-between">
                  <Badge tone={k === "facebook" ? "blue" : k === "instagram" ? "purple" : "gray"} className="capitalize">
                    {k}
                  </Badge>
                  <CopyButton text={v} />
                </div>
                <p className="mt-2 whitespace-pre-line text-xs text-ink-soft dark:text-slate-300">{v}</p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <ErrorState error={kit.error} onRetry={() => kit.refetch()} />
      )}
    </div>
  );
}

function ReportsTab({ p }: { p: Property }) {
  const [frame, setFrame] = useState<{ title: string; url: string } | null>(null);
  const reports = [
    { title: "GIS analysis report", sub: "Area, valuation, population, cost & economics", url: apiUrl(`/gis/report/property/${p.id}`), icon: Layers },
    { title: "Investment outlook", sub: "Cost/development, predictions, risks & news ticker", url: apiUrl(`/gis/outlook/property/${p.id}`), icon: LineChart },
    { title: "Interactive GIS map", sub: "Base-map switcher with the property’s overlays", url: apiUrl(`/gis/map/property/${p.id}`), icon: Compass },
  ];
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        {reports.map((r) => (
          <button key={r.title} onClick={() => setFrame(r)} className="card card-hover flex flex-col items-start gap-3 p-5 text-start">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-white/5 dark:text-gold-300">
              <r.icon className="h-5 w-5" />
            </span>
            <span className="font-semibold">{r.title}</span>
            <span className="text-xs text-ink-mute">{r.sub}</span>
          </button>
        ))}
      </div>
      <Modal open={!!frame} onClose={() => setFrame(null)} size="xl" title={frame?.title}>
        {frame && (
          <div>
            <iframe title={frame.title} src={frame.url} className="h-[70vh] w-full rounded-xl border border-black/10 bg-white" />
            <a href={frame.url} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm mt-3">
              <Printer className="h-4 w-4" /> Open printable version
            </a>
          </div>
        )}
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------- sidebar
function ContactCard({ p }: { p: Property }) {
  const agents = useApi<{ agents: Agent[] }>("/crm/agents");
  const user = useAuth((s) => s.user);
  const nav = useNavigate();
  const agent = useMemo(() => {
    const list = agents.data?.agents ?? [];
    return list.find((a) => a.id === p.agent_id) ?? list.find((a) => a.region === p.city_name) ?? list[0];
  }, [agents.data, p]);
  const [mode, setMode] = useState<"enquiry" | "viewing" | null>(null);
  const [form, setForm] = useState({ name: user?.name ?? "", email: user?.email ?? "", phone: user?.mobile ?? "", message: `I'm interested in “${p.title}”. Please share more details.`, when: "" });

  const enquiry = useMutate(
    async () => {
      const lead = await post<{ id: string }>("/crm/leads", {
        name: form.name,
        email: form.email || undefined,
        phone: form.phone || undefined,
        source: "website",
        interest_use_type: p.use_type,
        interest_category: p.category,
        budget_max: p.price,
        city_id: p.city_id ?? undefined,
        scheme_id: p.scheme_id ?? undefined,
        assigned_agent_id: agent?.id,
        notes: `Enquiry on ${p.title} (${p.id}). ${form.message}`,
      });
      if (mode === "viewing" && form.when)
        await post("/crm/appointments", { title: `Viewing — ${p.title}`, scheduled_at: new Date(form.when).toISOString(), lead_id: lead.id, property_id: p.id, agent_id: agent?.id, notes: form.message });
      return lead;
    },
    { success: mode === "viewing" ? "Viewing requested — the agent will confirm shortly" : "Enquiry sent to the agent", onSuccess: () => setMode(null), invalidate: ["/crm"] },
  );

  const discuss = useMutate(() => post<{ id?: string; conversation?: { id: string } }>("/messaging/property-thread", { property_id: p.id, created_by: user?.id, title: p.title }), {
    onSuccess: (r) => nav(`/app/messages?c=${r.conversation?.id ?? r.id ?? ""}`),
  });

  return (
    <Card className="overflow-hidden">
      <div className="bg-brand-gradient p-5 text-white">
        <p className="text-xs uppercase tracking-widest text-white/70">Asking price</p>
        <p className="font-display text-3xl font-bold">{pkrShort(p.price)}</p>
        <p className="text-sm text-white/70">{pkr(p.price)}</p>
        {!!p.price_per_sqft && <p className="mt-1 text-xs text-gold-200">{pkr(p.price_per_sqft)} per sqft</p>}
      </div>
      <CardBody className="space-y-4">
        {agents.isLoading ? (
          <Skeleton className="h-16" />
        ) : agent ? (
          <div className="flex items-center gap-3">
            <Avatar name={agent.name} size={52} online />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{agent.name}</p>
              <p className="text-xs capitalize text-ink-mute">
                {agent.specialization} specialist · {agent.region}
              </p>
              <p className="mt-0.5 flex items-center gap-1 text-xs">
                <Star className="h-3.5 w-3.5 fill-gold-400 text-gold-400" /> {agent.rating} · {agent.deals_closed} deals
              </p>
            </div>
            <ShieldCheck className="h-5 w-5 text-brand-600" />
          </div>
        ) : null}
        <div className="grid grid-cols-2 gap-2">
          <a href={`tel:${agent?.phone ?? ""}`} className="btn btn-outline">
            <Phone className="h-4 w-4" /> Call
          </a>
          <a href={`mailto:${agent?.email ?? ""}?subject=${encodeURIComponent(p.title)}`} className="btn btn-outline">
            <Mail className="h-4 w-4" /> Email
          </a>
        </div>
        <Button className="w-full" icon={<MessageSquare className="h-4 w-4" />} onClick={() => setMode("enquiry")}>
          Send enquiry
        </Button>
        <Button variant="gold" className="w-full" icon={<CalendarCheck className="h-4 w-4" />} onClick={() => setMode("viewing")}>
          Book a viewing
        </Button>
        {user && (
          <Button variant="soft" className="w-full" loading={discuss.isPending} icon={<ClipboardList className="h-4 w-4" />} onClick={() => discuss.mutate()}>
            Open team discussion
          </Button>
        )}
      </CardBody>
      <Modal
        open={!!mode}
        onClose={() => setMode(null)}
        title={mode === "viewing" ? "Book a viewing" : "Send an enquiry"}
        subtitle={`${p.title} · ${agent?.name ?? "our team"} will reply`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
            <Button loading={enquiry.isPending} disabled={!form.name || (!form.email && !form.phone) || (mode === "viewing" && !form.when)} onClick={() => enquiry.mutate()}>
              {mode === "viewing" ? "Request viewing" : "Send"}
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name" className="sm:col-span-2">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Your name" />
          </Field>
          <Field label="Email">
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" />
          </Field>
          <Field label="Mobile">
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+92 3xx xxxxxxx" />
          </Field>
          {mode === "viewing" && (
            <Field label="Preferred date & time" className="sm:col-span-2">
              <Input type="datetime-local" value={form.when} onChange={(e) => setForm({ ...form, when: e.target.value })} />
            </Field>
          )}
          <Field label="Message" className="sm:col-span-2">
            <Textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} />
          </Field>
        </div>
        <p className="mt-3 text-xs text-ink-mute">Your enquiry is created as a CRM lead and routed to the listing agent.</p>
      </Modal>
    </Card>
  );
}

function MortgageMini({ price }: { price: number }) {
  const [down, setDown] = useState(25);
  const [rate, setRate] = useState(16);
  const [years, setYears] = useState(20);
  const loan = price * (1 - down / 100);
  const r = rate / 100 / 12;
  const n = years * 12;
  const emi = r ? (loan * r) / (1 - Math.pow(1 + r, -n)) : loan / n;
  return (
    <Card>
      <CardHeader title="Mortgage estimate" icon={<Tag className="h-4 w-4" />} action={<Link to="/tools/mortgage" className="text-xs font-semibold text-brand-700 dark:text-brand-300">Full calculator</Link>} />
      <CardBody className="space-y-4">
        <div className="rounded-2xl bg-brand-50 p-4 text-center dark:bg-white/5">
          <p className="text-xs uppercase text-ink-mute">Monthly instalment</p>
          <p className="font-display text-2xl font-bold text-brand-800 dark:text-gold-300">{pkr(Math.round(emi))}</p>
          <p className="text-xs text-ink-mute">Loan {pkrShort(loan)} · total interest {pkrShort(emi * n - loan)}</p>
        </div>
        {[
          ["Down payment", down, setDown, 10, 70, 5, `${down}%`],
          ["Interest rate", rate, setRate, 8, 25, 0.5, `${rate}%`],
          ["Tenure", years, setYears, 5, 25, 1, `${years} years`],
        ].map(([l, v, s, mn, mx, st, f]) => (
          <div key={l as string}>
            <div className="mb-1.5 flex justify-between text-xs font-semibold">
              <span>{l as string}</span>
              <span className="text-brand-700 dark:text-gold-300">{f as string}</span>
            </div>
            <Slider value={v as number} min={mn as number} max={mx as number} step={st as number} onChange={s as (n: number) => void} />
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------- page
type TabKey = "overview" | "location" | "investment" | "pricing" | "kit" | "reports";

export default function PropertyDetail() {
  const { id = "" } = useParams();
  const q = useApi<Property>(`/properties/${id}`);
  const all = useApi<PropertyList>("/properties", { limit: 200 });
  const stored = useApi<{ images: { url: string; is_primary?: boolean }[] }>(`/properties/${id}/images`);
  const pushRecent = usePrefs((s) => s.pushRecent);
  const [tab, setTab] = useState<TabKey>("overview");
  useEffect(() => {
    if (q.data) pushRecent(q.data.id);
  }, [q.data, pushRecent]);
  useEffect(() => {
    setTab("overview");
  }, [id]);

  if (q.isLoading)
    return (
      <div className="container space-y-4 py-8">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="aspect-[16/7] w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (q.error || !q.data)
    return (
      <div className="container py-16">
        <ErrorState error={q.error ?? "Property not found"} onRetry={() => q.refetch()} />
      </div>
    );
  const p = q.data;
  const uploads = [...(stored.data?.images ?? [])].sort((a, b) => Number(!!b.is_primary) - Number(!!a.is_primary)).map((x) => resolveImage(x.url));
  const imgs = uploads.length ? [...uploads, ...gallery(p).filter((g) => !uploads.includes(g))].slice(0, 10) : gallery(p);
  const similar = (all.data?.results ?? []).filter((x) => x.id !== p.id && (x.category === p.category || x.city_name === p.city_name)).slice(0, 8);
  const loc = [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", ");

  const facts = [
    { icon: Ruler, label: "Area", value: area(p) },
    { icon: Layers, label: "Total", value: p.total_area ? `${num(p.total_area)} sqft` : "—" },
    { icon: BedDouble, label: "Bedrooms", value: p.bedrooms ?? "—" },
    { icon: Bath, label: "Bathrooms", value: p.bathrooms ?? "—" },
    { icon: Building2, label: "Floors", value: p.floors ?? "—" },
    { icon: Tag, label: "Type", value: titleCase(p.category) },
  ];

  return (
    <div className="container py-6">
      <nav className="mb-4 flex flex-wrap items-center gap-1 text-xs text-ink-mute">
        <Link to="/" className="hover:text-brand-700">
          Home
        </Link>
        <ChevronRight className="h-3 w-3 rtl:rotate-180" />
        <Link to="/properties" className="hover:text-brand-700">
          Properties
        </Link>
        {p.city_name && (
          <>
            <ChevronRight className="h-3 w-3 rtl:rotate-180" />
            <Link to={`/cities/${encodeURIComponent(p.city_name)}`} className="hover:text-brand-700">
              {p.city_name}
            </Link>
          </>
        )}
        <ChevronRight className="h-3 w-3 rtl:rotate-180" />
        <span className="text-ink dark:text-slate-200">{p.title}</span>
      </nav>

      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex flex-wrap gap-2">
            {p.featured && <Badge tone="gold" icon={<Sparkles className="h-3 w-3" />}>Featured</Badge>}
            <Badge tone="green">{titleCase(p.use_type)}</Badge>
            <Badge tone="blue">{titleCase(p.status)}</Badge>
            <Badge tone="gray" icon={<ShieldCheck className="h-3 w-3" />}>Verified listing</Badge>
          </div>
          <h1 className="mt-3 font-display text-3xl font-bold text-brand-900 sm:text-4xl dark:text-white">{p.title}</h1>
          <p className="mt-2 flex items-center gap-1.5 text-ink-mute">
            <MapPin className="h-4 w-4 text-gold-600" /> {[p.street_address, loc].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex gap-2">
          <FavoriteButton id={p.id} className="h-11 w-11 shadow-none ring-1 ring-black/10" />
          <CompareButton id={p.id} label className="h-11 shadow-none ring-1 ring-black/10" />
          <Button
            variant="outline"
            icon={<Share2 className="h-4 w-4" />}
            onClick={() => {
              const url = location.href;
              if (navigator.share) navigator.share({ title: p.title, url }).catch(() => {});
              else navigator.clipboard.writeText(url).then(() => toast.success("Link copied"));
            }}
          >
            Share
          </Button>
        </div>
      </div>

      <Gallery images={imgs} title={p.title} />

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_360px]">
        <div className="min-w-0 space-y-6">
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
            {facts.map((f) => (
              <div key={f.label} className="card flex flex-col items-center gap-1 p-3 text-center">
                <f.icon className="h-5 w-5 text-brand-600 dark:text-gold-300" />
                <span className="text-[11px] uppercase text-ink-mute">{f.label}</span>
                <span className="text-sm font-bold">{f.value}</span>
              </div>
            ))}
          </div>

          <Card>
            <Tabs<TabKey>
              className="px-3"
              value={tab}
              onChange={setTab}
              tabs={[
                { value: "overview", label: "Overview", icon: <FileText className="h-4 w-4" /> },
                { value: "location", label: "Location & nearby", icon: <MapPin className="h-4 w-4" /> },
                { value: "investment", label: "Investment", icon: <TrendingUp className="h-4 w-4" /> },
                { value: "pricing", label: "AI pricing", icon: <Sparkles className="h-4 w-4" /> },
                { value: "kit", label: "Listing kit", icon: <Wand2 className="h-4 w-4" /> },
                { value: "reports", label: "Reports", icon: <Printer className="h-4 w-4" /> },
              ]}
            />
            <CardBody>
              <AnimatePresence mode="wait">
                <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                  {tab === "overview" && (
                    <div className="space-y-6">
                      <div>
                        <h2 className="font-display text-xl font-semibold">About this property</h2>
                        <p className="mt-2 leading-relaxed text-ink-soft dark:text-slate-300">{p.description || "No description provided yet."}</p>
                      </div>
                      <KeyValue
                        cols={3}
                        items={[
                          { label: "City", value: p.city_name ?? "—" },
                          { label: "Housing society", value: p.scheme_name ?? "—" },
                          { label: "Block / sector", value: p.block_name ?? p.sector ?? "—" },
                          { label: "Marla", value: p.marla_area ?? "—" },
                          { label: "Kanal", value: p.kanal_area ?? "—" },
                          { label: "Covered area", value: p.covered_area ? `${num(p.covered_area)} sqft` : "—" },
                          { label: "Price / sqft", value: p.price_per_sqft ? pkr(p.price_per_sqft) : "—" },
                          { label: "Listed", value: p.created_at ? new Date(p.created_at).toLocaleDateString() : "—" },
                          { label: "Reference", value: <span className="font-mono text-xs">{p.id.slice(0, 8).toUpperCase()}</span> },
                        ]}
                      />
                      {!!p.amenities?.length && (
                        <div>
                          <p className="mb-2 font-display font-semibold">Amenities</p>
                          <div className="flex flex-wrap gap-2">
                            {p.amenities.map((a) => (
                              <Badge key={a} tone="green">
                                {a}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {tab === "location" && <LocationTab p={p} />}
                  {tab === "investment" && <InvestmentTab p={p} />}
                  {tab === "pricing" && <PricingTab p={p} />}
                  {tab === "kit" && <ListingKitTab p={p} />}
                  {tab === "reports" && <ReportsTab p={p} />}
                </motion.div>
              </AnimatePresence>
            </CardBody>
          </Card>

          <div className="relative overflow-hidden rounded-3xl bg-brand-950 p-6 text-white">
            <div className="pointer-events-none absolute inset-0 bg-mesh opacity-60" />
            <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center">
              <Sparkles className="h-10 w-10 shrink-0 text-gold-300" />
              <div className="flex-1">
                <p className="font-display text-lg font-semibold">Not sure it’s the one?</p>
                <p className="text-sm text-white/70">The Homebuying agent can compare this listing with everything else in your budget and flag better-value bargains.</p>
              </div>
              <Link to={`/ai/agents/conversational_buyer_agent?objective=${encodeURIComponent(`${p.bedrooms ?? ""} bed ${p.category} in ${p.city_name ?? ""} around ${pkrShort(p.price, false)}`)}`} className="btn btn-gold shrink-0">
                Ask the agent
              </Link>
            </div>
          </div>
        </div>

        <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <ContactCard p={p} />
          <MortgageMini price={p.price} />
          <AdSlot slot="sidebar" placement="detail" />
        </aside>
      </div>

      {!!similar.length && (
        <section className="mt-14">
          <div className="mb-6 flex items-end justify-between">
            <div>
              <p className="section-eyebrow">You may also like</p>
              <h2 className="section-title mt-1 !text-2xl sm:!text-3xl">Similar properties</h2>
            </div>
            <Link to={`/properties?category=${p.category}`} className="btn btn-outline btn-sm">
              More like this
            </Link>
          </div>
          <Carousel slideClass="basis-[85%] sm:basis-1/2 lg:basis-1/3 xl:basis-1/4">
            {similar.map((s) => (
              <PropertyCard key={s.id} p={s} />
            ))}
          </Carousel>
        </section>
      )}
    </div>
  );
}
