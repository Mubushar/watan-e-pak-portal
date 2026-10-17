/**
 * The assistant's "brain" for typed messages and voice notes. With OpenAI connected it
 * is a tool-using agent: the model reads the conversation, calls the same tools as the
 * live voice agent (lib/tools: listing search, details, your listings, drafting a
 * listing) and answers. Without it, the request is understood on-device (lib/intent)
 * and answered from built-in templates.
 *
 * It mirrors the person: replies come in the language of their message (English,
 * Urdu script or Roman Urdu — lib/lang), and spoken replies (voice notes, voice
 * conversation) are phrased to be heard rather than read.
 */
import { create } from "zustand";
import type { Property, PropertyList } from "@/types";
import { get, post } from "./api";
import { draftFromIntent, parseIntent, searchQuery, type Intent, type ListingDraft } from "./intent";
import { city as cityName, describe, detectLang, money, t, type Lang } from "./lang";
import { mergeEffects, runAgentTool, type ToolEffect } from "./tools";
import type { User } from "@/store/auth";

export interface ChatAction {
  label: string;
  /** In-app route to open. */
  to?: string;
  /** Opens the create-listing form pre-filled with this draft. */
  draft?: ListingDraft;
  /** Sends this text as the next user message. */
  say?: string;
  primary?: boolean;
}

/** How a message was sent: typed, as a voice note, or in a live voice conversation. */
export type MsgKind = "text" | "voice-note" | "live";

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  kind?: MsgKind;
  /** Language of the message (drives the reply language and the voice used). */
  lang?: Lang;
  /** Recorded or synthesized audio for voice notes (object or data URL). */
  audioUrl?: string;
  durationMs?: number;
  listings?: Property[];
  actions?: ChatAction[];
  pending?: boolean;
  /** What the agent looked up for this reply (shown to the model on later turns, not to the user). */
  context?: string;
}

interface ChatState {
  messages: ChatMsg[];
  add: (m: ChatMsg) => void;
  update: (id: string, patch: Partial<ChatMsg>) => void;
  clear: () => void;
  /** A listing draft waiting for the user to finish signing in. */
  pendingDraft: ListingDraft | null;
  setPendingDraft: (d: ListingDraft | null) => void;
}

export const useChat = create<ChatState>((set) => ({
  messages: [],
  add: (m) => set((s) => ({ messages: [...s.messages, m] })),
  update: (id, patch) => set((s) => ({ messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) })),
  clear: () => set({ messages: [] }),
  pendingDraft: null,
  setPendingDraft: (pendingDraft) => set({ pendingDraft }),
}));

export const newId = () => Math.random().toString(36).slice(2, 10);

/** The greeting shown before the person says anything (in the app's chosen language). */
export function welcomeFor(user: User | null, lang: Lang): ChatMsg {
  return { id: "welcome", role: "assistant", lang, content: t(lang).welcome(user?.name?.split(" ")[0], user?.role) };
}

export function suggestionsFor(role: string | undefined, lang: Lang): string[] {
  return t(lang).suggestions(role);
}

// ------------------------------------------------------------------ capabilities
let caps: Promise<{ chat_mode: "local" | "upstream"; chat_model: string }> | null = null;
function capabilities() {
  caps ??= get<{ chat_mode: "local" | "upstream"; chat_model: string }>("/ai/capabilities", undefined, { noFallback: true }).catch(() => {
    caps = null;
    return { chat_mode: "local" as const, chat_model: "portal-realestate-rag" };
  });
  return caps;
}

let cityNames: string[] | null = null;
async function knownCities(): Promise<string[]> {
  if (cityNames) return cityNames;
  try {
    const r = await get<{ cities: { name: string }[] }>("/cities");
    cityNames = r.cities.map((c) => c.name);
  } catch {
    cityNames = [];
  }
  return cityNames;
}

interface RagHit {
  type: string;
  id: string;
  title?: string;
  name?: string;
  price?: number;
  city?: string;
  category?: string;
  use_type?: string;
  marla?: number;
  bedrooms?: number;
}

const ragToProperty = (h: RagHit): Property => ({
  id: h.id,
  title: h.title ?? h.name ?? "Listing",
  price: h.price ?? 0,
  category: h.category ?? "house",
  use_type: h.use_type ?? "residential",
  status: "active",
  marla_area: h.marla ?? null,
  bedrooms: h.bedrooms ?? null,
  city_name: h.city,
});

