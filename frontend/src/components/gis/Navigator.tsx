/**
 * Map search + route finder ("navigator") for the map explorer.
 *   - Search bar: type-ahead places / addresses (PlaceSearch); the result gets a pin with
 *     "Directions to here" / "from here".
 *   - Route finder: From / To (search, your location, "pick on the map", right-click
 *     "Directions from / to here", or drag the A / B markers), drive / bike / walk, up to three
 *     routes on real roads (GET /geo/directions) with turn-by-turn steps.
 * State lives in useNavigator(); render <NavigatorLayer> inside the map and <NavigatorPanel> over it.
 */
import { useEffect, useState } from "react";
import { Marker, Polyline, Popup, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { ArrowDownUp, Bike, Car, ChevronDown, CircleDot, Crosshair, Footprints, Loader2, MapPin, Navigation, Route, X } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { pin } from "@/components/map/PortalMap";
import { PlaceSearch, type PlaceHit } from "./PlaceSearch";

type Mode = "drive" | "bike" | "walk";
interface Step {
  instruction: string;
  road: string | null;
  distance_text: string;
  duration_s: number;
}
interface RouteOption {
  label: string;
  distance_text: string;
  duration_text: string;
  duration_s: number;
  via: string[];
  geometry: [number, number][];
  steps: Step[];
}
interface Directions {
  mode: Mode;
  source: "osm" | "portal";
  traffic_factor: number;
  routes: RouteOption[];
  attribution: string;
}

export function useNavigator() {
  const [hit, setHit] = useState<PlaceHit | null>(null);
  const [routing, setRouting] = useState(false);
  const [from, setFrom] = useState<PlaceHit | null>(null);
  const [to, setTo] = useState<PlaceHit | null>(null);
  const [mode, setMode] = useState<Mode>("drive");
  const [picking, setPicking] = useState<"from" | "to" | null>(null);
  const [selected, setSelected] = useState(0);
  const q = useApi<Directions>(
    routing && from && to ? "/geo/directions" : null,
    from && to ? { from_lat: from.lat, from_lon: from.lon, to_lat: to.lat, to_lon: to.lon, mode } : undefined,
    { staleTime: 10 * 60_000, retry: false },
  );
  useEffect(() => setSelected(0), [q.data]);
  return { hit, setHit, routing, setRouting, from, setFrom, to, setTo, mode, setMode, picking, setPicking, selected, setSelected, q };
}
export type NavigatorState = ReturnType<typeof useNavigator>;

/** Fly to a picked place (its bounds when it has them). */
function useFly() {
  const map = useMap();
  return (h: PlaceHit) => {
    if (h.bounds) map.flyToBounds([[h.bounds[0], h.bounds[1]], [h.bounds[2], h.bounds[3]]], { maxZoom: 16, duration: 0.8 });
    else map.flyTo([h.lat, h.lon], h.zoom ?? 16, { duration: 0.8 });
  };
}

/** Map side: the search pin, route lines, A / B markers, picking points by clicking. */
export function NavigatorLayer({ nav }: { nav: NavigatorState }) {
  const map = useMap();
  const fly = useFly();
  const { hit, routing, from, to, picking, q, selected } = nav;
  const [ctx, setCtx] = useState<{ lat: number; lon: number } | null>(null);
  const point = (lat: number, lon: number, label?: string): PlaceHit => ({ type: "picked", label: label ?? `Point ${lat.toFixed(5)}, ${lon.toFixed(5)}`, lat, lon });

  // Fly to a new search result.
  useEffect(() => {
    if (hit) fly(hit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hit]);

  // Fit a fresh set of routes.
  useEffect(() => {
    const r = q.data?.routes[0];
    if (!r?.geometry.length) return;
    map.flyToBounds(r.geometry, { paddingTopLeft: [window.innerWidth >= 768 ? 420 : 30, 140], paddingBottomRight: [70, 40], maxZoom: 16, duration: 0.8 });
  }, [q.data, map]);

  useMapEvents({
    click(e) {
      if (!picking) return;
      const h = point(e.latlng.lat, e.latlng.lng);
      if (picking === "from") nav.setFrom(h);
      else nav.setTo(h);
      nav.setPicking(null);
    },
    // Right-click (long-press on touch): "Directions from here / to here".
    contextmenu(e) {
      setCtx({ lat: e.latlng.lat, lon: e.latlng.lng });
    },
  });
  useEffect(() => {
    const el = map.getContainer();
    el.style.cursor = picking ? "crosshair" : "";
    return () => {
      el.style.cursor = "";
    };
  }, [picking, map]);

  const routes = routing ? (q.data?.routes ?? []) : [];
  return (
    <>
      {hit && !routing && (
        <Marker position={[hit.lat, hit.lon]} icon={pin("featured", { pulse: true, size: 38 })}>
          <Popup>
            <div className="w-56 p-3">
              <p className="font-semibold text-ink">{hit.label}</p>
              {hit.sub && <p className="text-xs text-ink-mute">{hit.sub}</p>}
              <div className="mt-2 flex gap-1.5">
                <button
                  type="button"
                  className="btn btn-primary btn-sm flex-1"
                  onClick={() => {
                    nav.setTo(hit);
                    nav.setRouting(true);
                  }}
                >
                  <Navigation className="h-3.5 w-3.5" /> Directions
                </button>
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={() => {
                    nav.setFrom(hit);
                    nav.setRouting(true);
                  }}
                >
                  From here
                </button>
              </div>
            </div>
          </Popup>
        </Marker>
      )}
      {routes.map((r, i) =>
        i === selected ? null : (
          <Polyline key={`alt-${i}`} positions={r.geometry} pathOptions={{ color: "#64748b", weight: 6, opacity: 0.55 }} eventHandlers={{ click: () => nav.setSelected(i) }}>
            <Tooltip sticky>
              {r.label} · {r.duration_text} · {r.distance_text} — click to choose
            </Tooltip>
          </Polyline>
        ),
      )}
      {routes[selected] && (
        <>
          <Polyline positions={routes[selected]!.geometry} pathOptions={{ color: "#ffffff", weight: 10, opacity: 0.95 }} interactive={false} />
          <Polyline positions={routes[selected]!.geometry} pathOptions={{ color: "#1a73e8", weight: 6, opacity: 1 }} interactive={false} />
        </>
      )}
      {ctx && (
        <Popup position={[ctx.lat, ctx.lon]} eventHandlers={{ remove: () => setCtx(null) }}>
          <div className="w-52 p-2">
            <p className="px-1 pb-1 text-[11px] text-ink-mute">
              {ctx.lat.toFixed(5)}, {ctx.lon.toFixed(5)}
            </p>
            {(
              [
                ["Directions from here", (h: PlaceHit) => nav.setFrom(h)],
                ["Directions to here", (h: PlaceHit) => nav.setTo(h)],
              ] as [string, (h: PlaceHit) => void][]
            ).map(([label, set]) => (
              <button
                key={label}
                type="button"
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-sm font-semibold text-ink hover:bg-brand-50"
                onClick={() => {
                  set(point(ctx.lat, ctx.lon));
                  nav.setRouting(true);
                  setCtx(null);
                  map.closePopup();
                }}
              >
                <Navigation className="h-4 w-4 text-brand-600" /> {label}
              </button>
            ))}
          </div>
        </Popup>
      )}
      {/* A and B can be dragged to adjust the route. */}
      {routing && from && (
        <Marker
          position={[from.lat, from.lon]}
          icon={pin("city", { label: "A" })}
          draggable
          eventHandlers={{ dragend: (e) => nav.setFrom(point(e.target.getLatLng().lat, e.target.getLatLng().lng)) }}
        >
          <Tooltip direction="top" offset={[0, -30]}>
            Start · drag to move
          </Tooltip>
        </Marker>
      )}
      {routing && to && (
        <Marker
          position={[to.lat, to.lon]}
          icon={pin("featured", { label: "B" })}
          draggable
          eventHandlers={{ dragend: (e) => nav.setTo(point(e.target.getLatLng().lat, e.target.getLatLng().lng)) }}
        >
          <Tooltip direction="top" offset={[0, -30]}>
            Destination · drag to move
          </Tooltip>
        </Marker>
      )}
    </>
  );
}

const MODES: { value: Mode; label: string; icon: typeof Car }[] = [
  { value: "drive", label: "Drive", icon: Car },
  { value: "bike", label: "Bike", icon: Bike },
  { value: "walk", label: "Walk", icon: Footprints },
];

/** Overlay: the search bar, or the route finder card. */
export function NavigatorPanel({ nav, className }: { nav: NavigatorState; className?: string }) {
  const { routing, from, to, mode, q, selected } = nav;
  const [stepsOpen, setStepsOpen] = useState(false);

  const myLocation = (set: (h: PlaceHit) => void) => () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (p) => set({ type: "here", label: "Your location", lat: p.coords.latitude, lon: p.coords.longitude }),
      () => set({ type: "here", label: "Location unavailable — pick on the map", lat: 0, lon: 0 }),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };
  const fieldExtras = (which: "from" | "to") => [
    { label: "Your location", icon: Crosshair, onSelect: myLocation(which === "from" ? nav.setFrom : nav.setTo) },
    { label: "Pick on the map", icon: MapPin, onSelect: () => nav.setPicking(which) },
  ];

  if (!routing)
    return (
      <div className={cn("flex items-start gap-2", className)}>
        <PlaceSearch className="flex-1" inputClassName="shadow-soft" onPick={(h) => nav.setHit(h)} />
        <button
          type="button"
          onClick={() => {
            if (nav.hit) nav.setTo(nav.hit);
            nav.setRouting(true);
          }}
          className="flex h-10 shrink-0 items-center gap-1.5 rounded-xl bg-brand-700 px-3 text-sm font-semibold text-white shadow-soft hover:bg-brand-800"
          title="Find a route"
        >
          <Route className="h-4 w-4" /> <span className="hidden sm:inline">Directions</span>
        </button>
      </div>
    );

  const r = q.data?.routes ?? [];
  const valid = (h: PlaceHit | null) => !!h && !(h.lat === 0 && h.lon === 0);
  return (
    <div className={cn("overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-black/5 dark:bg-brand-950", className)}>
      <div className="flex items-center gap-2 border-b border-black/5 px-3 py-2 dark:border-white/10">
        <div className="flex flex-1 gap-1">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => nav.setMode(m.value)}
              className={cn("flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition", mode === m.value ? "bg-brand-700 text-white" : "text-ink-soft hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/10")}
            >
              <m.icon className="h-3.5 w-3.5" /> {m.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => {
            nav.setRouting(false);
            nav.setPicking(null);
          }}
          className="btn btn-ghost btn-icon h-8 w-8"
          aria-label="Close directions"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex items-center gap-2 p-3">
        <div className="flex flex-col items-center gap-1 text-ink-mute">
          <CircleDot className="h-4 w-4 text-brand-600" />
          <span className="h-5 border-s-2 border-dotted border-black/20 dark:border-white/20" />
          <MapPin className="h-4 w-4 text-red-500" />
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <PlaceSearch value={from?.label} onPick={nav.setFrom} placeholder="Choose starting point" icon={<span />} extra={fieldExtras("from")} inputClassName="!px-2.5" />
          <PlaceSearch value={to?.label} onPick={nav.setTo} placeholder="Choose destination" icon={<span />} extra={fieldExtras("to")} inputClassName="!px-2.5" />
        </div>
        <button
          type="button"
          onClick={() => {
            const f = from;
            nav.setFrom(to);
            nav.setTo(f);
          }}
          className="btn btn-ghost btn-icon h-9 w-9"
          title="Swap start and destination"
          aria-label="Swap start and destination"
        >
          <ArrowDownUp className="h-4 w-4" />
        </button>
      </div>
      {!nav.picking && (!valid(from) || !valid(to)) && (
        <p className="mx-3 mb-2 text-[11px] text-ink-mute">Tip: right-click the map for “Directions from / to here”, or drag the A / B pins.</p>
      )}
      {nav.picking && <p className="mx-3 mb-2 rounded-lg bg-gold-50 px-3 py-2 text-xs font-semibold text-gold-800 dark:bg-gold-500/10 dark:text-gold-200">Click the map to set the {nav.picking === "from" ? "starting point" : "destination"}.</p>}
      {valid(from) && valid(to) && (
        <div className="max-h-[42vh] overflow-y-auto border-t border-black/5 dark:border-white/10">
          {q.isLoading ? (
            <p className="flex items-center gap-2 p-4 text-sm text-ink-mute">
              <Loader2 className="h-4 w-4 animate-spin" /> Finding the best routes…
            </p>
          ) : q.error ? (
            <p className="p-4 text-sm text-red-600">{q.error.message}</p>
          ) : (
            <>
              {r.map((o, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => nav.setSelected(i)}
                  className={cn("flex w-full items-start gap-3 border-b border-black/5 px-4 py-3 text-start transition dark:border-white/10", i === selected ? "bg-blue-50/70 dark:bg-blue-500/10" : "hover:bg-black/[0.03]")}
                >
                  <span className={cn("mt-1 h-3 w-3 shrink-0 rounded-full", i === selected ? "bg-[#1a73e8]" : "bg-slate-400")} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className={cn("font-display text-lg font-bold", i === 0 ? "text-emerald-700 dark:text-emerald-400" : "")}>{o.duration_text}</span>
                      <span className="text-sm text-ink-mute">{o.distance_text}</span>
                    </span>
                    <span className="block truncate text-xs text-ink-mute">
                      {o.via.length ? `via ${o.via.join(", ")}` : o.label}
                      {i === 0 && r.length > 1 ? " · fastest" : ""}
                    </span>
                  </span>
                </button>
              ))}
              {r[selected] && (
                <div className="px-4 py-2">
                  <button type="button" onClick={() => setStepsOpen((v) => !v)} className="flex w-full items-center justify-between py-1 text-sm font-semibold">
                    Turn-by-turn ({r[selected]!.steps.length} steps) <ChevronDown className={cn("h-4 w-4 transition", stepsOpen && "rotate-180")} />
                  </button>
                  {stepsOpen && (
                    <ol className="mt-1 space-y-1.5 pb-2">
                      {r[selected]!.steps.map((s, k) => (
                        <li key={k} className="flex gap-2 text-xs">
                          <span className="w-5 shrink-0 text-end font-semibold text-ink-mute">{k + 1}.</span>
                          <span className="flex-1">{s.instruction}</span>
                          <span className="shrink-0 text-ink-mute">{s.distance_text}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              )}
              {q.data && (
                <p className="px-4 pb-3 text-[10px] text-ink-mute">
                  {mode === "drive" && "Driving times include typical city traffic. "}
                  {q.data.source === "portal" ? "Approximate route (online routing unavailable)." : q.data.attribution}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
