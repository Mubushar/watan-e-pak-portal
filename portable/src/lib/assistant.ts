/**
 * The assistant's "brain": understands the request on-device (lib/intent), fetches
 * real data from the portal (search, RAG, the user's own listings), and phrases the
 * reply — with the backend LLM when one is configured (PORTAL_LLM_BASE_URL), or from
 * templates when the backend runs its built-in RAG fallback.
 */
import { create } from "zustand";
import type { Property, PropertyList } from "@/types";
import { get, post } from "./api";
import { pkrShort } from "./format";
import { describeIntent, draftFromIntent, parseIntent, searchQuery, type Intent, type ListingDraft } from "./intent";
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

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  listings?: Property[];
  actions?: ChatAction[];
  pending?: boolean;
  voice?: boolean;
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

export function welcomeFor(user: User | null): ChatMsg {
  const name = user?.name?.split(" ")[0];
  const role = user?.role;
  const line =
    role === "seller" || role === "landlord"
      ? "Tell me about the property you want to sell or rent out and I’ll draft the listing for you."
      : role === "agent"
        ? "I can draft listings for your clients, find matching properties and price-check deals."
        : role === "investor"
          ? "Ask me for investment picks, price trends or yields in any city."
          : "Tell me what you’re looking for — city, budget, size or purpose — and I’ll search live listings for you.";
  return {
    id: "welcome",
    role: "assistant",
    content: `Assalam-o-Alaikum${name ? ` ${name}` : ""}! I’m **Arz-e-Pak AI**. ${line}\n\nTap the mic to talk, or type below — English or Urdu.`,
  };
}

