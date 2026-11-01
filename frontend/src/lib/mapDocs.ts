/**
 * The documents the assistant (and the Map page's buttons) make: PDF reports and map pictures of
 * a measurement, a location, the route in the route finder, the current map view, a listing, or
 * the conversation. Each returns a ChatFile (a blob URL the chat shows with Open / Download).
 */
import type { NearbyPlace, Property } from "@/types";
import { BASE_MAPS } from "@/components/map/PortalMap";
import { pkrShort, titleCase, area as fmtPropArea } from "./format";
import { coverImage } from "./images";
import { areaUnits, centroid, fmtLatLon, googleMapsUrl, lengthUnits, pathLengthM, polygonAreaM2, toDms, type LatLon } from "./geoMeasure";
import { renderMapImage, type MapShapes, type TileSource } from "./mapImage";
import { ReportBuilder, canvasPng } from "./pdfDoc";
import { getMapRender, getMapView, type MapRender, type Spot } from "./mapFocus";
import type { ChatFile } from "./chatShare";

export type DocFormat = "pdf" | "image";

const today = () => new Date().toISOString().slice(0, 10);
const safeName = (s: string) => s.replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 90);

function finish(blob: Blob, base: string, kind: DocFormat, caption?: string): ChatFile {
  const name = `${safeName(base)} - ${today()}.${kind === "pdf" ? "pdf" : "png"}`;
  return { kind, name, url: URL.createObjectURL(blob), size: blob.size, caption };
}

/** Base map + the master plans on screen that touch the picture. */
function layers(render: MapRender | null, fit: LatLon[]): { base: TileSource; overlays: TileSource[]; attribution: string } {
  const base = render?.base ?? BASE_MAPS.streets;
  const lats = fit.map((p) => p[0]);
  const lons = fit.map((p) => p[1]);
  const box = [Math.min(...lats) - 0.01, Math.min(...lons) - 0.01, Math.max(...lats) + 0.01, Math.max(...lons) + 0.01];
  const overlays = (render?.plans ?? [])
    .filter((p) => p.bounds[0] < box[2]! && p.bounds[2] > box[0]! && p.bounds[1] < box[3]! && p.bounds[3] > box[1]!)
    .map((p) => ({ url: p.url, bounds: p.bounds, minNative: p.zoom[0], maxNative: p.zoom[1], opacity: render!.planOpacity }));
  return { base: { url: base.url }, overlays, attribution: `${base.attribution}${overlays.length ? " · master plans: developers / CDA / RDA" : ""}` };
}

async function picture(fit: LatLon[], shapes: MapShapes, size: [number, number] = [1100, 760], maxZoom = 17) {
  const render = getMapRender();
  const l = layers(render, fit);
  return renderMapImage({ fit, width: size[0], height: size[1], maxZoom, base: l.base, overlays: l.overlays, attribution: l.attribution, ...shapes });
}

async function out(r: ReportBuilder, img: HTMLCanvasElement, kind: DocFormat, base: string, caption: string): Promise<ChatFile> {
  return kind === "image" ? finish(await canvasPng(img), base, "image", caption) : finish(await r.toPdf(), base, "pdf", caption);
}

const notesSection = (r: ReportBuilder, notes?: string) => {
  if (notes?.trim()) r.heading("Notes").paragraph(notes.trim());
};

