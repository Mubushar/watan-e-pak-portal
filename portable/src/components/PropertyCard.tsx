import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Bath, BedDouble, Heart, MapPin, Ruler, Sparkles } from "lucide-react";
import type { Property } from "@/types";
import { area, pkrShort, titleCase } from "@/lib/format";
import { coverImage, isRepresentative } from "@/lib/images";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";
import { Badge, statusTone } from "./ui";

export function locationOf(p: Property): string {
  return [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", ") || p.street_address || p.city_name || "Pakistan";
}

export function FavoriteButton({ id, className }: { id: string; className?: string }) {
  const fav = usePrefs((s) => s.favorites.includes(id));
  const toggle = usePrefs((s) => s.toggleFavorite);
  return (
    <button
      type="button"
      aria-label={fav ? "Remove from saved" : "Save"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle(id);
      }}
      className={cn("flex h-9 w-9 items-center justify-center rounded-full bg-white/90 shadow-md backdrop-blur transition active:scale-90 dark:bg-black/50", className)}
    >
      <Heart className={cn("h-4 w-4 transition", fav ? "fill-red-500 text-red-500" : "text-brand-800 dark:text-white")} />
    </button>
  );
}

/** Shown on a library photo: a real photo of a similar property, not this listing's own. */
export function RepresentativeTag({ src, className }: { src: string; className?: string }) {
  if (!isRepresentative(src)) return null;
  return (
    <span
      title="A real photo of a similar property — the owner hasn’t added photos of this one yet"
      className={cn("pointer-events-none absolute bottom-12 start-3 rounded-md bg-black/40 px-1.5 py-0.5 text-[10px] font-medium text-white/90 backdrop-blur-sm", className)}
    >
      Representative photo
    </span>
  );
}

/** Large photo card — portal PropertyCard styling. */
export function PropertyCard({ p, className, compact }: { p: Property; className?: string; compact?: boolean }) {
  return (
    <Link to={`/property/${p.id}`} className={cn("group card block overflow-hidden active:scale-[.99] transition", className)}>
      <div className={cn("relative overflow-hidden", compact ? "aspect-[16/10]" : "aspect-[4/3]")}>
        <img src={coverImage(p)} alt={p.title} loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-transparent to-transparent" />
        <RepresentativeTag src={coverImage(p)} />
        <div className="absolute start-3 top-3 flex flex-wrap gap-1.5">
          {p.featured && (
            <span className="chip bg-gold-gradient text-brand-950 shadow">
              <Sparkles className="h-3 w-3" /> Featured
            </span>
          )}
          <span className="chip bg-white/90 text-brand-800 shadow dark:bg-black/50 dark:text-white">{titleCase(p.category)}</span>
        </div>
        <FavoriteButton id={p.id} className="absolute end-3 top-3" />
        <div className="absolute bottom-3 start-3 end-3 flex items-end justify-between text-white">
          <p className="font-display text-xl font-bold drop-shadow">{pkrShort(p.price)}{p.listing_purpose === "rent" ? (p.rent_frequency === "weekly" ? "/wk" : "/mo") : ""}</p>
          <span className="chip bg-black/40 text-white backdrop-blur">{titleCase(p.use_type)}</span>
        </div>
      </div>
      <div className="p-3.5">
        <h3 className="line-clamp-1 font-display font-semibold text-brand-900 dark:text-white">{p.title}</h3>
        <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-ink-mute dark:text-slate-400">
          <MapPin className="h-3.5 w-3.5 shrink-0" /> {locationOf(p)}
        </p>
        <NearbyNote p={p} />
        <Specs p={p} className="mt-2.5" />
      </div>
    </Link>
  );
}

/** What a place-aware search matched on: the closest school / mosque … or the distance from a named place. */
export function NearbyNote({ p, className }: { p: Property; className?: string }) {
  const km = (v: number) => (v < 1 ? `${Math.round(v * 1000)} m` : `${v.toFixed(1)} km`);
  const text = p.nearby ? `${p.nearby.kind} ${km(p.nearby.distance_km)} away · ${p.nearby.name}` : p.distance_km !== undefined ? `${km(p.distance_km)} away` : null;
  return text ? <p className={cn("mt-1 line-clamp-1 text-xs font-semibold text-brand-700 dark:text-brand-300", className)}>{text}</p> : null;
}

export function Specs({ p, className }: { p: Property; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-medium text-ink-soft dark:text-slate-300", className)}>
      {!!p.bedrooms && (
        <span className="flex items-center gap-1">
          <BedDouble className="h-3.5 w-3.5 text-brand-600" /> {p.bedrooms} Beds
        </span>
      )}
      {!!p.bathrooms && (
        <span className="flex items-center gap-1">
          <Bath className="h-3.5 w-3.5 text-brand-600" /> {p.bathrooms} Baths
        </span>
      )}
      <span className="flex items-center gap-1">
        <Ruler className="h-3.5 w-3.5 text-brand-600" /> {area(p)}
      </span>
    </div>
  );
}

/** Compact row — used in lists, chat replies and My Listings. */
export function PropertyRow({ p, extra, to, className }: { p: Property; extra?: ReactNode; to?: string; className?: string }) {
  return (
    <Link to={to ?? `/property/${p.id}`} className={cn("flex items-center gap-3 rounded-xl p-2 transition hover:bg-brand-50 active:scale-[.99] dark:hover:bg-white/5", className)}>
      <img src={coverImage(p)} alt="" loading="lazy" className="h-16 w-20 shrink-0 rounded-lg object-cover" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-brand-900 dark:text-white">{p.title}</p>
        <p className="truncate text-xs text-ink-mute dark:text-slate-400">
          {titleCase(p.category)} · {area(p)} · {p.city_name ?? "Pakistan"}
        </p>
        <NearbyNote p={p} className="mt-0" />
        <div className="mt-1 flex items-center gap-2">
          <span className="font-display text-sm font-bold text-brand-700 dark:text-brand-300">{pkrShort(p.price)}{p.listing_purpose === "rent" ? (p.rent_frequency === "weekly" ? "/wk" : "/mo") : ""}</span>
          {p.status && p.status !== "active" && <Badge tone={statusTone(p.status)}>{titleCase(p.status)}</Badge>}
        </div>
      </div>
      {extra}
    </Link>
  );
}
