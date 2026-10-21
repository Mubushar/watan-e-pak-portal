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
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Calculator, Check, Copy, Download, ExternalLink, FileText, Loader2, Map as MapIcon, MapPin, Paperclip, Ruler, Send, Shapes, Sparkles, User as UserIcon, Wand2, X } from "lucide-react";
import type { Property } from "@/types";
import { agentReply, attachmentText, capabilities, type AgentEffect, type KnowledgeSource } from "@/lib/agent";
import { ACCEPT, attachmentShape, downloadUrl, onShare, readAttachment, showShapeOnMap, takePendingShares, type ChatAttachment, type ChatFile, type LocationCard } from "@/lib/chatShare";
import { fmtLatLon, googleMapsUrl, toDms } from "@/lib/geoMeasure";
import { focusMap, onMapPage } from "@/lib/mapFocus";
import { toast } from "sonner";
import { ApiError, get, post } from "@/lib/api";
import { pkrShort, titleCase } from "@/lib/format";
import { cn, safeHref } from "@/lib/utils";
import { PropertyRow } from "@/components/property/PropertyCard";
// Leaflet (~150 kB) loads only when a reply actually contains a map.
const ChatMap = lazy(() => import("./ChatMap"));
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
  /** What the user attached / shared from the map with this message. */
  attachments?: ChatAttachment[];
}

const kb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const attLabel = (a: ChatAttachment) =>
  a.kind === "image" || a.kind === "document" || a.kind === "geodata" ? a.name : a.kind === "pin" ? `${a.label} · ${fmtLatLon(a.lat, a.lon, 5)}` : `${a.label} · ${a.value_text}`;
const AttIcon = ({ a, className }: { a: ChatAttachment; className?: string }) => {
  const I = a.kind === "document" ? FileText : a.kind === "geodata" ? Shapes : a.kind === "pin" ? MapPin : a.kind === "measure" ? Ruler : Paperclip;
  return <I className={className} />;
};

/** Show a shared shape / point on the portal's map (opening the Map page when needed). */
function useShowOnMap() {
  const nav = useNavigate();
  return (a: ChatAttachment | LocationCard) => {
    if ("kind" in a) {
      const fc = attachmentShape(a);
      if (fc) showShapeOnMap({ id: `chat-${a.kind}-${attLabel(a)}`, name: attLabel(a), geojson: fc, fit: true });
    } else focusMap({ name: a.label, latitude: a.lat, longitude: a.lon, zoom: 17, masterPlan: true });
    if (!onMapPage()) nav("/map");
  };
}

