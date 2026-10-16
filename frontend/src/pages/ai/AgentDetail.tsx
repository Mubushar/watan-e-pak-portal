import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown,
  ArrowRight,
  ArrowRightLeft,
  Bot,
  ClipboardList,
  Cpu,
  Gauge,
  GitBranch,
  History,
  ListChecks,
  Lock,
  MessageSquare,
  Network,
  Play,
  Rocket,
  ShieldCheck,
  Target,
  Wrench,
} from "lucide-react";
import type { AgentDef, AgentRun } from "@/types";
import { useApi, useMutate } from "@/hooks/useApi";
import { post } from "@/lib/api";
import { titleCase, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { Badge, Breadcrumbs, Button, ButtonLink, Card, CardBody, CardHeader, EmptyState, ErrorState, Field, KeyValue, Select, Skeleton, StatusBadge, Textarea, Toggle } from "@/components/ui";
import { ApprovalGate, AutonomyBadge, CategoryIcon, fmtValue, HeroBackdrop, PriorityBadge, runProgress } from "@/components/agents/AgentBits";
import { RunView, SubjectPicker, SUBJECT_TYPES } from "@/components/agents/RunPanel";

const EXAMPLES: Record<string, string> = {
  conversational_buyer_agent: "10 marla house in DHA Lahore under 5 crore, near good schools",
  anomaly_agent: "Find underpriced listings in Lahore and Islamabad",
  seller_pricing_agent: "Price my 10 marla house in DHA Lahore and draft the marketing kit",
  cma_agent: "Comparable-sales analysis for a 10 marla house in DHA Lahore",
  staging_agent: "Suggest virtual staging for a 3-bed apartment listing",
  investment_screener: "Find high-yield rental investments in Lahore under 6 crore",
  screening_agent: "Screen residential listings for cap rate above 5%",
  underwriting_agent: "Underwrite a 4.5 crore house with 60% financing",
  autonomous_leasing_agent: "Answer a tenant enquiry for a 2-bed apartment in Islamabad",
  renewal_agent: "Recommend renewals for leases expiring in the next 60 days",
  maintenance_triage_agent: "Leaking water tank on the roof, tenant reports damp walls",
  broker_workspace: "Daily morning brief",
  crm_agent: "Prioritise today's leads and draft follow-ups",
  transaction_agent: "Check overdue milestones on open transactions",
  accounting_agent: "Commission projection for this quarter",
  marketing_agent: "Create a campaign for a new 1 kanal listing in Bahria Town",
  marketing_conductor: "Plan a launch campaign for a new housing scheme in Islamabad",
  lead_engine_agent: "Generate and score leads for luxury homes in DHA",
  routing_agent: "Route new website leads to the best-fit agents",
  reengagement_agent: "Re-engage cold leads from the last 90 days",
  compliance_agent: "KYC / AML check for a new property sale",
  construction_advisor_agent: "Estimate cost and timeline to build on a 10 marla plot",
  property_intelligence_mcp: "GIS score and market snapshot for DHA Lahore",
  mcp_for_brokers: "Show my commission projection and today's tasks",
};

function Chain({ chain }: { chain: { seq: number; agent: string; name: string; handoff_to: string | null; tools: string[] }[] }) {
  return (
    <div className="flex flex-col items-stretch gap-2 md:flex-row md:items-center md:overflow-x-auto md:pb-2">
      {chain.map((c, i) => (
        <div key={c.seq} className="flex flex-col items-center gap-2 md:flex-row">
          <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.15 }} className="w-full md:w-56">
            <Link to={`/ai/agents/${c.agent}`} className="card card-hover block p-4">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-gradient text-xs font-bold text-white">{c.seq}</span>
                <p className="truncate font-display text-sm font-semibold">{c.name}</p>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.tools.map((t) => (
                  <span key={t} className="chip bg-slate-100 font-mono text-[9px] text-slate-600 dark:bg-white/10 dark:text-slate-300">
                    {t}
                  </span>
                ))}
              </div>
            </Link>
          </motion.div>
          {c.handoff_to && (
            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.15 + 0.1 }} className="flex shrink-0 items-center gap-1 text-[10px] font-semibold uppercase text-gold-600">
              <ArrowDown className="h-4 w-4 md:hidden" />
              <ArrowRight className="hidden h-4 w-4 md:block rtl:rotate-180" />
              hand-off
            </motion.span>
          )}
        </div>
      ))}
    </div>
  );
}

