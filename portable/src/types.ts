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
