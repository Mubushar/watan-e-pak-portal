import { Link } from "react-router-dom";
import { ArrowRight, Building2, Layers, MapPin, Ruler } from "lucide-react";
import { priceRange, type UnitGroup } from "@/lib/projectGroups";
import { coverImage } from "@/lib/images";
import { cn } from "@/lib/utils";

const plural = (t: string) => (/s$/i.test(t) ? t : `${t}s`);
const num = (n: number, d = 0) => n.toLocaleString("en-PK", { maximumFractionDigits: d });
const span = (lo: number | null, hi: number | null, unit: string, d = 0) =>
  lo == null || hi == null ? null : lo === hi ? `${num(lo, d)} ${unit}` : `${num(lo, d)} – ${num(hi, d)} ${unit}`;
export const groupHref = (g: UnitGroup) => `/explore?project=${g.projectId}&unit_type=${encodeURIComponent(g.unitType)}`;
export const priceSpan = priceRange;

/** One card for every available unit of one type in a big project — same as the web portal. */
export function UnitGroupCard({ g, className }: { g: UnitGroup; className?: string }) {
  const first = g.units[0]!;
  const size = span(g.marlaMin, g.marlaMax, "marla", 1) ?? span(g.sqftMin, g.sqftMax, "sq ft");
  return (
    <Link to={groupHref(g)} className={cn("group card block overflow-hidden transition active:scale-[.99]", className)}>
      <div className="relative aspect-[4/3] overflow-hidden">
        <img src={coverImage(first)} alt={g.projectName} loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
        <div className="absolute start-3 top-3 flex flex-wrap gap-1.5">
          <span className="chip bg-gold-gradient text-brand-950 shadow">New project</span>
          <span className="chip bg-white/90 text-brand-800 shadow dark:bg-black/50 dark:text-white">{g.units.length} available</span>
        </div>
        <p className="absolute bottom-3 start-3 end-3 font-display text-lg font-bold text-white drop-shadow">{priceSpan(g.priceMin, g.priceMax)}</p>
      </div>
      <div className="p-3.5">
        <p className="truncate font-display text-base font-semibold capitalize text-brand-900 dark:text-white">{plural(g.unitType)}</p>
        <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-ink-mute">
          <MapPin className="h-3.5 w-3.5 shrink-0" /> {g.projectName}
          {first.city_name ? `, ${first.city_name}` : ""}
        </p>
        <div className="mt-2 space-y-1 text-xs text-ink-soft dark:text-slate-300">
          {size && (
            <p className="flex items-center gap-1.5">
              <Ruler className="h-3.5 w-3.5 shrink-0 text-brand-600" /> {size}
            </p>
          )}
          {g.floors && (
            <p className="flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 shrink-0 text-brand-600" /> {g.floors}
            </p>
          )}
          <p className="flex items-center gap-1.5">
            <Building2 className="h-3.5 w-3.5 shrink-0 text-brand-600" /> {g.units.length} of {g.projectTotal} units in this project
          </p>
        </div>
        <p className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 dark:text-brand-300">
          See all {g.units.length} <ArrowRight className="h-4 w-4 rtl:rotate-180" />
        </p>
      </div>
    </Link>
  );
}
