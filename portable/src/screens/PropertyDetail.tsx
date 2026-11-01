import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Bath, BedDouble, Bot, Building2, CalendarDays, KeyRound, Layers, MapPin, Navigation, PhoneCall, Ruler, Share2, Sparkles, Tag } from "lucide-react";
import { Share } from "@capacitor/share";
import { toast } from "sonner";
import type { MapView, NearbyList, Property } from "@/types";
import { useApi } from "@/hooks/useApi";
import { apiBase, post } from "@/lib/api";
import { area, date, num, pkr, pkrShort, titleCase } from "@/lib/format";
import { gallery, libraryPhoto } from "@/lib/images";
import { isNative } from "@/lib/platform";
import { useAuth } from "@/store/auth";
import { Badge, Button, EmptyState, Field, Input, Select, Sheet, Skeleton, statusTone, Textarea, TopBar } from "@/components/ui";
import { FavoriteButton, locationOf } from "@/components/PropertyCard";
import { AdSlot } from "@/components/Ads";
import { MapCard } from "@/components/MapCard";

/** GET /masterplans/view — a close-up of the master plan around the listing. */
interface PlanView {
  plan: string;
  snapshot_url: string;
  on_the_plan?: { features?: Record<string, string[]>; plot_sizes?: { size: string; count: number }[]; note?: string };
}

