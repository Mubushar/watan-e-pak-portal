#!/usr/bin/env node
/**
 * Seed the frontend with local real-estate imagery for testing.
 *
 *   npm run seed
 *
 * Produces (all under public/):
 *   brand/        logo, logo mark, header banners (resized from the repo's brand PNGs)
 *   seed/hero/    photographic crops of the header banners (hero backgrounds)
 *   seed/properties/<category>-<n>.svg   exterior illustrations per listing category
 *   seed/interiors/interior-<n>.svg      interior scenes for galleries
 *   seed/plans/plan-<n>.svg              floor plans
 *   seed/cities/<city>.svg               landmark skylines per city
 *   seed/manifest.json                   index of everything above
 *
 * Everything is deterministic (seeded PRNG) so re-running yields identical files.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const repo = path.resolve(root, "..");
const pub = path.join(root, "public");
const out = (...p) => path.join(pub, ...p);
const ensure = (d) => fs.mkdirSync(d, { recursive: true });

// ---------------------------------------------------------------- PRNG
function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const pick = (r, arr) => arr[Math.floor(r() * arr.length)];
const between = (r, a, b) => a + r() * (b - a);

// ---------------------------------------------------------------- palettes
const SKIES = {
  dawn: { top: "#8fb8de", mid: "#f6c79b", bottom: "#fde8cf", sun: "#ffd28a", lit: 0.35, hill: ["#9bb3a6", "#7f9a8d"] },
  day: { top: "#5ea9e6", mid: "#a9d6f5", bottom: "#e6f4ff", sun: "#fff4c2", lit: 0.0, hill: ["#8fb0a0", "#6f9483"] },
  golden: { top: "#4a6fa5", mid: "#f2a65a", bottom: "#ffd9a0", sun: "#ffbf5e", lit: 0.6, hill: ["#7c7f86", "#5d6a68"] },
  dusk: { top: "#1f2552", mid: "#a64d79", bottom: "#f6a96b", sun: "#ffb07a", lit: 0.85, hill: ["#3e3d5c", "#2d2f49"] },
  night: { top: "#070d24", mid: "#16234d", bottom: "#2b3d72", sun: "#f3f1de", lit: 1.0, hill: ["#1b2440", "#131a30"] },
};
const FACADES = [
  { wall: "#f4f1ea", trim: "#d9d3c6", accent: "#2b2b2b", wood: "#9b6a43" },
  { wall: "#ece4d6", trim: "#cdbfa8", accent: "#3a3631", wood: "#a5713f" },
  { wall: "#e9ecef", trim: "#c7ccd1", accent: "#1f2933", wood: "#8a5a35" },
  { wall: "#3a3f44", trim: "#2a2e32", accent: "#d9c49a", wood: "#b07a46" },
  { wall: "#e6d5bd", trim: "#c4ab88", accent: "#5a4632", wood: "#7d5432" },
  { wall: "#fafafa", trim: "#e0e0e0", accent: "#0f5a39", wood: "#a06b3f" },
];

// ---------------------------------------------------------------- primitives
const W = 1200, H = 800, GROUND = 560;

function defs(id, sky, r) {
  return `
  <defs>
    <linearGradient id="sky${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${sky.top}"/><stop offset=".62" stop-color="${sky.mid}"/><stop offset="1" stop-color="${sky.bottom}"/>
    </linearGradient>
    <radialGradient id="sun${id}" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="${sky.sun}" stop-opacity="1"/><stop offset=".35" stop-color="${sky.sun}" stop-opacity=".55"/><stop offset="1" stop-color="${sky.sun}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="lawn${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${shade("#4f9a52", -sky.lit * 0.55)}"/><stop offset="1" stop-color="${shade("#2f7a3d", -sky.lit * 0.6)}"/>
    </linearGradient>
    <linearGradient id="glass${id}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${sky.lit > 0.5 ? "#ffd27a" : "#cfe8ff"}"/><stop offset=".5" stop-color="${sky.lit > 0.5 ? "#f2a94a" : "#6fa8d6"}"/><stop offset="1" stop-color="${sky.lit > 0.5 ? "#c9772c" : "#2f5f8a"}"/>
    </linearGradient>
    <linearGradient id="curtain${id}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="${shade("#4b7fa8", -sky.lit * 0.5)}"/><stop offset=".45" stop-color="${shade("#a8d2ef", -sky.lit * 0.55)}"/><stop offset="1" stop-color="${shade("#2c5878", -sky.lit * 0.5)}"/>
    </linearGradient>
    <linearGradient id="road${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${shade("#8a8f93", -sky.lit * 0.5)}"/><stop offset="1" stop-color="${shade("#5f6468", -sky.lit * 0.5)}"/>
    </linearGradient>
    <filter id="blur${id}"><feGaussianBlur stdDeviation="2"/></filter>
    <filter id="glow${id}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>
  </defs>`;
}

function shade(hex, amt) {
  // amt in [-1, 1]; negative darkens, positive lightens
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const t = amt < 0 ? 0 : 255, p = Math.abs(amt);
  r = Math.round((t - r) * p + r); g = Math.round((t - g) * p + g); b = Math.round((t - b) * p + b);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

function skyLayer(id, sky, r) {
  const sx = between(r, 150, 1050), sy = between(r, 90, 220);
  let s = `<rect width="${W}" height="${H}" fill="url(#sky${id})"/>`;
  s += `<circle cx="${sx}" cy="${sy}" r="140" fill="url(#sun${id})"/><circle cx="${sx}" cy="${sy}" r="${sky.lit > 0.9 ? 26 : 38}" fill="${sky.sun}" opacity=".95"/>`;
  if (sky.lit > 0.9) {
    for (let i = 0; i < 70; i++) s += `<circle cx="${between(r, 0, W)}" cy="${between(r, 0, 360)}" r="${between(r, 0.6, 1.8)}" fill="#fff" opacity="${between(r, 0.3, 0.9)}"/>`;
  } else {
    for (let i = 0; i < 4; i++) {
      const cx = between(r, 0, W), cy = between(r, 60, 260), sc = between(r, 0.6, 1.4);
      s += `<g opacity="${sky.lit > 0.5 ? 0.35 : 0.8}" transform="translate(${cx} ${cy}) scale(${sc})"><ellipse rx="70" ry="18" fill="#fff"/><ellipse cx="-35" cy="-10" rx="40" ry="20" fill="#fff"/><ellipse cx="25" cy="-14" rx="46" ry="24" fill="#fff"/></g>`;
    }
  }
  return s;
}

function hills(sky, r, snow = true) {
  let s = "";
  const layers = [
    { base: 470, amp: 150, col: sky.hill[0], op: 0.75 },
    { base: 520, amp: 90, col: sky.hill[1], op: 0.9 },
  ];
  for (const L of layers) {
    let d = `M0 ${GROUND} L0 ${L.base}`;
    const peaks = [];
    for (let x = 0; x <= W; x += 80) {
      const y = L.base - between(r, 0.2, 1) * L.amp;
      peaks.push([x, y]);
      d += ` L${x} ${y.toFixed(1)}`;
    }
    d += ` L${W} ${GROUND} Z`;
    s += `<path d="${d}" fill="${L.col}" opacity="${L.op}"/>`;
    if (snow && L === layers[0]) {
      for (const [x, y] of peaks) if (y < L.base - L.amp * 0.75) s += `<path d="M${x - 22} ${y + 26} L${x} ${y} L${x + 22} ${y + 26} L${x + 8} ${y + 20} L${x} ${y + 30} L${x - 9} ${y + 20}Z" fill="#fff" opacity=".85"/>`;
    }
  }
  return s;
}

function ground(id, sky) {
  return `<rect y="${GROUND}" width="${W}" height="${H - GROUND}" fill="url(#lawn${id})"/>`;
}

function tree(x, y, s, r, sky, kind = "round") {
  const dk = -sky.lit * 0.55;
  if (kind === "palm") {
    let g = `<path d="M${x} ${y} Q${x + 6 * s} ${y - 60 * s} ${x + 2 * s} ${y - 120 * s}" stroke="${shade("#7a5a3a", dk)}" stroke-width="${7 * s}" fill="none"/>`;
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      g += `<path d="M${x + 2 * s} ${y - 120 * s} q${Math.cos(a) * 40 * s} ${-10 * s} ${Math.cos(a) * 60 * s} ${Math.abs(Math.sin(a)) * 30 * s + 10 * s}" stroke="${shade("#2f8a45", dk)}" stroke-width="${9 * s}" fill="none" stroke-linecap="round"/>`;
    }
    return g;
  }
  if (kind === "cypress") {
    return `<rect x="${x - 3 * s}" y="${y - 20 * s}" width="${6 * s}" height="${20 * s}" fill="${shade("#6b4a2e", dk)}"/><ellipse cx="${x}" cy="${y - 70 * s}" rx="${16 * s}" ry="${60 * s}" fill="${shade("#2c6e3a", dk)}"/>`;
  }
  const c1 = shade(pick(r, ["#3f8f4a", "#4d9d50", "#2f7f43", "#5aa65a"]), dk);
  const c2 = shade(c1, -0.15);
  return `<rect x="${x - 4 * s}" y="${y - 40 * s}" width="${8 * s}" height="${40 * s}" fill="${shade("#6b4a2e", dk)}"/>
    <circle cx="${x}" cy="${y - 62 * s}" r="${34 * s}" fill="${c2}"/><circle cx="${x - 22 * s}" cy="${y - 50 * s}" r="${24 * s}" fill="${c1}"/><circle cx="${x + 22 * s}" cy="${y - 52 * s}" r="${26 * s}" fill="${c1}"/><circle cx="${x + 4 * s}" cy="${y - 82 * s}" r="${24 * s}" fill="${c1}"/>`;
}

function hedge(x, y, w, sky) {
  return `<rect x="${x}" y="${y - 18}" width="${w}" height="22" rx="11" fill="${shade("#2f7a3d", -sky.lit * 0.6)}"/>`;
}

function windowRect(id, x, y, w, h, sky, r, frame = "#2b2b2b") {
  const lit = r() < 0.25 + sky.lit * 0.75;
  const fill = lit && sky.lit > 0.3 ? `url(#glass${id})` : sky.lit > 0.3 ? shade("#3b4a5c", -0.3) : `url(#glass${id})`;
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" stroke="${frame}" stroke-width="3"/>`;
  if (w > 40) s += `<line x1="${x + w / 2}" y1="${y}" x2="${x + w / 2}" y2="${y + h}" stroke="${frame}" stroke-width="2"/>`;
  if (lit && sky.lit > 0.5) s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#ffcc66" opacity=".25" filter="url(#glow${id})"/>`;
  return s;
}

function car(x, y, r, sky) {
  const c = shade(pick(r, ["#c0392b", "#f4f4f4", "#1f2933", "#2c6fb0", "#9aa5b1"]), -sky.lit * 0.4);
  return `<g transform="translate(${x} ${y})"><rect x="0" y="-26" width="120" height="26" rx="10" fill="${c}"/><path d="M22 -26 L38 -46 H86 L102 -26Z" fill="${c}"/><path d="M30 -27 L42 -42 H60 V-27Z M64 -27 V-42 H82 L94 -27Z" fill="${shade("#9fc3dd", -sky.lit * 0.5)}"/><circle cx="28" cy="0" r="12" fill="#1b1b1b"/><circle cx="92" cy="0" r="12" fill="#1b1b1b"/>${sky.lit > 0.5 ? `<circle cx="116" cy="-16" r="5" fill="#fff6c8"/>` : ""}</g>`;
}

// ---------------------------------------------------------------- buildings
function modernHouse(id, x, y, f, sky, r, scale = 1) {
  const s = scale, W1 = 420 * s, H1 = 150 * s, W2 = 320 * s, H2 = 130 * s;
  const lit = sky.lit;
  const wall = shade(f.wall, -lit * 0.45), trim = shade(f.trim, -lit * 0.45), wood = shade(f.wood, -lit * 0.4);
  let g = `<g>`;
  // shadow
  g += `<ellipse cx="${x + W1 / 2}" cy="${y + 6}" rx="${W1 * 0.62}" ry="16" fill="#000" opacity=".18"/>`;
  // ground floor
  g += `<rect x="${x}" y="${y - H1}" width="${W1}" height="${H1}" fill="${wall}"/>`;
  g += `<rect x="${x + W1 * 0.62}" y="${y - H1}" width="${W1 * 0.38}" height="${H1}" fill="${wood}"/>`;
  for (let i = 0; i < 6; i++) g += `<line x1="${x + W1 * 0.62}" y1="${y - H1 + 12 + i * 22 * s}" x2="${x + W1}" y2="${y - H1 + 12 + i * 22 * s}" stroke="${shade(wood, -0.2)}" stroke-width="2"/>`;
  g += windowRect(id, x + 30 * s, y - H1 + 28 * s, 190 * s, 100 * s, sky, r, f.accent);
  g += `<rect x="${x + 240 * s}" y="${y - 110 * s}" width="${36 * s}" height="${110 * s}" fill="${shade(f.accent, -0.1)}"/>`;
  // upper floor (cantilever)
  const ux = x + 70 * s;
  g += `<rect x="${ux - 20 * s}" y="${y - H1 - 14 * s}" width="${W2 + 60 * s}" height="${14 * s}" fill="${trim}"/>`;
  g += `<rect x="${ux}" y="${y - H1 - 14 * s - H2}" width="${W2}" height="${H2}" fill="${wall}"/>`;
  g += windowRect(id, ux + 24 * s, y - H1 - H2 + 12 * s, 120 * s, 80 * s, sky, r, f.accent);
  g += windowRect(id, ux + 170 * s, y - H1 - H2 + 12 * s, 120 * s, 80 * s, sky, r, f.accent);
  // balcony glass
  g += `<rect x="${ux + 150 * s}" y="${y - H1 - 50 * s}" width="${170 * s}" height="${36 * s}" fill="#bfe3f5" opacity=".45" stroke="${trim}" stroke-width="2"/>`;
  // roof slab
  g += `<rect x="${ux - 30 * s}" y="${y - H1 - 14 * s - H2 - 16 * s}" width="${W2 + 70 * s}" height="${16 * s}" fill="${shade(f.accent, -lit * 0.3)}"/>`;
  // solar panels
  if (r() > 0.4) for (let i = 0; i < 4; i++) g += `<rect x="${ux + 20 * s + i * 52 * s}" y="${y - H1 - H2 - 52 * s}" width="${46 * s}" height="${22 * s}" fill="#1d3557" stroke="#8fb3d9" stroke-width="1.5" transform="skewX(-12)"/>`;
  g += `</g>`;
  return g;
}

function villa(id, x, y, f, sky, r) {
  let g = modernHouse(id, x + 160, y, f, sky, r, 1);
  const lit = sky.lit, wall = shade(f.wall, -lit * 0.45);
  // side wing
  g += `<rect x="${x}" y="${y - 120}" width="190" height="120" fill="${shade(wall, -0.05)}"/>`;
  g += windowRect(id, x + 20, y - 95, 150, 70, sky, r, f.accent);
  g += `<rect x="${x - 10}" y="${y - 132}" width="210" height="12" fill="${shade(f.accent, -lit * 0.3)}"/>`;
  // pool
  g += `<path d="M${x - 40} ${y + 70} L${x + 360} ${y + 70} L${x + 400} ${y + 130} L${x - 80} ${y + 130}Z" fill="${shade("#3fb6d9", -lit * 0.5)}" stroke="#e8f6fb" stroke-width="5"/>`;
  g += `<path d="M${x - 20} ${y + 95} q40 -8 80 0 t80 0 t80 0 t80 0" stroke="#ffffff" stroke-opacity=".6" stroke-width="3" fill="none"/>`;
  return g;
}

function apartment(id, x, y, f, sky, r, floors = 10, cols = 5) {
  const fw = 72, fh = 46, w = cols * fw + 40, h = floors * fh + 30;
  const lit = sky.lit, wall = shade(f.wall, -lit * 0.5), trim = shade(f.trim, -lit * 0.5);
  let g = `<ellipse cx="${x + w / 2}" cy="${y + 6}" rx="${w * 0.65}" ry="16" fill="#000" opacity=".18"/>`;
  g += `<rect x="${x}" y="${y - h}" width="${w}" height="${h}" fill="${wall}"/>`;
  g += `<rect x="${x + w - 30}" y="${y - h}" width="30" height="${h}" fill="${shade(wall, -0.12)}"/>`;
  for (let fl = 0; fl < floors; fl++) {
    const fy = y - 30 - (fl + 1) * fh;
    g += `<rect x="${x - 6}" y="${fy + fh - 6}" width="${w + 12}" height="6" fill="${trim}"/>`;
    for (let c = 0; c < cols; c++) {
      g += windowRect(id, x + 20 + c * fw, fy + 6, fw - 22, fh - 18, sky, r, f.accent);
      if (c % 2 === 0) g += `<rect x="${x + 14 + c * fw}" y="${fy + fh - 22}" width="${fw - 10}" height="16" fill="#cde9f6" opacity=".35" stroke="${trim}" stroke-width="1.5"/>`;
    }
  }
  // lobby
  g += `<rect x="${x + w / 2 - 50}" y="${y - 30}" width="100" height="30" fill="url(#glass${id})" stroke="${f.accent}" stroke-width="3"/>`;
  g += `<rect x="${x - 10}" y="${y - h - 14}" width="${w + 20}" height="14" fill="${shade(f.accent, -lit * 0.3)}"/>`;
  return g;
}

function glassTower(id, x, y, sky, r, floors = 18) {
  const w = 230, fh = 24, h = floors * fh + 40;
  let g = `<ellipse cx="${x + w / 2}" cy="${y + 6}" rx="${w * 0.7}" ry="14" fill="#000" opacity=".2"/>`;
  g += `<rect x="${x}" y="${y - h}" width="${w}" height="${h}" fill="url(#curtain${id})"/>`;
  for (let i = 1; i < floors; i++) g += `<line x1="${x}" y1="${y - 40 - i * fh}" x2="${x + w}" y2="${y - 40 - i * fh}" stroke="#ffffff" stroke-opacity=".25" stroke-width="1.5"/>`;
  for (let c = 1; c < 6; c++) g += `<line x1="${x + (c * w) / 6}" y1="${y - h}" x2="${x + (c * w) / 6}" y2="${y - 40}" stroke="#0b2236" stroke-opacity=".35" stroke-width="2"/>`;
  if (sky.lit > 0.4) for (let i = 0; i < floors * 3; i++) if (r() < sky.lit * 0.5) g += `<rect x="${x + Math.floor(r() * 6) * (w / 6) + 3}" y="${y - 40 - Math.ceil(r() * floors) * fh + 3}" width="${w / 6 - 6}" height="${fh - 6}" fill="#ffd27a" opacity=".85"/>`;
  g += `<path d="M${x + w * 0.1} ${y - h} L${x + w * 0.55} ${y - h} L${x + w * 0.1} ${y - h * 0.55}Z" fill="#fff" opacity=".12"/>`;
  g += `<rect x="${x - 20}" y="${y - 40}" width="${w + 40}" height="40" fill="${shade("#2c3440", -sky.lit * 0.3)}"/>`;
  g += `<rect x="${x + 40}" y="${y - 34}" width="${w - 80}" height="30" fill="url(#glass${id})"/>`;
  g += `<rect x="${x + w / 2 - 4}" y="${y - h - 60}" width="8" height="60" fill="#9aa5b1"/><circle cx="${x + w / 2}" cy="${y - h - 62}" r="5" fill="#e74c3c"/>`;
  return g;
}

function plaza(id, x, y, f, sky, r) {
  const w = 620, floors = 3, fh = 80;
  const lit = sky.lit, wall = shade(f.wall, -lit * 0.45);
  let g = `<ellipse cx="${x + w / 2}" cy="${y + 6}" rx="${w * 0.6}" ry="14" fill="#000" opacity=".18"/>`;
  g += `<rect x="${x}" y="${y - floors * fh - 30}" width="${w}" height="${floors * fh + 30}" fill="${wall}"/>`;
  g += `<rect x="${x}" y="${y - floors * fh - 30}" width="${w}" height="30" fill="${shade("#0f5a39", -lit * 0.3)}"/>`;
  g += `<text x="${x + w / 2}" y="${y - floors * fh - 9}" text-anchor="middle" font-family="Outfit, Arial" font-weight="700" font-size="20" fill="#f2dd8f" letter-spacing="4">${pick(r, ["CITY PLAZA", "GRAND ARCADE", "MARKET SQUARE", "TRADE CENTRE"])}</text>`;
  const awn = ["#c0392b", "#0f5a39", "#c99a22", "#2c6fb0"];
  for (let fl = 0; fl < floors; fl++) {
    const fy = y - (fl + 1) * fh;
    for (let c = 0; c < 6; c++) {
      const cx = x + 14 + c * 101;
      if (fl === 0) {
        g += `<rect x="${cx}" y="${fy + 22}" width="88" height="${fh - 22}" fill="url(#glass${id})" stroke="${f.accent}" stroke-width="3"/>`;
        g += `<path d="M${cx - 4} ${fy + 22} L${cx + 92} ${fy + 22} L${cx + 84} ${fy + 6} L${cx + 4} ${fy + 6}Z" fill="${awn[(c + fl) % 4]}"/>`;
      } else {
        g += windowRect(id, cx + 6, fy + 14, 76, fh - 30, sky, r, f.accent);
      }
    }
    g += `<rect x="${x - 6}" y="${fy - 4}" width="${w + 12}" height="6" fill="${shade(f.trim, -lit * 0.4)}"/>`;
  }
  return g;
}

function farmhouse(id, x, y, f, sky, r) {
  const lit = sky.lit, wall = shade(f.wall, -lit * 0.45);
  const roof = shade(pick(r, ["#8c3b2a", "#5a3a2a", "#3d4b55"]), -lit * 0.3);
  let g = `<ellipse cx="${x + 300}" cy="${y + 6}" rx="380" ry="16" fill="#000" opacity=".18"/>`;
  g += `<rect x="${x}" y="${y - 130}" width="600" height="130" fill="${wall}"/>`;
  g += `<path d="M${x - 30} ${y - 130} L${x + 120} ${y - 230} L${x + 480} ${y - 230} L${x + 630} ${y - 130}Z" fill="${roof}"/>`;
  g += `<rect x="${x + 30}" y="${y - 120}" width="540" height="10" fill="${shade(f.wood, -lit * 0.4)}"/>`;
  for (let c = 0; c < 6; c++) g += `<rect x="${x + 40 + c * 92}" y="${y - 110}" width="10" height="110" fill="${shade(f.wood, -lit * 0.4)}"/>`;
  g += windowRect(id, x + 70, y - 95, 120, 70, sky, r, f.accent);
  g += windowRect(id, x + 410, y - 95, 120, 70, sky, r, f.accent);
  g += `<rect x="${x + 260}" y="${y - 100}" width="80" height="100" fill="${shade(f.wood, -0.2 - lit * 0.3)}"/>`;
  // fence
  for (let i = -6; i < 30; i++) g += `<rect x="${x - 200 + i * 36}" y="${y + 96}" width="6" height="36" fill="#f1ede4" opacity=".9"/>`;
  g += `<rect x="${x - 420}" y="${y + 104}" width="1600" height="5" fill="#f1ede4" opacity=".9"/><rect x="${x - 420}" y="${y + 118}" width="1600" height="5" fill="#f1ede4" opacity=".9"/>`;
  return g;
}

function plot(id, sky, r) {
  // perspective view of a demarcated, pegged plot beside an access road
  const lit = sky.lit;
  let g = `<path d="M0 ${GROUND} L${W} ${GROUND} L${W} ${H} L0 ${H}Z" fill="${shade("#c8b48a", -lit * 0.5)}"/>`;
  g += `<path d="M0 ${GROUND + 14} L${W} ${GROUND + 4} L${W} ${GROUND + 46} L0 ${GROUND + 60}Z" fill="url(#road${id})"/>`;
  for (let i = 0; i < 12; i++) g += `<rect x="${i * 110 + 20}" y="${GROUND + 31 - i * 0.9}" width="60" height="4" fill="#f5f5f5" opacity=".8"/>`;
  const pts = [[330, GROUND + 90], [870, GROUND + 86], [1040, H - 40], [160, H - 34]];
  g += `<path d="M${pts.map((p) => p.join(" ")).join(" L")}Z" fill="${shade("#a9c27a", -lit * 0.5)}" stroke="#ffffff" stroke-width="4" stroke-dasharray="18 10"/>`;
  for (let i = 1; i < 4; i++) g += `<line x1="${330 + i * 135}" y1="${GROUND + 89}" x2="${160 + i * 220}" y2="${H - 36}" stroke="#ffffff" stroke-opacity=".35" stroke-width="2" stroke-dasharray="8 8"/>`;
  for (const [px, py] of pts) g += `<rect x="${px - 5}" y="${py - 26}" width="10" height="30" fill="#e74c3c"/><rect x="${px - 5}" y="${py - 26}" width="10" height="8" fill="#fff"/>`;
  g += `<rect x="568" y="${GROUND + 110}" width="8" height="70" fill="#5b4632"/><rect x="628" y="${GROUND + 110}" width="8" height="70" fill="#5b4632"/>`;
  g += `<rect x="527" y="${GROUND + 56}" width="150" height="70" rx="6" fill="#0f5a39" stroke="#c99a22" stroke-width="4"/>`;
  g += `<text x="602" y="${GROUND + 88}" text-anchor="middle" font-family="Outfit, Arial" font-size="20" font-weight="800" fill="#f2dd8f">PLOT</text><text x="602" y="${GROUND + 113}" text-anchor="middle" font-family="Outfit, Arial" font-size="15" font-weight="600" fill="#fff">FOR SALE</text>`;
  return g;
}

function skylineBg(sky, r, n = 10, base = GROUND) {
  let g = "";
  for (let i = 0; i < n; i++) {
    const w = between(r, 40, 90), h = between(r, 60, 200), x = between(r, 0, W - w);
    g += `<rect x="${x}" y="${base - h}" width="${w}" height="${h}" fill="${shade(sky.hill[1], 0.05)}" opacity=".55"/>`;
  }
  return g;
}

// ---------------------------------------------------------------- scene composer
const TIMES = ["day", "golden", "dawn", "dusk", "night", "day"];

function property(category, n) {
  const r = rng(hash(`${category}-${n}`));
  const time = TIMES[n % TIMES.length];
  const sky = SKIES[time];
  const f = FACADES[(n + category.length) % FACADES.length];
  const id = `${category[0]}${n}`;
  let body = skyLayer(id, sky, r);
  const mountains = !["shop", "office", "tower"].includes(category) || r() > 0.5;
  if (mountains) body += hills(sky, r, time !== "dusk");
  if (["apartment", "shop", "office", "tower", "building", "mall"].includes(category)) body += skylineBg(sky, r, 12);
  body += ground(id, sky);
  // driveway / road
  if (category !== "plot") body += `<path d="M0 ${H - 60} L${W} ${H - 90} L${W} ${H} L0 ${H}Z" fill="url(#road${id})"/>`;
  const palms = r() > 0.6;
  const tk = palms ? "palm" : "round";
  switch (category) {
    case "house": {
      body += tree(110, GROUND + 30, 1.3, r, sky, tk) + tree(1080, GROUND + 25, 1.1, r, sky, "cypress");
      body += modernHouse(id, 360, GROUND + 70, f, sky, r, 1.05);
      body += hedge(80, GROUND + 90, 260, sky) + hedge(880, GROUND + 85, 260, sky);
      body += car(140, H - 64, r, sky);
      break;
    }
    case "villa": {
      body += tree(80, GROUND + 30, 1.4, r, sky, tk) + tree(1110, GROUND + 20, 1.3, r, sky, tk);
      body += villa(id, 330, GROUND + 40, f, sky, r);
      body += hedge(40, GROUND + 70, 200, sky);
      break;
    }
    case "apartment": {
      body += apartment(id, 120, GROUND + 60, f, sky, r, 9, 4);
      body += apartment(id, 640, GROUND + 60, FACADES[(n + 2) % FACADES.length], sky, r, 11, 5);
      body += tree(560, GROUND + 70, 1.0, r, sky, tk) + tree(1130, GROUND + 70, 1.0, r, sky, tk);
      body += car(900, H - 70, r, sky);
      break;
    }
    case "tower":
    case "office": {
      body += glassTower(id, 470, GROUND + 60, sky, r, category === "tower" ? 18 : 14);
      body += glassTower(id, 790, GROUND + 60, sky, r, 10);
      body += apartment(id, 110, GROUND + 60, f, sky, r, 7, 4);
      body += tree(420, GROUND + 70, 1, r, sky, "cypress") + tree(1100, GROUND + 70, 1.1, r, sky, tk);
      body += car(300, H - 66, r, sky) + car(700, H - 74, r, sky);
      break;
    }
    case "shop":
    case "space":
    case "mall": {
      body += plaza(id, 290, GROUND + 60, f, sky, r);
      body += tree(180, GROUND + 70, 1.2, r, sky, tk) + tree(1030, GROUND + 70, 1.2, r, sky, tk);
      body += car(420, H - 68, r, sky) + car(640, H - 72, r, sky);
      break;
    }
    case "building":
    case "floor": {
      body += apartment(id, 380, GROUND + 60, f, sky, r, 6, 6);
      body += tree(260, GROUND + 70, 1.2, r, sky, tk) + tree(1010, GROUND + 70, 1.2, r, sky, tk);
      body += car(500, H - 70, r, sky);
      break;
    }
    case "farmhouse": {
      body += tree(90, GROUND + 20, 1.5, r, sky) + tree(1100, GROUND + 15, 1.4, r, sky) + tree(980, GROUND, 1.1, r, sky, "cypress");
      body += farmhouse(id, 300, GROUND + 50, f, sky, r);
      break;
    }
    case "plot":
    default: {
      body += tree(80, GROUND + 10, 1.0, r, sky) + tree(1130, GROUND + 10, 1.0, r, sky);
      body += plot(id, sky, r);
      break;
    }
  }
  // atmospheric vignette
  body += `<rect width="${W}" height="${H}" fill="url(#sky${id})" opacity=".06"/>`;
  return svg(defs(id, sky, r) + body);
}

function svg(inner) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" preserveAspectRatio="xMidYMid slice">${inner}</svg>`;
}

function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return h >>> 0;
}

// ---------------------------------------------------------------- interiors
function interior(n) {
  const r = rng(hash(`interior-${n}`));
  const wall = pick(r, ["#f3eee6", "#e9e4dc", "#eef1ee", "#f5efe4"]);
  const floor = pick(r, ["#c49a6c", "#a77b52", "#d8c3a5", "#8a6a4f"]);
  const sofa = pick(r, ["#2f5d50", "#3a4a6b", "#8c5a3c", "#6b6f72", "#0f5a39"]);
  const rug = pick(r, ["#c99a22", "#b5523b", "#6b8f71", "#4a5a7a"]);
  const outside = pick(r, ["#a9d6f5", "#f6c79b", "#1f2552"]);
  let s = `<defs><linearGradient id="fl${n}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${shade(floor, 0.1)}"/><stop offset="1" stop-color="${shade(floor, -0.2)}"/></linearGradient><linearGradient id="win${n}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${outside}"/><stop offset="1" stop-color="${shade(outside, 0.4)}"/></linearGradient><radialGradient id="lamp${n}"><stop offset="0" stop-color="#ffe2a6" stop-opacity=".9"/><stop offset="1" stop-color="#ffe2a6" stop-opacity="0"/></radialGradient></defs>`;
  s += `<rect width="${W}" height="${H}" fill="${wall}"/>`;
  s += `<path d="M0 560 L${W} 560 L${W} ${H} L0 ${H}Z" fill="url(#fl${n})"/>`;
  for (let i = 0; i < 14; i++) s += `<line x1="${i * 100 - 200}" y1="${H}" x2="${i * 90}" y2="560" stroke="${shade(floor, -0.25)}" stroke-width="2" opacity=".5"/>`;
  // window wall
  s += `<rect x="640" y="90" width="460" height="400" fill="url(#win${n})" stroke="#2b2b2b" stroke-width="8"/>`;
  s += `<line x1="870" y1="90" x2="870" y2="490" stroke="#2b2b2b" stroke-width="6"/>`;
  s += `<path d="M640 420 Q760 360 870 400 T1100 380 V490 H640Z" fill="#4f9a52" opacity=".7"/>`;
  s += `<rect x="610" y="80" width="40" height="440" fill="${shade(sofa, 0.5)}" opacity=".85"/><rect x="1090" y="80" width="40" height="440" fill="${shade(sofa, 0.5)}" opacity=".85"/>`;
  // art
  s += `<rect x="150" y="150" width="220" height="150" fill="#fff" stroke="#3a3631" stroke-width="6"/><path d="M160 290 L230 210 L280 260 L320 220 L360 290Z" fill="${rug}"/><circle cx="320" cy="190" r="18" fill="#c99a22"/>`;
  // rug + sofa + table
  s += `<ellipse cx="460" cy="680" rx="340" ry="70" fill="${rug}" opacity=".85"/>`;
  s += `<rect x="120" y="470" width="520" height="120" rx="26" fill="${sofa}"/><rect x="100" y="500" width="70" height="120" rx="24" fill="${shade(sofa, -0.15)}"/><rect x="590" y="500" width="70" height="120" rx="24" fill="${shade(sofa, -0.15)}"/><rect x="140" y="440" width="480" height="70" rx="24" fill="${shade(sofa, 0.1)}"/>`;
  s += `<rect x="180" y="455" width="90" height="60" rx="14" fill="${shade(rug, 0.3)}"/><rect x="480" y="455" width="90" height="60" rx="14" fill="${shade(rug, 0.2)}"/>`;
  s += `<rect x="300" y="650" width="260" height="22" rx="10" fill="#3a3631"/><rect x="320" y="672" width="12" height="40" fill="#3a3631"/><rect x="528" y="672" width="12" height="40" fill="#3a3631"/>`;
  s += `<circle cx="380" cy="640" r="14" fill="#fff"/><rect x="430" y="626" width="60" height="22" rx="4" fill="${rug}"/>`;
  // plant + lamp
  s += `<rect x="1120" y="600" width="50" height="60" fill="#e6dccd"/><ellipse cx="1145" cy="560" rx="50" ry="70" fill="#3f8f4a"/>`;
  s += `<circle cx="70" cy="300" r="160" fill="url(#lamp${n})"/><rect x="66" y="320" width="8" height="260" fill="#2b2b2b"/><path d="M30 320 L110 320 L90 270 L50 270Z" fill="#f2dd8f"/>`;
  // pendant lights
  for (let i = 0; i < 3; i++) s += `<line x1="${330 + i * 90}" y1="0" x2="${330 + i * 90}" y2="80" stroke="#2b2b2b" stroke-width="2"/><path d="M${310 + i * 90} 80 L${350 + i * 90} 80 L${340 + i * 90} 100 L${320 + i * 90} 100Z" fill="#c99a22"/>`;
  return svg(s);
}

// ---------------------------------------------------------------- floor plans
function floorplan(n) {
  const r = rng(hash(`plan-${n}`));
  const rooms = [
    ["Master Bed", 3, 3], ["Bedroom", 3, 2.5], ["Bedroom", 2.5, 2.5], ["Living", 4, 3], ["Kitchen", 2.5, 2], ["Dining", 3, 2], ["Bath", 1.5, 1.5], ["Bath", 1.5, 1.5], ["Lounge", 3, 2.5], ["Store", 1.5, 1.5],
  ];
  const cell = 70, ox = 120, oy = 90;
  let s = `<rect width="${W}" height="${H}" fill="#f8faf9"/>`;
  for (let x = 0; x < W; x += 25) s += `<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="#e3ebe7" stroke-width="1"/>`;
  for (let y = 0; y < H; y += 25) s += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#e3ebe7" stroke-width="1"/>`;
  let x = 0, y = 0, rowH = 0;
  const maxW = 13;
  const tones = ["#e8f4ee", "#fdf5dc", "#eef2f8", "#f6ece6"];
  for (const [name, w0, h0] of rooms) {
    const w = w0 + (r() > 0.5 ? 0.5 : 0), h = h0;
    if (x + w > maxW) { x = 0; y += rowH; rowH = 0; }
    const px = ox + x * cell, py = oy + y * cell, pw = w * cell, ph = h * cell;
    s += `<rect x="${px}" y="${py}" width="${pw}" height="${ph}" fill="${pick(r, tones)}" stroke="#0f5a39" stroke-width="6"/>`;
    s += `<text x="${px + pw / 2}" y="${py + ph / 2}" text-anchor="middle" font-family="Outfit, Arial" font-size="20" font-weight="700" fill="#0c472e">${name}</text>`;
    s += `<text x="${px + pw / 2}" y="${py + ph / 2 + 24}" text-anchor="middle" font-family="Arial" font-size="14" fill="#5b6b62">${Math.round(w * 4)}' × ${Math.round(h * 4)}'</text>`;
    // door arc
    s += `<path d="M${px + 10} ${py + ph} a34 34 0 0 1 34 -34" fill="none" stroke="#c99a22" stroke-width="3"/>`;
    x += w; rowH = Math.max(rowH, h);
  }
  s += `<text x="${ox}" y="${H - 40}" font-family="Outfit, Arial" font-size="26" font-weight="800" fill="#0f5a39">ARZ-E-PAK · Floor Plan ${String.fromCharCode(65 + n)}</text>`;
  s += `<g transform="translate(${W - 120} ${H - 110})"><circle r="44" fill="none" stroke="#0f5a39" stroke-width="3"/><path d="M0 -40 L10 0 L0 -8 L-10 0Z" fill="#c99a22"/><text y="-48" text-anchor="middle" font-family="Arial" font-size="16" font-weight="700" fill="#0f5a39">N</text></g>`;
  return svg(s);
}

// ---------------------------------------------------------------- cities
function city(name) {
  const r = rng(hash(`city-${name}`));
  const sky = name === "karachi" ? SKIES.golden : name === "lahore" ? SKIES.dusk : name === "islamabad" ? SKIES.dawn : SKIES.day;
  const id = `c${name[0]}`;
  let s = defs(id, sky, r) + skyLayer(id, sky, r);
  if (name === "islamabad" || name === "rawalpindi") s += hills(sky, r, true);
  s += skylineBg(sky, r, 18, 600);
  const dk = -sky.lit * 0.5;
  const fg = shade("#f4efe6", dk);
  if (name === "islamabad") {
    // Faisal-mosque-inspired tent + four minarets
    s += `<path d="M420 600 L600 420 L780 600Z" fill="${fg}"/><path d="M600 420 L640 600 L560 600Z" fill="${shade(fg, -0.1)}"/>`;
    for (const mx of [360, 450, 750, 840]) s += `<rect x="${mx - 6}" y="370" width="12" height="230" fill="${fg}"/><path d="M${mx - 6} 370 L${mx} 330 L${mx + 6} 370Z" fill="${fg}"/>`;
  } else if (name === "lahore") {
    // Minar-inspired tower + domed silhouette
    s += `<path d="M560 600 L580 300 L620 300 L640 600Z" fill="${fg}"/><rect x="566" y="300" width="68" height="14" fill="${shade(fg, -0.1)}"/><rect x="574" y="420" width="52" height="10" fill="${shade(fg, -0.1)}"/><path d="M584 300 L600 250 L616 300Z" fill="${fg}"/>`;
    s += `<rect x="760" y="520" width="260" height="80" fill="${shade("#b5523b", dk)}"/><ellipse cx="890" cy="520" rx="70" ry="60" fill="${shade("#f4efe6", dk)}"/><ellipse cx="800" cy="520" rx="30" ry="28" fill="${shade("#f4efe6", dk)}"/><ellipse cx="980" cy="520" rx="30" ry="28" fill="${shade("#f4efe6", dk)}"/>`;
    s += `<rect x="240" y="500" width="220" height="100" fill="${shade("#b5523b", dk)}"/><path d="M280 600 v-50 a30 30 0 0 1 60 0 v50Z M370 600 v-50 a30 30 0 0 1 60 0 v50Z" fill="${shade("#3a2a20", dk)}"/>`;
  } else if (name === "karachi") {
    s += `<rect x="520" y="480" width="200" height="120" fill="${fg}"/><path d="M520 480 Q620 340 720 480Z" fill="${fg}"/><path d="M540 600 v-70 a30 40 0 0 1 60 0 v70Z M640 600 v-70 a30 40 0 0 1 60 0 v70Z" fill="${shade("#3a3631", dk)}"/>`;
    s += glassTower(id, 820, 600, sky, r, 16) + glassTower(id, 220, 600, sky, r, 12);
  } else {
    s += apartment(id, 200, 600, FACADES[1], sky, r, 8, 4) + apartment(id, 760, 600, FACADES[2], sky, r, 6, 4) + glassTower(id, 500, 600, sky, r, 13);
  }
  s += `<path d="M0 600 L${W} 600 L${W} ${H} L0 ${H}Z" fill="${name === "karachi" ? shade("#2c7fa8", dk) : shade("#3f7f45", dk)}"/>`;
  if (name === "karachi") for (let i = 0; i < 10; i++) s += `<path d="M${i * 130} ${650 + (i % 3) * 30} q30 -10 60 0 t60 0" stroke="#fff" stroke-opacity=".5" stroke-width="3" fill="none"/>`;
  else for (let i = 0; i < 12; i++) s += tree(i * 110 + 40, 640 + (i % 2) * 40, 0.8, r, sky, i % 3 ? "round" : "cypress");
  return svg(s);
}

// ---------------------------------------------------------------- brand assets
/** Turn the logo's near-white background transparent (soft edge for anti-aliasing). */
async function knockOutWhite(img) {
  const { data, info } = await img.ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  for (let i = 0; i < data.length; i += 4) {
    const lo = Math.min(data[i], data[i + 1], data[i + 2]);
    if (lo > 238) data[i + 3] = 0;
    else if (lo > 215) data[i + 3] = Math.round(((238 - lo) / 23) * 255);
  }
  return { data, info: { width: info.width, height: info.height, channels: 4 } };
}

