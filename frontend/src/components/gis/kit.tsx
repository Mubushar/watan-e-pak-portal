/**
 * Small building blocks shared by the GIS / insights pages (map explorer, insights,
 * news, societies, city pages, projects). Local to src/components/gis.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { useMapEvents } from "react-leaflet";
import type L from "leaflet";
import { ExternalLink, FileText } from "lucide-react";
import { apiUrl, type Query } from "@/lib/api";
import { pct, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Modal, Spinner, type Tone } from "@/components/ui";
import { AreaTrend, PALETTE } from "@/components/ui/charts";
import { usePrefs } from "@/store/prefs";
import type { Scenarios } from "./types";

// ---------------------------------------------------------------- chips
export function FilterChip({
  active,
  onClick,
  children,
  color,
  count,
  className,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  color?: string;
  count?: number;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-all",
        active
          ? "border-transparent bg-brand-700 text-white shadow-soft dark:bg-brand-600"
          : "border-black/10 bg-white/70 text-ink-soft hover:border-brand-300 hover:text-brand-800 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:border-brand-400/40",
        className,
      )}
    >
      {color && <span className="h-2 w-2 rounded-full ring-2 ring-white/60" style={{ background: color }} />}
      {children}
      {count !== undefined && (
        <span className={cn("rounded-full px-1.5 text-[10px]", active ? "bg-white/20" : "bg-black/5 dark:bg-white/10")}>{count}</span>
      )}
    </button>
  );
}

export function ChipRow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1", className)}>{children}</div>;
}

// ---------------------------------------------------------------- sentiment
export function sentimentTone(s?: string | null): Tone {
  if (s === "positive") return "green";
  if (s === "negative") return "red";
  return "gray";
}
export const SENTIMENT_COLOR: Record<string, string> = { positive: "#16a34a", neutral: "#64748b", negative: "#dc2626" };

/** -100..100 impact meter: fills from the centre towards the sign of the value. */
export function ImpactMeter({ value, className, showLabel = true }: { value: number; className?: string; showLabel?: boolean }) {
  const v = Math.max(-100, Math.min(100, value));
  const w = Math.abs(v) / 2;
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
        <div className="absolute inset-y-0 start-1/2 w-px bg-black/20 dark:bg-white/30" />
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${w}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className={cn("absolute inset-y-0 rounded-full", v >= 0 ? "start-1/2 bg-gradient-to-r from-emerald-400 to-emerald-600 rtl:bg-gradient-to-l" : "end-1/2 bg-gradient-to-l from-red-400 to-red-600 rtl:bg-gradient-to-r")}
        />
      </div>
      {showLabel && <span className={cn("w-10 text-end text-xs font-bold tabular-nums", v > 0 ? "text-emerald-600" : v < 0 ? "text-red-600" : "text-ink-mute")}>{v > 0 ? `+${Math.round(v)}` : Math.round(v)}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- reports
/** Theme of the app, for the backend's `?theme=` HTML reports. */
export function useUiTheme(): "light" | "dark" {
  const theme = usePrefs((s) => s.theme);
  const [dark, setDark] = useState(() => typeof document !== "undefined" && document.documentElement.classList.contains("dark"));
  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, [theme]);
  return dark ? "dark" : "light";
}

export interface ReportRef {
  title: string;
  path: string;
  query?: Query;
}

/** Modal that embeds a backend HTML report (`/gis/report/...`, `/gis/outlook/...`). */
export function ReportModal({ report, onClose }: { report: ReportRef | null; onClose: () => void }) {
  const theme = useUiTheme();
  const lang = usePrefs((s) => s.lang);
  const [loading, setLoading] = useState(true);
  const src = report ? apiUrl(report.path, { ...report.query, theme, lang }) : "";
  useEffect(() => setLoading(true), [src]);
  return (
    <Modal open={!!report} onClose={onClose} title={report?.title} subtitle="Generated live by the Watan-e-Pak GIS engine" size="xl">
      {report && (
        <div className="relative -mx-6 -my-5">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center gap-2 bg-white/60 text-sm text-ink-mute dark:bg-black/30">
              <Spinner /> Building report…
            </div>
          )}
          <iframe title={report.title} src={src} onLoad={() => setLoading(false)} className="h-[72vh] w-full border-0 bg-white" />
          <div className="flex justify-end border-t border-black/5 px-6 py-3 dark:border-white/10">
            <a href={src} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm">
              <ExternalLink className="h-3.5 w-3.5" /> Open in new tab
            </a>
          </div>
        </div>
      )}
    </Modal>
  );
}

export function ReportButton({ onClick, children, icon, disabled }: { onClick: () => void; children: ReactNode; icon?: ReactNode; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="group disabled:cursor-not-allowed disabled:opacity-50 flex w-full items-center gap-3 rounded-xl border border-black/5 bg-white/60 px-3 py-2.5 text-start text-sm font-semibold text-ink transition hover:border-brand-300 hover:bg-brand-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-100 dark:hover:bg-white/10"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-white">{icon ?? <FileText className="h-4 w-4" />}</span>
      <span className="min-w-0 flex-1 truncate">{children}</span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-ink-mute transition group-hover:text-brand-700" />
    </button>
  );
}

