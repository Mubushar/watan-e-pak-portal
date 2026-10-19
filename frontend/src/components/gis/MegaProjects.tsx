/**
 * Infrastructure & development mega projects that move land prices (GET /geo/megaprojects):
 * ring roads, motorways, expressways, mass transit, rail, new sectors, industrial / economic
 * zones, airports and business districts.
 *
 *   MegaProjectLayer   the projects on a Leaflet map, styled by type and status, with
 *                      optional annotations (name, status, completion, size, price effect)
 *   MegaProjectCard    a project's details (used in map popups and the Infrastructure page)
 */
import { Fragment } from "react";
import { Circle, Marker, Polygon, Polyline, Popup, Tooltip } from "react-leaflet";
import { iconPin } from "@/components/map/PortalMap";
import { Link } from "react-router-dom";
import { Building, CalendarRange, Construction, Factory, Landmark, Plane, Route, TrainFront, TramFront, type LucideIcon } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { num } from "@/lib/format";
import { cn } from "@/lib/utils";
import { labelText, type MapLang } from "./PakistanLayers";

export interface MegaProject {
  id: string;
  name: string;
  name_ur?: string;
  type: string;
  type_label: string;
  status: "planned" | "approved" | "under_construction" | "completed";
  status_label: string;
  city: string;
  province: string;
  authority?: string;
  start_year?: number | null;
  completion?: string;
  length_km?: number;
  area_acres?: number;
  summary: string;
  impact: string;
  uplift: "high" | "medium" | "low";
  impact_radius_km: number;
  bounds: [number, number, number, number];
  center: [number, number];
  geometry?: { type: "line"; path: [number, number][] } | { type: "polygon"; ring: [number, number][] } | { type: "point"; center: [number, number]; radius_km: number };
  /** An inventory project (edited as a big project). */
  portal_project?: boolean;
  /** A shipped project an admin has changed / one an admin added. */
  edited?: boolean;
  created_by_admin?: boolean;
  /** From /near and the study report. */
  distance_km?: number;
  inside?: boolean;
  effect?: number;
}

export const MEGA_TYPES: {
  key: string;
  label: string;
  color: string;
  icon: LucideIcon;
}[] = [
  { key: "ring_road", label: "Ring roads", color: "#dc2626", icon: Route },
  { key: "motorway", label: "Motorways", color: "#2563eb", icon: Route },
  {
    key: "expressway",
    label: "Expressways & avenues",
    color: "#ea580c",
    icon: Route,
  },
  {
    key: "transit",
    label: "Mass transit (BRT / metro)",
    color: "#db2777",
    icon: TramFront,
  },
  { key: "railway", label: "Railways", color: "#475569", icon: TrainFront },
  {
    key: "subdivision",
    label: "New sectors & cities",
    color: "#16a34a",
    icon: Landmark,
  },
  {
    key: "industrial",
    label: "Industrial & economic zones",
    color: "#9333ea",
    icon: Factory,
  },
  { key: "airport", label: "Airports", color: "#0891b2", icon: Plane },
  { key: "cbd", label: "Business districts", color: "#ca8a04", icon: Building },
  { key: "tower", label: "High-rise & mixed-use projects", color: "#0f766e", icon: Building },
];
export const megaColor = (t: string) => MEGA_TYPES.find((x) => x.key === t)?.color ?? "#64748b";
export const megaIcon = (t: string) => MEGA_TYPES.find((x) => x.key === t)?.icon ?? Construction;

export const STATUS_STYLE: Record<string, { dash?: string; cls: string }> = {
  completed: {
    cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200",
  },
  under_construction: {
    dash: "14 7",
    cls: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200",
  },
  approved: {
    dash: "4 8",
    cls: "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200",
  },
  planned: {
    dash: "2 9",
    cls: "bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-slate-300",
  },
};
const UPLIFT_CLS: Record<string, string> = {
  high: "text-emerald-700 dark:text-emerald-400",
  medium: "text-amber-700 dark:text-amber-400",
  low: "text-ink-mute",
};

export function useMegaProjects() {
  return useApi<{ count: number; note: string; projects: MegaProject[] }>("/geo/megaprojects", undefined, { staleTime: 60 * 60_000 });
}

