import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BedDouble,
  Bot,
  Building,
  Calculator,
  ClipboardCheck,
  Coins,
  Filter,
  Home,
  KeyRound,
  MessageCircle,
  Plus,
  Repeat,
  Ruler,
  Send,
  ShieldCheck,
  UserRound,
  Wallet,
} from "lucide-react";
import { post } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { useApi, useMutate } from "@/hooks/useApi";
import { coverImage } from "@/lib/images";
import { num, pct, pkr, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Badge,
  BarList,
  Button,
  Card,
  DataTable,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Progress,
  QueryState,
  ScoreRing,
  Select,
  Skeleton,
  Slider,
  StatCard,
  StatusBadge,
  Tabs,
  Toggle,
} from "@/components/ui";
import { FormGrid, MiniStat, Panel, SkeletonGrid, ensure, numOr, stagger, useDebounced, useFormState, rs } from "@/components/biz/ops-kit";

// ------------------------------------------------------------------ types
interface Unit {
  id: string;
  title: string;
  city?: string | null;
  scheme?: string | null;
  rent: number;
  deposit: number;
  bedrooms?: number | null;
  area?: number | null;
  status: string;
  monthly_holding_cost: number;
  floor_rent: number;
  amenities: string[];
}
interface Inquiry {
  id: string;
  unit_id?: string | null;
  channel: string;
  lang: string;
  message: string;
  intent: string;
  lead_score: number;
  reply: string;
  auto_handled: boolean;
  status: string;
  created_at: string;
}
interface Funnel {
  inquiries: number;
  auto_handled: number;
  escalated: number;
  applications: number;
  avg_inquiry_score: number;
  by_channel: Record<string, number>;
  by_intent: Record<string, number>;
}
interface Collection {
  leases: number;
  in_arrears: number;
  total_outstanding: number;
  rows: { lease_id: string; tenant: string; unit: string; outstanding: number; status: string }[];
}
interface Renewal {
  current_rent: number;
  market_rent: number;
  proposed_renewal_rent: number;
  uplift_pct: number;
  days_to_expiry: number;
  retention_risk: string;
  vacancy_cost_if_lost: number;
  recommendation: string;
  message: string;
  tenant?: string;
  unit?: string;
}
interface Screening {
  application_id: string;
  unit_id?: string | null;
  income_to_rent: number;
  score: number;
  decision: "approve" | "conditional" | "decline" | string;
  conditions: string[];
  recommended_deposit?: number | null;
  explanation: string[];
}

type TabKey = "units" | "agent" | "screening" | "renewals" | "floor";
const CHANNELS = ["web_chat", "whatsapp", "sms", "email", "voice"];
const INVALIDATE = ["/leasing", "/portal"];

export default function Leasing() {
  const [tab, setTab] = useState<TabKey>("units");
  const [adding, setAdding] = useState(false);
  const units = useApi<{ count: number; units: Unit[] }>("/leasing/units");
  const funnel = useApi<Funnel>("/leasing/funnel");
  const collection = useApi<Collection>("/leasing/collection");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leasing"
        subtitle="Autonomous leasing agent, tenant screening, renewals and rent collection"
        actions={
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>
            Add unit
          </Button>
        }
      />

      {units.isLoading || funnel.isLoading ? (
        <SkeletonGrid n={4} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Listed units" value={units.data?.units.filter((u) => u.status === "listed").length ?? "—"} icon={<Building className="h-5 w-5" />} hint={`${units.data?.count ?? 0} in portfolio`} />
          <StatCard
            label="Inquiries handled"
            value={funnel.data ? `${funnel.data.auto_handled}/${funnel.data.inquiries}` : "—"}
            icon={<Bot className="h-5 w-5" />}
            hint={funnel.data?.inquiries ? `${pct(funnel.data.auto_handled / funnel.data.inquiries, 0)} autonomous` : undefined}
            tone="purple"
          />
          <StatCard label="Applications" value={funnel.data?.applications ?? "—"} icon={<ClipboardCheck className="h-5 w-5" />} hint={`avg inquiry score ${num(funnel.data?.avg_inquiry_score, 1)}`} tone="blue" />
          <StatCard
            label="Rent outstanding"
            value={collection.data ? rs(collection.data.total_outstanding) : "—"}
            icon={<Wallet className="h-5 w-5" />}
            hint={collection.data ? `${collection.data.in_arrears} of ${collection.data.leases} leases in arrears` : undefined}
            tone={collection.data?.in_arrears ? "red" : "green"}
          />
        </div>
      )}

      <Card className="overflow-hidden">
        <Tabs<TabKey>
          className="px-2"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "units", label: "Units", icon: <Home className="h-4 w-4" />, count: units.data?.count },
            { value: "agent", label: "Leasing agent", icon: <Bot className="h-4 w-4" /> },
            { value: "screening", label: "Screening", icon: <ShieldCheck className="h-4 w-4" /> },
            { value: "renewals", label: "Renewals & collection", icon: <Repeat className="h-4 w-4" /> },
            { value: "floor", label: "Rent floor", icon: <Calculator className="h-4 w-4" /> },
          ]}
        />
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="p-4 sm:p-5">
          {tab === "units" && <UnitsGrid q={units} onAdd={() => setAdding(true)} />}
          {tab === "agent" && <AgentSimulator units={units.data?.units ?? []} funnel={funnel} />}
          {tab === "screening" && <ScreeningForm units={units.data?.units ?? []} />}
          {tab === "renewals" && <RenewalsAndCollection collection={collection} />}
          {tab === "floor" && <RentFloor units={units.data?.units ?? []} />}
        </motion.div>
      </Card>

      <AddUnitModal open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}

