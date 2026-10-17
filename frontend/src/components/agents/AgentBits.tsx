/**
 * Shared Agentic-OS building blocks: badges, icons, the animated hero backdrop,
 * the run-step timeline and the smart renderer for (truncated) step outputs.
 */
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Bot,
  Briefcase,
  CheckCircle2,
  ChevronDown,
  Circle,
  Handshake,
  Home as HomeIcon,
  KeyRound,
  Lightbulb,
  LineChart,
  Lock,
  Megaphone,
  MinusCircle,
  Server,
  ShieldCheck,
  TrendingUp,
  Wrench,
  XCircle,
  Zap,
} from "lucide-react";
import type { AgentRun, AgentStep } from "@/types";
import { num, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, JsonView, KeyValue, type Tone } from "@/components/ui";
import { PropertyRow } from "@/components/property/PropertyCard";
import { looseJson } from "./looseJson";

// ------------------------------------------------------------------ meta
export const AUTONOMY: Record<string, { label: string; tone: Tone; icon: ReactNode; blurb: string }> = {
  suggest: { label: "Suggest", tone: "blue", icon: <Lightbulb className="h-3 w-3" />, blurb: "Drafts recommendations; a human acts." },
  assist: { label: "Assist", tone: "gold", icon: <Handshake className="h-3 w-3" />, blurb: "Executes tools, pauses at a human gate." },
  autonomous: { label: "Autonomous", tone: "green", icon: <Zap className="h-3 w-3" />, blurb: "Runs end-to-end within guardrails." },
};

export function AutonomyBadge({ autonomy, className }: { autonomy?: string | null; className?: string }) {
  const m = AUTONOMY[autonomy ?? ""] ?? { label: titleCase(autonomy ?? "—"), tone: "gray" as Tone, icon: null };
  return (
    <Badge tone={m.tone} icon={m.icon} className={className}>
      {m.label}
    </Badge>
  );
}

export function PriorityBadge({ priority }: { priority?: string | null }) {
  const tone: Tone = priority === "P0" ? "red" : priority === "P1" ? "gold" : priority === "P2" ? "blue" : "gray";
  return <Badge tone={tone}>{priority ?? "—"}</Badge>;
}

export function ApprovalGate({ required, compact }: { required: boolean; compact?: boolean }) {
  return required ? (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-gold-700 dark:text-gold-300" title="Pauses for human approval">
      <Lock className="h-3 w-3" /> {compact ? "Gate" : "Human gate"}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand-700 dark:text-brand-300" title="Runs without a human gate">
      <ShieldCheck className="h-3 w-3" /> {compact ? "Auto" : "No gate"}
    </span>
  );
}

const CATEGORY_ICON: Record<string, typeof Bot> = {
  platform: Server,
  broker: Briefcase,
  marketing: Megaphone,
  buyer_side: HomeIcon,
  seller_side: TrendingUp,
  landlord: KeyRound,
  investor: LineChart,
};

export function CategoryIcon({ category, className }: { category?: string | null; className?: string }) {
  const I = CATEGORY_ICON[category ?? ""] ?? Bot;
  return <I className={cn("h-5 w-5", className)} />;
}

