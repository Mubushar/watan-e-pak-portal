import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Bot, Briefcase, Building2, CalendarDays, Flag, LineChart, MapPin, MessageSquareQuote, Quote, Sparkles, Star, Trophy } from "lucide-react";
import type { Story } from "@/types";
import { useApi } from "@/hooks/useApi";
import { date, titleCase } from "@/lib/format";
import { HERO, themedImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { Avatar, ButtonLink, Carousel, EmptyState, PageHeader, QueryState, Skeleton } from "@/components/ui";
import { Chip, stagger } from "@/components/collab/kit";

type StoryX = Story & { tags?: string[]; image_url?: string | null };

const TYPE_ICON: Record<string, ReactNode> = {
  case_study: <Briefcase className="h-3.5 w-3.5" />,
  testimonial: <MessageSquareQuote className="h-3.5 w-3.5" />,
  project: <Building2 className="h-3.5 w-3.5" />,
  investment: <LineChart className="h-3.5 w-3.5" />,
  milestone: <Flag className="h-3.5 w-3.5" />,
};

function Stars({ rating, light }: { rating?: number | null; light?: boolean }) {
  if (rating === undefined || rating === null) return null;
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((i) => {
        const fill = Math.max(0, Math.min(1, rating - (i - 1)));
        return (
          <span key={i} className="relative inline-block h-4 w-4">
            <Star className={cn("absolute inset-0 h-4 w-4", light ? "text-white/30" : "text-black/15 dark:text-white/20")} />
            <span className="absolute inset-0 overflow-hidden" style={{ width: `${fill * 100}%` }}>
              <Star className="h-4 w-4 fill-gold-400 text-gold-400" />
            </span>
          </span>
        );
      })}
      <span className={cn("ms-1 text-xs font-bold", light ? "text-white" : "text-ink dark:text-white")}>{rating.toFixed(1)}</span>
    </span>
  );
}

