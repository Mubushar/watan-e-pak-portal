import { Fragment, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, LayoutGrid, List, SearchX, SlidersHorizontal, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { City, PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { pkrShort, titleCase } from "@/lib/format";
import { Button, EmptyState, Field, Input, Segmented, Select, Sheet, Skeleton, TopBar } from "@/components/ui";
import { PropertyCard, PropertyRow } from "@/components/PropertyCard";
import { groupHref, priceSpan, UnitGroupCard } from "@/components/UnitGroupCard";
import { groupProjectUnits, isGroup, projectNameOf, unitTypeOf } from "@/lib/projectGroups";
import { AdSlot, BannerSpacer, useNativeBanner } from "@/components/Ads";

/** Listings between in-feed ads. */
const AD_EVERY = 6;

const CATEGORIES = ["house", "apartment", "plot", "shop", "office", "floor", "building"];
const PRICE_STEPS = [0, 2_500_000, 5_000_000, 10_000_000, 20_000_000, 35_000_000, 50_000_000, 100_000_000, 250_000_000];
/** Every /search filter, so links from the assistant ("See all …") show exactly what it found. */
const FILTER_KEYS = ["purpose", "city", "category", "use_type", "bedrooms", "min_bathrooms", "min_price", "max_price", "min_marla", "max_marla", "featured", "feature", "near", "near_km", "near_place"] as const;
type Filters = Partial<Record<(typeof FILTER_KEYS)[number], string>>;
/** `near=` kinds the backend understands. */
const NEAR_KINDS = ["school", "mosque", "hospital", "market", "park", "transport"];

function chipLabel(k: string, v: string, f: Filters): string {
  const km = f.near_km ?? "2";
  switch (k) {
    case "min_price":
      return `≥ ${pkrShort(Number(v))}`;
    case "max_price":
      return `≤ ${pkrShort(Number(v))}`;
    case "bedrooms":
      return `${v}+ beds`;
    case "min_bathrooms":
      return `${v}+ baths`;
    case "min_marla":
      return `≥ ${v} marla`;
    case "max_marla":
      return `≤ ${v} marla`;
    case "featured":
      return "Featured";
    case "feature":
      return `With “${v}”`;
    case "near":
      return `Near a ${v} (${km} km)`;
    case "near_place":
      return `Within ${km} km of ${v}`;
    default:
      return titleCase(v);
  }
}

export default function Explore() {
  const [sp, setSp] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"grid" | "list">("grid");
  useNativeBanner();
  const filters: Filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, sp.get(k) ?? undefined]).filter(([, v]) => v));
  const [draft, setDraft] = useState<Filters>(filters);
  const cities = useApi<{ cities: City[] }>("/cities");
  // One project's units (from a project card): filtered here; /search doesn't know projects.
  const project = sp.get("project") ?? "";
  const unitType = sp.get("unit_type") ?? "";
  const q = useApi<PropertyList>("/search", {
    ...filters,
    featured: filters.featured ? true : undefined,
    limit: 600,
  });
  const results = useMemo(
    () => (q.data?.results ?? []).filter((p) => (!project || p.project_id === project) && (!unitType || unitTypeOf(p) === unitType)),
    [q.data, project, unitType],
  );
  // Big project inventories: one card per unit type, unless one project is open.
  const shown = useMemo(() => (project ? results : groupProjectUnits(results)), [results, project]);
  const projectUnits = useMemo(() => (project ? (q.data?.results ?? []).filter((p) => p.project_id === project) : []), [q.data, project]);
  const setUnitType = (t: string) => {
    const next = new URLSearchParams(sp);
    if (t) next.set("unit_type", t);
    else next.delete("unit_type");
    setSp(next, { replace: true });
  };

  const apply = (f: Filters) => {
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v) next.set(k, v);
    setSp(next, { replace: true });
  };
  // near_km only qualifies near / near_place; it's shown inside their chips.
  const chips = Object.entries(filters)
    .filter(([k]) => k !== "near_km")
    .map(([k, v]) => ({ key: k, label: chipLabel(k, v!, filters) }));
  const nearest = q.data?.nearest_outside_radius ?? [];
  const placeMissing = q.data?.near_place && !q.data.near_place.found;

  return (
    <div>
      <TopBar
        title="Explore"
        actions={
          <>
            <Segmented
              value={view}
              onChange={setView}
              className="hidden sm:flex"
              options={[
                { value: "grid", label: "", icon: <LayoutGrid className="h-4 w-4" /> },
                { value: "list", label: "", icon: <List className="h-4 w-4" /> },
              ]}
            />
            <Button
              variant="outline"
              size="sm"
              icon={<SlidersHorizontal className="h-4 w-4" />}
              onClick={() => {
                setDraft(filters);
                setOpen(true);
              }}
            >
              Filters{chips.length ? ` (${chips.length})` : ""}
            </Button>
          </>
        }
      />
      <div className="screen pt-4">
        <div className="mb-3 flex gap-2">
          {[{ value: undefined, label: "Buy" }, { value: "rent", label: "Rent" }].map((o) => <button key={o.label} onClick={() => apply({ ...filters, purpose: o.value })} className={`chip px-4 py-2 text-sm ${filters.purpose === o.value ? "bg-brand-700 text-white" : "bg-white text-brand-800 ring-1 ring-black/5 dark:bg-white/5 dark:text-brand-100"}`}>{o.label}</button>)}
        </div>
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          <button onClick={() => apply({ ...filters, category: undefined })} className={`chip shrink-0 px-3.5 py-2 text-sm ${!filters.category ? "bg-brand-700 text-white" : "bg-white text-brand-800 ring-1 ring-black/5 dark:bg-white/5 dark:text-brand-100"}`}>
            All
          </button>
          {CATEGORIES.map((c) => (
            <button key={c} onClick={() => apply({ ...filters, category: c })} className={`chip shrink-0 px-3.5 py-2 text-sm ${filters.category === c ? "bg-brand-700 text-white" : "bg-white text-brand-800 ring-1 ring-black/5 dark:bg-white/5 dark:text-brand-100"}`}>
              {titleCase(c)}
            </button>
          ))}
        </div>

        {chips.filter((c) => c.key !== "category").length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {chips
              .filter((c) => c.key !== "category")
              .map((c) => (
                <button key={c.key} onClick={() => apply({ ...filters, [c.key]: undefined, ...(c.key === "near" || c.key === "near_place" ? { near_km: filters.near && filters.near_place ? filters.near_km : undefined } : {}) })} className="chip bg-gold-50 text-gold-800 ring-1 ring-gold-200 dark:bg-gold-500/10 dark:text-gold-200 dark:ring-gold-500/20">
                  {c.label} <X className="h-3 w-3" />
                </button>
              ))}
            <button onClick={() => apply({})} className="text-xs font-semibold text-ink-mute">
              Clear all
            </button>
          </div>
        )}

        {project && projectUnits.length > 0 && (
          <div className="card mt-4 p-4">
            <p className="text-[11px] font-bold uppercase tracking-wider text-gold-700 dark:text-gold-300">Available inventory</p>
            <p className="font-display text-lg font-bold text-brand-900 dark:text-white">{projectNameOf(projectUnits[0]!)}</p>
            <p className="text-xs text-ink-mute">
              {projectUnits.length} units · {priceSpan(Math.min(...projectUnits.map((u) => u.price)), Math.max(...projectUnits.map((u) => u.price)))}
            </p>
            <div className="no-scrollbar -mx-1 mt-3 flex gap-1.5 overflow-x-auto px-1">
              <button onClick={() => setUnitType("")} className={`chip shrink-0 ring-1 ${!unitType ? "bg-brand-700 text-white ring-brand-700" : "bg-white text-ink-soft ring-black/10 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10"}`}>
                All {projectUnits.length}
              </button>
              {[...new Set(projectUnits.map(unitTypeOf))].map((t) => (
                <button key={t} onClick={() => setUnitType(unitType === t ? "" : t)} className={`chip shrink-0 capitalize ring-1 ${unitType === t ? "bg-brand-700 text-white ring-brand-700" : "bg-white text-ink-soft ring-black/10 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10"}`}>
                  {t} <span className="text-[10px] opacity-70">{projectUnits.filter((u) => unitTypeOf(u) === t).length}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <p className="mt-4 text-sm text-ink-mute dark:text-slate-400">
          {q.data ? `${results.length} ${results.length === 1 ? "property" : "properties"} found${shown.length < results.length ? " · new projects grouped by unit type" : ""}` : " "}
        </p>

        {q.isLoading ? (
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-72" />
            ))}
          </div>
        ) : q.error ? (
          <EmptyState icon={<SearchX className="h-7 w-7" />} title="Couldn't load listings">
            {q.error.message}
          </EmptyState>
        ) : !q.data?.results.length && placeMissing ? (
          <EmptyState icon={<SearchX className="h-7 w-7" />} title={`Couldn't find “${filters.near_place}” on the map`}>
            Try a sector, society or landmark — e.g. “G-13”, “DHA Phase 2” or a university.
          </EmptyState>
        ) : !q.data?.results.length && nearest.length ? (
          <div className="mt-3">
            <p className="mb-3 text-sm text-ink-mute dark:text-slate-400">
              Nothing within {filters.near_km ?? 2} km of {q.data?.near_place?.name ?? filters.near_place} — the closest listings:
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {nearest.map((p) => (
                <PropertyCard key={p.id} p={p} />
              ))}
            </div>
          </div>
        ) : !q.data?.results.length ? (
          <EmptyState
            icon={<SearchX className="h-7 w-7" />}
            title="No matching properties"
            action={
              <Link to="/assistant" className="btn btn-gold">
                <Bot className="h-4 w-4" /> Ask the AI to help
              </Link>
            }
          >
            Try widening your budget or removing a filter.
          </EmptyState>
        ) : view === "grid" ? (
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((p, i) => (
              <Fragment key={isGroup(p) ? p.key : p.id}>
                {isGroup(p) ? <UnitGroupCard g={p} /> : <PropertyCard p={p} />}
                {(i + 1) % AD_EVERY === 0 && <AdSlot slot="infeed" placement="explore" index={(i + 1) / AD_EVERY - 1} />}
              </Fragment>
            ))}
          </div>
        ) : (
          <div className="card mt-3 divide-y divide-black/5 p-1.5 dark:divide-white/5">
            {shown.map((p, i) => (
              <Fragment key={isGroup(p) ? p.key : p.id}>
                {isGroup(p) ? (
                  <PropertyRow
                    p={{ ...p.units[0]!, title: `${p.projectName} — ${p.units.length} × ${p.unitType}` }}
                    to={groupHref(p)}
                    extra={<span className="shrink-0 text-xs font-semibold text-brand-700 dark:text-brand-300">{priceSpan(p.priceMin, p.priceMax)}</span>}
                  />
                ) : (
                  <PropertyRow p={p} />
                )}
                {(i + 1) % AD_EVERY === 0 && <AdSlot slot="infeed" placement="explore" variant="row" index={(i + 1) / AD_EVERY - 1} />}
              </Fragment>
            ))}
          </div>
        )}
        <BannerSpacer />
      </div>

      <Sheet open={open} onClose={() => setOpen(false)} title="Filters">
        <div className="space-y-4">
          <Field label="City">
            <Select value={draft.city ?? ""} onChange={(e) => setDraft({ ...draft, city: e.target.value || undefined })}>
              <option value="">Any city</option>
              {cities.data?.cities.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Type">
              <Select value={draft.category ?? ""} onChange={(e) => setDraft({ ...draft, category: e.target.value || undefined })}>
                <option value="">Any type</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Use">
              <Select value={draft.use_type ?? ""} onChange={(e) => setDraft({ ...draft, use_type: e.target.value || undefined })}>
                <option value="">Any</option>
                <option value="residential">Residential</option>
                <option value="commercial">Commercial</option>
                <option value="mix">Mixed use</option>
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Min price">
              <Select value={draft.min_price ?? ""} onChange={(e) => setDraft({ ...draft, min_price: e.target.value || undefined })}>
                {PRICE_STEPS.slice(0, -1).map((v) => (
                  <option key={v} value={v || ""}>
                    {v ? pkrShort(v) : "No min"}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Max price">
              <Select value={draft.max_price ?? ""} onChange={(e) => setDraft({ ...draft, max_price: e.target.value || undefined })}>
                <option value="">No max</option>
                {PRICE_STEPS.slice(1).map((v) => (
                  <option key={v} value={v}>
                    {pkrShort(v)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Bedrooms">
            <div className="grid grid-cols-6 gap-2">
              {["", "1", "2", "3", "4", "5"].map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => setDraft({ ...draft, bedrooms: b || undefined })}
                  className={`rounded-xl border py-2 text-sm font-semibold ${(draft.bedrooms ?? "") === b ? "border-brand-600 bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-white" : "border-black/10 dark:border-white/10"}`}
                >
                  {b ? `${b}+` : "Any"}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Bathrooms">
            <div className="grid grid-cols-5 gap-2">
              {["", "1", "2", "3", "4"].map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => setDraft({ ...draft, min_bathrooms: b || undefined })}
                  className={`rounded-xl border py-2 text-sm font-semibold ${(draft.min_bathrooms ?? "") === b ? "border-brand-600 bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-white" : "border-black/10 dark:border-white/10"}`}
                >
                  {b ? `${b}+` : "Any"}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Close to">
            <div className="flex flex-wrap gap-2">
              {NEAR_KINDS.map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setDraft({ ...draft, near: draft.near === k ? undefined : k })}
                  className={`chip px-3 py-1.5 text-sm ${draft.near === k ? "bg-brand-700 text-white" : "bg-white text-brand-800 ring-1 ring-black/10 dark:bg-white/5 dark:text-brand-100 dark:ring-white/10"}`}
                >
                  {titleCase(k)}
                </button>
              ))}
            </div>
          </Field>
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <Field label="Near a place">
              <Input value={draft.near_place ?? ""} onChange={(e) => setDraft({ ...draft, near_place: e.target.value || undefined })} placeholder="e.g. G-13, a university" />
            </Field>
            <Field label="Within">
              <Select value={draft.near_km ?? "2"} onChange={(e) => setDraft({ ...draft, near_km: e.target.value === "2" ? undefined : e.target.value })}>
                {["1", "2", "5"].map((km) => (
                  <option key={km} value={km}>
                    {km} km
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Feature">
            <Input value={draft.feature ?? ""} onChange={(e) => setDraft({ ...draft, feature: e.target.value || undefined })} placeholder="e.g. solar, basement, corner" />
          </Field>
          <label className="flex items-center gap-3 text-sm font-semibold">
            <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={!!draft.featured} onChange={(e) => setDraft({ ...draft, featured: e.target.checked ? "1" : undefined })} />
            Featured listings only
          </label>
          <div className="flex gap-3 pt-2">
            <Button variant="outline" className="flex-1" onClick={() => setDraft({})}>
              Reset
            </Button>
            <Button
              className="flex-1"
              onClick={() => {
                apply({ ...draft, near_place: draft.near_place?.trim() || undefined, feature: draft.feature?.trim() || undefined });
                setOpen(false);
              }}
            >
              Show results
            </Button>
          </div>
        </div>
      </Sheet>
    </div>
  );
}
