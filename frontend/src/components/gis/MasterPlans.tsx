/**
 * DHA master plans as map layers (built locally by backend/masterplans/build_masterplans.py).
 *   GET /masterplans                         plans, bounds, zoom range, tile URL
 *   GET /masterplans/{key}/tiles/{z}/{x}/{y}.png
 *   GET /masterplans/search?q=…              text on the plans (sectors, roads, mosques, plot numbers)
 * With no plans built, the section says so and nothing is drawn.
 */
import { useState } from "react";
import type L from "leaflet";
import { CircleMarker, TileLayer, Tooltip } from "react-leaflet";
import { Map as MapIcon, Search, Target } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { API_BASE } from "@/lib/api";
import { Badge, Button, EmptyState, Input, Skeleton, Toggle } from "@/components/ui";
import { fitTo } from "./kit";

export interface MasterPlan {
  key: string;
  name: string;
  city?: string;
  center?: [number, number];
  /** [south, west, north, east] */
  bounds: [number, number, number, number];
  tile_url: string | null;
  zoom?: [number, number];
  accuracy?: { rmse_m?: number };
  attribution?: string;
}
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

/** Tile layers + the highlighted search hit; render inside the map. */
export function MasterPlanLayers({ plans, shown, opacity, hit }: { plans: MasterPlan[]; shown: Set<string>; opacity: number; hit?: PlanLabel | null }) {
  return (
    <>
      {plans
        .filter((p) => p.tile_url && shown.has(p.key))
        .map((p) => (
          <TileLayer
            key={p.key}
            url={`${API_BASE}${p.tile_url}`}
            bounds={corners(p.bounds)}
            minZoom={p.zoom?.[0]}
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
}: {
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
  const plans = q.data?.plans ?? [];
  const show = (key: string, on: boolean) => {
    const n = new Set(shown);
    if (on) n.add(key);
    else n.delete(key);
    setShown(n);
  };

  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-ink-mute">
        <MapIcon className="h-3.5 w-3.5" /> DHA master plans
      </p>
      {q.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : !plans.length ? (
        <EmptyState title="No master plans loaded" hint="Build them on the server with backend/masterplans/build_masterplans.py." />
      ) : (
        <>
          {plans.map((p) => (
            <div key={p.key} className="flex items-center gap-3 rounded-xl border border-black/5 p-3 dark:border-white/10">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{p.name}</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {p.city && <Badge tone="gray">{p.city}</Badge>}
                  {p.accuracy?.rmse_m && <span className="text-[11px] text-ink-mute">± {Math.round(p.accuracy.rmse_m)} m</span>}
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
