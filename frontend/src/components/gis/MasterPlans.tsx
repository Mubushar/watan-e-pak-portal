/**
 * Master plans (DHA, Bahria Town, other housing societies) as map layers (built locally by backend/masterplans/build_masterplans.py).
 *   GET /masterplans                         plans, bounds, zoom range, tile URL
 *   GET /masterplans/{key}/tiles/{z}/{x}/{y}.png
 *   GET /masterplans/search?q=…              text on the plans (sectors, roads, mosques, plot numbers)
 * With no plans built, the section says so and nothing is drawn.
 *
 * Plan tiles exist only for zooms 12–17, so each plan's boundary is also drawn as an
 * outline (visible at any zoom, click to zoom in) and the tiles are scaled down to zoom 9.
 */
import { useEffect, useState } from "react";
import type L from "leaflet";
import type { FeatureCollection } from "geojson";
import { CircleMarker, Polygon, Rectangle, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Map as MapIcon, Search, Target } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { API_BASE } from "@/lib/api";
import { Badge, Button, EmptyState, Input, Skeleton, Toggle } from "@/components/ui";
import { fitTo } from "./kit";
import type { GisLayer } from "./types";
import { PlanTextLayer } from "./PlanTextLayer";

/** Plan text is drawn from this zoom in; smaller text (plot numbers) appears around zoom 17–18. */
export const LABEL_MIN_ZOOM = 14;

/** Master-plan text drawn as text, at the plan's own size and angle (see PlanTextLayer). */
export function PlanLabels({ data, color }: { data: FeatureCollection; color: string }) {
  const map = useMap();
  useEffect(() => {
    const layer = new PlanTextLayer(data, color).addTo(map);
    return () => {
      layer.remove();
    };
  }, [map, data, color]);
  return null;
}

/** The label layers of one plan, from the GIS layer list ("<plan> — plan labels: <group>"). */
export interface PlanLabelControls {
  layers: GisLayer[];
  on: Set<string>;
  loading: boolean;
  zoomedIn: boolean;
  toggle: (id: string) => void;
}

export interface MasterPlan {
  key: string;
  name: string;
  city?: string;
  center?: [number, number];
  /** [south, west, north, east] */
  bounds: [number, number, number, number];
  tile_url: string | null;
  /** The plan's boundary as [lat, lon] points. */
  outline?: [number, number][] | null;
  zoom?: [number, number];
  accuracy?: { rmse_m?: number };
  attribution?: string;
  /** dha | bahria | societies — each is its own section on the map */
  group?: string;
  group_label?: string;
}

/** The plan sections, in the order the map lists them. */
export const PLAN_GROUPS: { key: string; title: string }[] = [
  { key: "dha", title: "DHA master plans" },
  { key: "bahria", title: "Bahria Town master plans" },
  { key: "societies", title: "Housing society master plans" },
];
export const planGroup = (p: MasterPlan) => p.group ?? "dha";

export interface PlanLabel {
  text: string;
  kind: string;
  plan: string;
  plan_key: string;
  latitude: number;
  longitude: number;
  near?: string;
}

export function useMasterPlans() {
  return useApi<{ count: number; plans: MasterPlan[]; attribution?: string }>("/masterplans", undefined, { staleTime: 30 * 60_000 });
}

const corners = (b: MasterPlan["bounds"]): [number, number][] => [
  [b[0], b[1]],
  [b[2], b[3]],
];

/** Tile layers, boundaries + the highlighted search hit; render inside the map. */
export function MasterPlanLayers({
  plans,
  shown,
  opacity,
  hit,
  onSelect,
}: {
  plans: MasterPlan[];
  shown: Set<string>;
  opacity: number;
  hit?: PlanLabel | null;
  /** Clicking a plan's boundary (e.g. to zoom to it). */
  onSelect?: (p: MasterPlan) => void;
}) {
  const map = useMap();
  const visible = plans.filter((p) => shown.has(p.key));
  const style = { color: "#c99a22", weight: 2, dashArray: "6 5", fillColor: "#f2dd8f", fillOpacity: 0.06 };
  return (
    <>
      {visible.map((p) => {
        // No cursor tooltip (it covered the plan); a click zooms to the phase only from far out,
        // so clicks while reading the plan never move the map.
        const eventHandlers = onSelect ? { click: () => map.getZoom() < 14 && onSelect(p) } : undefined;
        return p.outline?.length ? (
          <Polygon key={`outline-${p.key}`} positions={p.outline} pathOptions={style} eventHandlers={eventHandlers} />
        ) : (
          <Rectangle key={`outline-${p.key}`} bounds={corners(p.bounds)} pathOptions={style} eventHandlers={eventHandlers} />
        );
      })}
      {visible
        .filter((p) => p.tile_url)
        .map((p) => (
          <TileLayer
            key={p.key}
            url={`${API_BASE}${p.tile_url}`}
            bounds={corners(p.bounds)}
            // Native tiles start at zoom 12; Leaflet scales them down a few levels so the plan
            // is still visible when the whole phase is on screen.
            minNativeZoom={p.zoom?.[0]}
            minZoom={p.zoom ? Math.max(9, p.zoom[0] - 3) : undefined}
            maxNativeZoom={p.zoom?.[1]}
            maxZoom={20}
            opacity={opacity}
            attribution={p.attribution}
            zIndex={250}
          />
        ))}
      {hit && (
        <CircleMarker center={[hit.latitude, hit.longitude]} radius={10} pathOptions={{ color: "#c99a22", weight: 3, fillColor: "#f2dd8f", fillOpacity: 0.6 }}>
          <Tooltip permanent direction="top">
            <span className="font-semibold">{hit.text}</span> · {hit.plan}
          </Tooltip>
        </CircleMarker>
      )}
    </>
  );
}

