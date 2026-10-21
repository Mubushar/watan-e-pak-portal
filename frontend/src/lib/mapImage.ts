/**
 * Draw a map picture on a canvas from tiles — base map, master-plan overlays, routes, measured
 * lines / areas and pins — for the assistant's PDFs and shared images. It works from map tiles
 * directly (no screenshot of the page), so it can draw any place at any size, also when the Map
 * page isn't open. Tile servers used (OpenStreetMap, Esri, OpenTopoMap, the portal) allow CORS.
 */
import type { LatLon } from "./geoMeasure";

export interface TileSource {
  url: string; // {z}/{x}/{y}, optional {s}
  /** Only draw tiles inside these bounds [south, west, north, east]. */
  bounds?: [number, number, number, number];
  minNative?: number;
  maxNative?: number;
  opacity?: number;
}
export interface MapShapes {
  lines?: { coords: LatLon[]; color: string; width: number; halo?: boolean; dash?: number[] }[];
  polygons?: { coords: LatLon[]; color: string; fill: string }[];
  circles?: { center: LatLon; radius_m: number; color: string; fill: string }[];
  pins?: { at: LatLon; label?: string; color?: string; letter?: string }[];
}
export interface MapImageSpec extends MapShapes {
  /** Fit these points (with padding), or give center + zoom. */
  fit?: LatLon[];
  center?: LatLon;
  zoom?: number;
  maxZoom?: number;
  width: number;
  height: number;
  /** Pixel density (2 = sharp on paper / retina). */
  scale?: number;
  base: TileSource;
  overlays?: TileSource[];
  attribution?: string;
}

const TILE = 256;
const worldPx = (z: number) => TILE * 2 ** z;
function project(lat: number, lon: number, z: number): [number, number] {
  const s = Math.sin((Math.max(-85.05, Math.min(85.05, lat)) * Math.PI) / 180);
  const w = worldPx(z);
  return [((lon + 180) / 360) * w, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * w];
}

function loadTile(url: string, timeoutMs = 10_000): Promise<HTMLImageElement | null> {
  return new Promise((res) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    const t = setTimeout(() => res(null), timeoutMs);
    img.onload = () => {
      clearTimeout(t);
      res(img);
    };
    img.onerror = () => {
      clearTimeout(t);
      res(null);
    };
    img.src = url;
  });
}

/** Zoom (fractional) and centre that fit the points into w×h with `pad` px around. */
function fitView(pts: LatLon[], w: number, h: number, pad: number, maxZoom: number): { center: LatLon; zoom: number } {
  if (pts.length === 1) return { center: pts[0]!, zoom: Math.min(maxZoom, 16) };
  const lats = pts.map((p) => p[0]);
  const lons = pts.map((p) => p[1]);
  const s = Math.min(...lats);
  const n = Math.max(...lats);
  const wv = Math.min(...lons);
  const e = Math.max(...lons);
  const [x0, y0] = project(n, wv, 0);
  const [x1, y1] = project(s, e, 0);
  const zx = Math.log2((w - 2 * pad) / Math.max(1e-9, x1 - x0));
  const zy = Math.log2((h - 2 * pad) / Math.max(1e-9, y1 - y0));
  const z = Math.min(maxZoom, zx, zy);
  // Centre in projected space (the middle of the box, not of the degrees).
  const zc = Math.max(1, Math.floor(z));
  const [cx0, cy0] = project(n, wv, zc);
  const [cx1, cy1] = project(s, e, zc);
  const cx = (cx0 + cx1) / 2;
  const cy = (cy0 + cy1) / 2;
  const lon = (cx / worldPx(zc)) * 360 - 180;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * cy) / worldPx(zc)))) * 180) / Math.PI;
  return { center: [lat, lon], zoom: z };
}

