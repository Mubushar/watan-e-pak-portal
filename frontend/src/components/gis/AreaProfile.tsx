/**
 * Area profile of a housing society / sector / neighbourhood (GET /areas/profile):
 * population, development level and facilities from OpenStreetMap + Kontur, plus the
 * portal's own development details for registered societies — which admins can edit
 * here (PUT /schemes/{id}).
 */
import { useState } from "react";
import { Building, Pencil, Users, Zap } from "lucide-react";
import { useApi, useMutate } from "@/hooks/useApi";
import { put } from "@/lib/api";
import { compact, num, titleCase } from "@/lib/format";
import { useAuth } from "@/store/auth";
import { Badge, Button, Card, CardBody, CardHeader, Field, Input, KeyValue, Modal, Select, Skeleton } from "@/components/ui";

export interface PortalSchemeFacts {
  name?: string;
  city?: string;
  developer?: string;
  established_year?: number;
  total_units?: number;
  development_status?: string;
  approval_authority?: string;
  possession_status?: string;
  utilities?: string[];
  population?: number;
  description?: string;
}

interface AreaProfileResult {
  found: boolean;
  area?: string;
  note?: string;
  size_km2?: number;
  population_estimate?: number;
  population_density_per_km2?: number;
  development_level?: string;
  facility_counts?: Record<string, number>;
  notable_places?: Record<string, string[]>;
  listings_on_portal?: { count: number; average_price_pkr?: number; average_price_per_marla_pkr?: number };
  nearby_housing_areas?: { name: string; distance_km: number; population_estimate?: number | null }[];
  portal_scheme?: PortalSchemeFacts;
  sources?: string;
}

const DEV_STATUSES = ["developed", "under development", "planned"];
const POSSESSION = ["possession given", "partial", "not yet"];
const UTILITIES = ["electricity", "gas", "water", "sewerage", "fibre internet", "underground wiring"];

