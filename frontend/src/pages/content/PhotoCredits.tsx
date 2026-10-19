/**
 * Photo credits: every photograph the portal shows that isn't a listing's own — the photo library
 * used for listings without photos, the page headers, and the landing page — with author,
 * licence and a link to the original.
 */
import { Camera, ExternalLink } from "lucide-react";
import { PHOTO_LIBRARY } from "@/lib/photoLibrary";
import { HERO_PHOTOS } from "@/pages/public/home/Landing";
import { titleCase } from "@/lib/format";

const SECTION_LABELS: Record<string, string> = {
  scene: "Page headers (Islamabad)",
  house: "Houses",
  villa: "Large houses & villas",
  apartment: "Apartments",
  interior: "Interiors",
  tower: "Towers",
  office: "Offices",
  shop: "Shops & markets",
  mall: "Malls",
  plot: "Plots & land",
  farmhouse: "Farmhouses",
  building: "Commercial buildings",
};

export default function PhotoCredits() {
  return (
    <div className="container py-10">
      <p className="section-eyebrow">Photo credits</p>
      <h1 className="mt-1 font-display text-3xl font-bold text-brand-900 dark:text-white">The photographs on Arz-e-Pak</h1>
      <p className="mt-3 max-w-3xl text-sm text-ink-mute">
        Listings show their owner’s or developer’s own photos. When a listing has none yet, it shows a <b>representative photo</b> — a real photograph of a similar property, clearly marked as
        such — from the library below. All are free-licence photographs (Creative Commons or public domain) from Wikimedia Commons, Flickr, Rawpixel, StockSnap and the WordPress Photo
        Directory; city and society photos are credited where they appear.
      </p>

      <section className="mt-8">
        <h2 className="font-display text-xl font-semibold text-brand-900 dark:text-white">Landing page</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {HERO_PHOTOS.map((p) => (
            <figure key={p.img} className="card overflow-hidden">
              <img src={p.img.replace(/\/\d+px-/, "/500px-")} alt={p.caption} loading="lazy" className="aspect-[4/3] w-full object-cover" />
              <figcaption className="p-3 text-xs">
                <p className="font-semibold text-ink dark:text-white">{p.caption}</p>
                <p className="mt-0.5 text-ink-mute">{p.credit}</p>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      {Object.entries(PHOTO_LIBRARY).map(([cat, photos]) => (
        <section key={cat} className="mt-10">
          <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-brand-900 dark:text-white">
            <Camera className="h-5 w-5 text-gold-600" /> {SECTION_LABELS[cat] ?? titleCase(cat)}
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {photos.map((p) => (
              <figure key={p.src} className="card overflow-hidden">
                <img src={`/${p.src}`} alt={p.title} loading="lazy" className="aspect-[4/3] w-full object-cover" />
                <figcaption className="p-3 text-xs">
                  <p className="line-clamp-1 font-semibold text-ink dark:text-white">{p.title || "Untitled"}</p>
                  <a href={p.link} target="_blank" rel="noreferrer" className="mt-0.5 inline-flex items-center gap-1 text-ink-mute hover:text-brand-700">
                    {p.credit} <ExternalLink className="h-3 w-3" />
                  </a>
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
