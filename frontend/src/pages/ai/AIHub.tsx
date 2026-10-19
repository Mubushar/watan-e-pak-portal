import { useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  Boxes,
  Brain,
  Building2,
  ClipboardList,
  Cpu,
  Database,
  FileSearch,
  Lock,
  PackageCheck,
  Plug,
  Route as RouteIcon,
  Search,
  Sparkles,
  Terminal,
  Workflow,
} from "lucide-react";
import type { AgentDef } from "@/types";
import { useApi } from "@/hooks/useApi";
import { apiUrl } from "@/lib/api";
import { num, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, ButtonLink, Card, CardBody, CardHeader, CopyButton, EmptyState, Input, QueryState, Section, Segmented, Skeleton } from "@/components/ui";
import { ChatPanel } from "@/components/ai/ChatPanel";
import { PropertyRow } from "@/components/property/PropertyCard";
import { AUTONOMY, CategoryIcon, HeroBackdrop, PriorityBadge } from "@/components/agents/AgentBits";
import { AgentCard } from "@/components/agents/AgentCard";

interface Overview {
  counts: { agents: number; products: number; autonomous: number; runs_recorded: number };
  by_autonomy: Record<string, number>;
}
interface Product {
  key: string;
  name: string;
  priority: string;
  category: string;
  agents: string[];
  agent_count: number;
}
interface RagHit {
  score: number;
  type: string;
  id: string;
  title?: string;
  name?: string;
  price?: number;
  city?: string;
  category?: string;
  marla?: number;
  bedrooms?: number | null;
}

const FLOW = [
  { icon: ClipboardList, title: "Brief", text: "You describe the goal in plain English or Urdu — budget, area, timeline." },
  { icon: Brain, title: "Plan", text: "The agent expands it into a workflow of typed steps." },
  { icon: Plug, title: "Tools via MCP", text: "Each step calls live portal tools — search, GIS, CRM, finance." },
  { icon: Lock, title: "Human gate", text: "Assist-level agents pause for your approval before acting." },
  { icon: PackageCheck, title: "Deliver", text: "Shortlists, drafts and actions land in your workspace with a full audit trail." },
];

