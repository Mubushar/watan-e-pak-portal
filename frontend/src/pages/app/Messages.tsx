import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  AtSign,
  Check,
  CheckCheck,
  ClipboardList,
  CornerDownRight,
  Hash,
  Home,
  Info,
  ListTodo,
  Loader2,
  MessageSquarePlus,
  MessagesSquare,
  MoreHorizontal,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Radio,
  Search,
  Send,
  SmilePlus,
  Sparkles,
  Trash2,
  Users,
  WifiOff,
  X,
} from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { del, post, put } from "@/lib/api";
import { date, timeAgo, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import {
  Avatar,
  Badge,
  Button,
  Drawer,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  QueryState,
  Segmented,
  Select,
  Skeleton,
  Spinner,
  StatusBadge,
  Textarea,
} from "@/components/ui";
import { ok } from "@/components/collab/kit";
import { useLiveConversation, type LiveMode } from "@/components/collab/useLiveConversation";

// ---------------------------------------------------------------- types
interface Member {
  user_id: string;
  name: string;
  role: string;
  muted?: boolean;
  presence?: string;
}
interface Conversation {
  id: string;
  kind: "channel" | "direct" | "property" | "group" | string;
  title: string;
  topic?: string | null;
  channel_key?: string | null;
  property_id?: string | null;
  member_count: number;
  members: Member[];
  unread: number;
  my_role?: string;
  pinned_message_ids?: string[];
  last_message_at?: string | null;
  last_message?: { id: string; author: string; body: string; type: string; created_at: string; seq: number } | null;
}
interface Message {
  id: string;
  conversation_id: string;
  seq: number;
  author_id: string | null;
  author_name: string;
  body: string;
  type: string;
  parent_id: string | null;
  mentions: string[];
  pinned: boolean;
  reactions: Record<string, string[]>;
  edited_at: string | null;
  deleted: boolean;
  created_at: string;
  reply_count: number;
  action_id?: string | null;
  read_by?: string[];
}
interface Profile {
  user_id: string;
  display_name: string;
  handle: string;
  role: string;
  title?: string;
  presence: string;
}
interface MsgAction {
  id: string;
  kind: string;
  title: string;
  detail?: string | null;
  owner_id?: string | null;
  owner_name?: string | null;
  due_on?: string | null;
  status: string;
  overdue?: boolean;
  message_id?: string | null;
}

const QUICK_REACTIONS = ["👍", "❤️", "😂", "🎉", "✅", "👀", "🙏"];
const FILTERS = [
  { value: "all", label: "All" },
  { value: "unread", label: "Unread" },
  { value: "channel", label: "Channels" },
  { value: "direct", label: "Direct" },
  { value: "property", label: "Property" },
] as const;
type Filter = (typeof FILTERS)[number]["value"];

const UUIDISH = /^[0-9a-f]{8}-[0-9a-f-]{20,}$/i;

function convTitle(c: Conversation, me?: string) {
  if (c.kind === "direct") {
    const other = c.members.find((m) => m.user_id !== me);
    return other?.name ?? c.title;
  }
  if (c.kind === "property") {
    const rest = c.title.replace(/^Property\s+/i, "");
    return UUIDISH.test(rest) ? `Property · ${rest.slice(0, 8)}` : c.title;
  }
  return c.title;
}

function useIsWide(query = "(min-width: 1280px)") {
  const [wide, setWide] = useState(() => (typeof window !== "undefined" ? window.matchMedia(query).matches : true));
  useEffect(() => {
    const mq = window.matchMedia(query);
    const h = () => setWide(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [query]);
  return wide;
}

/** Invalidate every cached /messaging query. */
function useRefreshMessaging() {
  const qc = useQueryClient();
  return useCallback(
    () => qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && (q.queryKey[0] as string).startsWith("/messaging") }),
    [qc],
  );
}

// ---------------------------------------------------------------- page
export default function Messages() {
  const user = useAuth((s) => s.user);
  const me = user?.id ?? "";
  const [params, setParams] = useSearchParams();
  const selected = params.get("c");
  const select = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("c", id);
    else next.delete("c");
    setParams(next, { replace: false });
  };
  const [panel, setPanel] = useState<"details" | "actions" | "ai" | "thread" | null>(null);
  const [threadOf, setThreadOf] = useState<Message | null>(null);
  const [actionFrom, setActionFrom] = useState<{ message?: Message; title?: string } | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const wide = useIsWide();
  const refresh = useRefreshMessaging();

  const live = useLiveConversation(selected, me, () => refresh());
  const polling = live === "polling" ? 10_000 : false;

  const convs = useApi<{ count: number; unread_total: number; conversations: Conversation[] }>(me ? "/messaging/conversations" : null, { user_id: me }, { refetchInterval: 30_000 });
  const profiles = useApi<{ profiles: Profile[] }>("/messaging/profiles", undefined, { staleTime: 5 * 60_000 });
  const conv = convs.data?.conversations.find((c) => c.id === selected) ?? null;

  useEffect(() => {
    setThreadOf(null);
    setPanel((p) => (p === "thread" ? null : p));
  }, [selected]);

  const openThread = (m: Message) => {
    setThreadOf(m);
    setPanel("thread");
  };

  if (!user) return <EmptyState title="Sign in to use messages" />;

  const panelBody = conv && panel && (
    <RightPanel
      conv={conv}
      me={me}
      tab={panel}
      setTab={setPanel}
      threadOf={threadOf}
      profiles={profiles.data?.profiles ?? []}
      onClose={() => setPanel(null)}
      onMakeAction={(title, message) => setActionFrom({ title, message })}
    />
  );

  return (
    <div>
      <PageHeader
        title="Messages"
        subtitle="Team channels, direct messages and property threads — live."
        crumbs={[{ label: "Dashboard", to: "/app" }, { label: "Messages" }]}
        className="mb-4"
        actions={
          <>
            <LiveBadge mode={selected ? live : "off"} />
            <Button icon={<MessageSquarePlus className="h-4 w-4" />} onClick={() => setNewOpen(true)}>
              New message
            </Button>
          </>
        }
      />
      <div className="card flex h-[calc(100dvh-14rem)] min-h-[520px] overflow-hidden p-0">
        {/* left */}
        <aside className={cn("w-full shrink-0 flex-col border-e border-black/5 dark:border-white/10 md:flex md:w-80", selected ? "hidden" : "flex")}>
          <ConversationList q={convs} me={me} selected={selected} onSelect={select} onNew={() => setNewOpen(true)} />
        </aside>

        {/* center */}
        <section className={cn("min-w-0 flex-1 flex-col", selected ? "flex" : "hidden md:flex")}>
          {selected && conv ? (
            <ChatPane
              key={conv.id}
              conv={conv}
              me={me}
              profiles={profiles.data?.profiles ?? []}
              polling={polling}
              live={live}
              onBack={() => select(null)}
              panelOpen={!!panel}
              onTogglePanel={() => setPanel((p) => (p ? null : "details"))}
              onOpenPanel={setPanel}
              onThread={openThread}
              onMakeAction={(m) => setActionFrom({ message: m, title: m.body.slice(0, 120) })}
            />
          ) : selected && convs.isLoading ? (
            <div className="flex flex-1 items-center justify-center">
              <Spinner />
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center p-6">
              <div className="max-w-sm text-center">
                <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-3xl bg-brand-gradient text-white shadow-glow">
                  <MessagesSquare className="h-9 w-9" />
                </div>
                <h3 className="mt-5 font-display text-xl font-semibold">{selected ? "Conversation not found" : "Pick a conversation"}</h3>
                <p className="mt-2 text-sm text-ink-mute">Choose a channel, a direct message or a property thread from the list — or start a new conversation.</p>
                <Button className="mt-5" icon={<Plus className="h-4 w-4" />} onClick={() => setNewOpen(true)}>
                  New message
                </Button>
              </div>
            </div>
          )}
        </section>

        {/* right */}
        {wide && panelBody && <aside className="flex w-[340px] shrink-0 flex-col border-s border-black/5 dark:border-white/10">{panelBody}</aside>}
      </div>
      {!wide && (
        <Drawer open={!!panelBody} onClose={() => setPanel(null)} title={conv ? convTitle(conv, me) : ""} width="max-w-sm">
          <div className="flex h-full flex-col">{panelBody}</div>
        </Drawer>
      )}

      <NewMessageModal open={newOpen} onClose={() => setNewOpen(false)} me={me} profiles={profiles.data?.profiles ?? []} onOpen={(id) => select(id)} />
      {actionFrom && conv && <ActionModal conv={conv} me={me} message={actionFrom.message} initialTitle={actionFrom.title} onClose={() => setActionFrom(null)} />}
    </div>
  );
}

