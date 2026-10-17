import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Marker, Popup } from "react-leaflet";
import { ArrowRight, Banknote, Building2, CalendarDays, Compass, Gauge, Home, Landmark, LineChart, MapPin, PieChart, Ruler, Sparkles, TrendingUp } from "lucide-react";
import type { City, PropertyList } from "@/types";
import { useApi } from "@/hooks/useApi";
import { compact, num, pct, pkrShort, titleCase } from "@/lib/format";
import { cityImage, themedImage } from "@/lib/images";
import { ButtonLink, Badge, Card, CardBody, CardHeader, Carousel, Donut, EmptyState, ErrorState, Legendish, PageHeader, ScoreRing, Skeleton, StatCard } from "@/components/ui";
import { PropertyCard } from "@/components/property/PropertyCard";
import { PortalMap, PIN_STYLES, pin } from "@/components/map/PortalMap";
import { AdSlot } from "@/components/ads/AdSlot";
import { FactorBars, ForecastChart, backendError, bandTone, entriesToDonut } from "@/components/gis/kit";
import type { MarketTrends, Poi } from "@/components/gis/types";

interface CityDetails {
  city: { id: string; name: string; state?: string; country?: string; latitude: number; longitude: number; description?: string | null };
  schemes: { id: string; name: string; total_units?: number; established_year?: number; developer?: string | null; latitude?: number | null; longitude?: number | null }[];
  property_count: number;
  big_projects: number;
  error?: string;
}
interface CityInsights {
  city: string;
  properties: number;
  avg_price: number | null;
  min_price: number | null;
  max_price: number | null;
  avg_price_per_sqft: number | null;
  by_category: Record<string, number>;
  by_use_type: Record<string, number>;
  schemes: number;
  big_projects: number;
  error?: string;
}

