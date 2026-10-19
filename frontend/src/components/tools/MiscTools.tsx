/** Calendar converter, map measurement and a generic MCP-backed tool runner. */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CircleMarker, Polygon, Polyline, Tooltip as LTooltip, useMapEvents } from "react-leaflet";
import { ArrowRightLeft, CalendarDays, Clock, Eraser, Hexagon, Moon, Play, Route, Ruler, Sun, Terminal, Undo2 } from "lucide-react";
import { isMcpAdmin, mcp, parseToolResult, type McpTool } from "@/lib/mcp";
import { useAuth } from "@/store/auth";
import { date as fmtDate, num } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, ButtonLink, Card, CardBody, CardHeader, EmptyState, ErrorState, Field, Input, JsonView, KeyValue, Select, Skeleton, Spinner, StatCard } from "@/components/ui";
import { PortalMap } from "@/components/map/PortalMap";
import { CalcShell, SaveProjectButton, StatGrid, useCalc } from "./CalcKit";
import { buildArgs, initialValues, SchemaForm, type FormValues } from "./SchemaForm";
import type { ToolCard } from "./toolMeta";

// ================================================================== calendar
const HIJRI_MONTHS = ["Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani", "Jumada al-Awwal", "Jumada al-Thani", "Rajab", "Sha'ban", "Ramadan", "Shawwal", "Dhu al-Qadah", "Dhu al-Hijjah"];

interface Holiday {
  name: string;
  date: string;
  type: string;
  predicted?: boolean;
  announced?: boolean;
}

