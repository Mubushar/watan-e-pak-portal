/**
 * Recharts wrappers in the brand palette. All are responsive; give the parent a height.
 *   <AreaTrend data={rows} x="year" series={[{ key: "base", label: "Base" }]} />
 */
import type { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { compact } from "@/lib/format";

export const PALETTE = ["#146f45", "#c99a22", "#2c7fb8", "#7c3aed", "#e4572e", "#17a398", "#8a5a35", "#64748b"];

export interface Series {
  key: string;
  label?: string;
  color?: string;
}

const axis = { fontSize: 11, fill: "currentColor" };
const tooltipStyle = {
  contentStyle: { borderRadius: 12, border: "1px solid rgba(0,0,0,.06)", boxShadow: "0 8px 24px -8px rgba(0,0,0,.2)", fontSize: 12 },
  labelStyle: { fontWeight: 600 },
};

function Frame({ height = 260, children }: { height?: number; children: ReactNode }) {
  return (
    <div style={{ height }} className="w-full text-ink-mute dark:text-slate-400">
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}

export function AreaTrend({
  data,
  x,
  series,
  height,
  format = compact,
  stacked,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: Series[];
  height?: number;
  format?: (v: number) => string;
  stacked?: boolean;
}) {
  return (
    <Frame height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color ?? PALETTE[i % PALETTE.length]} stopOpacity={0.35} />
              <stop offset="100%" stopColor={s.color ?? PALETTE[i % PALETTE.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.12} vertical={false} />
        <XAxis dataKey={x} tick={axis} tickLine={false} axisLine={false} />
        <YAxis tick={axis} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} width={56} />
        <Tooltip {...tooltipStyle} formatter={(v: number) => format(Number(v))} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label ?? s.key}
            stroke={s.color ?? PALETTE[i % PALETTE.length]}
            strokeWidth={2.5}
            fill={`url(#g-${s.key})`}
            stackId={stacked ? "1" : undefined}
          />
        ))}
      </AreaChart>
    </Frame>
  );
}

export function LineTrend({ data, x, series, height, format = compact }: { data: Record<string, unknown>[]; x: string; series: Series[]; height?: number; format?: (v: number) => string }) {
  return (
    <Frame height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.12} vertical={false} />
        <XAxis dataKey={x} tick={axis} tickLine={false} axisLine={false} />
        <YAxis tick={axis} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} width={56} />
        <Tooltip {...tooltipStyle} formatter={(v: number) => format(Number(v))} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s, i) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label ?? s.key} stroke={s.color ?? PALETTE[i % PALETTE.length]} strokeWidth={2.5} dot={false} />
        ))}
      </LineChart>
    </Frame>
  );
}

export function Bars({
  data,
  x,
  series,
  height,
  format = compact,
  horizontal,
  stacked,
  colorByIndex,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: Series[];
  height?: number;
  format?: (v: number) => string;
  horizontal?: boolean;
  stacked?: boolean;
  colorByIndex?: boolean;
}) {
  return (
    <Frame height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.12} vertical={!!horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tick={axis} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} />
            <YAxis type="category" dataKey={x} tick={axis} tickLine={false} axisLine={false} width={110} />
          </>
        ) : (
          <>
            <XAxis dataKey={x} tick={axis} tickLine={false} axisLine={false} />
            <YAxis tick={axis} tickLine={false} axisLine={false} tickFormatter={(v) => format(Number(v))} width={56} />
          </>
        )}
        <Tooltip {...tooltipStyle} formatter={(v: number) => format(Number(v))} cursor={{ fill: "currentColor", fillOpacity: 0.05 }} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label ?? s.key} fill={s.color ?? PALETTE[i % PALETTE.length]} radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} stackId={stacked ? "1" : undefined} maxBarSize={44}>
            {colorByIndex && data.map((_, j) => <Cell key={j} fill={PALETTE[j % PALETTE.length]} />)}
          </Bar>
        ))}
      </BarChart>
    </Frame>
  );
}

export function Donut({
  data,
  height = 240,
  format = compact,
  center,
}: {
  data: { name: string; value: number; color?: string }[];
  height?: number;
  format?: (v: number) => string;
  center?: ReactNode;
}) {
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="88%" paddingAngle={2} stroke="none">
            {data.map((d, i) => (
              <Cell key={d.name} fill={d.color ?? PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip {...tooltipStyle} formatter={(v: number) => format(Number(v))} />
        </PieChart>
      </ResponsiveContainer>
      {center && <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">{center}</div>}
    </div>
  );
}

export function Legendish({ data }: { data: { name: string; value: number; color?: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {data.map((d, i) => (
        <span key={d.name} className="inline-flex items-center gap-1.5 text-xs text-ink-soft dark:text-slate-300">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: d.color ?? PALETTE[i % PALETTE.length] }} />
          {d.name}
          <span className="font-semibold">{d.value}</span>
        </span>
      ))}
    </div>
  );
}
