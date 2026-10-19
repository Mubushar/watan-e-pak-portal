/**
 * Pakistan reference layers for the map explorer.
 *   GET /geo/provinces   provinces & territories (GeoJSON) with the portal's listing count
 *   GET /geo/cities      main cities: name, province, population; `portal` = has a city page
 * Provinces are soft-filled shapes with their name in the middle; city names thin out by size
 * as you zoom out so the country view stays readable.
 */
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import L from "leaflet";
import type { FeatureCollection } from "geojson";
import { GeoJSON, Marker, Tooltip } from "react-leaflet";
import { useApi } from "@/hooks/useApi";
import { compact } from "@/lib/format";
import { escapeHtml } from "@/lib/utils";

const PROVINCE_COLORS: Record<string, string> = {
  Punjab: "#16a34a",
  Sindh: "#0ea5e9",
  "Khyber Pakhtunkhwa": "#f59e0b",
  Balochistan: "#a855f7",
  "Gilgit-Baltistan": "#14b8a6",
  "Azad Kashmir": "#ef4444",
  "Islamabad Capital Territory": "#c99a22",
};

/** Map label language: English, Urdu, or both. */
export type MapLang = "en" | "ur" | "both";

/** Label HTML in the chosen language(s); Urdu is right-to-left in the Nastaliq font. Names are escaped. */
export function labelHtml(en: string, ur: string | null | undefined, lang: MapLang): string {
  const e = escapeHtml(en);
  const u = ur ? `<span class="map-ur" dir="rtl">${escapeHtml(ur)}</span>` : "";
  if (lang === "ur") return u || e;
  if (lang === "both" && u) return `<span>${e}</span>${u}`;
  return e;
}
/** Plain-text label in the chosen language(s) (canvas text, tooltips). */
export function labelText(en: string, ur: string | null | undefined, lang: MapLang): string {
  if (!ur || lang === "en") return en;
  return lang === "ur" ? ur : `${en} · ${ur}`;
}

export interface PkCity {
  name: string;
  name_ur?: string | null;
  province_ur?: string | null;
  province: string;
  population: number;
  rank: number;
  capital: boolean;
  lat: number;
  lon: number;
  portal: boolean;
}

export function useProvinces(enabled: boolean) {
  return useApi<FeatureCollection & { attribution?: string }>(enabled ? "/geo/provinces" : null, undefined, { staleTime: 60 * 60_000 });
}
export function useCities(enabled: boolean) {
  return useApi<{ count: number; attribution?: string; cities: PkCity[] }>(enabled ? "/geo/cities" : null, undefined, { staleTime: 60 * 60_000 });
}

/** Small territories get their name only when zoomed in enough not to cover their neighbours. */
const LABEL_FROM_ZOOM: Record<string, number> = { "Islamabad Capital Territory": 9, "Azad Kashmir": 7 };

/** Province & territory boundaries with names; click one to zoom to it. */
export function ProvinceLayer({ map, lang = "en", zoom = 5 }: { map: L.Map | null; lang?: MapLang; zoom?: number }) {
  const q = useProvinces(true);
  const hidden = Object.entries(LABEL_FROM_ZOOM)
    .filter(([, z]) => zoom < z)
    .map(([n]) => n)
    .join("|");
  if (!q.data) return null;
  return (
    <GeoJSON
      key={`${q.data.features.length}-${lang}-${hidden}`}
      data={q.data}
      attribution={q.data.attribution}
      style={(f) => {
        const c = PROVINCE_COLORS[String(f?.properties?.name)] ?? "#64748b";
        return { color: c, weight: 1.6, opacity: 0.9, fillColor: c, fillOpacity: 0.07, dashArray: "5 4" };
      }}
      onEachFeature={(f, layer) => {
        const p = f.properties as { name: string; name_ur?: string; listings?: number };
        const count = p.listings ? (lang === "ur" ? `${p.listings} اشتہارات` : `${p.listings} listing${p.listings === 1 ? "" : "s"}`) : "";
        if (!hidden.split("|").includes(p.name)) layer.bindTooltip(
          `<div class="province-inner">${labelHtml(p.name, p.name_ur, lang)}${count ? `<span class="province-count">${escapeHtml(count)}</span>` : ""}</div>`,
          { permanent: true, direction: "center", className: "province-label", interactive: false },
        );
        layer.on("click", () => {
          const b = (layer as L.Polygon).getBounds();
          if (map && b.isValid()) map.flyToBounds(b, { padding: [40, 40], maxZoom: 9, duration: 0.8 });
        });
      }}
    />
  );
}

/** Which cities to show at a zoom: big ones from afar, all of them up close. */
const minRankFor = (zoom: number) => (zoom <= 5 ? 3 : zoom <= 6 ? 5 : zoom <= 7 ? 7 : 10);

/** City names with a dot; portal cities link to their city page. */
export function CityLabels({ zoom, lang = "en" }: { zoom: number; lang?: MapLang }) {
  const q = useCities(true);
  const nav = useNavigate();
  const maxRank = minRankFor(zoom);
  const shown = useMemo(() => (q.data?.cities ?? []).filter((c) => c.rank <= maxRank || (c.portal && zoom >= 6)), [q.data, maxRank, zoom]);
  return (
    <>
      {shown.map((c) => (
        <Marker
          key={c.name}
          position={[c.lat, c.lon]}
          icon={L.divIcon({
            className: "city-label",
            html: `<span class="city-dot${c.portal ? " is-portal" : ""}"></span><span class="city-name${c.population >= 1_000_000 ? " is-big" : ""}">${labelHtml(c.name, c.name_ur, lang)}</span>`,
            iconSize: [0, 0],
          })}
          eventHandlers={{ click: () => c.portal && nav(`/cities/${encodeURIComponent(c.name)}`) }}
          keyboard={false}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <b>{labelText(c.name, c.name_ur, lang)}</b> · {labelText(c.province, c.province_ur, lang)}
            <br />
            Population ~{compact(c.population)}
            {c.portal && <> · open city page</>}
          </Tooltip>
        </Marker>
      ))}
    </>
  );
}