export function CalendarTool() {
  const today = new Date().toISOString().slice(0, 10);
  const [on, setOn] = useState(today);
  const [hy, setHy] = useState(1448);
  const [hm, setHm] = useState(9);
  const [hd, setHd] = useState(1);
  const [year, setYear] = useState(new Date().getFullYear());
  const hq = useCalc<{ hijri: string; hijri_year: number; hijri_month: number; hijri_month_name: string; hijri_day: number; calendar: string }>("/tools/calendar/hijri", { on }, { method: "GET", enabled: /^\d{4}-\d{2}-\d{2}$/.test(on) });
  const gq = useCalc<{ hijri: string; gregorian: string; note?: string }>("/tools/calendar/gregorian", { year: hy, month: hm, day: hd }, { method: "GET", enabled: hy > 0 && hd > 0 && hd <= 30 });
  const yq = useCalc<{ year: number; count: number; holidays: Holiday[] }>("/tools/calendar/holidays", { year }, { method: "GET", enabled: year > 1900 && year < 2200 });
  const next = yq.data?.holidays.find((h) => h.date >= today);
  const daysTo = (d: string) => Math.round((new Date(d).getTime() - new Date(today).getTime()) / 86_400_000);

  return (
    <div className="space-y-6">
      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader title="Gregorian → Hijri" icon={<Sun className="h-4 w-4" />} />
          <CardBody className="space-y-4">
            <Field label="Gregorian date">
              <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
            </Field>
            <div className="rounded-2xl bg-brand-gradient p-5 text-white">
              {hq.data ? (
                <>
                  <p className="text-xs uppercase tracking-wider text-white/60">Hijri</p>
                  <p className="mt-1 font-display text-2xl font-bold">{hq.data.hijri}</p>
                  <p className="mt-1 text-xs text-white/70">{hq.data.calendar} calendar</p>
                  <button
                    type="button"
                    className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-gold-300 hover:underline"
                    onClick={() => {
                      setHy(hq.data!.hijri_year);
                      setHm(hq.data!.hijri_month);
                      setHd(hq.data!.hijri_day);
                    }}
                  >
                    <ArrowRightLeft className="h-3 w-3" /> Use in reverse converter
                  </button>
                </>
              ) : hq.error ? (
                <p className="text-sm">{(hq.error as Error).message}</p>
              ) : (
                <Skeleton className="h-16 bg-white/10" />
              )}
            </div>
          </CardBody>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader title="Hijri → Gregorian" icon={<Moon className="h-4 w-4" />} />
          <CardBody className="space-y-4">
            <div className="grid grid-cols-[1fr_2fr_1fr] gap-2">
              <Field label="Year">
                <Input type="number" value={hy} onChange={(e) => setHy(Number(e.target.value))} />
              </Field>
              <Field label="Month">
                <Select value={hm} onChange={(e) => setHm(Number(e.target.value))} options={HIJRI_MONTHS.map((m, i) => ({ value: String(i + 1), label: m }))} />
              </Field>
              <Field label="Day">
                <Input type="number" min={1} max={30} value={hd} onChange={(e) => setHd(Number(e.target.value))} />
              </Field>
            </div>
            <div className="rounded-2xl bg-gold-gradient p-5 text-brand-950">
              {gq.data ? (
                <>
                  <p className="text-xs uppercase tracking-wider text-brand-950/60">{gq.data.hijri}</p>
                  <p className="mt-1 font-display text-2xl font-bold">{fmtDate(gq.data.gregorian, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
                  {gq.data.note && <p className="mt-1 text-xs text-brand-950/70">{gq.data.note}</p>}
                </>
              ) : gq.error ? (
                <p className="text-sm">{(gq.error as Error).message}</p>
              ) : (
                <Skeleton className="h-16 bg-black/10" />
              )}
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title={`Pakistan public holidays ${year}`}
          subtitle="Fixed national days plus predicted Islamic holidays"
          icon={<CalendarDays className="h-4 w-4" />}
          action={
            <div className="flex items-center gap-2">
              <Input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} className="!w-24 !py-1.5 text-sm" aria-label="Year" />
              {yq.data && <SaveProjectButton tool="calendar" inputs={{ year }} outputs={yq.data} defaultName={`Holidays ${year}`} />}
            </div>
          }
        />
        <CardBody>
          {next && (
            <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl bg-brand-50 px-4 py-3 dark:bg-brand-500/10">
              <Clock className="h-5 w-5 text-brand-700 dark:text-brand-300" />
              <span className="text-sm">
                Next up: <b>{next.name}</b> on {fmtDate(next.date, { weekday: "short", day: "numeric", month: "short" })}
              </span>
              <Badge tone="gold" className="ms-auto">
                {daysTo(next.date) === 0 ? "Today" : `in ${daysTo(next.date)} days`}
              </Badge>
            </div>
          )}
          {yq.isLoading ? (
            <Skeleton className="h-60" />
          ) : yq.error ? (
            <ErrorState error={yq.error} onRetry={() => yq.refetch()} />
          ) : (
            <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {yq.data?.holidays.map((h, i) => {
                const past = h.date < today;
                return (
                  <motion.li
                    key={h.name + h.date}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.02 }}
                    className={cn("flex items-center gap-3 rounded-xl border border-black/5 p-3 dark:border-white/10", past && "opacity-55")}
                  >
                    <div className={cn("flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl text-white", h.type === "religious" ? "bg-brand-gradient" : "bg-gold-gradient !text-brand-950")}>
                      <span className="text-[10px] font-semibold uppercase leading-none">{fmtDate(h.date, { month: "short" })}</span>
                      <span className="font-display text-lg font-bold leading-none">{new Date(h.date).getDate()}</span>
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{h.name}</p>
                      <div className="mt-0.5 flex gap-1.5">
                        <Badge tone={h.type === "religious" ? "green" : "gold"}>{h.type}</Badge>
                        {h.predicted && <Badge tone="gray">predicted</Badge>}
                      </div>
                    </div>
                  </motion.li>
                );
              })}
            </ol>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

// ================================================================== map measure
interface MeasureRes {
  segments: { distance_m: number; bearing_deg: number }[];
  path_length_m: number;
  path_length_km: number;
  perimeter_m: number;
  area_sqm: number;
  area_sqft: number;
  area_sqyd: number;
  area_marla: number;
  area_kanal: number;
  area_acre: number;
  centroid: { lat: number; lon: number };
}

function ClickCatcher({ onClick }: { onClick: (p: [number, number]) => void }) {
  useMapEvents({ click: (e) => onClick([Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6))]) });
  return null;
}

const dist = (m: number) => (m >= 1000 ? `${num(m / 1000, 2)} km` : `${num(m, 1)} m`);

export function MapMeasureTool() {
  const [pts, setPts] = useState<[number, number][]>([]);
  const body = { coords: pts };
  const q = useCalc<MeasureRes>("/tools/gis/measure", body, { enabled: pts.length >= 2 });
  const d = pts.length >= 2 ? q.data : undefined;
  return (
    <CalcShell
      save={{ tool: "map_measure", inputs: body, outputs: d, name: `Map measure · ${pts.length} points` }}
      form={
        <>
          <p className="text-sm text-ink-soft dark:text-slate-300">Click on the map to drop points. Two points give a distance; three or more close a polygon and report its area in marla, kanal and acres.</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" icon={<Undo2 className="h-4 w-4" />} onClick={() => setPts((p) => p.slice(0, -1))} disabled={!pts.length}>
              Undo
            </Button>
            <Button variant="ghost" size="sm" icon={<Eraser className="h-4 w-4" />} onClick={() => setPts([])} disabled={!pts.length}>
              Clear
            </Button>
            <Badge tone="gray" className="ms-auto self-center">
              {pts.length} point{pts.length === 1 ? "" : "s"}
            </Badge>
          </div>
          {pts.length > 0 && (
            <ol className="max-h-56 space-y-1 overflow-auto font-mono text-[11px] text-ink-mute">
              {pts.map((p, i) => (
                <li key={i}>
                  {i + 1}. {p[0]}, {p[1]}
                </li>
              ))}
            </ol>
          )}
        </>
      }
    >
      <Card className="overflow-hidden">
        <PortalMap center={[31.5204, 74.3587]} zoom={14} height={440} className="!rounded-none" scrollWheelZoom>
          <ClickCatcher onClick={(p) => setPts((x) => [...x, p])} />
          {pts.length >= 3 ? (
            <Polygon positions={pts} pathOptions={{ color: "#c99a22", weight: 3, fillColor: "#146f45", fillOpacity: 0.25 }} />
          ) : pts.length === 2 ? (
            <Polyline positions={pts} pathOptions={{ color: "#c99a22", weight: 3, dashArray: "6 6" }} />
          ) : null}
          {pts.map((p, i) => (
            <CircleMarker key={i} center={p} radius={6} pathOptions={{ color: "#fff", weight: 2, fillColor: "#0f5a39", fillOpacity: 1 }}>
              <LTooltip direction="top" offset={[0, -6]}>
                {i + 1}
              </LTooltip>
            </CircleMarker>
          ))}
        </PortalMap>
      </Card>
      {pts.length < 2 ? (
        <EmptyState icon={<Ruler className="h-6 w-6" />} title="Drop at least two points" hint="Tip: trace a plot boundary on the satellite base map (layers button, top corner)." />
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !d ? (
        <Skeleton className="h-28" />
      ) : (
        <>
          <StatGrid>
            <StatCard label="Path length" value={dist(d.path_length_m)} icon={<Route className="h-5 w-5" />} />
            <StatCard label="Perimeter" value={pts.length >= 3 ? dist(d.perimeter_m) : "—"} icon={<Hexagon className="h-5 w-5" />} tone="blue" />
            <StatCard label="Area" value={pts.length >= 3 ? `${num(d.area_marla, 2)} marla` : "—"} hint={pts.length >= 3 ? `${num(d.area_kanal, 2)} kanal` : "add a 3rd point"} icon={<Ruler className="h-5 w-5" />} tone="gold" />
            <StatCard label="Acres" value={pts.length >= 3 ? num(d.area_acre, 3) : "—"} hint={pts.length >= 3 ? `${num(d.area_sqft)} sqft` : undefined} icon={<Hexagon className="h-5 w-5" />} tone="purple" />
          </StatGrid>
          <Card>
            <CardHeader title="Segments" subtitle={`Centroid ${d.centroid.lat}, ${d.centroid.lon}`} />
            <CardBody>
              <KeyValue cols={3} items={d.segments.map((s, i) => ({ label: `Leg ${i + 1} → ${i + 2}`, value: `${dist(s.distance_m)} · ${num(s.bearing_deg, 0)}°` }))} />
            </CardBody>
          </Card>
        </>
      )}
    </CalcShell>
  );
}

// ================================================================== generic (MCP-backed)
/** The MCP endpoint admits administrators only, so the tools list is fetched just for them. */
export function useMcpAdmin() {
  return isMcpAdmin(useAuth((s) => s.user));
}

export function useMcpTools() {
  const admin = useMcpAdmin();
  return useQuery({ queryKey: ["mcp", "tools/list"], queryFn: () => mcp.listTools(), staleTime: 5 * 60_000, enabled: admin });
}

export function GenericTool({ tool }: { tool: ToolCard }) {
  const admin = useMcpAdmin();
  const tq = useMcpTools();
  const def: McpTool | undefined = useMemo(() => tq.data?.tools.find((t) => t.name === tool.mcp_tool), [tq.data, tool.mcp_tool]);
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
      <Card>
        <CardHeader title="Run via MCP" subtitle={tool.mcp_tool ? <code>{tool.mcp_tool}</code> : "No MCP tool"} icon={<Terminal className="h-4 w-4" />} action={<ButtonLink to="/ai/mcp" variant="ghost" size="sm">Console</ButtonLink>} />
        <CardBody>
          {!admin ? (
            <EmptyState title="Admins only" hint="Running tools over MCP needs an administrator account. The portal's calculators and pages work for everyone." />
          ) : tq.isLoading ? (
            <Skeleton className="h-48" />
          ) : tq.error ? (
            <ErrorState error={tq.error} onRetry={() => tq.refetch()} />
          ) : def ? (
            <McpRunner key={def.name} def={def} toolKey={tool.key} />
          ) : (
            <EmptyState title="No interactive form for this tool yet" hint={<>Explore every capability in the <Link className="link" to="/ai/mcp">MCP console</Link>.</>} />
          )}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="About this tool" />
        <CardBody className="space-y-3 text-sm text-ink-soft dark:text-slate-300">
          <p>{tool.blurb}</p>
          {def?.description && <p className="whitespace-pre-line rounded-xl bg-brand-50/60 p-3 text-xs dark:bg-white/5">{def.description}</p>}
          <KeyValue items={[{ label: "Category", value: tool.category }, { label: "Phase", value: `Phase ${tool.phase}` }]} />
        </CardBody>
      </Card>
    </div>
  );
}

function McpRunner({ def, toolKey }: { def: McpTool; toolKey: string }) {
  const [values, setValues] = useState<FormValues>(() => initialValues(def.inputSchema));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [res, setRes] = useState<{ data: unknown; ms: number; isError?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const run = async () => {
    const { args, errors } = buildArgs(def.inputSchema, values);
    setErrors(errors);
    if (Object.keys(errors).length) return;
    setBusy(true);
    setErr(null);
    const t0 = performance.now();
    try {
      const r = await mcp.callTool(def.name, args);
      setRes({ data: parseToolResult(r), ms: Math.round(performance.now() - t0), isError: r.isError });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-4">
      <SchemaForm schema={def.inputSchema} values={values} onChange={setValues} errors={errors} />
      <div className="flex flex-wrap items-center gap-2">
        <Button icon={<Play className="h-4 w-4" />} loading={busy} onClick={run}>
          Run
        </Button>
        {res && <SaveProjectButton tool={toolKey} inputs={buildArgs(def.inputSchema, values).args} outputs={res.data} defaultName={def.name} />}
        {busy && <Spinner className="h-4 w-4" />}
      </div>
      {err != null && <ErrorState error={err} />}
      {res && (
        <div className="rounded-2xl border border-black/5 p-3 dark:border-white/10">
          <div className="mb-2 flex items-center gap-2 text-xs">
            <Badge tone={res.isError ? "red" : "green"}>{res.isError ? "error" : "ok"}</Badge>
            <span className="text-ink-mute">{res.ms} ms</span>
          </div>
          <div className="max-h-[480px] overflow-auto">
            <JsonView data={res.data} defaultOpen={2} />
          </div>
        </div>
      )}
    </div>
  );
}
