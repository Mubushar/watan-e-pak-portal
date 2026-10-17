/** Backend payload shapes used by the app (same as the web portal's src/types.ts). */

export interface Property {
  id: string;
  title: string;
  description?: string | null;
  price: number;
  currency?: string;
  use_type: string;
  category: string;
  status: string;
  featured?: boolean;
  total_area?: number | null;
  marla_area?: number | null;
  kanal_area?: number | null;
  city_id?: string | null;
  scheme_id?: string | null;
  block_zone_area_id?: string | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  floors?: number | null;
  street_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  image_urls?: string[];
  amenities?: string[];
  /** Set by /search?near=…: the matching place and how far it is. */
  nearby?: NearbyPlace;
  agent_id?: string | null;
  owner_user_id?: string | null;
  created_at?: string;
  city_name?: string | null;
  scheme_name?: string | null;
  block_name?: string | null;
  price_per_sqft?: number | null;
}

export interface PropertyList {
  count: number;
  returned: number;
  results: Property[];
}

export interface City {
  id: string;
  name: string;
  state?: string;
  latitude: number;
  longitude: number;
  schemes: number;
  properties: number;
}

export interface Hierarchy {
  tree: { id: string; name: string; schemes: { id: string; name: string; blocks: { id: string; name: string; area_type: string }[] }[] }[];
}

/** A place near a listing (GET /properties/{id}/nearby, or /search?near=…). */
export interface NearbyPlace {
  category: string;
  kind: string;
  name: string;
  distance_km: number;
  walk_minutes: number;
}
export interface NearbyList {
  property_id: string;
  radius_km: number;
  nearby: NearbyPlace[];
}

/** A map card: a listing or place with nearby places (GET /places/map). */
export interface MapMarker {
  name: string;
  kind: string;
  category: string;
  group: string;
  latitude: number;
  longitude: number;
  distance_km?: number;
  walk_minutes?: number;
}
export interface MapView {
  focus: { type: "listing" | "place"; id?: string; name: string; latitude: number; longitude: number; price?: number; city?: string };
  radius_km: number;
  kinds: string[];
  markers: MapMarker[];
  listings?: { id: string; name: string; latitude: number; longitude: number; price: number; distance_km: number }[];
  tiles: { url: string; attribution: string };
}
