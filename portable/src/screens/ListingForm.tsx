/**
 * Create-listing wizard: Describe → Location → Size & price → Photos → Review.
 * The first step can be filled by speaking ("I'm selling a 10 marla house in DHA
 * Lahore for 4.5 crore"), and the assistant can open this screen with a draft.
 *   POST /me/listings                 (owned by the signed-in account)
 *   POST /me/listings/{id}/photos     (one call per photo)
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Camera, CheckCircle2, Home, ImagePlus, Loader2, MapPin, Mic, Ruler, Sparkles, Square, Trash2 } from "lucide-react";
import { toast } from "sonner";
import type { City, Hierarchy, Property } from "@/types";
import { useApi } from "@/hooks/useApi";
import { useChat } from "@/lib/assistant";
import { post } from "@/lib/api";
import { area, pkr, pkrShort, titleCase } from "@/lib/format";
import { compressImage, coverImage } from "@/lib/images";
import { draftFromIntent, parseIntent, type ListingDraft } from "@/lib/intent";
import { listen, type ListenSession } from "@/lib/voice";
import { cn } from "@/lib/utils";
import { Button, Field, Input, Segmented, Select, Stepper, Textarea, TopBar } from "@/components/ui";

const CATEGORIES = ["house", "apartment", "plot", "shop", "office", "floor", "building"];
const STEPS = [
  { key: "basics", label: "Describe", icon: Home },
  { key: "location", label: "Location", icon: MapPin },
  { key: "details", label: "Size & price", icon: Ruler },
  { key: "photos", label: "Photos", icon: ImagePlus },
  { key: "review", label: "Review", icon: CheckCircle2 },
] as const;
const MAX_PHOTOS = 8;

interface Form {
  title: string;
  description: string;
  category: string;
  use_type: string;
  city_id: string;
  scheme_id: string;
  block_zone_area_id: string;
  unit: "marla" | "kanal";
  size: number;
  bedrooms: number;
  bathrooms: number;
  price: number;
  /** Comma-separated: "Solar system, Basement, Gated community". */
  amenities: string;
  photos: string[];
}

