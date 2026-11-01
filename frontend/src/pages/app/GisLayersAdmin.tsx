/**
 * Administration › GIS layers: upload, edit, replace, download and delete the portal's map layers
 * (GeoJSON, KML, GPX or CSV), and switch each one on or off for the public map
 * (/gis/layers*, permission gis.manage).
 *
 * "Published" decides whether a layer exists on the public map at all; "On by default" whether it
 * is drawn before a visitor chooses (visitors can still switch published layers on and off in the
 * map's Layers panel). Layers generated from the DHA master plans are marked and their geometry
 * is rebuilt from the plan files, so replace those only on purpose.
 */
import { useMemo, useRef, useState } from "react";
import { Download, Eye, FileUp, Layers, Map as MapIcon, Pencil, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { del, get, post, put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { num, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Button, Card, Drawer, EmptyState, ErrorState, Field, Input, Modal, PageHeader, Select, Skeleton, Textarea, Toggle } from "@/components/ui";

type Row = {
  id: string;
  name: string;
  layer_type: string;
  entity_type: string;
  entity_id: string;
  visible: boolean;
  published: boolean;
  features: number;
  description?: string | null;
  z_index: number;
  opacity: number;
  style?: { color?: string; fillColor?: string; fillOpacity?: number; weight?: number };
  source_url?: string | null;
  source_file?: string | null;
  created_by?: string | null;
  derived: boolean;
  builtin?: string | null;
  updated_at: string;
  image_url?: string | null;
};
interface ImportStats {
  format: string;
  features?: number;
  dropped?: number;
  geometry_types?: Record<string, number>;
  vertices?: number;
  bbox?: [number, number, number, number];
  bounds?: [[number, number], [number, number]];
  inside_pakistan_pct?: number;
  property_keys?: string[];
  warnings?: string[];
}
type GroundControlPoint = { image: [number, number]; geo: [number, number] };
type UploadCheck = { kind: "vector" | "raster"; import: ImportStats; preview_base64?: string; alignment_preview_base64?: string | null; width?: number; height?: number; requires_control_points?: boolean; embedded_georeference?: boolean; georeference?: { rmse_m?: number; quality?: string } };
interface Named {
  id: string;
  name: string;
  city?: string;
}
interface GisStorageStatus {
  backend: string;
  spatial: boolean;
  format: string;
  detail?: string;
  catalog_table?: string;
  feature_table?: string;
}

const LAYER_TYPES = ["zone", "boundary", "road", "green_area", "plot_layout", "master_plan", "annotation", "utility", "flood_risk", "elevation", "raster", "other"];
const ENTITY_TYPES = ["city", "scheme", "block", "bigproject"];
// Request JSON/base64 expands data by roughly a third; stay under the default 30 MB body cap.
const MAX_MB = 20;

const readFile = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? "").split(",", 2)[1] ?? "");
    r.onerror = () => reject(new Error("Couldn't read the file"));
    r.readAsDataURL(file);
  });