export function AreaProfileCard({ schemeId, area }: { schemeId: string; area: string }) {
  // Editing writes PUT /schemes/{id}, which the API allows to holders of basedata.manage.
  const canEdit = useAuth((s) => s.can("basedata.manage"));
  const [editing, setEditing] = useState(false);
  // 503 when the geodata isn't installed: the card then only shows the portal's own facts.
  const q = useApi<AreaProfileResult>("/areas/profile", { area }, { retry: false, staleTime: 10 * 60_000 });
  const d = q.data;
  const facts = d?.portal_scheme;
  if (q.isLoading) return <Skeleton className="h-56 w-full" />;
  if (!d?.found && !facts && !canEdit) return null;

  return (
    <Card>
      <CardHeader
        title="Area profile"
        subtitle={d?.found ? `Population, development and facilities around ${d.area}` : "Development details"}
        icon={<Users className="h-5 w-5" />}
        action={
          canEdit && (
            <Button variant="ghost" size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditing(true)}>
              Edit details
            </Button>
          )
        }
      />
      <CardBody className="space-y-5">
        {facts && (
          <div className="flex flex-wrap gap-2">
            {facts.development_status && <Badge tone={facts.development_status === "developed" ? "green" : "gold"}>{titleCase(facts.development_status)}</Badge>}
            {facts.approval_authority && <Badge tone="blue">Approved by {facts.approval_authority}</Badge>}
            {facts.possession_status && <Badge tone="gray">{titleCase(facts.possession_status)}</Badge>}
            {facts.developer && <Badge tone="gray" icon={<Building className="h-3 w-3" />}>{facts.developer}</Badge>}
            {(facts.utilities ?? []).map((u) => (
              <Badge key={u} tone="green" icon={<Zap className="h-3 w-3" />}>
                {titleCase(u)}
              </Badge>
            ))}
          </div>
        )}
        {d?.found ? (
          <>
            <KeyValue
              cols={4}
              items={[
                { label: "Population", value: compact(facts?.population ?? d.population_estimate) },
                { label: "Density / km²", value: num(d.population_density_per_km2) },
                { label: "Size", value: d.size_km2 ? `${d.size_km2} km²` : "—" },
                { label: "Development", value: titleCase(d.development_level) || "—" },
              ]}
            />
            {!!Object.keys(d.facility_counts ?? {}).length && (
              <div>
                <p className="label">Facilities mapped</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(d.facility_counts!).map(([k, n]) => (
                    <Badge key={k} tone="gray">
                      {k}: {n}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {!!Object.keys(d.notable_places ?? {}).length && (
              <div className="space-y-1 text-sm">
                {Object.entries(d.notable_places!).map(([k, names]) => (
                  <p key={k}>
                    <span className="font-semibold capitalize">{k}:</span> <span className="text-ink-mute">{names.join(", ")}</span>
                  </p>
                ))}
              </div>
            )}
            {!!d.nearby_housing_areas?.length && (
              <div>
                <p className="label">Nearby housing areas</p>
                <div className="flex flex-wrap gap-1.5">
                  {d.nearby_housing_areas.slice(0, 8).map((a) => (
                    <span key={a.name} className="chip bg-brand-50 text-brand-800 dark:bg-white/5 dark:text-brand-200">
                      {a.name} · {a.distance_km} km
                    </span>
                  ))}
                </div>
              </div>
            )}
            {d.sources && <p className="text-xs text-ink-mute">{d.sources}</p>}
          </>
        ) : (
          <p className="text-sm text-ink-mute">{d?.note ?? "Area data (population, facilities) isn’t available for this society yet."}</p>
        )}
      </CardBody>
      {editing && <EditSchemeModal schemeId={schemeId} facts={facts} onClose={() => setEditing(false)} />}
    </Card>
  );
}

function EditSchemeModal({ schemeId, facts, onClose }: { schemeId: string; facts?: PortalSchemeFacts; onClose: () => void }) {
  const [f, setF] = useState({
    development_status: facts?.development_status ?? "",
    approval_authority: facts?.approval_authority ?? "",
    possession_status: facts?.possession_status ?? "",
    developer: facts?.developer ?? "",
    population: facts?.population ? String(facts.population) : "",
    utilities: facts?.utilities ?? [],
  });
  const save = useMutate(
    () =>
      put(`/schemes/${schemeId}`, {
        development_status: f.development_status || undefined,
        approval_authority: f.approval_authority.trim() || undefined,
        possession_status: f.possession_status || undefined,
        developer: f.developer.trim() || undefined,
        population: f.population ? Number(f.population) : undefined,
        utilities: f.utilities,
      }),
    { invalidate: ["/areas/profile", "/schemes", "/hierarchy"], success: "Society details saved", onSuccess: onClose },
  );
  const toggle = (u: string) => setF((x) => ({ ...x, utilities: x.utilities.includes(u) ? x.utilities.filter((y) => y !== u) : [...x.utilities, u] }));
  return (
    <Modal
      open
      onClose={onClose}
      title="Society development details"
      subtitle="Shown to buyers and used by the AI assistant."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Development status">
          <Select value={f.development_status} onChange={(e) => setF({ ...f, development_status: e.target.value })} options={[{ value: "", label: "—" }, ...DEV_STATUSES.map((v) => ({ value: v, label: titleCase(v) }))]} />
        </Field>
        <Field label="Possession">
          <Select value={f.possession_status} onChange={(e) => setF({ ...f, possession_status: e.target.value })} options={[{ value: "", label: "—" }, ...POSSESSION.map((v) => ({ value: v, label: titleCase(v) }))]} />
        </Field>
        <Field label="Approval authority" hint="e.g. RDA, CDA, LDA, KDA">
          <Input value={f.approval_authority} onChange={(e) => setF({ ...f, approval_authority: e.target.value })} />
        </Field>
        <Field label="Developer">
          <Input value={f.developer} onChange={(e) => setF({ ...f, developer: e.target.value })} />
        </Field>
        <Field label="Residents" hint="If the society publishes it">
          <Input inputMode="numeric" value={f.population} onChange={(e) => setF({ ...f, population: e.target.value.replace(/\D/g, "") })} />
        </Field>
        <div className="sm:col-span-2">
          <p className="label">Utilities</p>
          <div className="flex flex-wrap gap-1.5">
            {[...UTILITIES, ...f.utilities.filter((u) => !UTILITIES.includes(u))].map((u) => (
              <button key={u} type="button" onClick={() => toggle(u)} className={f.utilities.includes(u) ? "chip bg-brand-700 text-white" : "chip ring-1 ring-black/10 dark:ring-white/10"}>
                {titleCase(u)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
