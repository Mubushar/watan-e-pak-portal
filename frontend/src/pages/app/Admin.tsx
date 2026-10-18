import { Link } from "react-router-dom";
import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BadgeCheck,
  Boxes,
  Check,
  CheckCircle2,
  Cpu,
  Database,
  FileClock,
  HeartPulse,
  KeyRound,
  ListChecks,
  LogIn,
  Pencil,
  RotateCcw,
  Save,
  Settings2,
  ShieldCheck,
  UserCog,
  Users,
  XCircle,
} from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { put } from "@/lib/api";
import { compact, date, num, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { Avatar, Badge, BarList, Button, Card, CardBody, CardHeader, DataTable, EmptyState, JsonView, Modal, PageHeader, QueryState, Segmented, Skeleton, StatCard, StatusBadge, Tabs, type Column } from "@/components/ui";
import { Donut, Legendish } from "@/components/ui/charts";
import { ok } from "@/components/collab/kit";
import { IntegrationsCard } from "@/components/collab/Integrations";

// ---------------------------------------------------------------- types
interface AdminUser {
  id: string;
  name: string | null;
  email: string | null;
  mobile: string | null;
  role: string;
  roles: string[];
  permissions: string[];
  status: string;
  verified: boolean;
  email_verified?: boolean;
  mobile_verified?: boolean;
  has_password?: boolean;
  created_at?: string;
  last_login_at?: string | null;
}
interface Role {
  name: string;
  label: string;
  description?: string;
  portal_area: string;
  level: number;
  permissions: string[];
  is_system: boolean;
  permission_count: number;
  members: number;
}
interface AuthEvent {
  id: string;
  event: string;
  identifier?: string | null;
  user_id?: string | null;
  detail?: string | null;
  created_at: string;
}

type Tab = "users" | "roles" | "audit" | "settings" | "system";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("users");
  const me = useAuth((s) => s.user);
  const canManage = useAuth.getState().can("users.manage") || useAuth.getState().hasRole("super_admin", "admin");
  return (
    <div className="space-y-6">
      <PageHeader
        title="Administration"
        subtitle="Users, roles & permissions, the audit trail, runtime settings and system health."
        crumbs={[{ label: "Dashboard", to: "/app" }, { label: "Administration" }]}
        actions={
          <>
            {useAuth.getState().can("basedata.manage") && (
              <Link to="/app/admin/base-data" className="btn btn-outline btn-sm">
                <Database className="h-4 w-4" /> Base data
              </Link>
            )}
            {me && <Badge tone={canManage ? "gold" : "gray"} icon={<ShieldCheck className="h-3 w-3" />}>{titleCase(me.role)}</Badge>}
          </>
        }
      />
      {!canManage && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
          You are viewing administration in read-only mode. Sign in as <b>admin@portal.pk</b> to manage users and settings.
        </div>
      )}
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "users", label: "Users", icon: <Users className="h-4 w-4" /> },
          { value: "roles", label: "Roles & permissions", icon: <KeyRound className="h-4 w-4" /> },
          { value: "audit", label: "Audit", icon: <FileClock className="h-4 w-4" /> },
          { value: "settings", label: "Settings", icon: <Settings2 className="h-4 w-4" /> },
          { value: "system", label: "System", icon: <HeartPulse className="h-4 w-4" /> },
        ]}
      />
      <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
        {tab === "users" && <UsersTab canManage={canManage} />}
        {tab === "roles" && <RolesTab />}
        {tab === "audit" && <AuditTab />}
        {tab === "settings" && <SettingsTab canManage={canManage} />}
        {tab === "system" && <SystemTab />}
      </motion.div>
    </div>
  );
}