const HELP_RE = /^(hi|hello|hey|salam|assalam|aoa|help|madad|what can you do|who are you|kya kar sakte|السلام|سلام|مدد|آپ کیا)/i;

export interface Reply {
  content: string;
  /** Language the reply is written in. */
  lang: Lang;
  listings?: Property[];
  actions?: ChatAction[];
  context?: string;
}

export interface RespondOptions {
  /** "voice" when the reply will be heard (voice note or voice conversation). */
  mode: "text" | "voice";
  /** Language to use when the message itself gives no clue ("ok", "5 crore"). */
  fallback?: Lang;
  /** The person's chosen reply language (Profile / assistant header); overrides detection. */
  force?: Lang;
}

/** Whether the server has a real AI model for chat (vs. the built-in templates). */
export async function chatMode(): Promise<"local" | "upstream"> {
  return (await capabilities()).chat_mode;
}

/** Produce the assistant's reply to `text` in the person's language, given the conversation so far. */
export async function respond(text: string, history: ChatMsg[], user: User | null, opts: RespondOptions): Promise<Reply> {
  let lang = opts.force ?? detectLang(text, opts.fallback ?? "en");
  // Spoken Urdu sounds right only from Urdu script, so voice replies use it.
  if (lang === "roman" && opts.mode === "voice") lang = "ur";
  const { chat_mode, chat_model } = await capabilities();

  // With OpenAI connected, the model understands the request in context and runs the tools itself.
  if (chat_mode === "upstream") {
    try {
      return await agentReply(text, history, user, lang, opts, chat_model);
    } catch {
      /* fall back to the built-in replies below */
    }
  }

  const cities = await knownCities();
  const intent = withContext(parseIntent(text, cities), history);
  const facts = await gather(intent, text, user, lang);
  if (intent.action === "chat" && HELP_RE.test(text.trim()) && !facts.listings?.length) return { ...facts, content: t(lang).help(user?.name?.split(" ")[0]) };
  // Heard replies can't show cards, so name the best match out loud.
  const top = facts.listings?.[0];
  if (opts.mode === "voice" && top) return { ...facts, content: facts.content + t(lang).bestMatch(top.title, money(top.price, lang)) };
  return facts;
}

// ------------------------------------------------------------------ OpenAI agent (tool calling)

type ToolDef = { type: "function"; function: { name: string; description: string; parameters: unknown } };
let toolDefs: Promise<ToolDef[]> | null = null;
function chatTools(): Promise<ToolDef[]> {
  toolDefs ??= get<{ tools: ToolDef[] }>("/ai/tools", undefined, { noFallback: true })
    .then((r) => r.tools)
    .catch((e) => {
      toolDefs = null;
      throw e;
    });
  return toolDefs;
}

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

const LANGUAGE_RULE: Record<Lang, string> = {
  ur: "Reply in Urdu written in Urdu script.",
  roman: "Reply in Roman Urdu (Urdu written in English letters), the way the user writes.",
  en: "Reply in English.",
};

function agentSystem(user: User | null, lang: Lang, opts: RespondOptions): string {
  return [
    "# Role",
    "You are Arz-e-Pak AI, the friendly real-estate assistant inside the Arz-e-Pak app in Pakistan. You help people find, buy, rent, sell and list property.",
    user ? `You are talking to ${user.name ?? "a member"} (${user.role} account).` : "The user is a guest (not signed in).",
    "",
    "# Language",
    opts.force ? `${LANGUAGE_RULE[lang]} Always, whatever language the user writes in.` : `${LANGUAGE_RULE[lang]} Match the language of the user's latest message.`,
    "",
    "# Style",
    opts.mode === "voice"
      ? "Your reply is played as audio (a voice note): 1-3 short natural sentences, no markdown, lists, emojis or links."
      : "Keep replies short (under 100 words), warm and practical. Short bullet points only when comparing options.",
    "Say prices in crore/lakh and sizes in marla/kanal (1 kanal = 20 marla). Never read out ids.",
    "",
    "# Tools",
    "- You search yourself with search_listings — never ask the user to press a search button, and never mention buttons except ones a tool result says are on screen ('See all', 'Create listing', 'Sign in').",
    "- Follow-ups refine the previous search: keep the earlier city, type and budget unless the user changes them. The app appends notes like [context: ...] to your earlier replies so you know what was searched; never write such notes yourself.",
    "- If a search finds nothing, relax one filter and search again, then say what you changed.",
    "- Mention the best 1-3 results (name, size, price); they also appear as cards under your reply. Never invent listings.",
    "- When the user wants to sell or rent out a property, ask briefly for missing essentials (type, city, size, price), then call draft_listing.",
    "- For their own listings call my_listings; if it says not_signed_in, ask them to sign in with a one-time code.",
  ].join("\n");
}

