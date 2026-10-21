/**
 * Master plans (DHA, Bahria Town, other housing societies) as map layers (built locally by backend/masterplans/build_masterplans.py).
 *   GET /masterplans                         plans, bounds, zoom range, tile URL
 *   GET /masterplans/{key}/tiles/{z}/{x}/{y}.png
 *   GET /masterplans/search?q=…              text on the plans (sectors, roads, mosques, plot numbers)
 * With no plans built, the section says so and nothing is drawn.
 *
 * Plan tiles exist only for zooms 12–17, so each plan's boundary is also drawn as an
 * outline (visible at any zoom, click to zoom in) and the tiles are scaled down to zoom 11.
 * With 100+ plans, only the tile layers of plans in (or next to) the view are on the map: every
 * Leaflet tile layer re-plans its whole grid on each pan / zoom, and 129 of them froze the page.
 */
import { useEffect, useMemo, useState } from "react";
import type L from "leaflet";
import type { FeatureCollection } from "geojson";
import { CircleMarker, Polygon, Rectangle, TileLayer, Tooltip, useMap } from "react-leaflet";
import { ChevronDown, Map as MapIcon, Search, Target } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { API_BASE } from "@/lib/api";
import { EmptyState, Input, Skeleton, Toggle } from "@/components/ui";
import { cn } from "@/lib/utils";
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
  { key: "cda", title: "Islamabad sectors (CDA)" },
];
export const planGroup = (p: MasterPlan) => p.group ?? "dha";
/** The society a plan belongs to (its phases / sections / sheets are grouped under it). */
const FAMILIES: [RegExp, string][] = [
  [/^DHA /, "DHA"],
  [/^(Sector [A-I]-\d+|[A-I]-\d+\b)/, "CDA sectors"],
  [/^Islamabad (zon|master plan)/i, "Islamabad zoning"],
  [/^Bahria Town Lahore/, "Bahria Town Lahore"],
  [/^Bahria Town Karachi/, "Bahria Town Karachi"],
  [/^Bahria Nasheman/, "Bahria Nasheman"],
  [/^Bahria Enclave/, "Bahria Enclave"],
  [/^Bahria (Town|Garden City|Paradise)/, "Bahria Town"],
  [/^Multi Gardens/, "Multi Gardens (MPCHS)"],
  [/^Faisal Town/, "Faisal Town"],
  [/^Faisal Hills/, "Faisal Hills"],
  [/^Jinnah Garden/, "Jinnah Garden"],
  [/^Rudn Enclave/, "Rudn Enclave"],
  [/^Capital Smart City/, "Capital Smart City"],
  [/^Park View City/, "Park View City"],
  [/^Taj Residencia/, "Taj Residencia"],
];
export const planFamily = (p: MasterPlan) => FAMILIES.find(([re]) => re.test(p.name))?.[1] ?? p.name;
/** The plan's name within its society: "DHA Phase II" → "Phase II", "Bahria Town Lahore — Sector A" → "Sector A". */
export function phaseLabel(p: MasterPlan, family = planFamily(p)): string {
  let n = p.name;
  if (n.startsWith(family)) n = n.slice(family.length);
  else if (family.startsWith("Bahria ") && n.startsWith("Bahria ")) n = n.slice(7).replace(/^Town /, "");
  n = n.replace(/^[\s—:–-]+/, "").trim();
  return n || "Master plan";
}
/** Cities in the portal's priority order (Islamabad first), others alphabetically. */
const CITY_ORDER = ["Islamabad", "Rawalpindi", "Lahore", "Karachi"];
const cityRank = (c: string) => (CITY_ORDER.includes(c) ? CITY_ORDER.indexOf(c) : CITY_ORDER.length);