export function suggestionsFor(role?: string): string[] {
  switch (role) {
    case "seller":
    case "landlord":
      return ["I want to sell my 10 marla house in Lahore for 4.5 crore", "What’s my 5 marla plot in Islamabad worth?", "Show my listings", "How do I sell faster?"];
    case "agent":
      return ["List a 1 kanal house in DHA Lahore for 9.5 crore", "3 bed apartments in Karachi under 2 crore", "Show my listings", "Commercial shops in Lahore"];
    case "investor":
      return ["Best investment plots in Islamabad", "Commercial property in Lahore under 10 crore", "Featured listings", "Which city has the best returns?"];
    default:
      return ["10 marla house in Lahore under 5 crore", "Apartments in Karachi", "Plots in Islamabad", "I want to sell my house"];
  }
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

const HELP_RE = /^(hi|hello|hey|salam|assalam|aoa|help|what can you do|who are you|kya kar sakte)/i;

export interface Reply {
  content: string;
  listings?: Property[];
  actions?: ChatAction[];
}

/** Produce the assistant's reply to `text`, given the conversation so far. */
export async function respond(text: string, history: ChatMsg[], user: User | null, voiceLang: string): Promise<Reply> {
  const intent = parseIntent(text, await knownCities());
  const { chat_mode, chat_model } = await capabilities();
  const facts = await gather(intent, text, user);

  // Template replies are clearer than the RAG fallback for actions and greetings.
  if (chat_mode === "local" || intent.action === "my_listings" || intent.action === "signin") {
    if (intent.action === "chat" && HELP_RE.test(text.trim()) && !facts.listings?.length) return { ...facts, content: helpText(user) };
    return facts;
  }

  // Upstream LLM: let it phrase the answer, grounded on what we found.
  const context = facts.listings?.length
    ? `Listings found in the Arz-e-Pak database (shown to the user as cards below your reply):\n${facts.listings
        .slice(0, 6)
        .map((p) => `- ${p.title} — ${pkrShort(p.price)}, ${p.category}, ${p.city_name ?? ""}${p.bedrooms ? `, ${p.bedrooms} bed` : ""}`)
        .join("\n")}`
    : "No matching listings were found in the database for this message.";
  const system = [
    "You are Arz-e-Pak AI, the friendly assistant inside the Arz-e-Pak real-estate app for Pakistan.",
    `The user is ${user ? `${user.name ?? "a member"} (${user.role} account)` : "a guest (not signed in)"}.`,
    "Keep replies under 120 words, warm and practical. Quote prices in PKR crore/lakh. Use short bullet points only when listing options.",
    voiceLang.startsWith("ur") ? "Reply in Urdu script." : "Reply in the language the user writes in (English, Urdu or Roman Urdu).",
    "The app can search listings, open details, draft a listing from a description, and manage the user's own listings — buttons for these appear under your reply, so refer to them instead of inventing links.",
    intent.action === "sell" ? "The user wants to list a property; a draft has been prepared — encourage them to tap 'Create listing' and mention any missing details (size, price, location, photos)." : "",
    context,
  ]
    .filter(Boolean)
    .join("\n");
  try {
    const r = await post<{ choices: { message: { content: string } }[] }>(
      "/v1/chat/completions",
      {
        model: chat_model,
        messages: [
          { role: "system", content: system },
          ...history
            .filter((m) => !m.pending && m.id !== "welcome")
            .slice(-8)
            .map((m) => ({ role: m.role, content: m.content })),
          { role: "user", content: text },
        ],
      },
      { timeoutMs: 60_000 },
    );
    const content = r.choices?.[0]?.message?.content?.trim();
    return { ...facts, content: content || facts.content };
  } catch {
    return facts;
  }
}

async function gather(intent: Intent, text: string, user: User | null): Promise<Reply> {
  switch (intent.action) {
    case "search":
      return searchReply(intent);
    case "sell": {
      const draft = draftFromIntent(intent, text);
      const missing = [!intent.city && "city", !intent.marla && "size", !(intent.price ?? intent.max_price) && "asking price"].filter(Boolean) as string[];
      const summary = [draft.title, draft.price ? `at ${pkrShort(draft.price)}` : ""].filter(Boolean).join(" ");
      return {
        content: `Great — I’ve drafted a listing${summary ? ` for **${summary}**` : ""}. ${missing.length ? `I still need the ${missing.join(", ")} — you can add ${missing.length > 1 ? "them" : "it"} on the form. ` : ""}Tap **Create listing** to add photos and publish.${user ? "" : " You’ll need to sign in first — it only takes a one-time code."}`,
        actions: [{ label: "Create listing", draft, primary: true }, ...(user ? [{ label: "My listings", to: "/listings" }] : [{ label: "Sign in", to: "/signin?next=/listings/new" }])],
      };
    }
    case "my_listings": {
      if (!user)
        return {
          content: "Sign in to see and manage your listings — I’ll send you a one-time code, no password needed.",
          actions: [
            { label: "Sign in", to: "/signin?next=/listings", primary: true },
            { label: "Create account", to: "/signup" },
          ],
        };
      try {
        const r = await get<PropertyList>("/me/listings", undefined, { noFallback: true });
        const active = r.results.filter((p) => p.status === "active");
        return {
          content: r.count
            ? `You have **${r.count}** listing${r.count === 1 ? "" : "s"} (${active.length} active, worth ${pkrShort(active.reduce((s, p) => s + p.price, 0))}).`
            : "You haven’t listed anything yet. Tell me about your property — e.g. “10 marla house in Lahore for 4 crore” — and I’ll draft it.",
          listings: r.results.slice(0, 5),
          actions: [
            { label: "Manage listings", to: "/listings", primary: true },
            { label: "Add a listing", to: "/listings/new" },
          ],
        };
      } catch (e) {
        return { content: (e as Error).message };
      }
    }
    case "signin":
      return user
        ? { content: `You’re signed in as **${user.name ?? user.email ?? user.mobile}**.`, actions: [{ label: "Profile", to: "/profile", primary: true }] }
        : {
            content: "You can sign up or sign in with just your mobile number or e-mail — I’ll send a 6-digit code.",
            actions: [
              { label: "Create account", to: "/signup", primary: true },
              { label: "Sign in", to: "/signin" },
            ],
          };
    default: {
      try {
        const r = await get<{ results: RagHit[] }>("/rag/search", { query: text, top_k: 6 }, { noFallback: true });
        const listings = r.results.filter((h) => h.type === "property").map(ragToProperty);
        const places = r.results.filter((h) => h.type !== "property").map((h) => h.name ?? h.title);
        return {
          content: listings.length
            ? `Here are the closest matches I found${places.length ? ` (related: ${places.slice(0, 3).join(", ")})` : ""}:`
            : places.length
              ? `I found these related places: **${places.slice(0, 4).join(", ")}**. Tell me a budget or property type and I’ll find listings there.`
              : "I couldn’t find a match for that. Try a city (Lahore, Karachi, Islamabad), a type (house, plot, apartment, shop) and a budget.",
          listings,
          actions: listings.length ? [{ label: "Open Explore", to: "/explore" }] : undefined,
        };
      } catch (e) {
        return { content: (e as Error).message };
      }
    }
  }
}

async function searchReply(intent: Intent): Promise<Reply> {
  const q = searchQuery(intent);
  const label = describeIntent(intent, (n) => pkrShort(n));
  const explore = `/explore?${new URLSearchParams(Object.entries({ city: intent.city, category: intent.category, use_type: intent.use_type, bedrooms: intent.bedrooms, min_price: intent.min_price, max_price: intent.max_price }).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString()}`;
  try {
    let r = await get<PropertyList>("/search", { ...q, limit: 6 });
    let relaxed = false;
    if (!r.count && (intent.max_price || intent.min_price || intent.marla || intent.bedrooms)) {
      r = await get<PropertyList>("/search", { city: intent.city, category: intent.category, use_type: intent.use_type, limit: 6 });
      relaxed = true;
    }
    const invest = intent.purpose === "invest" ? " For investment, look at featured and newly launched schemes — ask me about returns in any city." : "";
    return {
      content: !r.count
        ? `I couldn’t find any listings for **${label || "that"}** yet. Try another city, type or budget.`
        : relaxed
          ? `Nothing matched **${label}** exactly, so here are the closest ${r.count === 1 ? "option" : "options"}${intent.city ? ` in ${intent.city}` : ""}:`
          : `I found **${r.count}** ${r.count === 1 ? "listing" : "listings"} for **${label}**.${invest}`,
      listings: r.results,
      actions: r.count ? [{ label: `See all ${r.count}`, to: explore, primary: true }] : [{ label: "Browse all listings", to: "/explore" }],
    };
  } catch (e) {
    return { content: (e as Error).message };
  }
}

function helpText(user: User | null): string {
  return [
    `Here’s what I can do${user?.name ? `, ${user.name.split(" ")[0]}` : ""}:`,
    "- **Find property** — “3 bed house in Lahore under 5 crore”",
    "- **List your property** — “I want to sell my 1 kanal plot in DHA Islamabad for 3.5 crore”",
    "- **Your listings** — “Show my listings”",
    "- **Ask anything** — areas, schemes, prices and buying tips",
    "",
    "You can talk to me in English or Urdu — tap the mic.",
  ].join("\n");
}