// ------------------------------------------------------------------ hero backdrop
/** Dark brand gradient with drifting orbs and a faint grid — the "Agentic OS" look. */
export function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden bg-brand-gradient">
      <div
        className="absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage: "linear-gradient(rgba(255,255,255,.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.5) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage: "radial-gradient(ellipse at 50% 30%, black 20%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 30%, black 20%, transparent 75%)",
        }}
      />
      <motion.div
        className="absolute -start-24 -top-24 h-80 w-80 rounded-full bg-gold-400/30 blur-3xl"
        animate={{ x: [0, 60, 0], y: [0, 40, 0] }}
        transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -end-20 top-10 h-96 w-96 rounded-full bg-brand-400/30 blur-3xl"
        animate={{ x: [0, -50, 0], y: [0, 60, 0] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-[-8rem] start-1/3 h-80 w-80 rounded-full bg-emerald-300/20 blur-3xl"
        animate={{ scale: [1, 1.2, 1] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/20 to-transparent" />
    </div>
  );
}

// ------------------------------------------------------------------ step status
export function stepHasError(step: Pick<AgentStep, "output">): string | null {
  const r = looseJson(step.output);
  if (r.ok && r.value && typeof r.value === "object" && !Array.isArray(r.value)) {
    const e = (r.value as Record<string, unknown>).error;
    if (typeof e === "string") return e;
  }
  return null;
}

export function StepIcon({ status, warn }: { status: string; warn?: boolean }) {
  const base = "flex h-9 w-9 shrink-0 items-center justify-center rounded-full ring-4 ring-white dark:ring-[#0d1f16]";
  if (status === "done" && warn)
    return (
      <span className={cn(base, "bg-orange-100 text-orange-600 dark:bg-orange-500/20 dark:text-orange-300")}>
        <AlertTriangle className="h-4 w-4" />
      </span>
    );
  if (status === "done")
    return (
      <span className={cn(base, "bg-brand-600 text-white")}>
        <CheckCircle2 className="h-4 w-4" />
      </span>
    );
  if (status === "failed")
    return (
      <span className={cn(base, "bg-red-500 text-white")}>
        <XCircle className="h-4 w-4" />
      </span>
    );
  if (status === "skipped")
    return (
      <span className={cn(base, "bg-slate-200 text-slate-500 dark:bg-white/10 dark:text-slate-400")}>
        <MinusCircle className="h-4 w-4" />
      </span>
    );
  if (status === "awaiting_approval")
    return (
      <span className={cn(base, "relative bg-gold-gradient text-brand-950")}>
        <span className="absolute inset-0 animate-ping rounded-full bg-gold-400/50" />
        <Lock className="relative h-4 w-4" />
      </span>
    );
  return (
    <span className={cn(base, "border-2 border-dashed border-black/15 bg-white text-ink-mute dark:border-white/20 dark:bg-transparent")}>
      <Circle className="h-3 w-3" />
    </span>
  );
}

const STATUS_LABEL: Record<string, string> = {
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
  awaiting_approval: "Awaiting approval",
  pending: "Pending",
};

// ------------------------------------------------------------------ smart output
const MONEY_KEY = /(price|amount|value|cost|income|rent|budget|mean|profit|proceeds|cash|payment|equity|commission|tax|loan)/i;

export function fmtValue(key: string, v: unknown): ReactNode {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (/_pct$|percent/i.test(key)) return `${num(v, 2)}%`;
    if (/(rate|ratio|share|cap_rate|yield)$/i.test(key) && Math.abs(v) <= 1) return `${num(v * 100, 2)}%`;
    if (MONEY_KEY.test(key) && Math.abs(v) >= 1000) return pkrShort(v);
    return num(v, 2);
  }
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.length ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ") : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function scalarItems(obj: Record<string, unknown>, skip: string[] = [], max = 8) {
  return Object.entries(obj)
    .filter(([k, v]) => !skip.includes(k) && (v === null || ["string", "number", "boolean"].includes(typeof v) || (Array.isArray(v) && v.every((x) => typeof x !== "object") && v.length <= 6)))
    .filter(([, v]) => !(typeof v === "string" && v.length > 140))
    .slice(0, max)
    .map(([k, v]) => ({ label: titleCase(k), value: fmtValue(k, v) }));
}

type Row = Record<string, unknown>;
const asRows = (v: unknown): Row[] => (Array.isArray(v) ? v.filter((x): x is Row => !!x && typeof x === "object") : []);
const n = (v: unknown) => (typeof v === "number" ? v : undefined);
const s = (v: unknown) => (typeof v === "string" ? v : undefined);

function Shortlist({ rows }: { rows: Row[] }) {
  return (
    <div className="space-y-1 rounded-xl bg-brand-50/40 p-1.5 dark:bg-white/5">
      {rows.map((c, i) => {
        const id = s(c.candidate_id) ?? s(c.id) ?? String(i);
        return (
          <PropertyRow
            key={id + i}
            p={{ id, title: s(c.title) ?? "Listing", price: n(c.price) ?? 0, category: s(c.category) ?? "property", city_name: s(c.city) }}
            extra={
              n(c.composite) !== undefined ? (
                <span className="chip shrink-0 bg-gold-gradient text-brand-950">{num(n(c.composite), 1)}</span>
              ) : n(c.score) !== undefined ? (
                <span className="chip shrink-0 bg-brand-700 text-white">{num(n(c.score), 1)}</span>
              ) : undefined
            }
          />
        );
      })}
    </div>
  );
}

function Bargains({ rows }: { rows: Row[] }) {
  return (
    <div className="space-y-1 rounded-xl bg-brand-50/40 p-1.5 dark:bg-white/5">
      {rows.map((b, i) => (
        <PropertyRow
          key={(s(b.id) ?? "") + i}
          p={{ id: s(b.id) ?? String(i), title: s(b.title) ?? "Listing", price: n(b.price) ?? 0, category: s(b.category) ?? "property", city_name: s(b.group) }}
          extra={
            <span className="flex shrink-0 flex-col items-end gap-1">
              {n(b.deviation_pct) !== undefined && <Badge tone={n(b.deviation_pct)! < 0 ? "green" : "red"}>{num(n(b.deviation_pct), 1)}%</Badge>}
              {n(b.z_score) !== undefined && <span className="text-[10px] font-semibold text-ink-mute">z {num(n(b.z_score), 2)}</span>}
            </span>
          }
        />
      ))}
    </div>
  );
}

function TopPicks({ rows }: { rows: Row[] }) {
  const cols = ["rank", "title", "city", "cap_rate", "dscr", "irr", "score", "grade"].filter((c) => rows.some((r) => r[c] !== undefined));
  return (
    <div className="scroll-x overflow-x-auto rounded-xl ring-1 ring-black/5 dark:ring-white/10">
      <table className="w-full min-w-[480px] text-xs">
        <thead className="bg-brand-50/70 text-ink-mute dark:bg-white/5">
          <tr>
            {cols.map((c) => (
              <th key={c} className="px-3 py-2 text-start font-semibold uppercase tracking-wide">
                {titleCase(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-black/5 dark:border-white/10">
              {cols.map((c) => (
                <td key={c} className="px-3 py-2 tabular-nums">
                  {c === "title" && s(r.id) ? (
                    <Link to={`/properties/${s(r.id)}`} className="font-semibold text-brand-700 hover:underline dark:text-brand-300">
                      {s(r.title)}
                    </Link>
                  ) : c === "grade" ? (
                    <Badge tone={r.grade === "A" ? "green" : r.grade === "B" ? "blue" : r.grade === "C" ? "gold" : "red"}>{String(r.grade ?? "—")}</Badge>
                  ) : (
                    fmtValue(c, r[c])
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Render a step's output (a possibly-truncated JSON string) as the most useful view. */
export function StepOutput({ output }: { output: unknown }) {
  const [raw, setRaw] = useState(false);
  const r = looseJson(output);
  if (!r.ok) {
    if (output === null || output === undefined || output === "") return null;
    return <p className="rounded-xl bg-brand-50/60 px-3 py-2 text-sm text-ink-soft dark:bg-white/5 dark:text-slate-300">{String(output)}</p>;
  }
  const v = r.value;
  if (Array.isArray(v)) return <JsonView data={v} />;
  const obj = v as Record<string, unknown>;
  const special: ReactNode[] = [];
  const skip: string[] = [];
  if (typeof obj.error === "string") {
    special.push(
      <div key="err" className="flex items-start gap-2 rounded-xl bg-orange-50 px-3 py-2 text-sm text-orange-800 dark:bg-orange-500/10 dark:text-orange-200">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {obj.error}
      </div>,
    );
    skip.push("error");
  }
  if (asRows(obj.shortlist).length) {
    special.push(<Shortlist key="sl" rows={asRows(obj.shortlist)} />);
    skip.push("shortlist");
  }
  if (asRows(obj.bargains).length) {
    special.push(<Bargains key="bg" rows={asRows(obj.bargains)} />);
    skip.push("bargains");
  }
  if (asRows(obj.top_picks).length) {
    special.push(<TopPicks key="tp" rows={asRows(obj.top_picks)} />);
    skip.push("top_picks");
  }
  const kv = scalarItems(obj, skip);
  const hasNested = Object.entries(obj).some(([k, x]) => !skip.includes(k) && x !== null && typeof x === "object");
  return (
    <div className="space-y-3">
      {special}
      {kv.length > 0 && <KeyValue items={kv} cols={kv.length >= 6 ? 3 : 2} />}
      {(hasNested || (!special.length && !kv.length)) && (
        <div>
          <button type="button" onClick={() => setRaw((x) => !x)} className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300">
            <ChevronDown className={cn("h-3.5 w-3.5 transition", raw && "rotate-180")} /> {raw ? "Hide" : "Show"} full output
          </button>
          {raw && (
            <div className="mt-2 max-h-80 overflow-auto rounded-xl bg-slate-50 p-3 dark:bg-black/30">
              <JsonView data={obj} defaultOpen={2} />
            </div>
          )}
        </div>
      )}
      {r.truncated && <p className="text-[11px] italic text-ink-mute">Output summarised by the agent engine (first 480 characters) — partial view.</p>}
    </div>
  );
}

// ------------------------------------------------------------------ run timeline
export function RunTimeline({ run, onApprove, approving }: { run: Pick<AgentRun, "steps" | "status">; onApprove?: () => void; approving?: boolean }) {
  return (
    <ol className="relative space-y-4">
      <span className="absolute bottom-4 start-[17px] top-4 w-0.5 bg-gradient-to-b from-brand-500 via-gold-400 to-transparent opacity-40" />
      <AnimatePresence initial>
        {run.steps.map((st, i) => {
          const err = st.status === "done" ? stepHasError(st) : null;
          return (
            <motion.li
              key={st.seq}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.12, type: "spring", bounce: 0.25 }}
              className="relative flex gap-3"
            >
              <StepIcon status={st.status} warn={!!err} />
              <div
                className={cn(
                  "min-w-0 flex-1 rounded-2xl border p-3.5 transition",
                  st.status === "awaiting_approval" ? "border-gold-300 bg-gold-50/60 shadow-glow dark:border-gold-500/40 dark:bg-gold-500/10" : "border-black/5 bg-white dark:border-white/10 dark:bg-white/[0.03]",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-bold text-ink-mute">#{st.seq}</span>
                  <p className="font-display font-semibold text-ink dark:text-white">{titleCase(st.name)}</p>
                  {st.tool && (
                    <span className="chip bg-slate-100 font-mono text-[10px] text-slate-700 dark:bg-white/10 dark:text-slate-300">
                      <Wrench className="h-3 w-3" /> {st.tool}
                    </span>
                  )}
                  {st.requires_approval && <ApprovalGate required compact />}
                  <span className="ms-auto">
                    <Badge tone={err ? "orange" : st.status === "done" ? "green" : st.status === "failed" ? "red" : st.status === "awaiting_approval" ? "gold" : "gray"}>
                      {err ? "Done · warning" : STATUS_LABEL[st.status] ?? titleCase(st.status)}
                    </Badge>
                  </span>
                </div>
                {st.approved_by && <p className="mt-1 text-xs text-brand-700 dark:text-brand-300">Approved by {st.approved_by}</p>}
                {st.output && (
                  <div className="mt-3">
                    <StepOutput output={st.output} />
                  </div>
                )}
                {st.status === "awaiting_approval" && onApprove && (
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <button type="button" onClick={onApprove} disabled={approving} className="btn btn-gold btn-sm">
                      <Lock className="h-3.5 w-3.5" /> {approving ? "Approving…" : "Approve & continue"}
                    </button>
                    <span className="text-xs text-ink-mute">A human must sign off before the agent delivers.</span>
                  </div>
                )}
              </div>
            </motion.li>
          );
        })}
      </AnimatePresence>
    </ol>
  );
}

/** "3/6" style progress for a run. */
export function runProgress(r: Pick<AgentRun, "steps" | "step_count" | "done_steps">) {
  const total = r.step_count ?? r.steps?.length ?? 0;
  const done = r.done_steps ?? r.steps?.filter((x) => x.status === "done").length ?? 0;
  return { total, done, pct: total ? (done / total) * 100 : 0 };
}
