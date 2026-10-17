import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Marker, useMapEvents } from "react-leaflet";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, Home, ImagePlus, MapPin, Ruler, Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";
import type { City, Property } from "@/types";
import { useApi } from "@/hooks/useApi";
import { post } from "@/lib/api";
import { pkr, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { Badge, Button, Card, CardBody, Field, Input, PageHeader, Select, Slider, Textarea, Toggle } from "@/components/ui";
import { PortalMap, pin } from "@/components/map/PortalMap";

interface Tree {
  tree: { id: string; name: string; schemes: { id: string; name: string; blocks: { id: string; name: string; area_type: string }[] }[] }[];
}

const CATEGORIES = ["house", "apartment", "plot", "shop", "office", "floor", "building", "space"];
const STEPS = [
  { key: "basics", label: "Basics", icon: Home },
  { key: "location", label: "Location", icon: MapPin },
  { key: "details", label: "Size & price", icon: Ruler },
  { key: "photos", label: "Photos", icon: ImagePlus },
  { key: "review", label: "Review", icon: CheckCircle2 },
] as const;
const MARLA_SQFT = 272.25;

function ClickToPlace({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

export default function ListingNew() {
  const nav = useNavigate();
  const user = useAuth((s) => s.user);
  const cities = useApi<{ cities: City[] }>("/cities");
  const tree = useApi<Tree>("/hierarchy");
  const [step, setStep] = useState(0);
  const [created, setCreated] = useState<Property | null>(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({
    title: "",
    description: "",
    category: "house",
    use_type: "residential",
    city_id: "",
    scheme_id: "",
    block_zone_area_id: "",
    latitude: 0,
    longitude: 0,
    marla_area: 10,
    bedrooms: 4,
    bathrooms: 4,
    price: 35_000_000,
    featured: false,
    images: [] as string[],
  });
  const set = (patch: Partial<typeof f>) => setF((x) => ({ ...x, ...patch }));

  const city = cities.data?.cities.find((c) => c.id === f.city_id);
  const schemes = tree.data?.tree.find((c) => c.id === f.city_id)?.schemes ?? [];
  const blocks = schemes.find((s) => s.id === f.scheme_id)?.blocks ?? [];
  const isLand = f.category === "plot";
  const library = useMemo(() => {
    const cat = f.category === "house" && f.marla_area >= 20 ? "villa" : f.category;
    const ext = [1, 2, 3, 4].map((n) => `/seed/properties/${cat}-${n}.svg`);
    const int = isLand ? [] : [1, 2, 3, 4, 5, 6].map((n) => `/seed/interiors/interior-${n}.svg`);
    const plans = isLand ? [] : [1, 2, 3].map((n) => `/seed/plans/plan-${n}.svg`);
    return [...ext, ...int, ...plans];
  }, [f.category, f.marla_area, isLand]);

  const canNext = [
    f.title.trim().length >= 5,
    !!f.city_id,
    f.price > 0 && f.marla_area > 0,
    true,
    true,
  ][step];

  const autoTitle = () => {
    const size = f.marla_area >= 20 ? `${+(f.marla_area / 20).toFixed(1)} Kanal` : `${f.marla_area} Marla`;
    const where = [blocks.find((b) => b.id === f.block_zone_area_id)?.name, schemes.find((s) => s.id === f.scheme_id)?.name, city?.name].filter(Boolean)[0] ?? "Prime Location";
    set({ title: `${size} ${isLand ? "Plot" : titleCase(f.category)} in ${where}` });
  };
  const autoDescription = () => {
    const where = [schemes.find((s) => s.id === f.scheme_id)?.name, city?.name].filter(Boolean).join(", ");
    set({
      description: isLand
        ? `A well-located ${f.marla_area}-marla ${f.use_type} plot${where ? ` in ${where}` : ""}, ideal for building your dream home or as a long-term investment. Clear title, wide access road and all utilities nearby.`
        : `Beautifully finished ${f.bedrooms}-bedroom ${f.category}${where ? ` in ${where}` : ""} on ${f.marla_area} marla with ${f.bathrooms} bathrooms. Modern layout, ample natural light, secure neighbourhood and easy access to schools, mosques and markets.`,
    });
  };

  const publish = async () => {
    setBusy(true);
    try {
      const p = await post<Property>("/properties", {
        title: f.title,
        description: f.description || undefined,
        price: f.price,
        city_id: f.city_id,
        scheme_id: f.scheme_id || undefined,
        block_zone_area_id: f.block_zone_area_id || undefined,
        category: f.category,
        use_type: f.use_type,
        marla_area: f.marla_area,
        kanal_area: +(f.marla_area / 20).toFixed(2),
        total_area: Math.round(f.marla_area * MARLA_SQFT),
        bedrooms: isLand ? undefined : f.bedrooms,
        bathrooms: isLand ? undefined : f.bathrooms,
        latitude: f.latitude || city?.latitude,
        longitude: f.longitude || city?.longitude,
        featured: f.featured,
        agent_id: user?.agent_id ?? undefined,
      });
      await Promise.all(f.images.map((url, i) => post("/images", { entity_type: "property", entity_id: p.id, image_url: url, is_primary: i === 0 }).catch(() => null)));
      setCreated(p);
      toast.success("Listing published");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (created)
    return (
      <div className="mx-auto max-w-2xl py-10 text-center">
        <motion.div initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-gold-gradient shadow-glow">
          <Check className="h-10 w-10 text-brand-950" />
        </motion.div>
        <h1 className="mt-6 font-display text-3xl font-bold">Your listing is live</h1>
        <p className="mt-2 text-ink-mute">“{created.title}” is now searchable on the portal, the map and by every AI agent.</p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link to={`/properties/${created.id}`} className="btn btn-primary">
            View listing
          </Link>
          <Link to={`/ai/agents/seller_pricing_agent?objective=${encodeURIComponent(`Price and market ${created.title}`)}`} className="btn btn-gold">
            <Sparkles className="h-4 w-4" /> Get AI pricing & marketing kit
          </Link>
          <Button variant="outline" onClick={() => { setCreated(null); setStep(0); set({ title: "", description: "", images: [] }); }}>
            List another
          </Button>
        </div>
      </div>
    );

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="List a property" subtitle="Five quick steps — the portal geocodes, scores and markets it for you." crumbs={[{ label: "Dashboard", to: "/app" }, { label: "New listing" }]} />

      <div className="mb-6 grid grid-cols-5 gap-2">
        {STEPS.map((s, i) => (
          <button key={s.key} onClick={() => i < step && setStep(i)} className="group text-start" disabled={i > step}>
            <div className={cn("h-1.5 rounded-full transition", i <= step ? "bg-gold-gradient" : "bg-black/10 dark:bg-white/10")} />
            <div className={cn("mt-2 flex items-center gap-1.5 text-xs font-semibold", i === step ? "text-brand-800 dark:text-white" : "text-ink-mute")}>
              <s.icon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{s.label}</span>
            </div>
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <Card>
          <CardBody className="min-h-[420px]">
            <AnimatePresence mode="wait">
              <motion.div key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.2 }} className="space-y-5">
                {step === 0 && (
                  <>
                    <div>
                      <p className="label">Property type</p>
                      <div className="grid grid-cols-4 gap-2">
                        {CATEGORIES.map((c) => (
                          <button key={c} onClick={() => set({ category: c, use_type: ["shop", "office", "space", "building"].includes(c) ? "commercial" : f.use_type })} className={cn("rounded-xl border px-2 py-3 text-sm font-semibold transition", f.category === c ? "border-brand-600 bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-white" : "border-black/10 hover:border-brand-300 dark:border-white/10")}>
                            {titleCase(c)}
                          </button>
                        ))}
                      </div>
                    </div>
                    <Field label="Use">
                      <Select value={f.use_type} onChange={(e) => set({ use_type: e.target.value })} options={["residential", "commercial", "mix"].map((v) => ({ value: v, label: titleCase(v) }))} />
                    </Field>
                    <Field label={<span className="flex items-center justify-between">Title <button type="button" onClick={autoTitle} className="inline-flex items-center gap-1 normal-case tracking-normal text-brand-700 dark:text-gold-300"><Wand2 className="h-3 w-3" /> Suggest</button></span>}>
                      <Input value={f.title} onChange={(e) => set({ title: e.target.value })} placeholder="e.g. Modern 10 Marla House in DHA Phase 6" />
                    </Field>
                    <Field label={<span className="flex items-center justify-between">Description <button type="button" onClick={autoDescription} className="inline-flex items-center gap-1 normal-case tracking-normal text-brand-700 dark:text-gold-300"><Wand2 className="h-3 w-3" /> Write for me</button></span>}>
                      <Textarea rows={5} value={f.description} onChange={(e) => set({ description: e.target.value })} placeholder="Highlights, finishes, nearby landmarks…" />
                    </Field>
                  </>
                )}
                {step === 1 && (
                  <>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <Field label="City">
                        <Select
                          value={f.city_id}
                          onChange={(e) => {
                            const c = cities.data?.cities.find((x) => x.id === e.target.value);
                            set({ city_id: e.target.value, scheme_id: "", block_zone_area_id: "", latitude: c?.latitude ?? 0, longitude: c?.longitude ?? 0 });
                          }}
                        >
                          <option value="">Select city</option>
                          {cities.data?.cities.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </Select>
                      </Field>
                      <Field label="Scheme / society">
                        <Select value={f.scheme_id} onChange={(e) => set({ scheme_id: e.target.value, block_zone_area_id: "" })} disabled={!schemes.length}>
                          <option value="">—</option>
                          {schemes.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </Select>
                      </Field>
                      <Field label="Block / zone">
                        <Select value={f.block_zone_area_id} onChange={(e) => set({ block_zone_area_id: e.target.value })} disabled={!blocks.length}>
                          <option value="">—</option>
                          {blocks.map((b) => (
                            <option key={b.id} value={b.id}>
                              {b.name}
                            </option>
                          ))}
                        </Select>
                      </Field>
                    </div>
                    <div>
                      <p className="label">Drop a pin {f.latitude ? <span className="normal-case tracking-normal text-brand-700">· {f.latitude.toFixed(5)}, {f.longitude.toFixed(5)}</span> : null}</p>
                      <PortalMap center={city ? [city.latitude, city.longitude] : undefined} zoom={city ? 12 : 5} height={300} follow scrollWheelZoom>
                        <ClickToPlace onPick={(lat, lon) => set({ latitude: lat, longitude: lon })} />
                        {!!f.latitude && <Marker position={[f.latitude, f.longitude]} icon={pin("featured", { pulse: true })} />}
                      </PortalMap>
                      <p className="mt-2 text-xs text-ink-mute">Click the map to place the property precisely — it powers nearby places, GIS scores and the map search.</p>
                    </div>
                  </>
                )}
                {step === 2 && (
                  <>
                    <div>
                      <div className="mb-2 flex justify-between text-sm font-semibold">
                        <span>Plot size</span>
                        <span className="text-brand-700 dark:text-gold-300">
                          {f.marla_area} marla · {(f.marla_area / 20).toFixed(2)} kanal · {Math.round(f.marla_area * MARLA_SQFT).toLocaleString()} sqft
                        </span>
                      </div>
                      <Slider value={f.marla_area} min={1} max={200} step={1} onChange={(v) => set({ marla_area: v })} />
                    </div>
                    {!isLand && (
                      <div className="grid grid-cols-2 gap-4">
                        {(["bedrooms", "bathrooms"] as const).map((k) => (
                          <div key={k}>
                            <p className="label">{k}</p>
                            <div className="flex gap-1.5">
                              {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                                <button key={n} onClick={() => set({ [k]: n } as Partial<typeof f>)} className={cn("h-10 flex-1 rounded-lg text-sm font-semibold ring-1", f[k] === n ? "bg-brand-700 text-white ring-brand-700" : "ring-black/10 dark:ring-white/10")}>
                                  {n}
                                </button>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div>
                      <div className="mb-2 flex justify-between text-sm font-semibold">
                        <span>Asking price</span>
                        <span className="text-brand-700 dark:text-gold-300">{pkrShort(f.price)}</span>
                      </div>
                      <Slider value={f.price} min={1_000_000} max={500_000_000} step={500_000} onChange={(v) => set({ price: v })} />
                      <Input className="mt-3" type="number" value={f.price} onChange={(e) => set({ price: Number(e.target.value) })} />
                      <p className="mt-2 text-xs text-ink-mute">
                        {pkr(Math.round(f.price / f.marla_area))} per marla · {pkr(Math.round(f.price / (f.marla_area * MARLA_SQFT)))} per sqft
                      </p>
                    </div>
                    <Toggle checked={f.featured} onChange={(v) => set({ featured: v })} label={<span className="text-sm font-medium">Feature this listing on the home page</span>} />
                  </>
                )}
                {step === 3 && (
                  <>
                    <p className="text-sm text-ink-mute">Pick images from the seeded media library (real uploads plug into the same images API). The first selected becomes the cover.</p>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {library.map((src) => {
                        const idx = f.images.indexOf(src);
                        return (
                          <button key={src} onClick={() => setF((x) => ({ ...x, images: x.images.includes(src) ? x.images.filter((i) => i !== src) : [...x.images, src] }))} className={cn("relative aspect-[4/3] overflow-hidden rounded-xl ring-2 transition", idx >= 0 ? "ring-gold-400" : "ring-transparent hover:ring-brand-200")}>
                            <img src={src} alt="" className="h-full w-full object-cover" />
                            {idx >= 0 && <span className="absolute end-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-gold-400 text-xs font-bold text-brand-950">{idx + 1}</span>}
                            {idx === 0 && <span className="chip absolute bottom-2 start-2 bg-white/90 text-[10px] text-brand-800">Cover</span>}
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}
                {step === 4 && (
                  <div className="space-y-4">
                    <div className="overflow-hidden rounded-2xl border border-black/5 dark:border-white/10">
                      {f.images[0] && <img src={f.images[0]} alt="" className="aspect-[16/7] w-full object-cover" />}
                      <div className="p-5">
                        <div className="flex flex-wrap gap-2">
                          <Badge tone="green">{titleCase(f.use_type)}</Badge>
                          <Badge tone="gray">{titleCase(f.category)}</Badge>
                          {f.featured && <Badge tone="gold">Featured</Badge>}
                        </div>
                        <p className="mt-3 font-display text-xl font-bold">{f.title}</p>
                        <p className="text-sm text-ink-mute">{[blocks.find((b) => b.id === f.block_zone_area_id)?.name, schemes.find((s) => s.id === f.scheme_id)?.name, city?.name].filter(Boolean).join(", ")}</p>
                        <p className="mt-2 font-display text-2xl font-bold text-brand-700 dark:text-gold-300">{pkrShort(f.price)}</p>
                        <p className="mt-3 text-sm text-ink-soft dark:text-slate-300">{f.description}</p>
                      </div>
                    </div>
                    <p className="text-xs text-ink-mute">Publishing creates the listing via the REST API (and the same engine the MCP tools use), so it’s instantly available to search, maps and agents.</p>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          </CardBody>
          <div className="flex justify-between border-t border-black/5 px-5 py-4 dark:border-white/10">
            <Button variant="ghost" disabled={step === 0} onClick={() => setStep((s) => s - 1)} icon={<ArrowLeft className="h-4 w-4 rtl:rotate-180" />}>
              Back
            </Button>
            {step < STEPS.length - 1 ? (
              <Button disabled={!canNext} onClick={() => setStep((s) => s + 1)}>
                Continue <ArrowRight className="h-4 w-4 rtl:rotate-180" />
              </Button>
            ) : (
              <Button variant="gold" loading={busy} onClick={publish}>
                Publish listing
              </Button>
            )}
          </div>
        </Card>
        <aside className="space-y-4">
          <Card>
            <CardBody className="space-y-3 text-sm">
              <p className="flex items-center gap-2 font-display font-semibold">
                <Sparkles className="h-4 w-4 text-gold-600" /> After you publish
              </p>
              {["Location score from nearby schools, hospitals & mosques", "Comparable-sales pricing range (CMA agent)", "Listing kit: headline, social posts & e-mail", "Buyer intent scoring on every enquiry"].map((t) => (
                <p key={t} className="flex items-start gap-2 text-ink-soft dark:text-slate-300">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" /> {t}
                </p>
              ))}
            </CardBody>
          </Card>
          <div className="rounded-2xl bg-brand-50 p-4 text-xs text-brand-800 dark:bg-white/5 dark:text-brand-200">Listing as <b>{user?.name ?? user?.email}</b> ({titleCase(user?.role)})</div>
        </aside>
      </div>
    </div>
  );
}
