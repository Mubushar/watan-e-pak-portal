import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertOctagon,
  Bug,
  CalendarDays,
  ClipboardList,
  Columns3,
  Gauge,
  Hammer,
  ListChecks,
  Plus,
  RefreshCcw,
  Sparkles,
  Table2,
  Wallet,
} from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { get, post, put } from "@/lib/api";
import { useApi, useMutate } from "@/hooks/useApi";
import { num, pkrShort, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Avatar,
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  QueryState,
  Segmented,
  Select,
  Skeleton,
  StatCard,
  Tabs,
  Textarea,
  type Column,
} from "@/components/ui";
import { FormGrid, SkeletonGrid, bandTone, ensure, numOr, rs, useFormState } from "@/components/biz/ops-kit";
import {
  AnnualEstimate,
  ConditionScorer,
  DefectsCatalogue,
  LifecycleReserve,
  PROPERTY_TYPES,
  PreventiveSchedule,
  RepairOrReplace,
  type Component,
  type Defect,
} from "@/components/biz/MaintenanceTools";

interface WorkOrder {
  id: string;
  title: string;
  property_type: string;
  component?: string | null;
  defect?: string | null;
  priority: string;
  status: string;
  description?: string | null;
  estimated_cost: number;
  assignee?: string | null;
  created_at: string;
}
type WoRes = { count: number; work_orders: WorkOrder[] };

const STATUSES = ["open", "assigned", "in_progress", "done", "cancelled"] as const;
const PRIORITIES = ["routine", "soon", "urgent", "emergency"] as const;
const STATUS_ACCENT: Record<string, string> = { open: "bg-sky-500", assigned: "bg-violet-500", in_progress: "bg-orange-500", done: "bg-brand-600", cancelled: "bg-slate-400" };
const WO_KEY = ["/maintenance/work-orders", {}] as const;
const INVALIDATE_PREFIX = ["/maintenance", "/portal", "/agents"];

type TabKey = "orders" | "condition" | "estimate" | "lifecycle" | "ror" | "schedule" | "defects";

export default function Maintenance() {
  const [tab, setTab] = useState<TabKey>("orders");
  const [creating, setCreating] = useState(false);
  const wos = useApi<WoRes>("/maintenance/work-orders");
  const components = useApi<{ components: Component[] }>("/maintenance/components");

  const list = wos.data?.work_orders ?? [];
  const active = list.filter((w) => w.status !== "done" && w.status !== "cancelled");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Maintenance"
        subtitle="Work orders, condition surveys, reserve studies and the defect catalogue"
        actions={
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
            New work order
          </Button>
        }
      />

      {wos.isLoading ? (
        <SkeletonGrid n={4} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Active work orders" value={active.length} icon={<ClipboardList className="h-5 w-5" />} hint={`${list.length} total`} />
          <StatCard
            label="Urgent / emergency"
            value={active.filter((w) => w.priority === "urgent" || w.priority === "emergency").length}
            icon={<AlertOctagon className="h-5 w-5" />}
            tone="red"
          />
          <StatCard label="Open estimate" value={rs(active.reduce((s, w) => s + (w.estimated_cost || 0), 0))} icon={<Wallet className="h-5 w-5" />} tone="gold" />
          <StatCard label="Completed" value={list.filter((w) => w.status === "done").length} icon={<ListChecks className="h-5 w-5" />} tone="green" hint="work orders closed" />
        </div>
      )}

      <Card className="overflow-hidden">
        <Tabs<TabKey>
          className="px-2"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "orders", label: "Work orders", icon: <ClipboardList className="h-4 w-4" />, count: active.length },
            { value: "condition", label: "Condition", icon: <Gauge className="h-4 w-4" /> },
            { value: "estimate", label: "Annual estimate", icon: <Wallet className="h-4 w-4" /> },
            { value: "lifecycle", label: "Lifecycle reserve", icon: <RefreshCcw className="h-4 w-4" /> },
            { value: "ror", label: "Repair or replace", icon: <Hammer className="h-4 w-4" /> },
            { value: "schedule", label: "Preventive plan", icon: <CalendarDays className="h-4 w-4" /> },
            { value: "defects", label: "Defects", icon: <Bug className="h-4 w-4" /> },
          ]}
        />
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="p-4 sm:p-5">
          {tab === "orders" && <WorkOrders q={wos} onNew={() => setCreating(true)} />}
          {tab === "condition" && <ConditionScorer />}
          {tab === "estimate" && <AnnualEstimate />}
          {tab === "lifecycle" && <LifecycleReserve />}
          {tab === "ror" && <RepairOrReplace components={components.data?.components ?? []} />}
          {tab === "schedule" && <PreventiveSchedule />}
          {tab === "defects" && <DefectsCatalogue />}
        </motion.div>
      </Card>

      <NewWorkOrderModal open={creating} onClose={() => setCreating(false)} components={components.data?.components ?? []} />
    </div>
  );
}

