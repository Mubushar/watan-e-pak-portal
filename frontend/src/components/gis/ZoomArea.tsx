/**
 * "Zoom to area": drag a rectangle over the map and zoom to it.
 *   press + drag     draw the box (mouse, pen or touch)
 *   release          zoom to the box
 *   Esc              cancel
 * Render inside the map; `active` turns it on, `onDone` is called when it zooms or is cancelled.
 * (Leaflet's own Shift + drag box zoom keeps working too.)
 */
import { useEffect, useRef, useState } from "react";
import { Rectangle, useMap } from "react-leaflet";
import L from "leaflet";

const STYLE = { color: "#c99a22", weight: 2.5, dashArray: "6 5", fillColor: "#f2dd8f", fillOpacity: 0.18 };

export function ZoomArea({ active, onDone, padding }: { active: boolean; onDone: () => void; padding?: { start?: number; bottom?: number } }) {
  const map = useMap();
  const [box, setBox] = useState<L.LatLngBounds | null>(null);
  const start = useRef<L.LatLng | null>(null);

  useEffect(() => {
    if (!active) {
      setBox(null);
      start.current = null;
      return;
    }
    const el = map.getContainer();
    // While the tool is on, a drag draws the box instead of panning the map.
    map.dragging.disable();
    map.boxZoom.disable();
    el.style.cursor = "crosshair";
    el.style.touchAction = "none";

    const at = (e: PointerEvent) => map.mouseEventToLatLng(e as unknown as MouseEvent);
    // The release also produces a click; don't let it reach map layers (clicking a plan
    // outline zooms to the whole plan, which would undo the box zoom).
    const swallowClick = (e: MouseEvent) => {
      e.stopPropagation();
      e.preventDefault();
    };
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest(".leaflet-control")) return;
      e.preventDefault();
      e.stopPropagation();
      start.current = at(e);
      setBox(L.latLngBounds(start.current, start.current));
    };
    const move = (e: PointerEvent) => {
      if (start.current) setBox(L.latLngBounds(start.current, at(e)));
    };
    const up = (e: PointerEvent) => {
      if (!start.current) return;
      const a = map.latLngToContainerPoint(start.current);
      const b = map.mouseEventToContainerPoint(e as unknown as MouseEvent);
      const bounds = L.latLngBounds(start.current, at(e));
      start.current = null;
      setBox(null);
      if (Math.abs(a.x - b.x) < 8 || Math.abs(a.y - b.y) < 8) return; // a click, not a box
      const rtl = document.documentElement.dir === "rtl";
      const s = 24 + (padding?.start ?? 0);
      const bottom = 24 + (padding?.bottom ?? 0);
      map.flyToBounds(bounds, { paddingTopLeft: [rtl ? 24 : s, 24], paddingBottomRight: [rtl ? s : 24, bottom], maxZoom: 19, duration: 0.8 });
      // Turn the tool off after this gesture's click has been swallowed.
      setTimeout(onDone, 0);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && onDone();
    // Move / release are watched on the window so a drag that ends outside the map still finishes.
    el.addEventListener("pointerdown", down, true);
    el.addEventListener("click", swallowClick, true);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    window.addEventListener("keydown", key);
    return () => {
      el.removeEventListener("pointerdown", down, true);
      el.removeEventListener("click", swallowClick, true);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      window.removeEventListener("keydown", key);
      map.dragging.enable();
      map.boxZoom.enable();
      el.style.cursor = "";
      el.style.touchAction = "";
    };
  }, [active, map, onDone, padding?.start, padding?.bottom]);

  return active && box ? <Rectangle bounds={box} pathOptions={STYLE} interactive={false} /> : null;
}
