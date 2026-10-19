import { useMemo, type ReactNode } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Cpu, FolderOpen, Info } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import { titleCase, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuth } from "@/store/auth";
import { Badge, Breadcrumbs, ButtonLink, Card, CardBody, CardHeader, EmptyState, Skeleton } from "@/components/ui";
import { CATEGORY_ICON, EXTRA_TOOLS, INTERACTIVE_TOOLS, phaseTone, ToolIcon, type ToolCard } from "@/components/tools/toolMeta";
import { AppreciationCalc, InstallmentCalc, MortgageCalc, RentalYieldCalc, RentVsBuyCalc } from "@/components/tools/FinanceCalcs";
import { AreaCalc, PlotDimensionsCalc, PricePerUnitCalc } from "@/components/tools/AreaCalcs";
import { CgtCalc, CommissionCalc, ConstructionCalc, JointInvestmentCalc, TransferCalc } from "@/components/tools/CostCalcs";
import { CalendarTool, GenericTool, MapMeasureTool } from "@/components/tools/MiscTools";

const CALCS: Record<string, () => ReactNode> = {
  mortgage: () => <MortgageCalc />,
  installment: () => <InstallmentCalc />,
  rental_yield: () => <RentalYieldCalc />,
  appreciation: () => <AppreciationCalc />,
  rent_vs_buy: () => <RentVsBuyCalc />,
  area: () => <AreaCalc />,
  price_per_unit: () => <PricePerUnitCalc />,
  plot_dimensions: () => <PlotDimensionsCalc />,
  construction: () => <ConstructionCalc />,
  transfer: () => <TransferCalc />,
  commission: () => <CommissionCalc />,
  cgt: () => <CgtCalc />,
  joint_investment: () => <JointInvestmentCalc />,
  calendar: () => <CalendarTool />,
  map_measure: () => <MapMeasureTool />,
  coords_area: () => <MapMeasureTool />,
};

