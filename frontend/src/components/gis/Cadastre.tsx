/**
 * Cadastre: collect land-parcel base data on the Map page (GIS managers).
 *
 *   Draw parcel     click each corner (snaps to nearby parcel corners); click the first corner,
 *                   or "Finish", to close it
 *   Plot by size    click the plot's centre, then set front × depth (ft) and the angle
 *   Edit parcel     click a parcel to change its outline (drag corners, "+" to insert, right-click
 *                   to remove) and its record
 *   Layer · Export  show / hide the parcels; download them all as GeoJSON
 *
 * Each parcel carries the society plot (society / sector / block / street / plot no.) and the revenue
 * record (province / district / tehsil / mouza, khewat, khatooni, khasra), land use, status, ownership
 * and how it was surveyed. Area (m², marla, kanal), perimeter and edge lengths are measured live;
 * the server rejects self-crossing outlines and warns about overlaps.
 *   GET/POST /cadastre/parcels · PUT/DELETE /cadastre/parcels/{id} · GET /cadastre/summary · /cadastre/export.geojson
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { CircleMarker, Polygon, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Eye, EyeOff, Hexagon, MousePointerClick, Ruler, Save, Trash2, Undo2, X } from "lucide-react";
import { toast } from "sonner";
import { del, get, post, put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";
import { VertexEditor, type LatLng } from "./GeoEditor";

export type CadMode = null | "draw" | "size" | "select";
/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
type Fields = Record<string, any>;
export interface CadDraft {
  id?: string;
  fields: Fields;
  pts: LatLng[];
  /** Corners still being clicked. */
  drawing: boolean;
  /** "Plot by size": the centre the rectangle is built around. */
  center?: LatLng;
}
interface ParcelFeature {
  id: string;
  properties: Fields & { label: string; status?: string; land_use?: string; area_m2?: number };
  geometry: { type: "Polygon"; coordinates: [number, number][][] };
}
interface ParcelFC {
  count: number;
  features: ParcelFeature[];
  unpublished?: boolean;
}

const MIN_ZOOM = 13;
const SQFT_M2 = 0.09290304;
const FT = 0.3048;
export const CAD_DEFAULTS: Fields = {
  land_use: "residential", status: "vacant", parcel_type: "plot", ownership: "private", capture_method: "digitised_satellite",
  front_ft: 25, depth_ft: 50, angle: 0,
};
const STATUS_COLORS: Record<string, string> = {
  vacant: "#16a34a", under_construction: "#f59e0b", built: "#2563eb", agricultural: "#65a30d", disputed: "#dc2626", unknown: "#64748b",
};
const OPTIONS = {
  land_use: ["residential", "commercial", "mixed_use", "agricultural", "industrial", "amenity", "park", "graveyard", "mosque", "school", "health", "road", "government", "other"],
  status: ["vacant", "under_construction", "built", "agricultural", "disputed", "unknown"],
  parcel_type: ["plot", "khasra_field", "building_footprint", "amenity_plot", "road_reserve", "other"],
  ownership: ["private", "society", "government", "auqaf", "shamlat", "cantonment", "unknown"],
  capture_method: ["digitised_master_plan", "digitised_satellite", "gps_survey", "total_station", "imported", "other"],
};
const nice = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const ringOf = (f: ParcelFeature): LatLng[] => f.geometry.coordinates[0]!.slice(0, -1).map(([lon, lat]) => [lat, lon]);

// ------------------------------------------------------------------ measuring

/** Area, perimeter and edges of an outline (local plane about its centre — fine for parcels). */
export function measureRing(pts: LatLng[]) {
  if (pts.length < 2) return null;
  const lat0 = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const k = Math.cos((lat0 * Math.PI) / 180);
  const xy = pts.map((p) => [((p[1] * Math.PI) / 180) * 6378137 * k, ((p[0] * Math.PI) / 180) * 6378137]);
  const n = xy.length;
  let a = 0;
  const edges: number[] = [];
  for (let i = 0; i < n; i++) {
    const p = xy[i]!;
    const q = xy[(i + 1) % n]!;
    a += p[0]! * q[1]! - q[0]! * p[1]!;
    edges.push(Math.hypot(q[0]! - p[0]!, q[1]! - p[1]!));
  }
  const area = n >= 3 ? Math.abs(a) / 2 : 0;
  const sqft = area / SQFT_M2;
  return { area, sqft, marla: sqft / 225, kanal: sqft / 225 / 20, revenueMarla: sqft / 272.25, perimeter: edges.reduce((s, e) => s + e, 0), edges };
}

