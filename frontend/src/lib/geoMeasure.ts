/**
 * Distances, areas and coordinates for the map's measure tool, shared pins and the assistant.
 * Lengths are great-circle (haversine); areas are on a local equal-area projection around the
 * shape (well under 0.1 % off for anything up to tens of km across). Pakistani land units:
 * 1 marla = 272.25 sq ft (Punjab revenue / government); societies such as DHA use 225 sq ft.
 */
export type LatLon = [number, number];

const R = 6_371_008.8; // mean Earth radius (m)
const rad = (d: number) => (d * Math.PI) / 180;

export function distanceM(a: LatLon, b: LatLon): number {
  const dLat = rad(b[0] - a[0]);
  const dLon = rad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function pathLengthM(pts: LatLon[]): number {
  let m = 0;
  for (let i = 1; i < pts.length; i++) m += distanceM(pts[i - 1]!, pts[i]!);
  return m;
}

/** Area (m²) of a ring (first point need not repeat). */
export function polygonAreaM2(ring: LatLon[]): number {
  if (ring.length < 3) return 0;
  const lat0 = rad(ring.reduce((a, p) => a + p[0], 0) / ring.length);
  const k = Math.cos(lat0);
  let a = 0;
  for (let i = 0; i < ring.length; i++) {
    const [y1, x1] = ring[i]!;
    const [y2, x2] = ring[(i + 1) % ring.length]!;
    a += rad(x1) * k * rad(y2) - rad(x2) * k * rad(y1);
  }
  return (Math.abs(a) / 2) * R * R;
}

export function centroid(pts: LatLon[]): LatLon {
  return [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[1], 0) / pts.length];
}

const SQFT = 0.09290304;
export const MARLA_SQFT = 272.25;
export const MARLA_SQFT_SOCIETY = 225;

export function fmtLength(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(m >= 100_000 ? 0 : m >= 10_000 ? 1 : 2)} km`;
  return `${m >= 100 ? Math.round(m) : m.toFixed(1)} m`;
}

/** Every unit people use for a length (for the assistant and reports). */
export function lengthUnits(m: number) {
  return { meters: Math.round(m * 10) / 10, km: Math.round(m) / 1000, feet: Math.round(m / 0.3048), miles: Math.round((m / 1609.344) * 1000) / 1000, text: fmtLength(m) };
}

export function fmtArea(m2: number): string {
  if (m2 >= 1_000_000) return `${(m2 / 1_000_000).toFixed(2)} km²`;
  const kanal = m2 / SQFT / (MARLA_SQFT * 20);
  if (kanal >= 1) return `${kanal.toFixed(kanal >= 100 ? 0 : 1)} kanal · ${Math.round(m2).toLocaleString()} m²`;
  return `${(m2 / SQFT / MARLA_SQFT).toFixed(1)} marla · ${Math.round(m2).toLocaleString()} m²`;
}

/** Every unit people use for an area (marla / kanal in both the government and the society size). */
export function areaUnits(m2: number) {
  const sqft = m2 / SQFT;
  const r = (x: number, d = 2) => Math.round(x * 10 ** d) / 10 ** d;
  return {
    square_meters: r(m2, 1),
    square_feet: Math.round(sqft),
    marla: r(sqft / MARLA_SQFT),
    kanal: r(sqft / (MARLA_SQFT * 20), 3),
    marla_society_225sqft: r(sqft / MARLA_SQFT_SOCIETY),
    kanal_society_4500sqft: r(sqft / (MARLA_SQFT_SOCIETY * 20), 3),
    acres: r(m2 / 4046.8564224, 3),
    hectares: r(m2 / 10_000, 3),
    square_km: r(m2 / 1_000_000, 4),
    text: fmtArea(m2),
  };
}

function dms(v: number, pos: string, neg: string): string {
  const a = Math.abs(v);
  const d = Math.floor(a);
  const mf = (a - d) * 60;
  const m = Math.floor(mf);
  const s = (mf - m) * 60;
  return `${d}°${String(m).padStart(2, "0")}′${s.toFixed(1).padStart(4, "0")}″${v >= 0 ? pos : neg}`;
}
export const toDms = (lat: number, lon: number) => `${dms(lat, "N", "S")} ${dms(lon, "E", "W")}`;
export const fmtLatLon = (lat: number, lon: number, d = 6) => `${lat.toFixed(d)}, ${lon.toFixed(d)}`;
export const googleMapsUrl = (lat: number, lon: number) => `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(6)},${lon.toFixed(6)}`;

/**
 * Coordinates written in a message or a place box: "33.6844, 73.0479", "33.6844 N 73.0479 E",
 * "33°41'4"N 73°2'52"E", or a Google Maps link (…@33.68,73.04… / ?q=33.68,73.04). Null when none.
 */
export function parseCoords(text: string): LatLon | null {
  const s = text.trim();
  const link = s.match(/[@=](-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)/);
  if (link) return valid(Number(link[1]), Number(link[2]));
  const dmsRe = /(\d{1,3})\s*[°º]\s*(\d{1,2})?\s*['′]?\s*(\d{1,2}(?:\.\d+)?)?\s*["″]?\s*([NSEW])/gi;
  const parts = [...s.matchAll(dmsRe)];
  if (parts.length >= 2) {
    const val = (m: RegExpMatchArray) => {
      const v = Number(m[1]) + Number(m[2] ?? 0) / 60 + Number(m[3] ?? 0) / 3600;
      return /[SW]/i.test(m[4]!) ? -v : v;
    };
    const a = parts[0]!;
    const b = parts[1]!;
    const lat = /[NS]/i.test(a[4]!) ? val(a) : val(b);
    const lon = /[EW]/i.test(b[4]!) ? val(b) : val(a);
    return valid(lat, lon);
  }
  const dec = s.match(/(-?\d{1,2}\.\d{2,})\s*°?\s*([NS])?\s*[,;\s]\s*(-?\d{1,3}\.\d{2,})\s*°?\s*([EW])?/i);
  if (dec) {
    const lat = Number(dec[1]) * (dec[2] && /s/i.test(dec[2]) ? -1 : 1);
    const lon = Number(dec[3]) * (dec[4] && /w/i.test(dec[4]) ? -1 : 1);
    return valid(lat, lon);
  }
  return null;
}
function valid(lat: number, lon: number): LatLon | null {
  return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lat, lon] : null;
}
