/**
 * Master-plan text drawn as text on one canvas: each label sized from the plan's own text
 * (`size_m`, metres on the ground, enlarged by BOOST because the printed text is tiny) and
 * at its orientation (`rot`, degrees CCW from east), so the map reads like the plan. Small
 * text appears as you zoom in; labels that would overlap a larger one are skipped. Redrawn after every pan / zoom, so cost depends on what's on
 * screen, not on the ~15,000 labels a plan can have.
 */
import L from "leaflet";
import type { FeatureCollection } from "geojson";

interface Label {
  lat: number;
  lon: number;
  text: string;
  /** Text height on the ground, metres. */
  size: number;
  /** Radians, clockwise on screen (canvas convention). */
  rot: number;
}

const MIN_PX = 8; // smaller text is unreadable: wait for the next zoom level
// The plan's own lettering is ~6 m tall for streets and plot numbers (≈6 px at zoom 17):
// draw labels larger than printed so they read at zoom 17 and up.
const BOOST = 1.8;
const MAX_PX = 28;
const CELL = 12; // collision grid, px
const FONT = '700 {px}px "Plus Jakarta Sans", system-ui, sans-serif';

function prepare(data: FeatureCollection): Label[] {
  const out: Label[] = [];
  for (const f of data.features) {
    if (f.geometry?.type !== "Point") continue;
    const p = f.properties ?? {};
    const text = String(p.text ?? "").trim();
    if (!text) continue;
    const [lon, lat] = f.geometry.coordinates as [number, number];
    // Older data has no size_m: fall back to a fixed 6 m, roughly a plot number.
    const size = typeof p.size_m === "number" && p.size_m > 0 ? p.size_m : 6;
    let deg = typeof p.rot === "number" ? p.rot : typeof p.angle === "number" ? p.angle : 0;
    // Keep text upright: flip anything pointing left.
    if (deg > 90) deg -= 180;
    else if (deg < -90) deg += 180;
    out.push({ lat, lon, text, size, rot: (-deg * Math.PI) / 180 });
  }
  // Big text (sector, road and park names) claims space first.
  return out.sort((a, b) => b.size - a.size);
}

export class PlanTextLayer extends L.Layer {
  private labels: Label[];
  private canvas: HTMLCanvasElement | null = null;
  private frame = 0;

  constructor(
    data: FeatureCollection,
    private color: string,
  ) {
    super();
    this.labels = prepare(data);
  }

  onAdd(map: L.Map): this {
    const pane = map.getPane("planText") ?? map.createPane("planText");
    pane.style.zIndex = "450"; // above shapes (400), below markers (600)
    pane.style.pointerEvents = "none";
    const canvas = L.DomUtil.create("canvas", "leaflet-zoom-hide", pane);
    this.canvas = canvas;
    map.on("moveend zoomend resize viewreset", this.schedule, this);
    this.draw();
    return this;
  }

  onRemove(map: L.Map): this {
    map.off("moveend zoomend resize viewreset", this.schedule, this);
    cancelAnimationFrame(this.frame);
    this.canvas?.remove();
    this.canvas = null;
    return this;
  }

  private schedule() {
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(() => this.draw());
  }

  private draw() {
    const map = (this as unknown as { _map?: L.Map })._map;
    const canvas = this.canvas;
    if (!map || !canvas) return;
    const size = map.getSize();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.x * dpr);
    canvas.height = Math.round(size.y * dpr);
    canvas.style.width = `${size.x}px`;
    canvas.style.height = `${size.y}px`;
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);

    const bounds = map.getBounds().pad(0.1);
    const zoom = map.getZoom();
    const metresPerPx = (40_075_016.686 * Math.cos((map.getCenter().lat * Math.PI) / 180)) / (256 * 2 ** zoom);
    const used = new Set<number>();
    const cols = Math.ceil(size.x / CELL) + 2;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.fillStyle = this.color;
    let font = -1;

    for (const l of this.labels) {
      const px = (l.size * BOOST) / metresPerPx;
      if (px < MIN_PX) break; // sorted by size: everything after is smaller
      if (!bounds.contains([l.lat, l.lon])) continue;
      const fpx = Math.min(MAX_PX, Math.round(px));
      if (fpx !== font) {
        ctx.font = FONT.replace("{px}", String(fpx));
        ctx.lineWidth = Math.max(3, fpx / 3); // white halo keeps text readable over the coloured plan
        font = fpx;
      }
      const p = map.latLngToContainerPoint([l.lat, l.lon]);
      const w = ctx.measureText(l.text).width;
      // Axis-aligned box of the rotated text, for the overlap test.
      const c = Math.abs(Math.cos(l.rot));
      const s = Math.abs(Math.sin(l.rot));
      const hw = (w * c + fpx * s) / 2;
      const hh = (w * s + fpx * c) / 2;
      const x0 = Math.floor((p.x - hw) / CELL) + 1;
      const x1 = Math.floor((p.x + hw) / CELL) + 1;
      const y0 = Math.floor((p.y - hh) / CELL) + 1;
      const y1 = Math.floor((p.y + hh) / CELL) + 1;
      if (x1 < 0 || y1 < 0 || x0 > cols) continue;
      let free = true;
      for (let y = y0; y <= y1 && free; y++) for (let x = x0; x <= x1; x++) if (used.has(y * cols + x)) free = false;
      if (!free) continue;
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) used.add(y * cols + x);
      ctx.save();
      ctx.translate(p.x, p.y);
      if (l.rot) ctx.rotate(l.rot);
      ctx.strokeText(l.text, 0, 0);
      ctx.fillText(l.text, 0, 0);
      ctx.restore();
    }
  }
}
