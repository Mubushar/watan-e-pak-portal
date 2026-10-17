import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, animate, motion, useInView } from "framer-motion";
import { Marker, Popup } from "react-leaflet";
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  Building,
  Building2,
  Calculator,
  CheckCircle2,
  Cpu,
  Factory,
  Heart,
  Home as HomeIcon,
  KeyRound,
  Landmark,
  LandPlot,
  LineChart,
  MapPin,
  Quote,
  Ruler,
  Scale,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Store,
  Trees,
  TrendingUp,
  Users,
  Warehouse,
} from "lucide-react";
import type { City, NewsItem, Property, PropertyList, Story } from "@/types";
import { useApi } from "@/hooks/useApi";
import { get } from "@/lib/api";
import { compact, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { cityImage, coverImage, HERO, themedImage } from "@/lib/images";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";
import { AreaTrend, Badge, Carousel, Section, Segmented, Skeleton } from "@/components/ui";
import { PropertyCard, PropertyRow } from "@/components/property/PropertyCard";
import { PortalMap, pin } from "@/components/map/PortalMap";
import { AdSlot } from "@/components/ads/AdSlot";

// ---------------------------------------------------------------- helpers
function CountUp({ to, suffix = "" }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!inView) return;
    const c = animate(0, to, { duration: 1.6, ease: "easeOut", onUpdate: (x) => setV(x) });
    return () => c.stop();
  }, [inView, to]);
  return (
    <span ref={ref}>
      {Math.round(v).toLocaleString()}
      {suffix}
    </span>
  );
}

const HERO_SLIDES = [
  { img: HERO.panorama, caption: "Islamabad · Margalla foothills" },
  { img: HERO.villa, caption: "Luxury villas · DHA & Bahria" },
  { img: HERO.landscape, caption: "From the north to the coast" },
];

const PURPOSES = [
  { value: "buy", label: "Buy", icon: <HomeIcon className="h-4 w-4" /> },
  { value: "rent", label: "Rent", icon: <KeyRound className="h-4 w-4" /> },
  { value: "plot", label: "Plot", icon: <LandPlot className="h-4 w-4" /> },
  { value: "commercial", label: "Commercial", icon: <Building2 className="h-4 w-4" /> },
] as const;

const FEATURES = [
  { icon: ShieldCheck, title: "Verified Listings", sub: "Trusted & authentic" },
  { icon: Cpu, title: "AI Recommendations", sub: "Smarter property search" },
  { icon: MapPin, title: "Interactive Map", sub: "Explore locations" },
  { icon: LineChart, title: "Market Insights", sub: "Data-driven decisions" },
  { icon: Scale, title: "Easy Comparisons", sub: "Find the best deal" },
  { icon: Heart, title: "Save & Shortlist", sub: "Your favourite properties" },
];

const CATEGORIES = [
  { key: "house", label: "Houses", icon: HomeIcon },
  { key: "apartment", label: "Apartments", icon: Building },
  { key: "plot", label: "Plots", icon: LandPlot },
  { key: "shop", label: "Shops", icon: Store },
  { key: "office", label: "Offices", icon: Building2 },
  { key: "building", label: "Buildings", icon: Factory },
  { key: "floor", label: "Floors", icon: Warehouse },
  { key: "farmhouse", label: "Farmhouses", icon: Trees },
];

const SHOWCASE_AGENTS = [
  { key: "conversational_buyer_agent", name: "Homebuying Agent", blurb: "Understands your brief in plain language, shortlists homes and checks affordability.", icon: HomeIcon },
  { key: "seller_pricing_agent", name: "Seller Pricing Agent", blurb: "Comparable-sales pricing range, net proceeds and a full marketing kit in seconds.", icon: TrendingUp },
  { key: "investment_screener", name: "Investment Screener", blurb: "Screens the market into risk-adjusted top picks with IRR, DSCR and exit timing.", icon: LineChart },
  { key: "autonomous_leasing_agent", name: "Leasing Agent", blurb: "Answers tenant enquiries 24/7, screens applicants and recommends renewals.", icon: KeyRound },
];