async function drawTiles(ctx: CanvasRenderingContext2D, src: TileSource, zView: number, origin: [number, number], W: number, H: number) {
  const tz = Math.max(src.minNative ?? 0, Math.min(src.maxNative ?? 19, Math.round(zView)));
  const f = 2 ** (zView - tz); // canvas px per tile px
  const size = TILE * f;
  const ox = origin[0] / f; // origin in tile-zoom pixels
  const oy = origin[1] / f;
  const tx0 = Math.floor(ox / TILE);
  const ty0 = Math.floor(oy / TILE);
  const tx1 = Math.floor((ox + W / f) / TILE);
  const ty1 = Math.floor((oy + H / f) / TILE);
  const n = 2 ** tz;
  let bx: [number, number, number, number] | null = null;
  if (src.bounds) {
    const [s, w, nn, e] = src.bounds;
    const a = project(nn, w, tz);
    const b = project(s, e, tz);
    bx = [Math.floor(a[0] / TILE), Math.floor(a[1] / TILE), Math.floor(b[0] / TILE), Math.floor(b[1] / TILE)];
  }
  const jobs: Promise<void>[] = [];
  let k = 0;
  for (let ty = ty0; ty <= ty1; ty++) {
    if (ty < 0 || ty >= n) continue;
    for (let tx = tx0; tx <= tx1; tx++) {
      if (bx && (tx < bx[0] || tx > bx[2] || ty < bx[1] || ty > bx[3])) continue;
      const wx = ((tx % n) + n) % n;
      const url = src.url.replace("{s}", "abc"[k++ % 3]!).replace("{z}", String(tz)).replace("{x}", String(wx)).replace("{y}", String(ty));
      const dx = tx * size - origin[0];
      const dy = ty * size - origin[1];
      jobs.push(
        loadTile(url).then((img) => {
          if (!img) return;
          ctx.save();
          ctx.globalAlpha = src.opacity ?? 1;
          ctx.drawImage(img, Math.floor(dx), Math.floor(dy), Math.ceil(size) + 1, Math.ceil(size) + 1);
          ctx.restore();
        }),
      );
    }
  }
  await Promise.all(jobs);
}

function niceScale(maxM: number): number {
  const p = 10 ** Math.floor(Math.log10(maxM));
  for (const m of [5, 2, 1]) if (m * p <= maxM) return m * p;
  return p;
}