// ================================================================== work orders
function useMoveWorkOrder() {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { id: string; patch: Partial<WorkOrder> }, { prev?: WoRes }>({
    mutationFn: ({ id, patch }) => put(`/maintenance/work-orders/${id}`, patch).then(ensure),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: WO_KEY });
      const prev = qc.getQueryData<WoRes>(WO_KEY);
      qc.setQueryData<WoRes>(WO_KEY, (old) => (old ? { ...old, work_orders: old.work_orders.map((w) => (w.id === id ? { ...w, ...patch } : w)) } : old));
      return { prev };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(WO_KEY, ctx.prev);
      toast.error(e.message || "Update failed");
    },
    onSuccess: (_r, v) => toast.success(v.patch.status ? `Moved to ${titleCase(v.patch.status)}` : "Work order updated"),
    onSettled: () => qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && INVALIDATE_PREFIX.some((p) => (q.queryKey[0] as string).startsWith(p)) }),
  });
}

function WorkOrders({ q, onNew }: { q: ReturnType<typeof useApi<WoRes>>; onNew: () => void }) {
  const [view, setView] = useState<"board" | "table">("board");
  const [priority, setPriority] = useState("");
  const [editing, setEditing] = useState<WorkOrder | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const move = useMoveWorkOrder();
  const rows = (q.data?.work_orders ?? []).filter((w) => !priority || w.priority === priority);

  const columns: Column<WorkOrder>[] = [
    {
      key: "title",
      header: "Work order",
      render: (w) => (
        <div className="min-w-[200px]">
          <p className="font-semibold">{w.title}</p>
          <p className="text-xs text-ink-mute">
            {titleCase(w.property_type)} · {titleCase(w.component) || "General"}
          </p>
        </div>
      ),
    },
    { key: "priority", header: "Priority", render: (w) => <Badge tone={bandTone(w.priority)} className="capitalize">{w.priority}</Badge> },
    {
      key: "status",
      header: "Status",
      render: (w) => (
        <select
          value={w.status}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => move.mutate({ id: w.id, patch: { status: e.target.value } })}
          className="rounded-lg border border-black/10 bg-white px-2 py-1 text-xs font-semibold dark:border-white/10 dark:bg-white/5"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {titleCase(s)}
            </option>
          ))}
        </select>
      ),
    },
    { key: "estimated_cost", header: "Estimate", align: "right", render: (w) => <span className="whitespace-nowrap">{w.estimated_cost ? `Rs ${num(w.estimated_cost)}` : "—"}</span> },
    { key: "assignee", header: "Assignee", render: (w) => <span className="text-xs">{w.assignee ?? "—"}</span> },
    { key: "created_at", header: "Raised", render: (w) => <span className="whitespace-nowrap text-xs text-ink-mute">{timeAgo(w.created_at)}</span> },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          size="sm"
          value={view}
          onChange={setView}
          options={[
            { value: "board", label: "Board", icon: <Columns3 className="h-3.5 w-3.5" /> },
            { value: "table", label: "Table", icon: <Table2 className="h-3.5 w-3.5" /> },
          ]}
        />
        <div className="flex items-center gap-2">
          <Select className="w-36 py-2 text-xs" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {titleCase(p)}
              </option>
            ))}
          </Select>
          <Button size="sm" variant="soft" icon={<Plus className="h-4 w-4" />} onClick={onNew}>
            Add
          </Button>
        </div>
      </div>

      <QueryState q={q} skeleton={<div className="flex gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-72 w-64 shrink-0" />)}</div>}>
        {() =>
          view === "board" ? (
            <div className="no-scrollbar -mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-3 sm:mx-0 sm:px-0">
              {STATUSES.map((status) => {
                const items = rows.filter((w) => w.status === status);
                return (
                  <div
                    key={status}
                    onDragOver={(e) => {
                      e.preventDefault();
                      if (over !== status) setOver(status);
                    }}
                    onDragLeave={(e) => {
                      if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver((o) => (o === status ? null : o));
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setOver(null);
                      const id = e.dataTransfer.getData("text/plain");
                      const wo = rows.find((w) => w.id === id);
                      if (wo && wo.status !== status) move.mutate({ id, patch: { status } });
                    }}
                    className={cn(
                      "flex w-[260px] shrink-0 snap-start flex-col rounded-2xl border bg-black/[.02] transition-colors dark:bg-white/[.02]",
                      over === status ? "border-brand-400 bg-brand-50/70 dark:border-brand-500/60 dark:bg-brand-500/10" : "border-black/5 dark:border-white/10",
                    )}
                  >
                    <div className="flex items-center gap-2 border-b border-black/5 px-3 py-3 dark:border-white/10">
                      <span className={cn("h-2.5 w-2.5 rounded-full", STATUS_ACCENT[status])} />
                      <span className="text-sm font-semibold">{titleCase(status)}</span>
                      <span className="ms-auto rounded-full bg-black/5 px-2 py-0.5 text-[11px] font-bold dark:bg-white/10">{items.length}</span>
                    </div>
                    <div className="flex min-h-[200px] flex-1 flex-col gap-2 p-2">
                      {items.map((w) => (
                        <motion.div key={w.id} layout>
                          <div
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.setData("text/plain", w.id);
                              e.dataTransfer.effectAllowed = "move";
                            }}
                            onClick={() => setEditing(w)}
                            className="cursor-grab rounded-xl border border-black/5 bg-white p-3 shadow-sm transition-shadow hover:shadow-soft active:cursor-grabbing dark:border-white/10 dark:bg-[#0d1f16]"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-sm font-semibold leading-snug">{w.title}</p>
                              <Badge tone={bandTone(w.priority)} className="shrink-0 capitalize">
                                {w.priority}
                              </Badge>
                            </div>
                            <p className="mt-1 text-xs text-ink-mute">
                              {titleCase(w.component) || "General"}
                              {w.defect ? ` · ${titleCase(w.defect)}` : ""}
                            </p>
                            <div className="mt-2.5 flex items-center justify-between text-xs">
                              <span className="font-semibold">{w.estimated_cost ? pkrShort(w.estimated_cost) : "—"}</span>
                              {w.assignee ? (
                                <span className="inline-flex items-center gap-1 text-ink-mute">
                                  <Avatar name={w.assignee} size={18} /> <span className="max-w-[90px] truncate">{w.assignee}</span>
                                </span>
                              ) : (
                                <span className="text-ink-mute">{timeAgo(w.created_at)}</span>
                              )}
                            </div>
                          </div>
                        </motion.div>
                      ))}
                      {items.length === 0 && (
                        <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-black/10 p-4 text-xs text-ink-mute dark:border-white/10">Drop here</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <Card className="overflow-hidden">
              <DataTable rows={rows} columns={columns} search onRowClick={setEditing} empty={<EmptyState title="No work orders" />} />
            </Card>
          )
        }
      </QueryState>
      <EditWorkOrderModal wo={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

function EditWorkOrderModal({ wo, onClose }: { wo: WorkOrder | null; onClose: () => void }) {
  const [f, , , setF] = useFormState({ status: "open", priority: "routine", assignee: "", estimated_cost: "", description: "" });
  useEffect(() => {
    if (wo) setF({ status: wo.status, priority: wo.priority, assignee: wo.assignee ?? "", estimated_cost: String(wo.estimated_cost ?? ""), description: wo.description ?? "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wo]);
  const save = useMutate(
    () =>
      put(`/maintenance/work-orders/${wo!.id}`, {
        status: f.status,
        priority: f.priority,
        assignee: f.assignee || undefined,
        estimated_cost: numOr(f.estimated_cost),
        description: f.description || undefined,
      }).then(ensure),
    { invalidate: INVALIDATE_PREFIX, success: "Work order updated", onSuccess: onClose },
  );
  return (
    <Modal
      open={!!wo}
      onClose={onClose}
      title={wo?.title ?? "Work order"}
      subtitle={wo ? `${titleCase(wo.property_type)} · ${titleCase(wo.component) || "General"}${wo.defect ? ` · ${titleCase(wo.defect)}` : ""}` : undefined}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="mb-4 flex flex-wrap gap-1.5">
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setF((x) => ({ ...x, status: s }))}
            className={cn("rounded-full px-3 py-1 text-xs font-semibold transition-colors", f.status === s ? "bg-brand-700 text-white" : "bg-black/5 text-ink-soft hover:bg-black/10 dark:bg-white/10 dark:text-slate-300")}
          >
            {titleCase(s)}
          </button>
        ))}
      </div>
      <FormGrid>
        <Field label="Priority">
          <Select value={f.priority} onChange={(e) => setF((x) => ({ ...x, priority: e.target.value }))} options={PRIORITIES.map((p) => ({ value: p, label: titleCase(p) }))} />
        </Field>
        <Field label="Estimated cost (Rs)">
          <Input type="number" min={0} value={f.estimated_cost} onChange={(e) => setF((x) => ({ ...x, estimated_cost: e.target.value }))} />
        </Field>
        <Field label="Assignee" className="sm:col-span-2">
          <Input value={f.assignee} onChange={(e) => setF((x) => ({ ...x, assignee: e.target.value }))} placeholder="Contractor / technician" />
        </Field>
        <Field label="Notes" className="sm:col-span-2">
          <Textarea value={f.description} onChange={(e) => setF((x) => ({ ...x, description: e.target.value }))} />
        </Field>
      </FormGrid>
    </Modal>
  );
}

function NewWorkOrderModal({ open, onClose, components }: { open: boolean; onClose: () => void; components: Component[] }) {
  const defectsQ = useApi<{ defects: Defect[] }>(open ? "/maintenance/defects" : null);
  const [f, set, reset, setF] = useFormState({ title: "", property_type: "house", component: "", defect: "", priority: "routine", estimated_cost: "", assignee: "", description: "", quantity: "1" });
  const defects = useMemo(() => (defectsQ.data?.defects ?? []).filter((d) => !f.component || d.affected_components.includes(f.component)), [defectsQ.data, f.component]);
  const selectedDefect = defectsQ.data?.defects.find((d) => d.key === f.defect);
  const [estimating, setEstimating] = useState(false);

  const estimate = async () => {
    if (!f.defect) return;
    setEstimating(true);
    try {
      const r = await get<{ cost_mid: number; urgency?: string; error?: string }>("/maintenance/repair-estimate", { defect: f.defect, quantity: numOr(f.quantity, 1) });
      ensure(r);
      setF((x) => ({ ...x, estimated_cost: String(Math.round(r.cost_mid)), priority: r.urgency && (PRIORITIES as readonly string[]).includes(r.urgency) ? r.urgency : x.priority }));
      toast.success(`Estimated Rs ${num(r.cost_mid)}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setEstimating(false);
    }
  };

  const create = useMutate(
    () =>
      post("/maintenance/work-orders", {
        title: f.title.trim(),
        property_type: f.property_type,
        component: f.component || undefined,
        defect: f.defect || undefined,
        priority: f.priority,
        estimated_cost: numOr(f.estimated_cost, 0),
        assignee: f.assignee || undefined,
        description: f.description || undefined,
      }).then(ensure),
    {
      invalidate: INVALIDATE_PREFIX,
      success: "Work order raised",
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
      title="New work order"
      subtitle="Raise a repair or service job"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} disabled={!f.title.trim()} onClick={() => create.mutate()}>
            Raise work order
          </Button>
        </>
      }
    >
      <FormGrid>
        <Field label="Title *" className="sm:col-span-2">
          <Input value={f.title} onChange={(e) => set("title")(e.target.value)} placeholder="e.g. Roof seepage — House 12, DHA Lahore" autoFocus />
        </Field>
        <Field label="Property type">
          <Select value={f.property_type} onChange={(e) => set("property_type")(e.target.value)} options={PROPERTY_TYPES.map((p) => ({ value: p, label: titleCase(p) }))} />
        </Field>
        <Field label="Priority">
          <Select value={f.priority} onChange={(e) => set("priority")(e.target.value)} options={PRIORITIES.map((p) => ({ value: p, label: titleCase(p) }))} />
        </Field>
        <Field label="Component">
          <Select
            value={f.component}
            onChange={(e) => setF((x) => ({ ...x, component: e.target.value, defect: "" }))}
          >
            <option value="">General</option>
            {components.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Defect" hint={selectedDefect ? `${selectedDefect.severity} severity · Rs ${num(selectedDefect.cost_low)}–${num(selectedDefect.cost_high)} per ${selectedDefect.unit}` : undefined}>
          <Select value={f.defect} onChange={(e) => set("defect")(e.target.value)}>
            <option value="">None / unknown</option>
            {defects.map((d) => (
              <option key={d.key} value={d.key}>
                {d.name}
              </option>
            ))}
          </Select>
        </Field>
        {f.defect && (
          <Field label={`Quantity (${selectedDefect?.unit ?? "units"})`}>
            <Input type="number" min={1} value={f.quantity} onChange={(e) => set("quantity")(e.target.value)} />
          </Field>
        )}
        <Field label="Estimated cost (Rs)">
          <div className="flex gap-2">
            <Input type="number" min={0} value={f.estimated_cost} onChange={(e) => set("estimated_cost")(e.target.value)} />
            {f.defect && (
              <Button variant="gold" size="sm" className="shrink-0" icon={<Sparkles className="h-4 w-4" />} loading={estimating} onClick={estimate}>
                Estimate
              </Button>
            )}
          </div>
        </Field>
        <Field label="Assignee">
          <Input value={f.assignee} onChange={(e) => set("assignee")(e.target.value)} placeholder="Contractor / technician" />
        </Field>
        <Field label="Description" className="sm:col-span-2">
          <Textarea value={f.description} onChange={(e) => set("description")(e.target.value)} />
        </Field>
      </FormGrid>
    </Modal>
  );
}