async function brand() {
  ensure(out("brand"));
  ensure(out("seed", "hero"));
  const src = (f) => path.join(repo, f);
  const logoEn = src("Arz-e-Pak AI Real Estate Logo English.png");
  const logoUr = src("Arz-e-Pak AI Real Estate Logo Urdue.png");
  const headEn = src("ARZ-E-PAK Header Image English.png");
  const headUr = src("ARZ-E-PAK Header Image Urdue.png");
  const dash = src("ARZ-E-PAK AI Real Estate Dashboard.png");
  const jobs = [];
  if (fs.existsSync(logoEn)) {
    jobs.push(sharp(logoEn).resize(560).webp({ quality: 88 }).toFile(out("brand", "logo-en.webp")));
    // mark = the emblem without the wordmark, on a transparent background
    const mark = await knockOutWhite(sharp(logoEn).extract({ left: 160, top: 140, width: 960, height: 650 }));
    jobs.push(sharp(mark.data, { raw: mark.info }).resize(320).png().toFile(out("brand", "logo-mark.png")));
    jobs.push(sharp(mark.data, { raw: mark.info }).resize(640).webp({ quality: 90, alphaQuality: 90 }).toFile(out("brand", "logo-mark.webp")));
  }
  if (fs.existsSync(logoUr)) jobs.push(sharp(logoUr).resize(560).webp({ quality: 88 }).toFile(out("brand", "logo-ur.webp")));
  if (fs.existsSync(headEn)) {
    jobs.push(sharp(headEn).resize(1920).webp({ quality: 82 }).toFile(out("brand", "header-en.webp")));
    const m = await sharp(headEn).metadata();
    const box = (l, t, w, h) => ({ left: Math.round(m.width * l), top: Math.round(m.height * t), width: Math.round(m.width * w), height: Math.round(m.height * h) });
    // Crops avoid the banner's logo, tagline and search box.
    jobs.push(sharp(headEn).extract(box(0, 0, 0.3, 0.68)).resize(1400).webp({ quality: 84 }).toFile(out("seed", "hero", "islamabad-panorama.webp")));
    jobs.push(sharp(headEn).extract(box(0.75, 0.24, 0.25, 0.58)).resize(1200).webp({ quality: 84 }).toFile(out("seed", "hero", "luxury-villa.webp")));
    jobs.push(sharp(headEn).extract(box(0.63, 0, 0.37, 0.4)).resize(1200).webp({ quality: 84 }).toFile(out("seed", "hero", "ai-map.webp")));
  }
  if (fs.existsSync(headUr)) jobs.push(sharp(headUr).resize(1920).webp({ quality: 82 }).toFile(out("brand", "header-ur.webp")));
  if (fs.existsSync(dash)) {
    const m = await sharp(dash).metadata();
    jobs.push(sharp(dash).extract({ left: Math.round(m.width * 0.3), top: Math.round(m.height * 0.06), width: Math.round(m.width * 0.32), height: Math.round(m.height * 0.29) }).resize(1600).webp({ quality: 84 }).toFile(out("seed", "hero", "pakistan-landscape.webp")));
    jobs.push(sharp(dash).resize(1600).webp({ quality: 80 }).toFile(out("brand", "dashboard-concept.webp")));
  }
  await Promise.all(jobs);
  return jobs.length;
}

