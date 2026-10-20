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
import { focusMap, getMapView, lastFocusAt, onMapPage } from "./mapFocus";

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
    .then((r) => [...r.tools, FOCUS_MAP, READ_MAP])
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

/** A button under the reply: a portal link. */
export interface ChatLink {
  label: string;
  to: string;
  primary?: boolean;
}
export interface MapCard {
  focus: { name: string; latitude: number; longitude: number };
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
  listings?: Property[];
  links?: ChatLink[];
  image?: { url: string; caption: string };
  map?: MapCard;
  sources?: KnowledgeSource[];
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
    let spot: { name: string; latitude: number; longitude: number } | null = null;
    const lookup = async (q: { listing_id?: string; place?: string }) =>
      (await get<MapCard>("/places/map", { ...q, per_kind: 1, radius_km: 0.5 }).catch(() => null))?.focus ?? null;
    if (args.listing_id) spot = await lookup({ listing_id: str(args, "listing_id") });
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
    if (!spot) return { output: { ok: false, error: `Couldn't find "${place ?? args.listing_id}" — ask for a nearby landmark or the society name.` }, effect: {} };
    const zoom = Math.max(5, Math.min(19, numArg(args, "zoom") ?? 15));
    const wasOnMap = onMapPage();
    focusMap({ ...spot, zoom, masterPlan: args.master_plan !== false });
    return {
      output: {
        ok: true,
        moved_main_map: true,
        location: spot.name,
        coordinates: [Number(spot.latitude.toFixed(5)), Number(spot.longitude.toFixed(5))],
        zoom,
        shown_on_screen: wasOnMap ? "The main map has flown there and the spot is marked." : "The Map page is opening, centred there with the spot marked.",
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
  return { output: { error: `unknown tool ${name}` }, effect: {} };
}

function merge(a: AgentEffect, b: AgentEffect): AgentEffect {
  const links = [...(b.listings ? [] : a.links ?? []), ...(b.links ?? [])].filter((x, i, all) => all.findIndex((y) => y.label === x.label) === i);
  return { navigate: b.navigate ?? a.navigate, listings: b.listings ?? a.listings, links: links.length ? links : undefined, image: b.image ?? a.image, map: b.map ?? a.map, sources: a.sources || b.sources ? [...(a.sources ?? []), ...(b.sources ?? [])] : undefined };
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
  "Any question about what is on the map, in this area / the current view / visible ('how many parks here', 'what is this', 'which roads / layers', 'is there a mosque nearby'): call read_map first and answer from it — never say you can't see the map. After focus_map, call read_map if the user also asked what is there.",
].join(" ");

interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}
interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

/** Answer one user turn with the tool-calling agent. Throws when the model can't be reached. */
export async function agentReply(history: { role: "user" | "assistant"; content: string }[], model: string): Promise<AgentReply> {
  const question = [...history].reverse().find((m) => m.role === "user")?.content ?? "";
  const [tools, ctx] = await Promise.all([chatTools(), aiContext(question)]);
  const messages: ChatMessage[] = [{ role: "system", content: (ctx?.system_prompt || systemPrompt()) + `\n${WEB_ONLY}` }, ...history.slice(-12).map((m) => ({ role: m.role, content: m.content }))];
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
      const content = (msg.content ?? "").trim();
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