async function agentReply(text: string, history: ChatMsg[], user: User | null, lang: Lang, opts: RespondOptions, model: string): Promise<Reply> {
  const tools = await chatTools();
  const messages: ChatMessage[] = [
    { role: "system", content: agentSystem(user, lang, opts) },
    ...history
      .filter((m) => !m.pending && m.id !== "welcome" && m.content)
      .slice(-12)
      .map((m): ChatMessage => ({ role: m.role, content: m.context ? `${m.content}\n\n[context: ${m.context}]` : m.content })),
    { role: "user", content: text },
  ];
  let effect: ToolEffect = {};
  const notes: string[] = [];
  for (let round = 0; round < 4; round++) {
    const r = await post<{ choices: { message: ChatMessage }[] }>(
      "/v1/chat/completions",
      // gpt-5.x models only accept function tools in Chat Completions with reasoning off.
      { model, messages, tools, tool_choice: round === 3 ? "none" : "auto", reasoning_effort: "none" },
      { timeoutMs: 90_000 },
    );
    const msg = r.choices?.[0]?.message;
    if (!msg) throw new Error("empty reply");
    if (!msg.tool_calls?.length) {
      // Drop any [context: …] note the model copied from earlier turns.
      const content = (msg.content ?? "").replace(/\s*\[context:[^\]]*\]/gi, "").trim();
      if (!content) throw new Error("empty reply");
      return { lang, content, listings: effect.listings, actions: effect.actions, context: notes.join(" | ") || undefined };
    }
    messages.push({ role: "assistant", content: msg.content ?? null, tool_calls: msg.tool_calls });
    for (const call of msg.tool_calls) {
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(call.function.arguments || "{}");
      } catch {
        /* keep {} */
      }
      let output: unknown;
      try {
        const run = await runAgentTool(call.function.name, args, lang);
        effect = mergeEffects(effect, run.effect);
        output = run.output;
      } catch (e) {
        output = { error: (e as Error).message };
      }
      notes.push(summarizeCall(call.function.name, args, output));
      messages.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(output ?? {}) });
    }
  }
  throw new Error("too many tool rounds");
}

/** One-line memory of a tool call, e.g. `search_listings {"city":"Rawalpindi",...} → 1 result: Rawalpindi 7 Marla House (PKR 2.8 Crore)`. */
function summarizeCall(name: string, args: Record<string, unknown>, output: unknown): string {
  const out = output as { count?: number; results?: { title: string; price: string }[]; error?: string };
  const found = out?.error ? `error ${out.error}` : out?.results ? `${out.count ?? out.results.length} result(s)${out.results.length ? ": " + out.results.slice(0, 3).map((x) => `${x.title} (${x.price})`).join("; ") : ""}` : "done";
  return `${name} ${JSON.stringify(args)} → ${found}`;
}

/**
 * Follow-ups refine the previous search: after "plots in Islamabad", "10 marla" means
 * 10-marla plots in Islamabad, and "under 2 crore" keeps the city and type.
 */
let lastSearch: Intent | null = null;

function withContext(intent: Intent, history: ChatMsg[]): Intent {
  if (!history.some((m) => m.role === "user")) lastSearch = null; // new conversation
  if (intent.action !== "search") return intent;
  const prev = lastSearch;
  lastSearch = prev ? merge(intent, prev) : intent;
  return lastSearch;
}

function merge(intent: Intent, prev: Intent): Intent {
  const merged: Intent = { ...intent };
  merged.city ??= prev.city;
  merged.area_hint ??= intent.city ? undefined : prev.area_hint;
  merged.category ??= prev.category;
  merged.use_type ??= prev.use_type;
  merged.purpose ??= prev.purpose;
  // Size, rooms and budget only carry over while the property type stays the same.
  if (merged.category === prev.category) {
    merged.marla ??= prev.marla;
    merged.bedrooms ??= prev.bedrooms;
    if (!intent.min_price && !intent.max_price) {
      merged.min_price = prev.min_price;
      merged.max_price = prev.max_price;
    }
  }
  return merged;
}

