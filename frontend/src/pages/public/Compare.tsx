import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import { Check, GitCompareArrows, Plus, Sparkles, Trash2, Trophy, X } from "lucide-react";
import type { Property, PropertyList } from "@/types";
import { get } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { area, num, pct, pkr, pkrShort, titleCase } from "@/lib/format";
import { coverImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { MAX_COMPARE, usePrefs } from "@/store/prefs";
import { Button, EmptyState, PageHeader, ScoreRing, Skeleton } from "@/components/ui";

interface Investment {
  price_per_sqft: number;
  delta_vs_city_pct: number;
  verdict: string;
  estimated_monthly_rent: number;
  estimated_gross_yield_pct: number;
}
interface GisScore {
  composite_score: number;
  grade: string;
  dimensions: Record<string, number>;
  commute_minutes: number;
}

type Row = { label: string; get: (p: Property, inv?: Investment, gis?: GisScore) => number | string | null | undefined; best?: "min" | "max"; fmt?: (v: number) => string };

const ROWS: Row[] = [
  { label: "Price", get: (p) => p.price, best: "min", fmt: (v) => pkrShort(v) },
  { label: "Price / sqft", get: (p, inv) => inv?.price_per_sqft ?? p.price_per_sqft, best: "min", fmt: (v) => pkr(v) },
  { label: "vs city average", get: (_, inv) => inv?.delta_vs_city_pct, best: "min", fmt: (v) => `${v > 0 ? "+" : ""}${v}%` },
  { label: "Area", get: (p) => area(p) },
  { label: "Total sqft", get: (p) => p.total_area, best: "max", fmt: (v) => num(v) },
  { label: "Bedrooms", get: (p) => p.bedrooms, best: "max" },
  { label: "Bathrooms", get: (p) => p.bathrooms, best: "max" },
  { label: "Floors", get: (p) => p.floors },
  { label: "Type", get: (p) => titleCase(p.category) },
  { label: "Use", get: (p) => titleCase(p.use_type) },
  { label: "Location", get: (p) => [p.scheme_name, p.city_name].filter(Boolean).join(", ") },
  { label: "Est. monthly rent", get: (_, inv) => inv?.estimated_monthly_rent, best: "max", fmt: (v) => pkrShort(v) },
  { label: "Gross yield", get: (_, inv) => inv?.estimated_gross_yield_pct, best: "max", fmt: (v) => pct(v, 1, false) },
  { label: "Location score", get: (_, __, g) => g?.composite_score, best: "max", fmt: (v) => `${Math.round(v)} / 100` },
  { label: "Schools", get: (_, __, g) => g?.dimensions?.schools, best: "max", fmt: (v) => String(Math.round(v)) },
  { label: "Amenities", get: (_, __, g) => g?.dimensions?.amenities, best: "max", fmt: (v) => String(Math.round(v)) },
  { label: "Safety", get: (_, __, g) => g?.dimensions?.safety, best: "max", fmt: (v) => String(Math.round(v)) },
  { label: "Commute (min)", get: (_, __, g) => g?.commute_minutes, best: "min", fmt: (v) => String(Math.round(v)) },
];

export default function Compare() {
  const ids = usePrefs((s) => s.compare);
  const toggle = usePrefs((s) => s.toggleCompare);
  const clear = usePrefs((s) => s.clearCompare);
  const all = useApi<PropertyList>("/properties", { limit: 200 });
  const details = useQueries({ queries: ids.map((id) => ({ queryKey: [`/properties/${id}`, {}], queryFn: () => get<Property>(`/properties/${id}`) })) });
  const invs = useQueries({ queries: ids.map((id) => ({ queryKey: [`/properties/${id}/investment`, {}], queryFn: () => get<Investment>(`/properties/${id}/investment`) })) });
  const gis = useQueries({ queries: ids.map((id) => ({ queryKey: ["/property-intelligence/gis-score", { property_id: id }], queryFn: () => get<GisScore>("/property-intelligence/gis-score", { property_id: id }) })) });

  const props = details.map((d) => d.data).filter(Boolean) as Property[];
  const loading = details.some((d) => d.isLoading);

  // Score each column: +1 for every "best" row it wins.
  const wins = useMemo(() => {
    const w = props.map(() => 0);
    for (const r of ROWS) {
      if (!r.best) continue;
      const vals = props.map((p, i) => r.get(p, invs[i]?.data, gis[i]?.data));
      const nums = vals.map((v) => (typeof v === "number" ? v : null));
      const valid = nums.filter((v): v is number => v !== null);
      if (valid.length < 2) continue;
      const target = r.best === "min" ? Math.min(...valid) : Math.max(...valid);
      nums.forEach((v, i) => v === target && (w[i] = (w[i] ?? 0) + 1));
    }
    return w;
  }, [props, invs, gis]);
  const leader = wins.length ? wins.indexOf(Math.max(...wins)) : -1;

  const available = (all.data?.results ?? []).filter((p) => !ids.includes(p.id));

  if (!ids.length)
    return (
      <div className="container py-12">
        <PageHeader title="Compare properties" subtitle="Put up to four listings side by side — price, size, yield and location scores." crumbs={[{ label: "Home", to: "/" }, { label: "Compare" }]} />
        <EmptyState icon={<GitCompareArrows className="h-6 w-6" />} title="Nothing to compare yet" hint="Tap the compare icon on any property card to add it here." action={<Link to="/properties" className="btn btn-primary">Browse properties</Link>} />
        <div className="mt-10">
          <PropertyRowPicker items={available.slice(0, 8)} onPick={toggle} />
        </div>
      </div>
    );

  return (
    <div className="container py-8">
      <PageHeader
        title="Compare properties"
        subtitle={`${ids.length} of ${MAX_COMPARE} selected · best value in each row is highlighted`}
        crumbs={[{ label: "Home", to: "/" }, { label: "Properties", to: "/properties" }, { label: "Compare" }]}
        actions={
          <Button variant="outline" icon={<Trash2 className="h-4 w-4" />} onClick={clear}>
            Clear all
          </Button>
        }
      />
      {loading ? (
        <Skeleton className="h-[480px]" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[720px] table-fixed text-sm">
            <thead>
              <tr>
                <th className="w-44 p-4" />
                {props.map((p, i) => (
                  <th key={p.id} className="p-4 align-top">
                    <div className={cn("relative overflow-hidden rounded-2xl text-start ring-2", i === leader ? "ring-gold-400 shadow-glow" : "ring-transparent")}>
                      <img src={coverImage(p)} alt="" className="aspect-[4/3] w-full object-cover" />
                      {i === leader && props.length > 1 && (
                        <span className="chip absolute start-2 top-2 bg-gold-gradient text-brand-950">
                          <Trophy className="h-3 w-3" /> Best overall
                        </span>
                      )}
                      <button onClick={() => toggle(p.id)} className="absolute end-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-white/90 text-red-600 shadow" aria-label="Remove">
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    <Link to={`/properties/${p.id}`} className="mt-3 block text-start font-display text-base font-semibold hover:text-brand-700">
                      {p.title}
                    </Link>
                    <div className="mt-2 flex items-center gap-2">
                      <ScoreRing value={gis[i]?.data?.composite_score ?? 0} size={44} stroke={5} />
                      <span className="text-start text-xs text-ink-mute">
                        {wins[i]} wins · <span className="capitalize">{invs[i]?.data?.verdict ?? "…"}</span>
                      </span>
                    </div>
                  </th>
                ))}
                {ids.length < MAX_COMPARE && (
                  <th className="p-4 align-top">
                    <Link to="/properties" className="flex aspect-[4/3] flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-brand-200 text-brand-700 transition hover:bg-brand-50 dark:border-white/15 dark:text-brand-200 dark:hover:bg-white/5">
                      <Plus className="h-6 w-6" />
                      <span className="text-sm font-semibold">Add property</span>
                    </Link>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => {
                const vals = props.map((p, i) => r.get(p, invs[i]?.data, gis[i]?.data));
                const nums = vals.filter((v): v is number => typeof v === "number");
                const target = r.best && nums.length > 1 ? (r.best === "min" ? Math.min(...nums) : Math.max(...nums)) : null;
                return (
                  <tr key={r.label} className="border-t border-black/5 dark:border-white/5">
                    <td className="p-4 text-xs font-bold uppercase tracking-wide text-ink-mute">{r.label}</td>
                    {vals.map((v, i) => {
                      const best = target !== null && v === target;
                      return (
                        <td key={i} className={cn("p-4 font-semibold", best && "bg-brand-50/70 text-brand-800 dark:bg-brand-500/10 dark:text-brand-200")}>
                          <span className="inline-flex items-center gap-1.5">
                            {v === null || v === undefined || v === "" ? "—" : typeof v === "number" && r.fmt ? r.fmt(v) : String(v)}
                            {best && <Check className="h-4 w-4 text-brand-600" />}
                          </span>
                        </td>
                      );
                    })}
                    {ids.length < MAX_COMPARE && <td />}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-8 flex flex-col items-start gap-4 rounded-3xl bg-brand-950 p-6 text-white sm:flex-row sm:items-center">
        <Sparkles className="h-8 w-8 shrink-0 text-gold-300" />
        <p className="flex-1 text-sm text-white/80">Want a second opinion? The Investment Screener agent underwrites each shortlisted property with IRR, DSCR and a risk-adjusted grade.</p>
        <Link to={`/ai/agents/investment_screener?objective=${encodeURIComponent(`Compare ${props.map((p) => p.title).join(" vs ")}`)}`} className="btn btn-gold">
          Run Investment Screener
        </Link>
      </div>
      {available.length > 0 && ids.length < MAX_COMPARE && (
        <div className="mt-10">
          <PropertyRowPicker items={available.slice(0, 8)} onPick={toggle} />
        </div>
      )}
    </div>
  );
}

/** "Quick add" strip of properties. */
function PropertyRowPicker({ items, onPick }: { items: Property[]; onPick: (id: string) => void }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="mb-3 font-display text-lg font-semibold">Quick add</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((p) => (
          <button key={p.id} onClick={() => onPick(p.id)} className="card card-hover flex items-center gap-3 p-2 text-start">
            <img src={coverImage(p)} alt="" className="h-14 w-20 rounded-lg object-cover" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">{p.title}</span>
              <span className="text-xs font-bold text-brand-700 dark:text-gold-300">{pkrShort(p.price)}</span>
            </span>
            <Plus className="h-4 w-4 shrink-0 text-brand-600" />
          </button>
        ))}
      </div>
    </div>
  );
}
