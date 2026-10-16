import { Link, useNavigate } from "react-router-dom";
import { Clock, Heart } from "lucide-react";
import type { PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { usePrefs } from "@/store/prefs";
import { Button, EmptyState, PageHeader, Skeleton } from "@/components/ui";
import { PropertyCard } from "@/components/property/PropertyCard";

export default function Favorites() {
  const favs = usePrefs((s) => s.favorites);
  const recent = usePrefs((s) => s.recent);
  const toggleCompare = usePrefs((s) => s.toggleCompare);
  const nav = useNavigate();
  const q = useApi<PropertyList>("/properties", { limit: 500 });
  const byId = new Map((q.data?.results ?? []).map((p) => [p.id, p]));
  const saved = favs.map((id) => byId.get(id)).filter(Boolean) as NonNullable<ReturnType<typeof byId.get>>[];
  const viewed = recent.filter((id) => !favs.includes(id)).map((id) => byId.get(id)).filter(Boolean) as typeof saved;

  return (
    <div className="container py-8">
      <PageHeader
        title="Your shortlist"
        subtitle="Saved properties stay on this device. Compare them side by side or ask the AI for a recommendation."
        crumbs={[{ label: "Home", to: "/" }, { label: "Shortlist" }]}
        actions={
          saved.length > 1 ? (
            <Button
              variant="gold"
              onClick={() => {
                saved.slice(0, 4).forEach((p) => !usePrefs.getState().compare.includes(p.id) && toggleCompare(p.id));
                nav("/compare");
              }}
            >
              Compare saved
            </Button>
          ) : undefined
        }
      />
      {q.isLoading ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : saved.length ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {saved.map((p) => (
            <PropertyCard key={p.id} p={p} />
          ))}
        </div>
      ) : (
        <EmptyState icon={<Heart className="h-6 w-6" />} title="No saved properties yet" hint="Tap the heart on any listing to save it here." action={<Link to="/properties" className="btn btn-primary">Browse properties</Link>} />
      )}
      {!!viewed.length && (
        <section className="mt-14">
          <p className="mb-4 flex items-center gap-2 font-display text-xl font-semibold">
            <Clock className="h-5 w-5 text-gold-600" /> Recently viewed
          </p>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {viewed.slice(0, 8).map((p) => (
              <PropertyCard key={p.id} p={p} compact />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
