/**
 * Map editing for admins (CAD-style): pick a listing, a big project or an infrastructure mega
 * project on the map and change its data and its geometry, or add new ones — saved straight to
 * the portal database through the admin APIs.
 *
 *   Edit (select)   click a feature → its editor opens; drag the pin / the vertices to move it
 *   Add             property pin · big project pin · mega project as a point, a line or an area
 *   Vertices        drag to move · click a "+" midpoint to insert · right-click a vertex to remove
 *
 * Rights follow the API: properties.manage (listings), projects.manage (big projects),
 * gis.manage (mega projects). Portal projects shown as mega projects are edited as big projects —
 * moving one moves its unit listings too.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { Marker, Polygon, Polyline, useMap } from "react-leaflet";
import { useQueryClient } from "@tanstack/react-query";
import { Building2, Check, Crosshair, MapPin, Milestone, PencilLine, RotateCcw, Save, Spline, Square, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { del, get, post, put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";
import type { MegaProject } from "./MegaProjects";

export type EditMode = null | "select" | "add-property" | "add-project" | "add-mega-point" | "add-mega-line" | "add-mega-polygon";
export type LatLng = [number, number];
export type Geom = { type: "point"; at: LatLng | null; radius_km?: number } | { type: "line" | "polygon"; pts: LatLng[] };
export type EditKind = "property" | "project" | "mega";
export interface Draft {
  kind: EditKind;
  id?: string;
  /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
  fields: Record<string, any>;
  geom: Geom;
  /** A shipped mega project the admin has changed (it can be reset). */
  edited?: boolean;
  /** A line / area being drawn: map clicks add vertices. */
  drawing?: boolean;
}
export interface EditRights {
  property: boolean;
  project: boolean;
  mega: boolean;
}
type Pt = { id: string; title?: string; latitude?: number | null; longitude?: number | null };
type BigProjectRow = { id: string; name: string; latitude?: number | null; longitude?: number | null };

const ADD_KIND: Record<string, { kind: EditKind; geom: Geom["type"] }> = {
  "add-property": { kind: "property", geom: "point" },
  "add-project": { kind: "project", geom: "point" },
  "add-mega-point": { kind: "mega", geom: "point" },
  "add-mega-line": { kind: "mega", geom: "line" },
  "add-mega-polygon": { kind: "mega", geom: "polygon" },
};

export function newDraft(mode: EditMode, at: LatLng): Draft | null {
  const a = mode ? ADD_KIND[mode] : undefined;
  if (!a) return null;
  if (a.kind === "property") return { kind: "property", fields: { title: "", price: "", category: "house", use_type: "residential", status: "active" }, geom: { type: "point", at } };
  if (a.kind === "project") return { kind: "project", fields: { name: "", project_type: "mixed_use", status: "planned" }, geom: { type: "point", at } };
  if (a.geom === "point") return { kind: "mega", fields: { name: "", type: "cbd", status: "planned", uplift: "medium", impact_radius_km: 2 }, geom: { type: "point", at, radius_km: 0.5 } };
  return { kind: "mega", fields: { name: "", type: a.geom === "line" ? "expressway" : "subdivision", status: "planned", uplift: "medium", impact_radius_km: 2 }, geom: { type: a.geom, pts: [at] }, drawing: true };
}

// ------------------------------------------------------------------ hit testing

