/**
 * The assistant's tools, run by the app against our REST API with the user's own
 * session. Shared by the live voice agent (lib/realtime) and the text / voice-note
 * chat (lib/assistant), so every mode can really search and act — the model never has
 * to ask the person to press a button. Definitions live on the backend
 * (openai_voice.REALTIME_TOOLS, served at GET /ai/tools).
 */
import type { ChatImage, MapView, NearbyList, NearbyPlace, Property, PropertyList } from "@/types";
import { apiBase, get, post } from "./api";
import type { ListingDraft } from "./intent";
import { money, t, type Lang } from "./lang";
import { useAuth } from "@/store/auth";
import type { ChatAction } from "./assistant";

/** What a tool call adds to the chat: listing cards and/or buttons. */
export interface ToolEffect {
  listings?: Property[];
  actions?: ChatAction[];
  /** A map card (show_map). */
  map?: MapView;
  /** An image card (show_plan). */
  image?: ChatImage;
}

export interface ToolRun {
  /** Sent back to the model (compact JSON). */
  output: unknown;
  effect: ToolEffect;
}

/** A compact listing for the model to talk about (ids for follow-ups, no long fields). */
const brief = (p: Property) => ({
  id: p.id,
  title: p.title,
  price: money(p.price, "en"),
  price_rupees: p.price,
  city: p.city_name,
  category: p.category,
  size_marla: p.marla_area ?? undefined,
  bedrooms: p.bedrooms ?? undefined,
  bathrooms: p.bathrooms ?? undefined,
  distance_km: (p as Property & { distance_km?: number }).distance_km,
  features: p.amenities?.length ? p.amenities : undefined,
  nearby: p.nearby ? `${p.nearby.name} (${p.nearby.kind}), ${p.nearby.distance_km} km` : undefined,
  status: p.status,
});

/** "Faisal Mosque (Mosque), 0.4 km, ~5 min walk" for the model. */
const nearbyLine = (n: NearbyPlace) => `${n.name} (${n.kind}), ${n.distance_km} km, ~${n.walk_minutes} min walk`;

const SEARCH_KEYS = ["city", "category", "use_type", "min_price", "max_price", "bedrooms", "min_bathrooms", "min_marla", "max_marla", "featured", "feature", "near", "near_km", "near_place"];

const PLACE_KEYS = ["kind", "area", "near", "radius_km", "name"];
const pick = (args: Record<string, unknown>, keys: string[]) =>
  Object.fromEntries(Object.entries(args).filter(([k, v]) => keys.includes(k) && v !== undefined && v !== null && v !== "")) as Record<string, string | number>;

/** "Open listing" (+ "Request a call" while it's for sale/rent) under a listing's card. */
function listingButtons(p: Property, lang: Lang): ChatAction[] {
  const tr = t(lang);
  const open: ChatAction = { label: tr.openListing, to: `/property/${p.id}`, primary: true };
  return p.status === "active" ? [open, { label: tr.requestCall, to: `/property/${p.id}?enquire=1` }] : [open];
}

