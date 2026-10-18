/**
 * Write and send a WhatsApp, SMS or e-mail to a lead / customer: AI draft by goal, tone and
 * language (English / Urdu), edit, send. Sent (or simulated) messages land on the timeline.
 */
import { useEffect, useState } from "react";
import { Mail, MessageCircle, MessageSquareText, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { post } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Field, Input, Modal, Segmented, Select, Textarea } from "@/components/ui";
import { GOALS, type Draft, type SendResult } from "./types";

export type Channel = "whatsapp" | "sms" | "email";

export function ComposeModal({
  open,
  onClose,
  entityType = "lead",
  entityId,
  name,
  channel: initialChannel = "whatsapp",
  subject: initialSubject,
  body: initialBody,
}: {
  open: boolean;
  onClose: () => void;
  entityType?: "lead" | "customer";
  entityId: string | null;
  name?: string;
  channel?: Channel;
  subject?: string;
  body?: string;
}) {
  const qc = useQueryClient();
  const [channel, setChannel] = useState<Channel>(initialChannel);
  const [goal, setGoal] = useState("follow_up");
  const [lang, setLang] = useState<"en" | "ur">("en");
  const [tone, setTone] = useState("friendly");
  const [subject, setSubject] = useState(initialSubject ?? "");
  const [body, setBody] = useState(initialBody ?? "");
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [source, setSource] = useState<"ai" | "rules" | null>(null);

  useEffect(() => {
    if (!open) return;
    setChannel(initialChannel);
    setSubject(initialSubject ?? "");
    setBody(initialBody ?? "");
    setSource(null);
  }, [open, initialChannel, initialSubject, initialBody]);

  const draft = async () => {
    if (!entityId) return;
    setDrafting(true);
    try {
      const d = await post<Draft>("/crm/ai/draft", { entity_type: entityType, entity_id: entityId, channel, goal, lang, tone });
      setBody(d.body);
      if (d.subject) setSubject(d.subject);
      setSource(d.source);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDrafting(false);
    }
  };

  const send = async () => {
    setSending(true);
    try {
      const r = await post<SendResult>("/crm/messages/send", { channel, body, subject: channel === "email" ? subject : undefined, entity_type: entityType, entity_id: entityId });
      if (r.status === "sent") toast.success(`Sent by ${channel === "email" ? "e-mail" : channel === "sms" ? "SMS" : "WhatsApp"} to ${r.to}`);
      else toast.message("Logged on the timeline (simulated)", { description: `${channel} isn't configured yet — see CRM › Channels.` });
      void qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0] ?? "").startsWith("/crm") });
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const limit = channel === "sms" ? 300 : channel === "whatsapp" ? 4096 : 10000;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Message ${name ?? ""}`.trim()}
      subtitle="Draft with AI, edit, send — it is logged on the timeline."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button icon={<Send className="h-4 w-4" />} loading={sending} disabled={!body.trim() || (channel === "email" && !subject.trim())} onClick={send}>
            Send
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Segmented<Channel>
          value={channel}
          onChange={setChannel}
          options={[
            { value: "whatsapp", label: "WhatsApp", icon: <MessageCircle className="h-4 w-4" /> },
            { value: "sms", label: "SMS", icon: <MessageSquareText className="h-4 w-4" /> },
            { value: "email", label: "E-mail", icon: <Mail className="h-4 w-4" /> },
          ]}
        />
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Goal">
            <Select value={goal} onChange={(e) => setGoal(e.target.value)} options={GOALS} />
          </Field>
          <Field label="Tone">
            <Select value={tone} onChange={(e) => setTone(e.target.value)} options={["friendly", "professional", "concise", "warm and persuasive"]} />
          </Field>
          <Field label="Language">
            <Select value={lang} onChange={(e) => setLang(e.target.value as "en" | "ur")} options={[{ value: "en", label: "English" }, { value: "ur", label: "اردو Urdu" }]} />
          </Field>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="gold" size="sm" icon={<Sparkles className="h-4 w-4" />} loading={drafting} disabled={!entityId} onClick={draft}>
            Write with AI
          </Button>
          {source && <Badge tone={source === "ai" ? "purple" : "gray"}>{source === "ai" ? "AI draft" : "Template draft"}</Badge>}
        </div>
        {channel === "email" && (
          <Field label="Subject">
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject" />
          </Field>
        )}
        <Field label={`Message${channel === "sms" ? ` (${body.length}/${limit})` : ""}`}>
          <Textarea value={body} onChange={(e) => setBody(e.target.value.slice(0, limit))} rows={channel === "email" ? 9 : 6} dir="auto" placeholder="Type a message or let AI write it" />
        </Field>
      </div>
    </Modal>
  );
}
