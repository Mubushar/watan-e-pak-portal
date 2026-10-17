/**
 * Conversational property assistant.
 *
 * With OpenAI connected on the backend (GET /ai/capabilities → "upstream"), each turn
 * runs the tool-calling agent (lib/agent): the model searches listings, opens details,
 * looks up places, master plans and the web itself, and its results appear as cards.
 * Otherwise (or if that fails) a turn fans out to:
 *   - POST /v1/chat/completions  (the facade's local RAG answer)
 *   - GET  /rag/search            (structured matches rendered as listing cards)
 * Either way it offers a one-click hand-off to the Conversational Homebuying agent.
 */
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { CircleMarker, Marker, Tooltip } from "react-leaflet";
import { Bot, Calculator, Map as MapIcon, Send, Sparkles, User as UserIcon, Wand2 } from "lucide-react";
import type { Property } from "@/types";
import { agentReply, capabilities, type AgentEffect } from "@/lib/agent";
import { get, post } from "@/lib/api";
import { pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PropertyRow } from "@/components/property/PropertyCard";
import { PortalMap, pin } from "@/components/map/PortalMap";
import { Markdown } from "./Markdown";

interface RagHit {
  score: number;
  type: string;
  id: string;
  title?: string;
  name?: string;
  price?: number;
  city?: string;
  category?: string;
  bedrooms?: number;
  marla?: number;
}

interface Msg extends AgentEffect {
  role: "user" | "assistant";
  content: string;
  hits?: RagHit[];
  pending?: boolean;
}

export const SUGGESTIONS = [
  "10 marla house in DHA Lahore under 5 crore",
  "Best investment plots in Islamabad",
  "Apartments in Karachi with sea view",
  "Commercial shop for rent in Lahore",
];

const WELCOME: Msg = {
  role: "assistant",
  content:
    "Assalam-o-Alaikum! I’m **Arz-e-Pak AI**. Tell me what you’re looking for — city, budget, size or purpose — and I’ll search live listings, schemes and market data for you.",
};

