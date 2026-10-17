/**
 * Live advertisement slot backed by `/ads/active`. Impressions are tracked once
 * per creative per mount; clicks are tracked before opening the CTA.
 *
 *   <AdSlot slot="banner" />            full-width banner
 *   <AdSlot slot="sidebar" />           stacked tiles
 *   <AdSlot slot="infeed" layout="card" />
 */
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpRight,
  Building2,
  Droplets,
  Hammer,
  Home,
  Landmark,
  Lock,
  Megaphone,
  Paintbrush,
  Phone,
  Scale,
  ShieldCheck,
  Sun,
  Trees,
  Truck,
  Wrench,
  Cpu,
  type LucideIcon,
} from "lucide-react";
import type { Ad } from "@/types";
import { post } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";

const CATEGORY_STYLE: Record<string, { icon: LucideIcon; from: string; to: string }> = {
  smart_technology: { icon: Cpu, from: "#0f3d5a", to: "#1f6f9a" },
  construction_technique: { icon: Building2, from: "#3d2f1f", to: "#8a5a35" },
  materials: { icon: Hammer, from: "#4a3b2a", to: "#a87a19" },
  tools_equipment: { icon: Wrench, from: "#33363b", to: "#5f6670" },
  solar_energy: { icon: Sun, from: "#7a4b00", to: "#e0a31a" },
  water: { icon: Droplets, from: "#0b4f6c", to: "#1aa0c9" },
  security: { icon: Lock, from: "#1d1f3a", to: "#3f4596" },
  elevators: { icon: Building2, from: "#26313d", to: "#4f6378" },
  interiors: { icon: Paintbrush, from: "#5a2a3a", to: "#b5523b" },
  landscaping: { icon: Trees, from: "#0c472e", to: "#2f8a45" },
  finance: { icon: Landmark, from: "#093a26", to: "#146f45" },
  insurance: { icon: ShieldCheck, from: "#123a5a", to: "#2c7fb8" },
  legal: { icon: Scale, from: "#2a2a3a", to: "#5b5b7a" },
  services: { icon: Truck, from: "#3a1f4a", to: "#7c3aed" },
};
const styleFor = (c: string) => CATEGORY_STYLE[c] ?? { icon: Home, from: "#093a26", to: "#146f45" };

const seen = new Set<string>();
function trackImpression(id: string) {
  if (seen.has(id)) return;
  seen.add(id);
  post(`/ads/${id}/track`, undefined, { event: "impression" }).catch(() => {});
}
function trackClick(ad: Ad) {
  post(`/ads/${ad.id}/track`, undefined, { event: "click" }).catch(() => {});
  if (ad.cta_url) window.open(ad.cta_url, "_blank", "noopener,noreferrer");
}