export default function GisLayersAdmin() {
  const qc = useQueryClient();
  const list = useApi<{ layers: Row[] }>("/gis/layers");
  const storage = useApi<GisStorageStatus>("/gis/storage");
  const cities = useApi<{ cities: Named[] }>("/cities");
  const schemes = useApi<{ schemes: Named[] }>("/schemes");
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [state, setState] = useState("");
  const [showDerived, setShowDerived] = useState(false);
  const [upload, setUpload] = useState<{ replace?: Row } | null>(null);
  const [edit, setEdit] = useState<Row | null>(null);
  const [confirm, setConfirm] = useState<Row | null>(null);

  const entityName = useMemo(() => {
    const m = new Map<string, string>();
    (cities.data?.cities ?? []).forEach((c) => m.set(c.id, c.name));
    (schemes.data?.schemes ?? []).forEach((s) => m.set(s.id, s.name));
    return m;
  }, [cities.data, schemes.data]);

  const all = list.data?.layers ?? [];
  const rows = all.filter(
    (l) =>
      (showDerived || !l.derived) &&
      (!type || l.layer_type === type) &&
      (!state || (state === "published" ? l.published : state === "hidden" ? !l.published : state === "on" ? l.published && l.visible : l.published && !l.visible)) &&
      (!q.trim() || [l.name, l.description, entityName.get(l.entity_id), l.source_file].some((x) => x?.toLowerCase().includes(q.trim().toLowerCase()))),
  );
  const derivedCount = all.filter((l) => l.derived).length;
  const unpublished = all.filter((l) => !l.published).length;

  const publishAll = async (published: boolean) => {
    try {
      const r = await post<{ changed: number; now_published: number; layers: number }>("/gis/layers/publish", { published, scope: "all" });
      toast.success(published ? `Published ${r.changed} layers — ${r.now_published} of ${r.layers} are on the public map` : `Hid ${r.changed} layers from the public map`);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const refresh = () => void qc.invalidateQueries({ predicate: (x) => String(x.queryKey[0] ?? "").startsWith("/gis/layers") });

  const patch = async (l: Row, body: Partial<Row>, done: string) => {
    try {
      await put(`/gis/layers/${l.id}`, body);
      toast.success(done);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const download = async (l: Row) => {
    try {
      const d = await get<{ geojson: unknown }>(`/gis/layers/${l.id}`);
      const blob = new Blob([JSON.stringify(d.geojson)], { type: "application/geo+json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${l.name.replace(/[^\w\- ]+/g, "").trim() || "layer"}.geojson`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const remove = async (l: Row) => {
    try {
      await del(`/gis/layers/${l.id}`);
      toast.success(`Deleted “${l.name}”`);
      setConfirm(null);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="GIS layers"
        subtitle="Upload, edit and publish the map layers people see on the portal map — boundaries, zones, roads, green areas, plans"
        actions={
          <>
            <Link to="/map" className="btn btn-outline btn-sm">
              <MapIcon className="h-4 w-4" /> Open map
            </Link>
            {unpublished > 0 && (
              <Button size="sm" variant="soft" icon={<Eye className="h-4 w-4" />} onClick={() => publishAll(true)}>
                Publish all ({unpublished})
              </Button>
            )}
            <Button size="sm" icon={<Upload className="h-4 w-4" />} onClick={() => setUpload({})}>
              Upload layer
            </Button>
          </>
        }
      />
      <Card className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <p className="font-semibold">Spatial database storage</p>
          <p className="text-sm text-ink-mute">
            {storage.data?.spatial
              ? `PostGIS is active: geometries are indexed in ${storage.data.feature_table}; layer settings remain in the portal catalog.`
              : storage.data?.detail ?? `Current store: ${storage.data?.backend ?? "checking"} · ${storage.data?.format ?? "checking capability"}.`}
          </p>
        </div>
        <Badge tone={storage.data?.spatial ? "green" : "orange"}>{storage.data?.spatial ? "PostGIS enabled" : "Spatial store unavailable"}</Badge>
      </Card>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-black/5 p-4 dark:border-white/10">
          <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-xl bg-black/5 px-3 dark:bg-white/10">
            <Search className="h-4 w-4 text-ink-mute" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search layers…" className="h-9 w-full bg-transparent text-sm outline-none" />
          </div>
          <Select value={type} onChange={(e) => setType(e.target.value)} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">All types</option>
            {LAYER_TYPES.map((t) => (
              <option key={t} value={t}>
                {titleCase(t)}
              </option>
            ))}
          </Select>
          <Select value={state} onChange={(e) => setState(e.target.value)} className="!h-9 !w-auto !py-0 text-sm">
            <option value="">Any state</option>
            <option value="published">Published</option>
            <option value="on">Published · on by default</option>
            <option value="off">Published · off by default</option>
            <option value="hidden">Hidden (unpublished)</option>
          </Select>
          {derivedCount > 0 && <Toggle checked={showDerived} onChange={setShowDerived} label={`Master-plan layers (${derivedCount})`} />}
          <span className="text-xs text-ink-mute">{rows.length} layers</span>
        </div>

        {list.error ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : list.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : !rows.length ? (
          <div className="p-6">
            <EmptyState icon={<Layers className="h-6 w-6" />} title="No layers here" hint="Upload a GeoJSON, KML, GPX or CSV file, or change the filters." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink-mute">
                <tr className="border-b border-black/5 dark:border-white/10">
                  <th className="px-4 py-2 text-start">Layer</th>
                  <th className="px-2 py-2 text-start">Type</th>
                  <th className="px-2 py-2 text-start">Belongs to</th>
                  <th className="px-2 py-2 text-end">Features</th>
                  <th className="px-2 py-2 text-center">Published</th>
                  <th className="px-2 py-2 text-center">On by default</th>
                  <th className="px-2 py-2 text-start">Updated</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((l) => {
                  const color = l.builtin ? "#146f45" : l.style?.color ?? "#146f45";
                  return (
                    <tr key={l.id} className={cn("border-b border-black/5 last:border-0 dark:border-white/10", !l.published && "opacity-60")}>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span className="h-6 w-6 shrink-0 rounded-md border-2" style={{ borderColor: color, background: `${l.builtin ? color : l.style?.fillColor ?? color}33` }} />
                          <div className="min-w-0">
                            <p className="truncate font-semibold">{l.name}</p>
                            <p className="truncate text-[11px] text-ink-mute">
                              {l.builtin ? "Built-in map overlay" : l.derived ? "Built from the master-plan PDF" : l.source_file ? `From ${l.source_file}` : l.description || "—"}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-2 py-2.5">
                        <Badge tone={l.builtin ? "blue" : "gray"}>{l.builtin ? "Built-in" : titleCase(l.layer_type)}</Badge>
                      </td>
                      <td className="max-w-[180px] truncate px-2 py-2.5 text-ink-soft">
                        {titleCase(l.entity_type)} · {entityName.get(l.entity_id) ?? l.entity_id}
                      </td>
                      <td className="px-2 py-2.5 text-end tabular-nums">{l.builtin ? "—" : num(l.features)}</td>
                      <td className="px-2 py-2.5 text-center">
                        <div className="inline-flex">
                          <Toggle checked={l.published} onChange={(v) => patch(l, { published: v }, v ? `“${l.name}” is on the public map` : `“${l.name}” is hidden from the public map`)} />
                        </div>
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        <div className={cn("inline-flex", !l.published && "pointer-events-none")}>
                          <Toggle checked={l.visible} onChange={(v) => patch(l, { visible: v }, v ? "Drawn by default" : "Off by default (visitors can switch it on)")} />
                        </div>
                      </td>
                      <td className="px-2 py-2.5 text-xs text-ink-mute">{new Date(l.updated_at).toLocaleDateString()}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-end">
                        <button type="button" className="btn btn-ghost btn-icon h-8 w-8" title="Edit" onClick={() => setEdit(l)}>
                          <Pencil className="h-4 w-4" />
                        </button>
                        {!l.builtin && (
                          <>
                            <button type="button" className="btn btn-ghost btn-icon h-8 w-8" title="Replace the geometry with a new file" onClick={() => setUpload({ replace: l })}>
                              <RefreshCw className="h-4 w-4" />
                            </button>
                            <button type="button" className="btn btn-ghost btn-icon h-8 w-8" title="Download GeoJSON" onClick={() => download(l)}>
                              <Download className="h-4 w-4" />
                            </button>
                            <button type="button" className="btn btn-ghost btn-icon h-8 w-8 text-red-600" title="Delete" onClick={() => setConfirm(l)}>
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <UploadDrawer state={upload} cities={cities.data?.cities ?? []} schemes={schemes.data?.schemes ?? []} onClose={() => setUpload(null)} onSaved={refresh} />
      <EditDrawer layer={edit} cities={cities.data?.cities ?? []} schemes={schemes.data?.schemes ?? []} onClose={() => setEdit(null)} onSaved={refresh} />

      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={`Delete “${confirm?.name ?? ""}”?`}
        subtitle={confirm?.derived ? "This layer is rebuilt from the master plan only if the plan is imported again." : "This can't be undone. Download it first if you may need it again."}
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
          {num(confirm?.features ?? 0)} features will be removed from the map for everyone.
        </p>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ shared bits

function EntityPicker({ entityType, entityId, onChange, cities, schemes }: { entityType: string; entityId: string; onChange: (type: string, id: string) => void; cities: Named[]; schemes: Named[] }) {
  const options = entityType === "city" ? cities : entityType === "scheme" ? schemes : [];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Belongs to">
        <Select value={entityType} onChange={(e) => onChange(e.target.value, e.target.value === "city" ? "pakistan" : "")}>
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t === "bigproject" ? "Big project" : titleCase(t)}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={entityType === "city" ? "City (or all of Pakistan)" : "Which one"} hint={options.length ? undefined : "Paste the record's id"}>
        {options.length ? (
          <Select value={entityId} onChange={(e) => onChange(entityType, e.target.value)}>
            {entityType === "city" && <option value="pakistan">All of Pakistan</option>}
            {entityType !== "city" && <option value="">Choose…</option>}
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
                {o.city ? ` · ${o.city}` : ""}
              </option>
            ))}
          </Select>
        ) : (
          <Input value={entityId} onChange={(e) => onChange(entityType, e.target.value)} />
        )}
      </Field>
    </div>
  );
}

function StatsCard({ stats }: { stats: ImportStats }) {
  return (
    <div className="space-y-2 rounded-xl border border-black/5 bg-brand-50/40 p-3 text-sm dark:border-white/10 dark:bg-white/5">
      <p className="font-semibold">
        {num(stats.features ?? 0)} feature{stats.features === 1 ? "" : "s"} read from {stats.format.toUpperCase()}
        {stats.dropped ? ` · ${stats.dropped} skipped` : ""}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(stats.geometry_types ?? {}).map(([t, n]) => (
          <Badge key={t} tone="blue">
            {n} × {t}
          </Badge>
        ))}
        {stats.inside_pakistan_pct !== undefined && <Badge tone={stats.inside_pakistan_pct >= 50 ? "green" : "orange"}>{stats.inside_pakistan_pct}% inside Pakistan</Badge>}
      </div>
      {(stats.bbox || stats.bounds) && <p className="text-[11px] text-ink-mute">
        {stats.bbox ? `Box ${stats.bbox.map((v) => v.toFixed(4)).join(", ")}` : `WGS84 bounds ${stats.bounds?.flat().map((v) => v.toFixed(5)).join(", ")}`}
        {stats.vertices !== undefined && ` · ${num(stats.vertices)} vertices`}
        {stats.property_keys?.length ? ` · attributes: ${stats.property_keys.slice(0, 8).join(", ")}` : ""}
      </p>}
      {(stats.warnings ?? []).map((w) => (
        <p key={w} className="text-[12px] text-orange-700 dark:text-orange-300">
          ⚠ {w}
        </p>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ upload

function UploadDrawer({ state, cities, schemes, onClose, onSaved }: { state: { replace?: Row } | null; cities: Named[]; schemes: Named[]; onClose: () => void; onSaved: () => void }) {
  const replace = state?.replace;
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<{ name: string; base64: string } | null>(null);
  const [stats, setStats] = useState<ImportStats | null>(null);
  const [check, setCheck] = useState<UploadCheck | null>(null);
  const [georeferenceMode, setGeoreferenceMode] = useState<"auto" | "assisted" | "manual">("auto");
  const [controlPoints, setControlPoints] = useState<GroundControlPoint[]>([]);
  const [pickedPixel, setPickedPixel] = useState<[number, number] | null>(null);
  const [pointLatLon, setPointLatLon] = useState({ lat: "", lon: "" });
  const [sourceCrs, setSourceCrs] = useState("");
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", layer_type: "zone", entity_type: "city", entity_id: "pakistan", description: "", color: "#146f45", visible: true, published: true, source_url: "" });
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));

  const reset = () => {
    setFile(null);
    setStats(null);
    setCheck(null);
    setControlPoints([]);
    setPickedPixel(null);
    setGeoreferenceMode("auto");
    setSourceCrs("");
    if (fileRef.current) fileRef.current.value = "";
  };
  const close = () => {
    reset();
    onClose();
  };

  const runCheck = async (selected: { name: string; base64: string }, mode = georeferenceMode, points = controlPoints, crs = sourceCrs) => {
    const result = await post<UploadCheck>("/gis/layers/upload", {
      filename: selected.name, content_base64: selected.base64, dry_run: true,
      georeference_mode: mode, control_points: points, source_crs: crs || undefined,
    });
    setCheck(result);
    setStats(result.import);
  };

  const choose = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) {
      toast.error(`That file is larger than ${MAX_MB} MB — simplify it or split it`);
      return;
    }
    setChecking(true);
    setStats(null);
    setControlPoints([]);
    setPickedPixel(null);
    setGeoreferenceMode("auto");
    setSourceCrs("");
    try {
      const base64 = await readFile(f);
      const selected = { name: f.name, base64 };
      setFile(selected);
      if (!form.name && !replace) set({ name: f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ") });
      await runCheck(selected, "auto", [], "");
    } catch (e) {
      toast.error((e as Error).message);
      setFile(null);
    } finally {
      setChecking(false);
    }
  };

  const save = async () => {
    if (!file || !stats) return;
    setSaving(true);
    try {
      const style = { color: form.color, fillColor: form.color, fillOpacity: 0.25, weight: 2, opacity: 0.9 };
      await post("/gis/layers/upload", {
        filename: file.name,
        content_base64: file.base64,
        georeference_mode: georeferenceMode,
        control_points: controlPoints,
        source_crs: sourceCrs || undefined,
        ...(replace
          ? { replace_layer_id: replace.id }
          : { name: form.name, layer_type: form.layer_type, entity_type: form.entity_type, entity_id: form.entity_id || "pakistan", description: form.description || undefined, style, visible: form.visible, published: form.published, source_url: form.source_url || undefined }),
      });
      toast.success(replace ? `Replaced the geometry of “${replace.name}”` : `Added “${form.name}” to the map`);
      onSaved();
      close();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer open={!!state} onClose={close} title={replace ? `Replace geometry · ${replace.name}` : "Upload a GIS layer"} width="max-w-xl">
      <div className="space-y-4 p-5 pb-24">
        <label
          className="flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-brand-200 p-6 text-center hover:bg-brand-50/50 dark:border-white/15 dark:hover:bg-white/5"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            void choose(e.dataTransfer.files?.[0]);
          }}
        >
          <FileUp className="h-7 w-7 text-brand-600" />
          <span className="text-sm font-semibold">{file ? file.name : "Choose or drop a file"}</span>
          <span className="text-xs text-ink-mute">GeoJSON, KML, GPX, CSV, images, georeferenced PDF, ECW, DWG/DGN, GeoPackage, or ZIP containing a shapefile/file geodatabase · up to {MAX_MB} MB. GDAL/OGR drivers are required; ECW/DWG drivers depend on the server build.</span>
          <input ref={fileRef} type="file" accept=".geojson,.json,.kml,.gpx,.csv,.png,.jpg,.jpeg,.tif,.tiff,.ecw,.pdf,.dwg,.dgn,.zip,.gpkg" className="hidden" onChange={(e) => void choose(e.target.files?.[0])} />
        </label>
        {file && check?.kind === "raster" && (
          <div className="space-y-3 rounded-xl border border-black/5 p-3 dark:border-white/10">
            <Field label="Georeferencing method">
              <Select value={georeferenceMode} onChange={(e) => { const mode = e.target.value as typeof georeferenceMode; setGeoreferenceMode(mode); setStats(null); }}>
                <option value="auto">Automatic · use embedded coordinates</option>
                <option value="assisted">Assisted · use embedded data or add control points</option>
                <option value="manual">Manual · rectify with control points</option>
              </Select>
            </Field>
            <Field label="Source CRS (optional)" hint="Use an EPSG code, such as EPSG:32643, when the file has a known CRS but lacks CRS metadata.">
              <Input value={sourceCrs} onChange={(e) => { setSourceCrs(e.target.value); setStats(null); }} placeholder="EPSG:4326" />
            </Field>
            {check.preview_base64 && <div>
              <p className="mb-1 text-xs text-ink-mute">Click the image to capture pixel coordinates (origin at top left), then enter its matching map latitude/longitude.</p>
              <img src={`data:image/png;base64,${check.preview_base64}`} alt="Raster source preview" className="max-h-64 max-w-full cursor-crosshair rounded-lg border" onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const x = Math.round((e.clientX - rect.left) / rect.width * (check.width ?? e.currentTarget.naturalWidth));
                const y = Math.round((e.clientY - rect.top) / rect.height * (check.height ?? e.currentTarget.naturalHeight));
                setPickedPixel([x, y]);
              }} />
            </div>}
            <div className="grid grid-cols-2 gap-2">
              <Field label={`Pixel X${pickedPixel ? ` · ${pickedPixel[0]}` : ""}`}><Input readOnly value={pickedPixel?.[0] ?? "Click the image"} /></Field>
              <Field label={`Pixel Y${pickedPixel ? ` · ${pickedPixel[1]}` : ""}`}><Input readOnly value={pickedPixel?.[1] ?? "Click the image"} /></Field>
              <Field label="Latitude"><Input type="number" step="any" value={pointLatLon.lat} onChange={(e) => setPointLatLon((p) => ({ ...p, lat: e.target.value }))} /></Field>
              <Field label="Longitude"><Input type="number" step="any" value={pointLatLon.lon} onChange={(e) => setPointLatLon((p) => ({ ...p, lon: e.target.value }))} /></Field>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={!pickedPixel || !pointLatLon.lat || !pointLatLon.lon} onClick={() => {
                const next = [...controlPoints, { image: pickedPixel!, geo: [Number(pointLatLon.lat), Number(pointLatLon.lon)] as [number, number] }];
                setControlPoints(next); setPickedPixel(null); setPointLatLon({ lat: "", lon: "" }); setStats(null);
              }}>Add control point ({controlPoints.length})</Button>
              <Button size="sm" variant="outline" disabled={!file || checking} loading={checking} onClick={async () => { if (!file) return; setChecking(true); try { await runCheck(file); } catch (e) { toast.error((e as Error).message); } finally { setChecking(false); } }}>Estimate / check alignment</Button>
            </div>
            {!!controlPoints.length && <div className="space-y-1 text-xs">{controlPoints.map((p, i) => <div key={i} className="flex justify-between">GCP {i + 1}: px {p.image.join(", ")} → {p.geo.join(", ")}<button className="text-red-600" onClick={() => { setControlPoints(controlPoints.filter((_, j) => j !== i)); setStats(null); }}>Remove</button></div>)}</div>}
            {check.alignment_preview_base64 && <div><p className="mb-1 text-xs font-medium">Rectified preview · RMSE {check.georeference?.rmse_m?.toFixed(1) ?? "—"} m · {check.georeference?.quality ?? "embedded"}</p><img src={`data:image/png;base64,${check.alignment_preview_base64}`} alt="Georeferenced map preview" className="max-h-64 max-w-full rounded-lg border" /></div>}
          </div>
        )}
        {checking && <Skeleton className="h-20" />}
        {stats && <StatsCard stats={stats} />}

        {!replace && (
          <>
            <Field label="Layer name">
              <Input value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Islamabad green belts" />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Type">
                <Select value={form.layer_type} onChange={(e) => set({ layer_type: e.target.value })}>
                  {LAYER_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {titleCase(t)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Colour">
                <input type="color" value={form.color} onChange={(e) => set({ color: e.target.value })} className="h-10 w-full cursor-pointer rounded-xl border border-black/10 bg-transparent dark:border-white/15" />
              </Field>
            </div>
            <EntityPicker entityType={form.entity_type} entityId={form.entity_id} cities={cities} schemes={schemes} onChange={(entity_type, entity_id) => set({ entity_type, entity_id })} />
            <Field label="Description" hint="Shown in the map's layer list — say where the data comes from and how current it is.">
              <Textarea rows={3} value={form.description} onChange={(e) => set({ description: e.target.value })} />
            </Field>
            <Field label="Source link" hint="The authority / dataset the file came from (shown to admins and in exports).">
              <Input value={form.source_url} onChange={(e) => set({ source_url: e.target.value })} placeholder="https://…" />
            </Field>
            <div className="flex flex-wrap gap-6">
              <Toggle checked={form.published} onChange={(v) => set({ published: v })} label="Published on the public map" />
              <Toggle checked={form.visible} onChange={(v) => set({ visible: v })} label="On by default" />
            </div>
          </>
        )}
        {replace && <p className="text-sm text-ink-soft">The layer keeps its name, style and settings; only its features are replaced by the file's.</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button icon={<Upload className="h-4 w-4" />} disabled={!stats || check?.requires_control_points || saving || (!replace && !form.name.trim())} onClick={save}>
            {saving ? "Saving…" : replace ? "Replace geometry" : "Save layer"}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}

// ------------------------------------------------------------------ edit

function EditDrawer({ layer, cities, schemes, onClose, onSaved }: { layer: Row | null; cities: Named[]; schemes: Named[]; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Row | null>(null);
  const [saving, setSaving] = useState(false);
  const current = form && layer && form.id === layer.id ? form : layer;
  const set = (patch: Partial<Row>) => setForm({ ...(current as Row), ...patch });

  const save = async () => {
    if (!current) return;
    setSaving(true);
    try {
      await put(`/gis/layers/${current.id}`, {
        name: current.name,
        description: current.description ?? "",
        layer_type: current.layer_type,
        entity_type: current.entity_type,
        entity_id: current.entity_id,
        z_index: Number(current.z_index) || 0,
        opacity: Number(current.opacity),
        style: current.style,
        source_url: current.source_url ?? "",
        visible: current.visible,
        published: current.published,
      });
      toast.success(`Saved “${current.name}”`);
      onSaved();
      onClose();
      setForm(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const style = current?.style ?? {};
  return (
    <Drawer open={!!layer} onClose={() => { setForm(null); onClose(); }} title={current ? `Edit · ${current.name}` : "Edit layer"} width="max-w-xl">
      {current && (
        <div className="space-y-4 p-5 pb-24">
          <Field label="Name">
            <Input value={current.name} onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Type">
              <Select value={current.layer_type} onChange={(e) => set({ layer_type: e.target.value })}>
                {[...new Set([current.layer_type, ...LAYER_TYPES])].map((t) => (
                  <option key={t} value={t}>
                    {titleCase(t)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Draw order" hint="Higher draws on top">
              <Input type="number" value={current.z_index} onChange={(e) => set({ z_index: Number(e.target.value) })} />
            </Field>
          </div>
          <EntityPicker entityType={current.entity_type} entityId={current.entity_id} cities={cities} schemes={schemes} onChange={(entity_type, entity_id) => set({ entity_type, entity_id })} />
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Line colour">
              <input type="color" value={style.color ?? "#146f45"} onChange={(e) => set({ style: { ...style, color: e.target.value } })} className="h-10 w-full cursor-pointer rounded-xl border border-black/10 bg-transparent dark:border-white/15" />
            </Field>
            <Field label="Fill colour">
              <input type="color" value={style.fillColor ?? style.color ?? "#146f45"} onChange={(e) => set({ style: { ...style, fillColor: e.target.value } })} className="h-10 w-full cursor-pointer rounded-xl border border-black/10 bg-transparent dark:border-white/15" />
            </Field>
            <Field label="Line width">
              <Input type="number" min={0} max={12} value={style.weight ?? 2} onChange={(e) => set({ style: { ...style, weight: Number(e.target.value) } })} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={`Fill opacity · ${Math.round((style.fillOpacity ?? 0.25) * 100)}%`}>
              <input type="range" min={0} max={1} step={0.05} value={style.fillOpacity ?? 0.25} onChange={(e) => set({ style: { ...style, fillOpacity: Number(e.target.value) } })} className="w-full" />
            </Field>
            <Field label={`Layer opacity · ${Math.round(current.opacity * 100)}%`}>
              <input type="range" min={0} max={1} step={0.05} value={current.opacity} onChange={(e) => set({ opacity: Number(e.target.value) })} className="w-full" />
            </Field>
          </div>
          <Field label="Description">
            <Textarea rows={3} value={current.description ?? ""} onChange={(e) => set({ description: e.target.value })} />
          </Field>
          <Field label="Source link">
            <Input value={current.source_url ?? ""} onChange={(e) => set({ source_url: e.target.value })} placeholder="https://…" />
          </Field>
          <div className="flex flex-wrap gap-6">
            <Toggle checked={current.published} onChange={(v) => set({ published: v })} label="Published on the public map" />
            <Toggle checked={current.visible} onChange={(v) => set({ visible: v })} label="On by default" />
          </div>
          <p className="text-[11px] text-ink-mute">
            {num(current.features)} features · {current.derived ? "geometry from the master-plan PDF" : current.source_file ? `from ${current.source_file}` : "added by hand"}
            {current.created_by ? ` · by ${current.created_by}` : ""} · updated {new Date(current.updated_at).toLocaleString()}
          </p>
          <div className="flex justify-between gap-2 pt-2">
            <Link to="/map" className="btn btn-ghost btn-sm">
              <Eye className="h-4 w-4" /> See it on the map
            </Link>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => { setForm(null); onClose(); }}>
                Cancel
              </Button>
              <Button disabled={saving || !current.name.trim()} onClick={save}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}
