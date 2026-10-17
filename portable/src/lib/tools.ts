/**
 * The assistant's tools, run by the app against our REST API with the user's own
 * session. Shared by the live voice agent (lib/realtime) and the text / voice-note
 * chat (lib/assistant), so every mode can really search and act — the model never has
 * to ask the person to press a button. Definitions live on the backend
 * (openai_voice.REALTIME_TOOLS, served at GET /ai/tools).
 */
import type { NearbyList, NearbyPlace, Property, PropertyList } from "@/types";
import { get, post } from "./api";
import type { ListingDraft } from "./intent";
import { money, t, type Lang } from "./lang";
import { useAuth } from "@/store/auth";
import type { ChatAction } from "./assistant";

/** What a tool call adds to the chat: listing cards and/or buttons. */
export interface ToolEffect {
  listings?: Property[];
  actions?: ChatAction[];
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
  features: p.amenities?.length ? p.amenities : undefined,
  nearby: p.nearby ? `${p.nearby.name} (${p.nearby.kind}), ${p.nearby.distance_km} km` : undefined,
  status: p.status,
});

/** "Faisal Mosque (Mosque), 0.4 km, ~5 min walk" for the model. */
const nearbyLine = (n: NearbyPlace) => `${n.name} (${n.kind}), ${n.distance_km} km, ~${n.walk_minutes} min walk`;

const SEARCH_KEYS = ["city", "category", "use_type", "min_price", "max_price", "bedrooms", "min_bathrooms", "min_marla", "max_marla", "featured", "feature", "near", "near_km"];

/** "Open listing" (+ "Request a call" while it's for sale/rent) under a listing's card. */
function listingButtons(p: Property, lang: Lang): ChatAction[] {
  const tr = t(lang);
  const open: ChatAction = { label: tr.openListing, to: `/property/${p.id}`, primary: true };
  return p.status === "active" ? [open, { label: tr.requestCall, to: `/property/${p.id}?enquire=1` }] : [open];
}

export async function runAgentTool(name: string, args: Record<string, unknown>, lang: Lang): Promise<ToolRun> {
  const tr = t(lang);
  if (name === "search_listings") {
    const query = Object.fromEntries(Object.entries(args).filter(([k, v]) => SEARCH_KEYS.includes(k) && v !== undefined && v !== null && v !== "")) as Record<string, string | number | boolean>;
    const r = await get<PropertyList>("/search", { ...query, limit: 6 });
    const q = new URLSearchParams(Object.entries(query).map(([k, v]) => [k, String(v)]));
    return {
      output: { count: r.count, results: r.results.map(brief), searched_with: query },
      effect: { listings: r.results, actions: r.count ? [{ label: tr.seeAll(r.count), to: `/explore?${q}`, primary: true }] : [{ label: tr.browseAll, to: "/explore" }] },
    };
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
      notes: `Call request from the Arz-e-Pak AI assistant.${when}${note}\n\nListing: ${p.title} (${p.id})`,
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
  return { output: { error: `unknown tool ${name}` }, effect: {} };
}

/** Merge effects from several tool calls in one reply (latest listings win, buttons add up). */
export function mergeEffects(a: ToolEffect, b: ToolEffect): ToolEffect {
  // New cards replace the older cards' buttons ("See all", "Open listing", ...).
  const belongsToCards = (x: ChatAction) => !!x.to && /^\/(explore|property\/|signin\?next=\/property)/.test(x.to);
  const keep = b.listings ? (a.actions ?? []).filter((x) => !belongsToCards(x)) : a.actions ?? [];
  const actions = [...keep, ...(b.actions ?? [])].filter((x, i, all) => all.findIndex((y) => y.label === x.label) === i);
  return { listings: b.listings ?? a.listings, actions: actions.length ? actions : undefined };
}
