/**
 * Landing-page sections built around the assistant: a full-bleed photo hero with an AI composer
 * (describe the home, get a shortlist), a dark "on the market now" showcase, the "you decide,
 * the AI does the legwork" strip and a product showcase. Photos are real and credited.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Bot, Building2, Home as HomeIcon, KeyRound, LandPlot, MapPin, Mic, Shuffle, Sparkles, Store, TrendingUp, UserRound } from "lucide-react";
import type { Property } from "@/types";
import { useApi } from "@/hooks/useApi";
import { pkrShort } from "@/lib/format";
import { coverImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";

// Real photos (Wikimedia Commons, credited) and the project's own render.
const HERO_PHOTOS = [
  {
    img: "https://upload.wikimedia.org/wikipedia/commons/thumb/e/eb/Faisal_Mosque%2C_Islamabad_III.jpg/1920px-Faisal_Mosque%2C_Islamabad_III.jpg",
    caption: "Faisal Mosque, Islamabad",
    credit: "Fassifarooq · CC BY-SA 4.0 · Wikimedia Commons",
  },
  {
    img: "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4f/Lahore_Fort_view_from_Baradari.jpg/1920px-Lahore_Fort_view_from_Baradari.jpg",
    caption: "Lahore Fort",
    credit: "Rohaan Bhatti · CC BY-SA 3.0 · Wikimedia Commons",
  },
  {
    img: "https://upload.wikimedia.org/wikipedia/commons/thumb/2/20/Clifton_Karachi_View.jpg/1920px-Clifton_Karachi_View.jpg",
    caption: "Clifton, Karachi",
    credit: "Ktownboy103 · CC0 · Wikimedia Commons",
  },
];

type Mode = "find" | "invest" | "sell";
const MODES: { value: Mode; label: string; icon: typeof HomeIcon; placeholder: string; prefix: string }[] = [
  { value: "find", label: "Find a home", icon: HomeIcon, placeholder: "A 10 marla house in DHA Phase 2 under 5 crore, near a good school…", prefix: "" },
  { value: "invest", label: "Invest", icon: TrendingUp, placeholder: "Where should I invest 2 crore in Rawalpindi for the best return in 3 years?", prefix: "Investment question: " },
  { value: "sell", label: "Sell or rent out", icon: KeyRound, placeholder: "I want to sell my 1 kanal house in Bahria Town Phase 8 — what is it worth?", prefix: "I want to sell or rent out my property: " },
];
const SURPRISES = [
  "Show me shops under 50 lakh in China Center, Bahria Town Phase 8",
  "Which housing societies in Rawalpindi are approved by RDA?",
  "2 bed apartment in Goldcrest Breeze with a Margalla view",
  "How will the Rawalpindi Ring Road affect plot prices near Adyala Road?",
  "اسلام آباد میں 1.5 کروڑ تک 3 کمروں کا گھر",
  "Skyra Tower penthouse with a private pool — payment plan?",
  "5 marla plot in Lahore under 1 crore near a mosque",
];
const POPULAR = ["Approved societies in Islamabad", "Apartments under 1 crore", "Plots near the Ring Road", "Shops in Bahria Town", "New projects with instalments"];

type SpeechRec = { lang: string; interimResults: boolean; onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void; onend: () => void; start: () => void; stop: () => void };

// ---------------------------------------------------------------- hero
export function ComposerHero() {
  const nav = useNavigate();
  const lang = usePrefs((s) => s.lang);
  const [mode, setMode] = useState<Mode>("find");
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState(0);
  const [listening, setListening] = useState(false);
  const rec = useRef<SpeechRec | null>(null);
  const current = MODES.find((m) => m.value === mode)!;

  useEffect(() => {
    const id = setInterval(() => setPhoto((p) => (p + 1) % HERO_PHOTOS.length), 8000);
    return () => clearInterval(id);
  }, []);

  const ask = (q: string) => {
    const query = q.trim() || current.placeholder.replace(/…$/, "");
    nav(`/ai?q=${encodeURIComponent(current.prefix + query)}`);
  };
  const SpeechCtor = typeof window !== "undefined" ? ((window as unknown as Record<string, unknown>).SpeechRecognition ?? (window as unknown as Record<string, unknown>).webkitSpeechRecognition) as (new () => SpeechRec) | undefined : undefined;
  const voice = () => {
    if (!SpeechCtor) {
      nav("/ai");
      return;
    }
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new SpeechCtor();
    r.lang = lang === "ur" ? "ur-PK" : "en-PK";
    r.interimResults = true;
    r.onresult = (e) => setText(Array.from(e.results).map((x) => x[0]!.transcript).join(" "));
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };

  return (
    <section className="relative isolate flex min-h-[640px] items-center overflow-hidden py-24 sm:min-h-[720px]">
      <div className="absolute inset-0 -z-10 bg-brand-950">
        <AnimatePresence>
          <motion.img
            key={photo}
            src={HERO_PHOTOS[photo]!.img}
            alt={HERO_PHOTOS[photo]!.caption}
            initial={{ opacity: 0, scale: 1.06 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ opacity: { duration: 1.4 }, scale: { duration: 9, ease: "linear" } }}
            className="absolute inset-0 h-full w-full object-cover"
          />
        </AnimatePresence>
        <div className="absolute inset-0 bg-gradient-to-b from-black/55 via-black/35 to-black/70" />
      </div>

      <div className="container flex flex-col items-center text-center">
        <motion.span initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-white/90 backdrop-blur">
          <Sparkles className="h-3.5 w-3.5 text-gold-300" /> Pakistan’s AI real-estate portal
        </motion.span>
        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className={cn("mt-6 max-w-4xl font-display text-[2.6rem] font-light leading-[1.05] tracking-tight text-white sm:text-6xl lg:text-7xl", lang === "ur" && "font-urdu leading-[1.5]")}
        >
          Tell us the home you want. <span className="font-semibold text-gold-300">Watch AI find it.</span>
        </motion.h1>
        <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mt-5 max-w-2xl text-base text-white/80 sm:text-lg">
          Describe it in English or Urdu. Arz-e-Pak AI searches every listing and new project, checks the society’s approval with official sources, and remembers what matters to you.
        </motion.p>

        {/* composer */}
        <motion.form
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.18 }}
          onSubmit={(e) => {
            e.preventDefault();
            ask(text);
          }}
          className="mt-10 w-full max-w-2xl rounded-[28px] bg-white p-2 text-start shadow-[0_30px_80px_-20px_rgba(0,0,0,.55)] dark:bg-[#0f1f17]"
        >
          <div className="grid grid-cols-3 gap-1 rounded-[22px] bg-black/[.05] p-1 dark:bg-white/[.06]" role="tablist" aria-label="What do you want to do?">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="tab"
                aria-selected={mode === m.value}
                onClick={() => setMode(m.value)}
                className={cn(
                  "flex items-center justify-center gap-1.5 rounded-[18px] px-2 py-2 text-xs font-semibold transition sm:text-sm",
                  mode === m.value ? "bg-white text-brand-900 shadow-sm dark:bg-white/15 dark:text-white" : "text-ink-mute hover:text-ink dark:hover:text-white",
                )}
              >
                <m.icon className="h-4 w-4" /> <span className="truncate">{m.label}</span>
              </button>
            ))}
          </div>
          <label htmlFor="landing-ask" className="sr-only">
            Describe what you are looking for
          </label>
          <textarea
            id="landing-ask"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(text);
              }
            }}
            rows={2}
            dir="auto"
            placeholder={current.placeholder}
            className="mt-2 block w-full resize-none bg-transparent px-4 py-3 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-mute dark:text-white"
          />
          <div className="flex items-center gap-2 px-2 pb-1">
            <button
              type="button"
              onClick={() => setText(SURPRISES[Math.floor(Math.random() * SURPRISES.length)]!)}
              className="inline-flex items-center gap-1.5 rounded-full border border-gold-300 bg-gold-50 px-3 py-1.5 text-xs font-semibold text-gold-800 transition hover:bg-gold-100 dark:border-gold-500/40 dark:bg-gold-500/10 dark:text-gold-200"
            >
              <Shuffle className="h-3.5 w-3.5" /> Surprise me
            </button>
            <span className="flex-1" />
            <button
              type="button"
              onClick={voice}
              aria-label={listening ? "Stop listening" : "Speak your request"}
              className={cn("flex h-10 w-10 items-center justify-center rounded-full transition", listening ? "animate-pulse bg-red-500 text-white" : "text-ink-soft hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/10")}
            >
              <Mic className="h-[18px] w-[18px]" />
            </button>
            <button type="submit" className="inline-flex h-10 items-center gap-2 rounded-full bg-gold-gradient px-5 text-sm font-bold text-brand-950 shadow-glow transition hover:brightness-105">
              Ask Arz-e-Pak AI <ArrowRight className="h-4 w-4 rtl:rotate-180" />
            </button>
          </div>
        </motion.form>

        <div className="mt-5 flex max-w-2xl flex-wrap justify-center gap-2">
          {POPULAR.map((s) => (
            <button key={s} type="button" onClick={() => ask(s)} className="rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium text-white/90 backdrop-blur transition hover:bg-white/20">
              {s}
            </button>
          ))}
        </div>
        <Link to="/properties" className="mt-4 text-sm font-semibold text-white/80 underline-offset-4 hover:text-white hover:underline">
          Prefer filters? Browse all properties →
        </Link>
      </div>

      <p className="absolute bottom-3 end-4 max-w-[70%] truncate text-[10px] text-white/55">
        {HERO_PHOTOS[photo]!.caption} · Photo: {HERO_PHOTOS[photo]!.credit}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- market showcase
