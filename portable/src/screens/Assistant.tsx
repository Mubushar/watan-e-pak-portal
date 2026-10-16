/**
 * Conversational AI assistant — voice and text.
 *   - Mic: speak in English or Urdu; partial transcript shows live.
 *   - Replies are read aloud (toggle), and "Conversation mode" keeps listening
 *     after each spoken reply for hands-free use.
 *   - Replies carry real listings and one-tap actions (open results, create a
 *     pre-filled listing, sign in, manage listings).
 * URL params: ?q=<text> sends a message, ?listen=1 starts listening.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Headphones, Keyboard, Mic, RotateCcw, Send, Sparkles, Square, User as UserIcon, Volume2, VolumeX } from "lucide-react";
import { toast } from "sonner";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import { newId, respond, suggestionsFor, useChat, welcomeFor, type ChatAction, type ChatMsg } from "@/lib/assistant";
import { canSpeak, listen, speak, stopSpeaking, sttEngine, type ListenSession } from "@/lib/voice";
import { isNative } from "@/lib/platform";
import { cn, isUrdu } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { Markdown } from "@/components/Markdown";
import { PropertyRow } from "@/components/PropertyCard";
import { TopBar } from "@/components/ui";

type Phase = "idle" | "listening" | "thinking" | "speaking";

export default function Assistant() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const user = useAuth((s) => s.user);
  const { messages, add, update, clear, setPendingDraft } = useChat();
  const { voiceLang, setVoiceLang, autoSpeak, setAutoSpeak, handsFree, setHandsFree } = usePrefs();
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [partial, setPartial] = useState("");
  const [voiceOk, setVoiceOk] = useState<boolean | null>(null);
  const [typing, setTyping] = useState(false);
  const session = useRef<ListenSession | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const handsFreeRef = useRef(handsFree);
  handsFreeRef.current = handsFree;
  const all: ChatMsg[] = [welcomeFor(user), ...messages];

  useEffect(() => {
    void sttEngine().then((e) => setVoiceOk(!!e));
    return () => {
      session.current?.stop();
      void stopSpeaking();
    };
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, partial, phase]);

  const send = useCallback(
    async (text: string, viaVoice = false) => {
      const q = text.trim();
      if (!q || phase === "thinking") return;
      setInput("");
      const history = useChat.getState().messages;
      add({ id: newId(), role: "user", content: q, voice: viaVoice });
      const id = newId();
      add({ id, role: "assistant", content: "", pending: true });
      setPhase("thinking");
      const reply = await respond(q, history, useAuth.getState().user, usePrefs.getState().voiceLang);
      update(id, { ...reply, pending: false });
      const { autoSpeak: say, voiceLang: lang } = usePrefs.getState();
      if (say && canSpeak() && (viaVoice || handsFreeRef.current)) {
        setPhase("speaking");
        await speak(reply.content, isUrdu(reply.content) ? "ur-PK" : lang);
      }
      setPhase("idle");
      if (viaVoice && handsFreeRef.current) void startListening();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [phase, add, update],
  );

  const startListening = useCallback(async () => {
    if (session.current) {
      session.current.stop();
      return;
    }
    await stopSpeaking();
    setPartial("");
    if (isNative) void Haptics.impact({ style: ImpactStyle.Medium }).catch(() => undefined);
    try {
      const s = await listen({ lang: usePrefs.getState().voiceLang, onPartial: setPartial });
      session.current = s;
      setPhase("listening");
      const said = await s.result;
      session.current = null;
      setPartial("");
      setPhase("idle");
      if (said) void send(said, true);
      else if (!handsFreeRef.current) toast.info("I didn't catch that — tap the mic and try again.");
    } catch (e) {
      session.current = null;
      setPartial("");
      setPhase("idle");
      toast.error((e as Error).message);
    }
  }, [send]);

  // Deep links: ?q=… and ?listen=1
  const handled = useRef(false);
  useEffect(() => {
    if (handled.current) return;
    const q = sp.get("q");
    const l = sp.get("listen");
    if (!q && !l) return;
    handled.current = true;
    setSp({}, { replace: true });
    if (q) void send(q);
    else if (l) void startListening();
  }, [sp, setSp, send, startListening]);

  const runAction = (a: ChatAction) => {
    if (a.say) return void send(a.say);
    if (a.draft) {
      if (!useAuth.getState().token) {
        setPendingDraft(a.draft);
        return nav("/signin?next=/listings/new");
      }
      return nav("/listings/new", { state: { draft: a.draft } });
    }
    if (a.to) nav(a.to);
  };

  const listening = phase === "listening";
  return (
    <div className="flex h-[calc(100dvh-5.25rem-env(safe-area-inset-bottom))] flex-col md:h-screen">
      <TopBar
        title={
          <span className="flex items-center gap-2.5">
            <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-brand-gradient text-white">
              <Bot className="h-5 w-5" />
              <span className="absolute -end-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-[#f6f8f6] dark:ring-[#07130d]" />
            </span>
            <span className="leading-tight">
              Arz-e-Pak AI
              <span className="block text-[11px] font-medium text-ink-mute">{phase === "thinking" ? "Thinking…" : phase === "listening" ? "Listening…" : phase === "speaking" ? "Speaking…" : "Voice & chat assistant"}</span>
            </span>
          </span>
        }
        actions={
          <>
            <button
              className="btn btn-ghost btn-sm font-bold"
              onClick={() => setVoiceLang(voiceLang === "en-US" ? "ur-PK" : "en-US")}
              aria-label="Voice language"
              title="Voice language"
            >
              {voiceLang === "en-US" ? "EN" : "اردو"}
            </button>
            {canSpeak() && (
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => {
                  if (autoSpeak) void stopSpeaking();
                  setAutoSpeak(!autoSpeak);
                }}
                aria-label={autoSpeak ? "Mute spoken replies" : "Read replies aloud"}
                title={autoSpeak ? "Spoken replies on" : "Spoken replies off"}
              >
                {autoSpeak ? <Volume2 className="h-5 w-5" /> : <VolumeX className="h-5 w-5" />}
              </button>
            )}
            {messages.length > 0 && (
              <button className="btn btn-ghost btn-icon" onClick={() => { void stopSpeaking(); clear(); }} aria-label="New conversation" title="New conversation">
                <RotateCcw className="h-5 w-5" />
              </button>
            )}
          </>
        }
      />

      <div ref={scroller} className="flex-1 overflow-y-auto">
        <div className="screen space-y-4 py-4">
          <AnimatePresence initial={false}>
            {all.map((m) => (
              <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("flex gap-2.5", m.role === "user" && "flex-row-reverse")}>
                <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-gold-gradient text-brand-950" : "bg-brand-700 text-white")}>
                  {m.role === "user" ? m.voice ? <Mic className="h-4 w-4" /> : <UserIcon className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </span>
                <div className={cn("min-w-0 max-w-[85%] rounded-2xl px-3.5 py-2.5", m.role === "user" ? "rounded-tr-sm bg-brand-700 text-white" : "rounded-tl-sm bg-white text-ink shadow-card dark:bg-[#0d1f16] dark:text-slate-100")}>
                  {m.pending ? (
                    <span className="flex gap-1 py-1.5">
                      {[0, 1, 2].map((d) => (
                        <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-brand-500" style={{ animationDelay: `${d * 0.15}s` }} />
                      ))}
                    </span>
                  ) : (
                    <div dir="auto" className={cn(isUrdu(m.content) && "urdu")}>
                      <Markdown text={m.content} />
                    </div>
                  )}
                  {!!m.listings?.length && (
                    <div className="mt-2 space-y-0.5 rounded-xl bg-brand-50/60 p-1 dark:bg-black/20">
                      {m.listings.slice(0, 5).map((p) => (
                        <PropertyRow key={p.id} p={p} className="p-1.5" />
                      ))}
                    </div>
                  )}
                  {!!m.actions?.length && (
                    <div className="mt-2.5 flex flex-wrap gap-2">
                      {m.actions.map((a) => (
                        <button key={a.label} onClick={() => runAction(a)} className={cn("chip px-3 py-1.5", a.primary ? "bg-gold-gradient text-brand-950 shadow-glow" : "bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100")}>
                          {a.primary && <Sparkles className="h-3 w-3" />} {a.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {m.role === "assistant" && !m.pending && m.id !== "welcome" && canSpeak() && (
                    <button onClick={() => void speak(m.content, isUrdu(m.content) ? "ur-PK" : voiceLang)} className="mt-1.5 flex items-center gap-1 text-[11px] font-semibold text-ink-mute hover:text-brand-700" aria-label="Read aloud">
                      <Volume2 className="h-3.5 w-3.5" /> Listen
                    </button>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {messages.length === 0 && (
            <div className="flex flex-wrap gap-2 ps-10">
              {suggestionsFor(user?.role).map((s) => (
                <button key={s} onClick={() => void send(s)} className="chip bg-white px-3 py-1.5 text-brand-800 ring-1 ring-brand-200 transition hover:bg-brand-50 dark:bg-white/5 dark:text-brand-100 dark:ring-white/10">
                  <Sparkles className="h-3 w-3 text-gold-500" /> {s}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ---------- composer ---------- */}
      <div className="border-t border-black/5 bg-white/90 backdrop-blur-xl dark:border-white/10 dark:bg-[#0b1a12]/90">
        <AnimatePresence>
          {listening && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
              <div className="screen flex items-center gap-3 pt-3">
                <div className="flex h-8 items-center gap-1">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <span key={i} className="h-full w-1 origin-center animate-wave rounded-full bg-brand-500" style={{ animationDelay: `${i * 0.12}s` }} />
                  ))}
                </div>
                <p dir="auto" className={cn("min-w-0 flex-1 truncate text-sm text-ink-soft dark:text-slate-300", isUrdu(partial) && "urdu")}>
                  {partial || (voiceLang === "ur-PK" ? "بولیے… میں سن رہا ہوں" : "Speak now — I'm listening…")}
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="screen flex items-center gap-2 py-3">
          {typing || voiceOk === false ? (
            <form
              className="flex flex-1 items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void send(input);
              }}
            >
              <input
                dir="auto"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about properties, prices, areas…"
                className={cn("input flex-1 rounded-full", isUrdu(input) && "urdu")}
                disabled={phase === "thinking"}
                autoFocus={typing}
              />
              <button type="submit" className="btn btn-primary btn-icon h-11 w-11 shrink-0 rounded-full" disabled={phase === "thinking" || !input.trim()} aria-label="Send">
                <Send className="h-4 w-4 rtl:rotate-180" />
              </button>
            </form>
          ) : (
            <button className="btn btn-outline h-11 flex-1 justify-start rounded-full text-ink-mute" onClick={() => setTyping(true)}>
              <Keyboard className="h-4 w-4" /> Type a message
            </button>
          )}

          {voiceOk !== false && (
            <button
              onClick={() => void startListening()}
              disabled={phase === "thinking"}
              aria-label={listening ? "Stop listening" : "Speak"}
              className={cn(
                "relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full shadow-glow transition active:scale-95 disabled:opacity-60",
                listening ? "bg-red-600 text-white" : "bg-gold-gradient text-brand-950",
              )}
            >
              {listening && <span className="absolute inset-0 animate-pulse-ring rounded-full bg-red-500/50" />}
              {listening ? <Square className="relative h-5 w-5 fill-current" /> : <Mic className="relative h-6 w-6" />}
            </button>
          )}
        </div>

        {voiceOk !== false && (
          <div className="screen -mt-1 flex items-center justify-between pb-2 text-[11px] text-ink-mute">
            <button onClick={() => setHandsFree(!handsFree)} className={cn("flex items-center gap-1.5 font-semibold", handsFree && "text-brand-700 dark:text-brand-300")}>
              <Headphones className="h-3.5 w-3.5" /> Conversation mode {handsFree ? "on" : "off"}
            </button>
            {typing && (
              <button onClick={() => setTyping(false)} className="font-semibold">
                Use voice
              </button>
            )}
          </div>
        )}
        {voiceOk === false && <p className="screen -mt-1 pb-2 text-[11px] text-ink-mute">Voice input isn’t available on this device — type instead, or use your keyboard’s dictation.</p>}
      </div>
    </div>
  );
}
