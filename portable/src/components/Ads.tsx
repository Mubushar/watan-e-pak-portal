/**
 * Ad slots. A slot shows a sponsored ad sold by Watan-e-Pak when there is one, otherwise
 * Google AdSense on the web build (see lib/ads). Every ad is labelled "Sponsored".
 */
import { useEffect, useRef, useState, type ComponentType } from "react";
import {
  ArrowUpDown, Boxes, Cpu, Droplets, ExternalLink, HardHat, Landmark, Megaphone, Scale, ShieldCheck, Sofa, Sun, Trees, Truck, Umbrella, Wrench,
} from "lucide-react";
import { adConfig, adsFor, hideNativeBanner, loadAdSense, showNativeBanner, trackAd, type Ad, type AdConfig } from "@/lib/ads";
import { runtime } from "@/lib/platform";
import { cn } from "@/lib/utils";

type Look = { icon: ComponentType<{ className?: string }>; from: string; to: string };
const LOOK: Record<string, Look> = {
  smart_technology: { icon: Cpu, from: "#0ea5e9", to: "#1e3a8a" },
  construction_technique: { icon: HardHat, from: "#f59e0b", to: "#b45309" },
  materials: { icon: Boxes, from: "#a8a29e", to: "#44403c" },
  tools_equipment: { icon: Wrench, from: "#64748b", to: "#1e293b" },
  solar_energy: { icon: Sun, from: "#facc15", to: "#ea580c" },
  water: { icon: Droplets, from: "#22d3ee", to: "#0369a1" },
  security: { icon: ShieldCheck, from: "#475569", to: "#0f172a" },
  elevators: { icon: ArrowUpDown, from: "#a78bfa", to: "#5b21b6" },
  interiors: { icon: Sofa, from: "#f472b6", to: "#9d174d" },
  landscaping: { icon: Trees, from: "#4ade80", to: "#166534" },
  finance: { icon: Landmark, from: "#34d399", to: "#065f46" },
  insurance: { icon: Umbrella, from: "#60a5fa", to: "#1d4ed8" },
  legal: { icon: Scale, from: "#c084fc", to: "#6b21a8" },
  services: { icon: Truck, from: "#fb923c", to: "#9a3412" },
};
const look = (category: string): Look => LOOK[category] ?? { icon: Megaphone, from: "#22c55e", to: "#14532d" };

/** Counts a view once at least half the ad has been on screen for a second. */
function useImpression(ad: Ad) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let timer: number | undefined;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          timer = window.setTimeout(() => {
            trackAd(ad.id, "impression");
            io.disconnect();
          }, 1000);
        } else window.clearTimeout(timer);
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      window.clearTimeout(timer);
    };
  }, [ad.id]);
  return ref;
}

function open(ad: Ad) {
  trackAd(ad.id, "click");
  if (ad.cta_url) window.open(ad.cta_url, "_blank", "noopener,noreferrer");
}

function Label({ ad }: { ad: Ad }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">{ad.sponsored_label ?? "Sponsored"}</span>
      {ad.sample && <span className="rounded bg-white/85 px-1.5 py-0.5 text-[10px] font-semibold text-ink-soft">Sample</span>}
    </span>
  );
}

function Art({ ad, className }: { ad: Ad; className?: string }) {
  const l = look(ad.category);
  const Icon = l.icon;
  if (ad.image_url) return <img src={ad.image_url} alt="" loading="lazy" className={cn("object-cover", className)} />;
  return (
    <div className={cn("relative grid place-items-center overflow-hidden", className)} style={{ background: `linear-gradient(135deg, ${l.from}, ${l.to})` }}>
      <Icon className="h-10 w-10 text-white/90 drop-shadow" />
      <div className="absolute -bottom-6 -right-6 h-24 w-24 rounded-full bg-white/10" />
      <div className="absolute -left-4 -top-8 h-20 w-20 rounded-full bg-white/10" />
    </div>
  );
}

