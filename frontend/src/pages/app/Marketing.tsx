import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  CalendarRange,
  Check,
  Filter,
  GitBranch,
  Megaphone,
  PenSquare,
  Plus,
  RadioTower,
  Rocket,
  Route,
  Sparkles,
  Target,
  TrendingUp,
  UserRoundSearch,
  Users,
  Wand2,
} from "lucide-react";
import { post } from "@/lib/api";
import { useApi, useMutate } from "@/hooks/useApi";
import { num, pct, pkr, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Badge,
  BarList,
  Button,
  Card,
  CopyButton,
  Donut,
  EmptyState,
  Field,
  Input,
  Legendish,
  Modal,
  PageHeader,
  QueryState,
  Segmented,
  Select,
  Skeleton,
  StatCard,
  StatusBadge,
  Tabs,
  Textarea,
} from "@/components/ui";
import { FormGrid, MiniStat, Panel, SkeletonGrid, bandTone, ensure, numOr, stagger, useFormState } from "@/components/biz/ops-kit";
import type { Agent, AgentsRes, LeadsRes } from "@/components/biz/crm-types";
import type { PropertyList } from "@/types";

// ------------------------------------------------------------------ types
interface Funnel {
  leads: number;
  by_stage: Record<string, number>;
  by_band: Record<string, number>;
  by_channel: Record<string, number>;
  qualified: number;
  won: number;
  conversion_pct: number;
}
interface Channels {
  channels: Record<string, number>;
  lead_stages: string[];
  content_kinds: string[];
}
interface Asset {
  id: string;
  kind: string;
  ref?: string | null;
  lang: string;
  body: string;
  status: string;
  requires_approval: boolean;
  created_at: string;
}
interface RouteRule {
  id: string;
  name: string;
  priority: number;
  match: Record<string, unknown>;
  assign_to_agent_id?: string | null;
  queue: string;
  sla_hours: number;
  active: boolean;
}
interface Campaign {
  id: string;
  objective: string;
  budget: number;
  channels: string[];
  days: number;
  schedule: { day: number; channel: string; action: string }[];
  kpis: { expected_leads: number; cost_per_lead: number; target_qualified_rate: number; expected_qualified: number; audience?: number | null };
}
interface Revived {
  id: string;
  name: string;
  score: number;
  band: string;
  stage: string;
  last_contact_days: number;
  reason: string;
  outreach: string;
}

type TabKey = "funnel" | "content" | "campaigns" | "reengage" | "routing";
const TONES = ["professional", "luxury", "urgent", "family"];
const LISTING_KINDS = ["listing_description", "social_post", "reel_script", "video_script", "email"];
const CAMPAIGN_CHANNELS = ["whatsapp", "website", "instagram", "facebook", "sms", "email"];
const CHANNEL_WEIGHTS: Record<string, number> = { whatsapp: 0.3, website: 0.25, instagram: 0.15, facebook: 0.12, sms: 0.1, email: 0.08 };
const FUNNEL_COLORS = ["#093a26", "#0f5a39", "#146f45", "#1f8a57", "#3da772", "#c99a22"];

