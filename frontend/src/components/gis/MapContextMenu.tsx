/**
 * The map's right-click (long-press on touch) menu: a small floating menu at the pointer.
 * Closes on any click outside it, Esc, panning / zooming the map, or another right-click —
 * so it never gets stuck the way a Leaflet popup tied to React state can.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import { useMap, useMapEvents } from "react-leaflet";
import { Check, Copy } from "lucide-react";

export interface MapMenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: (lat: number, lon: number) => void;
}

const W = 216;

export function MapContextMenu({ items, disabled }: { items: MapMenuItem[]; disabled?: boolean }) {
  const map = useMap();
  const [at, setAt] = useState<{ lat: number; lon: number; x: number; y: number } | null>(null);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);

  useMapEvents({
    contextmenu(e) {
      e.originalEvent.preventDefault();
      if (disabled) return;
      setCopied(false);
      setAt({ lat: e.latlng.lat, lon: e.latlng.lng, x: e.containerPoint.x, y: e.containerPoint.y });
    },
  });

  // Close on outside pointer, Esc, map pan / zoom, and when the map is resized.
  useEffect(() => {
    if (!at) return;
    const close = () => setAt(null);
    const outside = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) close();
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", key);
    map.on("movestart zoomstart resize", close);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", key);
      map.off("movestart zoomstart resize", close);
    };
  }, [at, map]);

  if (!at) return null;
  const size = map.getSize();
  const height = 44 + items.length * 36 + 36;
  const left = Math.max(8, Math.min(at.x, size.x - W - 8));
  const top = Math.max(8, Math.min(at.y, size.y - height - 8));

  return createPortal(
    <div
      ref={(el) => {
        box.current = el;
        if (el) {
          L.DomEvent.disableClickPropagation(el);
          L.DomEvent.disableScrollPropagation(el);
        }
      }}
      role="menu"
      className="absolute z-[1000] overflow-hidden rounded-xl bg-white p-1.5 shadow-2xl ring-1 ring-black/10 dark:bg-brand-950 dark:ring-white/10"
      style={{ left, top, width: W }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <p className="px-2 pb-1 pt-0.5 font-mono text-[11px] text-ink-mute">
        {at.lat.toFixed(5)}, {at.lon.toFixed(5)}
      </p>
      {items.map((it) => (
        <button
          key={it.label}
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-sm font-semibold text-ink hover:bg-brand-50 dark:text-white dark:hover:bg-white/10"
          onClick={() => {
            it.onSelect(at.lat, at.lon);
            setAt(null);
          }}
        >
          {it.icon} {it.label}
        </button>
      ))}
      <button
        type="button"
        role="menuitem"
        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-sm text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/10"
        onClick={() => {
          void navigator.clipboard?.writeText(`${at.lat.toFixed(6)}, ${at.lon.toFixed(6)}`);
          setCopied(true);
          setTimeout(() => setAt(null), 600);
        }}
      >
        {copied ? <Check className="h-4 w-4 text-brand-600" /> : <Copy className="h-4 w-4" />} {copied ? "Copied" : "Copy coordinates"}
      </button>
    </div>,
    map.getContainer(),
  );
}