export interface PlanCity {
  city: string;
  societies: { name: string; plans: MasterPlan[] }[];
  plans: MasterPlan[];
}
/** Plans as city → society → phase. */
export function groupPlans(plans: MasterPlan[]): PlanCity[] {
  const by = new Map<string, Map<string, MasterPlan[]>>();
  for (const p of plans) {
    const city = p.city || "Other";
    const fam = planFamily(p);
    if (!by.has(city)) by.set(city, new Map());
    const m = by.get(city)!;
    if (!m.has(fam)) m.set(fam, []);
    m.get(fam)!.push(p);
  }
  const cmp = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });
  return [...by.entries()]
    .sort(([a], [b]) => cityRank(a) - cityRank(b) || cmp(a, b))
    .map(([city, m]) => {
      const societies = [...m.entries()]
        .sort(([a], [b]) => cmp(a, b))
        .map(([name, ps]) => ({ name, plans: ps.sort((x, y) => cmp(phaseLabel(x, name), phaseLabel(y, name))) }));
      return { city, societies, plans: societies.flatMap((s) => s.plans) };
    });
}

/** The plan a generated layer belongs to ("<plan> — boundary / master plan / plan labels: …"), lower-cased.
 *  Plan names may themselves contain " — " (e.g. "Bahria Town Lahore — Sector A"). */
export const planOfLayer = (name: string) => name.replace(/ — (boundary|master plan|plan labels: .*)$/, "").toLowerCase();

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

/** Plan images are drawn from this zoom in (scaled down from 12); further out only outlines. */
const TILES_FROM_ZOOM = 11;