function LiveBadge({ mode }: { mode: LiveMode }) {
  if (mode === "off") return null;
  if (mode === "live")
    return (
      <span className="chip bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-500/15 dark:text-emerald-200">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
        </span>
        Live
      </span>
    );
  if (mode === "polling")
    return (
      <span className="chip bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20 dark:bg-amber-500/15 dark:text-amber-200" title="Socket unavailable — refreshing every 10 s">
        <WifiOff className="h-3 w-3" /> Polling
      </span>
    );
  return (
    <span className="chip bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300">
      <Loader2 className="h-3 w-3 animate-spin" /> Connecting
    </span>
  );
}

// ---------------------------------------------------------------- list
function ConvIcon({ c, me, size = 40 }: { c: Conversation; me: string; size?: number }) {
  if (c.kind === "direct") {
    const other = c.members.find((m) => m.user_id !== me);
    return <Avatar name={other?.name ?? c.title} size={size} />;
  }
  const isProp = c.kind === "property";
  return (
    <span
      className={cn("flex shrink-0 items-center justify-center rounded-xl text-white", isProp ? "bg-gold-gradient !text-brand-950" : "bg-brand-gradient")}
      style={{ width: size, height: size }}
    >
      {isProp ? <Home className="h-[45%] w-[45%]" /> : c.kind === "channel" ? <Hash className="h-[45%] w-[45%]" /> : <Users className="h-[45%] w-[45%]" />}
    </span>
  );
}