/** A front × depth (ft) plot around a centre, turned by ``angle``° (clockwise from north). */
export function plotRect(c: LatLng, frontFt: number, depthFt: number, angle: number): LatLng[] {
  const w = (frontFt * FT) / 2;
  const d = (depthFt * FT) / 2;
  const t = (angle * Math.PI) / 180;
  const m = 111320;
  return [[-w, d], [w, d], [w, -d], [-w, -d]].map(([x, y]) => {
    const ex = x! * Math.cos(t) + y! * Math.sin(t);
    const ny = -x! * Math.sin(t) + y! * Math.cos(t);
    return [c[0] + ny / m, c[1] + ex / (m * Math.cos((c[0] * Math.PI) / 180))] as LatLng;
  });
}

// ------------------------------------------------------------------ menu bar

/** The "Cadastre" menu: a horizontal bar beside the Edit Listing bar. */
export function CadastreBar({
  mode,
  onMode,
  layerOn,
  onLayer,
  className,
}: {
  mode: CadMode;
  onMode: (m: CadMode) => void;
  layerOn: boolean;
  onLayer: (on: boolean) => void;
  className?: string;
}) {
  const summary = useApi<{ parcels: number; verified: number }>("/cadastre/summary", undefined, { staleTime: 30_000 });
  const item = (active: boolean) =>
    cn("flex h-10 items-center gap-1.5 px-3 text-xs font-bold transition first:rounded-s-xl last:rounded-e-xl", active ? "bg-brand-700 text-white" : "text-brand-800 hover:bg-brand-50 dark:text-white dark:hover:bg-white/10");
  const tool = (m: Exclude<CadMode, null>, Icon: typeof Hexagon, label: string, tip: string) => (
    <button type="button" className={item(mode === m)} aria-pressed={mode === m} title={mode === m ? `Stop: ${label}` : tip} onClick={() => onMode(mode === m ? null : m)}>
      <Icon className="h-4 w-4" /> {label}
    </button>
  );
  const exportAll = async () => {
    try {
      const fc = await get("/cadastre/export.geojson");
      const url = URL.createObjectURL(new Blob([JSON.stringify(fc)], { type: "application/geo+json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `cadastre_parcels_${new Date().toISOString().slice(0, 10)}.geojson`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(`Export failed: ${(e as Error).message}`);
    }
  };
  return (
    <div className={cn("flex flex-col items-start gap-1", className)}>
      <span className="rounded-full bg-white/90 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-ink-mute shadow-sm dark:bg-brand-950/90">
        Cadastre{summary.data ? ` · ${summary.data.parcels} parcels` : ""}
      </span>
      <div className="flex divide-x divide-black/5 rounded-xl bg-white shadow-soft ring-1 ring-black/5 dark:divide-white/10 dark:bg-brand-950">
        {tool("draw", Hexagon, "Parcel", "Draw a parcel: click each corner (snaps to nearby corners), then click the first corner or Finish")}
        {tool("size", Ruler, "Plot", "Plot by size: click the plot's centre, then set front × depth in feet and the angle")}
        {tool("select", MousePointerClick, "Edit", "Edit a parcel: click it to change its outline and record")}
        <button type="button" className={item(false)} title={layerOn ? "Hide the parcels" : "Show the parcels"} aria-pressed={layerOn} onClick={() => onLayer(!layerOn)}>
          {layerOn ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        </button>
        <button type="button" className={item(false)} title="Download every parcel as GeoJSON (QGIS / ArcGIS)" onClick={exportAll}>
          <Download className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ map layer

/** The parcels in view (fetched from zoom 13). */
export function useParcels(on: boolean) {
  const [view, setView] = useState<{ z: number; b: [number, number, number, number] } | null>(null);
  const map = useMap();
  useMapEvents({
    moveend: () => {
      const b = map.getBounds();
      setView({ z: map.getZoom(), b: [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()] });
    },
  });
  useEffect(() => {
    const b = map.getBounds();
    setView({ z: map.getZoom(), b: [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()] });
  }, [map]);
  const r = (x: number) => Number(x.toFixed(3)); // round so small pans hit the cache
  const q = view && view.z >= MIN_ZOOM ? { south: r(view.b[0]) - 0.001, west: r(view.b[1]) - 0.001, north: r(view.b[2]) + 0.001, east: r(view.b[3]) + 0.001 } : undefined;
  return useApi<ParcelFC>(on && q ? "/cadastre/parcels" : null, q, { staleTime: 20_000, placeholderData: (prev) => prev });
}

function inside(p: L.Point, ring: L.Point[]): boolean {
  let hit = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i]!;
    const b = ring[j]!;
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}

/**
 * Inside the map: draws the parcels, captures clicks while a Cadastre tool is on (snapping to the
 * nearest parcel corner within 10 px), and shows the draft with its edge lengths.
 */
export function CadastreLayer({
  on,
  mode,
  draft,
  setDraft,
  onPick,
  onSelect,
}: {
  on: boolean;
  mode: CadMode;
  draft: CadDraft | null;
  setDraft: (d: CadDraft | null) => void;
  /** A map click while a tool is on, already snapped; ``first`` = it hit the draft's first corner. */
  onPick: (at: LatLng, first: boolean) => void;
  /** A parcel clicked with the Edit tool. */
  onSelect: (f: ParcelFeature) => void;
}) {
  const map = useMap();
  const q = useParcels(on || !!mode);
  const feats = useMemo(() => q.data?.features ?? [], [q.data]);
  const [zoom, setZoom] = useState(map.getZoom());
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) });
  const ref = useRef({ mode, draft, feats, onPick, onSelect });
  ref.current = { mode, draft, feats, onPick, onSelect };

  useEffect(() => {
    if (!mode) return;
    const el = map.getContainer();
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => (down = { x: e.clientX, y: e.clientY });
    const onClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest(".leaflet-control, .leaflet-popup, .geo-edit-handle")) return;
      if (!t.closest(".leaflet-pane") && !t.classList.contains("leaflet-container")) return;
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      e.stopPropagation();
      e.preventDefault();
      const { mode: m, draft: d, feats: fs } = ref.current;
      const c = map.mouseEventToContainerPoint(e);
      if (m === "select") {
        const hit = fs.find((f) => inside(c, ringOf(f).map((p) => map.latLngToContainerPoint(p))));
        if (hit) ref.current.onSelect(hit);
        else toast.message("No parcel there — click inside a parcel");
        return;
      }
      // snap: the draft's first corner (to close it), then any parcel corner within 10 px
      const cands: { p: LatLng; first: boolean }[] = [];
      if (d?.drawing && d.pts.length >= 3) cands.push({ p: d.pts[0]!, first: true });
      for (const f of fs) for (const p of ringOf(f)) cands.push({ p, first: false });
      let best: { p: LatLng; first: boolean; dist: number } | null = null;
      for (const k of cands) {
        const dist = c.distanceTo(map.latLngToContainerPoint(k.p));
        if (dist <= 10 && (!best || dist < best.dist - (k.first ? 3 : 0))) best = { ...k, dist };
      }
      const ll = map.containerPointToLatLng(c);
      ref.current.onPick(best ? best.p : [ll.lat, ll.lng], !!best?.first);
    };
    el.addEventListener("pointerdown", onDown, true);
    el.addEventListener("click", onClick, true);
    el.style.cursor = "crosshair";
    if (mode === "draw") map.doubleClickZoom.disable();
    return () => {
      el.removeEventListener("pointerdown", onDown, true);
      el.removeEventListener("click", onClick, true);
      el.style.cursor = "";
      map.doubleClickZoom.enable();
    };
  }, [map, mode]);

  const m = draft ? measureRing(draft.pts) : null;
  return (
    <>
      {(on || mode) &&
        feats
          .filter((f) => f.id !== draft?.id)
          .map((f) => {
            const color = STATUS_COLORS[f.properties.status ?? "unknown"] ?? "#64748b";
            return (
              <Polygon
                key={f.id}
                positions={ringOf(f)}
                pathOptions={{ color, weight: 1.5, fillColor: color, fillOpacity: 0.18, dashArray: f.properties.verified ? undefined : "4 3" }}
                interactive={!mode}
              >
                {zoom >= 18 ? (
                  <Tooltip permanent direction="center" className="!border-0 !bg-transparent !p-0 !shadow-none">
                    <span className="text-[10px] font-bold text-ink">{f.properties.plot_no || f.properties.khasra_no || ""}</span>
                  </Tooltip>
                ) : (
                  !mode && (
                    <Tooltip sticky>
                      <span className="font-semibold">{f.properties.label}</span>
                      <br />
                      {nice(f.properties.land_use ?? "")} · {nice(f.properties.status ?? "")} · {Math.round(f.properties.area_m2 ?? 0)} m²
                    </Tooltip>
                  )
                )}
              </Polygon>
            );
          })}
      {draft && draft.pts.length > 0 && (
        <>
          <VertexEditor pts={draft.pts} closed={!draft.drawing && draft.pts.length >= 3} onChange={(pts) => setDraft({ ...draft, pts })} />
          {m &&
            zoom >= 16 &&
            draft.pts.map((p, i) => {
              if (draft.drawing && i === draft.pts.length - 1) return null;
              const q2 = draft.pts[(i + 1) % draft.pts.length]!;
              return (
                <CircleMarker key={`e${i}`} center={[(p[0] + q2[0]) / 2, (p[1] + q2[1]) / 2]} radius={0} pathOptions={{ opacity: 0 }} interactive={false}>
                  <Tooltip permanent direction="top" offset={[0, -6]} className="!px-1 !py-0 !text-[10px]">
                    {(m.edges[i]! / FT).toFixed(1)} ft
                  </Tooltip>
                </CircleMarker>
              );
            })}
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------ side panel

function F({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <label className={cn("block", wide && "col-span-2")}>
      <span className="mb-1 block text-[11px] font-semibold text-ink-mute">{label}</span>
      {children}
    </label>
  );
}

const HINTS: Record<Exclude<CadMode, null>, string> = {
  draw: "Click each corner of the parcel on the map — clicks snap to nearby parcel corners. Click the first corner (or Finish) to close it.",
  size: "Click the centre of the plot on the map, then set its front and depth in feet and the angle.",
  select: "Click a parcel on the map to edit its outline and record. Zoom in (level 13+) to see the parcels.",
};

/** The Cadastre side panel: the tool's hint, then the parcel's measurements and record. */
export function CadastrePanel({
  mode,
  draft,
  setDraft,
  onClose,
  className,
}: {
  mode: CadMode;
  draft: CadDraft | null;
  setDraft: (d: CadDraft | null) => void;
  onClose: () => void;
  className?: string;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  // Live check of a closed outline: the PIN it will get, and overlap / shape problems before saving.
  const [check, setCheck] = useState<{ pin?: string | null; errors: string[]; warnings: string[] } | null>(null);
  const closedRing = draft && !draft.drawing && draft.pts.length >= 3 ? JSON.stringify(draft.pts) : null;
  useEffect(() => {
    setCheck(null);
    if (!closedRing) return;
    const t = setTimeout(() => {
      post<{ pin?: string | null; errors: string[]; warnings: string[] }>("/cadastre/check", { ring: JSON.parse(closedRing), id: draft?.id })
        .then(setCheck)
        .catch(() => undefined);
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closedRing, draft?.id]);
  if (!mode) return null;
  const set = (k: string, v: unknown) => draft && setDraft({ ...draft, fields: { ...draft.fields, [k]: v } });
  const m = draft ? measureRing(draft.pts) : null;
  const closed = !!draft && !draft.drawing && draft.pts.length >= 3;
  const resize = (patch: Fields) => {
    if (!draft?.center) return;
    const f = { ...draft.fields, ...patch };
    setDraft({ ...draft, fields: f, pts: plotRect(draft.center, Number(f.front_ft) || 0, Number(f.depth_ft) || 0, Number(f.angle) || 0) });
  };
  const input = (k: string, ph?: string, type = "text") => (
    <input className="input h-9 w-full text-sm" type={type} value={draft?.fields[k] ?? ""} placeholder={ph} onChange={(e) => set(k, e.target.value)} />
  );
  const select = (k: keyof typeof OPTIONS) => (
    <select className="input h-9 w-full text-sm" value={draft?.fields[k] ?? ""} onChange={(e) => set(k, e.target.value)}>
      {OPTIONS[k].map((o) => (
        <option key={o} value={o}>
          {nice(o)}
        </option>
      ))}
    </select>
  );
  const refresh = () => qc.invalidateQueries({ predicate: (x) => String(x.queryKey[0] ?? "").startsWith("/cadastre") });
  const save = async () => {
    if (!draft || !closed) return;
    setBusy(true);
    try {
      const { front_ft, depth_ft, angle, ...fields } = draft.fields;
      void front_ft;
      void depth_ft;
      void angle;
      const body = { ...fields, ring: draft.pts };
      const r = draft.id ? await put(`/cadastre/parcels/${draft.id}`, body) : await post("/cadastre/parcels", body);
      (r.warnings ?? []).forEach((w: string) => toast.warning(w));
      toast.success(`${draft.id ? "Updated" : "Saved"} ${r.parcel.parcel_no} — ${Math.round(r.parcel.area_m2)} m² (${r.parcel.area_marla} marla)`);
      void refresh();
      setDraft(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!draft?.id || !confirm(`Delete parcel ${draft.fields.parcel_no ?? ""}? This cannot be undone.`)) return;
    try {
      await del(`/cadastre/parcels/${draft.id}`);
      toast.success("Parcel deleted");
      void refresh();
      setDraft(null);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className={cn("absolute z-[450] max-h-[calc(100%-1.5rem)] w-[360px] max-w-[calc(100vw-1.5rem)] overflow-y-auto rounded-2xl bg-white p-4 shadow-2xl ring-1 ring-black/5 dark:bg-brand-950", className)}>
      <div className="mb-2 flex items-center gap-2">
        <Hexagon className="h-4 w-4 text-gold-600" />
        <p className="flex-1 text-sm font-bold">{draft?.id ? `Parcel ${draft.fields.plot_no ? `plot ${draft.fields.plot_no}` : ""}` : mode === "size" ? "Plot by size" : mode === "draw" ? "New parcel" : "Edit a parcel"}</p>
        <button type="button" onClick={onClose} className="rounded-md p-1 text-ink-mute hover:bg-black/5 dark:hover:bg-white/10" aria-label="Close the Cadastre tool">
          <X className="h-4 w-4" />
        </button>
      </div>
      {!draft ? (
        <p className="rounded-xl bg-brand-50/70 p-3 text-xs text-ink-soft dark:bg-white/5 dark:text-slate-300">{HINTS[mode]}</p>
      ) : (
        <div className="space-y-3">
          {/* ---- parcel PIN: 15-digit geographic ID (≈1 m cell + check digit) */}
          <div className="flex items-center justify-between gap-2 rounded-xl bg-gold-50 px-3 py-2 ring-1 ring-gold-200 dark:bg-white/5 dark:ring-white/10">
            <span className="text-[11px] font-bold uppercase tracking-wider text-ink-mute" title="Parcel PIN: a 15-digit geographic code of the ~1 m cell inside the parcel, with a check digit. Parcels nearby share their leading digits.">
              Parcel PIN
            </span>
            <span className="font-mono text-sm font-bold tabular-nums tracking-wide">
              {draft.fields.pin ?? check?.pin ?? (closed ? "…" : "after the shape is closed")}
            </span>
          </div>
          {!!check && (check.errors.length > 0 || check.warnings.length > 0) && (
            <div className="space-y-1 rounded-xl bg-amber-50 p-2.5 text-[11px] text-amber-900 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-100 dark:ring-amber-400/20">
              {[...check.errors, ...check.warnings].map((w) => (
                <p key={w}>{w}</p>
              ))}
            </div>
          )}
          {/* ---- geometry */}
          <div className="rounded-xl bg-brand-50/70 p-3 text-xs dark:bg-white/5">
            {m && m.area > 0 ? (
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                <span className="text-ink-mute">Area</span>
                <span className="font-semibold tabular-nums">{m.area.toFixed(1)} m² · {Math.round(m.sqft)} sq ft</span>
                <span className="text-ink-mute">Marla / kanal</span>
                <span className="font-semibold tabular-nums">{m.marla.toFixed(2)} marla · {m.kanal.toFixed(3)} kanal</span>
                <span className="text-ink-mute">Revenue marla</span>
                <span className="tabular-nums">{m.revenueMarla.toFixed(2)} (272.25 sq ft)</span>
                <span className="text-ink-mute">Perimeter</span>
                <span className="tabular-nums">{m.perimeter.toFixed(1)} m · {draft.pts.length} corners</span>
              </div>
            ) : (
              <p className="text-ink-mute">{draft.pts.length} corner{draft.pts.length === 1 ? "" : "s"} — keep clicking corners.</p>
            )}
            {mode === "size" && draft.center && (
              <div className="mt-2 grid grid-cols-3 gap-2">
                {(["front_ft", "depth_ft", "angle"] as const).map((k) => (
                  <F key={k} label={k === "front_ft" ? "Front (ft)" : k === "depth_ft" ? "Depth (ft)" : "Angle (°)"}>
                    <input className="input h-8 w-full text-sm" type="number" value={draft.fields[k] ?? ""} onChange={(e) => resize({ [k]: e.target.value })} />
                  </F>
                ))}
              </div>
            )}
            {draft.drawing ? (
              <div className="mt-2 flex gap-2">
                <Button size="sm" disabled={draft.pts.length < 3} onClick={() => setDraft({ ...draft, drawing: false })}>
                  Finish shape
                </Button>
                <Button size="sm" variant="soft" icon={<Undo2 className="h-3.5 w-3.5" />} disabled={!draft.pts.length} onClick={() => setDraft({ ...draft, pts: draft.pts.slice(0, -1) })}>
                  Undo corner
                </Button>
              </div>
            ) : (
              <p className="mt-2 text-[11px] text-ink-mute">Drag corners to adjust · click “+” to add a corner · right-click a corner to remove it.</p>
            )}
          </div>

          {/* ---- record */}
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Plot / society</p>
          <div className="grid grid-cols-2 gap-2">
            <F label="Parcel no. (optional)">{input("parcel_no", "= PIN")}</F>
            <F label="Plot no.">{input("plot_no")}</F>
            <F label="Sector / phase">{input("sector")}</F>
            <F label="Block">{input("block")}</F>
            <F label="Street">{input("street")}</F>
            <F label="City">{input("city")}</F>
            <F label="Society / scheme" wide>{input("society")}</F>
          </div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Revenue record</p>
          <div className="grid grid-cols-2 gap-2">
            <F label="District">{input("district")}</F>
            <F label="Tehsil">{input("tehsil")}</F>
            <F label="Mouza" wide>{input("mouza")}</F>
            <F label="Khewat no.">{input("khewat_no")}</F>
            <F label="Khatooni no.">{input("khatooni_no")}</F>
            <F label="Khasra no(s)." wide>{input("khasra_no", "e.g. 345/2, 346")}</F>
          </div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Land &amp; ownership</p>
          <div className="grid grid-cols-2 gap-2">
            <F label="Parcel type">{select("parcel_type")}</F>
            <F label="Land use">{select("land_use")}</F>
            <F label="Status">{select("status")}</F>
            <F label="Ownership">{select("ownership")}</F>
            <F label="Owner name (managers only)" wide>{input("owner_name")}</F>
            <F label="Declared area (as per documents)" wide>{input("declared_area", "e.g. 5 marla / 1 kanal 4 marla")}</F>
          </div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-mute">Survey</p>
          <div className="grid grid-cols-2 gap-2">
            <F label="Captured by">{select("capture_method")}</F>
            <F label="Accuracy (m)">{input("accuracy_m", "e.g. 2", "number")}</F>
            <F label="Source document" wide>{input("source_document", "fard / registry / LOP ref.")}</F>
            <F label="Notes" wide>
              <textarea className="input min-h-[56px] w-full text-sm" value={draft.fields.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
            </F>
            <label className="col-span-2 flex items-center gap-2 text-xs font-semibold">
              <input type="checkbox" checked={!!draft.fields.verified} onChange={(e) => set("verified", e.target.checked)} /> Verified against documents / on site
            </label>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <Button icon={<Save className="h-4 w-4" />} disabled={!closed || busy} onClick={save}>
              {busy ? "Saving…" : draft.id ? "Save changes" : "Save parcel"}
            </Button>
            <Button variant="soft" onClick={() => setDraft(null)}>
              Cancel
            </Button>
            {draft.id && (
              <button type="button" onClick={remove} className="ms-auto rounded-lg p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10" title="Delete this parcel" aria-label="Delete this parcel">
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** A parcel from the map, as an editable draft. */
export async function parcelDraft(id: string): Promise<CadDraft> {
  const p = await get<Fields & { ring: LatLng[] }>(`/cadastre/parcels/${id}`);
  const { ring, ...fields } = p;
  return { id: p.id, fields: { ...CAD_DEFAULTS, ...fields }, pts: ring, drawing: false };
}