async function gather(intent: Intent, text: string, user: User | null, lang: Lang): Promise<Reply> {
  const tr = t(lang);
  switch (intent.action) {
    case "search":
      return searchReply(intent, lang);
    case "sell": {
      const draft = draftFromIntent(intent, text);
      const missing = [!intent.city && tr.missingCity, !intent.marla && tr.missingSize, !(intent.price ?? intent.max_price) && tr.missingPrice].filter(Boolean) as string[];
      const what = describe({ ...intent, action: "sell", min_price: undefined, max_price: undefined }, lang);
      const summary = [what, draft.price ? `— ${money(draft.price, lang)}` : ""].filter(Boolean).join(" ");
      return {
        lang,
        content: tr.drafted(summary, missing, !!user),
        actions: [{ label: tr.createListing, draft, primary: true }, user ? { label: tr.myListings, to: "/listings" } : { label: tr.signIn, to: "/signin?next=/listings/new" }],
      };
    }
    case "my_listings": {
      if (!user)
        return {
          lang,
          content: tr.listingsNeedSignIn,
          actions: [
            { label: tr.signIn, to: "/signin?next=/listings", primary: true },
            { label: tr.createAccount, to: "/signup" },
          ],
        };
      try {
        const r = await get<PropertyList>("/me/listings", undefined, { noFallback: true });
        const active = r.results.filter((p) => p.status === "active");
        return {
          lang,
          content: r.count ? tr.listingsCount(r.count, active.length, money(active.reduce((s, p) => s + p.price, 0), lang)) : tr.listingsNone,
          listings: r.results.slice(0, 5),
          actions: [
            { label: tr.manageListings, to: "/listings", primary: true },
            { label: tr.addListing, to: "/listings/new" },
          ],
        };
      } catch (e) {
        return { lang, content: (e as Error).message };
      }
    }
    case "signin":
      return user
        ? { lang, content: tr.signedInAs(user.name ?? user.email ?? user.mobile ?? ""), actions: [{ label: tr.profile, to: "/profile", primary: true }] }
        : {
            lang,
            content: tr.signInHelp,
            actions: [
              { label: tr.createAccount, to: "/signup", primary: true },
              { label: tr.signIn, to: "/signin" },
            ],
          };
    default: {
      try {
        const r = await get<{ results: RagHit[] }>("/rag/search", { query: text, top_k: 6 }, { noFallback: true });
        const listings = r.results.filter((h) => h.type === "property").map(ragToProperty);
        const places = r.results.filter((h) => h.type !== "property").map((h) => h.name ?? h.title ?? "");
        return {
          lang,
          content: listings.length ? tr.ragMatches(places) : places.length ? tr.ragPlaces(places) : tr.ragNone,
          listings,
          actions: listings.length ? [{ label: tr.openExplore, to: "/explore" }] : undefined,
        };
      } catch (e) {
        return { lang, content: (e as Error).message };
      }
    }
  }
}

async function searchReply(intent: Intent, lang: Lang): Promise<Reply> {
  const tr = t(lang);
  const q = searchQuery(intent);
  const label = describe(intent, lang);
  const explore = `/explore?${new URLSearchParams(Object.entries({ city: intent.city, category: intent.category, use_type: intent.use_type, bedrooms: intent.bedrooms, min_price: intent.min_price, max_price: intent.max_price }).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString()}`;
  try {
    let r = await get<PropertyList>("/search", { ...q, limit: 6 });
    let relaxed = false;
    if (!r.count && (intent.max_price || intent.min_price || intent.marla || intent.bedrooms)) {
      r = await get<PropertyList>("/search", { city: intent.city, category: intent.category, use_type: intent.use_type, limit: 6 });
      relaxed = true;
    }
    return {
      lang,
      content: !r.count ? tr.none(label) : relaxed ? tr.relaxed(label, cityName(intent.city, lang)) : tr.found(r.count, label) + (intent.purpose === "invest" ? tr.investHint : ""),
      listings: r.results,
      actions: r.count ? [{ label: tr.seeAll(r.count), to: explore, primary: true }] : [{ label: tr.browseAll, to: "/explore" }],
    };
  } catch (e) {
    return { lang, content: (e as Error).message };
  }
}
