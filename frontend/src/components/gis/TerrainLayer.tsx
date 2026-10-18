/**
 * Digital terrain model (DTM) of Pakistan on the map, decoded in the browser from the open
 * AWS Terrain Tiles (Terrarium PNGs: SRTM 30 m over Pakistan, with GMTED2010 / ETOPO1 for coarse
 * zooms; registry.opendata.aws/terrain-tiles). Each tile's pixels are real heights in metres, so
 * the layer can:
 *   colour   hypsometric tints, green lowlands → brown hills → white peaks
 *   shade    hillshade (sun from the north-west) computed from the heights
 * and report the elevation under the mouse (`onElevation`).
 */
import { useEffect, useRef } from "react";
import L from "leaflet";
import { useMap } from "react-leaflet";

const URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const MAX_NATIVE = 15;
export const TERRAIN_ATTRIBUTION = 'Elevation: <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noreferrer">AWS Terrain Tiles</a> (SRTM, GMTED2010, ETOPO1)';

/** Colour stops (metres → rgb), tuned for Pakistan's 0 – 8,611 m. */
export const ELEVATION_STOPS: [number, [number, number, number]][] = [
  [-20, [168, 213, 240]],
  [0, [46, 125, 50]],
  [150, [104, 170, 82]],
  [400, [178, 205, 120]],
  [800, [232, 214, 140]],
  [1500, [205, 160, 100]],
  [2500, [160, 112, 74]],
  [3500, [128, 100, 88]],
  [4500, [170, 165, 160]],
  [5500, [235, 235, 235]],
  [7000, [255, 255, 255]],
];
export const ELEVATION_GRADIENT = `linear-gradient(to right, ${ELEVATION_STOPS.slice(1)
  .map(([m, c]) => `rgb(${c.join(",")}) ${Math.round((m / 7000) * 100)}%`)
  .join(", ")})`;

function colourAt(m: number): [number, number, number] {
  const s = ELEVATION_STOPS;
  if (m <= s[0]![0]) return s[0]![1];
  for (let i = 1; i < s.length; i++) {
    const [m1, c1] = s[i]!;
    if (m <= m1) {
      const [m0, c0] = s[i - 1]!;
      const t = (m - m0) / (m1 - m0);
      return [c0[0] + (c1[0] - c0[0]) * t, c0[1] + (c1[1] - c0[1]) * t, c0[2] + (c1[2] - c0[2]) * t];
    }
  }
  return s[s.length - 1]![1];
}

/** Decoded heights per tile ("z/x/y"), kept for the elevation read-out. */
const heights = new Map<string, Float32Array>();
function remember(key: string, h: Float32Array) {
  heights.set(key, h);
  if (heights.size > 300) heights.delete(heights.keys().next().value!);
}

class TerrainGrid extends L.GridLayer {
  constructor(
    private mode: { colour: boolean; shade: boolean },
    options: L.GridLayerOptions,
  ) {
    super(options);
  }

