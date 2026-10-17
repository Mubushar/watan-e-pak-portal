import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Marker } from "react-leaflet";
import {
  ArrowRight,
  Building,
  Building2,
  CalendarRange,
  Car,
  CheckCircle2,
  Construction,
  Factory,
  FileImage,
  Hammer,
  Layers,
  LayoutGrid,
  Map as MapIcon,
  MapPin,
  Percent,
  RotateCcw,
  Ruler,
  ShoppingBag,
  Sparkles,
  Store,
  Users,
  Video,
} from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { compact, date, num, pct, titleCase } from "@/lib/format";
import { HERO, themedImage } from "@/lib/images";
import { cn } from "@/lib/utils";
import { Badge, ButtonLink, EmptyState, ErrorState, Modal, PageHeader, Progress, Skeleton, StatCard, StatusBadge, toneFor } from "@/components/ui";
import { PortalMap, pin } from "@/components/map/PortalMap";
import { AdSlot } from "@/components/ads/AdSlot";
import { ChipRow, FilterChip, MiniStat, fmtArea } from "@/components/gis/kit";
import type { BigProject, BigProjectDetail } from "@/components/gis/types";

const TYPE_ICON: Record<string, typeof Building> = {
  mall: ShoppingBag,
  tower: Building,
  mixed_use: Building2,
  compound_living: LayoutGrid,
  office_complex: Factory,
  plaza: Store,
};
const STATUS_ICON: Record<string, typeof Hammer> = { under_construction: Construction, completed: CheckCircle2, planned: Hammer };

export default function Projects() {
  const q = useApi<{ count: number; projects: BigProject[] }>("/bigprojects");
  const projects = q.data?.projects ?? [];
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [city, setCity] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  const facets = useMemo(() => {
    const count = (k: keyof BigProject) => {
      const m = new Map<string, number>();
      projects.forEach((p) => {
        const v = String(p[k] ?? "");
        if (v) m.set(v, (m.get(v) ?? 0) + 1);
      });
      return [...m.entries()].sort((a, b) => b[1] - a[1]);
    };
    return { types: count("project_type"), statuses: count("status"), cities: count("city") };
  }, [projects]);

  const list = projects.filter((p) => (!type || p.project_type === type) && (!status || p.status === status) && (!city || p.city === city));
  const occ = projects.filter((p) => p.occupancy_rate != null);
  const totalArea = projects.reduce((a, p) => a + (p.total_area ?? 0), 0);
  const anyFilter = type || status || city;

  return (
    <div className="pb-16">
      <PageHeader
        image={HERO.panorama}
        eyebrow="Mega projects"
        title={
          <>
            Landmark <span className="text-gradient">developments</span> reshaping Pakistan
          </>
        }
        subtitle="Malls, towers, mixed-use plazas and gated compounds — with live construction status, floor counts and occupancy."
        crumbs={[{ label: "Home", to: "/" }, { label: "Mega projects" }]}
      />

      <div className="container -mt-10 relative z-10 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {q.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <StatCard label="Projects" value={projects.length} icon={<Building2 className="h-5 w-5" />} hint={`${facets.cities.length} cities`} />
            <StatCard label="Under construction" value={projects.filter((p) => p.status === "under_construction").length} icon={<Construction className="h-5 w-5" />} tone="gold" />
            <StatCard label="Total floor area" value={fmtArea(totalArea)} icon={<Ruler className="h-5 w-5" />} tone="blue" />
            <StatCard label="Avg occupancy" value={occ.length ? pct(occ.reduce((a, p) => a + (p.occupancy_rate ?? 0), 0) / occ.length, 0) : "—"} icon={<Users className="h-5 w-5" />} tone="purple" hint={`${occ.length} reporting`} />
          </>
        )}
      </div>

      <div className="container mt-8">
        {/* filters */}
        <div className="card mb-6 space-y-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="font-display text-sm font-bold text-ink dark:text-white">Filter projects</p>
            {anyFilter && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setType("");
                  setStatus("");
                  setCity("");
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
            {facets.types.map(([t, n]) => {
              const Icon = TYPE_ICON[t] ?? Building2;
              return (
                <FilterChip key={t} active={type === t} onClick={() => setType(type === t ? "" : t)} count={n}>
                  <Icon className="h-3.5 w-3.5" /> {titleCase(t)}
                </FilterChip>
              );
            })}
          </ChipRow>
          <div className="flex flex-col gap-3 sm:flex-row">
            <ChipRow className="sm:flex-1">
              <FilterChip active={!status} onClick={() => setStatus("")}>
                Any status
              </FilterChip>
              {facets.statuses.map(([s, n]) => (
                <FilterChip key={s} active={status === s} onClick={() => setStatus(status === s ? "" : s)} count={n}>
                  {titleCase(s)}
                </FilterChip>
              ))}
            </ChipRow>
            <ChipRow className="sm:flex-1 sm:justify-end">
              <FilterChip active={!city} onClick={() => setCity("")}>
                All cities
              </FilterChip>
              {facets.cities.map(([c, n]) => (
                <FilterChip key={c} active={city === c} onClick={() => setCity(city === c ? "" : c)} count={n}>
                  {c}
                </FilterChip>
              ))}
            </ChipRow>
          </div>
        </div>

        {q.isLoading ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-96" />
            ))}
          </div>
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !list.length ? (
          <EmptyState title="No projects match" hint="Try a different type, status or city." icon={<Building2 className="h-6 w-6" />} />
        ) : (
          <motion.div layout className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>
              {list.map((p, i) => (
                <ProjectCard key={p.id} p={p} i={i} onOpen={() => setOpenId(p.id)} />
              ))}
            </AnimatePresence>
          </motion.div>
        )}

        <AdSlot slot="banner" className="mt-12" />
      </div>

      <ProjectModal id={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}

