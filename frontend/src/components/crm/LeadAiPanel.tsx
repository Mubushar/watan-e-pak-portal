/**
 * AI for one lead, inside the lead drawer:
 *   brief    summary, temperature, next best action, follow-up date, talking points, risks,
 *            and ready WhatsApp / SMS / e-mail drafts (English or Urdu) — one click to send
 *   note     record a voice note (or type one): transcribed, summarised, logged on the timeline,
 *            follow-up tasks created, budget filled, status suggested
 */
import { useState } from "react";
import { AlertTriangle, CalendarClock, Loader2, Mail, MessageCircle, MessageSquareText, Mic, Sparkles, Square, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { post, put } from "@/lib/api";
import { date, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, Segmented, Textarea } from "@/components/ui";
import { ComposeModal, type Channel } from "./ComposeModal";
import { useRecorder } from "./useRecorder";
import type { LeadBrief, NoteResult } from "./types";

const TEMP_TONE = { hot: "red", warm: "orange", cold: "blue" } as const;
const URGENCY_TONE = { urgent: "red", high: "orange", medium: "gold", low: "gray" } as const;

export function LeadAiPanel({ leadId, name, onChanged }: { leadId: string; name: string; onChanged?: () => void }) {
  const qc = useQueryClient();
  const [lang, setLang] = useState<"en" | "ur">("en");
  const [brief, setBrief] = useState<LeadBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [compose, setCompose] = useState<{ channel: Channel; body: string; subject?: string } | null>(null);
  const [noteText, setNoteText] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);
  const [note, setNote] = useState<NoteResult | null>(null);

  const refresh = () => {
    void qc.invalidateQueries({ predicate: (q) => /^\/(crm|agents|broker)/.test(String(q.queryKey[0] ?? "")) });
    onChanged?.();
  };

  const loadBrief = async (l = lang) => {
    setLoading(true);
    try {
      setBrief(await post<LeadBrief>(`/crm/ai/lead-brief/${leadId}?lang=${l}`));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const saveNote = async (audio?: { base64: string; mime: string }) => {
    if (!audio && !noteText.trim()) return;
    setNoteBusy(true);
    try {
      const r = await post<NoteResult>("/crm/ai/note", {
        entity_type: "lead",
        entity_id: leadId,
        text: audio ? undefined : noteText,
        audio_base64: audio?.base64,
        mime_type: audio?.mime,
        apply: true,
      });
      setNote(r);
      setNoteText("");
      toast.success(`Note saved${r.applied?.tasks.length ? ` · ${r.applied.tasks.length} follow-up task${r.applied.tasks.length > 1 ? "s" : ""} created` : ""}`);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setNoteBusy(false);
    }
  };
  const rec = useRecorder((r) => void saveNote({ base64: r.base64, mime: r.mime }));

  const applyStatus = async (status: string) => {
    try {
      await put(`/crm/leads/${leadId}`, { status });
      toast.success(`Status set to ${titleCase(status)}`);
      setNote((n) => (n ? { ...n, analysis: { ...n.analysis, status_suggestion: null } } : n));
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="space-y-4 rounded-2xl border border-violet-200 bg-gradient-to-br from-violet-50 via-white to-gold-50/40 p-4 dark:border-violet-500/20 dark:from-violet-500/10 dark:via-transparent dark:to-transparent">
      {/* ---- brief */}
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-violet-600" />
        <p className="text-sm font-bold">AI sales assistant</p>
        <Segmented<"en" | "ur">
          size="sm"
          value={lang}
          onChange={(l) => {
            setLang(l);
            if (brief) void loadBrief(l);
          }}
          options={[
            { value: "en", label: "EN" },
            { value: "ur", label: "اردو" },
          ]}
        />
        <Button size="sm" variant="gold" className="ms-auto" icon={<Wand2 className="h-4 w-4" />} loading={loading} onClick={() => loadBrief()}>
          {brief ? "Refresh brief" : "Brief me"}
        </Button>
      </div>

      {brief && (
        <div className="space-y-3 text-sm" dir={lang === "ur" ? "rtl" : undefined}>
          <div className="flex flex-wrap items-center gap-1.5" dir="ltr">
            <Badge tone={TEMP_TONE[brief.temperature as keyof typeof TEMP_TONE] ?? "gray"} className="capitalize">
              {brief.temperature}
            </Badge>
            <Badge tone={URGENCY_TONE[brief.urgency as keyof typeof URGENCY_TONE] ?? "gray"} className="capitalize">
              {brief.urgency}
            </Badge>
            <Badge tone="gray" icon={<CalendarClock className="h-3 w-3" />}>
              Follow up {date(brief.follow_up_date)}
            </Badge>
            <Badge tone={brief.source === "ai" ? "purple" : "gray"} className="ms-auto">
              {brief.source === "ai" ? "AI" : "Rules"}
            </Badge>
          </div>
          <p className={cn("leading-relaxed", lang === "ur" && "map-ur text-base")}>{brief.summary}</p>
          <div className="rounded-xl bg-white/80 p-3 dark:bg-white/5">
            <p className="text-[11px] font-bold uppercase tracking-wider text-violet-700 dark:text-violet-300">Next best action · {titleCase(brief.channel)}</p>
            <p className={cn("mt-0.5 font-semibold", lang === "ur" && "map-ur")}>{brief.next_best_action}</p>
          </div>
          {!!brief.talking_points.length && (
            <ul className="list-inside list-disc space-y-0.5 text-xs text-ink-soft dark:text-slate-300">
              {brief.talking_points.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          )}
          {!!brief.risks.length && (
            <div className="space-y-0.5 text-xs text-red-700 dark:text-red-300">
              {brief.risks.map((r) => (
                <p key={r} className="flex items-start gap-1.5">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {r}
                </p>
              ))}
            </div>
          )}
          <div className="grid gap-2 sm:grid-cols-3" dir="ltr">
            <Button size="sm" variant="soft" icon={<MessageCircle className="h-4 w-4" />} onClick={() => setCompose({ channel: "whatsapp", body: brief.drafts.whatsapp })}>
              WhatsApp draft
            </Button>
            <Button size="sm" variant="soft" icon={<MessageSquareText className="h-4 w-4" />} onClick={() => setCompose({ channel: "sms", body: brief.drafts.sms })}>
              SMS draft
            </Button>
            <Button size="sm" variant="soft" icon={<Mail className="h-4 w-4" />} onClick={() => setCompose({ channel: "email", body: brief.drafts.email_body, subject: brief.drafts.email_subject })}>
              E-mail draft
            </Button>
          </div>
        </div>
      )}

      {/* ---- voice / text note */}
      <div className="border-t border-violet-200/70 pt-3 dark:border-white/10">
        <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Voice or typed note</p>
        <div className="flex items-start gap-2">
          <button
            type="button"
            onClick={rec.toggle}
            disabled={noteBusy}
            className={cn(
              "flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white shadow-soft transition",
              rec.recording ? "animate-pulse bg-red-600" : "bg-violet-600 hover:bg-violet-700",
            )}
            title={rec.recording ? "Stop and save" : "Record a voice note (English / Urdu)"}
            aria-label={rec.recording ? "Stop recording" : "Record a voice note"}
          >
            {noteBusy ? <Loader2 className="h-5 w-5 animate-spin" /> : rec.recording ? <Square className="h-4 w-4" /> : <Mic className="h-5 w-5" />}
          </button>
          <Textarea
            value={rec.recording ? `Recording… ${rec.seconds}s — tap ■ to finish` : noteText}
            readOnly={rec.recording}
            onChange={(e) => setNoteText(e.target.value)}
            rows={2}
            dir="auto"
            className="min-h-[44px] flex-1 text-sm"
            placeholder="e.g. Called — liked the 10 marla in DHA, budget 3.5 crore, site visit tomorrow 5pm"
          />
          <Button size="sm" disabled={!noteText.trim() || noteBusy || rec.recording} loading={noteBusy && !rec.recording} onClick={() => saveNote()}>
            Save
          </Button>
        </div>
        {rec.error && <p className="mt-1 text-xs text-red-600">{rec.error}</p>}
        {note && (
          <div className="mt-3 space-y-1.5 rounded-xl bg-white/80 p-3 text-xs dark:bg-white/5">
            {note.transcript !== note.analysis.summary && <p className="italic text-ink-mute">“{note.transcript}”</p>}
            <p className="text-sm font-medium">{note.analysis.summary}</p>
            <div className="flex flex-wrap gap-1.5">
              <Badge tone={note.analysis.sentiment === "positive" ? "green" : note.analysis.sentiment === "negative" ? "red" : "gray"} className="capitalize">
                {note.analysis.sentiment}
              </Badge>
              {note.analysis.budget_pkr ? <Badge tone="gold">Budget {pkrShort(note.analysis.budget_pkr)}</Badge> : null}
              {note.analysis.follow_up_date && <Badge tone="blue">Follow up {date(note.analysis.follow_up_date)}</Badge>}
              <Badge tone={note.analysis.source === "ai" ? "purple" : "gray"}>{note.analysis.source === "ai" ? "AI" : "Rules"}</Badge>
            </div>
            {!!note.analysis.tasks.length && <p>Tasks created: {note.analysis.tasks.map((t) => t.title).join(" · ")}</p>}
            {note.analysis.status_suggestion && (
              <div className="flex items-center gap-2 pt-1">
                <span>Suggested status: <b className="capitalize">{note.analysis.status_suggestion}</b></span>
                <Button size="sm" variant="soft" onClick={() => applyStatus(note.analysis.status_suggestion!)}>
                  Apply
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      <ComposeModal
        open={!!compose}
        onClose={() => setCompose(null)}
        entityId={leadId}
        name={name}
        channel={compose?.channel}
        body={compose?.body}
        subject={compose?.subject}
      />
    </div>
  );
}
