/** Backend payload shapes used by the GIS / insights screens (observed on the live API). */
import type { FeatureCollection, Geometry } from "geojson";
import type { Property } from "@/types";

export interface Poi {
  id: string;
  name: string;
  category: string;
  subcategory?: string | null;
  latitude: number;
  longitude: number;
  address?: string | null;
  city_id?: string | null;
  scheme_id?: string | null;
  rating?: number | null;
  city_name?: string | null;
  distance_m?: number;
  distance_km?: number;
}

export interface PoiCategory {
  category: string;
  count: number;
  weight: number;
  avg_rating: number | null;
}

export interface GisLayer {
  id: string;
  name: string;
  layer_type: string;
  entity_type: string;
  entity_id: string;
  base_map?: string;
  visible: boolean;
  features: number;
  image_url?: string | null;
  /** false while an admin hasn't published it (only GIS managers see such layers). */
  published?: boolean;
  /** Set on the portal's built-in overlays: roads, water, provinces … */
  builtin?: string | null;
}

export interface GisLayerDetail extends GisLayer {
  description?: string | null;
  geojson: FeatureCollection;
  style?: { color?: string; fillColor?: string; fillOpacity?: number; weight?: number; opacity?: number };
  z_index?: number;
  opacity?: number;
}

export interface Aoi {
  id: string;
  name: string;
  description?: string | null;
  kind: string;
  center_latitude?: number | null;
  center_longitude?: number | null;
  radius_m?: number | null;
  bounds?: { south: number; west: number; north: number; east: number };
  tags?: string[];
  geometry?: Geometry | null;
  area_sqm?: number;
  city_name?: string | null;
}

export interface AoiStats {
  id: string;
  name: string;
  kind: string;
  area: { area_sqm: number; area_sqft: number; area_marla: number; area_kanal: number; area_acres: number };
  properties: number;
  market_value: number;
  population: number;
  density_per_sqkm: number;
  development_cost: number;
  pois: number;
  poi_by_category: Record<string, number>;
  accessibility: number;
  center: { latitude: number; longitude: number };
}

export interface ScenarioPoint {
  year: number;
  offset: number;
  price_per_marla: number;
  market_value: number;
  rental_value: number;
  population: number;
  development_cost: number;
}
export interface Scenario {
  label: string;
  probability: number;
  price_cagr: number;
  series: ScenarioPoint[];
}
export type Scenarios = Partial<Record<"optimistic" | "base" | "pessimistic" | "stress", Scenario>>;

export interface NewsSummary {
  count: number;
  avg_impact: number;
  positive: number;
  neutral: number;
  negative: number;
  net_sentiment: string;
  momentum: number;
}

export interface MarketTrends {
  scope: { scope_type: string; scope_id: string | null };
  supply: { listings: number; by_category: Record<string, number>; by_use_type: Record<string, number> };
  pricing: { avg_price: number; median_price: number; price_per_marla: number; total_market_value: number };
  factors: { scores: Record<string, number>; index: { composite: number; band: string; weights: Record<string, number> } };
  news: NewsSummary;
  forecast: { composite_index: number; index_band: string; base_cagr: number; scenarios: Scenarios };
  yield?: { annual_rent: number; blended_yield: number };
  error?: string;
}

export interface MarketIntelligence {
  region: string;
  market_index: { composite: number; band: string };
  direction: string;
  pricing: MarketTrends["pricing"];
  supply: MarketTrends["supply"];
  yield?: { annual_rent: number; blended_yield: number };
  factors: Record<string, number>;
  news_momentum: NewsSummary;
  recommendation: string;
  forecast?: MarketTrends["forecast"];
}

export interface NewsImpact {
  summary: NewsSummary;
  by_category: Record<string, { count: number; avg_impact: number }>;
  effect_on_outlook?: { momentum: number; interpretation: string };
}

export interface NewsChannel {
  source: string;
  channel_type: string;
  count: number;
  avg_impact: number;
}

