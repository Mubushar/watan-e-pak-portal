import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlarmClock,
  ArrowLeftRight,
  BadgeCheck,
  Check,
  CircleDashed,
  FileSearch,
  FileSignature,
  Gavel,
  Handshake,
  LayoutGrid,
  ListChecks,
  PenLine,
  Plus,
  Printer,
  ScanText,
  Sparkles,
  Timer,
  Wand2,
} from "lucide-react";
import { api, post, put } from "@/lib/api";
import { useApi, useMutate } from "@/hooks/useApi";
import { date, num, pct, pkr, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Avatar,
  Badge,
  Button,
  Card,
  DataTable,
  Drawer,
  EmptyState,
  Field,
  Input,
  KeyValue,
  Modal,
  PageHeader,
  Progress,
  QueryState,
  Segmented,
  Select,
  Skeleton,
  StatCard,
  StatusBadge,
  Tabs,
  Textarea,
} from "@/components/ui";
import { FormGrid, MiniStat, Panel, SkeletonGrid, Stepper, ensure, isoDay, numOr, openHtml, stagger, useFormState, rs } from "@/components/biz/ops-kit";
import { toast } from "sonner";

// ------------------------------------------------------------------ types
interface Milestone {
  key: string;
  name: string;
  due_date?: string | null;
  owner: string;
  status: string;
  blocking: boolean;
  required: boolean;
  completed_at?: string | null;
}
interface Offer {
  id: string;
  transaction_id: string;
  price: number;
  buyer_name?: string | null;
  terms?: string | null;
  status: string;
  counter_price?: number | null;
  created_at: string;
}
interface Signature {
  id: string;
  signer: string;
  role: string;
  method: string;
  signed: boolean;
  signed_at?: string | null;
}
interface Txn {
  id: string;
  code: string;
  transaction_type: string;
  type_label?: string;
  property_title?: string | null;
  buyer_name?: string | null;
  seller_name?: string | null;
  price: number;
  currency: string;
  commission_rate?: number | null;
  stage: string;
  stage_index: number;
  status: string;
  milestones: Milestone[];
  milestone_progress: { total: number; done: number };
  risk_flags: string[];
  terms: { key: string; label: string; value: unknown }[];
  notes?: string | null;
  created_at: string;
  offers?: Offer[];
  signatures?: Signature[];
}
interface Stages {
  stages: { stage: string; index: number; is_final: boolean }[];
  types: Record<string, string>;
  config: { default_commission_rate: number };
}
interface TxnProgress {
  progress_pct: number;
  milestones_total: number;
  milestones_done: number;
  overdue: { key: string; name: string; due_date: string; days_late: number; blocking: boolean }[];
  next_deadline?: { key: string; name: string; due_date: string; days_left: number } | null;
  rag: string;
}
interface Signatures {
  expected_roles: string[];
  signed_roles: string[];
  missing: string[];
  complete: boolean;
  signature_count: number;
}
interface Deadline {
  transaction_id: string;
  code: string;
  milestone: string;
  name: string;
  due_date: string;
  days_left: number;
  owner: string;
  blocking: boolean;
  overdue: boolean;
}
interface Extracted {
  terms: { key: string; label: string; value: unknown; extracted_from?: string; confidence?: number }[];
  term_count: number;
  parties: (string | string[])[];
  dates: string[];
  confidence: number;
}

type TabKey = "board" | "deadlines" | "terms";
const INVALIDATE = ["/transactions", "/agents", "/portal", "/accounting"];
const FALLBACK_STAGES = ["draft", "listed", "offer", "negotiation", "under_contract", "due_diligence", "financing", "closing", "closed"];

