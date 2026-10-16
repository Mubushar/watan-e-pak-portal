import { Link } from "react-router-dom";
import { Heart } from "lucide-react";
import type { PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { usePrefs } from "@/store/prefs";
import { EmptyState, Skeleton, TopBar } from "@/components/ui";
import { PropertyCard } from "@/components/PropertyCard";

/** Saved (favourite) listings — stored on the device. */
export default function Saved() {
  const favorites = usePrefs((s) => s.favorites);
  const q = useApi<PropertyList>(favorites.length ? "/properties" : null, { limit: 500 });
  const saved = (q.data?.results ?? []).filter((p) => favorites.includes(p.id));
  return (
    <div>
      <TopBar title="Saved" />
      <div className="screen pt-4">
        {!favorites.length ? (
          <EmptyState
            icon={<Heart className="h-7 w-7" />}
            title="No saved properties yet"
            action={
              <Link to="/explore" className="btn btn-primary">
                Explore listings
              </Link>
            }
          >
            Tap the heart on any listing to keep it here.
          </EmptyState>
        ) : q.isLoading ? (
          <Skeleton className="h-72" />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {saved.map((p) => (
              <PropertyCard key={p.id} p={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
