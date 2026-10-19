/**
 * Shared Leaflet map with a base-map switcher and brand-styled pins.
 *
 *   <PortalMap center={[31.52, 74.35]} zoom={11} height={420}>
 *     <Marker position={[lat, lon]} icon={pin("property")} />
 *   </PortalMap>
 *
 * Children are any react-leaflet layers. `fit` auto-fits the view to points.
 */
import { createElement, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import L from "leaflet";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import { BedDouble, BookOpen, Briefcase, Building, Building2, Bus, Dumbbell, Fuel, HeartPulse, Home, Landmark, LandPlot, Layers, MapPin, ShoppingBag, Store, Trees, Utensils, Wallet, Warehouse, type LucideIcon } from "lucide-react";
import { cn, escapeHtml } from "@/lib/utils";

export const BASE_MAPS = {
  streets: { label: "Streets", url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: "© OpenStreetMap" },
  satellite: {
    label: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles © Esri",
  },
  // Light / Dark: OpenStreetMap tiles restyled with a CSS filter (CARTO's basemaps now need an API key).
  light: { label: "Light", url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: "© OpenStreetMap", className: "tiles-light" },
  dark: { label: "Dark", url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: "© OpenStreetMap", className: "tiles-dark" },
  terrain: { label: "Terrain", url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", attribution: "© OpenTopoMap" },
} as const;
export type BaseMapKey = keyof typeof BASE_MAPS;

export const PAKISTAN_CENTER: [number, number] = [30.3753, 69.3451];

/** Category colours + glyphs for pins. */
export const PIN_STYLES: Record<string, { color: string; glyph: string }> = {
  property: { color: "#0f5a39", glyph: "🏠" },
  featured: { color: "#c99a22", glyph: "★" },
  commercial: { color: "#2c7fb8", glyph: "🏢" },
  plot: { color: "#8a5a35", glyph: "▦" },
  education: { color: "#2563eb", glyph: "🎓" },
  health: { color: "#dc2626", glyph: "✚" },
  shopping: { color: "#ea580c", glyph: "🛍" },
  worship: { color: "#7c3aed", glyph: "🕌" },
  transport: { color: "#0891b2", glyph: "🚌" },
  park: { color: "#16a34a", glyph: "🌳" },
  restaurant: { color: "#db2777", glyph: "🍽" },
  bank: { color: "#0f766e", glyph: "🏦" },
  fuel: { color: "#4b5563", glyph: "⛽" },
  government: { color: "#334155", glyph: "🏛" },
  hotel: { color: "#9333ea", glyph: "🛏" },
  sports: { color: "#65a30d", glyph: "⚽" },
  city: { color: "#0f5a39", glyph: "◉" },
  project: { color: "#a87a19", glyph: "🏗" },
  other: { color: "#64748b", glyph: "•" },
};

const iconCache = new Map<string, L.DivIcon>();
export function pin(kind: string = "property", opts: { label?: string; size?: number; pulse?: boolean } = {}): L.DivIcon {
  const s = PIN_STYLES[kind] ?? PIN_STYLES.other!;
  const size = opts.size ?? 34;
  const key = `${kind}|${opts.label ?? ""}|${size}|${opts.pulse ? 1 : 0}`;
  const hit = iconCache.get(key);
  if (hit) return hit;
  const html = `
    <div style="position:relative;width:${size}px;height:${size + 8}px">
      ${opts.pulse ? `<span style="position:absolute;left:50%;top:${size / 2}px;width:${size}px;height:${size}px;margin:-${size / 2}px 0 0 -${size / 2}px;border-radius:9999px;background:${s.color};opacity:.35" class="animate-pulse-ring"></span>` : ""}
      <svg viewBox="0 0 40 48" width="${size}" height="${size + 8}" style="position:absolute;inset:0;filter:drop-shadow(0 4px 6px rgba(0,0,0,.3))">
        <path d="M20 47s16-14.6 16-27A16 16 0 0 0 4 20c0 12.4 16 27 16 27z" fill="${s.color}" stroke="#fff" stroke-width="2.5"/>
      </svg>
      <span style="position:absolute;left:0;right:0;top:${size * 0.18}px;text-align:center;font-size:${size * 0.4}px;line-height:1;color:#fff">${s.glyph}</span>
      ${opts.label ? `<span style="position:absolute;left:50%;top:-22px;transform:translateX(-50%);white-space:nowrap;background:#fff;color:#0c472e;font:600 11px/1 'Plus Jakarta Sans',sans-serif;padding:4px 7px;border-radius:999px;box-shadow:0 2px 6px rgba(0,0,0,.2)">${escapeHtml(opts.label)}</span>` : ""}
    </div>`;
  const icon = L.divIcon({ html, className: "arz-pin", iconSize: [size, size + 8], iconAnchor: [size / 2, size + 6], popupAnchor: [0, -size] });
  iconCache.set(key, icon);
  return icon;
}

// ------------------------------------------------------------------ vector icon pins

const svgCache = new Map<string, string>();
/** A Lucide icon as an SVG string (white, for drawing inside pins and badges). */
export function iconSvg(Icon: LucideIcon, size = 16, color = "#ffffff"): string {
  const key = `${Icon.displayName ?? Icon.name}|${size}|${color}`;
  let svg = svgCache.get(key);
  if (!svg) {
    svg = renderToStaticMarkup(createElement(Icon, { size, color, strokeWidth: 2.25 }));
    svgCache.set(key, svg);
  }
  return svg;
}

/** A map pin in `color` with a vector icon in it (crisper than emoji, same on every device). */
export function iconPin(color: string, Icon: LucideIcon, opts: { size?: number; label?: string; pulse?: boolean; star?: boolean } = {}): L.DivIcon {
  const size = opts.size ?? 34;
  const key = `ip|${color}|${Icon.displayName ?? Icon.name}|${size}|${opts.label ?? ""}|${opts.pulse ? 1 : 0}|${opts.star ? 1 : 0}`;
  const hit = iconCache.get(key);
  if (hit) return hit;
  const g = Math.round(size * 0.46);
  const html = `
    <div style="position:relative;width:${size}px;height:${size + 8}px">
      ${opts.pulse ? `<span style="position:absolute;left:50%;top:${size / 2}px;width:${size}px;height:${size}px;margin:-${size / 2}px 0 0 -${size / 2}px;border-radius:9999px;background:${color};opacity:.35" class="animate-pulse-ring"></span>` : ""}
      <svg viewBox="0 0 40 48" width="${size}" height="${size + 8}" style="position:absolute;inset:0;filter:drop-shadow(0 4px 6px rgba(0,0,0,.3))">
        <path d="M20 47s16-14.6 16-27A16 16 0 0 0 4 20c0 12.4 16 27 16 27z" fill="${color}" stroke="#fff" stroke-width="2.5"/>
      </svg>
      <span style="position:absolute;left:0;right:0;top:${Math.round(size * 0.2)}px;display:flex;justify-content:center;line-height:0">${iconSvg(Icon, g)}</span>
      ${opts.star ? `<span style="position:absolute;right:-3px;top:-3px;width:15px;height:15px;border-radius:9999px;background:#f2c94c;border:2px solid #fff;color:#5c4407;font:700 9px/11px sans-serif;text-align:center">★</span>` : ""}
      ${opts.label ? `<span style="position:absolute;left:50%;top:-22px;transform:translateX(-50%);white-space:nowrap;background:#fff;color:#0c472e;font:600 11px/1 'Plus Jakarta Sans',sans-serif;padding:4px 7px;border-radius:999px;box-shadow:0 2px 6px rgba(0,0,0,.2)">${escapeHtml(opts.label)}</span>` : ""}
    </div>`;
  const icon = L.divIcon({ html, className: "arz-pin", iconSize: [size, size + 8], iconAnchor: [size / 2, size + 6], popupAnchor: [0, -size] });
  iconCache.set(key, icon);
  return icon;
}

/** A small round badge with a vector icon (places / points of interest). */
export function iconBadge(color: string, Icon: LucideIcon, size = 24): L.DivIcon {
  const key = `ib|${color}|${Icon.displayName ?? Icon.name}|${size}`;
  const hit = iconCache.get(key);
  if (hit) return hit;
  const html = `<div style="width:${size}px;height:${size}px;border-radius:9999px;background:${color};border:2px solid #fff;box-shadow:0 2px 5px rgba(0,0,0,.3);display:flex;align-items:center;justify-content:center">${iconSvg(Icon, Math.round(size * 0.55))}</div>`;
  const icon = L.divIcon({ html, className: "arz-badge", iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2] });
  iconCache.set(key, icon);
  return icon;
}

/** Listing pins: the icon says what it is, the colour says how it is used; featured get a star. */
export const LISTING_ICONS: Record<string, LucideIcon> = {
  house: Home, villa: Home, farmhouse: Home, apartment: Building2, flat: Building2, plot: LandPlot,
  shop: Store, office: Briefcase, floor: Layers, portion: Layers, building: Building, space: Warehouse, warehouse: Warehouse, shed: Warehouse,
};
export function listingPin(p: { category?: string | null; use_type?: string | null; featured?: boolean | null }, opts: { size?: number; label?: string } = {}): L.DivIcon {
  const cat = (p.category ?? "").toLowerCase();
  const color = p.featured ? "#b8860b" : cat === "plot" ? "#8a5a35" : p.use_type === "commercial" ? "#2c7fb8" : "#0f5a39";
  return iconPin(color, LISTING_ICONS[cat] ?? MapPin, { ...opts, star: !!p.featured });
}

/** Places (points of interest) by category. */
export const PLACE_ICONS: Record<string, { color: string; icon: LucideIcon }> = {
  education: { color: "#2563eb", icon: BookOpen },
  worship: { color: "#059669", icon: Landmark },
  health: { color: "#dc2626", icon: HeartPulse },
  shopping: { color: "#db2777", icon: ShoppingBag },
  park: { color: "#16a34a", icon: Trees },
  bank: { color: "#0d9488", icon: Wallet },
  restaurant: { color: "#ea580c", icon: Utensils },
  transport: { color: "#7c3aed", icon: Bus },
  fuel: { color: "#64748b", icon: Fuel },
  government: { color: "#1e3a8a", icon: Building },
  hotel: { color: "#9333ea", icon: BedDouble },
  sports: { color: "#65a30d", icon: Dumbbell },
};
export function placeBadge(category: string, size = 24): L.DivIcon {
  const c = PLACE_ICONS[category] ?? { color: "#475569", icon: MapPin };
  return iconBadge(c.color, c.icon, size);
}
export function placePin(category: string, size = 30): L.DivIcon {
  const c = PLACE_ICONS[category] ?? { color: "#475569", icon: MapPin };
  return iconPin(c.color, c.icon, { size });
}

function FitPoints({ points, maxZoom = 14 }: { points: [number, number][]; maxZoom?: number }) {
  const map = useMap();
  const sig = points.map((p) => p.join(",")).join("|");
  useEffect(() => {
    if (!points.length) return;
    if (points.length === 1) map.setView(points[0]!, Math.min(maxZoom, 14));
    else map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig]);
  return null;
}

/** Recentre when `center` changes (controlled maps). */
function Recenter({ center, zoom }: { center?: [number, number]; zoom?: number }) {
  const map = useMap();
  useEffect(() => {
    if (center) map.setView(center, zoom ?? map.getZoom(), { animate: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center?.[0], center?.[1], zoom]);
  return null;
}

export function PortalMap({
  center = PAKISTAN_CENTER,
  zoom = 5,
  height = 420,
  className,
  children,
  fit,
  base: baseProp = "streets",
  baseKey,
  switcher = true,
  scrollWheelZoom = false,
  follow,
  onReady,
}: {
  center?: [number, number];
  zoom?: number;
  height?: number | string;
  className?: string;
  children?: ReactNode;
  fit?: [number, number][];
  base?: BaseMapKey;
  /** Controlled base map (the parent renders its own switcher; pass switcher={false}). */
  baseKey?: BaseMapKey;
  switcher?: boolean;
  scrollWheelZoom?: boolean;
  /** Re-center when center/zoom props change. */
  follow?: boolean;
  onReady?: (map: L.Map) => void;
}) {
  const [ownBase, setBase] = useState<BaseMapKey>(baseProp);
  const base = baseKey ?? ownBase;
  const [open, setOpen] = useState(false);
  const bm = BASE_MAPS[base];
  // react-leaflet 4 re-creates the Leaflet map whenever its container ref re-attaches
  // (e.g. a Suspense boundary hiding then revealing this subtree, or Fast Refresh), and
  // Leaflet refuses to init twice on one node. Tear the old instance down when our layout
  // effects are hidden/unmounted and neuter its remove() so react-leaflet's own cleanup
  // doesn't trip over the already-released container.
  const mapRef = useRef<L.Map | null>(null);
  useLayoutEffect(
    () => () => {
      const m = mapRef.current;
      if (!m) return;
      try {
        m.remove();
      } catch {
        /* already detached */
      }
      (m as unknown as { remove: () => L.Map }).remove = () => m;
      mapRef.current = null;
    },
    [],
  );
  return (
    <div className={cn("relative overflow-hidden rounded-2xl", className)} style={{ height }}>
      <MapContainer center={center} zoom={zoom} scrollWheelZoom={scrollWheelZoom} className="h-full w-full"
        ref={(m) => {
          if (m && m !== mapRef.current) {
            mapRef.current = m;
            onReady?.(m);
          }
        }}
      >
        <TileLayer key={base} url={bm.url} attribution={bm.attribution} maxZoom={19} className={"className" in bm ? bm.className : undefined} />
        {fit && <FitPoints points={fit} />}
        {follow && <Recenter center={center} zoom={zoom} />}
        {children}
      </MapContainer>
      {switcher && (
        <div className="absolute end-3 top-3 z-[400]">
          <button onClick={() => setOpen((o) => !o)} className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-brand-800 shadow-soft ring-1 ring-black/5 dark:bg-brand-950 dark:text-white" aria-label="Base map">
            <Layers className="h-5 w-5" />
          </button>
          {open && (
            <div className="mt-2 w-36 overflow-hidden rounded-xl bg-white p-1 shadow-soft ring-1 ring-black/5 dark:bg-brand-950">
              {(Object.keys(BASE_MAPS) as BaseMapKey[]).map((k) => (
                <button
                  key={k}
                  onClick={() => {
                    setBase(k);
                    setOpen(false);
                  }}
                  className={cn("block w-full rounded-lg px-3 py-2 text-left text-sm font-medium", k === base ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/10")}
                >
                  {BASE_MAPS[k].label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
