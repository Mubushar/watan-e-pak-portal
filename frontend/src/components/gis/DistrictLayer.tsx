/**
 * Pakistan's district boundaries (GET /geo/districts, from OpenStreetMap admin_level 6, plus
 * Islamabad Capital Territory). Thin outlines on a canvas; hover highlights a district and shows
 * its province, area and listing count; click zooms to it. Names show from zoom 7.
 */
import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import type { FeatureCollection, MultiPolygon, Polygon } from "geojson";
import { useMap } from "react-leaflet";
import { useApi } from "@/hooks/useApi";
import { labelHtml, labelText, type MapLang } from "./PakistanLayers";

export const DISTRICT_LABEL_ZOOM = 7;

interface DistrictProps {
  name: string;
  name_ur?: string | null;
  province: string;
  area_km2?: number;
  label?: [number, number];
  listings?: number;
}
type Districts = FeatureCollection<Polygon | MultiPolygon, DistrictProps> & { missing?: boolean; hint?: string; meta?: { extract_date?: string } };

export function useDistricts(enabled: boolean) {
  return useApi<Districts>(enabled ? "/geo/districts" : null, undefined, { staleTime: 60 * 60_000 });
}

export function DistrictLayer({ lang, zoom, labels }: { lang: MapLang; zoom: number; labels: boolean }) {
  const map = useMap();
  const q = useDistricts(true);
  const renderer = useMemo(() => L.canvas({ padding: 0.3, tolerance: 3 }), []);
  const group = useRef<L.LayerGroup | null>(null);
  const showLabels = labels && zoom >= DISTRICT_LABEL_ZOOM;

  useEffect(() => {
    if (!map.getPane("districts")) map.createPane("districts").style.zIndex = "395";
    const g = L.layerGroup().addTo(map);
    group.current = g;
    return () => {
      g.remove();
      group.current = null;
    };
  }, [map]);

  // Outlines (rebuilt only when the data or language changes).
  useEffect(() => {
    const g = group.current;
    if (!g || !q.data?.features?.length) return;
    const base: L.PathOptions = { color: "#6741d9", weight: 1.1, opacity: 0.75, dashArray: "4 3", fillColor: "#7950f2", fillOpacity: 0.02 };
    const layer = L.geoJSON(q.data, {
      pane: "districts",
      style: () => ({ ...base, renderer }) as L.PathOptions,
      onEachFeature: (f, l) => {
        const p = f.properties as DistrictProps;
        const n = p.listings ?? 0;
        l.bindTooltip(
          `<b>${labelText(p.name, p.name_ur, lang)}</b><br>${p.province}${p.area_km2 ? ` · ${Math.round(p.area_km2).toLocaleString()} km²` : ""}${n ? `<br>${n} listing${n === 1 ? "" : "s"} on the portal` : ""}`,
          { sticky: true, className: "mega-tip" },
        );
        l.on("mouseover", () => (l as L.Path).setStyle({ weight: 2.5, opacity: 1, dashArray: "", fillOpacity: 0.12 }));
        l.on("mouseout", () => (l as L.Path).setStyle(base));
        l.on("click", () => map.flyToBounds((l as L.Polygon).getBounds(), { padding: [40, 40], maxZoom: 11, duration: 0.8 }));
      },
    });
    g.addLayer(layer);
    return () => {
      g.removeLayer(layer);
    };
  }, [q.data, lang, map, renderer]);

  // Names (only when zoomed in enough to read them).
  useEffect(() => {
    const g = group.current;
    if (!g || !showLabels || !q.data?.features?.length) return;
    const markers = q.data.features
      .filter((f) => f.properties.label)
      .map((f) =>
        L.marker(f.properties.label!, {
          pane: "districts",
          interactive: false,
          keyboard: false,
          icon: L.divIcon({ className: "district-label", html: `<span>${labelHtml(f.properties.name, f.properties.name_ur, lang)}</span>`, iconSize: [0, 0] }),
        }),
      );
    markers.forEach((m) => g.addLayer(m));
    return () => markers.forEach((m) => g.removeLayer(m));
  }, [q.data, showLabels, lang]);

  return null;
}
