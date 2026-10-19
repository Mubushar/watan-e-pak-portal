/** Shapes of the most-used backend payloads (fields observed on the live API). */

export interface Property {
  id: string;
  title: string;
  description?: string | null;
  price: number;
  currency: string;
  use_type: string;
  category: string;
  status: string;
  featured?: boolean;
  total_area?: number | null;
  covered_area?: number | null;
  marla_area?: number | null;
  kanal_area?: number | null;
  city_id?: string | null;
  scheme_id?: string | null;
  block_zone_area_id?: string | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  floors?: number | null;
  street_address?: string | null;
  sector?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  image_urls?: string[];
  /** Set on units of a new project (China Center, Skyra Tower …): the big project's id and unit code. */
  project_id?: string | null;
  project_unit?: string | null;
  amenities?: string[];
  /** Set by /search?near=…: the closest matching place. */
  nearby?: NearbyPlace;
  /** Set by /search?near_place=…: km from that place. */
  distance_km?: number;
  agent_id?: string | null;
  /** Portal account that published it (`/me/listings`). */
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
  /** Present when searching with `near_place`. */
  near_place?: { query: string; found: boolean; name?: string; latitude?: number; longitude?: number; radius_km?: number };
  /** With `near_place` and nothing inside the radius: the closest listings outside it. */
  nearest_outside_radius?: Property[];
  note?: string;
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
  counts_within_radius?: Record<string, number>;
  note?: string;
}

/** A georeferenced DHA master plan laid over the map (GET /places/map, /masterplans). */
export interface MapOverlay {
  key: string;
  name: string;
  tile_url: string;
  bounds: [number, number, number, number];
  min_zoom: number;
  max_native_zoom: number;
  attribution: string;
}

export interface City {
  id: string;
  name: string;
  state?: string;
  latitude: number;
  longitude: number;
  schemes: number;
  properties: number;
  population?: number | null;
}

export interface Scheme {
  id: string;
  name: string;
  city: string;
  total_units?: number;
  established_year?: number;
  blocks?: number;
  development_status?: string | null;
  approval_authority?: string | null;
}

export interface NewsItem {
  id: string;
  title: string;
  source: string;
  channel_type: string;
  category: string;
  sentiment: "positive" | "negative" | "neutral";
  impact_score: number;
  summary?: string | null;
  url?: string | null;
  city_id?: string | null;
  scheme_id?: string | null;
  tags?: string[];
  published_at: string;
}

export interface Ad {
  id: string;
  title: string;
  headline: string;
  body?: string;
  advertiser: string;
  category: string;
  slot: string;
  cta_label?: string;
  cta_url?: string;
  image_url?: string | null;
  phone?: string | null;
  price_text?: string | null;
  offer?: string | null;
  impressions?: number;
  clicks?: number;
  ctr?: number;
  category_label?: string;
  slot_label?: string;
  status?: string;
  live?: boolean;
  priority?: number;
  budget?: number;
  spend?: number;
  remaining_budget?: number;
  /** How the advertiser pays: flat fee, per 1,000 impressions or per click. */
  pricing?: "flat" | "cpm" | "cpc";
  /** PKR per 1,000 impressions (cpm) or per click (cpc). */
  rate?: number;
  pricing_label?: string;
  /** "Sponsored" (configurable on the backend). */
  sponsored_label?: string;
  /** Demo creative, not a real advertiser. */
  sample?: boolean;
}

/** GET /ads/config — direct ads plus Google AdSense ids for slots nobody has bought. */
export interface AdConfig {
  direct: boolean;
  sponsored_label: string;
  advertise: { title: string; body: string; email: string | null };
  adsense: { client: string; slots: Partial<Record<AdPlacement, string>> } | null;
}
/** The AdSense placements the backend knows (ADS_ADSENSE_SLOT_HOME / _EXPLORE / _DETAIL). */
export type AdPlacement = "home" | "explore" | "detail";

export interface Story {
  id: string;
  title: string;
  story_type: string;
  client_name: string;
  client_role?: string;
  quote?: string;
  rating?: number | null;
  location?: string;
  narrative?: string[];
  metrics?: { label: string; value: string }[];
  highlights?: string[];
  featured?: boolean;
  date?: string;
}

export interface AgentDef {
  key: string;
  name: string;
  product: string;
  category: string;
  priority: string;
  autonomy: "suggest" | "assist" | "autonomous";
  summary: string;
  description?: string;
  tools: string[];
  inputs?: string[];
  outputs?: string[];
  channels?: string[];
  kpis?: Record<string, unknown>;
  requires_approval: boolean;
  handoffs?: string[];
  workflow?: { name: string; tool: string | null; requires_approval: boolean }[] | null;
  workflow_steps?: number;
  tool_count?: number;
}

export interface AgentStep {
  seq: number;
  name: string;
  tool: string | null;
  status: "done" | "skipped" | "failed" | "pending" | "awaiting_approval" | string;
  requires_approval: boolean;
  approved_by: string | null;
  output: string | null;
}

export interface AgentRun {
  id: string;
  agent_key: string;
  agent_name?: string;
  objective: string;
  status: string;
  steps: AgentStep[];
  approvals?: { step: string; approved_by: string; at: string }[];
  outcome?: Record<string, unknown>;
  metrics?: Record<string, number>;
  created_at: string;
  completed_at?: string | null;
  step_count?: number;
  done_steps?: number;
  awaiting_approval?: string[];
}

export interface SmartAction {
  kind: string;
  title: string;
  entity_type: string;
  entity_id: string;
  due_in_hours: number;
  priority: number;
  band: "urgent" | "high" | "normal";
  reason: string;
  suggested_agent: string;
  sla_hours: number;
}
