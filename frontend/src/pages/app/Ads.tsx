import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Eye, ExternalLink, FileBarChart, Megaphone, MousePointerClick, Pencil, Percent, Plus, Trash2, Trophy, Wallet } from "lucide-react";
import type { Ad } from "@/types";
import { useApi, useMutate } from "@/hooks/useApi";
import { apiUrl, del, post, put } from "@/lib/api";
import { compact, date, num, pct, pkrShort, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import { AdCreative } from "@/components/ads/AdSlot";
import { Badge, Button, Card, CardBody, CardHeader, DataTable, Field, Input, Modal, PageHeader, Progress, QueryState, Segmented, Select, Skeleton, StatCard, StatusBadge, Textarea, type Column } from "@/components/ui";
import { Bars, Donut, Legendish } from "@/components/ui/charts";
import { ok } from "@/components/collab/kit";

interface AdRow extends Ad {
  keywords?: string[];
  tags?: string[];
  remaining_budget?: number;
  valid_from?: string | null;
  valid_until?: string | null;
  created_at?: string;
  weight?: number;
  lang?: string | null;
}
interface PerfBucket {
  impressions: number;
  clicks: number;
  spend: number;
  ads: number;
  ctr: number;
}
interface Performance {
  totals: { ads: number; live: number; impressions: number; clicks: number; ctr: number; spend: number; budget: number; remaining_budget: number };
  by_slot: Record<string, PerfBucket>;
  by_category: Record<string, PerfBucket>;
  top_performers: { id: string; title: string; category: string; slot: string; impressions: number; clicks: number; ctr: number }[];
}

const STATUSES = ["active", "paused", "draft", "expired"];
const SLOT_LAYOUT: Record<string, "banner" | "card" | "tile" | "strip"> = { hero: "banner", banner: "banner", sidebar: "tile", infeed: "card", footer: "strip", newsletter: "banner" };

export default function Ads() {
  const [status, setStatus] = useState("");
  const [slot, setSlot] = useState("");
  const ads = useApi<{ count: number; advertisements: AdRow[] }>("/ads", { status, slot, limit: 500 });
  const perf = useApi<Performance>("/ads/performance");
  const slots = useApi<{ slots: Record<string, string> }>("/ads/slots", undefined, { staleTime: 30 * 60_000 });
  const cats = useApi<{ categories: Record<string, string> }>("/ads/categories", undefined, { staleTime: 30 * 60_000 });
  const [editing, setEditing] = useState<AdRow | "new" | null>(null);
  const [deleting, setDeleting] = useState<AdRow | null>(null);
  const [view, setView] = useState<"slot" | "category">("slot");

  const t = perf.data?.totals;
  const breakdown = useMemo(() => {
    const src = view === "slot" ? perf.data?.by_slot : perf.data?.by_category;
    const labels = view === "slot" ? slots.data?.slots : cats.data?.categories;
    return Object.entries(src ?? {}).map(([k, v]) => ({ key: k, name: view === "slot" ? titleCase(k) : (labels?.[k] ?? titleCase(k)).split(/[,&]/)[0]!.trim(), impressions: v.impressions, clicks: v.clicks, spend: v.spend, ctr: v.ctr * 100 }));
  }, [perf.data, view, slots.data, cats.data]);

  const remove = useMutate((id: string) => ok(del(`/ads/${id}`)), { invalidate: ["/ads"], success: "Advertisement deleted", onSuccess: () => setDeleting(null) });

  const cols: Column<AdRow>[] = [
    {
      key: "title",
      header: "Creative",
      render: (a) => (
        <div className="min-w-[220px]">
          <p className="font-semibold text-ink dark:text-white">{a.title}</p>
          <p className="line-clamp-1 text-xs text-ink-mute">
            {a.advertiser} · “{a.headline}”
          </p>
          {a.sample && <Badge tone="gray" className="mt-1">Sample</Badge>}
        </div>
      ),
    },
    { key: "status", header: "Status", render: (a) => <StatusBadge status={a.live && a.status === "active" ? "live" : a.status} /> },
    { key: "slot", header: "Slot", render: (a) => <Badge tone="blue">{a.slot_label ?? titleCase(a.slot)}</Badge> },
    { key: "category", header: "Category", render: (a) => <span className="text-xs">{a.category_label ?? titleCase(a.category)}</span> },
    { key: "impressions", header: "Impr.", align: "right", render: (a) => compact(a.impressions ?? 0) },
    { key: "clicks", header: "Clicks", align: "right", render: (a) => num(a.clicks ?? 0) },
    {
      key: "ctr",
      header: "CTR",
      align: "right",
      render: (a) => <span className={cn("font-semibold", (a.ctr ?? 0) >= 0.025 ? "text-emerald-600" : (a.ctr ?? 0) < 0.018 ? "text-red-600" : "")}>{pct(a.ctr ?? 0, 2)}</span>,
    },
    {
      key: "spend",
      header: "Spend / budget",
      value: (a) => a.spend ?? 0,
      render: (a) => (
        <div className="min-w-[130px]">
          <p className="text-xs tabular-nums">
            {pkrShort(a.spend ?? 0, false)} <span className="text-ink-mute">/ {a.budget ? pkrShort(a.budget, false) : "∞"}</span>
          </p>
          {!!a.budget && <Progress value={a.spend ?? 0} max={a.budget} tone={(a.spend ?? 0) / a.budget > 0.9 ? "red" : "gold"} className="mt-1 h-1.5" />}
          {a.pricing && a.pricing !== "flat" && (
            <p className="mt-0.5 text-[10px] text-ink-mute">
              {a.pricing.toUpperCase()} · Rs {(a.rate ?? 0).toLocaleString("en-PK")}
              {a.pricing === "cpc" ? "/click" : "/1k"}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      sortable: false,
      render: (a) => (
        <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          <button className="btn btn-ghost btn-icon h-8 w-8" title="Edit" onClick={() => setEditing(a)}>
            <Pencil className="h-4 w-4" />
          </button>
          <button className="btn btn-ghost btn-icon h-8 w-8 text-red-600" title="Delete" onClick={() => setDeleting(a)}>
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Advertising"
        subtitle="The ad book, slot performance and live creative previews."
        crumbs={[{ label: "Dashboard", to: "/app" }, { label: "Advertising" }]}
        actions={
          <>
            <a href={apiUrl("/ads/report")} target="_blank" rel="noreferrer" className="btn btn-outline">
              <FileBarChart className="h-4 w-4" /> Report
            </a>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>
              New creative
            </Button>
          </>
        }
      />

      {perf.isLoading ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : t ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatCard label="Creatives" value={t.ads} icon={<Megaphone className="h-5 w-5" />} hint={`${t.live} live`} />
          <StatCard label="Impressions" value={compact(t.impressions)} icon={<Eye className="h-5 w-5" />} tone="blue" />
          <StatCard label="Clicks" value={compact(t.clicks)} icon={<MousePointerClick className="h-5 w-5" />} tone="purple" />
          <StatCard label="CTR" value={pct(t.ctr, 2)} icon={<Percent className="h-5 w-5" />} tone="gold" hint="book average" />
          <StatCard label="Spend" value={pkrShort(t.spend)} icon={<Wallet className="h-5 w-5" />} hint={`${pkrShort(t.remaining_budget)} left of ${pkrShort(t.budget)}`} className="col-span-2 lg:col-span-1" />
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Delivery"
            subtitle="Impressions & clicks"
            icon={<FileBarChart className="h-5 w-5" />}
            action={<Segmented size="sm" value={view} onChange={setView} options={[{ value: "slot", label: "By slot" }, { value: "category", label: "By category" }]} />}
          />
          <CardBody>
            <QueryState q={perf} skeleton={<Skeleton className="h-72" />}>
              {() => (
                <Bars
                  data={breakdown}
                  x="name"
                  height={view === "slot" ? 290 : Math.max(290, breakdown.length * 34)}
                  horizontal={view === "category"}
                  series={[
                    { key: "impressions", label: "Impressions", color: "#146f45" },
                    { key: "clicks", label: "Clicks", color: "#c99a22" },
                  ]}
                />
              )}
            </QueryState>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Spend share" subtitle="By slot" icon={<Wallet className="h-5 w-5" />} />
          <CardBody>
            {perf.data ? (
              <>
                <Donut
                  data={Object.entries(perf.data.by_slot).map(([k, v]) => ({ name: titleCase(k), value: v.spend }))}
                  height={200}
                  format={(v) => pkrShort(v)}
                  center={
                    <>
                      <span className="font-display text-xl font-bold">{pkrShort(perf.data.totals.spend, false)}</span>
                      <span className="text-[10px] uppercase text-ink-mute">PKR spent</span>
                    </>
                  }
                />
                <div className="mt-3">
                  <Legendish data={Object.entries(perf.data.by_slot).map(([k, v]) => ({ name: titleCase(k), value: v.ads }))} />
                </div>
                <p className="label mt-5 flex items-center gap-1.5">
                  <Trophy className="h-3.5 w-3.5 text-gold-500" /> Top performers
                </p>
                <ul className="space-y-2">
                  {perf.data.top_performers.slice(0, 4).map((a, i) => (
                    <li key={a.id} className="flex items-center gap-2 text-sm">
                      <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold", i === 0 ? "bg-gold-gradient text-brand-950" : "bg-black/5 dark:bg-white/10")}>{i + 1}</span>
                      <span className="min-w-0 flex-1 truncate">{a.title}</span>
                      <Badge tone="green">{pct(a.ctr, 2)}</Badge>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <Skeleton className="h-72" />
            )}
          </CardBody>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <CardHeader title="Ad book" subtitle={ads.data ? `${ads.data.count} creative(s)` : undefined} icon={<Megaphone className="h-5 w-5" />} />
        <QueryState q={ads} skeleton={<Skeleton className="m-5 h-72" />}>
          {(d) => (
            <DataTable
              rows={d.advertisements}
              columns={cols}
              search
              pageSize={12}
              onRowClick={(a) => setEditing(a)}
              toolbar={
                <>
                  <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-auto py-2 text-xs">
                    <option value="">All statuses</option>
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {titleCase(s)}
                      </option>
                    ))}
                  </Select>
                  <Select value={slot} onChange={(e) => setSlot(e.target.value)} className="w-auto py-2 text-xs">
                    <option value="">All slots</option>
                    {Object.entries(slots.data?.slots ?? {}).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </Select>
                  <a href={apiUrl("/ads/preview", { slot: slot || "infeed" })} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm">
                    <ExternalLink className="h-3.5 w-3.5" /> Preview slot
                  </a>
                </>
              }
            />
          )}
        </QueryState>
      </Card>

      {editing && <AdEditor ad={editing === "new" ? null : editing} slots={slots.data?.slots ?? {}} cats={cats.data?.categories ?? {}} onClose={() => setEditing(null)} />}
      <Modal
        open={!!deleting}
        onClose={() => setDeleting(null)}
        size="sm"
        title="Delete creative?"
        subtitle={deleting?.title}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => deleting && remove.mutate(deleting.id)}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-mute">The creative and its delivery statistics are removed from the ad book. This cannot be undone.</p>
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------- editor
function AdEditor({ ad, slots, cats, onClose }: { ad: AdRow | null; slots: Record<string, string>; cats: Record<string, string>; onClose: () => void }) {
  const [f, setF] = useState({
    title: ad?.title ?? "",
    headline: ad?.headline ?? "",
    advertiser: ad?.advertiser ?? "",
    body: ad?.body ?? "",
    category: ad?.category ?? "services",
    slot: ad?.slot ?? "infeed",
    cta_label: ad?.cta_label ?? "Learn more",
    cta_url: ad?.cta_url ?? "",
    phone: ad?.phone ?? "",
    price_text: ad?.price_text ?? "",
    offer: ad?.offer ?? "",
    keywords: (ad?.keywords ?? []).join(", "),
    priority: String(ad?.priority ?? 100),
    status: ad?.status ?? "active",
    budget: String(ad?.budget ?? 0),
    pricing: ad?.pricing ?? "flat",
    rate: String(ad?.rate ?? 0),
    valid_from: ad?.valid_from?.slice(0, 10) ?? "",
    valid_until: ad?.valid_until?.slice(0, 10) ?? "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }));
  const payload = () => ({
    title: f.title,
    headline: f.headline,
    advertiser: f.advertiser,
    body: f.body || null,
    category: f.category,
    slot: f.slot,
    cta_label: f.cta_label || null,
    cta_url: f.cta_url || null,
    phone: f.phone || null,
    price_text: f.price_text || null,
    offer: f.offer || null,
    keywords: f.keywords
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    priority: Number(f.priority) || 100,
    status: f.status,
    budget: Number(f.budget) || 0,
    pricing: f.pricing,
    rate: f.pricing === "flat" ? 0 : Number(f.rate) || 0,
    valid_from: f.valid_from || null,
    valid_until: f.valid_until || null,
  });
  const save = useMutate(() => ok(ad ? put(`/ads/${ad.id}`, payload()) : post("/ads", payload())), {
    invalidate: ["/ads"],
    success: ad ? "Creative updated" : "Creative created",
    onSuccess: onClose,
  });
  const preview: Ad = {
    id: `preview-${ad?.id ?? "new"}`,
    title: f.title,
    headline: f.headline || "Your headline goes here",
    body: f.body || "A short, benefit-led description of the offer.",
    advertiser: f.advertiser || "Advertiser",
    category: f.category,
    slot: f.slot,
    cta_label: f.cta_label || "Learn more",
    cta_url: undefined,
    phone: f.phone || null,
    price_text: f.price_text || null,
    offer: f.offer || null,
  };
  const layout = SLOT_LAYOUT[f.slot] ?? "card";
  const valid = f.title.trim() && f.headline.trim();
  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={ad ? "Edit creative" : "New creative"}
      subtitle={ad ? `${ad.id} · created ${date(ad.created_at)}` : "Preview updates live as you type."}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} disabled={!valid} onClick={() => save.mutate()}>
            {ad ? "Save changes" : "Create creative"}
          </Button>
        </>
      }
    >
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="grid content-start gap-4 sm:grid-cols-2">
          <Field label="Internal title" className="sm:col-span-2">
            <Input value={f.title} onChange={set("title")} autoFocus />
          </Field>
          <Field label="Headline" className="sm:col-span-2" hint={`${f.headline.length}/70`}>
            <Input value={f.headline} onChange={set("headline")} maxLength={90} />
          </Field>
          <Field label="Body" className="sm:col-span-2">
            <Textarea rows={3} value={f.body} onChange={set("body")} />
          </Field>
          <Field label="Advertiser">
            <Input value={f.advertiser} onChange={set("advertiser")} />
          </Field>
          <Field label="Status">
            <Select value={f.status} onChange={set("status")} options={STATUSES.map((s) => ({ value: s, label: titleCase(s) }))} />
          </Field>
          <Field label="Slot">
            <Select value={f.slot} onChange={set("slot")}>
              {Object.entries(slots).length ? Object.entries(slots).map(([k, v]) => <option key={k} value={k}>{v}</option>) : <option value={f.slot}>{titleCase(f.slot)}</option>}
            </Select>
          </Field>
          <Field label="Category">
            <Select value={f.category} onChange={set("category")}>
              {Object.entries(cats).length ? Object.entries(cats).map(([k, v]) => <option key={k} value={k}>{v}</option>) : <option value={f.category}>{titleCase(f.category)}</option>}
            </Select>
          </Field>
          <Field label="CTA label">
            <Input value={f.cta_label} onChange={set("cta_label")} />
          </Field>
          <Field label="CTA URL">
            <Input type="url" value={f.cta_url} onChange={set("cta_url")} placeholder="https://" />
          </Field>
          <Field label="Price text">
            <Input value={f.price_text} onChange={set("price_text")} placeholder="From Rs 1.2 Lakh" />
          </Field>
          <Field label="Offer">
            <Input value={f.offer} onChange={set("offer")} placeholder="10% off this month" />
          </Field>
          <Field label="Phone">
            <Input value={f.phone} onChange={set("phone")} />
          </Field>
          <Field label="Priority" hint="Higher shows first">
            <Input type="number" value={f.priority} onChange={set("priority")} />
          </Field>
          <Field label="Budget (PKR)" hint={Number(f.budget) ? pkrShort(Number(f.budget)) : "0 = unlimited"}>
            <Input type="number" min={0} value={f.budget} onChange={set("budget")} />
          </Field>
          <Field label="Pricing" hint={f.pricing === "flat" ? "Fixed fee — spend is entered by hand" : "Spend grows automatically as the ad is shown / clicked"}>
            <Select
              value={f.pricing}
              onChange={set("pricing")}
              options={[
                { value: "flat", label: "Fixed fee" },
                { value: "cpm", label: "Per 1,000 impressions (CPM)" },
                { value: "cpc", label: "Per click (CPC)" },
              ]}
            />
          </Field>
          <Field label={f.pricing === "cpc" ? "Rate per click (PKR)" : "Rate per 1,000 impressions (PKR)"} hint={f.pricing === "flat" ? "Not used for fixed-fee ads" : "Delivery pauses when the budget is spent"}>
            <Input type="number" min={0} step="0.5" value={f.rate} onChange={set("rate")} disabled={f.pricing === "flat"} />
          </Field>
          <Field label="Keywords" hint="comma separated">
            <Input value={f.keywords} onChange={set("keywords")} />
          </Field>
          <Field label="Valid from">
            <Input type="date" value={f.valid_from} onChange={set("valid_from")} />
          </Field>
          <Field label="Valid until">
            <Input type="date" value={f.valid_until} onChange={set("valid_until")} />
          </Field>
        </div>
        <div className="lg:sticky lg:top-0 lg:self-start">
          <p className="label">Live preview · {slots[f.slot] ?? titleCase(f.slot)}</p>
          <div className="rounded-3xl border border-dashed border-black/10 bg-[repeating-linear-gradient(45deg,transparent,transparent_10px,rgba(0,0,0,.02)_10px,rgba(0,0,0,.02)_20px)] p-4 dark:border-white/10">
            <motion.div key={`${f.slot}-${f.category}`} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className={cn("pointer-events-none mx-auto", layout === "tile" ? "max-w-[280px]" : layout === "card" ? "max-w-sm" : "")}>
              <AdCreative ad={preview} layout={layout} noTrack />
            </motion.div>
          </div>
          {ad && (
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                <p className="text-[10px] uppercase text-ink-mute">Impr.</p>
                <p className="font-bold">{compact(ad.impressions ?? 0)}</p>
              </div>
              <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                <p className="text-[10px] uppercase text-ink-mute">Clicks</p>
                <p className="font-bold">{num(ad.clicks ?? 0)}</p>
              </div>
              <div className="rounded-xl bg-brand-50/60 p-2 dark:bg-white/5">
                <p className="text-[10px] uppercase text-ink-mute">CTR</p>
                <p className="font-bold">{pct(ad.ctr ?? 0, 2)}</p>
              </div>
            </div>
          )}
          <a href={apiUrl("/ads/preview", { slot: f.slot })} target="_blank" rel="noreferrer" className="link mt-4 inline-flex items-center gap-1 text-sm">
            <ExternalLink className="h-3.5 w-3.5" /> Preview the whole {titleCase(f.slot)} slot
          </a>
        </div>
      </div>
    </Modal>
  );
}
