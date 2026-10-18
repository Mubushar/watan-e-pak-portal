import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  ChevronDown,
  Facebook,
  GitCompareArrows,
  Heart,
  Instagram,
  Linkedin,
  Mail,
  MapPin,
  Menu,
  Phone,
  Plus,
  Search,
  Twitter,
  Youtube,
} from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";
import { useAuth } from "@/store/auth";
import { Drawer, Spinner } from "@/components/ui";
import { AdSlot } from "@/components/ads/AdSlot";
import { AssistantWidget } from "@/components/ai/AssistantWidget";
import { LiveTicker } from "@/components/ticker/LiveTicker";
import { usePalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import { LangToggle, Logo, OfflineBanner, ThemeToggle, UserMenu } from "./Chrome";

const MAIN_NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/properties", label: "Properties" },
  { to: "/schemes", label: "Schemes" },
  { to: "/map", label: "Map" },
  { to: "/insights", label: "Insights" },
  { to: "/tools", label: "Tools" },
  { to: "/ai", label: "AI Hub" },
];

const MORE_NAV = [
  { to: "/infrastructure", label: "Infrastructure", hint: "Ring roads, motorways, new sectors, SEZs" },
  { to: "/projects", label: "Mega Projects", hint: "Malls, towers & compounds" },
  { to: "/news", label: "News & Impact", hint: "Market-moving headlines" },
  { to: "/stories", label: "Success Stories", hint: "Case studies & testimonials" },
  { to: "/pricing", label: "Products & Pricing", hint: "Plans for brokers & developers" },
  { to: "/pages/about", label: "About Arz-e-Pak", hint: "Our mission and team" },
  { to: "/pages/faq", label: "FAQ", hint: "How the portal works" },
];