function Rail({ tools, current }: { tools: ToolCard[]; current: string }) {
  const groups = useMemo(() => {
    const m = new Map<string, ToolCard[]>();
    for (const t of tools) m.set(t.category, [...(m.get(t.category) ?? []), t]);
    return [...m.entries()];
  }, [tools]);
  return (
    <>
      {/* mobile: horizontal chips */}
      <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1 lg:hidden">
        {tools.map((t) => (
          <Link
            key={t.key}
            to={`/tools/${t.key}`}
            className={cn("chip shrink-0 px-3 py-1.5", t.key === current ? "bg-brand-700 text-white" : "bg-white text-ink-soft ring-1 ring-black/5 dark:bg-white/5 dark:text-slate-300 dark:ring-white/10")}
          >
            {t.name}
          </Link>
        ))}
      </div>
      {/* desktop: grouped rail */}
      <nav className="hidden space-y-5 lg:block">
        {groups.map(([cat, list]) => {
          const CI = CATEGORY_ICON[cat] ?? Cpu;
          return (
            <div key={cat}>
              <p className="mb-1.5 flex items-center gap-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-ink-mute">
                <CI className="h-3.5 w-3.5" /> {titleCase(cat)}
              </p>
              <ul className="space-y-0.5">
                {list.map((t) => (
                  <li key={t.key}>
                    <NavLink
                      to={`/tools/${t.key}`}
                      className={({ isActive }) =>
                        cn(
                          "group flex items-center gap-2.5 rounded-xl px-2 py-1.5 text-sm transition",
                          isActive ? "bg-brand-700 font-semibold text-white shadow-soft" : "text-ink-soft hover:bg-brand-50 hover:text-brand-800 dark:text-slate-300 dark:hover:bg-white/5",
                        )
                      }
                    >
                      <ToolIcon toolKey={t.key} category={t.category} size="sm" className="!h-7 !w-7 !shadow-none" />
                      <span className="truncate">{t.name}</span>
                      {INTERACTIVE_TOOLS.has(t.key) && <span className="ms-auto h-1.5 w-1.5 shrink-0 rounded-full bg-gold-400" title="Interactive" />}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>
    </>
  );
}

function SavedProjects({ toolKey }: { toolKey: string }) {
  // Saved projects belong to an account: guests have none (the API answers 401).
  const signedIn = !!useAuth((s) => s.token);
  const q = useApi<{ count: number; projects: { id: string; name: string; tool: string; created_at?: string; notes?: string }[] }>(signedIn ? "/tools/projects" : null, { tool: toolKey });
  const list = q.data?.projects ?? [];
  if (!list.length) return null;
  return (
    <Card>
      <CardHeader title="Saved projects" subtitle={`${list.length} for this tool`} icon={<FolderOpen className="h-4 w-4" />} />
      <ul className="divide-y divide-black/5 dark:divide-white/10">
        {list.slice(0, 6).map((p) => (
          <li key={p.id} className="px-5 py-2.5 text-sm">
            <p className="truncate font-medium">{p.name}</p>
            {p.created_at && <p className="text-xs text-ink-mute">{timeAgo(p.created_at)}</p>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function ToolPage() {
  const { key = "mortgage" } = useParams();
  const cat = useApi<{ tools: ToolCard[] }>("/tools/catalog");
  const extra = EXTRA_TOOLS.find((t) => t.key === key);
  // NB: an unknown key answers 200 with {"error": "Unknown tool: …"}.
  const one = useApi<ToolCard & { error?: string }>(extra ? null : `/tools/catalog/${key}`, undefined, { retry: false });
  const found = one.data && !one.data.error && one.data.key ? one.data : undefined;
  const tool: ToolCard | undefined = extra ?? found ?? cat.data?.tools.find((t) => t.key === key);
  const allTools = useMemo(() => {
    const base = cat.data?.tools ?? [];
    const out = [...base];
    for (const e of EXTRA_TOOLS) {
      if (out.some((t) => t.key === e.key)) continue;
      const idx = out.findIndex((t) => t.category !== e.category && out.some((x) => x.category === e.category));
      out.splice(idx < 0 ? out.length : idx, 0, e);
    }
    return out;
  }, [cat.data]);
  const render = CALCS[key];

  return (
    <div className="pb-16">
      <section className="relative isolate overflow-hidden bg-brand-gradient text-white">
        <div aria-hidden className="absolute inset-0 -z-10 bg-mesh opacity-70" />
        <div aria-hidden className="absolute -end-16 -top-16 -z-10 h-64 w-64 rounded-full bg-gold-400/25 blur-3xl" />
        <div className="container py-8 sm:py-10">
          <Breadcrumbs light crumbs={[{ label: "Home", to: "/" }, { label: "Tools", to: "/tools" }, { label: tool?.name ?? titleCase(key) }]} />
          <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center">
            <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
              <ToolIcon toolKey={key} category={tool?.category} size="lg" className="ring-4 ring-white/15" />
            </motion.div>
            <div className="min-w-0 flex-1">
              {tool ? (
                <>
                  <h1 className="font-display text-3xl font-bold sm:text-4xl">{tool.name}</h1>
                  <p className="mt-1 max-w-2xl text-white/75">{tool.blurb}</p>
                </>
              ) : one.isLoading || cat.isLoading ? (
                <Skeleton className="h-16 w-80 bg-white/10" />
              ) : (
                <h1 className="font-display text-3xl font-bold">{titleCase(key)}</h1>
              )}
            </div>
            {tool && (
              <div className="flex flex-wrap gap-2">
                <Badge tone={phaseTone(tool.phase)}>Phase {tool.phase}</Badge>
                {tool.mcp_tool && (
                  <span className="chip bg-white/10 font-mono text-[11px] text-gold-200 ring-1 ring-white/15">
                    <Cpu className="h-3 w-3" /> {tool.mcp_tool}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      <div className="container mt-6 grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
        <aside className="space-y-4 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto lg:pe-1">
          <ButtonLink to="/tools" variant="ghost" size="sm" icon={<ArrowLeft className="h-4 w-4 rtl:rotate-180" />} className="hidden lg:inline-flex">
            All tools
          </ButtonLink>
          {cat.isLoading ? <Skeleton className="h-96" /> : <Rail tools={allTools} current={key} />}
        </aside>

        <main className="min-w-0 space-y-6">
          {render ? (
            render()
          ) : tool ? (
            <GenericTool tool={tool} />
          ) : one.isLoading ? (
            <Skeleton className="h-96" />
          ) : (
            <EmptyState title="Tool not found" hint={`There is no tool called “${key}”.`} action={<ButtonLink to="/tools">Browse tools</ButtonLink>} />
          )}
          <div className="grid gap-5 md:grid-cols-2">
            <SavedProjects toolKey={key} />
            <Card className="h-fit">
              <CardBody className="flex gap-3 text-xs text-ink-mute">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-gold-500" />
                Indicative figures for planning and comparison. Statutory rates and Islamic-calendar dates change — confirm with the district office and official announcements before relying on them.
              </CardBody>
            </Card>
          </div>
        </main>
      </div>
    </div>
  );
}
