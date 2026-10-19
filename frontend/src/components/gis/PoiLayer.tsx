/**
 * Points of interest from the portal's OpenStreetMap place data (GET /geo/places): schools,
 * mosques, hospitals, markets, parks, banks … in the visible area, reloaded as you pan.
 * Coloured dots on one canvas while zoomed out (cheap even for 1,500 places); from street level
 * (zoom 15) each place gets its category icon; names are written on the map when zoomed in.
 */
import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import type { FeatureCollection } from "geojson";
import { CircleMarker, Marker, Tooltip, useMap } from "react-leaflet";
import { iconBadge } from "@/components/map/PortalMap";
import { BookOpen, Building, Bus, Fuel, HeartPulse, Landmark, ShoppingBag, Trees, Utensils, Wallet, type LucideIcon } from "lucide-react";
import { get } from "@/lib/api";
import { PlanLabels } from "./MasterPlans";
import { labelText, type MapLang } from "./PakistanLayers";

export const POI_CATEGORIES: { key: string; label: string; color: string; icon: LucideIcon }[] = [
  { key: "education", label: "Schools & colleges", color: "#2563eb", icon: BookOpen },
  { key: "worship", label: "Mosques", color: "#059669", icon: Landmark },
  { key: "health", label: "Hospitals & clinics", color: "#dc2626", icon: HeartPulse },
  { key: "shopping", label: "Malls & markets", color: "#db2777", icon: ShoppingBag },
  { key: "park", label: "Parks", color: "#16a34a", icon: Trees },
  { key: "bank", label: "Banks", color: "#0d9488", icon: Wallet },
  { key: "restaurant", label: "Food", color: "#ea580c", icon: Utensils },
  { key: "transport", label: "Transport", color: "#7c3aed", icon: Bus },
  { key: "fuel", label: "Fuel", color: "#64748b", icon: Fuel },
  { key: "government", label: "Government", color: "#1e3a8a", icon: Building },
];
const COLOR = Object.fromEntries(POI_CATEGORIES.map((c) => [c.key, c.color]));
const ICON = Object.fromEntries(POI_CATEGORIES.map((c) => [c.key, c.icon]));
/** From this zoom places show their category icon instead of a dot. */
export const POI_ICON_ZOOM = 15;
export const POI_MIN_ZOOM = 14;

interface Place {
  name: string;
  name_ur?: string | null;
  category: string;
  kind_label: string;
  lat: number;
  lon: number;
}

export function PoiLayer({ categories, onStatus, lang = "en" }: { categories: Set<string>; onStatus?: (s: { count: number; total: number; zoomIn: boolean }) => void; lang?: MapLang }) {
  const map = useMap();
  const [places, setPlaces] = useState<Place[]>([]);
  const [zoom, setZoom] = useState(map.getZoom());
  const renderer = useMemo(() => L.canvas({ padding: 0.3 }), []);
  const cats = [...categories].sort().join(",");

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ctrl: AbortController | undefined;
    const load = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const z = map.getZoom();
        setZoom(z);
        if (z < POI_MIN_ZOOM || !cats) {
          setPlaces([]);
          onStatus?.({ count: 0, total: 0, zoomIn: z < POI_MIN_ZOOM });
          return;
        }
        const b = map.getBounds().pad(0.15);
        ctrl?.abort();
        ctrl = new AbortController();
        try {
          const r = await get<{ places: Place[]; total: number }>(
            "/geo/places",
            { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast(), categories: cats, limit: 1500 },
            { signal: ctrl.signal, noFallback: true },
          );
          setPlaces(r.places);
          onStatus?.({ count: r.places.length, total: r.total, zoomIn: false });
        } catch {
          /* aborted or offline: keep what is shown */
        }
      }, 250);
    };
    load();
    map.on("moveend", load);
    return () => {
      clearTimeout(timer);
      ctrl?.abort();
      map.off("moveend", load);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, cats]);

  // Names as text (same renderer as the plan labels): readable from zoom 17.
  const names = useMemo<FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: places.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat + 0.00006] }, properties: { text: labelText(p.name, p.name_ur, lang), size_m: 5, rot: 0 } })),
    }),
    [places, lang],
  );

  return (
    <>
      {zoom >= POI_ICON_ZOOM &&
        places.map((p, i) => (
          <Marker key={`i${p.lat},${p.lon},${i}`} position={[p.lat, p.lon]} icon={iconBadge(COLOR[p.category] ?? "#475569", ICON[p.category] ?? Building, zoom >= 17 ? 26 : 22)}>
            <Tooltip direction="top" offset={[0, -10]}>
              <b>{labelText(p.name, p.name_ur, lang)}</b> · {p.kind_label}
            </Tooltip>
          </Marker>
        ))}
      {zoom < POI_ICON_ZOOM && places.map((p, i) => (
        <CircleMarker
          key={`${p.lat},${p.lon},${i}`}
          center={[p.lat, p.lon]}
          radius={zoom >= 17 ? 6 : 4.5}
          renderer={renderer}
          pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: COLOR[p.category] ?? "#475569", fillOpacity: 0.95 }}
        >
          <Tooltip direction="top" offset={[0, -4]}>
            <b>{labelText(p.name, p.name_ur, lang)}</b> · {p.kind_label}
          </Tooltip>
        </CircleMarker>
      ))}
      {zoom >= 17 && names.features.length > 0 && <PlanLabels data={names} color="#334155" />}
    </>
  );
}