export async function runAgentTool(name: string, args: Record<string, unknown>, lang: Lang): Promise<ToolRun> {
  const tr = t(lang);
  if (name === "search_listings") {
    const query = pick(args, SEARCH_KEYS);
    const r = await get<PropertyList & { near_place?: unknown; nearest_outside_radius?: Property[]; note?: string }>("/search", { ...query, limit: 6 });
    const { near_place: _np, ...browse } = query;
    const q = new URLSearchParams(Object.entries(browse).map(([k, v]) => [k, String(v)]));
    const nearest = r.nearest_outside_radius ?? [];
    return {
      output: {
        count: r.count,
        results: r.results.map(brief),
        searched_with: query,
        ...(r.near_place ? { near_place: r.near_place } : {}),
        ...(nearest.length ? { nearest_outside_radius: nearest.map(brief) } : {}),
        ...(r.note ? { note: r.note } : {}),
      },
      effect: {
        listings: r.results.length ? r.results : nearest.length ? nearest : r.results,
        actions: r.count ? [{ label: tr.seeAll(r.count), to: `/explore?${q}`, primary: true }] : [{ label: tr.browseAll, to: "/explore" }],
      },
    };
  }
  if (name === "find_places") {
    const r = await get<Record<string, unknown>>("/places/find", { ...pick(args, PLACE_KEYS), limit: 15 });
    return { output: r, effect: {} };
  }
  if (name === "area_info") {
    const r = await get<Record<string, unknown>>("/areas/profile", { area: String(args.area ?? "") });
    return { output: r, effect: {} };
  }
  if (name === "show_map") {
    const kinds = Array.isArray(args.kinds) ? (args.kinds as string[]).join(",") : undefined;
    const view = await get<MapView>("/places/map", {
      listing_id: args.listing_id ? String(args.listing_id) : undefined,
      place: !args.listing_id && args.place ? String(args.place) : undefined,
      kinds,
      radius_km: typeof args.radius_km === "number" ? args.radius_km : undefined,
    });
    const shown = view.markers.map((m) => `${m.name} (${m.kind}, ${m.distance_km} km)`);
    return {
      output: { ok: true, shown_on_screen: `A map of ${view.focus.name} with ${view.markers.length} nearby places marked.`, radius_km: view.radius_km, marked: shown },
      effect: { map: view },
    };
  }
  if (name === "master_plan") {
    const action = String(args.action ?? "summary");
    const s = (k: string) => (args[k] ? String(args[k]) : undefined);
    const r =
      action === "search"
        ? await get<Record<string, unknown>>("/masterplans/search", { q: s("query") ?? s("place") ?? "", plan: s("plan"), category: s("category"), limit: 15 })
        : action === "at"
          ? await get<Record<string, unknown>>("/masterplans/at", { place: s("place"), listing_id: s("listing_id"), plan: s("plan"), radius_m: typeof args.radius_m === "number" ? args.radius_m : undefined })
          : await get<Record<string, unknown>>(`/masterplans/${encodeURIComponent(s("plan") ?? "")}`);
    return { output: r, effect: {} };
  }
  if (name === "show_plan") {
    const v = await get<{ plan: string; location: string; snapshot_url: string; map: MapView; on_the_plan: unknown; accuracy: unknown }>("/masterplans/view", {
      plan: args.plan ? String(args.plan) : undefined,
      place: args.place ? String(args.place) : undefined,
      listing_id: args.listing_id ? String(args.listing_id) : undefined,
      radius_m: typeof args.radius_m === "number" ? args.radius_m : undefined,
    });
    return {
      output: { ok: true, shown_on_screen: `A close-up of the ${v.plan} master plan around ${v.location}, and a map with the plan overlaid.`, on_the_plan: v.on_the_plan, accuracy: v.accuracy },
      effect: { image: { url: `${apiBase()}${v.snapshot_url}`, caption: `${v.plan} master plan — ${v.location}` }, map: v.map },
    };
  }
  if (name === "web_lookup") {
    const r = await post<{ answer: string; sources: { site: string; url: string }[] }>("/ai/web-lookup", { question: String(args.question ?? "") }, { timeoutMs: 90_000 });
    return { output: { answer: r.answer, sources: r.sources.map((x) => x.site) }, effect: {} };
  }
  if (name === "get_listing") {
    const id = String(args.id ?? "");
    const [p, near] = await Promise.all([
      get<Property>(`/properties/${id}`),
      get<NearbyList>(`/properties/${id}/nearby`).catch(() => null),
    ]);
    return {
      output: {
        ...brief(p),
        description: p.description,
        nearby_places: near?.nearby.map(nearbyLine) ?? [],
        location: [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", "),
        shown_on_screen: `This listing's card with '${tr.openListing}' and '${tr.requestCall}' buttons (say the button names exactly like this).`,
      },
      effect: { listings: [p], actions: listingButtons(p, lang) },
    };
  }
  if (name === "request_call") {
    const p = await get<Property>(`/properties/${String(args.listing_id ?? args.id ?? "")}`);
    if (p.status !== "active") return { output: { ok: false, error: `listing is ${p.status}` }, effect: { listings: [p], actions: listingButtons(p, lang) } };
    const user = useAuth.getState().user;
    if (!user || (!user.mobile && !user.email)) {
      return {
        output: { ok: false, error: "not_signed_in", shown_on_screen: `A '${tr.requestCall}' button for this listing (say the button name exactly like this).` },
        effect: { listings: [p], actions: [{ label: tr.requestCall, to: `/property/${p.id}?enquire=1`, primary: true }, { label: tr.signIn, to: `/signin?next=/property/${p.id}` }] },
      };
    }
    const when = typeof args.preferred_time === "string" && args.preferred_time.trim() ? `\nPreferred time: ${args.preferred_time.trim()}` : "";
    const note = typeof args.message === "string" && args.message.trim() ? `\n${args.message.trim()}` : "";
    await post("/crm/leads", {
      name: user.name || user.mobile || user.email,
      phone: user.mobile ?? undefined,
      email: user.email ?? undefined,
      source: "mobile_app_ai",
      interest_use_type: p.use_type,
      interest_category: p.category,
      budget_max: p.price,
      city_id: p.city_id ?? undefined,
      scheme_id: p.scheme_id ?? undefined,
      assigned_agent_id: p.agent_id || undefined,
      notes: `Call request from the Watan-e-Pak AI assistant.${when}${note}\n\nListing: ${p.title} (${p.id})`,
    });
    return {
      output: { ok: true, sent_to: "the owner / agent of this listing", they_will_contact: user.mobile ? "by phone" : "by e-mail" },
      effect: { listings: [p], actions: [{ label: tr.openListing, to: `/property/${p.id}`, primary: true }] },
    };
  }
  if (name === "my_listings") {
    if (!useAuth.getState().token) {
      return { output: { error: "not_signed_in" }, effect: { actions: [{ label: tr.signIn, to: "/signin?next=/listings", primary: true }] } };
    }
    const r = await get<PropertyList>("/me/listings", undefined, { noFallback: true });
    return {
      output: { count: r.count, results: r.results.slice(0, 10).map(brief) },
      effect: { listings: r.results.slice(0, 5), actions: [{ label: tr.manageListings, to: "/listings" }] },
    };
  }
  if (name === "draft_listing") {
    const d = args as Record<string, string | number | undefined>;
    const draft: ListingDraft = {
      title: d.title as string | undefined,
      description: d.description as string | undefined,
      category: d.category as string | undefined,
      use_type: d.use_type as string | undefined,
      city: d.city as string | undefined,
      marla: d.marla as number | undefined,
      bedrooms: d.bedrooms as number | undefined,
      bathrooms: d.bathrooms as number | undefined,
      price: d.price as number | undefined,
    };
    return {
      output: { ok: true, shown_on_screen: "A 'Create listing' button with these details is now shown under your reply.", signed_in: !!useAuth.getState().token },
      effect: { actions: [{ label: tr.createListing, draft, primary: true }] },
    };
  }
  if (name === "knowledge_search") {
    const r = await post<{ context: string }>("/ai/knowledge/search", {
      query: String(args.query ?? ""),
      types: Array.isArray(args.types) ? args.types : undefined,
      k: 5,
    });
    return { output: { results: r.context || "nothing found in the portal's knowledge base", note: "name the source in words, no [n] markers" }, effect: {} };
  }
  if (name === "remember") {
    if (!useAuth.getState().token) return { output: { ok: false, reason: "not_signed_in" }, effect: {} };
    return { output: await post("/me/memory", { text: String(args.note ?? "") }), effect: {} };
  }
  return { output: { error: `unknown tool ${name}` }, effect: {} };
}

/** Merge effects from several tool calls in one reply (latest listings win, buttons add up). */
export function mergeEffects(a: ToolEffect, b: ToolEffect): ToolEffect {
  // New cards replace the older cards' buttons ("See all", "Open listing", ...).
  const belongsToCards = (x: ChatAction) => !!x.to && /^\/(explore|property\/|signin\?next=\/property)/.test(x.to);
  const keep = b.listings ? (a.actions ?? []).filter((x) => !belongsToCards(x)) : a.actions ?? [];
  const actions = [...keep, ...(b.actions ?? [])].filter((x, i, all) => all.findIndex((y) => y.label === x.label) === i);
  return { listings: b.listings ?? a.listings, actions: actions.length ? actions : undefined, map: b.map ?? a.map, image: b.image ?? a.image };
}