// ================================================================== units
function UnitsGrid({ q, onAdd }: { q: ReturnType<typeof useApi<{ count: number; units: Unit[] }>>; onAdd: () => void }) {
  return (
    <QueryState q={q} skeleton={<SkeletonGrid n={3} className="lg:grid-cols-3" tile="h-72" />}>
      {(d) =>
        d.units.length ? (
          <motion.div variants={stagger.container} initial="hidden" animate="show" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {d.units.map((u) => {
              const margin = u.floor_rent ? (u.rent - u.floor_rent) / u.floor_rent : 0;
              return (
                <motion.article key={u.id} variants={stagger.item} className="card card-hover overflow-hidden">
                  <div className="relative aspect-[16/10] overflow-hidden bg-brand-50 dark:bg-white/5">
                    <img src={coverImage({ id: u.id, title: u.title, category: "apartment" })} alt="" className="h-full w-full object-cover transition-transform duration-500 hover:scale-105" loading="lazy" />
                    <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/60 to-transparent" />
                    <div className="absolute start-3 top-3">
                      <StatusBadge status={u.status} />
                    </div>
                    <div className="absolute bottom-3 start-3 text-white">
                      <p className="font-display text-xl font-bold">{pkr(u.rent)}</p>
                      <p className="text-[11px] text-white/80">per month</p>
                    </div>
                  </div>
                  <div className="space-y-3 p-4">
                    <div>
                      <h3 className="line-clamp-1 font-display font-semibold">{u.title}</h3>
                      <p className="text-xs text-ink-mute">{[u.scheme, u.city].filter(Boolean).join(", ") || "—"}</p>
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-ink-soft dark:text-slate-300">
                      {u.bedrooms ? (
                        <span className="inline-flex items-center gap-1">
                          <BedDouble className="h-3.5 w-3.5" /> {u.bedrooms} bed
                        </span>
                      ) : null}
                      {u.area ? (
                        <span className="inline-flex items-center gap-1">
                          <Ruler className="h-3.5 w-3.5" /> {num(u.area)} sqft
                        </span>
                      ) : null}
                      <span className="inline-flex items-center gap-1">
                        <KeyRound className="h-3.5 w-3.5" /> {pkrShort(u.deposit, false)} deposit
                      </span>
                    </div>
                    <div className="rounded-xl bg-brand-50/60 p-2.5 dark:bg-white/5">
                      <div className="flex items-center justify-between text-[11px] font-semibold">
                        <span className="text-ink-mute">Rent floor {pkrShort(u.floor_rent, false)}</span>
                        <span className={margin >= 0.1 ? "text-brand-700 dark:text-brand-300" : margin >= 0 ? "text-gold-700" : "text-red-600"}>{margin >= 0 ? "+" : ""}{pct(margin, 0)} headroom</span>
                      </div>
                      <Progress value={Math.min(100, (u.floor_rent / Math.max(1, u.rent)) * 100)} className="mt-1.5 h-1.5" tone={margin >= 0.1 ? "green" : margin >= 0 ? "gold" : "red"} />
                    </div>
                    {u.amenities.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {u.amenities.slice(0, 4).map((a) => (
                          <span key={a} className="rounded-full bg-black/5 px-2 py-0.5 text-[11px] font-medium dark:bg-white/10">
                            {a}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.article>
              );
            })}
          </motion.div>
        ) : (
          <EmptyState title="No rental units" action={<Button size="sm" onClick={onAdd}>Add a unit</Button>} />
        )
      }
    </QueryState>
  );
}

// ================================================================== agent simulator
const PROMPTS = ["Is it still available?", "What is the rent and deposit?", "Is there backup power and parking?", "Can I book a viewing this Saturday?", "How do I apply?", "Any good schools nearby?"];

function AgentSimulator({ units, funnel }: { units: Unit[]; funnel: ReturnType<typeof useApi<Funnel>> }) {
  const [unitId, setUnitId] = useState("");
  const [channel, setChannel] = useState("web_chat");
  const [lang, setLang] = useState("en");
  const [msg, setMsg] = useState("");
  const [session, setSession] = useState<Inquiry[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!unitId && units.length) setUnitId(units[0].id);
  }, [units, unitId]);
  const history = useApi<{ count: number; inquiries: Inquiry[] }>("/leasing/inquiries", { unit_id: unitId || undefined });
  const unit = units.find((u) => u.id === unitId);

  const send = useMutate((m: string) => post<Inquiry>("/leasing/inquiries", { message: m, unit_id: unitId || undefined, channel, lang }).then(ensure), {
    invalidate: ["/leasing/funnel", "/portal"],
    onSuccess: (r) => {
      setSession((s) => [...s, r]);
      setMsg("");
    },
  });
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [session.length, send.isPending]);
  useEffect(() => setSession([]), [unitId]);

  const past = (history.data?.inquiries ?? []).filter((i) => !session.some((s) => s.id === i.id)).slice(-4);
  const thread = [...past, ...session];
  const submit = (m: string) => {
    const t = m.trim();
    if (t && !send.isPending) send.mutate(t);
  };

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card className="flex min-h-[520px] flex-col overflow-hidden lg:col-span-2">
        <div className="flex flex-wrap items-center gap-3 border-b border-black/5 bg-brand-gradient px-4 py-3 text-white dark:border-white/10">
          <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-white/15">
            <Bot className="h-5 w-5" />
            <span className="absolute bottom-0 end-0 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-brand-800" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">Autonomous leasing agent</p>
            <p className="truncate text-xs text-white/70">{unit ? unit.title : "Any unit"} · replies 24/7</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select value={unitId} onChange={(e) => setUnitId(e.target.value)} className="rounded-lg border border-white/20 bg-white/10 px-2 py-1 text-xs text-white focus:outline-none [&>option]:text-ink">
              <option value="">Any unit</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.title}
                </option>
              ))}
            </select>
            <select value={channel} onChange={(e) => setChannel(e.target.value)} className="rounded-lg border border-white/20 bg-white/10 px-2 py-1 text-xs text-white focus:outline-none [&>option]:text-ink">
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {titleCase(c)}
                </option>
              ))}
            </select>
            <select value={lang} onChange={(e) => setLang(e.target.value)} className="rounded-lg border border-white/20 bg-white/10 px-2 py-1 text-xs text-white focus:outline-none [&>option]:text-ink">
              <option value="en">English</option>
              <option value="ur">Urdu</option>
            </select>
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto bg-[radial-gradient(circle_at_1px_1px,rgba(15,90,57,.07)_1px,transparent_0)] bg-[length:18px_18px] p-4">
          {history.isLoading && <Skeleton className="h-16 w-2/3" />}
          {thread.length === 0 && !history.isLoading && (
            <div className="flex h-full flex-col items-center justify-center gap-2 py-10 text-center text-sm text-ink-mute">
              <MessageCircle className="h-8 w-8 text-brand-400" />
              Ask the agent anything a prospective tenant would.
            </div>
          )}
          <AnimatePresence initial={false}>
            {thread.map((i) => (
              <motion.div key={i.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-2">
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-ee-sm bg-brand-700 px-4 py-2.5 text-sm text-white shadow-sm">
                    {i.message}
                    <p className="mt-1 text-end text-[10px] text-white/60">
                      {titleCase(i.channel)} · {timeAgo(i.created_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-end gap-2">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gold-gradient text-brand-950">
                    <Bot className="h-4 w-4" />
                  </span>
                  <div className="max-w-[85%] rounded-2xl rounded-es-sm border border-black/5 bg-white px-4 py-2.5 text-sm shadow-sm dark:border-white/10 dark:bg-[#12261b]">
                    {i.reply}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <Badge tone="blue">{titleCase(i.intent)}</Badge>
                      <Badge tone={i.auto_handled ? "green" : "orange"}>{i.auto_handled ? "Auto-handled" : "Escalated to human"}</Badge>
                      <span className="text-[10px] font-semibold text-ink-mute">lead score {i.lead_score}</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          {send.isPending && (
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gold-gradient text-brand-950">
                <Bot className="h-4 w-4" />
              </span>
              <span className="flex gap-1 rounded-2xl bg-white px-4 py-3 shadow-sm dark:bg-[#12261b]">
                {[0, 1, 2].map((k) => (
                  <motion.span key={k} className="h-1.5 w-1.5 rounded-full bg-brand-500" animate={{ y: [0, -4, 0] }} transition={{ duration: 0.8, repeat: Infinity, delay: k * 0.15 }} />
                ))}
              </span>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="border-t border-black/5 p-3 dark:border-white/10">
          <div className="no-scrollbar mb-2 flex gap-2 overflow-x-auto">
            {PROMPTS.map((p) => (
              <button key={p} type="button" onClick={() => submit(p)} className="shrink-0 rounded-full border border-brand-200 bg-brand-50/60 px-3 py-1 text-xs font-medium text-brand-800 transition-colors hover:bg-brand-100 dark:border-white/10 dark:bg-white/5 dark:text-brand-100">
                {p}
              </button>
            ))}
          </div>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              submit(msg);
            }}
          >
            <Input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Type a tenant message…" />
            <Button type="submit" size="icon" aria-label="Send" loading={send.isPending} disabled={!msg.trim()}>
              {!send.isPending && <Send className="h-4 w-4 rtl:-scale-x-100" />}
            </Button>
          </form>
        </div>
      </Card>

      <Panel title="Leasing funnel" subtitle="Inquiry → application" icon={<Filter className="h-4 w-4" />}>
        <QueryState q={funnel} skeleton={<Skeleton className="h-80" />}>
          {(f) => {
            const steps = [
              { label: "Inquiries", value: f.inquiries },
              { label: "Auto-handled", value: f.auto_handled },
              { label: "Applications", value: f.applications },
            ];
            const max = Math.max(1, f.inquiries);
            return (
              <div className="space-y-5">
                <div className="space-y-2">
                  {steps.map((s, i) => (
                    <div key={s.label} className="flex justify-center">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.max(28, (s.value / max) * 100)}%` }}
                        transition={{ duration: 0.6, delay: i * 0.08 }}
                        className={cn("flex items-center justify-between rounded-xl px-3 py-2 text-xs font-semibold text-white", ["bg-brand-700", "bg-brand-500", "bg-gold-500"][i])}
                      >
                        <span className="truncate">{s.label}</span>
                        <span className="tabular-nums">{s.value}</span>
                      </motion.div>
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <MiniStat label="Escalated" value={f.escalated} tone={f.escalated ? "gold" : "default"} />
                  <MiniStat label="Avg score" value={num(f.avg_inquiry_score, 1)} tone="green" />
                </div>
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">By channel</p>
                  <BarList items={Object.entries(f.by_channel).map(([k, v]) => ({ label: titleCase(k), value: v }))} />
                </div>
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-mute">By intent</p>
                  <BarList tone="gold" items={Object.entries(f.by_intent).map(([k, v]) => ({ label: titleCase(k), value: v }))} />
                </div>
              </div>
            );
          }}
        </QueryState>
      </Panel>
    </div>
  );
}

// ================================================================== screening
function ScreeningForm({ units }: { units: Unit[] }) {
  const canManage = useAuth((s) => s.can("properties.manage"));
  const applications = useApi<{ count: number; applications: { id: string; applicant: string; email?: string; phone?: string; property_title?: string; monthly_income: number; created_at: string; screening?: { decision?: string; score?: number; explanation?: string[] } }[] }>(canManage ? "/leasing/applications" : null);
  const [f, set] = useFormState({ applicant: "", monthly_income: "", unit_id: "", employment: "salaried", references_count: "2", credit_proxy: 70, occupants: "2", pets: false, move_in_days: "15" });
  useEffect(() => {
    if (!f.unit_id && units.length) set("unit_id")(units[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [units]);
  const unit = units.find((u) => u.id === f.unit_id);
  const apply = useMutate(
    () =>
      post<Screening>("/leasing/apply", {
        applicant: f.applicant.trim(),
        monthly_income: numOr(f.monthly_income, 0),
        unit_id: f.unit_id || undefined,
        employment: f.employment,
        references_count: numOr(f.references_count, 0),
        credit_proxy: f.credit_proxy,
        occupants: numOr(f.occupants, 1),
        pets: f.pets,
        move_in_days: numOr(f.move_in_days, 15),
      }).then(ensure),
    { invalidate: INVALIDATE, success: (r) => `Decision: ${titleCase(r.decision)}` },
  );
  const r = apply.data;
  const verdict = r
    ? {
        approve: { tone: "from-brand-600 to-brand-800", label: "Approved", icon: "✓" },
        conditional: { tone: "from-gold-500 to-gold-700", label: "Conditional", icon: "!" },
        decline: { tone: "from-red-500 to-red-700", label: "Declined", icon: "✕" },
      }[r.decision as "approve" | "conditional" | "decline"] ?? { tone: "from-slate-500 to-slate-700", label: titleCase(r.decision), icon: "?" }
    : null;

  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <Panel title="Rental application" subtitle="Instant AI screening against the unit's rent" icon={<UserRound className="h-4 w-4" />} className="lg:col-span-3">
        <FormGrid>
          <Field label="Applicant *">
            <Input value={f.applicant} onChange={(e) => set("applicant")(e.target.value)} placeholder="Full name" />
          </Field>
          <Field label="Unit">
            <Select value={f.unit_id} onChange={(e) => set("unit_id")(e.target.value)}>
              <option value="">No specific unit</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.title} · {pkrShort(u.rent, false)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Monthly income (PKR) *" hint={unit && numOr(f.monthly_income) ? `${(Number(f.monthly_income) / unit.rent).toFixed(2)}× rent` : undefined}>
            <Input type="number" min={0} value={f.monthly_income} onChange={(e) => set("monthly_income")(e.target.value)} placeholder="300000" />
          </Field>
          <Field label="Employment">
            <Select value={f.employment} onChange={(e) => set("employment")(e.target.value)} options={["salaried", "business", "self_employed", "retired", "student"].map((x) => ({ value: x, label: titleCase(x) }))} />
          </Field>
          <Field label="References">
            <Input type="number" min={0} max={5} value={f.references_count} onChange={(e) => set("references_count")(e.target.value)} />
          </Field>
          <Field label="Occupants">
            <Input type="number" min={1} value={f.occupants} onChange={(e) => set("occupants")(e.target.value)} />
          </Field>
          <Field label={`Credit proxy · ${f.credit_proxy}`} className="sm:col-span-2">
            <Slider value={f.credit_proxy} min={0} max={100} onChange={set("credit_proxy")} />
          </Field>
          <Field label="Move in within (days)">
            <Input type="number" min={0} value={f.move_in_days} onChange={(e) => set("move_in_days")(e.target.value)} />
          </Field>
          <div className="flex items-end pb-2">
            <Toggle checked={f.pets} onChange={set("pets")} label={<span className="text-sm">Has pets</span>} />
          </div>
        </FormGrid>
        <div className="mt-5 flex justify-end">
          <Button icon={<ShieldCheck className="h-4 w-4" />} disabled={!f.applicant.trim() || !numOr(f.monthly_income)} loading={apply.isPending} onClick={() => apply.mutate()}>
            Screen applicant
          </Button>
        </div>
      </Panel>

      <div className="lg:col-span-2">
        {r && verdict ? (
          <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="card overflow-hidden">
            <div className={cn("flex items-center gap-4 bg-gradient-to-br p-5 text-white", verdict.tone)}>
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/20 font-display text-2xl font-bold">{verdict.icon}</span>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-white/75">Verdict</p>
                <p className="font-display text-2xl font-bold">{verdict.label}</p>
              </div>
            </div>
            <div className="space-y-4 p-5">
              <div className="flex items-center gap-4">
                <ScoreRing value={r.score} label="score" />
                <div className="grid flex-1 grid-cols-1 gap-2">
                  <MiniStat label="Income / rent" value={`${r.income_to_rent.toFixed(2)}×`} tone={r.income_to_rent >= 2.5 ? "green" : "gold"} />
                  <MiniStat label="Recommended deposit" value={r.recommended_deposit ? pkrShort(r.recommended_deposit, false) : "—"} />
                </div>
              </div>
              {r.conditions.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wider text-ink-mute">Conditions</p>
                  <ul className="space-y-1">
                    {r.conditions.map((c) => (
                      <li key={c} className="rounded-lg bg-gold-50 px-3 py-1.5 text-sm text-gold-800 dark:bg-gold-500/10 dark:text-gold-100">
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap gap-1.5">
                {r.explanation.map((e) => (
                  <Badge key={e} tone="gray">
                    {e}
                  </Badge>
                ))}
              </div>
            </div>
          </motion.div>
        ) : (
          <Card className="flex h-full min-h-[280px] items-center justify-center p-6">
            <EmptyState title="No decision yet" hint="Fill the application and screen it — the verdict appears here." icon={<ClipboardCheck className="h-6 w-6" />} />
          </Card>
        )}
      </div>
      {canManage && <div className="lg:col-span-5">
        <Panel title="Submitted tenant applications" subtitle="Applications received from public rental listings, with a preliminary screening summary." icon={<ClipboardCheck className="h-4 w-4" />}>
          {applications.isLoading ? <Skeleton className="h-24" /> : applications.error ? <p className="text-sm text-red-600">Could not load applications: {String(applications.error)}</p> : !(applications.data?.applications.length) ? <p className="text-sm text-ink-mute">No online tenant applications yet.</p> : <div className="space-y-3">{applications.data.applications.map((a) => <div key={a.id} className="flex flex-col gap-2 rounded-xl border border-black/5 p-4 sm:flex-row sm:items-center dark:border-white/10"><div className="min-w-0 flex-1"><p className="font-semibold">{a.applicant}</p><p className="text-xs text-ink-mute">{a.property_title ?? "Rental listing"} · {a.email || a.phone || "No contact"} · {a.created_at ? new Date(a.created_at).toLocaleDateString() : ""}</p></div><p className="text-sm">Income {pkrShort(a.monthly_income, false)} / mo</p><Badge tone={a.screening?.decision === "approve" ? "green" : a.screening?.decision === "decline" ? "red" : "gold"}>{titleCase(a.screening?.decision ?? "pending review")} · {a.screening?.score ?? "—"}</Badge></div>)}</div>}
        </Panel>
      </div>}
    </div>
  );
}

// ================================================================== renewals + collection
function RenewalsAndCollection({ collection }: { collection: ReturnType<typeof useApi<Collection>> }) {
  const [uplift, setUplift] = useState(8);
  const up = useDebounced(uplift, 300);
  const renewals = useApi<{ count: number; uplift: number; renewals: Renewal[] }>("/leasing/renewals", { uplift: up / 100 });
  const roll = useApi<{ tenants: { tenant: string; unit_label?: string | null; rent_amount: number; status: string }[] }>("/accounting/rent-roll");

  // The renewals endpoint omits tenant names; join with the rent roll (same order, matched on rent).
  const rows: Renewal[] = useMemo(() => {
    const list = renewals.data?.renewals ?? [];
    const tenants = (roll.data?.tenants ?? []).filter((t) => t.status === "active");
    const used = new Set<number>();
    return list.map((r, i) => {
      let idx = tenants.findIndex((t, j) => !used.has(j) && Math.abs(t.rent_amount - r.current_rent) < 1);
      if (idx < 0 && tenants[i] && !used.has(i)) idx = i;
      if (idx >= 0) used.add(idx);
      const t = idx >= 0 ? tenants[idx] : undefined;
      return { ...r, tenant: t?.tenant ?? `Lease ${i + 1}`, unit: t?.unit_label ?? undefined };
    });
  }, [renewals.data, roll.data]);

  return (
    <div className="space-y-6">
      <Panel
        title="Renewal recommendations"
        subtitle="Retention-aware rent proposals for every active lease"
        icon={<Repeat className="h-4 w-4" />}
        flush
        action={
          <div className="flex w-44 items-center gap-2">
            <span className="shrink-0 text-xs font-semibold">Uplift {uplift}%</span>
            <Slider value={uplift} min={0} max={20} onChange={setUplift} />
          </div>
        }
      >
        <QueryState q={renewals} skeleton={<div className="p-5"><Skeleton className="h-48" /></div>}>
          {() => (
            <DataTable
              rows={rows}
              rowKey={(r, i) => `${r.tenant}-${i}`}
              columns={[
                {
                  key: "tenant",
                  header: "Tenant",
                  render: (r) => (
                    <div className="min-w-[140px]">
                      <p className="font-semibold">{r.tenant}</p>
                      <p className="text-xs text-ink-mute">{r.unit ?? "—"}</p>
                    </div>
                  ),
                },
                { key: "current_rent", header: "Current", align: "right", render: (r) => num(r.current_rent) },
                { key: "market_rent", header: "Market", align: "right", render: (r) => num(r.market_rent) },
                {
                  key: "proposed_renewal_rent",
                  header: "Proposed",
                  align: "right",
                  render: (r) => (
                    <span className="whitespace-nowrap font-semibold text-brand-700 dark:text-brand-300">
                      {num(r.proposed_renewal_rent)} <span className="text-xs font-normal text-ink-mute">+{r.uplift_pct}%</span>
                    </span>
                  ),
                },
                { key: "retention_risk", header: "Risk", render: (r) => <Badge tone={r.retention_risk === "high" ? "red" : r.retention_risk === "medium" ? "gold" : "green"}>{titleCase(r.retention_risk)}</Badge> },
                { key: "days_to_expiry", header: "Expires", align: "right", render: (r) => <span className="text-xs">{num(r.days_to_expiry)}d</span> },
                { key: "recommendation", header: "Action", render: (r) => <StatusBadge status={r.recommendation} /> },
                { key: "vacancy_cost_if_lost", header: "Vacancy risk", align: "right", render: (r) => <span className="text-xs">{pkrShort(r.vacancy_cost_if_lost, false)}</span> },
              ]}
              empty={<EmptyState title="No active leases" />}
            />
          )}
        </QueryState>
      </Panel>

      <div>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="section-eyebrow">Collection board</p>
            <h3 className="mt-1 font-display text-lg font-semibold">Rent collection from the ledger</h3>
          </div>
          {collection.data && (
            <div className="flex gap-2">
              <Badge tone="red">{pkrShort(collection.data.total_outstanding)} outstanding</Badge>
              <Badge tone="gray">
                {collection.data.in_arrears}/{collection.data.leases} in arrears
              </Badge>
            </div>
          )}
        </div>
        <QueryState q={collection} skeleton={<SkeletonGrid n={4} tile="h-32" />}>
          {(c) => {
            const max = Math.max(1, ...c.rows.map((r) => r.outstanding));
            return c.rows.length ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[...c.rows]
                  .sort((a, b) => b.outstanding - a.outstanding)
                  .map((r) => (
                    <div key={r.lease_id} className={cn("rounded-2xl border p-4", r.outstanding > 0 ? "border-red-200 bg-red-50/40 dark:border-red-500/20 dark:bg-red-500/5" : "border-brand-200 bg-brand-50/40 dark:border-brand-500/20 dark:bg-brand-500/5")}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate font-semibold">{r.tenant}</p>
                          <p className="truncate text-xs text-ink-mute">{r.unit}</p>
                        </div>
                        <StatusBadge status={r.status === "in_arrears" ? "overdue" : r.status} />
                      </div>
                      <p className={cn("mt-3 font-display text-xl font-bold", r.outstanding > 0 ? "text-red-700 dark:text-red-300" : "text-brand-700")}>{pkrShort(r.outstanding, false)}</p>
                      <Progress value={(r.outstanding / max) * 100} tone={r.outstanding > 0 ? "red" : "green"} className="mt-2 h-1.5" />
                    </div>
                  ))}
              </div>
            ) : (
              <EmptyState title="No leases to collect" />
            );
          }}
        </QueryState>
      </div>
    </div>
  );
}

// ================================================================== rent floor
function RentFloor({ units }: { units: Unit[] }) {
  const [cost, setCost] = useState("70000");
  const [margin, setMargin] = useState(3);
  const c = useDebounced(cost);
  const m = useDebounced(margin);
  const q = useApi<{ monthly_holding_cost: number; margin: number; rent_floor: number }>(numOr(c) ? "/leasing/rent-floor" : null, { monthly_holding_cost: c, margin: m / 100 });
  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <Panel title="Rent floor calculator" subtitle="Minimum rent that keeps a unit cash-flow positive" icon={<Calculator className="h-4 w-4" />} className="lg:col-span-2">
        <div className="space-y-5">
          <Field label="Monthly holding cost (PKR)" hint="Mortgage / financing, service charges, insurance, upkeep">
            <Input type="number" min={0} value={cost} onChange={(e) => setCost(e.target.value)} icon={<Coins className="h-4 w-4" />} />
          </Field>
          <Field label={`Safety margin · ${margin}%`}>
            <Slider value={margin} min={0} max={30} onChange={setMargin} />
          </Field>
          <div className="rounded-2xl bg-brand-gradient p-5 text-white">
            <p className="text-xs font-semibold uppercase tracking-wider text-gold-200">Rent floor</p>
            {q.isFetching && !q.data ? (
              <Skeleton className="mt-2 h-9 w-40 bg-white/10" />
            ) : (
              <p className="mt-1 font-display text-3xl font-bold">{q.data ? pkr(q.data.rent_floor) : "—"}</p>
            )}
            <p className="mt-1 text-xs text-white/70">per month · {q.data ? pct(q.data.margin, 0) : `${margin}%`} above holding cost</p>
          </div>
          {q.error && <p className="text-sm text-red-600">{q.error.message}</p>}
        </div>
      </Panel>
      <Panel title="Portfolio check" subtitle="Each unit's asking rent vs its own floor" icon={<Building className="h-4 w-4" />} className="lg:col-span-3">
        {units.length ? (
          <ul className="space-y-3">
            {units.map((u) => {
              const head = u.floor_rent ? (u.rent - u.floor_rent) / u.floor_rent : 0;
              return (
                <li key={u.id} className="rounded-xl border border-black/5 p-3 dark:border-white/10">
                  <div className="flex items-center justify-between gap-3">
                    <p className="min-w-0 truncate text-sm font-semibold">{u.title}</p>
                    <Badge tone={head >= 0.1 ? "green" : head >= 0 ? "gold" : "red"}>{head >= 0 ? "+" : ""}{pct(head, 0)}</Badge>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                    <span>
                      <span className="block text-ink-mute">Holding</span>
                      {num(u.monthly_holding_cost)}
                    </span>
                    <span>
                      <span className="block text-ink-mute">Floor</span>
                      {num(u.floor_rent)}
                    </span>
                    <span>
                      <span className="block text-ink-mute">Asking</span>
                      <strong>{num(u.rent)}</strong>
                    </span>
                  </div>
                  <button type="button" className="link mt-2 text-xs" onClick={() => setCost(String(u.monthly_holding_cost))}>
                    Use this unit's holding cost
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState title="No units yet" />
        )}
      </Panel>
    </div>
  );
}

// ================================================================== add unit
function AddUnitModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [f, set, reset] = useFormState({ title: "", rent: "", deposit: "", city: "Lahore", scheme: "", bedrooms: "2", area: "", monthly_holding_cost: "", amenities: "" });
  const create = useMutate(
    () =>
      post("/leasing/units", {
        title: f.title.trim(),
        rent: numOr(f.rent, 0),
        deposit: numOr(f.deposit, 0),
        city: f.city || undefined,
        scheme: f.scheme || undefined,
        bedrooms: numOr(f.bedrooms),
        area: numOr(f.area),
        monthly_holding_cost: numOr(f.monthly_holding_cost, 0),
        amenities: f.amenities
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      }).then(ensure),
    {
      invalidate: INVALIDATE,
      success: "Unit added",
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
      title="Add rental unit"
      subtitle="The leasing agent starts answering for it immediately"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} disabled={!f.title.trim() || !numOr(f.rent)} onClick={() => create.mutate()}>
            Add unit
          </Button>
        </>
      }
    >
      <FormGrid>
        <Field label="Title *" className="sm:col-span-2">
          <Input value={f.title} onChange={(e) => set("title")(e.target.value)} placeholder="e.g. 2-bed Apartment — Bahria Town" autoFocus />
        </Field>
        <Field label="Monthly rent (PKR) *">
          <Input type="number" min={0} value={f.rent} onChange={(e) => set("rent")(e.target.value)} />
        </Field>
        <Field label="Security deposit (PKR)">
          <Input type="number" min={0} value={f.deposit} onChange={(e) => set("deposit")(e.target.value)} />
        </Field>
        <Field label="City">
          <Select value={f.city} onChange={(e) => set("city")(e.target.value)} options={["Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta"]} />
        </Field>
        <Field label="Society / area">
          <Input value={f.scheme} onChange={(e) => set("scheme")(e.target.value)} placeholder="DHA Lahore" />
        </Field>
        <Field label="Bedrooms">
          <Input type="number" min={0} value={f.bedrooms} onChange={(e) => set("bedrooms")(e.target.value)} />
        </Field>
        <Field label="Area (sqft)">
          <Input type="number" min={0} value={f.area} onChange={(e) => set("area")(e.target.value)} />
        </Field>
        <Field label="Monthly holding cost (PKR)" hint="Used to compute the rent floor">
          <Input type="number" min={0} value={f.monthly_holding_cost} onChange={(e) => set("monthly_holding_cost")(e.target.value)} />
        </Field>
        <Field label="Amenities" hint="Comma separated">
          <Input value={f.amenities} onChange={(e) => set("amenities")(e.target.value)} placeholder="lift, parking, backup power" />
        </Field>
      </FormGrid>
    </Modal>
  );
}

