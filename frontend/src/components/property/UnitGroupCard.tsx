import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Building2, Layers, MapPin, Ruler } from "lucide-react";
import { priceRange, type UnitGroup } from "@/lib/projectGroups";
import { coverImage } from "@/lib/images";
import { cn } from "@/lib/utils";

const plural = (t: string) => (/s$/i.test(t) ? t : `${t}s`);
const num = (n: number, d = 0) => n.toLocaleString("en-PK", { maximumFractionDigits: d });
const span = (lo: number | null, hi: number | null, unit: string, d = 0) =>
  lo == null || hi == null ? null : lo === hi ? `${num(lo, d)} ${unit}` : `${num(lo, d)} – ${num(hi, d)} ${unit}`;
const priceSpan = priceRange;

/** One card for every available unit of one type in a big project (see lib/projectGroups.ts). */
export function UnitGroupCard({ g, className }: { g: UnitGroup; className?: string }) {
  const first = g.units[0]!;
  const to = `/properties?project=${g.projectId}&unit_type=${encodeURIComponent(g.unitType)}`;
  const size = span(g.marlaMin, g.marlaMax, "marla", 1) ?? span(g.sqftMin, g.sqftMax, "sq ft");
  const sqft = g.marlaMin != null ? span(g.sqftMin, g.sqftMax, "sq ft") : null;
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-40px" }} transition={{ duration: 0.4 }}>
      <Link to={to} className={cn("group card card-hover block overflow-hidden", className)}>
        <div className="relative aspect-[4/3] overflow-hidden">
          <img src={coverImage(first)} alt={g.projectName} loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
          <div className="absolute start-3 top-3 flex flex-wrap gap-1.5">
            <span className="chip bg-gold-gradient text-brand-950 shadow">New project</span>
            <span className="chip bg-white/90 text-brand-800 shadow dark:bg-black/50 dark:text-white">{g.units.length} available</span>
          </div>
          <div className="absolute bottom-3 start-3 end-3 text-white">
            <p className="text-[11px] font-medium uppercase tracking-wider text-white/80">Price range</p>
            <p className="font-display text-xl font-bold drop-shadow">{priceSpan(g.priceMin, g.priceMax)}</p>
          </div>
        </div>
        <div className="p-4">
          <h3 className="line-clamp-1 font-display text-base font-semibold capitalize text-ink group-hover:text-brand-700 dark:text-white">{plural(g.unitType)}</h3>
          <p className="mt-1 flex items-center gap-1 text-xs text-ink-mute dark:text-slate-400">
            <MapPin className="h-3.5 w-3.5 shrink-0 text-gold-600" />
            <span className="line-clamp-1">
              {g.projectName}
              {first.city_name ? `, ${first.city_name}` : ""}
            </span>
          </p>
          <div className="mt-3 space-y-1.5 border-t border-black/5 pt-3 text-xs text-ink-soft dark:border-white/10 dark:text-slate-300">
            {size && (
              <p className="flex items-center gap-1.5">
                <Ruler className="h-3.5 w-3.5 shrink-0 text-brand-600" /> {size}
                {sqft && <span className="text-ink-mute">({sqft})</span>}
              </p>
            )}
            {g.floors && (
              <p className="flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 shrink-0 text-brand-600" /> {g.floors}
              </p>
            )}
            <p className="flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5 shrink-0 text-brand-600" /> {g.units.length} of {g.projectTotal} units available in this project
            </p>
          </div>
          <p className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 dark:text-brand-300">
            See all {g.units.length} <ArrowRight className="h-4 w-4 rtl:rotate-180" />
          </p>
        </div>
      </Link>
    </motion.div>
  );
}