function segDist(p: L.Point, a: L.Point, b: L.Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const t = dx || dy ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
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

export type Hit = { kind: "property"; id: string } | { kind: "project"; id: string } | { kind: "mega"; project: MegaProject };

/** The nearest editable feature under a click (pins first, then lines, then areas). */
export function pick(map: L.Map, at: L.LatLng, rights: EditRights, props: Pt[], projects: BigProjectRow[], megas: MegaProject[]): Hit | null {
  const c = map.latLngToContainerPoint(at);
  const near = (lat: number, lon: number) => c.distanceTo(map.latLngToContainerPoint([lat, lon]));
  let best: { d: number; hit: Hit } | null = null;
  const take = (d: number, hit: Hit, tol: number) => {
    if (d <= tol && (!best || d < best.d)) best = { d, hit };
  };
  if (rights.property) for (const p of props) if (p.latitude != null && p.longitude != null) take(near(p.latitude, p.longitude), { kind: "property", id: p.id }, 16);
  if (rights.project) for (const b of projects) if (b.latitude != null && b.longitude != null) take(near(b.latitude, b.longitude), { kind: "project", id: b.id }, 18);
  if (best) return (best as { hit: Hit }).hit;
  for (const m of megas) {
    const g = m.geometry;
    if (!g) continue;
    if (m.portal_project) {
      const b = projects.find((x) => x.name.toLowerCase() === m.name.toLowerCase());
      if (b && rights.project && g.type === "point") take(near(g.center[0], g.center[1]), { kind: "project", id: b.id }, 18);
      continue;
    }
    if (!rights.mega) continue;
    if (g.type === "point") take(near(g.center[0], g.center[1]), { kind: "mega", project: m }, 18);
    else {
      const pts = (g.type === "line" ? g.path : g.ring).map((x) => map.latLngToContainerPoint(x));
      const ends = g.type === "polygon" ? [...pts, pts[0]!] : pts;
      let d = Infinity;
      for (let i = 1; i < ends.length; i++) d = Math.min(d, segDist(c, ends[i - 1]!, ends[i]!));
      take(d, { kind: "mega", project: m }, 10);
      if (g.type === "polygon" && inside(c, pts)) take(12, { kind: "mega", project: m }, 12);
    }
  }
  return best ? (best as { hit: Hit }).hit : null;
}

// ------------------------------------------------------------------ map layer

const handleIcon = (cls: string, size: number) => L.divIcon({ className: `geo-edit-handle ${cls}`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
const VERTEX = handleIcon("rounded-full bg-white ring-2 ring-[#c99a22] shadow", 14);
const MID = handleIcon("rounded-full bg-[#c99a22]/70 ring-1 ring-white text-[9px] leading-[10px] text-white text-center font-bold", 11);
const PIN = L.divIcon({
  className: "geo-edit-handle",
  html: `<div style="width:30px;height:30px;transform:translate(-50%,-100%);display:flex;align-items:flex-start;justify-content:center"><svg width="30" height="30" viewBox="0 0 24 24" fill="#c99a22" stroke="#ffffff" stroke-width="1.6"><path d="M12 22s7-6.1 7-12a7 7 0 1 0-14 0c0 5.9 7 12 7 12z"/><circle cx="12" cy="10" r="2.6" fill="#ffffff"/></svg></div>`,
  iconSize: [0, 0],
});

/** Draggable vertices with "+" midpoints for a line or an area. */
function VertexEditor({ pts, closed, onChange }: { pts: LatLng[]; closed: boolean; onChange: (pts: LatLng[]) => void }) {
  const [live, setLive] = useState(pts);
  useEffect(() => setLive(pts), [pts]);
  const style = { color: "#c99a22", weight: 3, dashArray: "6 4", fillColor: "#f2dd8f", fillOpacity: 0.18 };
  const mids = live.map((p, i) => {
    const q = live[(i + 1) % live.length]!;
    return { i, at: [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2] as LatLng };
  });
  const usable = closed ? mids : mids.slice(0, -1);
  const min = closed ? 3 : 2;
  return (
    <>
      {closed && live.length >= 3 ? <Polygon positions={live} pathOptions={style} interactive={false} /> : <Polyline positions={live} pathOptions={style} interactive={false} />}
      {live.length >= 2 &&
        usable.map((m) => (
          <Marker
            key={`m${m.i}-${live.length}`}
            position={m.at}
            icon={MID}
            title="Click to add a point here"
            eventHandlers={{
              click: (e) => {
                L.DomEvent.stop(e);
                const next = [...live];
                next.splice(m.i + 1, 0, m.at);
                onChange(next);
              },
            }}
          />
        ))}
      {live.map((p, i) => (
        <Marker
          key={`v${i}-${live.length}`}
          position={p}
          icon={VERTEX}
          draggable
          title="Drag to move · right-click to remove"
          eventHandlers={{
            drag: (e) => {
              const ll = (e.target as L.Marker).getLatLng();
              setLive((cur) => cur.map((x, k) => (k === i ? [ll.lat, ll.lng] : x)));
            },
            dragend: (e) => {
              const ll = (e.target as L.Marker).getLatLng();
              onChange(live.map((x, k) => (k === i ? [ll.lat, ll.lng] : x)));
            },
            contextmenu: (e) => {
              L.DomEvent.stop(e);
              if (live.length > min) onChange(live.filter((_, k) => k !== i));
              else toast.message(`A ${closed ? "area" : "line"} needs at least ${min} points`);
            },
          }}
        />
      ))}
    </>
  );
}

/**
 * Inside the map: intercepts clicks while an edit tool is on (so listing / project popups don't
 * open), draws the draft's pin or vertices.
 */
export function GeoEditLayer({
  mode,
  draft,
  setDraft,
  onPick,
}: {
  mode: EditMode;
  draft: Draft | null;
  setDraft: (d: Draft | null) => void;
  /** A click on the map while a tool is on (not on an edit handle). */
  onPick: (at: L.LatLng) => void;
}) {
  const map = useMap();
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const drawing = !!draft?.drawing;
  useEffect(() => {
    if (!mode) return;
    const el = map.getContainer();
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => (down = { x: e.clientX, y: e.clientY });
    const onClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest(".leaflet-control, .leaflet-popup, .geo-edit-handle")) return;
      if (!t.closest(".leaflet-pane") && !t.classList.contains("leaflet-container")) return;
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return; // a drag, not a click
      e.stopPropagation();
      e.preventDefault();
      pickRef.current(map.mouseEventToLatLng(e));
    };
    el.addEventListener("pointerdown", onDown, true);
    el.addEventListener("click", onClick, true);
    el.style.cursor = "crosshair";
    return () => {
      el.removeEventListener("pointerdown", onDown, true);
      el.removeEventListener("click", onClick, true);
      el.style.cursor = "";
    };
  }, [map, mode]);
  useEffect(() => {
    if (drawing) map.doubleClickZoom.disable();
    else map.doubleClickZoom.enable();
  }, [map, drawing]);

  if (!draft) return null;
  const g = draft.geom;
  if (g.type === "point")
    return g.at ? (
      <Marker
        position={g.at}
        icon={PIN}
        draggable
        zIndexOffset={2000}
        eventHandlers={{ dragend: (e) => setDraft({ ...draft, geom: { ...g, at: [(e.target as L.Marker).getLatLng().lat, (e.target as L.Marker).getLatLng().lng] } }) }}
      />
    ) : null;
  return <VertexEditor pts={g.pts} closed={g.type === "polygon"} onChange={(pts) => setDraft({ ...draft, geom: { ...g, pts } })} />;
}

// ------------------------------------------------------------------ editor panel

const PROJECT_TYPES = ["mall", "tower", "mixed_use", "compound_living", "plaza", "office_complex", "residential_complex"];
const PROJECT_STATUSES = ["planned", "under_construction", "completed"];
const title = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

type Meta = { statuses: string[]; categories: string[]; use_types: string[]; cities: { id: string; name: string }[]; schemes: { id: string; name: string; city_id: string }[] };

/** Loads a picked feature into a draft. */
export async function loadDraft(hit: Hit): Promise<Draft> {
  if (hit.kind === "property") {
    const p = await get(`/admin/properties/${hit.id}`);
    return {
      kind: "property",
      id: p.id,
      fields: { title: p.title, price: p.price, category: p.category, use_type: p.use_type, status: p.status, city_id: p.city_id, scheme_id: p.scheme_id ?? "", bedrooms: p.bedrooms ?? "", bathrooms: p.bathrooms ?? "", total_area: p.total_area ?? "", street_address: p.street_address ?? "", project_id: p.project_id },
      geom: { type: "point", at: p.latitude != null ? [p.latitude, p.longitude] : null },
    };
  }
  if (hit.kind === "project") {
    const b = await get(`/bigprojects/${hit.id}`);
    return {
      kind: "project",
      id: b.id,
      fields: { name: b.name, project_type: b.project_type, status: b.status, city_id: b.city_id, scheme_id: b.scheme_id ?? "", developer: b.developer ?? "", floor_count: b.floor_count ?? "", total_area: b.total_area ?? "", address: b.address ?? "", website: b.website ?? "", description: b.description ?? "" },
      geom: { type: "point", at: b.latitude != null ? [b.latitude, b.longitude] : null },
    };
  }
  const m = hit.project;
  const g = m.geometry!;
  return {
    kind: "mega",
    id: m.id,
    edited: !!m.edited,
    fields: { name: m.name, type: m.type, status: m.status, city: m.city ?? "", province: m.province ?? "", authority: m.authority ?? "", completion: m.completion ?? "", uplift: m.uplift, impact_radius_km: m.impact_radius_km, summary: m.summary ?? "", impact: m.impact ?? "" },
    geom: g.type === "point" ? { type: "point", at: g.center, radius_km: g.radius_km } : { type: g.type, pts: g.type === "line" ? g.path : g.ring },
  };
}

const num = (v: unknown) => (v === "" || v == null ? undefined : Number(v));
const ok = <T,>(r: T) => {
  const e = (r as { error?: string })?.error;
  if (e) throw new Error(e);
  return r;
};

function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <label className={cn("block", wide && "col-span-2")}>
      <span className="mb-1 block text-[11px] font-semibold text-ink-mute">{label}</span>
      {children}
    </label>
  );
}

