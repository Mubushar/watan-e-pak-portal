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

export function focusMap(f: MapFocus): void {
  pending = f;
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
