/**
 * The assistant moving the portal's main map (Map page). The chat calls focusMap(); an open Map
 * page flies there at once, and one opened afterwards (the chat navigates to /map) picks up the
 * last request when it mounts.
 */
export interface MapFocus {
  name: string;
  latitude: number;
  longitude: number;
  zoom: number;
  /** Also switch on the master plan(s) covering the spot. */
  masterPlan?: boolean;
}

const EVENT = "arzepak:map-focus";
let pending: MapFocus | null = null;
let focusedAt = 0;
/** When the assistant last moved the map (the fly-to takes ~1 s). */
export const lastFocusAt = () => focusedAt;

export function focusMap(f: MapFocus): void {
  pending = f;
  focusedAt = Date.now();
  window.dispatchEvent(new CustomEvent<MapFocus>(EVENT, { detail: f }));
}

/** The request waiting for a Map page that wasn't open yet (taken once). */
export function takePendingFocus(): MapFocus | null {
  const f = pending;
  pending = null;
  return f;
}

export function onMapFocus(fn: (f: MapFocus) => void): () => void {
  const h = (e: Event) => {
    pending = null;
    fn((e as CustomEvent<MapFocus>).detail);
  };
  window.addEventListener(EVENT, h);
  return () => window.removeEventListener(EVENT, h);
}

/** Is the Map page (/map) the current page? */
export const onMapPage = () => /\/map\/?$/.test(window.location.pathname);

/** What the Map page shows right now — read by the assistant (read_map). */
export interface MapViewState {
  south: number;
  west: number;
  north: number;
  east: number;
  zoom: number;
  /** Keys of the master plans drawn now, and their names. */
  plans: { key: string; name: string }[];
  /** Other GIS layers switched on. */
  gis: { id: string; name: string; type: string }[];
  /** Built-in overlays switched on (listings, osm_pois, mega_projects, roads, …). */
  overlays: string[];
  base: string;
  /** What the user has selected / is doing on the map (the assistant resolves "this", "here", "selected" from it). */
  selection: MapSelection;
}
export interface Spot {
  label: string;
  lat: number;
  lon: number;
}
export interface MapSelection {
  /** A listing whose popup is open (or the one last opened, ``open: false``). */
  listing?: Spot & { id: string; open: boolean; price?: number | null };
  /** A featured place whose popup is open. */
  place?: Spot;
  /** The search bar's result pin. */
  search_pin?: Spot;
  /** The route finder's From / To. */
  route?: { from?: Spot; to?: Spot; mode: string; showing: boolean };
  /** A point clicked with the Analyse tool. */
  analysis_point?: Spot;
  /** The listing / project / mega project open in the map editor. */
  editing?: Spot & { kind: string };
  /** The parcel open in the Cadastre form. */
  parcel?: Spot & { parcel_no?: string };
  /** Where the assistant last flew the map. */
  assistant_pin?: Spot;
  /** The tool switched on, in words (e.g. "route finder: picking the start point"). */
  active_tool?: string | null;
}

/** The assistant asking the Map page to show a route in its route finder. */
export interface RouteRequest {
  from: Spot;
  to: Spot;
  mode: "drive" | "bike" | "walk";
}
const ROUTE_EVENT = "arzepak:map-route";
let pendingRoute: RouteRequest | null = null;
export function routeOnMap(r: RouteRequest): void {
  pendingRoute = r;
  focusedAt = Date.now();
  window.dispatchEvent(new CustomEvent<RouteRequest>(ROUTE_EVENT, { detail: r }));
}
export function takePendingRoute(): RouteRequest | null {
  const r = pendingRoute;
  pendingRoute = null;
  return r;
}
export function onMapRoute(fn: (r: RouteRequest) => void): () => void {
  const h = (e: Event) => {
    pendingRoute = null;
    fn((e as CustomEvent<RouteRequest>).detail);
  };
  window.addEventListener(ROUTE_EVENT, h);
  return () => window.removeEventListener(ROUTE_EVENT, h);
}
let readView: (() => MapViewState) | null = null;
/** The Map page registers how to read its view (null when it closes). */
export function registerMapView(fn: (() => MapViewState) | null): void {
  readView = fn;
}
/** The open Map page's view right now, or null when the Map page isn't open. */
export const getMapView = (): MapViewState | null =>
  onMapPage() && readView ? readView() : null;
