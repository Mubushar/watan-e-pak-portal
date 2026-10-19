/**
 * Field survey: an agent (or admin) on site with a phone, tablet or laptop. Live GPS shows where
 * they stand; around that point the app lists the listings, big projects and mega projects, and
 * lets them — as their rights allow —
 *   • add a listing here (the listing form, pinned with GPS, photos from the camera)
 *   • add a big project or a mega project here (admins), with photos
 *   • move an existing one to where they stand, add site photos, or delete it
 * Everything is saved to the portal database straight away.
 *
 *   GET  /geo/nearby-entities?lat&lon&radius_m
 *   PUT  /me/listings/{id} · /admin/properties/{id} · /bigprojects/{id} · /geo/megaprojects/{id}
 *   POST /me/listings/{id}/photos · /bigprojects/{id}/photos · /geo/megaprojects/{id}/photos
 */
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { Map as LeafletMap, LayerGroup } from "leaflet";
import { Building2, Crosshair, ImagePlus, Loader2, LocateFixed, MapPin, Milestone, Navigation, PlusCircle, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { del, get, post, put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/store/auth";
import type { City } from "@/types";
import { canDo, nearestCity, watchPosition, type Fix } from "@/lib/device";
import { pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CameraButton } from "@/components/CameraButton";
import { Button, EmptyState, Field, Input, Segmented, Select, Sheet, Skeleton, TopBar } from "@/components/ui";

interface NearbyProperty { id: string; title: string; price: number; category: string; city?: string; owner_user_id?: string | null; project_id?: string | null; image?: string | null; distance_m: number }
interface NearbyProject { id: string; name: string; project_type: string; status: string; city?: string; image?: string | null; distance_m: number }
interface NearbyMega { id: string; name: string; type: string; status: string; city?: string; geometry_type: "point" | "line" | "polygon"; image?: string | null; distance_m: number }
interface Nearby { properties: NearbyProperty[]; projects: NearbyProject[]; megaprojects: NearbyMega[] }
type Target = { kind: "property"; item: NearbyProperty } | { kind: "project"; item: NearbyProject } | { kind: "mega"; item: NearbyMega };

const PROJECT_TYPES = ["mixed_use", "mall", "tower", "plaza", "office_complex", "residential_complex", "compound_living"];
const PROJECT_STATUSES = ["planned", "under_construction", "completed"];
const ok = <T,>(r: T) => {
  const e = (r as { error?: string } | null)?.error;
  if (e) throw new Error(e);
  return r;
};

function accuracyTone(m: number) {
  return m <= 15 ? "bg-emerald-500" : m <= 50 ? "bg-amber-500" : "bg-red-500";
}

/** A small live map: where I stand (with the accuracy circle) and what is around. */
function SurveyMap({ fix, nearby, radius }: { fix: Fix | null; nearby?: Nearby; radius: number }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const layer = useRef<LayerGroup | null>(null);
  const L = useRef<typeof import("leaflet") | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let dead = false;
    (async () => {
      const lib = (await import("leaflet")).default;
      await import("leaflet/dist/leaflet.css");
      if (dead || !el.current || map.current) return;
      L.current = lib;
      map.current = lib.map(el.current, { zoomControl: false, attributionControl: true }).setView([33.6844, 73.0479], 12);
      lib.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap", maxZoom: 19 }).addTo(map.current);
      layer.current = lib.layerGroup().addTo(map.current);
      setReady(true);
    })();
    return () => {
      dead = true;
      map.current?.remove();
      map.current = null;
    };
  }, []);
  const centred = useRef(false);
  useEffect(() => {
    const lib = L.current;
    if (!lib || !map.current || !layer.current || !fix) return;
    layer.current.clearLayers();
    const at: [number, number] = [fix.latitude, fix.longitude];
    lib.circle(at, { radius, color: "#c99a22", weight: 1, dashArray: "4 4", fillOpacity: 0.04 }).addTo(layer.current);
    lib.circle(at, { radius: fix.accuracy, color: "#2563eb", weight: 1, fillOpacity: 0.12 }).addTo(layer.current);
    lib.circleMarker(at, { radius: 7, color: "#fff", weight: 3, fillColor: "#2563eb", fillOpacity: 1 }).addTo(layer.current).bindTooltip("You are here");
    if (!centred.current) {
      map.current.setView(at, 17);
      centred.current = true;
    }
  }, [fix, nearby, radius, ready]);
  return <div ref={el} className="h-52 w-full overflow-hidden rounded-2xl ring-1 ring-black/5 dark:ring-white/10" />;
}

