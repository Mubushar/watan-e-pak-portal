/**
 * Listings owned by the signed-in account.
 *   GET    /me/listings                 (Bearer token)
 *   PUT    /me/listings/{id}            (status, price, details)
 *   DELETE /me/listings/{id}
 *   POST   /me/listings/{id}/photos     (add photos later)
 */
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, CheckCircle2, Eye, ImagePlus, Pencil, Plus, RotateCcw, Trash2, Wallet } from "lucide-react";
import { toast } from "sonner";
import type { Property, PropertyList } from "@/types";
import { useApi, useMutate } from "@/hooks/useApi";
import { del, post, put } from "@/lib/api";
import { pkrShort, titleCase } from "@/lib/format";
import { compressImage, coverImage } from "@/lib/images";
import { Button, ButtonLink, Card, EmptyState, ErrorState, Field, Input, Modal, PageHeader, Segmented, Skeleton, StatCard, StatusBadge, Textarea } from "@/components/ui";

type Tab = "active" | "closed";
const INVALIDATE = ["/me/listings", "/search", "/properties"];
const isClosed = (p: Property) => p.status === "sold" || p.status === "rented";

export default function MyListings() {
  const [tab, setTab] = useState<Tab>("active");
  const [edit, setEdit] = useState<Property | null>(null);
  const [deleting, setDeleting] = useState<Property | null>(null);
  const q = useApi<PropertyList>("/me/listings");
  const all = q.data?.results ?? [];
  const shown = all.filter((p) => (tab === "active" ? !isClosed(p) : isClosed(p)));
  const active = all.filter((p) => p.status === "active");

  const setStatus = useMutate((v: { id: string; status: string }) => put<Property>(`/me/listings/${v.id}`, { status: v.status }), {
    invalidate: INVALIDATE,
    success: (r) => `Marked as ${r.status}`,
  });
  const remove = useMutate((id: string) => del(`/me/listings/${id}`), { invalidate: INVALIDATE, success: "Listing removed", onSuccess: () => setDeleting(null) });

  return (
    <div>
      <PageHeader
        title="My listings"
        subtitle="Properties you’ve published — update prices, mark them sold or rented, and add photos."
        crumbs={[{ label: "Dashboard", to: "/app" }, { label: "My listings" }]}
        actions={
          <ButtonLink to="/app/listings/new" variant="gold" icon={<Plus className="h-4 w-4" />}>
            List a property
          </ButtonLink>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Active" value={active.length} icon={<Building2 className="h-5 w-5" />} />
        <StatCard label="Sold / rented" value={all.filter(isClosed).length} icon={<CheckCircle2 className="h-5 w-5" />} tone="gold" />
        <StatCard label="Active value" value={active.length ? pkrShort(active.reduce((s, p) => s + p.price, 0), false) : "—"} icon={<Wallet className="h-5 w-5" />} tone="blue" />
      </div>

      <Segmented
        className="mt-6"
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
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !shown.length ? (
          <EmptyState
            icon={<Building2 className="h-6 w-6" />}
            title={tab === "active" ? "No active listings yet" : "Nothing sold or rented yet"}
            hint={tab === "active" ? "List a house, plot, apartment or commercial space — it’s searchable on the portal, the map and by every AI agent straight away." : "Listings you mark as sold or rented appear here."}
            action={
              tab === "active" && (
                <ButtonLink to="/app/listings/new" variant="gold" icon={<Plus className="h-4 w-4" />}>
                  List a property
                </ButtonLink>
              )
            }
          />
        ) : (
          <div className="space-y-3">
            {shown.map((p) => (
              <ListingRow
                key={p.id}
                p={p}
                onEdit={() => setEdit(p)}
                onDelete={() => setDeleting(p)}
                onStatus={(status) => setStatus.mutate({ id: p.id, status })}
                busy={setStatus.isPending && setStatus.variables?.id === p.id}
              />
            ))}
          </div>
        )}
      </div>

      {edit && <EditModal p={edit} onClose={() => setEdit(null)} />}
      <Modal
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title="Delete listing?"
        size="sm"
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
        <p className="text-sm text-ink-mute">“{deleting?.title}” is removed from search, the map and the AI agents. This cannot be undone.</p>
      </Modal>
    </div>
  );
}