// ---------------------------------------------------------------- users
function UsersTab({ canManage }: { canManage: boolean }) {
  const [status, setStatus] = useState<"all" | "active" | "pending" | "suspended">("all");
  const q = useApi<{ count: number; users: AdminUser[] }>("/auth/users", { status: status === "all" ? undefined : status });
  const roles = useApi<{ roles: Role[] }>("/roles", undefined, { staleTime: 5 * 60_000 });
  const [edit, setEdit] = useState<AdminUser | null>(null);
  const users = q.data?.users ?? [];
  const cols: Column<AdminUser>[] = [
    {
      key: "name",
      header: "User",
      value: (u) => `${u.name ?? ""} ${u.email ?? ""}`,
      render: (u) => (
        <div className="flex min-w-[220px] items-center gap-3">
          <Avatar name={u.name ?? u.email} size={36} />
          <div className="min-w-0">
            <p className="flex items-center gap-1 truncate font-semibold text-ink dark:text-white">
              {u.name ?? "—"} {u.verified && <BadgeCheck className="h-3.5 w-3.5 text-brand-600" />}
            </p>
            <p className="truncate text-xs text-ink-mute">{[u.email, u.mobile].filter(Boolean).join(" · ")}</p>
          </div>
        </div>
      ),
    },
    {
      key: "roles",
      header: "Roles",
      value: (u) => u.roles.join(" "),
      render: (u) => (
        <div className="flex max-w-[260px] flex-wrap gap-1">
          {u.roles.map((r) => (
            <Badge key={r} tone={r === u.role ? "gold" : "gray"}>
              {r.replace(/_/g, " ")}
            </Badge>
          ))}
        </div>
      ),
    },
    { key: "permissions", header: "Perms", align: "right", value: (u) => u.permissions.length, render: (u) => <span className="tabular-nums">{u.permissions.length}</span> },
    { key: "status", header: "Status", render: (u) => <StatusBadge status={u.status} /> },
    { key: "last_login_at", header: "Last login", render: (u) => <span className="whitespace-nowrap text-xs text-ink-mute">{u.last_login_at ? timeAgo(u.last_login_at) : "never"}</span> },
    {
      key: "edit",
      header: "",
      sortable: false,
      render: (u) => (
        <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} disabled={!canManage} onClick={(e) => (e.stopPropagation(), setEdit(u))}>
          Roles
        </Button>
      ),
    },
  ];
  const byStatus = users.reduce<Record<string, number>>((a, u) => ((a[u.status] = (a[u.status] ?? 0) + 1), a), {});
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Accounts" value={q.data?.count ?? "—"} icon={<Users className="h-5 w-5" />} />
        <StatCard label="Active" value={byStatus.active ?? 0} tone="green" icon={<CheckCircle2 className="h-5 w-5" />} />
        <StatCard label="Verified" value={users.filter((u) => u.verified).length} tone="blue" icon={<BadgeCheck className="h-5 w-5" />} />
        <StatCard label="Roles in use" value={new Set(users.flatMap((u) => u.roles)).size} tone="gold" icon={<KeyRound className="h-5 w-5" />} />
      </div>
      <Card className="overflow-hidden">
        <CardHeader title="Accounts" subtitle="Click a row to edit roles" icon={<UserCog className="h-5 w-5" />} action={<Segmented size="sm" value={status} onChange={setStatus} options={["all", "active", "pending", "suspended"].map((s) => ({ value: s as typeof status, label: titleCase(s) }))} />} />
        <QueryState q={q} skeleton={<Skeleton className="m-5 h-72" />}>
          {() => <DataTable rows={users} columns={cols} search pageSize={12} onRowClick={canManage ? setEdit : undefined} />}
        </QueryState>
      </Card>
      {edit && <RoleEditor user={edit} roles={roles.data?.roles ?? []} onClose={() => setEdit(null)} />}
    </div>
  );
}