/** The map view (padded by half a screen each way) and zoom, updated when a move / zoom ends. */
function useViewBox(map: L.Map): { box: [number, number, number, number]; zoom: number } {
  const read = () => {
    const b = map.getBounds().pad(0.5);
    return { box: [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()] as [number, number, number, number], zoom: map.getZoom() };
  };
  const [view, setView] = useState(read);
  useEffect(() => {
    const on = () => setView(read());
    map.on("moveend", on);
    return () => {
      map.off("moveend", on);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);
  return view;
}

const overlaps = (b: MasterPlan["bounds"], v: [number, number, number, number]) => b[0] < v[2] && b[2] > v[0] && b[1] < v[3] && b[3] > v[1];

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
  const view = useViewBox(map);
  const visible = plans.filter((p) => shown.has(p.key));
  const tiled = view.zoom >= TILES_FROM_ZOOM ? visible.filter((p) => p.tile_url && overlaps(p.bounds, view.box)) : [];
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
      {tiled.map((p) => (
        <TileLayer
          key={p.key}
          url={`${API_BASE}${p.tile_url}`}
          bounds={corners(p.bounds)}
          // Native tiles start at zoom 12; Leaflet scales them down a level so the plan
          // is still visible when the whole phase is on screen.
          minNativeZoom={p.zoom?.[0]}
          minZoom={p.zoom ? Math.max(TILES_FROM_ZOOM, p.zoom[0] - 1) : TILES_FROM_ZOOM}
          maxNativeZoom={p.zoom?.[1]}
          maxZoom={20}
          // Load tiles once a pan / zoom ends, not on every animation frame.
          updateWhenIdle
          updateWhenZooming={false}
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
  const show = (key: string, on: boolean) => showAll([key], on);
  const showAll = (keys: string[], on: boolean) => {
    const n = new Set(shown);
    keys.forEach((k) => (on ? n.add(k) : n.delete(k)));
    setShown(n);
  };
  const tree = useMemo(() => groupPlans(plans), [plans]);
  // Cities and societies start folded, except the first city (Islamabad), so the list stays short.
  const [openCity, setOpenCity] = useState<Set<string>>(() => new Set());
  const [openSoc, setOpenSoc] = useState<Set<string>>(() => new Set());
  const cityOpen = (c: string) => openCity.has(c) !== (c === tree[0]?.city);
  const flip = (set: Set<string>, k: string) => {
    const n = new Set(set);
    if (n.has(k)) n.delete(k);
    else n.add(k);
    return n;
  };
  const zoomTo = (ps: MasterPlan[]) => {
    showAll(ps.map((x) => x.key), true);
    const b: MasterPlan["bounds"] = [
      Math.min(...ps.map((x) => x.bounds[0])),
      Math.min(...ps.map((x) => x.bounds[1])),
      Math.max(...ps.map((x) => x.bounds[2])),
      Math.max(...ps.map((x) => x.bounds[3])),
    ];
    fitTo(map, corners(b), ps.length > 1 ? 15 : 16, pad());
  };
  const count = (ps: MasterPlan[]) => ps.filter((x) => shown.has(x.key)).length;

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
          {/* City → society → phase, each level with its own switch. */}
          <div className="space-y-2">
            {tree.map((c) => {
              const open = cityOpen(c.city);
              const on = count(c.plans);
              return (
                <div key={c.city} className="rounded-xl border border-black/5 dark:border-white/10">
                  <div className="flex items-center gap-2 px-3 py-2.5">
                    <button
                      type="button"
                      onClick={() => setOpenCity((s) => flip(s, c.city))}
                      className="flex min-w-0 flex-1 items-center gap-2 text-start"
                      aria-expanded={open}
                    >
                      <ChevronDown className={cn("h-4 w-4 shrink-0 text-ink-mute transition", !open && "-rotate-90")} />
                      <span className="truncate text-sm font-bold">{c.city}</span>
                      <span className="text-[11px] text-ink-mute">
                        {c.societies.length} {c.societies.length === 1 ? "society" : "societies"} · {on}/{c.plans.length} on
                      </span>
                    </button>
                    <Toggle checked={on > 0} onChange={(v) => showAll(c.plans.map((x) => x.key), v)} />
                  </div>
                  {open && (
                    <div className="space-y-1 border-t border-black/5 px-2 py-2 dark:border-white/10">
                      {c.societies.map((soc) => {
                        const k = `${c.city}|${soc.name}`;
                        const many = soc.plans.length > 1;
                        const socOpen = openSoc.has(k);
                        const sOn = count(soc.plans);
                        const one = soc.plans[0]!;
                        return (
                          <div key={k} className="rounded-lg bg-black/[0.02] dark:bg-white/[0.03]">
                            <div className="flex items-center gap-2 px-2 py-1.5">
                              <button
                                type="button"
                                disabled={!many}
                                onClick={() => setOpenSoc((s) => flip(s, k))}
                                className="flex min-w-0 flex-1 items-center gap-1.5 text-start"
                                aria-expanded={many ? socOpen : undefined}
                              >
                                {many ? (
                                  <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 text-ink-mute transition", !socOpen && "-rotate-90")} />
                                ) : (
                                  <MapIcon className="h-3.5 w-3.5 shrink-0 text-ink-mute" />
                                )}
                                <span className="min-w-0">
                                  <span className="block truncate text-sm font-semibold">{soc.name}</span>
                                  <span className="block truncate text-[11px] text-ink-mute">
                                    {many
                                      ? `${soc.plans.length} plans · ${sOn} on`
                                      : [phaseLabel(one, soc.name), one.accuracy?.rmse_m ? `± ${Math.round(one.accuracy.rmse_m)} m` : ""].filter((x) => x && x !== "Master plan").join(" · ")}
                                    {!many && !one.tile_url && " · labels only"}
                                  </span>
                                </span>
                              </button>
                              <button
                                type="button"
                                onClick={() => zoomTo(soc.plans)}
                                className="rounded-md p-1.5 text-brand-700 hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-white/10"
                                title={`Zoom to ${soc.name}`}
                                aria-label={`Zoom to ${soc.name}`}
                              >
                                <Target className="h-4 w-4" />
                              </button>
                              <Toggle checked={sOn > 0} onChange={(v) => showAll(soc.plans.map((x) => x.key), v)} />
                            </div>
                            {many && socOpen && (
                              <div className="pb-1.5 ps-7 pe-2">
                                {soc.plans.map((p) => (
                                  <div key={p.key} className="flex items-center gap-2 py-1">
                                    <span className="min-w-0 flex-1">
                                      <span className="block truncate text-xs font-medium">{phaseLabel(p, soc.name)}</span>
                                      {!!p.accuracy?.rmse_m && <span className="block text-[10px] text-ink-mute">± {Math.round(p.accuracy.rmse_m)} m</span>}
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => zoomTo([p])}
                                      className="rounded-md p-1 text-brand-700 hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-white/10"
                                      title={`Zoom to ${p.name}`}
                                      aria-label={`Zoom to ${p.name}`}
                                    >
                                      <Target className="h-3.5 w-3.5" />
                                    </button>
                                    <Toggle checked={shown.has(p.key)} onChange={(v) => show(p.key, v)} />
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
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
