import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AtSign,
  BadgeCheck,
  Bell,
  BellRing,
  Eye,
  EyeOff,
  GitCompareArrows,
  Globe,
  Heart,
  History,
  KeyRound,
  Languages,
  Lock,
  Mail,
  MessageSquare,
  Moon,
  Monitor,
  Phone,
  Save,
  Send,
  ShieldCheck,
  Smartphone,
  Sun,
  Trash2,
  Pencil,
  Check,
  X,
  UserRound,
} from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { del, post, put } from "@/lib/api";
import { date, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth, type User } from "@/store/auth";
import { usePrefs, type Lang, type Theme } from "@/store/prefs";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, EmptyState, Field, Input, PageHeader, Progress, QueryState, Segmented, Select, Skeleton, Toggle } from "@/components/ui";
import { ok } from "@/components/collab/kit";

interface Prefs {
  user_id: string;
  display_name: string;
  notification_prefs: Record<string, string[]>;
  quiet_hours: { start: string; end: string };
  digest: string;
  telegram_opt_in: boolean;
  telegram_linked: boolean;
  categories: string[];
  channels: string[];
}
interface Telegram {
  opt_in: boolean;
  linked: boolean;
  chat_id: string | null;
  categories: string[];
  bot: string;
  policy: string;
}

const CHANNEL_ICON: Record<string, ReactNode> = {
  in_app: <Bell className="h-3.5 w-3.5" />,
  email: <Mail className="h-3.5 w-3.5" />,
  telegram: <Send className="h-3.5 w-3.5" />,
  sms: <Smartphone className="h-3.5 w-3.5" />,
};
const CATEGORY_HINT: Record<string, string> = {
  mention: "Someone @mentions you",
  direct: "Direct messages",
  channel: "Channel activity",
  property: "Property threads",
  lead: "New & assigned leads",
  approval: "Approvals waiting on you",
  task: "Tasks & actions",
  system: "System notices",
};

