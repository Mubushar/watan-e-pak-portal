/** ⌘K / Ctrl+K federated search over `/portal/search` plus quick navigation. */
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Building2, CornerDownLeft, FileText, Home, Landmark, MapPin, Newspaper, Search, Sparkles, Users, Wrench } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { create } from "zustand";

export const usePalette = create<{ open: boolean; setOpen: (v: boolean) => void }>((set) => ({ open: false, setOpen: (open) => set({ open }) }));

type Hit = { group: string; label: string; sub?: string; to: string; icon: React.ReactNode };

const NAV: Hit[] = [
  { group: "Go to", label: "Browse properties", to: "/properties", icon: <Home className="h-4 w-4" /> },
  { group: "Go to", label: "Map explorer (GIS)", to: "/map", icon: <MapPin className="h-4 w-4" /> },
  { group: "Go to", label: "Infrastructure mega projects", to: "/infrastructure", icon: <MapPin className="h-4 w-4" /> },
  { group: "Go to", label: "AI Hub & agents", to: "/ai", icon: <Sparkles className="h-4 w-4" /> },
  { group: "Go to", label: "Tools & calculators", to: "/tools", icon: <Wrench className="h-4 w-4" /> },
  { group: "Go to", label: "Market insights", to: "/insights", icon: <Landmark className="h-4 w-4" /> },
  { group: "Go to", label: "News", to: "/news", icon: <Newspaper className="h-4 w-4" /> },
  { group: "Go to", label: "Dashboard", to: "/app", icon: <Building2 className="h-4 w-4" /> },
  { group: "Go to", label: "CRM", to: "/app/crm", icon: <Users className="h-4 w-4" /> },
];

function useDebounced<T>(v: T, ms = 220) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

export function CommandPalette() {
  const { open, setOpen } = usePalette();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const nav = useNavigate();
  const dq = useDebounced(q.trim());
  const search = useApi<{ results: Record<string, any[]> }>(dq.length >= 2 ? "/portal/search" : null, { query: dq, limit: 6 });

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!usePalette.getState().open);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [setOpen]);

  useEffect(() => {
    if (!open) setQ("");
  }, [open]);

  const hits = useMemo<Hit[]>(() => {
    const r = search.data?.results ?? {};
    const out: Hit[] = [];
    const add = (key: string, group: string, map: (x: any) => Omit<Hit, "group">) => (r[key] ?? []).forEach((x) => out.push({ group, ...map(x) }));
    add("properties", "Properties", (x) => ({ label: x.title, sub: `${x.city ?? ""} · ${x.category ?? ""}`, to: `/properties/${x.id}`, icon: <Home className="h-4 w-4" /> }));
    add("cities", "Cities", (x) => ({ label: x.name, sub: x.state, to: `/cities/${encodeURIComponent(x.name)}`, icon: <MapPin className="h-4 w-4" /> }));
    add("schemes", "Schemes", (x) => ({ label: x.name, sub: x.city, to: `/schemes?scheme=${x.id}`, icon: <Building2 className="h-4 w-4" /> }));
    add("big_projects", "Projects", (x) => ({ label: x.name, sub: x.city, to: `/projects`, icon: <Building2 className="h-4 w-4" /> }));
    add("news", "News", (x) => ({ label: x.title, sub: x.source, to: `/news`, icon: <Newspaper className="h-4 w-4" /> }));
    add("agents", "Agents", (x) => ({ label: x.name, sub: x.region, to: `/app/crm`, icon: <Users className="h-4 w-4" /> }));
    add("pages", "Pages", (x) => ({ label: x.title, to: `/pages/${x.key}`, icon: <FileText className="h-4 w-4" /> }));
    add("tools", "Tools", (x) => ({ label: x.name, to: `/tools/${x.key}`, icon: <Wrench className="h-4 w-4" /> }));
    add("ai_agents", "AI agents", (x) => ({ label: x.name, to: `/ai/agents/${x.key ?? x.id}`, icon: <Sparkles className="h-4 w-4" /> }));
    add("pmo_projects", "PMO", (x) => ({ label: x.name, sub: x.code, to: `/app/pmo/${x.id}`, icon: <Building2 className="h-4 w-4" /> }));
    add("transactions", "Transactions", (x) => ({ label: x.title ?? x.code, sub: x.code, to: `/app/transactions`, icon: <FileText className="h-4 w-4" /> }));
    if (!dq) return NAV;
    out.push({ group: "Ask AI", label: `Ask the assistant: “${dq}”`, to: `/ai?q=${encodeURIComponent(dq)}`, icon: <Sparkles className="h-4 w-4" /> });
    return out;
  }, [search.data, dq]);

  useEffect(() => setSel(0), [hits.length]);

  const go = (h?: Hit) => {
    if (!h) return;
    setOpen(false);
    nav(h.to);
  };

  const groups = hits.reduce<Record<string, Hit[]>>((acc, h) => ((acc[h.group] ??= []).push(h), acc), {});
  let idx = -1;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[120] flex items-start justify-center p-4 pt-[12vh]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-brand-950/50 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <motion.div initial={{ y: -10, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ y: -10, opacity: 0 }} className="card relative w-full max-w-2xl overflow-hidden">
            <div className="flex items-center gap-3 border-b border-black/5 px-4 dark:border-white/10">
              <Search className="h-5 w-5 text-brand-600" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setSel((s) => Math.min(hits.length - 1, s + 1));
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setSel((s) => Math.max(0, s - 1));
                  } else if (e.key === "Enter") go(hits[sel]);
                  else if (e.key === "Escape") setOpen(false);
                }}
                placeholder="Search cities, schemes, properties, news, tools…"
                className="h-14 flex-1 bg-transparent text-base outline-none placeholder:text-ink-mute"
              />
              <kbd className="kbd">ESC</kbd>
            </div>
            <div className="max-h-[60vh] overflow-y-auto p-2">
              {search.isFetching && <p className="px-3 py-2 text-xs text-ink-mute">Searching…</p>}
              {Object.entries(groups).map(([g, list]) => (
                <div key={g} className="mb-1">
                  <p className="px-3 pb-1 pt-2 text-[11px] font-bold uppercase tracking-wider text-ink-mute">{g}</p>
                  {list.map((h) => {
                    idx++;
                    const i = idx;
                    return (
                      <button
                        key={`${g}-${h.to}-${h.label}`}
                        onMouseEnter={() => setSel(i)}
                        onClick={() => go(h)}
                        className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left", i === sel ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/5")}
                      >
                        <span className={cn("flex h-8 w-8 items-center justify-center rounded-lg", i === sel ? "bg-white/15" : "bg-brand-50 text-brand-700 dark:bg-white/10 dark:text-brand-200")}>{h.icon}</span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold">{h.label}</span>
                          {h.sub && <span className={cn("block truncate text-xs", i === sel ? "text-white/70" : "text-ink-mute")}>{h.sub}</span>}
                        </span>
                        {i === sel ? <CornerDownLeft className="h-4 w-4" /> : <ArrowRight className="h-4 w-4 opacity-30" />}
                      </button>
                    );
                  })}
                </div>
              ))}
              {dq && !search.isFetching && hits.length <= 1 && <p className="px-3 py-6 text-center text-sm text-ink-mute">No direct matches — try asking the AI.</p>}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