function ListingRow({ p, onEdit, onDelete, onStatus, busy }: { p: Property; onEdit: () => void; onDelete: () => void; onStatus: (s: string) => void; busy: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const addPhotos = useMutate(
    async (files: File[]) => {
      let done = 0;
      for (const file of files) {
        setUploading(`Uploading ${done + 1} of ${files.length}…`);
        await post(`/me/listings/${p.id}/photos`, { data_url: await compressImage(file), is_primary: false });
        done++;
      }
      return done;
    },
    { invalidate: INVALIDATE, success: (n) => `${n} photo${n > 1 ? "s" : ""} added` },
  );
  const where = [p.block_name, p.scheme_name, p.city_name].filter(Boolean).join(", ");
  return (
    <Card className="flex flex-col gap-3 p-3 xl:flex-row xl:items-center">
      <Link to={`/properties/${p.id}`} className="flex min-w-0 flex-1 items-center gap-4">
        <img src={coverImage(p)} alt="" className="h-20 w-28 shrink-0 rounded-xl object-cover" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={p.status} />
            <span className="text-xs text-ink-mute">{titleCase(p.category)}</span>
          </div>
          <p className="mt-1 truncate font-semibold">{p.title}</p>
          <p className="truncate text-xs text-ink-mute">{where || "—"}</p>
          <p className="mt-0.5 font-display font-bold text-brand-700 dark:text-gold-300">{pkrShort(p.price)}</p>
        </div>
      </Link>
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) addPhotos.mutate(files, { onSettled: () => setUploading(null), onError: () => toast.error("Some photos couldn’t be uploaded") });
        }}
      />
      <div className="flex flex-wrap gap-2 xl:justify-end">
        <ButtonLink to={`/properties/${p.id}`} variant="ghost" size="sm" icon={<Eye className="h-4 w-4" />}>
          View
        </ButtonLink>
        <Button variant="ghost" size="sm" icon={<Pencil className="h-4 w-4" />} onClick={onEdit}>
          Edit
        </Button>
        <Button variant="ghost" size="sm" icon={<ImagePlus className="h-4 w-4" />} loading={addPhotos.isPending} onClick={() => fileRef.current?.click()}>
          {uploading ?? "Photos"}
        </Button>
        {isClosed(p) ? (
          <Button variant="outline" size="sm" icon={<RotateCcw className="h-4 w-4" />} loading={busy} onClick={() => onStatus("active")}>
            Re-list
          </Button>
        ) : (
          <>
            <Button variant="outline" size="sm" loading={busy} onClick={() => onStatus("sold")}>
              Mark sold
            </Button>
            <Button variant="outline" size="sm" loading={busy} onClick={() => onStatus("rented")}>
              Mark rented
            </Button>
          </>
        )}
        <Button variant="ghost" size="sm" className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10" icon={<Trash2 className="h-4 w-4" />} onClick={onDelete} aria-label="Delete listing" />
      </div>
    </Card>
  );
}

function EditModal({ p, onClose }: { p: Property; onClose: () => void }) {
  const [f, setF] = useState({ title: p.title, price: String(p.price), description: p.description ?? "", amenities: (p.amenities ?? []).join(", ") });
  const amenities = f.amenities.split(/[,،\n]/).map((a) => a.trim()).filter(Boolean);
  const save = useMutate(
    () => put(`/me/listings/${p.id}`, { title: f.title.trim(), price: Number(f.price), description: f.description, amenities }),
    { invalidate: INVALIDATE, success: "Listing updated", onSuccess: onClose },
  );
  const valid = f.title.trim().length >= 5 && Number(f.price) > 0;
  return (
    <Modal
      open
      onClose={onClose}
      title="Edit listing"
      subtitle={`Status: ${titleCase(p.status)}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} disabled={!valid} onClick={() => save.mutate()}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Title">
          <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        </Field>
        <Field label="Price (PKR)" hint={Number(f.price) > 0 ? pkrShort(Number(f.price)) : undefined}>
          <Input inputMode="numeric" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value.replace(/\D/g, "") })} />
        </Field>
        <Field label="Description">
          <Textarea rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        <Field label="Features & amenities" hint="Comma-separated, e.g. Solar system, Basement, Corner">
          <Input value={f.amenities} onChange={(e) => setF({ ...f, amenities: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}