function ProjectCard({ p, i, onOpen }: { p: BigProject; i: number; onOpen: () => void }) {
  const Icon = TYPE_ICON[p.project_type] ?? Building2;
  const SIcon = STATUS_ICON[p.status] ?? Hammer;
  const occ = p.occupancy_rate;
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.94 }}
      transition={{ duration: 0.4, delay: Math.min(i, 9) * 0.06 }}
      onClick={onOpen}
      className="card card-hover group flex flex-col overflow-hidden text-start"
    >
      <div className="relative aspect-[4/3] overflow-hidden">
        <img src={themedImage(p.id, p.project_type)} alt={p.name} loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110" />
        <div className="absolute inset-0 bg-gradient-to-t from-brand-950/90 via-brand-950/20 to-transparent" />
        <div className="absolute start-3 top-3 flex flex-wrap gap-1.5">
          <span className="chip bg-white/90 text-brand-800 shadow dark:bg-black/50 dark:text-white">
            <Icon className="h-3 w-3" /> {titleCase(p.project_type)}
          </span>
        </div>
        <div className="absolute end-3 top-3">
          <Badge tone={toneFor(p.status)} icon={<SIcon className="h-3 w-3" />} className="shadow">
            {titleCase(p.status)}
          </Badge>
        </div>
        <div className="absolute bottom-3 start-4 end-4 text-white">
          <h3 className="font-display text-xl font-bold leading-tight drop-shadow">{p.name}</h3>
          <p className="mt-0.5 flex items-center gap-1 text-xs text-white/80">
            <MapPin className="h-3 w-3 text-gold-300" /> {p.city}
          </p>
        </div>
      </div>
      <div className="flex flex-1 flex-col p-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
              <Layers className="h-4 w-4" />
            </span>
            <span>
              <b className="block text-ink dark:text-white">{p.floor_count ?? "—"}</b>
              <span className="text-[11px] text-ink-mute">floors</span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gold-50 text-gold-700 dark:bg-gold-500/15 dark:text-gold-200">
              <Ruler className="h-4 w-4" />
            </span>
            <span>
              <b className="block text-ink dark:text-white">{fmtArea(p.total_area)}</b>
              <span className="text-[11px] text-ink-mute">total area</span>
            </span>
          </div>
        </div>
        <div className="mt-4">
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="font-semibold text-ink-soft dark:text-slate-300">Occupancy</span>
            <span className="font-bold tabular-nums text-ink dark:text-white">{occ != null ? pct(occ, 0) : "Not yet open"}</span>
          </div>
          <Progress value={(occ ?? 0) * 100} tone={occ == null ? "blue" : occ >= 0.7 ? "green" : occ >= 0.4 ? "gold" : "red"} />
        </div>
        <span className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 dark:text-brand-300">
          View project details <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-1 rtl:rotate-180 rtl:group-hover:-translate-x-1" />
        </span>
      </div>
    </motion.button>
  );
}

function ProjectModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useApi<BigProjectDetail>(id ? `/bigprojects/${id}` : null);
  const p = q.data;
  const occ = p?.occupancy_rate;
  const listCount = (v: unknown) => (Array.isArray(v) ? v.length : v && typeof v === "object" ? Object.keys(v).length : 0);
  return (
    <Modal open={!!id} onClose={onClose} title={p?.name ?? "Project"} subtitle={p ? `${titleCase(p.project_type)} · ${p.city_name ?? ""}` : undefined} size="lg">
      {q.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-56" />
          <Skeleton className="h-24" />
        </div>
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : p ? (
        <div className="space-y-6">
          <div className="relative -mx-6 -mt-5 h-56 overflow-hidden sm:h-64">
            <img src={p.image_urls?.[0] ?? themedImage(p.id, p.project_type)} alt="" className="h-full w-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-brand-950/80 to-transparent" />
            <div className="absolute bottom-4 start-6 flex flex-wrap gap-2">
              <StatusBadge status={p.status} className="shadow" />
              {p.developer && <span className="chip bg-white/90 text-brand-800 shadow">By {p.developer}</span>}
            </div>
          </div>

          {p.description && <p className="text-sm text-ink-soft dark:text-slate-300">{p.description}</p>}

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <MiniStat label="Floors" value={p.floor_count ?? "—"} />
            <MiniStat label="Total area" value={fmtArea(p.total_area)} />
            <MiniStat label="Units" value={p.total_units ? num(p.total_units) : "—"} hint={p.leased_units ? `${p.leased_units} leased` : undefined} />
            <MiniStat label="Parking" value={p.total_parking_spaces ? compact(p.total_parking_spaces) : "—"} hint="spaces" />
            {!!p.total_retail_space && <MiniStat label="Retail space" value={fmtArea(p.total_retail_space)} />}
            {!!p.total_office_space && <MiniStat label="Office space" value={fmtArea(p.total_office_space)} />}
            {!!p.total_residential_units && <MiniStat label="Residences" value={num(p.total_residential_units)} />}
            <MiniStat label="Timeline" value={p.completion_date ? date(p.completion_date, { month: "short", year: "numeric" }) : "—"} hint={p.start_date ? `from ${date(p.start_date, { month: "short", year: "numeric" })}` : undefined} />
          </div>

          <div>
            <div className="mb-1.5 flex justify-between text-xs">
              <span className="inline-flex items-center gap-1 font-semibold text-ink-soft dark:text-slate-300">
                <Percent className="h-3.5 w-3.5" /> Occupancy
              </span>
              <span className="font-bold">{occ != null ? pct(occ, 0) : "Not yet open"}</span>
            </div>
            <Progress value={(occ ?? 0) * 100} tone={occ == null ? "blue" : occ >= 0.7 ? "green" : occ >= 0.4 ? "gold" : "red"} className="h-3" />
          </div>

          <div>
            <p className="label">Amenities</p>
            {p.amenities?.length ? (
              <div className="flex flex-wrap gap-1.5">
                {p.amenities.map((a, i) => (
                  <motion.span key={a} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.04 }} className="chip bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-brand-100">
                    <Sparkles className="h-3 w-3 text-gold-600" /> {a}
                  </motion.span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-mute">No amenities listed yet.</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["Floor plans", listCount(p.floor_plans), LayoutGrid],
              ["Maps", listCount(p.maps), MapIcon],
              ["Multimedia", listCount(p.multimedia), Video],
              ["Image library", listCount(p.image_library), FileImage],
            ].map(([label, n, Icon]) => {
              const I = Icon as typeof MapIcon;
              return (
                <div key={String(label)} className={cn("flex items-center gap-2 rounded-xl border p-3", (n as number) > 0 ? "border-brand-200 bg-brand-50/50 dark:border-brand-500/30 dark:bg-white/5" : "border-dashed border-black/10 dark:border-white/10")}>
                  <I className={cn("h-4 w-4", (n as number) > 0 ? "text-brand-700 dark:text-brand-300" : "text-ink-mute")} />
                  <span className="min-w-0">
                    <b className="block text-sm text-ink dark:text-white">{n as number}</b>
                    <span className="block truncate text-[11px] text-ink-mute">{label as string}</span>
                  </span>
                </div>
              );
            })}
          </div>

          {p.latitude != null && p.longitude != null && (
            <div>
              <p className="label">Location</p>
              <PortalMap height={240} center={[p.latitude, p.longitude]} zoom={14} switcher={false}>
                <Marker position={[p.latitude, p.longitude]} icon={pin("project", { pulse: true, label: p.name })} />
              </PortalMap>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {p.city_name && (
              <ButtonLink to={`/cities/${encodeURIComponent(p.city_name)}`} variant="soft" size="sm" icon={<MapPin className="h-3.5 w-3.5" />} onClick={onClose}>
                {p.city_name} guide
              </ButtonLink>
            )}
            {p.scheme_id && (
              <ButtonLink to={`/schemes?scheme=${p.scheme_id}`} variant="outline" size="sm" icon={<CalendarRange className="h-3.5 w-3.5" />} onClick={onClose}>
                View scheme
              </ButtonLink>
            )}
            <Link to="/map" onClick={onClose} className="btn btn-ghost btn-sm">
              <Car className="h-3.5 w-3.5" /> Route & nearby on map
            </Link>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
