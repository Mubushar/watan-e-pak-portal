/**
 * Landing-page pieces built around the assistant, in the portal's own light green-and-gold look:
 * the Islamabad hero photos (real, credited), the AI composer card (describe the home, get a
 * shortlist), the "on the market now" listings, the "you decide, the AI does the legwork" strip
 * and the map showcase.
 */
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, BadgeCheck, Bot, Home as HomeIcon, KeyRound, Lock, MapPin, Mic, Quote, ShieldCheck, Shuffle, Sparkles, TrendingUp, UserRound } from "lucide-react";
import type { Property } from "@/types";
import { useApi } from "@/hooks/useApi";
import { pkrShort } from "@/lib/format";
import { coverImage } from "@/lib/images";
import { RepresentativeTag } from "@/components/property/PropertyCard";
import { groupProjectUnits, isGroup, priceRange } from "@/lib/projectGroups";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";

/** Islamabad, where Watan-e-Pak is based: real photos from Wikimedia Commons, credited. */
export const HERO_PHOTOS = [
  {
    img: "https://upload.wikimedia.org/wikipedia/commons/thumb/4/40/Faisal_Mosque%2C_Islamabad%2C_Pakistan.jpg/1920px-Faisal_Mosque%2C_Islamabad%2C_Pakistan.jpg",
    caption: "Faisal Mosque and the Margalla Hills",
    credit: "Ahmad Haq · CC BY-SA 4.0 · Wikimedia Commons",
  },
  {
    img: "https://upload.wikimedia.org/wikipedia/commons/thumb/2/20/Faisal_Masjid_in_cloudy_weather.jpg/1920px-Faisal_Masjid_in_cloudy_weather.jpg",
    caption: "Faisal Mosque under the Margallas",
    credit: "King Eliot · CC BY-SA 4.0 · Wikimedia Commons",
  },
  {
    img: "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Blue_Hour_at_Pakistan_Monument.jpg/1920px-Blue_Hour_at_Pakistan_Monument.jpg",
    caption: "Pakistan Monument, Islamabad",
    credit: "Muhammad Ashar · CC BY-SA 4.0 · Wikimedia Commons",
  },
  {
    img: "https://upload.wikimedia.org/wikipedia/commons/e/e5/The_Margalla_Hills%2C_Islamabad%2C_Pakistan_from_Daman-e-Koh_park.jpg",
    caption: "Margalla Hills from Daman-e-Koh",
    credit: "Fraz.khalid1 · CC0 · Wikimedia Commons",
  },
];

type Mode = "find" | "invest" | "sell";
const MODES: { value: Mode; label: string; icon: typeof HomeIcon; placeholder: string; prefix: string }[] = [
  { value: "find", label: "Find a home", icon: HomeIcon, placeholder: "A 10 marla house in DHA Phase 2 under 5 crore, near a good school…", prefix: "" },
  { value: "invest", label: "Invest", icon: TrendingUp, placeholder: "Where should I invest 2 crore in Rawalpindi for the best return?", prefix: "Investment question: " },
  { value: "sell", label: "Sell / rent out", icon: KeyRound, placeholder: "I want to sell my 1 kanal house in Bahria Town Phase 8 — what is it worth?", prefix: "I want to sell or rent out my property: " },
];
const SURPRISES = [
  "Show me shops under 50 lakh in China Center, Bahria Town Phase 8",
  "Which housing societies in Rawalpindi are approved by RDA?",
  "2 bed apartment in Goldcrest Breeze with a Margalla view",
  "How will the Rawalpindi Ring Road affect plot prices near Adyala Road?",
  "اسلام آباد میں 1.5 کروڑ تک 3 کمروں کا گھر",
  "Skyra Tower penthouse with a private pool — payment plan?",
  "Plots in DHA Phase V under 2 crore",
];

type SpeechRec = { lang: string; interimResults: boolean; onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void; onend: () => void; start: () => void; stop: () => void };

