/**
 * What users and the assistant hand each other in the chat besides text:
 *   - from the user: photos / screenshots, documents (PDF, Word, Excel, text, CSV), map data
 *     (KML, GeoJSON, GPX), and things from the Map page — a pin, a measured distance or area;
 *   - from the assistant: files it made (PDF reports, map pictures) and location cards.
 * The Map page sends its items with shareToChat(); the chat panel (which may not be open yet)
 * picks them up with takePendingShares() / onShare().
 */
import { post } from "./api";
import { areaUnits, centroid, lengthUnits, pathLengthM, polygonAreaM2, type LatLon } from "./geoMeasure";
import { usePrefs } from "@/store/prefs";

export type ChatAttachment =
  | { kind: "image"; name: string; dataUrl: string; width: number; height: number }
  | { kind: "document"; name: string; text: string; pages?: number | null; note?: string | null; truncated?: boolean; size: number }
  | { kind: "geodata"; name: string; summary: string; geojson: GeoJSON.FeatureCollection }
  | { kind: "pin"; label: string; lat: number; lon: number; source: string }
  | { kind: "measure"; label: string; mode: "distance" | "area"; coords: LatLon[]; value_text: string };

/** A file the assistant made (a blob URL, valid while the page is open). */
export interface ChatFile {
  kind: "pdf" | "image";
  name: string;
  url: string;
  size: number;
  caption?: string;
}
/** A shared location under a reply. */
export interface LocationCard {
  label: string;
  lat: number;
  lon: number;
  note?: string;
}

// ------------------------------------------------------------------ map → chat
const EVENT = "watanepak:chat-share";
let pending: { item: ChatAttachment; ask?: string }[] = [];
/** Put a map item into the chat input (opening the assistant); `ask` pre-fills the question. */
export function shareToChat(item: ChatAttachment, ask?: string) {
  pending.push({ item, ask });
  usePrefs.getState().setAssistantOpen(true);
  window.dispatchEvent(new CustomEvent(EVENT));
}
export function takePendingShares() {
  const p = pending;
  pending = [];
  return p;
}
export function onShare(fn: () => void): () => void {
  window.addEventListener(EVENT, fn);
  return () => window.removeEventListener(EVENT, fn);
}

// ------------------------------------------------------------------ chat → map (show an attached shape)
const SHOW_EVENT = "watanepak:map-show-shape";
export interface MapShape {
  id: string;
  name: string;
  geojson: GeoJSON.FeatureCollection;
  /** Fly to it. */
  fit?: boolean;
}
let pendingShapes: MapShape[] = [];
export function showShapeOnMap(s: MapShape) {
  pendingShapes = [...pendingShapes.filter((x) => x.id !== s.id), s];
  window.dispatchEvent(new CustomEvent<MapShape>(SHOW_EVENT, { detail: s }));
}
export function takePendingShapes() {
  const p = pendingShapes;
  pendingShapes = [];
  return p;
}
export function onShowShape(fn: (s: MapShape) => void): () => void {
  const h = (e: Event) => {
    pendingShapes = pendingShapes.filter((x) => x.id !== (e as CustomEvent<MapShape>).detail.id);
    fn((e as CustomEvent<MapShape>).detail);
  };
  window.addEventListener(SHOW_EVENT, h);
  return () => window.removeEventListener(SHOW_EVENT, h);
}

// ------------------------------------------------------------------ reading files the user attaches
export const ACCEPT = "image/*,.pdf,.doc,.docx,.xlsx,.txt,.csv,.tsv,.md,.json,.geojson,.kml,.gpx";
const MAX_FILE = 15 * 1024 * 1024;

function readAs(file: Blob, how: "dataUrl" | "text"): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result));
    r.onerror = () => rej(r.error ?? new Error("couldn't read the file"));
    if (how === "dataUrl") r.readAsDataURL(file);
    else r.readAsText(file);
  });
}

/** A photo, scaled down to `max` px on its longer side, as JPEG (what vision models need, and small). */
async function imageAttachment(file: File, max = 1600): Promise<ChatAttachment> {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k);
  c.height = Math.round(bmp.height * k);
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.drawImage(bmp, 0, 0, c.width, c.height);
  return { kind: "image", name: file.name || "image.jpg", dataUrl: c.toDataURL("image/jpeg", 0.85), width: c.width, height: c.height };
}

