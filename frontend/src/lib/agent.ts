/**
 * Tool-calling assistant for the portal chat (same agent as the portable app).
 *
 * When the backend has OpenAI connected (GET /ai/capabilities → chat_mode "upstream"),
 * the model gets the assistant's tools (GET /ai/tools — the definitions the live voice
 * agent uses) and the portal runs each call against the REST API with the visitor's own
 * session: listing search, details, places and area facts, DHA master plans, web lookup,
 * the user's listings and call requests. Without OpenAI the chat falls back to the local
 * RAG answer (see components/ai/ChatPanel).
 */
import type { NearbyList, NearbyPlace, Property, PropertyList } from "@/types";
import { useAuth } from "@/store/auth";
import { API_BASE, get, post } from "./api";
import { pkrShort } from "./format";
import { focusMap, getMapRender, getMapView, getPointer, lastFocusAt, onMapPage, routeOnMap, type Spot } from "./mapFocus";
import { attachmentShape, geodataParts, showShapeOnMap, type ChatAttachment, type ChatFile, type LocationCard } from "./chatShare";
import { areaUnits, centroid, fmtLatLon, googleMapsUrl, lengthUnits, parseCoords, pathLengthM, polygonAreaM2, toDms, type LatLon } from "./geoMeasure";

export interface Capabilities {
  chat_mode: "local" | "upstream";
  chat_model: string;
}

let caps: Promise<Capabilities> | null = null;
export function capabilities(): Promise<Capabilities> {
  caps ??= get<Capabilities>("/ai/capabilities", undefined, { noFallback: true }).catch(() => {
    caps = null;
    return { chat_mode: "local" as const, chat_model: "portal-realestate-rag" };
  });
  return caps;
}

type ToolDef = { type: "function"; function: { name: string; description: string; parameters: unknown } };
let toolDefs: Promise<ToolDef[]> | null = null;
function chatTools(): Promise<ToolDef[]> {
  toolDefs ??= get<{ tools: ToolDef[] }>("/ai/tools", undefined, { noFallback: true })
    .then((r) => [...r.tools, FOCUS_MAP, READ_MAP, MAP_LAYERS, ROUTE_ON_MAP, OFFER_CHOICES, MAKE_DOCUMENT, SHARE_LOCATION, MEASURE])
    .catch((e) => {
      toolDefs = null;
      throw e;
    });
  return toolDefs;
}

/** Web-only tool: move the portal's own map (the Map page) — the chat's map cards can't do that. */
const FOCUS_MAP: ToolDef = {
  type: "function",
  function: {
    name: "focus_map",
    description:
      "Move the portal's main map (the Map page behind this chat) to a place, block, sector, society or listing, mark it and " +
      "switch on the master plan there. Opens the Map page if the user is elsewhere. Use whenever the user asks to zoom / " +
      "go / fly the map to somewhere, or to show something 'on the map' / 'on the front-end map'. This really moves the map — " +
      "never claim the map moved without calling it.",
    parameters: {
      type: "object",
      properties: {
        place: { type: "string", description: "What to go to, as specific as possible, e.g. 'Umar Block, Bahria Town Phase 8 Safari Valley, Rawalpindi'" },
        listing_id: { type: "string", description: "Or a listing id from search_listings / get_listing" },
        latitude: { type: "number", description: "Or coordinates (with longitude)" },
        longitude: { type: "number" },
        zoom: { type: "number", description: "10 = city, 13 = society, 15 = block / sector (default), 17 = street" },
        master_plan: { type: "boolean", description: "Also switch on the master plan covering the spot (default true)" },
      },
      additionalProperties: false,
    },
  },
};

/** Web-only tool: read what is in the user's current map view, from every layer switched on. */
const READ_MAP: ToolDef = {
  type: "function",
  function: {
    name: "read_map",
    description:
      "Read the user's current view on the portal's Map page: its area, zoom and every layer switched on (master plans, " +
      "GIS layers, listings, places, roads …), and count what is inside it — parks, mosques, schools, blocks and roads from " +
      "the master plans (their text, and parks read from the plan drawing's colours), OpenStreetMap places, population, " +
      "listings, housing societies and mega projects. Call it for any question about the map / this area / the current " +
      "view / what is visible ('how many parks here?', 'what is this area?', 'which layers are on?', 'which roads?').",
    parameters: { type: "object", properties: {}, additionalProperties: false },
  },
};

/** Web-only tool: everything the portal's map has (not only what is on screen). */
const MAP_LAYERS: ToolDef = {
  type: "function",
  function: {
    name: "map_layers",
    description:
      "Search / list every layer the portal's map has — master plans of DHA, Bahria Town, housing societies and Islamabad CDA " +
      "sectors (by city), uploaded GIS layers and their named features, housing societies and mega projects — with where each " +
      "is (centre, extent) and plan accuracy. Use it for 'which societies / sectors / plans do you have', 'is X on the map', " +
      "'what layers are there in Rawalpindi', to find the exact name of a society before focus_map, and before ever saying " +
      "something isn't on the map. q: a name or part of one; city; kind (master plan | mega project | housing society | GIS); " +
      "or near_latitude / near_longitude for what is around a point.",
    parameters: {
      type: "object",
      properties: {
        q: { type: "string" },
        city: { type: "string" },
        kind: { type: "string" },
        near_latitude: { type: "number" },
        near_longitude: { type: "number" },
        limit: { type: "number", description: "Default 25" },
      },
      additionalProperties: false,
    },
  },
};

/** What the map holds, in one line for the system prompt (fetched once). */
let layerSummary: Promise<string> | null = null;
function mapLayerSummary(): Promise<string> {
  layerSummary ??= get<{ total_on_map: number; counts: Record<string, number>; master_plans_by_group_and_city: Record<string, Record<string, number>> }>("/map/layers", { limit: 1 })
    .then((r) => {
      const plans = Object.entries(r.master_plans_by_group_and_city)
        .map(([g, byCity]) => `${g} (${Object.entries(byCity).map(([c, n]) => `${c} ${n}`).join(", ")})`)
        .join("; ");
      const other = Object.entries(r.counts)
        .filter(([k]) => k !== "master plan")
        .map(([k, n]) => `${n} ${k}${n === 1 ? "" : "s"}`)
        .join(", ");
      return `THE PORTAL MAP HAS ${r.total_on_map} named layers: master plans — ${plans}; plus ${other}. Find any of them with map_layers (by name, city or near a point); focus_map and every place lookup find them by name too.`;
    })
    .catch(() => {
      layerSummary = null;
      return "";
    });
  return layerSummary;
}

/** Web-only tool: a route on the portal's map, starting from what the user means by "here". */
const ROUTE_ON_MAP: ToolDef = {
  type: "function",
  function: {
    name: "route_on_map",
    description:
      "Find the shortest / fastest route on real roads and show it on the portal's Map page (route finder with turn-by-turn " +
      "steps). from: 'auto' (default) picks the start the user means — the listing selected on the map (or the listing page " +
      "they are on), else their device's location, else the centre of the map view — and asks when that's ambiguous. " +
      "Use from='my_location' when the user says 'my (current) location', 'selected' for the selected listing / place, " +
      "'map_center' for 'the centre of the map', or a place name. to: a place / listing / society name, or 'selected', " +
      "'search_pin', 'assistant_pin'. Use it for any route / directions / 'how far by road' question.",
    parameters: {
      type: "object",
      properties: {
        to: { type: "string", description: "Destination: a place, society, block or listing name; or selected | search_pin | assistant_pin" },
        to_listing_id: { type: "string", description: "Or the destination listing's id" },
        from: { type: "string", description: "auto (default) | my_location | selected | map_center | search_pin | assistant_pin | a place name" },
        from_listing_id: { type: "string", description: "Or the start listing's id" },
        mode: { type: "string", enum: ["drive", "bike", "walk"], description: "Default drive" },
      },
      additionalProperties: false,
    },
  },
};