function Navbar() {
  const t = useT();
  const [scrolled, setScrolled] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [more, setMore] = useState(false);
  const favs = usePrefs((s) => s.favorites.length);
  const cmp = usePrefs((s) => s.compare.length);
  const setPalette = usePalette((s) => s.setOpen);
  const loc = useLocation();
  const user = useAuth((s) => s.user);

  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 12);
    h();
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);
  useEffect(() => {
    setMobile(false);
    setMore(false);
  }, [loc.pathname]);

  const link = ({ isActive }: { isActive: boolean }) =>
    cn(
      "relative whitespace-nowrap rounded-full px-3 py-2 text-sm font-semibold transition-colors",
      isActive ? "bg-brand-700 text-white shadow-soft" : "text-ink-soft hover:bg-brand-50 hover:text-brand-800 dark:text-slate-300 dark:hover:bg-white/5",
    );

  return (
    <header className={cn("sticky top-0 z-50 transition-all duration-300", scrolled ? "glass shadow-soft" : "bg-white/40 backdrop-blur-sm dark:bg-transparent")}>
      <div className="container flex h-[72px] items-center gap-4">
        <Logo />
        <nav className="ms-2 hidden items-center gap-0.5 xl:flex">
          {MAIN_NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={link}>
              {t(n.label)}
            </NavLink>
          ))}
          <div className="relative" onMouseEnter={() => setMore(true)} onMouseLeave={() => setMore(false)}>
            <button className="inline-flex items-center gap-1 whitespace-nowrap rounded-full px-3 py-2 text-sm font-semibold text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/5">
              More <ChevronDown className={cn("h-4 w-4 transition", more && "rotate-180")} />
            </button>
            <AnimatePresence>
              {more && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} className="absolute start-0 top-full pt-2">
                  <div className="card grid w-[440px] grid-cols-2 gap-1 p-2">
                    {MORE_NAV.map((m) => (
                      <Link key={m.to} to={m.to} className="rounded-xl p-3 transition hover:bg-brand-50 dark:hover:bg-white/5">
                        <p className="text-sm font-semibold text-ink dark:text-white">{m.label}</p>
                        <p className="text-xs text-ink-mute">{m.hint}</p>
                      </Link>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </nav>

        <div className="ms-auto flex items-center gap-1.5">
          <button onClick={() => setPalette(true)} className="hidden h-10 items-center gap-2 whitespace-nowrap rounded-full border border-black/10 bg-white/70 px-3.5 text-sm text-ink-mute transition hover:border-brand-300 md:flex dark:border-white/10 dark:bg-white/5">
            <Search className="h-4 w-4" /> <span className="2xl:inline xl:hidden">Search</span>
            <kbd className="kbd ms-1 2xl:ms-3">Ctrl K</kbd>
          </button>
          <button onClick={() => setPalette(true)} className="btn btn-ghost btn-icon md:hidden" aria-label="Search">
            <Search className="h-5 w-5" />
          </button>
          <LangToggle className="hidden sm:inline-flex" />
          <ThemeToggle className="hidden sm:inline-flex" />
          <Link to="/compare" className="btn btn-ghost btn-icon relative hidden sm:inline-flex" aria-label="Compare">
            <GitCompareArrows className="h-5 w-5" />
            {cmp > 0 && <span className="absolute -end-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-gold-500 px-1 text-[10px] font-bold text-brand-950">{cmp}</span>}
          </Link>
          <Link to="/favorites" className="btn btn-ghost btn-icon relative hidden sm:inline-flex" aria-label="Favourites">
            <Heart className="h-5 w-5" />
            {favs > 0 && <span className="absolute -end-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">{favs}</span>}
          </Link>
          <UserMenu />
          <Link to={user ? "/app/listings/new" : "/login?next=/app/listings/new"} className="btn btn-primary ms-1 hidden lg:inline-flex">
            {t("List Property")} <Plus className="h-4 w-4" />
          </Link>
          <button className="btn btn-ghost btn-icon xl:hidden" onClick={() => setMobile(true)} aria-label="Menu">
            <Menu className="h-6 w-6" />
          </button>
        </div>
      </div>
      <Drawer open={mobile} onClose={() => setMobile(false)} title={<Logo />} side="right">
        <div className="space-y-1 p-4">
          {[...MAIN_NAV, ...MORE_NAV].map((n) => (
            <NavLink key={n.to} to={n.to} end={"end" in n ? n.end : false} className={({ isActive }) => cn("block rounded-xl px-4 py-3 font-semibold", isActive ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/5")}>
              {t(n.label)}
            </NavLink>
          ))}
          <div className="flex flex-wrap items-center gap-2 pt-4">
            <LangToggle />
            <ThemeToggle />
            <Link to="/compare" className="btn btn-outline btn-sm">
              Compare ({cmp})
            </Link>
            <Link to="/favorites" className="btn btn-outline btn-sm">
              <Heart className="h-4 w-4" /> Saved ({favs})
            </Link>
          </div>
          <Link to="/app" className="btn btn-primary mt-4 w-full">
            Open dashboard
          </Link>
        </div>
      </Drawer>
    </header>
  );
}

function CompareTray() {
  const ids = usePrefs((s) => s.compare);
  const clear = usePrefs((s) => s.clearCompare);
  const loc = useLocation();
  if (ids.length < 1 || loc.pathname === "/compare") return null;
  return (
    <motion.div initial={{ y: 80 }} animate={{ y: 0 }} className="fixed bottom-6 start-1/2 z-[80] -translate-x-1/2 rtl:translate-x-1/2">
      <div className="glass-dark flex items-center gap-3 rounded-full py-2 pe-2 ps-5 shadow-2xl">
        <GitCompareArrows className="h-4 w-4 text-gold-300" />
        <span className="text-sm font-semibold">{ids.length} selected for comparison</span>
        <button onClick={clear} className="text-xs text-white/60 hover:text-white">
          Clear
        </button>
        <Link to="/compare" className="btn btn-gold btn-sm rounded-full">
          Compare now
        </Link>
      </div>
    </motion.div>
  );
}

function Footer() {
  const contacts = useApi<{ channels: { id: string; channel_type: string; label: string; value: string; url?: string | null }[] }>("/content/contacts", undefined, { staleTime: 30 * 60_000 });
  const ch = contacts.data?.channels ?? [];
  const phone = ch.find((c) => c.channel_type === "phone");
  const email = ch.find((c) => c.channel_type === "email");
  const office = ch.find((c) => c.channel_type === "office" || c.channel_type === "address");
  const cols = [
    { title: "Explore", links: [["Properties", "/properties"], ["Housing schemes", "/schemes"], ["Infrastructure", "/infrastructure"], ["Mega projects", "/projects"], ["Map explorer", "/map"], ["Compare", "/compare"]] },
    { title: "Intelligence", links: [["Market insights", "/insights"], ["News & impact", "/news"], ["AI Hub", "/ai"], ["MCP console", "/ai/mcp"], ["Tools center", "/tools"]] },
    { title: "Company", links: [["About", "/pages/about"], ["Mission", "/pages/mission"], ["Careers", "/pages/careers"], ["Success stories", "/stories"], ["Pricing", "/pricing"]] },
    { title: "Help", links: [["How it works", "/pages/how-it-works"], ["FAQ", "/pages/faq"], ["Terms", "/pages/terms"], ["Privacy", "/pages/privacy"], ["Dashboard", "/app"]] },
  ];
  return (
    <footer className="relative mt-16 overflow-hidden bg-brand-950 text-white">
      <div className="pointer-events-none absolute inset-0 bg-mesh opacity-60" />
      <div className="container relative pt-12">
        <AdSlot slot="footer" />
      </div>
      <div className="container relative grid gap-10 py-14 lg:grid-cols-[1.3fr_2fr]">
        <div>
          <Logo light />
          <p className="mt-4 max-w-sm text-sm text-white/70">Your land · Our intelligence · A brighter Pakistan. An AI-first portal for buyers, investors, brokers and developers — powered by MCP agents and live market data.</p>
          <ul className="mt-6 space-y-2.5 text-sm text-white/80">
            {phone && (
              <li className="flex items-center gap-2">
                <Phone className="h-4 w-4 text-gold-300" /> {phone.value}
              </li>
            )}
            {email && (
              <li className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-gold-300" /> {email.value}
              </li>
            )}
            {office && (
              <li className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-gold-300" /> {office.value}
              </li>
            )}
          </ul>
          <div className="mt-6 flex gap-2">
            {[Facebook, Instagram, Twitter, Linkedin, Youtube].map((I, i) => (
              <a key={i} href="#" className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 transition hover:bg-gold-500 hover:text-brand-950" aria-label="Social link">
                <I className="h-4 w-4" />
              </a>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          {cols.map((c) => (
            <div key={c.title}>
              <p className="font-display font-semibold text-gold-300">{c.title}</p>
              <ul className="mt-3 space-y-2 text-sm text-white/70">
                {c.links.map(([l, to]) => (
                  <li key={to}>
                    <Link to={to!} className="hover:text-white">
                      {l}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div className="relative border-t border-white/10">
        <div className="container flex flex-col items-center justify-between gap-2 py-5 text-xs text-white/50 sm:flex-row">
          <p>© {new Date().getFullYear()} Arz-e-Pak AI Real Estate Portal. All rights reserved.</p>
          <p className="flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5" /> Built on FastAPI · MCP · OpenAI-compatible RAG
          </p>
        </div>
      </div>
    </footer>
  );
}

export function PublicLayout() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [pathname]);
  return (
    <div className="flex min-h-screen flex-col overflow-x-clip">
      <LiveTicker />
      <OfflineBanner />
      <Navbar />
      <main className="flex-1">
        <Suspense fallback={<div className="flex min-h-[50vh] items-center justify-center"><Spinner className="h-8 w-8" /></div>}>
          <ErrorBoundary resetKey={pathname}>
            <Outlet />
          </ErrorBoundary>
        </Suspense>
      </main>
      <Footer />
      <CompareTray />
      <AssistantWidget />
    </div>
  );
}
