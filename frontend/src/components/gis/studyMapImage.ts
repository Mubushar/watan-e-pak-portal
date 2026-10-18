/**
 * A static map image of a study area for the case-study report: base-map tiles fitted to the
 * drawn shape, the shape itself, its centre, listings inside, a scale bar, a north arrow and the
 * attribution — drawn on a canvas (2× for print) and returned as a data URL (PNG; JPEG for satellite).
 */
import type { StudyShape } from "./AreaDraw";

export type StudyMapBase = "streets" | "satellite";

const TILE = 256;
const BASES: Record<StudyMapBase, { url: (z: number, x: number, y: number) => string; attribution: string; maxZoom: number }> = {
  streets: {
    url: (z, x, y) => `https://${"abc"[(x + y) % 3]}.basemaps.cartocdn.com/rastertiles/voyager/${z}/${x}/${y}.png`,
    attribution: "© OpenStreetMap contributors © CARTO",
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
  opts: { base?: StudyMapBase; width?: number; height?: number; points?: [number, number][]; title?: string } = {},
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
        loadTile(base.url(zr, wx, ty)).then((img) => {
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
  const at = base.attribution;
  const aw = ctx.measureText(at).width;
  ctx.fillStyle = "rgba(255,255,255,0.85)";
  ctx.fillRect(W - aw - 14, H - 16, aw + 14, 16);
  ctx.fillStyle = "#334155";
  ctx.fillText(at, W - aw - 7, H - 5);

  // Photos compress far better as JPEG (a satellite PNG runs to ~5 MB).
  return opts.base === "satellite" ? canvas.toDataURL("image/jpeg", 0.86) : canvas.toDataURL("image/png");
}