export interface BigProject {
  id: string;
  name: string;
  project_type: string;
  status: string;
  city: string;
  floor_count?: number | null;
  total_area?: number | null;
  occupancy_rate?: number | null;
  developer?: string | null;
  price_from?: number | null;
  price_to?: number | null;
  units_available?: number | null;
  inventory_checked?: string | null;
  payment_plan?: string | null;
  website?: string | null;
  image?: string | null;
}

/** A group of a project's available units (BigProjectDetail.unit_types). */
export interface ProjectUnitType {
  kind: string;
  bedrooms?: number | null;
  label: string;
  available: number;
  sqft_min: number;
  sqft_max: number;
  price_min: number;
  price_max: number;
  layouts?: string[];
}
export interface ProjectUnit {
  id: string;
  unit: string;
  title: string;
  category: string;
  bedrooms?: number | null;
  sqft: number;
  price: number;
  status: string;
  floor?: string | null;
}

export interface BigProjectDetail extends Omit<BigProject, "city" | "payment_plan"> {
  description?: string | null;
  city_name?: string | null;
  city_id?: string | null;
  scheme_id?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  developer?: string | null;
  start_date?: string | null;
  completion_date?: string | null;
  total_units?: number | null;
  leased_units?: number | null;
  total_parking_spaces?: number | null;
  total_retail_space?: number | null;
  total_office_space?: number | null;
  total_residential_units?: number | null;
  amenities?: string[];
  floor_plans?: unknown[];
  maps?: unknown[];
  multimedia?: Record<string, unknown>;
  image_library?: string[];
  image_urls?: string[];
  address?: string | null;
  website?: string | null;
  marketed_by?: string | null;
  floors_label?: string | null;
  location_precision?: string | null;
  payment_plan?: { summary?: string; alternative?: string; down_pct?: number; on_possession_pct?: number } | null;
  offer?: string | null;
  unit_types?: ProjectUnitType[];
  price_from?: number | null;
  price_to?: number | null;
  units_available?: number | null;
  inventory_checked?: string | null;
  inventory_source?: string | null;
  sources?: { title?: string; url?: string }[];
}

export interface HierarchyBlock {
  id: string;
  name: string;
  area_type: string;
  properties: number;
}
export interface HierarchyScheme {
  id: string;
  name: string;
  blocks: HierarchyBlock[];
  properties: number;
}
export interface HierarchyCity {
  id: string;
  name: string;
  schemes: HierarchyScheme[];
}

export interface GisAreaAnalysis {
  name: string;
  geometry?: Geometry | null;
  area?: { area_sqm: number; area_sqft: number; area_marla: number; area_kanal: number; area_acres: number };
  properties?: { count: number; total_market_value: number; avg_price: number; by_category: Record<string, number> };
  population?: { projected?: { dwelling_units: number; population: number }; density_per_sqkm?: number; population_from_listings?: number };
  development_cost?: { total: number; cost_per_sqft_of_land?: number };
  economic_impact?: { total_economic_output: number; jobs_total: number; economic_multiplier: number; annual_rental_value: number; annual_property_tax: number };
  error?: string;
  [k: string]: unknown;
}

export interface RouteLeg {
  label: string;
  mode: string;
  mode_label: string;
  distance_km: number;
  duration_min: number;
  duration_text: string;
  average_speed_kmh: number;
  geometry: [number, number][];
  steps: { instruction: string; heading: string; road_class: string; distance_m: number }[];
}
export interface RouteResult {
  mode: string;
  mode_label: string;
  best: RouteLeg;
  alternatives: RouteLeg[];
  error?: string;
}

export interface RingResult {
  center: { latitude: number; longitude: number };
  rings: { inner_km: number; outer_km: number; geometry: Geometry; summary: { properties: number; market_value: number; population: number; area_sqkm: number } }[];
}

export type PropertyLite = Property;
