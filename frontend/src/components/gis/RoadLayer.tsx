/**
 * Pakistan's road network on the map (GET /geo/roads, built from OpenStreetMap):
 * motorways, national highways / trunk roads, primary and secondary roads and those under
 * construction. Loads only what is in view, with detail that follows the zoom, drawn on one
 * canvas; route numbers (M-2, N-5 …) as shields; hover for the name, click for details.
 *
 * Also exports the live road overlay (Esri World Transportation tiles) for satellite view.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { TileLayer, useMap } from "react-leaflet";
import { get } from "@/lib/api";
import { escapeHtml as esc } from "@/lib/utils";
import type { MapLang } from "./PakistanLayers";

export const ROAD_CLASSES = [
  { key: "motorway", label: "Motorways", color: "#e03131", casing: "#8f1d1d", weight: [2.5, 3.5, 5, 7], minZoom: 0 },
  { key: "trunk", label: "National highways & trunk roads", color: "#f76707", casing: "#9c3f00", weight: [2, 3, 4.5, 6], minZoom: 0 },
  { key: "primary", label: "Primary roads", color: "#f59f00", casing: "#8a5a00", weight: [0, 2, 3.5, 5], minZoom: 7 },
  { key: "secondary", label: "Secondary roads", color: "#fcc419", casing: "#8a6d00", weight: [0, 0, 2.5, 4], minZoom: 9 },
] as const;
const CLASS = Object.fromEntries(ROAD_CLASSES.map((c) => [c.key, c]));

interface Road {
  c: string;
  s?: "construction";
  r?: string;
  n?: string;
  u?: string;
  l?: string;
  v?: string;
  f?: string;
  p: [number, number][];
}
interface RoadsResponse {
  count: number;
  truncated?: boolean;
  zoom_band: number;
  roads: Road[];
  missing?: boolean;
  hint?: string;
  meta?: { attribution?: string; extract_date?: string };
}
export interface RoadStatus {
  count: number;
  missing?: boolean;
  hint?: string;
  date?: string;
}

function roadName(r: Road, lang: MapLang): string {
  const name = lang === "ur" ? r.u || r.n : lang === "both" && r.u && r.n ? `${r.n} · ${r.u}` : r.n || r.u;
  return [r.r, name].filter(Boolean).join(" · ") || CLASS[r.c]?.label || "Road";
}

function popupHtml(r: Road): string {
  const rows = [
    ["Road", CLASS[r.c]?.label ?? r.c],
    ["Number", r.r],
    ["Name", r.n],
    ["اردو", r.u],
    ["Lanes", r.l],
    ["Speed limit", r.v ? `${r.v} km/h` : undefined],
    ["Surface", r.f],
    ["Status", r.s === "construction" ? "Under construction" : "Open"],
  ].filter(([, v]) => v);
  return `<div style="min-width:180px"><p style="font-weight:800;margin:0 0 4px">${esc(r.r ? `${r.r}${r.n ? ` — ${r.n}` : ""}` : r.n || CLASS[r.c]?.label || "Road")}</p>
    <table style="font-size:12px">${rows.map(([k, v]) => `<tr><td style="color:#64748b;padding-right:8px">${esc(k!)}</td><td>${esc(String(v))}</td></tr>`).join("")}</table>
    <p style="font-size:10px;color:#94a3b8;margin:4px 0 0">© OpenStreetMap contributors</p></div>`;
}

function shield(ref: string): L.DivIcon {
  const motorway = /^M-?\d/i.test(ref);
  const bg = motorway ? "#2b8a3e" : /^N-?\d/i.test(ref) ? "#1c4a8f" : "#475569";
  const w = Math.max(28, ref.length * 7 + 10);
  return L.divIcon({
    className: "",
    iconSize: [w, 18],
    iconAnchor: [w / 2, 9],
    html: `<span style="display:flex;align-items:center;justify-content:center;width:${w}px;height:18px;border-radius:5px;background:${bg};color:#fff;font:800 10px/1 system-ui;border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)">${esc(ref)}</span>`,
  });
}

/** Roads in view. `classes` limits the road classes; `construction` adds roads being built. */
export function RoadLayer({
  classes,
  construction,
  shields,
  lang,
  onStatus,
}: {
  classes: Set<string>;
  construction: boolean;
  shields: boolean;
  lang: MapLang;
  onStatus?: (s: RoadStatus) => void;
}) {
  const map = useMap();
  const [data, setData] = useState<RoadsResponse | null>(null);
  const group = useRef<L.LayerGroup | null>(null);
  const renderer = useMemo(() => L.canvas({ padding: 0.3, tolerance: 4 }), []);
  const key = [...classes].sort().join(",");
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;

  // Pane between the base map and the portal's own overlays.
  useEffect(() => {
    if (!map.getPane("roads")) {
      const p = map.createPane("roads");
      p.style.zIndex = "390";
    }
    const g = L.layerGroup().addTo(map);
    group.current = g;
    return () => {
      g.remove();
      group.current = null;
    };
  }, [map]);

  // Load the roads in view (debounced; the newest request wins).
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
          const r = await get<RoadsResponse>(
            "/geo/roads",
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

  // Draw.
  useEffect(() => {
    const g = group.current;
    if (!g) return;
    g.clearLayers();
    if (!data?.roads.length) return;
    const band = data.zoom_band;
    const rows = data.roads.filter((r) => classes.has(r.c) && (construction || r.s !== "construction"));
    // Lower classes first so motorways draw on top.
    const order = ["secondary", "primary", "trunk", "motorway"];
    rows.sort((a, b) => order.indexOf(a.c) - order.indexOf(b.c));
    for (const r of rows) {
      const c = CLASS[r.c];
      if (!c) continue;
      const w = c.weight[band] || 1.5;
      const building = r.s === "construction";
      L.polyline(r.p, { renderer, pane: "roads", color: c.casing, weight: w + 2, opacity: building ? 0.35 : 0.85, interactive: false, lineCap: "round" }).addTo(g);
      L.polyline(r.p, { renderer, pane: "roads", color: building ? "#ffffff" : c.color, weight: w, opacity: 1, dashArray: building ? "6 6" : undefined, lineCap: "round" })
        .bindTooltip(esc(roadName(r, lang)) + (building ? " (under construction)" : ""), { sticky: true, className: "mega-tip" })
        .bindPopup(popupHtml(r))
        .addTo(g);
    }
    // Route-number shields: one per number per screen cell.
    if (shields && map.getZoom() >= 7) {
      const cell = 180;
      const seen = new Set<string>();
      for (const r of rows) {
        if (!r.r || (r.c !== "motorway" && r.c !== "trunk") || r.p.length < 2) continue;
        const ref = r.r.split(";")[0]!.trim();
        const mid = r.p[Math.floor(r.p.length / 2)]!;
        const pt = map.latLngToContainerPoint(mid);
        const k = `${ref}:${Math.floor(pt.x / cell)}:${Math.floor(pt.y / cell)}`;
        if (seen.has(k) || !map.getBounds().contains(mid)) continue;
        seen.add(k);
        L.marker(mid, { icon: shield(ref), interactive: false, pane: "roads", keyboard: false }).addTo(g);
      }
    }
  }, [data, classes, construction, shields, lang, map, renderer]);

  return null;
}

/** Live road overlay (Esri World Transportation): roads and labels over any base map, incl. satellite. */
export function LiveRoadOverlay() {
  return (
    <TileLayer
      url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}"
      attribution="Roads overlay: Esri, HERE, Garmin, © OpenStreetMap contributors"
      maxNativeZoom={19}
      maxZoom={20}
      zIndex={350}
      opacity={0.9}
    />
  );
}
