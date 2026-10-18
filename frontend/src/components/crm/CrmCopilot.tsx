/**
 * CRM copilot: ask the CRM in text or by voice ("who should I call first?", "deals at risk?",
 * "leads in Lahore") — answers come from live CRM data (POST /crm/ai/ask) and can be spoken back.
 * Push-to-talk conversation: tap the mic, speak (English / Urdu / Roman Urdu), tap again.
 */
import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, Mic, Send, Sparkles, Square, Volume2, VolumeX } from "lucide-react";
import { toast } from "sonner";
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge, Drawer, Segmented } from "@/components/ui";
import { useRecorder } from "./useRecorder";
import type { AskResult } from "./types";

interface Turn {
  role: "user" | "bot";
  text: string;
  source?: "ai" | "rules";
  leadIds?: string[];
  voice?: boolean;
}

const SUGGESTIONS = ["Who should I call first today?", "Which deals are at risk?", "What's overdue?", "How is the pipeline?", "Best agent this month?", "Leads in Lahore"];

/** Minimal markdown: **bold** and "- " bullets. */
function Rich({ text }: { text: string }) {
  return (
    <div className="space-y-1">
      {text.split("\n").map((line, i) => {
        const bullet = /^\s*[-•*]\s+/.test(line);
        const parts = line.replace(/^\s*[-•*]\s+/, "").split(/(\*\*[^*]+\*\*)/g);
        const body = parts.map((p, k) => (p.startsWith("**") && p.endsWith("**") ? <b key={k}>{p.slice(2, -2)}</b> : <span key={k}>{p}</span>));
        return line.trim() ? (
          <p key={i} className={cn(bullet && "ps-3 before:-ms-3 before:me-1.5 before:content-['•']")} dir="auto">
            {body}
          </p>
        ) : null;
      })}
    </div>
  );
}

export function CrmCopilot({ open, onClose, onOpenLead, initial }: { open: boolean; onClose: () => void; onOpenLead?: (id: string) => void; initial?: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [lang, setLang] = useState<"en" | "ur">("en");
  const [speak, setSpeak] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const asked = useRef<string | null>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, busy]);

  const ask = async (q: { question?: string; audio?: { base64: string; mime: string } }) => {
    if (busy) return;
    if (q.question) setTurns((t) => [...t, { role: "user", text: q.question! }]);
    setBusy(true);
    try {
      const r = await post<AskResult>("/crm/ai/ask", {
        question: q.question,
        audio_base64: q.audio?.base64,
        mime_type: q.audio?.mime,
        lang,
        speak: speak || !!q.audio,
      });
      setTurns((t) => [
        ...(q.audio ? [...t, { role: "user" as const, text: r.transcript || r.question, voice: true }] : t),
        { role: "bot", text: r.answer, source: r.source, leadIds: r.lead_ids },
      ]);
      if (r.audio_base64 && (speak || q.audio)) {
        audio.current?.pause();
        audio.current = new Audio(`data:${r.mime_type ?? "audio/mpeg"};base64,${r.audio_base64}`);
        void audio.current.play().catch(() => undefined);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const rec = useRecorder((r) => void ask({ audio: { base64: r.base64, mime: r.mime } }), 60);

  // A question handed in from the dashboard's quick-ask box.
  useEffect(() => {
    if (open && initial && asked.current !== initial) {
      asked.current = initial;
      void ask({ question: initial });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initial]);
  useEffect(() => () => audio.current?.pause(), []);

  const submit = () => {
    const q = text.trim();
    if (!q) return;
    setText("");
    void ask({ question: q });
  };

  return (
    <Drawer open={open} onClose={onClose} title="CRM copilot" width="max-w-lg">
      <div className="flex h-full min-h-[70vh] flex-col">
        <div className="flex items-center gap-2 border-b border-black/5 pb-3 dark:border-white/10">
          <Segmented<"en" | "ur">
            size="sm"
            value={lang}
            onChange={setLang}
            options={[
              { value: "en", label: "English" },
              { value: "ur", label: "اردو" },
            ]}
          />
          <button
            type="button"
            onClick={() => setSpeak((s) => !s)}
            className={cn("btn btn-sm ms-auto", speak ? "btn-soft" : "btn-ghost")}
            title="Speak answers aloud (voice replies always speak)"
          >
            {speak ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />} {speak ? "Speaking" : "Silent"}
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto py-4">
          {!turns.length && (
            <div className="space-y-3 text-center">
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-600 text-white shadow-glow">
                <Bot className="h-7 w-7" />
              </span>
              <p className="text-sm text-ink-soft dark:text-slate-300">Ask about your leads, deals, tasks and team — type, or tap the mic and speak in English or Urdu.</p>
              <div className="flex flex-wrap justify-center gap-1.5">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => void ask({ question: s })} className="chip bg-violet-50 text-xs text-violet-800 hover:bg-violet-100 dark:bg-violet-500/15 dark:text-violet-100">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className={cn("flex", t.role === "user" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm",
                  t.role === "user" ? "rounded-br-md bg-brand-700 text-white" : "rounded-bl-md bg-black/[.04] dark:bg-white/[.06]",
                )}
              >
                {t.voice && <Mic className="me-1 inline h-3.5 w-3.5 opacity-70" />}
                {t.role === "bot" ? <Rich text={t.text} /> : <span dir="auto">{t.text}</span>}
                {t.role === "bot" && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <Badge tone={t.source === "ai" ? "purple" : "gray"} icon={<Sparkles className="h-3 w-3" />}>
                      {t.source === "ai" ? "AI" : "Rules"}
                    </Badge>
                    {onOpenLead &&
                      (t.leadIds ?? []).slice(0, 5).map((id, k) => (
                        <button key={id} type="button" onClick={() => onOpenLead(id)} className="chip bg-white text-[11px] font-semibold text-brand-700 ring-1 ring-black/5 hover:bg-brand-50 dark:bg-white/10 dark:text-brand-200">
                          Open lead {k + 1}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-xs text-ink-mute">
              <Loader2 className="h-4 w-4 animate-spin" /> Thinking…
            </div>
          )}
          <div ref={end} />
        </div>

        <div className="flex items-end gap-2 border-t border-black/5 pt-3 dark:border-white/10">
          <button
            type="button"
            onClick={rec.toggle}
            disabled={busy && !rec.recording}
            className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white transition", rec.recording ? "animate-pulse bg-red-600" : "bg-violet-600 hover:bg-violet-700")}
            aria-label={rec.recording ? "Stop and ask" : "Ask by voice"}
            title={rec.recording ? "Stop and ask" : "Ask by voice"}
          >
            {rec.recording ? <Square className="h-4 w-4" /> : <Mic className="h-5 w-5" />}
          </button>
          <textarea
            value={rec.recording ? `Listening… ${rec.seconds}s` : text}
            readOnly={rec.recording}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            dir="auto"
            placeholder="Ask the CRM…"
            className="input max-h-32 min-h-[44px] flex-1 resize-none text-sm"
          />
          <button type="button" onClick={submit} disabled={!text.trim() || busy} className="btn btn-primary h-11 w-11 shrink-0 !p-0" aria-label="Send">
            <Send className="h-4 w-4" />
          </button>
        </div>
        {rec.error && <p className="mt-1 text-xs text-red-600">{rec.error}</p>}
      </div>
    </Drawer>
  );
}
