import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Marker, Popup } from "react-leaflet";
import { BedDouble, Grid3X3, KeyRound, List, Map as MapIcon, MapPin, Navigation, RotateCcw, Search, SlidersHorizontal, Sparkles, Wand2, X } from "lucide-react";
import type { City, Property, PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { post } from "@/lib/api";
import { area, pkrShort, titleCase } from "@/lib/format";
import { coverImage, HERO } from "@/lib/images";
import { cn } from "@/lib/utils";
import { Badge, Button, Drawer, EmptyState, ErrorState, RangeSlider, Segmented, Skeleton, Toggle } from "@/components/ui";
import { CompareButton, FavoriteButton, NearbyNote, PropertyCard } from "@/components/property/PropertyCard";
import { PortalMap, pin } from "@/components/map/PortalMap";
import { AdSlot } from "@/components/ads/AdSlot";

const CATEGORIES = ["house", "apartment", "plot", "shop", "office", "floor", "building", "space"];
const USE_TYPES = ["residential", "commercial", "mix"];
const MAX_PRICE = 200_000_000;
/** `near=` kinds the backend understands (school, mosque, hospital, market, park, transport …). */
const NEAR_KINDS = [
  { value: "school", label: "School" },
  { value: "mosque", label: "Mosque" },
  { value: "hospital", label: "Hospital" },
  { value: "market", label: "Market" },
  { value: "park", label: "Park" },
  { value: "transport", label: "Transport" },
];
const NEAR_KM = [1, 2, 5];
const SORTS = [
  { value: "relevance", label: "Featured first" },
  { value: "price_asc", label: "Price: low to high" },
  { value: "price_desc", label: "Price: high to low" },
  { value: "size_desc", label: "Size: largest" },
  { value: "newest", label: "Newest" },
];

interface ParsedBrief {
  city?: string;
  category?: string;
  bedrooms?: number;
  budget_min?: number;
  budget_max?: number;
  must_have?: string[];
  nice_to_have?: string[];
  confidence?: number;
  parsed_fields?: string[];
}

interface RentalUnit {
  id: string;
  title: string;
  city: string;
  scheme: string | null;
  rent: number;
  deposit: number;
  bedrooms: number;
  area: number;
  status: string;
  amenities: string[];
}

function useFilters() {
  const [sp, setSp] = useSearchParams();
  const f = {
    q: sp.get("q") ?? "",
    city: sp.get("city") ?? "",
    category: sp.get("category") ?? "",
    use_type: sp.get("use_type") ?? "",
    purpose: sp.get("purpose") ?? "buy",
    minPrice: Number(sp.get("min") ?? 0),
    maxPrice: Number(sp.get("max") ?? MAX_PRICE),
    beds: Number(sp.get("beds") ?? 0),
    baths: Number(sp.get("baths") ?? 0),
    feature: sp.get("feature") ?? "",
    near: sp.get("near") ?? "",
    nearPlace: sp.get("near_place") ?? "",
    nearKm: Number(sp.get("near_km") ?? 2),
    featured: sp.get("featured") === "1",
    sort: sp.get("sort") ?? "relevance",
    view: (sp.get("view") ?? "grid") as "grid" | "list" | "map",
    project: sp.get("project") ?? "",
  };
  const set = (patch: Partial<Record<keyof typeof f, string | number | boolean>>) => {
    const next = new URLSearchParams(sp);
    const keyMap: Record<string, string> = { minPrice: "min", maxPrice: "max", nearPlace: "near_place", nearKm: "near_km" };
    for (const [k, v] of Object.entries(patch)) {
      const key = keyMap[k] ?? k;
      const isDefault =
        v === "" || v === false || v === 0 || (k === "maxPrice" && v === MAX_PRICE) || (k === "sort" && v === "relevance") || (k === "view" && v === "grid") || (k === "purpose" && v === "buy") || (k === "nearKm" && v === 2);
      if (isDefault) next.delete(key);
      else next.set(key, v === true ? "1" : String(v));
    }
    setSp(next, { replace: true });
  };
  const reset = () => setSp(new URLSearchParams(f.view !== "grid" ? { view: f.view } : {}), { replace: true });
  return { f, set, reset };
}

function matches(p: Property, f: ReturnType<typeof useFilters>["f"]) {
  if (f.city && (p.city_name ?? "").toLowerCase() !== f.city.toLowerCase()) return false;
  if (f.category && p.category !== f.category) return false;
  if (f.use_type && p.use_type !== f.use_type) return false;
  if (p.price < f.minPrice || p.price > f.maxPrice) return false;
  if (f.beds && (p.bedrooms ?? 0) < f.beds) return false;
  if (f.baths && (p.bathrooms ?? 0) < f.baths) return false;
  if (f.featured && !p.featured) return false;
  if (f.project && p.project_id !== f.project) return false;
  if (f.q) {
    const hay = [p.title, p.description, p.scheme_name, p.block_name, p.city_name, p.category, p.use_type, p.street_address].join(" ").toLowerCase();
    const words = f.q.toLowerCase().split(/\s+/).filter((w) => w.length > 2 && !["for", "the", "and", "with", "under", "in"].includes(w));
    if (words.length && !words.some((w) => hay.includes(w))) return false;
  }
  return true;
}

function FilterPanel({ f, set, reset, cities, counts }: { f: ReturnType<typeof useFilters>["f"]; set: ReturnType<typeof useFilters>["set"]; reset: () => void; cities: City[]; counts: Record<string, number> }) {
  const [price, setPrice] = useState<[number, number]>([f.minPrice, f.maxPrice]);
  useEffect(() => setPrice([f.minPrice, f.maxPrice]), [f.minPrice, f.maxPrice]);
  const [place, setPlace] = useState(f.nearPlace);
  useEffect(() => setPlace(f.nearPlace), [f.nearPlace]);
  const [feature, setFeature] = useState(f.feature);
  useEffect(() => setFeature(f.feature), [f.feature]);
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 font-display font-semibold">
          <SlidersHorizontal className="h-4 w-4 text-brand-600" /> Filters
        </p>
        <button onClick={reset} className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300">
          <RotateCcw className="h-3 w-3" /> Reset
        </button>
      </div>
      <CityFilter cities={cities} value={f.city} onChange={(city) => set({ city })} />
      <div>
        <p className="label">Property type</p>
        <div className="grid grid-cols-2 gap-1.5">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              onClick={() => set({ category: f.category === c ? "" : c })}
              className={cn("flex items-center justify-between rounded-xl px-3 py-2 text-sm font-medium ring-1 transition", f.category === c ? "bg-brand-50 text-brand-800 ring-brand-500 dark:bg-brand-500/15 dark:text-white" : "ring-black/10 hover:ring-brand-300 dark:ring-white/10")}
            >
              {titleCase(c)}
              <span className="text-xs text-ink-mute">{counts[c] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="label">Use</p>
        <div className="flex flex-wrap gap-1.5">
          {["", ...USE_TYPES].map((u) => (
            <button key={u || "any"} onClick={() => set({ use_type: u })} className={cn("chip ring-1 transition", f.use_type === u ? "bg-brand-700 text-white ring-brand-700" : "bg-white text-ink-soft ring-black/10 hover:ring-brand-300 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10")}>
              {u ? titleCase(u) : "Any"}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="label">Price range</p>
        <div onPointerUp={() => set({ minPrice: price[0], maxPrice: price[1] })} onKeyUp={() => set({ minPrice: price[0], maxPrice: price[1] })}>
          <RangeSlider min={0} max={MAX_PRICE} step={2_500_000} value={price} onChange={setPrice} format={(v) => (v >= MAX_PRICE ? "20 Crore+" : pkrShort(v, false))} />
        </div>
      </div>
      <div>
        <p className="label">Bedrooms (min)</p>
        <div className="flex gap-1.5">
          {[0, 1, 2, 3, 4, 5].map((b) => (
            <button key={b} onClick={() => set({ beds: b })} className={cn("h-9 flex-1 rounded-lg text-sm font-semibold ring-1 transition", f.beds === b ? "bg-brand-700 text-white ring-brand-700" : "ring-black/10 hover:ring-brand-300 dark:ring-white/10")}>
              {b === 0 ? "Any" : `${b}+`}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="label">Bathrooms (min)</p>
        <div className="flex gap-1.5">
          {[0, 1, 2, 3, 4].map((b) => (
            <button key={b} onClick={() => set({ baths: b })} className={cn("h-9 flex-1 rounded-lg text-sm font-semibold ring-1 transition", f.baths === b ? "bg-brand-700 text-white ring-brand-700" : "ring-black/10 hover:ring-brand-300 dark:ring-white/10")}>
              {b === 0 ? "Any" : `${b}+`}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="label">Close to</p>
        <div className="flex flex-wrap gap-1.5">
          {NEAR_KINDS.map((k) => (
            <button key={k.value} onClick={() => set({ near: f.near === k.value ? "" : k.value })} className={cn("chip ring-1 transition", f.near === k.value ? "bg-brand-700 text-white ring-brand-700" : "bg-white text-ink-soft ring-black/10 hover:ring-brand-300 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10")}>
              {k.label}
            </button>
          ))}
        </div>
        <form
          className="mt-2"
          onSubmit={(e) => {
            e.preventDefault();
            set({ nearPlace: place.trim() });
          }}
        >
          <div className="flex items-center gap-2 rounded-xl px-3 ring-1 ring-black/10 focus-within:ring-brand-400 dark:ring-white/10">
            <Navigation className="h-4 w-4 shrink-0 text-brand-600" />
            <input value={place} onChange={(e) => setPlace(e.target.value)} onBlur={() => place.trim() !== f.nearPlace && set({ nearPlace: place.trim() })} placeholder="A place, e.g. G-13 or a university" className="h-10 w-full bg-transparent text-sm outline-none placeholder:text-ink-mute" />
          </div>
        </form>
        {(f.near || f.nearPlace) && (
          <div className="mt-2 flex gap-1.5">
            {NEAR_KM.map((km) => (
              <button key={km} onClick={() => set({ nearKm: km })} className={cn("h-8 flex-1 rounded-lg text-xs font-semibold ring-1 transition", f.nearKm === km ? "bg-brand-700 text-white ring-brand-700" : "ring-black/10 hover:ring-brand-300 dark:ring-white/10")}>
                within {km} km
              </button>
            ))}
          </div>
        )}
      </div>
      <div>
        <p className="label">Feature</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            set({ feature: feature.trim() });
          }}
        >
          <input value={feature} onChange={(e) => setFeature(e.target.value)} onBlur={() => feature.trim() !== f.feature && set({ feature: feature.trim() })} placeholder="e.g. solar, basement, corner" className="input text-sm" />
        </form>
      </div>
      <Toggle checked={f.featured} onChange={(v) => set({ featured: v })} label={<span className="text-sm font-medium">Featured only</span>} />
      <AdSlot slot="sidebar" />
    </div>
  );
}

function ListRow({ p }: { p: Property }) {
  return (
    <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <Link to={`/properties/${p.id}`} className="card card-hover group flex flex-col overflow-hidden sm:flex-row">
        <div className="relative aspect-[16/10] shrink-0 overflow-hidden sm:aspect-auto sm:w-72">
          <img src={coverImage(p)} alt="" className="h-full w-full object-cover transition duration-700 group-hover:scale-105" />
          {p.featured && <span className="chip absolute start-3 top-3 bg-gold-gradient text-brand-950">Featured</span>}
        </div>
        <div className="flex flex-1 flex-col p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="font-display text-lg font-semibold group-hover:text-brand-700">{p.title}</h3>
              <p className="mt-1 flex items-center gap-1 text-sm text-ink-mute">
                <MapPin className="h-4 w-4 text-gold-600" /> {[p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", ")}
              </p>
            </div>
            <p className="shrink-0 font-display text-xl font-bold text-brand-700 dark:text-gold-300">{pkrShort(p.price)}</p>
          </div>
          <NearbyNote p={p} />
          <p className="mt-3 line-clamp-2 text-sm text-ink-soft dark:text-slate-300">{p.description}</p>
          <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
            <Badge tone="gray">{titleCase(p.category)}</Badge>
            <Badge tone="blue">{area(p)}</Badge>
            {!!p.bedrooms && <Badge tone="green">{p.bedrooms} beds</Badge>}
            {!!p.price_per_sqft && <Badge tone="gold">{pkrShort(p.price_per_sqft)}/sqft</Badge>}
            <span className="ms-auto flex gap-2">
              <FavoriteButton id={p.id} className="shadow-none ring-1 ring-black/10" />
              <CompareButton id={p.id} className="shadow-none ring-1 ring-black/10" />
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

function Rentals({ city }: { city: string }) {
  const q = useApi<{ units: RentalUnit[] }>("/leasing/units");
  const units = (q.data?.units ?? []).filter((u) => !city || u.city.toLowerCase() === city.toLowerCase());
  if (!units.length) return null;
  return (
    <div className="mb-8">
      <p className="mb-3 flex items-center gap-2 font-display text-lg font-semibold">
        <KeyRound className="h-5 w-5 text-gold-600" /> Available for rent
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {units.map((u) => (
          <div key={u.id} className="card overflow-hidden">
            <img src={coverImage({ id: u.id, title: u.title, category: u.bedrooms >= 3 ? "house" : "apartment" })} alt="" className="aspect-[16/9] w-full object-cover" />
            <div className="p-4">
              <p className="font-semibold">{u.title}</p>
              <p className="text-xs text-ink-mute">{[u.scheme, u.city].filter(Boolean).join(", ")}</p>
              <div className="mt-2 flex items-end justify-between">
                <p className="font-display text-lg font-bold text-brand-700 dark:text-gold-300">
                  {pkrShort(u.rent)}
                  <span className="text-xs font-medium text-ink-mute">/month</span>
                </p>
                <span className="inline-flex items-center gap-1 text-xs text-ink-mute">
                  <BedDouble className="h-3.5 w-3.5" /> {u.bedrooms} · {u.area} sqft
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {u.amenities.map((a) => (
                  <span key={a} className="chip bg-brand-50 text-[10px] text-brand-700 dark:bg-white/5 dark:text-brand-200">
                    {a}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Properties() {
  const { f, set, reset } = useFilters();
  // Place- and feature-aware filters run on the server (/search); everything else filters the full list here.
  const serverSearch = !!(f.near || f.nearPlace || f.feature);
  const q = useApi<PropertyList>(
    serverSearch ? "/search" : "/properties",
    serverSearch ? { near: f.near, near_place: f.nearPlace, near_km: f.near || f.nearPlace ? f.nearKm : undefined, feature: f.feature, limit: 1000 } : { limit: 1000 },
  );
  const cities = useApi<{ cities: City[] }>("/cities");
  const [text, setText] = useState(f.q);
  const [mobileFilters, setMobileFilters] = useState(false);
  const [brief, setBrief] = useState<ParsedBrief | null>(null);
  const [parsing, setParsing] = useState(false);
  useEffect(() => setText(f.q), [f.q]);

  const all = q.data?.results ?? [];
  const counts = useMemo(() => all.reduce<Record<string, number>>((a, p) => ((a[p.category] = (a[p.category] ?? 0) + 1), a), {}), [all]);
  const results = useMemo(() => {
    const r = all.filter((p) => matches(p, f));
    const s = [...r];
    if (f.sort === "price_asc") s.sort((a, b) => a.price - b.price);
    else if (f.sort === "price_desc") s.sort((a, b) => b.price - a.price);
    else if (f.sort === "size_desc") s.sort((a, b) => (b.total_area ?? 0) - (a.total_area ?? 0));
    else if (f.sort === "newest") s.sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
    else if (!f.near && !f.nearPlace) s.sort((a, b) => Number(!!b.featured) - Number(!!a.featured)); // near searches come back closest first
    return s;
  }, [all, f]);
  const nearPlace = q.data?.near_place;
  const outside = q.data?.nearest_outside_radius ?? [];

  const aiSearch = async () => {
    if (!text.trim()) return;
    setParsing(true);
    try {
      const r = await post<ParsedBrief>("/intelligence/buyer/parse", { text });
      setBrief(r);
      set({
        q: "",
        city: r.city ?? "",
        category: r.category ?? "",
        beds: r.bedrooms ?? 0,
        maxPrice: r.budget_max ? Math.min(MAX_PRICE, Math.round(r.budget_max * 1.15)) : MAX_PRICE,
        minPrice: 0,
      });
    } catch {
      set({ q: text });
    } finally {
      setParsing(false);
    }
  };

  const activeChips = [
    f.q && { k: "q", label: `“${f.q}”` },
    f.project && { k: "project", label: "One project’s units" },
    f.city && { k: "city", label: f.city },
    f.category && { k: "category", label: titleCase(f.category) },
    f.use_type && { k: "use_type", label: titleCase(f.use_type) },
    f.beds > 0 && { k: "beds", label: `${f.beds}+ beds` },
    f.baths > 0 && { k: "baths", label: `${f.baths}+ baths` },
    f.near && { k: "near", label: `Near a ${NEAR_KINDS.find((k) => k.value === f.near)?.label.toLowerCase() ?? f.near} (${f.nearKm} km)` },
    f.nearPlace && { k: "nearPlace", label: `Within ${f.nearKm} km of ${nearPlace?.found && nearPlace.name ? nearPlace.name : f.nearPlace}` },
    f.feature && { k: "feature", label: `With “${f.feature}”` },
    (f.minPrice > 0 || f.maxPrice < MAX_PRICE) && { k: "price", label: `${pkrShort(f.minPrice, false)} – ${pkrShort(f.maxPrice, false)}` },
    f.featured && { k: "featured", label: "Featured" },
  ].filter(Boolean) as { k: string; label: string }[];

  const pts = results.filter((p) => p.latitude && p.longitude);

  return (
    <div>
      <section className="relative isolate overflow-hidden bg-brand-950 text-white">
        <img src={HERO.villa} alt="" className="absolute inset-0 -z-10 h-full w-full object-cover opacity-35" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-r from-brand-950 via-brand-950/85 to-brand-900/40" />
        <div className="container py-10 sm:py-14">
          <p className="section-eyebrow !text-gold-300">{f.purpose === "rent" ? "Homes for rent" : "Properties for sale"}</p>
          <h1 className="mt-2 font-display text-3xl font-bold sm:text-4xl">Find your next property</h1>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              set({ q: text });
            }}
            className="mt-6 flex max-w-3xl flex-col gap-2 rounded-3xl bg-white p-2 shadow-2xl sm:flex-row sm:rounded-full dark:bg-[#0d1f16]"
          >
            <div className="flex flex-1 items-center gap-3 px-4">
              <Search className="h-5 w-5 text-brand-600" />
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Try “3 bed house in DHA Lahore under 3 crore”" className="h-12 w-full bg-transparent text-ink outline-none placeholder:text-ink-mute dark:text-white" />
            </div>
            <Button type="button" variant="gold" className="h-12 rounded-full" loading={parsing} onClick={aiSearch} icon={<Wand2 className="h-4 w-4" />}>
              AI search
            </Button>
            <Button type="submit" className="h-12 rounded-full px-6">
              Search
            </Button>
          </form>
          <AnimatePresence>
            {brief && (
              <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                <span className="inline-flex items-center gap-1.5 font-semibold text-gold-200">
                  <Sparkles className="h-4 w-4" /> AI understood ({Math.round((brief.confidence ?? 0) * 100)}% confident):
                </span>
                {brief.city && <span className="chip bg-white/15">{brief.city}</span>}
                {brief.category && <span className="chip bg-white/15">{titleCase(brief.category)}</span>}
                {brief.bedrooms && <span className="chip bg-white/15">{brief.bedrooms} beds</span>}
                {brief.budget_max && <span className="chip bg-white/15">≤ {pkrShort(brief.budget_max)}</span>}
                {[...(brief.must_have ?? []), ...(brief.nice_to_have ?? [])].map((m) => (
                  <span key={m} className="chip bg-gold-400/20 text-gold-100">
                    {m}
                  </span>
                ))}
                <Link to={`/ai/agents/conversational_buyer_agent?objective=${encodeURIComponent(text)}`} className="chip bg-gold-gradient text-brand-950">
                  Let the Buyer Agent shortlist →
                </Link>
                <button onClick={() => setBrief(null)} className="text-white/60 hover:text-white" aria-label="Dismiss">
                  <X className="h-4 w-4" />
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </section>

      <div className="container grid gap-8 py-8 lg:grid-cols-[280px_1fr]">
        <aside className="hidden lg:block">
          <div className="card sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto p-5">
            <FilterPanel f={f} set={set} reset={reset} cities={cities.data?.cities ?? []} counts={counts} />
          </div>
        </aside>

        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Button variant="outline" size="sm" className="lg:hidden" icon={<SlidersHorizontal className="h-4 w-4" />} onClick={() => setMobileFilters(true)}>
              Filters
            </Button>
            <Segmented size="sm" value={f.purpose} onChange={(v) => set({ purpose: v })} options={[{ value: "buy", label: "Buy" }, { value: "rent", label: "Rent" }]} />
            <p className="text-sm text-ink-mute">
              {serverSearch ? (
                <>
                  <b className="text-ink dark:text-white">{results.length}</b> matching
                </>
              ) : (
                <>
                  <b className="text-ink dark:text-white">{results.length}</b> of {all.length} properties
                </>
              )}
            </p>
            <div className="ms-auto flex items-center gap-2">
              <select value={f.sort} onChange={(e) => set({ sort: e.target.value })} className="input w-auto py-2 text-sm">
                {SORTS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <Segmented
                size="sm"
                value={f.view}
                onChange={(v) => set({ view: v })}
                options={[
                  { value: "grid", label: <Grid3X3 className="h-4 w-4" /> },
                  { value: "list", label: <List className="h-4 w-4" /> },
                  { value: "map", label: <MapIcon className="h-4 w-4" /> },
                ]}
              />
            </div>
          </div>

          {!!activeChips.length && (
            <div className="mb-5 flex flex-wrap gap-2">
              {activeChips.map((c) => (
                <button
                  key={c.k}
                  onClick={() => (c.k === "price" ? set({ minPrice: 0, maxPrice: MAX_PRICE }) : set({ [c.k]: c.k === "beds" || c.k === "baths" ? 0 : c.k === "featured" ? false : "" } as never))}
                  className="chip bg-brand-700 text-white"
                >
                  {c.label} <X className="h-3 w-3" />
                </button>
              ))}
              <button onClick={reset} className="text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300">
                Clear all
              </button>
            </div>
          )}

          {f.purpose === "rent" && <Rentals city={f.city} />}

          {q.error ? (
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          ) : q.isLoading ? (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-80" />
              ))}
            </div>
          ) : !results.length && nearPlace && !nearPlace.found ? (
            <EmptyState title={`Couldn’t find “${f.nearPlace}” on the map`} hint="Try a sector, society, landmark or road name — e.g. “G-13”, “DHA Phase 2” or “Rawalpindi Medical University”." action={<Button variant="outline" onClick={() => set({ nearPlace: "" })}>Clear the place</Button>} />
          ) : !results.length && outside.length ? (
            <div>
              <p className="mb-4 text-sm text-ink-mute">
                Nothing within {f.nearKm} km of <b className="text-ink dark:text-white">{nearPlace?.name ?? f.nearPlace}</b> — these are the closest listings:
              </p>
              <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                {outside.map((p) => (
                  <PropertyCard key={p.id} p={p} />
                ))}
              </div>
            </div>
          ) : !results.length ? (
            <EmptyState
              title="No properties match these filters"
              hint="Loosen a filter, or let the AI buyer agent search the whole market for you."
              action={
                <div className="flex gap-2">
                  <Button variant="outline" onClick={reset}>
                    Reset filters
                  </Button>
                  <Link className="btn btn-gold" to={`/ai?q=${encodeURIComponent(f.q || "Find me a property")}`}>
                    Ask AI
                  </Link>
                </div>
              }
            />
          ) : f.view === "map" ? (
            <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
              <PortalMap height="72vh" fit={pts.map((p) => [p.latitude!, p.longitude!])} scrollWheelZoom>
                {pts.map((p) => (
                  <Marker key={p.id} position={[p.latitude!, p.longitude!]} icon={pin(p.featured ? "featured" : p.use_type === "commercial" ? "commercial" : p.category === "plot" ? "plot" : "property", { label: pkrShort(p.price, false) })}>
                    <Popup>
                      <Link to={`/properties/${p.id}`}>
                        <img src={coverImage(p)} alt="" className="h-28 w-full object-cover" />
                        <div className="p-3">
                          <p className="font-semibold text-ink">{p.title}</p>
                          <p className="font-bold text-brand-700">{pkrShort(p.price)}</p>
                        </div>
                      </Link>
                    </Popup>
                  </Marker>
                ))}
              </PortalMap>
              <div className="max-h-[72vh] space-y-3 overflow-y-auto pe-1">
                {results.map((p) => (
                  <PropertyCard key={p.id} p={p} compact />
                ))}
              </div>
            </div>
          ) : f.view === "list" ? (
            <div className="space-y-4">
              {results.map((p, i) => (
                <div key={p.id}>
                  <ListRow p={p} />
                  {i === 3 && <AdSlot slot="banner" className="mt-4" placement="explore" />}
                </div>
              ))}
            </div>
          ) : (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {results.flatMap((p, i) => {
                const items = [<PropertyCard key={p.id} p={p} />];
                if (i === 5) items.push(<AdSlot key="ad" slot="infeed" placement="explore" />);
                return items;
              })}
            </div>
          )}
        </div>
      </div>

      <Drawer open={mobileFilters} onClose={() => setMobileFilters(false)} title="Filters" side="left">
        <div className="p-5">
          <FilterPanel f={f} set={set} reset={reset} cities={cities.data?.cities ?? []} counts={counts} />
          <Button className="mt-6 w-full" onClick={() => setMobileFilters(false)}>
            Show {results.length} results
          </Button>
        </div>
      </Drawer>
    </div>
  );
}

/**
 * City filter: the main cities as chips (in the portal's order from the API), the chosen city
 * always visible, and every city one tap away in a searchable list grouped by province.
 */
const TOP_CITIES = 6;
function CityFilter({ cities, value, onChange }: { cities: City[]; value: string; onChange: (city: string) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ranked = cities; // already in the portal's order (Islamabad, Rawalpindi, Lahore, Karachi, then by population)
  const top = ranked.slice(0, TOP_CITIES);
  const chosen = value && !top.some((c) => c.name.toLowerCase() === value.toLowerCase()) ? ranked.find((c) => c.name.toLowerCase() === value.toLowerCase()) : undefined;
  const chips = chosen ? [...top, chosen] : top;
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const m = new Map<string, City[]>();
    for (const c of cities) {
      if (q && !c.name.toLowerCase().includes(q) && !(c.state ?? "").toLowerCase().includes(q)) continue;
      const k = c.state || "Other";
      m.set(k, [...(m.get(k) ?? []), c]);
    }
    return [...m.entries()]; // provinces in the order of their first city
  }, [cities, query]);
  const chip = (active: boolean) =>
    cn("chip ring-1 transition", active ? "bg-brand-700 text-white ring-brand-700" : "bg-white text-ink-soft ring-black/10 hover:ring-brand-300 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10");
  const pick = (name: string) => {
    onChange(value.toLowerCase() === name.toLowerCase() ? "" : name);
    setOpen(false);
    setQuery("");
  };
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="label">City</p>
        {cities.length > TOP_CITIES && (
          <button type="button" onClick={() => setOpen((o) => !o)} className="text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300" aria-expanded={open}>
            {open ? "Show fewer" : `All ${cities.length} cities`}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => onChange("")} className={chip(!value)}>
          All
        </button>
        {chips.map((c) => (
          <button key={c.id} type="button" onClick={() => pick(c.name)} className={chip(value.toLowerCase() === c.name.toLowerCase())}>
            {c.name}
            {!!c.properties && <span className="ms-1 text-[10px] opacity-70">{c.properties}</span>}
          </button>
        ))}
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mt-3 rounded-2xl border border-black/5 bg-white p-2 dark:border-white/10 dark:bg-white/5">
              <label className="flex items-center gap-2 rounded-xl bg-black/5 px-2.5 dark:bg-white/10">
                <Search className="h-3.5 w-3.5 text-ink-mute" />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a city or province" aria-label="Find a city" className="h-8 w-full bg-transparent text-sm outline-none" autoFocus />
              </label>
              <div className="mt-2 max-h-72 space-y-3 overflow-y-auto pe-1">
                {groups.map(([province, list]) => (
                  <div key={province}>
                    <p className="px-1 text-[10px] font-bold uppercase tracking-wider text-ink-mute">{province}</p>
                    <div className="mt-1 grid grid-cols-2 gap-1">
                      {list.map((c) => {
                        const active = value.toLowerCase() === c.name.toLowerCase();
                        return (
                          <button
                            key={c.id}
                            type="button"
                            onClick={() => pick(c.name)}
                            className={cn("flex items-center justify-between gap-1 rounded-lg px-2 py-1.5 text-start text-[13px] transition", active ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/10")}
                          >
                            <span className="truncate">{c.name}</span>
                            {!!c.properties && <span className={cn("text-[10px] tabular-nums", active ? "text-white/80" : "text-ink-mute")}>{c.properties}</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
                {!groups.length && <p className="px-1 py-3 text-sm text-ink-mute">No city matches “{query}”.</p>}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
