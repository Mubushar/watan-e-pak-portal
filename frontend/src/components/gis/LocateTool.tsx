/**
 * Locate: register or correct where a listing, big project or mega-project point is.
 *
 *   1. Find it — search the database; filters bring up the problem cases first
 *      (no location · doubtful: outside Pakistan, far from its city / society, on the city centre).
 *   2. Place it — any of: click the map / drag the gold pin · type or paste coordinates (decimal,
 *      degrees-minutes-seconds or a Google Maps link) · search a place or address · use this
 *      device's location · snap to its society's centre.
 *   3. Save, or "Save & next" to walk through the list.
 *
 *   GET /admin/locations?kind&q&status&page    PUT /admin/properties/{id} · /bigprojects/{id} · /geo/megaprojects/{id}
 */
import { useEffect, useMemo, useState } from "react";
import type L from "leaflet";
import { CircleMarker, Tooltip } from "react-leaflet";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Building2, CheckCircle2, ChevronLeft, ChevronRight, Crosshair, Hash, Home, LocateFixed, MapPin, MapPinOff, Milestone, MousePointerClick, Navigation, RotateCcw, Save, Search, X } from "lucide-react";
import { toast } from "sonner";
import { get, put } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";
import type { Draft, EditRights, LatLng } from "./GeoEditor";

type Kind = "property" | "project" | "mega";
type Status = "problems" | "missing" | "suspect" | "all";
export interface LocRow {
  kind: Kind;
  id: string;
  name: string;
  subtitle?: string;
  city?: string | null;
  city_center?: LatLng | null;
  society?: { id: string; name: string; latitude?: number | null; longitude?: number | null } | null;
  latitude?: number | null;
  longitude?: number | null;
  radius_km?: number | null;
  status: "missing" | "suspect" | "ok";
  issue?: string | null;
}
interface LocPage {
  total: number;
  page: number;
  pages: number;
  counts: { missing: number; suspect: number; ok: number };
  results: LocRow[];
}

// ------------------------------------------------------------------ coordinates from any text

const inPk = (p: LatLng) => p[0] >= 23 && p[0] <= 37.5 && p[1] >= 60 && p[1] <= 78;

