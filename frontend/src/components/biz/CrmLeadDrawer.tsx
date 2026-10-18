import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRightLeft, Brain, Mail, MessageSquarePlus, Phone, Sparkles, UserCheck, UserPlus } from "lucide-react";
import { post, put } from "@/lib/api";
import { useApi, useMutate } from "@/hooks/useApi";
import { date, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { Avatar, Badge, Button, Drawer, EmptyState, ErrorState, Field, KeyValue, Progress, ScoreRing, Select, Skeleton, StatusBadge, Textarea } from "@/components/ui";
import { LeadAiPanel } from "@/components/crm/LeadAiPanel";
import { bandTone, ensure, sentence } from "./ops-kit";
import { CUSTOMER_TYPES, INTERACTION_CHANNELS, LEAD_STATUSES, type Agent, type Deal, type Interaction, type Lead } from "./crm-types";

interface LeadDetail {
  lead: Lead;
  matches: { count: number; properties: { id: string; title: string; price: number; category: string; city_name?: string | null }[] };
  interactions: Interaction[];
  deals: Deal[];
}
interface MoveLikelihood {
  move_likelihood: { score: number; band: string; reasons: string[]; components: Record<string, number>; recommended_action: string };
}
interface Qualification {
  qualification: { score: number; band: string; reasons: string[]; recommended_action: string };
}

const INVALIDATE = ["/crm", "/broker", "/agents", "/marketing", "/portal"];

export function CrmLeadDrawer({ leadId, agents, onClose }: { leadId: string | null; agents: Agent[]; onClose: () => void }) {
  const detail = useApi<LeadDetail>(leadId ? `/crm/leads/${leadId}` : null);
  const ml = useApi<MoveLikelihood>(leadId ? `/agents/move-likelihood/${leadId}` : null);
  const lead = detail.data?.lead;

  const [status, setStatus] = useState("");
  const [agentId, setAgentId] = useState("");
  const [custType, setCustType] = useState<string>("buyer");
  const [note, setNote] = useState({ channel: "call", direction: "outbound", summary: "" });
  const [qual, setQual] = useState<Qualification["qualification"] | null>(null);

  useEffect(() => {
    setQual(null);
    setNote({ channel: "call", direction: "outbound", summary: "" });
  }, [leadId]);
  useEffect(() => {
    if (lead) {
      setStatus(lead.status);
      setAgentId(lead.assigned_agent_id ?? "");
    }
  }, [lead]);

  const updateStatus = useMutate((s: string) => put(`/crm/leads/${leadId}`, { status: s }).then(ensure), { invalidate: INVALIDATE, success: "Lead status updated" });
  const assign = useMutate((id: string) => post(`/crm/leads/${leadId}/assign`, { agent_id: id }).then(ensure), {
    invalidate: INVALIDATE,
    success: () => `Assigned to ${agents.find((a) => a.id === agentId)?.name ?? "agent"}`,
  });
  const convert = useMutate((t: string) => post(`/crm/leads/${leadId}/convert`, {}, { customer_type: t }).then(ensure), {
    invalidate: INVALIDATE,
    success: "Lead converted to a customer",
  });
  const logInteraction = useMutate(
    () =>
      post("/crm/interactions", {
        entity_type: "lead",
        entity_id: leadId,
        channel: note.channel,
        direction: note.direction,
        summary: note.summary.trim(),
        agent_id: lead?.assigned_agent_id ?? undefined,
      }).then(ensure),
    { invalidate: ["/crm", "/broker", "/agents"], success: "Interaction logged", onSuccess: () => setNote((n) => ({ ...n, summary: "" })) },
  );
  const qualify = useMutate(() => post<Qualification>(`/marketing/qualify/${leadId}`).then(ensure), {
    invalidate: INVALIDATE,
    success: (r) => `AI score: ${r.qualification.score} (${r.qualification.band})`,
    onSuccess: (r) => setQual(r.qualification),
  });

  const m = ml.data?.move_likelihood;

  return (
    <Drawer open={!!leadId} onClose={onClose} title="Lead details" width="max-w-xl">
      {detail.error ? (
        <div className="p-5">
          <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
        </div>
      ) : detail.isLoading || !lead ? (
        <div className="space-y-4 p-5">
          <Skeleton className="h-20" />
          <Skeleton className="h-32" />
          <Skeleton className="h-48" />
        </div>
      ) : (
        <div className="space-y-6 p-5">
          {/* identity */}
          <div className="flex items-start gap-4">
            <Avatar name={lead.name} size={52} />
            <div className="min-w-0 flex-1">
              <h3 className="truncate font-display text-xl font-bold">{lead.name}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <StatusBadge status={lead.status} />
                <Badge tone="gray">{titleCase(lead.source)}</Badge>
                {lead.converted_customer_id && <Badge tone="green" icon={<UserCheck className="h-3 w-3" />}>Customer</Badge>}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-mute dark:text-slate-400">
                {lead.phone && (
                  <a href={`tel:${lead.phone}`} className="inline-flex items-center gap-1 hover:text-brand-700">
                    <Phone className="h-3.5 w-3.5" /> {lead.phone}
                  </a>
                )}
                {lead.email && (
                  <a href={`mailto:${lead.email}`} className="inline-flex items-center gap-1 truncate hover:text-brand-700">
                    <Mail className="h-3.5 w-3.5" /> {lead.email}
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* intent + AI */}
          <div className="rounded-2xl border border-black/5 bg-gradient-to-br from-brand-50/80 to-gold-50/50 p-4 dark:border-white/10 dark:from-brand-500/10 dark:to-gold-500/5">
            <div className="flex items-center gap-4">
              {ml.isLoading ? <Skeleton className="h-[84px] w-[84px] rounded-full" /> : <ScoreRing value={m?.score ?? 0} label="intent" />}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold">Move likelihood</p>
                  {m && (
                    <Badge tone={bandTone(m.band)} className="capitalize">
                      {m.band}
                    </Badge>
                  )}
                </div>
                <p className="mt-1 text-sm text-ink-soft dark:text-slate-300">{m ? sentence(m.recommended_action) : ml.error ? "Score unavailable" : "Scoring…"}</p>
                {m?.reasons?.length ? <p className="mt-1 text-xs text-ink-mute">{m.reasons.join(" · ")}</p> : null}
              </div>
            </div>
            {m && (
              <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                {Object.entries(m.components).map(([k, v]) => (
                  <div key={k}>
                    <div className="mb-1 flex justify-between text-[11px] font-semibold text-ink-mute">
                      <span className="truncate">{titleCase(k)}</span>
                      <span className="tabular-nums">{Math.round(v * 100)}</span>
                    </div>
                    <Progress value={v * 100} className="h-1.5" />
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-black/5 pt-3 dark:border-white/10">
              <Button size="sm" variant="gold" icon={<Sparkles className="h-4 w-4" />} loading={qualify.isPending} onClick={() => qualify.mutate()}>
                Qualify with AI
              </Button>
              <span className="text-xs text-ink-mute">Re-scores the lead and syncs the score to CRM.</span>
            </div>
            {qual && (
              <div className="mt-3 rounded-xl bg-white/80 p-3 text-sm dark:bg-white/5">
                <div className="flex items-center gap-2">
                  <Brain className="h-4 w-4 text-brand-600" />
                  <span className="font-semibold">Score {qual.score}</span>
                  <Badge tone={bandTone(qual.band)} className="capitalize">
                    {qual.band}
                  </Badge>
                </div>
                <p className="mt-1 text-ink-soft dark:text-slate-300">{sentence(qual.recommended_action)}</p>
                <ul className="mt-1 list-inside list-disc text-xs text-ink-mute">
                  {qual.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* facts */}
          <KeyValue
            items={[
              { label: "Budget", value: lead.budget_min || lead.budget_max ? `${pkrShort(lead.budget_min, false)} – ${pkrShort(lead.budget_max, false)}` : "—" },
              { label: "Interest", value: [titleCase(lead.interest_use_type), titleCase(lead.interest_category)].filter(Boolean).join(" · ") || "—" },
              { label: "Lead score", value: lead.score },
              { label: "Created", value: date(lead.created_at) },
            ]}
          />
          {lead.notes && <p className="rounded-xl bg-gold-50/70 px-3 py-2 text-sm text-gold-800 dark:bg-gold-500/10 dark:text-gold-100">{lead.notes}</p>}

          {/* AI: brief, drafts, send, voice notes */}
          <LeadAiPanel key={lead.id} leadId={lead.id} name={lead.name} />

          {/* actions */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Status">
              <div className="flex gap-2">
                <Select value={status} onChange={(e) => setStatus(e.target.value)} options={LEAD_STATUSES.map((s) => ({ value: s, label: titleCase(s) }))} />
                <Button size="sm" variant="soft" disabled={status === lead.status} loading={updateStatus.isPending} onClick={() => updateStatus.mutate(status)}>
                  Save
                </Button>
              </div>
            </Field>
            <Field label="Assigned agent">
              <div className="flex gap-2">
                <Select value={agentId} onChange={(e) => setAgentId(e.target.value)}>
                  <option value="">Unassigned</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </Select>
                <Button
                  size="sm"
                  variant="soft"
                  icon={<UserPlus className="h-4 w-4" />}
                  disabled={!agentId || agentId === lead.assigned_agent_id}
                  loading={assign.isPending}
                  onClick={() => assign.mutate(agentId)}
                >
                  Assign
                </Button>
              </div>
            </Field>
            <Field label="Convert to customer" className="sm:col-span-2">
              <div className="flex gap-2">
                <Select value={custType} onChange={(e) => setCustType(e.target.value)} options={CUSTOMER_TYPES.map((s) => ({ value: s, label: titleCase(s) }))} />
                <Button
                  size="sm"
                  icon={<ArrowRightLeft className="h-4 w-4" />}
                  disabled={!!lead.converted_customer_id}
                  loading={convert.isPending}
                  onClick={() => convert.mutate(custType)}
                  className="shrink-0"
                >
                  {lead.converted_customer_id ? "Converted" : "Convert"}
                </Button>
              </div>
            </Field>
          </div>

          {/* matches */}
          <section>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Matching listings · {detail.data!.matches.count}</h4>
            {detail.data!.matches.properties.length ? (
              <ul className="space-y-2">
                {detail.data!.matches.properties.slice(0, 4).map((p) => (
                  <li key={p.id}>
                    <Link to={`/properties/${p.id}`} className="flex items-center justify-between gap-3 rounded-xl border border-black/5 px-3 py-2 text-sm hover:border-brand-300 dark:border-white/10">
                      <span className="min-w-0 truncate font-medium">{p.title}</span>
                      <span className="shrink-0 font-semibold text-brand-700 dark:text-brand-300">{pkrShort(p.price, false)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-mute">No matching listings yet.</p>
            )}
          </section>

          {/* deals */}
          {detail.data!.deals.length > 0 && (
            <section>
              <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Deals</h4>
              <ul className="space-y-2">
                {detail.data!.deals.map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-3 rounded-xl bg-brand-50/50 px-3 py-2 text-sm dark:bg-white/5">
                    <span className="min-w-0 truncate font-medium">{d.title}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      <StatusBadge status={d.stage} />
                      <span className="font-semibold">{pkrShort(d.amount, false)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* interactions */}
          <section>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Activity</h4>
            <div className="rounded-2xl border border-black/5 p-3 dark:border-white/10">
              <div className="flex flex-wrap gap-2">
                <Select className="w-auto py-1.5 text-xs" value={note.channel} onChange={(e) => setNote({ ...note, channel: e.target.value })} options={INTERACTION_CHANNELS.map((c) => ({ value: c, label: titleCase(c) }))} />
                <Select
                  className="w-auto py-1.5 text-xs"
                  value={note.direction}
                  onChange={(e) => setNote({ ...note, direction: e.target.value })}
                  options={[
                    { value: "outbound", label: "Outbound" },
                    { value: "inbound", label: "Inbound" },
                  ]}
                />
              </div>
              <Textarea className="mt-2 min-h-[72px]" placeholder="What happened? e.g. Called — wants a viewing on Saturday" value={note.summary} onChange={(e) => setNote({ ...note, summary: e.target.value })} />
              <div className="mt-2 flex justify-end">
                <Button size="sm" icon={<MessageSquarePlus className="h-4 w-4" />} disabled={!note.summary.trim()} loading={logInteraction.isPending} onClick={() => logInteraction.mutate()}>
                  Log interaction
                </Button>
              </div>
            </div>
            {detail.data!.interactions.length ? (
              <ol className="relative mt-4 space-y-4 border-s border-black/10 ps-5 dark:border-white/10">
                {[...detail.data!.interactions]
                  .sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1))
                  .map((i) => (
                    <li key={i.id} className="relative">
                      <span className="absolute -start-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-brand-600 dark:border-[#0b1a12]" />
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <Badge tone="blue">{titleCase(i.channel)}</Badge>
                        <span className="text-ink-mute">{titleCase(i.direction)}</span>
                        <span className="text-ink-mute">· {timeAgo(i.occurred_at)}</span>
                      </div>
                      <p className="mt-1 text-sm">{i.summary}</p>
                    </li>
                  ))}
              </ol>
            ) : (
              <div className="mt-4">
                <EmptyState title="No activity yet" hint="Log the first call, message or visit above." />
              </div>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
}