export default function Marketing() {
  const [tab, setTab] = useState<TabKey>("funnel");
  const [generating, setGenerating] = useState(false);
  const funnel = useApi<Funnel>("/marketing/funnel");
  const channels = useApi<Channels>("/marketing/channels");
  const content = useApi<{ count: number; assets: Asset[] }>("/marketing/content");
  const drafts = (content.data?.assets ?? []).filter((a) => a.status === "draft").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Marketing"
        subtitle="AI marketing conductor — funnel, content, campaigns, re-engagement and lead routing"
        actions={
          <>
            <Button variant="outline" size="sm" icon={<Rocket className="h-4 w-4" />} onClick={() => setTab("campaigns")}>
              Plan campaign
            </Button>
            <Button size="sm" variant="gold" icon={<Sparkles className="h-4 w-4" />} onClick={() => setGenerating(true)}>
              Generate content
            </Button>
          </>
        }
      />

      <QueryState q={funnel} skeleton={<SkeletonGrid n={4} />}>
        {(f) => (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Leads in funnel" value={num(f.leads)} icon={<Users className="h-5 w-5" />} hint={`${Object.keys(f.by_channel).length} channels`} />
            <StatCard label="Qualified" value={num(f.qualified)} icon={<BadgeCheck className="h-5 w-5" />} hint={f.leads ? `${pct(f.qualified / f.leads, 0)} of leads` : undefined} tone="blue" />
            <StatCard label="Won" value={num(f.won)} icon={<TrendingUp className="h-5 w-5" />} hint={`${f.conversion_pct.toFixed(1)}% conversion`} tone="gold" />
            <StatCard label="Content awaiting approval" value={drafts} icon={<PenSquare className="h-5 w-5" />} hint={`${content.data?.count ?? 0} assets`} tone={drafts ? "purple" : "green"} />
          </div>
        )}
      </QueryState>

      <Card className="overflow-hidden">
        <Tabs<TabKey>
          className="px-2"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "funnel", label: "Funnel & channels", icon: <Filter className="h-4 w-4" /> },
            { value: "content", label: "Content", icon: <PenSquare className="h-4 w-4" />, count: drafts || undefined },
            { value: "campaigns", label: "Campaign planner", icon: <Rocket className="h-4 w-4" /> },
            { value: "reengage", label: "Re-engagement", icon: <UserRoundSearch className="h-4 w-4" /> },
            { value: "routing", label: "Lead routing", icon: <Route className="h-4 w-4" /> },
          ]}
        />
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="p-4 sm:p-5">
          {tab === "funnel" && <FunnelTab funnel={funnel} channels={channels} />}
          {tab === "content" && <ContentTab q={content} onGenerate={() => setGenerating(true)} />}
          {tab === "campaigns" && <CampaignPlanner />}
          {tab === "reengage" && <ReengagementTab />}
          {tab === "routing" && <RoutingTab />}
        </motion.div>
      </Card>

      <GenerateContentModal open={generating} onClose={() => setGenerating(false)} kinds={channels.data?.content_kinds} />
    </div>
  );
}