export default function Profile() {
  const authUser = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const me = useApi<{ authenticated: boolean; user: User & { created_at?: string; email_verified?: boolean; mobile_verified?: boolean; has_password?: boolean } }>(authUser ? "/auth/me" : null);
  useEffect(() => {
    if (me.data?.user) setUser(me.data.user);
  }, [me.data, setUser]);
  const u = me.data?.user ?? authUser;
  const unread = useApi<{ conversations_unread: number; mentions: number; notifications_unread: number; open_actions: number; overdue_actions: number }>(u ? `/messaging/unread-summary/${u.id}` : null);

  if (!authUser) return <EmptyState title="Sign in to see your profile" action={<Link to="/login?next=/app/profile" className="btn btn-primary">Sign in</Link>} />;

  return (
    <div className="space-y-6">
      <PageHeader title="Profile" subtitle="Your account, security, notifications and display preferences." crumbs={[{ label: "Dashboard", to: "/app" }, { label: "Profile" }]} />

      {/* account hero */}
      <div className="relative overflow-hidden rounded-3xl bg-brand-gradient p-6 text-white shadow-soft sm:p-8">
        <div className="pointer-events-none absolute -end-20 -top-24 h-72 w-72 rounded-full bg-gold-400/25 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 start-1/3 h-40 w-40 rounded-full bg-emerald-300/20 blur-3xl" />
        {me.isLoading && !u ? (
          <Skeleton className="h-24 bg-white/10" />
        ) : u ? (
          <div className="relative flex flex-col gap-6 md:flex-row md:items-center">
            <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="rounded-full p-1 ring-2 ring-gold-300/70">
              <Avatar name={u.name ?? u.email} size={88} />
            </motion.div>
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 font-display text-2xl font-bold sm:text-3xl">
                {u.name ?? "Unnamed user"}
                {u.verified && <BadgeCheck className="h-6 w-6 text-gold-300" />}
              </p>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-white/80">
                {u.email && (
                  <span className="inline-flex items-center gap-1.5">
                    <Mail className="h-4 w-4" /> {u.email}
                  </span>
                )}
                {u.mobile && (
                  <span className="inline-flex items-center gap-1.5">
                    <Phone className="h-4 w-4" /> {u.mobile}
                  </span>
                )}
                {u.last_login_at && (
                  <span className="inline-flex items-center gap-1.5">
                    <History className="h-4 w-4" /> Last login {timeAgo(u.last_login_at)}
                  </span>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {u.roles.map((r) => (
                  <span key={r} className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", r === u.role ? "bg-gold-gradient text-brand-950" : "bg-white/15")}>
                    {titleCase(r)}
                  </span>
                ))}
                <span className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold capitalize">{u.status}</span>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center md:w-80">
              <HeroStat label="Permissions" value={u.permissions.length} />
              <HeroStat label="Unread" value={unread.data?.conversations_unread ?? "—"} to="/app/messages" />
              <HeroStat label="Mentions" value={unread.data?.mentions ?? "—"} to="/app/messages" />
            </div>
          </div>
        ) : null}
      </div>
      {me.error && <QueryState q={me}>{() => null}</QueryState>}

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <NotificationPrefs userId={authUser.id} />
          <AssistantMemory />
        </div>
        <div className="space-y-6">
          <PasswordCard hasPassword={(me.data?.user as { has_password?: boolean } | undefined)?.has_password} />
          <TelegramCard userId={authUser.id} />
          <UiPrefs />
          {u && (
            <Card>
              <CardHeader title="Account details" icon={<UserRound className="h-5 w-5" />} />
              <CardBody className="space-y-2 text-sm">
                <Row label="User ID" value={<span className="font-mono text-xs">{u.id}</span>} />
                <Row label="Primary role" value={titleCase(u.role)} />
                <Row label="Verified" value={u.verified ? <Badge tone="green">Yes</Badge> : <Badge tone="gold">Pending</Badge>} />
                {u.agent_id && <Row label="Agent profile" value={<span className="font-mono text-xs">{u.agent_id}</span>} />}
                {u.customer_id && <Row label="Customer profile" value={<span className="font-mono text-xs">{u.customer_id}</span>} />}
                {"created_at" in u && <Row label="Member since" value={date((u as { created_at?: string }).created_at)} />}
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

interface MemoryState {
  enabled: boolean;
  recent_turns: number;
  memories: { id: string; kind: string; value: string; source: string; updated_at?: string; updated?: string }[];
}

function AssistantMemory() {
  const q = useApi<MemoryState>("/me/memory");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const save = useMutate(({ id, value }: { id: string; value: string }) => put(`/me/memory/${id}`, { value }), {
    invalidate: ["/me/memory"], success: "Memory updated", onSuccess: () => setEditing(null),
  });
  const forget = useMutate((id: string) => del(`/me/memory/${id}`), { invalidate: ["/me/memory"], success: "Memory removed" });
  const clear = useMutate(() => del("/me/memory"), { invalidate: ["/me/memory"], success: "Assistant memory cleared" });
  const setting = useMutate((enabled: boolean) => put("/me/memory/settings", { enabled }), { invalidate: ["/me/memory"] });
  const memories = q.data?.memories ?? [];
  return (
    <Card>
      <CardHeader title="Assistant memory" subtitle="Review, correct, or remove what the assistant remembers" icon={<History className="h-5 w-5" />} />
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-mute">Recent turns: {q.data?.recent_turns ?? "—"}. Inferred facts expire from recall after 180 days.</p>
          <div className="flex items-center gap-3">
            <Toggle checked={q.data?.enabled ?? true} onChange={(enabled) => setting.mutate(enabled)} label="Memory on" />
            {memories.length > 0 && <Button variant="ghost" onClick={() => clear.mutate()}>Clear all</Button>}
          </div>
        </div>
        {q.isLoading ? <Skeleton className="h-16" /> : memories.length ? (
          <div className="divide-y divide-black/5 dark:divide-white/10">
            {memories.map((m) => (
              <div key={m.id} className="flex flex-wrap items-center gap-3 py-3">
                <span className="w-24 shrink-0 text-xs font-semibold uppercase tracking-wide text-ink-mute">{titleCase(m.kind)}</span>
                {editing === m.id ? (
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <Input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Correct remembered fact" />
                    <Button aria-label="Save memory" disabled={save.isPending || draft.trim().length < 2} onClick={() => save.mutate({ id: m.id, value: draft.trim() })}><Check className="h-4 w-4" /></Button>
                    <Button variant="ghost" aria-label="Cancel editing memory" onClick={() => setEditing(null)}><X className="h-4 w-4" /></Button>
                  </div>
                ) : (
                  <>
                    <span className="min-w-0 flex-1 text-sm">{m.value}</span>
                    <span className="text-xs text-ink-mute">{m.source === "explicit" ? "You asked to remember" : "Inferred"}</span>
                    <Button variant="ghost" aria-label={`Correct ${m.kind}`} onClick={() => { setEditing(m.id); setDraft(m.value); }}><Pencil className="h-4 w-4" /></Button>
                    <Button variant="ghost" aria-label={`Forget ${m.kind}`} disabled={forget.isPending} onClick={() => forget.mutate(m.id)}><Trash2 className="h-4 w-4" /></Button>
                  </>
                )}
              </div>
            ))}
          </div>
        ) : <EmptyState title="No saved preferences" hint="The assistant will use the current conversation only." />}
      </CardBody>
    </Card>
  );
}

function HeroStat({ label, value, to }: { label: string; value: number | string; to?: string }) {
  const body = (
    <div className="rounded-2xl bg-white/10 px-2 py-3 backdrop-blur transition hover:bg-white/15">
      <p className="font-display text-2xl font-bold">{value}</p>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-white/60">{label}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-black/5 pb-2 last:border-0 dark:border-white/10">
      <span className="text-ink-mute">{label}</span>
      <span className="min-w-0 truncate text-end font-medium">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------- password
function strength(p: string) {
  let s = 0;
  if (p.length >= 8) s++;
  if (p.length >= 12) s++;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) s++;
  if (/\d/.test(p)) s++;
  if (/[^A-Za-z0-9]/.test(p)) s++;
  return s;
}
function PasswordCard({ hasPassword = true }: { hasPassword?: boolean }) {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const m = useMutate(() => ok(post("/auth/password/set", { new_password: next, current_password: cur || null })), {
    success: "Password updated",
    onSuccess: () => {
      setCur("");
      setNext("");
      setConfirm("");
    },
  });
  const s = strength(next);
  const mismatch = confirm.length > 0 && confirm !== next;
  const valid = next.length >= 8 && next === confirm && (!hasPassword || cur.length > 0);
  const label = ["Too short", "Weak", "Fair", "Good", "Strong", "Excellent"][s];
  return (
    <Card>
      <CardHeader title={hasPassword ? "Change password" : "Set a password"} icon={<Lock className="h-5 w-5" />} />
      <CardBody>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) m.mutate();
          }}
        >
          {hasPassword && (
            <Field label="Current password">
              <Input type={show ? "text" : "password"} autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} icon={<KeyRound className="h-4 w-4" />} />
            </Field>
          )}
          <Field label="New password">
            <div className="relative">
              <Input type={show ? "text" : "password"} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} icon={<Lock className="h-4 w-4" />} className="pe-10" />
              <button type="button" onClick={() => setShow((v) => !v)} className="absolute inset-y-0 end-2 flex items-center px-1 text-ink-mute" aria-label={show ? "Hide password" : "Show password"}>
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>
          {next && (
            <div>
              <Progress value={s} max={5} tone={s <= 1 ? "red" : s <= 2 ? "gold" : "green"} />
              <p className="mt-1 text-[11px] text-ink-mute">{label} · use 12+ characters with numbers and symbols</p>
            </div>
          )}
          <Field label="Confirm new password" error={mismatch ? "Passwords don’t match" : undefined}>
            <Input type={show ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <Button type="submit" className="w-full" loading={m.isPending} disabled={!valid} icon={<ShieldCheck className="h-4 w-4" />}>
            Update password
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------- notifications
function NotificationPrefs({ userId }: { userId: string }) {
  const q = useApi<Prefs>(`/messaging/preferences/${userId}`);
  const [draft, setDraft] = useState<Prefs | null>(null);
  useEffect(() => {
    if (q.data && !("error" in (q.data as object))) setDraft(structuredClone(q.data));
  }, [q.data]);
  const dirty = useMemo(() => !!draft && !!q.data && JSON.stringify(draft) !== JSON.stringify(q.data), [draft, q.data]);
  const save = useMutate(
    () =>
      ok(
        put(`/messaging/preferences/${userId}`, {
          prefs: draft!.notification_prefs,
          quiet_hours: draft!.quiet_hours,
          digest: draft!.digest,
          telegram_opt_in: draft!.telegram_opt_in,
        }),
      ),
    { invalidate: ["/messaging/preferences", "/messaging/telegram"], success: "Notification preferences saved" },
  );
  const toggle = (cat: string, ch: string) =>
    setDraft((d) => {
      if (!d) return d;
      const cur = d.notification_prefs[cat] ?? [];
      const nextList = cur.includes(ch) ? cur.filter((x) => x !== ch) : [...cur, ch];
      return { ...d, notification_prefs: { ...d.notification_prefs, [cat]: nextList } };
    });

  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Notification preferences"
        subtitle="Choose where each kind of alert reaches you"
        icon={<BellRing className="h-5 w-5" />}
        action={
          <Button size="sm" icon={<Save className="h-4 w-4" />} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        }
      />
      <QueryState q={q} skeleton={<Skeleton className="m-5 h-72" />}>
        {() =>
          !draft ? (
            <div className="p-5">
              <EmptyState title="No messaging profile" hint="Your account has no messaging profile yet." />
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-black/5 bg-brand-50/50 text-[11px] font-bold uppercase tracking-wider text-ink-mute dark:border-white/10 dark:bg-white/5">
                      <th className="px-5 py-3 text-start">Category</th>
                      {draft.channels.map((ch) => (
                        <th key={ch} className="px-3 py-3 text-center">
                          <span className="inline-flex items-center gap-1">
                            {CHANNEL_ICON[ch]} {titleCase(ch)}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {draft.categories.map((cat) => (
                      <tr key={cat} className="border-b border-black/5 last:border-0 dark:border-white/5">
                        <td className="px-5 py-3">
                          <p className="font-semibold">{titleCase(cat)}</p>
                          <p className="text-xs text-ink-mute">{CATEGORY_HINT[cat] ?? ""}</p>
                        </td>
                        {draft.channels.map((ch) => {
                          const on = (draft.notification_prefs[cat] ?? []).includes(ch);
                          const disabled = ch === "telegram" && !draft.telegram_opt_in;
                          return (
                            <td key={ch} className={cn("px-3 py-3 text-center", disabled && "opacity-40")}>
                              <div className="inline-flex">
                                <Toggle checked={on && !disabled} onChange={() => !disabled && toggle(cat, ch)} />
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid gap-4 border-t border-black/5 p-5 sm:grid-cols-2 lg:grid-cols-4 dark:border-white/10">
                <Field label="Quiet hours from">
                  <Input type="time" value={draft.quiet_hours.start} onChange={(e) => setDraft({ ...draft, quiet_hours: { ...draft.quiet_hours, start: e.target.value } })} />
                </Field>
                <Field label="Quiet hours until">
                  <Input type="time" value={draft.quiet_hours.end} onChange={(e) => setDraft({ ...draft, quiet_hours: { ...draft.quiet_hours, end: e.target.value } })} />
                </Field>
                <Field label="Digest">
                  <Select
                    value={draft.digest}
                    onChange={(e) => setDraft({ ...draft, digest: e.target.value })}
                    options={[
                      { value: "instant", label: "Instant" },
                      { value: "hourly", label: "Hourly digest" },
                      { value: "daily", label: "Daily digest" },
                    ]}
                  />
                </Field>
                <Field label="Telegram">
                  <div className="pt-2">
                    <Toggle checked={draft.telegram_opt_in} onChange={(v) => setDraft({ ...draft, telegram_opt_in: v })} label={draft.telegram_opt_in ? "Opted in" : "Off"} />
                  </div>
                </Field>
              </div>
              {dirty && (
                <div className="flex items-center justify-between gap-3 border-t border-gold-200 bg-gold-50/70 px-5 py-3 text-sm dark:border-gold-500/20 dark:bg-gold-500/10">
                  <span>You have unsaved changes.</span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setDraft(structuredClone(q.data!))}>
                      Discard
                    </Button>
                    <Button size="sm" variant="gold" loading={save.isPending} onClick={() => save.mutate()}>
                      Save changes
                    </Button>
                  </div>
                </div>
              )}
            </>
          )
        }
      </QueryState>
    </Card>
  );
}

// ---------------------------------------------------------------- telegram
function TelegramCard({ userId }: { userId: string }) {
  const q = useApi<Telegram>(`/messaging/telegram/status/${userId}`);
  return (
    <Card>
      <CardHeader title="Telegram alerts" icon={<Send className="h-5 w-5" />} />
      <CardBody>
        <QueryState q={q} skeleton={<Skeleton className="h-24" />}>
          {(t) => (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <span className={cn("flex h-11 w-11 items-center justify-center rounded-2xl text-white", t.linked ? "bg-sky-500" : "bg-slate-400")}>
                  <Send className="h-5 w-5" />
                </span>
                <div>
                  <p className="font-semibold">{t.linked ? "Linked" : "Not linked"}</p>
                  <p className="text-xs text-ink-mute">
                    @{t.bot} · {t.opt_in ? "opted in" : "opted out"}
                  </p>
                </div>
                <Badge tone={t.linked ? "green" : "gray"} className="ms-auto">
                  {t.linked ? "Active" : "Inactive"}
                </Badge>
              </div>
              {t.chat_id && (
                <p className="text-xs">
                  Chat ID <span className="font-mono">{t.chat_id}</span>
                </p>
              )}
              {!!t.categories.length && (
                <div className="flex flex-wrap gap-1">
                  {t.categories.map((c) => (
                    <Badge key={c} tone="blue">
                      {c}
                    </Badge>
                  ))}
                </div>
              )}
              <p className="rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-800 dark:bg-sky-500/10 dark:text-sky-200">{t.policy}</p>
              {!t.linked && (
                <p className="text-xs text-ink-mute">
                  Open <b>@{t.bot}</b> in Telegram and send <span className="kbd">/start</span> to link this account.
                </p>
              )}
            </div>
          )}
        </QueryState>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------- UI prefs
function UiPrefs() {
  const { theme, lang, favorites, compare, recent, setTheme, setLang } = usePrefs();
  return (
    <Card>
      <CardHeader title="Display & language" icon={<Monitor className="h-5 w-5" />} />
      <CardBody className="space-y-4">
        <Field label="Theme">
          <Segmented<Theme>
            size="sm"
            value={theme}
            onChange={setTheme}
            className="flex w-full [&>button]:flex-1"
            options={[
              { value: "light", label: "Light", icon: <Sun className="h-3.5 w-3.5" /> },
              { value: "dark", label: "Dark", icon: <Moon className="h-3.5 w-3.5" /> },
              { value: "system", label: "System", icon: <Monitor className="h-3.5 w-3.5" /> },
            ]}
          />
        </Field>
        <Field label="Language">
          <Segmented<Lang>
            size="sm"
            value={lang}
            onChange={setLang}
            className="flex w-full [&>button]:flex-1"
            options={[
              { value: "en", label: "English", icon: <Globe className="h-3.5 w-3.5" /> },
              { value: "ur", label: "اردو", icon: <Languages className="h-3.5 w-3.5" /> },
            ]}
          />
        </Field>
        <div className="grid grid-cols-3 gap-2 pt-1">
          <Link to="/favorites" className="rounded-2xl bg-red-50 p-3 text-center transition hover:-translate-y-0.5 dark:bg-red-500/10">
            <Heart className="mx-auto h-5 w-5 text-red-500" />
            <p className="mt-1 font-display text-xl font-bold">{favorites.length}</p>
            <p className="text-[10px] font-semibold uppercase text-ink-mute">Favourites</p>
          </Link>
          <Link to="/compare" className="rounded-2xl bg-gold-50 p-3 text-center transition hover:-translate-y-0.5 dark:bg-gold-500/10">
            <GitCompareArrows className="mx-auto h-5 w-5 text-gold-600" />
            <p className="mt-1 font-display text-xl font-bold">{compare.length}</p>
            <p className="text-[10px] font-semibold uppercase text-ink-mute">Compare</p>
          </Link>
          <div className="rounded-2xl bg-brand-50 p-3 text-center dark:bg-white/5">
            <History className="mx-auto h-5 w-5 text-brand-600" />
            <p className="mt-1 font-display text-xl font-bold">{recent.length}</p>
            <p className="text-[10px] font-semibold uppercase text-ink-mute">Recent</p>
          </div>
        </div>
        <p className="flex items-center gap-1.5 text-[11px] text-ink-mute">
          <AtSign className="h-3 w-3" /> Saved on this device. <MessageSquare className="h-3 w-3" /> Message alerts follow the table on the left.
        </p>
      </CardBody>
    </Card>
  );
}
