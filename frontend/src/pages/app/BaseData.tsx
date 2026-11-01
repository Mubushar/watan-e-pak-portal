/**
 * Administration › Base data: create, edit and delete the portal's cities, housing societies /
 * societies and their blocks / zones (/admin/basedata/*, permission basedata.manage).
 * Deleting is refused while societies, blocks or listings still use a record.
 */
import { useState } from "react";
import { Building, Database, ExternalLink, Landmark, MapPinned, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { del, post, put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { num, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, Card, Drawer, EmptyState, ErrorState, Field, Input, Modal, PageHeader, Select, Skeleton, Tabs, Textarea } from "@/components/ui";

type Table = "cities" | "schemes" | "blocks" | "landmarks";
type Row = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
interface Source {
  title: string;
  url: string;
}

const PROVINCES = ["Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan", "Islamabad Capital Territory", "Gilgit-Baltistan", "Azad Kashmir"];
const APPROVAL = ["approved", "noc_issued", "partially_approved", "under_process", "unapproved", "illegal", "cancelled"];
const DEV = ["developed", "under development", "planned"];
const UTILITIES = ["electricity", "gas", "water", "sewerage", "underground electricity", "security"];
const AREA_TYPES = ["residential", "commercial", "mixed", "park", "amenity", "industrial"];
const APPROVAL_TONE: Record<string, "green" | "blue" | "gold" | "gray" | "red" | "orange"> = {
  approved: "green",
  noc_issued: "green",
  partially_approved: "blue",
  under_process: "gold",
  unapproved: "orange",
  illegal: "red",
  cancelled: "red",
};

const EMPTY: Record<Table, Row> = {
  cities: { name: "", state: "Punjab", sources: [] },
  schemes: { name: "", approval_status: null, plot_sizes: [], utilities: [], sources: [] },
  blocks: { name: "", area_type: "residential" },
  landmarks: { name: "", city_id: "", project_type: "mall", status: "planned", floor_count: 0 },
};

export default function BaseData() {
  const qc = useQueryClient();
  const [table, setTable] = useState<Table>("cities");
  const [q, setQ] = useState("");
  const [cityFilter, setCityFilter] = useState("");
  const [schemeFilter, setSchemeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [edit, setEdit] = useState<Row | null>(null);
  const [confirm, setConfirm] = useState<Row | null>(null);

  const overview = useApi<{ tables: { table: Table; count: number }[] }>("/admin/basedata");
  const list = useApi<{ rows: Row[] }>(`/admin/basedata/${table}`, {
    q: q || undefined,
    city_id: table === "schemes" || table === "landmarks" ? cityFilter || undefined : undefined,
    scheme_id: table === "blocks" ? schemeFilter || undefined : undefined,
  });
  const cities = useApi<{ rows: Row[] }>("/admin/basedata/cities");
  const schemes = useApi<{ rows: Row[] }>("/admin/basedata/schemes");
  const rows = (list.data?.rows ?? []).filter((r) => table !== "schemes" || !statusFilter || (r.approval_status ?? "unknown") === statusFilter);
  const count = (t: Table) => overview.data?.tables.find((x) => x.table === t)?.count;

  const refresh = () => void qc.invalidateQueries({ predicate: (x) => /^\/(admin\/basedata|cities|schemes|blocks)/.test(String(x.queryKey[0] ?? "")) });

  const remove = async (r: Row) => {
    try {
      await del(`/admin/basedata/${table}/${r.id}`);
      toast.success(`Deleted “${r.name}”`);
      setConfirm(null);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Base data"
        subtitle="Cities, housing societies, blocks and landmarks — the reference data behind listings, maps and reports"
        actions={
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({ ...EMPTY[table] })}>
            Add {table === "cities" ? "city" : table === "schemes" ? "scheme" : table === "landmarks" ? "landmark" : "block"}
          </Button>
        }
      />
      <Card className="overflow-hidden">
        <Tabs<Table>
          className="px-2"
          value={table}
          onChange={(t) => {
            setTable(t);
            setQ("");
          }}
          tabs={[
            { value: "cities", label: "Cities", icon: <Building className="h-4 w-4" />, count: count("cities") },
            { value: "schemes", label: "Housing societies", icon: <Landmark className="h-4 w-4" />, count: count("schemes") },
            { value: "blocks", label: "Blocks & zones", icon: <MapPinned className="h-4 w-4" />, count: count("blocks") },
            { value: "landmarks", label: "Landmarks", icon: <Building className="h-4 w-4" />, count: count("landmarks") },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2 border-b border-black/5 p-4 dark:border-white/10">
          <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-xl bg-black/5 px-3 dark:bg-white/10">
            <Search className="h-4 w-4 text-ink-mute" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${table === "blocks" ? "blocks" : table}…`} className="h-9 w-full bg-transparent text-sm outline-none" />
          </div>
          {table === "schemes" && (
            <>
              <Select value={cityFilter} onChange={(e) => setCityFilter(e.target.value)} className="!h-9 !w-auto !py-0 text-sm">
                <option value="">All cities</option>
                {(cities.data?.rows ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
              <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="!h-9 !w-auto !py-0 text-sm">
                <option value="">Any approval status</option>
                {[...APPROVAL, "unknown"].map((s) => (
                  <option key={s} value={s}>
                    {titleCase(s)}
                  </option>
                ))}
              </Select>
            </>
          )}
          {table === "blocks" && (
            <Select value={schemeFilter} onChange={(e) => setSchemeFilter(e.target.value)} className="!h-9 !w-auto !py-0 text-sm">
              <option value="">All societies</option>
              {(schemes.data?.rows ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.city}
                </option>
              ))}
            </Select>
          )}
          {table === "landmarks" && (
            <Select value={cityFilter} onChange={(e) => setCityFilter(e.target.value)} className="!h-9 !w-auto !py-0 text-sm">
              <option value="">All cities</option>
              {(cities.data?.rows ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          )}
          <span className="text-xs text-ink-mute">{rows.length} rows</span>
        </div>

        {list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : list.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-11" />
            ))}
          </div>
        ) : !rows.length ? (
          <div className="p-6">
            <EmptyState icon={<Database className="h-6 w-6" />} title="Nothing here" hint="Add a record or change the filters." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink-mute">
                <tr className="border-b border-black/5 dark:border-white/10">
                  <th className="px-4 py-2 text-start">Name</th>
                  {table === "cities" && (
                    <>
                      <th className="px-2 py-2 text-start">Province</th>
                      <th className="px-2 py-2 text-end">Population (2023)</th>
                      <th className="px-2 py-2 text-start">Authority</th>
                      <th className="px-2 py-2 text-end">Societies</th>
                      <th className="px-2 py-2 text-end">Listings</th>
                    </>
                  )}
                  {table === "schemes" && (
                    <>
                      <th className="px-2 py-2 text-start">City</th>
                      <th className="px-2 py-2 text-start">Developer</th>
                      <th className="px-2 py-2 text-start">Approval</th>
                      <th className="px-2 py-2 text-start">Status</th>
                      <th className="px-2 py-2 text-end">Blocks</th>
                    </>
                  )}
                  {table === "blocks" && (
                    <>
                      <th className="px-2 py-2 text-start">Society</th>
                      <th className="px-2 py-2 text-start">Type</th>
                    </>
                  )}
                  {table === "landmarks" && <><th className="px-2 py-2 text-start">City</th><th className="px-2 py-2 text-start">Type</th><th className="px-2 py-2 text-start">Status</th><th className="px-2 py-2 text-start">Developer</th></>}
                  <th className="px-2 py-2 text-start">Sources</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="cursor-pointer border-b border-black/5 last:border-0 hover:bg-brand-50/50 dark:border-white/10 dark:hover:bg-white/5" onClick={() => setEdit(r)}>
                    <td className="px-4 py-2.5">
                      <span className="font-semibold">{r.name}</span>
                      {r.name_ur && (
                        <span className="map-ur ms-2 text-ink-mute" dir="rtl">
                          {r.name_ur}
                        </span>
                      )}
                    </td>
                    {table === "cities" && (
                      <>
                        <td className="px-2 py-2.5">{r.state ?? "—"}</td>
                        <td className="px-2 py-2.5 text-end tabular-nums">{r.population ? num(r.population) : "—"}</td>
                        <td className="max-w-[200px] truncate px-2 py-2.5 text-ink-soft">{r.development_authority ?? "—"}</td>
                        <td className="px-2 py-2.5 text-end tabular-nums">{r.schemes}</td>
                        <td className="px-2 py-2.5 text-end tabular-nums">{r.properties}</td>
                      </>
                    )}
                    {table === "schemes" && (
                      <>
                        <td className="px-2 py-2.5">{r.city ?? "—"}</td>
                        <td className="max-w-[180px] truncate px-2 py-2.5 text-ink-soft">{r.developer ?? "—"}</td>
                        <td className="px-2 py-2.5">
                          {r.approval_status ? (
                            <Badge tone={APPROVAL_TONE[r.approval_status] ?? "gray"} className="capitalize">
                              {r.approval_status.replace("_", " ")}
                            </Badge>
                          ) : (
                            <span className="text-ink-mute">unknown</span>
                          )}
                          {r.approval_authority && <span className="ms-1.5 text-[11px] text-ink-mute">{r.approval_authority}</span>}
                        </td>
                        <td className="px-2 py-2.5 capitalize">{r.development_status ?? "—"}</td>
                        <td className="px-2 py-2.5 text-end tabular-nums">{r.blocks}</td>
                      </>
                    )}
                    {table === "blocks" && (
                      <>
                        <td className="px-2 py-2.5">{r.scheme ?? "—"}</td>
                        <td className="px-2 py-2.5 capitalize">{r.area_type}</td>
                      </>
                    )}
                    {table === "landmarks" && <><td className="px-2 py-2.5">{r.city ?? "—"}</td><td className="px-2 py-2.5 capitalize">{titleCase(r.project_type ?? "")}</td><td className="px-2 py-2.5 capitalize">{titleCase(r.status ?? "")}</td><td className="max-w-[180px] truncate px-2 py-2.5 text-ink-soft">{r.developer ?? "—"}</td></>}
                    <td className="px-2 py-2.5 text-xs text-ink-mute">{r.sources?.length ? `${r.sources.length} source${r.sources.length > 1 ? "s" : ""}` : "—"}</td>
                    <td className="px-4 py-2.5 text-end" onClick={(e) => e.stopPropagation()}>
                      <button type="button" className="btn btn-ghost btn-icon h-8 w-8" title="Edit" onClick={() => setEdit(r)}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button type="button" className="btn btn-ghost btn-icon h-8 w-8 text-red-600" title="Delete" onClick={() => setConfirm(r)}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <RecordForm table={table} record={edit} cities={cities.data?.rows ?? []} schemes={schemes.data?.rows ?? []} onClose={() => setEdit(null)} onSaved={refresh} />

      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={`Delete “${confirm?.name ?? ""}”?`}
        subtitle="This can't be undone. Records still used by listings or other base data can't be deleted."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => confirm && remove(confirm)}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-soft dark:text-slate-300">
          {table === "cities" ? `${confirm?.schemes ?? 0} societies and ${confirm?.properties ?? 0} listings use this city.` : table === "schemes" ? `${confirm?.blocks ?? 0} blocks and ${confirm?.properties ?? 0} listings use this society.` : table === "landmarks" ? `${confirm?.listings ?? 0} listings are associated with this landmark.` : "Listings in this block keep their society and city."}
        </p>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ form

const numOrNull = (v: string) => (v.trim() === "" ? null : Number(v));
const listOf = (v: string) =>
  v
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

function RecordForm({ table, record, cities, schemes, onClose, onSaved }: { table: Table; record: Row | null; cities: Row[]; schemes: Row[]; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Row>({});
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState<string | null>(null);
  const isNew = !record?.id;
  // Reset the form when another record opens.
  const id = record ? record.id ?? "new" : null;
  if (id !== key) {
    setKey(id);
    setForm(record ? { ...record } : {});
  }
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const text = (k: string, label: string, opts: { placeholder?: string; dir?: "rtl" } = {}) => (
    <Field label={label}>
      <Input value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} placeholder={opts.placeholder} dir={opts.dir} className={opts.dir ? "map-ur" : undefined} />
    </Field>
  );
  const number = (k: string, label: string, step = "any") => (
    <Field label={label}>
      <Input type="number" step={step} value={form[k] ?? ""} onChange={(e) => set(k, numOrNull(e.target.value))} />
    </Field>
  );
  const sources: Source[] = form.sources ?? [];

  const save = async () => {
    setBusy(true);
    const body: Row = {};
    for (const [k, v] of Object.entries(form)) {
      if (["id", "created_at", "updated_at", "schemes", "properties", "blocks", "city", "scheme"].includes(k)) continue;
      if (["image_urls", "maps", "floor_plans", "image_library", "amenities", "multimedia"].includes(k)) continue;
      body[k] = v === "" ? null : v;
    }
    body.sources = sources.filter((s) => s.url.trim());
    try {
      if (isNew) await post(`/admin/basedata/${table}`, body);
      else await put(`/admin/basedata/${table}/${record!.id}`, body);
      toast.success(isNew ? `Added “${body.name}”` : `Saved “${body.name}”`);
      onSaved();
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const title = `${isNew ? "Add" : "Edit"} ${table === "cities" ? "city" : table === "schemes" ? "housing society" : table === "landmarks" ? "landmark" : "block / zone"}`;
  return (
    <Drawer open={!!record} onClose={onClose} title={title} width="max-w-xl">
      <div className="space-y-4 pb-24">
        <div className="grid gap-3 sm:grid-cols-2">
          {text("name", "Name *")}
          {(table === "cities" || table === "schemes") && text("name_ur", "Name (Urdu)", { dir: "rtl" })}
        </div>

        {table === "cities" && (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Province / territory">
                <Select value={form.state ?? ""} onChange={(e) => set("state", e.target.value || null)} options={[{ value: "", label: "—" }, ...PROVINCES.map((p) => ({ value: p, label: p }))]} />
              </Field>
              {text("district", "District")}
              {number("population", "Population (2023 Census)", "1")}
              {number("area_km2", "Area (km²)")}
            </div>
            {text("population_note", "Population note", { placeholder: "e.g. City (urban) population, 2023 Census, PBS" })}
            {text("development_authority", "Development authority", { placeholder: "e.g. Lahore Development Authority (LDA)" })}
          </>
        )}

        {table === "schemes" && (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="City *">
                <Select value={form.city_id ?? ""} onChange={(e) => set("city_id", e.target.value)}>
                  <option value="">Choose a city</option>
                  {cities.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </Field>
              {text("developer", "Developer")}
              {text("approval_authority", "Approval authority", { placeholder: "CDA, RDA, LDA, SBCA, DHA…" })}
              <Field label="Approval status">
                <Select value={form.approval_status ?? ""} onChange={(e) => set("approval_status", e.target.value || null)}>
                  <option value="">Unknown</option>
                  {APPROVAL.map((s) => (
                    <option key={s} value={s}>
                      {titleCase(s)}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {text("approval_note", "Approval note (which list / ruling / when)")}
            <div className="grid gap-3 sm:grid-cols-3">
              {number("established_year", "Launched (year)", "1")}
              {number("area_acres", "Area (acres)")}
              {number("total_units", "Plots / units", "1")}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Development status">
                <Select value={form.development_status ?? ""} onChange={(e) => set("development_status", e.target.value || null)}>
                  <option value="">—</option>
                  {DEV.map((s) => (
                    <option key={s} value={s}>
                      {titleCase(s)}
                    </option>
                  ))}
                </Select>
              </Field>
              {text("possession_status", "Possession", { placeholder: "possession given / partial / not yet" })}
            </div>
            <Field label="Plot sizes (comma separated)">
              <Input value={(form.plot_sizes ?? []).join(", ")} onChange={(e) => set("plot_sizes", listOf(e.target.value))} placeholder="5 marla, 10 marla, 1 kanal" />
            </Field>
            <Field label="Utilities">
              <div className="flex flex-wrap gap-1.5">
                {UTILITIES.map((u) => {
                  const on = (form.utilities ?? []).includes(u);
                  return (
                    <button
                      key={u}
                      type="button"
                      onClick={() => set("utilities", on ? form.utilities.filter((x: string) => x !== u) : [...(form.utilities ?? []), u])}
                      className={cn("chip text-xs capitalize", on ? "bg-brand-700 text-white" : "bg-black/5 dark:bg-white/10")}
                    >
                      {u}
                    </button>
                  );
                })}
              </div>
            </Field>
            {text("website", "Website", { placeholder: "https://…" })}
          </>
        )}

        {table === "blocks" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Housing society *">
              <Select value={form.scheme_id ?? ""} onChange={(e) => set("scheme_id", e.target.value)}>
                <option value="">Choose a society</option>
                {schemes.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} · {s.city}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Type">
              <Select value={form.area_type ?? "residential"} onChange={(e) => set("area_type", e.target.value)} options={AREA_TYPES.map((t) => ({ value: t, label: titleCase(t) }))} />
            </Field>
          </div>
        )}

        {table === "landmarks" && (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="City *">
                <Select value={form.city_id ?? ""} onChange={(e) => set("city_id", e.target.value)}>
                  <option value="">Choose a city</option>
                  {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
              </Field>
              <Field label="Landmark type">
                <Select value={form.project_type ?? "mall"} onChange={(e) => set("project_type", e.target.value)}>
                  {["mall", "tower", "mixed_use", "compound_living", "office_complex", "plaza"].map((v) => <option key={v} value={v}>{titleCase(v)}</option>)}
                </Select>
              </Field>
              <Field label="Development status">
                <Select value={form.status ?? "planned"} onChange={(e) => set("status", e.target.value)}>
                  {["planned", "under_construction", "completed"].map((v) => <option key={v} value={v}>{titleCase(v)}</option>)}
                </Select>
              </Field>
              {text("developer", "Developer")}
              {number("floor_count", "Floors", "1")}
              {number("total_area", "Total area (sq ft)")}
              {number("total_units", "Total units", "1")}
              {number("occupancy_rate", "Occupancy rate (%)")}
              {text("address", "Address")}
              {text("website", "Website", { placeholder: "https://…" })}
              {text("completion_date", "Completion date", { placeholder: "YYYY-MM-DD" })}
            </div>
          </>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {number("latitude", "Latitude")}
          {number("longitude", "Longitude")}
        </div>
        <Field label="Description">
          <Textarea value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} rows={3} dir="auto" />
        </Field>

        {table !== "blocks" && (
          <Field label="Sources (where each fact comes from)">
            <div className="space-y-2">
              {sources.map((s, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input value={s.title} onChange={(e) => set("sources", sources.map((x, k) => (k === i ? { ...x, title: e.target.value } : x)))} placeholder="Title" className="w-2/5" />
                  <Input value={s.url} onChange={(e) => set("sources", sources.map((x, k) => (k === i ? { ...x, url: e.target.value } : x)))} placeholder="https://…" className="flex-1" />
                  {s.url && (
                    <a href={s.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-icon h-9 w-9" title="Open">
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                  <button type="button" className="btn btn-ghost btn-icon h-9 w-9" title="Remove" onClick={() => set("sources", sources.filter((_, k) => k !== i))}>
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <Button size="sm" variant="soft" icon={<Plus className="h-4 w-4" />} onClick={() => set("sources", [...sources, { title: "", url: "" }])}>
                Add source
              </Button>
            </div>
          </Field>
        )}
      </div>
      <div className="sticky bottom-0 -mx-5 flex justify-end gap-2 border-t border-black/5 bg-white px-5 py-3 dark:border-white/10 dark:bg-brand-950">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button loading={busy} disabled={!form.name?.trim() || ((table === "schemes" || table === "landmarks") && !form.city_id) || (table === "blocks" && !form.scheme_id)} onClick={save}>
          {isNew ? "Add" : "Save"}
        </Button>
      </div>
    </Drawer>
  );
}

