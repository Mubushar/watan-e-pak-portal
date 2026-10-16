/** Navigation chrome: bottom tab bar on phones, a side rail on tablets / desktop. */
import { Suspense, useSyncExternalStore, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Building2, CloudOff, Compass, Heart, Home, LogIn, Mic, UserRound } from "lucide-react";
import { connectivity } from "@/lib/api";
import { cn } from "@/lib/utils";
import { roleLabel, useAuth } from "@/store/auth";
import { Avatar, Logo, Spinner } from "./ui";

const TABS = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/explore", label: "Explore", icon: Compass },
  { to: "/assistant", label: "Assistant", icon: Bot, center: true },
  { to: "/listings", label: "My Listings", icon: Building2 },
  { to: "/profile", label: "Profile", icon: UserRound },
];

export function useOffline() {
  return useSyncExternalStore(
    (cb) => connectivity.subscribe(cb),
    () => connectivity.offline,
  );
}

function OfflineBanner() {
  const offline = useOffline();
  return (
    <AnimatePresence>
      {offline && (
        <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden bg-gold-100 text-gold-900 dark:bg-gold-900/40 dark:text-gold-100">
          <div className="screen flex items-center gap-2 py-1.5 text-xs font-medium">
            <CloudOff className="h-3.5 w-3.5 shrink-0" />
            Offline — showing saved sample listings. Check your connection or Profile → Server.
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function SideRail() {
  const user = useAuth((s) => s.user);
  return (
    <aside className="pt-safe sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-e border-black/5 bg-white/70 px-4 pb-6 backdrop-blur-xl md:flex dark:border-white/10 dark:bg-[#0b1a12]/70">
      <div className="drag flex h-16 items-center">
        <NavLink to="/" className="no-drag">
          <Logo />
        </NavLink>
      </div>
      <nav className="mt-6 flex flex-col gap-1">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition",
                isActive ? "bg-brand-700 text-white shadow-soft dark:bg-brand-600" : "text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/5",
              )
            }
          >
            <t.icon className="h-5 w-5" />
            {t.label}
          </NavLink>
        ))}
        <NavLink
          to="/saved"
          className={({ isActive }) =>
            cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition", isActive ? "bg-brand-700 text-white" : "text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/5")
          }
        >
          <Heart className="h-5 w-5" /> Saved
        </NavLink>
      </nav>
      <NavLink to="/assistant?listen=1" className="btn btn-gold mt-6 w-full">
        <Mic className="h-4 w-4" /> Talk to AI
      </NavLink>
      <div className="mt-auto">
        {user ? (
          <NavLink to="/profile" className="flex items-center gap-3 rounded-xl p-2 hover:bg-brand-50 dark:hover:bg-white/5">
            <Avatar name={user.name ?? user.email ?? user.mobile} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold">{user.name ?? user.email ?? user.mobile}</span>
              <span className="block text-xs text-ink-mute">{roleLabel(user.role)}</span>
            </span>
          </NavLink>
        ) : (
          <NavLink to="/signin" className="btn btn-outline w-full">
            <LogIn className="h-4 w-4" /> Sign in
          </NavLink>
        )}
      </div>
    </aside>
  );
}

function TabBar() {
  return (
    <nav className="pb-safe fixed inset-x-0 bottom-0 z-40 border-t border-black/5 bg-white/90 backdrop-blur-xl md:hidden dark:border-white/10 dark:bg-[#0b1a12]/90">
      <div className="mx-auto flex h-16 max-w-lg items-stretch justify-around px-2">
        {TABS.map((t) =>
          t.center ? (
            <NavLink key={t.to} to={t.to} aria-label={t.label} className="-mt-6 flex flex-col items-center">
              {({ isActive }) => (
                <>
                  <span className={cn("relative flex h-14 w-14 items-center justify-center rounded-full bg-gold-gradient text-brand-950 shadow-glow ring-4 ring-[#f6f8f6] transition dark:ring-[#07130d]", isActive && "scale-105")}>
                    <span className="absolute inset-0 animate-ping rounded-full bg-gold-400 opacity-20" />
                    <Bot className="relative h-6 w-6" />
                  </span>
                  <span className="mt-0.5 text-[10px] font-bold text-gold-700 dark:text-gold-300">Ask AI</span>
                </>
              )}
            </NavLink>
          ) : (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) => cn("flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition", isActive ? "text-brand-700 dark:text-brand-300" : "text-ink-mute dark:text-slate-500")}
            >
              {({ isActive }) => (
                <>
                  <t.icon className={cn("h-5 w-5 transition", isActive && "scale-110")} strokeWidth={isActive ? 2.4 : 2} />
                  {t.label}
                </>
              )}
            </NavLink>
          ),
        )}
      </div>
    </nav>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const { pathname } = useLocation();
  // The assistant manages its own full-height layout (composer pinned above the tab bar).
  const flush = pathname.startsWith("/assistant");
  return (
    <div className="flex min-h-full">
      <SideRail />
      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <main key={pathname} className={cn("flex-1", flush ? "pb-[calc(5.25rem+env(safe-area-inset-bottom))] md:pb-0" : "tabbar-space md:pb-8")}>
          <Suspense
            fallback={
              <div className="flex h-[60vh] items-center justify-center">
                <Spinner className="h-7 w-7" />
              </div>
            }
          >
            {children ?? <Outlet />}
          </Suspense>
        </main>
      </div>
      <TabBar />
    </div>
  );
}