export default function Transactions() {
  const [tab, setTab] = useState<TabKey>("board");
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const list = useApi<{ count: number; transactions: Txn[] }>("/transactions");
  const stagesQ = useApi<Stages>("/transactions/stages");
  const deadlines = useApi<{ count: number; overdue: number; deadlines: Deadline[] }>("/transactions/deadlines", { horizon_days: 30 });
  const flow = useMemo(() => (stagesQ.data?.stages.filter((s) => s.stage !== "fallen_through").map((s) => s.stage) ?? FALLBACK_STAGES), [stagesQ.data]);

  const txns = list.data?.transactions ?? [];
  const open = txns.filter((t) => t.status === "open");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Transactions"
        subtitle="Offer-to-close workflow with milestones, offers and e-signatures"
        actions={
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
            New transaction
          </Button>
        }
      />

      {list.isLoading ? (
        <SkeletonGrid n={4} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Open deals" value={open.length} icon={<Handshake className="h-5 w-5" />} hint={`${txns.length} total`} />
          <StatCard label="Value in flight" value={rs(open.reduce((s, t) => s + t.price, 0))} icon={<ArrowLeftRight className="h-5 w-5" />} tone="gold" />
          <StatCard
            label="Overdue milestones"
            value={deadlines.data?.overdue ?? "…"}
            icon={<AlarmClock className="h-5 w-5" />}
            tone={deadlines.data?.overdue ? "red" : "green"}
            hint={`${deadlines.data?.count ?? 0} due in 30 days`}
          />
          <StatCard
            label="Milestones done"
            value={`${txns.reduce((s, t) => s + t.milestone_progress.done, 0)} / ${txns.reduce((s, t) => s + t.milestone_progress.total, 0)}`}
            icon={<ListChecks className="h-5 w-5" />}
            tone="blue"
          />
        </div>
      )}

      <Card className="overflow-hidden">
        <Tabs<TabKey>
          className="px-2"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "board", label: "Transactions", icon: <LayoutGrid className="h-4 w-4" />, count: txns.length },
            { value: "deadlines", label: "Deadlines", icon: <Timer className="h-4 w-4" />, count: deadlines.data?.overdue || undefined },
            { value: "terms", label: "AI terms extractor", icon: <Wand2 className="h-4 w-4" /> },
          ]}
        />
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="p-4 sm:p-5">
          {tab === "board" && (
            <QueryState q={list} skeleton={<SkeletonGrid n={2} className="lg:grid-cols-2" tile="h-56" />}>
              {(d) =>
                d.transactions.length ? (
                  <motion.div variants={stagger.container} initial="hidden" animate="show" className="grid gap-4 lg:grid-cols-2">
                    {d.transactions.map((t) => (
                      <TxnCard key={t.id} t={t} flow={flow} onOpen={() => setOpenId(t.id)} />
                    ))}
                  </motion.div>
                ) : (
                  <EmptyState title="No transactions yet" action={<Button size="sm" onClick={() => setCreating(true)}>Open one</Button>} />
                )
              }
            </QueryState>
          )}
          {tab === "deadlines" && <DeadlinesTab onOpen={setOpenId} />}
          {tab === "terms" && <TermsExtractor />}
        </motion.div>
      </Card>

      <TxnDrawer id={openId} flow={flow} stages={stagesQ.data} onClose={() => setOpenId(null)} />
      <NewTxnModal open={creating} onClose={() => setCreating(false)} types={stagesQ.data?.types} />
    </div>
  );
}