// ---------------------------------------------------------------- composer
/** Describe what you want in your own words (English or Urdu); the AI Hub takes it from there. */
export function ComposerCard({ className }: { className?: string }) {
  const nav = useNavigate();
  const lang = usePrefs((s) => s.lang);
  const [mode, setMode] = useState<Mode>("find");
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const rec = useRef<SpeechRec | null>(null);
  const current = MODES.find((m) => m.value === mode)!;

  const ask = (q: string) => nav(`/ai?q=${encodeURIComponent(current.prefix + (q.trim() || current.placeholder.replace(/…$/, "")))}`);
  const SpeechCtor =
    typeof window !== "undefined"
      ? ((window as unknown as Record<string, unknown>).SpeechRecognition ?? (window as unknown as Record<string, unknown>).webkitSpeechRecognition) as (new () => SpeechRec) | undefined
      : undefined;
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
    <form
      onSubmit={(e) => {
        e.preventDefault();
        ask(text);
      }}
      className={cn("glass relative overflow-hidden rounded-3xl p-5 shadow-soft", className)}
    >
      <div className="pointer-events-none absolute -end-16 -top-16 h-48 w-48 rounded-full bg-gold-300/30 blur-3xl" />
      <div className="relative flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-soft">
          <Bot className="h-5 w-5" />
        </span>
        <div>
          <p className="font-display text-lg font-bold text-brand-900 dark:text-white">Ask Watan-e-Pak AI</p>
          <p className="text-xs text-ink-mute">Describe it in English or Urdu — AI finds and checks it</p>
        </div>
      </div>
      <div className="relative mt-4 grid grid-cols-3 gap-1 rounded-2xl bg-brand-50/80 p-1 dark:bg-white/[.06]" role="tablist" aria-label="What do you want to do?">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            role="tab"
            aria-selected={mode === m.value}
            onClick={() => setMode(m.value)}
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-xl px-1.5 py-1.5 text-[12px] font-semibold transition",
              mode === m.value ? "bg-white text-brand-800 shadow-sm dark:bg-white/15 dark:text-white" : "text-ink-mute hover:text-brand-800 dark:hover:text-white",
            )}
          >
            <m.icon className="h-3.5 w-3.5" /> <span className="truncate">{m.label}</span>
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
        rows={3}
        dir="auto"
        placeholder={current.placeholder}
        className="relative mt-3 block w-full resize-none rounded-2xl bg-white px-3.5 py-3 text-sm leading-relaxed text-ink outline-none ring-1 ring-brand-100 placeholder:text-ink-mute focus:ring-brand-400 dark:bg-white/5 dark:text-white dark:ring-white/10"
      />
      <div className="relative mt-3 flex items-center gap-2">
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
          className={cn("flex h-10 w-10 items-center justify-center rounded-full transition", listening ? "animate-pulse bg-red-500 text-white" : "text-brand-700 hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-white/10")}
        >
          <Mic className="h-[18px] w-[18px]" />
        </button>
        <button type="submit" className="btn btn-gold h-10 rounded-full px-4 text-sm">
          <Sparkles className="h-4 w-4" /> Ask AI
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- market showcase
const FILTERS: { key: string; label: string; match: (p: Property) => boolean }[] = [
  { key: "all", label: "All", match: () => true },
  { key: "projects", label: "New projects", match: (p) => !!p.project_id },
  { key: "apartment", label: "Apartments", match: (p) => p.category === "apartment" },
  { key: "house", label: "Houses", match: (p) => p.category === "house" },
  { key: "plot", label: "Plots", match: (p) => p.category === "plot" },
  { key: "commercial", label: "Shops & offices", match: (p) => p.use_type === "commercial" },
];

