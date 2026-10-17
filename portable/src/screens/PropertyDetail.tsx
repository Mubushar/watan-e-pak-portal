import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Bath, BedDouble, Bot, Building2, CalendarDays, Layers, MapPin, Navigation, PhoneCall, Ruler, Share2, Sparkles, Tag } from "lucide-react";
import { Share } from "@capacitor/share";
import { toast } from "sonner";
import type { Property } from "@/types";
import { useApi } from "@/hooks/useApi";
import { post } from "@/lib/api";
import { area, date, num, pkr, pkrShort, titleCase } from "@/lib/format";
import { gallery } from "@/lib/images";
import { isNative } from "@/lib/platform";
import { useAuth } from "@/store/auth";
import { Badge, Button, EmptyState, Field, Input, Sheet, Skeleton, statusTone, Textarea, TopBar } from "@/components/ui";
import { FavoriteButton, locationOf } from "@/components/PropertyCard";

export default function PropertyDetail() {
  const { id } = useParams();
  const q = useApi<Property>(id ? `/properties/${id}` : null);
  const [slide, setSlide] = useState(0);
  // ?enquire=1 (the assistant's "Request a call" button) opens the call request straight away.
  const [params] = useSearchParams();
  const [enquire, setEnquire] = useState(params.get("enquire") === "1");
  const p = q.data;

  const share = async () => {
    if (!p) return;
    const text = `${p.title} — ${pkrShort(p.price)} · ${locationOf(p)} (Arz-e-Pak)`;
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
    ...(p.price_per_sqft ? ([[Sparkles, "Price / sqft", pkr(p.price_per_sqft)]] as [typeof Ruler, string, string][]) : []),
    ...(p.created_at ? ([[CalendarDays, "Listed", date(p.created_at)]] as [typeof Ruler, string, string][]) : []),
  ];
  const askAi = `/assistant?q=${encodeURIComponent(`Is ${pkrShort(p.price)} a fair price for "${p.title}" (${area(p)} ${p.category}) in ${locationOf(p)}? What should I check before buying?`)}`;

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

        {/* headline */}
        <div className="mt-5">
          <p className="font-display text-3xl font-bold text-brand-700 dark:text-brand-300">{pkrShort(p.price)}</p>
          <p className="text-xs text-ink-mute">{pkr(p.price)}</p>
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

        <Link to={askAi} className="mt-6 flex items-center gap-3 rounded-2xl bg-brand-gradient p-4 text-white shadow-soft">
          <Bot className="h-6 w-6 shrink-0 text-gold-200" />
          <span className="min-w-0 flex-1">
            <span className="block font-semibold">Ask AI about this property</span>
            <span className="block text-xs text-white/75">Fair price, area insights, what to check before buying</span>
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
          <Button variant="gold" icon={<PhoneCall className="h-4 w-4" />} onClick={() => setEnquire(true)} disabled={p.status !== "active"}>
            {p.status === "active" ? "Request a call" : titleCase(p.status)}
          </Button>
        </div>
      </div>
      <div className="h-20" />

      <EnquirySheet p={p} open={enquire} onClose={() => setEnquire(false)} />
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