const fade = { initial: { opacity: 0, y: 16 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-60px" }, transition: { duration: 0.45 } };

export default function CityPage() {
  const { city: raw = "" } = useParams();
  const name = decodeURIComponent(raw);
  const detailQ = useApi<CityDetails>(name ? `/cities/${encodeURIComponent(name)}` : null);
  const insightsQ = useApi<CityInsights>(name ? `/cities/${encodeURIComponent(name)}/insights` : null);
  const trendsQ = useApi<MarketTrends>(name ? "/portal/market-trends" : null, { city: name });
  const poiQ = useApi<{ pois: Poi[] }>(name ? "/poi" : null, { city: name, limit: 500 });
  const propsQ = useApi<PropertyList>("/properties", { limit: 200 });
  const citiesQ = useApi<{ cities: City[] }>("/cities");

  const d = detailQ.data && !backendError(detailQ.data) ? detailQ.data : undefined;
  const cityName = d?.city.name ?? name;
  const ins = insightsQ.data && !backendError(insightsQ.data) ? insightsQ.data : undefined;
  const t = trendsQ.data && !backendError(trendsQ.data) ? trendsQ.data : undefined;
  const props = useMemo(() => (propsQ.data?.results ?? []).filter((p) => (d ? p.city_id === d.city.id : p.city_name?.toLowerCase() === name.toLowerCase())), [propsQ.data, d, name]);
  const pois = poiQ.data?.pois ?? [];
  const poiMix = useMemo(() => {
    const m: Record<string, number> = {};
    pois.forEach((p) => (m[p.category] = (m[p.category] ?? 0) + 1));
    return Object.entries(m)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => ({ name: titleCase(k), value: v, color: PIN_STYLES[k]?.color }));
  }, [pois]);
  const mapPts = useMemo(
    () => [...props.filter((p) => p.latitude != null && p.longitude != null).map((p) => [p.latitude!, p.longitude!] as [number, number]), ...pois.map((p) => [p.latitude, p.longitude] as [number, number])],
    [props, pois],
  );

  const err = detailQ.error as (Error & { status?: number }) | null;
  const notFound = (detailQ.data && backendError(detailQ.data)) || (err && (err.status === 404 || /not found/i.test(err.message)));

  if (notFound)
    return (
      <div className="container py-20">
        <EmptyState
          title={`We couldn't find “${name}”`}
          hint="Try one of the cities we cover."
          icon={<MapPin className="h-6 w-6" />}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {(citiesQ.data?.cities ?? []).map((c) => (
                <ButtonLink key={c.id} to={`/cities/${encodeURIComponent(c.name)}`} variant="soft" size="sm">
                  {c.name}
                </ButtonLink>
              ))}
            </div>
          }
        />
      </div>
    );

  return (
    <div className="pb-16">
      <PageHeader
        image={cityImage(cityName)}
        eyebrow={d ? [d.city.state, d.city.country].filter(Boolean).join(" · ") : "City guide"}
        title={
          <>
            Property in <span className="text-gradient">{cityName}</span>
          </>
        }
        subtitle={d?.city.description ?? `Listings, housing schemes, market trends and amenities across ${cityName}.`}
        crumbs={[{ label: "Home", to: "/" }, { label: "Insights", to: "/insights" }, { label: cityName }]}
        actions={
          <>
            <ButtonLink to={`/properties?city=${encodeURIComponent(cityName)}`} variant="gold" icon={<Home className="h-4 w-4" />}>
              Browse {cityName} listings
            </ButtonLink>
            <ButtonLink to="/map" variant="outline" className="!border-white/30 !bg-white/10 !text-white hover:!bg-white/20" icon={<Compass className="h-4 w-4" />}>
              Open on map
            </ButtonLink>
          </>
        }
      >
        {d && (
          <div className="mt-8 flex flex-wrap gap-3">
            {[
              ["Listings", d.property_count],
              ["Schemes", d.schemes.length],
              ["Mega projects", d.big_projects],
              ["Places mapped", pois.length],
            ].map(([l, v]) => (
              <div key={String(l)} className="glass-dark min-w-[110px] rounded-2xl px-4 py-2.5">
                <p className="font-display text-2xl font-bold">{v}</p>
                <p className="text-[10px] font-bold uppercase tracking-wider text-gold-200">{l}</p>
              </div>
            ))}
          </div>
        )}
      </PageHeader>

      <div className="container mt-8 space-y-10">
        {err && <ErrorState error={err} onRetry={() => detailQ.refetch()} />}

        {/* -------------------------------------------------------------- KPIs */}
        {insightsQ.isLoading ? (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
        ) : ins ? (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Average price" value={pkrShort(ins.avg_price)} icon={<Banknote className="h-5 w-5" />} hint={`${ins.properties} listings`} />
            <StatCard label="Price range" value={`${pkrShort(ins.min_price, false)} – ${pkrShort(ins.max_price, false)}`} icon={<TrendingUp className="h-5 w-5" />} tone="gold" />
            <StatCard label="Avg price / sqft" value={ins.avg_price_per_sqft ? `PKR ${num(ins.avg_price_per_sqft)}` : "—"} icon={<Ruler className="h-5 w-5" />} tone="blue" />
            <StatCard label="Market value" value={t ? pkrShort(t.pricing.total_market_value) : "—"} icon={<Landmark className="h-5 w-5" />} tone="purple" hint={t ? `${pkrShort(t.pricing.price_per_marla)} / marla` : undefined} />
          </div>
        ) : null}

        {/* -------------------------------------------------------------- schemes */}
        <motion.section {...fade}>
          <div className="mb-5 flex items-end justify-between gap-3">
            <div>
              <p className="section-eyebrow">Housing schemes</p>
              <h2 className="mt-1 font-display text-2xl font-bold text-brand-900 dark:text-white">Societies in {cityName}</h2>
            </div>
            <Link to="/schemes" className="link shrink-0 text-sm">
              All schemes
            </Link>
          </div>
          {detailQ.isLoading ? (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-56" />
              ))}
            </div>
          ) : !d?.schemes.length ? (
            <EmptyState title={`No schemes listed in ${cityName} yet`} icon={<Building2 className="h-6 w-6" />} />
          ) : (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {d.schemes.map((s, i) => (
                <motion.div key={s.id} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.06 }}>
                  <Link to={`/schemes?scheme=${s.id}`} className="card card-hover group block overflow-hidden">
                    <div className="relative aspect-[16/10] overflow-hidden">
                      <img src={themedImage(s.id, s.name)} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110" />
                      <div className="absolute inset-0 bg-gradient-to-t from-brand-950/80 to-transparent" />
                      <p className="absolute bottom-3 start-3 end-3 font-display text-lg font-bold leading-tight text-white">{s.name}</p>
                    </div>
                    <div className="flex items-center justify-between gap-2 p-3 text-xs text-ink-mute">
                      <span className="inline-flex items-center gap-1">
                        <CalendarDays className="h-3.5 w-3.5 text-gold-600" /> {s.established_year ?? "—"}
                      </span>
                      <span>{compact(s.total_units)} units</span>
                      {s.developer && <span className="truncate font-semibold text-ink-soft dark:text-slate-300">{s.developer}</span>}
                    </div>
                  </Link>
                </motion.div>
              ))}
            </div>
          )}
        </motion.section>

        {/* -------------------------------------------------------------- properties */}
        <motion.section {...fade}>
          <div className="mb-5 flex items-end justify-between gap-3">
            <div>
              <p className="section-eyebrow">For sale & rent</p>
              <h2 className="mt-1 font-display text-2xl font-bold text-brand-900 dark:text-white">Listings in {cityName}</h2>
            </div>
          </div>
          {propsQ.isLoading ? (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-72" />
              ))}
            </div>
          ) : propsQ.error ? (
            <ErrorState error={propsQ.error} onRetry={() => propsQ.refetch()} />
          ) : !props.length ? (
            <EmptyState title={`No live listings in ${cityName}`} icon={<Home className="h-6 w-6" />} />
          ) : (
            <Carousel slideClass="basis-full sm:basis-1/2 lg:basis-1/3" arrowsPosition="top" autoplay delay={5000}>
              {props.map((p) => (
                <PropertyCard key={p.id} p={p} />
              ))}
            </Carousel>
          )}
        </motion.section>

        {/* -------------------------------------------------------------- market */}
        <motion.section {...fade} className="grid gap-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <Card>
            <CardHeader title="Market trend & forecast" subtitle="Price per marla under three scenarios" icon={<LineChart className="h-5 w-5" />} action={<Link to="/insights" className="btn btn-ghost btn-sm">Full insights <ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" /></Link>} />
            <CardBody>{trendsQ.isLoading ? <Skeleton className="h-72" /> : trendsQ.error ? <ErrorState error={trendsQ.error} onRetry={() => trendsQ.refetch()} /> : <ForecastChart scenarios={t?.forecast.scenarios} height={290} />}</CardBody>
          </Card>
          <Card>
            <CardHeader title="Market health" icon={<Gauge className="h-5 w-5" />} />
            <CardBody>
              {trendsQ.isLoading ? (
                <Skeleton className="h-72" />
              ) : t ? (
                <div className="space-y-5">
                  <div className="flex items-center gap-4">
                    <ScoreRing value={t.factors.index.composite} size={92} label="index" />
                    <div className="space-y-1.5 text-sm">
                      <Badge tone={bandTone(t.factors.index.band)} className="capitalize">
                        {t.factors.index.band}
                      </Badge>
                      <p className="text-ink-mute">
                        Base CAGR <b className="text-ink dark:text-white">{pct(t.forecast.base_cagr)}</b>
                      </p>
                      <p className="text-ink-mute">
                        News <b className="capitalize text-ink dark:text-white">{t.news.net_sentiment}</b> ({t.news.count})
                      </p>
                    </div>
                  </div>
                  <FactorBars scores={t.factors.scores} />
                </div>
              ) : (
                <p className="py-8 text-center text-sm text-ink-mute">No market data.</p>
              )}
            </CardBody>
          </Card>
        </motion.section>

        {/* -------------------------------------------------------------- map + POI + supply */}
        <motion.section {...fade} className="grid gap-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
          <Card className="overflow-hidden">
            <CardHeader title={`${cityName} on the map`} subtitle={`${props.length} listings · ${pois.length} places`} icon={<MapPin className="h-5 w-5" />} />
            {detailQ.isLoading ? (
              <Skeleton className="h-[420px] rounded-none" />
            ) : (
              <PortalMap height={420} className="rounded-none" center={d ? [d.city.latitude, d.city.longitude] : undefined} zoom={d ? 11 : 5} fit={mapPts.length ? mapPts : undefined}>
                {props.map((p) =>
                  p.latitude != null && p.longitude != null ? (
                    <Marker key={p.id} position={[p.latitude, p.longitude]} icon={pin(p.featured ? "featured" : p.use_type === "commercial" ? "commercial" : "property")}>
                      <Popup>
                        <div className="p-3">
                          <p className="text-sm font-semibold">{p.title}</p>
                          <p className="text-sm font-bold text-brand-700">{pkrShort(p.price)}</p>
                          <Link to={`/properties/${p.id}`} className="mt-1 inline-block text-xs font-semibold text-brand-700 hover:underline">
                            View details →
                          </Link>
                        </div>
                      </Popup>
                    </Marker>
                  ) : null,
                )}
                {pois.map((p) => (
                  <Marker key={p.id} position={[p.latitude, p.longitude]} icon={pin(PIN_STYLES[p.category] ? p.category : "other", { size: 26 })}>
                    <Popup>
                      <div className="p-3">
                        <p className="text-sm font-semibold">{p.name}</p>
                        <p className="text-xs text-slate-500">
                          {titleCase(p.subcategory ?? p.category)}
                          {p.rating != null && ` · ★ ${p.rating}`}
                        </p>
                      </div>
                    </Popup>
                  </Marker>
                ))}
              </PortalMap>
            )}
          </Card>
          <div className="space-y-6">
            <Card>
              <CardHeader title="Amenity mix" subtitle="Points of interest by category" icon={<Sparkles className="h-5 w-5" />} />
              <CardBody>
                {poiQ.isLoading ? (
                  <Skeleton className="h-52" />
                ) : poiMix.length ? (
                  <>
                    <Donut
                      data={poiMix}
                      height={180}
                      format={(v) => `${v} places`}
                      center={
                        <>
                          <span className="font-display text-2xl font-bold text-ink dark:text-white">{pois.length}</span>
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-mute">places</span>
                        </>
                      }
                    />
                    <div className="mt-3">
                      <Legendish data={poiMix} />
                    </div>
                  </>
                ) : (
                  <p className="py-8 text-center text-sm text-ink-mute">No places mapped yet.</p>
                )}
              </CardBody>
            </Card>
            {ins && Object.keys(ins.by_category).length > 0 && (
              <Card>
                <CardHeader title="Supply by type" icon={<PieChart className="h-5 w-5" />} />
                <CardBody>
                  <Legendish data={entriesToDonut(ins.by_category)} />
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {Object.entries(ins.by_use_type).map(([k, v]) => (
                      <Badge key={k} tone={k === "commercial" ? "blue" : k === "residential" ? "green" : "gold"}>
                        {titleCase(k)} · {v}
                      </Badge>
                    ))}
                  </div>
                </CardBody>
              </Card>
            )}
          </div>
        </motion.section>

        <AdSlot slot="banner" city={cityName} />

        {/* -------------------------------------------------------------- other cities */}
        {(citiesQ.data?.cities ?? []).filter((c) => c.name !== cityName).length > 0 && (
          <section>
            <p className="section-eyebrow">Keep exploring</p>
            <h2 className="mt-1 font-display text-2xl font-bold text-brand-900 dark:text-white">Other cities</h2>
            <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-4">
              {(citiesQ.data?.cities ?? [])
                .filter((c) => c.name !== cityName)
                .map((c) => (
                  <Link key={c.id} to={`/cities/${encodeURIComponent(c.name)}`} className="group relative block aspect-[4/3] overflow-hidden rounded-2xl shadow-soft">
                    <img src={cityImage(c.name)} alt="" className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-110" />
                    <div className="absolute inset-0 bg-gradient-to-t from-brand-950/85 to-transparent" />
                    <div className="absolute bottom-3 start-3 text-white">
                      <p className="font-display text-lg font-bold">{c.name}</p>
                      <p className="text-[11px] text-white/75">
                        {c.properties} listings · {c.schemes} schemes
                      </p>
                    </div>
                  </Link>
                ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