/** What the user sent with a message (in their bubble). */
function SentAttachments({ items }: { items: ChatAttachment[] }) {
  const show = useShowOnMap();
  const pics = items.filter((a): a is Extract<ChatAttachment, { kind: "image" }> => a.kind === "image");
  const rest = items.filter((a) => a.kind !== "image");
  return (
    <div className="mt-1.5 space-y-1.5">
      {pics.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {pics.map((p, i) => (
            <a key={i} href={p.dataUrl} target="_blank" rel="noreferrer" title={p.name}>
              <img src={p.dataUrl} alt={p.name} className="h-20 w-20 rounded-lg object-cover ring-1 ring-white/30" />
            </a>
          ))}
        </div>
      )}
      {rest.map((a, i) => (
        <div key={i} className="flex items-center gap-1.5 rounded-lg bg-white/15 px-2 py-1 text-[12px]">
          <AttIcon a={a} className="h-3.5 w-3.5 shrink-0" />
          <span className="min-w-0 flex-1 truncate">
            {attLabel(a)}
            {a.kind === "document" && a.pages ? ` · ${a.pages} pages` : ""}
          </span>
          {(a.kind === "geodata" || a.kind === "pin" || a.kind === "measure") && (
            <button type="button" onClick={() => show(a)} className="shrink-0 font-semibold underline-offset-2 hover:underline">
              Show on map
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

/** Files the assistant made: open / download (pictures are shown). */
function FileCards({ files }: { files: ChatFile[] }) {
  return (
    <div className="mt-2 space-y-1.5">
      {files.map((f) => (
        <div key={f.url} className="overflow-hidden rounded-xl bg-white ring-1 ring-black/5 dark:bg-black/20 dark:ring-white/10">
          {f.kind === "image" && (
            <a href={f.url} target="_blank" rel="noreferrer">
              <img src={f.url} alt={f.caption ?? f.name} className="max-h-56 w-full object-cover" />
            </a>
          )}
          <div className="flex items-center gap-2 p-2">
            <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold", f.kind === "pdf" ? "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300" : "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300")}>
              {f.kind === "pdf" ? "PDF" : "PNG"}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold">{f.name}</span>
              <span className="block text-[11px] text-ink-mute">{kb(f.size)}</span>
            </span>
            <a href={f.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-icon h-8 w-8" aria-label={`Open ${f.name}`} title="Open">
              <ExternalLink className="h-4 w-4" />
            </a>
            <button type="button" onClick={() => downloadUrl(f.url, f.name)} className="btn btn-primary btn-icon h-8 w-8" aria-label={`Download ${f.name}`} title="Download">
              <Download className="h-4 w-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

/** A shared location: coordinates, copy, Google Maps, show on the portal map. */
function LocationCardView({ loc }: { loc: LocationCard }) {
  const show = useShowOnMap();
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-2 rounded-xl bg-white p-2.5 text-[12px] ring-1 ring-black/5 dark:bg-black/20 dark:ring-white/10">
      <div className="flex items-start gap-2">
        <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold">{loc.label}</p>
          <p className="font-mono text-ink-mute">{fmtLatLon(loc.lat, loc.lon)}</p>
          <p className="font-mono text-ink-mute">{toDms(loc.lat, loc.lon)}</p>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <button type="button" className="chip bg-brand-700 text-white" onClick={() => show(loc)}>
          <MapIcon className="h-3 w-3" /> Show on map
        </button>
        <button
          type="button"
          className="chip bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100"
          onClick={() => {
            void navigator.clipboard?.writeText(fmtLatLon(loc.lat, loc.lon));
            setCopied(true);
          }}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />} {copied ? "Copied" : "Copy"}
        </button>
        <a href={googleMapsUrl(loc.lat, loc.lon)} target="_blank" rel="noopener noreferrer" className="chip bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100">
          <ExternalLink className="h-3 w-3" /> Google Maps
        </a>
      </div>
    </div>
  );
}

let aiWarned = false;

const TIER_STYLE: Record<KnowledgeSource["tier"], string> = {
  official: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-200",
  verified: "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-200",
  reference: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-200",
  listing: "bg-gold-50 text-gold-700 dark:bg-gold-500/10 dark:text-gold-200",
  unverified: "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300",
};
const TIER_LABEL: Record<KnowledgeSource["tier"], string> = {
  official: "Official",
  verified: "Verified",
  reference: "Reference",
  listing: "Listing",
  unverified: "Unverified",
};

/** The knowledge the reply cites: [n], title, how far to trust it, and the original source. */
function Sources({ items }: { items: KnowledgeSource[] }) {
  return (
    <div className="mt-2 space-y-1 rounded-xl bg-white p-2 text-[12px] dark:bg-black/20">
      <div className="px-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink-mute">Sources</div>
      {items.map((s) => {
        const origin = s.sources?.find((o) => safeHref(o.url ?? ""));
        const href = safeHref(origin?.url ?? "");
        return (
          <div key={`${s.cite}-${s.id}`} className="flex flex-wrap items-baseline gap-1.5">
            <span className="font-semibold text-brand-700 dark:text-brand-200">{s.cite}</span>
            {s.url.startsWith("/") ? (
              <Link to={s.url} className="font-medium hover:underline">
                {s.title}
              </Link>
            ) : (
              <span className="font-medium">{s.title}</span>
            )}
            <span className={cn("chip px-1.5 py-0 text-[10px]", TIER_STYLE[s.tier] ?? TIER_STYLE.unverified)} title={s.trust}>
              {TIER_LABEL[s.tier] ?? "Unverified"}
            </span>
            {href && (
              <a href={href} target="_blank" rel="noopener noreferrer" className="truncate text-ink-mute hover:underline">
                {origin?.title || new URL(href, window.location.href).hostname}
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
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
    "Assalam-o-Alaikum! I’m **Arz-e-Pak AI**. Tell me what you’re looking for — city, budget, size or purpose — and I’ll search live listings, societies and market data for you.",
};

export function ChatPanel({ compact, className, initial }: { compact?: boolean; className?: string; initial?: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const sentInitial = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wasBusy = useRef(false);
  // Attachments waiting to go with the next message (files, or items shared from the Map page).
  const [atts, setAtts] = useState<ChatAttachment[]>([]);
  const [reading, setReading] = useState(0);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  async function addFiles(files: FileList | File[]) {
    const list = [...files].slice(0, 6);
    setReading((n) => n + list.length);
    await Promise.all(
      list.map(async (f) => {
        try {
          const a = await readAttachment(f);
          setAtts((cur) => [...cur, a].slice(-8));
        } catch (e) {
          toast.error(`${f.name}: ${(e as Error).message}`);
        } finally {
          setReading((n) => n - 1);
        }
      }),
    );
    inputRef.current?.focus({ preventScroll: true });
  }
  useEffect(() => {
    const take = () => {
      const got = takePendingShares();
      if (!got.length) return;
      setAtts((cur) => [...cur, ...got.map((g) => g.item)].slice(-8));
      const ask = got.map((g) => g.ask).find(Boolean);
      if (ask) setInput((cur) => cur || ask);
      setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 50);
    };
    take();
    return onShare(take);
  }, []);

  // The input is disabled while the assistant answers, which drops focus — and moving the map can take
  // it too. Give it back when the reply lands (and again once a fly-to has finished), so the user keeps typing.
  useEffect(() => {
    if (busy) {
      wasBusy.current = true;
      return;
    }
    if (!wasBusy.current) return;
    wasBusy.current = false;
    const refocus = () => {
      const a = document.activeElement;
      if (!a || a === document.body || a.closest?.(".leaflet-container") || a === inputRef.current) inputRef.current?.focus({ preventScroll: true });
    };
    const t1 = setTimeout(refocus, 30);
    const t2 = setTimeout(refocus, 1400);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [busy]);

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
    const withAtts = text === input ? atts : [];
    if ((!q && !withAtts.length) || busy || reading) return;
    setInput("");
    if (withAtts.length) setAtts([]);
    setBusy(true);
    const history: Msg[] = [...msgs.filter((m) => !m.pending), { role: "user", content: q, attachments: withAtts.length ? withAtts : undefined }];
    setMsgs([...history, { role: "assistant", content: "", pending: true }]);
    const { chat_mode, chat_model } = await capabilities();
    if (chat_mode === "upstream") {
      try {
        const turns = history.filter((m) => m !== WELCOME && (m.content || m.attachments?.length)).map((m) => ({ role: m.role, content: m.content, attachments: m.attachments }));
        const { navigate, ...reply } = await agentReply(turns, chat_model);
        setMsgs([...history, { role: "assistant", ...reply }]);
        if (navigate) nav(navigate); // focus_map: open the Map page it moved
        setBusy(false);
        return;
      } catch (e) {
        // Fall back to the local answer below; say why once if the AI itself refused (e.g. no credit).
        if (e instanceof ApiError && e.status >= 400 && !aiWarned) {
          aiWarned = true;
          toast.warning(`AI unavailable — answering from portal data for now. ${e.message}`);
        }
      }
    }
    const [chat, rag] = await Promise.allSettled([
      post<{ choices: { message: { content: string } }[] }>("/v1/chat/completions", {
        model: "portal-realestate-rag",
        messages: [
          { role: "system", content: "You are Arz-e-Pak AI, a helpful Pakistani real-estate assistant. Answer concisely; prices in PKR crore/lakh." },
          ...history.slice(-8).map((m) => ({ role: m.role, content: [m.content, ...(m.attachments ?? []).map((a) => attachmentText(a, false))].filter(Boolean).join("\n\n") })),
        ],
      }),
      get<{ results: RagHit[] }>("/rag/search", { query: q || withAtts.map(attLabel).join(" "), top_k: 6 }),
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
    <div
      className={cn("relative flex h-full min-h-0 flex-col", className)}
      onDragOver={(e) => {
        if (![...e.dataTransfer.types].includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={(e) => {
        if (!e.dataTransfer.files.length) return;
        e.preventDefault();
        setDragging(false);
        void addFiles(e.dataTransfer.files);
      }}
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-2 z-10 flex items-center justify-center rounded-2xl border-2 border-dashed border-brand-500 bg-brand-50/90 text-sm font-semibold text-brand-800 dark:bg-brand-950/90 dark:text-brand-100">
          Drop photos, PDFs, documents or KML / GeoJSON / GPX here
        </div>
      )}
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
                  m.content && <Markdown text={m.content} />
                )}
                {!!m.attachments?.length && <SentAttachments items={m.attachments} />}
                {!!m.files?.length && <FileCards files={m.files} />}
                {m.location && <LocationCardView loc={m.location} />}
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
                    <Suspense fallback={<div className="animate-pulse bg-black/5 dark:bg-white/5" style={{ height: compact ? 180 : 240 }} />}>
                      <ChatMap map={m.map} height={compact ? 180 : 240} />
                    </Suspense>
                  </div>
                )}
                {!!m.choices?.length && i === msgs.length - 1 && !busy && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.choices.map((c) => (
                      <button key={c} type="button" onClick={() => void send(c)} className="chip bg-gold-50 text-brand-900 ring-1 ring-gold-300 hover:bg-gold-100 dark:bg-white/10 dark:text-gold-200 dark:ring-white/20">
                        {c}
                      </button>
                    ))}
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
                {!!m.sources?.length && <Sources items={m.sources} />}
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
      {(atts.length > 0 || reading > 0) && (
        <div className="flex flex-wrap gap-1.5 border-t border-black/5 px-3 pt-2 dark:border-white/10">
          {atts.map((a, i) => (
            <span key={i} className="chip max-w-full bg-brand-50 pe-1 text-brand-900 dark:bg-white/10 dark:text-brand-100">
              {a.kind === "image" ? <img src={a.dataUrl} alt="" className="h-5 w-5 rounded object-cover" /> : <AttIcon a={a} className="h-3.5 w-3.5" />}
              <span className="max-w-[180px] truncate">{attLabel(a)}</span>
              <button type="button" onClick={() => setAtts((cur) => cur.filter((_, j) => j !== i))} className="rounded-full p-0.5 hover:bg-black/10" aria-label={`Remove ${attLabel(a)}`}>
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {reading > 0 && (
            <span className="chip bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Reading {reading} file{reading > 1 ? "s" : ""}…
            </span>
          )}
        </div>
      )}
      <form
        className="flex items-center gap-2 border-t border-black/5 p-3 dark:border-white/10"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <input
          ref={fileInput}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) void addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          className="btn btn-ghost btn-icon h-11 w-11 shrink-0 rounded-full"
          onClick={() => fileInput.current?.click()}
          disabled={busy}
          aria-label="Attach photos, documents or map files"
          title="Attach photos, PDFs, Word / Excel / text files, or KML / GeoJSON / GPX"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPaste={(e) => {
            const files = [...e.clipboardData.files];
            if (files.length) {
              e.preventDefault();
              void addFiles(files);
            }
          }}
          placeholder={atts.length ? "Ask about what you attached…" : "Ask about properties, prices, areas…"}
          className="input min-w-0 flex-1 rounded-full"
          disabled={busy}
        />
        <button type="submit" className="btn btn-primary btn-icon h-11 w-11 shrink-0 rounded-full" disabled={busy || reading > 0 || (!input.trim() && !atts.length)} aria-label="Send">
          <Send className="h-4 w-4 rtl:rotate-180" />
        </button>
      </form>
    </div>
  );
}
