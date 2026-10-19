/**
 * Property imagery — same deterministic mapping as the web portal (frontend/src/lib/images.ts)
 * so a listing shows the same cover in both apps. A listing's own photos always win; the rest
 * get REAL photographs from the portal's photo library (public/seed/photos/, credited in
 * photoLibrary.ts), marked "Representative photo".
 */
import { apiBase } from "./api";
import { asset } from "./utils";
import { PHOTO_LIBRARY, type LibraryPhoto } from "./photoLibrary";

const KNOWN = ["house", "villa", "apartment", "tower", "office", "shop", "plot", "farmhouse", "building", "mall"];
/** Listing categories without their own photo set borrow the closest one. */
const ALIAS: Record<string, string> = { floor: "house", space: "office", portion: "house", flat: "apartment", warehouse: "building" };

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

type Imageable = { id?: string; title?: string; category?: string | null; image_urls?: string[]; kanal_area?: number | null; price?: number };

function categoryFor(p: Imageable): string {
  const c = (p.category ?? "").toLowerCase();
  const t = (p.title ?? "").toLowerCase();
  if (t.includes("farmhouse") || t.includes("farm house")) return "farmhouse";
  if (c === "house" && ((p.kanal_area ?? 0) >= 1 || (p.price ?? 0) >= 80_000_000)) return "villa";
  if (KNOWN.includes(c)) return c;
  if (ALIAS[c]) return ALIAS[c]!;
  if (/(tower|mall|plaza)/.test(t)) return "tower";
  return "house";
}

const pool = (cat: string): LibraryPhoto[] => (PHOTO_LIBRARY[cat]?.length ? PHOTO_LIBRARY[cat]! : PHOTO_LIBRARY.house ?? []);
const url = (ph: LibraryPhoto) => asset(ph.src);
const BY_SRC = new Map(Object.values(PHOTO_LIBRARY).flat().map((ph) => [url(ph), ph]));

/** The library photo (with its credit) behind a URL, if it is one. */
export function libraryPhoto(src: string): LibraryPhoto | undefined {
  return BY_SRC.get(src);
}

/** True when the image is a representative library photo, not the listing's own. */
export function isRepresentative(src: string): boolean {
  return BY_SRC.has(src);
}

function pick(cat: string, key: string, offset = 0): string {
  const list = pool(cat);
  return list.length ? url(list[(hash(key) + offset) % list.length]!) : "";
}

/** Photos may be absolute URLs, backend uploads (/media/…) or portal seed paths (/seed/…). */
function resolve(src: string): string {
  if (/^(https?:|data:|blob:)/.test(src)) return src;
  if (src.startsWith("/media/")) return `${apiBase()}${src}`;
  return asset(src);
}

export function coverImage(p: Imageable): string {
  if (p.image_urls?.length) return resolve(p.image_urls[0]!);
  return pick(categoryFor(p), p.id ?? p.title ?? "");
}

/** Gallery: three exterior photos, three interiors (not for plots / shops) and a floor plan. */
export function gallery(p: Imageable): string[] {
  if (p.image_urls && p.image_urls.length > 0) return p.image_urls.map(resolve);
  const cat = categoryFor(p);
  const key = p.id ?? p.title ?? cat;
  const size = pool(cat).length || 1;
  const ext = [...new Set([0, 1, 2].map((i) => pick(cat, key, i % size)))];
  const indoor = !["plot", "shop", "mall", "building", "tower"].includes(cat);
  const interiors = indoor ? [...new Set([0, 1, 2].map((i) => pick("interior", key, i)))] : [];
  const plan = indoor ? [asset(`seed/plans/plan-${(hash(key) % 3) + 1}.svg`)] : [];
  return [...ext, ...interiors, ...plan].filter(Boolean);
}

/** A Wikimedia Commons thumbnail at a smaller standard width (phones don't need 1280 px). */
export function sized(src: string, width: 330 | 500 | 960 | 1280 = 500): string {
  return src.includes("upload.wikimedia.org") ? src.replace(/\/\d+px-/, `/${width}px-`) : src;
}

/** A city's real (credited) photo when it has one, else an Islamabad scene. */
export function cityImage(name?: string | null, image?: string | null): string {
  if (image) return sized(image, 500);
  return pick("scene", name ?? "city");
}

const scene = (i: number) => (PHOTO_LIBRARY.scene?.[i] ? url(PHOTO_LIBRARY.scene[i]!) : "");

export const HERO = {
  panorama: scene(0),
  villa: pick("villa", "hero"),
  aiMap: scene(2),
  landscape: scene(1),
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
  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((ok, fail) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = () => fail(new Error("Unsupported image"));
      i.src = objectUrl;
    });
    const scale = Math.min(1, max / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", quality);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
