import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Braces, ChevronRight, Clock, Database, FileCode2, MessageSquareText, Play, Plug, RotateCcw, Search, Server, ShieldAlert, Terminal, Trash2, Wrench, Zap } from "lucide-react";
import { mcp, parseToolResult, type McpTool } from "@/lib/mcp";
import { cn } from "@/lib/utils";
import { Badge, Breadcrumbs, Button, Card, CardBody, CardHeader, CopyButton, EmptyState, ErrorState, Field, Input, JsonView, Segmented, Skeleton, Spinner, Tabs } from "@/components/ui";
import { HeroBackdrop } from "@/components/agents/AgentBits";
import { buildArgs, initialValues, SchemaForm, type FormValues } from "@/components/tools/SchemaForm";
import { useMcpAdmin, useMcpTools } from "@/components/tools/MiscTools";

const MCP_URL = "http://127.0.0.1:8000/mcp";
// MCP needs PORTAL_MCP_TOKEN (backend/.env) as a bearer token; local dev clients may skip it.
const CONFIG = JSON.stringify({ mcpServers: { arzepak: { type: "http", url: MCP_URL, headers: { Authorization: "Bearer <PORTAL_MCP_TOKEN>" } } } }, null, 2);

const prefixOf = (n: string) => n.split("_")[0] ?? n;
const tryParse = (t?: string): unknown => {
  if (t === undefined) return undefined;
  try {
    return JSON.parse(t);
  } catch {
    return t;
  }
};

// ------------------------------------------------------------------ result view
interface CallRecord {
  id: number;
  tool: string;
  args: Record<string, unknown>;
  values: FormValues;
  ms: number;
  isError?: boolean;
  parsed: unknown;
  raw: string;
  at: Date;
}