/** A sponsored ad: wide banner (home), card (grid / listing page) or row (list view). */
export function SponsoredAd({ ad, variant = "card", className }: { ad: Ad; variant?: "banner" | "card" | "row"; className?: string }) {
  const ref = useImpression(ad);
  const cta = ad.cta_label || "Learn more";
  if (variant === "row") {
    return (
      <div ref={ref} role="link" tabIndex={0} onClick={() => open(ad)} onKeyDown={(e) => e.key === "Enter" && open(ad)}
        className={cn("flex cursor-pointer items-center gap-3 rounded-xl p-2 transition hover:bg-gold-50 dark:hover:bg-white/5", className)}>
        <Art ad={ad} className="h-16 w-20 shrink-0 rounded-lg" />
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-gold-700 dark:text-gold-300">{ad.sponsored_label ?? "Sponsored"}{ad.sample ? " · Sample" : ""} · {ad.advertiser}</p>
          <p dir="auto" className="truncate text-sm font-semibold text-brand-900 dark:text-white">{ad.headline}</p>
          <p dir="auto" className="truncate text-xs text-ink-mute dark:text-slate-400">{ad.price_text || ad.offer || ad.title}</p>
        </div>
        <ExternalLink className="h-4 w-4 shrink-0 text-ink-mute" />
      </div>
    );
  }
  if (variant === "banner") {
    return (
      <div ref={ref} className={cn("card overflow-hidden", className)}>
        <div className="flex flex-col sm:flex-row">
          <div className="relative sm:w-56">
            <Art ad={ad} className="h-32 w-full sm:h-full" />
            <div className="absolute left-2 top-2"><Label ad={ad} /></div>
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-4">
            <p className="text-xs font-semibold text-ink-mute">{ad.advertiser}</p>
            <p dir="auto" className="font-display text-lg font-bold leading-snug text-brand-900 dark:text-white">{ad.headline}</p>
            {ad.body && <p dir="auto" className="line-clamp-2 text-sm text-ink-soft dark:text-slate-300">{ad.body}</p>}
            <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
              {(ad.offer || ad.price_text) && <span dir="auto" className="rounded-full bg-gold-100 px-2.5 py-1 text-xs font-semibold text-gold-800 dark:bg-gold-500/15 dark:text-gold-200">{ad.offer || ad.price_text}</span>}
              <button type="button" onClick={() => open(ad)} className="btn btn-gold ms-auto !py-2 text-sm">
                {cta} <ExternalLink className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div ref={ref} role="link" tabIndex={0} onClick={() => open(ad)} onKeyDown={(e) => e.key === "Enter" && open(ad)}
      className={cn("card flex cursor-pointer flex-col overflow-hidden transition hover:-translate-y-0.5 hover:shadow-lg", className)}>
      <div className="relative">
        <Art ad={ad} className="aspect-[16/10] w-full" />
        <div className="absolute left-2 top-2"><Label ad={ad} /></div>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3.5">
        <p className="text-xs font-semibold text-ink-mute">{ad.advertiser}</p>
        <p dir="auto" className="font-semibold leading-snug text-brand-900 dark:text-white">{ad.headline}</p>
        {ad.body && <p dir="auto" className="line-clamp-2 text-xs text-ink-soft dark:text-slate-300">{ad.body}</p>}
        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          <span dir="auto" className="truncate text-xs font-semibold text-gold-700 dark:text-gold-300">{ad.offer || ad.price_text || ""}</span>
          <span className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-brand-700 dark:text-brand-300">{cta} <ExternalLink className="h-3 w-3" /></span>
        </div>
      </div>
    </div>
  );
}

/** Google AdSense unit (web build only). */
function AdSenseUnit({ client, slot, className }: { client: string; slot: string; className?: string }) {
  const pushed = useRef(false);
  useEffect(() => {
    loadAdSense(client);
    if (pushed.current) return;
    pushed.current = true;
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch {
      /* blocked by an ad blocker */
    }
  }, [client]);
  return (
    <div className={cn("overflow-hidden", className)}>
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-mute">Advertisement</p>
      <ins className="adsbygoogle block" style={{ display: "block" }} data-ad-client={client} data-ad-slot={slot} data-ad-format="auto" data-full-width-responsive="true" />
    </div>
  );
}

/**
 * One ad position. `slot` picks sponsored ads (hero, banner, infeed, sidebar, footer);
 * `placement` picks the AdSense unit used when no sponsored ad is booked.
 * `index` spreads different ads across repeated slots; `rotate` cycles them.
 */
export function AdSlot({ slot, placement, variant = "card", index = 0, rotate = false, className }: {
  slot: string;
  placement: "home" | "explore" | "detail";
  variant?: "banner" | "card" | "row";
  index?: number;
  rotate?: boolean;
  className?: string;
}) {
  const [ads, setAds] = useState<Ad[] | null>(null);
  const [cfg, setCfg] = useState<AdConfig | null>(null);
  const [turn, setTurn] = useState(0);
  useEffect(() => {
    let live = true;
    void adsFor(slot).then((a) => live && setAds(a));
    void adConfig().then((c) => live && setCfg(c));
    return () => {
      live = false;
    };
  }, [slot]);
  useEffect(() => {
    if (!rotate || !ads || ads.length < 2) return;
    const t = window.setInterval(() => setTurn((n) => n + 1), 8000);
    return () => window.clearInterval(t);
  }, [rotate, ads]);

  if (ads === null) return null;
  if (ads.length) {
    const ad = ads[(index + turn) % ads.length];
    return (
      <div className={className}>
        <SponsoredAd key={ad.id} ad={ad} variant={variant} />
        {rotate && ads.length > 1 && (
          <div className="mt-2 flex justify-center gap-1.5">
            {ads.map((a, i) => (
              <button key={a.id} type="button" aria-label={`Ad ${i + 1}`} onClick={() => setTurn(i - index + ads.length * 100)}
                className={cn("h-1.5 rounded-full transition-all", i === (index + turn) % ads.length ? "w-5 bg-gold-500" : "w-1.5 bg-black/15 dark:bg-white/20")} />
            ))}
          </div>
        )}
      </div>
    );
  }
  const adsense = runtime === "web" ? cfg?.adsense : null;
  const unit = adsense?.slots[placement];
  if (adsense && unit) return <AdSenseUnit client={adsense.client} slot={unit} className={className} />;
  return null;
}

/** "Advertise with Watan-e-Pak": invites vendors to buy ad space. */
export function AdvertiseWithUs({ className }: { className?: string }) {
  const [cfg, setCfg] = useState<AdConfig | null>(null);
  useEffect(() => {
    void adConfig().then(setCfg);
  }, []);
  const email = cfg?.advertise.email;
  return (
    <section className={cn("card flex items-start gap-4 p-5", className)}>
      <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gold-gradient text-brand-950">
        <Megaphone className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-brand-900 dark:text-white">Advertise with Watan-e-Pak</p>
        <p className="mt-0.5 text-sm text-ink-soft dark:text-slate-300">{cfg?.advertise.body ?? "Reach buyers, investors and developers across Pakistan."}</p>
        {email && (
          <a href={`mailto:${email}?subject=${encodeURIComponent("Advertising on Watan-e-Pak")}`} className="btn btn-outline mt-3 !py-2 text-sm">
            Contact {email}
          </a>
        )}
      </div>
    </section>
  );
}

/** Shows the AdMob banner while a screen is open (Android / iOS only). */
export function useNativeBanner() {
  useEffect(() => {
    void showNativeBanner();
    return () => {
      void hideNativeBanner();
    };
  }, []);
}

/** Room at the end of a screen so the AdMob banner never covers content. */
export function BannerSpacer() {
  return <div aria-hidden style={{ height: "var(--ad-banner-h, 0px)" }} />;
}
