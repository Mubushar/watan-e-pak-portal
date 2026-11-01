import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, CheckCircle2, ImagePlus, MoreVertical, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";
import type { Property, PropertyList } from "@/types";
import { useApi, useMutate } from "@/hooks/useApi";
import { del, post, put } from "@/lib/api";
import { compressImage } from "@/lib/images";
import { pkrShort, titleCase } from "@/lib/format";
import { useAuth, roleLabel } from "@/store/auth";
import { Button, EmptyState, Field, Input, Segmented, Select, Sheet, Skeleton, Textarea, TopBar } from "@/components/ui";
import { PropertyRow } from "@/components/PropertyCard";

type Tab = "active" | "closed";

export default function MyListings() {
  const user = useAuth((s) => s.user);
  const [tab, setTab] = useState<Tab>("active");
  const [menu, setMenu] = useState<Property | null>(null);
  const [edit, setEdit] = useState<Property | null>(null);
  const q = useApi<PropertyList>("/me/listings");
  const all = q.data?.results ?? [];
  const shown = all.filter((p) => (tab === "active" ? p.status === "active" || p.status === "pending" : p.status === "sold" || p.status === "rented"));
  const active = all.filter((p) => p.status === "active");
  const activeSales = active.filter((p) => p.listing_purpose !== "rent");
  const activeRentals = active.filter((p) => p.listing_purpose === "rent");
  const monthlyRent = activeRentals.reduce((s, p) => s + (p.rent_frequency === "weekly" ? p.price * 52 / 12 : p.price), 0);

  const setStatus = useMutate((v: { id: string; status: string }) => put(`/me/listings/${v.id}`, { status: v.status }), {
    invalidate: ["/me/listings", "/search", "/properties"],
    success: (r) => `Marked as ${(r as Property).status}`,
  });
  const remove = useMutate((id: string) => del(`/me/listings/${id}`), { invalidate: ["/me/listings", "/search", "/properties"], success: "Listing removed" });
  const fileRef = useRef<HTMLInputElement>(null);
  const [photoFor, setPhotoFor] = useState<Property | null>(null);
  const addPhotos = useMutate(
    async ({ id, files }: { id: string; files: File[] }) => {
      let done = 0;
      for (const file of files) {
        await post(`/me/listings/${id}/photos`, { data_url: await compressImage(file), is_primary: false }, { timeoutMs: 60_000 });
        done++;
      }
      return done;
    },
    { invalidate: ["/me/listings", "/search", "/properties"], success: (n) => `${n} photo${n === 1 ? "" : "s"} added` },
  );

  return (
    <div>
      <TopBar
        title="My listings"
        actions={
          <Link to="/listings/new" className="btn btn-primary btn-sm">
            <Plus className="h-4 w-4" /> New
          </Link>
        }
      />
      <div className="screen pt-4">
        <div className="grid grid-cols-2 gap-2.5">
          {[
            ["Active for sale", activeSales.length],
            ["Active rentals", activeRentals.length],
            ["Closed", all.filter((p) => p.status === "sold" || p.status === "rented").length],
            ["Monthly rent", `${pkrShort(monthlyRent, false) || "0"}/mo`],
          ].map(([l, v]) => (
            <div key={l} className="card p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-mute">{l}</p>
              <p className="mt-1 font-display text-xl font-bold text-brand-800 dark:text-white">{v}</p>
            </div>
          ))}
        </div>

        <Segmented
          className="mt-5"
          value={tab}
          onChange={setTab}
          options={[
            { value: "active", label: "Active" },
            { value: "closed", label: "Sold / Rented" },
          ]}
        />

        <div className="mt-4">
          {q.isLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : q.error ? (
            <EmptyState icon={<Building2 className="h-7 w-7" />} title="Couldn't load your listings">
              {q.error.message}
            </EmptyState>
          ) : !shown.length ? (
            <EmptyState
              icon={<Building2 className="h-7 w-7" />}
              title={tab === "active" ? "No active listings yet" : "Nothing sold or rented yet"}
              action={
                tab === "active" && (
                  <Link to="/listings/new" className="btn btn-gold">
                    <Plus className="h-4 w-4" /> List a property
                  </Link>
                )
              }
            >
              {tab === "active" ? `As ${/^[aeiou]/i.test(roleLabel(user?.role)) ? "an" : "a"} ${roleLabel(user?.role).toLowerCase()}, you can list houses, plots, apartments and commercial space — or just tell the AI assistant what you want to sell.` : "Listings you mark as sold or rented appear here."}
            </EmptyState>
          ) : (
            <div className="card divide-y divide-black/5 p-1.5 dark:divide-white/5">
              {shown.map((p) => (
                <div key={p.id} className="flex items-center">
                  <PropertyRow p={p} className="min-w-0 flex-1" />
                  <button className="btn btn-ghost btn-icon shrink-0" aria-label="Listing actions" onClick={() => setMenu(p)}>
                    <MoreVertical className="h-5 w-5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (photoFor && files.length) addPhotos.mutate({ id: photoFor.id, files });
          setPhotoFor(null);
        }}
      />

      <Sheet open={!!menu} onClose={() => setMenu(null)} title={menu?.title}>
        {menu && (
          <div className="grid gap-2">
            <Button
              variant="soft"
              className="justify-start"
              icon={<Pencil className="h-4 w-4" />}
              onClick={() => {
                setEdit(menu);
                setMenu(null);
              }}
            >
              Edit price & details
            </Button>
            <Button
              variant="soft"
              className="justify-start"
              icon={<ImagePlus className="h-4 w-4" />}
              loading={addPhotos.isPending}
              onClick={() => {
                setPhotoFor(menu);
                setMenu(null);
                fileRef.current?.click();
              }}
            >
              Add photos
            </Button>
            {menu.status === "active" ? (
              <>
                <Button variant="soft" className="justify-start" icon={<CheckCircle2 className="h-4 w-4" />} onClick={() => { setStatus.mutate({ id: menu.id, status: "sold" }); setMenu(null); }}>
                  Mark as sold
                </Button>
                <Button variant="soft" className="justify-start" icon={<CheckCircle2 className="h-4 w-4" />} onClick={() => { setStatus.mutate({ id: menu.id, status: "rented" }); setMenu(null); }}>
                  Mark as rented
                </Button>
              </>
            ) : (
              <Button variant="soft" className="justify-start" icon={<RotateCcw className="h-4 w-4" />} onClick={() => { setStatus.mutate({ id: menu.id, status: "active" }); setMenu(null); }}>
                Re-list as active
              </Button>
            )}
            <Button
              variant="ghost"
              className="justify-start text-red-600 hover:bg-red-50 dark:text-red-400"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={() => {
                if (confirm(`Delete “${menu.title}”? This can’t be undone.`)) remove.mutate(menu.id);
                setMenu(null);
              }}
            >
              Delete listing
            </Button>
          </div>
        )}
      </Sheet>

      {edit && <EditSheet p={edit} onClose={() => setEdit(null)} />}
    </div>
  );
}

function EditSheet({ p, onClose }: { p: Property; onClose: () => void }) {
  const [f, setF] = useState({ title: p.title, price: String(p.price), description: p.description ?? "", amenities: (p.amenities ?? []).join(", "), security_deposit: String(p.security_deposit ?? 0), advance_months: String(p.advance_months ?? 1), lease_term_months: String(p.lease_term_months ?? 12), rent_frequency: p.rent_frequency ?? "monthly", furnishing_status: p.furnishing_status ?? "unfurnished", tenant_preference: p.tenant_preference ?? "" });
  const amenities = f.amenities.split(/[,،\n]/).map((a) => a.trim()).filter(Boolean);
  const save = useMutate(() => put(`/me/listings/${p.id}`, { title: f.title.trim(), price: Number(f.price), description: f.description, amenities, ...(p.listing_purpose === "rent" ? { security_deposit: Number(f.security_deposit), advance_months: Number(f.advance_months), lease_term_months: Number(f.lease_term_months), rent_frequency: f.rent_frequency, furnishing_status: f.furnishing_status, tenant_preference: f.tenant_preference } : {}) }), {
    invalidate: ["/me/listings", "/search", "/properties"],
    success: "Listing updated",
    onSuccess: onClose,
  });
  return (
    <Sheet open onClose={onClose} title={p.listing_purpose === "rent" ? "Edit rental listing" : "Edit listing"}>
      <div className="space-y-4">
        <Field label="Title">
          <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        </Field>
        <Field label={p.listing_purpose === "rent" ? `Rent per ${f.rent_frequency === "weekly" ? "week" : "month"} (PKR)` : "Price (PKR)"} hint={Number(f.price) > 0 ? pkrShort(Number(f.price)) : undefined}>
          <Input inputMode="numeric" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value.replace(/\D/g, "") })} />
        </Field>
        {p.listing_purpose === "rent" && <>
          <Field label="Rent frequency"><Select value={f.rent_frequency} onChange={(e) => setF({ ...f, rent_frequency: e.target.value })}><option value="monthly">Monthly</option><option value="weekly">Weekly</option></Select></Field>
          <Field label="Security deposit (PKR)"><Input inputMode="numeric" value={f.security_deposit} onChange={(e) => setF({ ...f, security_deposit: e.target.value.replace(/\D/g, "") })} /></Field>
          <div className="grid grid-cols-2 gap-3"><Field label="Advance months"><Input inputMode="numeric" value={f.advance_months} onChange={(e) => setF({ ...f, advance_months: e.target.value.replace(/\D/g, "") })} /></Field><Field label="Lease term (months)"><Input inputMode="numeric" value={f.lease_term_months} onChange={(e) => setF({ ...f, lease_term_months: e.target.value.replace(/\D/g, "") })} /></Field></div>
          <Field label="Furnishing"><Select value={f.furnishing_status} onChange={(e) => setF({ ...f, furnishing_status: e.target.value })}><option value="unfurnished">Unfurnished</option><option value="semi_furnished">Semi furnished</option><option value="furnished">Furnished</option></Select></Field>
          <Field label="Tenant preference (optional)"><Input value={f.tenant_preference} onChange={(e) => setF({ ...f, tenant_preference: e.target.value })} maxLength={500} /></Field>
        </>}
        <Field label="Description">
          <Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        <Field label="Features" hint="Comma-separated, e.g. Solar system, Basement, Corner">
          <Input value={f.amenities} onChange={(e) => setF({ ...f, amenities: e.target.value })} />
        </Field>
        <Button className="w-full" size="lg" loading={save.isPending} disabled={f.title.trim().length < 5 || !(Number(f.price) > 0)} onClick={() => save.mutate()}>
          Save changes
        </Button>
        <p className="text-center text-xs text-ink-mute">Status: {titleCase(p.status)}</p>
      </div>
    </Sheet>
  );
}