export function ChatPanel({ compact, className, initial }: { compact?: boolean; className?: string; initial?: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const sentInitial = useRef(false);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  useEffect(() => {
    if (initial && !sentInitial.current) {
      sentInitial.current = true;
      void send(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    const history = [...msgs.filter((m) => !m.pending), { role: "user" as const, content: q }];
    setMsgs([...history, { role: "assistant", content: "", pending: true }]);
    const { chat_mode, chat_model } = await capabilities();
    if (chat_mode === "upstream") {
      try {
        const turns = history.filter((m) => m !== WELCOME && m.content).map((m) => ({ role: m.role, content: m.content }));
        const reply = await agentReply(turns, chat_model);
        setMsgs([...history, { role: "assistant", ...reply }]);
        setBusy(false);
        return;
      } catch {
        /* fall back to the local answer below */
      }
    }
    const [chat, rag] = await Promise.allSettled([
      post<{ choices: { message: { content: string } }[] }>("/v1/chat/completions", {
        model: "portal-realestate-rag",
        messages: [
          { role: "system", content: "You are Arz-e-Pak AI, a helpful Pakistani real-estate assistant. Answer concisely; prices in PKR crore/lakh." },
          ...history.slice(-8).map((m) => ({ role: m.role, content: m.content })),
        ],
      }),
      get<{ results: RagHit[] }>("/rag/search", { query: q, top_k: 6 }),
    ]);
    let content = chat.status === "fulfilled" ? chat.value.choices?.[0]?.message?.content ?? "" : "";
    // The local RAG fallback appends an operator note; keep replies user-facing.
    content = content.replace(/\n*\(No[td]e:[^)]*\)\n*/i, "\n").replace(/\n*Matched records:[\s\S]*$/i, "").trim();
    if (!content) content = chat.status === "rejected" ? "I couldn’t reach the AI service just now — here’s what I found in the listings:" : "Here’s what I found:";
    const hits = rag.status === "fulfilled" ? rag.value.results ?? [] : [];
    setMsgs([...history, { role: "assistant", content, hits }]);
    setBusy(false);
  }

  const lastUser = [...msgs].reverse().find((m) => m.role === "user")?.content;

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <AnimatePresence initial={false}>
          {msgs.map((m, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("flex gap-2.5", m.role === "user" && "flex-row-reverse")}>
              <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-gold-gradient text-brand-950" : "bg-brand-700 text-white")}>
                {m.role === "user" ? <UserIcon className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              </span>
              <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2.5", m.role === "user" ? "rounded-tr-sm bg-brand-700 text-white" : "rounded-tl-sm bg-brand-50 text-ink dark:bg-white/5 dark:text-slate-100")}>
                {m.pending ? (
                  <span className="flex gap-1 py-1.5">
                    {[0, 1, 2].map((d) => (
                      <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-brand-500" style={{ animationDelay: `${d * 0.15}s` }} />
                    ))}
                  </span>
                ) : (
                  <Markdown text={m.content} />
                )}
                {!!m.listings?.length && (
                  <div className="mt-2 space-y-1 rounded-xl bg-white p-1.5 dark:bg-black/20">
                    {m.listings.slice(0, compact ? 3 : 5).map((l: Property) => (
                      <PropertyRow key={l.id} p={l} />
                    ))}
                  </div>
                )}
                {m.image && (
                  <a href={m.image.url} target="_blank" rel="noreferrer" className="mt-2 block overflow-hidden rounded-xl bg-white dark:bg-black/20">
                    <img src={m.image.url} alt={m.image.caption} className="max-h-64 w-full object-cover" loading="lazy" />
                    <span className="block px-2 py-1 text-[11px] text-ink-mute">{m.image.caption}</span>
                  </a>
                )}
                {m.map && (
                  <div className="mt-2 overflow-hidden rounded-xl">
                    <PortalMap center={[m.map.focus.latitude, m.map.focus.longitude]} zoom={14} height={compact ? 180 : 240} switcher={false}>
                      <Marker position={[m.map.focus.latitude, m.map.focus.longitude]} icon={pin("featured", { size: 32 })} />
                      {m.map.markers.map((mk, k) => (
                        <CircleMarker key={k} center={[mk.latitude, mk.longitude]} radius={6} pathOptions={{ color: "#146f45", weight: 2, fillColor: "#f2dd8f", fillOpacity: 0.9 }}>
                          <Tooltip>
                            {mk.name} · {mk.kind}
                            {mk.distance_km !== undefined ? ` · ${mk.distance_km} km` : ""}
                          </Tooltip>
                        </CircleMarker>
                      ))}
                    </PortalMap>
                  </div>
                )}
                {!!m.links?.length && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.links.map((l) => (
                      <Link key={l.label} to={l.to} className={cn("chip", l.primary ? "bg-brand-700 text-white" : "bg-white text-brand-800 ring-1 ring-brand-200 dark:bg-white/10 dark:text-brand-100 dark:ring-white/10")}>
                        {l.label}
                      </Link>
                    ))}
                  </div>
                )}
                {!!m.hits?.length && (
                  <div className="mt-2 space-y-1 rounded-xl bg-white p-1.5 dark:bg-black/20">
                    {m.hits
                      .filter((h) => h.type === "property")
                      .slice(0, compact ? 3 : 5)
                      .map((h) => (
                        <PropertyRow
                          key={h.id}
                          p={{ id: h.id, title: h.title ?? h.name ?? "Listing", price: h.price ?? 0, category: h.category ?? "house", city_name: h.city }}
                          extra={<span className="chip bg-gold-50 text-gold-700 dark:bg-gold-500/10 dark:text-gold-200">{Math.round(Math.min(1, h.score / 2) * 100)}%</span>}
                        />
                      ))}
                    {m.hits.filter((h) => h.type !== "property").length > 0 && (
                      <div className="flex flex-wrap gap-1.5 px-1.5 pb-1 pt-1.5">
                        {m.hits
                          .filter((h) => h.type !== "property")
                          .slice(0, 4)
                          .map((h) => (
                            <span key={h.id} className="chip bg-brand-50 text-brand-700 dark:bg-white/10 dark:text-brand-200">
                              {titleCase(h.type)} · {h.title ?? h.name}
                              {h.price ? ` · ${pkrShort(h.price)}` : ""}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {msgs.length === 1 && (
          <div className="flex flex-wrap gap-2 ps-10">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} className="chip bg-white text-brand-800 ring-1 ring-brand-200 transition hover:bg-brand-50 dark:bg-white/5 dark:text-brand-100 dark:ring-white/10">
                <Sparkles className="h-3 w-3 text-gold-500" /> {s}
              </button>
            ))}
          </div>
        )}
      </div>
      {lastUser && !busy && (
        <div className="no-scrollbar flex gap-2 overflow-x-auto border-t border-black/5 px-4 py-2 dark:border-white/10">
          <button onClick={() => nav(`/ai/agents/conversational_buyer_agent?objective=${encodeURIComponent(lastUser)}`)} className="chip shrink-0 bg-gold-gradient text-brand-950">
            <Wand2 className="h-3 w-3" /> Run Buyer Agent
          </button>
          <button onClick={() => nav(`/properties?q=${encodeURIComponent(lastUser)}`)} className="chip shrink-0 bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100">
            <Sparkles className="h-3 w-3" /> Show all results
          </button>
          <button onClick={() => nav("/map")} className="chip shrink-0 bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100">
            <MapIcon className="h-3 w-3" /> View on map
          </button>
          <button onClick={() => nav("/tools/mortgage")} className="chip shrink-0 bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100">
            <Calculator className="h-3 w-3" /> Mortgage
          </button>
        </div>
      )}
      <form
        className="flex items-center gap-2 border-t border-black/5 p-3 dark:border-white/10"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about properties, prices, areas…" className="input flex-1 rounded-full" disabled={busy} />
        <button type="submit" className="btn btn-primary btn-icon h-11 w-11 rounded-full" disabled={busy || !input.trim()} aria-label="Send">
          <Send className="h-4 w-4 rtl:rotate-180" />
        </button>
      </form>
    </div>
  );
}
