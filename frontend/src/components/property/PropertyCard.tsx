import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Bath, BedDouble, GitCompareArrows, Heart, MapPin, Ruler, Sparkles } from "lucide-react";
import { toast } from "sonner";
import type { Property } from "@/types";
import { area, pkrShort, titleCase } from "@/lib/format";
import { coverImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";

export function FavoriteButton({ id, className }: { id: string; className?: string }) {
  const fav = usePrefs((s) => s.favorites.includes(id));
  const toggle = usePrefs((s) => s.toggleFavorite);
  return (
    <button
      type="button"
      aria-label={fav ? "Remove from favourites" : "Save to favourites"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle(id);
        toast.success(fav ? "Removed from shortlist" : "Saved to your shortlist");
      }}
      className={cn("flex h-9 w-9 items-center justify-center rounded-full bg-white/90 shadow-md backdrop-blur transition hover:scale-110 dark:bg-black/50", className)}
    >
      <Heart className={cn("h-4 w-4 transition", fav ? "fill-red-500 text-red-500" : "text-brand-800 dark:text-white")} />
    </button>
  );
}

export function CompareButton({ id, className, label }: { id: string; className?: string; label?: boolean }) {
  const on = usePrefs((s) => s.compare.includes(id));
  const toggle = usePrefs((s) => s.toggleCompare);
  const nav = useNavigate();
  return (
    <button
      type="button"
      aria-label="Compare"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle(id);
        toast(on ? "Removed from comparison" : "Added to comparison", { action: { label: "Compare", onClick: () => nav("/compare") } });
      }}
      className={cn(
        label ? "btn btn-sm" : "flex h-9 w-9 items-center justify-center rounded-full shadow-md backdrop-blur transition hover:scale-110",
        on ? "bg-gold-400 text-brand-950" : "bg-white/90 text-brand-800 dark:bg-black/50 dark:text-white",
        className,
      )}
    >
      <GitCompareArrows className="h-4 w-4" />
      {label && (on ? "In comparison" : "Compare")}
    </button>
  );
}

/** What a place-aware search matched on: the closest school / mosque … or the distance from a named place. */
export function NearbyNote({ p, className }: { p: Property; className?: string }) {
  const km = (v: number) => (v < 1 ? `${Math.round(v * 1000)} m` : `${v.toFixed(1)} km`);
  if (p.nearby)
    return (
      <p className={cn("mt-1 line-clamp-1 text-xs font-semibold text-brand-700 dark:text-brand-300", className)}>
        {p.nearby.kind} {km(p.nearby.distance_km)} away · {p.nearby.name}
      </p>
    );
  if (p.distance_km !== undefined) return <p className={cn("mt-1 text-xs font-semibold text-brand-700 dark:text-brand-300", className)}>{km(p.distance_km)} away</p>;
  return null;
}

export function PropertyCard({ p, className, compact }: { p: Property; className?: string; compact?: boolean }) {
  const loc = [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", ") || p.street_address || p.city_name || "Pakistan";
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-40px" }} transition={{ duration: 0.4 }}>
      <Link to={`/properties/${p.id}`} className={cn("group card card-hover block overflow-hidden", className)}>
        <div className={cn("relative overflow-hidden", compact ? "aspect-[16/10]" : "aspect-[4/3]")}>
          <img src={coverImage(p)} alt={p.title} loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-80" />
          <div className="absolute start-3 top-3 flex flex-wrap gap-1.5">
            {p.featured && (
              <span className="chip bg-gold-gradient text-brand-950 shadow">
                <Sparkles className="h-3 w-3" /> Featured
              </span>
            )}
            <span className="chip bg-white/90 text-brand-800 shadow dark:bg-black/50 dark:text-white">{titleCase(p.category)}</span>
          </div>
          <div className="absolute end-3 top-3 flex flex-col gap-2">
            <FavoriteButton id={p.id} />
            <CompareButton id={p.id} />
          </div>
          <div className="absolute bottom-3 start-3 end-3 flex items-end justify-between text-white">
            <p className="font-display text-xl font-bold drop-shadow">{pkrShort(p.price)}</p>
            <span className="chip bg-black/40 text-white backdrop-blur">{titleCase(p.use_type)}</span>
          </div>
        </div>
        <div className="p-4">
          <h3 className="line-clamp-1 font-display text-base font-semibold text-ink group-hover:text-brand-700 dark:text-white">{p.title}</h3>
          <p className="mt-1 flex items-center gap-1 text-xs text-ink-mute dark:text-slate-400">
            <MapPin className="h-3.5 w-3.5 shrink-0 text-gold-600" />
            <span className="line-clamp-1">{loc}</span>
          </p>
          <NearbyNote p={p} />
          <div className="mt-3 flex items-center gap-4 border-t border-black/5 pt-3 text-xs font-medium text-ink-soft dark:border-white/10 dark:text-slate-300">
            <span className="inline-flex items-center gap-1">
              <Ruler className="h-3.5 w-3.5 text-brand-600" />
              {area(p)}
            </span>
            {!!p.bedrooms && (
              <span className="inline-flex items-center gap-1">
                <BedDouble className="h-3.5 w-3.5 text-brand-600" />
                {p.bedrooms} Beds
              </span>
            )}
            {!!p.bathrooms && (
              <span className="inline-flex items-center gap-1">
                <Bath className="h-3.5 w-3.5 text-brand-600" />
                {p.bathrooms} Baths
              </span>
            )}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

/** Compact horizontal row (AI results, sidebars). */
export function PropertyRow({ p, extra }: { p: Pick<Property, "id" | "title" | "price" | "category"> & Partial<Property>; extra?: React.ReactNode }) {
  return (
    <Link to={`/properties/${p.id}`} className="group flex items-center gap-3 rounded-xl p-2 transition hover:bg-brand-50 dark:hover:bg-white/5">
      <img src={coverImage(p)} alt="" className="h-14 w-20 shrink-0 rounded-lg object-cover" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-ink group-hover:text-brand-700 dark:text-white">{p.title}</p>
        <p className="truncate text-xs text-ink-mute">{[p.scheme_name, p.city_name ?? (p as { city?: string }).city].filter(Boolean).join(", ") || titleCase(p.category)}</p>
        <p className="text-sm font-bold text-brand-700 dark:text-brand-300">{pkrShort(p.price)}</p>
      </div>
      {extra}
    </Link>
  );
}