/** `noTrack` disables impression/click tracking (previews in the ad manager). */
export function AdCreative({ ad, layout = "banner", className, noTrack }: { ad: Ad; layout?: "banner" | "card" | "tile" | "strip"; className?: string; noTrack?: boolean }) {
  const st = styleFor(ad.category);
  const Icon = st.icon;
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || noTrack) return;
    const io = new IntersectionObserver((es) => es.some((e) => e.isIntersecting) && trackImpression(ad.id), { threshold: 0.5 });
    io.observe(el);
    return () => io.disconnect();
  }, [ad.id, noTrack]);

  const bg = { background: `linear-gradient(135deg, ${st.from}, ${st.to})` };
  const sponsor = (
    <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white/90 backdrop-blur">
      <Megaphone className="h-3 w-3" /> Sponsored · {ad.advertiser}
    </span>
  );

  if (layout === "strip") {
    return (
      <div ref={ref} className={cn("flex items-center gap-3 rounded-xl px-4 py-2.5 text-white", className)} style={bg}>
        <Icon className="h-5 w-5 shrink-0 text-gold-200" />
        <p className="min-w-0 flex-1 truncate text-sm">
          <span className="font-semibold">{ad.headline}</span> <span className="text-white/75">— {ad.price_text ?? ad.body}</span>
        </p>
        <button onClick={() => (noTrack ? undefined : trackClick(ad))} className="btn btn-sm bg-white text-brand-900 hover:bg-gold-100">
          {ad.cta_label ?? "Learn more"}
        </button>
      </div>
    );
  }

  if (layout === "tile" || layout === "card") {
    return (
      <div ref={ref} className={cn("relative flex flex-col overflow-hidden rounded-2xl p-5 text-white shadow-soft", layout === "card" && "min-h-[260px]", className)} style={bg}>
        <Icon className="absolute -end-6 -top-6 h-32 w-32 text-white/10" />
        {sponsor}
        <h4 className="mt-3 font-display text-lg font-bold leading-snug">{ad.headline}</h4>
        <p className="mt-1.5 line-clamp-3 text-sm text-white/80">{ad.body}</p>
        <div className="mt-auto pt-4">
          {ad.offer && <p className="mb-2 text-xs font-semibold text-gold-200">{ad.offer}</p>}
          {ad.price_text && <p className="mb-3 text-sm font-semibold text-white">{ad.price_text}</p>}
          <div className="flex items-center gap-2">
            <button onClick={() => (noTrack ? undefined : trackClick(ad))} className="btn btn-sm btn-gold">
              {ad.cta_label ?? "Learn more"} <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
            {ad.phone && (
              <a href={`tel:${ad.phone}`} className="btn btn-sm bg-white/10 text-white hover:bg-white/20" onClick={(e) => e.stopPropagation()}>
                <Phone className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={ref} className={cn("relative overflow-hidden rounded-3xl text-white shadow-soft", className)} style={bg}>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_85%_30%,rgba(255,255,255,.18),transparent_45%)]" />
      <Icon className="absolute -bottom-8 end-10 h-48 w-48 text-white/10" />
      <div className="relative flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:p-8">
        <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-white/15 backdrop-blur">
          <Icon className="h-8 w-8 text-gold-200" />
        </span>
        <div className="min-w-0 flex-1">
          {sponsor}
          <h4 className="mt-2 font-display text-2xl font-bold">{ad.headline}</h4>
          <p className="mt-1 max-w-2xl text-sm text-white/80">{ad.body}</p>
          {ad.price_text && <p className="mt-2 text-sm font-semibold text-gold-200">{ad.price_text}</p>}
        </div>
        <button onClick={() => (noTrack ? undefined : trackClick(ad))} className="btn btn-lg btn-gold shrink-0">
          {ad.cta_label ?? "Learn more"} <ArrowUpRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function AdSlot({
  slot,
  layout,
  limit = 3,
  rotate = 9000,
  className,
  city,
}: {
  slot: "hero" | "banner" | "sidebar" | "infeed" | "footer" | "newsletter";
  layout?: "banner" | "card" | "tile" | "strip";
  limit?: number;
  rotate?: number;
  className?: string;
  city?: string;
}) {
  const q = useApi<{ advertisements: Ad[] }>("/ads/active", { slot, limit, city }, { staleTime: 5 * 60_000 });
  const ads = q.data?.advertisements ?? [];
  const [i, setI] = useState(0);
  useEffect(() => {
    if (ads.length < 2 || !rotate) return;
    const t = setInterval(() => setI((x) => (x + 1) % ads.length), rotate);
    return () => clearInterval(t);
  }, [ads.length, rotate]);
  if (!ads.length) return null;
  const lay = layout ?? (slot === "sidebar" ? "tile" : slot === "footer" ? "strip" : slot === "infeed" ? "card" : "banner");
  const ad = ads[i % ads.length]!;
  return (
    <div className={cn("relative", className)}>
      <AnimatePresence mode="wait">
        <motion.div key={ad.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.35 }}>
          <AdCreative ad={ad} layout={lay} />
        </motion.div>
      </AnimatePresence>
      {ads.length > 1 && (
        <div className="absolute bottom-2 end-3 flex gap-1">
          {ads.map((a, j) => (
            <button key={a.id} onClick={() => setI(j)} className={cn("h-1.5 rounded-full transition-all", j === i % ads.length ? "w-4 bg-white" : "w-1.5 bg-white/40")} aria-label={`Ad ${j + 1}`} />
          ))}
        </div>
      )}
    </div>
  );
}