// ------------------------------------------------------------------ measurement
export async function measureFile(m: { mode: "distance" | "area"; coords: LatLon[] }, kind: DocFormat, notes?: string): Promise<ChatFile> {
  const isArea = m.mode === "area";
  const shapes: MapShapes = isArea
    ? { polygons: [{ coords: m.coords, color: "#d97706", fill: "rgba(251,191,36,.25)" }] }
    : { lines: [{ coords: m.coords, color: "#d97706", width: 4, halo: true }], pins: [{ at: m.coords[0]!, letter: "A", color: "#0f5a39" }, { at: m.coords[m.coords.length - 1]!, letter: "B", color: "#b45309" }] };
  const img = await picture(m.coords, shapes);
  const len = lengthUnits(isArea ? pathLengthM([...m.coords, m.coords[0]!]) : pathLengthM(m.coords));
  const a = isArea ? areaUnits(polygonAreaM2(m.coords)) : null;
  const title = isArea ? `Area measurement — ${a!.text}` : `Distance measurement — ${len.text}`;
  const r = new ReportBuilder(isArea ? "Area measurement" : "Distance measurement", `${isArea ? a!.text : len.text} · measured on the Watan-e-Pak map`);
  r.image(img, "Measured on the map (scale bar bottom left).");
  r.heading("Result");
  if (a)
    r.keyValues([
      ["Area", `${a.square_meters.toLocaleString()} m² · ${a.square_feet.toLocaleString()} sq ft`],
      ["Marla / kanal (272.25 sq ft)", `${a.marla} marla · ${a.kanal} kanal`],
      ["Marla / kanal (225 sq ft, societies)", `${a.marla_society_225sqft} marla · ${a.kanal_society_4500sqft} kanal`],
      ["Acres / hectares", `${a.acres} acres · ${a.hectares} ha`],
      ["Perimeter", `${len.text} (${len.feet.toLocaleString()} ft)`],
      ["Corners", String(m.coords.length)],
      ["Centre", `${fmtLatLon(...centroid(m.coords))}`],
    ]);
  else
    r.keyValues([
      ["Distance", `${len.text} · ${len.meters.toLocaleString()} m · ${len.feet.toLocaleString()} ft · ${len.miles} mi`],
      ["Points", String(m.coords.length)],
      ["Start", fmtLatLon(...m.coords[0]!)],
      ["End", fmtLatLon(...m.coords[m.coords.length - 1]!)],
    ]);
  r.heading("Points").table(
    ["#", "Latitude, longitude", "Degrees / minutes / seconds"],
    m.coords.map((p, i) => [String(i + 1), fmtLatLon(p[0], p[1]), toDms(p[0], p[1])]),
    [0.08, 0.42, 0.5],
  );
  r.paragraph("Measured on the map, which is accurate to a few metres at street zoom; for legal boundaries use a licensed surveyor's demarcation.", { size: 17, color: "#5c6b64" });
  notesSection(r, notes);
  return out(r, img, kind, title, title);
}

// ------------------------------------------------------------------ a location / pin
export async function locationFile(spot: Spot, kind: DocFormat, notes?: string, extra: [string, string][] = []): Promise<ChatFile> {
  const at: LatLon = [spot.lat, spot.lon];
  const img = await picture([[at[0] - 0.004, at[1] - 0.006], [at[0] + 0.004, at[1] + 0.006]], { pins: [{ at, label: spot.label.slice(0, 40), color: "#dc2626" }] }, [1100, 760], 17);
  const r = new ReportBuilder(`Location — ${spot.label}`, fmtLatLon(spot.lat, spot.lon));
  r.image(img);
  r.heading("Coordinates").keyValues([
    ["Place", spot.label],
    ["Latitude, longitude", fmtLatLon(spot.lat, spot.lon)],
    ["Degrees / minutes / seconds", toDms(spot.lat, spot.lon)],
    ["Google Maps", googleMapsUrl(spot.lat, spot.lon)],
    ...extra,
  ]);
  notesSection(r, notes);
  return out(r, img, kind, `Location - ${spot.label}`, spot.label);
}

// ------------------------------------------------------------------ the route in the route finder
export async function routeFile(kind: DocFormat, notes?: string): Promise<ChatFile | { error: string }> {
  const route = getMapRender()?.route;
  if (!route) return { error: "No route is showing in the route finder." };
  const g = route.best.geometry;
  const img = await picture(g, {
    lines: [
      ...route.alternatives.map((a) => ({ coords: a.geometry, color: "#64748b", width: 4, dash: [8, 8] })),
      { coords: g, color: "#1a73e8", width: 6, halo: true },
    ],
    pins: [
      { at: [route.from.lat, route.from.lon] as LatLon, letter: "A", color: "#0f5a39" },
      { at: [route.to.lat, route.to.lon] as LatLon, letter: "B", color: "#dc2626" },
    ],
  });
  const title = `Route - ${route.from.label} to ${route.to.label}`;
  const r = new ReportBuilder("Route", `${route.from.label} → ${route.to.label}`);
  r.image(img, "Blue: the suggested route · grey dashed: alternatives.");
  r.heading("Summary").keyValues([
    ["From (A)", `${route.from.label} — ${fmtLatLon(route.from.lat, route.from.lon, 5)}`],
    ["To (B)", `${route.to.label} — ${fmtLatLon(route.to.lat, route.to.lon, 5)}`],
    ["By", titleCase(route.mode)],
    ["Distance", route.best.distance_text],
    ["Time", `${route.best.duration_text} (typical traffic)`],
    ["Via", route.best.via.join(", ")],
  ]);
  if (route.alternatives.length)
    r.heading("Other routes").table(
      ["Route", "Distance", "Time"],
      route.alternatives.map((a) => [a.label, a.distance_text, a.duration_text]),
      [0.5, 0.25, 0.25],
    );
  if (route.best.steps.length)
    r.heading("Turn by turn").table(
      ["#", "Instruction", "Road", "Distance"],
      route.best.steps.map((s, i) => [String(i + 1), s.instruction, s.road ?? "", s.distance_text]),
      [0.07, 0.53, 0.25, 0.15],
    );
  r.paragraph(route.attribution, { size: 16, color: "#5c6b64" });
  notesSection(r, notes);
  return out(r, img, kind, title, `${route.from.label} → ${route.to.label} · ${route.best.distance_text}, ${route.best.duration_text}`);
}

