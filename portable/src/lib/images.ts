/**
 * Property imagery — same deterministic mapping as the web portal (frontend/src/lib/images.ts)
 * so a listing shows the same cover in both apps. Real uploaded photos always win.
 */
import { apiBase } from "./api";
import { asset } from "./utils";

const PER_CATEGORY = 4;
const KNOWN = ["house", "villa", "apartment", "tower", "office", "shop", "plot", "farmhouse", "building", "floor", "space", "mall"];

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

type Imageable = { id?: string; title?: string; category?: string | null; image_urls?: string[]; kanal_area?: number | null; price?: number };

function categoryFor(p: Imageable): string {
  const c = (p.category ?? "").toLowerCase();
  const t = (p.title ?? "").toLowerCase();
  if (t.includes("farmhouse")) return "farmhouse";
  if (c === "house" && ((p.kanal_area ?? 0) >= 1 || (p.price ?? 0) >= 80_000_000)) return "villa";
  if (KNOWN.includes(c)) return c;
  if (/(tower|mall|plaza)/.test(t)) return "tower";
  return "house";
}

/** Photos may be absolute URLs, backend uploads (/media/…) or portal seed paths (/seed/…). */
function resolve(url: string): string {
  if (/^(https?:|data:|blob:)/.test(url)) return url;
  if (url.startsWith("/media/")) return `${apiBase()}${url}`;
  return asset(url);
}

export function coverImage(p: Imageable): string {
  if (p.image_urls?.length) return resolve(p.image_urls[0]!);
  const cat = categoryFor(p);
  const n = (hash(p.id ?? p.title ?? cat) % PER_CATEGORY) + 1;
  return asset(`seed/properties/${cat}-${n}.svg`);
}

export function gallery(p: Imageable): string[] {
  if (p.image_urls && p.image_urls.length > 0) return p.image_urls.map(resolve);
  const cat = categoryFor(p);
  const h = hash(p.id ?? p.title ?? cat);
  const ext = Array.from({ length: PER_CATEGORY }, (_, i) => asset(`seed/properties/${cat}-${((h + i) % PER_CATEGORY) + 1}.svg`));
  const isLand = cat === "plot";
  const interiors = isLand ? [] : [0, 1, 2].map((i) => asset(`seed/interiors/interior-${((h + i) % 6) + 1}.svg`));
  const plan = isLand ? [] : [asset(`seed/plans/plan-${(h % 3) + 1}.svg`)];
  return [...ext.slice(0, 3), ...interiors, ...plan];
}

export function cityImage(name?: string | null): string {
  const n = (name ?? "").toLowerCase();
  if (["lahore", "karachi", "islamabad", "rawalpindi"].includes(n)) return asset(`seed/cities/${n}.svg`);
  return asset("seed/cities/rawalpindi.svg");
}

export const HERO = {
  panorama: asset("seed/hero/islamabad-panorama.webp"),
  villa: asset("seed/hero/luxury-villa.webp"),
  aiMap: asset("seed/hero/ai-map.webp"),
  landscape: asset("seed/hero/pakistan-landscape.webp"),
  headerEn: asset("brand/header-en.webp"),
};

export const BRAND = {
  logo: asset("brand/logo-en.webp"),
  mark: asset("brand/logo-mark.webp"),
};

/**
 * Downscale a picked photo to a JPEG data URL (max 1280px, ~80% quality) so it can be
 * stored with the listing through the existing `/images` endpoint.
 */
export async function compressImage(file: File, max = 1280, quality = 0.8): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((ok, fail) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = () => fail(new Error("Unsupported image"));
      i.src = url;
    });
    const scale = Math.min(1, max / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", quality);
  } finally {
    URL.revokeObjectURL(url);
  }
}