/** Web-only tool: put 2–4 choices under the reply as buttons when the request is ambiguous. */
const OFFER_CHOICES: ToolDef = {
  type: "function",
  function: {
    name: "offer_choices",
    description:
      "When the user's request could mean different things (which listing, which start point, which society / phase, which " +
      "city), ask one short question and offer 2–4 concrete choices — they appear as buttons the user can tap. Then stop and " +
      "follow the user's pick.",
    parameters: {
      type: "object",
      properties: {
        question: { type: "string" },
        choices: { type: "array", items: { type: "string" }, minItems: 2, maxItems: 4, description: "Short, specific options in the user's language" },
      },
      required: ["question", "choices"],
      additionalProperties: false,
    },
  },
};

/** Web-only tool: make a PDF report or a picture and hand it over in the chat. */
const MAKE_DOCUMENT: ToolDef = {
  type: "function",
  function: {
    name: "make_document",
    description:
      "Make a file for the user — a PDF report or a PNG picture — and put it in the chat with Open / Download buttons. Subjects: " +
      "route (the route in the map's route finder: map, distance, time, turn-by-turn), map_view (the user's current map view with " +
      "its layers and what is in it), listing, measurement (the distance / area measured on the map or attached), location (a pin, " +
      "place or coordinates), conversation (this chat), custom (a report you write: give sections). Use it whenever the user asks " +
      "for a PDF, report, document, printout, file, picture / image / screenshot of the map or route, or to save / download / share " +
      "something. Never say you can't make files. For a route, call route_on_map first if no route is showing.",
    parameters: {
      type: "object",
      properties: {
        subject: { type: "string", enum: ["route", "map_view", "listing", "measurement", "location", "conversation", "custom"] },
        format: { type: "string", enum: ["pdf", "image"], description: "Default pdf; image = a PNG map picture" },
        title: { type: "string" },
        notes: { type: "string", description: "A short summary / your findings to print in the report, in the user's language" },
        listing_id: { type: "string" },
        place: { type: "string", description: "location: a place name or coordinates" },
        latitude: { type: "number" },
        longitude: { type: "number" },
        sections: {
          type: "array",
          description: "custom: the report's sections",
          items: {
            type: "object",
            properties: {
              heading: { type: "string" },
              text: { type: "string" },
              bullets: { type: "array", items: { type: "string" } },
              table: { type: "object", properties: { headers: { type: "array", items: { type: "string" } }, rows: { type: "array", items: { type: "array", items: { type: "string" } } } } },
            },
          },
        },
        include_map: { type: "boolean", description: "custom: add a picture of the current map view" },
      },
      required: ["subject"],
      additionalProperties: false,
    },
  },
};

/** Web-only tool: a location card (coordinates, DMS, Google Maps, show on map). */
const SHARE_LOCATION: ToolDef = {
  type: "function",
  function: {
    name: "share_location",
    description:
      "Share a location in the chat as a card: its name, coordinates (decimal and degrees-minutes-seconds), a Google Maps link and " +
      "'Show on map'. source: mouse (where the user's mouse is / was on the map), pin (a pin the user dropped or shared), selected " +
      "(the selected listing / place), map_center, my_location (the device's GPS), place (a name or address), coordinates (latitude " +
      "+ longitude). Use for 'what are the coordinates of …', 'share / send me the location', 'where is my mouse', 'pin this'.",
    parameters: {
      type: "object",
      properties: {
        source: { type: "string", enum: ["mouse", "pin", "selected", "map_center", "my_location", "place", "coordinates"] },
        place: { type: "string" },
        latitude: { type: "number" },
        longitude: { type: "number" },
        label: { type: "string", description: "A name for the card" },
      },
      required: ["source"],
      additionalProperties: false,
    },
  },
};

/** Web-only tool: distances and areas, drawn on the map. */
const MEASURE: ToolDef = {
  type: "function",
  function: {
    name: "measure",
    description:
      "Measure a distance (straight line between places, or along several points) or an area (of a shape from corners) and draw it " +
      "on the portal's map. points: place names, listing titles or 'lat, lon' strings in order. Without points it measures what the " +
      "user measured on the map or attached (a measurement, KML / GeoJSON / GPX). Returns every unit: m, km, ft, miles; m², sq ft, " +
      "marla and kanal (272.25 sq ft marla, and 225 sq ft as many societies use), acres. For distance BY ROAD use route_on_map.",
    parameters: {
      type: "object",
      properties: {
        kind: { type: "string", enum: ["distance", "area"] },
        points: { type: "array", items: { type: "string" }, description: "Places / coordinates in order (2+ for distance, 3+ for area)" },
      },
      required: ["kind"],
      additionalProperties: false,
    },
  },
};

/** What the user attached in this conversation (newest last) — the tools can use it. */
let sharedThisChat: ChatAttachment[] = [];

/** A place, block, society or listing name → a point (gazetteer, shorter forms of the name, then master-plan text). */
async function findSpot(text: string): Promise<Spot | null> {
  const c = parseCoords(text);
  if (c) return { label: fmtLatLon(c[0], c[1], 5), lat: c[0], lon: c[1] };
  const lookup = async (place: string) => (await get<MapCard>("/places/map", { place, per_kind: 1, radius_km: 0.5 }).catch(() => null))?.focus ?? null;
  const parts = text.split(/\s*,\s*/).filter(Boolean);
  const tries = [text, parts.slice(0, 2).join(" "), parts.slice(0, 2).reverse().join(" "), ...parts.slice(0, -1).map((_, i) => parts.slice(0, parts.length - 1 - i).join(", "))].filter(
    (q, i, all) => q && all.indexOf(q) === i,
  );
  for (const q of tries) {
    const f = await lookup(q);
    if (f) return { label: f.name, lat: f.latitude, lon: f.longitude };
  }
  const hit = (await get<{ results: { text: string; plan: string; latitude: number; longitude: number }[] }>("/masterplans/search", { q: parts[0], limit: 1 }).catch(() => null))?.results?.[0];
  return hit ? { label: `${hit.text}, ${hit.plan}`, lat: hit.latitude, lon: hit.longitude } : null;
}

async function listingSpot(id: string): Promise<Spot | null> {
  const p = await get<Property>(`/properties/${id}`).catch(() => null);
  return p && p.latitude != null && p.longitude != null ? { label: p.title, lat: p.latitude, lon: p.longitude } : null;
}

/** The device's position (asks the browser; null with the reason when it can't). */
function deviceSpot(timeoutMs = 9000): Promise<{ spot: Spot | null; why?: string }> {
  return new Promise((res) => {
    if (!navigator.geolocation) return res({ spot: null, why: "this browser has no location service" });
    navigator.geolocation.getCurrentPosition(
      (p) => res({ spot: { label: `Your location (±${Math.round(p.coords.accuracy)} m)`, lat: p.coords.latitude, lon: p.coords.longitude } }),
      (e) => res({ spot: null, why: e.code === 1 ? "location permission was refused" : e.code === 3 ? "the location request timed out" : "the device couldn't find its location" }),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60_000 },
    );
  });
}

