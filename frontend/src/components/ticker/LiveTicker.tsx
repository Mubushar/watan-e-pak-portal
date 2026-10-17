/**
 * Live market + news ticker. Polls `/news` and per-city `/portal/market-trends`
 * every minute and scrolls them as a seamless marquee (pause on hover/click).
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import { Pause, Play, Radio, TrendingDown, TrendingUp } from "lucide-react";
import type { City, NewsItem } from "@/types";
import { get } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { pkrShort } from "@/lib/format";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";

interface Trend {
  pricing: { price_per_marla: number; avg_price: number };
  forecast: { base_cagr: number; composite_index: number; index_band: string };
  news: { net_sentiment: string; momentum: number };
}

export function LiveTicker({ className }: { className?: string }) {
  const paused = usePrefs((s) => s.tickerPaused);
  const setPaused = usePrefs((s) => s.setTickerPaused);
  const [hover, setHover] = useState(false);
  const news = useApi<{ news: NewsItem[] }>("/news", { limit: 14 }, { refetchInterval: 60_000 });
  const cities = useApi<{ cities: City[] }>("/cities", undefined, { staleTime: 10 * 60_000 });
  const trends = useQueries({
    queries: (cities.data?.cities ?? []).map((c) => ({
      queryKey: ["/portal/market-trends", { city: c.name }],
      queryFn: () => get<Trend>("/portal/market-trends", { city: c.name }),
      refetchInterval: 60_000,
      staleTime: 30_000,
    })),
  });

  const items = useMemo(() => {
    const out: { key: string; node: React.ReactNode }[] = [];
    (cities.data?.cities ?? []).forEach((c, i) => {
      const t = trends[i]?.data;
      if (!t?.pricing?.price_per_marla) return;
      const g = t.forecast?.base_cagr ?? 0;
      const up = g >= 0;
      out.push({
        key: `c-${c.id}`,
        node: (
          <Link to={`/cities/${encodeURIComponent(c.name)}`} className="inline-flex items-center gap-2 hover:text-gold-200">
            <span className="font-bold text-white">{c.name.toUpperCase()}</span>
            <span className="text-white/80">{pkrShort(t.pricing.price_per_marla)}/marla</span>
            <span className={cn("inline-flex items-center gap-0.5 font-semibold", up ? "text-emerald-300" : "text-red-300")}>
              {up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {(g * 100).toFixed(1)}%
            </span>
            <span className="rounded bg-white/10 px-1.5 text-[10px] font-semibold uppercase text-gold-200">idx {Math.round(t.forecast.composite_index)}</span>
          </Link>
        ),
      });
    });
    for (const n of news.data?.news ?? []) {
      const tone = n.sentiment === "positive" ? "text-emerald-300" : n.sentiment === "negative" ? "text-red-300" : "text-slate-300";
      out.push({
        key: `n-${n.id}`,
        node: (
          <Link to="/news" className="inline-flex items-center gap-2 hover:text-gold-200">
            <span className={cn("h-1.5 w-1.5 rounded-full", n.sentiment === "positive" ? "bg-emerald-400" : n.sentiment === "negative" ? "bg-red-400" : "bg-slate-400")} />
            <span className="text-white/90">{n.title}</span>
            <span className="text-white/50">· {n.source}</span>
            <span className={cn("font-semibold", tone)}>
              {n.impact_score > 0 ? "+" : ""}
              {Math.round(n.impact_score)}
            </span>
          </Link>
        ),
      });
    }
    return out;
  }, [cities.data, trends, news.data]);

  if (!items.length) return <div className={cn("h-9 bg-brand-950", className)} />;
  const duration = Math.max(40, items.length * 7);

  return (
    <div dir="ltr" className={cn("relative flex h-9 items-center overflow-hidden bg-brand-950 text-[13px] text-white", (paused || hover) && "paused", className)}>
      <div className="z-10 flex h-full shrink-0 items-center gap-2 bg-gradient-to-r from-red-700 to-red-600 px-3 font-bold uppercase tracking-wider">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
        </span>
        <Radio className="hidden h-3.5 w-3.5 sm:block" /> Live
      </div>
      <div className="ticker-mask relative h-full flex-1 overflow-hidden" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
        <div className="absolute flex h-full w-max animate-marquee items-center gap-10 ps-6" style={{ ["--marquee-duration" as string]: `${duration}s` }}>
          {[...items, ...items].map((it, i) => (
            <span key={`${it.key}-${i}`} className="shrink-0">
              {it.node}
            </span>
          ))}
        </div>
      </div>
      <button onClick={() => setPaused(!paused)} className="z-10 flex h-full shrink-0 items-center px-3 text-white/70 hover:text-white" aria-label={paused ? "Play ticker" : "Pause ticker"}>
        {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
