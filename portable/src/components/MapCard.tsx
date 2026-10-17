/**
 * A map card: a listing (or a place) with the nearest schools, mosques, parks, malls,
 * hospitals … as coloured markers. Used in the assistant's replies (show_map) and on the
 * listing page. Data from GET /places/map; Leaflet is loaded only when a map is shown.
 */
import { useEffect, useRef, useState } from "react";
import { ExternalLink, MapPinned } from "lucide-react";
import type { Map as LeafletMap } from "leaflet";
import type { MapView } from "@/types";
import { pkrShort } from "@/lib/format";
import { cn } from "@/lib/utils";

const GROUPS: Record<string, { label: string; color: string; glyph: string }> = {
  school: { label: "School", color: "#2563eb", glyph: "🏫" },
  "high school": { label: "High school", color: "#2563eb", glyph: "🏫" },
  "primary school": { label: "Primary school", color: "#2563eb", glyph: "🏫" },
  college: { label: "College", color: "#4f46e5", glyph: "🎓" },
  university: { label: "University", color: "#4f46e5", glyph: "🎓" },
  "medical college": { label: "Medical college", color: "#4f46e5", glyph: "🎓" },
  kindergarten: { label: "Kindergarten", color: "#0ea5e9", glyph: "🧸" },
  mosque: { label: "Mosque", color: "#059669", glyph: "🕌" },
  masjid: { label: "Mosque", color: "#059669", glyph: "🕌" },
  park: { label: "Park", color: "#16a34a", glyph: "🌳" },
  sports: { label: "Sports", color: "#16a34a", glyph: "🏏" },
  mall: { label: "Mall", color: "#db2777", glyph: "🛍️" },
  market: { label: "Market", color: "#db2777", glyph: "🛒" },
  supermarket: { label: "Supermarket", color: "#db2777", glyph: "🛒" },
  hospital: { label: "Hospital", color: "#dc2626", glyph: "🏥" },
  clinic: { label: "Clinic", color: "#dc2626", glyph: "⚕️" },
  pharmacy: { label: "Pharmacy", color: "#dc2626", glyph: "💊" },
  bank: { label: "Bank", color: "#0d9488", glyph: "🏦" },
  restaurant: { label: "Restaurant", color: "#ea580c", glyph: "🍽️" },
  cafe: { label: "Café", color: "#ea580c", glyph: "☕" },
  transport: { label: "Transport", color: "#7c3aed", glyph: "🚌" },
  station: { label: "Station", color: "#7c3aed", glyph: "🚉" },
  fuel: { label: "Fuel", color: "#64748b", glyph: "⛽" },
  petrol: { label: "Fuel", color: "#64748b", glyph: "⛽" },
  police: { label: "Police", color: "#1e3a8a", glyph: "🚓" },
  government: { label: "Government", color: "#1e3a8a", glyph: "🏛️" },
};
const group = (g: string) => GROUPS[g] ?? { label: g, color: "#475569", glyph: "📍" };

const pin = (color: string, glyph: string, size = 30) =>
  `<div style="width:${size}px;height:${size}px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);display:grid;place-items:center">` +
  `<span style="transform:rotate(45deg);font-size:${Math.round(size * 0.5)}px;line-height:1">${glyph}</span></div>`;

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export function MapCard({ view, className, height = 260 }: { view: MapView; className?: string; height?: number }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const L = (await import("leaflet")).default;
        await import("leaflet/dist/leaflet.css");
        if (cancelled || !el.current || map.current) return;
        const m = L.map(el.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
        map.current = m;
        L.tileLayer(view.tiles.url, { attribution: view.tiles.attribution, maxZoom: 19 }).addTo(m);
        const f = view.focus;
        const bounds = L.latLngBounds([[f.latitude, f.longitude]]);
        L.marker([f.latitude, f.longitude], {
          icon: L.divIcon({ className: "", html: pin("#c99a22", f.type === "listing" ? "🏠" : "📍", 38), iconSize: [38, 38], iconAnchor: [19, 38], popupAnchor: [0, -34] }),
          zIndexOffset: 1000,
        })
          .addTo(m)
          .bindPopup(`<b>${esc(f.name)}</b>${f.price ? `<br>${esc(pkrShort(f.price))}` : ""}`);
        for (const p of view.markers) {
          const g = group(p.group);
          L.marker([p.latitude, p.longitude], { icon: L.divIcon({ className: "", html: pin(g.color, g.glyph), iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -26] }) })
            .addTo(m)
            .bindPopup(`<b>${esc(p.name)}</b><br>${esc(g.label)}${p.distance_km != null ? ` · ${p.distance_km} km (~${p.walk_minutes} min walk)` : ""}`);
          bounds.extend([p.latitude, p.longitude]);
        }
        for (const l of view.listings ?? []) {
          L.marker([l.latitude, l.longitude], { icon: L.divIcon({ className: "", html: pin("#065f46", "🏠"), iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -26] }) })
            .addTo(m)
            .bindPopup(`<b>${esc(l.name)}</b><br>${esc(pkrShort(l.price))} · ${l.distance_km} km`);
          bounds.extend([l.latitude, l.longitude]);
        }
        m.fitBounds(bounds.pad(0.15), { maxZoom: 16 });
        setTimeout(() => m.invalidateSize(), 150);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, [view]);

  const legend = Array.from(new Map(view.markers.map((p) => [group(p.group).label, group(p.group)])).values());
  const gmaps = `https://www.google.com/maps/search/?api=1&query=${view.focus.latitude},${view.focus.longitude}`;
  return (
    <div className={cn("overflow-hidden rounded-xl border border-black/5 bg-white dark:border-white/10 dark:bg-black/20", className)}>
      {failed ? (
        <div className="grid place-items-center gap-1 p-6 text-center text-sm text-ink-mute" style={{ height }}>
          <MapPinned className="h-6 w-6" />
          The map couldn't load (no internet?).
        </div>
      ) : (
        <div ref={el} style={{ height }} className="z-0 w-full" aria-label={`Map of ${view.focus.name} and nearby places`} />
      )}
      <div className="flex flex-wrap items-center gap-1.5 px-2.5 py-2">
        <span className="chip bg-gold-100 px-2 py-0.5 text-[11px] text-gold-800 dark:bg-gold-500/15 dark:text-gold-200">
          {view.focus.type === "listing" ? "🏠" : "📍"} {view.focus.name}
        </span>
        {legend.map((g) => (
          <span key={g.label} className="chip px-2 py-0.5 text-[11px]" style={{ background: `${g.color}1a`, color: g.color }}>
            {g.glyph} {g.label}
          </span>
        ))}
        <a href={gmaps} target="_blank" rel="noreferrer" className="ms-auto inline-flex items-center gap-1 text-[11px] font-semibold text-brand-700 hover:underline dark:text-brand-300">
          Open in Google Maps <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}
