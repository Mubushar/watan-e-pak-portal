/**
 * Map backend entities to images. Listings with their own photos (uploads via
 * `POST /me/listings/{id}/photos` → `/media/uploads/…`, or a developer's photos) show those; the
 * rest get a deterministic, category-appropriate set of REAL photographs from the portal's photo
 * library (public/seed/photos/, built by backend/build_listing_photos.py, credited in
 * photoLibrary.ts). Those are marked "Representative photo" wherever a listing shows them.
 */
import { API_BASE } from "./api";
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

const pool = (cat: string): LibraryPhoto[] => PHOTO_LIBRARY[cat]?.length ? PHOTO_LIBRARY[cat]! : PHOTO_LIBRARY.house ?? [];
const url = (ph: LibraryPhoto) => `/${ph.src}`;
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

/** Photos may be absolute URLs, backend uploads (/media/…) or seed paths (/seed/…). */
export function resolveImage(src: string): string {
  if (src.startsWith("/media/")) return `${API_BASE}${src}`;
  return src;
}

/** Primary cover image for a property. Its own photos win over the library. */
export function coverImage(p: Imageable): string {
  if (p.image_urls?.length) return resolveImage(p.image_urls[0]!);
  return pick(categoryFor(p), p.id ?? p.title ?? "");
}

/** Gallery: three exterior photos, three interiors (not for plots / shops) and a floor plan. */
export function gallery(p: Imageable): string[] {
  if (p.image_urls?.length) return p.image_urls.map(resolveImage);
  const cat = categoryFor(p);
  const key = p.id ?? p.title ?? cat;
  const size = pool(cat).length || 1;
  const ext = [...new Set([0, 1, 2].map((i) => pick(cat, key, i % size)))];
  const indoor = !["plot", "shop", "mall", "building", "tower"].includes(cat);
  const interiors = indoor ? [...new Set([0, 1, 2].map((i) => pick("interior", key, i)))] : [];
  const h = hash(key);
  const plan = indoor ? [`/seed/plans/plan-${(h % 3) + 1}.svg`] : [];
  return [...ext, ...interiors, ...plan].filter(Boolean);
}

/** A Wikimedia Commons thumbnail at a smaller standard width (cards don't need 1280 px). */
export function sized(src: string, width: 330 | 500 | 960 | 1280 = 960): string {
  return src.includes("upload.wikimedia.org") ? src.replace(/\/\d+px-/, `/${width}px-`) : src;
}

/** A city's photo: its real (credited) image when it has one, else an Islamabad scene. */
export function cityImage(name?: string | null, image?: string | null): string {
  if (image) return sized(image, 960);
  return pick("scene", name ?? "city");
}

/** Image for a society / big project / story / news item, chosen by keyword then hash. */
export function themedImage(key: string, hint?: string | null): string {
  const h = (hint ?? "").toLowerCase();
  let cat = "building";
  if (/(mall|arcade|retail)/.test(h)) cat = "mall";
  else if (/(shop|market|bazaar|store)/.test(h)) cat = "shop";
  else if (/(tower|skyscraper|high-rise|heights)/.test(h)) cat = "tower";
  else if (/(office|corporate|tech|business)/.test(h)) cat = "office";
  else if (/(compound|villa|garden|housing|residence|home|house|society|dha|bahria|town|city|enclave|phase)/.test(h)) cat = "house";
  else if (/(apartment|flat)/.test(h)) cat = "apartment";
  else if (/(plot|land|development|infrastructure|road|sector)/.test(h)) cat = "plot";
  else if (/(farm)/.test(h)) cat = "farmhouse";
  return pick(cat, key);
}

const scene = (i: number) => (PHOTO_LIBRARY.scene?.[i] ? url(PHOTO_LIBRARY.scene[i]!) : "");

/** Page headers: real Islamabad photographs (credited on the photo credits page). */
export const HERO = {
  panorama: scene(0),
  landscape: scene(1),
  villa: pick("villa", "hero"),
  aiMap: scene(2),
  headerEn: "/brand/header-en.webp",
  headerUr: "/brand/header-ur.webp",
};

export const BRAND = {
  logo: "/brand/logo-en.webp",
  logoUr: "/brand/logo-ur.webp",
  mark: "/brand/logo-mark.webp",
};

/**
 * Downscale a picked photo to a JPEG data URL (max 1600px, ~82% quality) for
 * `POST /me/listings/{id}/photos`, which accepts JPEG / PNG / WebP up to 5 MB.
 */
export async function compressImage(file: File, max = 1600, quality = 0.82): Promise<string> {
  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((ok, fail) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = () => fail(new Error(`${file.name} isn’t a supported image`));
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
