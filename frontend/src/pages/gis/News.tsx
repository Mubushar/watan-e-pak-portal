import { useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, Building, Clock, Flame, Landmark, Megaphone, Newspaper, Radio, RotateCcw, Search, ShieldCheck, TrendingDown, TrendingUp, Minus, Tag, Microscope, Banknote } from "lucide-react";
import type { City, NewsItem } from "@/types";
import { useApi } from "@/hooks/useApi";
import { pct, timeAgo, titleCase } from "@/lib/format";
import { HERO, themedImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { Badge, Card, CardBody, CardHeader, Carousel, Donut, EmptyState, ErrorState, Input, PageHeader, QueryState, Skeleton } from "@/components/ui";
import { AdSlot } from "@/components/ads/AdSlot";
import { ChipRow, FilterChip, ImpactMeter, SENTIMENT_COLOR, sentimentTone } from "@/components/gis/kit";
import type { NewsChannel, NewsImpact } from "@/components/gis/types";

const CHANNEL_ICON: Record<string, typeof Newspaper> = {
  news: Newspaper,
  regulator: ShieldCheck,
  government: Landmark,
  research: Microscope,
  developer: Building,
  bank: Banknote,
};
const SENT_ICON = { positive: TrendingUp, negative: TrendingDown, neutral: Minus } as const;
const SENTIMENTS = ["positive", "neutral", "negative"] as const;

export default function News() {
  const [category, setCategory] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [channel, setChannel] = useState("");
  const [city, setCity] = useState("");
  const [q, setQ] = useState("");

  const newsQ = useApi<{ count: number; news: NewsItem[] }>("/news", { category, sentiment, channel_type: channel, city, limit: 100 });
  const allQ = useApi<{ count: number; news: NewsItem[] }>("/news", { limit: 200 });
  const impactQ = useApi<NewsImpact>("/news/impact", { city });
  const channelsQ = useApi<{ channels: NewsChannel[] }>("/news/channels");
  const citiesQ = useApi<{ cities: City[] }>("/cities");

  const categories = useMemo(() => [...new Set((allQ.data?.news ?? []).map((n) => n.category))].sort(), [allQ.data]);
  const channelTypes = useMemo(() => [...new Set((channelsQ.data?.channels ?? []).map((c) => c.channel_type))].sort(), [channelsQ.data]);
  const catCount = useMemo(() => {
    const m: Record<string, number> = {};
    (allQ.data?.news ?? []).forEach((n) => (m[n.category] = (m[n.category] ?? 0) + 1));
    return m;
  }, [allQ.data]);

  const items = useMemo(() => {
    const s = q.trim().toLowerCase();
    const list = newsQ.data?.news ?? [];
    return s ? list.filter((n) => [n.title, n.summary, n.source, ...(n.tags ?? [])].some((x) => x?.toLowerCase().includes(s))) : list;
  }, [newsQ.data, q]);
  const featured = useMemo(() => [...(allQ.data?.news ?? [])].sort((a, b) => Math.abs(b.impact_score) - Math.abs(a.impact_score)).slice(0, 5), [allQ.data]);
  const cityName = useMemo(() => new Map((citiesQ.data?.cities ?? []).map((c) => [c.id, c.name])), [citiesQ.data]);

  const anyFilter = category || sentiment || channel || city || q;
  const reset = () => {
    setCategory("");
    setSentiment("");
    setChannel("");
    setCity("");
    setQ("");
  };

  return (
    <div className="pb-16">
      <PageHeader
        image={HERO.landscape}
        eyebrow="News & market impact"
        title={
          <>
            Headlines that <span className="text-gradient">move prices</span>
          </>
        }
        subtitle="Every story is scored for sentiment and price impact (−100 to +100) and feeds straight into our market forecasts."
        crumbs={[{ label: "Home", to: "/" }, { label: "News" }]}
      >
        {impactQ.data && (
          <div className="mt-6 flex flex-wrap gap-3">
            {[
              ["Stories tracked", impactQ.data.summary.count],
              ["Avg impact", `${impactQ.data.summary.avg_impact > 0 ? "+" : ""}${impactQ.data.summary.avg_impact}`],
              ["Net sentiment", titleCase(impactQ.data.summary.net_sentiment)],
              ["Outlook momentum", pct(impactQ.data.summary.momentum)],
            ].map(([l, v]) => (
              <div key={String(l)} className="glass-dark rounded-2xl px-4 py-2.5">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gold-200">{l}</p>
                <p className="font-display text-xl font-bold">{v}</p>
              </div>
            ))}
          </div>
        )}
      </PageHeader>

      {/* ------------------------------------------------------------ featured */}
      <section className="container -mt-10 relative z-10">
        {allQ.isLoading ? (
          <Skeleton className="h-72 rounded-3xl" />
        ) : featured.length ? (
          <Carousel autoplay delay={6000} slideClass="basis-full lg:basis-1/2" gap="gap-5" arrows={false}>
            {featured.map((n) => (
              <FeaturedSlide key={n.id} n={n} city={n.city_id ? cityName.get(n.city_id) : undefined} />
            ))}
          </Carousel>
        ) : null}
      </section>

      <div className="container mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          {/* ---------------------------------------------------------- filters */}
          <Card className="mb-6">
            <CardBody className="space-y-3 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="flex-1">
                  <Input icon={<Search className="h-4 w-4" />} placeholder="Search headlines, sources, tags…" value={q} onChange={(e) => setQ(e.target.value)} />
                </div>
                {anyFilter && (
                  <button onClick={reset} className="btn btn-ghost btn-sm shrink-0">
                    <RotateCcw className="h-3.5 w-3.5" /> Reset filters
                  </button>
                )}
              </div>
              <FilterRow label="Category">
                <FilterChip active={!category} onClick={() => setCategory("")}>
                  All
                </FilterChip>
                {categories.map((c) => (
                  <FilterChip key={c} active={category === c} onClick={() => setCategory(category === c ? "" : c)} count={catCount[c]}>
                    {titleCase(c)}
                  </FilterChip>
                ))}
              </FilterRow>
              <FilterRow label="Sentiment">
                <FilterChip active={!sentiment} onClick={() => setSentiment("")}>
                  Any
                </FilterChip>
                {SENTIMENTS.map((s) => (
                  <FilterChip key={s} active={sentiment === s} onClick={() => setSentiment(sentiment === s ? "" : s)} color={SENTIMENT_COLOR[s]}>
                    {titleCase(s)}
                  </FilterChip>
                ))}
              </FilterRow>
              <FilterRow label="Channel">
                <FilterChip active={!channel} onClick={() => setChannel("")}>
                  All
                </FilterChip>
                {channelTypes.map((c) => (
                  <FilterChip key={c} active={channel === c} onClick={() => setChannel(channel === c ? "" : c)}>
                    {titleCase(c)}
                  </FilterChip>
                ))}
              </FilterRow>
              <FilterRow label="City">
                <FilterChip active={!city} onClick={() => setCity("")}>
                  Nationwide
                </FilterChip>
                {(citiesQ.data?.cities ?? []).map((c) => (
                  <FilterChip key={c.id} active={city === c.name} onClick={() => setCity(city === c.name ? "" : c.name)}>
                    {c.name}
                  </FilterChip>
                ))}
              </FilterRow>
            </CardBody>
          </Card>

          {/* ---------------------------------------------------------- grid */}
          {newsQ.isLoading ? (
            <div className="grid gap-5 sm:grid-cols-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-64" />
              ))}
            </div>
          ) : newsQ.error ? (
            <ErrorState error={newsQ.error} onRetry={() => newsQ.refetch()} />
          ) : !items.length ? (
            <EmptyState title="No stories match these filters" icon={<Newspaper className="h-6 w-6" />} action={<button onClick={reset} className="btn btn-outline btn-sm">Clear filters</button>} />
          ) : (
            <>
              <p className="mb-3 text-sm text-ink-mute">
                Showing <b className="text-ink dark:text-white">{items.length}</b> {items.length === 1 ? "story" : "stories"}
              </p>
              <motion.div layout className="grid gap-5 sm:grid-cols-2">
                <AnimatePresence initial={false}>
                  {items.flatMap((n, i) => {
                    const cells = [<NewsCard key={n.id} n={n} i={i} city={n.city_id ? cityName.get(n.city_id) : undefined} />];
                    if (i === 3)
                      cells.push(
                        <motion.div key="ad-infeed" layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                          <AdSlot slot="infeed" />
                        </motion.div>,
                      );
                    return cells;
                  })}
                </AnimatePresence>
              </motion.div>
              {items.length <= 3 && (
                <div className="mt-5">
                  <AdSlot slot="infeed" layout="strip" />
                </div>
              )}
            </>
          )}
        </div>

        {/* ---------------------------------------------------------- sidebar */}
        <aside className="space-y-6 lg:sticky lg:top-[96px] lg:self-start">
          <Card>
            <CardHeader title="Sentiment mix" subtitle={city ? `${city}, last 120 days` : "Nationwide, last 120 days"} icon={<Flame className="h-5 w-5" />} />
            <CardBody>
              <QueryState q={impactQ} skeleton={<Skeleton className="h-56" />}>
                {(im) => {
                  const data = SENTIMENTS.map((s) => ({ name: titleCase(s), value: im.summary[s], color: SENTIMENT_COLOR[s] })).filter((d) => d.value > 0);
                  return (
                    <>
                      {data.length ? (
                        <Donut
                          data={data}
                          height={190}
                          format={(v) => `${v} stories`}
                          center={
                            <>
                              <span className={cn("font-display text-2xl font-bold", im.summary.avg_impact >= 0 ? "text-emerald-600" : "text-red-600")}>
                                {im.summary.avg_impact > 0 ? "+" : ""}
                                {im.summary.avg_impact}
                              </span>
                              <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-mute">avg impact</span>
                            </>
                          }
                        />
                      ) : (
                        <p className="py-8 text-center text-sm text-ink-mute">No stories in this window.</p>
                      )}
                      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                        {SENTIMENTS.map((s) => (
                          <div key={s} className="rounded-xl bg-black/[.03] py-2 dark:bg-white/5">
                            <p className="font-display text-lg font-bold" style={{ color: SENTIMENT_COLOR[s] }}>
                              {im.summary[s]}
                            </p>
                            <p className="text-[10px] font-semibold capitalize text-ink-mute">{s}</p>
                          </div>
                        ))}
                      </div>
                      <div className="mt-4 space-y-2">
                        {Object.entries(im.by_category)
                          .sort((a, b) => b[1].avg_impact - a[1].avg_impact)
                          .map(([k, v]) => (
                            <button key={k} onClick={() => setCategory(category === k ? "" : k)} className={cn("block w-full rounded-lg px-2 py-1 text-start transition hover:bg-brand-50 dark:hover:bg-white/5", category === k && "bg-brand-50 dark:bg-white/5")}>
                              <div className="mb-0.5 flex justify-between text-xs">
                                <span className="font-semibold text-ink-soft dark:text-slate-300">{titleCase(k)}</span>
                                <span className="text-ink-mute">{v.count}</span>
                              </div>
                              <ImpactMeter value={v.avg_impact} />
                            </button>
                          ))}
                      </div>
                    </>
                  );
                }}
              </QueryState>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Sources & channels" subtitle="Who is moving the market" icon={<Radio className="h-5 w-5" />} />
            <CardBody className="p-2">
              <QueryState q={channelsQ} skeleton={<Skeleton className="m-3 h-60" />}>
                {(d) => (
                  <ul className="divide-y divide-black/5 dark:divide-white/5">
                    {d.channels.map((c) => {
                      const Icon = CHANNEL_ICON[c.channel_type] ?? Megaphone;
                      return (
                        <li key={c.source}>
                          <button onClick={() => setChannel(channel === c.channel_type ? "" : c.channel_type)} className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-start transition hover:bg-brand-50 dark:hover:bg-white/5">
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
                              <Icon className="h-4 w-4" />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-semibold text-ink dark:text-white">{c.source}</span>
                              <span className="block text-[11px] capitalize text-ink-mute">
                                {c.channel_type} · {c.count} {c.count === 1 ? "story" : "stories"}
                              </span>
                            </span>
                            <span className={cn("text-sm font-bold tabular-nums", c.avg_impact > 0 ? "text-emerald-600" : c.avg_impact < 0 ? "text-red-600" : "text-ink-mute")}>
                              {c.avg_impact > 0 ? "+" : ""}
                              {Math.round(c.avg_impact)}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </QueryState>
            </CardBody>
          </Card>

          <AdSlot slot="sidebar" />
        </aside>
      </div>
    </div>
  );
}

function FilterRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="hidden w-20 shrink-0 text-[11px] font-bold uppercase tracking-wider text-ink-mute sm:block">{label}</span>
      <ChipRow className="flex-1">{children}</ChipRow>
    </div>
  );
}

function FeaturedSlide({ n, city }: { n: NewsItem; city?: string }) {
  const Icon = SENT_ICON[n.sentiment] ?? Minus;
  return (
    <article className="group relative h-72 overflow-hidden rounded-3xl bg-brand-950 text-white shadow-soft sm:h-80">
      <img src={themedImage(n.id, n.category === "development" || n.category === "infrastructure" ? "tower" : n.tags?.join(" "))} alt="" className="absolute inset-0 h-full w-full object-cover opacity-45 transition-transform duration-[1.5s] group-hover:scale-105" />
      <div className={cn("absolute inset-0 bg-gradient-to-t", n.sentiment === "negative" ? "from-red-950 via-brand-950/80 to-brand-950/30" : "from-brand-950 via-brand-950/75 to-brand-900/20")} />
      <div className="relative flex h-full flex-col p-6 sm:p-7">
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip bg-gold-gradient text-brand-950">
            <Flame className="h-3 w-3" /> Top impact
          </span>
          <span className="chip bg-white/15 text-white backdrop-blur">{titleCase(n.category)}</span>
          <span className={cn("chip text-white backdrop-blur", n.sentiment === "positive" ? "bg-emerald-500/30" : n.sentiment === "negative" ? "bg-red-500/40" : "bg-white/15")}>
            <Icon className="h-3 w-3" /> {n.sentiment}
          </span>
        </div>
        <h3 className="mt-auto line-clamp-3 font-display text-xl font-bold leading-snug sm:text-2xl">{n.title}</h3>
        {n.summary && <p className="mt-2 line-clamp-2 text-sm text-white/75">{n.summary}</p>}
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-white/70">
          <span className="font-semibold text-white">{n.source}</span>
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" /> {timeAgo(n.published_at)}
          </span>
          {city && <span>{city}</span>}
          <span className="ms-auto flex w-40 items-center">
            <ImpactMeter value={n.impact_score} className="w-full [&_span:last-child]:text-white" />
          </span>
        </div>
      </div>
    </article>
  );
}

function NewsCard({ n, i, city }: { n: NewsItem; i: number; city?: string }) {
  const Icon = SENT_ICON[n.sentiment] ?? Minus;
  const ChIcon = CHANNEL_ICON[n.channel_type] ?? Megaphone;
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.35, delay: Math.min(i, 8) * 0.04 }}
      className="card card-hover group relative flex flex-col overflow-hidden"
    >
      <span className="absolute inset-y-0 start-0 w-1" style={{ background: SENTIMENT_COLOR[n.sentiment] }} />
      <div className="flex flex-1 flex-col p-5 ps-6">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="gray">{titleCase(n.category)}</Badge>
          <Badge tone={sentimentTone(n.sentiment)} icon={<Icon className="h-3 w-3" />}>
            {n.sentiment}
          </Badge>
          {city && <Badge tone="blue">{city}</Badge>}
        </div>
        <h3 className="mt-3 font-display text-base font-semibold leading-snug text-ink transition group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300">{n.title}</h3>
        {n.summary && <p className="mt-1.5 line-clamp-3 text-sm text-ink-mute dark:text-slate-400">{n.summary}</p>}
        <div className="mt-4">
          <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-ink-mute">Price impact</p>
          <ImpactMeter value={n.impact_score} />
        </div>
        {!!n.tags?.length && (
          <div className="mt-3 flex flex-wrap gap-1">
            {n.tags.map((t) => (
              <span key={t} className="inline-flex items-center gap-0.5 rounded-full bg-black/[.04] px-2 py-0.5 text-[10px] font-medium text-ink-soft dark:bg-white/10 dark:text-slate-300">
                <Tag className="h-2.5 w-2.5" /> {t}
              </span>
            ))}
          </div>
        )}
        <div className="flex-1" />
        <div className="mt-4 flex items-center gap-2 border-t border-black/5 pt-3 text-xs text-ink-mute dark:border-white/10">
          <ChIcon className="h-3.5 w-3.5 text-gold-600" />
          <span className="truncate font-semibold text-ink-soft dark:text-slate-300">{n.source}</span>
          <span>·</span>
          <span className="shrink-0">{timeAgo(n.published_at)}</span>
          {n.url && (
            <a href={n.url} target="_blank" rel="noreferrer" className="ms-auto inline-flex shrink-0 items-center gap-0.5 font-semibold text-brand-700 hover:underline dark:text-brand-300">
              Read <ArrowUpRight className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>
    </motion.article>
  );
}
