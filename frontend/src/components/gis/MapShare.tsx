/**
 * Map tools for sharing with the assistant (and as files):
 *   - MeasureLayer   measure a distance (click points along a line) or an area (click corners);
 *                    double-click / Enter finishes, Backspace removes the last point, Esc cancels
 *   - MeasureCard    the result in every unit, with Ask AI / PDF / Image / Clear
 *   - CoordReadout   the mouse's coordinates (decimal or DMS), click to copy
 *   - PinsLayer      pins the user dropped (right-click → Drop a pin), each with Ask AI / Copy / Remove
 *   - ShapesLayer    shapes sent from the chat (attached KML / GeoJSON / GPX, measurements)
 */
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { CircleMarker, GeoJSON, Marker, Polygon, Polyline, Popup, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { Bot, Check, Copy, FileDown, ImageDown, Loader2, Ruler, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { areaUnits, fmtLatLon, lengthUnits, pathLengthM, polygonAreaM2, toDms, centroid, type LatLon } from "@/lib/geoMeasure";
import { setPointer, type Spot } from "@/lib/mapFocus";
import { downloadUrl, shareToChat, type MapShape } from "@/lib/chatShare";
import { measureFile } from "@/lib/mapDocs";
import { pin } from "@/components/map/PortalMap";
import { cn } from "@/lib/utils";

export type MeasureMode = "distance" | "area";
export interface Measurement {
  mode: MeasureMode;
  coords: LatLon[];
  done: boolean;
}

const LINE = { color: "#d97706", weight: 3.5, dashArray: "8 6" };
const AREA = { color: "#d97706", weight: 3, fillColor: "#fbbf24", fillOpacity: 0.18 };

export function measureValue(m: Measurement): string {
  if (m.mode === "area") return m.coords.length >= 3 ? areaUnits(polygonAreaM2(m.coords)).text : "—";
  return lengthUnits(pathLengthM(m.coords)).text;
}

/** Drawing (while `active`) and showing a measurement. */
export function MeasureLayer({ active, value, onChange }: { active: MeasureMode | null; value: Measurement | null; onChange: (m: Measurement | null, stop?: boolean) => void }) {
  const map = useMap();
  const [hover, setHover] = useState<LatLon | null>(null);
  const cur = active ? (value && !value.done && value.mode === active ? value : { mode: active, coords: [], done: false }) : value;

  useEffect(() => {
    if (!active) return;
    map.doubleClickZoom.disable();
    const el = map.getContainer();
    el.style.cursor = "crosshair";
    return () => {
      map.doubleClickZoom.enable();
      el.style.cursor = "";
      setHover(null);
    };
  }, [active, map]);

  const finish = () => {
    if (!cur || !active) return;
    const enough = cur.mode === "area" ? cur.coords.length >= 3 : cur.coords.length >= 2;
    onChange(enough ? { ...cur, done: true } : null, true);
  };
  useMapEvents({
    click(e) {
      if (!active || !cur) return;
      onChange({ ...cur, coords: [...cur.coords, [e.latlng.lat, e.latlng.lng]], done: false });
    },
    dblclick() {
      if (!active || !cur) return;
      // The double-click's two clicks added the last point twice.
      const c = cur.coords;
      const dup = c.length >= 2 && c[c.length - 1]![0] === c[c.length - 2]![0] && c[c.length - 1]![1] === c[c.length - 2]![1];
      const coords = dup ? c.slice(0, -1) : c;
      const enough = cur.mode === "area" ? coords.length >= 3 : coords.length >= 2;
      onChange(enough ? { ...cur, coords, done: true } : null, true);
    },
    mousemove(e) {
      if (active) setHover([e.latlng.lat, e.latlng.lng]);
    },
  });
  useEffect(() => {
    if (!active) return;
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest?.("input, textarea, [contenteditable]")) return;
      if (e.key === "Enter") finish();
      else if (e.key === "Escape") onChange(null, true);
      else if (e.key === "Backspace" && cur?.coords.length) onChange({ ...cur, coords: cur.coords.slice(0, -1) });
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });

  if (!cur || (!cur.coords.length && !hover)) return null;
  const pts = active && hover ? [...cur.coords, hover] : cur.coords;
  let run = 0;
  return (
    <>
      {cur.mode === "area" && pts.length >= 3 ? (
        <Polygon positions={pts} pathOptions={AREA} interactive={false}>
          <Tooltip permanent direction="center" className="!rounded-lg !border-0 !bg-white/95 !px-2 !py-1 !text-xs !font-bold !text-amber-800 !shadow">
            {areaUnits(polygonAreaM2(pts)).text}
          </Tooltip>
        </Polygon>
      ) : (
        pts.length >= 2 && <Polyline positions={pts} pathOptions={LINE} interactive={false} />
      )}
      {cur.coords.map((p, i) => {
        if (i) run += pathLengthM([cur.coords[i - 1]!, p]);
        const last = i === cur.coords.length - 1;
        return (
          <CircleMarker key={i} center={p} radius={5} pathOptions={{ color: "#d97706", weight: 2, fillColor: "#fff", fillOpacity: 1 }} interactive={false}>
            {cur.mode === "distance" && i > 0 && (last || cur.coords.length <= 12) && (
              <Tooltip permanent direction="top" offset={[0, -6]} className="!rounded-md !border-0 !bg-white/95 !px-1.5 !py-0.5 !text-[11px] !font-bold !text-amber-800 !shadow">
                {lengthUnits(run).text}
              </Tooltip>
            )}
          </CircleMarker>
        );
      })}
      {active && hover && cur.coords.length > 0 && cur.mode === "distance" && (
        <CircleMarker center={hover} radius={1} pathOptions={{ opacity: 0, fillOpacity: 0 }} interactive={false}>
          <Tooltip permanent direction="right" offset={[10, 0]} className="!rounded-md !border-0 !bg-amber-600 !px-1.5 !py-0.5 !text-[11px] !font-bold !text-white">
            {lengthUnits(pathLengthM(pts)).text}
          </Tooltip>
        </CircleMarker>
      )}
    </>
  );
}

/** The hint while measuring, and the finished result with what to do with it. */
export function MeasureCard({ active, value, onClear, onStop, className }: { active: MeasureMode | null; value: Measurement | null; onClear: () => void; onStop: () => void; className?: string }) {
  const [busy, setBusy] = useState<"pdf" | "image" | null>(null);
  if (active)
    return (
      <div className={cn("glass flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm shadow-soft", className)}>
        <Ruler className="h-4 w-4 shrink-0 text-amber-600" />
        <span>
          <b>{active === "area" ? "Measure an area" : "Measure a distance"}</b> — click {active === "area" ? "each corner" : "points along the way"}; double-click or Enter to finish, Backspace to undo, Esc to cancel.
          {value && !value.done && value.coords.length > 0 && <b className="ms-2 text-amber-700 dark:text-amber-300">{measureValue(value)}</b>}
        </span>
        <button type="button" className="btn btn-ghost btn-icon h-8 w-8" onClick={onStop} aria-label="Stop measuring">
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  if (!value?.done) return null;
  const isArea = value.mode === "area";
  const units = isArea ? areaUnits(polygonAreaM2(value.coords)) : null;
  const len = lengthUnits(isArea ? pathLengthM([...value.coords, value.coords[0]!]) : pathLengthM(value.coords));
  const make = async (kind: "pdf" | "image") => {
    setBusy(kind);
    try {
      const f = await measureFile(value, kind);
      downloadUrl(f.url, f.name);
    } catch (e) {
      toast.error(`Couldn't make the ${kind === "pdf" ? "PDF" : "image"}: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className={cn("glass w-[min(440px,calc(100vw-2rem))] rounded-2xl p-3 text-sm shadow-soft", className)}>
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-700 dark:text-amber-300">
          <Ruler className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">{isArea ? "Measured area" : "Measured distance"}</p>
          <p className="font-display text-xl font-bold">{isArea ? units!.text : len.text}</p>
          <p className="text-[12px] text-ink-mute">
            {isArea
              ? `${units!.marla} marla (272.25 sq ft) · ${units!.marla_society_225sqft} marla (225 sq ft) · ${units!.kanal} kanal · ${units!.acres} acres · perimeter ${len.text}`
              : `${len.meters.toLocaleString()} m · ${len.feet.toLocaleString()} ft · ${len.miles} mi · ${value.coords.length} points`}
          </p>
        </div>
        <button type="button" className="btn btn-ghost btn-icon h-8 w-8" onClick={onClear} aria-label="Clear measurement">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <button
          type="button"
          className="chip bg-brand-700 text-white"
          onClick={() => shareToChat({ kind: "measure", label: isArea ? "Measured area" : "Measured distance", mode: value.mode, coords: value.coords, value_text: measureValue(value) })}
        >
          <Bot className="h-3.5 w-3.5" /> Ask AI about it
        </button>
        <button type="button" className="chip bg-white text-brand-800 ring-1 ring-brand-200 dark:bg-white/10 dark:text-brand-100" onClick={() => void make("pdf")} disabled={!!busy}>
          {busy === "pdf" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />} PDF
        </button>
        <button type="button" className="chip bg-white text-brand-800 ring-1 ring-brand-200 dark:bg-white/10 dark:text-brand-100" onClick={() => void make("image")} disabled={!!busy}>
          {busy === "image" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageDown className="h-3.5 w-3.5" />} Image
        </button>
      </div>
    </div>
  );
}

/** Live mouse coordinates (written straight to the DOM — no re-render per mouse move). */
export function CoordReadout({ className }: { className?: string }) {
  const map = useMap();
  const text = useRef<HTMLSpanElement>(null);
  const last = useRef<LatLon | null>(null);
  const [dms, setDms] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const show = (p: LatLon) => {
      if (text.current) text.current.textContent = dms ? toDms(p[0], p[1]) : fmtLatLon(p[0], p[1], 5);
    };
    const move = (e: L.LeafletMouseEvent) => {
      last.current = [e.latlng.lat, e.latlng.lng];
      setPointer(e.latlng.lat, e.latlng.lng);
      show(last.current);
    };
    if (last.current) show(last.current);
    else {
      const c = map.getCenter();
      show([c.lat, c.lng]);
    }
    map.on("mousemove", move);
    return () => {
      map.off("mousemove", move);
    };
  }, [map, dms]);
  const copy = () => {
    const p = last.current ?? [map.getCenter().lat, map.getCenter().lng];
    void navigator.clipboard?.writeText(fmtLatLon(p[0], p[1]));
    setCopied(true);
    setTimeout(() => setCopied(false), 900);
  };
  return (
    <div
      className={cn("glass pointer-events-auto flex items-center gap-1 rounded-full py-0.5 pe-1 ps-2.5 font-mono text-[11px] text-ink shadow-soft dark:text-slate-100", className)}
      ref={(el) => {
        if (el) {
          L.DomEvent.disableClickPropagation(el);
          L.DomEvent.disableScrollPropagation(el);
        }
      }}
    >
      <button type="button" onClick={() => setDms((v) => !v)} className="tabular-nums" title="Mouse position — click to switch decimal / degrees-minutes-seconds">
        <span ref={text} />
      </button>
      <button type="button" onClick={copy} className="btn btn-ghost btn-icon h-6 w-6" aria-label="Copy the mouse coordinates" title="Copy coordinates (where the mouse last was)">
        {copied ? <Check className="h-3 w-3 text-brand-600" /> : <Copy className="h-3 w-3" />}
      </button>
    </div>
  );
}

/** Pins the user dropped. */
export function PinsLayer({ pins, onRemove }: { pins: Spot[]; onRemove: (i: number) => void }) {
  return (
    <>
      {pins.map((p, i) => (
        <Marker key={`${p.lat},${p.lon},${i}`} position={[p.lat, p.lon]} icon={pin("featured", { label: p.label })}>
          <Popup>
            <PinPopup spot={p} onRemove={() => onRemove(i)} />
          </Popup>
        </Marker>
      ))}
    </>
  );
}

export function PinPopup({ spot, onRemove }: { spot: Spot; onRemove?: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-1.5 bg-white p-3 text-ink dark:bg-[#0d1f16] dark:text-white">
      <p className="text-sm font-semibold">{spot.label}</p>
      <p className="font-mono text-[11px] text-ink-mute">
        {fmtLatLon(spot.lat, spot.lon)}
        <br />
        {toDms(spot.lat, spot.lon)}
      </p>
      <div className="flex flex-wrap gap-1.5 pt-1">
        <button type="button" className="chip bg-brand-700 text-white" onClick={() => shareToChat({ kind: "pin", label: spot.label, lat: spot.lat, lon: spot.lon, source: "dropped pin" })}>
          <Bot className="h-3 w-3" /> Ask AI
        </button>
        <button
          type="button"
          className="chip bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100"
          onClick={() => {
            void navigator.clipboard?.writeText(fmtLatLon(spot.lat, spot.lon));
            setCopied(true);
          }}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />} {copied ? "Copied" : "Copy"}
        </button>
        {onRemove && (
          <button type="button" className="chip bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100" onClick={onRemove}>
            <Trash2 className="h-3 w-3" /> Remove
          </button>
        )}
      </div>
    </div>
  );
}

/** Shapes the chat put on the map (attached files, measurements, shared pins). */
export function ShapesLayer({ shapes, onRemove }: { shapes: MapShape[]; onRemove: (id: string) => void }) {
  const map = useMap();
  const fitted = useRef(new Set<string>());
  useEffect(() => {
    for (const s of shapes) {
      if (!s.fit || fitted.current.has(s.id)) continue;
      fitted.current.add(s.id);
      const b = L.geoJSON(s.geojson).getBounds();
      if (b.isValid()) map.flyToBounds(b, { padding: [60, 60], maxZoom: 17, duration: 0.8 });
    }
  }, [shapes, map]);
  return (
    <>
      {shapes.map((s) => (
        <GeoJSON
          key={s.id}
          data={s.geojson}
          style={() => ({ color: "#2563eb", weight: 3, fillColor: "#60a5fa", fillOpacity: 0.18 })}
          pointToLayer={(_f, ll) => L.marker(ll, { icon: pin("city") })}
          onEachFeature={(f, layer) => {
            const name = String((f.properties as { name?: string } | null)?.name || s.name);
            const g = f.geometry;
            const ring = g.type === "Polygon" ? (g.coordinates[0] as number[][]).map((c) => [c[1]!, c[0]!] as LatLon) : null;
            const line = g.type === "LineString" ? (g.coordinates as number[][]).map((c) => [c[1]!, c[0]!] as LatLon) : null;
            const what = ring ? areaUnits(polygonAreaM2(ring)).text : line ? lengthUnits(pathLengthM(line)).text : g.type === "Point" ? fmtLatLon((g.coordinates as number[])[1]!, (g.coordinates as number[])[0]!) : "";
            const at = ring ? centroid(ring) : line ? line[0]! : null;
            const box = document.createElement("div");
            box.className = "p-3 text-sm";
            box.innerHTML = `<p class="font-semibold"></p><p class="text-[12px] text-ink-mute"></p><button type="button" class="chip mt-2 bg-brand-50 text-brand-800">Remove from map</button>`;
            box.querySelector("p")!.textContent = name;
            box.querySelectorAll("p")[1]!.textContent = [what, at ? fmtLatLon(at[0], at[1], 5) : ""].filter(Boolean).join(" · ");
            box.querySelector("button")!.addEventListener("click", () => onRemove(s.id));
            layer.bindPopup(box);
          }}
        />
      ))}
    </>
  );
}