const FILTERS: { key: string; label: string; icon: typeof HomeIcon; match: (p: Property) => boolean }[] = [
  { key: "all", label: "All", icon: Sparkles, match: () => true },
  { key: "projects", label: "New projects", icon: Building2, match: (p) => !!p.project_id },
  { key: "apartment", label: "Apartments", icon: Building2, match: (p) => p.category === "apartment" },
  { key: "house", label: "Houses", icon: HomeIcon, match: (p) => p.category === "house" },
  { key: "plot", label: "Plots", icon: LandPlot, match: (p) => p.category === "plot" },
  { key: "commercial", label: "Shops & offices", icon: Store, match: (p) => p.use_type === "commercial" },
];

export function MarketShowcase({ props, loading }: { props: Property[]; loading: boolean }) {
  const nav = useNavigate();
  const [filter, setFilter] = useState("all");
  const [more, setMore] = useState(false);
  const list = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter)!;
    const rows = props.filter(f.match);
    if (filter !== "all") return rows;
    // a mix: one unit from each new project (real photos) first, then the other listings
    const seen = new Set<string>();
    const projectPicks = rows.filter((p) => p.project_id && !seen.has(p.project_id) && seen.add(p.project_id));
    return [...projectPicks, ...rows.filter((p) => !p.project_id)];
  }, [props, filter]);
  const shown = list.slice(0, more ? 12 : 8);
  return (
    <section className="mt-16 bg-[#0b1611] py-16 text-white sm:py-20">
      <div className="container">
        <div className="flex flex-col items-center text-center">
          <span className="rounded-full border border-white/15 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/70">On the market now</span>
          <h2 className="mt-4 font-display text-3xl font-light tracking-tight sm:text-5xl">See what people are buying across Pakistan</h2>
        </div>
        <div className="no-scrollbar mt-8 flex justify-start gap-2 overflow-x-auto sm:justify-center" role="tablist" aria-label="Filter listings">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={filter === f.key}
              onClick={() => {
                setFilter(f.key);
                setMore(false);
              }}
              className={cn("shrink-0 rounded-full px-4 py-2 text-sm font-medium transition", filter === f.key ? "bg-white text-brand-950" : "border border-white/15 text-white/80 hover:bg-white/10")}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {loading
            ? Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-80 animate-pulse rounded-3xl bg-white/5" />)
            : shown.map((p, i) => (
                <motion.article
                  key={p.id}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i, 8) * 0.04 }}
                  className="flex flex-col overflow-hidden rounded-3xl bg-white text-ink shadow-xl dark:bg-[#13241b] dark:text-white"
                >
                  <Link to={`/properties/${p.id}`} className="group relative block aspect-[4/3] overflow-hidden bg-black/5">
                    <img src={coverImage(p)} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
                    <span className="absolute start-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-semibold text-brand-900">{p.project_id ? "New project" : p.category}</span>
                  </Link>
                  <div className="flex flex-1 flex-col p-4">
                    <p className="line-clamp-2 font-display text-[15px] font-semibold leading-snug">{p.title}</p>
                    <p className="mt-1 flex items-center gap-1 text-xs text-ink-mute">
                      <MapPin className="h-3.5 w-3.5" /> {[p.scheme_name, p.city_name].filter(Boolean).join(", ")}
                    </p>
                    <p className="mt-2 font-display text-lg font-bold text-brand-800 dark:text-gold-300">{pkrShort(p.price)}</p>
                    <div className="mt-auto flex gap-2 pt-4">
                      <Link to={`/properties/${p.id}`} className="flex-1 rounded-full bg-brand-950 px-3 py-2 text-center text-xs font-semibold text-white transition hover:bg-brand-800 dark:bg-white/10">
                        View details
                      </Link>
                      <button
                        type="button"
                        onClick={() => nav(`/ai?q=${encodeURIComponent(`Tell me about “${p.title}” — is it good value, and what is nearby?`)}`)}
                        className="inline-flex flex-1 items-center justify-center gap-1 rounded-full bg-gold-gradient px-3 py-2 text-xs font-bold text-brand-950 transition hover:brightness-105"
                      >
                        <Sparkles className="h-3.5 w-3.5" /> Ask AI
                      </button>
                    </div>
                  </div>
                </motion.article>
              ))}
        </div>
        {!loading && list.length > shown.length && (
          <div className="mt-8 flex justify-center">
            {more ? (
              <Link to="/properties" className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-brand-950">
                See all listings
              </Link>
            ) : (
              <button type="button" onClick={() => setMore(true)} className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-brand-950">
                Show more
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- you + AI
const TOGETHER: [string, string][] = [
  ["You describe the home, budget and area — in English or Urdu.", "Arz-e-Pak AI searches every listing and new project and shortlists the best three."],
  ["You ask whether a society is approved.", "It checks the authority’s list and shows you the official source."],
  ["You choose what matters: schools, commute, price per marla.", "It compares them on the map, with ring roads and mega projects nearby."],
  ["You decide to visit.", "It sends the call request and remembers your budget for next time."],
];

export function Together() {
  return (
    <section className="bg-[#0b1611] pb-20 text-white">
      <div className="container">
        <div className="rounded-[32px] border border-white/10 bg-white/[.03] p-6 sm:p-10">
          <div className="text-center">
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gold-300">How we work together</span>
            <h2 className="mt-3 font-display text-3xl font-light tracking-tight sm:text-4xl">You stay in charge. Arz-e-Pak AI does the legwork.</h2>
          </div>
          <div className="mt-10 grid gap-x-6 gap-y-3 md:grid-cols-2">
            {TOGETHER.map(([you, ai], i) => (
              <div key={i} className="flex flex-col gap-3">
                <motion.p initial={{ opacity: 0, x: -10 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} className="flex items-center gap-3 rounded-2xl bg-white/[.07] px-4 py-3 text-sm text-white/85">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10">
                    <UserRound className="h-4 w-4" />
                  </span>
                  {you}
                </motion.p>
                <motion.p initial={{ opacity: 0, x: 10 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.08 }} className="flex items-center gap-3 rounded-2xl bg-gold-gradient px-4 py-3 text-sm font-semibold text-brand-950">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-950/90 text-gold-300">
                    <Bot className="h-4 w-4" />
                  </span>
                  {ai}
                </motion.p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- showcase
export function MapShowcase() {
  const stats = useApi<{ inventory: Record<string, number> }>("/portal/statistics");
  const inv = stats.data?.inventory;
  return (
    <section className="container mt-20">
      <div className="grid items-center gap-10 lg:grid-cols-[1.2fr_1fr]">
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="rounded-[28px] bg-gold-gradient p-3 shadow-soft">
          <img src="/showcase/gis-explorer.png" alt="The GIS explorer: roads, water bodies, provinces, mega projects and listings across Pakistan" loading="lazy" className="w-full rounded-[20px]" />
        </motion.div>
        <div>
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gold-700 dark:text-gold-300">Your search in one place</span>
          <h2 className="mt-3 font-display text-3xl font-light tracking-tight text-brand-950 sm:text-5xl dark:text-white">One map for every decision.</h2>
          <p className="mt-4 text-ink-soft dark:text-slate-300">
            Listings, housing societies and DHA master plans, roads and water, districts and terrain, and the ring roads and motorways that move prices — on one map, with an area study you can print.
          </p>
          <div className="mt-6 flex flex-wrap gap-6 text-sm">
            {[
              [inv?.properties, "listings on the map"],
              [inv?.schemes, "housing societies"],
              [inv?.cities, "cities"],
            ].map(([n, l]) => (
              <div key={String(l)}>
                <p className="font-display text-3xl font-bold text-brand-800 dark:text-gold-300">{n ?? "—"}</p>
                <p className="text-ink-mute">{l}</p>
              </div>
            ))}
          </div>
          <Link to="/map" className="mt-7 inline-flex items-center gap-2 rounded-full bg-brand-950 px-6 py-3 text-sm font-semibold text-white transition hover:bg-brand-800 dark:bg-gold-gradient dark:text-brand-950">
            Open the map <ArrowRight className="h-4 w-4 rtl:rotate-180" />
          </Link>
        </div>
      </div>
    </section>
  );
}
