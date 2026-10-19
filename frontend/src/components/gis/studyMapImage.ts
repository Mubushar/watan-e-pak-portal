/**
 * A static map image of a study area for the case-study report: base-map tiles fitted to the
 * drawn shape, the shape itself, its centre, listings inside, a scale bar, a north arrow and the
 * attribution — drawn on a canvas (2× for print) and returned as a JPEG data URL. Custom layers
 * (DHA master plan tiles, the portal's GIS layers) can be drawn over the base map.
 */
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { StudyShape } from "./AreaDraw";

export type StudyMapBase = "streets" | "satellite";

const TILE = 256;
// Keyless tile sources that allow canvas use (CORS). CARTO's basemaps now need an API key.
export type TileUrl = (z: number, x: number, y: number) => string;

/** A custom layer drawn over the base map: map tiles (e.g. a master plan) or GeoJSON shapes. */
export type StudyOverlay =
  | { kind: "tiles"; url: TileUrl; minZoom: number; maxZoom: number; opacity?: number; bounds?: [number, number, number, number]; attribution?: string }
  | { kind: "geojson"; data: FeatureCollection | Feature | Geometry; color: string; fillColor?: string; fillOpacity?: number; attribution?: string };

/** [south, west, north, east] of the drawn shape. */
export function shapeBounds(shape: StudyShape): [number, number, number, number] {
  const ring = ringOf(shape);
  const lats = ring.map((p) => p[0]);
  const lons = ring.map((p) => p[1]);
  return [Math.min(...lats), Math.min(...lons), Math.max(...lats), Math.max(...lons)];
}
const BASES: Record<StudyMapBase, { url: TileUrl; fallback?: TileUrl; attribution: string; maxZoom: number }> = {
  streets: {
    url: (z, x, y) => `https://tile.openstreetmap.org/${z}/${x}/${y}.png`,
    fallback: (z, x, y) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/${z}/${y}/${x}`,
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  },
  satellite: {
    url: (z, x, y) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    maxZoom: 19,
  },
};

/** Web-Mercator world pixel of a lat/lon at zoom z. */
function project(lat: number, lon: number, z: number): [number, number] {
  const s = TILE * 2 ** z;
  const sin = Math.sin((lat * Math.PI) / 180);
  return [((lon + 180) / 360) * s, (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * s];
}

function ringOf(shape: StudyShape): [number, number][] {
  if (shape.kind !== "circle") return shape.coordinates;
  const [lat, lon] = shape.center;
  const dLat = shape.radius_m / 111_320;
  const dLon = shape.radius_m / (111_320 * Math.cos((lat * Math.PI) / 180));
  return Array.from({ length: 72 }, (_, i) => {
    const a = (i / 72) * 2 * Math.PI;
    return [lat + dLat * Math.sin(a), lon + dLon * Math.cos(a)] as [number, number];
  });
}

function loadTile(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

function niceDistance(m: number): number {
  const p = 10 ** Math.floor(Math.log10(m));
  return [1, 2, 5, 10].map((k) => k * p).filter((v) => v <= m).pop() ?? p;
}

export async function studyMapImage(
  shape: StudyShape,
  opts: { base?: StudyMapBase; width?: number; height?: number; points?: [number, number][]; title?: string; overlays?: StudyOverlay[] } = {},
): Promise<string> {
  const base = BASES[opts.base ?? "streets"];
  const W = opts.width ?? 880;
  const H = opts.height ?? 500;
  const SCALE = 2; // render at 2× for a crisp print
  const ring = ringOf(shape);
  const lats = ring.map((p) => p[0]);
  const lons = ring.map((p) => p[1]);
  const s = Math.min(...lats);
  const n = Math.max(...lats);
  const w = Math.min(...lons);
  const e = Math.max(...lons);
  const centre: [number, number] = shape.kind === "circle" ? shape.center : [(s + n) / 2, (w + e) / 2];

  // Highest zoom at which the shape (plus 18% margin) fits the frame.
  let z = 3;
  for (let t = base.maxZoom - 1; t >= 3; t--) {
    const [x0, y0] = project(n, w, t);
    const [x1, y1] = project(s, e, t);
    if ((x1 - x0) * 1.36 <= W && (y1 - y0) * 1.36 <= H) {
      z = t;
      break;
    }
  }
  const zr = Math.min(base.maxZoom, z + 1); // tiles for the 2× canvas
  const k = 2 ** (zr - z) / SCALE; // tile px per canvas px (1 when zr = z + 1)
  const [cx, cy] = project(centre[0], centre[1], zr);
  const cw = W * SCALE * k;
  const ch = H * SCALE * k;
  const left = cx - cw / 2;
  const top = cy - ch / 2;

  const canvas = document.createElement("canvas");
  canvas.width = W * SCALE;
  canvas.height = H * SCALE;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#e9eef2";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(1 / k, 1 / k);

  // Tiles.
  const tiles: Promise<void>[] = [];
  const max = 2 ** zr;
  for (let ty = Math.floor(top / TILE); ty <= Math.floor((top + ch) / TILE); ty++) {
    if (ty < 0 || ty >= max) continue;
    for (let tx = Math.floor(left / TILE); tx <= Math.floor((left + cw) / TILE); tx++) {
      const wx = ((tx % max) + max) % max;
      tiles.push(
        loadTile(base.url(zr, wx, ty))
          .then((img) => img ?? (base.fallback ? loadTile(base.fallback(zr, wx, ty)) : null))
          .then((img) => {
            if (img) ctx.drawImage(img, tx * TILE - left, ty * TILE - top, TILE, TILE);
          }),
      );
    }
  }
  await Promise.all(tiles);
  const px = (lat: number, lon: number): [number, number] => {
    const [x, y] = project(lat, lon, zr);
    return [x - left, y - top];
  };

  // Custom layers, in order, over the base map.
  for (const o of opts.overlays ?? []) {
    if (o.kind === "tiles") await drawTileOverlay(ctx, o, zr, left, top, cw, ch);
    else drawGeoJson(ctx, o, px, SCALE * k);
  }

  // Dim everything outside the shape so the study area stands out.
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, cw, ch);
  ring.forEach((p, i) => (i ? ctx.lineTo(...px(...p)) : ctx.moveTo(...px(...p))));
  ctx.closePath();
  ctx.fillStyle = "rgba(15, 23, 42, 0.28)";
  ctx.fill("evenodd");
  ctx.restore();

  // The shape.
  const u = SCALE * k; // one CSS px in tile px
  ctx.beginPath();
  ring.forEach((p, i) => (i ? ctx.lineTo(...px(...p)) : ctx.moveTo(...px(...p))));
  ctx.closePath();
  ctx.fillStyle = "rgba(167, 139, 250, 0.16)";
  ctx.fill();
  ctx.lineWidth = 3 * u;
  ctx.strokeStyle = "#ffffff";
  ctx.stroke();
  ctx.lineWidth = 2 * u;
  ctx.strokeStyle = "#7c3aed";
  ctx.stroke();

  // Listings inside.
  for (const [lat, lon] of opts.points ?? []) {
    const [x, y] = px(lat, lon);
    ctx.beginPath();
    ctx.arc(x, y, 5 * u, 0, 2 * Math.PI);
    ctx.fillStyle = "#146f45";
    ctx.fill();
    ctx.lineWidth = 2 * u;
    ctx.strokeStyle = "#fff";
    ctx.stroke();
  }

  // Centre.
  const [mx, my] = px(...centre);
  ctx.beginPath();
  ctx.arc(mx, my, 4 * u, 0, 2 * Math.PI);
  ctx.fillStyle = "#c99a22";
  ctx.fill();
  ctx.lineWidth = 2 * u;
  ctx.strokeStyle = "#fff";
  ctx.stroke();

  // Back to CSS-pixel units for the furniture.
  ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
  ctx.font = "600 11px system-ui, sans-serif";

  // Scale bar (bottom left).
  const mPerPx = (156543.03 * Math.cos((centre[0] * Math.PI) / 180)) / 2 ** z;
  const dist = niceDistance(mPerPx * W * 0.22);
  const barW = dist / mPerPx;
  ctx.fillStyle = "rgba(255,255,255,0.88)";
  ctx.fillRect(10, H - 34, barW + 20, 24);
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(20, H - 16, barW, 3);
  ctx.fillRect(20, H - 21, 2, 8);
  ctx.fillRect(20 + barW - 2, H - 21, 2, 8);
  ctx.fillText(dist >= 1000 ? `${dist / 1000} km` : `${dist} m`, 22, H - 22);

  // North arrow (top right).
  ctx.fillStyle = "rgba(255,255,255,0.88)";
  ctx.beginPath();
  ctx.arc(W - 26, 26, 16, 0, 2 * Math.PI);
  ctx.fill();
  ctx.fillStyle = "#0f172a";
  ctx.beginPath();
  ctx.moveTo(W - 26, 13);
  ctx.lineTo(W - 32, 31);
  ctx.lineTo(W - 26, 27);
  ctx.lineTo(W - 20, 31);
  ctx.closePath();
  ctx.fill();
  ctx.font = "800 9px system-ui, sans-serif";
  ctx.fillText("N", W - 29, 40);

  // Title (top left) and attribution (bottom right).
  if (opts.title) {
    ctx.font = "800 13px system-ui, sans-serif";
    const tw = ctx.measureText(opts.title).width;
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.fillRect(10, 10, tw + 16, 24);
    ctx.fillStyle = "#4c1d95";
    ctx.fillText(opts.title, 18, 27);
  }
  ctx.font = "500 9px system-ui, sans-serif";
  const at = [base.attribution, ...new Set((opts.overlays ?? []).map((o) => o.attribution).filter(Boolean))].join(" · ");
  const aw = ctx.measureText(at).width;
  ctx.fillStyle = "rgba(255,255,255,0.85)";
  ctx.fillRect(W - aw - 14, H - 16, aw + 14, 16);
  ctx.fillStyle = "#334155";
  ctx.fillText(at, W - aw - 7, H - 5);

  // JPEG keeps a 2x map image around half a megabyte (a PNG runs to 4-5 MB).
  return canvas.toDataURL("image/jpeg", opts.base === "satellite" ? 0.86 : 0.9);
}

/** Tiles of an overlay that exist only for some zooms (master plans: 12–17) are scaled to fit. */
async function drawTileOverlay(
  ctx: CanvasRenderingContext2D,
  o: Extract<StudyOverlay, { kind: "tiles" }>,
  zr: number,
  left: number,
  top: number,
  cw: number,
  ch: number,
) {
  const nz = Math.max(o.minZoom, Math.min(o.maxZoom, zr));
  const f = 2 ** (zr - nz); // canvas tile px per overlay tile px
  const max = 2 ** nz;
  let x0 = Math.floor(left / f / TILE);
  let x1 = Math.floor((left + cw) / f / TILE);
  let y0 = Math.floor(top / f / TILE);
  let y1 = Math.floor((top + ch) / f / TILE);
  if (o.bounds) {
    const [s, w, n, e] = o.bounds;
    const [bx0, by0] = project(n, w, nz);
    const [bx1, by1] = project(s, e, nz);
    x0 = Math.max(x0, Math.floor(bx0 / TILE));
    x1 = Math.min(x1, Math.floor(bx1 / TILE));
    y0 = Math.max(y0, Math.floor(by0 / TILE));
    y1 = Math.min(y1, Math.floor(by1 / TILE));
  }
  if (x1 < x0 || y1 < y0 || (x1 - x0 + 1) * (y1 - y0 + 1) > 160) return; // nothing here, or far too many tiles
  const jobs: Promise<void>[] = [];
  ctx.save();
  ctx.globalAlpha = o.opacity ?? 0.8;
  for (let ty = Math.max(0, y0); ty <= Math.min(max - 1, y1); ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      jobs.push(
        loadTile(o.url(nz, ((tx % max) + max) % max, ty)).then((img) => {
          if (img) ctx.drawImage(img, tx * TILE * f - left, ty * TILE * f - top, TILE * f, TILE * f);
        }),
      );
    }
  }
  await Promise.all(jobs);
  ctx.restore();
}

function drawGeoJson(
  ctx: CanvasRenderingContext2D,
  o: Extract<StudyOverlay, { kind: "geojson" }>,
  px: (lat: number, lon: number) => [number, number],
  u: number,
) {
  const geoms: Geometry[] = [];
  const add = (g: FeatureCollection | Feature | Geometry | null | undefined) => {
    if (!g) return;
    if (g.type === "FeatureCollection") g.features.forEach(add);
    else if (g.type === "Feature") add(g.geometry);
    else if (g.type === "GeometryCollection") g.geometries.forEach(add);
    else geoms.push(g);
  };
  add(o.data);
  const path = (ring: number[][]) => ring.forEach((c, i) => (i ? ctx.lineTo(...px(c[1]!, c[0]!)) : ctx.moveTo(...px(c[1]!, c[0]!))));
  ctx.save();
  ctx.strokeStyle = o.color;
  ctx.fillStyle = o.fillColor ?? o.color;
  ctx.lineWidth = 2 * u;
  for (const g of geoms) {
    if (g.type === "Polygon" || g.type === "MultiPolygon") {
      const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
      for (const poly of polys) {
        ctx.beginPath();
        poly.forEach((ring) => {
          path(ring);
          ctx.closePath();
        });
        ctx.globalAlpha = o.fillOpacity ?? 0.15;
        ctx.fill("evenodd");
        ctx.globalAlpha = 0.95;
        ctx.stroke();
      }
    } else if (g.type === "LineString" || g.type === "MultiLineString") {
      const lines = g.type === "LineString" ? [g.coordinates] : g.coordinates;
      ctx.globalAlpha = 0.95;
      for (const line of lines) {
        ctx.beginPath();
        path(line);
        ctx.stroke();
      }
    } else if (g.type === "Point" || g.type === "MultiPoint") {
      const pts = g.type === "Point" ? [g.coordinates] : g.coordinates;
      ctx.globalAlpha = 0.95;
      for (const c of pts) {
        const [x, y] = px(c[1]!, c[0]!);
        ctx.beginPath();
        ctx.arc(x, y, 3.5 * u, 0, 2 * Math.PI);
        ctx.fill();
      }
    }
  }
  ctx.restore();
}