/** The listing the user is looking at: selected on the map, or the listing page they are on. */
async function selectedListing(): Promise<(Spot & { id: string }) | null> {
  const sel = getMapView()?.selection.listing;
  if (sel) return sel;
  const m = window.location.pathname.match(/\/properties\/([^/?#]+)/);
  if (m) {
    const s = await listingSpot(m[1]!);
    return s ? { ...s, id: m[1]! } : null;
  }
  return null;
}

/** The user's screen, as context for "this", "here", "selected", "my location" (sent with every turn). */
function screenContext(): string {
  const v = getMapView();
  const path = window.location.pathname;
  const ctx: Record<string, unknown> = { page: path };
  const listingPage = path.match(/\/properties\/([^/?#]+)/);
  if (listingPage) ctx.viewing_listing_id = listingPage[1];
  if (v) {
    const clean = Object.fromEntries(Object.entries(v.selection).filter(([, x]) => x !== undefined && x !== null));
    ctx.page = "Map page";
    ctx.map_view = { center: [Number(((v.south + v.north) / 2).toFixed(6)), Number(((v.west + v.east) / 2).toFixed(6))], zoom: v.zoom, plans_on: v.plans.length, layers_on: v.overlays };
    ctx.selection = Object.keys(clean).length ? clean : "nothing selected";
    const p = getPointer();
    if (p) ctx.mouse_on_map = { lat: p.lat, lon: p.lon, seconds_ago: Math.round((Date.now() - p.at) / 1000) };
  }
  const shared = sharedThisChat.slice(-6).map((a) => (a.kind === "image" || a.kind === "document" || a.kind === "geodata" ? `${a.kind}: ${a.name}` : `${a.kind}: ${a.label}`));
  if (shared.length) ctx.shared_in_this_chat = shared;
  return `SCREEN CONTEXT (live, read from the user's screen this turn — use it to resolve "this", "here", "selected", "the listing", "my location"; ids are for tools only): ${JSON.stringify(ctx)}`;
}

/** A button under the reply: a portal link. */
export interface ChatLink {
  label: string;
  to: string;
  primary?: boolean;
}
export interface MapCard {
  focus: { name: string; latitude: number; longitude: number; bounds?: [number, number, number, number]; kind?: string };
  markers: { name: string; kind: string; latitude: number; longitude: number; distance_km?: number }[];
}
/** A knowledge-base hit the reply can cite as [n] (POST /ai/knowledge/search, /ai/context). */
export interface KnowledgeSource {
  cite: string;
  type: string;
  id: string;
  title: string;
  url: string;
  tier: "official" | "verified" | "reference" | "listing" | "unverified";
  trust: string;
  snippet?: string;
  sources?: { title?: string; url?: string }[];
}
/** What tool calls add under the reply. */
export interface AgentEffect {
  /** Open this portal page (e.g. the Map page focus_map moved). */
  navigate?: string;
  /** Quick replies under the reply (a choice when the request is ambiguous); a click sends it. */
  choices?: string[];
  listings?: Property[];
  links?: ChatLink[];
  image?: { url: string; caption: string };
  map?: MapCard;
  sources?: KnowledgeSource[];
  /** Files the assistant made (PDF reports, map pictures). */
  files?: ChatFile[];
  /** A shared location card. */
  location?: LocationCard;
}

interface AiContext {
  system_prompt: string;
  knowledge: { results: KnowledgeSource[] };
  memory: { enabled: boolean; items: { kind: string; value: string }[] };
}

/** One id per browser tab, so the server's short-term memory keeps this conversation together. */
const conversationId = (() => {
  try {
    const key = "arzepak.chat.conversation";
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const id = `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem(key, id);
    return id;
  } catch {
    return `web-${Date.now().toString(36)}`;
  }
})();
export interface AgentReply extends AgentEffect {
  content: string;
}

const brief = (p: Property) => ({
  id: p.id,
  title: p.title,
  price: pkrShort(p.price),
  price_rupees: p.price,
  city: p.city_name,
  category: p.category,
  size_marla: p.marla_area ?? undefined,
  bedrooms: p.bedrooms ?? undefined,
  bathrooms: p.bathrooms ?? undefined,
  distance_km: p.distance_km,
  features: p.amenities?.length ? p.amenities : undefined,
  nearby: p.nearby ? `${p.nearby.name} (${p.nearby.kind}), ${p.nearby.distance_km} km` : undefined,
  status: p.status,
});
const nearbyLine = (n: NearbyPlace) => `${n.name} (${n.kind}), ${n.distance_km} km, ~${n.walk_minutes} min walk`;

const SEARCH_KEYS = ["city", "category", "use_type", "min_price", "max_price", "bedrooms", "min_bathrooms", "min_marla", "max_marla", "featured", "feature", "near", "near_km", "near_place"];
const PLACE_KEYS = ["kind", "area", "near", "radius_km", "name"];
const pick = (args: Record<string, unknown>, keys: string[]) =>
  Object.fromEntries(Object.entries(args).filter(([k, v]) => keys.includes(k) && v !== undefined && v !== null && v !== "")) as Record<string, string | number>;
const str = (args: Record<string, unknown>, k: string) => (args[k] ? String(args[k]) : undefined);
const numArg = (args: Record<string, unknown>, k: string) => (typeof args[k] === "number" ? (args[k] as number) : undefined);

/** The portal's /properties page understands these filters (others are dropped from "See all"). */
function browseLink(q: Record<string, string | number>): string {
  const sp = new URLSearchParams();
  if (q.city) sp.set("city", String(q.city));
  if (q.category) sp.set("category", String(q.category));
  if (q.use_type) sp.set("use_type", String(q.use_type));
  if (q.min_price) sp.set("min", String(q.min_price));
  if (q.max_price) sp.set("max", String(q.max_price));
  if (q.bedrooms) sp.set("beds", String(q.bedrooms));
  if (q.min_bathrooms) sp.set("baths", String(q.min_bathrooms));
  if (q.feature) sp.set("feature", String(q.feature));
  if (q.near) sp.set("near", String(q.near));
  if (q.near_place) sp.set("near_place", String(q.near_place));
  if (q.near_km && (q.near || q.near_place)) sp.set("near_km", String(q.near_km));
  const s = sp.toString();
  return `/properties${s ? `?${s}` : ""}`;
}

async function runTool(name: string, args: Record<string, unknown>): Promise<{ output: unknown; effect: AgentEffect }> {
  if (name === "search_listings") {
    const query = pick(args, SEARCH_KEYS);
    const r = await get<PropertyList>("/search", { ...query, limit: 6 });
    const nearest = r.nearest_outside_radius ?? [];
    return {
      output: {
        count: r.count,
        results: r.results.map(brief),
        searched_with: query,
        ...(r.near_place ? { near_place: r.near_place } : {}),
        ...(nearest.length ? { nearest_outside_radius: nearest.map(brief) } : {}),
        ...(r.note ? { note: r.note } : {}),
        shown_on_screen: r.count ? `Listing cards and a 'See all ${r.count}' button` : "A 'Browse all' button",
      },
      effect: {
        listings: r.results.length ? r.results : nearest,
        links: [r.count ? { label: `See all ${r.count}`, to: browseLink(query), primary: true } : { label: "Browse all", to: "/properties" }],
      },
    };
  }
  if (name === "get_listing") {
    const id = String(args.id ?? "");
    const [p, near] = await Promise.all([get<Property>(`/properties/${id}`), get<NearbyList>(`/properties/${id}/nearby`).catch(() => null)]);
    return {
      output: {
        ...brief(p),
        description: p.description,
        nearby_places: near?.nearby.map(nearbyLine) ?? [],
        location: [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", "),
        shown_on_screen: "This listing's card with an 'Open listing' button.",
      },
      effect: { listings: [p], links: [{ label: "Open listing", to: `/properties/${p.id}`, primary: true }] },
    };
  }
  if (name === "find_places") return { output: await get("/places/find", { ...pick(args, PLACE_KEYS), limit: 15 }), effect: {} };
  if (name === "area_info") return { output: await get("/areas/profile", { area: String(args.area ?? "") }), effect: {} };
  if (name === "master_plan") {
    const action = String(args.action ?? "summary");
    const output =
      action === "search"
        ? await get("/masterplans/search", { q: str(args, "query") ?? str(args, "place") ?? "", plan: str(args, "plan"), category: str(args, "category"), limit: 15 })
        : action === "at"
          ? await get("/masterplans/at", { place: str(args, "place"), listing_id: str(args, "listing_id"), plan: str(args, "plan"), radius_m: numArg(args, "radius_m") })
          : await get(`/masterplans/${encodeURIComponent(str(args, "plan") ?? "")}`);
    return { output, effect: {} };
  }
  if (name === "show_plan") {
    const v = await get<{ plan: string; location: string; snapshot_url: string; on_the_plan: unknown; accuracy: unknown }>("/masterplans/view", {
      plan: str(args, "plan"),
      place: str(args, "place"),
      listing_id: str(args, "listing_id"),
      radius_m: numArg(args, "radius_m"),
    });
    return {
      output: { ok: true, shown_on_screen: `A close-up of the ${v.plan} master plan around ${v.location}.`, on_the_plan: v.on_the_plan, accuracy: v.accuracy },
      effect: { image: { url: `${API_BASE}${v.snapshot_url}`, caption: `${v.plan} master plan — ${v.location}` } },
    };
  }
  if (name === "show_map") {
    const view = await get<MapCard & { radius_km: number }>("/places/map", {
      listing_id: str(args, "listing_id"),
      place: !args.listing_id ? str(args, "place") : undefined,
      kinds: Array.isArray(args.kinds) ? (args.kinds as string[]).join(",") : undefined,
      radius_km: numArg(args, "radius_km"),
    });
    return {
      output: { ok: true, shown_on_screen: `A map of ${view.focus.name} with ${view.markers.length} nearby places marked.`, radius_km: view.radius_km, marked: view.markers.map((m) => `${m.name} (${m.kind}, ${m.distance_km} km)`) },
      effect: { map: view },
    };
  }
  if (name === "focus_map") {
    const place = str(args, "place");
    let spot: { name: string; latitude: number; longitude: number; bounds?: [number, number, number, number]; kind?: string } | null = null;
    const lookup = async (q: { listing_id?: string; place?: string }) =>
      (await get<MapCard>("/places/map", { ...q, per_kind: 1, radius_km: 0.5 }).catch(() => null))?.focus ?? null;
    const coords = place ? parseCoords(place) : null;
    const lat = numArg(args, "latitude");
    const lon = numArg(args, "longitude");
    if (lat !== undefined && lon !== undefined) spot = { name: fmtLatLon(lat, lon, 5), latitude: lat, longitude: lon };
    else if (coords) spot = { name: fmtLatLon(coords[0], coords[1], 5), latitude: coords[0], longitude: coords[1] };
    else if (args.listing_id) spot = await lookup({ listing_id: str(args, "listing_id") });
    else if (place) {
      // The model adds society / city context ("Umar Block, Safari Valley, Bahria Town Phase 8, Rawalpindi") that
      // the gazetteer may not match: try the full name, then shorter forms, then the master-plan text.
      const parts = place.split(/\s*,\s*/).filter(Boolean);
      const tries = [place, parts.slice(0, 2).join(" "), parts.slice(0, 2).reverse().join(" "), ...parts.slice(0, -1).map((_, i) => parts.slice(0, parts.length - 1 - i).join(", "))]
        .filter((q, i, all) => q && all.indexOf(q) === i);
      for (const q of tries) if ((spot = await lookup({ place: q }))) break;
      if (!spot) {
        const hit = (await get<{ results: { text: string; plan: string; latitude: number; longitude: number }[] }>("/masterplans/search", { q: parts[0], limit: 1 }).catch(() => null))?.results?.[0];
        if (hit) spot = { name: `${hit.text}, ${hit.plan}`, latitude: hit.latitude, longitude: hit.longitude };
      }
    }
    if (!spot) {
      // Not a place name: what on the map is called like it (for the model to offer as choices).
      const near = await get<{ results: { name: string; kind: string; city?: string }[] }>("/map/layers", { q: place ?? "", limit: 5 }).catch(() => null);
      return {
        output: {
          ok: false,
          error: `Couldn't find "${place ?? args.listing_id}".`,
          similar_layers_on_the_map: near?.results?.map((r) => `${r.name} (${r.kind}${r.city ? `, ${r.city}` : ""})`) ?? [],
          what_to_do: "If one of the similar layers fits, offer them with offer_choices; otherwise ask for a nearby landmark or the society name.",
        },
        effect: {},
      };
    }
    const asked = numArg(args, "zoom");
    const zoom = Math.max(5, Math.min(19, asked ?? 15));
    // A whole society / sector / project: fit it, unless a closer (street) zoom was asked for.
    const fit = spot.bounds && (asked === undefined || asked <= 15) ? spot.bounds : undefined;
    const wasOnMap = onMapPage();
    focusMap({ name: spot.name, latitude: spot.latitude, longitude: spot.longitude, zoom, masterPlan: args.master_plan !== false, bounds: fit });
    return {
      output: {
        ok: true,
        moved_main_map: true,
        location: spot.name,
        ...(spot.kind ? { what_it_is: spot.kind } : {}),
        ...(fit ? { showing: "the whole of it" } : {}),
        coordinates: [Number(spot.latitude.toFixed(5)), Number(spot.longitude.toFixed(5))],
        zoom,
        shown_on_screen: wasOnMap ? "The main map has flown there and the spot is marked." : "The Map page is opening, centred there with the spot marked.",
      },
      effect: wasOnMap ? {} : { navigate: "/map" },
    };
  }
  if (name === "offer_choices") {
    const choices = (Array.isArray(args.choices) ? (args.choices as unknown[]) : []).map(String).filter(Boolean).slice(0, 4);
    return { output: { ok: true, shown_on_screen: "The choices are buttons under your reply. Ask the question briefly and wait." }, effect: { choices } };
  }
  if (name === "route_on_map") {
    const sel = getMapView()?.selection;
    const named = (k?: string): Spot | null | undefined =>
      k === "search_pin" ? sel?.search_pin ?? null : k === "assistant_pin" ? sel?.assistant_pin ?? null : k === "map_center" ? centreSpot() : undefined;
    const centreSpot = (): Spot | null => {
      const v = getMapView();
      return v ? { label: "Centre of the map view", lat: (v.south + v.north) / 2, lon: (v.west + v.east) / 2 } : null;
    };
    // ---- destination
    const toKey = str(args, "to")?.trim();
    let to: Spot | null = null;
    if (args.to_listing_id) to = await listingSpot(str(args, "to_listing_id")!);
    else if (toKey && /^(selected|selected_listing|this|this listing)$/i.test(toKey)) to = (await selectedListing()) ?? sel?.place ?? null;
    else if (toKey && named(toKey) !== undefined) to = named(toKey) ?? null;
    else if (toKey) to = await findSpot(toKey);
    if (!to) return { output: { ok: false, ask_user: `Where to? I couldn't place "${toKey ?? "the destination"}" — ask for a landmark, society or listing.` }, effect: {} };
    // ---- start: what the user means by "here"
    const fromKey = (str(args, "from") ?? "auto").trim();
    let from: Spot | null = null;
    let why = "";
    if (args.from_listing_id) {
      from = await listingSpot(str(args, "from_listing_id")!);
      why = "the listing you named";
    } else if (/^(my_location|my location|current location|here)$/i.test(fromKey)) {
      const d = await deviceSpot();
      from = d.spot;
      why = "your device's location";
      if (!from)
        return {
          output: { ok: false, ask_user: `I couldn't get your location (${d.why}). Should I start from the selected listing, the centre of the map, or a place you name?` },
          effect: { choices: ["Start from the selected listing", "Start from the centre of the map", "Allow my location and try again"] },
        };
    } else if (/^(selected|selected_listing|this listing)$/i.test(fromKey)) {
      from = (await selectedListing()) ?? sel?.place ?? null;
      why = "the selected listing";
      if (!from)
        return {
          output: { ok: false, ask_user: "Nothing is selected on the map. Open a listing's pin first, or tell me where to start (your location, a place)." },
          effect: { choices: ["Start from my current location", "Start from the centre of the map"] },
        };
    } else if (fromKey !== "auto" && named(fromKey) !== undefined) {
      from = named(fromKey) ?? null;
      why = fromKey.replace("_", " ");
    } else if (fromKey !== "auto") {
      from = await findSpot(fromKey);
      why = "the place you named";
    } else {
      // auto: the selected listing → the device's location → the map centre; ask when two selections compete
      const listing = await selectedListing();
      const same = (a: Spot | null | undefined, b: Spot) => !!a && Math.abs(a.lat - b.lat) < 1e-5 && Math.abs(a.lon - b.lon) < 1e-5;
      const others = [sel?.place, sel?.search_pin, sel?.analysis_point].filter((x): x is Spot => !!x && !same(x, to!));
      const listingUsable = listing && !same(listing, to) ? listing : null;
      if (listingUsable && others.length) {
        return {
          output: {
            ok: false,
            ask_user: `Should the route start from the selected listing (${listingUsable.label}) or from ${others.map((o) => o.label).join(" / ")} — or from your current location?`,
          },
          effect: { choices: [`Start from ${listingUsable.label}`, ...others.slice(0, 2).map((o) => `Start from ${o.label}`), "Start from my current location"] },
        };
      }
      if (listingUsable) {
        from = listingUsable;
        why = sel?.listing ? "the listing selected on the map" : "the listing page you're on";
      } else if (others.length === 1) {
        from = others[0]!;
        why = "the point selected on the map";
      } else {
        const d = await deviceSpot();
        if (d.spot) {
          from = d.spot;
          why = "your device's location";
        } else {
          from = centreSpot();
          why = `the centre of the map view (no listing selected and ${d.why})`;
          if (!from)
            return {
              output: { ok: false, ask_user: `Where should the route start? Nothing is selected and ${d.why}.` },
              effect: { choices: ["Allow my location and try again", "Open the map so I can pick a start"] },
            };
        }
      }
    }
    if (!from) return { output: { ok: false, ask_user: `I couldn't place the start "${fromKey}". Where should the route start?` }, effect: {} };
    const mode = (["drive", "bike", "walk"].includes(String(args.mode)) ? args.mode : "drive") as "drive" | "bike" | "walk";
    const d = await get<{ routes: { label: string; distance_text: string; duration_text: string; via: string[] }[]; source: string }>("/geo/directions", {
      from_lat: from.lat,
      from_lon: from.lon,
      to_lat: to.lat,
      to_lon: to.lon,
      mode,
    });
    const wasOnMap = onMapPage();
    routeOnMap({ from, to, mode });
    return {
      output: {
        ok: true,
        from: { place: from.label, chosen_because: why },
        to: to.label,
        mode,
        routes: d.routes.slice(0, 3).map((x) => ({ route: x.label, distance: x.distance_text, time: x.duration_text, via: x.via.slice(0, 4) })),
        shown_on_screen: wasOnMap ? "The route is drawn on the map with turn-by-turn steps in the route finder." : "The Map page is opening with the route and its steps.",
        how_to_answer: "Say where the route starts and why (e.g. 'from the selected listing'), give the shortest route's distance and time, and mention a faster alternative if there is one.",
      },
      effect: wasOnMap ? {} : { navigate: "/map" },
    };
  }
  if (name === "read_map") {
    const settle = 1800 - (Date.now() - lastFocusAt()); // just flown somewhere: let the map arrive first
    if (settle > 0) await new Promise((res) => setTimeout(res, settle));
    const v = getMapView();
    if (!v) return { output: { ok: false, error: "The Map page isn't open. Offer to open it (focus_map) on a place first." }, effect: {} };
    const read = await get<Record<string, unknown>>("/map/read", {
      south: v.south.toFixed(6),
      west: v.west.toFixed(6),
      north: v.north.toFixed(6),
      east: v.east.toFixed(6),
      zoom: v.zoom,
      plans: v.plans.map((p) => p.key).join(","),
      gis: v.gis.map((l) => l.id).join(","),
      overlays: v.overlays.join(","),
    });
    return {
      output: {
        ok: true,
        switched_on: { master_plans: v.plans.map((p) => p.name), gis_layers: v.gis.map((l) => `${l.name} (${l.type})`), overlays: v.overlays, base_map: v.base },
        ...read,
        how_to_answer:
          "Answer from these numbers and name the source (master plan text / master plan drawing / OpenStreetMap / portal listings). " +
          "Parks read from a plan drawing's colours are approximate; on a plan with text, prefer its park labels. " +
          "Where plans overlap, lead with the plan covering most of the view (largest plan_area_in_view_m2) and don't add their counts. " +
          "If several sources disagree, give both briefly. Don't list ids or keys.",
      },
      effect: {},
    };
  }
  if (name === "web_lookup") {
    const r = await post<{ answer: string; sources: { site: string; url: string }[] }>("/ai/web-lookup", { question: String(args.question ?? "") });
    return { output: { answer: r.answer, sources: r.sources.map((x) => x.site) }, effect: {} };
  }
  if (name === "my_listings") {
    if (!useAuth.getState().token) return { output: { error: "not_signed_in" }, effect: { links: [{ label: "Sign in", to: "/login?next=/app/listings", primary: true }] } };
    const r = await get<PropertyList>("/me/listings", undefined, { noFallback: true });
    return { output: { count: r.count, results: r.results.slice(0, 10).map(brief) }, effect: { listings: r.results.slice(0, 5), links: [{ label: "My listings", to: "/app/listings" }] } };
  }
  if (name === "request_call") {
    const p = await get<Property>(`/properties/${String(args.listing_id ?? args.id ?? "")}`);
    const open = { label: "Open listing", to: `/properties/${p.id}`, primary: true };
    if (p.status !== "active") return { output: { ok: false, error: `listing is ${p.status}` }, effect: { listings: [p], links: [open] } };
    const user = useAuth.getState().user;
    if (!user || (!user.mobile && !user.email))
      return { output: { ok: false, error: "not_signed_in", shown_on_screen: "A 'Sign in' button" }, effect: { listings: [p], links: [open, { label: "Sign in", to: `/login?next=/properties/${p.id}` }] } };
    const when = typeof args.preferred_time === "string" && args.preferred_time.trim() ? `\nPreferred time: ${args.preferred_time.trim()}` : "";
    const note = typeof args.message === "string" && args.message.trim() ? `\n${args.message.trim()}` : "";
    await post("/crm/leads", {
      name: user.name || user.mobile || user.email,
      phone: user.mobile ?? undefined,
      email: user.email ?? undefined,
      source: "website_ai",
      interest_use_type: p.use_type,
      interest_category: p.category,
      budget_max: p.price,
      city_id: p.city_id ?? undefined,
      scheme_id: p.scheme_id ?? undefined,
      assigned_agent_id: p.agent_id || undefined,
      notes: `Call request from the Arz-e-Pak AI assistant (web).${when}${note}\n\nListing: ${p.title} (${p.id})`,
    });
    return { output: { ok: true, sent_to: "the owner / agent of this listing", they_will_contact: user.mobile ? "by phone" : "by e-mail" }, effect: { listings: [p], links: [open] } };
  }
  if (name === "draft_listing") {
    return {
      output: { ok: true, shown_on_screen: "A 'List a property' button that opens the listing form.", signed_in: !!useAuth.getState().token },
      effect: { links: [{ label: "List a property", to: "/app/listings/new", primary: true }] },
    };
  }
  if (name === "knowledge_search") {
    const r = await post<{ results: KnowledgeSource[]; context: string }>("/ai/knowledge/search", {
      query: str(args, "query") ?? "",
      types: Array.isArray(args.types) ? args.types : undefined,
      k: 6,
    });
    return { output: { results: r.context || "nothing found in the portal's knowledge base", cite_with: "the [n] markers" }, effect: { sources: r.results } };
  }
  if (name === "remember") {
    if (!useAuth.getState().token) return { output: { ok: false, reason: "The user is not signed in, so nothing can be remembered." }, effect: {} };
    const r = await post<{ remembered?: boolean; error?: string }>("/me/memory", { text: str(args, "note") ?? "" });
    return { output: r, effect: {} };
  }
  if (name === "map_layers") {
    const r = await get<Record<string, unknown>>("/map/layers", {
      q: str(args, "q"),
      city: str(args, "city"),
      kind: str(args, "kind"),
      lat: numArg(args, "near_latitude"),
      lon: numArg(args, "near_longitude"),
      limit: Math.max(1, Math.min(60, numArg(args, "limit") ?? 25)),
    });
    return { output: { ...r, how_to_answer: "Name the layers with their city; to show one call focus_map with its exact name. Don't list coordinates unless asked." }, effect: {} };
  }
  if (name === "make_document") return makeDocument(args);
  if (name === "share_location") {
    const r = await resolveLocation(str(args, "source") ?? "place", args);
    if ("ask_user" in r) return { output: { ok: false, ask_user: r.ask_user }, effect: r.choices ? { choices: r.choices } : {} };
    const s = r.spot;
    const label = str(args, "label") ?? s.label;
    return {
      output: {
        ok: true,
        location: label,
        decimal: fmtLatLon(s.lat, s.lon),
        dms: toDms(s.lat, s.lon),
        google_maps: googleMapsUrl(s.lat, s.lon),
        shown_on_screen: "A location card with the coordinates, Copy, Google Maps and 'Show on map' buttons.",
      },
      effect: { location: { label, lat: s.lat, lon: s.lon, note: r.why } },
    };
  }
  if (name === "measure") return measureTool(args);
  return { output: { error: `unknown tool ${name}` }, effect: {} };
}

// ------------------------------------------------------------------ locations, measuring, documents

/** A point the user means: the mouse, a pin, the selection, the map centre, the device, a place or coordinates. */
async function resolveLocation(source: string, args: Record<string, unknown>): Promise<{ spot: Spot; why: string } | { ask_user: string; choices?: string[] }> {
  const lat = numArg(args, "latitude");
  const lon = numArg(args, "longitude");
  if (lat !== undefined && lon !== undefined) return { spot: { label: fmtLatLon(lat, lon, 5), lat, lon }, why: "the coordinates given" };
  const sel = getMapView()?.selection;
  const pinned = [...sharedThisChat].reverse().find((a) => a.kind === "pin") as Extract<ChatAttachment, { kind: "pin" }> | undefined;
  if (source === "mouse") {
    const p = getPointer();
    if (!p) return { ask_user: "I can't see your mouse on the map yet — move it over the map (or right-click the spot → 'Ask AI about this point') and ask again." };
    return { spot: { label: "Mouse position", lat: p.lat, lon: p.lon }, why: `where your mouse ${Date.now() - p.at < 5000 ? "is" : "last was"} on the map` };
  }
  if (source === "pin") {
    const dropped = sel?.user_pins?.at(-1);
    if (pinned) return { spot: { label: pinned.label, lat: pinned.lat, lon: pinned.lon }, why: "the point you shared" };
    if (dropped) return { spot: dropped, why: "your dropped pin" };
    return { ask_user: "There's no pin yet. Right-click the spot on the map → 'Drop a pin here' (or 'Ask AI about this point')." };
  }
  if (source === "selected") {
    const s = (await selectedListing()) ?? sel?.place ?? sel?.search_pin ?? null;
    return s ? { spot: s, why: "what is selected" } : { ask_user: "Nothing is selected. Open a listing's pin or search a place first, or tell me the place." };
  }
  if (source === "map_center") {
    const v = getMapView();
    return v ? { spot: { label: "Centre of the map view", lat: (v.south + v.north) / 2, lon: (v.west + v.east) / 2 }, why: "the centre of your map view" } : { ask_user: "The Map page isn't open." };
  }
  if (source === "my_location") {
    const d = await deviceSpot();
    return d.spot ? { spot: d.spot, why: "your device's location" } : { ask_user: `I couldn't get your location (${d.why}).`, choices: ["Allow my location and try again", "Use the centre of the map"] };
  }
  const place = str(args, "place");
  if (!place) return { ask_user: "Which place? Give me a name, an address or coordinates." };
  const s = await findSpot(place);
  return s ? { spot: s, why: "the place you named" } : { ask_user: `I couldn't find "${place}" — a nearby landmark, society or the coordinates would help.` };
}

async function measureTool(args: Record<string, unknown>): Promise<{ output: unknown; effect: AgentEffect }> {
  const kind = str(args, "kind") === "area" ? "area" : "distance";
  const names = Array.isArray(args.points) ? (args.points as unknown[]).map(String).filter(Boolean) : [];
  let coords: LatLon[] = [];
  let source = "";
  if (names.length) {
    const spots = await Promise.all(names.map((n) => findSpot(n)));
    const missing = names.filter((_, i) => !spots[i]);
    if (missing.length) return { output: { ok: false, ask_user: `I couldn't place ${missing.map((m) => `"${m}"`).join(", ")} — a landmark, society or coordinates?` }, effect: {} };
    coords = spots.map((s) => [s!.lat, s!.lon] as LatLon);
    source = "the places given";
  } else {
    const m = getMapRender()?.measure;
    const att = [...sharedThisChat].reverse().find((a) => a.kind === "measure" || a.kind === "geodata");
    if (m && m.mode === kind) {
      coords = m.coords;
      source = "your measurement on the map";
    } else if (att?.kind === "measure") {
      coords = att.coords;
      source = "the measurement you shared";
    } else if (att?.kind === "geodata") {
      const parts = geodataParts(att.geojson);
      coords = kind === "area" ? (parts.polys[0]?.ring ?? []) : (parts.lines[0]?.line ?? []);
      source = `the file ${att.name}`;
    }
    if (!coords.length)
      return {
        output: { ok: false, ask_user: `What should I measure? Name the places, or measure it on the map (Measure tool → ${kind === "area" ? "Area" : "Distance"}) and send it to me.` },
        effect: {},
      };
  }
  if (kind === "area" && coords.length < 3) return { output: { ok: false, ask_user: "An area needs at least three corners." }, effect: {} };
  if (kind === "distance" && coords.length < 2) return { output: { ok: false, ask_user: "A distance needs at least two points." }, effect: {} };
  const flip = (p: LatLon): [number, number] => [p[1], p[0]];
  const len = lengthUnits(kind === "area" ? pathLengthM([...coords, coords[0]!]) : pathLengthM(coords));
  const area = kind === "area" ? areaUnits(polygonAreaM2(coords)) : undefined;
  const label = kind === "area" ? `Area ${area!.text}` : `Distance ${len.text}`;
  showShapeOnMap({
    id: "assistant-measure",
    name: label,
    fit: true,
    geojson: {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: { name: label }, geometry: kind === "area" ? { type: "Polygon", coordinates: [[...coords, coords[0]!].map(flip)] } : { type: "LineString", coordinates: coords.map(flip) } }],
    },
  });
  sharedThisChat.push({ kind: "measure", label, mode: kind, coords, value_text: kind === "area" ? area!.text : len.text });
  const wasOnMap = onMapPage();
  return {
    output: {
      ok: true,
      measured: source,
      ...(area ? { area, perimeter: len.text } : { straight_line_distance: len }),
      centre: centroid(coords).map((x) => Number(x.toFixed(6))),
      shown_on_screen: wasOnMap ? "It is drawn on the map." : "The Map page is opening with it drawn.",
      how_to_answer: kind === "area" ? "Give the area in marla / kanal (say which marla size) and m² or acres as fits." : "This is the straight line; mention that the road distance is longer (route_on_map) if relevant.",
    },
    effect: wasOnMap ? {} : { navigate: "/map" },
  };
}

async function makeDocument(args: Record<string, unknown>): Promise<{ output: unknown; effect: AgentEffect }> {
  const docs = await import("./mapDocs"); // PDF / picture code loads only when a file is asked for
  const subject = str(args, "subject") ?? "map_view";
  const kind = str(args, "format") === "image" ? "image" : "pdf";
  const notes = str(args, "notes");
  const done = (f: ChatFile | { error: string }, extra: Record<string, unknown> = {}) =>
    "error" in f
      ? { output: { ok: false, error: f.error, ...extra }, effect: {} }
      : { output: { ok: true, file: f.name, kind: f.kind, size_kb: Math.round(f.size / 1024), shown_on_screen: "The file is in the chat with Open and Download buttons.", ...extra }, effect: { files: [f] } };
  if (subject === "route") {
    const f = await docs.routeFile(kind, notes);
    return "error" in f ? done(f, { what_to_do: onMapPage() ? "Call route_on_map first (ask where from / to if unclear), then make_document again." : "Open the route first with route_on_map." }) : done(f);
  }
  if (subject === "map_view") {
    const v = getMapView();
    if (!v) return done({ error: "The Map page isn't open." }, { what_to_do: "Offer to open it with focus_map on a place first." });
    const facts = await get<Record<string, unknown>>("/map/read", {
      south: v.south.toFixed(6),
      west: v.west.toFixed(6),
      north: v.north.toFixed(6),
      east: v.east.toFixed(6),
      zoom: v.zoom,
      plans: v.plans.map((p) => p.key).join(","),
      gis: v.gis.map((l) => l.id).join(","),
      overlays: v.overlays.join(","),
    }).catch(() => undefined);
    const keep = facts ? Object.fromEntries(Object.entries(facts).filter(([k]) => !/^(how_to|view|bounds|zoom|note)/.test(k))) : undefined;
    return done(await docs.mapViewFile(kind, { title: str(args, "title"), notes, facts: keep }));
  }
  if (subject === "listing") {
    const id = str(args, "listing_id") ?? (await selectedListing())?.id;
    if (!id) return done({ error: "No listing named or selected." }, { what_to_do: "Ask which listing (offer_choices with the ones discussed)." });
    const [p, near] = await Promise.all([get<Property>(`/properties/${id}`), get<NearbyList>(`/properties/${id}/nearby`).catch(() => null)]);
    return done(await docs.listingFile(p, kind, near?.nearby ?? [], notes));
  }
  if (subject === "measurement") {
    const m = getMapRender()?.measure;
    const att = [...sharedThisChat].reverse().find((a) => a.kind === "measure") as Extract<ChatAttachment, { kind: "measure" }> | undefined;
    const src = m ?? (att ? { mode: att.mode, coords: att.coords } : null);
    if (!src) return done({ error: "Nothing has been measured." }, { what_to_do: "Ask the user to measure with the map's Measure tool, or use the measure tool with places." });
    return done(await docs.measureFile(src, kind, notes));
  }
  if (subject === "location") {
    const r = await resolveLocation(args.latitude !== undefined ? "coordinates" : str(args, "place") ? "place" : "pin", args);
    if ("ask_user" in r) return { output: { ok: false, ask_user: r.ask_user }, effect: {} };
    return done(await docs.locationFile({ ...r.spot, label: str(args, "title") ?? r.spot.label }, kind, notes));
  }
  if (subject === "conversation") return done(await docs.chatFile(chatForReport, str(args, "title")));
  const sections = Array.isArray(args.sections) ? (args.sections as import("./mapDocs").ReportSection[]) : notes ? [{ text: notes }] : [];
  if (!sections.length) return done({ error: "A custom report needs sections." });
  return done(await docs.writtenReport(str(args, "title") ?? "Report", sections, { withMap: args.include_map === true }));
}
/** The conversation so far, for a "conversation" PDF. */
let chatForReport: { role: "user" | "assistant"; content: string }[] = [];

function merge(a: AgentEffect, b: AgentEffect): AgentEffect {
  const links = [...(b.listings ? [] : a.links ?? []), ...(b.links ?? [])].filter((x, i, all) => all.findIndex((y) => y.label === x.label) === i);
  return {
    choices: b.choices ?? a.choices,
    navigate: b.navigate ?? a.navigate,
    listings: b.listings ?? a.listings,
    links: links.length ? links : undefined,
    image: b.image ?? a.image,
    map: b.map ?? a.map,
    sources: a.sources || b.sources ? [...(a.sources ?? []), ...(b.sources ?? [])] : undefined,
    files: a.files || b.files ? [...(a.files ?? []), ...(b.files ?? [])] : undefined,
    location: b.location ?? a.location,
  };
}

/** Knowledge, memory and the shared system prompt for this question (one fast call). */
async function aiContext(query: string): Promise<AiContext | null> {
  try {
    return await post<AiContext>("/ai/context", { query, conversation_id: conversationId, channel: "chat", k: 5 });
  } catch {
    return null; // the built-in prompt below still works
  }
}

/** Keep only the sources the reply actually cites ([1], [2] …). */
function cited(content: string, sources?: KnowledgeSource[]): KnowledgeSource[] | undefined {
  const used = (sources ?? []).filter((s) => content.includes(s.cite));
  return used.length ? used : undefined;
}

function systemPrompt(): string {
  const user = useAuth.getState().user;
  return [
    "You are Arz-e-Pak AI, the friendly real-estate assistant on the Arz-e-Pak web portal in Pakistan. You help people find, buy, rent, sell and list property.",
    user ? `You are talking to ${user.name ?? "a member"} (${user.role} account).` : "The visitor is a guest (not signed in).",
    "Reply in the language of the user's latest message: Urdu in Urdu script, Roman Urdu in English letters, or English.",
    "Keep replies short (under 120 words), warm and practical; markdown bullet points only when comparing options. Prices in crore/lakh, sizes in marla/kanal (1 kanal = 20 marla). Never read out ids.",
    "Search yourself with search_listings — never ask the user to press a search button. Follow-ups refine the previous search. If nothing is found, relax one filter, search again and say what you changed. Mention the best 1-3 results; they appear as cards under your reply. Never invent listings.",
    "To show one listing call get_listing. 'Near a school / mosque / mall': search_listings with near (feature for things inside the property). 'Near <a named place>': near_place; if nothing is in range, name the nearest listings it returns (nearest_outside_radius) with their distance.",
    "Area questions (what's in it, how many schools, population, how developed): find_places and area_info, with real names and numbers. A map with nearby places in the chat: show_map. To move the portal's own map (zoom / go to a block, sector, society or listing 'on the map'): focus_map. DHA Islamabad-Rawalpindi phases: master_plan (summary / search / at) and show_plan for a close-up; say it's from the master plan and what is built may differ.",
    "For approval status, possession, developer, news or anything else the tools don't cover, use web_lookup and name the source. Never guess facts.",
    "To visit or talk to the owner, offer a call request and call request_call once they agree. To sell or rent out, ask briefly for missing essentials then call draft_listing. Their own listings: my_listings.",
    "Only mention buttons a tool result says are on screen.",
  ].join("\n");
}

/** Added to the server's prompt: what only the web portal can do. */
const WEB_ONLY = [
  "You are on the web portal, which has a full Map page with many GIS layers (DHA, Bahria Town and housing-society master plans, places, roads, listings, mega projects, uploaded layers).",
  "To zoom / go / fly the map somewhere, or show a place, block, sector or listing 'on the map' / 'on the front-end map': focus_map (it moves the main map, opening the Map page if needed, and switches on the master plan there). show_map only puts a small map in the chat. Never say the main map moved unless focus_map returned ok.",
  "Never tell the user a society, sector, phase or project isn't on the map before checking map_layers; if a name doesn't match, call map_layers with part of it and offer the closest names as choices.",
  "Any question about what is on the map, in this area / the current view / visible ('how many parks here', 'what is this', 'which roads / layers', 'is there a mosque nearby'): call read_map first and answer from it — never say you can't see the map. After focus_map, call read_map if the user also asked what is there.",
  "When a request is ambiguous, don't guess: call offer_choices (or use a tool's ask_user / choices) with 2–4 concrete options and follow what the user picks. The user's choice wins; if it can't work (no location permission, a place that doesn't exist, a listing that isn't on the map), say why politely and offer the closest choice that does.",
  "SCREEN CONTEXT tells you what the user has selected (a listing pin, a place, a search pin, the route finder, the item being edited) and the active tool: 'this / selected / here / the listing' mean those. Routes / directions / 'how far by road': route_on_map — with from='auto' unless the user names the start ('my current location' = my_location). If it returns ask_user, ask exactly that and wait.",
  "FILES: you can make real files. 'PDF / report / document / print / save / download / picture / screenshot / image of the map or route': make_document (subject route | map_view | listing | measurement | location | conversation | custom; format pdf or image) — the file appears in the chat; never say you can't make PDFs or images. For a route PDF with no route showing, call route_on_map first. Put a short summary in notes, in the user's language.",
  "LOCATIONS & MEASURING: share_location for coordinates / 'send me the location' / 'where is my mouse' (SCREEN CONTEXT mouse_on_map is the mouse); measure for straight-line distances and areas (marla, kanal, acres …) — by road is route_on_map. Coordinates the user types (decimal, DMS, a Google Maps link) work as a place in every tool.",
  "WHAT USERS SEND YOU: pictures (photos, screenshots, scanned plans — look at them and describe what matters for property), documents (their text is in the message between <<< >>>), map files (KML / GeoJSON / GPX — summarised and drawn on the map), and from the Map page a pin, a measured distance / area or 'Ask AI about this point'. Use them as the subject of the question. If you can't tell what the user wants with what they sent (a picture with no question, two documents, a pin and a listing), ask one short question with offer_choices (e.g. 'Find the area on the map', 'Read the plot details', 'Estimate its value') instead of guessing.",
  "Be a good conversation partner: confirm what you understood when a request is long or has several parts, say briefly what you did, and end with one helpful next step when there is one. If the user corrects you, accept it and continue from their correction.",
].join(" ");

interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}
type Part = { type: "text"; text: string } | { type: "image_url"; image_url: { url: string; detail?: "auto" | "low" | "high" } };
interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string | Part[] | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}
export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  attachments?: ChatAttachment[];
}

