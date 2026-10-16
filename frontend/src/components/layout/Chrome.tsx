/** App-wide chrome bits: theme/lang sync, offline banner, logo, theme + language toggles, user menu. */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { CloudOff, LayoutDashboard, LogOut, Moon, Sun, UserRound } from "lucide-react";
import { connectivity, post } from "@/lib/api";
import { BRAND } from "@/lib/images";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { Avatar } from "@/components/ui";
import { titleCase } from "@/lib/format";

export function PrefsSync() {
  const theme = usePrefs((s) => s.theme);
  const lang = usePrefs((s) => s.lang);
  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
      root.classList.toggle("dark", dark);
    };
    apply();
    if (theme !== "system") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ur" ? "rtl" : "ltr";
  }, [lang]);
  return null;
}

export function useOffline() {
  return useSyncExternalStore(
    (cb) => connectivity.subscribe(cb),
    () => connectivity.offline,
  );
}

export function OfflineBanner() {
  const offline = useOffline();
  return (
    <AnimatePresence>
      {offline && (
        <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden bg-gold-100 text-gold-900 dark:bg-gold-900/40 dark:text-gold-100">
          <div className="container flex items-center gap-2 py-1.5 text-xs font-medium">
            <CloudOff className="h-3.5 w-3.5" />
            Backend offline — showing the bundled seed snapshot. Start it with <code className="kbd">cd backend &amp;&amp; uv run python main.py</code>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Logo({ className, light }: { className?: string; light?: boolean }) {
  return (
    <Link to="/" className={cn("flex shrink-0 items-center gap-2.5 whitespace-nowrap", className)}>
      <img src={BRAND.mark} alt="Arz-e-Pak" className="h-10 w-auto drop-shadow-sm" />
      <span className="leading-none">
        <span className={cn("block font-display text-xl font-extrabold tracking-tight", light ? "text-white" : "text-brand-800 dark:text-white")}>
          ARZ-E-<span className="text-gradient">PAK</span>
        </span>
        <span className={cn("block text-[9px] font-semibold uppercase tracking-[.22em]", light ? "text-white/70" : "text-ink-mute dark:text-slate-400")}>AI Real Estate Portal</span>
      </span>
    </Link>
  );
}

export function ThemeToggle({ className }: { className?: string }) {
  const theme = usePrefs((s) => s.theme);
  const setTheme = usePrefs((s) => s.setTheme);
  const dark = theme === "dark";
  return (
    <button onClick={() => setTheme(dark ? "light" : "dark")} className={cn("btn btn-ghost btn-icon", className)} aria-label="Toggle theme">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={dark ? "d" : "l"} initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }}>
          {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

export function LangToggle({ className }: { className?: string }) {
  const lang = usePrefs((s) => s.lang);
  const setLang = usePrefs((s) => s.setLang);
  return (
    <button
      onClick={() => setLang(lang === "en" ? "ur" : "en")}
      className={cn("inline-flex h-9 items-center rounded-full border border-brand-200 bg-white/70 p-0.5 text-xs font-semibold dark:border-white/15 dark:bg-white/5", className)}
      aria-label="Switch language"
    >
      <span className={cn("rounded-full px-2.5 py-1", lang === "en" ? "bg-brand-700 text-white" : "text-brand-800 dark:text-slate-300")}>EN</span>
      <span className={cn("rounded-full px-2.5 py-1 font-urdu", lang === "ur" ? "bg-brand-700 text-white" : "text-brand-800 dark:text-slate-300")}>اردو</span>
    </button>
  );
}

export function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  if (!user)
    return (
      <Link to="/login" className="btn btn-ghost btn-icon" aria-label="Sign in">
        <UserRound className="h-5 w-5" />
      </Link>
    );
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 rounded-full p-0.5 ring-2 ring-gold-300/60 transition hover:ring-gold-400" aria-label="Account">
        <Avatar name={user.name ?? user.email} size={34} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }} className="card absolute end-0 top-12 z-50 w-64 overflow-hidden p-1.5">
            <div className="px-3 py-2.5">
              <p className="truncate font-semibold">{user.name ?? user.email}</p>
              <p className="truncate text-xs text-ink-mute">{user.email ?? user.mobile}</p>
              <p className="mt-1.5 inline-block rounded-full bg-gold-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-gold-700 dark:bg-gold-500/10 dark:text-gold-200">{titleCase(user.role)}</p>
            </div>
            <div className="divider my-1" />
            <Link to="/app" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-brand-50 dark:hover:bg-white/5">
              <LayoutDashboard className="h-4 w-4" /> Dashboard
            </Link>
            <Link to="/app/profile" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-brand-50 dark:hover:bg-white/5">
              <UserRound className="h-4 w-4" /> Profile & notifications
            </Link>
            <button
              onClick={() => {
                post("/auth/logout").catch(() => {});
                logout();
                setOpen(false);
                nav("/");
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
