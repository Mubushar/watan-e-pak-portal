/**
 * Draw a case-study area on the map, click by click, with the shape following the mouse:
 *   circle      click the centre, then click again to set the radius
 *   rectangle   click the four corners; the area closes on the fourth click
 *   polygon     click each corner; double-click, Enter or a click on the first corner finishes
 * Backspace removes the last point; Esc cancels. The map can still be dragged between clicks.
 * The finished shape stays on the map (rendered from `shape`) until cleared or redrawn.
 */
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { Circle, CircleMarker, Polygon, Polyline, Tooltip, useMap } from "react-leaflet";

export type DrawMode = "circle" | "rectangle" | "polygon";
export type StudyShape =
  | { kind: "circle"; center: [number, number]; radius_m: number }
  | { kind: "rectangle"; coordinates: [number, number][] }
  | { kind: "polygon"; coordinates: [number, number][] };

const DRAFT: L.PathOptions = { color: "#c99a22", weight: 2.5, dashArray: "6 5", fillColor: "#f2dd8f", fillOpacity: 0.15 };
const DONE: L.PathOptions = { color: "#7c3aed", weight: 3, fillColor: "#a78bfa", fillOpacity: 0.14 };
const CORNER: L.PathOptions = { color: "#c99a22", weight: 2, fillColor: "#ffffff", fillOpacity: 1 };
/** A press that moves less than this (px) is a click, not a map drag. */
const CLICK_TOLERANCE = 6;

