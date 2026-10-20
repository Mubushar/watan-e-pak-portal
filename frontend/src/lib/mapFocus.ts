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
}
let readView: (() => MapViewState) | null = null;
/** The Map page registers how to read its view (null when it closes). */
export function registerMapView(fn: (() => MapViewState) | null): void {
  readView = fn;
}
/** The open Map page's view right now, or null when the Map page isn't open. */
export const getMapView = (): MapViewState | null =>
  onMapPage() && readView ? readView() : null;