/** How an attachment reads to the model (pictures go as images, the rest as text). */
export function attachmentText(a: ChatAttachment, full: boolean): string {
  if (a.kind === "image") return `[Picture attached: ${a.name}, ${a.width}×${a.height}]`;
  if (a.kind === "document") {
    const body = full ? a.text : `${a.text.slice(0, 1500)}${a.text.length > 1500 ? " …" : ""}`;
    return `[Document attached: ${a.name}${a.pages ? `, ${a.pages} pages` : ""}${a.truncated ? " (only the start could be read)" : ""}${a.note ? ` — ${a.note}` : ""}]\n<<<\n${body}\n>>>`;
  }
  if (a.kind === "geodata") return `[Map file attached: ${a.name} — shown on the map] ${a.summary}`;
  if (a.kind === "pin") return `[Location shared from the map (${a.source}): ${a.label} at ${fmtLatLon(a.lat, a.lon)} — ${toDms(a.lat, a.lon)}]`;
  return `[Measurement shared from the map: ${a.mode} ${a.value_text}; ${a.coords.length} points; ${JSON.stringify(a.mode === "area" ? areaUnits(polygonAreaM2(a.coords)) : lengthUnits(pathLengthM(a.coords)))}; points ${JSON.stringify(a.coords.map((p) => p.map((x) => Number(x.toFixed(6)))))}]`;
}

