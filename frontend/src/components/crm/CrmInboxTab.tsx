/**
 * CRM inbox: every call, note, voice note, WhatsApp, SMS, e-mail and web enquiry across the CRM,
 * newest first — filter by channel and direction, open the lead, reply in one click.
 */
import { useMemo, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, CalendarCheck, Globe, Mail, MessageCircle, MessageSquareText, Mic, NotebookPen, Phone, Reply, Users } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, EmptyState, ErrorState, Segmented, Skeleton } from "@/components/ui";
import type { Interaction, LeadsRes } from "@/components/biz/crm-types";
import { ComposeModal, type Channel } from "./ComposeModal";

const ICON: Record<string, typeof Phone> = {
  call: Phone,
  whatsapp: MessageCircle,
  sms: MessageSquareText,
  email: Mail,
  meeting: Users,
  site_visit: CalendarCheck,
  voice_note: Mic,
  note: NotebookPen,
  web: Globe,
  website: Globe,
};
const COLOR: Record<string, string> = {
  whatsapp: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  email: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  sms: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
  call: "bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200",
  voice_note: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  note: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
};

type Filter = "all" | "messages" | "calls" | "notes" | "inbound";

export function CrmInboxTab({ onOpenLead }: { onOpenLead: (id: string) => void }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [reply, setReply] = useState<{ id: string; name: string; channel: Channel } | null>(null);
  const q = useApi<{ count: number; interactions: Interaction[] }>("/crm/interactions", { limit: 300 }, { refetchInterval: 30_000 });
  const leadsQ = useApi<LeadsRes>("/crm/leads");
  const leads = useMemo(() => Object.fromEntries((leadsQ.data?.leads ?? []).map((l) => [l.id, l])), [leadsQ.data]);

  const rows = (q.data?.interactions ?? []).filter((i) =>
    filter === "all"
      ? true
      : filter === "messages"
        ? ["whatsapp", "sms", "email"].includes(i.channel)
        : filter === "calls"
          ? ["call", "meeting", "site_visit"].includes(i.channel)
          : filter === "notes"
            ? ["note", "voice_note"].includes(i.channel)
            : i.direction === "inbound",
  );

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="space-y-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented<Filter>
          size="sm"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All" },
            { value: "inbound", label: "Inbound" },
            { value: "messages", label: "Messages" },
            { value: "calls", label: "Calls & visits" },
            { value: "notes", label: "Notes" },
          ]}
        />
        <span className="text-xs text-ink-mute">{rows.length} items · refreshes every 30 s</span>
      </div>
      {q.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : !rows.length ? (
        <EmptyState title="Nothing here yet" hint="Calls, notes, messages and web enquiries appear here as they happen." />
      ) : (
        <ul className="divide-y divide-black/5 rounded-2xl border border-black/5 dark:divide-white/10 dark:border-white/10">
          {rows.map((i) => {
            const Icon = ICON[i.channel] ?? MessageSquareText;
            const lead = i.entity_type === "lead" ? leads[i.entity_id] : undefined;
            const name = lead?.name ?? `${titleCase(i.entity_type)} ${i.entity_id.slice(0, 6)}`;
            return (
              <li key={i.id} className="flex items-start gap-3 px-4 py-3">
                <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", COLOR[i.channel] ?? "bg-black/5 text-ink-soft dark:bg-white/10")}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <button type="button" disabled={!lead} onClick={() => lead && onOpenLead(lead.id)} className={cn("truncate font-semibold", lead && "hover:underline")}>
                      {name}
                    </button>
                    <Badge tone={i.direction === "inbound" ? "blue" : i.direction === "internal" ? "purple" : "gray"} icon={i.direction === "inbound" ? <ArrowDownLeft className="h-3 w-3" /> : i.direction === "outbound" ? <ArrowUpRight className="h-3 w-3" /> : undefined}>
                      {i.direction === "internal" ? "note" : i.direction}
                    </Badge>
                    <span className="text-[11px] text-ink-mute">
                      {titleCase(i.channel)} · {timeAgo(i.occurred_at)}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-sm text-ink-soft dark:text-slate-300" dir="auto">
                    {i.summary}
                  </p>
                </div>
                {lead && (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Reply className="h-4 w-4" />}
                    onClick={() => setReply({ id: lead.id, name: lead.name, channel: i.channel === "email" ? "email" : i.channel === "sms" ? "sms" : lead.phone ? "whatsapp" : "email" })}
                  >
                    Reply
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <ComposeModal open={!!reply} onClose={() => setReply(null)} entityId={reply?.id ?? null} name={reply?.name} channel={reply?.channel} />
    </div>
  );
}