function Orchestrate({ agent, objective }: { agent: AgentDef; objective: string }) {
  const catalog = useApi<{ agents: AgentDef[] }>("/agents/catalog");
  const [picked, setPicked] = useState<string[]>(() => [agent.key, ...(agent.handoffs ?? [])].slice(0, 6));
  const [goal, setGoal] = useState(objective);
  useEffect(() => setGoal(objective), [objective]);
  const m = useMutate((b: { objective: string; agents_csv: string }) => post<{ agents: { seq: number; agent: string; name: string; handoff_to: string | null; tools: string[] }[]; count: number; error?: string }>("/agents/orchestrate", b));
  const toggle = (k: string) => setPicked((p) => (p.includes(k) ? p.filter((x) => x !== k) : p.length >= 6 ? p : [...p, k]));
  return (
    <Card>
      <CardHeader title="Orchestrate a hand-off chain" subtitle="Pick up to 6 agents — they pass the objective along in order" icon={<Network className="h-4 w-4" />} />
      <CardBody className="space-y-4">
        <Field label="Shared objective">
          <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} className="min-h-[64px]" />
        </Field>
        <div>
          <span className="label">Agents in order ({picked.length}/6)</span>
          <div className="flex flex-wrap gap-1.5">
            {(catalog.data?.agents ?? []).map((a) => {
              const idx = picked.indexOf(a.key);
              return (
                <button
                  key={a.key}
                  type="button"
                  onClick={() => toggle(a.key)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition",
                    idx >= 0 ? "bg-brand-700 text-white shadow-soft" : "bg-black/5 text-ink-soft hover:bg-brand-50 dark:bg-white/5 dark:text-slate-300",
                  )}
                >
                  {idx >= 0 && <span className="flex h-4 w-4 items-center justify-center rounded-full bg-gold-400 text-[9px] text-brand-950">{idx + 1}</span>}
                  {a.name}
                </button>
              );
            })}
            {catalog.isLoading && <Skeleton className="h-7 w-full" />}
          </div>
        </div>
        <Button variant="soft" icon={<GitBranch className="h-4 w-4" />} loading={m.isPending} disabled={!picked.length || !goal.trim()} onClick={() => m.mutate({ objective: goal, agents_csv: picked.join(",") })}>
          Build chain
        </Button>
        {m.data?.error && <ErrorState error={m.data.error} />}
        {m.data?.agents?.length ? <Chain chain={m.data.agents} /> : m.data && !m.data.error ? <p className="text-sm text-ink-mute">The orchestrator found no valid agents in that selection.</p> : null}
      </CardBody>
    </Card>
  );
}