/** The turns as model messages: the last 2 user turns' pictures go as images (6 at most), older ones as a note. */
function modelTurns(history: ChatTurn[]): ChatMessage[] {
  const turns = history.slice(-12);
  const userIdx = turns.map((m, i) => (m.role === "user" ? i : -1)).filter((i) => i >= 0);
  const recent = new Set(userIdx.slice(-2));
  const latest = userIdx.at(-1);
  let images = 0;
  const out = turns.map((m, i): ChatMessage => {
    if (!m.attachments?.length) return { role: m.role, content: m.content };
    const text = [m.content || "(no message — see what is attached)", ...m.attachments.map((a) => attachmentText(a, i === latest || (recent.has(i) && a.kind !== "document")))].join("\n\n");
    const pics = recent.has(i) ? m.attachments.filter((a): a is Extract<ChatAttachment, { kind: "image" }> => a.kind === "image") : [];
    if (!pics.length) return { role: m.role, content: text };
    const parts: Part[] = [{ type: "text", text }];
    for (const p of pics) if (images++ < 6) parts.push({ type: "image_url", image_url: { url: p.dataUrl, detail: "auto" } });
    return { role: m.role, content: parts };
  });
  return out;
}

/** Answer one user turn with the tool-calling agent. Throws when the model can't be reached. */
export async function agentReply(history: ChatTurn[], model: string): Promise<AgentReply> {
  const last = [...history].reverse().find((m) => m.role === "user");
  const question = [last?.content ?? "", ...(last?.attachments ?? []).filter((a) => a.kind !== "image").map((a) => attachmentText(a, false).slice(0, 600))].join("\n");
  sharedThisChat = history.flatMap((m) => m.attachments ?? []);
  chatForReport = history.filter((m) => m.content).map((m) => ({ role: m.role, content: m.content }));
  // Show attached map files on the map so the user and the tools see the same shapes.
  for (const a of last?.attachments ?? []) {
    const fc = a.kind === "geodata" ? attachmentShape(a) : null;
    if (fc && a.kind === "geodata") showShapeOnMap({ id: `chat-file-${a.name}`, name: a.name, geojson: fc, fit: true });
  }
  const [tools, ctx, layersLine] = await Promise.all([chatTools(), aiContext(question), mapLayerSummary()]);
  const messages: ChatMessage[] = [{ role: "system", content: (ctx?.system_prompt || systemPrompt()) + `\n${WEB_ONLY}\n${layersLine}\n${screenContext()}` }, ...modelTurns(history)];
  let effect: AgentEffect = { sources: ctx?.knowledge?.results };
  const finish = (content: string): AgentReply => {
    if (useAuth.getState().token) void post("/ai/turn", { content, conversation_id: conversationId }).catch(() => undefined);
    return { content, ...effect, sources: cited(content, effect.sources) };
  };
  for (let round = 0; round < 4; round++) {
    const r = await post<{ choices: { message: ChatMessage }[] }>("/v1/chat/completions", {
      model,
      messages,
      tools,
      tool_choice: round === 3 ? "none" : "auto",
      // gpt-5.x models only accept function tools in Chat Completions with reasoning off.
      reasoning_effort: "none",
    });
    const msg = r.choices?.[0]?.message;
    if (!msg) throw new Error("empty reply");
    if (!msg.tool_calls?.length) {
      const content = (typeof msg.content === "string" ? msg.content : "").trim();
      if (!content) throw new Error("empty reply");
      return finish(content);
    }
    messages.push({ role: "assistant", content: msg.content ?? null, tool_calls: msg.tool_calls });
    // Independent tool calls run in parallel; results go back in the order they were asked. read_map
    // waits for the rest (a focus_map in the same step moves the map it is about to read).
    const runCall = async (call: ToolCall) => {
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(call.function.arguments || "{}");
      } catch {
        /* keep {} */
      }
      try {
        const run = await runTool(call.function.name, args);
        if (import.meta.env.DEV) console.debug("[assistant tool]", call.function.name, args, run.output);
        return { call, ...run };
      } catch (e) {
        return { call, output: { error: (e as Error).message } as unknown, effect: {} as AgentEffect };
      }
    };
    const isRead = (c: ToolCall) => c.function.name === "read_map";
    const first = await Promise.all(msg.tool_calls.filter((c) => !isRead(c)).map(runCall));
    const later = await Promise.all(msg.tool_calls.filter(isRead).map(runCall));
    const runs = msg.tool_calls.map((c) => [...first, ...later].find((r) => r.call === c)!);
    for (const run of runs) {
      // Knowledge found by a tool continues the numbering of what the context already gave ([6], [7] …).
      const offset = effect.sources?.length ?? 0;
      if (offset && run.effect.sources?.length) {
        const shift = (cite: string) => `[${Number(cite.replace(/\D/g, "")) + offset}]`;
        run.effect.sources = run.effect.sources.map((s) => ({ ...s, cite: shift(s.cite) }));
        const out = run.output as { results?: unknown };
        if (typeof out?.results === "string") out.results = out.results.replace(/^\[(\d+)\]/gm, (m) => shift(m));
      }
      effect = merge(effect, run.effect);
      messages.push({ role: "tool", tool_call_id: run.call.id, content: JSON.stringify(run.output ?? {}) });
    }
  }
  throw new Error("too many tool rounds");
}
