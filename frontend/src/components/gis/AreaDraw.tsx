/**
 * Draw a case-study area on the map.
 *   circle      press at the centre, drag out the radius, release
 *   rectangle   press at a corner, drag to the opposite corner, release
 *   polygon     click each corner; double-click (or click the first corner) to finish;
 *               Backspace removes the last corner; Esc cancels
 * The finished shape stays on the map (rendered from `shape`) until cleared or redrawn.
 */
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { Circle, CircleMarker, Polygon, Polyline, Rectangle, Tooltip, useMap } from "react-leaflet";

export type DrawMode = "circle" | "rectangle" | "polygon";
export type StudyShape =
  | { kind: "circle"; center: [number, number]; radius_m: number }
  | {
      kind: "rectangle";
      bounds: { south: number; west: number; north: number; east: number };
    }
  | { kind: "polygon"; coordinates: [number, number][] };

const DRAFT = {
  color: "#c99a22",
  weight: 2.5,
  dashArray: "6 5",
  fillColor: "#f2dd8f",
  fillOpacity: 0.15,
};
const DONE = {
  color: "#7c3aed",
  weight: 3,
  fillColor: "#a78bfa",
  fillOpacity: 0.14,
};

export function fmtDistance(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(m >= 10_000 ? 0 : 1)} km` : `${Math.round(m)} m`;
}

/** Area of a shape in km² (spherical approximation; fine at city scale). */
export function shapeAreaKm2(s: StudyShape): number {
  if (s.kind === "circle") return Math.PI * (s.radius_m / 1000) ** 2;
  const ring: [number, number][] =
    s.kind === "rectangle"
      ? [
          [s.bounds.south, s.bounds.west],
          [s.bounds.south, s.bounds.east],
          [s.bounds.north, s.bounds.east],
          [s.bounds.north, s.bounds.west],
        ]
      : s.coordinates;
  const lat0 = (ring.reduce((a, p) => a + p[0], 0) / ring.length) * (Math.PI / 180);
  const kx = 111.32 * Math.cos(lat0);
  const ky = 110.57;
  let a = 0;
  for (let i = 0; i < ring.length; i++) {
    const [y1, x1] = ring[i]!;
    const [y2, x2] = ring[(i + 1) % ring.length]!;
    a += x1 * kx * (y2 * ky) - x2 * kx * (y1 * ky);
  }
  return Math.abs(a) / 2;
}

export function AreaDraw({ mode, shape, onShape, onCancel }: { mode: DrawMode | null; shape: StudyShape | null; onShape: (s: StudyShape) => void; onCancel: () => void }) {
  const map = useMap();
  const [draft, setDraft] = useState<StudyShape | null>(null);
  const [pts, setPts] = useState<[number, number][]>([]);
  const [hover, setHover] = useState<[number, number] | null>(null);
  const start = useRef<L.LatLng | null>(null);
  const ptsRef = useRef(pts);
  ptsRef.current = pts;

  useEffect(() => {
    setDraft(null);
    setPts([]);
    setHover(null);
    start.current = null;
    if (!mode) return;
    const el = map.getContainer();
    const drag = mode !== "polygon";
    if (drag) map.dragging.disable();
    map.doubleClickZoom.disable();
    map.boxZoom.disable();
    el.style.cursor = "crosshair";
    el.style.touchAction = "none";
    const at = (e: PointerEvent | MouseEvent) => map.mouseEventToLatLng(e as MouseEvent);
    const swallowClick = (e: MouseEvent) => {
      e.stopPropagation();
      e.preventDefault();
    };

    const finishPolygon = (list: [number, number][]) => {
      const clean = list.filter((p, i) => i === 0 || p[0] !== list[i - 1]![0] || p[1] !== list[i - 1]![1]);
      if (clean.length >= 3) onShape({ kind: "polygon", coordinates: clean });
      else onCancel();
    };

    const down = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest(".leaflet-control")) return;
      e.preventDefault();
      e.stopPropagation();
      if (drag) {
        start.current = at(e);
        return;
      }
      const ll = at(e);
      const list = ptsRef.current;
      if (list.length >= 3) {
        const a = map.latLngToContainerPoint(list[0]!);
        if (a.distanceTo(map.mouseEventToContainerPoint(e as unknown as MouseEvent)) < 12) return finishPolygon(list);
      }
      setPts([...list, [ll.lat, ll.lng]]);
    };
    const move = (e: PointerEvent) => {
      const ll = at(e);
      if (drag && start.current) {
        if (mode === "circle")
          setDraft({
            kind: "circle",
            center: [start.current.lat, start.current.lng],
            radius_m: start.current.distanceTo(ll),
          });
        else
          setDraft({
            kind: "rectangle",
            bounds: {
              south: Math.min(start.current.lat, ll.lat),
              west: Math.min(start.current.lng, ll.lng),
              north: Math.max(start.current.lat, ll.lat),
              east: Math.max(start.current.lng, ll.lng),
            },
          });
      } else if (!drag) setHover([ll.lat, ll.lng]);
    };
    const up = (e: PointerEvent) => {
      if (!drag || !start.current) return;
      const a = map.latLngToContainerPoint(start.current);
      const b = map.mouseEventToContainerPoint(e as unknown as MouseEvent);
      const ll = at(e);
      const s = start.current;
      start.current = null;
      if (a.distanceTo(b) < 10) return setDraft(null); // a click, not a drag
      if (mode === "circle")
        onShape({
          kind: "circle",
          center: [s.lat, s.lng],
          radius_m: s.distanceTo(ll),
        });
      else
        onShape({
          kind: "rectangle",
          bounds: {
            south: Math.min(s.lat, ll.lat),
            west: Math.min(s.lng, ll.lng),
            north: Math.max(s.lat, ll.lat),
            east: Math.max(s.lng, ll.lng),
          },
        });
    };
    const dbl = (e: MouseEvent) => {
      if (drag) return;
      e.preventDefault();
      e.stopPropagation();
      finishPolygon(ptsRef.current);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      else if (e.key === "Backspace" && !drag && !(e.target as HTMLElement).closest("input,textarea")) setPts((p) => p.slice(0, -1));
      else if (e.key === "Enter" && !drag) finishPolygon(ptsRef.current);
    };
    el.addEventListener("pointerdown", down, true);
    el.addEventListener("click", swallowClick, true);
    el.addEventListener("dblclick", dbl, true);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("keydown", key);
    return () => {
      el.removeEventListener("pointerdown", down, true);
      el.removeEventListener("click", swallowClick, true);
      el.removeEventListener("dblclick", dbl, true);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("keydown", key);
      map.dragging.enable();
      map.doubleClickZoom.enable();
      map.boxZoom.enable();
      el.style.cursor = "";
      el.style.touchAction = "";
    };
  }, [mode, map, onShape, onCancel]);

  const render = (s: StudyShape, style: L.PathOptions, label?: string) => {
    const tip = label ? (
      <Tooltip permanent direction="center" className="study-tip">
        {label}
      </Tooltip>
    ) : null;
    if (s.kind === "circle")
      return (
        <Circle center={s.center} radius={s.radius_m} pathOptions={style} interactive={false}>
          {tip}
        </Circle>
      );
    if (s.kind === "rectangle")
      return (
        <Rectangle
          bounds={[
            [s.bounds.south, s.bounds.west],
            [s.bounds.north, s.bounds.east],
          ]}
          pathOptions={style}
          interactive={false}
        >
          {tip}
        </Rectangle>
      );
    return (
      <Polygon positions={s.coordinates} pathOptions={style} interactive={false}>
        {tip}
      </Polygon>
    );
  };

  const label = (s: StudyShape) => (s.kind === "circle" ? `r ${fmtDistance(s.radius_m)} · ${shapeAreaKm2(s).toFixed(2)} km²` : `${shapeAreaKm2(s).toFixed(2)} km²`);
  const preview = hover && pts.length ? [...pts, hover] : pts;
  return (
    <>
      {shape && !mode && render(shape, DONE)}
      {draft && render(draft, DRAFT, label(draft))}
      {mode === "polygon" && preview.length >= 3 && render({ kind: "polygon", coordinates: preview }, DRAFT, label({ kind: "polygon", coordinates: preview }))}
      {mode === "polygon" && preview.length === 2 && <Polyline positions={preview} pathOptions={DRAFT} interactive={false} />}
      {mode === "polygon" &&
        pts.map((p, i) => (
          <CircleMarker
            key={i}
            center={p}
            radius={i === 0 ? 6 : 4}
            pathOptions={{
              color: "#c99a22",
              weight: 2,
              fillColor: "#ffffff",
              fillOpacity: 1,
            }}
            interactive={false}
          />
        ))}
    </>
  );
}