function ResultView({ rec }: { rec: CallRecord }) {
  const [view, setView] = useState<"parsed" | "raw">("parsed");
  return (
    <div className="rounded-2xl border border-black/5 dark:border-white/10">
      <div className="flex flex-wrap items-center gap-2 border-b border-black/5 px-4 py-2.5 dark:border-white/10">
        <Badge tone={rec.isError ? "red" : "green"}>{rec.isError ? "isError" : "ok"}</Badge>
        <span className="inline-flex items-center gap-1 text-xs text-ink-mute">
          <Clock className="h-3 w-3" /> {rec.ms} ms
        </span>
        <span className="text-xs text-ink-mute">{(rec.raw.length / 1024).toFixed(1)} KB</span>
        <div className="ms-auto flex items-center gap-1">
          <Segmented size="sm" value={view} onChange={setView} options={[{ value: "parsed", label: "Parsed" }, { value: "raw", label: "Raw" }]} />
          <CopyButton text={rec.raw} />
        </div>
      </div>
      <div className="max-h-[520px] overflow-auto p-4">
        {view === "parsed" ? <JsonView data={rec.parsed} defaultOpen={2} /> : <pre className="whitespace-pre-wrap break-all font-mono text-[11px] leading-5 text-ink-soft dark:text-slate-300">{rec.raw}</pre>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ tools tab
function ToolsTab() {
  const tq = useMcpTools();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const selectedName = params.get("tool");
  const tools = tq.data?.tools ?? [];
  const selected = tools.find((t) => t.name === selectedName) ?? null;
  const [values, setValues] = useState<FormValues>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [history, setHistory] = useState<CallRecord[]>([]);
  const [current, setCurrent] = useState<CallRecord | null>(null);
  const pending = useRef<FormValues | null>(null);

  useEffect(() => {
    if (selected) {
      setValues(pending.current ?? initialValues(selected.inputSchema));
      pending.current = null;
      setErrors({});
      setErr(null);
      setCurrent(history.find((h) => h.tool === selected.name) ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.name]);

  const groups = useMemo(() => {
    const m = new Map<string, McpTool[]>();
    const s = search.trim().toLowerCase();
    for (const t of tools) {
      if (s && !`${t.name} ${t.description ?? ""}`.toLowerCase().includes(s)) continue;
      const p = prefixOf(t.name);
      if (group && p !== group) continue;
      m.set(p, [...(m.get(p) ?? []), t]);
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [tools, search, group]);
  const prefixes = useMemo(() => {
    const c = new Map<string, number>();
    for (const t of tools) c.set(prefixOf(t.name), (c.get(prefixOf(t.name)) ?? 0) + 1);
    return [...c.entries()].filter(([, n]) => n >= 3).sort((a, b) => b[1] - a[1]);
  }, [tools]);
  const matchCount = groups.reduce((a, [, l]) => a + l.length, 0);

  const select = (name: string) => {
    const next = new URLSearchParams(params);
    next.set("tool", name);
    setParams(next, { replace: true });
  };

  const call = async (tool: McpTool, vals: FormValues) => {
    const { args, errors } = buildArgs(tool.inputSchema, vals);
    setErrors(errors);
    if (Object.keys(errors).length) return;
    setBusy(true);
    setErr(null);
    const t0 = performance.now();
    try {
      const r = await mcp.callTool(tool.name, args);
      const raw = r.content?.map((c) => c.text ?? "").join("\n") ?? JSON.stringify(r);
      const rec: CallRecord = { id: Date.now(), tool: tool.name, args, values: vals, ms: Math.round(performance.now() - t0), isError: r.isError, parsed: parseToolResult(r), raw, at: new Date() };
      setCurrent(rec);
      setHistory((h) => [rec, ...h].slice(0, 25));
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  if (tq.isLoading)
    return (
      <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Skeleton className="h-[600px]" />
        <Skeleton className="h-[600px]" />
      </div>
    );
  if (tq.error) return <ErrorState error={tq.error} onRetry={() => tq.refetch()} />;

  return (
    <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
      {/* catalogue */}
      <Card className="flex max-h-[78vh] min-h-[420px] flex-col overflow-hidden">
        <div className="space-y-3 border-b border-black/5 p-3 dark:border-white/10">
          <Input icon={<Search className="h-4 w-4" />} placeholder={`Search ${tools.length} tools`} value={search} onChange={(e) => setSearch(e.target.value)} className="!py-2" />
          <div className="no-scrollbar flex gap-1 overflow-x-auto">
            <button type="button" onClick={() => setGroup(null)} className={cn("chip shrink-0", !group ? "bg-brand-700 text-white" : "bg-black/5 dark:bg-white/10")}>
              all
            </button>
            {prefixes.map(([p, n]) => (
              <button key={p} type="button" onClick={() => setGroup(group === p ? null : p)} className={cn("chip shrink-0 font-mono", group === p ? "bg-brand-700 text-white" : "bg-black/5 dark:bg-white/10")}>
                {p}_ <span className="opacity-60">{n}</span>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-ink-mute">
            {matchCount} match{matchCount === 1 ? "" : "es"} in {groups.length} group{groups.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {groups.map(([p, list]) => {
            const isOpen = open[p] ?? (!!search.trim() || !!group || groups.length <= 3 || list.some((t) => t.name === selectedName));
            return (
              <div key={p} className="mb-1">
                <button type="button" onClick={() => setOpen((o) => ({ ...o, [p]: !isOpen }))} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-start text-xs font-semibold uppercase tracking-wider text-ink-mute hover:bg-black/5 dark:hover:bg-white/5">
                  <ChevronRight className={cn("h-3.5 w-3.5 transition rtl:rotate-180", isOpen && "rotate-90 rtl:rotate-90")} />
                  <span className="font-mono normal-case">{p}_</span>
                  <span className="ms-auto rounded-full bg-black/5 px-1.5 text-[10px] dark:bg-white/10">{list.length}</span>
                </button>
                {isOpen && (
                  <ul className="ms-3 border-s border-black/5 ps-2 dark:border-white/10">
                    {list.map((t) => (
                      <li key={t.name}>
                        <button
                          type="button"
                          onClick={() => select(t.name)}
                          className={cn(
                            "block w-full truncate rounded-md px-2 py-1 text-start font-mono text-[12px] transition",
                            t.name === selectedName ? "bg-brand-700 text-white" : "text-ink-soft hover:bg-brand-50 dark:text-slate-300 dark:hover:bg-white/5",
                          )}
                          title={t.description}
                        >
                          {t.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
          {!groups.length && <EmptyState title="No tools match" />}
        </div>
      </Card>

      {/* inspector */}
      <div className="min-w-0 space-y-5">
        {selected ? (
          <Card>
            <CardHeader
              title={<span className="font-mono">{selected.name}</span>}
              subtitle={`${Object.keys(selected.inputSchema?.properties ?? {}).length} parameters · ${(selected.inputSchema?.required ?? []).length} required`}
              icon={<Wrench className="h-4 w-4" />}
              action={<CopyButton text={selected.name} />}
            />
            <CardBody className="space-y-5">
              {selected.description && <p className="whitespace-pre-line rounded-xl bg-brand-50/60 p-3 text-sm text-ink-soft dark:bg-white/5 dark:text-slate-300">{selected.description}</p>}
              <SchemaForm schema={selected.inputSchema} values={values} onChange={setValues} errors={errors} compact />
              <div className="flex flex-wrap items-center gap-2">
                <Button icon={<Play className="h-4 w-4" />} loading={busy} onClick={() => call(selected, values)}>
                  Call tool
                </Button>
                <Button variant="ghost" size="sm" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setValues(initialValues(selected.inputSchema))}>
                  Reset
                </Button>
                <details className="ms-auto text-xs">
                  <summary className="cursor-pointer text-ink-mute hover:text-brand-700">inputSchema</summary>
                  <div className="mt-2 max-h-64 overflow-auto rounded-xl bg-slate-50 p-3 dark:bg-black/30">
                    <JsonView data={selected.inputSchema} defaultOpen={3} />
                  </div>
                </details>
              </div>
              {err != null && <ErrorState error={err} />}
              {busy && !current && <Skeleton className="h-40" />}
              {current && current.tool === selected.name && <ResultView key={current.id} rec={current} />}
            </CardBody>
          </Card>
        ) : (
          <Card>
            <CardBody>
              <EmptyState icon={<Terminal className="h-6 w-6" />} title="Pick a tool" hint="Select any tool on the left to see its schema, fill an auto-generated form and call it live." />
            </CardBody>
          </Card>
        )}

        <Card>
          <CardHeader
            title="Call history"
            subtitle="This session"
            icon={<Clock className="h-4 w-4" />}
            action={
              history.length > 0 && (
                <Button variant="ghost" size="sm" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setHistory([])}>
                  Clear
                </Button>
              )
            }
          />
          {history.length ? (
            <ul className="max-h-72 divide-y divide-black/5 overflow-y-auto dark:divide-white/10">
              <AnimatePresence initial={false}>
                {history.map((h) => (
                  <motion.li key={h.id} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="flex items-center gap-3 px-5 py-2.5">
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", h.isError ? "bg-red-500" : "bg-emerald-500")} />
                    <button type="button" className="min-w-0 flex-1 text-start" onClick={() => { select(h.tool); setCurrent(h); }}>
                      <span className="block truncate font-mono text-xs font-semibold">{h.tool}</span>
                      <span className="block truncate font-mono text-[10px] text-ink-mute">{JSON.stringify(h.args)}</span>
                    </button>
                    <span className="text-[10px] tabular-nums text-ink-mute">{h.ms} ms</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<RotateCcw className="h-3.5 w-3.5" />}
                      onClick={() => {
                        const t = tools.find((x) => x.name === h.tool);
                        if (!t) return;
                        pending.current = h.values;
                        setValues(h.values);
                        select(t.name);
                        call(t, h.values);
                      }}
                    >
                      Re-run
                    </Button>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          ) : (
            <CardBody>
              <p className="text-sm text-ink-mute">No calls yet.</p>
            </CardBody>
          )}
        </Card>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ resources tab
function ContentsView({ contents }: { contents: { uri: string; text?: string; mimeType?: string }[] }) {
  return (
    <div className="space-y-3">
      {contents.map((c, i) => {
        const parsed = tryParse(c.text);
        return (
          <div key={i} className="rounded-2xl border border-black/5 dark:border-white/10">
            <div className="flex items-center gap-2 border-b border-black/5 px-4 py-2 dark:border-white/10">
              <code className="truncate text-xs">{c.uri}</code>
              {c.mimeType && <Badge tone="gray">{c.mimeType}</Badge>}
              <CopyButton text={c.text ?? ""} className="ms-auto" />
            </div>
            <div className="max-h-[460px] overflow-auto p-4">
              {typeof parsed === "object" && parsed !== null ? <JsonView data={parsed} defaultOpen={2} /> : <pre className="whitespace-pre-wrap font-mono text-xs">{String(c.text ?? "")}</pre>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ResourcesTab() {
  const rq = useQuery({ queryKey: ["mcp", "resources/list"], queryFn: () => mcp.listResources() });
  const tq = useQuery({ queryKey: ["mcp", "resources/templates/list"], queryFn: () => mcp.listResourceTemplates() });
  const [sel, setSel] = useState<{ kind: "res" | "tpl"; key: string } | null>(null);
  const [params, setParams] = useState<Record<string, string>>({});
  const [uri, setUri] = useState<string | null>(null);
  const read = useQuery({ queryKey: ["mcp", "resources/read", uri], queryFn: () => mcp.readResource(uri!), enabled: !!uri, retry: false });
  const tpl = sel?.kind === "tpl" ? tq.data?.resourceTemplates.find((t) => t.uriTemplate === sel.key) : undefined;
  const tplParams = tpl ? [...tpl.uriTemplate.matchAll(/\{([^}]+)\}/g)].map((m) => m[1]) : [];
  const filled = tpl ? tpl.uriTemplate.replace(/\{([^}]+)\}/g, (_, k: string) => encodeURIComponent(params[k] ?? "")) : "";

  return (
    <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Card className="max-h-[78vh] overflow-y-auto">
        <CardHeader title="Resources" subtitle={`${rq.data?.resources.length ?? "…"} static · ${tq.data?.resourceTemplates.length ?? "…"} templates`} icon={<Database className="h-4 w-4" />} />
        <div className="p-2">
          {rq.isLoading || tq.isLoading ? <Skeleton className="h-80" /> : null}
          {rq.error ? <ErrorState error={rq.error} /> : null}
          {rq.data?.resources.map((r) => (
            <button
              key={r.uri}
              type="button"
              onClick={() => {
                setSel({ kind: "res", key: r.uri });
                setUri(r.uri);
              }}
              className={cn("block w-full rounded-xl px-3 py-2 text-start transition", sel?.key === r.uri ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/5")}
            >
              <span className="block text-sm font-semibold">{r.name}</span>
              <span className={cn("block truncate font-mono text-[11px]", sel?.key === r.uri ? "text-white/70" : "text-ink-mute")}>{r.uri}</span>
            </button>
          ))}
          {!!tq.data?.resourceTemplates.length && <p className="mt-3 px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-mute">Templates</p>}
          {tq.data?.resourceTemplates.map((t) => (
            <button
              key={t.uriTemplate}
              type="button"
              onClick={() => {
                setSel({ kind: "tpl", key: t.uriTemplate });
                setParams({});
                setUri(null);
              }}
              className={cn("block w-full rounded-xl px-3 py-2 text-start transition", sel?.key === t.uriTemplate ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/5")}
            >
              <span className="flex items-center gap-1.5 text-sm font-semibold">
                <Braces className="h-3.5 w-3.5" /> {t.name}
              </span>
              <span className={cn("block truncate font-mono text-[11px]", sel?.key === t.uriTemplate ? "text-white/70" : "text-ink-mute")}>{t.uriTemplate}</span>
            </button>
          ))}
        </div>
      </Card>
      <div className="min-w-0 space-y-5">
        {tpl && (
          <Card>
            <CardHeader title={tpl.name} subtitle={tpl.description} icon={<Braces className="h-4 w-4" />} />
            <CardBody className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                {tplParams.map((p) => (
                  <Field key={p} label={p}>
                    <Input value={params[p] ?? ""} onChange={(e) => setParams((x) => ({ ...x, [p]: e.target.value }))} placeholder={p.includes("id") ? "Paste an id from a list resource" : p} />
                  </Field>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button icon={<FileCode2 className="h-4 w-4" />} disabled={tplParams.some((p) => !params[p])} onClick={() => setUri(filled)}>
                  Read resource
                </Button>
                <code className="truncate text-xs text-ink-mute">{filled}</code>
              </div>
            </CardBody>
          </Card>
        )}
        {uri ? (
          read.isLoading ? (
            <Skeleton className="h-80" />
          ) : read.error ? (
            <ErrorState error={read.error} onRetry={() => read.refetch()} />
          ) : read.data ? (
            <ContentsView contents={read.data.contents} />
          ) : null
        ) : !tpl ? (
          <Card>
            <CardBody>
              <EmptyState icon={<Database className="h-6 w-6" />} title="Pick a resource" hint="Static resources read instantly; templates take parameters such as a city or property id." />
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ prompts tab
function PromptsTab() {
  const pq = useQuery({ queryKey: ["mcp", "prompts/list"], queryFn: () => mcp.listPrompts() });
  const [name, setName] = useState<string | null>(null);
  const [args, setArgs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [msgs, setMsgs] = useState<{ role: string; content: { type: string; text?: string } }[] | null>(null);
  const prompt = pq.data?.prompts.find((p) => p.name === name);
  const get = async () => {
    if (!prompt) return;
    setBusy(true);
    setErr(null);
    try {
      const clean = Object.fromEntries(Object.entries(args).filter(([, v]) => v.trim()));
      const r = await mcp.getPrompt(prompt.name, clean);
      setMsgs(r.messages);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Card className="max-h-[78vh] overflow-y-auto">
        <CardHeader title="Prompts" subtitle={`${pq.data?.prompts.length ?? "…"} templates`} icon={<MessageSquareText className="h-4 w-4" />} />
        <div className="p-2">
          {pq.isLoading && <Skeleton className="h-80" />}
          {pq.error ? <ErrorState error={pq.error} /> : null}
          {pq.data?.prompts.map((p) => (
            <button
              key={p.name}
              type="button"
              onClick={() => {
                setName(p.name);
                setArgs({});
                setMsgs(null);
              }}
              className={cn("block w-full rounded-xl px-3 py-2 text-start transition", name === p.name ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/5")}
            >
              <span className="block font-mono text-xs font-semibold">{p.name}</span>
              <span className={cn("block truncate text-[11px]", name === p.name ? "text-white/70" : "text-ink-mute")}>{p.description}</span>
            </button>
          ))}
        </div>
      </Card>
      <div className="min-w-0 space-y-5">
        {prompt ? (
          <Card>
            <CardHeader title={<span className="font-mono">{prompt.name}</span>} subtitle={prompt.description} icon={<MessageSquareText className="h-4 w-4" />} />
            <CardBody className="space-y-4">
              {prompt.arguments?.length ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {prompt.arguments.map((a) => (
                    <Field key={a.name} label={<>{a.name}{a.required && <span className="text-red-500"> *</span>}</>} hint={a.description}>
                      <Input value={args[a.name] ?? ""} onChange={(e) => setArgs((x) => ({ ...x, [a.name]: e.target.value }))} />
                    </Field>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-ink-mute">No arguments.</p>
              )}
              <Button icon={<Zap className="h-4 w-4" />} loading={busy} disabled={prompt.arguments?.some((a) => a.required && !args[a.name]?.trim())} onClick={get}>
                Get prompt
              </Button>
              {err != null && <ErrorState error={err} />}
              {msgs && (
                <div className="space-y-3">
                  {msgs.map((m, i) => (
                    <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl bg-brand-50/70 p-4 dark:bg-white/5">
                      <div className="mb-2 flex items-center gap-2">
                        <Badge tone={m.role === "user" ? "gold" : "green"}>{m.role}</Badge>
                        <CopyButton text={m.content.text ?? ""} className="ms-auto" />
                      </div>
                      <p className="whitespace-pre-wrap text-sm text-ink-soft dark:text-slate-200">{m.content.text}</p>
                    </motion.div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        ) : (
          <Card>
            <CardBody>
              <EmptyState icon={<MessageSquareText className="h-6 w-6" />} title="Pick a prompt" hint="Prompts are reusable instructions an AI client can pull from the server." />
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ page
export default function McpConsole() {
  // The MCP endpoint admits administrators only (session token or PORTAL_MCP_TOKEN).
  const admin = useMcpAdmin();
  const init = useQuery({ queryKey: ["mcp", "initialize"], queryFn: () => mcp.initialize(), retry: false, enabled: admin });
  const tq = useMcpTools();
  const rq = useQuery({ queryKey: ["mcp", "resources/list"], queryFn: () => mcp.listResources(), enabled: admin });
  const pq = useQuery({ queryKey: ["mcp", "prompts/list"], queryFn: () => mcp.listPrompts(), enabled: admin });
  const [tab, setTab] = useState<"tools" | "resources" | "prompts">("tools");
  const [client, setClient] = useState<"claude" | "cursor" | "code">("claude");
  const info = init.data;
  const caps = info?.capabilities && typeof info.capabilities === "object" ? Object.keys(info.capabilities as Record<string, unknown>) : [];
  const snippet = client === "code" ? `claude mcp add --transport http arzepak ${MCP_URL}` : CONFIG;
  const where = { claude: "claude_desktop_config.json", cursor: ".cursor/mcp.json", code: "terminal" }[client];

  return (
    <div className="pb-16">
      <section className="relative isolate overflow-hidden text-white">
        <HeroBackdrop />
        <div className="container grid gap-8 py-10 lg:grid-cols-[minmax(0,1fr)_440px] lg:items-center lg:py-14">
          <div>
            <Breadcrumbs light crumbs={[{ label: "AI Hub", to: "/ai" }, { label: "MCP console" }]} />
            <h1 className="mt-4 flex items-center gap-3 font-display text-3xl font-bold sm:text-4xl">
              <Terminal className="h-8 w-8 text-gold-300" /> MCP Console
            </h1>
            <p className="mt-3 max-w-xl text-white/75">Inspect and call every tool, resource and prompt the Arz-e-Pak Model Context Protocol server exposes — exactly what Claude, ChatGPT or Cursor see.</p>
            <div className="mt-5 flex flex-wrap items-center gap-2 text-xs">
              {!admin ? (
                <span className="chip bg-gold-400/20 text-gold-100">
                  <ShieldAlert className="h-3 w-3" /> admins only
                </span>
              ) : init.isLoading ? (
                <span className="chip bg-white/10">
                  <Spinner className="h-3 w-3 text-white" /> connecting…
                </span>
              ) : init.error ? (
                <span className="chip bg-red-500/20 text-red-100">
                  <span className="h-2 w-2 rounded-full bg-red-400" /> {(init.error as Error).message}
                </span>
              ) : (
                <>
                  <span className="chip bg-emerald-500/20 text-emerald-100">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" /> connected
                  </span>
                  <span className="chip bg-white/10">
                    <Server className="h-3 w-3" /> {info?.serverInfo.name} {info?.serverInfo.version}
                  </span>
                  <span className="chip bg-white/10 font-mono">protocol {info?.protocolVersion}</span>
                  {caps.map((c) => (
                    <span key={c} className="chip bg-gold-400/20 text-gold-100">
                      {c}
                    </span>
                  ))}
                </>
              )}
            </div>
            <div className="mt-6 grid max-w-md grid-cols-3 gap-3">
              {[
                { label: "Tools", v: tq.data?.tools.length, icon: Wrench },
                { label: "Resources", v: rq.data?.resources.length, icon: Database },
                { label: "Prompts", v: pq.data?.prompts.length, icon: MessageSquareText },
              ].map((s) => (
                <div key={s.label} className="glass-dark rounded-2xl px-3 py-3">
                  <s.icon className="h-4 w-4 text-gold-300" />
                  <p className="mt-1 font-display text-2xl font-bold">{s.v ?? "–"}</p>
                  <p className="text-[11px] uppercase tracking-wider text-white/60">{s.label}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="glass-dark rounded-3xl p-5">
            <div className="flex items-center gap-2">
              <Plug className="h-5 w-5 text-gold-300" />
              <p className="font-display text-lg font-semibold">Connect your AI client</p>
            </div>
            <div className="mt-3">
              <Segmented
                size="sm"
                value={client}
                onChange={setClient}
                options={[
                  { value: "claude", label: "Claude Desktop" },
                  { value: "cursor", label: "Cursor" },
                  { value: "code", label: "Claude Code" },
                ]}
                className="!bg-white/10 [&_button]:!text-white/80"
              />
            </div>
            <p className="mt-3 text-xs text-white/60">
              Add to <code className="text-gold-200">{where}</code>:
            </p>
            <div className="relative mt-2">
              <pre className="no-scrollbar overflow-x-auto rounded-2xl bg-black/40 p-4 pe-20 font-mono text-[12px] leading-5 text-emerald-200">{snippet}</pre>
              <CopyButton text={snippet} className="absolute end-2 top-2 !text-emerald-200 hover:!bg-white/10" />
            </div>
            <p className="mt-3 text-[11px] text-white/50">Streamable HTTP transport · stateless JSON-RPC 2.0 · endpoint {MCP_URL}</p>
          </div>
        </div>
      </section>

      {!admin ? (
        <div className="container mx-auto mt-8 max-w-xl">
          <EmptyState
            icon={<ShieldAlert className="h-6 w-6" />}
            title="Admins only"
            hint="The MCP server exposes every portal tool, so only administrators can use this console. Sign in with an admin account, or connect an AI client with the server's PORTAL_MCP_TOKEN."
            action={
              <Link to="/login?next=/ai/mcp" className="btn btn-outline btn-sm">
                Sign in
              </Link>
            }
          />
        </div>
      ) : (
      <div className="container mt-8 space-y-6">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "tools", label: "Tools", icon: <Wrench className="h-4 w-4" />, count: tq.data?.tools.length },
            { value: "resources", label: "Resources", icon: <Database className="h-4 w-4" />, count: rq.data ? rq.data.resources.length : undefined },
            { value: "prompts", label: "Prompts", icon: <MessageSquareText className="h-4 w-4" />, count: pq.data?.prompts.length },
          ]}
        />
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            {tab === "tools" ? <ToolsTab /> : tab === "resources" ? <ResourcesTab /> : <PromptsTab />}
          </motion.div>
        </AnimatePresence>
        <p className="text-center text-xs text-ink-mute">
          Tools are grouped by name prefix (crm_, pm_, gis_, msg_…). Calls run against the live portal with your session token.
        </p>
      </div>
      )}
    </div>
  );
}