export function StatusPill({ p, className }: { p: Pick<MegaProject, "status" | "status_label">; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold", STATUS_STYLE[p.status]?.cls, className)}>{p.status_label}</span>;
}

export function MegaProjectCard({ p, compact, onMap }: { p: MegaProject; compact?: boolean; onMap?: boolean }) {
  const Icon = megaIcon(p.type);
  return (
    <div className={cn("space-y-2", compact ? "w-64" : "")}>
      <div className="flex items-start gap-2.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: megaColor(p.type) }}>
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="font-display text-sm font-bold leading-tight">{p.name}</p>
          {p.name_ur && <p className="map-ur text-xs text-ink-mute">{p.name_ur}</p>}
          <p className="text-[11px] text-ink-mute">
            {p.type_label} · {p.city}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <StatusPill p={p} />
        {p.length_km ? <span className="chip bg-black/5 dark:bg-white/10">{num(p.length_km)} km</span> : null}
        {p.area_acres ? <span className="chip bg-black/5 dark:bg-white/10">{num(p.area_acres)} acres</span> : null}
        <span className="chip bg-black/5 dark:bg-white/10">
          <CalendarRange className="me-1 h-3 w-3" />
          {p.start_year ? `${p.start_year} → ` : ""}
          {p.completion ?? "TBA"}
        </span>
      </div>
      <p className="text-xs leading-relaxed">{p.summary}</p>
      <p className="rounded-lg bg-brand-50/70 p-2 text-xs leading-relaxed dark:bg-white/5">
        <span className={cn("font-bold", UPLIFT_CLS[p.uplift])}>Price effect: {p.uplift}</span> · reaches ~{p.impact_radius_km} km. {p.impact}
      </p>
      {p.authority && <p className="text-[10px] text-ink-mute">{p.authority}</p>}
      {onMap && (
        <Link to={`/infrastructure#${p.id}`} className="link text-xs font-semibold">
          All infrastructure projects →
        </Link>
      )}
    </div>
  );
}

/** Zoom from which annotations are shown (below it the map is too crowded). */
export const ANNOTATION_MIN_ZOOM = 7;

/** A project's annotation: name, then status · completion · size, then the price effect when zoomed in. */
function Annotation({ p, label, zoom }: { p: MegaProject; label: string; zoom: number }) {
  const size = p.length_km ? `${num(p.length_km)} km` : p.area_acres ? `${num(p.area_acres)} acres` : null;
  return (
    <div className="mega-annot-body" style={{ borderInlineStartColor: megaColor(p.type) }}>
      <p className="mega-annot-name">{label}</p>
      <p className="mega-annot-meta">
        <span className="mega-annot-dot" style={{ background: p.status === "completed" ? "#059669" : p.status === "under_construction" ? "#d97706" : "#64748b" }} />
        {[p.status_label, p.completion && p.completion !== "TBA" ? `→ ${p.completion}` : null, size].filter(Boolean).join(" · ")}
      </p>
      {zoom >= 10 && (
        <p className="mega-annot-meta">
          {p.type_label} · price effect {p.uplift}, ~{p.impact_radius_km} km
        </p>
      )}
    </div>
  );
}

/**
 * The projects on the map. `types` limits which kinds are drawn. With `annotate`, each project
 * carries an annotation from zoom 7; otherwise its name shows from `labelZoom` (or on hover).
 */
export function MegaProjectLayer({
  projects,
  types,
  lang,
  zoom,
  selected,
  labelZoom = 10,
  annotate = false,
}: {
  projects: MegaProject[];
  types?: Set<string>;
  lang: MapLang;
  zoom: number;
  selected?: string | null;
  labelZoom?: number;
  annotate?: boolean;
}) {
  return (
    <>
      {projects.map((p) => {
        if (types && !types.has(p.type)) return null;
        const g = p.geometry;
        if (!g) return null;
        const color = megaColor(p.type);
        const sel = selected === p.id;
        const dash = STATUS_STYLE[p.status]?.dash;
        const label = labelText(p.name, p.name_ur, lang);
        const annot = annotate && (zoom >= ANNOTATION_MIN_ZOOM || sel);
        const perm = annot || zoom >= labelZoom || sel;
        // `permanent` is fixed when a tooltip is created, so the key remounts it on change.
        const tip = annot ? (
          <Tooltip key={`annot-${zoom >= 10}`} permanent direction="top" offset={[0, -6]} className="mega-annot" opacity={1}>
            <Annotation p={p} label={label} zoom={zoom} />
          </Tooltip>
        ) : (
          <Tooltip key={perm ? "label" : "hover"} permanent={perm} sticky={!perm} direction="top" className="mega-tip">
            {label}
          </Tooltip>
        );
        const popup = (
          <Popup maxWidth={300}>
            <MegaProjectCard p={p} compact onMap />
          </Popup>
        );
        if (g.type === "line")
          return (
            <Fragment key={p.id}>
              <Polyline
                positions={g.path}
                pathOptions={{
                  color: "#ffffff",
                  weight: sel ? 11 : 8,
                  opacity: 0.9,
                  lineCap: "round",
                }}
                interactive={false}
              />
              <Polyline
                positions={g.path}
                pathOptions={{
                  color,
                  weight: sel ? 7 : 5,
                  opacity: 1,
                  dashArray: dash,
                  lineCap: "round",
                }}
              >
                {tip}
                {popup}
              </Polyline>
            </Fragment>
          );
        if (g.type === "polygon")
          return (
            <Polygon
              key={p.id}
              positions={g.ring}
              pathOptions={{
                color,
                weight: sel ? 4 : 2.5,
                dashArray: dash,
                fillColor: color,
                fillOpacity: sel ? 0.25 : 0.14,
              }}
            >
              {tip}
              {popup}
            </Polygon>
          );
        return (
          <Fragment key={p.id}>
            <Circle
              center={g.center}
              radius={g.radius_km * 1000}
              pathOptions={{
                color,
                weight: sel ? 4 : 2.5,
                dashArray: dash,
                fillColor: color,
                fillOpacity: sel ? 0.25 : 0.14,
              }}
            >
              {tip}
              {popup}
            </Circle>
            {/* a pin with the project type's icon (tower, mall, interchange, zone …) */}
            <Marker position={g.center} icon={iconPin(color, megaIcon(p.type), { size: zoom < 11 ? 26 : 32 })}>
              {tip}
              {popup}
            </Marker>
          </Fragment>
        );
      })}
    </>
  );
}
