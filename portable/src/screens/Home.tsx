import { useState } from "react";
import { cn } from "@/lib/utils";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Bot, Building, Building2, Compass, Heart, Home as HomeIcon, KeyRound, LandPlot, LineChart, Mic, PlusCircle, Search, Shuffle, Sparkles, Store, TrendingUp, UserRound, Wand2 } from "lucide-react";
import type { City, PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { cityImage } from "@/lib/images";
import { roleLabel, useAuth } from "@/store/auth";
import { Avatar, Logo, SectionHead, Skeleton } from "@/components/ui";
import { PropertyCard, PropertyRow } from "@/components/PropertyCard";
import { AdSlot, BannerSpacer, useNativeBanner } from "@/components/Ads";

type Action = { icon: typeof HomeIcon; label: string; to: string; tone?: "gold" };

/** Shortcuts tuned to what each kind of member usually does first. */
function actionsFor(role?: string): Action[] {
  const ask = (q: string) => `/assistant?q=${encodeURIComponent(q)}`;
  switch (role) {
    case "seller":
    case "landlord":
    case "agent":
      return [
        { icon: PlusCircle, label: "Add listing", to: "/listings/new", tone: "gold" },
        { icon: Building2, label: "My listings", to: "/listings" },
        { icon: Wand2, label: "Price check", to: ask("What is a fair asking price for a 10 marla house in Lahore?") },
        { icon: Compass, label: "Market", to: "/explore" },
      ];
    case "investor":
      return [
        { icon: LineChart, label: "Best picks", to: ask("Best investment plots in Islamabad"), tone: "gold" },
        { icon: Sparkles, label: "Featured", to: "/explore?featured=1" },
        { icon: PlusCircle, label: "List asset", to: "/listings/new" },
        { icon: Heart, label: "Saved", to: "/saved" },
      ];
    case "buyer":
    case "tenant":
      return [
        { icon: HomeIcon, label: "Homes", to: "/explore?category=house", tone: "gold" },
        { icon: LandPlot, label: "Plots", to: "/explore?category=plot" },
        { icon: Bot, label: "Ask AI", to: "/assistant" },
        { icon: Heart, label: "Saved", to: "/saved" },
      ];
    default:
      return [
        { icon: Search, label: "Find", to: "/explore", tone: "gold" },
        { icon: PlusCircle, label: "Sell / Rent", to: "/listings/new" },
        { icon: Bot, label: "Ask AI", to: "/assistant" },
        { icon: Heart, label: "Saved", to: "/saved" },
      ];
  }
}

// A real photo (Wikimedia Commons, credited) behind the greeting.
const HERO_PHOTO = {
  img: "https://upload.wikimedia.org/wikipedia/commons/thumb/4/40/Faisal_Mosque%2C_Islamabad%2C_Pakistan.jpg/960px-Faisal_Mosque%2C_Islamabad%2C_Pakistan.jpg",
  credit: "Faisal Mosque & Margalla Hills · Ahmad Haq · CC BY-SA 4.0",
};

type Mode = "find" | "invest" | "sell";
const MODES: { value: Mode; label: string; icon: typeof HomeIcon; placeholder: string; prefix: string }[] = [
  { value: "find", label: "Find", icon: HomeIcon, placeholder: "10 marla house in DHA Phase 2 under 5 crore…", prefix: "" },
  { value: "invest", label: "Invest", icon: TrendingUp, placeholder: "Best place to invest 2 crore in Rawalpindi?", prefix: "Investment question: " },
  { value: "sell", label: "Sell", icon: KeyRound, placeholder: "Sell my 1 kanal house in Bahria Phase 8…", prefix: "I want to sell or rent out my property: " },
];
const SURPRISES = [
  "Shops under 50 lakh in China Center, Bahria Town Phase 8",
  "Which housing societies in Rawalpindi are approved by RDA?",
  "2 bed apartment in Goldcrest Breeze with a Margalla view",
  "اسلام آباد میں 1.5 کروڑ تک 3 کمروں کا گھر",
  "Skyra Tower penthouse with a private pool — payment plan?",
];
const POPULAR = ["Approved societies", "Apartments under 1 crore", "New projects", "Plots near Ring Road"];

const CATEGORIES = [
  { value: "house", label: "Houses", icon: HomeIcon },
  { value: "apartment", label: "Apartments", icon: Building },
  { value: "plot", label: "Plots", icon: LandPlot },
  { value: "shop", label: "Shops", icon: Store },
  { value: "office", label: "Offices", icon: Building2 },
];

export default function Home() {
  const nav = useNavigate();
  const user = useAuth((s) => s.user);
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<Mode>("find");
  const current = MODES.find((m) => m.value === mode)!;
  const ask = (text: string) => nav(`/assistant?q=${encodeURIComponent(current.prefix + (text.trim() || current.placeholder.replace(/…$/, "")))}`);
  const projects = useApi<{ projects: { id: string; name: string; city: string; image?: string | null; price_from?: number | null; units_available?: number | null; payment_plan?: string | null }[] }>("/bigprojects");
  const featured = useApi<PropertyList>("/search", { featured: true, limit: 10 });
  const latest = useApi<PropertyList>("/properties", { limit: 6 });
  const cities = useApi<{ cities: City[] }>("/cities");
  const first = user?.name?.split(" ")[0];
  useNativeBanner();

  return (
    <div>
      {/* ---------- hero ---------- */}
      <section className="relative overflow-hidden bg-brand-gradient text-white md:mx-6 md:mt-6 md:rounded-3xl">
        <img src={HERO_PHOTO.img} alt="Faisal Mosque and the Margalla Hills, Islamabad" className="absolute inset-0 h-full w-full object-cover opacity-35" />
        <div className="absolute inset-0 bg-mesh" />
        <p className="absolute bottom-12 end-3 text-[9px] text-white/50">{HERO_PHOTO.credit}</p>
        <div className="pt-safe relative">
          <div className="screen flex items-center justify-between py-3 md:hidden">
            <Logo light compact />
            {user ? (
              <Link to="/profile" aria-label="Profile">
                <Avatar name={user.name ?? user.email ?? user.mobile} className="h-9 w-9 text-sm" />
              </Link>
            ) : (
              <Link to="/signin" className="btn btn-sm border border-white/25 bg-white/10 text-white">
                Sign in
              </Link>
            )}
          </div>
          <div className="screen pb-16 pt-4 md:pb-14 md:pt-10">
            <p className="text-sm text-white/75">{first ? `Assalam-o-Alaikum, ${first}` : "Assalam-o-Alaikum"} 👋</p>
            <h1 className="mt-1 font-display text-3xl font-bold leading-tight md:text-4xl">
              {user ? (
                <>
                  What can we help you <span className="text-gradient">{["seller", "agent", "landlord"].includes(user.role) ? "sell" : "find"}</span> today?
                </>
              ) : (
                <>
                  Find your place in <span className="text-gradient">Pakistan</span>
                </>
              )}
            </h1>
            {user && <span className="chip mt-3 bg-white/10 text-gold-200 ring-1 ring-white/15">{roleLabel(user.role)} account</span>}
          </div>
        </div>
      </section>

      <div className="screen -mt-9 relative z-10">
        {/* ---------- AI search ---------- */}
        <form
          className="card p-1.5 shadow-soft"
          onSubmit={(e) => {
            e.preventDefault();
            ask(q);
          }}
        >
          <div className="grid grid-cols-3 gap-1 rounded-[20px] bg-black/[.05] p-1 dark:bg-white/[.06]" role="tablist" aria-label="What do you want to do?">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="tab"
                aria-selected={mode === m.value}
                onClick={() => setMode(m.value)}
                className={cn("flex items-center justify-center gap-1.5 rounded-[16px] py-2 text-xs font-semibold transition", mode === m.value ? "bg-white text-brand-900 shadow-sm dark:bg-white/15 dark:text-white" : "text-ink-mute")}
              >
                <m.icon className="h-4 w-4" /> {m.label}
              </button>
            ))}
          </div>
          <textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            rows={2}
            dir="auto"
            aria-label="Describe what you are looking for"
            placeholder={current.placeholder}
            className="mt-1 block w-full resize-none bg-transparent px-3 py-2.5 text-base leading-snug outline-none placeholder:text-ink-mute/70"
          />
          <div className="flex items-center gap-2 px-1.5 pb-1">
            <button type="button" onClick={() => setQ(SURPRISES[Math.floor(Math.random() * SURPRISES.length)]!)} className="inline-flex items-center gap-1 rounded-full border border-gold-300 bg-gold-50 px-2.5 py-1.5 text-[11px] font-semibold text-gold-800 dark:border-gold-500/40 dark:bg-gold-500/10 dark:text-gold-200">
              <Shuffle className="h-3.5 w-3.5" /> Surprise me
            </button>
            <span className="flex-1" />
            <Link to="/assistant?listen=1" aria-label="Speak to the assistant" className="flex h-10 w-10 items-center justify-center rounded-full text-ink-soft active:bg-black/5 dark:text-slate-300">
              <Mic className="h-5 w-5" />
            </Link>
            <button type="submit" className="inline-flex h-10 items-center gap-1.5 rounded-full bg-gold-gradient px-4 text-sm font-bold text-brand-950 shadow-glow">
              Ask AI <ArrowRight className="h-4 w-4 rtl:rotate-180" />
            </button>
          </div>
        </form>
        <div className="no-scrollbar -mx-4 mt-3 flex gap-2 overflow-x-auto px-4">
          {POPULAR.map((s) => (
            <button key={s} type="button" onClick={() => ask(s)} className="shrink-0 rounded-full bg-white px-3 py-1.5 text-xs font-medium text-brand-800 ring-1 ring-black/5 dark:bg-white/5 dark:text-brand-100 dark:ring-white/10">
              {s}
            </button>
          ))}
        </div>

        {/* ---------- quick actions ---------- */}
        <div className="mt-5 grid grid-cols-4 gap-2.5">
          {actionsFor(user?.role).map((a, i) => (
            <motion.div key={a.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Link to={a.to} className="card flex flex-col items-center gap-1.5 px-1 py-3 text-center active:scale-95 transition">
                <span className={a.tone === "gold" ? "flex h-10 w-10 items-center justify-center rounded-xl bg-gold-gradient text-brand-950 shadow-glow" : "flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-white/10 dark:text-brand-200"}>
                  <a.icon className="h-5 w-5" />
                </span>
                <span className="text-[11px] font-semibold leading-tight">{a.label}</span>
              </Link>
            </motion.div>
          ))}
        </div>

        {/* ---------- categories ---------- */}
        <div className="no-scrollbar -mx-4 mt-6 flex gap-2 overflow-x-auto px-4">
          {CATEGORIES.map((c) => (
            <Link key={c.value} to={`/explore?category=${c.value}`} className="chip shrink-0 bg-white px-3.5 py-2 text-sm text-brand-800 ring-1 ring-black/5 dark:bg-white/5 dark:text-brand-100 dark:ring-white/10">
              <c.icon className="h-4 w-4" /> {c.label}
            </Link>
          ))}
        </div>

        {/* ---------- featured ---------- */}
        <section className="mt-8">
          <SectionHead title="Featured listings" to="/explore?featured=1" />
          <div className="scroll-x no-scrollbar -mx-4 px-4">
            {featured.isLoading
              ? [0, 1].map((i) => <Skeleton key={i} className="h-72 w-72 shrink-0" />)
              : featured.data?.results.map((p) => (
                  <div key={p.id} className="w-72 shrink-0 snap-start">
                    <PropertyCard p={p} compact />
                  </div>
                ))}
          </div>
        </section>

        {/* ---------- new projects (real photos from each project's website) ---------- */}
        {!!projects.data?.projects.some((p) => p.units_available) && (
          <section className="mt-8">
            <SectionHead title="New projects" />
            <div className="scroll-x no-scrollbar -mx-4 px-4">
              {projects.data!.projects
                .filter((p) => p.units_available)
                .map((p) => (
                  <Link key={p.id} to={`/assistant?q=${encodeURIComponent(`Tell me about ${p.name}: unit types, prices and payment plan`)}`} className="relative block aspect-[4/5] w-60 shrink-0 snap-start overflow-hidden rounded-3xl bg-brand-950">
                    {p.image && <img src={p.image} alt={p.name} loading="lazy" className="absolute inset-0 h-full w-full object-cover" />}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
                    <div className="absolute inset-x-0 bottom-0 p-4 text-white">
                      <p className="font-display text-lg font-bold leading-tight">{p.name}</p>
                      <p className="text-xs text-white/75">{p.city} · {p.units_available} units available</p>
                      {p.payment_plan && <p className="mt-1 line-clamp-2 text-[11px] text-white/70">{p.payment_plan}</p>}
                      <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-gold-gradient px-3 py-1 text-[11px] font-bold text-brand-950">
                        <Sparkles className="h-3 w-3" /> Ask AI
                      </span>
                    </div>
                  </Link>
                ))}
            </div>
          </section>
        )}

        {/* ---------- you + AI ---------- */}
        <section className="mt-8 rounded-3xl bg-[#0b1611] p-4 text-white">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-gold-300">How we work together</p>
          <p className="mt-1 font-display text-xl font-light">You stay in charge. Arz-e-Pak AI does the legwork.</p>
          <div className="mt-4 space-y-2 text-[13px]">
            {[
              ["You describe the home and budget.", "AI shortlists the best three."],
              ["You ask: is this society approved?", "AI shows the official source."],
            ].map(([you, ai]) => (
              <div key={you} className="space-y-2">
                <p className="flex items-center gap-2 rounded-2xl bg-white/[.07] px-3 py-2.5 text-white/85">
                  <UserRound className="h-4 w-4 shrink-0" /> {you}
                </p>
                <p className="flex items-center gap-2 rounded-2xl bg-gold-gradient px-3 py-2.5 font-semibold text-brand-950">
                  <Bot className="h-4 w-4 shrink-0" /> {ai}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ---------- sponsored (rotating) ---------- */}
        <AdSlot slot="hero" placement="home" variant="banner" rotate className="mt-6" />

        {/* ---------- AI banner ---------- */}
        <Link to="/assistant" className="mt-6 flex items-center gap-4 overflow-hidden rounded-2xl bg-brand-gradient p-4 text-white shadow-soft">
          <span className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15">
            <span className="absolute inset-0 animate-pulse-ring rounded-2xl bg-gold-400/40" />
            <Bot className="relative h-6 w-6 text-gold-200" />
          </span>
          <span className="min-w-0">
            <span className="block font-display font-bold">Talk to Arz-e-Pak AI</span>
            <span className="block text-xs text-white/75">Search, price or list a property just by speaking — in English or Urdu.</span>
          </span>
        </Link>

        {/* ---------- cities ---------- */}
        <section className="mt-8">
          <SectionHead title="Explore by city" />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(cities.data?.cities ?? []).slice(0, 8).map((c) => (
              <Link key={c.id} to={`/explore?city=${encodeURIComponent(c.name)}`} className="group relative aspect-[4/3] overflow-hidden rounded-2xl">
                <img src={cityImage(c.name, c.image)} alt={c.name} loading="lazy" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
                <div className="absolute inset-0 bg-gradient-to-t from-brand-950/85 to-transparent" />
                <div className="absolute bottom-2.5 start-3 text-white">
                  <p className="font-display font-bold">{c.name}</p>
                  <p className="text-[11px] text-white/75">
                    {c.properties} listings · {c.schemes} societies
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </section>

        <AdSlot slot="banner" placement="home" variant="banner" rotate className="mt-8" />

        {/* ---------- latest ---------- */}
        <section className="mt-8">
          <SectionHead title="Just listed" to="/explore" />
          <div className="card divide-y divide-black/5 p-1.5 dark:divide-white/5">
            {latest.isLoading ? [0, 1, 2].map((i) => <Skeleton key={i} className="m-2 h-16" />) : latest.data?.results.map((p) => <PropertyRow key={p.id} p={p} />)}
          </div>
        </section>
        <BannerSpacer />
      </div>
    </div>
  );
}