/** Decimal ("33.5252, 73.1493"), DMS ("33°31'30.9"N 73°08'57.5"E") or a Google / OSM map link. */
export function parseCoordinates(text: string): LatLng | null {
  const t = text.trim();
  if (!t) return null;
  const link = t.match(/@(-?\d+\.\d+),\s*(-?\d+\.\d+)/) ?? t.match(/[?&](?:q|ll|query|destination)=(-?\d+\.\d+)(?:,|%2C)\s*(-?\d+\.\d+)/i) ?? t.match(/[#&]map=\d+\/(-?\d+\.\d+)\/(-?\d+\.\d+)/);
  if (link) return [Number(link[1]), Number(link[2])];
  const dms = [...t.matchAll(/(\d+(?:\.\d+)?)\s*°\s*(?:(\d+(?:\.\d+)?)\s*['′]\s*)?(?:(\d+(?:\.\d+)?)\s*(?:["″]|''))?\s*([NSEW])?/gi)];
  if (dms.length >= 2) {
    const val = (m: RegExpMatchArray) => {
      const v = Number(m[1]) + Number(m[2] ?? 0) / 60 + Number(m[3] ?? 0) / 3600;
      return /[SW]/i.test(m[4] ?? "") ? -v : v;
    };
    const a = val(dms[0]!);
    const b = val(dms[1]!);
    return /[EW]/i.test(dms[0]![4] ?? "") ? [b, a] : [a, b];
  }
  const nums = t.match(/-?\d+(?:\.\d+)?/g);
  if (nums && nums.length >= 2) {
    const a = Number(nums[0]);
    const b = Number(nums[1]);
    // Pakistan: latitude 23–37, longitude 60–78 — so a swapped pair is easy to spot
    return a > 50 && b < 40 ? [b, a] : [a, b];
  }
  return null;
}

export function metres(a: LatLng, b: LatLng): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(r(b[0] - a[0]) / 2) ** 2 + Math.cos(r(a[0])) * Math.cos(r(b[0])) * Math.sin(r(b[1] - a[1]) / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}
const dist = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(m >= 10_000 ? 0 : 1)} km` : `${Math.round(m)} m`);

/** The saved (old) spot, faint, so the admin sees how far the pin moved. Render inside the map. */
export function LocateMarks({ row }: { row: LocRow | null }) {
  if (!row || row.latitude == null || row.longitude == null) return null;
  return (
    <CircleMarker center={[row.latitude, row.longitude]} radius={7} pathOptions={{ color: "#64748b", weight: 2, dashArray: "3 3", fillColor: "#94a3b8", fillOpacity: 0.35 }}>
      <Tooltip direction="top">Saved location</Tooltip>
    </CircleMarker>
  );
}

const KINDS: { key: Kind; label: string; icon: typeof Home; right: keyof EditRights }[] = [
  { key: "property", label: "Listings", icon: Home, right: "property" },
  { key: "project", label: "Projects", icon: Building2, right: "project" },
  { key: "mega", label: "Mega pts", icon: Milestone, right: "mega" },
];
type Method = "map" | "coords" | "place" | "device" | "society";

export function LocatePanel({
  rights,
  draft,
  setDraft,
  row,
  setRow,
  map,
  onClose,
}: {
  rights: EditRights;
  /** The pin being placed (drawn and dragged by GeoEditLayer). */
  draft: Draft | null;
  setDraft: (d: Draft | null) => void;
  row: LocRow | null;
  setRow: (r: LocRow | null) => void;
  map: L.Map | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const kinds = KINDS.filter((k) => rights[k.right]);
  const [kind, setKind] = useState<Kind>(kinds[0]?.key ?? "property");
  const [status, setStatus] = useState<Status>("problems");
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const t = setTimeout(() => setQ(text), 300);
    return () => clearTimeout(t);
  }, [text]);
  useEffect(() => setPage(1), [kind, status, q]);
  const list = useApi<LocPage>("/admin/locations", { kind, q, status, page, page_size: 25 });

  const pin = draft?.geom.type === "point" ? draft.geom.at : null;
  const setPin = (at: LatLng, fly = true) => {
    if (!row) return;
    setDraft({ kind: row.kind, id: row.id, fields: {}, geom: { type: "point", at } });
    if (fly) map?.flyTo(at, Math.max(map.getZoom(), 17), { duration: 0.6 });
  };

  const open = (r: LocRow) => {
    setRow(r);
    setMethod("map");
    const saved: LatLng | null = r.latitude != null && r.longitude != null ? [r.latitude, r.longitude] : null;
    setDraft({ kind: r.kind, id: r.id, fields: {}, geom: { type: "point", at: saved } });
    const focus = saved ?? (r.society?.latitude != null ? ([r.society.latitude, r.society.longitude!] as LatLng) : (r.city_center ?? null));
    if (focus) map?.flyTo(focus, saved ? 17 : r.society?.latitude != null ? 15 : 12, { duration: 0.7 });
  };

  // ---- ways to place the pin
  const [method, setMethod] = useState<Method>("map");
  const [coordText, setCoordText] = useState("");
  const parsed = useMemo(() => parseCoordinates(coordText), [coordText]);
  const [placeText, setPlaceText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const findPlace = async () => {
    if (!placeText.trim()) return;
    setBusy("place");
    try {
      const hit = await get<{ lat?: number; lon?: number; latitude?: number; longitude?: number; label?: string; name?: string; found?: boolean }>("/geo/geocode", { q: placeText.trim() }, { noFallback: true });
      const lat = hit.lat ?? hit.latitude;
      const lon = hit.lon ?? hit.longitude;
      if (lat == null || lon == null || hit.found === false) throw new Error(`Couldn't find “${placeText.trim()}”`);
      setPin([lat, lon]);
      toast.success(`Pinned at ${hit.label ?? hit.name ?? placeText.trim()} — drag the pin to the exact spot`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const useDevice = () => {
    if (!("geolocation" in navigator)) return toast.error("This device can't share its location");
    setBusy("device");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setBusy(null);
        setPin([p.coords.latitude, p.coords.longitude]);
        toast.success(`Your location (±${Math.round(p.coords.accuracy)} m)`);
      },
      () => {
        setBusy(null);
        toast.error("Couldn't read this device's location");
      },
      { enableHighAccuracy: true, timeout: 20_000 },
    );
  };

  // ---- checks on the new spot (same rules as the server)
  const saved: LatLng | null = row && row.latitude != null && row.longitude != null ? [row.latitude, row.longitude] : null;
  const moved = pin && saved ? metres(pin, saved) : null;
  const warning = !pin
    ? null
    : !inPk(pin)
      ? "This spot is outside Pakistan"
      : row?.society?.latitude != null && metres(pin, [row.society.latitude, row.society.longitude!]) > 8000
        ? `${dist(metres(pin, [row.society.latitude, row.society.longitude!]))} from ${row.society.name}`
        : row?.city_center && metres(pin, row.city_center) > 40_000
          ? `${dist(metres(pin, row.city_center))} from ${row.city}`
          : null;

  const save = async (next: boolean) => {
    if (!row || !pin) return;
    setBusy("save");
    try {
      const at = { latitude: Number(pin[0].toFixed(7)), longitude: Number(pin[1].toFixed(7)) };
      let r: { error?: string } | null = null;
      if (row.kind === "property") r = await put(`/admin/properties/${row.id}`, at);
      else if (row.kind === "project") r = await put(`/bigprojects/${row.id}`, at);
      else r = await put(`/geo/megaprojects/${row.id}`, { geometry: { type: "point", center: [at.latitude, at.longitude], radius_km: row.radius_km ?? 0.3 } });
      if (r?.error) throw new Error(r.error);
      toast.success(`Location saved for “${row.name}”`);
      await qc.invalidateQueries({ predicate: (x) => typeof x.queryKey[0] === "string" && ["/admin/locations", "/admin/properties", "/properties", "/search", "/bigprojects", "/geo/megaprojects"].some((p) => (x.queryKey[0] as string).startsWith(p)) });
      const rows = list.data?.results ?? [];
      // the next one down the list, or wrap round to the first one still waiting
      const after = rows[rows.findIndex((x) => x.id === row.id) + 1] ?? rows.find((x) => x.id !== row.id && x.status !== "ok");
      if (next && after) open(after);
      else {
        setRow(null);
        setDraft(null);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const chip = (active: boolean) => cn("rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 transition", active ? "bg-brand-700 text-white ring-brand-700" : "text-ink-soft ring-black/10 hover:ring-brand-300 dark:text-slate-300 dark:ring-white/15");
  const badge = (r: LocRow) =>
    r.status === "missing" ? (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-600"><MapPinOff className="h-3 w-3" /> No location</span>
    ) : r.status === "suspect" ? (
      <span className="inline-flex items-center gap-1 truncate text-[11px] font-semibold text-amber-600"><AlertTriangle className="h-3 w-3 shrink-0" /> {r.issue}</span>
    ) : (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600"><CheckCircle2 className="h-3 w-3" /> Located</span>
    );

  const METHODS: { key: Method; label: string; icon: typeof MousePointerClick; show: boolean }[] = [
    { key: "map", label: "Map", icon: MousePointerClick, show: true },
    { key: "coords", label: "Coordinates", icon: Hash, show: true },
    { key: "place", label: "Place", icon: Search, show: true },
    { key: "device", label: "My location", icon: Navigation, show: true },
    { key: "society", label: "Society", icon: Crosshair, show: !!row?.society && row.society.latitude != null },
  ];

  return (
    <div className="absolute end-16 top-3 z-[450] flex max-h-[calc(100%-1.5rem)] w-[360px] max-w-[calc(100vw-6rem)] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-black/5 dark:bg-brand-950">
      <div className="flex items-center gap-2 border-b border-black/5 px-4 py-2.5 dark:border-white/10">
        {row ? (
          <button type="button" onClick={() => (setRow(null), setDraft(null))} className="btn btn-ghost btn-icon -ms-1 h-7 w-7" aria-label="Back to the list">
            <ArrowLeft className="h-4 w-4" />
          </button>
        ) : (
          <LocateFixed className="h-4 w-4 text-gold-600" />
        )}
        <p className="min-w-0 flex-1 truncate text-sm font-semibold">{row ? row.name : "Locate · register or fix locations"}</p>
        <button type="button" onClick={onClose} className="btn btn-ghost btn-icon h-7 w-7" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>

      {!row ? (
        <>
          <div className="space-y-2.5 border-b border-black/5 px-4 py-3 dark:border-white/10">
            {kinds.length > 1 && (
              <div className="grid grid-cols-3 gap-1 rounded-xl bg-black/5 p-1 dark:bg-white/10">
                {kinds.map((k) => (
                  <button key={k.key} type="button" onClick={() => setKind(k.key)} className={cn("flex items-center justify-center gap-1 rounded-lg py-1.5 text-xs font-semibold transition", kind === k.key ? "bg-white text-brand-800 shadow-sm dark:bg-brand-900 dark:text-white" : "text-ink-mute")}>
                    <k.icon className="h-3.5 w-3.5" /> {k.label}
                  </button>
                ))}
              </div>
            )}
            <label className="flex items-center gap-2 rounded-xl px-3 ring-1 ring-black/10 focus-within:ring-brand-400 dark:ring-white/15">
              <Search className="h-4 w-4 text-ink-mute" />
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search by name, address, plot no. or ID" className="h-9 w-full bg-transparent text-sm outline-none" />
            </label>
            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  ["problems", `Needs fixing ${list.data ? list.data.counts.missing + list.data.counts.suspect : ""}`],
                  ["missing", `No location ${list.data?.counts.missing ?? ""}`],
                  ["suspect", `Doubtful ${list.data?.counts.suspect ?? ""}`],
                  ["all", "All"],
                ] as [Status, string][]
              ).map(([k, label]) => (
                <button key={k} type="button" onClick={() => setStatus(k)} className={chip(status === k)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {list.isLoading ? (
              <p className="p-4 text-center text-sm text-ink-mute">Loading…</p>
            ) : list.error ? (
              <p className="p-4 text-center text-sm text-red-600">{list.error.message}</p>
            ) : !list.data?.results.length ? (
              <p className="p-6 text-center text-sm text-ink-mute">{status === "all" ? "Nothing found." : "Nothing to fix here 🎉"}</p>
            ) : (
              list.data.results.map((r) => (
                <button key={r.id} type="button" onClick={() => open(r)} className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-start transition hover:bg-brand-50 dark:hover:bg-white/5">
                  <MapPin className={cn("h-4 w-4 shrink-0", r.status === "missing" ? "text-red-500" : r.status === "suspect" ? "text-amber-500" : "text-emerald-600")} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{r.name}</span>
                    <span className="block truncate text-[11px] text-ink-mute">{r.subtitle || r.city || "—"}</span>
                    {badge(r)}
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-ink-mute rtl:rotate-180" />
                </button>
              ))
            )}
          </div>
          {list.data && list.data.pages > 1 && (
            <div className="flex items-center justify-between border-t border-black/5 px-3 py-1.5 text-xs dark:border-white/10">
              <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="btn btn-ghost btn-sm disabled:opacity-40">
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-ink-mute">
                Page {list.data.page} of {list.data.pages} · {list.data.total}
              </span>
              <button type="button" disabled={page >= list.data.pages} onClick={() => setPage((p) => p + 1)} className="btn btn-ghost btn-sm disabled:opacity-40">
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
            <div>
              <p className="truncate text-xs text-ink-mute">{row.subtitle || row.city}</p>
              {badge(row)}
            </div>

            <div>
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-mute">Set the location by</p>
              <div className="grid grid-cols-5 gap-1">
                {METHODS.filter((m) => m.show).map((m) => (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => {
                      setMethod(m.key);
                      if (m.key === "device") useDevice();
                      if (m.key === "society" && row.society?.latitude != null) setPin([row.society.latitude, row.society.longitude!]);
                    }}
                    className={cn("flex flex-col items-center gap-1 rounded-xl px-1 py-2 text-[10px] font-semibold ring-1 transition", method === m.key ? "bg-brand-700 text-white ring-brand-700" : "text-ink-soft ring-black/10 hover:ring-brand-300 dark:text-slate-300 dark:ring-white/15")}
                  >
                    <m.icon className="h-4 w-4" /> {m.label}
                  </button>
                ))}
              </div>
            </div>

            {method === "map" && <p className="rounded-xl bg-brand-50/70 p-2.5 text-xs text-ink-soft dark:bg-white/5 dark:text-slate-300">Click the map where it is, then drag the gold pin to the exact spot. The grey dot is the saved location.</p>}
            {method === "coords" && (
              <div className="space-y-1.5">
                <input
                  value={coordText}
                  onChange={(e) => setCoordText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && parsed && setPin(parsed)}
                  placeholder={`33.525261, 73.149310  ·  33°31'30.9"N 73°08'57.5"E  ·  a Google Maps link`}
                  className="input py-1.5 text-xs tabular-nums"
                  autoFocus
                />
                <div className="flex items-center justify-between gap-2 text-[11px]">
                  <span className={cn(parsed ? (inPk(parsed) ? "text-emerald-600" : "text-amber-600") : "text-ink-mute")}>
                    {parsed ? `${parsed[0].toFixed(6)}, ${parsed[1].toFixed(6)}${inPk(parsed) ? "" : " — outside Pakistan"}` : "Decimal, degrees-minutes-seconds or a map link"}
                  </span>
                  <Button size="sm" disabled={!parsed} onClick={() => parsed && setPin(parsed)}>
                    Place pin
                  </Button>
                </div>
              </div>
            )}
            {method === "place" && (
              <div className="flex gap-1.5">
                <input value={placeText} onChange={(e) => setPlaceText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void findPlace()} placeholder="A place, road or address — e.g. Giga Mall" className="input py-1.5 text-xs" autoFocus />
                <Button size="sm" loading={busy === "place"} onClick={findPlace}>
                  Find
                </Button>
              </div>
            )}
            {method === "device" && <p className="rounded-xl bg-brand-50/70 p-2.5 text-xs text-ink-soft dark:bg-white/5 dark:text-slate-300">{busy === "device" ? "Reading this device's location…" : "Standing at it? Your device's location was used — drag the pin if needed."}</p>}
            {method === "society" && row.society && <p className="rounded-xl bg-brand-50/70 p-2.5 text-xs text-ink-soft dark:bg-white/5 dark:text-slate-300">Pinned at the centre of {row.society.name} — drag it to the plot.</p>}

            <div className="rounded-xl ring-1 ring-black/5 p-2.5 text-xs dark:ring-white/10">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink-soft dark:text-slate-300">New location</span>
                {pin && saved && (
                  <button type="button" onClick={() => setPin(saved)} className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand-700 hover:underline dark:text-brand-300">
                    <RotateCcw className="h-3 w-3" /> Saved spot
                  </button>
                )}
              </div>
              <p className="mt-1 tabular-nums">{pin ? `${pin[0].toFixed(6)}, ${pin[1].toFixed(6)}` : "Not placed yet"}</p>
              {moved != null && moved > 1 && <p className="text-ink-mute">Moved {dist(moved)} from the saved location</p>}
              {warning && (
                <p className="mt-1 flex items-center gap-1 font-semibold text-amber-600">
                  <AlertTriangle className="h-3 w-3" /> {warning}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 border-t border-black/5 px-4 py-2.5 dark:border-white/10">
            <Button size="sm" icon={<Save className="h-3.5 w-3.5" />} loading={busy === "save"} disabled={!pin} onClick={() => save(false)}>
              Save
            </Button>
            <Button size="sm" variant="outline" disabled={!pin || busy === "save"} onClick={() => save(true)}>
              Save & next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
