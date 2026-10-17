/**
 * The assistant's tools, run by the app against our REST API with the user's own
 * session. Shared by the live voice agent (lib/realtime) and the text / voice-note
 * chat (lib/assistant), so every mode can really search and act — the model never has
 * to ask the person to press a button. Definitions live on the backend
 * (openai_voice.REALTIME_TOOLS, served at GET /ai/tools).
 */
import type { Property, PropertyList } from "@/types";
import { get } from "./api";
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
  status: p.status,
});

const SEARCH_KEYS = ["city", "category", "use_type", "min_price", "max_price", "bedrooms", "min_marla", "max_marla", "featured"];

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
    const p = await get<Property>(`/properties/${String(args.id ?? "")}`);
    return {
      output: { ...brief(p), description: p.description, bathrooms: p.bathrooms, location: [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", ") },
      effect: { listings: [p] },
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
  // A newer search replaces the older search's "See all" / "Browse" buttons.
  const isSearch = (x: ChatAction) => !!x.to?.startsWith("/explore");
  const keep = b.listings ? (a.actions ?? []).filter((x) => !isSearch(x)) : a.actions ?? [];
  const actions = [...keep, ...(b.actions ?? [])].filter((x, i, all) => all.findIndex((y) => y.label === x.label) === i);
  return { listings: b.listings ?? a.listings, actions: actions.length ? actions : undefined };
}
