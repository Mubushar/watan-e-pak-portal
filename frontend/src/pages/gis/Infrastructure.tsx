/**
 * Infrastructure & development mega projects that affect real estate — ring roads, motorways,
 * expressways, transit, rail, new sectors, industrial / economic zones, airports, business
 * districts — on a map and as a filterable list with each project's expected price effect.
 */
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import type L from "leaflet";
import { Compass, Construction, Info, MapPin, RotateCcw, Route, TrendingUp } from "lucide-react";
import { HERO } from "@/lib/images";
import { cn } from "@/lib/utils";
import { ButtonLink, EmptyState, ErrorState, PageHeader, Skeleton, StatCard } from "@/components/ui";
import { PortalMap } from "@/components/map/PortalMap";
import { ChipRow, FilterChip, fitTo } from "@/components/gis/kit";
import { MEGA_TYPES, MegaProjectCard, MegaProjectLayer, megaColor, useMegaProjects, type MegaProject } from "@/components/gis/MegaProjects";
import { usePrefs } from "@/store/prefs";

const STATUSES: [string, string][] = [
  ["under_construction", "Under construction"],
  ["approved", "Approved"],
  ["planned", "Planned"],
  ["completed", "Recently completed"],
];

const toBounds = (p: MegaProject): [number, number][] => [
  [p.bounds[0], p.bounds[1]],
  [p.bounds[2], p.bounds[3]],
];

export default function Infrastructure() {
  const q = useMegaProjects();
  const all = q.data?.projects ?? [];
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [province, setProvince] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  const [zoom, setZoom] = useState(5);
  const lang = usePrefs((s) => s.lang) === "ur" ? "both" : "en";
  const { hash } = useLocation();

  const provinces = useMemo(() => [...new Set(all.map((p) => p.province))].sort(), [all]);
  const list = all.filter((p) => (!type || p.type === type) && (!status || p.status === status) && (!province || p.province === province));
  const shown = useMemo(() => new Set(list.map((p) => p.type)), [list]);
  const anyFilter = type || status || province;

  useEffect(() => {
    if (!map) return;
    const z = () => setZoom(map.getZoom());
    map.on("zoomend", z);
    return () => void map.off("zoomend", z);
  }, [map]);

  const focus = (p: MegaProject) => {
    setSel(p.id);
    fitTo(map, toBounds(p), p.geometry?.type === "line" ? 12 : 13);
    document.getElementById("infra-map")?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  // /infrastructure#<id> opens on that project.
  useEffect(() => {
    const id = hash.slice(1);
    const p = id && all.find((x) => x.id === id);
    if (p && map) {
      setSel(p.id);
      fitTo(map, toBounds(p), 12);
    }
  }, [hash, all, map]);

  return (
    <div className="pb-16">
      <PageHeader
        image={HERO.panorama}
        eyebrow="Infrastructure"
        title={
          <>
            Mega projects that <span className="text-gradient">move land prices</span>
          </>
        }
        subtitle="Ring roads, motorways, expressways, mass transit, new sectors, industrial and economic zones, airports and business districts — what is being built, where, and how far its effect on property reaches."
        crumbs={[{ label: "Home", to: "/" }, { label: "Infrastructure" }]}
      />

      <div className="container relative z-10 -mt-10 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {q.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <StatCard label="Projects" value={all.length} icon={<Route className="h-5 w-5" />} hint={`${provinces.length} provinces`} />
            <StatCard label="Under construction" value={all.filter((p) => p.status === "under_construction").length} icon={<Construction className="h-5 w-5" />} tone="gold" />
            <StatCard label="High price effect" value={all.filter((p) => p.uplift === "high").length} icon={<TrendingUp className="h-5 w-5" />} tone="blue" />
            <StatCard
              label="Road & rail length"
              value={`${Math.round(all.reduce((a, p) => a + (p.length_km ?? 0), 0)).toLocaleString()} km`}
              icon={<MapPin className="h-5 w-5" />}
              tone="purple"
            />
          </>
        )}
      </div>

      <div className="container mt-8 space-y-6">
        <div className="card space-y-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="font-display text-sm font-bold">Filter projects</p>
            {anyFilter && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setType("");
                  setStatus("");
                  setProvince("");
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" /> Reset
              </button>
            )}
          </div>
          <ChipRow>
            <FilterChip active={!type} onClick={() => setType("")}>
              All types
            </FilterChip>
            {MEGA_TYPES.filter((t) => all.some((p) => p.type === t.key)).map((t) => (
              <FilterChip
                key={t.key}
                active={type === t.key}
                onClick={() => setType(type === t.key ? "" : t.key)}
                color={t.color}
                count={all.filter((p) => p.type === t.key).length}
              >
                <t.icon className="h-3.5 w-3.5" /> {t.label}
              </FilterChip>
            ))}
          </ChipRow>
          <div className="flex flex-col gap-3 sm:flex-row">
            <ChipRow className="sm:flex-1">
              <FilterChip active={!status} onClick={() => setStatus("")}>
                Any status
              </FilterChip>
              {STATUSES.filter(([k]) => all.some((p) => p.status === k)).map(([k, l]) => (
                <FilterChip key={k} active={status === k} onClick={() => setStatus(status === k ? "" : k)} count={all.filter((p) => p.status === k).length}>
                  {l}
                </FilterChip>
              ))}
            </ChipRow>
            <ChipRow className="sm:flex-1 sm:justify-end">
              <FilterChip active={!province} onClick={() => setProvince("")}>
                All provinces
              </FilterChip>
              {provinces.map((p) => (
                <FilterChip key={p} active={province === p} onClick={() => setProvince(province === p ? "" : p)}>
                  {p}
                </FilterChip>
              ))}
            </ChipRow>
          </div>
        </div>

        <div id="infra-map" className="card overflow-hidden p-0">
          <PortalMap height={480} className="rounded-none" scrollWheelZoom zoom={5} onReady={setMap}>
            <MegaProjectLayer projects={list} types={shown} lang={lang} zoom={zoom} selected={sel} annotate />
          </PortalMap>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-black/5 px-4 py-2.5 text-[11px] dark:border-white/10">
            {MEGA_TYPES.filter((t) => shown.has(t.key)).map((t) => (
              <span key={t.key} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: t.color }} /> {t.label}
              </span>
            ))}
            <span className="ms-auto text-ink-mute">Solid: built · long dashes: under construction · dots: approved / planned</span>
          </div>
        </div>

        {q.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-64" />
            ))}
          </div>
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !list.length ? (
          <EmptyState title="No projects match" hint="Try a different type, status or province." icon={<Route className="h-6 w-6" />} />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((p) => (
              <button
                key={p.id}
                id={p.id}
                type="button"
                onClick={() => focus(p)}
                className={cn("card card-hover border-t-4 p-4 text-start", sel === p.id && "ring-2 ring-brand-500")}
                style={{ borderTopColor: megaColor(p.type) }}
              >
                <MegaProjectCard p={p} />
              </button>
            ))}
          </div>
        )}

        <div className="flex flex-col items-start gap-3 rounded-2xl bg-brand-50/70 p-4 text-sm sm:flex-row sm:items-center dark:bg-white/5">
          <Info className="h-5 w-5 shrink-0 text-brand-700" />
          <p className="flex-1 text-ink-soft dark:text-slate-300">{q.data?.note}</p>
          <ButtonLink to="/map" variant="outline" size="sm" icon={<Compass className="h-4 w-4" />}>
            Draw a study area on the map
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}