/** Read a file the user attached: images stay pictures, map files become shapes, the rest becomes text. */
export async function readAttachment(file: File): Promise<ChatAttachment> {
  if (file.size > MAX_FILE) throw new Error(`${file.name} is larger than 15 MB`);
  const name = file.name.toLowerCase();
  if (file.type.startsWith("image/") && !name.endsWith(".svg")) return imageAttachment(file);
  if (/\.(kml|geojson|gpx)$/.test(name) || (name.endsWith(".json") && file.size < 5_000_000)) {
    const text = await readAs(file, "text");
    const fc = parseGeodata(text, name);
    if (fc) return { kind: "geodata", name: file.name, geojson: fc, summary: summarizeGeodata(fc) };
    if (!name.endsWith(".json")) throw new Error(`${file.name} has no shapes I can read`);
  }
  const r = await post<{ name: string; kind: string; pages: number | null; text: string; truncated: boolean; note: string | null }>("/ai/extract", {
    name: file.name,
    data_url: await readAs(file, "dataUrl"),
  });
  return { kind: "document", name: file.name, text: r.text, pages: r.pages, note: r.note, truncated: r.truncated, size: file.size };
}

// ------------------------------------------------------------------ KML / GPX / GeoJSON
function parseGeodata(text: string, name: string): GeoJSON.FeatureCollection | null {
  try {
    if (name.endsWith(".kml") || /<kml[\s>]/i.test(text)) return kmlToGeojson(text);
    if (name.endsWith(".gpx") || /<gpx[\s>]/i.test(text)) return gpxToGeojson(text);
    const j = JSON.parse(text);
    if (j?.type === "FeatureCollection") return j;
    if (j?.type === "Feature") return { type: "FeatureCollection", features: [j] };
    if (j?.type && j?.coordinates) return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: j }] };
  } catch {
    /* not map data */
  }
  return null;
}

const coordsOf = (s: string): [number, number][] =>
  s
    .trim()
    .split(/\s+/)
    .map((t) => t.split(",").map(Number))
    .filter((c) => c.length >= 2 && Number.isFinite(c[0]) && Number.isFinite(c[1]))
    .map((c) => [c[0]!, c[1]!]); // KML is lon,lat — same as GeoJSON

function kmlToGeojson(text: string): GeoJSON.FeatureCollection {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const features: GeoJSON.Feature[] = [];
  for (const pm of Array.from(doc.getElementsByTagName("Placemark"))) {
    const props = { name: pm.getElementsByTagName("name")[0]?.textContent?.trim() ?? "", description: pm.getElementsByTagName("description")[0]?.textContent?.trim() ?? "" };
    for (const poly of Array.from(pm.getElementsByTagName("Polygon"))) {
      const outer = poly.getElementsByTagName("outerBoundaryIs")[0]?.getElementsByTagName("coordinates")[0]?.textContent ?? poly.getElementsByTagName("coordinates")[0]?.textContent ?? "";
      const ring = coordsOf(outer);
      if (ring.length >= 3) features.push({ type: "Feature", properties: props, geometry: { type: "Polygon", coordinates: [ring] } });
    }
    for (const ls of Array.from(pm.getElementsByTagName("LineString"))) {
      const line = coordsOf(ls.getElementsByTagName("coordinates")[0]?.textContent ?? "");
      if (line.length >= 2) features.push({ type: "Feature", properties: props, geometry: { type: "LineString", coordinates: line } });
    }
    for (const pt of Array.from(pm.getElementsByTagName("Point"))) {
      const c = coordsOf(pt.getElementsByTagName("coordinates")[0]?.textContent ?? "")[0];
      if (c) features.push({ type: "Feature", properties: props, geometry: { type: "Point", coordinates: c } });
    }
  }
  return { type: "FeatureCollection", features };
}