// ---------------------------------------------------------------- hero
function Hero() {
  const t = useT();
  const nav = useNavigate();
  const lang = usePrefs((s) => s.lang);
  const [slide, setSlide] = useState(0);
  const [purpose, setPurpose] = useState<(typeof PURPOSES)[number]["value"]>("buy");
  const [q, setQ] = useState("");
  const [city, setCity] = useState("");
  const cities = useApi<{ cities: City[] }>("/cities");

  useEffect(() => {
    const id = setInterval(() => setSlide((s) => (s + 1) % HERO_SLIDES.length), 6500);
    return () => clearInterval(id);
  }, []);

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (city) params.set("city", city);
    if (purpose === "plot") params.set("category", "plot");
    if (purpose === "commercial") params.set("use_type", "commercial");
    if (purpose === "rent") params.set("purpose", "rent");
    nav(`/properties?${params.toString()}`);
  };

  return (
    <section className="relative isolate overflow-hidden">
      {/* crossfading background slider */}
      <div className="absolute inset-0 -z-10">
        <AnimatePresence>
          <motion.img
            key={slide}
            src={HERO_SLIDES[slide]!.img}
            alt=""
            initial={{ opacity: 0, scale: 1.08 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ opacity: { duration: 1.2 }, scale: { duration: 7, ease: "linear" } }}
            className="absolute inset-0 h-full w-full object-cover"
          />
        </AnimatePresence>
        <div className="absolute inset-0 bg-gradient-to-r from-white via-white/85 to-white/10 dark:from-[#07130d] dark:via-[#07130d]/85 dark:to-[#07130d]/20 rtl:bg-gradient-to-l" />
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#f6f8f6] to-transparent dark:from-[#07130d]" />
      </div>

      <div className="container grid gap-10 pb-28 pt-12 lg:grid-cols-[1.25fr_1fr] lg:pt-20">
        <div className="min-w-0">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Badge tone="gold" icon={<Sparkles className="h-3 w-3" />}>
              Pakistan’s first agentic real-estate portal
            </Badge>
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className={cn("mt-5 font-display text-4xl font-extrabold leading-[1.05] text-brand-900 sm:text-6xl dark:text-white", lang === "ur" && "font-urdu leading-[1.6]")}
          >
            {t("Find the Perfect")}
            <br />
            <span className="text-gradient">{t("Property with AI")}</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="mt-5 max-w-xl text-lg text-ink-soft dark:text-slate-300">
            Explore verified properties, housing schemes and investment opportunities across Pakistan — with live market intelligence and AI agents at your side.
          </motion.p>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm font-semibold text-brand-800 dark:text-brand-100">
            {[
              [Trees, t("Your Land")],
              [Cpu, t("Our Intelligence")],
              [TrendingUp, t("A Brighter Pakistan")],
            ].map(([I, l], i) => {
              const Icon = I as typeof Trees;
              return (
                <span key={i} className="inline-flex items-center gap-2">
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white shadow-card dark:bg-white/10">
                    <Icon className="h-4 w-4 text-brand-600 dark:text-gold-300" />
                  </span>
                  {l as string}
                </span>
              );
            })}
          </motion.div>

          {/* search */}
          <motion.form onSubmit={submit} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="mt-10">
            <Segmented value={purpose} onChange={setPurpose} options={PURPOSES.map((p) => ({ ...p, label: t(p.label) }))} className="glass no-scrollbar max-w-full overflow-x-auto shadow-soft" />
            <div className="glass mt-3 flex flex-col gap-2 rounded-3xl p-2 shadow-soft sm:flex-row sm:items-center sm:rounded-full">
              <div className="flex flex-1 items-center gap-3 px-4">
                <Search className="h-5 w-5 shrink-0 text-brand-600" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search city, housing scheme, block, area or property…"
                  className="h-12 w-full bg-transparent text-[15px] outline-none placeholder:text-ink-mute"
                />
              </div>
              <select value={city} onChange={(e) => setCity(e.target.value)} className="h-12 rounded-full border-0 bg-brand-50/80 px-4 text-sm font-semibold text-brand-800 outline-none dark:bg-white/10 dark:text-white">
                <option value="">All cities</option>
                {cities.data?.cities.map((c) => (
                  <option key={c.id} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button type="submit" className="btn btn-primary h-12 rounded-full px-7 text-[15px]">
                {t("Search Properties")} <ArrowRight className="h-4 w-4 rtl:rotate-180" />
              </button>
            </div>
          </motion.form>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="font-semibold text-ink-mute">Popular:</span>
            {["DHA Lahore", "Bahria Town Karachi", "Islamabad apartments", "10 Marla house", "Commercial plaza"].map((s) => (
              <button key={s} onClick={() => nav(`/properties?q=${encodeURIComponent(s)}`)} className="rounded-full bg-white/70 px-3 py-1 font-medium text-brand-800 ring-1 ring-brand-100 transition hover:bg-white dark:bg-white/5 dark:text-brand-100 dark:ring-white/10">
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* AI panel */}
        <motion.div initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }} className="hidden lg:block">
          <AiSearchPanel />
          <div className="mt-4 flex items-center justify-end gap-2">
            {HERO_SLIDES.map((s, i) => (
              <button key={i} onClick={() => setSlide(i)} className={cn("h-1.5 rounded-full transition-all", i === slide ? "w-8 bg-brand-700 dark:bg-gold-400" : "w-3 bg-brand-900/20 dark:bg-white/30")} aria-label={s.caption} />
            ))}
            <span className="ms-2 text-xs font-medium text-ink-mute">{HERO_SLIDES[slide]!.caption}</span>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function AiSearchPanel() {
  const setOpen = usePrefs((s) => s.setAssistantOpen);
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<{ id: string; title: string; price: number; city?: string; category?: string; type: string }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (text: string) => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await get<{ results: typeof hits }>("/rag/search", { query: text, limit: 6 });
      setHits((r.results ?? []).filter((h) => h.type === "property").slice(0, 3));
    } catch {
      setHits([]);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="glass relative overflow-hidden rounded-3xl p-6 shadow-soft">
      <div className="pointer-events-none absolute -end-16 -top-16 h-48 w-48 rounded-full bg-gold-300/30 blur-3xl" />
      <div className="flex items-center gap-3">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-soft">
          <Bot className="h-6 w-6" />
        </span>
        <div>
          <p className="font-display text-lg font-bold text-brand-900 dark:text-white">AI Powered Property Search</p>
          <p className="text-xs text-ink-mute">RAG over live listings · MCP agents</p>
        </div>
      </div>
      <ul className="mt-5 grid grid-cols-2 gap-2.5 text-sm font-medium text-ink-soft dark:text-slate-300">
        {["Smart recommendations", "Market insights", "Compare properties", "Nearby places", "Investment analysis", "Price predictions"].map((f) => (
          <li key={f} className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-brand-600 dark:text-gold-300" /> {f}
          </li>
        ))}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(q);
        }}
        className="mt-5 flex items-center gap-2 rounded-2xl bg-white p-1.5 ring-1 ring-brand-100 dark:bg-white/5 dark:ring-white/10"
      >
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a 10-marla house in DHA under 7 crore…" className="h-10 flex-1 bg-transparent px-3 text-sm outline-none" />
        <button className="btn btn-primary btn-icon h-10 w-10" aria-label="Ask" disabled={busy}>
          <Send className="h-4 w-4 rtl:rotate-180" />
        </button>
      </form>
      <div className="mt-3 min-h-[60px]">
        {busy && <Skeleton className="h-16 w-full" />}
        {!busy && hits && (
          <div className="space-y-1">
            <p className="flex items-center gap-1.5 px-1 text-xs font-semibold text-brand-700 dark:text-brand-300">
              <Sparkles className="h-3.5 w-3.5" /> Best matches for you
            </p>
            {hits.length ? hits.map((h) => <PropertyRow key={h.id} p={{ id: h.id, title: h.title, price: h.price, category: h.category ?? "house", city_name: h.city }} />) : <p className="px-1 text-sm text-ink-mute">No direct matches — try the full assistant.</p>}
          </div>
        )}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => setOpen(true)} className="btn btn-gold flex-1">
          <Sparkles className="h-4 w-4" /> Chat with AI
        </button>
        <button onClick={() => nav("/ai")} className="btn btn-outline">
          Agents
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- sections
function FeatureStrip() {
  return (
    <div className="container relative z-10 -mt-16">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {FEATURES.map((f, i) => (
          <motion.div key={f.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }} className="card card-hover flex items-center gap-3 p-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-gold-300">
              <f.icon className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-ink dark:text-white">{f.title}</p>
              <p className="truncate text-xs text-ink-mute">{f.sub}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function StatsBand() {
  const s = useApi<{ inventory: Record<string, number>; portfolio: { total_market_value: number }; users_and_roles: { users: number } }>("/portal/statistics");
  const inv = s.data?.inventory;
  const items = [
    { icon: HomeIcon, value: inv?.properties ?? 0, label: "Live properties", suffix: "" },
    { icon: MapPin, value: inv?.schemes ?? 0, label: "Housing schemes", suffix: "" },
    { icon: Building2, value: inv?.cities ?? 0, label: "Major cities", suffix: "" },
    { icon: Landmark, value: Math.round((s.data?.portfolio.total_market_value ?? 0) / 10_000_000), label: "Crore market value", suffix: "+" },
  ];
  return (
    <section className="container mt-12">
      <div className="relative overflow-hidden rounded-3xl bg-brand-gradient text-white shadow-soft">
        <div className="pointer-events-none absolute inset-0 bg-mesh opacity-70" />
        <div className="relative grid gap-6 p-6 sm:grid-cols-2 sm:p-8 lg:grid-cols-[repeat(4,1fr)_1.2fr]">
          {items.map((it) => (
            <div key={it.label} className="flex items-center gap-4">
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 border-gold-400/70 text-gold-300">
                <it.icon className="h-6 w-6" />
              </span>
              <div>
                <p className="font-display text-3xl font-bold">{s.isLoading ? "…" : <CountUp to={it.value} suffix={it.suffix} />}</p>
                <p className="text-sm text-white/75">{it.label}</p>
              </div>
            </div>
          ))}
          <div className="flex items-center gap-3 rounded-2xl bg-gold-gradient px-5 py-4 text-brand-950">
            <Trees className="h-8 w-8 shrink-0" />
            <p className="font-display text-xl font-bold leading-tight">
              Building a<br />
              Brighter Pakistan
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Featured({ props, loading }: { props: Property[]; loading: boolean }) {
  const t = useT();
  const featured = props.filter((p) => p.featured);
  const list = featured.length >= 4 ? featured : props;
  return (
    <Section
      eyebrow="Handpicked for you"
      title={t("Featured Properties")}
      subtitle="Verified homes, plots and commercial spaces — refreshed live from the portal."
      action={
        <Link to="/properties" className="btn btn-outline">
          {t("View all")} <ArrowRight className="h-4 w-4 rtl:rotate-180" />
        </Link>
      }
    >
      {loading ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : (
        <Carousel slideClass="basis-[85%] sm:basis-1/2 lg:basis-1/3 xl:basis-1/4" autoplay>
          {list.map((p) => (
            <PropertyCard key={p.id} p={p} />
          ))}
        </Carousel>
      )}
    </Section>
  );
}

const POI_LEGEND = [
  ["property", "Properties"],
  ["education", "Schools"],
  ["health", "Hospitals"],
  ["park", "Parks"],
  ["worship", "Mosques"],
  ["shopping", "Shopping"],
  ["transport", "Transport"],
] as const;

function MapAndAssistant({ props }: { props: Property[] }) {
  const pois = useApi<{ pois: { id: string; name: string; category: string; latitude: number; longitude: number }[] }>("/poi", { limit: 200 });
  const [layers, setLayers] = useState<string[]>(["property", "education", "health", "park"]);
  const pts = props.filter((p) => p.latitude && p.longitude);
  const fit = useMemo(() => pts.map((p) => [p.latitude!, p.longitude!] as [number, number]), [pts]);
  const toggle = (k: string) => setLayers((l) => (l.includes(k) ? l.filter((x) => x !== k) : [...l, k]));
  return (
    <section className="container grid gap-6 lg:grid-cols-[1.6fr_1fr]">
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-black/5 px-5 py-4 dark:border-white/10">
          <div className="flex items-center gap-2">
            <MapPin className="h-5 w-5 text-brand-600" />
            <h3 className="font-display text-lg font-semibold">Explore properties on the map</h3>
          </div>
          <Link to="/map" className="btn btn-outline btn-sm">
            Full map <ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" />
          </Link>
        </div>
        <div className="grid md:grid-cols-[180px_1fr]">
          <div className="flex flex-wrap gap-1.5 p-4 md:flex-col">
            {POI_LEGEND.map(([k, l]) => (
              <button
                key={k}
                onClick={() => toggle(k)}
                className={cn("flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm font-medium transition", layers.includes(k) ? "bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-white" : "text-ink-mute opacity-60 hover:opacity-100")}
              >
                <img src={`data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14'><circle cx='7' cy='7' r='6' fill='${({ property: "#0f5a39", education: "#2563eb", health: "#dc2626", park: "#16a34a", worship: "#7c3aed", shopping: "#ea580c", transport: "#0891b2" } as Record<string, string>)[k]}'/></svg>`)}`} alt="" />
                {l}
              </button>
            ))}
          </div>
          <PortalMap height={420} fit={fit} className="rounded-none" scrollWheelZoom={false}>
            {layers.includes("property") &&
              pts.map((p) => (
                <Marker key={p.id} position={[p.latitude!, p.longitude!]} icon={pin(p.featured ? "featured" : p.use_type === "commercial" ? "commercial" : "property")}>
                  <Popup>
                    <Link to={`/properties/${p.id}`} className="block">
                      <img src={coverImage(p)} alt="" className="h-28 w-full object-cover" />
                      <div className="p-3">
                        <p className="font-semibold text-ink">{p.title}</p>
                        <p className="text-xs text-ink-mute">{[p.scheme_name, p.city_name].filter(Boolean).join(", ")}</p>
                        <p className="mt-1 font-bold text-brand-700">{pkrShort(p.price)}</p>
                      </div>
                    </Link>
                  </Popup>
                </Marker>
              ))}
            {(pois.data?.pois ?? [])
              .filter((x) => layers.includes(x.category))
              .map((x) => (
                <Marker key={x.id} position={[x.latitude, x.longitude]} icon={pin(x.category, { size: 26 })}>
                  <Popup>
                    <div className="p-3">
                      <p className="font-semibold">{x.name}</p>
                      <p className="text-xs capitalize text-ink-mute">{x.category}</p>
                    </div>
                  </Popup>
                </Marker>
              ))}
          </PortalMap>
        </div>
      </div>
      <div className="card flex flex-col overflow-hidden">
        <MarketPulse />
      </div>
    </section>
  );
}

function MarketPulse() {
  const [city, setCity] = useState("Lahore");
  const cities = useApi<{ cities: City[] }>("/cities");
  const t = useApi<{ pricing: { price_per_marla: number }; forecast: { base_cagr: number; composite_index: number; index_band: string; scenarios: Record<string, { series: { year: number; price_per_marla: number }[] }> }; news: { net_sentiment: string } }>(
    "/portal/market-trends",
    { city },
  );
  const series = useMemo(() => {
    const sc = t.data?.forecast?.scenarios;
    if (!sc?.base) return [];
    return sc.base.series.map((r, i) => ({ year: r.year, base: r.price_per_marla, optimistic: sc.optimistic?.series[i]?.price_per_marla, pessimistic: sc.pessimistic?.series[i]?.price_per_marla }));
  }, [t.data]);
  return (
    <>
      <div className="flex items-center justify-between gap-2 border-b border-black/5 px-5 py-4 dark:border-white/10">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-gold-600" />
          <h3 className="font-display text-lg font-semibold">Market pulse</h3>
        </div>
        <select value={city} onChange={(e) => setCity(e.target.value)} className="input w-auto py-1.5 text-sm">
          {(cities.data?.cities ?? [{ name: "Lahore" } as City]).map((c) => (
            <option key={c.name}>{c.name}</option>
          ))}
        </select>
      </div>
      <div className="flex-1 p-5">
        {t.isLoading ? (
          <Skeleton className="h-64" />
        ) : (
          <>
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-xl bg-brand-50/70 p-3 dark:bg-white/5">
                <p className="text-[10px] font-bold uppercase text-ink-mute">Per marla</p>
                <p className="font-display text-lg font-bold">{pkrShort(t.data?.pricing.price_per_marla, false)}</p>
              </div>
              <div className="rounded-xl bg-brand-50/70 p-3 dark:bg-white/5">
                <p className="text-[10px] font-bold uppercase text-ink-mute">Growth</p>
                <p className="font-display text-lg font-bold text-emerald-600">+{((t.data?.forecast.base_cagr ?? 0) * 100).toFixed(1)}%</p>
              </div>
              <div className="rounded-xl bg-brand-50/70 p-3 dark:bg-white/5">
                <p className="text-[10px] font-bold uppercase text-ink-mute">Index</p>
                <p className="font-display text-lg font-bold">{Math.round(t.data?.forecast.composite_index ?? 0)}</p>
              </div>
            </div>
            <div className="mt-4">
              <AreaTrend
                data={series}
                x="year"
                height={210}
                format={(v) => pkrShort(v, false)}
                series={[
                  { key: "optimistic", label: "Optimistic", color: "#c99a22" },
                  { key: "base", label: "Base", color: "#146f45" },
                  { key: "pessimistic", label: "Pessimistic", color: "#94a3b8" },
                ]}
              />
            </div>
            <p className="mt-2 text-xs text-ink-mute">
              5-year price-per-marla forecast · news sentiment <b className="capitalize text-ink dark:text-white">{t.data?.news.net_sentiment}</b> · band <b className="capitalize text-ink dark:text-white">{t.data?.forecast.index_band}</b>
            </p>
          </>
        )}
      </div>
      <Link to="/insights" className="flex items-center justify-center gap-2 border-t border-black/5 py-3 text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:border-white/10 dark:text-brand-300 dark:hover:bg-white/5">
        Full market insights <ArrowRight className="h-4 w-4 rtl:rotate-180" />
      </Link>
    </>
  );
}

function Cities() {
  const q = useApi<{ cities: City[] }>("/cities");
  return (
    <Section eyebrow="Explore Pakistan" title="Top cities" subtitle="From Lahore’s heritage to Karachi’s coastline — dive into every city’s schemes, prices and growth.">
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {(q.data?.cities ?? []).map((c, i) => (
          <motion.div key={c.id} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.06 }}>
            <Link to={`/cities/${encodeURIComponent(c.name)}`} className="group relative block aspect-[4/5] overflow-hidden rounded-3xl shadow-card">
              <img src={cityImage(c.name)} alt={c.name} className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110" />
              <div className="absolute inset-0 bg-gradient-to-t from-brand-950/90 via-brand-950/20 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 p-5 text-white">
                <p className="text-xs font-semibold uppercase tracking-widest text-gold-300">{c.state}</p>
                <p className="font-display text-2xl font-bold">{c.name}</p>
                <div className="mt-2 flex gap-3 text-xs text-white/80">
                  <span>{c.schemes} schemes</span>
                  <span>·</span>
                  <span>{c.properties} listings</span>
                </div>
                <span className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-gold-200 opacity-0 transition group-hover:opacity-100">
                  Explore <ArrowRight className="h-4 w-4 rtl:rotate-180" />
                </span>
              </div>
            </Link>
          </motion.div>
        ))}
        {q.isLoading && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="aspect-[4/5] rounded-3xl" />)}
      </div>
    </Section>
  );
}

function Categories() {
  const s = useApi<{ portfolio: { by_category: Record<string, number> } }>("/portal/statistics");
  const counts = s.data?.portfolio.by_category ?? {};
  return (
    <section className="container">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        {CATEGORIES.map((c) => (
          <Link key={c.key} to={c.key === "farmhouse" ? "/properties?q=farmhouse" : `/properties?category=${c.key}`} className="group card flex flex-col items-center gap-2 p-4 text-center transition hover:-translate-y-1 hover:border-gold-300 hover:shadow-glow">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-50 to-gold-50 text-brand-700 transition group-hover:from-brand-700 group-hover:to-brand-600 group-hover:text-white dark:from-white/5 dark:to-white/10 dark:text-gold-300">
              <c.icon className="h-6 w-6" />
            </span>
            <span className="text-sm font-semibold">{c.label}</span>
            <span className="text-xs text-ink-mute">{counts[c.key] ?? 0} listings</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function MegaProjects() {
  const q = useApi<{ projects: { id: string; name: string; project_type: string; status: string; city: string; floor_count: number; total_area: number; occupancy_rate: number | null }[] }>("/bigprojects");
  if (!q.data?.projects.length) return null;
  return (
    <Section
      eyebrow="Landmark developments"
      title="Mega projects"
      subtitle="Malls, towers, mixed-use plazas and gated compounds shaping Pakistan’s skylines."
      action={
        <Link to="/projects" className="btn btn-outline">
          All projects <ArrowRight className="h-4 w-4 rtl:rotate-180" />
        </Link>
      }
    >
      <Carousel slideClass="basis-[85%] sm:basis-1/2 lg:basis-1/3" arrows dots>
        {q.data.projects.map((p) => (
          <Link key={p.id} to="/projects" className="group relative block aspect-[16/11] overflow-hidden rounded-3xl shadow-card">
            <img src={themedImage(p.id, `${p.project_type} ${p.name}`)} alt="" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
            <div className="absolute start-4 top-4 flex gap-2">
              <span className="chip bg-white/90 text-brand-800">{titleCase(p.project_type)}</span>
              <span className={cn("chip", p.status === "completed" ? "bg-emerald-500 text-white" : p.status === "planned" ? "bg-sky-500 text-white" : "bg-gold-400 text-brand-950")}>{titleCase(p.status)}</span>
            </div>
            <div className="absolute inset-x-0 bottom-0 p-5 text-white">
              <p className="font-display text-xl font-bold">{p.name}</p>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/80">
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" /> {p.city}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Building className="h-3.5 w-3.5" /> {p.floor_count} floors
                </span>
                <span className="inline-flex items-center gap-1">
                  <Ruler className="h-3.5 w-3.5" /> {compact(p.total_area)} sqft
                </span>
              </div>
              {p.occupancy_rate !== null && (
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/20">
                  <div className="h-full rounded-full bg-gold-gradient" style={{ width: `${(p.occupancy_rate ?? 0) * 100}%` }} />
                </div>
              )}
            </div>
          </Link>
        ))}
      </Carousel>
    </Section>
  );
}

function AgentsShowcase() {
  return (
    <section className="relative mt-8 overflow-hidden bg-brand-950 py-16 text-white sm:py-20">
      <div className="pointer-events-none absolute inset-0 bg-mesh opacity-70" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.04)_1px,transparent_1px)] bg-[size:48px_48px]" />
      <div className="container relative">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="section-eyebrow !text-gold-300">Agentic OS · MCP-powered</p>
            <h2 className="mt-2 font-display text-3xl font-bold sm:text-4xl">AI agents that do the legwork</h2>
            <p className="mt-2 max-w-2xl text-white/70">24 specialised agents across buying, selling, leasing, investing and marketing — each wired to live portal data through the Model Context Protocol, with human approval gates where it matters.</p>
          </div>
          <Link to="/ai" className="btn btn-gold">
            Open the AI Hub <ArrowRight className="h-4 w-4 rtl:rotate-180" />
          </Link>
        </div>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {SHOWCASE_AGENTS.map((a, i) => (
            <motion.div key={a.key} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.08 }}>
              <Link to={`/ai/agents/${a.key}`} className="group flex h-full flex-col rounded-3xl border border-white/10 bg-white/5 p-6 backdrop-blur transition hover:-translate-y-1 hover:border-gold-400/50 hover:bg-white/10">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gold-gradient text-brand-950 shadow-glow">
                  <a.icon className="h-6 w-6" />
                </span>
                <p className="mt-5 font-display text-lg font-semibold">{a.name}</p>
                <p className="mt-2 flex-1 text-sm text-white/70">{a.blurb}</p>
                <span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-gold-300">
                  Run agent <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1 rtl:rotate-180" />
                </span>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ToolsStrip() {
  const tools = [
    { key: "mortgage", label: "Mortgage", icon: Landmark },
    { key: "area", label: "Area converter", icon: Ruler },
    { key: "construction", label: "Construction cost", icon: Building2 },
    { key: "rental_yield", label: "Rental yield", icon: TrendingUp },
    { key: "transfer", label: "Transfer & stamp duty", icon: BadgeCheck },
    { key: "installment", label: "Installments", icon: Calculator },
  ];
  return (
    <Section eyebrow="Tools center" title="Calculators & utilities" subtitle="Plan every rupee — financing, taxes, construction and returns, computed by the portal’s engines.">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        {tools.map((t) => (
          <Link key={t.key} to={`/tools/${t.key}`} className="group card relative overflow-hidden p-5 transition hover:-translate-y-1 hover:shadow-soft">
            <div className="absolute -end-6 -top-6 h-20 w-20 rounded-full bg-gold-100 transition group-hover:scale-150 dark:bg-gold-500/10" />
            <t.icon className="relative h-7 w-7 text-brand-700 dark:text-gold-300" />
            <p className="relative mt-4 text-sm font-semibold">{t.label}</p>
            <ArrowRight className="relative mt-2 h-4 w-4 text-ink-mute transition group-hover:translate-x-1 group-hover:text-brand-700 rtl:rotate-180" />
          </Link>
        ))}
      </div>
    </Section>
  );
}

function NewsAndStories() {
  const news = useApi<{ news: NewsItem[] }>("/news", { limit: 5 });
  const stories = useApi<{ stories: Story[] }>("/content/stories");
  return (
    <section className="container grid gap-6 py-12 lg:grid-cols-[1fr_1.2fr]">
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-black/5 px-5 py-4 dark:border-white/10">
          <h3 className="font-display text-lg font-semibold">Market-moving news</h3>
          <Link to="/news" className="text-sm font-semibold text-brand-700 dark:text-brand-300">
            All news
          </Link>
        </div>
        <ul className="divide-y divide-black/5 dark:divide-white/5">
          {(news.data?.news ?? []).map((n) => (
            <li key={n.id} className="flex gap-3 px-5 py-3.5">
              <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.sentiment === "positive" ? "bg-emerald-500" : n.sentiment === "negative" ? "bg-red-500" : "bg-slate-400")} />
              <div className="min-w-0">
                <p className="line-clamp-2 text-sm font-semibold">{n.title}</p>
                <p className="mt-0.5 text-xs text-ink-mute">
                  {n.source} · {timeAgo(n.published_at)} · <span className="capitalize">{n.category}</span>
                </p>
              </div>
              <span className={cn("ms-auto shrink-0 self-start rounded-md px-1.5 py-0.5 text-xs font-bold", n.impact_score >= 0 ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300")}>
                {n.impact_score > 0 ? "+" : ""}
                {Math.round(n.impact_score)}
              </span>
            </li>
          ))}
          {news.isLoading && <Skeleton className="m-5 h-40" />}
        </ul>
      </div>
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-gold-50 via-white to-brand-50 p-6 shadow-card dark:from-brand-900/40 dark:via-[#0d1f16] dark:to-brand-950 sm:p-8">
        <Quote className="absolute end-6 top-6 h-20 w-20 text-gold-200 dark:text-gold-500/20" />
        <p className="section-eyebrow">Success stories</p>
        <Carousel slideClass="basis-full" autoplay delay={6000} arrows={false} className="mt-4">
          {(stories.data?.stories ?? []).map((s) => (
            <div key={s.id} className="pe-2">
              <div className="flex gap-0.5">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star key={i} className={cn("h-4 w-4", i < Math.round(s.rating ?? 5) ? "fill-gold-400 text-gold-400" : "text-gold-200")} />
                ))}
              </div>
              <p className="mt-4 font-display text-xl font-medium leading-relaxed text-brand-900 dark:text-white">“{s.quote}”</p>
              <div className="mt-6 flex flex-wrap items-center gap-4">
                <div>
                  <p className="font-semibold">{s.client_name}</p>
                  <p className="text-xs text-ink-mute">
                    {s.client_role} · {s.location}
                  </p>
                </div>
                <div className="ms-auto flex flex-wrap gap-2">
                  {s.metrics?.slice(0, 3).map((m) => (
                    <span key={m.label} className="rounded-xl bg-white/80 px-3 py-1.5 text-center shadow-sm dark:bg-white/5">
                      <span className="block font-display text-sm font-bold text-brand-700 dark:text-gold-300">{m.value}</span>
                      <span className="block text-[10px] uppercase text-ink-mute">{m.label}</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </Carousel>
        <Link to="/stories" className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 dark:text-brand-300">
          Read all stories <ArrowRight className="h-4 w-4 rtl:rotate-180" />
        </Link>
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="container py-8">
      <div className="relative overflow-hidden rounded-[2rem] bg-brand-950 p-8 text-white sm:p-12">
        <img src={HERO.villa} alt="" className="absolute inset-0 h-full w-full object-cover opacity-30" />
        <div className="absolute inset-0 bg-gradient-to-r from-brand-950 via-brand-950/90 to-transparent rtl:bg-gradient-to-l" />
        <div className="relative max-w-xl">
          <p className="section-eyebrow !text-gold-300">For owners, brokers & developers</p>
          <h2 className="mt-2 font-display text-3xl font-bold sm:text-4xl">List with Arz-e-Pak and let AI market it for you</h2>
          <p className="mt-3 text-white/75">Instant pricing from comparable sales, auto-generated listing kits and social posts, and a CRM that scores every buyer’s intent.</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/app/listings/new" className="btn btn-gold btn-lg">
              List your property
            </Link>
            <Link to="/pricing" className="btn btn-lg border border-white/20 bg-white/10 text-white hover:bg-white/20">
              <Users className="h-4 w-4" /> Plans for agencies
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- page
export default function Home() {
  const q = useApi<PropertyList>("/properties", { limit: 50 });
  const props = q.data?.results ?? [];
  return (
    <div>
      <Hero />
      <FeatureStrip />
      <StatsBand />
      <Featured props={props} loading={q.isLoading} />
      <MapAndAssistant props={props} />
      <div className="container mt-12">
        <AdSlot slot="banner" placement="home" />
      </div>
      <Cities />
      <Categories />
      <MegaProjects />
      <AgentsShowcase />
      <ToolsStrip />
      <div className="container">
        <AdSlot slot="hero" />
      </div>
      <NewsAndStories />
      <Cta />
    </div>
  );
}