export default function ListingForm() {
  const nav = useNavigate();
  const loc = useLocation();
  const [incoming] = useState<ListingDraft | undefined>(() => (loc.state as { draft?: ListingDraft } | null)?.draft ?? useChat.getState().pendingDraft ?? undefined);
  const cities = useApi<{ cities: City[] }>("/cities");
  const tree = useApi<Hierarchy>("/hierarchy");
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [created, setCreated] = useState<Property | null>(null);
  const [f, setF] = useState<Form>({
    title: "",
    description: "",
    category: "house",
    use_type: "residential",
    city_id: "",
    scheme_id: "",
    block_zone_area_id: "",
    unit: "marla",
    size: 10,
    bedrooms: 3,
    bathrooms: 3,
    price: 0,
    amenities: "",
    photos: [],
  });
  const set = (patch: Partial<Form>) => setF((x) => ({ ...x, ...patch }));

  // ---- apply a draft (from the assistant or from speaking on step 1)
  const applyDraft = (d: ListingDraft) => {
    const city = d.city ? cities.data?.cities.find((c) => c.name.toLowerCase() === d.city!.toLowerCase()) : undefined;
    const kanal = d.marla && d.marla >= 20 && d.marla % 20 === 0;
    setF((x) => ({
      ...x,
      title: d.title ?? x.title,
      description: d.description ?? x.description,
      category: d.category ?? x.category,
      use_type: d.use_type ?? x.use_type,
      city_id: city?.id ?? x.city_id,
      unit: d.marla ? (kanal ? "kanal" : "marla") : x.unit,
      size: d.marla ? (kanal ? d.marla / 20 : d.marla) : x.size,
      bedrooms: d.bedrooms ?? x.bedrooms,
      bathrooms: d.bathrooms ?? d.bedrooms ?? x.bathrooms,
      price: d.price ?? x.price,
    }));
  };
  const appliedIncoming = useRef(false);
  useEffect(() => {
    if (incoming && cities.data && !appliedIncoming.current) {
      appliedIncoming.current = true;
      useChat.getState().setPendingDraft(null);
      applyDraft(incoming);
      toast.success("Filled in from your conversation — review and adjust");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming, cities.data]);

  // ---- voice description
  const [rec, setRec] = useState<ListenSession | null>(null);
  const [partial, setPartial] = useState("");
  const describeByVoice = async () => {
    if (rec) return rec.stop();
    try {
      const s = await listen({ onPartial: setPartial });
      setRec(s);
      const said = (await s.result).text;
      setRec(null);
      setPartial("");
      if (!said) return toast.info("I didn't catch that — try again or type it.");
      const names = cities.data?.cities.map((c) => c.name) ?? [];
      applyDraft(draftFromIntent({ ...parseIntent(said, names), action: "sell" }, said));
      toast.success("Got it — I've filled in what you said");
    } catch (e) {
      setRec(null);
      setPartial("");
      toast.error((e as Error).message);
    }
  };

  const schemes = tree.data?.tree.find((c) => c.id === f.city_id)?.schemes ?? [];
  const blocks = schemes.find((s) => s.id === f.scheme_id)?.blocks ?? [];
  const city = cities.data?.cities.find((c) => c.id === f.city_id);
  const isLand = f.category === "plot";
  const marla = f.unit === "kanal" ? f.size * 20 : f.size;
  const preview = useMemo<Property>(
    () => ({
      id: "preview",
      title: f.title || "Your listing",
      price: f.price,
      category: f.category,
      use_type: f.use_type,
      status: "active",
      marla_area: marla,
      kanal_area: marla / 20,
      bedrooms: isLand ? null : f.bedrooms,
      bathrooms: isLand ? null : f.bathrooms,
      city_name: city?.name,
      image_urls: f.photos.slice(0, 1),
    }),
    [f, marla, isLand, city],
  );

  const canNext = [f.title.trim().length >= 5, !!f.city_id, f.price > 0 && f.size > 0, true, true][step];

  const addPhotos = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy("Preparing photos…");
    try {
      const room = MAX_PHOTOS - f.photos.length;
      const picked = Array.from(files).slice(0, room);
      const out = await Promise.all(picked.map((file) => compressImage(file)));
      set({ photos: [...f.photos, ...out] });
      if (files.length > room) toast.info(`Up to ${MAX_PHOTOS} photos per listing`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const amenityList = f.amenities.split(/[,،\n]/).map((a) => a.trim()).filter(Boolean);

  const publish = async () => {
    setBusy("Publishing…");
    try {
      const p = await post<Property>("/me/listings", {
        title: f.title.trim(),
        description: f.description.trim() || undefined,
        category: f.category,
        use_type: f.use_type,
        city_id: f.city_id,
        scheme_id: f.scheme_id || undefined,
        block_zone_area_id: f.block_zone_area_id || undefined,
        marla_area: marla,
        bedrooms: isLand ? undefined : f.bedrooms,
        bathrooms: isLand ? undefined : f.bathrooms,
        price: f.price,
        amenities: amenityList.length ? amenityList : undefined,
      });
      for (let i = 0; i < f.photos.length; i++) {
        setBusy(`Uploading photo ${i + 1} of ${f.photos.length}…`);
        await post(`/me/listings/${p.id}/photos`, { data_url: f.photos[i], is_primary: false }, { timeoutMs: 60_000 }).catch(() => toast.error(`Photo ${i + 1} couldn't be uploaded`));
      }
      setCreated(p);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (created)
    return (
      <div>
        <TopBar title="Listing published" />
        <div className="screen flex flex-col items-center pt-14 text-center">
          <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex h-20 w-20 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-500/15">
            <CheckCircle2 className="h-10 w-10" />
          </motion.span>
          <h1 className="mt-5 font-display text-2xl font-bold text-brand-900 dark:text-white">You're live! 🎉</h1>
          <p className="mt-2 max-w-sm text-ink-mute">“{created.title}” is now searchable in the app, on the Arz-e-Pak portal and by every AI agent.</p>
          <div className="mt-8 grid w-full max-w-sm gap-3">
            <Link to={`/property/${created.id}`} className="btn btn-primary btn-lg">
              View listing
            </Link>
            <Link to={`/assistant?q=${encodeURIComponent(`How can I sell my ${area(created)} ${created.category} in ${city?.name ?? "my city"} faster at ${pkrShort(created.price)}?`)}`} className="btn btn-gold">
              <Sparkles className="h-4 w-4" /> Get AI selling tips
            </Link>
            <Link to="/listings" className="btn btn-ghost">
              Back to my listings
            </Link>
          </div>
        </div>
      </div>
    );

  return (
    <div>
      <TopBar back="/listings" title="New listing" />
      <div className="screen pt-4">
        {/* progress */}
        <div className="flex items-center gap-1.5">
          {STEPS.map((s, i) => (
            <button key={s.key} disabled={i > step} onClick={() => setStep(i)} className="flex flex-1 flex-col items-center gap-1" aria-label={s.label}>
              <span className={cn("h-1.5 w-full rounded-full transition", i <= step ? "bg-brand-600" : "bg-black/10 dark:bg-white/10")} />
              <span className={cn("hidden text-[11px] font-semibold sm:block", i === step ? "text-brand-700 dark:text-brand-300" : "text-ink-mute")}>{s.label}</span>
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs font-semibold uppercase tracking-wider text-gold-600 dark:text-gold-300">
          Step {step + 1} of {STEPS.length} · {STEPS[step]!.label}
        </p>

        <AnimatePresence mode="wait">
          <motion.div key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} className="mt-4 space-y-5">
            {step === 0 && (
              <>
                <button
                  type="button"
                  onClick={() => void describeByVoice()}
                  className={cn("flex w-full items-center gap-4 rounded-2xl p-4 text-start text-white shadow-soft transition", rec ? "bg-red-600" : "bg-brand-gradient")}
                >
                  <span className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white/15">
                    {rec && <span className="absolute inset-0 animate-pulse-ring rounded-full bg-white/40" />}
                    {rec ? <Square className="relative h-5 w-5 fill-white" /> : <Mic className="relative h-6 w-6 text-gold-200" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-semibold">{rec ? "Listening… tap to finish" : "Describe it by voice"}</span>
                    <span className="block truncate text-xs text-white/80">{partial || "“Selling a 10 marla house in DHA Lahore, 4 beds, for 4.5 crore”"}</span>
                  </span>
                </button>
                <Field label="I want to">
                  <Segmented
                    value={f.use_type === "commercial" ? "commercial" : "residential"}
                    onChange={(v) => set({ use_type: v })}
                    options={[
                      { value: "residential", label: "Residential" },
                      { value: "commercial", label: "Commercial" },
                    ]}
                  />
                </Field>
                <Field label="Property type">
                  <div className="grid grid-cols-4 gap-2">
                    {CATEGORIES.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => set({ category: c, use_type: ["shop", "office"].includes(c) ? "commercial" : f.use_type })}
                        className={cn("rounded-xl border px-1 py-2.5 text-xs font-semibold transition", f.category === c ? "border-brand-600 bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-white" : "border-black/10 bg-white dark:border-white/10 dark:bg-white/5")}
                      >
                        {titleCase(c)}
                      </button>
                    ))}
                  </div>
                </Field>
                <Field label="Title" hint="e.g. “Brand-new 10 Marla House in DHA Phase 6”">
                  <Input value={f.title} onChange={(e) => set({ title: e.target.value })} placeholder="Give your listing a clear title" maxLength={90} />
                </Field>
                <Field label="Description">
                  <Textarea value={f.description} onChange={(e) => set({ description: e.target.value })} placeholder="Highlights, condition, nearby landmarks, possession…" />
                </Field>
                <Field label="Amenities" hint="Separate with commas — buyers can search for these">
                  <Input value={f.amenities} onChange={(e) => set({ amenities: e.target.value })} placeholder="e.g. Solar system, Basement, Gated community, Parking" />
                </Field>
              </>
            )}

            {step === 1 && (
              <>
                <Field label="City">
                  <Select value={f.city_id} onChange={(e) => set({ city_id: e.target.value, scheme_id: "", block_zone_area_id: "" })}>
                    <option value="">Choose a city</option>
                    {cities.data?.cities.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Scheme / society" hint={f.city_id && !schemes.length ? "No registered schemes in this city yet — that's fine." : undefined}>
                  <Select value={f.scheme_id} disabled={!schemes.length} onChange={(e) => set({ scheme_id: e.target.value, block_zone_area_id: "" })}>
                    <option value="">{schemes.length ? "Choose a scheme (optional)" : "—"}</option>
                    {schemes.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Block / sector">
                  <Select value={f.block_zone_area_id} disabled={!blocks.length} onChange={(e) => set({ block_zone_area_id: e.target.value })}>
                    <option value="">{blocks.length ? "Choose a block (optional)" : "—"}</option>
                    {blocks.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} · {titleCase(b.area_type)}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            )}

            {step === 2 && (
              <>
                <Field label="Size">
                  <div className="flex gap-2">
                    <Input inputMode="decimal" className="flex-1" value={f.size || ""} onChange={(e) => set({ size: parseFloat(e.target.value) || 0 })} />
                    <Segmented
                      className="w-44"
                      value={f.unit}
                      onChange={(unit) => set({ unit })}
                      options={[
                        { value: "marla", label: "Marla" },
                        { value: "kanal", label: "Kanal" },
                      ]}
                    />
                  </div>
                </Field>
                {!isLand && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Stepper label="Bedrooms" value={f.bedrooms} onChange={(bedrooms) => set({ bedrooms })} />
                    <Stepper label="Bathrooms" value={f.bathrooms} onChange={(bathrooms) => set({ bathrooms })} />
                  </div>
                )}
                <Field label="Asking price (PKR)" hint={f.price > 0 ? `${pkrShort(f.price)} · ${pkr(f.price)}` : "Type the full amount, e.g. 45000000"}>
                  <Input inputMode="numeric" value={f.price || ""} onChange={(e) => set({ price: Number(e.target.value.replace(/\D/g, "")) || 0 })} placeholder="45000000" />
                </Field>
                <div className="flex flex-wrap gap-2">
                  {[5_000_000, 10_000_000, 25_000_000, 50_000_000, 100_000_000].map((v) => (
                    <button key={v} type="button" onClick={() => set({ price: v })} className="chip bg-brand-50 text-brand-800 dark:bg-white/10 dark:text-brand-100">
                      {pkrShort(v)}
                    </button>
                  ))}
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4">
                  {f.photos.map((src, i) => (
                    <div key={i} className="relative aspect-square overflow-hidden rounded-xl">
                      <img src={src} alt="" className="h-full w-full object-cover" />
                      {i === 0 && <span className="chip absolute start-1.5 top-1.5 bg-gold-gradient text-[10px] text-brand-950">Cover</span>}
                      <button type="button" onClick={() => set({ photos: f.photos.filter((_, j) => j !== i) })} className="absolute end-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white" aria-label="Remove photo">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                  {f.photos.length < MAX_PHOTOS && (
                    <>
                      <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-brand-300 text-brand-700 dark:border-white/20 dark:text-brand-200">
                        <ImagePlus className="h-6 w-6" />
                        <span className="text-xs font-semibold">Gallery</span>
                        <input type="file" accept="image/*" multiple className="hidden" onChange={(e) => void addPhotos(e.target.files)} />
                      </label>
                      <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-brand-300 text-brand-700 dark:border-white/20 dark:text-brand-200">
                        <Camera className="h-6 w-6" />
                        <span className="text-xs font-semibold">Camera</span>
                        <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => void addPhotos(e.target.files)} />
                      </label>
                    </>
                  )}
                </div>
                <p className="text-sm text-ink-mute dark:text-slate-400">Add up to {MAX_PHOTOS} photos. The first one is the cover. No photos? We'll show a matching illustration until you add some.</p>
              </>
            )}

            {step === 4 && (
              <div className="card overflow-hidden">
                <img src={coverImage(preview)} alt="" className="aspect-[16/9] w-full object-cover" />
                <div className="space-y-3 p-4">
                  <div>
                    <p className="font-display text-2xl font-bold text-brand-700 dark:text-brand-300">{pkrShort(f.price)}</p>
                    <p className="font-display text-lg font-bold">{f.title}</p>
                    <p className="text-sm text-ink-mute">
                      {[blocks.find((b) => b.id === f.block_zone_area_id)?.name, schemes.find((s) => s.id === f.scheme_id)?.name, city?.name].filter(Boolean).join(", ")}
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {[
                      ["Type", `${titleCase(f.category)} · ${titleCase(f.use_type)}`],
                      ["Size", `${f.size} ${titleCase(f.unit)}`],
                      ...(isLand ? [] : [["Beds / baths", `${f.bedrooms} / ${f.bathrooms}`]]),
                      ["Photos", String(f.photos.length)],
                    ].map(([k, v]) => (
                      <div key={k} className="rounded-xl bg-brand-50/60 p-2.5 dark:bg-white/5">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-mute">{k}</p>
                        <p className="font-semibold">{v}</p>
                      </div>
                    ))}
                  </div>
                  {f.description && <p className="whitespace-pre-line text-sm text-ink-soft dark:text-slate-300">{f.description}</p>}
                  {!!amenityList.length && <p className="text-sm text-ink-soft dark:text-slate-300">{amenityList.join(" · ")}</p>}
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        <div className="mt-8 flex gap-3 pb-6">
          {step > 0 && (
            <Button variant="outline" size="lg" icon={<ArrowLeft className="h-4 w-4" />} onClick={() => setStep(step - 1)}>
              Back
            </Button>
          )}
          {step < STEPS.length - 1 ? (
            <Button size="lg" className="flex-1" disabled={!canNext || !!busy} onClick={() => setStep(step + 1)}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {busy ?? "Continue"} {!busy && <ArrowRight className="h-4 w-4 rtl:rotate-180" />}
            </Button>
          ) : (
            <Button variant="gold" size="lg" className="flex-1" loading={!!busy} onClick={() => void publish()}>
              {busy ?? "Publish listing"}
            </Button>
          )}
        </div>
        {!f.title && step === 0 && (
          <button type="button" className="mb-6 w-full text-center text-sm font-semibold text-ink-mute" onClick={() => nav("/assistant?q=" + encodeURIComponent("Help me list my property for sale"))}>
            Not sure? Let the AI assistant guide you →
          </button>
        )}
      </div>
    </div>
  );
}