/** The side panel: the hint while a tool waits for a click, then the selected feature's form. */
export function GeoEditPanel({
  mode,
  draft,
  setDraft,
  onDone,
  megaTypes,
  megaStatuses,
}: {
  mode: EditMode;
  draft: Draft | null;
  setDraft: (d: Draft | null) => void;
  /** Close the editor (after a save / delete or on cancel). */
  onDone: () => void;
  megaTypes: Record<string, string>;
  megaStatuses: Record<string, string>;
}) {
  const qc = useQueryClient();
  const meta = useApi<Meta>(draft && draft.kind !== "mega" ? "/admin/properties/meta" : null, undefined, { staleTime: 10 * 60_000 });
  const [busy, setBusy] = useState(false);
  const f = draft?.fields ?? {};
  const set = (k: string, v: unknown) => draft && setDraft({ ...draft, fields: { ...draft.fields, [k]: v } });
  const schemes = useMemo(() => (meta.data?.schemes ?? []).filter((s) => s.city_id === f.city_id), [meta.data, f.city_id]);

  if (!mode && !draft) return null;
  const hint = !draft
    ? mode === "select"
      ? "Click a listing, a project or a mega project on the map to edit it."
      : mode === "add-mega-line" || mode === "add-mega-polygon"
        ? "Click on the map to start the shape, then keep clicking to add points."
        : "Click on the map where it is."
    : null;

  const refresh = () =>
    qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && ["/properties", "/search", "/bigprojects", "/geo/megaprojects", "/admin/properties", "/portal"].some((p) => (q.queryKey[0] as string).startsWith(p)) });

  const save = async () => {
    if (!draft) return;
    const g = draft.geom;
    setBusy(true);
    try {
      if (draft.kind === "property") {
        if (g.type !== "point" || !g.at) throw new Error("Place the pin on the map");
        const body = { ...f, price: num(f.price), bedrooms: num(f.bedrooms), bathrooms: num(f.bathrooms), total_area: num(f.total_area), scheme_id: f.scheme_id || null, latitude: g.at[0], longitude: g.at[1] };
        delete (body as Record<string, unknown>).project_id;
        ok(draft.id ? await put(`/admin/properties/${draft.id}`, body) : await post("/admin/properties", body));
      } else if (draft.kind === "project") {
        if (g.type !== "point" || !g.at) throw new Error("Place the pin on the map");
        if (!String(f.name ?? "").trim()) throw new Error("A name is required");
        if (!f.city_id) throw new Error("Choose a city");
        const common = { name: f.name, project_type: f.project_type, status: f.status, city_id: f.city_id, scheme_id: f.scheme_id || null, developer: f.developer || null, floor_count: num(f.floor_count), total_area: num(f.total_area), description: f.description || null, latitude: g.at[0], longitude: g.at[1] };
        ok(draft.id ? await put(`/bigprojects/${draft.id}`, { ...common, address: f.address || null, website: f.website || null }) : await post("/bigprojects", common));
      } else {
        const geometry =
          g.type === "point" ? { type: "point", center: g.at, radius_km: g.radius_km ?? 0.5 } : g.type === "line" ? { type: "line", path: g.pts } : { type: "polygon", ring: g.pts };
        const body = { ...f, impact_radius_km: num(f.impact_radius_km), geometry };
        ok(draft.id ? await put(`/geo/megaprojects/${draft.id}`, body) : await post("/geo/megaprojects", body));
      }
      toast.success(draft.id ? "Saved" : "Added");
      await refresh();
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!draft?.id) return;
    const what = draft.kind === "property" ? "listing" : draft.kind === "project" ? "big project" : "mega project";
    if (!window.confirm(`Delete this ${what}? This can't be undone.`)) return;
    setBusy(true);
    try {
      ok(await del(draft.kind === "property" ? `/admin/properties/${draft.id}` : draft.kind === "project" ? `/bigprojects/${draft.id}` : `/geo/megaprojects/${draft.id}`));
      toast.success("Deleted");
      await refresh();
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const reset = async () => {
    if (!draft?.id) return;
    setBusy(true);
    try {
      await post(`/geo/megaprojects/${draft.id}/reset`);
      toast.success("Back to the original");
      await refresh();
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const Icon = draft?.kind === "property" ? MapPin : draft?.kind === "project" ? Building2 : draft?.geom.type === "line" ? Spline : draft?.geom.type === "polygon" ? Square : Milestone;
  const g = draft?.geom;
  return (
    <div className="absolute end-16 top-3 z-[450] flex max-h-[calc(100%-1.5rem)] w-[340px] max-w-[calc(100vw-6rem)] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-black/5 dark:bg-brand-950">
      <div className="flex items-center gap-2 border-b border-black/5 px-4 py-2.5 dark:border-white/10">
        {draft ? <Icon className="h-4 w-4 text-gold-600" /> : <PencilLine className="h-4 w-4 text-gold-600" />}
        <p className="flex-1 text-sm font-semibold">
          {!draft ? "Map editing" : `${draft.id ? "Edit" : "New"} ${draft.kind === "property" ? "listing" : draft.kind === "project" ? "big project" : "mega project"}`}
        </p>
        <button type="button" onClick={onDone} className="btn btn-ghost btn-icon h-7 w-7" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>
      {hint && <p className="px-4 py-3 text-sm text-ink-soft dark:text-slate-300">{hint}</p>}
      {draft && (
        <>
          <div className="grid flex-1 grid-cols-2 gap-2.5 overflow-y-auto px-4 py-3 text-sm">
            {draft.kind === "property" && (
              <>
                <Field label="Title" wide>
                  <input className="input py-1.5 text-sm" value={f.title ?? ""} onChange={(e) => set("title", e.target.value)} />
                </Field>
                <Field label="Price (PKR)">
                  <input className="input py-1.5 text-sm" inputMode="numeric" value={f.price ?? ""} onChange={(e) => set("price", e.target.value)} />
                </Field>
                <Field label="Status">
                  <select className="input py-1.5 text-sm" value={f.status} onChange={(e) => set("status", e.target.value)}>
                    {(meta.data?.statuses ?? [f.status]).map((s) => <option key={s} value={s}>{title(s)}</option>)}
                  </select>
                </Field>
                <Field label="Type">
                  <select className="input py-1.5 text-sm" value={f.category} onChange={(e) => set("category", e.target.value)}>
                    {(meta.data?.categories ?? [f.category]).map((s) => <option key={s} value={s}>{title(s)}</option>)}
                  </select>
                </Field>
                <Field label="Use">
                  <select className="input py-1.5 text-sm" value={f.use_type} onChange={(e) => set("use_type", e.target.value)}>
                    {(meta.data?.use_types ?? [f.use_type]).map((s) => <option key={s} value={s}>{title(s)}</option>)}
                  </select>
                </Field>
                <Field label="Bedrooms">
                  <input className="input py-1.5 text-sm" inputMode="numeric" value={f.bedrooms ?? ""} onChange={(e) => set("bedrooms", e.target.value)} />
                </Field>
                <Field label="Bathrooms">
                  <input className="input py-1.5 text-sm" inputMode="numeric" value={f.bathrooms ?? ""} onChange={(e) => set("bathrooms", e.target.value)} />
                </Field>
                <Field label="Area (sq ft)">
                  <input className="input py-1.5 text-sm" inputMode="numeric" value={f.total_area ?? ""} onChange={(e) => set("total_area", e.target.value)} />
                </Field>
                <Field label="Address" wide>
                  <input className="input py-1.5 text-sm" value={f.street_address ?? ""} onChange={(e) => set("street_address", e.target.value)} />
                </Field>
              </>
            )}
            {draft.kind === "project" && (
              <>
                <Field label="Name" wide>
                  <input className="input py-1.5 text-sm" value={f.name ?? ""} onChange={(e) => set("name", e.target.value)} />
                </Field>
                <Field label="Type">
                  <select className="input py-1.5 text-sm" value={f.project_type} onChange={(e) => set("project_type", e.target.value)}>
                    {PROJECT_TYPES.map((s) => <option key={s} value={s}>{title(s)}</option>)}
                  </select>
                </Field>
                <Field label="Status">
                  <select className="input py-1.5 text-sm" value={f.status} onChange={(e) => set("status", e.target.value)}>
                    {PROJECT_STATUSES.map((s) => <option key={s} value={s}>{title(s)}</option>)}
                  </select>
                </Field>
                <Field label="Developer" wide>
                  <input className="input py-1.5 text-sm" value={f.developer ?? ""} onChange={(e) => set("developer", e.target.value)} />
                </Field>
                <Field label="Floors">
                  <input className="input py-1.5 text-sm" inputMode="numeric" value={f.floor_count ?? ""} onChange={(e) => set("floor_count", e.target.value)} />
                </Field>
                <Field label="Area (sq ft)">
                  <input className="input py-1.5 text-sm" inputMode="numeric" value={f.total_area ?? ""} onChange={(e) => set("total_area", e.target.value)} />
                </Field>
                {draft.id && (
                  <>
                    <Field label="Address" wide>
                      <input className="input py-1.5 text-sm" value={f.address ?? ""} onChange={(e) => set("address", e.target.value)} />
                    </Field>
                    <Field label="Website" wide>
                      <input className="input py-1.5 text-sm" value={f.website ?? ""} onChange={(e) => set("website", e.target.value)} />
                    </Field>
                  </>
                )}
                <Field label="Description" wide>
                  <textarea className="input min-h-16 py-1.5 text-sm" value={f.description ?? ""} onChange={(e) => set("description", e.target.value)} />
                </Field>
              </>
            )}
            {draft.kind !== "mega" && (
              <>
                <Field label="City">
                  <select className="input py-1.5 text-sm" value={f.city_id ?? ""} onChange={(e) => setDraft({ ...draft, fields: { ...f, city_id: e.target.value, scheme_id: "" } })}>
                    <option value="">Choose…</option>
                    {(meta.data?.cities ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </Field>
                <Field label="Housing society">
                  <select className="input py-1.5 text-sm" value={f.scheme_id ?? ""} onChange={(e) => set("scheme_id", e.target.value)}>
                    <option value="">None</option>
                    {schemes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </Field>
              </>
            )}
            {draft.kind === "mega" && (
              <>
                <Field label="Name" wide>
                  <input className="input py-1.5 text-sm" value={f.name ?? ""} onChange={(e) => set("name", e.target.value)} />
                </Field>
                <Field label="Type">
                  <select className="input py-1.5 text-sm" value={f.type} onChange={(e) => set("type", e.target.value)}>
                    {Object.entries(megaTypes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </Field>
                <Field label="Status">
                  <select className="input py-1.5 text-sm" value={f.status} onChange={(e) => set("status", e.target.value)}>
                    {Object.entries(megaStatuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </Field>
                <Field label="City">
                  <input className="input py-1.5 text-sm" value={f.city ?? ""} onChange={(e) => set("city", e.target.value)} />
                </Field>
                <Field label="Province">
                  <input className="input py-1.5 text-sm" value={f.province ?? ""} onChange={(e) => set("province", e.target.value)} />
                </Field>
                <Field label="Authority" wide>
                  <input className="input py-1.5 text-sm" value={f.authority ?? ""} onChange={(e) => set("authority", e.target.value)} />
                </Field>
                <Field label="Completion">
                  <input className="input py-1.5 text-sm" value={f.completion ?? ""} onChange={(e) => set("completion", e.target.value)} />
                </Field>
                <Field label="Price effect">
                  <select className="input py-1.5 text-sm" value={f.uplift} onChange={(e) => set("uplift", e.target.value)}>
                    {["high", "medium", "low"].map((s) => <option key={s} value={s}>{title(s)}</option>)}
                  </select>
                </Field>
                <Field label="Effect reaches (km)">
                  <input className="input py-1.5 text-sm" inputMode="decimal" value={f.impact_radius_km ?? ""} onChange={(e) => set("impact_radius_km", e.target.value)} />
                </Field>
                <Field label="Summary" wide>
                  <textarea className="input min-h-16 py-1.5 text-sm" value={f.summary ?? ""} onChange={(e) => set("summary", e.target.value)} />
                </Field>
                <Field label="Effect on land prices" wide>
                  <textarea className="input min-h-14 py-1.5 text-sm" value={f.impact ?? ""} onChange={(e) => set("impact", e.target.value)} />
                </Field>
              </>
            )}

            {/* geometry */}
            <div className="col-span-2 rounded-xl bg-brand-50/70 p-2.5 dark:bg-white/5">
              <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-mute">
                <Crosshair className="h-3.5 w-3.5" /> Location
              </p>
              {g?.type === "point" ? (
                <div className="grid grid-cols-2 gap-2">
                  <input
                    className="input py-1.5 text-xs tabular-nums"
                    aria-label="Latitude"
                    value={g.at?.[0] ?? ""}
                    placeholder="Latitude"
                    onChange={(e) => setDraft({ ...draft, geom: { ...g, at: [Number(e.target.value), g.at?.[1] ?? 0] } })}
                  />
                  <input
                    className="input py-1.5 text-xs tabular-nums"
                    aria-label="Longitude"
                    value={g.at?.[1] ?? ""}
                    placeholder="Longitude"
                    onChange={(e) => setDraft({ ...draft, geom: { ...g, at: [g.at?.[0] ?? 0, Number(e.target.value)] } })}
                  />
                  <p className="col-span-2 text-[11px] text-ink-mute">
                    Drag the gold pin, or type the coordinates.
                    {draft.kind === "project" && draft.id ? " Its unit listings move with it." : ""}
                    {draft.kind === "property" && f.project_id ? " This is a project unit — it normally follows its project." : ""}
                  </p>
                </div>
              ) : g ? (
                <div className="space-y-1.5 text-xs text-ink-soft dark:text-slate-300">
                  <p>
                    {g.type === "line" ? "Line" : "Area"} with <b>{g.pts.length}</b> points.
                    {draft.drawing ? " Click the map to add points." : " Drag a point to move it, click a + to add one, right-click a point to remove it."}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {draft.drawing ? (
                      <Button size="sm" icon={<Check className="h-3.5 w-3.5" />} disabled={g.pts.length < (g.type === "line" ? 2 : 3)} onClick={() => setDraft({ ...draft, drawing: false })}>
                        Finish shape
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setDraft({ ...draft, geom: { ...g, pts: [] }, drawing: true })}>
                        Redraw
                      </Button>
                    )}
                    {draft.drawing && g.pts.length > 0 && (
                      <Button size="sm" variant="ghost" onClick={() => setDraft({ ...draft, geom: { ...g, pts: g.pts.slice(0, -1) } })}>
                        Undo point
                      </Button>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-2 border-t border-black/5 px-4 py-2.5 dark:border-white/10">
            <Button size="sm" loading={busy} icon={<Save className="h-3.5 w-3.5" />} onClick={save} disabled={!!draft.drawing}>
              {draft.id ? "Save" : "Add"}
            </Button>
            {draft.kind === "mega" && draft.id && draft.edited && (
              <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={reset} disabled={busy}>
                Reset
              </Button>
            )}
            <span className="flex-1" />
            {draft.id && (
              <Button size="sm" variant="ghost" className="text-red-600" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={remove} disabled={busy}>
                Delete
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