// ---------------------------------------------------------------- main
const CATEGORIES = ["house", "villa", "apartment", "tower", "office", "shop", "plot", "farmhouse", "building", "floor", "space", "mall"];
const PER = 4;

async function main() {
  ensure(out("seed", "properties"));
  ensure(out("seed", "interiors"));
  ensure(out("seed", "plans"));
  ensure(out("seed", "cities"));
  const manifest = { generated: new Date().toISOString().slice(0, 10), properties: {}, interiors: [], plans: [], cities: {}, hero: [], brand: [] };
  for (const c of CATEGORIES) {
    manifest.properties[c] = [];
    for (let n = 0; n < PER; n++) {
      const file = `${c}-${n + 1}.svg`;
      fs.writeFileSync(out("seed", "properties", file), property(c, n));
      manifest.properties[c].push(`/seed/properties/${file}`);
    }
  }
  for (let n = 0; n < 6; n++) {
    fs.writeFileSync(out("seed", "interiors", `interior-${n + 1}.svg`), interior(n));
    manifest.interiors.push(`/seed/interiors/interior-${n + 1}.svg`);
  }
  for (let n = 0; n < 3; n++) {
    fs.writeFileSync(out("seed", "plans", `plan-${n + 1}.svg`), floorplan(n));
    manifest.plans.push(`/seed/plans/plan-${n + 1}.svg`);
  }
  for (const c of ["lahore", "karachi", "islamabad", "rawalpindi"]) {
    fs.writeFileSync(out("seed", "cities", `${c}.svg`), city(c));
    manifest.cities[c] = `/seed/cities/${c}.svg`;
  }
  const n = await brand();
  manifest.hero = fs.existsSync(out("seed", "hero")) ? fs.readdirSync(out("seed", "hero")).map((f) => `/seed/hero/${f}`) : [];
  manifest.brand = fs.existsSync(out("brand")) ? fs.readdirSync(out("brand")).map((f) => `/brand/${f}`) : [];
  fs.writeFileSync(out("seed", "manifest.json"), JSON.stringify(manifest, null, 2));
  const total = CATEGORIES.length * PER + 6 + 3 + 4 + n;
  console.log(`Seeded ${total} images into ${path.relative(repo, pub)}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
