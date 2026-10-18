/**
 * Channels: which outbound channels really send (WhatsApp Cloud API, SMTP e-mail, SMS gateway),
 * how to switch each on, the inbound webhooks for website forms / Facebook & Instagram lead ads /
 * WhatsApp, and a test send.
 */
import { useState } from "react";
import { Bot, CheckCircle2, CircleDashed, Facebook, Globe, Mail, MessageCircle, MessageSquareText, Mic, Send, Webhook } from "lucide-react";
import { toast } from "sonner";
import { post, API_BASE } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { Badge, Button, CopyButton, ErrorState, Field, Input, Segmented, Skeleton, Textarea } from "@/components/ui";
import { Panel } from "@/components/biz/ops-kit";
import type { Channel } from "./ComposeModal";
import type { ChannelStatus, SendResult } from "./types";

function Live({ on, label }: { on: boolean; label?: string }) {
  return on ? (
    <Badge tone="green" icon={<CheckCircle2 className="h-3 w-3" />}>
      {label ?? "Live"}
    </Badge>
  ) : (
    <Badge tone="gray" icon={<CircleDashed className="h-3 w-3" />}>
      {label ?? "Simulated"}
    </Badge>
  );
}

const FB_EXAMPLE = `{
  "field_data": [
    {"name": "full_name", "values": ["Ali Raza"]},
    {"name": "phone_number", "values": ["0300-1234567"]},
    {"name": "city", "values": ["Lahore"]},
    {"name": "budget", "values": ["2 crore"]}
  ]
}`;

