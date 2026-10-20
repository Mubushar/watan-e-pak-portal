import { useCallback, useEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import L from "leaflet";
import type { GeoJsonObject } from "geojson";
import { Circle, CircleMarker, GeoJSON, Marker, Polyline, Popup, Tooltip } from "react-leaflet";
import {
  ArrowRight,
  Building2,
  ChevronDown,
  Circle as CircleIcon,
  Compass,
  Construction,
  Crosshair,
  Eye,
  FileBarChart,
  FileText,
  Hash,
  Footprints,
  Globe2,
  Grid2x2,
  Home,
  LandPlot,
  Layers3,
  Map as MapIcon,
  MapPin,
  MessageSquareText,
  Mountain,
  MountainSnow,
  Navigation,
  PencilRuler,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  RotateCcw,
  Route,
  Search,
  Shapes,
  Sparkles,
  Square,
  Star,
  Target,
  Trash2,
  Type,
  Waves,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { City, Property, PropertyList, Scheme } from "@/types";
import { toast } from "sonner";
import { get } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useSavedState } from "@/hooks/useSavedState";
import { compact, num, pkrShort, titleCase } from "@/lib/format";
import { coverImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { PortalMap, PIN_STYLES, listingPin, pin, placePin, type BaseMapKey } from "@/components/map/PortalMap";
import { Badge, BarList, Button, EmptyState, ErrorState, Input, ScoreRing, Select, Segmented, Skeleton, Slider, Tabs, Toggle } from "@/components/ui";
import { ChipRow, FilterChip, MapClick, MiniStat, ReportButton, ReportModal, fitTo, type ReportRef } from "@/components/gis/kit";
import { ZoomArea } from "@/components/gis/ZoomArea";
import { MapControls, type LayerGroup } from "@/components/gis/MapControls";
import { CityLabels, ProvinceLayer, type MapLang } from "@/components/gis/PakistanLayers";
import { NavigatorLayer, NavigatorPanel, useNavigator } from "@/components/gis/Navigator";
import { POI_CATEGORIES, POI_MIN_ZOOM, PoiLayer } from "@/components/gis/PoiLayer";
import { AreaDraw, shapeAreaKm2, type DrawMode, type StudyShape } from "@/components/gis/AreaDraw";
import { StudyReport, useStudyReport } from "@/components/gis/StudyReport";
import { EditBar } from "@/components/gis/MapControls";
import { LocateMarks, LocatePanel, type LocRow } from "@/components/gis/LocateTool";
import { GeoEditLayer, GeoEditPanel, loadDraft, newDraft, pick, type Draft, type EditMode } from "@/components/gis/GeoEditor";
import { useAuth } from "@/store/auth";
import { ANNOTATION_MIN_ZOOM, MEGA_TYPES, MegaProjectLayer, useMegaProjects } from "@/components/gis/MegaProjects";
import { LiveRoadOverlay, ROAD_CLASSES, RoadLayer, type RoadStatus } from "@/components/gis/RoadLayer";
import { WATER_CLASSES, WaterLayer, type WaterStatus } from "@/components/gis/WaterLayer";
import { DISTRICT_LABEL_ZOOM, DistrictLayer } from "@/components/gis/DistrictLayer";
import { ELEVATION_GRADIENT, TerrainLayer } from "@/components/gis/TerrainLayer";
import { usePrefs } from "@/store/prefs";
import { onMapFocus, registerMapView, takePendingFocus, type MapFocus } from "@/lib/mapFocus";
import { LABEL_MIN_ZOOM, MasterPlanLayers, MasterPlanPanel, PLAN_GROUPS, PlanLabels, planGroup, planOfLayer, useMasterPlans, type PlanLabel } from "@/components/gis/MasterPlans";
import type { Aoi, AoiStats, GisLayer, GisLayerDetail, Poi, PoiCategory, RingResult, RouteResult } from "@/components/gis/types";

type TabKey = "properties" | "places" | "layers" | "areas" | "analyse";
type Vis = { props: boolean; pois: boolean; layers: boolean; aois: boolean; provinces: boolean; cities: boolean; districts: boolean; districtNames: boolean };
type AnalyseMode = "radius" | "route" | "rings";
type LatLon = [number, number];

/** A layer generated from a built master plan ("<plan> — boundary / master plan / plan labels: …"). */
const fromPlan = (l: { name: string; layer_type: string }, planNames: Set<string>) =>
  ["boundary", "master_plan", "annotation"].includes(l.layer_type) && planNames.has(planOfLayer(l.name));

const LAYER_COLORS: Record<string, string> = {
  master_plan: "#c99a22",
  boundary: "#146f45",
  plot_layout: "#17a398",
  zone: "#2c7fb8",
  road: "#e0a31a",
};
const RING_COLORS = ["#146f45", "#c99a22", "#2c7fb8", "#7c3aed", "#e4572e"];

/** Horizontal room taken by the desktop side panel. */
const sidePad = () => (window.innerWidth >= 768 ? { start: 390 } : { bottom: Math.round(window.innerHeight * 0.45) });

function useDebounced<T>(v: T, ms = 350): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

function geoBounds(g: GeoJsonObject): LatLon[] {
  try {
    const b = L.geoJSON(g).getBounds();
    if (!b.isValid()) return [];
    return [
      [b.getSouth(), b.getWest()],
      [b.getNorth(), b.getEast()],
    ];
  } catch {
    return [];
  }
}

// ======================================================================= page
export default function MapExplorer() {
  const [map, setMap] = useState<L.Map | null>(null);
  const [tab, setTab] = useState<TabKey>("properties");
  const [open, setOpen] = useState(true);
  // Layer choices are saved per user and come back on the next visit.
  const [vis, setVis] = useSavedState<Vis>("map.vis.v2", { props: true, pois: true, layers: true, aois: false, provinces: true, cities: true, districts: false, districtNames: true });
  const [report, setReport] = useState<ReportRef | null>(null);
  const markerRefs = useRef(new Map<string, L.Marker>());
  const zoomMoved = useRef(false);

  // -------------------------------------------------------------- data
  const propsQ = useApi<PropertyList>("/properties", { limit: 200 });
  const poiQ = useApi<{ pois: Poi[] }>("/poi", { limit: 500 });
  const catQ = useApi<{ categories: PoiCategory[] }>("/poi/categories");
  const layersQ = useApi<{ layers: GisLayer[] }>("/gis/layers");
  const aoiQ = useApi<{ areas: Aoi[] }>("/aoi");
  const citiesQ = useApi<{ cities: City[] }>("/cities");
  const schemesQ = useApi<{ schemes: Scheme[] }>("/schemes");

  const properties = useMemo(() => (propsQ.data?.results ?? []).filter((p) => p.latitude != null && p.longitude != null), [propsQ.data]);
  const layers = useMemo(() => layersQ.data?.layers ?? [], [layersQ.data]);
  // Layers generated from the master plans (outline, plan, text labels — "<plan> — …") are shown by
  // the DHA / Bahria / society master plan sections; their labels (~100k points) load only when on.
  const planNames = useMemo(
    () => new Set(layers.filter((l) => l.layer_type === "master_plan" && l.image_url?.startsWith("/masterplans/")).map((l) => planOfLayer(l.name))),
    [layers],
  );

  // Every overlay (except base maps) is a layer record an admin publishes in Administration › GIS
  // layers; the map shows only what is published (built-in overlays carry a `builtin` key).
  const published = useMemo(() => new Set(layers.filter((l) => l.published !== false && l.builtin).map((l) => l.builtin as string)), [layers]);
  const on = (key: string) => published.has(key);
  const gisLayers = useMemo(() => layers.filter((l) => !l.builtin && l.published !== false && !fromPlan(l, planNames)), [layers, planNames]);
  const labelLayers = useMemo(() => layers.filter((l) => l.published !== false && fromPlan(l, planNames) && l.layer_type === "annotation"), [layers, planNames]);
  const publishedPlans = useMemo(() => new Set(layers.filter((l) => l.published !== false && l.layer_type === "master_plan").map((l) => planOfLayer(l.name))), [layers]);
  const plansQ = useMasterPlans();
  const visiblePlans = useMemo(() => (plansQ.data?.plans ?? []).filter((pl) => publishedPlans.has(pl.name.toLowerCase())), [plansQ.data, publishedPlans]);
  /** The Layers panel offers only published overlays (a group disappears when nothing in it is). */
  const gateGroups = (groups: LayerGroup[]): LayerGroup[] => {
    const itemLayer: Record<string, string> = { props: "listings", pois: "featured_places", aois: "aois", provinces: "provinces", districts: "districts", cities: "city_names", "road-live": "roads_live" };
    const groupLayer: Record<string, string> = { poi: "osm_pois", terrain: "terrain", water: "water", roads: "roads", mega: "mega_projects" };
    return groups
      .map((g) => ({ ...g, items: g.items.filter((it) => {
        const key = itemLayer[it.key] ?? groupLayer[g.key];
        return !key || on(key);
      }) }))
      .filter((g) => g.items.length > 0);
  };

  // -------------------------------------------------------------- property filters
  const [useType, setUseType] = useState("all");
  const [category, setCategory] = useState("all");
  const [featuredOnly, setFeaturedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return properties.filter(
      (p) =>
        (useType === "all" || p.use_type === useType) &&
        (category === "all" || p.category === category) &&
        (!featuredOnly || p.featured) &&
        (!s || [p.title, p.city_name, p.sector, p.street_address].some((x) => x?.toLowerCase().includes(s))),
    );
  }, [properties, useType, category, featuredOnly, search]);

  // -------------------------------------------------------------- poi filters
  const [cats, setCats] = useState<Set<string> | null>(null);
  const poiCats = useMemo(() => (catQ.data?.categories ?? []).filter((c) => c.count > 0), [catQ.data]);
  const pois = useMemo(() => (poiQ.data?.pois ?? []).filter((p) => !cats || cats.has(p.category)), [poiQ.data, cats]);
  const toggleCat = (c: string) =>
    setCats((prev) => {
      const all = new Set(poiCats.map((x) => x.category));
      const next = new Set(prev ?? all);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next.size === all.size ? null : next;
    });

  // -------------------------------------------------------------- layers
  const [labelsOn, setLabelsOn] = useSavedState<Set<string>>("map.planLabels", () => new Set());
  // GIS layers follow their own default visibility until the user chooses.
  const [hiddenChoice, setHiddenChoice] = useSavedState<Set<string> | null>("map.hiddenLayers", null);
  const defaultHidden = useMemo(() => new Set(gisLayers.filter((l) => !l.visible).map((l) => l.id)), [gisLayers]);
  const hidden = hiddenChoice ?? defaultHidden;
  const setHidden = (u: SetStateAction<Set<string>>) => setHiddenChoice((prev) => (typeof u === "function" ? u(prev ?? defaultHidden) : u));
  // Only layers that are actually drawn are downloaded (each can be several MB).
  const activeLayers = useMemo(
    () => (vis.layers ? [...gisLayers.filter((l) => !hidden.has(l.id)), ...labelLayers.filter((l) => labelsOn.has(l.id))] : []),
    [vis.layers, gisLayers, labelLayers, hidden, labelsOn],
  );
  const qc = useQueryClient();
  const layerQuery = (id: string) => ({
    queryKey: [`/gis/layers/${id}`, {}],
    queryFn: ({ signal }: { signal: AbortSignal }) => get<GisLayerDetail>(`/gis/layers/${id}`, undefined, { signal }),
    staleTime: 30 * 60_000,
  });
  const detailQs = useQueries({ queries: activeLayers.map((l) => layerQuery(l.id)) });
  const details = new Map(activeLayers.map((l, i) => [l.id, detailQs[i]?.data] as const));
  const [zoom, setZoom] = useState(5);
  useEffect(() => {
    if (!map) return;
    const on = () => setZoom(map.getZoom());
    on();
    map.on("zoomend", on);
    return () => {
      map.off("zoomend", on);
    };
  }, [map]);
  // Master plans start switched on until the user chooses (null = no saved choice yet).
  const [planChoice, setPlanChoice] = useSavedState<Set<string> | null>("map.plans", null);
  const allPlans = useMemo(() => new Set((plansQ.data?.plans ?? []).map((p) => p.key)), [plansQ.data]);
  const planShown = planChoice ?? allPlans;
  const setPlanShown = (u: SetStateAction<Set<string>>) => setPlanChoice((prev) => (typeof u === "function" ? u(prev ?? allPlans) : u));
  const [planHit, setPlanHit] = useState<PlanLabel | null>(null);
  const [layerOpacity, setLayerOpacity] = useSavedState("map.layerOpacity", 70);

  // -------------------------------------------------------------- AOIs
  const [aoiId, setAoiId] = useState<string | null>(null);
  const aoiStatsQ = useApi<AoiStats>(aoiId ? `/aoi/${aoiId}/stats` : null);

  // -------------------------------------------------------------- analysis
  const [mode, setMode] = useState<AnalyseMode>("radius");
  const [pt, setPt] = useState<LatLon | null>(null);
  const [radius, setRadius] = useState(2);
  const dRadius = useDebounced(radius);
  const [routePts, setRoutePts] = useState<LatLon[]>([]);
  const [travel, setTravel] = useState<"walk" | "bike" | "drive">("drive");
  const [radii, setRadii] = useState("1,3,5");
  const dRadii = useDebounced(radii, 600);
  const analysing = tab === "analyse";
  const [zoomMode, setZoomMode] = useState<"in" | "out" | null>(null);
  const zoomDraw = zoomMode !== null;
  const setZoomDraw = (on: boolean) => setZoomMode(on ? "in" : null);
  const [baseMap, setBaseMap] = useSavedState<BaseMapKey>("map.base", "streets");
  const appLang = usePrefs((s) => s.lang);
  const [mapLang, setMapLang] = useSavedState<MapLang>("map.lang", appLang === "ur" ? "both" : "en");
  const nav = useNavigator();
  const [osmCats, setOsmCats] = useSavedState<Set<string>>("map.poi.v2", () => new Set(POI_CATEGORIES.map((c) => c.key)));
  const [poiStatus, setPoiStatus] = useState<{ count: number; total: number; zoomIn: boolean } | null>(null);
  const togglePoiCat = (k: string, on: boolean) =>
    setOsmCats((s) => {
      const n = new Set(s);
      if (on) n.add(k);
      else n.delete(k);
      return n;
    });
  const setLayerHidden = (id: string, on: boolean) => {
    setVis((v) => ({ ...v, layers: true }));
    setHidden((h) => {
      const n = new Set(h);
      if (on) n.delete(id);
      else n.add(id);
      return n;
    });
  };
  const setPlanOn = (key: string, on: boolean) => {
    setVis((v) => ({ ...v, layers: true }));
    setPlanShown((s) => {
      const n = new Set(s);
      if (on) n.add(key);
      else n.delete(key);
      return n;
    });
  };
  const setLabelOn = (id: string, on: boolean) => {
    setVis((v) => ({ ...v, layers: true }));
    setLabelsOn((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
  };
  const endZoomDraw = useCallback(() => setZoomMode(null), []);
  // Starting another map tool (directions, picking a point, a side-panel tab) switches the zoom tool off.
  useEffect(() => {
    setZoomDraw(false);
  }, [nav.routing, nav.picking, tab]);

  // ---- infrastructure mega projects
  const megaQ = useMegaProjects();
  const [megaTypes, setMegaTypes] = useSavedState<Set<string>>("map.mega", () => new Set(MEGA_TYPES.map((t) => t.key)));
  const [megaAnnot, setMegaAnnot] = useSavedState("map.megaAnnotations", true);

  // ---- road network (OpenStreetMap) and the live road overlay
  const [roadClasses, setRoadClasses] = useSavedState<Set<string>>("map.roads", () => new Set(["motorway", "trunk"]));
  const [roadBuilding, setRoadBuilding] = useSavedState("map.roadsConstruction", true);
  const [roadShields, setRoadShields] = useSavedState("map.roadShields", true);
  const [roadLive, setRoadLive] = useSavedState("map.roadsLive", false);
  const [roadStatus, setRoadStatus] = useState<RoadStatus | null>(null);

  // ---- water bodies (OpenStreetMap)
  const [waterClasses, setWaterClasses] = useSavedState<Set<string>>("map.water", () => new Set(["river", "reservoir", "lake", "riverbed"]));
  const [waterLabels, setWaterLabels] = useSavedState("map.waterLabels", true);
  const [waterStatus, setWaterStatus] = useState<WaterStatus | null>(null);

  // ---- terrain (DTM): elevation colours, hillshade, elevation under the mouse
  const [terrainColour, setTerrainColour] = useSavedState("map.terrainColour", false);
  const [terrainShade, setTerrainShade] = useSavedState("map.terrainShade", false);
  const [elevation, setElevation] = useState<number | null>(null);
  const toggleWater = (k: string, on: boolean) =>
    setWaterClasses((s) => {
      const n = new Set(s);
      if (on) n.add(k);
      else n.delete(k);
      return n;
    });
  const toggleRoad = (k: string, on: boolean) =>
    setRoadClasses((s) => {
      const n = new Set(s);
      if (on) n.add(k);
      else n.delete(k);
      return n;
    });
  const toggleMega = (k: string, on: boolean) =>
    setMegaTypes((s) => {
      const n = new Set(s);
      if (on) n.add(k);
      else n.delete(k);
      return n;
    });

  // ---- case-study area: draw a circle / rectangle / polygon -> report
  const [drawMode, setDrawMode] = useState<DrawMode | null>(null);
  const [studyShape, setStudyShape] = useState<StudyShape | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const study = useStudyReport();
  const runStudy = study.run;
  const startDraw = (m: DrawMode | null) => {
    setZoomDraw(false);
    nav.setPicking(null);
    setDrawMode(m);
  };
  const onStudyShape = useCallback(
    (s: StudyShape) => {
      setDrawMode(null);
      setStudyShape(s);
      if (shapeAreaKm2(s) > 500) {
        toast.error("That area is too large for a case study. Draw up to about 25 km across.");
        return;
      }
      setReportOpen(true);
      void runStudy(s, "Study area");
    },
    [runStudy],
  );
  const cancelDraw = useCallback(() => setDrawMode(null), []);
  const clearStudy = () => {
    setStudyShape(null);
    setReportOpen(false);
    study.setData(null);
  };

  const nearPoiQ = useApi<{ pois: Poi[]; count: number }>(
    analysing && mode === "radius" && pt ? "/poi/nearby" : null,
    pt ? { latitude: pt[0], longitude: pt[1], radius_km: dRadius, limit: 100 } : undefined,
  );
  const nearPropQ = useApi<{ results: (Property & { distance_km?: number })[]; count: number }>(
    analysing && mode === "radius" && pt ? "/nearby" : null,
    pt ? { lat: pt[0], lon: pt[1], radius_km: dRadius, limit: 50 } : undefined,
  );
  const routeQ = useApi<RouteResult>(
    analysing && mode === "route" && routePts.length === 2 ? "/gis/route" : null,
    routePts.length === 2
      ? { origin_latitude: routePts[0]![0], origin_longitude: routePts[0]![1], destination_latitude: routePts[1]![0], destination_longitude: routePts[1]![1], mode: travel, alternatives: 2 }
      : undefined,
  );
  const cleanRadii = dRadii
    .split(",")
    .map((x) => Number(x.trim()))
    .filter((x) => x > 0 && x <= 50)
    .slice(0, 5)
    .join(",");
  const ringQ = useApi<RingResult>(analysing && mode === "rings" && pt && cleanRadii ? "/gis/ring-analysis" : null, pt ? { lat: pt[0], lon: pt[1], radii_km: cleanRadii } : undefined);

  const onMapClick = useCallback(
    (lat: number, lon: number) => {
      if (mode === "route") setRoutePts((r) => (r.length >= 2 ? [[lat, lon]] : [...r, [lat, lon]]));
      else setPt([lat, lon]);
    },
    [mode],
  );

  // -------------------------------------------------------------- admin map editing
  const can = useAuth((s) => s.can);
  const editRights = { property: can("properties.manage"), project: can("projects.manage"), mega: can("gis.manage") };
  const [editMode, setEditModeRaw] = useState<EditMode>(null);
  const [editDraft, setEditDraft] = useState<Draft | null>(null);
  const [locateRow, setLocateRow] = useState<LocRow | null>(null);
  const editProjectsQ = useApi<{ projects: { id: string; name: string; latitude?: number | null; longitude?: number | null }[] }>(editMode ? "/bigprojects" : null);
  const setEditMode = (m: EditMode) => {
    setEditModeRaw(m);
    setEditDraft(null);
    setLocateRow(null);
    if (m) {
      setZoomMode(null);
      setDrawMode(null);
      nav.setPicking(null);
    }
  };
  const onEditClick = async (at: L.LatLng) => {
    if (editMode === "locate") {
      // Locate: a click places the record's pin (once a record is chosen)
      if (locateRow) setEditDraft({ kind: locateRow.kind, id: locateRow.id, fields: {}, geom: { type: "point", at: [at.lat, at.lng] } });
      return;
    }
    if (editDraft?.drawing && editDraft.geom.type !== "point") {
      setEditDraft({ ...editDraft, geom: { ...editDraft.geom, pts: [...editDraft.geom.pts, [at.lat, at.lng]] } });
      return;
    }
    if (editMode && editMode !== "select") {
      if (!editDraft) setEditDraft(newDraft(editMode, [at.lat, at.lng]));
      else if (editDraft.geom.type === "point" && !editDraft.id) setEditDraft({ ...editDraft, geom: { ...editDraft.geom, at: [at.lat, at.lng] } });
      return;
    }
    if (!map) return;
    const hit = pick(map, at, editRights, properties, editProjectsQ.data?.projects ?? [], megaQ.data?.projects ?? []);
    if (!hit) return;
    try {
      setEditDraft(await loadDraft(hit));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  useEffect(() => {
    if (!editMode) return;
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (editDraft) setEditDraft(null);
      else setEditModeRaw(null);
    };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [editMode, editDraft]);

  // -------------------------------------------------------------- view history ("Last view")
  const viewHistory = useRef<{ c: [number, number]; z: number }[]>([]);
  const goingBack = useRef(false);
  const [canGoBack, setCanGoBack] = useState(false);
  const sameView = (a: { c: [number, number]; z: number }, b: { c: [number, number]; z: number }) =>
    a.z === b.z && Math.abs(a.c[0] - b.c[0]) < 1e-6 && Math.abs(a.c[1] - b.c[1]) < 1e-6;
  useEffect(() => {
    if (!map) return;
    const record = () => {
      const c = map.getCenter();
      const v = { c: [c.lat, c.lng] as [number, number], z: map.getZoom() };
      const h = viewHistory.current;
      if (goingBack.current) {
        goingBack.current = false; // arriving at the view we went back to: don't record it again
        return;
      }
      if (h.length && sameView(h[h.length - 1]!, v)) return;
      h.push(v);
      if (h.length > 30) h.shift();
      setCanGoBack(h.length > 1);
    };
    record();
    map.on("moveend", record);
    return () => {
      map.off("moveend", record);
    };
  }, [map]);
  const lastView = () => {
    const h = viewHistory.current;
    if (!map || h.length < 2) return;
    h.pop();
    const prev = h[h.length - 1]!;
    const c = map.getCenter();
    if (!sameView(prev, { c: [c.lat, c.lng], z: map.getZoom() })) {
      goingBack.current = true;
      map.flyTo(prev.c, prev.z, { duration: 0.6 });
    }
    setCanGoBack(h.length > 1);
  };

  // -------------------------------------------------------------- map helpers
  const onReady = useCallback((m: L.Map) => {
    setMap(m);
    if (zoomMoved.current) return;
    zoomMoved.current = true;
    if (window.innerWidth >= 768) m.zoomControl?.setPosition(document.documentElement.dir === "rtl" ? "bottomleft" : "bottomright");
  }, []);

  const didFit = useRef(false);
  useEffect(() => {
    if (!map || didFit.current || !properties.length) return;
    const b = L.latLngBounds(properties.map((p) => [p.latitude!, p.longitude!] as LatLon));
    // The container may still be sizing on first paint; measure before fitting.
    const t = setTimeout(() => {
      didFit.current = true;
      map.invalidateSize();
      fitTo(map, [[b.getSouth(), b.getWest()], [b.getNorth(), b.getEast()]], 12, sidePad());
    }, 120);
    return () => clearTimeout(t);
  }, [map, properties]);

  const focusProperty = (p: Property) => {
    if (!map || p.latitude == null || p.longitude == null) return;
    setVis((v) => ({ ...v, props: true }));
    map.flyTo([p.latitude, p.longitude], 16, { duration: 0.9 });
    map.once("moveend", () => markerRefs.current.get(p.id)?.openPopup());
    if (window.innerWidth < 768) setOpen(false);
  };
  // The assistant moving this map (focus_map): fly there, mark the spot, switch on the plan covering it.
  const [aiPin, setAiPin] = useState<MapFocus | null>(null);
  const applyFocus = useRef<(f: MapFocus) => void>(() => undefined);
  applyFocus.current = (f) => {
    if (!map) return;
    didFit.current = true; // the first "fit all listings" must not undo it
    setAiPin(f);
    if (f.masterPlan) {
      const inside = (plansQ.data?.plans ?? []).filter(
        (pl) => f.latitude >= pl.bounds[0] && f.latitude <= pl.bounds[2] && f.longitude >= pl.bounds[1] && f.longitude <= pl.bounds[3],
      );
      if (inside.length) {
        setVis((v) => ({ ...v, layers: true }));
        setPlanShown((s) => new Set([...s, ...inside.map((pl) => pl.key)]));
      }
    }
    map.flyTo([f.latitude, f.longitude], f.zoom, { duration: 1.1 });
    // Where animation frames don't run (a background tab, a busy device) the fly-to never arrives: jump.
    setTimeout(() => {
      if (map.getZoom() !== f.zoom || map.getCenter().distanceTo([f.latitude, f.longitude]) > 30) {
        map.stop();
        map.setView([f.latitude, f.longitude], f.zoom, { animate: false });
      }
    }, 1600);
    if (window.innerWidth < 768) setOpen(false);
  };
  useEffect(() => {
    if (!map) return;
    const waiting = takePendingFocus();
    if (waiting) setTimeout(() => applyFocus.current(waiting), 250); // after the map has sized itself
    return onMapFocus((f) => applyFocus.current(f));
  }, [map]);

  // Share what is on screen with the assistant (read_map): the view and every layer switched on.
  const viewLayers = useRef({ plans: [] as { key: string; name: string }[], gis: [] as { id: string; name: string; type: string }[], overlays: [] as string[], base: "" });
  viewLayers.current = {
    plans: vis.layers ? visiblePlans.filter((pl) => planShown.has(pl.key)).map((pl) => ({ key: pl.key, name: pl.name })) : [],
    gis: vis.layers ? gisLayers.filter((l) => !hidden.has(l.id)).map((l) => ({ id: l.id, name: l.name, type: l.layer_type })) : [],
    overlays: [
      vis.props && on("listings") && "listings",
      vis.pois && on("featured_places") && "featured_places",
      osmCats.size > 0 && on("osm_pois") && "osm_pois",
      megaTypes.size > 0 && on("mega_projects") && "mega_projects",
      roadClasses.size > 0 && on("roads") && "roads",
      vis.districts && on("districts") && "districts",
      vis.aois && "areas_of_interest",
    ].filter(Boolean) as string[],
    base: baseMap,
  };
  useEffect(() => {
    if (!map) return;
    registerMapView(() => {
      const b = map.getBounds();
      return { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast(), zoom: map.getZoom(), ...viewLayers.current };
    });
    return () => registerMapView(null);
  }, [map]);

  const focusPoint = (lat: number, lon: number, z = 16) => {
    map?.flyTo([lat, lon], z, { duration: 0.9 });
    if (window.innerWidth < 768) setOpen(false);
  };

  const changeTab = (t: TabKey) => {
    setTab(t);
    if (t === "places") setVis((v) => ({ ...v, pois: true }));
    if (t === "areas") setVis((v) => ({ ...v, aois: true }));
    if (t === "layers") setVis((v) => ({ ...v, layers: true }));
    if (t === "properties") setVis((v) => ({ ...v, props: true }));
  };

  const selectAoi = (a: Aoi) => {
    setAoiId(a.id);
    setTab("areas");
    setVis((v) => ({ ...v, aois: true }));
    if (a.geometry) fitTo(map, geoBounds(a.geometry), 15, sidePad());
    setOpen(true);
  };

  const useTypes = useMemo(() => [...new Set(properties.map((p) => p.use_type))].sort(), [properties]);
  const categories = useMemo(() => [...new Set(properties.map((p) => p.category))].sort(), [properties]);

  // ================================================================== render
  return (
    <div className={cn("relative h-[calc(100dvh-110px)] min-h-[540px] w-full overflow-hidden bg-brand-950", analysing && "[&_.leaflet-container]:cursor-crosshair")}>
      <PortalMap height="100%" className="rounded-none" scrollWheelZoom onReady={onReady} zoom={5} switcher={false} baseKey={baseMap}>
        {/* ----------------------------------------------------- Pakistan reference layers */}
        {vis.provinces && on("provinces") && <ProvinceLayer map={map} lang={mapLang} zoom={zoom} />}
        <TerrainLayer colour={terrainColour && on("terrain")} shade={terrainShade && on("terrain")} opacity={terrainColour ? 0.6 : 0.8} onElevation={(m) => setElevation(m)} />
        {waterClasses.size > 0 && on("water") && <WaterLayer classes={waterClasses} labels={waterLabels} lang={mapLang} onStatus={setWaterStatus} />}
        {roadLive && on("roads_live") && <LiveRoadOverlay />}
        {roadClasses.size > 0 && on("roads") && <RoadLayer classes={roadClasses} construction={roadBuilding} shields={roadShields} lang={mapLang} onStatus={setRoadStatus} />}
        {megaTypes.size > 0 && on("mega_projects") && <MegaProjectLayer projects={megaQ.data?.projects ?? []} types={megaTypes} lang={mapLang} zoom={zoom} labelZoom={11} annotate={megaAnnot} />}
        {vis.districts && on("districts") && <DistrictLayer lang={mapLang} zoom={zoom} labels={vis.districtNames} />}
        {vis.cities && on("city_names") && <CityLabels zoom={zoom} lang={mapLang} />}
        {osmCats.size > 0 && on("osm_pois") && <PoiLayer categories={osmCats} lang={mapLang} onStatus={setPoiStatus} />}
        <NavigatorLayer nav={nav} />

        {/* ----------------------------------------------------- DHA master plans */}
        {vis.layers && (
          <MasterPlanLayers
            plans={visiblePlans}
            shown={planShown}
            opacity={layerOpacity / 100}
            hit={planHit}
            onSelect={(p) =>
              fitTo(
                map,
                [
                  [p.bounds[0], p.bounds[1]],
                  [p.bounds[2], p.bounds[3]],
                ],
                15,
                sidePad(),
              )
            }
          />
        )}

        {/* ----------------------------------------------------- the spot the assistant flew to */}
        {aiPin && (
          <CircleMarker
            center={[aiPin.latitude, aiPin.longitude]}
            radius={11}
            pathOptions={{ color: "#c99a22", weight: 3, fillColor: "#f2dd8f", fillOpacity: 0.65 }}
            eventHandlers={{ click: () => setAiPin(null) }}
          >
            <Tooltip permanent direction="top" offset={[0, -10]}>
              <span className="font-semibold">{aiPin.name}</span>
            </Tooltip>
          </CircleMarker>
        )}

        {/* ----------------------------------------------------- master-plan text labels (zoomed in only) */}
        {vis.layers &&
          zoom >= LABEL_MIN_ZOOM &&
          labelLayers.map((l) => {
            const d = labelsOn.has(l.id) ? details.get(l.id) : undefined;
            return d?.geojson ? <PlanLabels key={l.id} data={d.geojson} color="#172554" /> : null;
          })}

        {/* ----------------------------------------------------- GIS layers */}
        {vis.layers &&
          gisLayers.map((l) => {
            const d = details.get(l.id);
            if (!d?.geojson || hidden.has(l.id)) return null;
            const color = LAYER_COLORS[l.layer_type] ?? d.style?.color ?? "#146f45";
            const isLine = l.layer_type === "road";
            const o = layerOpacity / 100;
            return (
              <GeoJSON
                key={l.id}
                data={d.geojson}
                style={() => ({
                  color,
                  weight: isLine ? 5 : (d.style?.weight ?? 2) + 0.5,
                  opacity: Math.min(1, o + 0.25),
                  fillColor: color,
                  fillOpacity: isLine ? 0 : Math.max(0.05, (d.style?.fillOpacity ?? 0.15) * o * 1.6),
                  dashArray: l.layer_type === "boundary" ? "8 6" : isLine ? "1 0" : undefined,
                  lineCap: "round",
                })}
              >
                <Popup>
                  <span className="font-semibold">{l.name}</span> · {titleCase(l.layer_type)}
                </Popup>
              </GeoJSON>
            );
          })}

        {/* ----------------------------------------------------- AOIs */}
        {vis.aois &&
          on("aois") &&
          (aoiQ.data?.areas ?? []).map((a) =>
            a.geometry ? (
              <GeoJSON
                key={`${a.id}-${a.id === aoiId}`}
                data={a.geometry}
                style={() => ({
                  color: a.id === aoiId ? "#c99a22" : "#7c3aed",
                  weight: a.id === aoiId ? 3.5 : 2,
                  fillColor: a.id === aoiId ? "#f2dd8f" : "#7c3aed",
                  fillOpacity: a.id === aoiId ? 0.28 : 0.1,
                  dashArray: a.id === aoiId ? undefined : "4 4",
                })}
                eventHandlers={{ click: () => selectAoi(a) }}
              >
              </GeoJSON>
            ) : null,
          )}

        {/* ----------------------------------------------------- properties */}
        {vis.props &&
          on("listings") &&
          filtered.map((p) => (
            <Marker
              key={p.id}
              position={[p.latitude!, p.longitude!]}
              icon={listingPin(p)}
              ref={(m) => {
                if (m) markerRefs.current.set(p.id, m);
              }}
            >
              <Popup>
                <PropertyPopup p={p} />
              </Popup>
            </Marker>
          ))}

        {/* ----------------------------------------------------- POIs */}
        {vis.pois &&
          on("featured_places") &&
          pois.map((p) => (
            <Marker key={p.id} position={[p.latitude, p.longitude]} icon={placePin(p.category)}>
              <Popup>
                <PoiPopup p={p} />
              </Popup>
            </Marker>
          ))}

        {/* ----------------------------------------------------- analysis overlays */}
        {analysing && mode === "radius" && pt && (
          <>
            <Circle center={pt} radius={radius * 1000} pathOptions={{ color: "#c99a22", weight: 2, fillColor: "#c99a22", fillOpacity: 0.1, dashArray: "6 6" }} />
            <Marker position={pt} icon={pin("project", { pulse: true })} />
            {(nearPoiQ.data?.pois ?? []).map((p) => (
              <CircleMarker key={p.id} center={[p.latitude, p.longitude]} radius={6} pathOptions={{ color: "#fff", weight: 2, fillColor: PIN_STYLES[p.category]?.color ?? "#64748b", fillOpacity: 1 }}>
                <Tooltip>
                  {p.name} · {titleCase(p.category)} · {p.distance_km} km
                </Tooltip>
              </CircleMarker>
            ))}
            {(nearPropQ.data?.results ?? []).map((p) =>
              p.latitude != null && p.longitude != null ? (
                <Marker key={`n-${p.id}`} position={[p.latitude, p.longitude]} icon={listingPin(p)}>
                  <Popup>
                    <PropertyPopup p={p} />
                  </Popup>
                </Marker>
              ) : null,
            )}
          </>
        )}
        {analysing && mode === "rings" && pt && (
          <>
            {[...(ringQ.data?.rings ?? [])].reverse().map((r) => {
              const idx = (ringQ.data?.rings ?? []).indexOf(r);
              const c = RING_COLORS[idx % RING_COLORS.length]!;
              return (
                <GeoJSON key={`ring-${r.outer_km}-${pt.join(",")}`} data={r.geometry} style={() => ({ color: c, weight: 2, fillColor: c, fillOpacity: 0.08 })}>
                  <Popup>
                    {r.inner_km}–{r.outer_km} km · {r.summary.properties} listings
                  </Popup>
                </GeoJSON>
              );
            })}
            <Marker position={pt} icon={pin("project", { pulse: true })} />
          </>
        )}
        {analysing && mode === "route" && (
          <>
            {(routeQ.data?.alternatives ?? []).map((a, i) => (
              <Polyline key={`alt-${i}`} positions={a.geometry} pathOptions={{ color: "#64748b", weight: 5, opacity: 0.55, dashArray: "8 8" }}>
                <Tooltip sticky>
                  {a.label} · {a.distance_km} km · {a.duration_text}
                </Tooltip>
              </Polyline>
            ))}
            {routeQ.data?.best && (
              <>
                <Polyline positions={routeQ.data.best.geometry} pathOptions={{ color: "#ffffff", weight: 10, opacity: 0.9 }} />
                <Polyline positions={routeQ.data.best.geometry} pathOptions={{ color: "#146f45", weight: 6, opacity: 1 }}>
                  <Tooltip sticky>
                    Best · {routeQ.data.best.distance_km} km · {routeQ.data.best.duration_text}
                  </Tooltip>
                </Polyline>
              </>
            )}
            {routePts.map((p, i) => (
              <Marker key={`rp-${i}`} position={p} icon={pin(i === 0 ? "city" : "featured", { label: i === 0 ? "A" : "B" })} />
            ))}
          </>
        )}

        <MapClick enabled={analysing && !zoomDraw && !drawMode && !nav.picking} onClick={onMapClick} />
        <ZoomArea active={zoomDraw} mode={zoomMode ?? "in"} onDone={endZoomDraw} padding={sidePad()} sticky />
        <AreaDraw mode={drawMode} shape={studyShape} onShape={onStudyShape} onCancel={cancelDraw} />
        <GeoEditLayer mode={editMode} draft={editDraft} setDraft={setEditDraft} onPick={onEditClick} />
        {editMode === "locate" && <LocateMarks row={locateRow} />}
      </PortalMap>
      <EditBar
        edit={{ rights: editRights, mode: editMode, onMode: setEditMode }}
        className={cn("start-3", open ? "bottom-[calc(56%+0.75rem)] md:bottom-3 md:start-[408px]" : "bottom-[4.5rem] md:bottom-3 md:start-3")}
      />
      {editMode === "locate" && (
        <LocatePanel rights={editRights} draft={editDraft} setDraft={setEditDraft} row={locateRow} setRow={setLocateRow} map={map} onClose={() => setEditMode(null)} />
      )}
      <GeoEditPanel
        mode={editMode}
        draft={editDraft}
        setDraft={setEditDraft}
        onDone={() => (editDraft ? setEditDraft(null) : setEditModeRaw(null))}
        megaTypes={(megaQ.data as { types?: Record<string, string> } | undefined)?.types ?? {}}
        megaStatuses={(megaQ.data as { statuses?: Record<string, string> } | undefined)?.statuses ?? {}}
      />

      {/* ------------------------------------------------------- map controls (grouped) */}
      <MapControls
        base={baseMap}
        onBase={setBaseMap}
        zoomMode={zoomMode}
        onZoomMode={(m) => {
          if (m) {
            setDrawMode(null);
            nav.setPicking(null);
          }
          setZoomMode(m);
        }}
        panActive={!zoomMode && !drawMode && !nav.picking && !editMode}
        onPan={() => {
          setZoomMode(null);
          setDrawMode(null);
          nav.setPicking(null);
          setEditMode(null);
        }}
        drawMode={drawMode}
        onDraw={startDraw}
        onFit={properties.length ? () => fitTo(map, filtered.map((p) => [p.latitude!, p.longitude!]), 13, sidePad()) : undefined}
        onLastView={lastView}
        lastViewReady={canGoBack}
        lang={mapLang}
        onLang={setMapLang}
        groups={gateGroups([
          {
            key: "portal",
            title: "Portal data",
            icon: Home,
            items: [
              { key: "props", label: "Listings", hint: `${filtered.length} properties for sale & rent`, icon: Home, on: vis.props, onChange: (v) => setVis((x) => ({ ...x, props: v })) },
              { key: "pois", label: "Featured places", hint: "Curated places with ratings", icon: Star, on: vis.pois, onChange: (v) => setVis((x) => ({ ...x, pois: v })) },
              { key: "aois", label: "Areas of interest", hint: "Saved study areas", icon: Square, on: vis.aois, onChange: (v) => setVis((x) => ({ ...x, aois: v })) },
            ],
          },
          {
            key: "poi",
            title: "Points of interest",
            icon: MapPin,
            items: POI_CATEGORIES.map((c) => ({ key: `poi-${c.key}`, label: c.label, color: c.color, on: osmCats.has(c.key), onChange: (v: boolean) => togglePoiCat(c.key, v) })),
            note:
              osmCats.size === 0
                ? "Map data for Islamabad / Rawalpindi, Lahore and Karachi."
                : zoom < POI_MIN_ZOOM || poiStatus?.zoomIn
                  ? `Zoom in (level ${POI_MIN_ZOOM}+) to see places.`
                  : poiStatus
                    ? `${poiStatus.count.toLocaleString()} places in view${poiStatus.total > poiStatus.count ? ` (of ${poiStatus.total.toLocaleString()} — zoom in for all)` : ""}.`
                    : undefined,
          },
          {
            key: "reference",
            title: "Reference",
            icon: Globe2,
            items: [
              { key: "provinces", label: "Province boundaries", hint: "Provinces & territories, with listing counts", icon: MapIcon, on: vis.provinces, onChange: (v) => setVis((x) => ({ ...x, provinces: v })) },
              {
                key: "districts",
                label: "District boundaries",
                hint: "All districts (OpenStreetMap); hover for listings",
                icon: Grid2x2,
                on: vis.districts,
                onChange: (v) => setVis((x) => ({ ...x, districts: v })),
                children: [{ key: "district-names", label: `District names (from zoom ${DISTRICT_LABEL_ZOOM})`, on: vis.districtNames, onChange: (v: boolean) => setVis((x) => ({ ...x, districtNames: v })) }],
              },
              { key: "cities", label: "City names", hint: "Main cities; gold dots have a city page", icon: Building2, on: vis.cities, onChange: (v) => setVis((x) => ({ ...x, cities: v })) },
            ],
          },
          {
            key: "terrain",
            title: "Terrain (DTM)",
            icon: Mountain,
            items: [
              { key: "terrain-colour", label: "Elevation colours", hint: "Height above sea level, 30 m model", icon: Mountain, on: terrainColour, onChange: setTerrainColour },
              { key: "terrain-shade", label: "Hillshade", hint: "Relief shading of hills and slopes", icon: MountainSnow, on: terrainShade, onChange: setTerrainShade },
            ],
            note: (
              <span className="block space-y-1">
                <span className="block h-2 rounded-full" style={{ background: ELEVATION_GRADIENT }} />
                <span className="flex justify-between text-[10px]">
                  <span>0 m</span>
                  <span>1,500</span>
                  <span>3,500</span>
                  <span>7,000+ m</span>
                </span>
                <span className="block">AWS Terrain Tiles (SRTM 30 m). Move the mouse over the map to read the elevation.</span>
              </span>
            ),
          },
          {
            key: "water",
            title: "Water bodies",
            icon: Waves,
            items: [
              ...WATER_CLASSES.map((c) => ({
                key: `water-${c.key}`,
                label: c.label,
                hint: c.hint,
                color: c.color,
                on: waterClasses.has(c.key),
                onChange: (v: boolean) => toggleWater(c.key, v),
              })),
              { key: "water-labels", label: "Lake & dam names", hint: "From zoom 9", icon: Type, on: waterLabels, onChange: setWaterLabels },
            ],
            note: waterStatus?.missing
              ? waterStatus.hint
              : `OpenStreetMap${waterStatus?.date ? `, extract of ${waterStatus.date}` : ""}${waterStatus && waterClasses.size ? ` · ${waterStatus.count.toLocaleString()} features in view` : ""}. Click water for details.`,
          },
          {
            key: "roads",
            title: "Road network",
            icon: Route,
            items: [
              ...ROAD_CLASSES.map((c) => ({
                key: `road-${c.key}`,
                label: c.label,
                hint: c.minZoom ? `From zoom ${c.minZoom}` : "All zoom levels",
                color: c.color,
                on: roadClasses.has(c.key),
                onChange: (v: boolean) => toggleRoad(c.key, v),
              })),
              { key: "road-construction", label: "Roads under construction", hint: "Dashed, in the road's colour class", icon: Construction, on: roadBuilding, onChange: setRoadBuilding },
              { key: "road-shields", label: "Route numbers", hint: "M-2, N-5 … shields from zoom 7", icon: Hash, on: roadShields, onChange: setRoadShields },
              { key: "road-live", label: "Live road overlay", hint: "Esri World Transportation; best on satellite", icon: Layers3, on: roadLive, onChange: setRoadLive },
            ],
            note: roadStatus?.missing
              ? roadStatus.hint
              : `OpenStreetMap${roadStatus?.date ? `, extract of ${roadStatus.date}` : ""}${roadStatus && roadClasses.size ? ` · ${roadStatus.count.toLocaleString()} road sections in view` : ""}. Click a road for details.`,
          },
          {
            key: "mega",
            title: "Infrastructure projects",
            icon: Construction,
            items: [
              {
                key: "mega-annotations",
                label: "Annotations",
                hint: `Name, status, completion and price effect · from zoom ${ANNOTATION_MIN_ZOOM}`,
                icon: MessageSquareText,
                on: megaAnnot,
                onChange: setMegaAnnot,
              },
              ...MEGA_TYPES.filter((t) => (megaQ.data?.projects ?? []).some((p) => p.type === t.key)).map((t) => ({
                key: `mega-${t.key}`,
                label: t.label,
                hint: `${(megaQ.data?.projects ?? []).filter((p) => p.type === t.key).length} projects`,
                color: t.color,
                on: megaTypes.has(t.key),
                onChange: (v: boolean) => toggleMega(t.key, v),
              })),
            ],
            note: (
              <>
                Ring roads, motorways, new sectors and economic zones that move land prices.{" "}
                <Link to="/infrastructure" className="link">
                  Details
                </Link>
              </>
            ),
          },
          ...PLAN_GROUPS.map((g) => ({
            key: `plans-${g.key}`,
            title: g.title,
            icon: LandPlot,
            items: visiblePlans
              .filter((pl) => planGroup(pl) === g.key)
              .map((pl) => ({
                key: `plan-${pl.key}`,
                label: pl.name,
                hint: pl.city,
                icon: MapIcon,
                on: vis.layers && planShown.has(pl.key),
                onChange: (v: boolean) => setPlanOn(pl.key, v),
                children: labelLayers
                  .filter((l) => l.name.startsWith(`${pl.name} — plan labels: `))
                  .map((l) => ({ key: l.id, label: `Labels: ${l.name.split(" — plan labels: ")[1]}`, on: labelsOn.has(l.id), onChange: (v: boolean) => setLabelOn(l.id, v) })),
              })),
            note:
              g.key === "dha"
                ? `Plan text appears from zoom ${LABEL_MIN_ZOOM}; plot numbers from zoom 17. Use the Layers tab to search a plan.`
                : "Georeferenced from the developers' master plans (about 10–20 m accuracy) — plans change, so what is built may differ.",
          })).filter((g) => g.items.length > 0),
          {
            key: "gis",
            title: "GIS layers",
            icon: Shapes,
            items: gisLayers.map((l) => ({
              key: l.id,
              label: l.name,
              hint: titleCase(l.layer_type),
              color: LAYER_COLORS[l.layer_type] ?? "#146f45",
              on: vis.layers && !hidden.has(l.id),
              onChange: (v: boolean) => setLayerHidden(l.id, v),
            })),
          },
        ])}
      />

      {/* ------------------------------------------------------- search bar / route finder */}
      <NavigatorPanel
        nav={nav}
        className={cn(
          "absolute start-3 end-[4.25rem] top-3 z-[450] md:end-auto md:w-[min(420px,calc(100%-30rem))]",
          open ? "md:start-[404px]" : "md:start-3",
        )}
      />

      {(terrainColour || terrainShade) && elevation != null && (
        <div className="pointer-events-none absolute bottom-[6.75rem] end-3 z-[420] flex items-center gap-1.5 rounded-full bg-white/95 px-3 py-1 text-xs font-bold shadow-soft ring-1 ring-black/5 dark:bg-brand-950/95">
          <Mountain className="h-3.5 w-3.5 text-brand-700 dark:text-brand-300" />
          {elevation.toLocaleString()} m
        </div>
      )}

      {/* ------------------------------------------------------- tool hints */}
      <div className="pointer-events-none absolute bottom-6 start-1/2 z-[380] -translate-x-1/2 rtl:translate-x-1/2 md:start-[calc(50%+190px)]">
      <AnimatePresence>
        {zoomDraw && (
          <motion.div key="zoom" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
            <div className="glass-dark flex items-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-xs font-semibold shadow-soft">
              {zoomMode === "out" ? <ZoomOut className="h-4 w-4 text-sky-300" /> : <ZoomIn className="h-4 w-4 text-gold-300" />}
              {zoomMode === "out" ? "Zoom-out tool on: drag a box — the current view shrinks into it" : "Zoom-in tool on: drag boxes to zoom in"} · Pan (or Esc) turns it off
            </div>
          </motion.div>
        )}
        {drawMode && (
          <motion.div key="draw" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
            <div className="glass-dark flex items-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-xs font-semibold shadow-soft">
              <PencilRuler className="h-4 w-4 text-gold-300" />
              {drawMode === "circle"
                ? "Click the centre, then click again to set the radius"
                : drawMode === "rectangle"
                  ? "Click the four corners of the area"
                  : "Click each corner · double-click or Enter to finish · Backspace undoes"}{" "}
              · Esc cancels
            </div>
          </motion.div>
        )}
        {studyShape && !drawMode && !zoomDraw && (
          <motion.div key="study" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="pointer-events-auto">
            <div className="flex items-center gap-1 whitespace-nowrap rounded-2xl bg-white p-1.5 shadow-2xl ring-1 ring-black/5 dark:bg-brand-950">
              <span className="px-2 text-xs font-semibold">
                <span className="me-1.5 inline-block h-2.5 w-2.5 rounded-full bg-violet-600" />
                Study area · {shapeAreaKm2(studyShape).toFixed(2)} km²
              </span>
              <Button
                size="sm"
                icon={<FileText className="h-4 w-4" />}
                loading={study.loading}
                onClick={() => {
                  setReportOpen(true);
                  if (!study.data) void study.run(studyShape, "Study area");
                }}
              >
                Report
              </Button>
              <button type="button" onClick={() => startDraw(studyShape.kind)} className="btn btn-ghost btn-sm" title="Draw again">
                <PencilRuler className="h-4 w-4" /> Redraw
              </button>
              <button type="button" onClick={clearStudy} className="btn btn-ghost btn-icon h-8 w-8" title="Clear the study area" aria-label="Clear the study area">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </motion.div>
        )}
        {analysing && !zoomDraw && !drawMode && !studyShape && (
          <motion.div key="analyse" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
            <div className="glass-dark flex items-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-xs font-semibold shadow-soft">
              <Crosshair className="h-4 w-4 text-gold-300" />
              {mode === "route" ? (routePts.length === 0 ? "Click the map to set start A" : routePts.length === 1 ? "Now click destination B" : "Click again to start a new route") : "Click the map to drop an analysis point"}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      </div>

      {reportOpen && (
        <StudyReport
          data={study.data}
          loading={study.loading}
          shape={studyShape}
          onClose={() => setReportOpen(false)}
          onSave={async (name) => {
            if (!studyShape) return;
            const r = await study.run(studyShape, name, true);
            if (r) {
              toast.success(`Saved "${name}" to your areas of interest`);
              void qc.invalidateQueries({ queryKey: ["/aoi"] });
            }
          }}
        />
      )}

      {/* ------------------------------------------------------- side panel / bottom sheet */}
      <motion.aside
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", bounce: 0.15, duration: 0.5 }}
        className={cn(
          "glass absolute z-[500] flex flex-col overflow-hidden shadow-2xl transition-[height,width] duration-300",
          "inset-x-0 bottom-0 rounded-t-3xl",
          open ? "h-[56%]" : "h-[60px]",
          "md:inset-x-auto md:bottom-3 md:start-3 md:top-3 md:rounded-2xl",
          open ? "md:h-auto md:w-[384px]" : "md:bottom-auto md:h-auto md:w-auto",
        )}
      >
        {/* header */}
        <div className="flex shrink-0 items-center gap-3 px-4 py-3">
          <button className="flex min-w-0 flex-1 items-center gap-3 text-start md:pointer-events-none" onClick={() => setOpen((o) => !o)}>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-soft">
              <Compass className="h-5 w-5" />
            </span>
            <span className="min-w-0">
              <span className="block font-display text-base font-bold leading-tight text-brand-900 dark:text-white">GIS Explorer</span>
              <span className="block truncate text-[11px] text-ink-mute dark:text-slate-400">
                {properties.length} listings · {poiQ.data?.pois.length ?? 0} places · {gisLayers.length + (plansQ.data?.count ?? 0)} layers
              </span>
            </span>
          </button>
          <button onClick={() => setOpen((o) => !o)} className="btn btn-ghost btn-icon h-9 w-9" aria-label={open ? "Collapse panel" : "Expand panel"}>
            <ChevronDown className={cn("h-5 w-5 transition md:hidden", !open && "rotate-180")} />
            {open ? <PanelLeftClose className="hidden h-5 w-5 rtl:rotate-180 md:block" /> : <PanelLeftOpen className="hidden h-5 w-5 rtl:rotate-180 md:block" />}
          </button>
        </div>
        {open && (
          <>
            <Tabs<TabKey>
              className="shrink-0 px-2 [&>button]:px-2.5 [&>button]:text-xs"
              value={tab}
              onChange={changeTab}
              tabs={[
                { value: "properties", label: "Listings", icon: <Home className="h-3.5 w-3.5" />, count: filtered.length },
                { value: "places", label: "Places", icon: <MapPin className="h-3.5 w-3.5" /> },
                { value: "layers", label: "Layers", icon: <Layers3 className="h-3.5 w-3.5" /> },
                { value: "areas", label: "Areas", icon: <Square className="h-3.5 w-3.5" /> },
                { value: "analyse", label: "Analyse", icon: <Radar className="h-3.5 w-3.5" /> },
              ]}
            />
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              <AnimatePresence mode="wait">
                <motion.div key={tab} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} transition={{ duration: 0.18 }}>
                  {tab === "properties" && (
                    <div className="space-y-3">
                      <Input icon={<Search className="h-4 w-4" />} placeholder="Search title, city, sector…" value={search} onChange={(e) => setSearch(e.target.value)} />
                      <ChipRow>
                        <FilterChip active={useType === "all"} onClick={() => setUseType("all")}>
                          All uses
                        </FilterChip>
                        {useTypes.map((u) => (
                          <FilterChip key={u} active={useType === u} onClick={() => setUseType(u)} color={u === "commercial" ? PIN_STYLES.commercial!.color : u === "residential" ? PIN_STYLES.property!.color : "#8a5a35"}>
                            {titleCase(u)}
                          </FilterChip>
                        ))}
                        <FilterChip active={featuredOnly} onClick={() => setFeaturedOnly((f) => !f)} color={PIN_STYLES.featured!.color}>
                          Featured
                        </FilterChip>
                      </ChipRow>
                      <ChipRow>
                        <FilterChip active={category === "all"} onClick={() => setCategory("all")}>
                          All types
                        </FilterChip>
                        {categories.map((c) => (
                          <FilterChip key={c} active={category === c} onClick={() => setCategory(c)} count={properties.filter((p) => p.category === c).length}>
                            {titleCase(c)}
                          </FilterChip>
                        ))}
                      </ChipRow>
                      {propsQ.isLoading ? (
                        <ListSkeleton />
                      ) : propsQ.error ? (
                        <ErrorState error={propsQ.error} onRetry={() => propsQ.refetch()} />
                      ) : !filtered.length ? (
                        <EmptyState title="No listings match" hint="Try clearing a filter." />
                      ) : (
                        <div className="space-y-1.5">
                          {filtered.map((p, i) => (
                            <motion.button
                              key={p.id}
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: Math.min(i, 12) * 0.025 }}
                              onClick={() => focusProperty(p)}
                              className="group flex w-full items-center gap-3 rounded-xl p-2 text-start transition hover:bg-white/80 dark:hover:bg-white/5"
                            >
                              <div className="relative h-14 w-20 shrink-0 overflow-hidden rounded-lg">
                                <img src={coverImage(p)} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-110" />
                                {p.featured && (
                                  <span className="absolute start-1 top-1 rounded-full bg-gold-gradient p-0.5">
                                    <Star className="h-2.5 w-2.5 fill-brand-950 text-brand-950" />
                                  </span>
                                )}
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-semibold text-ink group-hover:text-brand-700 dark:text-white">{p.title}</p>
                                <p className="truncate text-[11px] text-ink-mute">
                                  {[p.sector, p.city_name].filter(Boolean).join(", ")} · {titleCase(p.category)}
                                </p>
                                <p className="text-sm font-bold text-brand-700 dark:text-brand-300">{pkrShort(p.price)}</p>
                              </div>
                              <Navigation className="h-4 w-4 shrink-0 text-ink-mute opacity-0 transition group-hover:opacity-100" />
                            </motion.button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {tab === "places" && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold uppercase tracking-wider text-ink-mute">Categories</p>
                        <button className="text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300" onClick={() => setCats(cats ? null : new Set())}>
                          {cats ? "Select all" : "Clear all"}
                        </button>
                      </div>
                      {catQ.isLoading ? (
                        <Skeleton className="h-16" />
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {poiCats.map((c) => (
                            <FilterChip key={c.category} active={!cats || cats.has(c.category)} onClick={() => toggleCat(c.category)} color={PIN_STYLES[c.category]?.color ?? PIN_STYLES.other!.color} count={c.count}>
                              {PIN_STYLES[c.category]?.glyph} {titleCase(c.category)}
                            </FilterChip>
                          ))}
                        </div>
                      )}
                      {poiQ.isLoading ? (
                        <ListSkeleton />
                      ) : poiQ.error ? (
                        <ErrorState error={poiQ.error} onRetry={() => poiQ.refetch()} />
                      ) : !pois.length ? (
                        <EmptyState title="No places selected" icon={<MapPin className="h-6 w-6" />} />
                      ) : (
                        <div className="divide-y divide-black/5 dark:divide-white/5">
                          {pois.map((p) => (
                            <button key={p.id} onClick={() => focusPoint(p.latitude, p.longitude, 17)} className="flex w-full items-center gap-3 py-2 text-start transition hover:bg-white/60 dark:hover:bg-white/5">
                              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm text-white" style={{ background: PIN_STYLES[p.category]?.color ?? "#64748b" }}>
                                {PIN_STYLES[p.category]?.glyph ?? "•"}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-semibold text-ink dark:text-white">{p.name}</span>
                                <span className="block truncate text-[11px] text-ink-mute">
                                  {titleCase(p.subcategory ?? p.category)} · {p.city_name ?? "—"}
                                </span>
                              </span>
                              {p.rating != null && <span className="text-xs font-semibold text-gold-600">★ {p.rating}</span>}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {tab === "layers" && (
                    <div className="space-y-3">
                      <div className="rounded-xl bg-brand-50/70 p-3 dark:bg-white/5">
                        <div className="mb-2 flex items-center justify-between text-xs font-semibold">
                          <span className="text-ink-soft dark:text-slate-300">Layer opacity</span>
                          <span className="tabular-nums text-brand-700 dark:text-brand-300">{layerOpacity}%</span>
                        </div>
                        <Slider value={layerOpacity} min={10} max={100} step={5} onChange={setLayerOpacity} />
                      </div>
                      <MasterPlanPanel
                        labels={{
                          layers: labelLayers,
                          on: labelsOn,
                          loading: activeLayers.some((l, i) => labelsOn.has(l.id) && detailQs[i]?.isLoading),
                          zoomedIn: zoom >= LABEL_MIN_ZOOM,
                          toggle: (id) => {
                            setVis((v) => ({ ...v, layers: true }));
                            setLabelsOn((s) => {
                              const n = new Set(s);
                              if (n.has(id)) n.delete(id);
                              else n.add(id);
                              return n;
                            });
                          },
                        }}
                        map={map}
                        only={layersQ.data ? visiblePlans : undefined}
                        shown={planShown}
                        setShown={(s) => {
                          setPlanShown(s);
                          setVis((v) => ({ ...v, layers: true }));
                        }}
                        onHit={(h) => {
                          setPlanHit(h);
                          if (window.innerWidth < 768) setOpen(false);
                        }}
                        pad={sidePad}
                      />
                      <p className="pt-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Portal GIS layers</p>
                      {layersQ.isLoading ? (
                        <ListSkeleton />
                      ) : layersQ.error ? (
                        <ErrorState error={layersQ.error} onRetry={() => layersQ.refetch()} />
                      ) : !gisLayers.length ? (
                        <EmptyState title="No GIS layers yet" />
                      ) : (
                        gisLayers.map((l) => {
                          const d = details.get(l.id);
                          const color = LAYER_COLORS[l.layer_type] ?? d?.style?.color ?? "#146f45";
                          const on = !hidden.has(l.id);
                          return (
                            <div key={l.id} className={cn("rounded-xl border p-3 transition", on ? "border-brand-200 bg-white/80 dark:border-brand-500/30 dark:bg-white/5" : "border-black/5 opacity-70 dark:border-white/10")}>
                              <div className="flex items-start gap-3">
                                <span className="mt-0.5 h-8 w-8 shrink-0 rounded-lg border-2" style={{ borderColor: color, background: `${color}33`, borderStyle: l.layer_type === "boundary" ? "dashed" : "solid" }} />
                                <div className="min-w-0 flex-1">
                                  <p className="text-sm font-semibold leading-snug text-ink dark:text-white">{l.name}</p>
                                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                    <Badge tone="gray">{titleCase(l.layer_type)}</Badge>
                                    <span className="text-[11px] text-ink-mute">
                                      {l.features} feature{l.features === 1 ? "" : "s"} · {l.entity_type}
                                    </span>
                                  </div>
                                  {d?.description && <p className="mt-1 text-[11px] text-ink-mute">{d.description}</p>}
                                </div>
                                <Toggle
                                  checked={on}
                                  onChange={(v) =>
                                    setHidden((h) => {
                                      const n = new Set(h);
                                      if (v) n.delete(l.id);
                                      else n.add(l.id);
                                      return n;
                                    })
                                  }
                                />
                              </div>
                              <div className="mt-2 flex gap-2">
                                <Button
                                  size="sm"
                                  variant="soft"
                                  icon={<Target className="h-3.5 w-3.5" />}
                                  onClick={async () => {
                                    setVis((v) => ({ ...v, layers: true }));
                                    setHidden((h) => {
                                      const n = new Set(h);
                                      n.delete(l.id);
                                      return n;
                                    });
                                    const g = d?.geojson ?? (await qc.fetchQuery(layerQuery(l.id))).geojson;
                                    fitTo(map, geoBounds(g), 16, sidePad());
                                    if (window.innerWidth < 768) setOpen(false);
                                  }}
                                >
                                  Zoom to
                                </Button>
                                {l.entity_type === "scheme" && (
                                  <Button size="sm" variant="ghost" icon={<FileBarChart className="h-3.5 w-3.5" />} onClick={() => setReport({ title: `${l.name} — GIS report`, path: `/gis/report/scheme/${l.entity_id}` })}>
                                    Report
                                  </Button>
                                )}
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}

                  {tab === "areas" && (
                    <AreasTab
                      aois={aoiQ.data?.areas}
                      loading={aoiQ.isLoading}
                      error={aoiQ.error}
                      retry={() => aoiQ.refetch()}
                      selected={aoiId}
                      onSelect={selectAoi}
                      stats={aoiStatsQ.data}
                      statsLoading={aoiStatsQ.isLoading}
                      statsError={aoiStatsQ.error}
                      onReport={(a) => setReport({ title: `${a.name} — area report`, path: `/aoi/${a.id}/report` })}
                    />
                  )}

                  {tab === "analyse" && (
                    <div className="space-y-4">
                      <Segmented<AnalyseMode>
                        size="sm"
                        className="w-full [&>button]:flex-1 [&>button]:justify-center"
                        value={mode}
                        onChange={setMode}
                        options={[
                          { value: "radius", label: "Radius", icon: <CircleIcon className="h-3.5 w-3.5" /> },
                          { value: "route", label: "Route", icon: <Route className="h-3.5 w-3.5" /> },
                          { value: "rings", label: "Rings", icon: <Radar className="h-3.5 w-3.5" /> },
                        ]}
                      />

                      {mode !== "route" && (
                        <div className="rounded-xl bg-brand-50/70 p-3 dark:bg-white/5">
                          {pt ? (
                            <div className="flex items-center justify-between gap-2 text-xs">
                              <span className="font-mono text-ink-soft dark:text-slate-300">
                                {pt[0].toFixed(4)}, {pt[1].toFixed(4)}
                              </span>
                              <button className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline dark:text-brand-300" onClick={() => setPt(null)}>
                                <RotateCcw className="h-3 w-3" /> Clear
                              </button>
                            </div>
                          ) : (
                            <p className="flex items-center gap-2 text-xs text-ink-mute">
                              <Crosshair className="h-4 w-4 text-gold-600" /> Click anywhere on the map to set the analysis point.
                            </p>
                          )}
                          {mode === "radius" && (
                            <div className="mt-3">
                              <div className="mb-2 flex justify-between text-xs font-semibold">
                                <span className="text-ink-soft dark:text-slate-300">Radius</span>
                                <span className="tabular-nums text-brand-700 dark:text-brand-300">{radius} km</span>
                              </div>
                              <Slider value={radius} min={0.5} max={10} step={0.5} onChange={setRadius} />
                            </div>
                          )}
                          {mode === "rings" && (
                            <div className="mt-3">
                              <p className="label">Ring radii (km, comma-separated)</p>
                              <Input value={radii} onChange={(e) => setRadii(e.target.value)} placeholder="1,3,5" />
                            </div>
                          )}
                        </div>
                      )}

                      {mode === "radius" && pt && <RadiusResults poiQ={nearPoiQ} propQ={nearPropQ} radius={dRadius} onProperty={focusProperty} />}

                      {mode === "rings" && pt && (
                        <div>
                          {ringQ.isLoading ? (
                            <Skeleton className="h-40" />
                          ) : ringQ.error ? (
                            <ErrorState error={ringQ.error} onRetry={() => ringQ.refetch()} />
                          ) : (
                            <div className="space-y-2">
                              {(ringQ.data?.rings ?? []).map((r, i) => (
                                <div key={r.outer_km} className="flex items-center gap-3 rounded-xl border border-black/5 bg-white/70 p-3 dark:border-white/10 dark:bg-white/5">
                                  <span className="h-10 w-1.5 shrink-0 rounded-full" style={{ background: RING_COLORS[i % RING_COLORS.length] }} />
                                  <div className="min-w-0 flex-1">
                                    <p className="text-sm font-bold text-ink dark:text-white">
                                      {r.inner_km}–{r.outer_km} km
                                    </p>
                                    <p className="text-[11px] text-ink-mute">{num(r.summary.area_sqkm, 1)} km² ring</p>
                                  </div>
                                  <div className="grid grid-cols-3 gap-3 text-end text-xs">
                                    <span>
                                      <b className="block text-sm text-ink dark:text-white">{r.summary.properties}</b>listings
                                    </span>
                                    <span>
                                      <b className="block text-sm text-ink dark:text-white">{pkrShort(r.summary.market_value, false)}</b>value
                                    </span>
                                    <span>
                                      <b className="block text-sm text-ink dark:text-white">{compact(r.summary.population)}</b>people
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {mode === "route" && (
                        <div className="space-y-3">
                          <Segmented<"walk" | "bike" | "drive">
                            size="sm"
                            value={travel}
                            onChange={setTravel}
                            options={[
                              { value: "walk", label: "Walk", icon: <Footprints className="h-3.5 w-3.5" /> },
                              { value: "bike", label: "Bike", icon: <CircleIcon className="h-3.5 w-3.5" /> },
                              { value: "drive", label: "Drive", icon: <Navigation className="h-3.5 w-3.5" /> },
                            ]}
                          />
                          <div className="grid grid-cols-2 gap-2">
                            {[0, 1].map((i) => (
                              <div key={i} className={cn("rounded-xl border p-2.5 text-xs", routePts[i] ? "border-brand-200 bg-white/80 dark:border-brand-500/30 dark:bg-white/5" : "border-dashed border-black/15 dark:border-white/15")}>
                                <p className="font-bold text-brand-800 dark:text-brand-200">{i === 0 ? "A · Start" : "B · Destination"}</p>
                                <p className="mt-0.5 font-mono text-ink-mute">{routePts[i] ? `${routePts[i]![0].toFixed(4)}, ${routePts[i]![1].toFixed(4)}` : "click map…"}</p>
                              </div>
                            ))}
                          </div>
                          {routePts.length > 0 && (
                            <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setRoutePts([])}>
                              Reset route
                            </Button>
                          )}
                          {routePts.length === 2 &&
                            (routeQ.isLoading ? (
                              <Skeleton className="h-32" />
                            ) : routeQ.error ? (
                              <ErrorState error={routeQ.error} onRetry={() => routeQ.refetch()} />
                            ) : routeQ.data?.best ? (
                              <div className="space-y-3">
                                <div className="overflow-hidden rounded-2xl bg-brand-gradient p-4 text-white shadow-soft">
                                  <p className="text-[11px] font-bold uppercase tracking-wider text-gold-200">{routeQ.data.best.mode_label}</p>
                                  <div className="mt-1 flex items-end gap-4">
                                    <p className="font-display text-3xl font-bold">{routeQ.data.best.distance_km} km</p>
                                    <p className="pb-1 text-sm text-white/80">{routeQ.data.best.duration_text}</p>
                                  </div>
                                  <p className="mt-1 text-xs text-white/70">avg {routeQ.data.best.average_speed_kmh} km/h</p>
                                </div>
                                <ol className="space-y-1.5">
                                  {routeQ.data.best.steps.map((s, i) => (
                                    <li key={i} className="flex gap-2 text-xs">
                                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[10px] font-bold text-brand-800 dark:bg-brand-500/20 dark:text-brand-200">{i + 1}</span>
                                      <span className="flex-1 text-ink-soft dark:text-slate-300">{s.instruction}</span>
                                      <span className="shrink-0 tabular-nums text-ink-mute">{(s.distance_m / 1000).toFixed(1)} km</span>
                                    </li>
                                  ))}
                                </ol>
                                {routeQ.data.alternatives.length > 0 && (
                                  <div className="space-y-1">
                                    <p className="label">Alternatives</p>
                                    {routeQ.data.alternatives.map((a, i) => (
                                      <div key={i} className="flex justify-between rounded-lg bg-black/[.03] px-3 py-2 text-xs dark:bg-white/5">
                                        <span className="font-semibold">{a.label}</span>
                                        <span className="text-ink-mute">
                                          {a.distance_km} km · {a.duration_text}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ) : null)}
                        </div>
                      )}

                      <ReportsCard properties={properties} cities={citiesQ.data?.cities ?? []} schemes={schemesQ.data?.schemes ?? []} onOpen={setReport} />
                    </div>
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
          </>
        )}
      </motion.aside>

      <ReportModal report={report} onClose={() => setReport(null)} />
    </div>
  );
}

// ======================================================================= pieces
function ListSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex gap-3">
          <Skeleton className="h-14 w-20" />
          <div className="flex-1 space-y-2 py-1">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

function PropertyPopup({ p }: { p: Property }) {
  return (
    <div className="bg-white text-ink dark:bg-[#0d1f16] dark:text-white">
      <div className="relative h-28 overflow-hidden">
        <img src={coverImage(p)} alt="" className="h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
        <p className="absolute bottom-2 start-3 font-display text-lg font-bold text-white drop-shadow">{pkrShort(p.price)}</p>
        {p.featured && (
          <span className="chip absolute end-2 top-2 bg-gold-gradient text-brand-950">
            <Sparkles className="h-3 w-3" /> Featured
          </span>
        )}
      </div>
      <div className="p-3">
        <p className="line-clamp-1 text-sm font-semibold">{p.title}</p>
        <p className="mt-0.5 line-clamp-1 text-[11px] text-ink-mute">
          {[p.sector, p.city_name].filter(Boolean).join(", ")} · {titleCase(p.category)} · {titleCase(p.use_type)}
        </p>
        <Link to={`/properties/${p.id}`} className="btn btn-primary btn-sm mt-2.5 w-full justify-center !text-white">
          View details <ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" />
        </Link>
      </div>
    </div>
  );
}

function PoiPopup({ p }: { p: Poi }) {
  const st = PIN_STYLES[p.category] ?? PIN_STYLES.other!;
  return (
    <div className="bg-white p-3 text-ink dark:bg-[#0d1f16] dark:text-white">
      <div className="flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl text-base text-white" style={{ background: st.color }}>
          {st.glyph}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{p.name}</p>
          <p className="text-[11px] text-ink-mute">
            {titleCase(p.subcategory ?? p.category)} · {p.city_name ?? ""}
          </p>
        </div>
      </div>
      {p.rating != null && <p className="mt-2 text-xs font-semibold text-gold-600">★ {p.rating} rating</p>}
    </div>
  );
}

function AreasTab({
  aois,
  loading,
  error,
  retry,
  selected,
  onSelect,
  stats,
  statsLoading,
  statsError,
  onReport,
}: {
  aois?: Aoi[];
  loading: boolean;
  error: unknown;
  retry: () => void;
  selected: string | null;
  onSelect: (a: Aoi) => void;
  stats?: AoiStats;
  statsLoading: boolean;
  statsError: unknown;
  onReport: (a: Aoi) => void;
}) {
  if (loading) return <ListSkeleton />;
  if (error) return <ErrorState error={error} onRetry={retry} />;
  if (!aois?.length) return <EmptyState title="No areas of interest" icon={<Square className="h-6 w-6" />} />;
  const sel = aois.find((a) => a.id === selected);
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        {aois.map((a) => (
          <button
            key={a.id}
            onClick={() => onSelect(a)}
            className={cn(
              "w-full rounded-xl border p-3 text-start transition",
              a.id === selected ? "border-gold-400 bg-gold-50/80 shadow-soft dark:border-gold-400/50 dark:bg-gold-500/10" : "border-black/5 bg-white/60 hover:border-brand-200 dark:border-white/10 dark:bg-white/5",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold text-ink dark:text-white">{a.name}</p>
              <Badge tone={a.kind === "circle" ? "blue" : "purple"}>{a.kind}</Badge>
            </div>
            {a.description && <p className="mt-0.5 line-clamp-2 text-[11px] text-ink-mute">{a.description}</p>}
            <div className="mt-1.5 flex flex-wrap gap-1">
              {a.area_sqm != null && <span className="text-[11px] font-semibold text-brand-700 dark:text-brand-300">{num(a.area_sqm / 1e6, 2)} km²</span>}
              {(a.tags ?? []).map((t) => (
                <span key={t} className="rounded-full bg-black/5 px-2 py-0.5 text-[10px] font-medium text-ink-soft dark:bg-white/10 dark:text-slate-300">
                  #{t}
                </span>
              ))}
            </div>
          </button>
        ))}
      </div>

      {sel && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-brand-200/70 bg-white/80 p-4 dark:border-white/10 dark:bg-white/5">
          <p className="section-eyebrow">Area statistics</p>
          <p className="mt-1 font-display font-bold text-ink dark:text-white">{sel.name}</p>
          {statsLoading ? (
            <Skeleton className="mt-3 h-40" />
          ) : statsError ? (
            <div className="mt-3">
              <ErrorState error={statsError} />
            </div>
          ) : stats ? (
            <div className="mt-3 space-y-4">
              <div className="flex items-center gap-4">
                <ScoreRing value={stats.accessibility} label="Access" size={78} />
                <div className="grid flex-1 grid-cols-2 gap-2">
                  <MiniStat label="Listings" value={stats.properties} />
                  <MiniStat label="Places" value={stats.pois} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <MiniStat label="Market value" value={pkrShort(stats.market_value)} />
                <MiniStat label="Area" value={`${num(stats.area.area_acres, 1)} acres`} hint={`${num(stats.area.area_kanal, 0)} kanal`} />
                <MiniStat label="Population" value={compact(stats.population)} hint={`${num(stats.density_per_sqkm, 1)}/km²`} />
                <MiniStat label="Dev. cost" value={pkrShort(stats.development_cost)} />
              </div>
              {Object.keys(stats.poi_by_category).length > 0 && (
                <div>
                  <p className="label">Places by category</p>
                  <BarList items={Object.entries(stats.poi_by_category).map(([k, v]) => ({ label: `${PIN_STYLES[k]?.glyph ?? "•"} ${titleCase(k)}`, value: v }))} />
                </div>
              )}
              <ReportButton onClick={() => onReport(sel)} icon={<FileBarChart className="h-4 w-4" />}>
                Full area report
              </ReportButton>
            </div>
          ) : null}
        </motion.div>
      )}
    </div>
  );
}

function RadiusResults({
  poiQ,
  propQ,
  radius,
  onProperty,
}: {
  poiQ: { data?: { pois: Poi[]; count: number }; isLoading: boolean; error: unknown; refetch: () => unknown };
  propQ: { data?: { results: (Property & { distance_km?: number })[]; count: number }; isLoading: boolean; error: unknown; refetch: () => unknown };
  radius: number;
  onProperty: (p: Property) => void;
}) {
  const byCat = useMemo(() => {
    const m: Record<string, number> = {};
    (poiQ.data?.pois ?? []).forEach((p) => (m[p.category] = (m[p.category] ?? 0) + 1));
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [poiQ.data]);
  if (poiQ.isLoading || propQ.isLoading) return <Skeleton className="h-48" />;
  if (poiQ.error) return <ErrorState error={poiQ.error} onRetry={() => poiQ.refetch()} />;
  if (propQ.error) return <ErrorState error={propQ.error} onRetry={() => propQ.refetch()} />;
  const props = propQ.data?.results ?? [];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        <MiniStat label={`Listings ≤ ${radius} km`} value={propQ.data?.count ?? 0} />
        <MiniStat label={`Places ≤ ${radius} km`} value={poiQ.data?.count ?? 0} />
      </div>
      {byCat.length > 0 && (
        <div>
          <p className="label">Amenity mix</p>
          <BarList items={byCat.map(([k, v]) => ({ label: `${PIN_STYLES[k]?.glyph ?? "•"} ${titleCase(k)}`, value: v }))} />
        </div>
      )}
      <div>
        <p className="label">Listings in range</p>
        {!props.length ? (
          <p className="rounded-xl border border-dashed border-black/10 p-4 text-center text-xs text-ink-mute dark:border-white/10">No listings within {radius} km — widen the radius.</p>
        ) : (
          <div className="space-y-1">
            {props.map((p) => (
              <button key={p.id} onClick={() => onProperty(p)} className="flex w-full items-center gap-3 rounded-xl p-1.5 text-start transition hover:bg-white/70 dark:hover:bg-white/5">
                <img src={coverImage(p)} alt="" className="h-11 w-14 shrink-0 rounded-lg object-cover" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold text-ink dark:text-white">{p.title}</span>
                  <span className="block text-xs font-bold text-brand-700 dark:text-brand-300">{pkrShort(p.price)}</span>
                </span>
                {p.distance_km != null && <span className="text-[11px] font-semibold text-ink-mute">{p.distance_km} km</span>}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ReportsCard({ properties, cities, schemes, onOpen }: { properties: Property[]; cities: City[]; schemes: Scheme[]; onOpen: (r: ReportRef) => void }) {
  const [propId, setPropId] = useState("");
  const [cityId, setCityId] = useState("");
  const [schemeId, setSchemeId] = useState("");
  const [metric, setMetric] = useState("market_value");
  const pid = propId || properties[0]?.id || "";
  const cid = cityId || cities[0]?.id || "";
  const sid = schemeId || schemes[0]?.id || "";
  return (
    <div className="rounded-2xl border border-black/5 bg-white/70 p-4 dark:border-white/10 dark:bg-white/5">
      <div className="mb-3 flex items-center gap-2">
        <FileBarChart className="h-4 w-4 text-gold-600" />
        <p className="font-display text-sm font-bold text-ink dark:text-white">Live GIS reports</p>
      </div>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Select value={pid} onChange={(e) => setPropId(e.target.value)} options={properties.map((p) => ({ value: p.id, label: p.title }))} />
          <ReportButton disabled={!pid} onClick={() => pid && onOpen({ title: "Property GIS report", path: `/gis/report/property/${pid}`, query: { include_outlook: true } })} icon={<Building2 className="h-4 w-4" />}>
            Property analysis report
          </ReportButton>
        </div>
        <div className="space-y-1.5">
          <Select value={sid} onChange={(e) => setSchemeId(e.target.value)} options={schemes.map((s) => ({ value: s.id, label: `${s.name} · ${s.city}` }))} />
          <ReportButton disabled={!sid} onClick={() => sid && onOpen({ title: "Society investment outlook", path: `/gis/outlook/scheme/${sid}` })} icon={<Eye className="h-4 w-4" />}>
            Society investment outlook
          </ReportButton>
        </div>
        <div className="space-y-1.5">
          <div className="grid grid-cols-2 gap-1.5">
            <Select value={cid} onChange={(e) => setCityId(e.target.value)} options={cities.map((c) => ({ value: c.id, label: c.name }))} />
            <Select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              options={["market_value", "property_count", "avg_price", "price_per_marla", "population", "density_per_sqkm", "development_cost", "economic_output", "jobs"].map((m) => ({ value: m, label: titleCase(m) }))}
            />
          </div>
          <ReportButton disabled={!cid} onClick={() => cid && onOpen({ title: "Thematic city map", path: `/gis/thematic/city/${cid}`, query: { metric, palette: "greens" } })} icon={<MapIcon className="h-4 w-4" />}>
            Thematic (choropleth) map
          </ReportButton>
        </div>
      </div>
      <p className="mt-3 flex items-center gap-1 text-[11px] text-ink-mute">
        <Sparkles className="h-3 w-3 text-gold-500" /> Generated live from the portal's GIS engine.
      </p>
    </div>
  );
}
