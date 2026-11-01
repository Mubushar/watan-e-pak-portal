/**
 * Administration › Property database: every listing with every field, for staff with
 * properties.manage (/admin/properties*). Search, filter, sort and page the catalogue; add, edit
 * or delete one listing; feature, re-status, re-assign or delete many at once; export to CSV and
 * import a CSV back (checked row by row first; nothing is saved while any row is wrong).
 */
import { useMemo, useRef, useState } from "react";
import { Building2, CheckSquare, Download, FileUp, Home, MapPin, Pencil, Plus, Search, Star, Trash2, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { del, get, post, put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { num, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, Card, Drawer, EmptyState, ErrorState, Field, Input, Modal, PageHeader, Select, Skeleton, Textarea, Toggle } from "@/components/ui";

type Row = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
interface Page {
  total: number;
  page: number;
  pages: number;
  page_size: number;
  catalogue: number;
  facets: { status: Record<string, number>; category: Record<string, number>; city: Record<string, number> };
  rows: Row[];
}
interface Meta {
  statuses: string[];
  categories: string[];
  use_types: string[];
  purposes?: string[];
  rent_frequencies?: string[];
  furnishing_statuses?: string[];
  cities: { id: string; name: string }[];
  schemes: { id: string; name: string; city_id: string }[];
  blocks: { id: string; name: string; scheme_id: string }[];
  agents: { id: string; name: string }[];
}
interface ImportResult {
  dry_run: boolean;
  saved: boolean;
  rows: number;
  valid: number;
  would_create: number;
  would_update: number;
  errors: { row: number; error: string }[];
}

const STATUS_TONE: Record<string, "green" | "blue" | "gold" | "gray" | "red" | "orange"> = {
  active: "green",
  pending: "gold",
  sold: "blue",
  rented: "blue",
  withdrawn: "gray",
  draft: "orange",
};
const EMPTY: Row = { title: "", price: "", listing_purpose: "sale", status: "active", use_type: "residential", category: "house", featured: false, city_id: "", amenities: [] };

export default function PropertiesAdmin({ rentalOnly = false }: { rentalOnly?: boolean } = {}) {
  const qc = useQueryClient();
  const meta = useApi<Meta>("/admin/properties/meta");
  const [q, setQ] = useState("");
  const [city, setCity] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [purpose, setPurpose] = useState("");
  const [featured, setFeatured] = useState("");
  const [located, setLocated] = useState("");
  const [sort, setSort] = useState("updated");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [edit, setEdit] = useState<Row | null>(null);
  const [confirm, setConfirm] = useState<{ ids: string[]; label: string } | null>(null);
  const [importing, setImporting] = useState(false);

  const query = {
    q: q || undefined,
    city_id: city || undefined,
    status: status || undefined,
    category: category || undefined,
    purpose: rentalOnly ? "rent" : purpose || undefined,
    featured: featured === "" ? undefined : featured === "yes",
    located: located === "" ? undefined : located === "yes",
    sort,
    order,
    page,
    page_size: 25,
  };
  const list = useApi<Page>("/admin/properties", query);
  const data = list.data;
  const rows = data?.rows ?? [];

  const refresh = () => {
    setSelected(new Set());
    void qc.invalidateQueries({ predicate: (x) => /^\/(admin\/properties|properties|search)/.test(String(x.queryKey[0] ?? "")) });
  };
  const setFilter = (fn: () => void) => {
    fn();
    setPage(1);
    setSelected(new Set());
  };
  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const allOnPage = rows.length > 0 && rows.every((r) => selected.has(r.id));

  const bulk = async (action: string, value?: string) => {
    try {
      const r = await post<{ affected: number }>("/admin/properties/bulk", { ids: [...selected], action, value });
      toast.success(`${titleCase(action.replace("_", " "))}: ${r.affected} listing${r.affected === 1 ? "" : "s"}`);
      setConfirm(null);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const removeOne = async (id: string) => {
    try {
      await del(`/admin/properties/${id}`);
      toast.success("Listing deleted");
      setConfirm(null);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const exportCsv = async () => {
    try {
      const text = await get<string>("/admin/properties/export.csv", { q: q || undefined, city_id: city || undefined, status: status || undefined, category: category || undefined, purpose: rentalOnly ? "rent" : purpose || undefined }, { text: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
      a.download = `watanepak-properties-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const sortBy = (key: string) => {
    if (sort === key) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setOrder(key === "title" ? "asc" : "desc");
    }
    setPage(1);
  };
  const SortHead = ({ k, children, end }: { k: string; children: string; end?: boolean }) => (
    <th className={cn("px-2 py-2", end ? "text-end" : "text-start")}>
      <button type="button" className={cn("uppercase tracking-wider hover:text-ink", sort === k && "text-brand-700 dark:text-brand-200")} onClick={() => sortBy(k)}>
        {children}
        {sort === k ? (order === "asc" ? " ↑" : " ↓") : ""}
      </button>
    </th>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={rentalOnly ? "Rental listings" : "Property database"}
        subtitle={`${rentalOnly ? "Rental homes and commercial spaces" : "Every listing on the portal"}${data ? ` — ${num(data.catalogue)} in the catalogue` : ""}. Add, edit, publish or remove listings; changes are saved to the database.`}
        actions={
          <>
            <Button size="sm" variant="soft" icon={<Download className="h-4 w-4" />} onClick={exportCsv}>
              Export CSV
            </Button>
            <Button size="sm" variant="soft" icon={<FileUp className="h-4 w-4" />} onClick={() => setImporting(true)}>
              Import CSV
            </Button>
            <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({ ...EMPTY, listing_purpose: rentalOnly ? "rent" : "sale" })}>
              {rentalOnly ? "Add rental" : "Add listing"}
            </Button>
          </>
        }
      />

      {data && (
        <div className="grid gap-3 sm:grid-cols-4">
          {Object.entries(data.facets.status)
            .slice(0, 4)
            .map(([s, n]) => (
              <button key={s} type="button" onClick={() => setFilter(() => setStatus(status === s ? "" : s))} className={cn("rounded-2xl border p-3 text-start transition", status === s ? "border-brand-400 bg-brand-50 dark:bg-white/10" : "border-black/5 bg-white hover:bg-brand-50/50 dark:border-white/10 dark:bg-white/5")}>
                <p className="text-xs uppercase tracking-wider text-ink-mute">{titleCase(s)}</p>
                <p className="text-2xl font-bold tabular-nums">{num(n)}</p>
              </button>
            ))}
        </div>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-black/5 p-4 dark:border-white/10">
          <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-xl bg-black/5 px-3 dark:bg-white/10">
            <Search className="h-4 w-4 text-ink-mute" />
            <input value={q} onChange={(e) => setFilter(() => setQ(e.target.value))} placeholder="Search title, sector, address, plot or id…" className="h-9 w-full bg-transparent text-sm outline-none" />
          </div>
          <Select value={city} onChange={(e) => setFilter(() => setCity(e.target.value))} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">All cities</option>
            {(meta.data?.cities ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <Select value={category} onChange={(e) => setFilter(() => setCategory(e.target.value))} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">All types</option>
            {(meta.data?.categories ?? []).map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </Select>
          {!rentalOnly && <Select value={purpose} onChange={(e) => setFilter(() => setPurpose(e.target.value))} className="!h-9 !w-auto !py-0 text-sm"><option value="">Sale and rent</option><option value="sale">For sale</option><option value="rent">For rent</option></Select>}
          <Select value={status} onChange={(e) => setFilter(() => setStatus(e.target.value))} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">Any status</option>
            {(meta.data?.statuses ?? []).map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </Select>
          <Select value={featured} onChange={(e) => setFilter(() => setFeatured(e.target.value))} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">Featured or not</option>
            <option value="yes">Featured</option>
            <option value="no">Not featured</option>
          </Select>
          <Select value={located} onChange={(e) => setFilter(() => setLocated(e.target.value))} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">On the map or not</option>
            <option value="yes">Has a map location</option>
            <option value="no">No map location</option>
          </Select>
          <span className="text-xs text-ink-mute">{data ? `${num(data.total)} found` : ""}</span>
        </div>

        {selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b border-black/5 bg-brand-50/60 px-4 py-2 text-sm dark:border-white/10 dark:bg-white/5">
            <CheckSquare className="h-4 w-4 text-brand-700" />
            <span className="font-semibold">{selected.size} selected</span>
            <Button size="sm" variant="soft" icon={<Star className="h-3.5 w-3.5" />} onClick={() => bulk("feature")}>
              Feature
            </Button>
            <Button size="sm" variant="ghost" onClick={() => bulk("unfeature")}>
              Unfeature
            </Button>
            <Select defaultValue="" onChange={(e) => e.target.value && bulk("status", e.target.value)} className="!h-8 !w-auto !py-0 text-sm">
              <option value="">Set status…</option>
              {(meta.data?.statuses ?? []).map((s) => (
                <option key={s} value={s}>
                  {titleCase(s)}
                </option>
              ))}
            </Select>
            <Select defaultValue="" onChange={(e) => e.target.value && bulk("assign_agent", e.target.value === "-" ? "" : e.target.value)} className="!h-8 !w-auto !py-0 text-sm">
              <option value="">Assign agent…</option>
              <option value="-">No agent</option>
              {(meta.data?.agents ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
            <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setConfirm({ ids: [...selected], label: `${selected.size} listings` })}>
              Delete
            </Button>
            <button type="button" className="ms-auto text-xs text-ink-mute hover:underline" onClick={() => setSelected(new Set())}>
              Clear selection
            </button>
          </div>
        )}

        {list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : list.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-11" />
            ))}
          </div>
        ) : !rows.length ? (
          <div className="p-6">
            <EmptyState icon={<Home className="h-6 w-6" />} title="No listings match" hint="Change the filters or add a listing." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink-mute">
                <tr className="border-b border-black/5 dark:border-white/10">
                  <th className="w-10 px-4 py-2">
                    <input
                      type="checkbox"
                      checked={allOnPage}
                      onChange={() => setSelected((s) => (allOnPage ? new Set([...s].filter((id) => !rows.some((r) => r.id === id))) : new Set([...s, ...rows.map((r) => r.id)])))}
                      aria-label="Select all on this page"
                    />
                  </th>
                  <SortHead k="title">Listing</SortHead>
                  <th className="px-2 py-2 text-start">Location</th>
                  <SortHead k="price" end>
                    {rentalOnly ? "Rent / period" : "Price / rent"}
                  </SortHead>
                  <SortHead k="size" end>
                    Size
                  </SortHead>
                  <th className="px-2 py-2 text-start">Status</th>
                  <th className="px-2 py-2 text-start">Agent</th>
                  <SortHead k="updated">Updated</SortHead>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={cn("cursor-pointer border-b border-black/5 last:border-0 hover:bg-brand-50/50 dark:border-white/10 dark:hover:bg-white/5", selected.has(r.id) && "bg-brand-50/70 dark:bg-white/10")} onClick={() => setEdit(r)}>
                    <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label={`Select ${r.title}`} />
                    </td>
                    <td className="max-w-[280px] px-2 py-2.5">
                      <p className="truncate font-semibold">
                        {r.featured && <Star className="me-1 inline h-3.5 w-3.5 fill-gold-400 text-gold-500" />}
                        {r.title}
                      </p>
                      <p className="truncate text-[11px] text-ink-mute">
                        {titleCase(r.category)} · {titleCase(r.use_type)}
                        {r.bedrooms ? ` · ${r.bedrooms} bed` : ""}
                        {r.images ? ` · ${r.images} photo${r.images === 1 ? "" : "s"}` : " · no photos"}
                      </p>
                    </td>
                    <td className="max-w-[200px] px-2 py-2.5">
                      <p className="truncate">{[r.scheme_name, r.city_name].filter(Boolean).join(", ")}</p>
                      <p className="flex items-center gap-1 text-[11px] text-ink-mute">
                        <MapPin className={cn("h-3 w-3", r.located ? "text-brand-600" : "text-red-500")} />
                        {r.located ? r.sector || "On the map" : "No map location"}
                      </p>
                    </td>
                    <td className="px-2 py-2.5 text-end tabular-nums">
                      {pkrShort(r.price)}{r.listing_purpose === "rent" ? <span className="text-[11px]">/{r.rent_frequency === "weekly" ? "wk" : "mo"}</span> : null}
                      {r.price_per_marla && <p className="text-[11px] text-ink-mute">{pkrShort(r.price_per_marla)}/marla</p>}
                    </td>
                    <td className="px-2 py-2.5 text-end tabular-nums">{r.marla_area ? `${num(r.marla_area)} marla` : r.total_area ? `${num(r.total_area)} sq ft` : "—"}</td>
                    <td className="px-2 py-2.5">
                      <Badge tone={STATUS_TONE[r.status] ?? "gray"}>{titleCase(r.status)}</Badge>
                    </td>
                    <td className="max-w-[140px] truncate px-2 py-2.5 text-ink-soft">{r.agent_name ?? "—"}</td>
                    <td className="px-2 py-2.5 text-xs text-ink-mute">{new Date(r.updated_at).toLocaleDateString()}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-end" onClick={(e) => e.stopPropagation()}>
                      <Link to={`/properties/${r.id}`} className="btn btn-ghost btn-icon h-8 w-8" title="Open the public page">
                        <Building2 className="h-4 w-4" />
                      </Link>
                      <button type="button" className="btn btn-ghost btn-icon h-8 w-8" title="Edit" onClick={() => setEdit(r)}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button type="button" className="btn btn-ghost btn-icon h-8 w-8 text-red-600" title="Delete" onClick={() => setConfirm({ ids: [r.id], label: `“${r.title}”` })}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between border-t border-black/5 px-4 py-3 text-sm dark:border-white/10">
            <span className="text-ink-mute">
              Page {data.page} of {data.pages}
            </span>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" disabled={data.page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <Button size="sm" variant="ghost" disabled={data.page >= data.pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>

      <PropertyForm record={edit} meta={meta.data} rentalOnly={rentalOnly} onClose={() => setEdit(null)} onSaved={refresh} />
      <ImportDialog open={importing} onClose={() => setImporting(false)} onSaved={refresh} />

      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={`Delete ${confirm?.label ?? ""}?`}
        subtitle="This removes the listing and its photos from the portal for everyone. It can't be undone — export a CSV first if you may need them."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => confirm && (confirm.ids.length === 1 && !selected.size ? removeOne(confirm.ids[0]) : bulk("delete"))}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-soft dark:text-slate-300">Leads, deals and messages that mention these listings keep their history.</p>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ form

function PropertyForm({ record, meta, rentalOnly, onClose, onSaved }: { record: Row | null; meta?: Meta; rentalOnly: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Row | null>(null);
  const [saving, setSaving] = useState(false);
  const current = form && record && (form.id ?? "new") === (record.id ?? "new") ? form : record;
  const set = (patch: Row) => setForm({ ...(current as Row), ...patch });
  const isNew = !current?.id;

  const schemes = useMemo(() => (meta?.schemes ?? []).filter((s) => s.city_id === current?.city_id), [meta, current?.city_id]);
  const blocks = useMemo(() => (meta?.blocks ?? []).filter((b) => b.scheme_id === current?.scheme_id), [meta, current?.scheme_id]);

  const close = () => {
    setForm(null);
    onClose();
  };
  const save = async () => {
    if (!current) return;
    setSaving(true);
    const fields = [
      "title", "description", "price", "listing_purpose", "security_deposit", "advance_months", "lease_term_months", "rent_frequency", "furnishing_status", "tenant_preference", "use_type", "category", "status", "featured", "city_id", "scheme_id", "block_zone_area_id",
      "marla_area", "kanal_area", "total_area", "covered_area", "bedrooms", "bathrooms", "balconies", "floors",
      "street_address", "plot_number", "sector", "landmark", "latitude", "longitude", "agent_id", "available_from", "amenities",
    ];
    const body: Row = {};
    for (const f of fields) if (current[f] !== undefined) body[f] = current[f] === "" ? null : current[f];
    if (body.title !== undefined) body.title = current.title ?? "";
    // Send only the size the admin typed, so the other units follow it.
    if (!isNew && record) for (const k of ["marla_area", "kanal_area", "total_area"]) if (current[k] === record[k]) delete body[k];
    try {
      if (isNew) await post("/admin/properties", body);
      else await put(`/admin/properties/${current.id}`, body);
      toast.success(isNew ? `Added “${current.title}”` : `Saved “${current.title}”`);
      onSaved();
      close();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const numField = (key: string, label: string, hint?: string, step = "any") => (
    <Field label={label} hint={hint}>
      <Input type="number" step={step} value={current?.[key] ?? ""} onChange={(e) => set({ [key]: e.target.value === "" ? null : Number(e.target.value) })} />
    </Field>
  );
  const textField = (key: string, label: string, placeholder?: string) => (
    <Field label={label}>
      <Input value={current?.[key] ?? ""} placeholder={placeholder} onChange={(e) => set({ [key]: e.target.value })} />
    </Field>
  );
  const section = (title: string) => <p className="pt-2 text-xs font-bold uppercase tracking-wider text-ink-mute">{title}</p>;

  return (
    <Drawer open={!!record} onClose={close} title={isNew ? "Add a listing" : `Edit · ${current?.title ?? ""}`} width="max-w-2xl">
      {current && (
        <div className="space-y-3 p-5 pb-24">
          {section("Listing")}
          {textField("title", "Title", "e.g. 10 Marla House in DHA Phase II")}
          <Field label="Description">
            <Textarea rows={4} value={current.description ?? ""} onChange={(e) => set({ description: e.target.value })} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            {numField("price", current.listing_purpose === "rent" ? `Rent per ${current.rent_frequency === "weekly" ? "week" : "month"} (PKR)` : "Asking price (PKR)", current.price ? pkrShort(Number(current.price)) : undefined, "1")}
            <Field label="Status">
              <Select value={current.status} onChange={(e) => set({ status: e.target.value })}>
                {(meta?.statuses ?? ["active"]).map((s) => (
                  <option key={s} value={s}>
                    {titleCase(s)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Featured">
              <div className="flex h-10 items-center">
                <Toggle checked={!!current.featured} onChange={(v) => set({ featured: v })} label={current.featured ? "Shown first" : "No"} />
              </div>
            </Field>
          </div>
          {!rentalOnly && <Field label="Listing goal"><Select value={current.listing_purpose ?? "sale"} onChange={(e) => set({ listing_purpose: e.target.value })}><option value="sale">Sell / purchase</option><option value="rent">Rent out / lease</option></Select></Field>}
          {current.listing_purpose === "rent" && <>
            {section("Rental terms & tenant information")}
            <div className="grid gap-3 sm:grid-cols-3">
              {numField("security_deposit", "Security deposit (PKR)", undefined, "1")}
              {numField("advance_months", "Advance months", undefined, "1")}
              {numField("lease_term_months", "Lease term (months)", "Leave blank for flexible", "1")}
              <Field label="Rent frequency"><Select value={current.rent_frequency ?? "monthly"} onChange={(e) => set({ rent_frequency: e.target.value })}><option value="monthly">Monthly</option><option value="weekly">Weekly</option></Select></Field>
              <Field label="Furnishing"><Select value={current.furnishing_status ?? ""} onChange={(e) => set({ furnishing_status: e.target.value || null })}><option value="">Not specified</option>{(meta?.furnishing_statuses ?? ["furnished", "semi_furnished", "unfurnished"]).map((v) => <option key={v} value={v}>{titleCase(v)}</option>)}</Select></Field>
            </div>
            <Field label="Tenant preference" hint="Optional, factual eligibility details; avoid discriminatory language."><Textarea rows={2} maxLength={500} value={current.tenant_preference ?? ""} onChange={(e) => set({ tenant_preference: e.target.value })} placeholder="e.g. Family tenancy preferred; no smoking indoors" /></Field>
          </>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Type">
              <Select value={current.category} onChange={(e) => set({ category: e.target.value })}>
                {(meta?.categories ?? []).map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Use">
              <Select value={current.use_type} onChange={(e) => set({ use_type: e.target.value })}>
                {(meta?.use_types ?? []).map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          {section("Where")}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="City">
              <Select value={current.city_id ?? ""} onChange={(e) => set({ city_id: e.target.value, scheme_id: null, block_zone_area_id: null })}>
                <option value="">Choose…</option>
                {(meta?.cities ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Housing society">
              <Select value={current.scheme_id ?? ""} onChange={(e) => set({ scheme_id: e.target.value || null, block_zone_area_id: null })} disabled={!current.city_id}>
                <option value="">None</option>
                {schemes.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Block / zone">
              <Select value={current.block_zone_area_id ?? ""} onChange={(e) => set({ block_zone_area_id: e.target.value || null })} disabled={!blocks.length}>
                <option value="">None</option>
                {blocks.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {textField("sector", "Sector / phase", "e.g. F-7/2")}
            {textField("plot_number", "Plot / house no.")}
            {textField("landmark", "Landmark")}
          </div>
          {textField("street_address", "Street address")}
          <div className="grid gap-3 sm:grid-cols-2">
            {numField("latitude", "Latitude", "23 – 37.5 (Pakistan)")}
            {numField("longitude", "Longitude", "60 – 78 (Pakistan)")}
          </div>

          {section("Size & rooms")}
          <div className="grid gap-3 sm:grid-cols-4">
            {numField("marla_area", "Marla")}
            {numField("kanal_area", "Kanal", "1 kanal = 20 marla")}
            {numField("total_area", "Plot area (sq ft)")}
            {numField("covered_area", "Covered (sq ft)")}
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            {numField("bedrooms", "Bedrooms", undefined, "1")}
            {numField("bathrooms", "Bathrooms", undefined, "1")}
            {numField("balconies", "Balconies", undefined, "1")}
            {numField("floors", "Floors", undefined, "1")}
          </div>
          <Field label="Features" hint="Comma-separated, e.g. solar, basement, corner, park facing">
            <Input value={(current.amenities ?? []).join(", ")} onChange={(e) => set({ amenities: e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean) })} />
          </Field>

          {section("Ownership")}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Agent">
              <Select value={current.agent_id ?? ""} onChange={(e) => set({ agent_id: e.target.value || null })}>
                <option value="">No agent</option>
                {(meta?.agents ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Available from">
              <Input type="date" value={(current.available_from ?? "").slice(0, 10)} onChange={(e) => set({ available_from: e.target.value || null })} />
            </Field>
          </div>
          {!isNew && (
            <p className="text-[11px] text-ink-mute">
              Id {current.id} · created {new Date(current.created_at).toLocaleString()} · updated {new Date(current.updated_at).toLocaleString()}
              {current.owner_user_id ? " · published by a portal member" : ""}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button disabled={saving || !String(current.title ?? "").trim() || !current.price || !current.city_id} onClick={save}>
              {saving ? "Saving…" : isNew ? "Add listing" : "Save"}
            </Button>
          </div>
        </div>
      )}
    </Drawer>
  );
}

// ------------------------------------------------------------------ CSV import

function ImportDialog({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [csv, setCsv] = useState<{ name: string; text: string } | null>(null);
  const [check, setCheck] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const close = () => {
    setCsv(null);
    setCheck(null);
    if (fileRef.current) fileRef.current.value = "";
    onClose();
  };
  const choose = async (f?: File) => {
    if (!f) return;
    setBusy(true);
    try {
      const text = await f.text();
      setCsv({ name: f.name, text });
      setCheck(await post<ImportResult>("/admin/properties/import", { csv: text, dry_run: true }));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!csv) return;
    setBusy(true);
    try {
      const r = await post<ImportResult>("/admin/properties/import", { csv: csv.text, dry_run: false });
      toast.success(`Imported: ${r.would_create} added, ${r.would_update} updated`);
      onSaved();
      close();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={close}
      title="Import listings from CSV"
      subtitle="Use the columns of the export (title, price, city … ). Rows with an id update that listing; rows without one are added. Every row is checked first."
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button icon={<Upload className="h-4 w-4" />} disabled={!check || check.errors.length > 0 || !check.valid || busy} onClick={save}>
            Import {check?.valid ?? 0} rows
          </Button>
        </>
      }
    >
      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-brand-200 p-5 text-center hover:bg-brand-50/50 dark:border-white/15">
        <FileUp className="h-6 w-6 text-brand-600" />
        <span className="text-sm font-semibold">{csv ? csv.name : "Choose a CSV file"}</span>
        <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => void choose(e.target.files?.[0])} />
      </label>
      {busy && <Skeleton className="mt-3 h-16" />}
      {check && (
        <div className="mt-3 space-y-1 text-sm">
          <p>
            {check.rows} rows · <b>{check.would_create}</b> to add · <b>{check.would_update}</b> to update
          </p>
          {check.errors.length > 0 && (
            <div className="max-h-48 overflow-y-auto rounded-xl bg-red-50 p-2 text-[12px] text-red-700 dark:bg-red-500/10 dark:text-red-200">
              {check.errors.map((e) => (
                <p key={e.row}>
                  Row {e.row}: {e.error}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
