/**
 * Arz-e-Pak AI assistant — OpenAI only, mirroring how the person talks:
 *   - Typed message      → text reply (OpenAI chat model).
 *   - Voice note         → voice-note reply (OpenAI speech-to-text → chat → text-to-speech).
 *   - Live conversation  → OpenAI Realtime voice agent (lib/realtime): one tap starts a
 *     natural, interruptible conversation; captions of both sides appear in the chat and
 *     the agent's tool calls (listing search, details, your listings, drafting a listing)
 *     show up as cards and buttons. Tap ■ to hang up.
 * Replies follow the reply-language choice (Auto / EN / اردو).
 * URL params: ?q=<text> sends a message, ?listen=1 starts the live conversation.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Headphones, Info, Keyboard, Languages, Mic, MicOff, Pause, Play, RotateCcw, Send, Sparkles, Square, Trash2, User as UserIcon, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import { chatMode, newId, respond, suggestionsFor, useChat, welcomeFor, type ChatAction, type ChatMsg, type MsgKind, type Reply } from "@/lib/assistant";
import { detectLang, speechTag, type Lang } from "@/lib/lang";
import { RealtimeAgent, type AgentState } from "@/lib/realtime";
import { mergeEffects, runAgentTool } from "@/lib/tools";
import { NOT_CONFIGURED, playAudio, recordVoiceNote, serverVoice, speak, stopSpeaking, synthesize, type ServerVoice, type VoiceNoteSession } from "@/lib/voice";
import { isNative } from "@/lib/platform";
import { cn, isUrdu } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { Markdown } from "@/components/Markdown";
import { PropertyRow } from "@/components/PropertyCard";
import { TopBar } from "@/components/ui";
import { OnScreenKeyboard, phoneticKeyDown } from "@/components/UrduKeyboard";

type Phase = "idle" | "recording" | "thinking" | "speaking";

const REPLY_LABEL = { auto: "Auto", en: "EN", ur: "اردو" } as const;
const NEXT_REPLY = { auto: "en", en: "ur", ur: "auto" } as const;

const haptic = () => {
  if (isNative) void Haptics.impact({ style: ImpactStyle.Medium }).catch(() => undefined);
};

const clock = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

export default function Assistant() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const user = useAuth((s) => s.user);
  const { messages, add, update, clear, setPendingDraft } = useChat();
  const { voiceLang, setVoiceLang, replyLang, setReplyLang } = usePrefs();
  const [basicMode, setBasicMode] = useState(false);
  // Greeting, suggestions and labels: the chosen reply language, else the typing language.
  const uiLang: Lang = replyLang !== "auto" ? replyLang : voiceLang === "ur-PK" ? "ur" : "en";
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [partial, setPartial] = useState("");
  const [voice, setVoice] = useState<ServerVoice | null>(null);
  const [live, setLive] = useState<AgentState | null>(null);
  const [muted, setMuted] = useState(false);
  const [note, setNote] = useState<{ session: VoiceNoteSession; started: number } | null>(null);
  const [noteClock, setNoteClock] = useState(0);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [showKeyboard, setShowKeyboard] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const agent = useRef<RealtimeAgent | null>(null);
  /** Cards / buttons produced by tool calls, waiting for the agent's spoken answer. */
  const liveExtras = useRef(new Map<string, Partial<ChatMsg>>());
  const busy = useRef(false); // a text / voice-note reply is being prepared
  const scroller = useRef<HTMLDivElement>(null);
  const all: ChatMsg[] = [welcomeFor(user, uiLang), ...messages];
  const inConversation = live !== null;
  const voiceReady = voice ? voice.stt : null;

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, partial, phase, live]);

  useEffect(() => {
    if (!note) return;
    const t = setInterval(() => setNoteClock(performance.now() - note.started), 250);
    return () => clearInterval(t);
  }, [note]);

  /** Show the person's message, get the reply in their language, and show it. */
  const ask = useCallback(
    async (q: string, kind: MsgKind, extra: Partial<ChatMsg> = {}): Promise<{ reply: Reply; id: string }> => {
      busy.current = true;
      const history = useChat.getState().messages;
      // Messages with no language clue ("ok", "5 crore") keep the conversation's language.
      const fallback: Lang = [...history].reverse().find((m) => m.role === "user" && m.lang)?.lang ?? (usePrefs.getState().voiceLang === "ur-PK" ? "ur" : "en");
      add({ id: newId(), role: "user", content: q, kind, lang: detectLang(q, fallback), ...extra });
      const id = newId();
      add({ id, role: "assistant", content: "", kind, pending: true });
      setPhase("thinking");
      try {
        const chosen = usePrefs.getState().replyLang;
        const reply = await respond(q, history, useAuth.getState().user, { mode: kind === "text" ? "text" : "voice", fallback, force: chosen === "auto" ? undefined : chosen });
        // A voice-note reply stays "pending" until its audio is ready.
        update(id, { ...reply, kind, pending: kind === "voice-note" });
        return { reply, id };
      } finally {
        busy.current = false;
      }
    },
    [add, update],
  );

  /** Play a message out loud: its audio clip if it has one, else the OpenAI voice. */
  const play = useCallback(
    async (m: ChatMsg) => {
      if (playingId === m.id) {
        await stopSpeaking();
        setPlayingId(null);
        return;
      }
      setPlayingId(m.id);
      try {
        if (m.audioUrl) await playAudio(m.audioUrl);
        else if ((await speak(m.content, speechTag(m.lang ?? detectLang(m.content)))) === "unavailable") toast.error(NOT_CONFIGURED);
      } catch {
        toast.error("Couldn't play this audio.");
      } finally {
        setPlayingId((cur) => (cur === m.id ? null : cur));
      }
    },
    [playingId],
  );

  // ------------------------------------------------------------- typed messages
  const sendText = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || busy.current) return;
      setInput("");
      await ask(q, "text");
      setPhase("idle");
    },
    [ask],
  );

  // ------------------------------------------------------------- voice notes
  const startNote = useCallback(async () => {
    if (busy.current || inConversation || note) return;
    await stopSpeaking();
    haptic();
    try {
      const s = await recordVoiceNote(setPartial);
      setNote({ session: s, started: performance.now() });
      setNoteClock(0);
      setPhase("recording");
      const recorded = await s.result;
      setNote(null);
      setPartial("");
      if (!recorded.text) {
        setPhase("idle");
        if (recorded.audioUrl) toast.info("I couldn't hear any words in that voice note — try again.");
        return;
      }
      const { reply, id } = await ask(recorded.text, "voice-note", { audioUrl: recorded.audioUrl, durationMs: recorded.durationMs });
      // Reply as a voice note (OpenAI voice) and play it once.
      const audioUrl = (await synthesize(reply.content, speechTag(reply.lang))) ?? undefined;
      update(id, { audioUrl, pending: false });
      if (audioUrl) {
        setPhase("speaking");
        setPlayingId(id);
        try {
          await playAudio(audioUrl);
        } finally {
          setPlayingId((cur) => (cur === id ? null : cur));
        }
      }
    } catch (e) {
      setNote(null);
      setPartial("");
      toast.error((e as Error).message);
    }
    setPhase("idle");
  }, [ask, inConversation, note, update]);

  // ------------------------------------------------------------- live conversation (OpenAI Realtime)
  /** Add or update a live caption bubble. */
  const upsert = useCallback(
    (id: string, patch: Partial<ChatMsg> & { role: ChatMsg["role"] }) => {
      if (useChat.getState().messages.some((m) => m.id === id)) update(id, patch);
      else add({ id, content: "", kind: "live", ...patch });
    },
    [add, update],
  );

  /** Attach cards/buttons from a tool call to the agent's answer for that response. */
  const attach = useCallback(
    (responseId: string, extra: Partial<ChatMsg>) => {
      const id = `rt-a-${responseId}`;
      const prev = liveExtras.current.get(responseId) ?? {};
      const merged = { ...prev, ...mergeEffects(prev, extra) };
      liveExtras.current.set(responseId, merged);
      if (useChat.getState().messages.some((m) => m.id === id)) update(id, merged);
    },
    [update],
  );

  /** Run a tool the live agent called, against our backend with the user's session. */
  const runTool = useCallback(
    async (name: string, args: Record<string, unknown>, responseId: string): Promise<unknown> => {
      // Buttons follow the language the person is speaking (unless they picked one).
      const spoken = [...useChat.getState().messages].reverse().find((m) => m.role === "user" && m.lang)?.lang;
      const lang = usePrefs.getState().replyLang === "auto" ? (spoken ?? uiLang) : uiLang;
      const { output, effect } = await runAgentTool(name, args, lang);
      attach(responseId, effect);
      return output;
    },
    [attach, uiLang],
  );

  const endConversation = useCallback(() => {
    agent.current?.stop();
  }, []);

  const startConversation = useCallback(async () => {
    if (agent.current || busy.current || note) return;
    const v = await serverVoice();
    if (!v.realtime) return void toast.error(NOT_CONFIGURED);
    await stopSpeaking();
    haptic();
    setMuted(false);
    liveExtras.current.clear();
    const a = new RealtimeAgent({
      onState: setLive,
      onUserText: (itemId, text, final) =>
        upsert(`rt-u-${itemId}`, { role: "user", content: text || (final ? "…" : ""), lang: text ? detectLang(text) : undefined, pending: !final && !text }),
      onAgentText: (responseId, text) => upsert(`rt-a-${responseId}`, { role: "assistant", content: text, lang: detectLang(text), pending: false, ...liveExtras.current.get(responseId) }),
      runTool,
      onError: (msg) => toast.error(msg),
      onEnd: () => {
        agent.current = null;
        setLive(null);
        setMuted(false);
      },
    });
    agent.current = a;
    try {
      await a.start(usePrefs.getState().replyLang);
    } catch (e) {
      toast.error((e as Error).message);
      a.stop();
    }
  }, [note, runTool, upsert]);

  // Voice + AI availability; hang up when leaving the screen.
  useEffect(() => {
    void serverVoice().then(setVoice);
    void chatMode().then((m) => setBasicMode(m === "local"));
    return () => {
      agent.current?.stop();
      void stopSpeaking();
    };
  }, []);

  // Deep links: ?q=... and ?listen=1
  const handled = useRef(false);
  useEffect(() => {
    if (handled.current) return;
    const q = sp.get("q");
    const l = sp.get("listen");
    if (!q && !l) return;
    handled.current = true;
    setSp({}, { replace: true });
    if (q) void sendText(q);
    else if (l) void startConversation();
  }, [sp, setSp, sendText, startConversation]);

  const runAction = (a: ChatAction) => {
    if (a.say) return void sendText(a.say);
    if (a.draft) {
      if (!useAuth.getState().token) {
        setPendingDraft(a.draft);
        return nav("/signin?next=/listings/new");
      }
      return nav("/listings/new", { state: { draft: a.draft } });
    }
    if (a.to) nav(a.to);
  };

  const ur = uiLang === "ur";
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
              <span className="block text-[11px] font-medium text-ink-mute">
                {live
                  ? liveLabel(live, ur)
                  : phase === "thinking"
                    ? ur ? "سوچ رہا ہوں…" : "Thinking…"
                    : phase === "recording"
                      ? ur ? "سن رہا ہوں…" : "Listening…"
                      : phase === "speaking"
                        ? ur ? "بول رہا ہوں…" : "Speaking…"
                        : ur ? "آواز اور چیٹ اسسٹنٹ" : "Voice & chat assistant"}
              </span>
            </span>
          </span>
        }
        actions={
          <>
            <button
              className="btn btn-ghost btn-sm gap-1 font-bold"
              onClick={() => setReplyLang(NEXT_REPLY[replyLang])}
              aria-label={`Reply language: ${REPLY_LABEL[replyLang]}`}
              title="Reply language — Auto follows each message; EN or اردو always replies in that language"
            >
              <Languages className="h-4 w-4" /> {REPLY_LABEL[replyLang]}
            </button>
            {messages.length > 0 && (
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => {
                  endConversation();
                  clear();
                }}
                aria-label="New conversation"
                title="New conversation"
              >
                <RotateCcw className="h-5 w-5" />
              </button>
            )}
          </>
        }
      />

      {basicMode && (
        <div className="border-b border-gold-200 bg-gold-50 text-gold-900 dark:border-gold-500/20 dark:bg-gold-500/10 dark:text-gold-100">
          <p className="screen flex items-start gap-2 py-2 text-xs">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              <b>Basic mode</b> — OpenAI isn't connected on the server, so answers come from listing search and voice is off. Add <code>OPENAI_API_KEY</code> to <code>backend/.env</code> and restart the backend.
            </span>
          </p>
        </div>
      )}

      <div ref={scroller} className="flex-1 overflow-y-auto">
        <div className="screen space-y-4 py-4">
          <AnimatePresence initial={false}>
            {all.map((m) => (
              <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn("flex gap-2.5", m.role === "user" && "flex-row-reverse")}>
                <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-gold-gradient text-brand-950" : "bg-brand-700 text-white")}>
                  {m.role === "assistant" ? <Bot className="h-4 w-4" /> : m.kind === "voice-note" ? <Mic className="h-4 w-4" /> : m.kind === "live" ? <Headphones className="h-4 w-4" /> : <UserIcon className="h-4 w-4" />}
                </span>
                <div className={cn("min-w-0 max-w-[85%] rounded-2xl px-3.5 py-2.5", m.role === "user" ? "rounded-tr-sm bg-brand-700 text-white" : "rounded-tl-sm bg-white text-ink shadow-card dark:bg-[#0d1f16] dark:text-slate-100")}>
                  {m.kind === "voice-note" && <VoiceNoteBar msg={m} playing={playingId === m.id} onToggle={() => void play(m)} mine={m.role === "user"} />}
                  {m.pending && !m.content ? (
                    <span className="flex gap-1 py-1.5">
                      {[0, 1, 2].map((d) => (
                        <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-brand-500" style={{ animationDelay: `${d * 0.15}s` }} />
                      ))}
                    </span>
                  ) : (
                    <div dir="auto" className={cn(isUrdu(m.content) && "urdu", m.kind === "voice-note" && "mt-1.5 text-[13px] opacity-90")}>
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
                    <div className="mt-2.5 flex flex-wrap gap-2" dir="auto">
                      {m.actions.map((a) => (
                        <button key={a.label} onClick={() => runAction(a)} className={cn("chip px-3 py-1.5", a.primary ? "bg-gold-gradient text-brand-950 shadow-glow" : "bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100")}>
                          {a.primary && <Sparkles className="h-3 w-3" />} {a.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {m.role === "assistant" && m.kind !== "voice-note" && !m.pending && m.id !== "welcome" && voice?.tts && (
                    <button onClick={() => void play(m)} className="mt-1.5 flex items-center gap-1 text-[11px] font-semibold text-ink-mute hover:text-brand-700" aria-label="Read aloud">
                      {playingId === m.id ? <Pause className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />} {playingId === m.id ? "Stop" : "Listen"}
                    </button>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {messages.length === 0 && (
            <div className="flex flex-wrap gap-2 ps-10">
              {suggestionsFor(user?.role, uiLang).map((s) => (
                <button key={s} dir="auto" onClick={() => void sendText(s)} className="chip bg-white px-3 py-1.5 text-brand-800 ring-1 ring-brand-200 transition hover:bg-brand-50 dark:bg-white/5 dark:text-brand-100 dark:ring-white/10">
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
          {live && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
              <div className="screen flex items-center gap-3 pt-3">
                <Wave active={live === "hearing" || live === "speaking"} tone={live === "speaking" ? "gold" : "green"} />
                <p className="min-w-0 flex-1 truncate text-sm font-medium text-ink-soft dark:text-slate-300">
                  {muted ? (ur ? "مائیک بند ہے" : "Microphone muted") : liveLabel(live, ur)}
                </p>
                {live === "speaking" && (
                  <button onClick={() => agent.current?.interrupt()} className="chip shrink-0 bg-brand-50 px-3 py-1.5 text-brand-800 dark:bg-white/10 dark:text-brand-100">
                    {ur ? "اب میں بولوں" : "Let me talk"}
                  </button>
                )}
                <button
                  onClick={() => {
                    const next = !muted;
                    agent.current?.setMuted(next);
                    setMuted(next);
                  }}
                  className={cn("btn btn-icon h-9 w-9 shrink-0 rounded-full", muted ? "bg-red-600 text-white" : "btn-soft")}
                  aria-label={muted ? "Unmute microphone" : "Mute microphone"}
                  disabled={live === "connecting"}
                >
                  {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {showKeyboard && !note && !inConversation && (
          <OnScreenKeyboard
            target={inputRef}
            value={input}
            onChange={setInput}
            lang={ur ? "ur" : "en"}
            onLangChange={(l) => setVoiceLang(l === "ur" ? "ur-PK" : "en-US")}
            onEnter={() => {
              void sendText(input);
              setShowKeyboard(false);
            }}
            className="screen mt-2"
          />
        )}

        <div className="screen flex items-center gap-2 py-3">
          {note ? (
            /* ---- recording a voice note ---- */
            <>
              <button onClick={() => note.session.cancel()} className="btn btn-ghost btn-icon h-11 w-11 shrink-0 rounded-full text-red-600" aria-label="Discard voice note">
                <Trash2 className="h-5 w-5" />
              </button>
              <div className="flex h-11 min-w-0 flex-1 items-center gap-3 rounded-full bg-red-50 px-4 dark:bg-red-500/10">
                <span className="relative flex h-2.5 w-2.5 shrink-0">
                  <span className="absolute inset-0 animate-ping rounded-full bg-red-500 opacity-60" />
                  <span className="relative h-2.5 w-2.5 rounded-full bg-red-600" />
                </span>
                <span className="font-mono text-sm font-semibold text-red-700 dark:text-red-300">{clock(noteClock)}</span>
                <span dir="auto" className={cn("min-w-0 flex-1 truncate text-sm text-ink-soft dark:text-slate-300", isUrdu(partial) && "urdu")}>
                  {partial || (ur ? "وائس نوٹ ریکارڈ ہو رہا ہے…" : "Recording voice note…")}
                </span>
              </div>
              <button onClick={() => note.session.stop()} className="btn btn-primary btn-icon h-12 w-12 shrink-0 rounded-full" aria-label="Send voice note">
                <Send className="h-5 w-5 rtl:rotate-180" />
              </button>
            </>
          ) : (
            <>
              <form
                className="flex min-w-0 flex-1 items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void sendText(input);
                  setShowKeyboard(false);
                }}
              >
                <div className="flex h-11 shrink-0 rounded-full bg-black/5 p-1 text-xs font-bold dark:bg-white/10" role="group" aria-label="Typing language">
                  {(["en-US", "ur-PK"] as const).map((l) => (
                    <button
                      key={l}
                      type="button"
                      aria-pressed={voiceLang === l}
                      onClick={() => {
                        setVoiceLang(l);
                        // Touch keyboards don't report letter keys, so open the on-screen keyboard there for Urdu.
                        if (l === "ur-PK" && matchMedia("(pointer: coarse)").matches) setShowKeyboard(true);
                        inputRef.current?.focus();
                      }}
                      className={cn("rounded-full px-2.5 transition", voiceLang === l ? "bg-white text-brand-800 shadow-sm dark:bg-brand-700 dark:text-white" : "text-ink-mute")}
                    >
                      {l === "en-US" ? "EN" : "اردو"}
                    </button>
                  ))}
                </div>
                <div className="relative min-w-0 flex-1">
                  <input
                    ref={inputRef}
                    dir={ur ? "rtl" : "auto"}
                    lang={ur ? "ur" : "en"}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={ur ? (e) => phoneticKeyDown(e, input, setInput) : undefined}
                    inputMode={showKeyboard ? "none" : "text"}
                    placeholder={ur ? "اردو میں لکھیں…" : "Type a message…"}
                    className={cn("input h-11 w-full rounded-full pe-11", (ur || isUrdu(input)) && "urdu")}
                    disabled={phase === "thinking" || inConversation}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setShowKeyboard((v) => !v);
                      inputRef.current?.focus();
                    }}
                    className={cn("absolute inset-y-0 end-1.5 my-auto flex h-8 w-8 items-center justify-center rounded-full transition", showKeyboard ? "bg-brand-700 text-white" : "text-ink-mute hover:bg-black/5 dark:hover:bg-white/10")}
                    aria-label={showKeyboard ? "Hide on-screen keyboard" : "Show on-screen keyboard"}
                    title={ur ? "آن اسکرین کی بورڈ" : "On-screen keyboard"}
                  >
                    <Keyboard className="h-4 w-4" />
                  </button>
                </div>
                {input.trim() ? (
                  <button type="submit" className="btn btn-primary btn-icon h-11 w-11 shrink-0 rounded-full" disabled={phase === "thinking"} aria-label="Send">
                    <Send className="h-4 w-4 rtl:rotate-180" />
                  </button>
                ) : (
                  voiceReady !== false &&
                  !inConversation && (
                    <button type="button" onClick={() => void startNote()} className="btn btn-soft btn-icon h-11 w-11 shrink-0 rounded-full" disabled={phase === "thinking"} aria-label="Record a voice note" title={ur ? "وائس نوٹ" : "Voice note"}>
                      <Mic className="h-5 w-5" />
                    </button>
                  )
                )}
              </form>
              {voiceReady !== false && (
                <button
                  onClick={() => (inConversation ? endConversation() : void startConversation())}
                  disabled={!inConversation && (phase === "thinking" || phase === "recording")}
                  aria-label={inConversation ? "End voice conversation" : "Start voice conversation"}
                  title={ur ? "آواز میں گفتگو" : "Voice conversation"}
                  className={cn(
                    "relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-glow transition active:scale-95 disabled:opacity-60",
                    inConversation ? "bg-red-600 text-white" : "bg-gold-gradient text-brand-950",
                  )}
                >
                  {live === "hearing" && <span className="absolute inset-0 animate-pulse-ring rounded-full bg-red-500/50" />}
                  {inConversation ? <Square className="relative h-5 w-5 fill-current" /> : <Headphones className="relative h-5 w-5" />}
                </button>
              )}
            </>
          )}
        </div>

        <p className="screen -mt-1 pb-2 text-[11px] text-ink-mute dark:text-slate-500">
          {voiceReady === false
            ? "Voice is off: the server needs OPENAI_API_KEY. You can still type."
            : inConversation
              ? ur
                ? "براہِ راست گفتگو — جب چاہیں بولیں، بیچ میں بھی ٹوک سکتے ہیں۔ ختم کرنے کے لیے ■ دبائیں۔"
                : "Live conversation — speak any time, even to interrupt. Tap ■ to hang up."
              : ur
                ? "اردو کی بورڈ: a=ا b=ب p=پ t=ت … (Shift سے مزید حروف) · ⌨ آن اسکرین کی بورڈ · 🎤 وائس نوٹ · 🎧 گفتگو"
                : "Type or tap ⌨ for the on-screen keyboard · 🎤 voice note · 🎧 voice conversation — I reply in your language."}
        </p>
      </div>
    </div>
  );
}

function liveLabel(state: AgentState, ur: boolean): string {
  const labels: Record<AgentState, [string, string]> = {
    connecting: ["Connecting to the voice agent…", "وائس ایجنٹ سے رابطہ ہو رہا ہے…"],
    listening: ["Listening — speak any time", "سن رہا ہوں — جب چاہیں بولیں"],
    hearing: ["Hearing you…", "آپ کی بات سن رہا ہوں…"],
    thinking: ["Thinking…", "سوچ رہا ہوں…"],
    speaking: ["Speaking — talk to interrupt", "بول رہا ہوں — بات کاٹنے کے لیے بولیں"],
  };
  return labels[state][ur ? 1 : 0];
}

function Wave({ active, tone }: { active: boolean; tone: "green" | "gold" }) {
  return (
    <div className="flex h-8 items-center gap-1">
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={cn("h-full w-1 origin-center rounded-full", active ? cn("animate-wave", tone === "gold" ? "bg-gold-500" : "bg-brand-500") : "scale-y-[.35] bg-ink-mute/40")}
          style={{ animationDelay: `${i * 0.12}s` }}
        />
      ))}
    </div>
  );
}

/** WhatsApp-style voice-note player row. */
function VoiceNoteBar({ msg, playing, onToggle, mine }: { msg: ChatMsg; playing: boolean; onToggle: () => void; mine: boolean }) {
  const bars = [6, 12, 18, 10, 22, 14, 8, 20, 12, 16, 9, 18, 11, 7, 15, 10, 19, 8];
  const ready = !msg.pending;
  return (
    <div className="flex min-w-[200px] items-center gap-3" dir="ltr">
      <button
        onClick={onToggle}
        disabled={!ready}
        className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition active:scale-95 disabled:opacity-50", mine ? "bg-white/20 text-white" : "bg-brand-700 text-white")}
        aria-label={playing ? "Pause voice note" : "Play voice note"}
      >
        {playing ? <Pause className="h-4 w-4 fill-current" /> : <Play className="ms-0.5 h-4 w-4 fill-current" />}
      </button>
      <div className="flex h-8 flex-1 items-center gap-[3px]">
        {bars.map((h, i) => (
          <span key={i} className={cn("w-[3px] rounded-full", mine ? "bg-white/70" : "bg-brand-500/70", playing && "animate-wave")} style={{ height: h, animationDelay: `${(i % 6) * 0.1}s` }} />
        ))}
      </div>
      <span className={cn("shrink-0 font-mono text-[11px]", mine ? "text-white/80" : "text-ink-mute")}>{msg.durationMs ? clock(msg.durationMs) : ready ? "🔊" : "…"}</span>
    </div>
  );
}