export function CrmChannelsTab() {
  const q = useApi<ChannelStatus>("/crm/channels");
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [to, setTo] = useState("");
  const [body, setBody] = useState("Test message from Arz-e-Pak CRM");
  const [sending, setSending] = useState(false);
  const base = API_BASE.startsWith("http") ? API_BASE : `${window.location.origin}${API_BASE}`;

  const test = async () => {
    setSending(true);
    try {
      const r = await post<SendResult>("/crm/messages/send", { channel, to, body, subject: channel === "email" ? "Arz-e-Pak CRM test" : undefined, entity_id: null });
      if (r.status === "sent") toast.success(`Delivered to ${r.to} via ${r.provider}`);
      else toast.message("Simulated — this channel is not configured yet");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data;
  return (
    <div className="space-y-5 p-4 sm:p-5">
      {!s ? (
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Panel title="WhatsApp" subtitle="Meta WhatsApp Business Cloud API" icon={<MessageCircle className="h-5 w-5" />} action={<Live on={s.whatsapp.live} />}>
              <p className="text-sm text-ink-soft dark:text-slate-300">
                Free-text replies reach people who messaged you in the last 24 h; outside that window WhatsApp needs an approved template
                {s.whatsapp.template ? ` (using “${s.whatsapp.template}”)` : " (set PORTAL_WHATSAPP_CRM_TEMPLATE)"}.
              </p>
              <code className="mt-3 block rounded-lg bg-black/5 px-2 py-1.5 text-[11px] dark:bg-white/10">{s.whatsapp.setup}</code>
            </Panel>
            <Panel title="E-mail" subtitle="Any SMTP server (Gmail, Zoho, SES, cPanel…)" icon={<Mail className="h-5 w-5" />} action={<Live on={s.email.live} />}>
              <p className="text-sm text-ink-soft dark:text-slate-300">Proposals, payment plans and follow-ups go out from your own mailbox.</p>
              <code className="mt-3 block rounded-lg bg-black/5 px-2 py-1.5 text-[11px] dark:bg-white/10">{s.email.setup}</code>
            </Panel>
            <Panel title="SMS" subtitle="Twilio or any Pakistani bulk-SMS gateway" icon={<MessageSquareText className="h-5 w-5" />} action={<Live on={s.sms.live} />}>
              <p className="text-sm text-ink-soft dark:text-slate-300">Short reminders for visits and token dates, up to 300 characters.</p>
              <code className="mt-3 block rounded-lg bg-black/5 px-2 py-1.5 text-[11px] dark:bg-white/10">{s.sms.setup}</code>
            </Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Inbound leads" subtitle="Website forms, Facebook / Instagram lead ads, property portals" icon={<Webhook className="h-5 w-5" />}>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="mb-1 text-xs font-semibold text-ink-mute">Lead webhook (POST JSON) · add ?source=facebook, instagram, zameen …</p>
                  <div className="flex items-center gap-2 rounded-lg bg-black/5 px-2 py-1.5 dark:bg-white/10">
                    <code className="min-w-0 flex-1 truncate text-[11px]">{base + s.inbound.lead_webhook}</code>
                    <CopyButton text={base + s.inbound.lead_webhook} />
                  </div>
                  <p className="mt-1 text-[11px] text-ink-mute">
                    {s.inbound.lead_webhook_secured ? "Secured: send the X-Webhook-Secret header." : "Tip: set PORTAL_CRM_WEBHOOK_SECRET and send it as X-Webhook-Secret."} Duplicates (same phone / e-mail) are merged; new leads are routed to an agent.
                  </p>
                </div>
                <div>
                  <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-ink-mute">
                    <Facebook className="h-3.5 w-3.5" /> Facebook / Instagram lead ads via Zapier or Make — sample body
                  </p>
                  <pre className="overflow-x-auto rounded-lg bg-black/5 p-2 text-[11px] dark:bg-white/10">{FB_EXAMPLE}</pre>
                </div>
                <div>
                  <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-ink-mute">
                    <MessageCircle className="h-3.5 w-3.5" /> WhatsApp webhook (Meta app → Webhooks → messages)
                  </p>
                  <div className="flex items-center gap-2 rounded-lg bg-black/5 px-2 py-1.5 dark:bg-white/10">
                    <code className="min-w-0 flex-1 truncate text-[11px]">{base + s.inbound.whatsapp_webhook}</code>
                    <CopyButton text={base + s.inbound.whatsapp_webhook} />
                  </div>
                  <p className="mt-1 text-[11px] text-ink-mute">
                    Verify token {s.inbound.whatsapp_verify_token_set ? "is set" : "not set — PORTAL_WHATSAPP_VERIFY_TOKEN"}. Incoming messages land on the sender's lead (new numbers become leads).
                  </p>
                </div>
              </div>
            </Panel>

            <Panel title="Test a channel" subtitle="Send one message without a lead" icon={<Send className="h-5 w-5" />}>
              <div className="space-y-3">
                <Segmented<Channel>
                  size="sm"
                  value={channel}
                  onChange={setChannel}
                  options={[
                    { value: "whatsapp", label: "WhatsApp" },
                    { value: "sms", label: "SMS" },
                    { value: "email", label: "E-mail" },
                  ]}
                />
                <Field label={channel === "email" ? "E-mail address" : "Mobile number"}>
                  <Input value={to} onChange={(e) => setTo(e.target.value)} placeholder={channel === "email" ? "name@example.com" : "0300 1234567"} />
                </Field>
                <Field label="Message">
                  <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} dir="auto" />
                </Field>
                <Button icon={<Send className="h-4 w-4" />} loading={sending} disabled={!to.trim() || !body.trim()} onClick={test}>
                  Send test
                </Button>
              </div>
              <div className="mt-4 grid gap-2 border-t border-black/5 pt-3 text-sm dark:border-white/10 sm:grid-cols-2">
                <p className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-violet-600" /> AI writing & copilot <Live on={!!s.ai} label={s.ai ? "On" : "Rules only"} />
                </p>
                <p className="flex items-center gap-2">
                  <Mic className="h-4 w-4 text-violet-600" /> Voice notes <Live on={!!s.voice} label={s.voice ? "On" : "Needs OpenAI key"} />
                </p>
                <p className="flex items-center gap-2 sm:col-span-2 text-[11px] text-ink-mute">
                  <Globe className="h-3.5 w-3.5" /> Social posts and ad copy: Marketing › Content. Campaign plans: Marketing › Campaigns.
                </p>
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