function drawPin(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, color: string, letter?: string, label?: string) {
  ctx.save();
  ctx.translate(x, y);
  ctx.shadowColor = "rgba(0,0,0,.35)";
  ctx.shadowBlur = 6 * s;
  ctx.shadowOffsetY = 3 * s;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.bezierCurveTo(-4 * s, -9 * s, -13 * s, -14 * s, -13 * s, -24 * s);
  ctx.arc(0, -24 * s, 13 * s, Math.PI, 0);
  ctx.bezierCurveTo(13 * s, -14 * s, 4 * s, -9 * s, 0, 0);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.shadowColor = "transparent";
  ctx.lineWidth = 2.5 * s;
  ctx.strokeStyle = "#fff";
  ctx.stroke();
  ctx.fillStyle = "#fff";
  ctx.font = `700 ${12 * s}px "Plus Jakarta Sans", system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  if (letter) ctx.fillText(letter, 0, -24 * s);
  else {
    ctx.beginPath();
    ctx.arc(0, -24 * s, 4.5 * s, 0, Math.PI * 2);
    ctx.fill();
  }
  if (label) {
    ctx.font = `600 ${11 * s}px "Plus Jakarta Sans", "Noto Nastaliq Urdu", system-ui, sans-serif`;
    const w = ctx.measureText(label).width + 14 * s;
    const ly = -48 * s;
    ctx.fillStyle = "rgba(255,255,255,.95)";
    ctx.beginPath();
    ctx.roundRect(-w / 2, ly - 10 * s, w, 20 * s, 10 * s);
    ctx.fill();
    ctx.fillStyle = "#0c472e";
    ctx.fillText(label, 0, ly);
  }
  ctx.restore();
}

/** The map picture. Resolves once every tile has loaded (or timed out). */
export async function renderMapImage(spec: MapImageSpec): Promise<HTMLCanvasElement> {
  const sc = spec.scale ?? 2;
  const W = Math.round(spec.width * sc);
  const H = Math.round(spec.height * sc);
  const maxZoom = spec.maxZoom ?? 18;
  const pts = spec.fit?.length ? spec.fit : null;
  const view = pts ? fitView(pts, spec.width, spec.height, 48, maxZoom) : { center: spec.center ?? [30.4, 69.3], zoom: Math.min(maxZoom, spec.zoom ?? 12) };
  const z = view.zoom + Math.log2(sc); // canvas-pixel zoom
  const [cx, cy] = project(view.center[0], view.center[1], z);
  const origin: [number, number] = [cx - W / 2, cy - H / 2];
  const toPx = (p: LatLon): [number, number] => {
    const [x, y] = project(p[0], p[1], z);
    return [x - origin[0], y - origin[1]];
  };

  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#e9eef0";
  ctx.fillRect(0, 0, W, H);
  await drawTiles(ctx, spec.base, z, origin, W, H);
  for (const o of spec.overlays ?? []) await drawTiles(ctx, o, z, origin, W, H);

  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  for (const c of spec.circles ?? []) {
    const [x, y] = toPx(c.center);
    const edge = toPx([c.center[0] + c.radius_m / 111_320, c.center[1]]);
    const r = Math.abs(edge[1] - y);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = c.fill;
    ctx.fill();
    ctx.lineWidth = 3 * sc;
    ctx.strokeStyle = c.color;
    ctx.stroke();
  }
  for (const p of spec.polygons ?? []) {
    ctx.beginPath();
    p.coords.forEach((q, i) => (i ? ctx.lineTo(...toPx(q)) : ctx.moveTo(...toPx(q))));
    ctx.closePath();
    ctx.fillStyle = p.fill;
    ctx.fill();
    ctx.lineWidth = 3 * sc;
    ctx.strokeStyle = p.color;
    ctx.stroke();
  }
  for (const l of spec.lines ?? []) {
    const path = () => {
      ctx.beginPath();
      l.coords.forEach((q, i) => (i ? ctx.lineTo(...toPx(q)) : ctx.moveTo(...toPx(q))));
    };
    if (l.halo) {
      path();
      ctx.setLineDash([]);
      ctx.lineWidth = (l.width + 4) * sc;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();
    }
    path();
    ctx.setLineDash((l.dash ?? []).map((d) => d * sc));
    ctx.lineWidth = l.width * sc;
    ctx.strokeStyle = l.color;
    ctx.stroke();
    ctx.setLineDash([]);
  }
  for (const p of spec.pins ?? []) drawPin(ctx, ...toPx(p.at), sc, p.color ?? "#0f5a39", p.letter, p.label);

  // Scale bar (bottom left) and north arrow (top right).
  const mPerPx = (156_543.033_92 * Math.cos((view.center[0] * Math.PI) / 180)) / 2 ** z;
  const barM = niceScale(mPerPx * 140 * sc);
  const barPx = barM / mPerPx;
  ctx.fillStyle = "rgba(255,255,255,.85)";
  ctx.fillRect(10 * sc, H - 34 * sc, barPx + 20 * sc, 24 * sc);
  ctx.fillStyle = "#111";
  ctx.fillRect(20 * sc, H - 16 * sc, barPx, 3 * sc);
  ctx.fillRect(20 * sc, H - 21 * sc, 2 * sc, 8 * sc);
  ctx.fillRect(20 * sc + barPx - 2 * sc, H - 21 * sc, 2 * sc, 8 * sc);
  ctx.font = `600 ${10 * sc}px "Plus Jakarta Sans", system-ui, sans-serif`;
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.fillText(barM >= 1000 ? `${barM / 1000} km` : `${barM} m`, 24 * sc, H - 21 * sc);
  ctx.save();
  ctx.translate(W - 26 * sc, 30 * sc);
  ctx.fillStyle = "rgba(255,255,255,.85)";
  ctx.beginPath();
  ctx.arc(0, 0, 16 * sc, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#111";
  ctx.beginPath();
  ctx.moveTo(0, -11 * sc);
  ctx.lineTo(6 * sc, 7 * sc);
  ctx.lineTo(0, 3 * sc);
  ctx.lineTo(-6 * sc, 7 * sc);
  ctx.closePath();
  ctx.fill();
  ctx.font = `700 ${8 * sc}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.fillText("N", 0, 14.5 * sc);
  ctx.restore();
  if (spec.attribution) {
    ctx.font = `${9 * sc}px system-ui, sans-serif`;
    const w = ctx.measureText(spec.attribution).width + 10 * sc;
    ctx.fillStyle = "rgba(255,255,255,.8)";
    ctx.fillRect(W - w, H - 15 * sc, w, 15 * sc);
    ctx.fillStyle = "#333";
    ctx.textAlign = "right";
    ctx.fillText(spec.attribution, W - 5 * sc, H - 4 * sc);
  }
  return canvas;
}