function Definition({ a }: { a: AgentDef }) {
  const kpis = Object.entries(a.kpis ?? {});
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader title="Workflow" subtitle={a.workflow ? `${a.workflow.length} steps` : `${a.workflow_steps ?? "?"} steps · generated per request`} icon={<ListChecks className="h-4 w-4" />} />
        <CardBody>
          {a.workflow?.length ? (
            <ol className="relative space-y-3">
              <span className="absolute bottom-3 start-[15px] top-3 w-0.5 bg-gradient-to-b from-brand-400 to-gold-300 opacity-50" />
              {a.workflow.map((w, i) => (
                <motion.li key={w.name} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }} className="relative flex items-start gap-3">
                  <span
                    className={cn(
                      "z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ring-4 ring-white dark:ring-[#0d1f16]",
                      w.requires_approval ? "bg-gold-gradient text-brand-950" : "bg-brand-700 text-white",
                    )}
                  >
                    {w.requires_approval ? <Lock className="h-3.5 w-3.5" /> : i + 1}
                  </span>
                  <div className="min-w-0 pt-1">
                    <p className="text-sm font-semibold">{titleCase(w.name)}</p>
                    {w.tool ? <code className="text-[11px] text-ink-mute">{w.tool}</code> : <p className="text-[11px] text-ink-mute">{w.requires_approval ? "Human approval gate" : "Agent step"}</p>}
                  </div>
                </motion.li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-ink-mute">This agent assembles its workflow from the objective. Use <b>Plan only</b> to preview the steps.</p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Tools" subtitle={`${a.tools.length} portal tools via MCP`} icon={<Wrench className="h-4 w-4" />} action={<ButtonLink to="/ai/mcp" variant="ghost" size="sm">Console</ButtonLink>} />
        <CardBody className="flex flex-wrap gap-1.5">
          {a.tools.map((t) => (
            <span key={t} className="chip bg-brand-50 font-mono text-[11px] text-brand-800 ring-1 ring-brand-600/10 dark:bg-white/5 dark:text-brand-200">
              <Cpu className="h-3 w-3" /> {t}
            </span>
          ))}
        </CardBody>
      </Card>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
        <Card>
          <CardHeader title="Inputs" icon={<ClipboardList className="h-4 w-4" />} />
          <CardBody>
            <ul className="space-y-1.5 text-sm">
              {(a.inputs ?? []).map((x) => (
                <li key={x} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                  {x}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Outputs" icon={<Target className="h-4 w-4" />} />
          <CardBody>
            <ul className="space-y-1.5 text-sm">
              {(a.outputs ?? []).map((x) => (
                <li key={x} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gold-500" />
                  {x}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      </div>

      {kpis.length > 0 && (
        <Card>
          <CardHeader title="KPIs" icon={<Gauge className="h-4 w-4" />} />
          <CardBody>
            <KeyValue items={kpis.map(([k, v]) => ({ label: titleCase(k), value: fmtValue(k, v) }))} />
          </CardBody>
        </Card>
      )}

      {(a.handoffs?.length ?? 0) > 0 && (
        <Card>
          <CardHeader title="Hands off to" icon={<ArrowRightLeft className="h-4 w-4" />} />
          <CardBody className="flex flex-wrap gap-2">
            {a.handoffs!.map((h) => (
              <Link key={h} to={`/ai/agents/${h}`} className="chip bg-gold-50 px-3 py-1.5 text-gold-800 ring-1 ring-gold-600/20 transition hover:bg-gold-100 dark:bg-gold-500/10 dark:text-gold-200">
                <Bot className="h-3.5 w-3.5" /> {titleCase(h)} <ArrowRight className="h-3 w-3 rtl:rotate-180" />
              </Link>
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

export default function AgentDetail() {
  const { key = "" } = useParams();
  const [params] = useSearchParams();
  const user = useAuth((s) => s.user);
  const q = useApi<AgentDef & { error?: string }>(key ? `/agents/${key}` : null);
  const a = q.data && !q.data.error ? q.data : undefined;

  const [objective, setObjective] = useState("");
  const [subjectType, setSubjectType] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [autoApprove, setAutoApprove] = useState(false);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [mode, setMode] = useState<"run" | "plan">("run");

  useEffect(() => {
    setObjective(params.get("objective") ?? EXAMPLES[key] ?? "");
    setRun(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  useEffect(() => {
    if (!objective && a) setObjective(`Run ${a.name.toLowerCase()} for today`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a]);

  const body = { agent_key: key, objective, subject_type: subjectType || undefined, subject_id: (subjectType && subjectId) || undefined };
  const runM = useMutate((approve: boolean) => post<AgentRun>("/agents/run", { ...body, approve }), {
    invalidate: ["/agents/runs", "/agents/overview"],
    onSuccess: (r) => {
      setMode("run");
      setRun(r);
    },
    success: (r) => (r.status === "awaiting_approval" ? "Run paused at the human gate" : `Run ${r.status}`),
  });
  const planM = useMutate(() => post<AgentRun>("/agents/plan", body), {
    onSuccess: (r) => {
      setMode("plan");
      setRun(r);
    },
  });
  const approveM = useMutate((id: string) => post<AgentRun>(`/agents/runs/${id}/approve`, undefined, { approver: user?.name || user?.email || "web-user", execute: true }), {
    invalidate: ["/agents/runs", "/agents/overview"],
    success: "Approved — run continued",
    onSuccess: (r) => setRun(r),
  });
  const runs = useApi<{ count: number; runs: AgentRun[] }>("/agents/runs", { agent_key: key });
  const recent = useMemo(() => [...(runs.data?.runs ?? [])].sort((x, y) => (y.created_at > x.created_at ? 1 : -1)).slice(0, 8), [runs.data]);

  if (q.isLoading)
    return (
      <div className="container space-y-4 py-10">
        <Skeleton className="h-48" />
        <Skeleton className="h-96" />
      </div>
    );
  if (q.error || !a)
    return (
      <div className="container py-16">
        {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <EmptyState title="Agent not found" hint={q.data?.error} action={<ButtonLink to="/ai">Back to AI Hub</ButtonLink>} />}
      </div>
    );

  return (
    <div className="pb-16">
      <section className="relative isolate overflow-hidden text-white">
        <HeroBackdrop />
        <div className="container py-10 sm:py-14">
          <Breadcrumbs light crumbs={[{ label: "AI Hub", to: "/ai" }, { label: "Agents", to: "/ai#catalog" }, { label: a.name }]} />
          <div className="mt-5 flex flex-col gap-5 sm:flex-row sm:items-start">
            <motion.span initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex h-16 w-16 shrink-0 items-center justify-center rounded-3xl bg-gold-gradient text-brand-950 shadow-glow">
              <CategoryIcon category={a.category} className="h-8 w-8" />
            </motion.span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <PriorityBadge priority={a.priority} />
                <AutonomyBadge autonomy={a.autonomy} />
                <Badge tone="gray" className="!bg-white/10 !text-white/80 !ring-white/10">
                  {titleCase(a.category)}
                </Badge>
                <span className="rounded-full bg-white/10 px-2 py-0.5 [&_*]:!text-gold-200">
                  <ApprovalGate required={a.requires_approval} />
                </span>
              </div>
              <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-3 font-display text-3xl font-bold sm:text-4xl">
                {a.name}
              </motion.h1>
              <p className="mt-2 max-w-3xl text-white/75">{a.description || a.summary}</p>
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-white/70">
                <span className="chip bg-white/10">Product: {titleCase(a.product)}</span>
                {(a.channels ?? []).map((c) => (
                  <span key={c} className="chip bg-white/10">
                    <MessageSquare className="h-3 w-3" /> {titleCase(c)}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="container mt-8 grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="order-2 lg:order-1">
          <Definition a={a} />
        </div>

        <div className="order-1 min-w-0 space-y-6 lg:order-2">
          <Card className="overflow-hidden">
            <div className="relative isolate overflow-hidden border-b border-black/5 bg-brand-50/60 px-5 py-4 dark:border-white/10 dark:bg-white/5">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-soft">
                  <Rocket className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="font-display text-lg font-semibold">Run this agent</h2>
                  <p className="text-xs text-ink-mute">Executes against the live portal and records an auditable run.</p>
                </div>
              </div>
            </div>
            <CardBody className="space-y-4">
              <Field label="Objective">
                <Textarea value={objective} onChange={(e) => setObjective(e.target.value)} className="min-h-[88px]" placeholder="What should the agent achieve?" />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Subject (optional)">
                  <Select
                    value={subjectType}
                    onChange={(e) => {
                      setSubjectType(e.target.value);
                      setSubjectId("");
                    }}
                    options={SUBJECT_TYPES}
                  />
                </Field>
                <SubjectPicker type={subjectType} value={subjectId} onChange={setSubjectId} />
              </div>
              <div className="flex flex-col gap-3 rounded-2xl bg-gold-50/70 p-3 sm:flex-row sm:items-center dark:bg-gold-500/10">
                <Toggle checked={autoApprove} onChange={setAutoApprove} label={<span className="text-sm font-semibold">Auto-approve the human gate</span>} />
                <span className="text-xs text-ink-mute sm:ms-auto">{autoApprove ? "Runs straight through to delivery." : "Pauses for your sign-off at locked steps."}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="gold" size="lg" icon={<Play className="h-4 w-4" />} loading={runM.isPending} disabled={!objective.trim()} onClick={() => runM.mutate(autoApprove)}>
                  Run agent
                </Button>
                <Button variant="outline" size="lg" icon={<ListChecks className="h-4 w-4" />} loading={planM.isPending} disabled={!objective.trim()} onClick={() => planM.mutate()}>
                  Plan only
                </Button>
              </div>
            </CardBody>
          </Card>

          <AnimatePresence mode="wait">
            {(runM.isPending || planM.isPending) && !run ? (
              <motion.div key="busy" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-20" />
                ))}
              </motion.div>
            ) : run ? (
              <motion.div key={run.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                <Card>
                  <CardHeader
                    title={mode === "plan" ? "Execution plan" : "Run timeline"}
                    subtitle={mode === "plan" ? "Nothing has been executed yet" : `${run.agent_name ?? a.name}`}
                    icon={mode === "plan" ? <ListChecks className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                    action={
                      mode === "plan" ? (
                        <Button size="sm" variant="gold" icon={<Play className="h-3.5 w-3.5" />} loading={runM.isPending} onClick={() => runM.mutate(autoApprove)}>
                          Execute
                        </Button>
                      ) : undefined
                    }
                  />
                  <CardBody>
                    <RunView run={run} onApprove={mode === "run" ? () => approveM.mutate(run.id) : undefined} approving={approveM.isPending} />
                  </CardBody>
                </Card>
              </motion.div>
            ) : null}
          </AnimatePresence>

          <Orchestrate key={a.key} agent={a} objective={objective} />

          <Card>
            <CardHeader title="Recent runs" subtitle="Audit trail for this agent" icon={<History className="h-4 w-4" />} />
            {runs.isLoading ? (
              <CardBody>
                <Skeleton className="h-32" />
              </CardBody>
            ) : recent.length ? (
              <ul className="divide-y divide-black/5 dark:divide-white/10">
                {recent.map((r) => {
                  const p = runProgress(r);
                  return (
                    <li key={r.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setMode("run");
                          setRun(r);
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                        className={cn("flex w-full items-center gap-3 px-5 py-3 text-start transition hover:bg-brand-50/60 dark:hover:bg-white/5", run?.id === r.id && "bg-brand-50/60 dark:bg-white/5")}
                      >
                        <StatusBadge status={r.status} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{r.objective || "—"}</span>
                          <span className="block text-xs text-ink-mute">
                            {timeAgo(r.created_at.replace(" ", "T"))} · {p.done}/{p.total} steps
                          </span>
                        </span>
                        <ArrowRight className="h-4 w-4 shrink-0 text-ink-mute rtl:rotate-180" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <CardBody>
                <EmptyState title="No runs yet" hint="Run the agent above to start its audit trail." />
              </CardBody>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