// ================================================================== funnel
function TaperedFunnel({ stages }: { stages: { label: string; value: number; atStage: number }[] }) {
  const max = Math.max(1, stages[0]?.value ?? 1);
  const widths = stages.map((s) => Math.max(14, (s.value / max) * 100));
  return (
    <div className="space-y-1.5">
      {stages.map((s, i) => {
        const w = widths[i];
        const next = widths[i + 1] ?? w * 0.85;
        const inset = Math.max(0, ((w - next) / 2 / w) * 100);
        const conv = i > 0 && stages[i - 1].value ? s.value / stages[i - 1].value : null;
        return (
          <div key={s.label} className="flex items-center gap-3">
            <div className="w-24 shrink-0 text-end text-xs font-semibold text-ink-soft sm:w-28 dark:text-slate-300">{s.label}</div>
            <div className="relative flex flex-1 justify-center">
              <motion.div
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: `${w}%`, opacity: 1 }}
                transition={{ duration: 0.6, delay: i * 0.07 }}
                className="flex h-11 items-center justify-center text-sm font-bold text-white"
                style={{ background: FUNNEL_COLORS[i % FUNNEL_COLORS.length], clipPath: `polygon(0 0, 100% 0, ${100 - inset}% 100%, ${inset}% 100%)` }}
              >
                <span className="tabular-nums">{s.value}</span>
              </motion.div>
            </div>
            <div className="w-16 shrink-0 text-xs text-ink-mute">
              {conv !== null ? <span className={cn("font-semibold", conv >= 0.5 ? "text-brand-700 dark:text-brand-300" : "text-gold-700")}>{pct(conv, 0)}</span> : "—"}
              <span className="block text-[10px]">{s.atStage} here</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FunnelTab({ funnel, channels }: { funnel: ReturnType<typeof useApi<Funnel>>; channels: ReturnType<typeof useApi<Channels>> }) {
  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <Panel title="Lead funnel" subtitle="Leads that reached each stage (cumulative)" icon={<Filter className="h-4 w-4" />} className="lg:col-span-3">
        <QueryState q={funnel} skeleton={<Skeleton className="h-80" />}>
          {(f) => {
            const order = (channels.data?.lead_stages ?? Object.keys(f.by_stage)).filter((s) => s !== "lost");
            const stages = order.map((s, i) => ({
              label: titleCase(s),
              atStage: f.by_stage[s] ?? 0,
              value: order.slice(i).reduce((acc, k) => acc + (f.by_stage[k] ?? 0), 0),
            }));
            return (
              <div className="space-y-5">
                {f.leads ? <TaperedFunnel stages={stages} /> : <EmptyState title="No leads yet" />}
                <div className="grid grid-cols-3 gap-2">
                  <MiniStat label="Lost" value={f.by_stage.lost ?? 0} tone={f.by_stage.lost ? "red" : "default"} />
                  <MiniStat label="Qualified" value={f.qualified} tone="blue" />
                  <MiniStat label="Conversion" value={`${f.conversion_pct.toFixed(1)}%`} tone="green" />
                </div>
              </div>
            );
          }}
        </QueryState>
      </Panel>
      <div className="space-y-5 lg:col-span-2">
        <Panel title="Lead temperature" subtitle="Score bands" icon={<Target className="h-4 w-4" />}>
          <QueryState q={funnel} skeleton={<Skeleton className="h-48" />}>
            {(f) => {
              const data = (["hot", "warm", "cool", "cold"] as const).map((b, i) => ({ name: titleCase(b), value: f.by_band[b] ?? 0, color: ["#dc2626", "#e4572e", "#c99a22", "#2c7fb8"][i] }));
              return (
                <div className="flex flex-col items-center gap-3 sm:flex-row">
                  <div className="w-40 shrink-0">
                    <Donut data={data} height={150} format={(v) => `${v} leads`} center={<span className="font-display text-xl font-bold">{f.leads}</span>} />
                  </div>
                  <Legendish data={data} />
                </div>
              );
            }}
          </QueryState>
        </Panel>
        <Panel title="Channels" subtitle="Lead quality by source · volume" icon={<RadioTower className="h-4 w-4" />}>
          <QueryState q={channels} skeleton={<Skeleton className="h-64" />}>
            {(c) => (
              <div className="space-y-4">
                <BarList
                  items={Object.entries(c.channels)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => ({ label: `${titleCase(k)}${funnel.data?.by_channel[k] ? ` · ${funnel.data.by_channel[k]} leads` : ""}`, value: Math.round(v * 100) }))}
                  format={(v) => `${v}%`}
                />
                <div>
                  <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-mute">Content kinds</p>
                  <div className="flex flex-wrap gap-1.5">
                    {c.content_kinds.map((k) => (
                      <Badge key={k} tone="purple">
                        {titleCase(k)}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </QueryState>
        </Panel>
      </div>
    </div>
  );
}

// ================================================================== content
function ContentTab({ q, onGenerate }: { q: ReturnType<typeof useApi<{ count: number; assets: Asset[] }>>; onGenerate: () => void }) {
  const [status, setStatus] = useState<"all" | "draft" | "approved">("all");
  const approve = useMutate((id: string) => post(`/marketing/content/${id}/approve`, { approver: "user" }).then(ensure), { invalidate: ["/marketing", "/portal"], success: "Content approved" });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          size="sm"
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "All" },
            { value: "draft", label: "Drafts" },
            { value: "approved", label: "Approved" },
          ]}
        />
        <Button size="sm" variant="gold" icon={<Sparkles className="h-4 w-4" />} onClick={onGenerate}>
          Generate content
        </Button>
      </div>
      <QueryState q={q} skeleton={<div className="grid gap-3 md:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-56" />)}</div>}>
        {(d) => {
          const rows = [...d.assets].reverse().filter((a) => status === "all" || a.status === status);
          return rows.length ? (
            <motion.div variants={stagger.container} initial="hidden" animate="show" className="grid gap-3 md:grid-cols-2">
              {rows.map((a) => (
                <motion.article key={a.id} variants={stagger.item} className="flex flex-col rounded-2xl border border-black/5 bg-white p-4 dark:border-white/10 dark:bg-white/[.02]">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone="purple">{titleCase(a.kind)}</Badge>
                      <Badge tone="gray">{a.lang.toUpperCase()}</Badge>
                      <StatusBadge status={a.status} />
                    </div>
                    <span className="shrink-0 text-[11px] text-ink-mute">{timeAgo(a.created_at)}</span>
                  </div>
                  <p dir="auto" className="mt-3 line-clamp-[8] flex-1 whitespace-pre-line text-sm leading-relaxed text-ink-soft dark:text-slate-300">
                    {a.body}
                  </p>
                  <div className="mt-3 flex items-center justify-between gap-2 border-t border-black/5 pt-3 dark:border-white/10">
                    <CopyButton text={a.body} />
                    {a.status === "draft" ? (
                      <Button size="sm" icon={<Check className="h-4 w-4" />} loading={approve.isPending && approve.variables === a.id} onClick={() => approve.mutate(a.id)}>
                        Approve
                      </Button>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 dark:text-brand-300">
                        <BadgeCheck className="h-4 w-4" /> Ready to publish
                      </span>
                    )}
                  </div>
                </motion.article>
              ))}
            </motion.div>
          ) : (
            <EmptyState title="No content assets" hint="Generate a listing description, social post or market report." icon={<Wand2 className="h-6 w-6" />} />
          );
        }}
      </QueryState>
    </div>
  );
}

function GenerateContentModal({ open, onClose, kinds }: { open: boolean; onClose: () => void; kinds?: string[] }) {
  const [f, set, reset] = useFormState({ kind: "social_post", property_id: "", tone: "professional", lang: "en", topic: "" });
  const props = useApi<PropertyList>(open ? "/properties" : null, { limit: 100 });
  const needsListing = LISTING_KINDS.includes(f.kind);
  const gen = useMutate(
    () =>
      post<{ asset: Asset }>("/marketing/content", {
        kind: f.kind,
        property_id: f.property_id || undefined,
        tone: f.tone,
        lang: f.lang,
        topic: f.topic || undefined,
      }).then(ensure),
    {
      invalidate: ["/marketing", "/portal"],
      success: (r) => `${titleCase(r.asset.kind)} drafted — awaiting approval`,
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
      title="Generate content"
      subtitle="Drafts land in the approval queue"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="gold" icon={<Sparkles className="h-4 w-4" />} loading={gen.isPending} disabled={needsListing && !f.property_id} onClick={() => gen.mutate()}>
            Generate
          </Button>
        </>
      }
    >
      <FormGrid>
        <Field label="Kind" className="sm:col-span-2">
          <Select value={f.kind} onChange={(e) => set("kind")(e.target.value)} options={(kinds ?? [...LISTING_KINDS, "market_report"]).map((k) => ({ value: k, label: titleCase(k) }))} />
        </Field>
        <Field label={needsListing ? "Listing *" : "Listing (optional)"} className="sm:col-span-2">
          <Select value={f.property_id} onChange={(e) => set("property_id")(e.target.value)}>
            <option value="">{needsListing ? "Select a listing…" : "None"}</option>
            {(props.data?.results ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title} · {pkrShort(p.price, false)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Tone">
          <Select value={f.tone} onChange={(e) => set("tone")(e.target.value)} options={TONES.map((t) => ({ value: t, label: titleCase(t) }))} />
        </Field>
        <Field label="Language">
          <Select
            value={f.lang}
            onChange={(e) => set("lang")(e.target.value)}
            options={[
              { value: "en", label: "English" },
              { value: "ur", label: "Urdu" },
            ]}
          />
        </Field>
        {!needsListing && (
          <Field label="Topic" className="sm:col-span-2" hint="e.g. a city or scheme for a market report">
            <Input value={f.topic} onChange={(e) => set("topic")(e.target.value)} placeholder="Lahore" />
          </Field>
        )}
      </FormGrid>
    </Modal>
  );
}

// ================================================================== campaigns
function CampaignPlanner() {
  const [f, set] = useFormState({ objective: "Generate qualified buyer leads for DHA Lahore houses", budget: "250000", days: "14", audience: "" });
  const [chs, setChs] = useState<string[]>(["whatsapp", "website", "instagram"]);
  const plan = useMutate(
    () =>
      post<{ campaign: Campaign }>("/marketing/campaigns", {
        objective: f.objective.trim(),
        budget: numOr(f.budget, 0),
        channels: chs,
        days: numOr(f.days, 14),
        audience: numOr(f.audience),
      }).then(ensure),
    { invalidate: ["/marketing", "/portal"], success: "Campaign plan ready" },
  );
  const c = plan.data?.campaign;
  // The API computes a budget split but doesn't return it; mirror its channel weights.
  const allocation = useMemo(() => {
    if (!c) return [];
    const w = c.channels.map((ch) => CHANNEL_WEIGHTS[ch] ?? 1 / c.channels.length);
    const total = w.reduce((s, x) => s + x, 0) || 1;
    return c.channels.map((ch, i) => ({ label: titleCase(ch), value: Math.round((c.budget * w[i]) / total) }));
  }, [c]);

  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <Panel title="Plan a campaign" subtitle="Multichannel plan with KPIs and a day-by-day schedule" icon={<Megaphone className="h-4 w-4" />} className="lg:col-span-2">
        <div className="space-y-4">
          <Field label="Objective *">
            <Textarea className="min-h-[72px]" value={f.objective} onChange={(e) => set("objective")(e.target.value)} />
          </Field>
          <FormGrid>
            <Field label="Budget (PKR) *" hint={f.budget ? pkrShort(Number(f.budget)) : undefined}>
              <Input type="number" min={0} value={f.budget} onChange={(e) => set("budget")(e.target.value)} />
            </Field>
            <Field label="Duration (days)">
              <Input type="number" min={1} max={90} value={f.days} onChange={(e) => set("days")(e.target.value)} />
            </Field>
            <Field label="Audience size" className="sm:col-span-2">
              <Input type="number" min={0} value={f.audience} onChange={(e) => set("audience")(e.target.value)} placeholder="Optional" />
            </Field>
          </FormGrid>
          <div>
            <p className="label">Channels</p>
            <div className="flex flex-wrap gap-2">
              {CAMPAIGN_CHANNELS.map((ch) => {
                const on = chs.includes(ch);
                return (
                  <button
                    key={ch}
                    type="button"
                    onClick={() => setChs((s) => (on ? s.filter((x) => x !== ch) : [...s, ch]))}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
                      on ? "border-brand-600 bg-brand-700 text-white" : "border-black/10 text-ink-soft hover:border-brand-300 dark:border-white/15 dark:text-slate-300",
                    )}
                  >
                    {on && <Check className="h-3 w-3" />}
                    {titleCase(ch)}
                  </button>
                );
              })}
            </div>
          </div>
          <Button className="w-full justify-center" icon={<Rocket className="h-4 w-4" />} loading={plan.isPending} disabled={!f.objective.trim() || !numOr(f.budget) || !chs.length} onClick={() => plan.mutate()}>
            Build plan
          </Button>
        </div>
      </Panel>

      <div className="min-w-0 lg:col-span-3">
        {c ? (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            <div className="rounded-2xl bg-brand-gradient p-5 text-white">
              <p className="text-xs font-semibold uppercase tracking-wider text-gold-200">Campaign {c.id}</p>
              <p className="mt-1 font-display text-lg font-semibold">{c.objective}</p>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["Budget", pkrShort(c.budget, false)],
                  ["Expected leads", num(c.kpis.expected_leads)],
                  ["Cost / lead", pkr(c.kpis.cost_per_lead)],
                  ["Qualified", `${num(c.kpis.expected_qualified)} (${pct(c.kpis.target_qualified_rate, 0)})`],
                ].map(([l, v]) => (
                  <div key={l} className="rounded-xl bg-white/10 px-3 py-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-white/70">{l}</p>
                    <p className="font-display text-lg font-bold">{v}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-5">
              <Panel title="Budget split" subtitle="Indicative, by channel weight" icon={<GitBranch className="h-4 w-4" />} className="md:col-span-2">
                <BarList tone="gold" items={allocation} format={(v) => pkrShort(v, false)} />
              </Panel>
              <Panel title="Schedule" subtitle={`${c.days} days`} icon={<CalendarRange className="h-4 w-4" />} className="md:col-span-3" flush>
                <ol className="relative max-h-[360px] space-y-0 overflow-y-auto p-5">
                  {c.schedule.map((s, i) => (
                    <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
                      {i < c.schedule.length - 1 && <span className="absolute start-[15px] top-8 h-[calc(100%-1.5rem)] w-px bg-black/10 dark:bg-white/10" />}
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-50 font-display text-xs font-bold text-brand-800 ring-4 ring-white dark:bg-brand-500/15 dark:text-brand-200 dark:ring-[#0d1f16]">
                        {s.day}
                      </span>
                      <div className="min-w-0 pt-1">
                        <p className="text-sm font-semibold">{titleCase(s.action)}</p>
                        <p className="text-xs text-ink-mute">Day {s.day} · {titleCase(s.channel)}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </Panel>
            </div>
          </motion.div>
        ) : (
          <Card className="flex h-full min-h-[320px] items-center justify-center p-6">
            <EmptyState title="No plan yet" hint="Set an objective, budget and channels — the planner returns KPIs and a launch timeline." icon={<Rocket className="h-6 w-6" />} />
          </Card>
        )}
      </div>
    </div>
  );
}

// ================================================================== re-engagement
function ReengagementTab() {
  const [inactive, setInactive] = useState("");
  const [minScore, setMinScore] = useState("");
  const q = useApi<{ scanned: number; candidates: number; revived: Revived[] }>("/marketing/reengagement", { inactive_days: inactive || undefined, min_score: minScore || undefined });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Inactive for (days)" className="w-40">
          <Input type="number" min={1} value={inactive} onChange={(e) => setInactive(e.target.value)} placeholder="Default" />
        </Field>
        <Field label="Min score" className="w-32">
          <Input type="number" min={0} max={100} value={minScore} onChange={(e) => setMinScore(e.target.value)} placeholder="Default" />
        </Field>
        {q.data && (
          <p className="pb-2 text-sm text-ink-mute">
            Scanned <strong>{q.data.scanned}</strong> leads · <strong>{q.data.candidates}</strong> worth reviving
          </p>
        )}
      </div>
      <QueryState q={q} skeleton={<div className="grid gap-3 md:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-40" />)}</div>}>
        {(d) =>
          d.revived.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              {d.revived.map((r) => (
                <div key={r.id} className="rounded-2xl border border-black/5 p-4 dark:border-white/10">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold">{r.name}</p>
                      <p className="text-xs text-ink-mute">{r.reason}</p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge tone={bandTone(r.band)} className="capitalize">
                        {r.band}
                      </Badge>
                      <span className="font-display text-lg font-bold">{r.score}</span>
                    </div>
                  </div>
                  <p className="mt-3 rounded-xl bg-brand-50/60 p-3 text-sm italic text-brand-900 dark:bg-white/5 dark:text-brand-100">“{r.outreach}”</p>
                  <div className="mt-2 flex items-center justify-between text-xs text-ink-mute">
                    <span>
                      {titleCase(r.stage)} · last contact {r.last_contact_days}d ago
                    </span>
                    <CopyButton text={r.outreach} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No dormant leads to revive" hint="Every high-scoring lead has been contacted recently. Try a lower inactivity window or score." icon={<UserRoundSearch className="h-6 w-6" />} />
          )
        }
      </QueryState>
    </div>
  );
}

// ================================================================== routing
function RoutingTab() {
  const routes = useApi<{ count: number; routes: RouteRule[] }>("/marketing/routes");
  const leads = useApi<LeadsRes>("/crm/leads");
  const agents = useApi<AgentsRes>("/crm/agents");
  const agentName = useMemo(() => Object.fromEntries((agents.data?.agents ?? []).map((a) => [a.id, a.name])), [agents.data]);
  const [leadId, setLeadId] = useState("");
  const [adding, setAdding] = useState(false);
  const route = useMutate((id: string) => post<{ lead: { id: string; name: string; band: string }; routing: { matched_rule: string; queue: string; assigned_agent_id?: string | null; sla_hours: number } }>(`/marketing/route/${id}`).then(ensure), {
    invalidate: ["/crm", "/marketing", "/broker"],
    success: (r) => `${r.lead.name} → ${r.routing.queue} queue`,
  });
  const res = route.data;

  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <Panel
        title="Routing rules"
        subtitle="Evaluated in priority order — first match wins"
        icon={<GitBranch className="h-4 w-4" />}
        className="lg:col-span-3"
        flush
        action={
          <Button size="sm" variant="soft" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>
            Add rule
          </Button>
        }
      >
        <QueryState q={routes} skeleton={<div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>}>
          {(d) =>
            d.routes.length ? (
              <ol className="divide-y divide-black/5 dark:divide-white/5">
                {[...d.routes]
                  .sort((a, b) => a.priority - b.priority)
                  .map((r, i) => (
                    <li key={r.id} className={cn("flex items-start gap-3 px-5 py-3.5", res?.routing.matched_rule === r.name && "bg-gold-50/70 dark:bg-gold-500/10")}>
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-50 font-display text-xs font-bold text-brand-800 dark:bg-brand-500/15 dark:text-brand-200">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold">{r.name}</p>
                          {!r.active && <Badge tone="gray">Paused</Badge>}
                          {res?.routing.matched_rule === r.name && <Badge tone="gold">Matched</Badge>}
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {Object.entries(r.match).map(([k, v]) => (
                            <span key={k} className="rounded-md bg-black/5 px-1.5 py-0.5 font-mono text-[11px] dark:bg-white/10">
                              {k}={typeof v === "number" && v >= 100000 ? pkrShort(v, false) : String(v)}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="shrink-0 text-end text-xs">
                        <Badge tone="blue">{r.queue}</Badge>
                        <p className="mt-1 text-ink-mute">SLA {r.sla_hours}h</p>
                        {r.assign_to_agent_id && <p className="text-ink-mute">{agentName[r.assign_to_agent_id] ?? "Agent"}</p>}
                      </div>
                    </li>
                  ))}
              </ol>
            ) : (
              <div className="p-5">
                <EmptyState title="No routing rules" />
              </div>
            )
          }
        </QueryState>
      </Panel>

      <div className="space-y-5 lg:col-span-2">
        <Panel title="Route a lead" subtitle="Qualifies the lead, then applies the rules" icon={<Route className="h-4 w-4" />}>
          <div className="space-y-3">
            <Select value={leadId} onChange={(e) => setLeadId(e.target.value)}>
              <option value="">Select a CRM lead…</option>
              {(leads.data?.leads ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} · {l.city_name ?? "any city"} · {titleCase(l.source)}
                </option>
              ))}
            </Select>
            <Button className="w-full justify-center" icon={<Route className="h-4 w-4" />} disabled={!leadId} loading={route.isPending} onClick={() => route.mutate(leadId)}>
              Route lead
            </Button>
            {res && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-gold-200 bg-gold-50/60 p-4 dark:border-gold-500/20 dark:bg-gold-500/10">
                <div className="flex items-center justify-between">
                  <p className="font-semibold">{res.lead.name}</p>
                  <Badge tone={bandTone(res.lead.band)} className="capitalize">
                    {res.lead.band}
                  </Badge>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <MiniStat label="Matched rule" value={<span className="text-sm">{res.routing.matched_rule}</span>} />
                  <MiniStat label="Queue" value={<span className="text-sm">{res.routing.queue}</span>} tone="blue" />
                  <MiniStat label="SLA" value={`${res.routing.sla_hours}h`} tone="gold" />
                  <MiniStat label="Agent" value={<span className="text-sm">{res.routing.assigned_agent_id ? agentName[res.routing.assigned_agent_id] ?? "Assigned" : "Queue"}</span>} />
                </div>
              </motion.div>
            )}
          </div>
        </Panel>
      </div>

      <AddRuleModal open={adding} onClose={() => setAdding(false)} agents={agents.data?.agents ?? []} />
    </div>
  );
}

function AddRuleModal({ open, onClose, agents }: { open: boolean; onClose: () => void; agents: Agent[] }) {
  const [f, set, reset] = useFormState({ name: "", city: "", language: "", use_type: "", source: "", price_min: "", price_max: "", queue: "general", priority: "50", sla_hours: "4", assign_to_agent_id: "" });
  const match: Record<string, unknown> = {};
  if (f.city) match.city = f.city;
  if (f.language) match.language = f.language;
  if (f.use_type) match.use_type = f.use_type;
  if (f.source) match.source = f.source;
  if (numOr(f.price_min)) match.price_min = numOr(f.price_min);
  if (numOr(f.price_max)) match.price_max = numOr(f.price_max);
  const add = useMutate(
    () =>
      post("/marketing/routes", {
        name: f.name.trim(),
        match,
        queue: f.queue || "general",
        priority: numOr(f.priority, 100),
        sla_hours: numOr(f.sla_hours, 4),
        assign_to_agent_id: f.assign_to_agent_id || undefined,
      }).then(ensure),
    {
      invalidate: ["/marketing"],
      success: "Routing rule added",
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
      title="Add routing rule"
      subtitle="Leave a condition empty to match anything"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={add.isPending} disabled={!f.name.trim()} onClick={() => add.mutate()}>
            Add rule
          </Button>
        </>
      }
    >
      <FormGrid cols={3}>
        <Field label="Rule name *" className="sm:col-span-3">
          <Input value={f.name} onChange={(e) => set("name")(e.target.value)} placeholder="e.g. Islamabad investors" />
        </Field>
        <Field label="City">
          <Select value={f.city} onChange={(e) => set("city")(e.target.value)} options={["", "Lahore", "Karachi", "Islamabad", "Rawalpindi"].map((c) => ({ value: c, label: c || "Any" }))} />
        </Field>
        <Field label="Language">
          <Select
            value={f.language}
            onChange={(e) => set("language")(e.target.value)}
            options={[
              { value: "", label: "Any" },
              { value: "en", label: "English" },
              { value: "ur", label: "Urdu" },
            ]}
          />
        </Field>
        <Field label="Use type">
          <Select value={f.use_type} onChange={(e) => set("use_type")(e.target.value)} options={["", "residential", "commercial", "mix"].map((c) => ({ value: c, label: c ? titleCase(c) : "Any" }))} />
        </Field>
        <Field label="Source">
          <Select value={f.source} onChange={(e) => set("source")(e.target.value)} options={["", "website", "referral", "walk_in", "call", "whatsapp", "portal"].map((c) => ({ value: c, label: c ? titleCase(c) : "Any" }))} />
        </Field>
        <Field label="Budget ≥ (PKR)">
          <Input type="number" min={0} value={f.price_min} onChange={(e) => set("price_min")(e.target.value)} />
        </Field>
        <Field label="Budget ≤ (PKR)">
          <Input type="number" min={0} value={f.price_max} onChange={(e) => set("price_max")(e.target.value)} />
        </Field>
        <Field label="Queue">
          <Input value={f.queue} onChange={(e) => set("queue")(e.target.value)} />
        </Field>
        <Field label="Priority" hint="Lower runs first">
          <Input type="number" min={1} value={f.priority} onChange={(e) => set("priority")(e.target.value)} />
        </Field>
        <Field label="SLA (hours)">
          <Input type="number" min={1} value={f.sla_hours} onChange={(e) => set("sla_hours")(e.target.value)} />
        </Field>
        <Field label="Assign to agent" className="sm:col-span-3">
          <Select value={f.assign_to_agent_id} onChange={(e) => set("assign_to_agent_id")(e.target.value)}>
            <option value="">Queue only</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
      </FormGrid>
    </Modal>
  );
}