export default function Survey() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const rights = { property: canDo(user, "properties.manage"), project: canDo(user, "projects.manage"), mega: canDo(user, "gis.manage") };
  const isAdmin = !!user?.roles?.some((r) => r === "super_admin" || r === "admin");

  // ---- live GPS
  const [fix, setFix] = useState<Fix | null>(null);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [watchKey, setWatchKey] = useState(0);
  useEffect(() => watchPosition((f) => (setFix(f), setGpsError(null)), (e) => setGpsError(e.message)), [watchKey]);

  // ---- what is around (re-asked when I move ~20 m)
  const [radius, setRadius] = useState<"100" | "300" | "1000">("300");
  const lat = fix ? Math.round(fix.latitude * 5000) / 5000 : null;
  const lon = fix ? Math.round(fix.longitude * 5000) / 5000 : null;
  const q = useApi<Nearby>(fix ? "/geo/nearby-entities" : null, fix ? { lat: lat!, lon: lon!, radius_m: Number(radius) } : undefined);
  const cities = useApi<{ cities: City[] }>("/cities");
  const megaMeta = useApi<{ types: Record<string, string>; statuses: Record<string, string> }>(rights.mega ? "/geo/megaprojects" : null);
  const refresh = () =>
    qc.invalidateQueries({ predicate: (x) => typeof x.queryKey[0] === "string" && ["/geo", "/properties", "/search", "/bigprojects", "/me/listings"].some((p) => (x.queryKey[0] as string).startsWith(p)) });

  // ---- acting on one feature
  const [target, setTarget] = useState<Target | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const canEdit = (t: Target) => (t.kind === "property" ? rights.property || t.item.owner_user_id === user?.id : t.kind === "project" ? rights.project : rights.mega);
  const moveHere = async (t: Target) => {
    if (!fix) return;
    setBusy("Saving the location…");
    try {
      const at = { latitude: fix.latitude, longitude: fix.longitude };
      if (t.kind === "property") ok(rights.property ? await put(`/admin/properties/${t.item.id}`, at) : await put(`/me/listings/${t.item.id}`, at));
      else if (t.kind === "project") ok(await put(`/bigprojects/${t.item.id}`, at));
      else {
        const full = await get<{ geometry?: { radius_km?: number } }>(`/geo/megaprojects/${t.item.id}`);
        ok(await put(`/geo/megaprojects/${t.item.id}`, { geometry: { type: "point", center: [fix.latitude, fix.longitude], radius_km: full.geometry?.radius_km ?? 0.3 } }));
      }
      toast.success(`Moved to where you are (±${fix.accuracy} m)`);
      await refresh();
      setTarget(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const addPhotos = async (t: Target, urls: string[]) => {
    const path = t.kind === "property" ? `/me/listings/${t.item.id}/photos` : t.kind === "project" ? `/bigprojects/${t.item.id}/photos` : `/geo/megaprojects/${t.item.id}/photos`;
    for (let i = 0; i < urls.length; i++) {
      setBusy(`Uploading photo ${i + 1} of ${urls.length}…`);
      try {
        await post(path, { data_url: urls[i], is_primary: false });
      } catch (e) {
        toast.error((e as Error).message);
        break;
      }
    }
    setBusy(null);
    toast.success(urls.length === 1 ? "Photo added" : `${urls.length} photos added`);
    await refresh();
  };
  const remove = async (t: Target) => {
    const name = t.kind === "property" ? t.item.title : t.item.name;
    if (!window.confirm(`Delete “${name}”? This can't be undone.`)) return;
    setBusy("Deleting…");
    try {
      ok(await del(t.kind === "property" ? `/admin/properties/${t.item.id}` : t.kind === "project" ? `/bigprojects/${t.item.id}` : `/geo/megaprojects/${t.item.id}`));
      toast.success("Deleted");
      await refresh();
      setTarget(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  // ---- creating here (admins): a big project or a mega project point, with photos
  const [creating, setCreating] = useState<"project" | "mega" | null>(null);
  const [form, setForm] = useState({ name: "", type: "mixed_use", status: "planned", city_id: "" });
  const [photos, setPhotos] = useState<string[]>([]);
  const startCreate = (kind: "project" | "mega") => {
    const c = fix ? nearestCity(fix, cities.data?.cities ?? []) : undefined;
    setForm({ name: "", type: kind === "project" ? "mixed_use" : "cbd", status: "planned", city_id: c?.id ?? "" });
    setPhotos([]);
    setCreating(kind);
  };
  const create = async () => {
    if (!fix || !creating) return;
    if (!form.name.trim()) return toast.error("Give it a name");
    setBusy("Saving…");
    try {
      let id: string;
      let photoPath: (id: string) => string;
      if (creating === "project") {
        if (!form.city_id) throw new Error("Choose a city");
        const r = ok(await post<{ id: string }>("/bigprojects", { name: form.name.trim(), city_id: form.city_id, project_type: form.type, status: form.status, latitude: fix.latitude, longitude: fix.longitude }));
        id = r.id;
        photoPath = (x) => `/bigprojects/${x}/photos`;
      } else {
        const city = cities.data?.cities.find((c) => c.id === form.city_id);
        const r = await post<{ id: string }>("/geo/megaprojects", { name: form.name.trim(), type: form.type, status: form.status, city: city?.name ?? "", province: city?.state ?? "", geometry: { type: "point", center: [fix.latitude, fix.longitude], radius_km: 0.3 } });
        id = r.id;
        photoPath = (x) => `/geo/megaprojects/${x}/photos`;
      }
      for (let i = 0; i < photos.length; i++) {
        setBusy(`Uploading photo ${i + 1} of ${photos.length}…`);
        await post(photoPath(id), { data_url: photos[i], is_primary: i === 0 }).catch((e) => toast.error((e as Error).message));
      }
      toast.success("Added to the map");
      await refresh();
      setCreating(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const data = q.data;
  const count = (data?.properties.length ?? 0) + (data?.projects.length ?? 0) + (data?.megaprojects.length ?? 0);
  const row = (t: Target, title: string, sub: string, img?: string | null, Icon = MapPin) => (
    <button key={`${t.kind}-${t.item.id}`} type="button" onClick={() => setTarget(t)} className="flex w-full items-center gap-3 rounded-xl p-2 text-start transition hover:bg-brand-50 active:scale-[.99] dark:hover:bg-white/5">
      {img ? (
        <img src={img} alt="" className="h-12 w-14 shrink-0 rounded-lg object-cover" />
      ) : (
        <span className="flex h-12 w-14 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-white/5">
          <Icon className="h-5 w-5" />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-brand-900 dark:text-white">{title}</span>
        <span className="block truncate text-xs text-ink-mute">{sub}</span>
      </span>
      <span className="shrink-0 text-xs font-semibold tabular-nums text-ink-mute">{t.item.distance_m} m</span>
    </button>
  );

  return (
    <div>
      <TopBar title="Field survey" back />
      <div className="screen space-y-4 pt-4">
        {/* where I am */}
        <div className="card space-y-3 p-3.5">
          <div className="flex items-center gap-3">
            <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700 dark:bg-white/5 dark:text-brand-200">
              <LocateFixed className="h-5 w-5" />
              {fix && <span className={cn("absolute end-0.5 top-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-white dark:ring-[#0d1f16]", accuracyTone(fix.accuracy))} />}
            </span>
            <div className="min-w-0 flex-1 text-sm">
              {fix ? (
                <>
                  <p className="font-semibold text-brand-900 dark:text-white">You are here · ±{fix.accuracy} m</p>
                  <p className="truncate text-xs tabular-nums text-ink-mute">
                    {fix.latitude.toFixed(6)}, {fix.longitude.toFixed(6)}
                  </p>
                </>
              ) : (
                <p className="font-semibold text-brand-900 dark:text-white">{gpsError ?? "Finding you with GPS…"}</p>
              )}
            </div>
            <button type="button" onClick={() => setWatchKey((k) => k + 1)} className="btn btn-ghost btn-icon" aria-label="Refresh GPS">
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
          <SurveyMap fix={fix} nearby={data} radius={Number(radius)} />
          {fix && fix.accuracy > 50 && <p className="text-xs text-amber-700 dark:text-amber-300">The GPS fix is rough — step outside or wait a moment before saving locations.</p>}
        </div>

        {/* add here */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Button icon={<PlusCircle className="h-4 w-4" />} disabled={!fix} onClick={() => nav("/listings/new", { state: { gps: fix } })}>
            New listing here
          </Button>
          {rights.project && (
            <Button variant="outline" icon={<Building2 className="h-4 w-4" />} disabled={!fix} onClick={() => startCreate("project")}>
              Big project here
            </Button>
          )}
          {rights.mega && (
            <Button variant="outline" icon={<Milestone className="h-4 w-4" />} disabled={!fix} onClick={() => startCreate("mega")}>
              Mega project here
            </Button>
          )}
        </div>

        {/* around me */}
        <div className="card p-3">
          <div className="mb-2 flex items-center justify-between gap-2 px-1">
            <p className="text-sm font-bold text-brand-900 dark:text-white">Around you{data ? ` · ${count}` : ""}</p>
            <Segmented
              value={radius}
              onChange={setRadius}
              options={[
                { value: "100", label: "100m" },
                { value: "300", label: "300m" },
                { value: "1000", label: "1km" },
              ]}
            />
          </div>
          {!fix ? (
            <p className="px-1 py-6 text-center text-sm text-ink-mute">Waiting for your location…</p>
          ) : q.error ? (
            <EmptyState icon={<Crosshair className="h-7 w-7" />} title="Couldn't load what is around you" action={<Button size="sm" variant="outline" onClick={() => q.refetch()}>Try again</Button>}>
              {q.error.message}
            </EmptyState>
          ) : q.isLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : !count ? (
            <EmptyState icon={<Crosshair className="h-7 w-7" />} title="Nothing on the map here yet">
              Add the listing or project you're standing at.
            </EmptyState>
          ) : (
            <div className="space-y-0.5">
              {data!.properties.map((p) => row({ kind: "property", item: p }, p.title, `${titleCase(p.category)} · ${pkrShort(p.price)}${p.city ? ` · ${p.city}` : ""}`, p.image))}
              {data!.projects.map((b) => row({ kind: "project", item: b }, b.name, `${titleCase(b.project_type)} · ${titleCase(b.status)}`, b.image, Building2))}
              {data!.megaprojects.map((m) => row({ kind: "mega", item: m }, m.name, `${megaMeta.data?.types?.[m.type] ?? titleCase(m.type)} · ${titleCase(m.status)}`, m.image, Milestone))}
            </div>
          )}
        </div>
      </div>

      {/* one feature: move here, photos, delete */}
      <Sheet open={!!target} onClose={() => setTarget(null)} title={target ? (target.kind === "property" ? target.item.title : target.item.name) : ""}>
        {target && (
          <div className="space-y-3">
            <p className="text-sm text-ink-mute">
              {target.kind === "property" ? "Listing" : target.kind === "project" ? "Big project" : "Mega project"} · {target.item.distance_m} m from you
            </p>
            {!canEdit(target) ? (
              <p className="rounded-xl bg-brand-50 p-3 text-sm dark:bg-white/5">Only its owner or an administrator can change this one.</p>
            ) : (
              <>
                {(target.kind !== "mega" || target.item.geometry_type === "point") && (
                  <Button className="w-full" icon={<Navigation className="h-4 w-4" />} disabled={!fix || !!busy} onClick={() => moveHere(target)}>
                    Set its location to where I am{fix ? ` (±${fix.accuracy} m)` : ""}
                  </Button>
                )}
                {(target.kind !== "property" || target.item.owner_user_id === user?.id || isAdmin) && (
                  <div className="grid grid-cols-2 gap-2">
                    <CameraButton className="h-20" label="Take photos" multiple onPhotos={(u) => void addPhotos(target, u)} />
                    <label className="flex h-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-brand-300 text-brand-700 dark:border-white/20 dark:text-brand-200">
                      <ImagePlus className="h-6 w-6" />
                      <span className="text-xs font-semibold">From gallery</span>
                      <input
                        type="file"
                        accept="image/*"
                        multiple
                        className="hidden"
                        onChange={async (e) => {
                          const files = Array.from(e.target.files ?? []);
                          e.target.value = "";
                          if (!files.length) return;
                          const { compressImage } = await import("@/lib/images");
                          void addPhotos(target, await Promise.all(files.map((f) => compressImage(f))));
                        }}
                      />
                    </label>
                  </div>
                )}
                {((target.kind === "property" && rights.property) || (target.kind === "project" && rights.project) || (target.kind === "mega" && rights.mega)) && (
                  <Button variant="ghost" className="w-full text-red-600" icon={<Trash2 className="h-4 w-4" />} disabled={!!busy} onClick={() => remove(target)}>
                    Delete
                  </Button>
                )}
              </>
            )}
            {target.kind === "property" && (
              <Link to={`/property/${target.item.id}`} className="btn btn-outline w-full">
                Open the listing
              </Link>
            )}
            {busy && (
              <p className="flex items-center justify-center gap-2 text-sm text-ink-mute">
                <Loader2 className="h-4 w-4 animate-spin" /> {busy}
              </p>
            )}
          </div>
        )}
      </Sheet>

      {/* add a big / mega project here */}
      <Sheet open={!!creating} onClose={() => setCreating(null)} title={creating === "project" ? "Big project here" : "Mega project here"}>
        <div className="space-y-3">
          <p className="text-xs text-ink-mute tabular-nums">{fix ? `At ${fix.latitude.toFixed(6)}, ${fix.longitude.toFixed(6)} · ±${fix.accuracy} m` : "Waiting for GPS…"}</p>
          <Field label="Name">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={creating === "project" ? "e.g. Grand Square Mall" : "e.g. Kashmir Highway interchange"} />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Type">
              <Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                {creating === "project"
                  ? PROJECT_TYPES.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)
                  : Object.entries(megaMeta.data?.types ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {(creating === "project" ? PROJECT_STATUSES : Object.keys(megaMeta.data?.statuses ?? { planned: 1 })).map((s) => (
                  <option key={s} value={s}>{titleCase(s)}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="City">
            <Select value={form.city_id} onChange={(e) => setForm({ ...form, city_id: e.target.value })}>
              <option value="">Choose a city</option>
              {cities.data?.cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <div className="grid grid-cols-4 gap-2">
            {photos.map((src, i) => (
              <img key={i} src={src} alt="" className="aspect-square w-full rounded-lg object-cover" />
            ))}
            <CameraButton className="aspect-square" label="Photo" onPhotos={(u) => setPhotos((p) => [...p, ...u].slice(0, 8))} />
          </div>
          <Button className="w-full" loading={!!busy} disabled={!fix} onClick={create}>
            Save to the map
          </Button>
          {busy && <p className="text-center text-sm text-ink-mute">{busy}</p>}
        </div>
      </Sheet>
    </div>
  );
}