export function MarketShowcase({ props, loading }: { props: Property[]; loading: boolean }) {
  const nav = useNavigate();
  const [filter, setFilter] = useState("all");
  const [more, setMore] = useState(false);
  const list = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter)!;
    // the portal's order from the API (DHA / Bahria phases first, Islamabad first); a big project's
    // units become one card per unit type, and on "All" one card per project so it can't fill the row
    const rows = groupProjectUnits(props.filter(f.match));
    const seen = new Set<string>();
    const items = filter === "all" ? rows.filter((r) => !isGroup(r) || (!seen.has(r.projectId) && !!seen.add(r.projectId))) : rows;
    return items.map((r) =>
      isGroup(r)
        ? {
            id: r.key,
            href: `/properties?project=${r.projectId}&unit_type=${encodeURIComponent(r.unitType)}`,
            img: coverImage(r.units[0]!),
            chip: `New project · ${r.units.length} available`,
            title: `${r.projectName} — ${/s$/i.test(r.unitType) ? r.unitType : r.unitType + "s"}`,
            where: [r.units[0]!.scheme_name, r.units[0]!.city_name].filter(Boolean).join(", "),
            price: priceRange(r.priceMin, r.priceMax),
            ask: `Tell me about the ${r.unitType}s at ${r.projectName} — prices, sizes, floors and payment plan.`,
            cta: `See all ${r.units.length}`,
          }
        : {
            id: r.id,
            href: `/properties/${r.id}`,
            img: coverImage(r),
            chip: r.project_id ? "New project" : r.category,
            title: r.title,
            where: [r.scheme_name, r.city_name].filter(Boolean).join(", "),
            price: pkrShort(r.price),
            ask: `Tell me about “${r.title}” — is it good value, and what is nearby?`,
            cta: "View details",
          },
    );
  }, [props, filter]);
  const shown = list.slice(0, more ? 12 : 8);
  return (
    <section className="container mt-16">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="section-eyebrow">On the market now</p>
          <h2 className="mt-1 font-display text-3xl font-bold text-brand-900 dark:text-white">Fresh listings and new projects</h2>
        </div>
        <Link to="/properties" className="btn btn-outline">
          View all <ArrowRight className="h-4 w-4 rtl:rotate-180" />
        </Link>
      </div>
      <div className="no-scrollbar mt-5 flex gap-2 overflow-x-auto" role="tablist" aria-label="Filter listings">
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
            className={cn("chip shrink-0 ring-1 transition", filter === f.key ? "bg-brand-700 text-white ring-brand-700" : "bg-white text-ink-soft ring-black/10 hover:ring-brand-300 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10")}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {loading
          ? Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-72 animate-pulse rounded-2xl bg-black/5 dark:bg-white/5" />)
          : shown.map((p, i) => (
              <motion.article
                key={p.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i, 8) * 0.04 }}
                className="card card-hover flex flex-col overflow-hidden"
              >
                <Link to={p.href} className="group relative block aspect-[16/10] overflow-hidden bg-black/5">
                  <img src={p.img} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
                  <span className="chip absolute start-2.5 top-2.5 bg-white/90 text-brand-800 shadow">{p.chip}</span>
                  <RepresentativeTag src={p.img} className="bottom-2 start-2.5" />
                </Link>
                <div className="flex flex-1 flex-col p-3.5">
                  <p className="line-clamp-2 text-sm font-semibold leading-snug text-ink dark:text-white">{p.title}</p>
                  <p className="mt-1 flex items-center gap-1 truncate text-xs text-ink-mute">
                    <MapPin className="h-3.5 w-3.5 shrink-0" /> {p.where}
                  </p>
                  <p className="mt-1.5 font-display text-base font-bold text-brand-800 dark:text-gold-300">{p.price}</p>
                  <div className="mt-auto flex gap-2 pt-3">
                    <Link to={p.href} className="btn btn-primary btn-sm flex-1">
                      {p.cta}
                    </Link>
                    <button
                      type="button"
                      onClick={() => nav(`/ai?q=${encodeURIComponent(p.ask)}`)}
                      className="btn btn-gold btn-sm flex-1"
                    >
                      <Sparkles className="h-3.5 w-3.5" /> Ask AI
                    </button>
                  </div>
                </div>
              </motion.article>
            ))}
      </div>
      {!loading && list.length > shown.length && !more && (
        <div className="mt-6 flex justify-center">
          <button type="button" onClick={() => setMore(true)} className="btn btn-outline btn-sm">
            Show more
          </button>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- you + AI
const TOGETHER: [string, string][] = [
  ["You describe the home, budget and area — in English or Urdu.", "AI searches every listing and new project and shortlists the best three."],
  ["You ask whether a society is approved.", "AI checks the authority’s list and shows the official source."],
  ["You choose what matters: schools, commute, price per marla.", "AI compares them on the map, with ring roads and major infrastructure nearby."],
  ["You decide to visit.", "AI sends the call request and remembers your budget for next time."],
];

export function Together() {
  return (
    <section className="container mt-14 grid gap-6 lg:grid-cols-3">
      <div className="card p-6 sm:p-8 lg:col-span-2">
        <p className="section-eyebrow">How we work together</p>
        <h2 className="mt-1 font-display text-2xl font-bold text-brand-900 sm:text-3xl dark:text-white">You stay in charge. Watan-e-Pak AI does the legwork.</h2>
        <div className="mt-6 grid gap-x-5 gap-y-3 md:grid-cols-2">
          {TOGETHER.map(([you, ai], i) => (
            <div key={i} className="flex flex-col gap-2">
              <motion.p initial={{ opacity: 0, x: -8 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} className="flex items-center gap-3 rounded-2xl bg-brand-50 px-4 py-2.5 text-sm text-brand-900 dark:bg-white/[.06] dark:text-slate-200">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-brand-700 dark:bg-white/10 dark:text-brand-200">
                  <UserRound className="h-3.5 w-3.5" />
                </span>
                {you}
              </motion.p>
              <motion.p initial={{ opacity: 0, x: 8 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.06 }} className="flex items-center gap-3 rounded-2xl bg-gold-gradient px-4 py-2.5 text-sm font-semibold text-brand-950">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-900 text-gold-300">
                  <Bot className="h-3.5 w-3.5" />
                </span>
                {ai}
              </motion.p>
            </div>
          ))}
        </div>
      </div>
      <TrustCard />
    </section>
  );
}

// The right third beside "You stay in charge": why the answers can be trusted.
const TRUST: { icon: typeof Quote; title: string; text: string }[] = [
  { icon: Quote, title: "Every answer is cited", text: "Numbered sources you can open and check." },
  { icon: BadgeCheck, title: "Official sources first", text: "Authority lists outrank listing data." },
  { icon: ShieldCheck, title: "Approval checks", text: "Society status from the CDA, RDA, LDA and others." },
  { icon: Lock, title: "Private memory", text: "Never CNIC or card numbers. Clear it any time." },
];
const TIERS = ["Official", "Verified", "Reference", "Listing"];

function TrustCard() {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="flex flex-col rounded-3xl bg-brand-gradient p-6 text-white shadow-soft sm:p-8">
      <p className="text-xs font-semibold uppercase tracking-[.18em] text-gold-300">Why you can trust it</p>
      <h3 className="mt-1 font-display text-xl font-bold">Answers you can check.</h3>
      <ul className="mt-4 space-y-3">
        {TRUST.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-gold-300">
              <Icon className="h-4 w-4" />
            </span>
            <span className="text-sm">
              <span className="block font-semibold">{title}</span>
              <span className="text-white/75">{text}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {TIERS.map((t, i) => (
          <span key={t} className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-semibold", i === 0 ? "bg-gold-gradient text-brand-950" : "bg-white/10 text-white/85")}>
            {t}
          </span>
        ))}
      </div>
      <div className="min-h-6 flex-1" />
      <Link to="/ai" className="btn btn-gold justify-center">
        <Sparkles className="h-4 w-4" /> Ask Watan-e-Pak AI
      </Link>
    </motion.div>
  );
}

// ---------------------------------------------------------------- showcase
export function MapShowcase() {
  const stats = useApi<{ inventory: Record<string, number> }>("/portal/statistics");
  const inv = stats.data?.inventory;
  return (
    <section className="container mt-16">
      <div className="grid items-center gap-8 lg:grid-cols-[1.15fr_1fr]">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="rounded-3xl bg-gold-gradient p-2 shadow-soft">
          <img src="/showcase/gis-explorer.png" alt="The GIS explorer: roads, water bodies, provinces, mega projects and listings across Pakistan" loading="lazy" className="w-full rounded-[20px]" />
        </motion.div>
        <div>
          <p className="section-eyebrow">Your search in one place</p>
          <h2 className="mt-1 font-display text-3xl font-bold text-brand-900 dark:text-white">One map for every decision</h2>
          <p className="mt-3 text-ink-soft dark:text-slate-300">
            Listings, housing societies and DHA master plans, roads and water, districts and terrain, and the ring roads and motorways that move prices — on one map, with an area study you can print.
          </p>
          <div className="mt-5 flex flex-wrap gap-6 text-sm">
            {[
              [inv?.properties, "listings on the map"],
              [inv?.schemes, "housing societies"],
              [inv?.cities, "cities"],
            ].map(([n, l]) => (
              <div key={String(l)}>
                <p className="font-display text-2xl font-bold text-brand-800 dark:text-gold-300">{n ?? "—"}</p>
                <p className="text-ink-mute">{l}</p>
              </div>
            ))}
          </div>
          <Link to="/map" className="btn btn-primary mt-6">
            Open the map <ArrowRight className="h-4 w-4 rtl:rotate-180" />
          </Link>
        </div>
      </div>
    </section>
  );
}