export default function Stories() {
  const q = useApi<{ count: number; types: string[]; stories: StoryX[] }>("/content/stories");
  const [type, setType] = useState("all");
  const [open, setOpen] = useState<StoryX | null>(null);
  const stories = q.data?.stories ?? [];
  const featured = stories.filter((s) => s.featured);
  const shown = type === "all" ? stories : stories.filter((s) => s.story_type === type);
  const rated = stories.filter((s) => typeof s.rating === "number");
  const avg = rated.length ? rated.reduce((a, s) => a + (s.rating ?? 0), 0) / rated.length : 0;
  const allMetrics = useMemo(() => stories.flatMap((s) => (s.metrics ?? []).map((m) => ({ ...m, story: s.title }))).slice(0, 8), [stories]);
  const highlights = useMemo(() => [...new Set(stories.flatMap((s) => s.highlights ?? []))].slice(0, 16), [stories]);

  return (
    <div>
      <PageHeader
        image={HERO.villa}
        eyebrow="Success stories"
        title={
          <>
            Real families. Real returns. <span className="text-gradient">Real Pakistan.</span>
          </>
        }
        subtitle="Buyers, investors, developers and landlords on what changed when they moved with Arz-e-Pak."
        crumbs={[{ label: "Home", to: "/" }, { label: "Stories" }]}
      >
        {q.data && (
          <div className="mt-8 flex flex-wrap gap-3">
            <span className="glass-dark inline-flex items-center gap-2 rounded-2xl px-4 py-2 text-sm">
              <Trophy className="h-4 w-4 text-gold-300" /> <b>{q.data.count}</b> stories
            </span>
            {avg > 0 && (
              <span className="glass-dark inline-flex items-center gap-2 rounded-2xl px-4 py-2 text-sm">
                <Stars rating={avg} light /> average rating
              </span>
            )}
          </div>
        )}
      </PageHeader>

      {/* featured */}
      <section className="container py-12">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <p className="section-eyebrow">Featured</p>
            <h2 className="section-title mt-1">Stories worth telling</h2>
          </div>
        </div>
        {q.isLoading ? (
          <Skeleton className="h-[420px] rounded-[2rem]" />
        ) : featured.length ? (
          <Carousel autoplay delay={6500} slideClass="basis-full" arrowsPosition="top">
            {featured.map((s) => (
              <div key={s.id} className="relative isolate min-h-[420px] overflow-hidden rounded-[2rem] text-white shadow-soft">
                <img src={s.image_url ?? themedImage(s.id, `${s.title} ${s.location ?? ""}`)} alt="" className="absolute inset-0 -z-10 h-full w-full object-cover" />
                <div className="absolute inset-0 -z-10 bg-gradient-to-r from-brand-950 via-brand-950/85 to-brand-900/30 rtl:bg-gradient-to-l" />
                <div className="grid h-full gap-8 p-7 sm:p-12 lg:grid-cols-[1.4fr_1fr]">
                  <div className="flex flex-col">
                    <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold uppercase tracking-wider backdrop-blur">
                      {TYPE_ICON[s.story_type]} {titleCase(s.story_type)}
                    </span>
                    <Quote className="mt-6 h-10 w-10 text-gold-300" />
                    <blockquote className="mt-3 font-display text-2xl font-semibold leading-snug sm:text-3xl">“{s.quote ?? s.title}”</blockquote>
                    <div className="mt-auto flex items-center gap-3 pt-8">
                      <Avatar name={s.client_name} size={48} className="ring-2 ring-gold-300" />
                      <div>
                        <p className="font-semibold">{s.client_name}</p>
                        <p className="text-sm text-white/70">
                          {s.client_role}
                          {s.location ? ` · ${s.location}` : ""}
                        </p>
                      </div>
                      <div className="ms-auto">
                        <Stars rating={s.rating} light />
                      </div>
                    </div>
                  </div>
                  {!!s.metrics?.length && (
                    <div className="grid content-center gap-3 sm:grid-cols-3 lg:grid-cols-1">
                      {s.metrics.slice(0, 3).map((m) => (
                        <div key={m.label} className="glass-dark rounded-2xl px-5 py-4">
                          <p className="font-display text-2xl font-bold text-gold-300">{m.value}</p>
                          <p className="text-xs text-white/70">{m.label}</p>
                        </div>
                      ))}
                      <button onClick={() => setOpen(s)} className="btn btn-gold w-fit">
                        Read the story <ArrowRight className="h-4 w-4 rtl:rotate-180" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </Carousel>
        ) : null}
      </section>

      {/* metrics */}
      {allMetrics.length > 0 && (
        <section className="bg-brand-50/50 py-12 dark:bg-white/[.02]">
          <div className="container">
            <p className="section-eyebrow">By the numbers</p>
            <motion.div variants={stagger.container} initial="hidden" whileInView="show" viewport={{ once: true }} className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-4">
              {allMetrics.map((m, i) => (
                <motion.div key={i} variants={stagger.item} className="card p-5 transition hover:-translate-y-1 hover:shadow-glow">
                  <p className="font-display text-2xl font-bold text-gradient sm:text-3xl">{m.value}</p>
                  <p className="mt-1 text-sm font-semibold">{m.label}</p>
                  <p className="mt-0.5 line-clamp-1 text-xs text-ink-mute">{m.story}</p>
                </motion.div>
              ))}
            </motion.div>
            {highlights.length > 0 && (
              <div className="mt-6 flex flex-wrap gap-2">
                {highlights.map((h) => (
                  <span key={h} className="inline-flex items-center gap-1 rounded-full border border-gold-300/60 bg-white px-3 py-1 text-xs font-semibold text-gold-700 dark:border-gold-500/30 dark:bg-white/5 dark:text-gold-300">
                    <Sparkles className="h-3 w-3" /> {h}
                  </span>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* grid */}
      <section className="container py-12">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="section-eyebrow">All stories</p>
            <h2 className="section-title mt-1">In their words</h2>
          </div>
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            <Chip active={type === "all"} onClick={() => setType("all")}>
              All {stories.length > 0 && <span className="opacity-70">{stories.length}</span>}
            </Chip>
            {(q.data?.types ?? []).map((t) => {
              const n = stories.filter((s) => s.story_type === t).length;
              return (
                <Chip key={t} active={type === t} onClick={() => setType(t)} className="shrink-0">
                  {TYPE_ICON[t]} {titleCase(t)} <span className="opacity-70">{n}</span>
                </Chip>
              );
            })}
          </div>
        </div>
        <QueryState
          q={q}
          skeleton={
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-72" />
              ))}
            </div>
          }
        >
          {() =>
            shown.length === 0 ? (
              <EmptyState title="No stories of this type yet" />
            ) : (
              <motion.div layout className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                <AnimatePresence mode="popLayout">
                  {shown.map((s) => (
                    <motion.button
                      layout
                      key={s.id}
                      initial={{ opacity: 0, scale: 0.96 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.96 }}
                      onClick={() => setOpen(s)}
                      className="card group flex flex-col overflow-hidden text-start transition hover:-translate-y-1 hover:shadow-glow"
                    >
                      <div className="relative h-36 overflow-hidden">
                        <img src={s.image_url ?? themedImage(s.id, `${s.title} ${s.location ?? ""}`)} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" loading="lazy" />
                        <div className="absolute inset-0 bg-gradient-to-t from-brand-950/80 to-transparent" />
                        <span className="absolute start-3 top-3 inline-flex items-center gap-1 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-semibold text-brand-800 backdrop-blur dark:bg-brand-950/80 dark:text-brand-100">
                          {TYPE_ICON[s.story_type]} {titleCase(s.story_type)}
                        </span>
                        <p className="absolute inset-x-4 bottom-3 line-clamp-2 font-display font-semibold text-white">{s.title}</p>
                      </div>
                      <div className="flex flex-1 flex-col p-5">
                        {s.quote && (
                          <p className="relative line-clamp-4 ps-6 text-sm italic text-ink-soft dark:text-slate-300">
                            <Quote className="absolute start-0 top-0 h-4 w-4 text-gold-500" />
                            {s.quote}
                          </p>
                        )}
                        {!!s.metrics?.length && (
                          <div className="mt-4 grid grid-cols-2 gap-2">
                            {s.metrics.slice(0, 2).map((m) => (
                              <div key={m.label} className="rounded-xl bg-brand-50/60 px-3 py-2 dark:bg-white/5">
                                <p className="font-display font-bold text-brand-700 dark:text-gold-300">{m.value}</p>
                                <p className="truncate text-[11px] text-ink-mute">{m.label}</p>
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="mt-auto flex items-center gap-3 pt-5">
                          <Avatar name={s.client_name} size={36} />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-semibold">{s.client_name}</p>
                            <p className="truncate text-xs text-ink-mute">{s.client_role}</p>
                          </div>
                          <Stars rating={s.rating} />
                        </div>
                      </div>
                    </motion.button>
                  ))}
                </AnimatePresence>
              </motion.div>
            )
          }
        </QueryState>
      </section>

      {/* CTA */}
      <section className="container pb-16">
        <div className="relative overflow-hidden rounded-[2rem] bg-brand-gradient p-8 text-center text-white shadow-soft sm:p-12">
          <div className="pointer-events-none absolute -top-24 start-1/2 h-72 w-72 -translate-x-1/2 rounded-full bg-gold-400/30 blur-3xl" />
          <h2 className="relative font-display text-3xl font-bold sm:text-4xl">Your story starts with the right property.</h2>
          <div className="relative mt-6 flex flex-wrap justify-center gap-3">
            <ButtonLink to="/properties" variant="gold" size="lg">
              Explore listings <ArrowRight className="h-4 w-4 rtl:rotate-180" />
            </ButtonLink>
            <ButtonLink to="/ai" size="lg" className="bg-white/10 text-white hover:bg-white/20" icon={<Bot className="h-4 w-4" />}>
              Talk to our AI
            </ButtonLink>
          </div>
        </div>
      </section>

      <StoryModal story={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function StoryModal({ story, onClose }: { story: StoryX | null; onClose: () => void }) {
  useEffect(() => {
    if (!story) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [story, onClose]);
  return (
    <AnimatePresence>
      {story && (
        <motion.div className="fixed inset-0 z-[100] flex items-end justify-center sm:items-center sm:p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-brand-950/60 backdrop-blur-sm" onClick={onClose} />
          <motion.article
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 30, opacity: 0 }}
            className="card relative max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-b-none sm:rounded-3xl"
            role="dialog"
            aria-modal="true"
          >
            <div className="relative h-48">
              <img src={story.image_url ?? themedImage(story.id, `${story.title} ${story.location ?? ""}`)} alt="" className="h-full w-full object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-brand-950 to-brand-950/10" />
              <button onClick={onClose} className="absolute end-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur hover:bg-black/60" aria-label="Close">
                ✕
              </button>
              <div className="absolute inset-x-6 bottom-4 text-white">
                <p className="text-xs font-semibold uppercase tracking-wider text-gold-300">{titleCase(story.story_type)}</p>
                <h3 className="font-display text-2xl font-bold leading-tight">{story.title}</h3>
              </div>
            </div>
            <div className="space-y-5 p-6">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-mute">
                {story.location && (
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="h-4 w-4" /> {story.location}
                  </span>
                )}
                {story.date && (
                  <span className="inline-flex items-center gap-1">
                    <CalendarDays className="h-4 w-4" /> {date(story.date)}
                  </span>
                )}
                <Stars rating={story.rating} />
              </div>
              {story.quote && <blockquote className="border-s-4 border-gold-400 ps-4 font-display text-lg italic">“{story.quote}”</blockquote>}
              <div className="prose-portal">
                {(story.narrative ?? []).map((n, i) => (
                  <p key={i}>{n}</p>
                ))}
              </div>
              {!!story.metrics?.length && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {story.metrics.map((m) => (
                    <div key={m.label} className="rounded-2xl bg-brand-50/70 p-3 dark:bg-white/5">
                      <p className="font-display text-xl font-bold text-gradient">{m.value}</p>
                      <p className="text-xs text-ink-mute">{m.label}</p>
                    </div>
                  ))}
                </div>
              )}
              {!!story.highlights?.length && (
                <div className="flex flex-wrap gap-2">
                  {story.highlights.map((h) => (
                    <span key={h} className="rounded-full bg-gold-50 px-3 py-1 text-xs font-semibold text-gold-700 dark:bg-gold-500/10 dark:text-gold-300">
                      {h}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-3 border-t border-black/5 pt-4 dark:border-white/10">
                <Avatar name={story.client_name} size={40} />
                <div>
                  <p className="font-semibold">{story.client_name}</p>
                  <p className="text-xs text-ink-mute">{story.client_role}</p>
                </div>
              </div>
            </div>
          </motion.article>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