// ------------------------------------------------------------------ the current map view
export async function mapViewFile(kind: DocFormat, opts: { title?: string; notes?: string; facts?: Record<string, unknown> } = {}): Promise<ChatFile | { error: string }> {
  const v = getMapView();
  const render = getMapRender();
  if (!v || !render) return { error: "The Map page isn't open." };
  const fit: LatLon[] = [
    [v.south, v.west],
    [v.north, v.east],
  ];
  const shapes: MapShapes = { pins: render.pins.map((p) => ({ at: [p.lat, p.lon] as LatLon, label: p.label.slice(0, 30), color: "#dc2626" })) };
  const sel = v.selection;
  if (sel.listing) shapes.pins!.push({ at: [sel.listing.lat, sel.listing.lon], label: sel.listing.label.slice(0, 30), color: "#0f5a39" });
  if (sel.assistant_pin) shapes.pins!.push({ at: [sel.assistant_pin.lat, sel.assistant_pin.lon], label: sel.assistant_pin.label.slice(0, 30), color: "#7c3aed" });
  if (render.route) shapes.lines = [{ coords: render.route.best.geometry, color: "#1a73e8", width: 6, halo: true }];
  if (render.measure)
    render.measure.mode === "area"
      ? (shapes.polygons = [{ coords: render.measure.coords, color: "#d97706", fill: "rgba(251,191,36,.25)" }])
      : (shapes.lines = [...(shapes.lines ?? []), { coords: render.measure.coords, color: "#d97706", width: 4, halo: true }]);
  const img = await picture(fit, shapes, [1100, 800], Math.min(17, v.zoom));
  const centre: LatLon = [(v.south + v.north) / 2, (v.west + v.east) / 2];
  const title = opts.title || "Map view";
  const r = new ReportBuilder(title, `Centre ${fmtLatLon(centre[0], centre[1], 5)} · zoom ${Math.round(v.zoom)}`);
  r.image(img);
  r.heading("This view").keyValues([
    ["Centre", `${fmtLatLon(centre[0], centre[1])} (${toDms(centre[0], centre[1])})`],
    ["Area shown", `${lengthUnits(pathLengthM([[centre[0], v.west], [centre[0], v.east]])).text} × ${lengthUnits(pathLengthM([[v.south, centre[1]], [v.north, centre[1]]])).text}`],
    ["Corners", `SW ${fmtLatLon(v.south, v.west, 5)} · NE ${fmtLatLon(v.north, v.east, 5)}`],
    ["Base map", v.base],
    ["Master plans on", v.plans.length ? v.plans.map((p) => p.name).slice(0, 25).join(", ") + (v.plans.length > 25 ? ` … (${v.plans.length})` : "") : "none"],
    ["Other layers", [...v.gis.map((l) => l.name), ...v.overlays].join(", ") || "none"],
    ["Measured", render.measure ? `${render.measure.mode}: ${render.measure.value}` : ""],
    ["Route", render.route ? `${render.route.from.label} → ${render.route.to.label}: ${render.route.best.distance_text}, ${render.route.best.duration_text}` : ""],
  ]);
  if (opts.facts && Object.keys(opts.facts).length)
    r.heading("What is in this view").keyValues(
      Object.entries(opts.facts)
        .filter(([, x]) => x !== null && x !== undefined && x !== "")
        .slice(0, 30)
        .map(([k, x]) => [titleCase(k.replace(/_/g, " ")), typeof x === "object" ? JSON.stringify(x).slice(0, 400) : String(x)]),
    );
  notesSection(r, opts.notes);
  return out(r, img, kind, title, `${title} · ${fmtLatLon(centre[0], centre[1], 4)}`);
}