  protected createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 256;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        this.paint(canvas, img, coords);
        done(undefined, canvas);
      } catch (e) {
        done(e as Error, canvas);
      }
    };
    img.onerror = () => done(new Error("terrain tile failed"), canvas);
    img.src = L.Util.template(URL, coords);
    return canvas;
  }

  private paint(canvas: HTMLCanvasElement, img: HTMLImageElement, c: L.Coords) {
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    ctx.drawImage(img, 0, 0);
    const im = ctx.getImageData(0, 0, 256, 256);
    const d = im.data;
    const h = new Float32Array(256 * 256);
    for (let i = 0; i < h.length; i++) h[i] = d[i * 4]! * 256 + d[i * 4 + 1]! + d[i * 4 + 2]! / 256 - 32768;
    remember(`${c.z}/${c.x}/${c.y}`, h);

    // Ground size of a pixel at this tile's latitude, for the slope.
    const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * (c.y + 0.5)) / 2 ** c.z))) * 180) / Math.PI;
    const px = (156543.03 * Math.cos((lat * Math.PI) / 180)) / 2 ** c.z;
    const zen = (45 * Math.PI) / 180;
    const az = (315 * Math.PI) / 180;
    const { colour, shade } = this.mode;
    for (let y = 0; y < 256; y++) {
      for (let x = 0; x < 256; x++) {
        const i = y * 256 + x;
        const e = h[i]!;
        let hs = 1;
        if (shade) {
          const l = h[y * 256 + Math.max(0, x - 1)]!;
          const r = h[y * 256 + Math.min(255, x + 1)]!;
          const t = h[Math.max(0, y - 1) * 256 + x]!;
          const b = h[Math.min(255, y + 1) * 256 + x]!;
          const dzdx = (r - l) / (2 * px);
          const dzdy = (b - t) / (2 * px);
          const slope = Math.atan(Math.hypot(dzdx, dzdy));
          const aspect = Math.atan2(dzdy, -dzdx);
          hs = Math.max(0, Math.cos(zen) * Math.cos(slope) + Math.sin(zen) * Math.sin(slope) * Math.cos(az - aspect));
        }
        const o = i * 4;
        if (colour) {
          const [cr, cg, cb] = colourAt(e);
          const k = shade ? 0.45 + 0.65 * hs : 1;
          d[o] = Math.min(255, cr * k);
          d[o + 1] = Math.min(255, cg * k);
          d[o + 2] = Math.min(255, cb * k);
          d[o + 3] = 255;
        } else {
          // Shade only: dark on slopes facing away from the sun, clear on flat ground.
          const g = Math.round(255 * hs);
          d[o] = d[o + 1] = d[o + 2] = g < 180 ? 20 : 255;
          d[o + 3] = g < 180 ? Math.min(200, (180 - g) * 1.3) : Math.min(90, (g - 180) * 1.2);
        }
      }
    }
    ctx.putImageData(im, 0, 0);
  }
}

/** Elevation (m) at a point from the tiles already loaded, or null. */
export function elevationAt(map: L.Map, ll: L.LatLng): number | null {
  const z = Math.min(MAX_NATIVE, Math.max(0, Math.round(map.getZoom())));
  const p = map.project(ll, z);
  const tx = Math.floor(p.x / 256);
  const ty = Math.floor(p.y / 256);
  const h = heights.get(`${z}/${tx}/${ty}`);
  if (!h) return null;
  const v = h[Math.floor(p.y - ty * 256) * 256 + Math.floor(p.x - tx * 256)];
  return v == null ? null : Math.round(v);
}

export function TerrainLayer({
  colour,
  shade,
  opacity = 0.65,
  onElevation,
}: {
  colour: boolean;
  shade: boolean;
  opacity?: number;
  onElevation?: (m: number | null, ll: L.LatLng | null) => void;
}) {
  const map = useMap();
  const cb = useRef(onElevation);
  cb.current = onElevation;

  useEffect(() => {
    if (!colour && !shade) return;
    if (!map.getPane("terrain")) map.createPane("terrain").style.zIndex = "250";
    const layer = new TerrainGrid({ colour, shade }, { pane: "terrain", maxNativeZoom: MAX_NATIVE, maxZoom: 20, opacity, attribution: TERRAIN_ATTRIBUTION, tileSize: 256 });
    layer.addTo(map);
    return () => {
      layer.remove();
    };
  }, [map, colour, shade, opacity]);

  useEffect(() => {
    if (!colour && !shade) return;
    const move = (e: L.LeafletMouseEvent) => cb.current?.(elevationAt(map, e.latlng), e.latlng);
    const out = () => cb.current?.(null, null);
    map.on("mousemove", move);
    map.on("mouseout", out);
    return () => {
      map.off("mousemove", move);
      map.off("mouseout", out);
      cb.current?.(null, null);
    };
  }, [map, colour, shade]);

  return null;
}
