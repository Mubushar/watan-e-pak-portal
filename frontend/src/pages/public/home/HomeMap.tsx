/** The home page's listings + places map (its own chunk: Leaflet loads when it scrolls into view). */
import { Link } from "react-router-dom";
import { Marker, Popup } from "react-leaflet";
import type { Property } from "@/types";
import { pkrShort } from "@/lib/format";
import { coverImage } from "@/lib/images";
import { PortalMap, pin } from "@/components/map/PortalMap";

export interface HomePoi {
  id: string;
  name: string;
  category: string;
  latitude: number;
  longitude: number;
}

export default function HomeMap({ pts, pois, layers, fit }: { pts: Property[]; pois: HomePoi[]; layers: string[]; fit: [number, number][] }) {
  return (
    <PortalMap height={420} fit={fit} className="rounded-none" scrollWheelZoom={false}>
      {layers.includes("property") &&
        pts.map((p) => (
          <Marker key={p.id} position={[p.latitude!, p.longitude!]} icon={pin(p.featured ? "featured" : p.use_type === "commercial" ? "commercial" : "property")}>
            <Popup>
              <Link to={`/properties/${p.id}`} className="block">
                <img src={coverImage(p)} alt="" className="h-28 w-full object-cover" />
                <div className="p-3">
                  <p className="font-semibold text-ink">{p.title}</p>
                  <p className="text-xs text-ink-mute">{[p.scheme_name, p.city_name].filter(Boolean).join(", ")}</p>
                  <p className="mt-1 font-bold text-brand-700">{pkrShort(p.price)}</p>
                </div>
              </Link>
            </Popup>
          </Marker>
        ))}
      {pois
        .filter((x) => layers.includes(x.category))
        .map((x) => (
          <Marker key={x.id} position={[x.latitude, x.longitude]} icon={pin(x.category, { size: 26 })}>
            <Popup>
              <div className="p-3">
                <p className="font-semibold">{x.name}</p>
                <p className="text-xs capitalize text-ink-mute">{x.category}</p>
              </div>
            </Popup>
          </Marker>
        ))}
    </PortalMap>
  );
}