// ================================================================== card
function TxnCard({ t, flow, onOpen }: { t: Txn; flow: string[]; onOpen: () => void }) {
  const done = t.milestone_progress.done;
  const total = t.milestone_progress.total;
  const overdue = t.milestones.filter((m) => m.status === "overdue").length;
  const current = Math.max(0, flow.indexOf(t.stage));
  const next = t.milestones.find((m) => m.status !== "done" && m.status !== "completed");
  return (
    <motion.button variants={stagger.item} type="button" onClick={onOpen} className="card card-hover group flex w-full flex-col gap-4 p-5 text-start">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-bold text-brand-700 dark:text-brand-300">{t.code}</span>
            <Badge tone="gray">{t.type_label?.split(" (")[0] ?? titleCase(t.transaction_type)}</Badge>
            {t.status !== "open" && <StatusBadge status={t.status} />}
          </div>
          <p className="mt-1.5 truncate font-display text-lg font-semibold">{t.property_title ?? "Untitled property"}</p>
          <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-ink-mute">
            {t.buyer_name ?? "Buyer"} <ArrowLeftRight className="h-3 w-3 shrink-0" /> {t.seller_name ?? "Seller"}
          </p>
        </div>
        <div className="shrink-0 text-end">
          <p className="font-display text-xl font-bold text-brand-800 dark:text-brand-200">{pkrShort(t.price, false)}</p>
          <p className="text-[11px] text-ink-mute">{t.currency}</p>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="font-semibold">
            Stage: <span className="text-gold-700 dark:text-gold-300">{titleCase(t.stage)}</span>
          </span>
          <span className="text-ink-mute">
            {current + 1} / {flow.length}
          </span>
        </div>
        <Stepper steps={flow} current={t.stage === "fallen_through" ? -1 : current} compact />
      </div>

      <div className="flex items-center gap-3">
        <Progress value={total ? (done / total) * 100 : 0} className="h-1.5" tone={overdue ? "gold" : "green"} />
        <span className="shrink-0 text-xs font-semibold tabular-nums">
          {done}/{total} milestones
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-black/5 pt-3 text-xs dark:border-white/10">
        {next ? (
          <span className="flex min-w-0 items-center gap-1.5 text-ink-soft dark:text-slate-300">
            <CircleDashed className="h-3.5 w-3.5 shrink-0 text-gold-600" />
            <span className="truncate">Next: {next.name}</span>
            {next.due_date && <span className="shrink-0 text-ink-mute">· {date(next.due_date, { day: "numeric", month: "short" })}</span>}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-brand-700">
            <BadgeCheck className="h-3.5 w-3.5" /> All milestones complete
          </span>
        )}
        {overdue > 0 && <Badge tone="red">{overdue} overdue</Badge>}
      </div>
    </motion.button>
  );
}