// ---------------------------------------------------------------- forecast
const SCENARIO_COLORS: Record<string, string> = { optimistic: "#146f45", base: "#c99a22", pessimistic: "#e4572e", stress: "#64748b" };

/** Multi-scenario price-per-marla forecast from `forecast.scenarios`. */
export function ForecastChart({
  scenarios,
  metric = "price_per_marla",
  height = 260,
  keys = ["optimistic", "base", "pessimistic"],
}: {
  scenarios?: Scenarios;
  metric?: "price_per_marla" | "market_value" | "rental_value";
  height?: number;
  keys?: ("optimistic" | "base" | "pessimistic" | "stress")[];
}) {
  const { rows, series } = useMemo(() => {
    const byYear = new Map<number, Record<string, number>>();
    const series = keys
      .filter((k) => scenarios?.[k]?.series?.length)
      .map((k) => {
        const sc = scenarios![k]!;
        sc.series.forEach((pt) => {
          const row = byYear.get(pt.year) ?? { year: pt.year };
          row[k] = pt[metric];
          byYear.set(pt.year, row);
        });
        return { key: k, label: `${sc.label} · ${pct(sc.price_cagr)} CAGR`, color: SCENARIO_COLORS[k] };
      });
    return { rows: [...byYear.values()].sort((a, b) => a.year! - b.year!), series };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarios, metric, keys.join(",")]);
  if (!rows.length) return <p className="py-10 text-center text-sm text-ink-mute">No forecast available.</p>;
  return <AreaTrend data={rows} x="year" series={series} height={height} format={(v) => pkrShort(v, false)} />;
}

// ---------------------------------------------------------------- factor bars
export function FactorBars({ scores, weights }: { scores: Record<string, number>; weights?: Record<string, number> }) {
  const items = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  return (
    <div className="space-y-3">
      {items.map(([k, v], i) => (
        <div key={k}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="font-semibold text-ink-soft dark:text-slate-300">
              {titleCase(k)}
              {weights?.[k] !== undefined && <span className="ms-1.5 font-normal text-ink-mute">w {Math.round(weights[k]! * 100)}%</span>}
            </span>
            <span className="font-bold tabular-nums text-ink dark:text-white">{Math.round(v)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${v}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.9, delay: i * 0.05 }}
              className="h-full rounded-full"
              style={{ background: v >= 70 ? "linear-gradient(90deg,#1f8a57,#146f45)" : v >= 55 ? "linear-gradient(90deg,#f2dd8f,#c99a22)" : "linear-gradient(90deg,#f59e0b,#e4572e)" }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function bandTone(band?: string | null): Tone {
  const b = (band ?? "").toLowerCase();
  if (/(strong|healthy|hot|expanding|bull)/.test(b)) return "green";
  if (/(moderate|stable|balanced|neutral)/.test(b)) return "gold";
  if (/(weak|soft|cool|declin|bear|contract)/.test(b)) return "red";
  return "gray";
}

// ---------------------------------------------------------------- misc
export function entriesToDonut(obj?: Record<string, number> | null) {
  return Object.entries(obj ?? {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value], i) => ({ name: titleCase(name), value, color: PALETTE[i % PALETTE.length] }));
}

/** Backend returns 200 + `{error}` for some not-found lookups. */
export function backendError(d: unknown): string | null {
  if (d && typeof d === "object" && "error" in d && typeof (d as { error: unknown }).error === "string") return (d as { error: string }).error;
  return null;
}

/** Map click handler (react-leaflet child). */
export function MapClick({ onClick, enabled = true }: { onClick: (lat: number, lon: number) => void; enabled?: boolean }) {
  useMapEvents({
    click(e) {
      if (enabled) onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export function fmtArea(sqft?: number | null): string {
  if (!sqft) return "—";
  if (sqft >= 1_000_000) return `${(sqft / 1_000_000).toFixed(2)}M sqft`;
  if (sqft >= 1000) return `${Math.round(sqft / 1000)}K sqft`;
  return `${Math.round(sqft)} sqft`;
}

/** Fit a Leaflet map to [lat, lon] points (no-op when empty). */
export function fitTo(map: L.Map | null, pts: [number, number][], maxZoom = 14, pad: { start?: number; bottom?: number } = {}) {
  if (!map || !pts.length) return;
  const rtl = document.documentElement.dir === "rtl";
  const s = 48 + (pad.start ?? 0);
  const b = 48 + (pad.bottom ?? 0);
  if (pts.length === 1) pts = [pts[0]!, pts[0]!];
  map.flyToBounds(pts, { paddingTopLeft: [rtl ? 48 : s, 48], paddingBottomRight: [rtl ? s : 48, b], maxZoom, duration: 0.8 });
}

/** Glass panel surface. */
export function Glass({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("glass rounded-2xl shadow-soft", className)}>{children}</div>;
}

export function MiniStat({ label, value, hint, className }: { label: ReactNode; value: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl bg-brand-50/60 px-3 py-2.5 dark:bg-white/5", className)}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-ink-mute dark:text-slate-400">{label}</p>
      <p className="mt-0.5 truncate font-display text-base font-bold text-ink dark:text-white">{value}</p>
      {hint && <p className="truncate text-[11px] text-ink-mute">{hint}</p>}
    </div>
  );
}