export function fmtDistance(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(m >= 10_000 ? 0 : 1)} km` : `${Math.round(m)} m`;
}

/** Area of a shape in km² (spherical approximation; fine at city scale). */
export function shapeAreaKm2(s: StudyShape): number {
  if (s.kind === "circle") return Math.PI * (s.radius_m / 1000) ** 2;
  const ring = s.coordinates;
  if (ring.length < 3) return 0;
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

const dist = (a: [number, number], b: [number, number]) => L.latLng(a).distanceTo(L.latLng(b));

export function AreaDraw({ mode, shape, onShape, onCancel }: { mode: DrawMode | null; shape: StudyShape | null; onShape: (s: StudyShape) => void; onCancel: () => void }) {
  const map = useMap();
  const [pts, setPts] = useState<[number, number][]>([]);
  const [hover, setHover] = useState<[number, number] | null>(null);
  const ptsRef = useRef(pts);
  ptsRef.current = pts;
  // Callbacks via refs: a parent re-render must not restart drawing (and drop the points).
  const cb = useRef({ onShape, onCancel });
  cb.current = { onShape, onCancel };

  useEffect(() => {
    setPts([]);
    setHover(null);
    if (!mode) return;
    const el = map.getContainer();
    map.doubleClickZoom.disable();
    map.boxZoom.disable();
    el.style.cursor = "crosshair";
    let down: L.Point | null = null;
    const onShape = (s: StudyShape) => cb.current.onShape(s);
    const onCancel = () => cb.current.onCancel();

    const finishPolygon = (list: [number, number][]) => {
      const clean = list.filter((p, i) => i === 0 || p[0] !== list[i - 1]![0] || p[1] !== list[i - 1]![1]);
      if (clean.length >= 3) onShape({ kind: "polygon", coordinates: clean });
      else onCancel();
    };

    const click = (ll: L.LatLng, at: L.Point) => {
      const p: [number, number] = [ll.lat, ll.lng];
      const list = ptsRef.current;
      if (mode === "circle") {
        if (!list.length) return setPts([p]);
        const r = dist(list[0]!, p);
        if (r < 1) return;
        return onShape({ kind: "circle", center: list[0]!, radius_m: r });
      }
      if (mode === "rectangle") {
        const next = [...list, p];
        if (next.length === 4) return onShape({ kind: "rectangle", coordinates: next });
        return setPts(next);
      }
      if (list.length >= 3 && map.latLngToContainerPoint(list[0]!).distanceTo(at) < 12) return finishPolygon(list);
      setPts([...list, p]);
    };

    const onDown = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest(".leaflet-control")) return;
      down = map.mouseEventToContainerPoint(e as unknown as MouseEvent);
    };
    const onUp = (e: PointerEvent) => {
      if (!down) return;
      const at = map.mouseEventToContainerPoint(e as unknown as MouseEvent);
      const moved = down.distanceTo(at);
      down = null;
      if (moved < CLICK_TOLERANCE) click(map.containerPointToLatLng(at), at);
    };
    const onMove = (e: PointerEvent) => {
      if (!el.contains(e.target as Node)) return;
      const ll = map.mouseEventToLatLng(e as unknown as MouseEvent);
      setHover([ll.lat, ll.lng]);
    };
    const onLeave = () => setHover(null);
    // Keep clicks from reaching other map layers (listing pins, plan outlines) while drawing.
    const swallowClick = (e: MouseEvent) => {
      if ((e.target as HTMLElement).closest(".leaflet-control")) return;
      e.stopPropagation();
      e.preventDefault();
    };
    const onDbl = (e: MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (mode === "polygon") finishPolygon(ptsRef.current);
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest?.("input,textarea")) return;
      if (e.key === "Escape") onCancel();
      else if (e.key === "Backspace") setPts((p) => p.slice(0, -1));
      else if (e.key === "Enter" && mode === "polygon") finishPolygon(ptsRef.current);
    };

    el.addEventListener("pointerdown", onDown, true);
    el.addEventListener("pointerleave", onLeave);
    el.addEventListener("click", swallowClick, true);
    el.addEventListener("dblclick", onDbl, true);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("keydown", onKey);
    return () => {
      el.removeEventListener("pointerdown", onDown, true);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("click", swallowClick, true);
      el.removeEventListener("dblclick", onDbl, true);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("keydown", onKey);
      map.doubleClickZoom.enable();
      map.boxZoom.enable();
      el.style.cursor = "";
    };
  }, [mode, map]);

  const tip = (text: string) => (
    <Tooltip permanent direction="center" className="study-tip">
      {text}
    </Tooltip>
  );
  const ringShape = (ring: [number, number][], style: L.PathOptions, label?: string) => (
    <Polygon positions={ring} pathOptions={style} interactive={false}>
      {label && tip(label)}
    </Polygon>
  );
  const areaLabel = (ring: [number, number][]) => `${shapeAreaKm2({ kind: "polygon", coordinates: ring }).toFixed(2)} km²`;

  // ---- finished shape
  let done = null;
  if (shape && !mode)
    done =
      shape.kind === "circle" ? <Circle center={shape.center} radius={shape.radius_m} pathOptions={DONE} interactive={false} /> : ringShape(shape.coordinates, DONE);

  // ---- live preview: the clicked points plus the mouse position
  let draft = null;
  if (mode === "circle" && pts.length === 1) {
    const c = pts[0]!;
    const r = hover ? dist(c, hover) : 0;
    draft = (
      <>
        {r > 0 && (
          <Circle center={c} radius={r} pathOptions={DRAFT} interactive={false}>
            {tip(`r ${fmtDistance(r)} · ${(Math.PI * (r / 1000) ** 2).toFixed(2)} km²`)}
          </Circle>
        )}
        {hover && <Polyline positions={[c, hover]} pathOptions={{ ...DRAFT, fillOpacity: 0, weight: 2 }} interactive={false} />}
        <CircleMarker center={c} radius={5} pathOptions={{ ...CORNER, fillColor: "#c99a22" }} interactive={false} />
      </>
    );
  } else if ((mode === "rectangle" || mode === "polygon") && pts.length) {
    const preview = hover ? [...pts, hover] : pts;
    draft = (
      <>
        {preview.length >= 3 && ringShape(preview, DRAFT, areaLabel(preview))}
        {preview.length === 2 && (
          <Polyline positions={preview} pathOptions={DRAFT} interactive={false}>
            {tip(fmtDistance(dist(preview[0]!, preview[1]!)))}
          </Polyline>
        )}
        {pts.map((p, i) => (
          <CircleMarker key={i} center={p} radius={i === 0 ? 6 : 4} pathOptions={CORNER} interactive={false} />
        ))}
      </>
    );
  }

  return (
    <>
      {done}
      {draft}
    </>
  );
}