function RoleEditor({ user, roles, onClose }: { user: AdminUser; roles: Role[]; onClose: () => void }) {
  const [sel, setSel] = useState<string[]>(user.roles);
  const m = useMutate(() => ok(put(`/users/${user.id}/roles`, { roles: sel })), { invalidate: ["/auth/users", "/roles"], success: "Roles updated", onSuccess: onClose });
  const areas = useMemo(() => {
    const g: Record<string, Role[]> = {};
    [...roles].sort((a, b) => b.level - a.level).forEach((r) => (g[r.portal_area] ??= []).push(r));
    return g;
  }, [roles]);
  const perms = new Set(roles.filter((r) => sel.includes(r.name)).flatMap((r) => r.permissions));
  const toggle = (r: string) => setSel((s) => (s.includes(r) ? s.filter((x) => x !== r) : [...s, r]));
  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={`Roles · ${user.name ?? user.email}`}
      subtitle="The highest-level role becomes the primary role."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} disabled={!sel.length} onClick={() => m.mutate()}>
            Save roles
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {Object.entries(areas).map(([area, rs]) => (
          <div key={area}>
            <p className="label">{titleCase(area)}</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {rs.map((r) => {
                const on = sel.includes(r.name);
                return (
                  <button
                    key={r.name}
                    onClick={() => toggle(r.name)}
                    className={cn("flex items-start gap-3 rounded-xl border p-3 text-start transition", on ? "border-brand-500 bg-brand-50 dark:border-brand-400 dark:bg-brand-500/15" : "border-black/10 hover:border-brand-300 dark:border-white/10")}
                  >
                    <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border", on ? "border-brand-600 bg-brand-600 text-white" : "border-black/20 dark:border-white/20")}>{on && <Check className="h-3.5 w-3.5" />}</span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold">{r.label}</span>
                      <span className="block text-[11px] text-ink-mute">
                        L{r.level} · {r.permission_count} permissions
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        <p className="rounded-xl bg-brand-50/60 px-3 py-2 text-xs dark:bg-white/5">
          Effective permissions: <b>{perms.size}</b>
        </p>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- roles
function RolesTab() {
  const roles = useApi<{ roles: Role[]; portal_areas: string[] }>("/roles");
  const perms = useApi<{ permissions: { permission: string; description: string }[] }>("/roles/permissions");
  const summary = useApi<{ roles: number; custom_roles: number; permissions: number; by_area: Record<string, number>; members_per_role: Record<string, number>; signup_roles: string[] }>("/roles/summary");
  const [area, setArea] = useState("all");
  const shown = (roles.data?.roles ?? []).filter((r) => area === "all" || r.portal_area === area).sort((a, b) => b.level - a.level);
  const groups = useMemo(() => {
    const g: Record<string, { permission: string; description: string }[]> = {};
    (perms.data?.permissions ?? []).forEach((p) => (g[p.permission.split(".")[0]!] ??= []).push(p));
    return g;
  }, [perms.data]);
  return (
    <div className="space-y-6">
      {summary.data && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="grid grid-cols-2 gap-4 lg:col-span-2">
            <StatCard label="Roles" value={summary.data.roles} icon={<KeyRound className="h-5 w-5" />} hint={`${summary.data.custom_roles} custom`} />
            <StatCard label="Permissions" value={summary.data.permissions} tone="gold" icon={<ListChecks className="h-5 w-5" />} />
            <Card className="col-span-2 p-5">
              <p className="label">Members per role</p>
              <BarList
                items={Object.entries(summary.data.members_per_role)
                  .filter(([, v]) => v > 0)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => ({ label: titleCase(k), value: v }))}
              />
            </Card>
          </div>
          <Card className="p-5">
            <p className="label">Roles by portal area</p>
            <Donut data={Object.entries(summary.data.by_area).map(([name, value]) => ({ name: titleCase(name), value }))} height={180} format={(v) => String(v)} />
            <div className="mt-3 flex justify-center">
              <Legendish data={Object.entries(summary.data.by_area).map(([name, value]) => ({ name: titleCase(name), value }))} />
            </div>
            <p className="label mt-4">Self-signup roles</p>
            <div className="flex flex-wrap gap-1.5">
              {summary.data.signup_roles.map((r) => (
                <Badge key={r} tone="blue">
                  {r}
                </Badge>
              ))}
            </div>
          </Card>
        </div>
      )}
      <Card className="overflow-hidden">
        <CardHeader
          title="Permission matrix"
          subtitle="Roles × permissions"
          icon={<ShieldCheck className="h-5 w-5" />}
          action={<Segmented size="sm" value={area} onChange={setArea} options={["all", ...(roles.data?.portal_areas ?? [])].map((a) => ({ value: a, label: titleCase(a) }))} />}
        />
        {roles.isLoading || perms.isLoading ? (
          <Skeleton className="m-5 h-96" />
        ) : (
          <div className="max-h-[70vh] overflow-auto">
            <table className="w-full border-separate border-spacing-0 text-xs">
              <thead>
                <tr>
                  <th className="sticky start-0 top-0 z-20 min-w-[200px] border-b border-black/5 bg-white px-3 py-2 text-start font-bold uppercase tracking-wider text-ink-mute dark:border-white/10 dark:bg-[#0d1f16]">Permission</th>
                  {shown.map((r) => (
                    <th key={r.name} className="sticky top-0 z-10 h-36 border-b border-black/5 bg-white px-1 align-bottom dark:border-white/10 dark:bg-[#0d1f16]" title={r.description}>
                      <div className="mx-auto flex w-6 items-end justify-center">
                        <span className="whitespace-nowrap pb-1 font-semibold text-ink-soft [writing-mode:vertical-rl] rotate-180 dark:text-slate-300">
                          {r.label} <span className="text-ink-mute">({r.members})</span>
                        </span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(groups).map(([g, ps]) => (
                  <Fragment key={g}>
                    <tr>
                      <td colSpan={shown.length + 1} className="sticky start-0 bg-brand-50/80 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-brand-800 dark:bg-white/5 dark:text-brand-200">
                        {g}
                      </td>
                    </tr>
                    {ps.map((p) => (
                      <tr key={p.permission} className="hover:bg-brand-50/40 dark:hover:bg-white/[.03]">
                        <td className="sticky start-0 z-10 border-b border-black/[.04] bg-white px-3 py-1.5 dark:border-white/5 dark:bg-[#0d1f16]" title={p.description}>
                          <p className="font-mono text-[11px] font-semibold">{p.permission}</p>
                          <p className="truncate text-[10px] text-ink-mute">{p.description}</p>
                        </td>
                        {shown.map((r) => (
                          <td key={r.name} className="border-b border-black/[.04] text-center dark:border-white/5">
                            {r.permissions.includes(p.permission) ? <span className="mx-auto block h-3 w-3 rounded-full bg-gradient-to-br from-brand-500 to-brand-700 shadow-sm" /> : <span className="mx-auto block h-1 w-1 rounded-full bg-black/15 dark:bg-white/15" />}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- audit
const EVENT_ICON: Record<string, ReactNode> = {
  login: <LogIn className="h-4 w-4" />,
  seed: <Database className="h-4 w-4" />,
  roles_set: <KeyRound className="h-4 w-4" />,
};
function AuditTab() {
  const events = useApi<{ count: number; events: AuthEvent[] }>("/auth/events", { limit: 100 });
  const audit = useApi<{
    memory: { kind: string; value: unknown; at: string }[];
    auth_events: AuthEvent[];
    journal_entries: { id: string; entry_no: number; date: string; reference: string; memo: string; source: string }[];
    counts: Record<string, number>;
  }>("/portal/audit", { limit: 100 });
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader title="Authentication events" subtitle={events.data ? `${events.data.count} recent events` : undefined} icon={<LogIn className="h-5 w-5" />} />
        <CardBody className="max-h-[640px] overflow-y-auto">
          <QueryState q={events} skeleton={<Skeleton className="h-60" />}>
            {(d) =>
              d.events.length === 0 ? (
                <EmptyState title="No events" />
              ) : (
                <ol className="relative space-y-4 ps-6 before:absolute before:inset-y-1 before:start-2 before:w-px before:bg-black/10 dark:before:bg-white/10">
                  {d.events.map((e) => (
                    <li key={e.id} className="relative">
                      <span className={cn("absolute -start-6 top-0 flex h-5 w-5 items-center justify-center rounded-full text-white", /fail|denied|locked/.test(e.event) ? "bg-red-500" : "bg-brand-600")}>
                        <span className="scale-75">{EVENT_ICON[e.event] ?? <Activity className="h-4 w-4" />}</span>
                      </span>
                      <p className="text-sm font-semibold">
                        {titleCase(e.event)} {e.identifier && <span className="font-normal text-ink-mute">· {e.identifier}</span>}
                      </p>
                      {e.detail && <p className="text-xs text-ink-mute">{e.detail}</p>}
                      <p className="text-[11px] text-ink-mute">
                        {date(e.created_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · {timeAgo(e.created_at)}
                      </p>
                    </li>
                  ))}
                </ol>
              )
            }
          </QueryState>
        </CardBody>
      </Card>
      <div className="space-y-6">
        <Card>
          <CardHeader title="Portal activity" subtitle={audit.data ? Object.entries(audit.data.counts).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(" · ") : undefined} icon={<Activity className="h-5 w-5" />} />
          <CardBody className="max-h-[320px] overflow-y-auto">
            <QueryState q={audit} skeleton={<Skeleton className="h-48" />}>
              {(d) => (
                <ul className="space-y-2">
                  {[...d.memory].reverse().slice(0, 40).map((m, i) => (
                    <li key={i} className="flex items-start gap-3 rounded-xl px-2 py-1.5 text-xs hover:bg-black/[.03] dark:hover:bg-white/5">
                      <Badge tone="blue">{m.kind}</Badge>
                      <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-mute">{typeof m.value === "object" ? JSON.stringify(m.value) : String(m.value)}</span>
                      <span className="shrink-0 text-ink-mute">{timeAgo(m.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </QueryState>
          </CardBody>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader title="Ledger postings" subtitle="Latest journal entries" icon={<FileClock className="h-5 w-5" />} />
          <QueryState q={audit} skeleton={<Skeleton className="m-5 h-48" />}>
            {(d) => (
              <DataTable
                dense
                pageSize={8}
                rows={[...d.journal_entries].reverse()}
                columns={[
                  { key: "entry_no", header: "#", align: "right" },
                  { key: "date", header: "Date", render: (j) => date(j.date) },
                  { key: "reference", header: "Ref", render: (j) => <span className="font-mono text-xs">{j.reference}</span> },
                  { key: "memo", header: "Memo", render: (j) => <span className="line-clamp-1 text-xs">{j.memo}</span> },
                  { key: "source", header: "Source", render: (j) => <Badge tone="gray">{j.source}</Badge> },
                ]}
              />
            )}
          </QueryState>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- settings
type Json = Record<string, unknown>;
function diff(orig: Json, next: Json): Json {
  const out: Json = {};
  for (const [section, val] of Object.entries(next)) {
    const o = orig[section];
    if (val && typeof val === "object" && !Array.isArray(val) && o && typeof o === "object") {
      const changed: Json = {};
      for (const [k, v] of Object.entries(val as Json)) if (JSON.stringify(v) !== JSON.stringify((o as Json)[k])) changed[k] = v;
      if (Object.keys(changed).length) out[section] = changed;
    } else if (JSON.stringify(val) !== JSON.stringify(o)) out[section] = val;
  }
  return out;
}

function SettingsTab({ canManage }: { canManage: boolean }) {
  const q = useApi<Json>("/portal/settings");
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"view" | "edit">("view");
  useEffect(() => {
    if (q.data) setText(JSON.stringify(q.data, null, 2));
  }, [q.data]);
  const parsed = useMemo((): { value?: Json; error?: string } => {
    try {
      const v = JSON.parse(text || "{}");
      if (!v || typeof v !== "object" || Array.isArray(v)) return { error: "Settings must be a JSON object" };
      return { value: v as Json };
    } catch (e) {
      return { error: (e as Error).message };
    }
  }, [text]);
  const changes = parsed.value && q.data ? diff(q.data, parsed.value) : {};
  const nChanges = Object.values(changes).reduce<number>((a, v) => a + (v && typeof v === "object" ? Object.keys(v).length : 1), 0);
  const save = useMutate(() => ok(put<{ updated: Json }>("/portal/settings", { updates: changes })), {
    invalidate: ["/portal/settings"],
    success: (r) => `${Object.keys(r.updated ?? {}).length} setting(s) applied`,
  });
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Runtime settings"
        subtitle="Assumptions, forecasting, accounting, auth and wing configuration"
        icon={<Settings2 className="h-5 w-5" />}
        action={<Segmented size="sm" value={mode} onChange={setMode} options={[{ value: "view", label: "Browse" }, { value: "edit", label: "JSON editor" }]} />}
      />
      <QueryState q={q} skeleton={<Skeleton className="m-5 h-96" />}>
        {(d) =>
          mode === "view" ? (
            <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
              {Object.entries(d).map(([k, v]) => (
                <div key={k} className="rounded-2xl border border-black/5 p-4 dark:border-white/10">
                  <p className="mb-2 flex items-center justify-between font-display font-semibold">
                    {titleCase(k)} {!!v && typeof v === "object" && <Badge tone="gray">{Object.keys(v as object).length}</Badge>}
                  </p>
                  <div className="max-h-56 overflow-auto">
                    <JsonView data={v} defaultOpen={1} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                {parsed.error ? (
                  <Badge tone="red" icon={<XCircle className="h-3 w-3" />}>
                    Invalid JSON: {parsed.error}
                  </Badge>
                ) : (
                  <Badge tone={nChanges ? "gold" : "green"} icon={<CheckCircle2 className="h-3 w-3" />}>
                    Valid · {nChanges} change(s)
                  </Badge>
                )}
                <div className="ms-auto flex gap-2">
                  <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setText(JSON.stringify(d, null, 2))}>
                    Reset
                  </Button>
                  <Button size="sm" icon={<Save className="h-3.5 w-3.5" />} disabled={!canManage || !!parsed.error || !nChanges} loading={save.isPending} onClick={() => save.mutate()}>
                    Apply changes
                  </Button>
                </div>
              </div>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                spellCheck={false}
                dir="ltr"
                className={cn("input h-[55vh] min-h-[360px] w-full resize-y font-mono text-xs leading-5", parsed.error && "border-red-400 focus:border-red-500")}
              />
              {nChanges > 0 && !parsed.error && (
                <div className="mt-3 rounded-xl bg-gold-50/70 p-3 dark:bg-gold-500/10">
                  <p className="label">Pending update payload</p>
                  <JsonView data={changes} defaultOpen={2} />
                </div>
              )}
              <p className="mt-2 text-xs text-ink-mute">Only changed keys are sent. Unknown keys are ignored by the server.</p>
            </div>
          )
        }
      </QueryState>
    </Card>
  );
}

// ---------------------------------------------------------------- system
function SystemTab() {
  const ph = useApi<{ status: string; version: string; mcp: Record<string, number>; stores: Record<string, number> }>("/portal/health", undefined, { refetchInterval: 30_000 });
  const h = useApi<{ status: string; version: string; time: string }>("/health", undefined, { refetchInterval: 30_000 });
  const cat = useApi<{ tool_count: number; groups: Record<string, number>; resources_count: number; templates_count: number; prompts_count: number }>("/portal/catalog", undefined, { staleTime: 10 * 60_000 });
  const subs = useApi<{ count: number; subscriptions: { id: string; account: string; plan_key: string; product: string; seats: number; status: string; started_at: string }[] }>("/commercial/subscriptions");
  const up = h.data?.status === "ok" && ph.data?.status === "ok";
  return (
    <div className="space-y-6">
      <div className={cn("relative overflow-hidden rounded-3xl p-6 text-white shadow-soft", up ? "bg-brand-gradient" : "bg-gradient-to-br from-red-700 to-red-500")}>
        <div className="pointer-events-none absolute -end-10 -top-10 h-48 w-48 rounded-full bg-gold-400/25 blur-3xl" />
        <div className="relative flex flex-wrap items-center gap-5">
          <span className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-white/15">
            <HeartPulse className="h-7 w-7" />
            {up && <span className="absolute -end-1 -top-1 h-3.5 w-3.5 animate-ping rounded-full bg-emerald-300" />}
          </span>
          <div className="flex-1">
            <p className="font-display text-2xl font-bold">{h.isLoading ? "Checking…" : up ? "All systems operational" : "Backend degraded"}</p>
            <p className="text-sm text-white/75">
              API v{h.data?.version ?? "—"} · server time {h.data ? date(h.data.time, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"} · auto-refresh 30 s
            </p>
          </div>
        </div>
      </div>

      {ph.data && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="MCP tools" value={num(ph.data.mcp.tools)} icon={<Cpu className="h-5 w-5" />} />
          <StatCard label="Resources" value={num(ph.data.mcp.resources)} tone="gold" icon={<Boxes className="h-5 w-5" />} hint={`${ph.data.mcp.resource_templates ?? 0} templates`} />
          <StatCard label="Prompts" value={num(ph.data.mcp.prompts)} tone="blue" icon={<ListChecks className="h-5 w-5" />} />
          <StatCard label="Data stores" value={Object.keys(ph.data.stores).length} tone="purple" icon={<Database className="h-5 w-5" />} hint={`${compact(Object.values(ph.data.stores).reduce((a, b) => a + b, 0))} records`} />
        </div>
      )}

      <IntegrationsCard />

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Record counts" subtitle="In-memory stores" icon={<Database className="h-5 w-5" />} />
          <CardBody>
            <QueryState q={ph} skeleton={<Skeleton className="h-60" />}>
              {(d) => (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                  {Object.entries(d.stores)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between gap-2 rounded-xl bg-brand-50/50 px-3 py-2 dark:bg-white/5">
                        <span className="truncate text-xs text-ink-soft dark:text-slate-300">{titleCase(k)}</span>
                        <span className="font-semibold tabular-nums">{num(v)}</span>
                      </div>
                    ))}
                </div>
              )}
            </QueryState>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="MCP catalog" subtitle={cat.data ? `${cat.data.tool_count} tools in ${Object.keys(cat.data.groups).length} groups` : undefined} icon={<Cpu className="h-5 w-5" />} />
          <CardBody className="max-h-[420px] overflow-y-auto">
            <QueryState q={cat} skeleton={<Skeleton className="h-60" />}>
              {(d) => (
                <BarList
                  tone="gold"
                  items={Object.entries(d.groups)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => ({ label: titleCase(k), value: v }))}
                />
              )}
            </QueryState>
          </CardBody>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <CardHeader title="Commercial subscriptions" icon={<BadgeCheck className="h-5 w-5" />} />
        <QueryState q={subs} skeleton={<Skeleton className="m-5 h-32" />}>
          {(d) => (
            <DataTable
              rows={d.subscriptions}
              columns={[
                { key: "account", header: "Account", render: (s) => <b>{s.account}</b> },
                { key: "product", header: "Product", render: (s) => titleCase(s.product) },
                { key: "plan_key", header: "Plan", render: (s) => <Badge tone="gold">{s.plan_key}</Badge> },
                { key: "seats", header: "Seats", align: "right" },
                { key: "status", header: "Status", render: (s) => <StatusBadge status={s.status} /> },
                { key: "started_at", header: "Started", render: (s) => date(s.started_at) },
              ]}
            />
          )}
        </QueryState>
      </Card>
    </div>
  );
}