function Hero({ initial }: { initial?: string }) {
  const ov = useApi<Overview>("/agents/overview");
  const c = ov.data?.counts;
  return (
    <section className="relative isolate overflow-hidden text-white">
      <HeroBackdrop />
      <div className="container grid gap-10 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center lg:py-16">
        <div>
          <motion.span initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="chip bg-white/10 text-gold-200 ring-1 ring-white/15">
            <Sparkles className="h-3.5 w-3.5" /> Arz-e-Pak Agentic OS
          </motion.span>
          <motion.h1 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="mt-5 font-display text-4xl font-bold leading-[1.08] sm:text-5xl xl:text-6xl">
            AI agents that <span className="bg-gold-gradient bg-clip-text text-transparent">actually do</span> real estate.
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mt-5 max-w-xl text-lg text-white/75">
            Brief an agent, watch it plan, call live portal tools over MCP and stop for your sign-off — from finding a home to pricing, leasing and investment screening.
          </motion.p>
          <div className="mt-7 flex flex-wrap gap-3">
            <a href="#catalog" className="btn btn-gold btn-lg">
              <Bot className="h-5 w-5" /> Explore agents
            </a>
            <ButtonLink to="/ai/mcp" variant="outline" size="lg" className="!border-white/30 !bg-white/5 !text-white hover:!bg-white/15" icon={<Terminal className="h-5 w-5" />}>
              MCP console
            </ButtonLink>
          </div>
          <div className="mt-9 grid max-w-lg grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Agents", value: c?.agents },
              { label: "Products", value: c?.products },
              { label: "Autonomous", value: c?.autonomous },
              { label: "Runs logged", value: c?.runs_recorded },
            ].map((s, i) => (
              <motion.div key={s.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.05 }} className="glass-dark rounded-2xl px-3 py-3">
                <p className="font-display text-2xl font-bold text-gold-200">{s.value ?? "–"}</p>
                <p className="text-[11px] uppercase tracking-wider text-white/60">{s.label}</p>
              </motion.div>
            ))}
          </div>
        </div>
        <motion.div initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay: 0.15, type: "spring", bounce: 0.2 }} className="relative">
          <div aria-hidden className="absolute -inset-1 rounded-[28px] bg-gradient-to-br from-gold-300/60 via-white/10 to-brand-400/40 blur-sm" />
          <div className="relative flex h-[600px] max-h-[80vh] flex-col overflow-hidden rounded-3xl bg-white text-ink shadow-2xl dark:bg-[#0d1f16] dark:text-slate-100">
            <div className="flex items-center gap-3 border-b border-black/5 bg-brand-50/70 px-4 py-3 dark:border-white/10 dark:bg-white/5">
              <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-brand-gradient text-white">
                <Bot className="h-5 w-5" />
                <span className="absolute -end-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-white dark:ring-[#0d1f16]" />
              </span>
              <div className="min-w-0">
                <p className="font-display font-semibold">Arz-e-Pak AI</p>
                <p className="text-xs text-ink-mute">RAG over live listings, societies & market data</p>
              </div>
              <Badge tone="gold" className="ms-auto hidden sm:inline-flex">
                OpenAI-compatible
              </Badge>
            </div>
            <ChatPanel key={initial ?? ""} initial={initial} className="min-h-0 flex-1" />
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function Products() {
  const q = useApi<{ count: number; products: Product[] }>("/agents/products");
  return (
    <Section eyebrow="Roadmap products" title="Eight products, one agent fabric" subtitle="Each product bundles specialist agents that hand work to one another.">
      <QueryState
        q={q}
        skeleton={
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-44" />
            ))}
          </div>
        }
      >
        {(d) => (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {d.products.map((p, i) => (
              <motion.div
                key={p.key}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.04 }}
                className={cn("card card-hover relative overflow-hidden p-5", p.priority === "P0" && "ring-1 ring-gold-300/60 dark:ring-gold-500/30")}
              >
                {p.priority === "P0" && <div aria-hidden className="absolute -end-12 -top-12 h-28 w-28 rounded-full bg-gold-300/25 blur-2xl" />}
                <div className="flex items-start justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
                    <CategoryIcon category={p.category} />
                  </span>
                  <PriorityBadge priority={p.priority} />
                </div>
                <h3 className="mt-3 font-display font-semibold leading-snug text-ink dark:text-white">{p.name}</h3>
                <p className="mt-1 text-xs text-ink-mute">
                  {titleCase(p.category)} · <b className="text-brand-700 dark:text-brand-300">{p.agent_count}</b> agent{p.agent_count === 1 ? "" : "s"}
                </p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {p.agents.map((a) => (
                    <Link key={a} to={`/ai/agents/${a}`} className="chip bg-black/5 text-[10px] text-ink-soft transition hover:bg-brand-700 hover:text-white dark:bg-white/10 dark:text-slate-300">
                      {titleCase(a.replace(/_agent$/, ""))}
                    </Link>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </QueryState>
    </Section>
  );
}

function HowItWorks() {
  return (
    <section className="relative overflow-hidden bg-brand-950 py-14 text-white sm:py-16">
      <div aria-hidden className="absolute inset-0 bg-mesh opacity-60" />
      <div className="container relative">
        <p className="section-eyebrow !text-gold-300">How it works</p>
        <h2 className="mt-2 font-display text-3xl font-bold sm:text-4xl">From brief to delivery — with you in control</h2>
        <div className="relative mt-10 grid gap-6 md:grid-cols-5">
          <div aria-hidden className="absolute start-[10%] end-[10%] top-7 hidden h-0.5 overflow-hidden rounded-full bg-white/10 md:block">
            <motion.div className="h-full w-1/3 bg-gradient-to-r from-transparent via-gold-300 to-transparent" animate={{ x: ["-100%", "300%"] }} transition={{ duration: 3.2, repeat: Infinity, ease: "linear" }} />
          </div>
          {FLOW.map((f, i) => (
            <motion.div key={f.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.1 }} className="relative flex gap-4 md:flex-col md:items-center md:text-center">
              <span className={cn("relative z-10 flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ring-4 ring-brand-950", i === 3 ? "bg-gold-gradient text-brand-950 shadow-glow" : "bg-brand-gradient text-white")}>
                <f.icon className="h-6 w-6" />
                <span className="absolute -end-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-white text-[10px] font-bold text-brand-900">{i + 1}</span>
              </span>
              <div>
                <p className="font-display text-lg font-semibold">{f.title}</p>
                <p className="mt-1 text-sm text-white/65">{f.text}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Catalogue() {
  const q = useApi<{ count: number; agents: AgentDef[]; categories: string[] }>("/agents/catalog");
  const [cat, setCat] = useState("all");
  const [auto, setAuto] = useState("all");
  const [search, setSearch] = useState("");
  const list = useMemo(
    () =>
      (q.data?.agents ?? []).filter(
        (a) => (cat === "all" || a.category === cat) && (auto === "all" || a.autonomy === auto) && (!search.trim() || `${a.name} ${a.summary} ${a.tools.join(" ")}`.toLowerCase().includes(search.toLowerCase())),
      ),
    [q.data, cat, auto, search],
  );
  return (
    <Section
      eyebrow="Agent catalogue"
      title="Pick an agent, give it a brief"
      subtitle="Product agents and specialist sub-agents. Gold locks mark workflows that pause for a human."
    >
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="no-scrollbar -mx-4 flex gap-1.5 overflow-x-auto px-4 lg:mx-0 lg:flex-wrap lg:px-0">
          {["all", ...(q.data?.categories ?? [])].map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCat(c)}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition",
                cat === c ? "bg-brand-700 text-white shadow-soft" : "bg-white text-ink-soft ring-1 ring-black/5 hover:bg-brand-50 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10",
              )}
            >
              {c !== "all" && <CategoryIcon category={c} className="h-3.5 w-3.5" />}
              {c === "all" ? "All" : titleCase(c)}
              <span className="text-[10px] opacity-70">{c === "all" ? q.data?.count : q.data?.agents.filter((a) => a.category === c).length}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-3 sm:flex-row lg:ms-auto">
          <Segmented
            size="sm"
            value={auto}
            onChange={setAuto}
            options={[{ value: "all", label: "Any" }, ...Object.entries(AUTONOMY).map(([k, v]) => ({ value: k, label: v.label, icon: v.icon }))]}
          />
          <Input icon={<Search className="h-4 w-4" />} placeholder="Search agents or tools" value={search} onChange={(e) => setSearch(e.target.value)} className="!py-2 sm:w-56" />
        </div>
      </div>
      <QueryState
        q={q}
        skeleton={
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-60" />
            ))}
          </div>
        }
      >
        {() =>
          list.length ? (
            <motion.div layout className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              <AnimatePresence mode="popLayout">
                {list.map((a, i) => (
                  <AgentCard key={a.key} a={a} i={i} />
                ))}
              </AnimatePresence>
            </motion.div>
          ) : (
            <EmptyState title="No agents match these filters" action={<Button variant="soft" size="sm" onClick={() => { setCat("all"); setAuto("all"); setSearch(""); }}>Reset filters</Button>} />
          )
        }
      </QueryState>
    </Section>
  );
}

function Developers() {
  const models = useApi<{ data: { id: string; owned_by: string }[] }>("/v1/models");
  const model = models.data?.data?.[0]?.id ?? "portal-realestate-rag";
  const base = `${location.origin}${apiUrl("/v1")}`;
  const curl = `curl ${base}/chat/completions \\\n  -H "Content-Type: application/json" \\\n  -d '{"model":"${model}","messages":[{"role":"user","content":"10 marla house in Lahore"}]}'`;
  return (
    <Section eyebrow="For developers" title="Plug the portal into any AI stack">
      <div className="grid gap-5 lg:grid-cols-2">
        <Link to="/ai/mcp" className="card card-hover group relative overflow-hidden p-6">
          <div aria-hidden className="absolute -end-16 -top-16 h-48 w-48 rounded-full bg-brand-400/20 blur-3xl transition group-hover:bg-gold-300/30" />
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-soft">
            <Cpu className="h-6 w-6" />
          </span>
          <h3 className="mt-4 font-display text-xl font-bold text-ink dark:text-white">MCP console</h3>
          <p className="mt-2 text-sm text-ink-mute dark:text-slate-400">Browse ~600 tools, resources and prompts on the portal’s Model Context Protocol server, call them live and copy a config for Claude Desktop or Cursor.</p>
          <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 dark:text-brand-300">
            Open console <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1 rtl:rotate-180" />
          </span>
        </Link>
        <Card className="relative overflow-hidden">
          <CardHeader
            title="OpenAI-compatible facade"
            subtitle="/v1/models · /v1/chat/completions"
            icon={<Boxes className="h-4 w-4" />}
            action={
              <Badge tone={models.error ? "red" : "green"} icon={<span className={cn("h-1.5 w-1.5 rounded-full", models.error ? "bg-red-500" : "bg-emerald-500")} />}>
                {models.error ? "offline" : "online"}
              </Badge>
            }
          />
          <CardBody className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {models.isLoading ? (
                <Skeleton className="h-7 w-48" />
              ) : (
                models.data?.data?.map((m) => (
                  <span key={m.id} className="chip bg-brand-50 font-mono text-xs text-brand-800 dark:bg-white/5 dark:text-brand-200">
                    <Database className="h-3 w-3" /> {m.id}
                  </span>
                ))
              )}
            </div>
            <div className="relative">
              <pre className="no-scrollbar overflow-x-auto rounded-xl bg-[#07140d] p-4 pe-20 font-mono text-[11px] leading-5 text-emerald-200">{curl}</pre>
              <CopyButton text={curl} className="absolute end-2 top-2 !text-emerald-200 hover:!bg-white/10" />
            </div>
          </CardBody>
        </Card>
      </div>
    </Section>
  );
}

function RagSearch() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const q = useApi<{ count: number; results: RagHit[] }>(query ? "/rag/search" : null, { query, top_k: 10 });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setQuery(input.trim());
  };
  const max = Math.max(1, ...(q.data?.results.map((r) => r.score) ?? [1]));
  return (
    <Section eyebrow="Retrieval" title="Search the knowledge base" subtitle="The same retrieval index the assistant and agents ground their answers on.">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <div className="flex-1">
          <Input icon={<FileSearch className="h-4 w-4" />} placeholder="e.g. corner house in DHA Lahore, smart city societies, commercial shop" value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
        <Button type="submit" icon={<Search className="h-4 w-4" />} disabled={!input.trim()} loading={q.isFetching}>
          Search
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {["1 kanal house Lahore", "Islamabad societies", "apartment under 5 crore"].map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setInput(s);
              setQuery(s);
            }}
            className="chip bg-black/5 text-ink-soft hover:bg-brand-50 dark:bg-white/5 dark:text-slate-300"
          >
            {s}
          </button>
        ))}
      </div>
      <div className="mt-6">
        {!query ? null : (
          <QueryState q={q} skeleton={<Skeleton className="h-48" />}>
            {(d) =>
              d.results.length ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {d.results.map((r, i) => (
                    <motion.div key={r.type + r.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="card p-2">
                      {r.type === "property" ? (
                        <PropertyRow
                          p={{ id: r.id, title: r.title ?? "Listing", price: r.price ?? 0, category: r.category ?? "property", city_name: r.city, marla_area: r.marla, bedrooms: r.bedrooms ?? undefined }}
                          extra={<ScorePill v={r.score / max} />}
                        />
                      ) : (
                        <Link to={r.type === "scheme" ? `/schemes?q=${encodeURIComponent(r.name ?? "")}` : `/properties?q=${encodeURIComponent(r.name ?? r.title ?? "")}`} className="flex items-center gap-3 rounded-xl p-2 transition hover:bg-brand-50 dark:hover:bg-white/5">
                          <span className="flex h-14 w-20 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-white">
                            {r.type === "scheme" ? <Building2 className="h-6 w-6" /> : <RouteIcon className="h-6 w-6" />}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-semibold">{r.name ?? r.title}</p>
                            <p className="text-xs text-ink-mute">
                              <Badge tone="blue">{r.type}</Badge> {r.city}
                            </p>
                          </div>
                          <ScorePill v={r.score / max} />
                        </Link>
                      )}
                    </motion.div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No matches" hint="Try a city, society or property type." />
              )
            }
          </QueryState>
        )}
      </div>
    </Section>
  );
}

function ScorePill({ v }: { v: number }) {
  return (
    <span className="flex w-14 shrink-0 flex-col items-end gap-1">
      <span className="text-[10px] font-semibold text-ink-mute">{num(v * 100, 0)}%</span>
      <span className="h-1.5 w-full overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
        <span className="block h-full rounded-full bg-gold-gradient" style={{ width: `${v * 100}%` }} />
      </span>
    </span>
  );
}

export default function AIHub() {
  const [params] = useSearchParams();
  const initial = params.get("q") ?? undefined;
  return (
    <div>
      <Hero initial={initial} />
      <Products />
      <HowItWorks />
      <div id="catalog" className="scroll-mt-16">
        <Catalogue />
      </div>
      <div className="bg-brand-50/40 dark:bg-white/[0.02]">
        <Developers />
      </div>
      <RagSearch />
      <div className="container pb-12">
        <Card className="relative isolate overflow-hidden border-0 p-8 text-white">
          <HeroBackdrop />
          <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
            <Workflow className="h-10 w-10 text-gold-300" />
            <div className="flex-1">
              <p className="font-display text-xl font-bold">Running a brokerage?</p>
              <p className="text-sm text-white/70">Agent Ops in your dashboard shows the morning brief, every run and every approval waiting on you.</p>
            </div>
            <ButtonLink to="/app/agents" variant="gold" icon={<ArrowRight className="h-4 w-4 rtl:rotate-180" />}>
              Open Agent Ops
            </ButtonLink>
          </div>
        </Card>
      </div>
    </div>
  );
}
