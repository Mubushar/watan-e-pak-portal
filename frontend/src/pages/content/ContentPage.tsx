import { useMemo, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Award, Bot, Building2, CheckCircle2, ChevronRight, Cpu, Flag, Handshake, HelpCircle, Landmark, Milestone, Rocket, Search, Sparkles, Star, TrendingUp } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { date, titleCase } from "@/lib/format";
import { HERO, themedImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { ButtonLink, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { Accordion, apiErr, stagger } from "@/components/collab/kit";

interface Page {
  id: string;
  key: string;
  title: string;
  category: string;
  subtitle?: string | null;
  summary?: string | null;
  body: string[];
  highlights: { label: string; value: string; sub?: string }[];
  bullets: string[];
  faqs: { question: string; answer: string }[];
  tags: string[];
  updated_at?: string;
  [k: string]: unknown;
}
interface NavItem {
  key: string;
  label: string;
  category: string;
}
interface HistoryItem {
  id: string;
  year: number;
  month?: number;
  title: string;
  description: string;
  kind: string;
  featured?: boolean;
}

const HERO_FOR: Record<string, string> = {
  about: HERO.panorama,
  mission: HERO.landscape,
  services: HERO.villa,
  "why-us": HERO.panorama,
  "how-it-works": HERO.aiMap,
  agentic: HERO.aiMap,
  tools: HERO.aiMap,
  messaging: HERO.aiMap,
  commercial: HERO.aiMap,
  team: HERO.landscape,
  careers: HERO.landscape,
};
const KIND_ICON: Record<string, ReactNode> = {
  founding: <Flag className="h-4 w-4" />,
  milestone: <Milestone className="h-4 w-4" />,
  expansion: <Building2 className="h-4 w-4" />,
  technology: <Cpu className="h-4 w-4" />,
  award: <Award className="h-4 w-4" />,
  partnership: <Handshake className="h-4 w-4" />,
  financial: <Landmark className="h-4 w-4" />,
  recognition: <Star className="h-4 w-4" />,
};
const NAV_GROUPS: Record<string, string> = { about: "Company", mission: "Company", team: "Company", careers: "Company", "why-us": "Company", services: "Services", help: "Help", faq: "Help", platform: "Platform", legal: "Legal", policy: "Legal" };

export default function ContentPage() {
  const { key = "about" } = useParams();
  const q = useApi<Page>(`/content/pages/${key}`);
  const nav = useApi<{ items: NavItem[] }>("/content/navigation", undefined, { staleTime: 30 * 60_000 });
  const history = useApi<{ count: number; items: HistoryItem[] }>(key === "about" ? "/content/history" : null);
  const p = q.data;
  const err = apiErr(p);
  const image = HERO_FOR[key] ?? themedImage(key, p?.title ?? key);

  const groups = useMemo(() => {
    const g: Record<string, NavItem[]> = {};
    (nav.data?.items ?? []).forEach((n) => (g[NAV_GROUPS[n.category] ?? "Services"] ??= []).push(n));
    return g;
  }, [nav.data]);

  // any other array-of-object fields the backend may add later (sections / items)
  const extras = useMemo(() => {
    if (!p || err) return [] as [string, Record<string, unknown>[]][];
    return Object.entries(p).filter(
      ([k, v]) => !["body", "highlights", "bullets", "faqs", "tags"].includes(k) && Array.isArray(v) && v.length && typeof v[0] === "object",
    ) as [string, Record<string, unknown>[]][];
  }, [p, err]);

  if (q.isLoading)
    return (
      <div>
        <Skeleton className="h-72 rounded-none" />
        <div className="container grid gap-8 py-10 lg:grid-cols-[1fr_280px]">
          <div className="space-y-4">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  if (q.error) return <div className="container py-16"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (err || !p)
    return (
      <div className="container py-16">
        <EmptyState title="Page not found" hint={`There is no page called “${key}”.`} icon={<Search className="h-6 w-6" />} action={<ButtonLink to="/pages/about">Go to About</ButtonLink>} />
      </div>
    );

  return (
    <div>
      <PageHeader image={image} eyebrow={titleCase(p.category)} title={p.title} subtitle={p.subtitle ?? undefined} crumbs={[{ label: "Home", to: "/" }, { label: p.title }]}>
        {!!p.highlights.length && (
          <div className="mt-8 hidden flex-wrap gap-3 sm:flex">
            {p.highlights.slice(0, 4).map((h) => (
              <span key={h.label} className="glass-dark rounded-2xl px-4 py-2 text-sm">
                <b className="text-gold-300">{h.value}</b> <span className="text-white/75">{h.label}</span>
              </span>
            ))}
          </div>
        )}
      </PageHeader>

      <div className="container grid gap-10 py-10 lg:grid-cols-[minmax(0,1fr)_280px] lg:py-14">
        <article className="min-w-0 space-y-10">
          {p.summary && (
            <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="border-s-4 border-gold-400 ps-5 font-display text-xl font-medium leading-relaxed text-brand-900 sm:text-2xl dark:text-white">
              {p.summary}
            </motion.p>
          )}

          {!!p.body.length && (
            <div className="prose-portal max-w-3xl text-[17px]">
              {p.body.map((para, i) => (
                <motion.p key={i} initial={{ opacity: 0, y: 8 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }}>
                  {para}
                </motion.p>
              ))}
            </div>
          )}

          {!!p.highlights.length && (
            <motion.div variants={stagger.container} initial="hidden" whileInView="show" viewport={{ once: true }} className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
              {p.highlights.map((h, i) => (
                <motion.div
                  key={h.label}
                  variants={stagger.item}
                  className={cn("group relative overflow-hidden rounded-3xl p-5 transition hover:-translate-y-1", i === 0 ? "bg-brand-gradient text-white shadow-soft" : "card hover:shadow-glow")}
                >
                  <div className={cn("pointer-events-none absolute -end-8 -top-8 h-24 w-24 rounded-full blur-2xl", i === 0 ? "bg-gold-400/30" : "bg-brand-500/10")} />
                  <p className={cn("font-display text-3xl font-bold", i === 0 ? "text-gold-300" : "text-gradient")}>{h.value}</p>
                  <p className={cn("mt-1 text-sm font-semibold", i === 0 ? "text-white" : "text-ink dark:text-white")}>{h.label}</p>
                  {h.sub && <p className={cn("mt-0.5 text-xs", i === 0 ? "text-white/70" : "text-ink-mute")}>{h.sub}</p>}
                </motion.div>
              ))}
            </motion.div>
          )}

          {!!p.bullets.length && (
            <section>
              <h2 className="section-title !text-2xl">{key === "careers" ? "Open roles" : "What you get"}</h2>
              <motion.ul variants={stagger.container} initial="hidden" whileInView="show" viewport={{ once: true }} className="mt-5 grid gap-3 sm:grid-cols-2">
                {p.bullets.map((b) => (
                  <motion.li key={b} variants={stagger.item} className="card flex items-start gap-3 p-4 transition hover:border-brand-300 hover:shadow-soft">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
                      {key === "careers" ? <Rocket className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
                    </span>
                    <span className="text-sm font-medium text-ink-soft dark:text-slate-200">{b}</span>
                  </motion.li>
                ))}
              </motion.ul>
            </section>
          )}

          {extras.map(([name, items]) => (
            <section key={name}>
              <h2 className="section-title !text-2xl">{titleCase(name)}</h2>
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                {items.map((it, i) => (
                  <div key={i} className="card p-5">
                    <p className="font-display font-semibold">{String(it.title ?? it.name ?? it.label ?? `Item ${i + 1}`)}</p>
                    {(it.description ?? it.body ?? it.summary) ? <p className="mt-1 text-sm text-ink-mute">{String(it.description ?? it.body ?? it.summary)}</p> : null}
                  </div>
                ))}
              </div>
            </section>
          ))}

          {!!p.faqs.length && (
            <section>
              <h2 className="section-title flex items-center gap-2 !text-2xl">
                <HelpCircle className="h-6 w-6 text-gold-500" /> Frequently asked
              </h2>
              <Accordion className="mt-5" items={p.faqs.map((f) => ({ title: f.question, content: <p className="leading-relaxed">{f.answer}</p> }))} />
            </section>
          )}

          {key === "about" && (
            <section>
              <p className="section-eyebrow">Since 2005</p>
              <h2 className="section-title mt-2 !text-2xl">Our journey</h2>
              {history.isLoading ? (
                <Skeleton className="mt-5 h-72" />
              ) : (
                <ol className="relative mt-8 space-y-6 before:absolute before:inset-y-0 before:start-[19px] before:w-0.5 before:bg-gradient-to-b before:from-brand-600 before:via-gold-400 before:to-brand-300 sm:before:start-1/2 sm:before:-translate-x-1/2">
                  {[...(history.data?.items ?? [])]
                    .sort((a, b) => a.year - b.year || (a.month ?? 0) - (b.month ?? 0))
                    .map((h, i) => (
                      <motion.li
                        key={h.id}
                        initial={{ opacity: 0, y: 14 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-40px" }}
                        className={cn("relative ps-14 sm:w-1/2 sm:ps-0", i % 2 ? "sm:ms-auto sm:ps-10" : "sm:pe-10 sm:text-end")}
                      >
                        <span
                          className={cn(
                            "absolute start-0 top-1 flex h-10 w-10 items-center justify-center rounded-full text-white shadow-soft ring-4 ring-white dark:ring-[#0b1a12]",
                            h.featured ? "bg-gold-gradient !text-brand-950" : "bg-brand-gradient",
                            i % 2 ? "sm:-start-5" : "sm:-end-5 sm:start-auto",
                          )}
                        >
                          {KIND_ICON[h.kind] ?? <Sparkles className="h-4 w-4" />}
                        </span>
                        <div className="card p-5 transition hover:shadow-glow">
                          <p className="font-display text-2xl font-bold text-gradient">{h.year}</p>
                          <p className="mt-1 font-semibold text-ink dark:text-white">{h.title}</p>
                          <p className="mt-1 text-sm text-ink-mute">{h.description}</p>
                          <span className="mt-2 inline-block rounded-full bg-black/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-mute dark:bg-white/10">{h.kind}</span>
                        </div>
                      </motion.li>
                    ))}
                </ol>
              )}
            </section>
          )}

          {!!p.tags.length && (
            <div className="flex flex-wrap items-center gap-2 border-t border-black/5 pt-6 text-xs dark:border-white/10">
              {p.tags.map((t) => (
                <span key={t} className="rounded-full bg-brand-50 px-3 py-1 font-semibold text-brand-700 dark:bg-white/5 dark:text-brand-200">
                  #{t}
                </span>
              ))}
              {p.updated_at && <span className="ms-auto text-ink-mute">Updated {date(p.updated_at)}</span>}
            </div>
          )}
        </article>

        {/* side nav */}
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="card overflow-hidden">
            <p className="border-b border-black/5 px-5 py-3 font-display font-semibold dark:border-white/10">Explore Watan-e-Pak</p>
            <nav className="max-h-[60vh] space-y-4 overflow-y-auto p-3">
              {nav.isLoading && <Skeleton className="h-60" />}
              {Object.entries(groups).map(([g, items]) => (
                <div key={g}>
                  <p className="px-2 pb-1 text-[10px] font-bold uppercase tracking-[.18em] text-ink-mute">{g}</p>
                  {items.map((n) => (
                    <Link
                      key={n.key}
                      to={`/pages/${n.key}`}
                      className={cn(
                        "group flex items-center justify-between rounded-xl px-3 py-2 text-sm transition",
                        n.key === key ? "bg-brand-700 font-semibold text-white shadow-soft" : "text-ink-soft hover:bg-brand-50 hover:text-brand-800 dark:text-slate-300 dark:hover:bg-white/5",
                      )}
                    >
                      {n.label}
                      <ChevronRight className={cn("h-4 w-4 transition rtl:rotate-180", n.key === key ? "text-gold-300" : "opacity-0 group-hover:opacity-100")} />
                    </Link>
                  ))}
                </div>
              ))}
              <Link to="/stories" className="flex items-center justify-between rounded-xl px-3 py-2 text-sm text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/5">
                Success stories <Star className="h-4 w-4 text-gold-500" />
              </Link>
              <Link to="/pricing" className="flex items-center justify-between rounded-xl px-3 py-2 text-sm text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/5">
                Pricing <TrendingUp className="h-4 w-4 text-brand-600" />
              </Link>
            </nav>
          </div>
        </aside>
      </div>

      {/* CTA */}
      <section className="container pb-16">
        <div className="relative overflow-hidden rounded-[2rem] bg-brand-gradient p-8 text-white shadow-soft sm:p-12">
          <div className="pointer-events-none absolute -end-20 -top-20 h-72 w-72 rounded-full bg-gold-400/30 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-24 start-10 h-60 w-60 rounded-full bg-emerald-300/20 blur-3xl" />
          <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="section-eyebrow !text-gold-300">Ready when you are</p>
              <h2 className="mt-2 font-display text-3xl font-bold sm:text-4xl">Find your next property — or ask our AI.</h2>
              <p className="mt-2 max-w-xl text-white/75">Verified listings across Lahore, Karachi, Islamabad and Rawalpindi, with instant valuations and forecasts.</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <ButtonLink to="/properties" variant="gold" size="lg">
                Browse properties <ArrowRight className="h-4 w-4 rtl:rotate-180" />
              </ButtonLink>
              <ButtonLink to="/ai" size="lg" className="bg-white/10 text-white hover:bg-white/20" icon={<Bot className="h-4 w-4" />}>
                Ask the AI
              </ButtonLink>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