/** Side-panel section: list, toggle and search the plans. */
export function MasterPlanPanel({
  map,
  shown,
  setShown,
  onHit,
  pad,
  labels,
  only,
}: {
  labels?: PlanLabelControls;
  /** The plans the map can draw (their layers are published); others are not listed. */
  only?: MasterPlan[];
  map: L.Map | null;
  shown: Set<string>;
  setShown: (s: Set<string>) => void;
  onHit: (l: PlanLabel | null) => void;
  pad: () => { start?: number; bottom?: number };
}) {
  const q = useMasterPlans();
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const hits = useApi<{ count: number; results: PlanLabel[]; note?: string }>(query ? "/masterplans/search" : null, { q: query, limit: 12 });
  const built = q.data?.plans ?? [];
  const plans = only ?? built;
  const show = (key: string, on: boolean) => {
    const n = new Set(shown);
    if (on) n.add(key);
    else n.delete(key);
    setShown(n);
  };

  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-ink-mute">
        <MapIcon className="h-3.5 w-3.5" /> Master plans
      </p>
      {q.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : !built.length ? (
        <EmptyState title="No master plans loaded" hint="Build them on the server with backend/masterplans/build_masterplans.py." />
      ) : !plans.length ? (
        <EmptyState title="Master plans are hidden" hint="An administrator can show them in Administration › GIS layers (publish the master plan layers)." />
      ) : (
        <>
          {PLAN_GROUPS.map((g) => ({ ...g, plans: plans.filter((p) => planGroup(p) === g.key) }))
            .filter((g) => g.plans.length)
            .map((g) => (
              <div key={g.key} className="space-y-2">
                <p className="text-[11px] font-semibold text-ink-soft dark:text-slate-300">{g.title}</p>
          {g.plans.map((p) => (
            <div key={p.key} className="flex items-center gap-3 rounded-xl border border-black/5 p-3 dark:border-white/10">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{p.name}</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {p.city && <Badge tone="gray">{p.city}</Badge>}
                  {!!p.accuracy?.rmse_m && <span className="text-[11px] text-ink-mute">± {Math.round(p.accuracy.rmse_m)} m</span>}
                  {!p.tile_url && <span className="text-[11px] text-ink-mute">labels only</span>}
                </div>
              </div>
              <Button
                size="sm"
                variant="soft"
                icon={<Target className="h-3.5 w-3.5" />}
                onClick={() => {
                  show(p.key, true);
                  fitTo(map, corners(p.bounds), 16, pad());
                }}
              >
                Zoom
              </Button>
              <Toggle checked={shown.has(p.key)} onChange={(v) => show(p.key, v)} />
            </div>
          ))}
              </div>
            ))}
          {!!labels?.layers.length && (
            <div className="rounded-xl bg-brand-50/60 p-3 dark:bg-white/5">
              <p className="text-xs font-semibold">Text from the plans</p>
              <p className="mt-0.5 text-[11px] text-ink-mute">
                Sector, road and park names, plot numbers and sizes, written on the map at the plan's own size — zoom in for the
                smaller text (plot numbers from about zoom 17). Shown from zoom {LABEL_MIN_ZOOM}
                {labels.on.size && !labels.zoomedIn ? " — zoom in to see them." : "."}
                {labels.loading && " Loading…"}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {labels.layers.map((l) => {
                  const on = labels.on.has(l.id);
                  return (
                    <button
                      key={l.id}
                      type="button"
                      onClick={() => labels.toggle(l.id)}
                      title={`${l.features.toLocaleString()} labels`}
                      className={on ? "chip bg-brand-700 text-white" : "chip bg-white text-ink-soft ring-1 ring-black/10 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10"}
                    >
                      {l.name.replace(" — plan labels: ", " · ")}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(text.trim());
            }}
          >
            <Input icon={<Search className="h-4 w-4" />} value={text} onChange={(e) => setText(e.target.value)} placeholder="Find on the plans: sector, road, mosque, plot…" />
          </form>
          {query &&
            (hits.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : !hits.data?.results.length ? (
              <p className="text-xs text-ink-mute">Nothing on the plans matches “{query}”.</p>
            ) : (
              <div className="space-y-1">
                {hits.data.results.map((h, i) => (
                  <button
                    key={`${h.plan_key}-${i}`}
                    onClick={() => {
                      show(h.plan_key, true);
                      onHit(h);
                      map?.flyTo([h.latitude, h.longitude], 17, { duration: 0.8 });
                    }}
                    className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-start text-sm transition hover:bg-brand-50 dark:hover:bg-white/5"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold">{h.text}</span>
                      <span className="block truncate text-[11px] text-ink-mute">
                        {h.kind} · {h.plan}
                        {h.near ? ` · near ${h.near}` : ""}
                      </span>
                    </span>
                  </button>
                ))}
                {hits.data.note && <p className="px-2 text-[11px] text-ink-mute">{hits.data.note}</p>}
              </div>
            ))}
        </>
      )}
    </div>
  );
}