export default function PropertyDetail() {
  const { id } = useParams();
  const q = useApi<Property>(id ? `/properties/${id}` : null);
  const near = useApi<NearbyList>(id ? `/properties/${id}/nearby` : null);
  // Both 404 / 422 when the listing has no location or isn't on a DHA master plan; the sections are then left out.
  const mapView = useApi<MapView>(id ? "/places/map" : null, id ? { listing_id: id } : undefined, { retry: false });
  const plan = useApi<PlanView>(id ? "/masterplans/view" : null, id ? { listing_id: id, radius_m: 250 } : undefined, { retry: false, staleTime: 10 * 60_000 });
  const [slide, setSlide] = useState(0);
  // ?enquire=1 (the assistant's "Request a call" button) opens the call request straight away.
  const [params] = useSearchParams();
  const [enquire, setEnquire] = useState(params.get("enquire") === "1");
  const [applyRent, setApplyRent] = useState(false);
  const p = q.data;

  const share = async () => {
    if (!p) return;
    const text = `${p.title} — ${pkrShort(p.price)} · ${locationOf(p)} (Watan-e-Pak)`;
    try {
      if (isNative) await Share.share({ title: p.title, text, dialogTitle: "Share listing" });
      else if (navigator.share) await navigator.share({ title: p.title, text });
      else {
        await navigator.clipboard.writeText(text);
        toast.success("Listing details copied");
      }
    } catch {
      /* user cancelled */
    }
  };

  if (q.isLoading)
    return (
      <div>
        <TopBar back title=" " />
        <div className="screen space-y-4 pt-4">
          <Skeleton className="aspect-[4/3] w-full" />
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      </div>
    );
  if (!p)
    return (
      <div>
        <TopBar back title="Listing" />
        <EmptyState icon={<Building2 className="h-7 w-7" />} title="Listing not found">
          {q.error?.message ?? "It may have been sold or removed."}
        </EmptyState>
      </div>
    );

  const imgs = gallery(p);
  const facts: [typeof Ruler, string, string][] = [
    [Tag, "Type", `${titleCase(p.category)} · ${titleCase(p.use_type)}`],
    [Ruler, "Size", `${area(p)}${p.total_area ? ` (${num(p.total_area)} sqft)` : ""}`],
    ...(p.bedrooms ? ([[BedDouble, "Bedrooms", String(p.bedrooms)]] as [typeof Ruler, string, string][]) : []),
    ...(p.bathrooms ? ([[Bath, "Bathrooms", String(p.bathrooms)]] as [typeof Ruler, string, string][]) : []),
    ...(p.floors ? ([[Layers, "Floors", String(p.floors)]] as [typeof Ruler, string, string][]) : []),
    ...(p.listing_purpose !== "rent" && p.price_per_sqft ? ([[Sparkles, "Price / sqft", pkr(p.price_per_sqft)]] as [typeof Ruler, string, string][]) : []),
    ...(p.created_at ? ([[CalendarDays, "Listed", date(p.created_at)]] as [typeof Ruler, string, string][]) : []),
  ];
  const askAi = `/assistant?q=${encodeURIComponent(p.listing_purpose === "rent" ? `Is ${pkrShort(p.price)} ${p.rent_frequency === "weekly" ? "per week" : "per month"} fair rent for "${p.title}" in ${locationOf(p)}? Explain the lease terms and what I should check before applying.` : `Is ${pkrShort(p.price)} a fair price for "${p.title}" (${area(p)} ${p.category}) in ${locationOf(p)}? What should I check before buying?`)}`;

  return (
    <div>
      <TopBar
        back
        title={p.title}
        actions={
          <>
            <button className="btn btn-ghost btn-icon" onClick={() => void share()} aria-label="Share">
              <Share2 className="h-5 w-5" />
            </button>
            <FavoriteButton id={p.id} className="shadow-none" />
          </>
        }
      />
      <div className="screen pt-4">
        {/* gallery */}
        <div className="relative overflow-hidden rounded-2xl">
          <div
            className="no-scrollbar flex snap-x snap-mandatory overflow-x-auto"
            onScroll={(e) => {
              const el = e.currentTarget;
              setSlide(Math.round(el.scrollLeft / el.clientWidth));
            }}
          >
            {imgs.map((src, i) => (
              <img key={i} src={src} alt={`${p.title} ${i + 1}`} className="aspect-[4/3] w-full shrink-0 snap-center object-cover sm:aspect-[16/9]" loading={i ? "lazy" : "eager"} />
            ))}
          </div>
          <div className="pointer-events-none absolute start-3 top-3 flex gap-1.5">
            {p.featured && (
              <span className="chip bg-gold-gradient text-brand-950 shadow">
                <Sparkles className="h-3 w-3" /> Featured
              </span>
            )}
            <Badge tone={statusTone(p.status)} className="bg-white/90 dark:bg-black/50">
              {titleCase(p.status)}
            </Badge>
          </div>
          <div className="pointer-events-none absolute bottom-3 inset-x-0 flex justify-center gap-1.5">
            {imgs.map((_, i) => (
              <span key={i} className={`h-1.5 rounded-full transition-all ${i === slide ? "w-5 bg-white" : "w-1.5 bg-white/60"}`} />
            ))}
          </div>
        </div>
        {(() => {
          const lib = imgs[slide] ? libraryPhoto(imgs[slide]!) : undefined;
          return lib ? (
            <p className="mt-1.5 text-[11px] leading-snug text-ink-mute">
              <b className="text-ink-soft dark:text-slate-300">Representative photo</b> — the owner hasn’t added photos yet.{" "}
              <a href={lib.link} target="_blank" rel="noreferrer" className="underline">
                Photo: {lib.credit}
              </a>
            </p>
          ) : null;
        })()}

        {/* headline */}
        <div className="mt-5">
          <p className="font-display text-3xl font-bold text-brand-700 dark:text-brand-300">{pkrShort(p.price)}{p.listing_purpose === "rent" ? (p.rent_frequency === "weekly" ? "/wk" : "/mo") : ""}</p>
          <p className="text-xs text-ink-mute">{pkr(p.price)}{p.listing_purpose === "rent" ? ` per ${p.rent_frequency === "weekly" ? "week" : "month"}` : ""}</p>
          {p.listing_purpose === "rent" && <div className="mt-3 rounded-xl bg-brand-50 p-3 text-sm dark:bg-white/5"><p>Security deposit: {p.security_deposit ? pkrShort(p.security_deposit) : "To be confirmed"}</p><p>Advance: {p.advance_months ?? 0} months · Lease: {p.lease_term_months || "Flexible"} months</p><p>Furnishing: {titleCase(p.furnishing_status ?? "not specified")}</p></div>}
          <h1 className="mt-2 font-display text-xl font-bold text-brand-900 dark:text-white">{p.title}</h1>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-mute dark:text-slate-400">
            <MapPin className="h-4 w-4 shrink-0 text-brand-600" /> {locationOf(p)}
          </p>
        </div>

        {/* facts */}
        <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {facts.map(([Icon, label, value]) => (
            <div key={label} className="card flex items-center gap-3 p-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-white/10 dark:text-brand-200">
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-[11px] font-semibold uppercase tracking-wider text-ink-mute">{label}</span>
                <span className="block text-sm font-semibold leading-snug">{value}</span>
              </span>
            </div>
          ))}
        </div>

        {p.description && (
          <section className="mt-6">
            <h2 className="section-title text-lg">About this property</h2>
            <p className="mt-2 whitespace-pre-line leading-relaxed text-ink-soft dark:text-slate-300">{p.description}</p>
          </section>
        )}

        {!!p.amenities?.length && (
          <section className="mt-6">
            <h2 className="section-title text-lg">Amenities</h2>
            <div className="mt-2 flex flex-wrap gap-2">
              {p.amenities.map((a) => (
                <Badge key={a} tone="gray">
                  {titleCase(a)}
                </Badge>
              ))}
            </div>
          </section>
        )}

        {mapView.data && (
          <section className="mt-6">
            <h2 className="section-title text-lg">On the map</h2>
            <MapCard view={mapView.data} className="mt-2" height={280} />
          </section>
        )}

        {plan.data && (
          <section className="mt-6">
            <h2 className="section-title text-lg">On the {plan.data.plan} master plan</h2>
            <a href={`${apiBase()}${plan.data.snapshot_url}`} target="_blank" rel="noreferrer" className="mt-2 block overflow-hidden rounded-2xl">
              <img src={`${apiBase()}${plan.data.snapshot_url}`} alt={`${plan.data.plan} master plan around this listing`} className="max-h-72 w-full object-cover" loading="lazy" />
            </a>
            {!!plan.data.on_the_plan?.plot_sizes?.length && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {plan.data.on_the_plan.plot_sizes.map((s) => (
                  <Badge key={s.size} tone="gray">
                    {s.size} × {s.count}
                  </Badge>
                ))}
              </div>
            )}
            {Object.entries(plan.data.on_the_plan?.features ?? {})
              .slice(0, 4)
              .map(([kind, names]) => (
                <p key={kind} className="mt-1.5 text-sm">
                  <span className="font-semibold capitalize">{kind}:</span> <span className="text-ink-mute dark:text-slate-400">{names.join(", ")}</span>
                </p>
              ))}
            {plan.data.on_the_plan?.note && <p className="mt-1.5 text-xs text-ink-mute">{plan.data.on_the_plan.note}</p>}
          </section>
        )}

        {!!near.data?.nearby.length && (
          <section className="mt-6">
            <h2 className="section-title text-lg">Nearby</h2>
            <ul className="mt-2 divide-y divide-black/5 rounded-2xl bg-brand-50/60 px-4 dark:divide-white/10 dark:bg-white/5">
              {near.data.nearby.map((n) => (
                <li key={n.category} className="flex items-center gap-3 py-2.5">
                  <MapPin className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{n.name}</span>
                    <span className="block text-xs text-ink-mute">{n.kind}</span>
                  </span>
                  <span className="shrink-0 text-end text-xs text-ink-mute">
                    <span className="block font-semibold text-ink dark:text-white">{n.distance_km < 1 ? `${Math.round(n.distance_km * 1000)} m` : `${n.distance_km} km`}</span>
                    ~{n.walk_minutes} min walk
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <AdSlot slot="sidebar" placement="detail" className="mt-6" index={p.title.length} />

        <Link to={askAi} className="mt-6 flex items-center gap-3 rounded-2xl bg-brand-gradient p-4 text-white shadow-soft">
          <Bot className="h-6 w-6 shrink-0 text-gold-200" />
          <span className="min-w-0 flex-1">
            <span className="block font-semibold">Ask AI about this property</span>
            <span className="block text-xs text-white/75">{p.listing_purpose === "rent" ? "Rent comparison, lease terms, and application checklist" : "Fair price, area insights, what to check before buying"}</span>
          </span>
        </Link>

        {p.latitude && p.longitude ? (
          <a href={`https://www.google.com/maps/search/?api=1&query=${p.latitude},${p.longitude}`} target="_blank" rel="noreferrer" className="btn btn-outline mt-3 w-full">
            <Navigation className="h-4 w-4" /> Open in Maps
          </a>
        ) : null}
      </div>

      {/* sticky action bar (sits above the tab bar on phones) */}
      <div className="fixed inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-30 border-t border-black/5 bg-white/95 backdrop-blur md:bottom-0 md:start-64 dark:border-white/10 dark:bg-[#0b1a12]/95">
        <div className="screen flex items-center gap-3 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-lg font-bold text-brand-800 dark:text-white">{pkrShort(p.price)}</p>
            <p className="truncate text-xs text-ink-mute">{area(p)} · {titleCase(p.category)}</p>
          </div>
          {p.listing_purpose === "rent" ? <Button variant="gold" icon={<KeyRound className="h-4 w-4" />} onClick={() => setApplyRent(true)} disabled={p.status !== "active"}>{p.status === "active" ? "Apply to rent" : titleCase(p.status)}</Button> : <Button variant="gold" icon={<PhoneCall className="h-4 w-4" />} onClick={() => setEnquire(true)} disabled={p.status !== "active"}>{p.status === "active" ? "Request a call" : titleCase(p.status)}</Button>}
        </div>
      </div>
      <div className="h-20" />

      <EnquirySheet p={p} open={enquire} onClose={() => setEnquire(false)} />
      {p.listing_purpose === "rent" && <TenantApplicationSheet p={p} open={applyRent} onClose={() => setApplyRent(false)} />}
    </div>
  );
}

/** Creates a CRM lead for the listing's agent (POST /crm/leads). */
function EnquirySheet({ p, open, onClose }: { p: Property; open: boolean; onClose: () => void }) {
  const user = useAuth((s) => s.user);
  const [f, setF] = useState({ name: user?.name ?? "", phone: user?.mobile ?? "", email: user?.email ?? "", notes: `I'm interested in "${p.title}". Please call me.` });
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      await post("/crm/leads", {
        name: f.name,
        phone: f.phone || undefined,
        email: f.email || undefined,
        source: "mobile_app",
        interest_use_type: p.use_type,
        interest_category: p.category,
        budget_max: p.price,
        city_id: p.city_id ?? undefined,
        scheme_id: p.scheme_id ?? undefined,
        assigned_agent_id: p.agent_id ?? undefined,
        notes: `${f.notes}\n\nListing: ${p.title} (${p.id})`,
      });
      toast.success("Request sent — the owner / agent will contact you soon");
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet open={open} onClose={onClose} title="Request a call">
      <div className="space-y-4">
        <Field label="Your name">
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Mobile">
            <Input type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} autoComplete="tel" />
          </Field>
          <Field label="E-mail">
            <Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" />
          </Field>
        </div>
        <Field label="Message">
          <Textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
        </Field>
        <Button className="w-full" size="lg" loading={busy} disabled={!f.name.trim() || (!f.phone.trim() && !f.email.trim())} onClick={() => void send()}>
          Send request
        </Button>
      </div>
    </Sheet>
  );
}

function TenantApplicationSheet({ p, open, onClose }: { p: Property; open: boolean; onClose: () => void }) {
  const user = useAuth((s) => s.user);
  const [f, setF] = useState({ applicant: user?.name ?? "", email: user?.email ?? "", phone: user?.mobile ?? "", monthly_income: "", employment: "salaried", references_count: "2", occupants: "1", move_in_days: "15", pets: false });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await post(`/properties/${p.id}/rental-applications`, { ...f, monthly_income: Number(f.monthly_income), references_count: Number(f.references_count), occupants: Number(f.occupants), move_in_days: Number(f.move_in_days) });
      toast.success("Application sent — the rental team will contact you");
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return <Sheet open={open} onClose={onClose} title="Apply to rent">
    <div className="space-y-4">
      <p className="text-sm text-ink-mute">{p.title} · {pkrShort(p.price)} / {p.rent_frequency === "weekly" ? "week" : "month"}</p>
      <Field label="Full name"><Input value={f.applicant} onChange={(e) => setF({ ...f, applicant: e.target.value })} autoComplete="name" /></Field>
      <Field label="Monthly household income (PKR)"><Input inputMode="numeric" value={f.monthly_income} onChange={(e) => setF({ ...f, monthly_income: e.target.value.replace(/\D/g, "") })} /></Field>
      <div className="grid grid-cols-2 gap-3"><Field label="Email"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" /></Field><Field label="Mobile"><Input type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} autoComplete="tel" /></Field></div>
      <Field label="Employment"><Select value={f.employment} onChange={(e) => setF({ ...f, employment: e.target.value })}>{["salaried", "business", "self_employed", "retired", "student"].map((v) => <option key={v} value={v}>{titleCase(v)}</option>)}</Select></Field>
      <div className="grid grid-cols-2 gap-3"><Field label="References"><Input inputMode="numeric" value={f.references_count} onChange={(e) => setF({ ...f, references_count: e.target.value.replace(/\D/g, "") })} /></Field><Field label="Household occupants"><Input inputMode="numeric" value={f.occupants} onChange={(e) => setF({ ...f, occupants: e.target.value.replace(/\D/g, "") })} /></Field><Field label="Move-in within (days)"><Input inputMode="numeric" value={f.move_in_days} onChange={(e) => setF({ ...f, move_in_days: e.target.value.replace(/\D/g, "") })} /></Field><label className="flex items-center gap-2 self-end pb-3 text-sm"><input type="checkbox" checked={f.pets} onChange={(e) => setF({ ...f, pets: e.target.checked })} /> Has pets</label></div>
      <p className="text-xs text-ink-mute">Your contact details are shared with the property team to follow up. Automated screening is preliminary and does not make a tenancy decision.</p>
      <Button className="w-full" size="lg" loading={busy} disabled={!f.applicant.trim() || (!f.email.trim() && !f.phone.trim()) || Number(f.monthly_income) <= 0} onClick={() => void submit()}>Submit application</Button>
    </div>
  </Sheet>;
}