// ================================================================== drawer
function TxnDrawer({ id, flow, stages, onClose }: { id: string | null; flow: string[]; stages?: Stages; onClose: () => void }) {
  const q = useApi<Txn>(id ? `/transactions/${id}` : null);
  const prog = useApi<TxnProgress>(id ? `/transactions/${id}/progress` : null);
  const sigs = useApi<Signatures>(id ? `/transactions/${id}/signatures` : null);
  const [section, setSection] = useState<"milestones" | "offers" | "signatures">("milestones");
  const [stage, setStage] = useState("");
  const [offer, setOffer] = useState({ price: "", buyer_name: "", terms: "" });
  const [counter, setCounter] = useState<Record<string, string>>({});
  const [printing, setPrinting] = useState(false);
  const t = q.data;

  useEffect(() => {
    if (t) setStage(t.stage);
  }, [t]);
  useEffect(() => {
    setSection("milestones");
    setOffer({ price: "", buyer_name: "", terms: "" });
    setCounter({});
  }, [id]);

  const complete = useMutate((key: string) => post(`/transactions/${id}/milestones/${encodeURIComponent(key)}/complete`, {}).then(ensure), {
    invalidate: INVALIDATE,
    success: "Milestone completed",
  });
  const updateStage = useMutate((s: string) => put(`/transactions/${id}`, { stage: s }).then(ensure), { invalidate: INVALIDATE, success: (r: Txn) => `Stage set to ${titleCase(r?.stage ?? stage)}` });
  const makeOffer = useMutate(
    () => post(`/transactions/${id}/offers`, { price: numOr(offer.price, 0), buyer_name: offer.buyer_name || undefined, terms: offer.terms || undefined }).then(ensure),
    { invalidate: INVALIDATE, success: "Offer recorded", onSuccess: () => setOffer({ price: "", buyer_name: "", terms: "" }) },
  );
  const respond = useMutate(
    (v: { offerId: string; action: string; counter_price?: number }) => post(`/transactions/offers/${v.offerId}/respond`, { action: v.action, counter_price: v.counter_price }).then(ensure),
    { invalidate: INVALIDATE, success: (r: { offer?: Offer }) => `Offer ${r?.offer?.status ?? "updated"}` },
  );

  const printReport = async () => {
    if (!id) return;
    const win = window.open("", "_blank");
    setPrinting(true);
    try {
      const html = await api<string>(`/transactions/${id}/report`, { method: "POST", body: {}, text: true });
      openHtml(html, win);
    } catch (e) {
      win?.close();
      toast.error((e as Error).message || "Couldn’t build the report");
    } finally {
      setPrinting(false);
    }
  };

  const allStages = stages?.stages.map((s) => s.stage) ?? [...flow, "fallen_through"];
  const p = prog.data;

  return (
    <Drawer open={!!id} onClose={onClose} title={t ? `${t.code} · ${titleCase(t.transaction_type)}` : "Transaction"} width="max-w-2xl">
      <QueryState q={q} skeleton={<div className="space-y-4 p-5"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>}>
        {(t) => (
          <div className="space-y-6 p-5">
            {/* header */}
            <div className="rounded-2xl bg-brand-gradient p-5 text-white">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gold-200">{t.type_label ?? titleCase(t.transaction_type)}</p>
                  <p className="mt-1 font-display text-xl font-bold">{t.property_title ?? "Untitled property"}</p>
                  <p className="mt-1 text-sm text-white/75">
                    {t.buyer_name ?? "—"} ⇄ {t.seller_name ?? "—"}
                  </p>
                </div>
                <div className="text-end">
                  <p className="font-display text-2xl font-bold">{pkrShort(t.price, false)}</p>
                  <p className="text-xs text-white/70">{t.commission_rate ? `${pct(t.commission_rate)} commission` : `${pct(stages?.config.default_commission_rate ?? 0.02)} default commission`}</p>
                </div>
              </div>
              <div className="mt-4 rounded-xl bg-white/10 px-3 py-3">
                <Stepper steps={flow} current={Math.max(0, flow.indexOf(t.stage))} compact />
              </div>
            </div>

            {/* progress */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <MiniStat label="Progress" value={p ? `${Math.round(p.progress_pct)}%` : "…"} tone="green" />
              <MiniStat label="Milestones" value={p ? `${p.milestones_done}/${p.milestones_total}` : "…"} />
              <MiniStat label="Overdue" value={p?.overdue.length ?? "…"} tone={p?.overdue.length ? "red" : "default"} />
              <MiniStat label="Health" value={<StatusBadge status={p?.rag ?? "—"} />} />
            </div>
            {p?.next_deadline && (
              <div className="flex items-center gap-3 rounded-xl border border-gold-200 bg-gold-50/70 px-3 py-2.5 text-sm dark:border-gold-500/20 dark:bg-gold-500/10">
                <Timer className="h-4 w-4 shrink-0 text-gold-700" />
                <span className="min-w-0 flex-1 truncate">
                  Next deadline: <strong>{p.next_deadline.name}</strong>
                </span>
                <span className="shrink-0 text-xs font-semibold">{p.next_deadline.days_left >= 0 ? `in ${p.next_deadline.days_left}d` : `${-p.next_deadline.days_left}d late`}</span>
              </div>
            )}

            {/* stage + report */}
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Stage" className="min-w-[180px] flex-1">
                <Select value={stage} onChange={(e) => setStage(e.target.value)} options={allStages.map((s) => ({ value: s, label: titleCase(s) }))} />
              </Field>
              <Button variant="soft" disabled={stage === t.stage} loading={updateStage.isPending} onClick={() => updateStage.mutate(stage)}>
                Update stage
              </Button>
              <Button variant="outline" icon={<Printer className="h-4 w-4" />} loading={printing} onClick={printReport}>
                Report
              </Button>
            </div>

            {t.risk_flags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {t.risk_flags.map((r) => (
                  <Badge key={r} tone="red">
                    {r}
                  </Badge>
                ))}
              </div>
            )}

            <Segmented
              size="sm"
              value={section}
              onChange={setSection}
              options={[
                { value: "milestones", label: "Milestones", icon: <ListChecks className="h-3.5 w-3.5" /> },
                { value: "offers", label: `Offers${t.offers?.length ? ` · ${t.offers.length}` : ""}`, icon: <Gavel className="h-3.5 w-3.5" /> },
                { value: "signatures", label: "Signatures", icon: <FileSignature className="h-3.5 w-3.5" /> },
              ]}
            />

            {section === "milestones" && (
              <ol className="space-y-2">
                {t.milestones.map((m) => {
                  const done = m.status === "done" || m.status === "completed" || !!m.completed_at;
                  const late = m.status === "overdue";
                  return (
                    <li
                      key={m.key}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border px-3 py-2.5",
                        done ? "border-brand-200 bg-brand-50/50 dark:border-brand-500/20 dark:bg-brand-500/5" : late ? "border-red-200 bg-red-50/40 dark:border-red-500/20 dark:bg-red-500/5" : "border-black/5 dark:border-white/10",
                      )}
                    >
                      <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full", done ? "bg-brand-600 text-white" : late ? "bg-red-100 text-red-600 dark:bg-red-500/20" : "bg-black/5 text-ink-mute dark:bg-white/10")}>
                        {done ? <Check className="h-4 w-4" strokeWidth={3} /> : late ? <AlarmClock className="h-3.5 w-3.5" /> : <CircleDashed className="h-3.5 w-3.5" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className={cn("text-sm font-semibold", done && "text-ink-mute line-through decoration-brand-600/40")}>{m.name}</p>
                        <p className="text-xs text-ink-mute">
                          {titleCase(m.owner)} · {done ? `done ${timeAgo(m.completed_at)}` : m.due_date ? `due ${date(m.due_date)}` : "no due date"}
                          {m.blocking && !done && " · blocking"}
                        </p>
                      </div>
                      {!done && (
                        <Button size="sm" variant={late ? "primary" : "soft"} loading={complete.isPending && complete.variables === m.key} onClick={() => complete.mutate(m.key)}>
                          Complete
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}

            {section === "offers" && (
              <div className="space-y-4">
                {t.offers?.length ? (
                  <ul className="space-y-2">
                    {t.offers.map((o) => {
                      const active = o.status === "submitted" || o.status === "countered";
                      const delta = t.price ? (o.price - t.price) / t.price : 0;
                      return (
                        <li key={o.id} className="rounded-xl border border-black/5 p-3 dark:border-white/10">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <Avatar name={o.buyer_name ?? "Buyer"} size={30} />
                              <div>
                                <p className="text-sm font-semibold">{o.buyer_name ?? "Buyer"}</p>
                                <p className="text-xs text-ink-mute">{timeAgo(o.created_at)}</p>
                              </div>
                            </div>
                            <div className="text-end">
                              <p className="font-display text-lg font-bold">{pkrShort(o.price, false)}</p>
                              <p className={cn("text-xs font-semibold", delta < 0 ? "text-red-600" : "text-brand-700")}>{pct(delta)} vs ask</p>
                            </div>
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <StatusBadge status={o.status} />
                            {o.counter_price ? <Badge tone="gold">Counter {pkrShort(o.counter_price, false)}</Badge> : null}
                            {o.terms && <span className="text-xs text-ink-mute">{o.terms}</span>}
                          </div>
                          {active && (
                            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-black/5 pt-3 dark:border-white/10">
                              <Button size="sm" loading={respond.isPending && respond.variables?.offerId === o.id && respond.variables.action === "accept"} onClick={() => respond.mutate({ offerId: o.id, action: "accept" })}>
                                Accept
                              </Button>
                              <Button size="sm" variant="outline" loading={respond.isPending && respond.variables?.offerId === o.id && respond.variables.action === "reject"} onClick={() => respond.mutate({ offerId: o.id, action: "reject" })}>
                                Reject
                              </Button>
                              <div className="flex min-w-[200px] flex-1 gap-2">
                                <Input className="py-1.5 text-xs" type="number" placeholder="Counter price" value={counter[o.id] ?? ""} onChange={(e) => setCounter({ ...counter, [o.id]: e.target.value })} />
                                <Button
                                  size="sm"
                                  variant="gold"
                                  disabled={!numOr(counter[o.id])}
                                  loading={respond.isPending && respond.variables?.offerId === o.id && respond.variables.action === "counter"}
                                  onClick={() => respond.mutate({ offerId: o.id, action: "counter", counter_price: numOr(counter[o.id]) })}
                                >
                                  Counter
                                </Button>
                              </div>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <EmptyState title="No offers yet" />
                )}
                <div className="rounded-2xl border border-dashed border-brand-300 p-4 dark:border-brand-500/30">
                  <p className="mb-3 flex items-center gap-2 text-sm font-semibold">
                    <PenLine className="h-4 w-4 text-brand-600" /> Make an offer
                  </p>
                  <FormGrid>
                    <Field label="Offer price (PKR)" hint={offer.price ? pkr(Number(offer.price)) : `Asking ${pkr(t.price)}`}>
                      <Input type="number" min={0} value={offer.price} onChange={(e) => setOffer({ ...offer, price: e.target.value })} />
                    </Field>
                    <Field label="Buyer">
                      <Input value={offer.buyer_name} onChange={(e) => setOffer({ ...offer, buyer_name: e.target.value })} placeholder={t.buyer_name ?? "Buyer name"} />
                    </Field>
                    <Field label="Terms" className="sm:col-span-2">
                      <Input value={offer.terms} onChange={(e) => setOffer({ ...offer, terms: e.target.value })} placeholder="e.g. 10% token, possession in 60 days" />
                    </Field>
                  </FormGrid>
                  <div className="mt-3 flex justify-end">
                    <Button size="sm" disabled={!numOr(offer.price)} loading={makeOffer.isPending} onClick={() => makeOffer.mutate()}>
                      Submit offer
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {section === "signatures" && (
              <div className="space-y-4">
                {sigs.data && (
                  <div className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm", sigs.data.complete ? "bg-brand-50 text-brand-800 dark:bg-brand-500/10 dark:text-brand-200" : "bg-gold-50 text-gold-800 dark:bg-gold-500/10 dark:text-gold-100")}>
                    <FileSignature className="h-4 w-4 shrink-0" />
                    {sigs.data.complete ? "All parties have signed." : `Waiting on: ${sigs.data.missing.map(titleCase).join(", ")}`}
                  </div>
                )}
                <div className="grid gap-2 sm:grid-cols-2">
                  {(sigs.data?.expected_roles ?? []).map((role) => {
                    const signed = sigs.data!.signed_roles.includes(role);
                    const who = t.signatures?.find((s) => s.role === role);
                    return (
                      <div key={role} className={cn("rounded-xl border p-3", signed ? "border-brand-200 dark:border-brand-500/30" : "border-dashed border-black/10 dark:border-white/15")}>
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold uppercase tracking-wider text-ink-mute">{titleCase(role)}</span>
                          {signed ? <Badge tone="green" icon={<Check className="h-3 w-3" />}>Signed</Badge> : <Badge tone="gold">Pending</Badge>}
                        </div>
                        <p className="mt-2 font-semibold">{who?.signer ?? "—"}</p>
                        <p className="text-xs text-ink-mute">{who?.signed_at ? `${titleCase(who.method)} · ${date(who.signed_at)}` : who ? `${titleCase(who.method)} requested` : "Not requested"}</p>
                      </div>
                    );
                  })}
                </div>
                {sigs.isLoading && <Skeleton className="h-24" />}
              </div>
            )}

            {t.terms.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">Contract terms</p>
                <KeyValue items={t.terms.map((x) => ({ label: x.label, value: formatTerm(x.key, x.value) }))} />
              </div>
            )}
          </div>
        )}
      </QueryState>
    </Drawer>
  );
}

function formatTerm(key: string, v: unknown): string {
  if (typeof v === "number") {
    if (/commission|rate|pct|percent/.test(key) && v < 1) return pct(v);
    if (v >= 1000) return pkr(v);
    return num(v, 2);
  }
  if (v === null || v === undefined) return "—";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

// ================================================================== deadlines
function DeadlinesTab({ onOpen }: { onOpen: (id: string) => void }) {
  const [horizon, setHorizon] = useState("14");
  const q = useApi<{ horizon_days: number; count: number; overdue: number; deadlines: Deadline[] }>("/transactions/deadlines", { horizon_days: horizon });
  return (
    <QueryState q={q} skeleton={<Skeleton className="h-72" />}>
      {(d) => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-2">
              <Badge tone="red">{d.overdue} overdue</Badge>
              <Badge tone="blue">{d.count - d.overdue} upcoming</Badge>
            </div>
            <Segmented
              size="sm"
              value={horizon}
              onChange={setHorizon}
              options={["7", "14", "30", "60"].map((h) => ({ value: h, label: `${h}d` }))}
            />
          </div>
          <Card className="overflow-hidden">
            <DataTable
              rows={d.deadlines}
              rowKey={(r) => `${r.transaction_id}-${r.milestone}`}
              onRowClick={(r) => onOpen(r.transaction_id)}
              search
              columns={[
                {
                  key: "days_left",
                  header: "When",
                  render: (r) => (
                    <span className={cn("inline-flex min-w-[64px] justify-center rounded-lg px-2 py-1 text-xs font-bold", r.overdue ? "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300" : r.days_left <= 3 ? "bg-gold-50 text-gold-700 dark:bg-gold-500/15 dark:text-gold-200" : "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200")}>
                      {r.overdue ? `${-r.days_left}d late` : r.days_left === 0 ? "today" : `in ${r.days_left}d`}
                    </span>
                  ),
                },
                { key: "code", header: "Deal", render: (r) => <span className="font-mono text-xs font-semibold">{r.code}</span> },
                { key: "name", header: "Milestone", render: (r) => <span className="font-medium">{r.name}</span> },
                { key: "owner", header: "Owner", render: (r) => <span className="text-xs">{titleCase(r.owner)}</span> },
                { key: "due_date", header: "Due", render: (r) => <span className="whitespace-nowrap text-xs">{date(r.due_date)}</span> },
                { key: "blocking", header: "Blocking", render: (r) => (r.blocking ? <Badge tone="orange">Blocking</Badge> : <span className="text-xs text-ink-mute">—</span>) },
              ]}
              empty={<EmptyState title="No deadlines in this window" />}
            />
          </Card>
        </div>
      )}
    </QueryState>
  );
}

// ================================================================== terms extractor
const SAMPLE =
  "This sale agreement is made on 1 November 2026 between Ahmed Ali (seller) and Bilal Khan (buyer) for the house at 10 Marla, DHA Phase 6, Lahore, for a total price of PKR 28,500,000. Token money of Rs 500,000 is payable within 3 days. Possession on 15 December 2026. Commission 2%.";

function TermsExtractor() {
  const [text, setText] = useState("");
  const extract = useMutate((t: string) => post<Extracted>("/transactions/terms/extract", { text: t }).then(ensure), {
    success: (r) => `Extracted ${r.term_count} term${r.term_count === 1 ? "" : "s"}`,
  });
  const r = extract.data;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel
        title="Agreement text"
        subtitle="Paste a sale / tenancy agreement or term sheet"
        icon={<ScanText className="h-4 w-4" />}
        action={
          <Button size="sm" variant="ghost" onClick={() => setText(SAMPLE)}>
            Use sample
          </Button>
        }
      >
        <Textarea className="min-h-[260px] font-mono text-xs leading-relaxed" value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste contract text here…" />
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="text-xs text-ink-mute">{text.trim().split(/\s+/).filter(Boolean).length} words</span>
          <Button variant="gold" icon={<Sparkles className="h-4 w-4" />} disabled={!text.trim()} loading={extract.isPending} onClick={() => extract.mutate(text)}>
            Extract terms
          </Button>
        </div>
      </Panel>
      <Panel title="Extracted terms" subtitle={r ? `${r.term_count} terms · ${pct(r.confidence, 0)} overall confidence` : "Results appear here"} icon={<FileSearch className="h-4 w-4" />}>
        {extract.isPending ? (
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : r ? (
          r.terms.length ? (
            <div className="space-y-4">
              <KeyValue items={r.terms.map((t) => ({ label: t.label, value: formatTerm(t.key, t.value) }))} />
              <ul className="space-y-1.5">
                {r.terms.map((t) => (
                  <li key={t.key} className="flex items-center gap-3 text-xs">
                    <span className="w-28 shrink-0 truncate font-semibold">{t.label}</span>
                    <span className="min-w-0 flex-1 truncate italic text-ink-mute">“{t.extracted_from}”</span>
                    {t.confidence !== undefined && <Progress value={t.confidence * 100} className="h-1.5 w-16 shrink-0" />}
                  </li>
                ))}
              </ul>
              {(r.dates.length > 0 || r.parties.length > 0) && (
                <div className="flex flex-wrap gap-2">
                  {r.parties.map((p, i) => (
                    <Badge key={i} tone="purple">
                      {Array.isArray(p) ? p.filter(Boolean).join(" · ") : p}
                    </Badge>
                  ))}
                  {r.dates.map((d) => (
                    <Badge key={d} tone="blue">
                      {d}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <EmptyState title="No terms recognised" hint="Try text with prices, dates, deposits or commission." />
          )
        ) : (
          <EmptyState title="Nothing extracted yet" hint="Paste text on the left and run the extractor." icon={<Wand2 className="h-6 w-6" />} />
        )}
      </Panel>
    </div>
  );
}

// ================================================================== new transaction
function NewTxnModal({ open, onClose, types }: { open: boolean; onClose: () => void; types?: Record<string, string> }) {
  const [f, set, reset] = useFormState({ transaction_type: "sale", property_title: "", price: "", buyer_name: "", seller_name: "", commission_rate: "", start_date: isoDay(0), notes: "" });
  const create = useMutate(
    () =>
      post<Txn>("/transactions", {
        transaction_type: f.transaction_type,
        property_title: f.property_title || undefined,
        price: numOr(f.price, 0),
        buyer_name: f.buyer_name || undefined,
        seller_name: f.seller_name || undefined,
        commission_rate: f.commission_rate ? (numOr(f.commission_rate, 0) ?? 0) / 100 : undefined,
        start_date: f.start_date || undefined,
        notes: f.notes || undefined,
      }).then(ensure),
    {
      invalidate: INVALIDATE,
      success: (r) => `Opened ${r?.code ?? "transaction"}`,
      onSuccess: () => {
        reset();
        onClose();
      },
    },
  );
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New transaction"
      subtitle="Opens the milestone checklist for the deal type"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} disabled={!numOr(f.price) || !f.property_title.trim()} onClick={() => create.mutate()}>
            Open transaction
          </Button>
        </>
      }
    >
      <FormGrid>
        <Field label="Type">
          <Select value={f.transaction_type} onChange={(e) => set("transaction_type")(e.target.value)} options={Object.entries(types ?? { sale: "Sale", purchase: "Purchase", rental: "Rental", lease: "Lease", assignment: "Assignment" }).map(([value, label]) => ({ value, label }))} />
        </Field>
        <Field label="Price (PKR) *" hint={f.price ? pkrShort(Number(f.price)) : undefined}>
          <Input type="number" min={0} value={f.price} onChange={(e) => set("price")(e.target.value)} />
        </Field>
        <Field label="Property *" className="sm:col-span-2">
          <Input value={f.property_title} onChange={(e) => set("property_title")(e.target.value)} placeholder="e.g. 10 Marla House — DHA Lahore" />
        </Field>
        <Field label="Buyer / tenant">
          <Input value={f.buyer_name} onChange={(e) => set("buyer_name")(e.target.value)} />
        </Field>
        <Field label="Seller / landlord">
          <Input value={f.seller_name} onChange={(e) => set("seller_name")(e.target.value)} />
        </Field>
        <Field label="Commission (%)">
          <Input type="number" min={0} step="0.1" value={f.commission_rate} onChange={(e) => set("commission_rate")(e.target.value)} placeholder="2" />
        </Field>
        <Field label="Start date">
          <Input type="date" value={f.start_date} onChange={(e) => set("start_date")(e.target.value)} />
        </Field>
        <Field label="Notes" className="sm:col-span-2">
          <Textarea className="min-h-[64px]" value={f.notes} onChange={(e) => set("notes")(e.target.value)} />
        </Field>
      </FormGrid>
    </Modal>
  );
}