function ConversationList({
  q,
  me,
  selected,
  onSelect,
  onNew,
}: {
  q: ReturnType<typeof useApi<{ count: number; unread_total: number; conversations: Conversation[] }>>;
  me: string;
  selected: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const list = useMemo(() => {
    let rows = [...(q.data?.conversations ?? [])];
    if (filter === "unread") rows = rows.filter((c) => c.unread > 0);
    else if (filter !== "all") rows = rows.filter((c) => c.kind === filter);
    const s = search.trim().toLowerCase();
    if (s) rows = rows.filter((c) => [convTitle(c, me), c.topic, c.last_message?.body].some((x) => (x ?? "").toLowerCase().includes(s)));
    return rows.sort((a, b) => (b.last_message_at ?? "").localeCompare(a.last_message_at ?? ""));
  }, [q.data, filter, search, me]);
  const counts = useMemo(() => {
    const all = q.data?.conversations ?? [];
    return {
      all: all.length,
      unread: all.filter((c) => c.unread > 0).length,
      channel: all.filter((c) => c.kind === "channel").length,
      direct: all.filter((c) => c.kind === "direct").length,
      property: all.filter((c) => c.kind === "property").length,
    } as Record<Filter, number>;
  }, [q.data]);

  return (
    <>
      <div className="space-y-3 border-b border-black/5 p-3 dark:border-white/10">
        <div className="flex items-center justify-between gap-2">
          <p className="font-display text-base font-semibold">
            Inbox {!!q.data?.unread_total && <span className="ms-1 rounded-full bg-gold-400 px-2 py-0.5 text-[11px] font-bold text-brand-950">{q.data.unread_total}</span>}
          </p>
          <button onClick={onNew} className="btn btn-soft btn-icon h-8 w-8" aria-label="New message">
            <MessageSquarePlus className="h-4 w-4" />
          </button>
        </div>
        <Input icon={<Search className="h-4 w-4" />} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search conversations" className="py-2" />
        <div className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto px-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold transition",
                filter === f.value ? "bg-brand-700 text-white" : "bg-black/5 text-ink-soft hover:bg-brand-50 dark:bg-white/5 dark:text-slate-300",
              )}
            >
              {f.label}
              {counts[f.value] > 0 && <span className="ms-1 opacity-70">{counts[f.value]}</span>}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        <QueryState
          q={q}
          skeleton={
            <div className="space-y-2 p-1">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          }
        >
          {() =>
            list.length === 0 ? (
              <p className="p-6 text-center text-sm text-ink-mute">No conversations match.</p>
            ) : (
              <ul className="space-y-0.5">
                {list.map((c) => {
                  const active = c.id === selected;
                  return (
                    <li key={c.id}>
                      <button
                        onClick={() => onSelect(c.id)}
                        className={cn(
                          "relative flex w-full items-center gap-3 rounded-2xl p-2.5 text-start transition",
                          active ? "bg-brand-50 ring-1 ring-brand-600/15 dark:bg-white/10" : "hover:bg-black/[.03] dark:hover:bg-white/5",
                        )}
                      >
                        {active && <span className="absolute inset-y-3 start-0 w-1 rounded-full bg-gold-400" />}
                        <ConvIcon c={c} me={me} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className={cn("truncate text-sm", c.unread ? "font-bold text-ink dark:text-white" : "font-semibold text-ink-soft dark:text-slate-200")}>{convTitle(c, me)}</p>
                            <span className="shrink-0 text-[10px] text-ink-mute">{timeAgo(c.last_message_at)}</span>
                          </div>
                          <div className="flex items-center justify-between gap-2">
                            <p className={cn("truncate text-xs", c.unread ? "text-ink-soft dark:text-slate-300" : "text-ink-mute")}>
                              {c.last_message ? (
                                <>
                                  {c.last_message.type !== "system" && <span className="font-medium">{c.last_message.author.split(" ")[0]}: </span>}
                                  {c.last_message.body}
                                </>
                              ) : (
                                c.topic ?? "No messages yet"
                              )}
                            </p>
                            {c.unread > 0 && (
                              <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-gold-400 px-1.5 text-[10px] font-bold text-brand-950">
                                {c.unread}
                              </motion.span>
                            )}
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )
          }
        </QueryState>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- chat
function ChatPane({
  conv,
  me,
  profiles,
  polling,
  live,
  onBack,
  panelOpen,
  onTogglePanel,
  onOpenPanel,
  onThread,
  onMakeAction,
}: {
  conv: Conversation;
  me: string;
  profiles: Profile[];
  polling: number | false;
  live: LiveMode;
  onBack: () => void;
  panelOpen: boolean;
  onTogglePanel: () => void;
  onOpenPanel: (p: "details" | "actions" | "ai") => void;
  onThread: (m: Message) => void;
  onMakeAction: (m: Message) => void;
}) {
  const path = `/messaging/conversations/${conv.id}/messages`;
  const q = useApi<{ count: number; total: number; messages: Message[] }>(path, { user_id: me, limit: 200 }, { refetchInterval: polling });
  const refresh = useRefreshMessaging();
  const scroller = useRef<HTMLDivElement>(null);
  const lastRead = useRef(0);
  const msgs = useMemo(() => (q.data?.messages ?? []).filter((m) => !m.parent_id), [q.data]);
  const lastSeq = q.data?.messages.length ? Math.max(...q.data.messages.map((m) => m.seq)) : 0;

  // mark read whenever new messages arrive
  useEffect(() => {
    if (!lastSeq || lastSeq <= lastRead.current) return;
    lastRead.current = lastSeq;
    post(`/messaging/conversations/${conv.id}/read`, { user_id: me, up_to_seq: lastSeq })
      .then(() => refresh())
      .catch(() => {});
  }, [lastSeq, conv.id, me, refresh]);

  // stick to bottom on new messages
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: lastRead.current ? "smooth" : "auto" });
  }, [msgs.length]);

  const handles = useMemo(() => {
    const m: Record<string, Profile> = {};
    profiles.forEach((p) => (m[p.user_id] = p));
    return m;
  }, [profiles]);
  const myHandle = handles[me]?.handle;
  const memberProfiles = conv.members.map((m) => ({ ...m, handle: handles[m.user_id]?.handle ?? m.name.toLowerCase().replace(/\s+/g, "."), presence: handles[m.user_id]?.presence }));
  const other = conv.kind === "direct" ? memberProfiles.find((m) => m.user_id !== me) : undefined;

  return (
    <>
      {/* header */}
      <div className="flex items-center gap-3 border-b border-black/5 px-3 py-2.5 dark:border-white/10 sm:px-4">
        <button onClick={onBack} className="btn btn-ghost btn-icon h-9 w-9 md:hidden" aria-label="Back">
          <ArrowLeft className="h-5 w-5 rtl:rotate-180" />
        </button>
        {conv.kind === "direct" ? <Avatar name={other?.name} size={38} online={other?.presence === "online"} /> : <ConvIcon c={conv} me={me} size={38} />}
        <div className="min-w-0 flex-1">
          <p className="truncate font-display font-semibold">
            {conv.kind === "channel" && <span className="text-ink-mute">#</span>}
            {convTitle(conv, me)}
          </p>
          <p className="truncate text-xs text-ink-mute">
            {conv.kind === "direct" ? (other?.presence === "online" ? "Online" : "Offline") : `${conv.member_count} members`}
            {conv.topic ? ` · ${conv.topic}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => onOpenPanel("ai")} className="btn btn-ghost btn-sm hidden sm:inline-flex" title="AI summary">
            <Sparkles className="h-4 w-4 text-gold-500" /> <span className="hidden lg:inline">Summarise</span>
          </button>
          <button onClick={() => onOpenPanel("actions")} className="btn btn-ghost btn-icon h-9 w-9" title="Actions">
            <ListTodo className="h-[18px] w-[18px]" />
          </button>
          <button onClick={onTogglePanel} className="btn btn-ghost btn-icon h-9 w-9" title="Details">
            {panelOpen ? <PanelRightClose className="h-[18px] w-[18px] rtl:rotate-180" /> : <PanelRightOpen className="h-[18px] w-[18px] rtl:rotate-180" />}
          </button>
        </div>
      </div>

      {/* messages */}
      <div ref={scroller} className="flex-1 overflow-y-auto bg-[radial-gradient(circle_at_20%_0%,rgba(20,111,69,.06),transparent_40%),radial-gradient(circle_at_100%_100%,rgba(201,154,34,.06),transparent_40%)] px-3 py-4 sm:px-5">
        <QueryState q={q} skeleton={<ChatSkeleton />}>
          {() =>
            msgs.length === 0 ? (
              <EmptyState title="Say salaam 👋" hint="This conversation has no messages yet." />
            ) : (
              <MessageList msgs={msgs} me={me} myHandle={myHandle} onThread={onThread} onMakeAction={onMakeAction} />
            )
          }
        </QueryState>
      </div>

      <Composer conv={conv} me={me} members={memberProfiles} />
      {live === "polling" && <p className="bg-amber-50 px-4 py-1 text-center text-[11px] text-amber-700 dark:bg-amber-500/10 dark:text-amber-200">Live connection unavailable — refreshing every 10 seconds.</p>}
    </>
  );
}

function ChatSkeleton() {
  return (
    <div className="space-y-4">
      {["w-3/5", "w-2/5", "w-2/3", "w-1/3", "w-1/2"].map((w, i) => (
        <div key={i} className={cn("flex", i % 2 ? "justify-end" : "justify-start")}>
          <Skeleton className={cn("h-14 rounded-2xl", w)} />
        </div>
      ))}
    </div>
  );
}

function dayLabel(iso: string) {
  const d = new Date(iso);
  const t = new Date();
  const y = new Date();
  y.setDate(t.getDate() - 1);
  if (d.toDateString() === t.toDateString()) return "Today";
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return date(iso, { weekday: "long", day: "numeric", month: "short", year: "numeric" });
}

function MessageList({ msgs, me, myHandle, onThread, onMakeAction }: { msgs: Message[]; me: string; myHandle?: string; onThread: (m: Message) => void; onMakeAction: (m: Message) => void }) {
  return (
    <div className="space-y-1">
      {msgs.map((m, i) => {
        const prev = msgs[i - 1];
        const newDay = !prev || new Date(prev.created_at).toDateString() !== new Date(m.created_at).toDateString();
        const grouped = !!prev && !newDay && prev.author_id === m.author_id && prev.type !== "system" && new Date(m.created_at).getTime() - new Date(prev.created_at).getTime() < 5 * 60_000;
        return (
          <Fragment key={m.id}>
            {newDay && (
              <div className="sticky top-0 z-10 flex justify-center py-2">
                <span className="glass rounded-full px-3 py-1 text-[11px] font-semibold text-ink-mute shadow-sm">{dayLabel(m.created_at)}</span>
              </div>
            )}
            <Bubble m={m} me={me} myHandle={myHandle} grouped={grouped} onThread={onThread} onMakeAction={onMakeAction} />
          </Fragment>
        );
      })}
    </div>
  );
}

function RichBody({ text, myHandle }: { text: string; myHandle?: string }) {
  const parts = text.split(/(@[A-Za-z0-9_][\w.-]*[A-Za-z0-9_])/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("@") && p.length > 1 ? (
          <span key={i} className={cn("rounded-md px-1 font-semibold", myHandle && p.slice(1) === myHandle ? "bg-gold-300/60 text-brand-950" : "bg-sky-500/15 text-sky-700 dark:text-sky-300")}>
            {p}
          </span>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

function Bubble({ m, me, myHandle, grouped, onThread, onMakeAction, compact }: { m: Message; me: string; myHandle?: string; grouped?: boolean; onThread?: (m: Message) => void; onMakeAction?: (m: Message) => void; compact?: boolean }) {
  const own = m.author_id === me;
  const mentioned = m.mentions?.includes(me);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.body);
  const [menu, setMenu] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const inv = ["/messaging"];
  const react = useMutate((emoji: string) => ok(post(`/messaging/messages/${m.id}/react`, { user_id: me, emoji })), { invalidate: inv });
  const pin = useMutate(() => ok(post(`/messaging/messages/${m.id}/pin`, { user_id: me, pinned: !m.pinned })), { invalidate: inv, success: m.pinned ? "Unpinned" : "Pinned to conversation" });
  const edit = useMutate(() => ok(put(`/messaging/messages/${m.id}`, { user_id: me, body: draft })), { invalidate: inv, success: "Message edited", onSuccess: () => setEditing(false) });
  const remove = useMutate(() => ok(del(`/messaging/messages/${m.id}`, { user_id: me })), { invalidate: inv, success: "Message deleted", onSuccess: () => setConfirmDel(false) });

  if (m.type === "system")
    return (
      <div className="flex justify-center py-2">
        <span className="rounded-full bg-brand-50 px-3 py-1 text-xs text-brand-800 dark:bg-white/5 dark:text-brand-100">{m.body}</span>
      </div>
    );

  const reactions = Object.entries(m.reactions ?? {}).filter(([, u]) => u.length);
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className={cn("group flex gap-2.5", own ? "flex-row-reverse" : "flex-row", grouped ? "mt-0.5" : "mt-3")}>
      <div className="w-8 shrink-0">{!grouped && !own && <Avatar name={m.author_name} size={32} />}</div>
      <div className={cn("flex min-w-0 max-w-[85%] flex-col sm:max-w-[70%]", own ? "items-end" : "items-start")}>
        {!grouped && (
          <div className={cn("mb-1 flex items-baseline gap-2 px-1 text-xs", own && "flex-row-reverse")}>
            <span className="font-semibold text-ink dark:text-white">{own ? "You" : m.author_name}</span>
            <span className="text-ink-mute">{new Date(m.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
          </div>
        )}
        <div className={cn("relative flex items-center gap-1", own ? "flex-row-reverse" : "flex-row")}>
          <div
            className={cn(
              "relative rounded-2xl px-3.5 py-2 text-sm leading-relaxed shadow-sm",
              own
                ? "rounded-se-md bg-gradient-to-br from-brand-700 to-brand-600 text-white"
                : "rounded-ss-md border border-black/5 bg-white text-ink dark:border-white/10 dark:bg-white/[.06] dark:text-slate-100",
              mentioned && !own && "ring-2 ring-gold-400/70",
              m.pinned && "outline outline-1 outline-offset-2 outline-gold-400/60",
            )}
          >
            {m.pinned && <Pin className={cn("absolute -top-2 h-3.5 w-3.5 rotate-45 text-gold-500", own ? "-start-2" : "-end-2")} />}
            {editing ? (
              <div className="w-64 max-w-full space-y-2">
                <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3} className="min-h-0 text-ink" autoFocus />
                <div className="flex justify-end gap-1.5">
                  <Button size="sm" variant="ghost" className={own ? "text-white hover:bg-white/10" : ""} onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                  <Button size="sm" variant="gold" loading={edit.isPending} disabled={!draft.trim()} onClick={() => edit.mutate()}>
                    Save
                  </Button>
                </div>
              </div>
            ) : (
              <p className="whitespace-pre-wrap break-words">
                <RichBody text={m.body} myHandle={myHandle} />
                {m.edited_at && <span className={cn("ms-1.5 text-[10px]", own ? "text-white/60" : "text-ink-mute")}>(edited)</span>}
              </p>
            )}
            {own && !editing && (
              <span className="mt-0.5 flex justify-end text-white/60" title={m.read_by?.length ? `Read by ${m.read_by.length}` : "Sent"}>
                {m.read_by?.length ? <CheckCheck className="h-3.5 w-3.5 text-gold-200" /> : <Check className="h-3.5 w-3.5" />}
              </span>
            )}
          </div>
          {/* hover toolbar */}
          {!compact && !editing && (
            <div className={cn("relative flex items-center gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100", menu && "opacity-100")}>
              <ToolbarBtn title="React" onClick={() => setMenu((v) => !v)}>
                <SmilePlus className="h-4 w-4" />
              </ToolbarBtn>
              {onThread && (
                <ToolbarBtn title="Reply in thread" onClick={() => onThread(m)}>
                  <CornerDownRight className="h-4 w-4" />
                </ToolbarBtn>
              )}
              <MoreMenu
                own={own}
                pinned={m.pinned}
                onPin={() => pin.mutate()}
                onEdit={() => {
                  setDraft(m.body);
                  setEditing(true);
                }}
                onDelete={() => setConfirmDel(true)}
                onAction={onMakeAction ? () => onMakeAction(m) : undefined}
              />
              <AnimatePresence>
                {menu && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9, y: 4 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    className={cn("absolute bottom-full z-20 mb-1 flex gap-0.5 rounded-full border border-black/5 bg-white p-1 shadow-soft dark:border-white/10 dark:bg-[#12271c]", own ? "end-0" : "start-0")}
                  >
                    {QUICK_REACTIONS.map((e) => (
                      <button
                        key={e}
                        onClick={() => {
                          react.mutate(e);
                          setMenu(false);
                        }}
                        className="flex h-8 w-8 items-center justify-center rounded-full text-lg transition hover:scale-125 hover:bg-black/5"
                      >
                        {e}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </div>
        {(reactions.length > 0 || m.reply_count > 0) && (
          <div className={cn("mt-1 flex flex-wrap items-center gap-1", own && "justify-end")}>
            {reactions.map(([emoji, users]) => {
              const mine = users.includes(me);
              return (
                <button
                  key={emoji}
                  onClick={() => react.mutate(emoji)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition hover:scale-105",
                    mine ? "border-brand-500 bg-brand-50 text-brand-800 dark:border-brand-400 dark:bg-brand-500/20 dark:text-brand-100" : "border-black/10 bg-white dark:border-white/10 dark:bg-white/5",
                  )}
                >
                  <span>{emoji}</span>
                  <span className="font-semibold">{users.length}</span>
                </button>
              );
            })}
            {m.reply_count > 0 && onThread && (
              <button onClick={() => onThread(m)} className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold text-brand-700 hover:bg-brand-50 dark:text-gold-300 dark:hover:bg-white/5">
                <CornerDownRight className="h-3 w-3" /> {m.reply_count} repl{m.reply_count === 1 ? "y" : "ies"}
              </button>
            )}
          </div>
        )}
      </div>
      <Modal
        open={confirmDel}
        onClose={() => setConfirmDel(false)}
        size="sm"
        title="Delete message?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDel(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-mute">The message will be removed for everyone in this conversation.</p>
      </Modal>
    </motion.div>
  );
}

function ToolbarBtn({ title, onClick, children }: { title: string; onClick: () => void; children: ReactNode }) {
  return (
    <button title={title} aria-label={title} onClick={onClick} className="flex h-7 w-7 items-center justify-center rounded-lg text-ink-mute transition hover:bg-black/5 hover:text-brand-700 dark:hover:bg-white/10 dark:hover:text-white">
      {children}
    </button>
  );
}

function MoreMenu({ own, pinned, onPin, onEdit, onDelete, onAction }: { own: boolean; pinned: boolean; onPin: () => void; onEdit: () => void; onDelete: () => void; onAction?: () => void }) {
  const [open, setOpen] = useState(false);
  const item = "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-sm hover:bg-black/5 dark:hover:bg-white/10";
  const run = (fn: () => void) => () => {
    setOpen(false);
    fn();
  };
  return (
    <div className="relative">
      <ToolbarBtn title="More" onClick={() => setOpen((v) => !v)}>
        <MoreHorizontal className="h-4 w-4" />
      </ToolbarBtn>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className={cn("absolute top-full z-30 mt-1 w-48 rounded-xl border border-black/5 bg-white p-1 shadow-soft dark:border-white/10 dark:bg-[#12271c]", own ? "end-0" : "start-0")}>
              <button className={item} onClick={run(onPin)}>
                {pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />} {pinned ? "Unpin" : "Pin message"}
              </button>
              {onAction && (
                <button className={item} onClick={run(onAction)}>
                  <ClipboardList className="h-4 w-4" /> Turn into action
                </button>
              )}
              {own && (
                <button className={item} onClick={run(onEdit)}>
                  <Pencil className="h-4 w-4" /> Edit
                </button>
              )}
              {own && (
                <button className={cn(item, "text-red-600")} onClick={run(onDelete)}>
                  <Trash2 className="h-4 w-4" /> Delete
                </button>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------- composer
function Composer({ conv, me, members, parentId, placeholder }: { conv: Conversation; me: string; members: (Member & { handle: string })[]; parentId?: string; placeholder?: string }) {
  const [text, setText] = useState("");
  const [caret, setCaret] = useState(0);
  const ref = useRef<HTMLTextAreaElement>(null);
  const send = useMutate(
    (body: string) => ok(post(`/messaging/conversations/${conv.id}/messages`, { author_id: me, body, message_type: "text", parent_id: parentId ?? null })),
    { invalidate: ["/messaging"], onSuccess: () => setText("") },
  );
  // @mention autocomplete
  const before = text.slice(0, caret);
  const at = before.match(/@([\w.-]*)$/);
  const suggestions = at ? members.filter((m) => m.user_id !== me && (m.handle.toLowerCase().includes(at[1]!.toLowerCase()) || m.name.toLowerCase().includes(at[1]!.toLowerCase()))).slice(0, 6) : [];
  const insert = (handle: string) => {
    if (!at) return;
    const start = caret - at[0].length;
    const next = `${text.slice(0, start)}@${handle} ${text.slice(caret)}`;
    setText(next);
    const pos = start + handle.length + 2;
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(pos, pos);
      setCaret(pos);
    });
  };
  const submit = () => {
    const body = text.trim();
    if (body && !send.isPending) send.mutate(body);
  };
  // auto-grow
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(160, el.scrollHeight)}px`;
  }, [text]);

  return (
    <div className="relative border-t border-black/5 p-3 dark:border-white/10">
      <AnimatePresence>
        {suggestions.length > 0 && (
          <motion.ul initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="absolute bottom-full start-3 z-20 mb-2 w-64 overflow-hidden rounded-xl border border-black/5 bg-white p-1 shadow-soft dark:border-white/10 dark:bg-[#12271c]">
            {suggestions.map((s) => (
              <li key={s.user_id}>
                <button onMouseDown={(e) => e.preventDefault()} onClick={() => insert(s.handle)} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-sm hover:bg-brand-50 dark:hover:bg-white/10">
                  <Avatar name={s.name} size={24} />
                  <span className="min-w-0 flex-1 truncate font-medium">{s.name}</span>
                  <span className="text-xs text-ink-mute">@{s.handle}</span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
      <div className="flex items-end gap-2 rounded-2xl border border-black/10 bg-white p-1.5 shadow-sm transition focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-500/10 dark:border-white/10 dark:bg-white/5">
        <button
          type="button"
          onClick={() => {
            const pos = ref.current?.selectionStart ?? text.length;
            const next = `${text.slice(0, pos)}@${text.slice(pos)}`;
            setText(next);
            requestAnimationFrame(() => {
              ref.current?.focus();
              ref.current?.setSelectionRange(pos + 1, pos + 1);
              setCaret(pos + 1);
            });
          }}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-ink-mute hover:bg-black/5 hover:text-brand-700 dark:hover:bg-white/10"
          title="Mention someone"
        >
          <AtSign className="h-[18px] w-[18px]" />
        </button>
        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setCaret(e.target.selectionStart);
          }}
          onKeyUp={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart)}
          onClick={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (suggestions.length) insert(suggestions[0]!.handle);
              else submit();
            }
          }}
          placeholder={placeholder ?? `Message ${conv.kind === "channel" ? "#" : ""}${conv.title}`}
          className="max-h-40 min-h-[36px] flex-1 resize-none bg-transparent px-1 py-2 text-sm outline-none placeholder:text-ink-mute"
        />
        <button
          onClick={submit}
          disabled={!text.trim() || send.isPending}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-700 text-white shadow-soft transition hover:bg-brand-800 disabled:opacity-40"
          aria-label="Send"
        >
          {send.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4 rtl:-scale-x-100" />}
        </button>
      </div>
      <p className="mt-1 hidden px-2 text-[10px] text-ink-mute sm:block">
        <b>Enter</b> to send · <b>Shift + Enter</b> for a new line · <b>@</b> to mention
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- right panel
function RightPanel({
  conv,
  me,
  tab,
  setTab,
  threadOf,
  profiles,
  onClose,
  onMakeAction,
}: {
  conv: Conversation;
  me: string;
  tab: "details" | "actions" | "ai" | "thread";
  setTab: (t: "details" | "actions" | "ai" | "thread" | null) => void;
  threadOf: Message | null;
  profiles: Profile[];
  onClose: () => void;
  onMakeAction: (title: string, message?: Message) => void;
}) {
  const members = conv.members.map((m) => ({ ...m, handle: profiles.find((p) => p.user_id === m.user_id)?.handle ?? m.name.toLowerCase().replace(/\s+/g, ".") }));
  if (tab === "thread" && threadOf)
    return <ThreadView root={threadOf} conv={conv} me={me} members={members} myHandle={profiles.find((p) => p.user_id === me)?.handle} onClose={() => setTab("details")} />;
  return (
    <>
      <div className="flex items-center gap-2 border-b border-black/5 p-3 dark:border-white/10">
        <Segmented
          size="sm"
          value={tab === "thread" ? "details" : tab}
          onChange={(v) => setTab(v)}
          options={[
            { value: "details", label: "Details", icon: <Info className="h-3.5 w-3.5" /> },
            { value: "actions", label: "Actions", icon: <ListTodo className="h-3.5 w-3.5" /> },
            { value: "ai", label: "AI", icon: <Sparkles className="h-3.5 w-3.5" /> },
          ]}
          className="flex-1"
        />
        <button onClick={onClose} className="btn btn-ghost btn-icon hidden h-8 w-8 xl:inline-flex" aria-label="Close panel">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {tab === "details" && <DetailsTab conv={conv} me={me} profiles={profiles} />}
        {tab === "actions" && <ActionsTab conv={conv} me={me} onNew={() => onMakeAction("")} />}
        {tab === "ai" && <AiTab conv={conv} me={me} onMakeAction={onMakeAction} />}
      </div>
    </>
  );
}

function DetailsTab({ conv, me, profiles }: { conv: Conversation; me: string; profiles: Profile[] }) {
  const ctx = useApi<{ pinned: string[]; open_actions: string[]; attachments: unknown[]; unread: number; retention_days: number; property_id?: string | null; channel_key?: string | null }>(`/messaging/conversations/${conv.id}/context`, { user_id: me });
  const members = useApi<{ count: number; members: Member[] }>(`/messaging/conversations/${conv.id}/members`, { user_id: me });
  const msgs = useApi<{ messages: Message[] }>(`/messaging/conversations/${conv.id}/messages`, { user_id: me, limit: 200 });
  const pinned = (msgs.data?.messages ?? []).filter((m) => m.pinned);
  return (
    <div className="space-y-5">
      <div className="text-center">
        <div className="flex justify-center">
          <ConvIcon c={conv} me={me} size={64} />
        </div>
        <p className="mt-2 font-display text-lg font-semibold">{convTitle(conv, me)}</p>
        {conv.topic && <p className="text-sm text-ink-mute">{conv.topic}</p>}
        <div className="mt-2 flex flex-wrap justify-center gap-1.5">
          <Badge tone="gray">{titleCase(conv.kind)}</Badge>
          {conv.my_role && <Badge tone="green">{titleCase(conv.my_role)}</Badge>}
          {ctx.data && <Badge tone="blue">Retention {ctx.data.retention_days} d</Badge>}
        </div>
      </div>
      <div>
        <p className="label flex items-center gap-1.5">
          <Pin className="h-3.5 w-3.5" /> Pinned ({pinned.length})
        </p>
        {pinned.length ? (
          <ul className="space-y-2">
            {pinned.map((m) => (
              <li key={m.id} className="rounded-xl border border-gold-300/50 bg-gold-50/60 px-3 py-2 text-xs dark:border-gold-500/20 dark:bg-gold-500/5">
                <p className="font-semibold">{m.author_name}</p>
                <p className="line-clamp-3 text-ink-soft dark:text-slate-300">{m.body}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-ink-mute">Nothing pinned yet — use a message’s ⋯ menu.</p>
        )}
      </div>
      <div>
        <p className="label flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5" /> Members ({members.data?.count ?? conv.member_count})
        </p>
        <QueryState q={members} skeleton={<Skeleton className="h-32" />}>
          {(d) => (
            <ul className="space-y-1">
              {d.members.map((m) => {
                const p = profiles.find((x) => x.user_id === m.user_id);
                return (
                  <li key={m.user_id} className="flex items-center gap-2.5 rounded-xl px-2 py-1.5 hover:bg-black/[.03] dark:hover:bg-white/5">
                    <Avatar name={m.name} size={30} online={(m.presence ?? p?.presence) === "online"} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {m.name} {m.user_id === me && <span className="text-ink-mute">(you)</span>}
                      </p>
                      <p className="truncate text-[11px] text-ink-mute">{p ? `@${p.handle} · ${titleCase(p.role)}` : titleCase(m.role)}</p>
                    </div>
                    {m.role !== "member" && <Badge tone="gold">{m.role}</Badge>}
                  </li>
                );
              })}
            </ul>
          )}
        </QueryState>
      </div>
    </div>
  );
}

function ActionsTab({ conv, me, onNew }: { conv: Conversation; me: string; onNew: () => void }) {
  const q = useApi<{ count: number; by_status: Record<string, number>; overdue: number; actions: MsgAction[] }>(`/messaging/conversations/${conv.id}/actions`, { user_id: me });
  const complete = useMutate((id: string) => ok(post(`/messaging/actions/${id}/complete`, { user_id: me })), { invalidate: ["/messaging"], success: "Action completed" });
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">
          Actions raised {q.data && <span className="text-ink-mute">· {q.data.count}</span>}
          {!!q.data?.overdue && <Badge tone="red" className="ms-2">{q.data.overdue} overdue</Badge>}
        </p>
        <Button size="sm" variant="soft" icon={<Plus className="h-3.5 w-3.5" />} onClick={onNew}>
          New
        </Button>
      </div>
      <QueryState q={q} skeleton={<Skeleton className="h-40" />}>
        {(d) =>
          d.actions.length === 0 ? (
            <EmptyState title="No actions yet" hint="Turn any message into a task, approval or verification." icon={<ListTodo className="h-6 w-6" />} />
          ) : (
            <ul className="space-y-2">
              {d.actions.map((a) => (
                <li key={a.id} className={cn("rounded-xl border p-3", a.overdue && a.status !== "done" ? "border-red-200 bg-red-50/50 dark:border-red-500/20 dark:bg-red-500/5" : "border-black/5 dark:border-white/10")}>
                  <div className="flex items-start gap-2">
                    <button
                      onClick={() => a.status !== "done" && complete.mutate(a.id)}
                      disabled={a.status === "done" || complete.isPending}
                      className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition", a.status === "done" ? "border-brand-600 bg-brand-600 text-white" : "border-black/20 hover:border-brand-500 dark:border-white/20")}
                      title="Mark complete"
                    >
                      {a.status === "done" && <Check className="h-3.5 w-3.5" />}
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className={cn("text-sm font-semibold", a.status === "done" && "text-ink-mute line-through")}>{a.title}</p>
                      {a.detail && <p className="text-xs text-ink-mute">{a.detail}</p>}
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-mute">
                        <Badge tone="purple">{a.kind}</Badge>
                        <StatusBadge status={a.overdue && a.status !== "done" ? "overdue" : a.status} />
                        {a.owner_name && <span>→ {a.owner_name}</span>}
                        {a.due_on && <span>· due {date(a.due_on)}</span>}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )
        }
      </QueryState>
    </div>
  );
}

interface Summary {
  total_messages: number;
  window: number;
  participants: { user_id: string; name: string; messages: number }[];
  topics: Record<string, number>;
  keywords: { term: string; count: number }[];
  salient_lines: { author: string; body: string; at: string }[];
  open_actions: number;
  method: string;
}
interface Extracted {
  suggestions: number;
  items: { message_id: string; author: string; body: string; at: string; suggested_owner_id?: string | null; suggested_owner?: string | null }[];
  created: number;
  method: string;
}

function AiTab({ conv, me, onMakeAction }: { conv: Conversation; me: string; onMakeAction: (title: string, message?: Message) => void }) {
  const summary = useApi<Summary>(`/messaging/conversations/${conv.id}/summary`, { user_id: me });
  const [extracted, setExtracted] = useState<Extracted | null>(null);
  const extract = useMutate(() => ok(post<Extracted>(`/messaging/conversations/${conv.id}/action-items`, { user_id: me, create: false })), {
    onSuccess: (r) => setExtracted(r),
    success: (r) => `${r.suggestions} action item(s) found`,
  });
  const createAll = useMutate(() => ok(post<Extracted>(`/messaging/conversations/${conv.id}/action-items`, { user_id: me, create: true, owner_default: me })), {
    invalidate: ["/messaging"],
    success: (r) => `${r.created} action(s) created`,
    onSuccess: () => setExtracted(null),
  });
  return (
    <div className="space-y-5">
      <div className="relative overflow-hidden rounded-2xl bg-brand-gradient p-4 text-white">
        <Sparkles className="absolute -end-3 -top-3 h-20 w-20 text-white/10" />
        <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-gold-300">
          <Sparkles className="h-3.5 w-3.5" /> AI summary
        </p>
        <QueryState q={summary} skeleton={<Skeleton className="mt-2 h-20 bg-white/10" />}>
          {(s) => (
            <div className="mt-2 space-y-3">
              <p className="text-sm text-white/85">
                {s.total_messages} message(s) from {s.participants.length} participant(s); {s.open_actions} open action(s).
              </p>
              {Object.keys(s.topics ?? {}).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(s.topics).map(([t, n]) => (
                    <span key={t} className="rounded-full bg-white/15 px-2 py-0.5 text-[11px] font-semibold">
                      {titleCase(t)} · {n}
                    </span>
                  ))}
                </div>
              )}
              <ul className="space-y-2">
                {s.salient_lines.slice(0, 4).map((l, i) => (
                  <li key={i} className="rounded-xl bg-white/10 px-3 py-2 text-xs">
                    <b>{l.author}:</b> {l.body}
                  </li>
                ))}
              </ul>
              {s.keywords.length > 0 && <p className="text-[11px] text-white/70">Keywords: {s.keywords.slice(0, 8).map((k) => k.term).join(", ")}</p>}
            </div>
          )}
        </QueryState>
      </div>

      <div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold">Action items</p>
          <Button size="sm" variant="gold" loading={extract.isPending} icon={<ClipboardList className="h-3.5 w-3.5" />} onClick={() => extract.mutate()}>
            Extract
          </Button>
        </div>
        {extracted && (
          <div className="mt-3 space-y-2">
            {extracted.items.length === 0 && <p className="text-xs text-ink-mute">No requests or assignments detected.</p>}
            {extracted.items.map((it) => (
              <div key={it.message_id} className="rounded-xl border border-black/5 p-3 dark:border-white/10">
                <p className="text-xs text-ink-mute">
                  {it.author} · {timeAgo(it.at)}
                </p>
                <p className="mt-0.5 text-sm">{it.body}</p>
                <div className="mt-2 flex items-center justify-between gap-2">
                  {it.suggested_owner && <span className="text-[11px] text-ink-mute">Suggested owner: {it.suggested_owner}</span>}
                  <Button size="sm" variant="soft" onClick={() => onMakeAction(it.body.slice(0, 120), { id: it.message_id } as Message)}>
                    Create action
                  </Button>
                </div>
              </div>
            ))}
            {extracted.items.length > 1 && (
              <Button size="sm" className="w-full" loading={createAll.isPending} onClick={() => createAll.mutate()}>
                Create all {extracted.items.length}
              </Button>
            )}
            <p className="text-[10px] text-ink-mute">{extracted.method}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function ThreadView({ root, conv, me, members, myHandle, onClose }: { root: Message; conv: Conversation; me: string; members: (Member & { handle: string })[]; myHandle?: string; onClose: () => void }) {
  const q = useApi<{ root: Message; count: number; replies: Message[] }>(`/messaging/messages/${root.id}/thread`, { user_id: me });
  return (
    <>
      <div className="flex items-center gap-2 border-b border-black/5 p-3 dark:border-white/10">
        <button onClick={onClose} className="btn btn-ghost btn-icon h-8 w-8" aria-label="Back">
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" />
        </button>
        <div className="min-w-0">
          <p className="font-display font-semibold">Thread</p>
          <p className="truncate text-xs text-ink-mute">#{conv.title}</p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <QueryState q={q} skeleton={<Skeleton className="h-40" />}>
          {(d) => (
            <div>
              <Bubble m={d.root ?? root} me={me} myHandle={myHandle} compact />
              <div className="my-3 flex items-center gap-2 text-[11px] font-semibold text-ink-mute">
                <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />
                {d.count} repl{d.count === 1 ? "y" : "ies"}
                <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />
              </div>
              {d.replies.map((r, i) => (
                <Bubble key={r.id} m={r} me={me} myHandle={myHandle} grouped={i > 0 && d.replies[i - 1]!.author_id === r.author_id} />
              ))}
            </div>
          )}
        </QueryState>
      </div>
      <Composer conv={conv} me={me} members={members} parentId={root.id} placeholder="Reply in thread…" />
    </>
  );
}

// ---------------------------------------------------------------- modals
function NewMessageModal({ open, onClose, me, profiles, onOpen }: { open: boolean; onClose: () => void; me: string; profiles: Profile[]; onOpen: (id: string) => void }) {
  const [s, setS] = useState("");
  const m = useMutate((other: string) => ok(post<{ conversation: Conversation }>("/messaging/direct", { user_a: me, user_b: other })), {
    invalidate: ["/messaging"],
    onSuccess: (r) => {
      onClose();
      if (r.conversation?.id) onOpen(r.conversation.id);
    },
  });
  const list = profiles.filter((p) => p.user_id !== me && [p.display_name, p.handle, p.role].some((x) => x.toLowerCase().includes(s.toLowerCase())));
  return (
    <Modal open={open} onClose={onClose} title="New direct message" subtitle="Pick a teammate to start (or reopen) a 1-to-1 conversation.">
      <Input icon={<Search className="h-4 w-4" />} value={s} onChange={(e) => setS(e.target.value)} placeholder="Search people, handles or roles" autoFocus />
      <ul className="mt-3 max-h-[50vh] space-y-1 overflow-y-auto">
        {list.map((p) => (
          <li key={p.user_id}>
            <button
              disabled={m.isPending}
              onClick={() => m.mutate(p.user_id)}
              className="flex w-full items-center gap-3 rounded-xl p-2 text-start transition hover:bg-brand-50 disabled:opacity-60 dark:hover:bg-white/5"
            >
              <Avatar name={p.display_name} size={38} online={p.presence === "online"} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{p.display_name}</p>
                <p className="truncate text-xs text-ink-mute">
                  @{p.handle} · {titleCase(p.role)}
                </p>
              </div>
              {m.isPending && m.variables === p.user_id ? <Spinner className="h-4 w-4" /> : <Send className="h-4 w-4 text-ink-mute rtl:-scale-x-100" />}
            </button>
          </li>
        ))}
        {list.length === 0 && <p className="p-6 text-center text-sm text-ink-mute">No people found.</p>}
      </ul>
    </Modal>
  );
}

function ActionModal({ conv, me, message, initialTitle, onClose }: { conv: Conversation; me: string; message?: Message; initialTitle?: string; onClose: () => void }) {
  const [f, setF] = useState({ title: initialTitle ?? "", kind: "task", owner_id: "", due_on: "", detail: "" });
  const m = useMutate(
    () =>
      ok(
        post(`/messaging/conversations/${conv.id}/actions`, {
          created_by: me,
          title: f.title,
          kind: f.kind,
          message_id: message?.id ?? null,
          owner_id: f.owner_id || null,
          due_on: f.due_on || null,
          detail: f.detail || null,
        }),
      ),
    { invalidate: ["/messaging"], success: "Action created", onSuccess: onClose },
  );
  return (
    <Modal
      open
      onClose={onClose}
      title="Create an action"
      subtitle={message?.body ? `From: “${message.body.slice(0, 80)}${message.body.length > 80 ? "…" : ""}”` : `In ${conv.title}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={m.isPending} disabled={!f.title.trim()} onClick={() => m.mutate()}>
            Create
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title" className="sm:col-span-2">
          <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} autoFocus />
        </Field>
        <Field label="Kind">
          <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} options={["task", "approval", "verification", "request"].map((k) => ({ value: k, label: titleCase(k) }))} />
        </Field>
        <Field label="Owner">
          <Select value={f.owner_id} onChange={(e) => setF({ ...f, owner_id: e.target.value })}>
            <option value="">Unassigned</option>
            {conv.members.map((mm) => (
              <option key={mm.user_id} value={mm.user_id}>
                {mm.name}
                {mm.user_id === me ? " (you)" : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Due on">
          <Input type="date" value={f.due_on} onChange={(e) => setF({ ...f, due_on: e.target.value })} />
        </Field>
        <Field label="Detail" className="sm:col-span-2">
          <Textarea rows={3} value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} />
        </Field>
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-mute">
        <Radio className="h-3.5 w-3.5" /> Members are notified in real time.
      </p>
    </Modal>
  );
}
