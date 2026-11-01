import { Suspense, useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Bell,
  Bot,
  BriefcaseBusiness,
  Building,
  Layers,
  Building2,
  Calculator,
  ChevronsLeft,
  FileSignature,
  Globe,
  HardHat,
  KeyRound,
  Database,
  Gauge,
  LayoutDashboard,
  Megaphone,
  Menu,
  MessagesSquare,
  PlusSquare,
  Search,
  Settings,
  ShieldCheck,
  Target,
  UserRound,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { get } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { Drawer, Spinner } from "@/components/ui";
import { usePalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import { LangToggle, Logo, OfflineBanner, ThemeToggle, UserMenu } from "./Chrome";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  badge?: number;
  /** Shown only to users with this permission (or any of these). */
  perm?: string | string[];
}

/** Permissions that open Administration → Users & roles (matches the route guard in App.tsx). */
const ADMIN_PERMS = ["users.view", "settings.manage"];

export function useDashboardNav(unread: number): { title: string; items: NavItem[] }[] {
  const can = useAuth((s) => s.can);
  useAuth((s) => s.user); // re-render when the user (and so their permissions) changes
  const groups: { title: string; items: NavItem[] }[] = [
    {
      title: "Overview",
      items: [
        { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
        { to: "/app/agents", label: "Agentic OS", icon: Bot },
        { to: "/app/messages", label: "Messages", icon: MessagesSquare, badge: unread },
      ],
    },
    {
      title: "Sales & Leasing",
      items: [
        { to: "/app/crm-dashboard", label: "CRM dashboard", icon: Gauge, perm: "crm.view" },
        { to: "/app/crm", label: "CRM", icon: Users, perm: "crm.view" },
        { to: "/app/listings", label: "My listings", icon: Building2, end: true },
        { to: "/app/listings/new", label: "List a property", icon: PlusSquare },
        { to: "/app/transactions", label: "Transactions", icon: FileSignature, perm: "crm.view" },
        { to: "/app/leasing", label: "Leasing", icon: KeyRound },
        { to: "/app/marketing", label: "Marketing", icon: Target, perm: "crm.view" },
      ],
    },
    {
      title: "Finance & Ads",
      items: [
        { to: "/app/accounting", label: "Accounting", icon: Calculator, perm: "accounting.view" },
        { to: "/app/ads", label: "Advertising", icon: Megaphone, perm: "ads.view" },
      ],
    },
    {
      title: "Delivery",
      items: [
        { to: "/app/pmo", label: "Projects (PMO)", icon: BriefcaseBusiness, perm: "projects.view" },
        { to: "/app/construction", label: "Construction", icon: HardHat },
        { to: "/app/maintenance", label: "Maintenance", icon: Wrench },
      ],
    },
    {
      title: "Administration",
      items: [
        { to: "/app/admin", label: "Users & roles", icon: ShieldCheck, end: true, perm: ADMIN_PERMS },
        { to: "/app/admin/base-data", label: "Base data", icon: Database, perm: "basedata.manage" },
        { to: "/app/admin/properties", label: "Property database", icon: Building, perm: "properties.manage" },
        { to: "/app/admin/gis-layers", label: "GIS layers", icon: Layers, perm: "gis.manage" },
        { to: "/app/profile", label: "Profile", icon: UserRound },
      ],
    },
  ];
  const allowed = (p?: string | string[]) => !p || (Array.isArray(p) ? p : [p]).some((x) => can(x));
  return groups.map((g) => ({ ...g, items: g.items.filter((i) => allowed(i.perm)) })).filter((g) => g.items.length);
}

function Sidebar({ collapsed, onToggle, unread }: { collapsed: boolean; onToggle?: () => void; unread: number }) {
  const groups = useDashboardNav(unread);
  return (
    <div className="flex h-full flex-col">
      <div className={cn("flex h-16 items-center border-b border-white/10 px-4", collapsed && "justify-center px-0")}>
        {collapsed ? (
          <Link to="/">
            <img src="/brand/logo-mark.webp" className="h-9" alt="Watan-e-Pak" />
          </Link>
        ) : (
          <Logo light />
        )}
      </div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {groups.map((g) => (
          <div key={g.title}>
            {!collapsed && <p className="mb-1.5 px-3 text-[10px] font-bold uppercase tracking-[.18em] text-white/40">{g.title}</p>}
            <div className="space-y-0.5">
              {g.items.map((it) => (
                <NavLink
                  key={it.to}
                  to={it.to}
                  end={it.end}
                  title={collapsed ? it.label : undefined}
                  className={({ isActive }) =>
                    cn(
                      "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                      collapsed && "justify-center px-0",
                      isActive ? "bg-white/10 text-white shadow-inner" : "text-white/65 hover:bg-white/5 hover:text-white",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="absolute inset-y-2 start-0 w-1 rounded-full bg-gold-400" />}
                      <it.icon className={cn("h-[18px] w-[18px] shrink-0", isActive && "text-gold-300")} />
                      {!collapsed && <span className="flex-1 truncate">{it.label}</span>}
                      {!!it.badge && <span className={cn("rounded-full bg-gold-400 px-1.5 text-[10px] font-bold text-brand-950", collapsed && "absolute end-1 top-1")}>{it.badge}</span>}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="space-y-1 border-t border-white/10 p-3">
        <Link to="/" className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-white/65 hover:bg-white/5 hover:text-white", collapsed && "justify-center px-0")}>
          <Globe className="h-[18px] w-[18px]" /> {!collapsed && "Public portal"}
        </Link>
        <Link to="/ai" className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-white/65 hover:bg-white/5 hover:text-white", collapsed && "justify-center px-0")}>
          <Building className="h-[18px] w-[18px]" /> {!collapsed && "AI Hub & MCP"}
        </Link>
        {onToggle && (
          <button onClick={onToggle} className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-white/65 hover:bg-white/5 hover:text-white", collapsed && "justify-center px-0")}>
            <ChevronsLeft className={cn("h-[18px] w-[18px] transition rtl:rotate-180", collapsed && "rotate-180 rtl:rotate-0")} /> {!collapsed && "Collapse"}
          </button>
        )}
      </div>
    </div>
  );
}

function NotificationBell({ userId }: { userId: string }) {
  const q = useApi<{ unread: number; notifications: { id: string; title: string; body: string; created_at: string; status: string; conversation_id?: string }[] }>(
    `/messaging/notifications/${userId}`,
    undefined,
    { refetchInterval: 30_000 },
  );
  const [open, setOpen] = useState(false);
  const n = q.data?.unread ?? 0;
  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)} className="btn btn-ghost btn-icon relative" aria-label="Notifications">
        <Bell className="h-5 w-5" />
        {n > 0 && <span className="absolute end-1.5 top-1.5 h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-white dark:ring-[#0a1a12]" />}
      </button>
      {open && (
        <div className="card absolute end-0 top-12 z-50 w-80 overflow-hidden">
          <div className="flex items-center justify-between border-b border-black/5 px-4 py-3 dark:border-white/10">
            <p className="font-semibold">Notifications</p>
            <Link to="/app/messages" onClick={() => setOpen(false)} className="text-xs font-semibold text-brand-700 dark:text-brand-300">
              Open inbox
            </Link>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {(q.data?.notifications ?? []).slice(0, 8).map((x) => (
              <Link key={x.id} to={x.conversation_id ? `/app/messages?c=${x.conversation_id}` : "/app/messages"} onClick={() => setOpen(false)} className="block border-b border-black/5 px-4 py-3 last:border-0 hover:bg-brand-50 dark:border-white/5 dark:hover:bg-white/5">
                <p className="text-sm font-semibold">{x.title}</p>
                <p className="line-clamp-2 text-xs text-ink-mute">{x.body}</p>
              </Link>
            ))}
            {!q.data?.notifications?.length && <p className="px-4 py-8 text-center text-sm text-ink-mute">You’re all caught up.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

export function DashboardLayout() {
  const { token, user, can } = useAuth();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobile, setMobile] = useState(false);
  const setPalette = usePalette((s) => s.setOpen);
  const unread = useApi<{ conversations_unread: number }>(user ? `/messaging/unread-summary/${user.id}` : null, undefined, { refetchInterval: 30_000 });

  useEffect(() => {
    setMobile(false);
  }, [loc.pathname]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [loc.pathname]);
  // Roles and permissions can change on the server (new permissions, role edits): sync them.
  const setUser = useAuth((s) => s.setUser);
  useEffect(() => {
    if (!token) return;
    get<{ user: typeof user }>("/auth/me", undefined, { noFallback: true })
      .then((r) => r?.user && setUser(r.user))
      .catch(() => undefined);
  }, [token, setUser]);

  if (!token || !user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;

  const u = unread.data?.conversations_unread ?? 0;
  return (
    <div className="flex min-h-screen bg-[#f3f6f4] dark:bg-[#06110b]">
      <aside className={cn("sticky top-0 hidden h-screen shrink-0 bg-brand-950 transition-all duration-300 lg:block", collapsed ? "w-20" : "w-64")}>
        <div className="pointer-events-none absolute inset-0 bg-mesh opacity-40" />
        <div className="relative h-full">
          <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} unread={u} />
        </div>
      </aside>
      <Drawer open={mobile} onClose={() => setMobile(false)} side="left" width="max-w-[280px]">
        <div className="h-full bg-brand-950">
          <Sidebar collapsed={false} unread={u} />
        </div>
      </Drawer>
      <div className="flex min-w-0 flex-1 flex-col overflow-x-clip">
        <OfflineBanner />
        <header className="glass sticky top-0 z-40 flex h-16 items-center gap-3 border-b border-black/5 px-4 sm:px-6 dark:border-white/10">
          <button className="btn btn-ghost btn-icon lg:hidden" onClick={() => setMobile(true)} aria-label="Menu">
            <Menu className="h-5 w-5" />
          </button>
          <button onClick={() => setPalette(true)} className="flex h-10 max-w-md flex-1 items-center gap-2 rounded-xl border border-black/10 bg-white/80 px-3.5 text-sm text-ink-mute transition hover:border-brand-300 dark:border-white/10 dark:bg-white/5">
            <Search className="h-4 w-4" /> <span className="truncate">Search leads, projects, properties…</span>
            <kbd className="kbd ms-auto hidden sm:inline">Ctrl K</kbd>
          </button>
          <div className="ms-auto flex items-center gap-1.5">
            <LangToggle className="hidden md:inline-flex" />
            <ThemeToggle />
            <NotificationBell userId={user.id} />
            {ADMIN_PERMS.some((p) => can(p)) && (
              <Link to="/app/admin" className="btn btn-ghost btn-icon hidden sm:inline-flex" aria-label="Settings">
                <Settings className="h-5 w-5" />
              </Link>
            )}
            <UserMenu />
          </div>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Suspense fallback={<div className="flex min-h-[50vh] items-center justify-center"><Spinner className="h-8 w-8" /></div>}>
          <ErrorBoundary resetKey={loc.pathname}>
            <Outlet />
          </ErrorBoundary>
        </Suspense>
        </main>
      </div>
    </div>
  );
}
