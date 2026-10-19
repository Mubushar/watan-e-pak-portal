/**
 * Pakistan's water bodies on the map (GET /geo/water, built from OpenStreetMap): rivers and
 * canals as lines; lakes, reservoirs, river beds and ponds as areas. Loads only what is in view,
 * thinned by zoom, drawn on one canvas. Hover for the name, click for details; big lakes and
 * reservoirs get a name label when zoomed in.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { useMap } from "react-leaflet";
import { get } from "@/lib/api";
import { escapeHtml as esc } from "@/lib/utils";
import { labelText, type MapLang } from "./PakistanLayers";

export const WATER_CLASSES = [
  { key: "river", label: "Rivers", color: "#1c7ed6", hint: "Named rivers at every zoom; all from zoom 9" },
  { key: "canal", label: "Canals", color: "#22b8cf", hint: "Named canals from zoom 7; all from zoom 9" },
  { key: "reservoir", label: "Dams & reservoirs", color: "#1971c2", hint: "Tarbela, Mangla, Warsak …" },
  { key: "lake", label: "Lakes", color: "#4dabf7", hint: "Natural lakes and other open water" },
  { key: "riverbed", label: "River beds", color: "#74c0fc", hint: "The wide beds of the Indus and other rivers" },
  { key: "pond", label: "Ponds & basins", color: "#a5d8ff", hint: "From zoom 9" },
] as const;
const CLASS = Object.fromEntries(WATER_CLASSES.map((c) => [c.key, c]));
const AREAS = new Set(["lake", "reservoir", "riverbed", "pond"]);
const KIND: Record<string, string> = { river: "River", canal: "Canal", reservoir: "Dam / reservoir", lake: "Lake", riverbed: "River bed", pond: "Pond / basin" };

interface Water {
  c: string;
  n?: string;
  u?: string;
  a?: number;
  p: [number, number][];
}
interface WaterResponse {
  count: number;
  zoom_band: number;
  water: Water[];
  missing?: boolean;
  hint?: string;
  meta?: { extract_date?: string };
}
export interface WaterStatus {
  count: number;
  missing?: boolean;
  hint?: string;
  date?: string;
}

function popupHtml(w: Water): string {
  const rows = [
    ["Type", KIND[w.c] ?? w.c],
    ["Name", w.n],
    ["اردو", w.u],
    ["Area", w.a ? `${w.a >= 10 ? Math.round(w.a).toLocaleString() : w.a.toFixed(2)} km²` : undefined],
  ].filter(([, v]) => v);
  return `<div style="min-width:160px"><p style="font-weight:800;margin:0 0 4px">${esc(w.n || w.u || KIND[w.c] || "Water")}</p>
    <table style="font-size:12px">${rows.map(([k, v]) => `<tr><td style="color:#64748b;padding-right:8px">${esc(k!)}</td><td>${esc(String(v))}</td></tr>`).join("")}</table>
    <p style="font-size:10px;color:#94a3b8;margin:4px 0 0">© OpenStreetMap contributors</p></div>`;
}

export function WaterLayer({ classes, labels, lang, onStatus }: { classes: Set<string>; labels: boolean; lang: MapLang; onStatus?: (s: WaterStatus) => void }) {
  const map = useMap();
  const [data, setData] = useState<WaterResponse | null>(null);
  const group = useRef<L.LayerGroup | null>(null);
  const renderer = useMemo(() => L.canvas({ padding: 0.3, tolerance: 4 }), []);
  const key = [...classes].sort().join(",");
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;

  useEffect(() => {
    if (!map.getPane("water")) map.createPane("water").style.zIndex = "385";
    const g = L.layerGroup().addTo(map);
    group.current = g;
    return () => {
      g.remove();
      group.current = null;
    };
  }, [map]);

  useEffect(() => {
    if (!key) {
      setData(null);
      return;
    }
    let seq = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const id = ++seq;
        const b = map.getBounds();
        try {
          const r = await get<WaterResponse>(
            "/geo/water",
            { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast(), zoom: Math.round(map.getZoom()), classes: key },
            { noFallback: true },
          );
          if (id === seq) {
            setData(r);
            statusRef.current?.({ count: r.count, missing: r.missing, hint: r.hint, date: r.meta?.extract_date });
          }
        } catch {
          /* keep what is drawn */
        }
      }, 250);
    };
    load();
    map.on("moveend", load);
    return () => {
      clearTimeout(timer);
      map.off("moveend", load);
    };
  }, [map, key]);

  useEffect(() => {
    const g = group.current;
    if (!g) return;
    g.clearLayers();
    if (!data?.water.length) return;
    const band = data.zoom_band;
    const z = map.getZoom();
    // Areas first, then canals, then rivers on top.
    const rank = (w: Water) => (AREAS.has(w.c) ? 0 : w.c === "canal" ? 1 : 2);
    const rows = data.water.filter((w) => classes.has(w.c)).sort((a, b) => rank(a) - rank(b));
    for (const w of rows) {
      const c = CLASS[w.c];
      if (!c) continue;
      const name = w.n || w.u ? labelText(w.n || w.u!, w.n ? w.u : undefined, lang) : KIND[w.c];
      const layer = AREAS.has(w.c)
        ? L.polygon(w.p, { renderer, pane: "water", color: "#1c7ed6", weight: 1, opacity: 0.7, fillColor: c.color, fillOpacity: 0.55 })
        : L.polyline(w.p, {
            renderer,
            pane: "water",
            color: c.color,
            weight: w.c === "river" ? [1.5, 2, 2.5, 3.5][band]! : [1, 1.2, 1.6, 2.5][band]!,
            opacity: 0.95,
            lineCap: "round",
          });
      layer.bindTooltip(esc(name), { sticky: true, className: "mega-tip" }).bindPopup(popupHtml(w)).addTo(g);
    }
    // Name labels for the larger lakes and reservoirs.
    if (labels && z >= 9) {
      for (const w of rows) {
        if (!AREAS.has(w.c) || w.c === "riverbed" || !(w.n || w.u) || (w.a ?? 0) < (z >= 12 ? 0.05 : 1)) continue;
        const center = L.polygon(w.p).getBounds().getCenter();
        if (!map.getBounds().contains(center)) continue;
        const text = labelText(w.n || w.u!, w.n ? w.u : undefined, lang);
        L.marker(center, {
          pane: "water",
          interactive: false,
          keyboard: false,
          icon: L.divIcon({ className: "water-label", html: `<span>${esc(text)}</span>`, iconSize: [0, 0] }),
        }).addTo(g);
      }
    }
  }, [data, classes, labels, lang, map, renderer]);

  return null;
}
