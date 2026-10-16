import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, LayoutGrid, List, SearchX, SlidersHorizontal, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { City, PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { pkrShort, titleCase } from "@/lib/format";
import { Button, EmptyState, Field, Segmented, Select, Sheet, Skeleton, TopBar } from "@/components/ui";
import { PropertyCard, PropertyRow } from "@/components/PropertyCard";

const CATEGORIES = ["house", "apartment", "plot", "shop", "office", "floor", "building"];
const PRICE_STEPS = [0, 2_500_000, 5_000_000, 10_000_000, 20_000_000, 35_000_000, 50_000_000, 100_000_000, 250_000_000];
const FILTER_KEYS = ["city", "category", "use_type", "bedrooms", "min_price", "max_price", "featured"] as const;
type Filters = Partial<Record<(typeof FILTER_KEYS)[number], string>>;

export default function Explore() {
  const [sp, setSp] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"grid" | "list">("grid");
  const filters: Filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, sp.get(k) ?? undefined]).filter(([, v]) => v));
  const [draft, setDraft] = useState<Filters>(filters);
  const cities = useApi<{ cities: City[] }>("/cities");
  const q = useApi<PropertyList>("/search", {
    ...filters,
    featured: filters.featured ? true : undefined,
    limit: 60,
  });

  const apply = (f: Filters) => {
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v) next.set(k, v);
    setSp(next, { replace: true });
  };
  const chips = Object.entries(filters).map(([k, v]) => ({
    key: k,
    label:
      k === "min_price" ? `≥ ${pkrShort(Number(v))}` : k === "max_price" ? `≤ ${pkrShort(Number(v))}` : k === "bedrooms" ? `${v}+ beds` : k === "featured" ? "Featured" : titleCase(v),
  }));

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
                <button key={c.key} onClick={() => apply({ ...filters, [c.key]: undefined })} className="chip bg-gold-50 text-gold-800 ring-1 ring-gold-200 dark:bg-gold-500/10 dark:text-gold-200 dark:ring-gold-500/20">
                  {c.label} <X className="h-3 w-3" />
                </button>
              ))}
            <button onClick={() => apply({})} className="text-xs font-semibold text-ink-mute">
              Clear all
            </button>
          </div>
        )}

        <p className="mt-4 text-sm text-ink-mute dark:text-slate-400">{q.data ? `${q.data.count} ${q.data.count === 1 ? "property" : "properties"} found` : " "}</p>

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
            {q.data.results.map((p) => (
              <PropertyCard key={p.id} p={p} />
            ))}
          </div>
        ) : (
          <div className="card mt-3 divide-y divide-black/5 p-1.5 dark:divide-white/5">
            {q.data.results.map((p) => (
              <PropertyRow key={p.id} p={p} />
            ))}
          </div>
        )}
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
                apply(draft);
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
