/** A small map card under an assistant reply (show_map). Loaded on demand with Leaflet. */
import { CircleMarker, Marker, Tooltip } from "react-leaflet";
import type { MapCard } from "@/lib/agent";
import { PortalMap, pin } from "@/components/map/PortalMap";

export default function ChatMap({ map, height }: { map: MapCard; height: number }) {
  return (
    <PortalMap center={[map.focus.latitude, map.focus.longitude]} zoom={14} height={height} switcher={false}>
      <Marker position={[map.focus.latitude, map.focus.longitude]} icon={pin("featured", { size: 32 })} />
      {map.markers.map((mk, k) => (
        <CircleMarker key={k} center={[mk.latitude, mk.longitude]} radius={6} pathOptions={{ color: "#146f45", weight: 2, fillColor: "#f2dd8f", fillOpacity: 0.9 }}>
          <Tooltip>
            {mk.name} · {mk.kind}
            {mk.distance_km !== undefined ? ` · ${mk.distance_km} km` : ""}
          </Tooltip>
        </CircleMarker>
      ))}
    </PortalMap>
  );
}