function gpxToGeojson(text: string): GeoJSON.FeatureCollection {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const pt = (e: Element): [number, number] => [Number(e.getAttribute("lon")), Number(e.getAttribute("lat"))];
  const features: GeoJSON.Feature[] = [];
  for (const trk of Array.from(doc.getElementsByTagName("trk"))) {
    const line = Array.from(trk.getElementsByTagName("trkpt")).map(pt);
    if (line.length >= 2) features.push({ type: "Feature", properties: { name: trk.getElementsByTagName("name")[0]?.textContent ?? "Track" }, geometry: { type: "LineString", coordinates: line } });
  }
  for (const rte of Array.from(doc.getElementsByTagName("rte"))) {
    const line = Array.from(rte.getElementsByTagName("rtept")).map(pt);
    if (line.length >= 2) features.push({ type: "Feature", properties: { name: rte.getElementsByTagName("name")[0]?.textContent ?? "Route" }, geometry: { type: "LineString", coordinates: line } });
  }
  for (const w of Array.from(doc.getElementsByTagName("wpt")))
    features.push({ type: "Feature", properties: { name: w.getElementsByTagName("name")[0]?.textContent ?? "Waypoint" }, geometry: { type: "Point", coordinates: pt(w) } });
  return { type: "FeatureCollection", features };
}

/** Lat/lon rings and lines of a feature collection (GeoJSON is lon,lat). */
export function geodataParts(fc: GeoJSON.FeatureCollection) {
  const polys: { name: string; ring: LatLon[] }[] = [];
  const lines: { name: string; line: LatLon[] }[] = [];
  const points: { name: string; at: LatLon }[] = [];
  const flip = (c: GeoJSON.Position): LatLon => [c[1]!, c[0]!];
  for (const f of fc.features) {
    const name = String((f.properties as { name?: string } | null)?.name ?? "");
    const g = f.geometry;
    if (!g) continue;
    if (g.type === "Polygon") polys.push({ name, ring: g.coordinates[0]!.map(flip) });
    else if (g.type === "MultiPolygon") g.coordinates.forEach((p) => polys.push({ name, ring: p[0]!.map(flip) }));
    else if (g.type === "LineString") lines.push({ name, line: g.coordinates.map(flip) });
    else if (g.type === "MultiLineString") g.coordinates.forEach((l) => lines.push({ name, line: l.map(flip) }));
    else if (g.type === "Point") points.push({ name, at: flip(g.coordinates) });
  }
  return { polys, lines, points };
}

/** What a map file holds, in words for the assistant: shapes, their areas / lengths, names, where. */
export function summarizeGeodata(fc: GeoJSON.FeatureCollection): string {
  const { polys, lines, points } = geodataParts(fc);
  const all = [...polys.flatMap((p) => p.ring), ...lines.flatMap((l) => l.line), ...points.map((p) => p.at)];
  const out: Record<string, unknown> = { features: fc.features.length };
  if (polys.length)
    out.areas = polys.slice(0, 20).map((p) => ({ name: p.name || undefined, ...areaUnits(polygonAreaM2(p.ring)), corners: p.ring.length, centre: centroid(p.ring).map((x) => Number(x.toFixed(6))) }));
  if (lines.length) out.lines = lines.slice(0, 20).map((l) => ({ name: l.name || undefined, length: lengthUnits(pathLengthM(l.line)).text, points: l.line.length }));
  if (points.length) out.points = points.slice(0, 30).map((p) => ({ name: p.name || undefined, at: p.at.map((x) => Number(x.toFixed(6))) }));
  if (all.length) out.centre = centroid(all).map((x) => Number(x.toFixed(6)));
  return JSON.stringify(out);
}

/** A measure / pin / map file as GeoJSON for the map. */
export function attachmentShape(a: ChatAttachment): GeoJSON.FeatureCollection | null {
  if (a.kind === "geodata") return a.geojson;
  const flip = (p: LatLon): [number, number] => [p[1], p[0]];
  if (a.kind === "measure")
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { name: a.label },
          geometry: a.mode === "area" ? { type: "Polygon", coordinates: [[...a.coords, a.coords[0]!].map(flip)] } : { type: "LineString", coordinates: a.coords.map(flip) },
        },
      ],
    };
  if (a.kind === "pin") return { type: "FeatureCollection", features: [{ type: "Feature", properties: { name: a.label }, geometry: { type: "Point", coordinates: [a.lon, a.lat] } }] };
  return null;
}

/** Trigger a download of a blob URL. */
export function downloadUrl(url: string, name: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