// ------------------------------------------------------------------ a listing
async function photo(url: string): Promise<ImageBitmap | null> {
  try {
    const res = await fetch(url, { mode: "cors" });
    if (!res.ok) return null;
    return await createImageBitmap(await res.blob());
  } catch {
    return null; // the photo's host doesn't allow it; the report goes without
  }
}

export async function listingFile(p: Property, kind: DocFormat, nearby: NearbyPlace[] = [], notes?: string): Promise<ChatFile> {
  const at: LatLon | null = p.latitude != null && p.longitude != null ? [p.latitude, p.longitude] : null;
  const img = at ? await picture([[at[0] - 0.005, at[1] - 0.007], [at[0] + 0.005, at[1] + 0.007]], { pins: [{ at, label: pkrShort(p.price), color: "#0f5a39" }] }, [1100, 640], 17) : null;
  const r = new ReportBuilder(p.title, [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", "));
  const ph = await photo(coverImage(p));
  if (ph) r.image(ph, undefined, 700);
  r.heading("Details").keyValues([
    ["Price", `${pkrShort(p.price)} (PKR ${p.price.toLocaleString()})`],
    ["Purpose / type", `${titleCase(p.use_type)} · ${titleCase(p.category)}`],
    ["Size", fmtPropArea(p)],
    ["Bedrooms / bathrooms", p.bedrooms || p.bathrooms ? `${p.bedrooms ?? "—"} / ${p.bathrooms ?? "—"}` : ""],
    ["Address", [p.street_address, p.sector, p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", ")],
    ["Status", titleCase(p.status)],
    ["Features", (p.amenities ?? []).join(", ")],
    ["Coordinates", at ? fmtLatLon(at[0], at[1]) : ""],
    ["Listing page", `${window.location.origin}/properties/${p.id}`],
  ]);
  if (p.description) r.heading("Description").paragraph(p.description);
  if (img) r.heading("Location").image(img);
  if (nearby.length)
    r.heading("Nearby").table(
      ["Place", "Kind", "Distance"],
      nearby.slice(0, 15).map((n) => [n.name, titleCase(n.kind), `${n.distance_km} km`]),
      [0.55, 0.25, 0.2],
    );
  notesSection(r, notes);
  const pic = img ?? (await picture([[30.4, 69.3]], {}));
  return out(r, pic, kind, `Listing - ${p.title}`, `${p.title} · ${pkrShort(p.price)}`);
}

// ------------------------------------------------------------------ a written report (the assistant's own text) / the chat
export interface ReportSection {
  heading?: string;
  text?: string;
  bullets?: string[];
  table?: { headers: string[]; rows: string[][] };
}
export async function writtenReport(title: string, sections: ReportSection[], opts: { subtitle?: string; withMap?: boolean } = {}): Promise<ChatFile> {
  const r = new ReportBuilder(title, opts.subtitle ?? "");
  if (opts.withMap) {
    const v = getMapView();
    if (v) {
      const img = await picture([[v.south, v.west], [v.north, v.east]], {}, [1100, 700], Math.min(17, v.zoom));
      r.image(img, "The map view at the time of this report.");
    }
  }
  for (const s of sections) {
    if (s.heading) r.heading(s.heading);
    if (s.text) r.paragraph(s.text);
    if (s.bullets?.length) r.bullets(s.bullets);
    if (s.table?.headers?.length) r.table(s.table.headers, s.table.rows ?? []);
  }
  return finish(await r.toPdf(), title, "pdf", title);
}

export async function chatFile(messages: { role: "user" | "assistant"; content: string }[], title = "Conversation with Watan-e-Pak AI"): Promise<ChatFile> {
  const r = new ReportBuilder(title, `${messages.length} messages`);
  for (const m of messages) {
    r.heading(m.role === "user" ? "You" : "Watan-e-Pak AI");
    r.paragraph(m.content.replace(/\*\*|__|`/g, "").replace(/^#+\s*/gm, ""));
  }
  return finish(await r.toPdf(), title, "pdf", title);
}
